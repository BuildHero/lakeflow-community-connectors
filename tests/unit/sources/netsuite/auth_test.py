"""Live authentication verification for the NetSuite TBA connector.

Not a unit test collected by pytest -- a standalone script that loads
credentials (via ``load_config``, never hardcoded/printed) and issues one
minimal SuiteQL request through the connector's own TBA-signing helper
(``run_suiteql`` in ``netsuite_utils.py``) to confirm the credentials
authenticate against a real NetSuite account.

Usage:
    CONNECTOR_TEST_CONFIG_PATH=tests/unit/sources/netsuite/configs/dev_config.json \
        python tests/unit/sources/netsuite/auth_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (``python .../auth_test.py``) as well as
# as a module (``python -m tests.unit.sources.netsuite.auth_test``) -- the
# direct-script form doesn't put the repo root on sys.path by default, which
# is otherwise needed to import the ``tests`` and ``databricks`` packages.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from databricks.labs.community_connector.sources.netsuite.netsuite_utils import (
    run_suiteql,
)
from tests.unit.sources.test_utils import load_config

# Simplest possible read-only SuiteQL call: just confirms the request is
# accepted and returns rows, without depending on the full vendorbill
# column set the connector queries at runtime.
_PROBE_QUERY = "SELECT id FROM transaction WHERE type = 'VendBill'"


def main() -> int:
    config = load_config(
        default_path="tests/unit/sources/netsuite/configs/dev_config.json"
    )

    required = ["account_id", "consumer_key", "consumer_secret", "token_id", "token_secret"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(f"FAIL: config is missing required field(s): {missing}")
        return 1

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
            diagnosis = "401 Unauthorized -- credentials are likely wrong/revoked (bad consumer key/secret or token id/secret)."
        elif status == 403:
            diagnosis = "403 Forbidden -- credentials authenticated but lack permission (role missing SuiteQL / REST Web Services permission, or REST Web Services feature not enabled on the account)."
        else:
            diagnosis = "See status code and error text above for diagnosis."

        print(f"FAIL: SuiteQL request did not succeed. {diagnosis}")
        print(f"Error detail: {message}")
        return 1

    items = result.get("items", [])
    row_count = len(items)
    print("PASS: NetSuite TBA authentication succeeded (HTTP 200).")
    print(f"Rows returned by probe query: {row_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
