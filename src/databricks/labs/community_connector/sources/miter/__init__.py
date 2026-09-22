"""Miter source connector."""

from databricks.labs.community_connector.sources.miter.miter import (
    MiterLakeflowConnect,
)


from databricks.labs.community_connector.sparkpds import LakeflowSource


class MiterDataSource(LakeflowSource):
    _lakeflow_connect_cls = MiterLakeflowConnect
    # Override the Spark format name with the source name once this no
    # longer relies on UC connection-option injection. Kept as the default
    # "lakeflow_connect" for now so existing pipelines keep working.
    # _format_name = "miter"


__all__ = ["MiterLakeflowConnect",
    "MiterDataSource",
]
