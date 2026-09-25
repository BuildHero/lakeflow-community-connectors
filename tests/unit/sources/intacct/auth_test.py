"""
Auth verification test for Sage Intacct connector.
Run this script to verify your credentials are correctly configured.

Sage Intacct uses the XML Gateway ("Intacct Web Services"), a two-layer
auth scheme: sender (application) credentials in every request's
<control> block, plus a company/user session obtained via the
getAPISession function. There is no OAuth/bearer token for this API.

Usage:
    # via env var (inline JSON):
    CONNECTOR_TEST_CONFIG_JSON='{"sender_id":"...","sender_password":"...",...}' \\
        python tests/unit/sources/intacct/auth_test.py

    # via env var (path to a JSON file at any location):
    CONNECTOR_TEST_CONFIG_PATH=~/secrets/intacct.json \\
        python tests/unit/sources/intacct/auth_test.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from tests.unit.sources.test_utils import load_config
import requests

from databricks.labs.community_connector.sources.intacct.intacct_xml import (
    build_login_envelope,
    build_session_envelope,
    get_api_session_function_xml,
    parse_response,
    query_function_xml,
)

DEFAULT_XMLGW_URL = "https://api.intacct.com/ia/xml/xmlgw.phtml"


def _post(url: str, envelope: str) -> str:
    response = requests.post(
        url,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "application/xml"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Intacct API HTTP {response.status_code}: {response.text[:500]}")
    return response.text


def test_auth() -> bool:
    """Verify supplied credentials are valid via getAPISession + a trivial read."""
    config = load_config()  # honors CONNECTOR_TEST_CONFIG_JSON / _PATH env vars

    base_url = config.get("base_url") or DEFAULT_XMLGW_URL

    # --- Step 1: obtain a session (validates sender + user/company creds) ---
    login_envelope = build_login_envelope(
        sender_id=config["sender_id"],
        sender_password=config["sender_password"],
        control_id="auth_verify_session",
        user_id=config["user_id"],
        company_id=config["company_id"],
        user_password=config["user_password"],
        location_id=config.get("location_id") or None,
        function_xml=get_api_session_function_xml(),
    )

    try:
        session_xml = _post(base_url, login_envelope)
    except requests.exceptions.RequestException as e:
        print(f"Network error while contacting Intacct XML Gateway: {e}")
        return False

    parsed = parse_response(session_xml)

    if parsed.get("auth_status") == "failure" or parsed["status"] != "success" or not parsed.get("session_id"):
        print("Authentication failed: could not obtain an API session.")
        print(f"   auth_status={parsed.get('auth_status')!r} status={parsed.get('status')!r}")
        print(f"   error: {parsed.get('error_message')}")
        print("   Check sender_id/sender_password (control block) and "
              "user_id/company_id/user_password (login block).")
        return False

    print("Session obtained successfully (getAPISession).")
    session_id = parsed["session_id"]
    session_endpoint = parsed.get("session_endpoint") or base_url

    # --- Step 2: a lightweight read to confirm the session is actually usable ---
    read_envelope = build_session_envelope(
        sender_id=config["sender_id"],
        sender_password=config["sender_password"],
        control_id="auth_verify_read",
        session_id=session_id,
        function_xml=query_function_xml(
            object_name="CUSTOMER",
            fields=["RECORDNO"],
            filter_xml="",
            pagesize=1,
            offset=0,
        ),
    )

    try:
        read_xml = _post(session_endpoint, read_envelope)
    except requests.exceptions.RequestException as e:
        print(f"Network error while contacting Intacct XML Gateway: {e}")
        return False

    read_parsed = parse_response(read_xml)

    if read_parsed["status"] != "success":
        print("Session obtained, but a lightweight read (query CUSTOMER, pagesize=1) failed.")
        print(f"   error: {read_parsed.get('error_message')}")
        print("   This suggests a permissions issue (module/object access) rather than "
              "bad sender/user credentials.")
        return False

    print("Authentication successful! Connected to Sage Intacct and read CUSTOMER.")
    print(f"   Records returned: {len(read_parsed.get('records', []))}")
    return True


if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)
