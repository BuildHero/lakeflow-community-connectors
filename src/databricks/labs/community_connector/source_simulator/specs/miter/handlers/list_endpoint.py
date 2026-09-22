"""Custom simulator handler for Miter's uniform ``GET`` list endpoints.

Every Miter v2 list endpoint behaves identically, and three of its
behaviours fall outside the declarative pipeline in ``handler.py``:

1. **Two-level envelope with a sibling flag.** The response is
   ``{"success": true, "data": {"size": N, "next_page": <id|null>,
   "results": [...]}}``. ``response.wrapper.extras`` can only inject keys
   *next to* ``results`` (inside ``data``), so a declarative spec cannot
   emit the top-level ``success`` key — and the live validator would then
   report ``success`` as drift on every endpoint.

2. **Opaque id cursor, not an offset.** ``data.next_page`` is the
   ``id`` of the last record on the page; the client passes it back as
   ``page=<id>`` to resume *after* that record. Verified against
   ``api.staging.miter.com`` (``limit=2`` over 5 line items yielded
   ``next_page`` == last id of each page, ``null`` on the final page).
   None of the registered pagination styles model this.

3. **Sparse fieldsets and strict params.** ``output_fields`` restricts
   the payload to the named top-level fields with ``id`` always added
   back, and an undeclared query param is rejected with
   ``400 {"success": false, "error": "Unrecognized key: \\"...\\""}``.

The range filters (``sort[after_exclusive]`` &co.) apply to whichever
field ``sort[field]`` selects, so the handler reads the *ops* from the
spec's declared ``filter`` params and resolves the *field* per request —
keeping ``endpoints.yaml`` the single place where param roles live.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from requests.models import PreparedRequest, Response

from databricks.labs.community_connector.source_simulator.cassette import (
    ResponseRecord,
)
from databricks.labs.community_connector.source_simulator.corpus import (
    apply_sort,
    get_field,
)
from databricks.labs.community_connector.source_simulator.endpoint_spec import (
    EndpointSpec,
    FilterOp,
)
from databricks.labs.community_connector.source_simulator.interceptor import (
    request_record_from_prepared,
    response_from_record,
)

# ``limit`` accepts 1-1000 and defaults to 100 (OpenAPI spec + API doc).
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000

# ``sort[field]`` defaults to ``updated_at``, ``sort[direction]`` to
# ``descending`` — both per the API doc's "Uniform list pattern".
_DEFAULT_SORT_FIELD = "updated_at"
_DEFAULT_SORT_DIRECTION = "descending"

_ASCENDING = "ascending"


def serve_list(prep: PreparedRequest, spec: EndpointSpec, corpus: Any) -> Response:
    """Serve one Miter list request from the corpus."""
    req = request_record_from_prepared(prep)
    query = req.query

    if spec.strict_params:
        unknown = sorted(set(query) - spec.known_param_names())
        if unknown:
            return _error(prep, 400, f'Unrecognized key: "{unknown[0]}"')

    # ``inject_future_records`` (run once at simulator boot for specs that
    # declare ``synthesize_future_records``) has already appended the
    # cap-validation clones to this list in place.
    records = corpus.get(spec.corpus) or []
    if not isinstance(records, list):
        raise ValueError(
            f"Corpus for {spec.corpus!r} is not a list, but endpoint "
            f"{spec.method} {spec.path} returns an array."
        )

    sort_field, ascending = _resolve_sort(spec, query)
    selected = _apply_range_filters(records, spec, query, sort_field)
    selected = apply_sort(
        selected, sort_field=sort_field, sort_order="asc" if ascending else "desc"
    )

    page, next_page = _paginate(selected, query, spec)
    page = [_project(r, query.get("output_fields")) for r in page]

    return _ok(
        prep,
        {
            "success": True,
            "data": {"size": len(page), "next_page": next_page, "results": page},
        },
    )


# ----- request handling --------------------------------------------------


def _resolve_sort(spec: EndpointSpec, query: Dict[str, str]) -> Tuple[str, bool]:
    """Return ``(sort_field, ascending)`` for this request."""
    sort_field = _DEFAULT_SORT_FIELD
    direction = _DEFAULT_SORT_DIRECTION
    if spec.response.default_sort is not None:
        sort_field, declared = spec.response.default_sort
        direction = _ASCENDING if declared == "asc" else _DEFAULT_SORT_DIRECTION

    if spec.sort_by is not None:
        candidate = query.get(spec.sort_by.name)
        if candidate and (
            not spec.sort_by.options or candidate in spec.sort_by.options
        ):
            sort_field = candidate
    if spec.sort_order is not None:
        candidate = (query.get(spec.sort_order.name) or "").lower()
        if candidate in spec.sort_order.options:
            direction = candidate

    return sort_field, direction == _ASCENDING


def _apply_range_filters(
    records: List[Dict[str, Any]],
    spec: EndpointSpec,
    query: Dict[str, str],
    sort_field: str,
) -> List[Dict[str, Any]]:
    """Bound records by the ``sort[before_*]`` / ``sort[after_*]`` params.

    Miter's range params constrain whichever field ``sort[field]``
    selects, so the comparison field comes from the request while the
    comparison operator comes from the spec's declared param role.
    """
    out = list(records)
    for fp in spec.filters:
        raw = query.get(fp.name)
        if raw is None:
            continue
        out = [r for r in out if _in_range(get_field(r, sort_field), raw, fp.op)]
    return out


def _in_range(value: Any, bound: str, op: FilterOp) -> bool:
    """Compare an ISO-8601 timestamp string against a bound.

    Miter emits millisecond-precision UTC timestamps (``...T05:31:47.085Z``)
    but accepts bounds at any ISO precision, so the two are normalised
    before the lexicographic comparison that ISO-8601 makes valid.
    """
    if not isinstance(value, str):
        return False
    left = _normalize_iso(value)
    right = _normalize_iso(bound)
    if op == FilterOp.GT:
        return left > right
    if op == FilterOp.GTE:
        return left >= right
    if op == FilterOp.LT:
        return left < right
    if op == FilterOp.LTE:
        return left <= right
    if op == FilterOp.EQ:
        return left == right
    if op == FilterOp.NE:
        return left != right
    return False


def _normalize_iso(value: str) -> str:
    """Pad an ISO-8601 UTC timestamp to millisecond precision.

    ``2026-09-18T05:31:47Z`` and ``2026-09-18T05:31:47.000Z`` denote the
    same instant but do not compare equal as strings.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1]
    if text.endswith("+00:00"):
        text = text[: -len("+00:00")]
    if "." in text:
        head, _, frac = text.partition(".")
        return f"{head}.{frac[:3].ljust(3, '0')}"
    return f"{text}.000"


