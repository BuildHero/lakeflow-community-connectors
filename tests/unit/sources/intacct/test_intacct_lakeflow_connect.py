from databricks.labs.community_connector.sources.intacct.intacct import (
    IntacctLakeflowConnect,
)
from tests.unit.sources.test_suite import LakeflowConnectTests


class TestIntacctConnector(LakeflowConnectTests):
    connector_class = IntacctLakeflowConnect
    simulator_source = "intacct"
    sample_records = 100

    # Stand-in credentials for simulate mode -- the simulator's custom
    # xmlgw handler never validates these (it always returns an
    # authentication success block), so any string of the right shape
    # works. See source_simulator/specs/intacct/handlers/xmlgw.py.
    replay_config = {
        "sender_id": "simulator-sender",
        "sender_password": "simulator-sender-password",
        "user_id": "simulator-user",
        "user_password": "simulator-user-password",
        "company_id": "simulator-company",
    }
