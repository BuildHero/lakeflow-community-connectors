"""Custom simulator handlers for the BuildOps public API.

* ``serve_token``  -- POST /v1/auth/token: stub client-credentials token.
* ``get_bill``     -- GET /v2/bills/{billId}: look the bill up by ``id`` in the
  ``bills`` corpus; 404 when absent (mirrors the live API).
* ``create_bill``  -- POST /v2/bills: build a live-shaped bill from the
  CreateBillDto body, append it to the in-memory corpus and return it (201).
* ``delete_bill``  -- DELETE /v2/bills/{billId}: remove from the corpus (204).

Behaviour mirrored from the live dev API (validated 2026-09-24):

* Corpus records carry every key, including the include-gated ones. GET only
  returns an include-gated key when it was requested; otherwise the key is
  absent from the body entirely (not null).
* ``include`` must be ONE comma-separated value (``include=vendor,job``).
  The repeated-key form (``include=vendor&include=job``) returns 200 but is
  ignored -- no relation is embedded. Unknown values return 400.
* Error bodies are NestJS-style ``{path, name, message}`` objects (the live
  ``path`` reports ``/v1/bills/...`` even for v2 calls).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlsplit

from requests.models import PreparedRequest, Response

from databricks.labs.community_connector.source_simulator.cassette import (
    ResponseRecord,
)
from databricks.labs.community_connector.source_simulator.interceptor import (
    response_from_record,
)

_CORPUS_KEY = "bills"

# Keys GET /v2/bills/{billId} only returns when named in ``include``, with the
# value served when the corpus record lacks one.
_INCLUDE_DEFAULTS: Dict[str, Any] = {
    "billLines": [],
    "addresses": [],
    "vendorDocumentAttachment": None,
    "purchaseOrder": None,
    "purchaseOrderReceipt": None,
    "vendor": None,
    "job": None,
    "project": None,
    "department": None,
    "orderedBy": None,
    "projectManager": None,
    "assignedTo": None,
    "approvalNoteBy": None,
    "paymentTerm": None,
    "taxRate": None,
}

# Non-gated keys of a live bill body, with the server-side defaults a freshly
# created bill gets (observed on POST /v2/bills responses).
_BILL_DEFAULTS: Dict[str, Any] = {
    "invoicedStatus": "NotInvoiced",
    "isImported": False,
    "isStandalone": False,
    "version": 1,
    "approvalStatus": "Unreviewed",
    "id": None,
    "tenantId": None,
    "tenantCompanyId": None,
    "transactionDate": None,
    "description": None,
    "freight": None,
    "totalAmountPreTax": 0,
    "tax": 0,
    "addedBy": None,
    "accountingRefIdOfClass": None,
    "purchaseOrderId": None,
    "purchaseOrderReceiptId": None,
    "departmentId": None,
    "taxRateId": None,
    "taxRegionId": None,
    "isUseTaxable": False,
    "useTaxTotal": 0,
    "vendorId": None,
    "jobId": None,
    "projectId": None,
    "billNumber": None,
    "uniqueBillNumber": None,
    "customIdentifier": None,
    "vendorDocumentNumber": None,
    "vendorDocumentAttachmentId": None,
    "orderedById": None,
    "issuedBy": None,
    "postingDate": None,
    "dueDate": None,
    "totalCost": 0,
    "taxAmountOverridden": None,
    "isReceiptBound": None,
    "syncLog": None,
    "syncStatus": None,
    "accountingVersion": None,
    "approvalNote": None,
    "approvalNoteById": None,
    "approvalNoteDateTime": None,
    "projectManagerId": None,
    "paymentTermId": None,
    "assignedToId": None,
    "accountingRefId": None,
    "status": "Pending",
    "isCreatedFromMobile": False,
    "createdByEmployeeId": None,
    "amountDue": None,
    "defaultRetainagePercent": None,
    "isRetainageApplicable": None,
    "isRetainageBill": None,
    "retainageAmountUnbilled": None,
    "totalRetainageAmount": None,
    "parentBillId": None,
    "vendorLocationId": None,
    "vendorContactId": None,
    "billToAddressId": None,
    "shipToAddressId": None,
    "shipFromAddressId": None,
    "audit": None,
}

# CreateBillDto fields the live API drops on create (server-managed).
_IGNORED_ON_CREATE = frozenset({"transactionDate"})


def _json_response(prep: PreparedRequest, status_code: int, body: Any) -> Response:
    rec = ResponseRecord(
        status_code=status_code,
        headers={"Content-Type": "application/json"} if body is not None else {},
        body_text=json.dumps(body) if body is not None else "",
        body_b64=None,
        encoding="utf-8",
        url=prep.url,
    )
    return response_from_record(rec, prep)


def _error(prep: PreparedRequest, status_code: int, name: str, message: str) -> Response:
    parts = urlsplit(prep.url or "")
    path = parts.path.replace("/v2/", "/v1/", 1)
    if parts.query:
        path = f"{path}?{parts.query}"
    return _json_response(
        prep, status_code, {"path": path, "name": name, "message": message}
    )


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


def _parse_include(prep: PreparedRequest) -> Tuple[List[str], Optional[str]]:
    """Return ``(requested include keys, invalid value or None)``.

    Mirrors the live API: a repeated ``include`` key is ignored wholesale;
    a single value is split on commas.
    """
    values = [
        v
        for k, v in parse_qsl(urlsplit(prep.url or "").query, keep_blank_values=True)
        if k == "include"
    ]
    if len(values) != 1:
        return [], None
    requested = [p.strip() for p in values[0].split(",") if p.strip()]
    for name in requested:
        if name not in _INCLUDE_DEFAULTS:
            return [], name
    return requested, None


def _render_bill(record: Dict[str, Any], include: List[str]) -> Dict[str, Any]:
    body = {k: v for k, v in record.items() if k not in _INCLUDE_DEFAULTS}
    for name in include:
        body[name] = record.get(name, _INCLUDE_DEFAULTS[name])
    return body


def _now() -> Tuple[int, str]:
    now = datetime.now(timezone.utc)
    return int(now.timestamp() * 1000), now.strftime("%Y-%m-%dT%H:%M:%SZ")


def serve_token(prep: PreparedRequest, spec, corpus) -> Response:  # noqa: ARG001
    return _json_response(
        prep,
        200,
        {
            "access_token": "sim-buildops-access-token",
            "token_type": "bearer",
            "expires_in": 10800,
        },
    )


def get_bill(prep: PreparedRequest, spec, corpus) -> Response:
    include, invalid = _parse_include(prep)
    if invalid is not None:
        return _error(
            prep,
            400,
            "BadRequestException",
            f'Property "{invalid}" is not a valid property',
        )
    bill_id = _path_bill_id(prep, spec)
    for record in _bills(corpus):
        if isinstance(record, dict) and str(record.get("id")) == bill_id:
            return _json_response(prep, 200, _render_bill(record, include))
    return _error(prep, 404, "NotFoundException", "Bill not found")


def _find_vendor(corpus, vendor_id: Any) -> Optional[Dict[str, Any]]:
    for record in _bills(corpus):
        vendor = record.get("vendor") if isinstance(record, dict) else None
        if isinstance(vendor, dict) and vendor.get("id") == vendor_id:
            return vendor
    return None


def create_bill(prep: PreparedRequest, spec, corpus) -> Response:  # noqa: ARG001
    body = _request_json(prep)
    missing = [k for k in ("departmentId", "vendorId") if not body.get(k)]
    if missing:
        return _error(
            prep,
            400,
            "BadRequestException",
            ", ".join(f"{k} should not be empty" for k in missing),
        )

    now_ms, _ = _now()
    bill_id = str(body.get("id") or uuid.uuid4())
    tenant_id = prep.headers.get("tenantId") if prep.headers else None
    bill_number = f"B{len(_bills(corpus)) + 1000}"
    audit = {
        "createdBy": {"username": "simulator"},
        "createdDate": None,
        "createdDateTime": now_ms,
        "lastUpdatedBy": {"username": "simulator"},
        "lastUpdatedDate": None,
        "lastUpdatedDateTime": now_ms,
        "deletedBy": {"username": None},
        "deletedDate": None,
        "deletedDateTime": None,
    }
    record: Dict[str, Any] = dict(_BILL_DEFAULTS)
    record.update(
        {
            "id": bill_id,
            "tenantId": tenant_id,
            "tenantCompanyId": tenant_id,
            "billNumber": bill_number,
            "uniqueBillNumber": bill_number,
            "customIdentifier": f"PO-D{bill_number}",
            "orderedById": str(uuid.uuid4()),
            "audit": audit,
        }
    )
    lines = body.pop("billLines", None) or []
    addresses = body.pop("addresses", None) or []
    for key, value in body.items():
        if key not in _IGNORED_ON_CREATE and key in _BILL_DEFAULTS:
            record[key] = value
    record["id"] = bill_id
    record["billLines"] = [
        {
            **line,
            "id": str(line.get("id") or uuid.uuid4()),
            "billId": bill_id,
            "tenantId": tenant_id,
            "audit": dict(audit),
        }
        for line in lines
        if isinstance(line, dict)
    ]
    record["addresses"] = [a for a in addresses if isinstance(a, dict)]
    record["vendorDocumentAttachment"] = None
    record["vendor"] = _find_vendor(corpus, record.get("vendorId"))
    _bills(corpus).append(record)

    # The live POST response embeds billLines, vendor and purchaseOrder but
    # none of the other include-gated keys.
    response = _render_bill(record, ["billLines", "purchaseOrder", "vendor"])
    return _json_response(prep, 201, response)


def delete_bill(prep: PreparedRequest, spec, corpus) -> Response:
    bill_id = _path_bill_id(prep, spec)
    records = _bills(corpus)
    for i, record in enumerate(records):
        if isinstance(record, dict) and str(record.get("id")) == bill_id:
            del records[i]
            return _json_response(prep, 204, None)
    return _error(prep, 404, "NotFoundException", "Bill not found")
