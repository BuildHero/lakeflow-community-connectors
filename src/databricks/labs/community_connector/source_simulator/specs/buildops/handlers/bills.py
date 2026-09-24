"""Custom simulator handlers for the BuildOps public API.

* ``serve_token``  -- POST /v1/auth/token: stub client-credentials token.
* ``get_bill``     -- GET /v2/bills/{billId}: look the bill up by ``id`` in the
  ``bills`` corpus; 404 when absent (mirrors the live API).
* ``create_bill``  -- POST /v2/bills: build a PublicBillResponseDto-shaped
  record from the CreateBillDto body, append it to the in-memory corpus and
  return it with 201.
* ``delete_bill``  -- DELETE /v2/bills/{billId}: remove from the corpus.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit

from requests.models import PreparedRequest, Response

from databricks.labs.community_connector.source_simulator.cassette import (
    ResponseRecord,
)
from databricks.labs.community_connector.source_simulator.interceptor import (
    response_from_record,
)

_CORPUS_KEY = "bills"


def _json_response(prep: PreparedRequest, status_code: int, body: Any) -> Response:
    rec = ResponseRecord(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        body_text=json.dumps(body) if body is not None else "",
        body_b64=None,
        encoding="utf-8",
        url=prep.url,
    )
    return response_from_record(rec, prep)


def _path_bill_id(prep: PreparedRequest, spec) -> Optional[str]:
    m = spec.path_regex.match(urlsplit(prep.url or "").path)
    if not m:
        return None
    raw = m.groupdict().get("billId")
    return unquote(raw) if raw is not None else None


def _bills(corpus) -> List[Dict[str, Any]]:
    records = corpus.get(_CORPUS_KEY)
    if not isinstance(records, list):
        records = []
        corpus.tables[_CORPUS_KEY] = records
    return records


def _request_json(prep: PreparedRequest) -> Dict[str, Any]:
    body = prep.body
    if body is None:
        return {}
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def serve_token(prep: PreparedRequest, spec, corpus) -> Response:  # noqa: ARG001
    return _json_response(
        prep,
        200,
        {
            "access_token": "sim-buildops-access-token",
            "expires_in": 86400,
            "token_type": "Bearer",
        },
    )


def get_bill(prep: PreparedRequest, spec, corpus) -> Response:
    bill_id = _path_bill_id(prep, spec)
    for record in _bills(corpus):
        if isinstance(record, dict) and str(record.get("id")) == bill_id:
            return _json_response(prep, 200, record)
    return _json_response(
        prep, 404, {"error": "Not Found", "message": f"Bill {bill_id} not found"}
    )


def create_bill(prep: PreparedRequest, spec, corpus) -> Response:  # noqa: ARG001
    body = _request_json(prep)
    missing = [k for k in ("vendorId", "departmentId") if not body.get(k)]
    if missing:
        return _json_response(
            prep,
            400,
            {"error": "Bad Request", "message": f"Missing required field(s): {missing}"},
        )

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ms = int(now.timestamp() * 1000)
    bill_id = str(body.get("id") or uuid.uuid4())
    audit = {
        "createdBy": None,
        "createdDate": now_iso,
        "createdDateTime": now_ms,
        "lastUpdatedBy": None,
        "lastUpdatedDate": now_iso,
        "lastUpdatedDateTime": str(now_ms),
        "deletedBy": None,
        "deletedDate": None,
        "deletedDateTime": None,
    }
    record: Dict[str, Any] = {
        "id": bill_id,
        "tenantId": prep.headers.get("tenantId") if prep.headers else None,
        "audit": audit,
        "billLines": [],
        "transactionDate": int(time.time()),
        "billNumber": f"BILL-{now_ms}",
        "description": "",
        "addedBy": "simulator",
        "vendorDocumentNumber": "",
        "orderedById": str(uuid.uuid4()),
        "isImported": False,
        "status": "Pending",
    }
    lines = body.pop("billLines", None) or []
    record.update(body)
    record["id"] = bill_id
    record["billLines"] = [
        {
            **line,
            "id": str(line.get("id") or uuid.uuid4()),
            "billId": bill_id,
            "audit": dict(audit),
        }
        for line in lines
        if isinstance(line, dict)
    ]
    _bills(corpus).append(record)
    return _json_response(prep, 201, record)


def delete_bill(prep: PreparedRequest, spec, corpus) -> Response:
    bill_id = _path_bill_id(prep, spec)
    records = _bills(corpus)
    for i, record in enumerate(records):
        if isinstance(record, dict) and str(record.get("id")) == bill_id:
            del records[i]
            return _json_response(prep, 200, {"id": bill_id})
    return _json_response(
        prep, 404, {"error": "Not Found", "message": f"Bill {bill_id} not found"}
    )
