"""Minimal XML request/response helpers for the Sage Intacct XML Gateway.

The XML Gateway (``xmlgw.phtml``) is a single-endpoint RPC-style API: every
call is an HTTP POST of an XML "envelope" to the same URL, and the *function*
being invoked (``getAPISession``, ``query``, ``readMore``, ...) is embedded
in the body rather than expressed via the URL or method. These helpers build
request envelopes and parse response envelopes using the stdlib
``xml.etree.ElementTree`` (no extra dependency needed).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from xml.sax.saxutils import escape

DTD_VERSION = "3.0"

# Intacct's wire format for date/timestamp fields, e.g. "09/23/2026 00:00:00".
_INTACCT_DT_FORMAT = "%m/%d/%Y %H:%M:%S"
_INTACCT_DATE_FORMAT = "%m/%d/%Y"


class IntacctApiError(RuntimeError):
    """Raised when the XML Gateway returns a failure status."""


class IntacctSessionExpiredError(IntacctApiError):
    """Raised when the cached session id is no longer valid."""


def to_intacct_timestamp(iso_str: str) -> str:
    """Convert an internal ISO-8601 cursor value to Intacct's wire format."""
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime(_INTACCT_DT_FORMAT)


def from_intacct_timestamp(value: str) -> str:
    """Convert an Intacct ``WHENMODIFIED``-style value to an ISO-8601 string.

    Intacct returns timestamps as ``mm/dd/yyyy hh:mm:ss``, which does not
    sort lexically. Internally we always keep cursors as ISO-8601 so plain
    string comparison ("did the cursor advance?") remains correct.
    """
    value = (value or "").strip()
    if not value:
        return value
    for fmt in (_INTACCT_DT_FORMAT, _INTACCT_DATE_FORMAT):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    # Unrecognized format -- pass through rather than fail the whole batch.
    return value


def build_login_envelope(
    *,
    sender_id: str,
    sender_password: str,
    control_id: str,
    user_id: str,
    company_id: str,
    user_password: str,
    location_id: str | None,
    function_xml: str,
) -> str:
    location_xml = f"<locationid>{escape(location_id)}</locationid>" if location_id else ""
    auth_xml = (
        "<login>"
        f"<userid>{escape(user_id)}</userid>"
        f"<companyid>{escape(company_id)}</companyid>"
        f"<password>{escape(user_password)}</password>"
        f"{location_xml}"
        "</login>"
    )
    return _build_envelope(
        sender_id=sender_id,
        sender_password=sender_password,
        control_id=control_id,
        auth_xml=auth_xml,
        function_xml=function_xml,
    )


def build_session_envelope(
    *,
    sender_id: str,
    sender_password: str,
    control_id: str,
    session_id: str,
    function_xml: str,
) -> str:
    auth_xml = f"<sessionid>{escape(session_id)}</sessionid>"
    return _build_envelope(
        sender_id=sender_id,
        sender_password=sender_password,
        control_id=control_id,
        auth_xml=auth_xml,
        function_xml=function_xml,
    )


def _build_envelope(
    *,
    sender_id: str,
    sender_password: str,
    control_id: str,
    auth_xml: str,
    function_xml: str,
) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<request>"
        "<control>"
        f"<senderid>{escape(sender_id)}</senderid>"
        f"<password>{escape(sender_password)}</password>"
        f"<controlid>{escape(control_id)}</controlid>"
        "<uniqueid>false</uniqueid>"
        f"<dtdversion>{DTD_VERSION}</dtdversion>"
        "<includewhitespace>false</includewhitespace>"
        "</control>"
        "<operation>"
        f"<authentication>{auth_xml}</authentication>"
        "<content>"
        f'<function controlid="{escape(control_id)}_fn">{function_xml}</function>'
        "</content>"
        "</operation>"
        "</request>"
    )


def get_api_session_function_xml() -> str:
    return "<getAPISession/>"


