"""Write-back test utilities for the BuildOps connector.

Creates bills through ``POST /v2/bills`` so the write -> read -> verify cycle
can be exercised against a (non-production) BuildOps tenant.

Extra connection options (test-only; ignored by the connector itself):

* ``test_vendor_id``     -- UUID of an existing vendor in the tenant.
* ``test_department_id`` -- UUID of an existing department in the tenant.

Both are required by ``CreateBillDto`` and must already exist; add them to the
JSON passed through ``CONNECTOR_TEST_CONFIG_JSON`` / ``CONNECTOR_TEST_CONFIG_PATH``.

Handing created ids to the read side
------------------------------------
``bills`` is a snapshot table read strictly by id (the API has no list
endpoint), so a freshly created bill is only visible if its id is part of the
``bill_ids`` table option. Every id created by ``generate_rows_and_write`` is
recorded on the instance (``created_bill_ids``); the connector test class
should merge them into the table options it hands to the connector::

    class TestBuildOpsConnector(LakeflowConnectWriteBackTests, LakeflowConnectTests):
        ...
        def _opts(self, table):
            opts = super()._opts(table)
            if getattr(self, "test_utils", None) is not None:
                opts = self.test_utils.with_created_bill_ids(table, opts)
            return opts

The harness calls ``_opts`` before and after the write in
``test_incremental_after_write``, so the post-write snapshot read contains
exactly one more bill than the pre-write read, as the suite expects. The
``dev_table_config.json`` (or equivalent) must still list at least one
pre-existing bill id so that reads made before any write succeed.

``cleanup()`` deletes every bill created by this instance; call it from the
test class's ``teardown_class`` if leftover fixtures are unwanted.
"""

import time
import uuid
from typing import Dict, List, Tuple

from databricks.labs.community_connector.sources.buildops.buildops_client import (
    BuildOpsClient,
)
from databricks.labs.community_connector.sources.buildops.buildops_schemas import (
    BILL_PATH,
    BILLS_PATH,
    DEFAULT_BASE_URL,
)
from tests.unit.sources.lakeflow_connect_test_utils import (
    LakeflowConnectWriteTestUtils as _BaseWriteTestUtils,
)

# Seconds to wait after creating bills before they are read back.
WRITE_SETTLE_SECONDS = 2


class LakeflowConnectWriteTestUtils(_BaseWriteTestUtils):
    """BuildOps write-back utilities (bills only)."""

    def __init__(self, options: Dict[str, str]) -> None:
        super().__init__(options)
        self._client = BuildOpsClient(
            client_id=str(options.get("client_id", "")),
            client_secret=str(options.get("client_secret", "")),
            tenant_id=str(options.get("tenant_id", "")),
            base_url=str(options.get("base_url") or DEFAULT_BASE_URL),
        )
        self._vendor_id = str(options.get("test_vendor_id") or "").strip()
        self._department_id = str(options.get("test_department_id") or "").strip()
        self.created_bill_ids: List[str] = []

    # ------------------------------------------------------------------
    # LakeflowConnectWriteTestUtils interface
    # ------------------------------------------------------------------

    def list_insertable_tables(self) -> List[str]:
        return ["bills"]

    def generate_rows_and_write(
        self, table_name: str, number_of_rows: int
    ) -> Tuple[bool, List[Dict], Dict[str, str]]:
        if table_name not in self.list_insertable_tables():
            return False, [], {}
        if not self._vendor_id or not self._department_id:
            raise ValueError(
                "BuildOps write-back tests need the 'test_vendor_id' and "
                "'test_department_id' options (UUIDs of an existing vendor and "
                "department in the test tenant)."
            )

        written_rows: List[Dict] = []
        for _ in range(number_of_rows):
            tag = uuid.uuid4().hex[:12]
            payload = {
                # Client-supplied id (CreateBillDto.id, honoured by the live
                # API): lets the live spec validator's simulated POST create
                # the same id, so the follow-up GET validates against it.
                "id": str(uuid.uuid4()),
                "vendorId": self._vendor_id,
                "departmentId": self._department_id,
                "description": f"lakeflow_test_bill_{tag}",
                "vendorDocumentNumber": f"LFTEST-{tag}",
            }
            resp = self._client.request("POST", BILLS_PATH, json=payload)
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"POST {BILLS_PATH} failed (HTTP {resp.status_code}): "
                    f"{resp.text[:500]}"
                )
            created = resp.json()
            bill_id = created.get("id") if isinstance(created, dict) else None
            if not bill_id:
                raise RuntimeError(
                    f"POST {BILLS_PATH} response did not include an 'id': "
                    f"{resp.text[:500]}"
                )
            self.created_bill_ids.append(str(bill_id))
            written_rows.append(
                {
                    "id": str(bill_id),
                    "description": payload["description"],
                    "vendorDocumentNumber": payload["vendorDocumentNumber"],
                    "vendorId": payload["vendorId"],
                    "departmentId": payload["departmentId"],
                }
            )

        if written_rows:
            time.sleep(WRITE_SETTLE_SECONDS)

        column_mapping = {
            "id": "id",
            "description": "description",
            "vendorDocumentNumber": "vendorDocumentNumber",
        }
        return True, written_rows, column_mapping

    # ------------------------------------------------------------------
    # Helpers for the connector test class
    # ------------------------------------------------------------------

    def with_created_bill_ids(self, table_name: str, table_options: Dict) -> Dict:
        """Return a copy of ``table_options`` whose ``bill_ids`` also lists
        every bill created by this instance (no-op for other tables)."""
        opts = dict(table_options or {})
        if table_name != "bills" or not self.created_bill_ids:
            return opts
        existing = [
            s.strip() for s in str(opts.get("bill_ids") or "").split(",") if s.strip()
        ]
        merged = list(dict.fromkeys(existing + self.created_bill_ids))
        opts["bill_ids"] = ",".join(merged)
        return opts

    def cleanup(self) -> None:
        """Best-effort delete of every bill created by this instance."""
        remaining: List[str] = []
        for bill_id in self.created_bill_ids:
            try:
                resp = self._client.request("DELETE", BILL_PATH.format(bill_id=bill_id))
                if resp.status_code not in (200, 204, 404):
                    remaining.append(bill_id)
            except Exception:  # pylint: disable=broad-except
                remaining.append(bill_id)
        self.created_bill_ids = remaining
