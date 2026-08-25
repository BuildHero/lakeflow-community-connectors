"""Custom simulator handler for NetSuite's POST ``/services/rest/query/v1/suiteql``.

SuiteQL's filtering lives entirely inside a free-text SQL string in the
JSON request body (``{"q": "SELECT ... WHERE lastmodifieddate >= ..."}``),
not in URL query params -- the simulator's declarative param-role pipeline
matches on query params/headers, so it can't express this. This handler:

  1. Parses the request body for the ``q`` SQL text.
  2. Extracts the ``lastmodifieddate >= TO_DATE('...')`` /
     ``lastmodifieddate < TO_DATE('...')`` window bounds the connector
     embeds (see ``netsuite.py::_read_vendorbill_window``), if present.
     A query without either bound (the connector's auto-discovery "peek
     oldest" call) is treated as unbounded.
  3. Filters + sorts the ``vendorbill`` corpus by that window.
  4. Paginates via the ``limit``/``offset`` URL query-string params (a
     real difference from the body-driven filter -- this matches
     NetSuite's actual SuiteQL contract).
  5. Renders the ``{links, count, hasMore, items, offset, totalResults}``
     envelope documented in ``netsuite_api_doc.md``.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from requests.models import PreparedRequest, Response

from databricks.labs.community_connector.source_simulator.cassette import (
    ResponseRecord,
)
from databricks.labs.community_connector.source_simulator.interceptor import (
    response_from_record,
)

_CORPUS_NAME = "vendorbill"
_CURSOR_FIELD = "lastmodifieddate"

_SINCE_RE = re.compile(r"lastmodifieddate\s*>=\s*TO_DATE\('([^']+)'")
_UNTIL_RE = re.compile(r"lastmodifieddate\s*<\s*TO_DATE\('([^']+)'")


def suiteql(prep: PreparedRequest, spec: Any, corpus: Any) -> Response:  # noqa: ARG001
    body = _parse_body(prep.body)
    query = body.get("q") or ""

    since_match = _SINCE_RE.search(query)
    until_match = _UNTIL_RE.search(query)
    since = since_match.group(1) if since_match else None
    until = until_match.group(1) if until_match else None

    records = corpus.get(_CORPUS_NAME) or []
    if not isinstance(records, list):
        records = []

    filtered = [r for r in records if _in_window(r, since, until)]
    filtered.sort(key=lambda r: r.get(_CURSOR_FIELD) or "")

    offset, limit = _parse_pagination(prep.url or "")
    page = filtered[offset : offset + limit]
    has_more = offset + len(page) < len(filtered)

    payload: dict[str, Any] = {
        "links": [],
        "count": len(page),
        "hasMore": has_more,
        "items": page,
        "offset": offset,
        "totalResults": len(filtered),
    }
    return _build_response(prep, status=200, payload=payload)


def _in_window(record: dict[str, Any], since: str | None, until: str | None) -> bool:
    value = record.get(_CURSOR_FIELD)
    if value is None:
        return False
    if since is not None and value < since:
        return False
    if until is not None and value >= until:
        return False
    return True


def _parse_pagination(url: str) -> tuple[int, int]:
    query = parse_qs(urlparse(url).query)
    offset = int(query.get("offset", ["0"])[0])
    limit = int(query.get("limit", ["1000"])[0])
    return offset, limit


def _parse_body(body: Any) -> dict[str, Any]:
    if body is None:
        return {}
    if isinstance(body, (bytes, bytearray)):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return {}
    else:
        text = str(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_response(prep: PreparedRequest, *, status: int, payload: dict[str, Any]) -> Response:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    rec = ResponseRecord(
        status_code=status,
        headers={"Content-Type": "application/json"},
        body_text=body.decode("utf-8"),
        body_b64=None,
        encoding="utf-8",
        url=prep.url,
    )
    return response_from_record(rec, prep)
