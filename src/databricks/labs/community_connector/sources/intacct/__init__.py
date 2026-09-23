"""Sage Intacct source connector."""

from databricks.labs.community_connector.sources.intacct.intacct import (
    IntacctLakeflowConnect,
)


from databricks.labs.community_connector.sparkpds import LakeflowSource


class IntacctDataSource(LakeflowSource):
    _lakeflow_connect_cls = IntacctLakeflowConnect


__all__ = [
    "IntacctLakeflowConnect",
    "IntacctDataSource",
]
