"""Live authentication verification for the NetSuite TBA connector.

Loads credentials (via ``load_config``, never hardcoded/printed) and issues
one minimal SuiteQL request through the connector's own TBA-signing helper
(``run_suiteql`` in ``netsuite_utils.py``) to confirm the credentials
authenticate against a real NetSuite account. Skips (rather than fails)
when no live credentials are configured, so it is a no-op in a normal CI
run without credentials.

Run with:
    CONNECTOR_TEST_CONFIG_PATH=tests/unit/sources/netsuite/configs/dev_config.json \
        .venv/bin/python -m pytest tests/unit/sources/netsuite/test_auth_verify.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

from databricks.labs.community_connector.sources.netsuite.netsuite_utils import (
    run_suiteql,
)
from tests.unit.sources.test_utils import load_config

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "dev_config.json"

# Simplest possible read-only SuiteQL call: just confirms the request is
# accepted and returns rows, without depending on the full vendorbill
# column set the connector queries at runtime.
_PROBE_QUERY = "SELECT id FROM transaction WHERE type = 'VendBill'"

_REQUIRED_FIELDS = [
    "account_id",
    "consumer_key",
    "consumer_secret",
    "token_id",
    "token_secret",
]


def _load_config_or_skip() -> dict:
    """Load live credentials, or skip the test if none are configured.

    Mirrors ``load_config``'s own precedence (inline JSON env var, then a
    path env var, then the default on-disk config), but skips instead of
    raising when none of those resolve -- this is a live-only check, and
    the default CI run (simulate mode, no credentials) has nothing to
    verify.
    """
    has_inline = bool(os.environ.get("CONNECTOR_TEST_CONFIG_JSON", "").strip())
    has_path_env = bool(os.environ.get("CONNECTOR_TEST_CONFIG_PATH", "").strip())
    if not (has_inline or has_path_env or _DEFAULT_CONFIG_PATH.exists()):
        pytest.skip(
            "No live NetSuite credentials found. Set CONNECTOR_TEST_CONFIG_PATH "
            "or CONNECTOR_TEST_CONFIG_JSON, or place a config at "
            f"{_DEFAULT_CONFIG_PATH}, to run the live TBA auth check."
        )
    return load_config(default_path=_DEFAULT_CONFIG_PATH)


def test_auth_verify():
    config = _load_config_or_skip()

    missing = [k for k in _REQUIRED_FIELDS if not config.get(k)]
    assert not missing, f"Config is missing required field(s): {missing}"

    account_id = config["account_id"]
    # Same account_id -> hostname transform as NetsuiteLakeflowConnect.__init__:
    # "1234567_SB1" -> "1234567-sb1.suitetalk.api.netsuite.com".
    host_account = account_id.lower().replace("_", "-")
    base_url = f"https://{host_account}.suitetalk.api.netsuite.com"

    session = requests.Session()

    try:
        result = run_suiteql(
            session,
            base_url=base_url,
            account_id=account_id,
            consumer_key=config["consumer_key"],
            consumer_secret=config["consumer_secret"],
            token_id=config["token_id"],
            token_secret=config["token_secret"],
            query=_PROBE_QUERY,
            limit=1,
            offset=0,
        )
    except RuntimeError as e:
        message = str(e)
        status = None
        for code in (401, 403, 404, 500, 502, 503):
            if f"status {code}" in message:
                status = code
                break

        if status == 401:
            diagnosis = (
                "401 Unauthorized -- credentials are likely wrong/revoked "
                "(bad consumer key/secret or token id/secret)."
            )
        elif status == 403:
            diagnosis = (
                "403 Forbidden -- credentials authenticated but lack "
                "permission (role missing SuiteQL / REST Web Services "
                "permission, or REST Web Services feature not enabled on "
                "the account)."
            )
        else:
            diagnosis = "See status code and error text above for diagnosis."

        pytest.fail(
            f"SuiteQL request did not succeed. {diagnosis}\nError detail: {message}"
        )
        return

    items = result.get("items", [])
    print(
        "PASS: NetSuite TBA authentication succeeded (HTTP 200). "
        f"Rows returned by probe query: {len(items)}"
    )
