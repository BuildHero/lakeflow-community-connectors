"""
Auth verification test for Miter connector.
Run this script to verify your credentials are correctly configured.

Usage:
    # via env var (inline JSON):
    CONNECTOR_TEST_CONFIG_JSON='{"api_token":"..."}' \\
        python tests/unit/sources/miter/auth_test.py

    # via env var (path to a JSON file at any location):
    CONNECTOR_TEST_CONFIG_PATH=tests/unit/sources/miter/configs/dev_config.json \\
        python tests/unit/sources/miter/auth_test.py

Note: the actual HTTPS request is issued via the system `curl` binary rather
than the `requests` library. In some sandboxed dev environments, `requests`
(via certifi) cannot read its bundled CA cert file due to filesystem
restrictions, while `curl` verifies TLS using the OS trust store and is
unaffected. This keeps the test runnable in both plain and sandboxed shells.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from tests.unit.sources.test_utils import load_config

BASE_URL = "https://api.staging.miter.com/api/v2"


def _curl_get(url: str, headers: dict, timeout: int = 10):
    """GET a URL via curl, returning (status_code, body_text).

    Avoids the `requests`/certifi CA-bundle file read, which is blocked in
    some sandboxed shells; curl verifies TLS via the OS trust store instead.
    """
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-w", "\n%{http_code}"]
    for key, value in headers.items():
        cmd += ["-H", f"{key}: {value}"]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr.strip()}")

    output = result.stdout
    body, _, status_code = output.rpartition("\n")
    return int(status_code), body


def test_auth():
    """Verify supplied credentials are valid by calling GET /ping."""
    config = load_config()  # honors CONNECTOR_TEST_CONFIG_JSON / _PATH env vars

    api_token = config["api_token"]
    headers = {"Authorization": f"Bearer {api_token}"}

    status_code, body_text = _curl_get(f"{BASE_URL}/ping", headers=headers, timeout=10)

    try:
        body = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        body = None

    if status_code == 200:
        data = (body or {}).get("data", {})
        print("Authentication successful! Connected to Miter.")
        print(f"   company_id: {data.get('company_id')}")
        print(f"   token_name: {data.get('token_name')}")
        print(f"   scopes: {data.get('scopes')}")
        print(f"   rate_limits: {data.get('rate_limits')}")
        return True
    elif status_code == 401:
        print("Authentication failed: Invalid or revoked token (HTTP 401).")
        print(f"   Body: {body_text}")
        print("   Check the api_token supplied via CONNECTOR_TEST_CONFIG_JSON / "
              "CONNECTOR_TEST_CONFIG_PATH.")
        return False
    elif status_code == 403:
        print("Authorization failed: Token lacks required scope (HTTP 403).")
        print(f"   Body: {body_text}")
        return False
    else:
        print(f"Unexpected response: HTTP {status_code}")
        print(f"   Body: {body_text}")
        return False


if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)
