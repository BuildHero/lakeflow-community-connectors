from databricks.labs.community_connector.sources.buildops.buildops import (
    BuildOpsLakeflowConnect,
)
from tests.unit.sources.buildops.buildops_test_utils import LakeflowConnectWriteTestUtils
from tests.unit.sources.test_suite import LakeflowConnectTests
from tests.unit.sources.test_write_back_suite import LakeflowConnectWriteBackTests

# Ids of the bills in the synthesized simulator corpus
# (source_simulator/specs/buildops/corpus/bills.json). The BuildOps API has no
# list endpoint, so the connector reads bills strictly by id. For live runs,
# put real bill ids in configs/dev_table_config.json instead.
_CORPUS_BILL_IDS = [
    "tango-45-pk0",
    "oscar-43-pk1",
    "whiskey--pk2",
    "echo-772-pk3",
    "yankee-9-pk4",
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
        # dev_table_config.json (live runs) wins; otherwise point at the
        # corpus bill ids so simulate-mode reads have something to fetch.
        configs = super()._load_table_configs()
        if not configs:
            configs = {"bills": {"bill_ids": ",".join(_CORPUS_BILL_IDS)}}
        return configs

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