def query_function_xml(
    *,
    object_name: str,
    fields: list[str],
    filter_xml: str,
    pagesize: int,
    offset: int,
) -> str:
    select_xml = "".join(f"<field>{escape(f)}</field>" for f in fields)
    return (
        "<query>"
        f"<object>{escape(object_name)}</object>"
        f"<select>{select_xml}</select>"
        f"{filter_xml}"
        "<orderby><order><field>WHENMODIFIED</field><ascending/></order></orderby>"
        f"<pagesize>{pagesize}</pagesize>"
        f"<offset>{offset}</offset>"
        "</query>"
    )


def range_filter_xml(field: str, since: str | None, until: str | None) -> str:
    """Build a ``<filter>`` block bounding ``field`` by [since, until)."""
    conditions = []
    if since:
        conditions.append(
            f"<greaterthanorequalto><field>{escape(field)}</field>"
            f"<value>{escape(since)}</value></greaterthanorequalto>"
        )
    if until:
        conditions.append(
            f"<lessthan><field>{escape(field)}</field>"
            f"<value>{escape(until)}</value></lessthan>"
        )
    if not conditions:
        return ""
    if len(conditions) == 1:
        return f"<filter>{conditions[0]}</filter>"
    return f"<filter><and>{''.join(conditions)}</and></filter>"


def parse_response(xml_text: str) -> dict:
    """Parse a response envelope into a small, function-agnostic dict.

    Returns a dict with keys:
        status: "success" | "failure"
        auth_status: "success" | "failure" | None
        error_message: str | None (joined description text, on failure)
        session_id: str | None (only present for getAPISession)
        session_endpoint: str | None
        records: list[dict] (flat field-name -> text, only for query/readMore)
        count / totalcount / numremaining: int (only for query/readMore)
        result_id: str | None
    """
    root = ET.fromstring(xml_text)

    auth_status_el = root.find("./operation/authentication/status")
    auth_status = auth_status_el.text if auth_status_el is not None else None

    result_el = root.find("./operation/result")
    if result_el is None:
        # Authentication itself failed before any function ran.
        return {
            "status": "failure",
            "auth_status": auth_status or "failure",
            "error_message": _extract_error(root),
            "session_id": None,
            "session_endpoint": None,
            "records": [],
            "count": 0,
            "totalcount": 0,
            "numremaining": 0,
            "result_id": None,
        }

    status_el = result_el.find("./status")
    status = status_el.text if status_el is not None else "failure"

    parsed = {
        "status": status,
        "auth_status": auth_status,
        "error_message": None,
        "session_id": None,
        "session_endpoint": None,
        "records": [],
        "count": 0,
        "totalcount": 0,
        "numremaining": 0,
        "result_id": None,
    }

    if status != "success":
        parsed["error_message"] = _extract_error(result_el)
        return parsed

    data_el = result_el.find("./data")
    if data_el is None:
        return parsed

    # getAPISession shape: <data><api><sessionid/><endpoint/></api></data>
    api_el = data_el.find("./api")
    if api_el is not None:
        sid = api_el.find("./sessionid")
        endpoint = api_el.find("./endpoint")
        parsed["session_id"] = sid.text if sid is not None else None
        parsed["session_endpoint"] = endpoint.text if endpoint is not None else None
        return parsed

    # query/readMore shape: <data listtype="OBJ" count="N" totalcount="M"
    #   numremaining="K" resultId="...">child records</data>
    parsed["count"] = int(data_el.get("count", "0") or "0")
    parsed["totalcount"] = int(data_el.get("totalcount", "0") or "0")
    parsed["numremaining"] = int(data_el.get("numremaining", "0") or "0")
    parsed["result_id"] = data_el.get("resultId")

    records = []
    for record_el in list(data_el):
        record = {child.tag: child.text for child in list(record_el)}
        records.append(record)
    parsed["records"] = records

    return parsed


def _extract_error(el: ET.Element) -> str:
    parts = [t.text for t in el.iter() if t.tag in ("description", "description2", "correction") and t.text]
    if parts:
        return " | ".join(parts)
    err = el.find(".//error")
    if err is not None and err.text:
        return err.text
    return "Unknown Intacct API error"
