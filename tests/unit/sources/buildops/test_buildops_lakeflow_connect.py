from databricks.labs.community_connector.source_simulator import MODE_SIMULATE
from databricks.labs.community_connector.sources.buildops.buildops import (
    BuildOpsLakeflowConnect,
)
from databricks.labs.community_connector.sources.buildops.buildops_schemas import (
    BILL_INCLUDE_VALUES,
)
from tests.unit.sources.buildops.buildops_test_utils import LakeflowConnectWriteTestUtils
from tests.unit.sources.test_suite import (
    LakeflowConnectTests,
    _resolve_env_mode_for_simulator,
)
from tests.unit.sources.test_write_back_suite import LakeflowConnectWriteBackTests

# Ids of the bills in the simulator corpus
# (source_simulator/specs/buildops/corpus/bills.json), seeded from a live dev
# recording. The BuildOps API has no list endpoint, so the connector reads
# bills strictly by id. For live runs, put real bill ids in
# configs/dev_table_config.json instead.
_CORPUS_BILL_IDS = [
    "355d6063-5bc2-4f39-8629-1de2a9c15b5b",  # live dev seed bill
    "a08b2cbd-60ff-457f-9528-d59ca559424c",  # live write-back bill (no include)
    "8bde8c3d-d1be-43a6-9aba-14265526b406",  # live write-back bill (include=all)
    "7f1c3b9e-2d4a-4e8b-9a61-5c0d8e2f4b17",  # live-shaped, every field populated
]


class TestBuildOpsConnector(LakeflowConnectWriteBackTests, LakeflowConnectTests):
    connector_class = BuildOpsLakeflowConnect
    test_utils_class = LakeflowConnectWriteTestUtils
    simulator_source = "buildops"
    sample_records = 5
    # Stand-in credentials; the simulator never validates them.
    replay_config = {
        "client_id": "sim-client-id",
        "client_secret": "sim-client-secret",
        "tenant_id": "00000000-0000-4000-8000-000000000001",
        "base_url": "https://public-api.dev.buildops.com",
        "test_vendor_id": "00000000-0000-4000-8000-00000000a001",
        "test_department_id": "00000000-0000-4000-8000-00000000d001",
    }

    @classmethod
    def _load_table_configs(cls):
        # Simulate mode always reads the corpus bills with every include
        # relation requested: billLines / addresses / vendorDocumentAttachment
        # and the relation objects are include-gated (absent from the GET body
        # unless requested), so this exercises the include path and keeps the
        # column-coverage invariant meaningful. Live runs use
        # dev_table_config.json.
        if _resolve_env_mode_for_simulator(cls.simulator_source) == MODE_SIMULATE:
            return {
                "bills": {
                    "bill_ids": ",".join(_CORPUS_BILL_IDS),
                    "include": ",".join(BILL_INCLUDE_VALUES),
                }
            }
        return super()._load_table_configs()

    @classmethod
    def teardown_class(cls):
        test_utils = getattr(cls, "test_utils", None)
        if test_utils is not None and test_utils.created_bill_ids:
            try:
                test_utils.cleanup()
            except Exception:  # pylint: disable=broad-except
                pass
        super().teardown_class()

    def _opts(self, table):
        opts = super()._opts(table)
        if getattr(self, "test_utils", None) is not None:
            opts = self.test_utils.with_created_bill_ids(table, opts)
        return opts
