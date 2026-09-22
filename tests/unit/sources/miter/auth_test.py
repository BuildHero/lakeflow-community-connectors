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
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from tests.unit.sources.test_utils import load_config

BASE_URL = "https://api.staging.miter.com/api/v2"

CONFIG_PATH = pathlib.Path(__file__).parent / "configs" / "dev_config.json"

# Pytest collects this file (``python_files`` includes ``*_test.py``), but the
# check only means anything when credentials are actually present. Gate it the
# same way the other connectors' auth-verification tests do — see
# ``tests/unit/sources/dicomweb/test_auth_verify.py`` — so the default
# credential-free, simulator-backed run stays green instead of erroring out of
# ``load_config``.
pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("CONNECTOR_TEST_CONFIG_JSON", "").strip()
        or os.environ.get("CONNECTOR_TEST_CONFIG_PATH", "").strip()
        or CONFIG_PATH.exists()
    ),
    reason="no Miter credentials supplied — skipping live auth check",
)


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


def _verify() -> "tuple[int, str]":
    """Call GET /ping and return (status_code, diagnostic_message).

    Shared by the pytest entry point (which asserts on the status code)
    and the ``__main__`` script entry point (which maps it to an exit
    code) so the two can't drift into reporting different outcomes.
    """
    # Honors CONNECTOR_TEST_CONFIG_JSON / _PATH, then the local dev_config.json.
    config = load_config(CONFIG_PATH)

    api_token = config["api_token"]
    headers = {"Authorization": f"Bearer {api_token}"}

    status_code, body_text = _curl_get(f"{BASE_URL}/ping", headers=headers, timeout=10)

    try:
        body = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        body = None

    if status_code == 200:
        data = (body or {}).get("data", {})
        message = (
            "Authentication successful! Connected to Miter.\n"
            f"   company_id: {data.get('company_id')}\n"
            f"   token_name: {data.get('token_name')}\n"
            f"   scopes: {data.get('scopes')}\n"
            f"   rate_limits: {data.get('rate_limits')}"
        )
    elif status_code == 401:
        message = (
            "Authentication failed: Invalid or revoked token (HTTP 401).\n"
            f"   Body: {body_text}\n"
            "   Check the api_token supplied via CONNECTOR_TEST_CONFIG_JSON / "
            "CONNECTOR_TEST_CONFIG_PATH."
        )
    elif status_code == 403:
        message = (
            "Authorization failed: Token lacks required scope (HTTP 403).\n"
            f"   Body: {body_text}"
        )
    else:
        message = f"Unexpected response: HTTP {status_code}\n   Body: {body_text}"

    print(message)
    return status_code, message


def test_auth():
    """Verify supplied credentials are valid by calling GET /ping."""
    status_code, message = _verify()
    assert status_code == 200, message


if __name__ == "__main__":
    _status_code, _message = _verify()
    sys.exit(0 if _status_code == 200 else 1)
