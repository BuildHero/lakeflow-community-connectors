"""Custom simulator handler for Sage Intacct's XML Gateway (``xmlgw.phtml``).

The XML Gateway is a single-endpoint, XML-RPC-style API: every function
(``getAPISession``, ``query``, ...) is an HTTP POST of an XML envelope to
the *same* URL, with the function name and its arguments embedded in the
body -- not expressed via the URL path or query string. This doesn't fit
the simulator's declarative per-param ``role:`` model (built around URL
query params), so the whole endpoint is served by this one custom handler,
which parses the request envelope and dispatches on the embedded function
name. See ``endpoints.yaml`` for why a handler is used here.

Functions handled (the only two ``IntacctLakeflowConnect`` calls):
    - ``getAPISession`` -- returns a fixed simulated session id/endpoint.
    - ``query`` -- filters the corpus by the ``WHENMODIFIED`` range clause,
      sorts ascending, and paginates via ``<pagesize>``/``<offset>``,
      mirroring the real Gateway's ``<data count totalcount numremaining>``
      response shape.

Cap-validation records: the handler appends a few future-dated
``WHENMODIFIED`` clones to each object's corpus on every ``query`` call.
This mirrors the declarative ``synthesize_future_records`` spec directive,
which only fires in the generic filter/sort/paginate pipeline -- custom
handlers bypass that pipeline entirely, so the synthesis has to happen
here (same pattern as ``specs/adme/handlers/search.py``). A connector that
correctly caps its window at ``self._init_ts`` (see
``IntacctLakeflowConnect._read_incremental_by_window``) will never request
-- and therefore never see -- these records; a connector that leaks its
cap will fetch them, and the termination test will detect non-convergence.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from xml.sax.saxutils import escape

from requests.models import PreparedRequest, Response

from databricks.labs.community_connector.source_simulator.cassette import (
    ResponseRecord,
)
from databricks.labs.community_connector.source_simulator.interceptor import (
    response_from_record,
)

_SESSION_ID = "SIMULATED-SESSION-ID"

# Mirrors intacct_schemas.TABLE_TO_OBJECT (inverted). Duplicated rather
# than imported so this simulator spec stays self-contained, matching the
# pattern of every other custom handler in source_simulator/specs/.
_OBJECT_TO_TABLE = {
    "CUSTOMER": "customers",
    "VENDOR": "vendors",
    "ARINVOICE": "invoices",
    "APBILL": "bills",
    "GLDETAIL": "gl_entries",
}

_CURSOR_FIELD = "WHENMODIFIED"
_PRIMARY_KEY_FIELD = "RECORDNO"
_FUTURE_RECORDS = 3
_DEFAULT_PAGESIZE = 100


def serve_xmlgw(prep: PreparedRequest, spec: Any, corpus: Any) -> Response:  # noqa: ARG001
    body = _decode_body(prep.body)
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return _error_response(prep, f"malformed request XML: {e}")

    function_el = root.find(".//content/function")
    if function_el is None or len(function_el) == 0:
        return _error_response(prep, "no <function> element found in request")
    call_el = function_el[0]
    fn_name = call_el.tag

    if fn_name == "getAPISession":
        return _serve_get_api_session(prep)
    if fn_name == "query":
        return _serve_query(prep, call_el, corpus)

    return _error_response(prep, f"unhandled function: {fn_name}")


def _serve_get_api_session(prep: PreparedRequest) -> Response:
    inner = (
        "<result><status>success</status>"
        "<function>getAPISession</function>"
        "<data><api>"
        f"<sessionid>{_SESSION_ID}</sessionid>"
        f"<endpoint>{escape(prep.url or '')}</endpoint>"
        "</api></data></result>"
    )
    return _envelope(prep, inner)


def _serve_query(prep: PreparedRequest, query_el: ET.Element, corpus: Any) -> Response:
    object_el = query_el.find("./object")
    object_name = object_el.text if object_el is not None and object_el.text else None
    table_name = _OBJECT_TO_TABLE.get(object_name or "")
    if table_name is None:
        return _error_response(prep, f"unknown object: {object_name}")

    fields = [f.text for f in query_el.findall("./select/field") if f.text]

    pagesize_el = query_el.find("./pagesize")
    offset_el = query_el.find("./offset")
    pagesize = (
        int(pagesize_el.text) if pagesize_el is not None and pagesize_el.text else _DEFAULT_PAGESIZE
    )
    offset = int(offset_el.text) if offset_el is not None and offset_el.text else 0

    since, until = _extract_range(query_el)

    records = corpus.get(table_name) or []
    if not isinstance(records, list):
        records = []
    records = _augment_with_future(records)

    matched = [r for r in records if _in_range(r, since, until)]
    matched.sort(key=_cursor_sort_key)

    page = matched[offset : offset + pagesize]
    numremaining = max(0, len(matched) - offset - len(page))

    records_xml = "".join(_record_to_xml(object_name, r, fields) for r in page)
    inner = (
        "<result><status>success</status>"
        "<function>query</function>"
        f'<data listtype="{escape(object_name)}" count="{len(page)}" '
        f'totalcount="{len(matched)}" numremaining="{numremaining}">'
        f"{records_xml}</data></result>"
    )
    return _envelope(prep, inner)


# ---------------------------------------------------------------------------
# filter / sort helpers
# ---------------------------------------------------------------------------


def _extract_range(query_el: ET.Element) -> tuple[datetime | None, datetime | None]:
    """Parse the connector's WHENMODIFIED [since, until) filter, if present.

    Matches the two shapes ``IntacctLakeflowConnect`` sends: a bare
    ``<greaterthanorequalto>`` (peek call has no filter at all), or an
    ``<and>`` of ``<greaterthanorequalto>`` + ``<lessthan>`` (sliding
    window). Only ``WHENMODIFIED`` is ever filtered by this connector.
    """
    filter_el = query_el.find("./filter")
    if filter_el is None:
        return None, None
    and_el = filter_el.find("./and")
    scope = and_el if and_el is not None else filter_el

    since = _condition_dt(scope, "greaterthanorequalto")
    if since is None:
        since = _condition_dt(scope, "greaterthan")
    until = _condition_dt(scope, "lessthan")
    if until is None:
        until = _condition_dt(scope, "lessthanorequalto")
    return since, until


def _condition_dt(scope: ET.Element, tag: str) -> datetime | None:
    el = scope.find(f"./{tag}")
    if el is None:
        return None
    field = el.findtext("field")
    if field != _CURSOR_FIELD:
        return None
    return _wire_to_dt(el.findtext("value"))


def _in_range(record: dict, since: datetime | None, until: datetime | None) -> bool:
    dt = _parse_corpus_datetime(record.get(_CURSOR_FIELD))
    if dt is None:
        return since is None and until is None
    if since is not None and dt < since:
        return False
    if until is not None and dt >= until:
        return False
    return True


def _cursor_sort_key(record: dict) -> datetime:
    return _parse_corpus_datetime(record.get(_CURSOR_FIELD)) or datetime.min


def _augment_with_future(records: list) -> list:
    """Append a few future-``WHENMODIFIED`` clones for cap-validation tests.

    RECORDNO (the primary key) is an integer, so clones get a synthetic,
    guaranteed-unique RECORDNO rather than a string-suffixed one.
    """
    if not records:
        return records
    template = records[-1]
    max_recordno = 0
    for r in records:
        try:
            max_recordno = max(max_recordno, int(r.get(_PRIMARY_KEY_FIELD) or 0))
        except (TypeError, ValueError):
            continue

    base = datetime.now(timezone.utc) + timedelta(days=365)
    future = []
    for i in range(_FUTURE_RECORDS):
        clone = copy.deepcopy(template)
        clone[_PRIMARY_KEY_FIELD] = max_recordno + 100_000 + i
        clone[_CURSOR_FIELD] = (base + timedelta(hours=i)).isoformat().replace("+00:00", "Z")
        future.append(clone)
    return list(records) + future


# ---------------------------------------------------------------------------
# wire-format <-> corpus-value conversion
# ---------------------------------------------------------------------------


def _parse_corpus_datetime(value: Any) -> datetime | None:
    """Parse a corpus field value (ISO-8601, possibly ``Z``-suffixed) to a
    naive UTC ``datetime`` -- matching the precision the real wire format
    round-trips through (Intacct's own timestamps carry no explicit
    timezone offset)."""
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _wire_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _to_wire(value: Any) -> str | None:
    """Render a corpus value the way the real XML Gateway would.

    Booleans become ``true``/``false`` text; ISO-8601 date/timestamp
    strings become Intacct's ``mm/dd/yyyy`` / ``mm/dd/yyyy hh:mm:ss``;
    everything else passes through as-is (numbers/strings -- the
    connector's own normalization step handles those).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        dt = _parse_corpus_datetime(value)
        if dt is not None:
            # Heuristic: a bare "YYYY-MM-DD" (10 chars, no time component)
            # came from a DateType field -- render date-only.
            if len(value) <= 10:
                return dt.strftime("%m/%d/%Y")
            return dt.strftime("%m/%d/%Y %H:%M:%S")
        return value
    return str(value)


def _record_to_xml(object_name: str, record: dict, fields: list[str]) -> str:
    parts = []
    for f in fields:
        value = _to_wire(record.get(f))
        if value is None:
            parts.append(f"<{f}/>")
        else:
            parts.append(f"<{f}>{escape(str(value))}</{f}>")
    return f"<{object_name}>{''.join(parts)}</{object_name}>"


# ---------------------------------------------------------------------------
# envelope plumbing
# ---------------------------------------------------------------------------


def _decode_body(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, (bytes, bytearray)):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _envelope(prep: PreparedRequest, result_inner: str) -> Response:
    """Wrap a ``<result>...</result>`` block in the full response envelope.

    Always HTTP 200 -- the real XML Gateway signals functional failure
    inside the XML body (``<status>failure</status>``), not via HTTP
    status, and the simulator never validates auth headers/credentials
    (per source_simulator/DESIGN.md), so ``<authentication><status>`` is
    always success here.
    """
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<response><control><status>success</status></control>"
        "<operation><authentication><status>success</status></authentication>"
        f"{result_inner}</operation></response>"
    )
    rec = ResponseRecord(
        status_code=200,
        headers={"Content-Type": "application/xml"},
        body_text=body,
        body_b64=None,
        encoding="utf-8",
        url=prep.url,
    )
    return response_from_record(rec, prep)


def _error_response(prep: PreparedRequest, message: str) -> Response:
    inner = (
        "<result><status>failure</status>"
        f"<errormessage><error><description2>{escape(message)}</description2></error></errormessage>"
        "</result>"
    )
    return _envelope(prep, inner)
