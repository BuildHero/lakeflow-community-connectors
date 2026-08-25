"""NetSuite source connector."""

from databricks.labs.community_connector.sources.netsuite.netsuite import (
    NetsuiteLakeflowConnect,
)


from databricks.labs.community_connector.sparkpds import LakeflowSource


class NetsuiteDataSource(LakeflowSource):
    _lakeflow_connect_cls = NetsuiteLakeflowConnect
    # Override the Spark format name with the source name once this no
    # longer relies on UC connection-option injection. Kept as the default
    # "lakeflow_connect" for now so existing pipelines keep working.
    # _format_name = "netsuite"


__all__ = [
    "NetsuiteLakeflowConnect",
    "NetsuiteDataSource",
]
