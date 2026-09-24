"""BuildOps source connector."""

from databricks.labs.community_connector.sources.buildops.buildops import (
    BuildOpsLakeflowConnect,
)
from databricks.labs.community_connector.sparkpds import LakeflowSource


class BuildOpsDataSource(LakeflowSource):
    _lakeflow_connect_cls = BuildOpsLakeflowConnect
    # Override the Spark format name with the source name once this no
    # longer relies on UC connection-option injection. Kept as the default
    # "lakeflow_connect" for now so existing pipelines keep working.
    # _format_name = "buildops"


__all__ = ["BuildOpsLakeflowConnect",
    "BuildOpsDataSource",
]
