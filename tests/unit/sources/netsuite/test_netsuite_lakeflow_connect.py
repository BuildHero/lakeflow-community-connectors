from databricks.labs.community_connector.sources.netsuite.netsuite import (
    NetsuiteLakeflowConnect,
)
from tests.unit.sources.test_suite import LakeflowConnectTests


class TestNetsuiteConnector(LakeflowConnectTests):
    connector_class = NetsuiteLakeflowConnect
    simulator_source = "netsuite"
    sample_records = 50

    # Stand-in credentials for simulate mode -- the simulator never
    # validates them, so any string of the right shape works.
    replay_config = {
        "account_id": "1234567_SB1",
        "consumer_key": "simulator-consumer-key",
        "consumer_secret": "simulator-consumer-secret",
        "token_id": "simulator-token-id",
        "token_secret": "simulator-token-secret",
    }