def _paginate(
    records: List[Dict[str, Any]], query: Dict[str, str], spec: EndpointSpec
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Slice one page and compute the next opaque cursor.

    ``page`` carries the ``id`` of the last record of the previous page;
    the page served starts at the record *after* it. A cursor that no
    longer resolves (record filtered out or deleted between calls) yields
    an empty terminal page rather than silently restarting from the top.
    """
    limit = _resolve_limit(query, spec)
    start = 0
    cursor = query.get(spec.page.name) if spec.page is not None else None
    if cursor:
        index = next(
            (i for i, r in enumerate(records) if str(r.get("id")) == cursor), None
        )
        if index is None:
            return [], None
        start = index + 1

    page = records[start : start + limit]
    has_more = start + len(page) < len(records)
    next_page = str(page[-1].get("id")) if page and has_more else None
    return page, next_page


def _resolve_limit(query: Dict[str, str], spec: EndpointSpec) -> int:
    default = spec.limit.default if spec.limit is not None else _DEFAULT_LIMIT
    maximum = spec.limit.max if spec.limit is not None else _MAX_LIMIT
    name = spec.limit.name if spec.limit is not None else "limit"
    raw = query.get(name)
    if raw is None:
        return default
    try:
        return max(1, min(int(raw), maximum))
    except (TypeError, ValueError):
        return default


def _project(record: Dict[str, Any], output_fields: Optional[str]) -> Dict[str, Any]:
    """Apply an ``output_fields`` sparse fieldset. ``id`` is always kept."""
    if not output_fields:
        return record
    wanted = {f.strip() for f in output_fields.split(",") if f.strip()}
    wanted.add("id")
    return {k: v for k, v in record.items() if k in wanted}


# ----- response building -------------------------------------------------


def _ok(prep: PreparedRequest, payload: Dict[str, Any]) -> Response:
    return _build(prep, 200, payload)


def _error(prep: PreparedRequest, status: int, message: str) -> Response:
    """Miter's uniform error envelope: ``{"success": false, "error": ...}``."""
    return _build(prep, status, {"success": False, "error": message})


def _build(prep: PreparedRequest, status: int, payload: Dict[str, Any]) -> Response:
    body = json.dumps(payload, ensure_ascii=False)
    rec = ResponseRecord(
        status_code=status,
        headers={"Content-Type": "application/json"},
        body_text=body,
        body_b64=None,
        encoding="utf-8",
        url=prep.url,
    )
    return response_from_record(rec, prep)
