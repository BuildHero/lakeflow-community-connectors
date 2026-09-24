"""BuildOps connector (public REST API).

Exposes a single snapshot table, ``bills``. The BuildOps public API has no
list endpoint for bills -- only ``GET /v2/bills/{billId}`` -- so the caller
supplies the set of bill ids through the required ``bill_ids`` table option
and every run re-reads each of them.

Connection options:
    client_id (required), client_secret (required), tenant_id (required),
    base_url (optional, default ``https://public-api.dev.buildops.com``).

Table options for ``bills``:
    bill_ids (required): comma-separated bill UUIDs.
    include (optional): comma-separated relation names to embed (see
        ``BILL_INCLUDE_VALUES``). ``billLines``, ``addresses`` and
        ``vendorDocumentAttachment`` populate their typed columns (the API
        omits them otherwise); every other relation becomes a JSON-string
        column.
"""

import json
from typing import Any, Iterator
from urllib.parse import quote

from pyspark.sql.types import ArrayType, DataType, StringType, StructType

from databricks.labs.community_connector.interface import LakeflowConnect
from databricks.labs.community_connector.sources.buildops.buildops_client import (
    BuildOpsAPIError,
    BuildOpsClient,
)
from databricks.labs.community_connector.sources.buildops.buildops_schemas import (
    BILL_INCLUDE_VALUES,
    BILL_PATH,
    DEFAULT_BASE_URL,
    SUPPORTED_TABLES,
    TABLE_METADATA,
    TABLE_SCHEMAS,
)

_INCLUDE_LOOKUP = {v.lower(): v for v in BILL_INCLUDE_VALUES}


def _split_csv(raw: Any) -> list[str]:
    """Split a comma-separated option into stripped, de-duplicated values."""
    if raw is None:
        return []
    seen: dict[str, None] = {}
    for part in str(raw).split(","):
        value = part.strip()
        if value:
            seen.setdefault(value, None)
    return list(seen)


def _prepare_value(value: Any, data_type: DataType) -> Any:
    """Make a raw API value safe for the framework's schema-driven parser.

    Only two structural adjustments are made; all type coercion is left to
    the framework:

    * a dict / list landing in a ``StringType`` column (undocumented nested
      objects such as ``vendor`` or ``audit.createdBy``) is JSON-encoded;
    * an empty dict landing in a ``StructType`` column becomes ``None``
      (the framework rejects ``{}`` for struct fields).
    """
    if value is None:
        return None
    if isinstance(data_type, StringType):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return value
    if isinstance(data_type, StructType):
        if not isinstance(value, dict):
            return value
        if not value:
            return None
        for field in data_type.fields:
            if field.name in value:
                value[field.name] = _prepare_value(value[field.name], field.dataType)
        return value
    if isinstance(data_type, ArrayType) and isinstance(value, list):
        return [_prepare_value(v, data_type.elementType) for v in value]
    return value


class BuildOpsLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for the BuildOps public API."""

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)
        missing = [
            key
            for key in ("client_id", "client_secret", "tenant_id")
            if not str(options.get(key) or "").strip()
        ]
        if missing:
            raise ValueError(
                f"BuildOps connector is missing required connection option(s): "
                f"{', '.join(missing)}."
            )
        base_url = str(options.get("base_url") or "").strip() or DEFAULT_BASE_URL
        self._client = BuildOpsClient(
            client_id=str(options["client_id"]).strip(),
            client_secret=str(options["client_secret"]).strip(),
            tenant_id=str(options["tenant_id"]).strip(),
            base_url=base_url,
        )

    # ------------------------------------------------------------------
    # LakeflowConnect interface
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return list(SUPPORTED_TABLES)

    def get_table_schema(self, table_name: str, table_options: dict[str, str]) -> StructType:
        self._validate_table(table_name)
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(self, table_name: str, table_options: dict[str, str]) -> dict:
        self._validate_table(table_name)
        return dict(TABLE_METADATA[table_name])

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        self._validate_table(table_name)
        bill_ids = self._parse_bill_ids(table_options)
        include = self._parse_include(table_options)
        # Snapshot: the whole table is returned in one batch with no offset.
        return self._iter_bills(bill_ids, include), None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_table(table_name: str) -> None:
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. Supported tables: {SUPPORTED_TABLES}"
            )

    @staticmethod
    def _parse_bill_ids(table_options: dict[str, str]) -> list[str]:
        bill_ids = _split_csv((table_options or {}).get("bill_ids"))
        if not bill_ids:
            raise ValueError(
                "Table 'bills' requires the 'bill_ids' table option: a "
                "comma-separated list of BuildOps bill UUIDs. The BuildOps "
                "public API has no endpoint for listing bills, so the ids to "
                "read must be supplied explicitly."
            )
        return bill_ids

    @staticmethod
    def _parse_include(table_options: dict[str, str]) -> list[str]:
        values = _split_csv((table_options or {}).get("include"))
        invalid = [v for v in values if v.lower() not in _INCLUDE_LOOKUP]
        if invalid:
            raise ValueError(
                f"Invalid value(s) for the 'include' table option: {invalid}. "
                f"Allowed values: {list(BILL_INCLUDE_VALUES)}."
            )
        # Canonicalise casing and drop case-insensitive duplicates.
        return list(dict.fromkeys(_INCLUDE_LOOKUP[v.lower()] for v in values))

    def _iter_bills(self, bill_ids: list[str], include: list[str]) -> Iterator[dict]:
        schema = TABLE_SCHEMAS["bills"]
        for bill_id in bill_ids:
            record = self._fetch_bill(bill_id, include)
            yield _prepare_value(record, schema)

    def _fetch_bill(self, bill_id: str, include: list[str]) -> dict:
        path = BILL_PATH.format(bill_id=quote(bill_id, safe=""))
        # The live API only honours a single comma-separated value
        # (include=a,b); the repeated-key form (include=a&include=b) is
        # accepted with HTTP 200 but silently ignored.
        params = {"include": ",".join(include)} if include else None
        resp = self._client.request("GET", path, params=params)

        if resp.status_code == 404:
            raise BuildOpsAPIError(
                f"BuildOps bill '{bill_id}' was not found (HTTP 404). It may "
                f"have been deleted, belong to a different tenant, or be a "
                f"wrong id -- check the 'bill_ids' table option.",
                status_code=404,
            )
        if resp.status_code == 403:
            raise BuildOpsAPIError(
                f"Access to BuildOps bill '{bill_id}' is forbidden (HTTP 403). "
                f"Verify the credentials are authorised for tenant_id "
                f"'{self._client.tenant_id}'. Response: {resp.text[:500]}",
                status_code=403,
            )
        if resp.status_code != 200:
            raise BuildOpsAPIError(
                f"Failed to read BuildOps bill '{bill_id}' "
                f"(HTTP {resp.status_code}): {resp.text[:500]}",
                status_code=resp.status_code,
            )
        try:
            record = resp.json()
        except ValueError as e:
            raise BuildOpsAPIError(
                f"BuildOps returned a non-JSON body for bill '{bill_id}': {resp.text[:500]}"
            ) from e
        if not isinstance(record, dict):
            raise BuildOpsAPIError(
                f"BuildOps returned an unexpected payload for bill '{bill_id}': "
                f"expected a JSON object, got {type(record).__name__}."
            )
        return record
