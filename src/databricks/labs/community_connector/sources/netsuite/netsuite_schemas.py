"""Static schema and metadata definitions for the NetSuite connector.

Scope for this phase: the single ``vendorbill`` table (header rows from
NetSuite's built-in ``transaction`` SuiteQL table, filtered to
``type = 'VendBill'``). See ``netsuite_api_doc.md`` for field-by-field
sourcing, the deferred ``transactionline`` decision, and known quirks
(account-locale dates, string-typed numerics, TBA sunset timeline).
"""

from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

SUPPORTED_TABLES: list[str] = ["vendorbill"]

# Header-only vendorbill schema. All SuiteQL wire values are JSON strings
# (see Known Quirks in netsuite_api_doc.md); the framework's parse_value
# coercion converts numeric-looking strings into LongType/DoubleType.
# Date/timestamp columns are kept as StringType (ISO 8601 text produced by
# the connector's TO_CHAR(...) wrapping in the SuiteQL query) rather than
# TimestampType/DateType, to avoid depending on Spark's locale-aware date
# parsing for any future column added without that normalization.
VENDOR_BILL_SCHEMA = StructType(
    [
        StructField("id", LongType(), False),
        StructField("tranid", StringType(), True),
        StructField("entity", LongType(), True),
        StructField("trandate", StringType(), True),
        StructField("duedate", StringType(), True),
        StructField("status", StringType(), True),
        StructField("currency", LongType(), True),
        StructField("exchangerate", DoubleType(), True),
        StructField("foreigntotal", DoubleType(), True),
        StructField("memo", StringType(), True),
        StructField("subsidiary", LongType(), True),
        StructField("terms", LongType(), True),
        StructField("postingperiod", LongType(), True),
        StructField("approvalstatus", StringType(), True),
        StructField("externalid", StringType(), True),
        StructField("createddate", StringType(), True),
        StructField("lastmodifieddate", StringType(), True),
    ]
)

TABLE_SCHEMAS: dict[str, StructType] = {
    "vendorbill": VENDOR_BILL_SCHEMA,
}

TABLE_METADATA: dict[str, dict] = {
    "vendorbill": {
        "primary_keys": ["id"],
        "cursor_field": "lastmodifieddate",
        # cdc (upsert) only -- delete detection deferred, see
        # netsuite_api_doc.md "Object's ingestion type".
        "ingestion_type": "cdc",
    },
}

# Columns requested from the `transaction` SuiteQL table, in order. Date /
# timestamp columns are wrapped in TO_CHAR(...) at query-build time (see
# netsuite.py) to normalize away account-locale date formats.
VENDOR_BILL_COLUMNS: list[str] = [
    "id",
    "tranid",
    "entity",
    "trandate",
    "duedate",
    "status",
    "currency",
    "exchangerate",
    "foreigntotal",
    "memo",
    "subsidiary",
    "terms",
    "postingperiod",
    "approvalstatus",
    "externalid",
    "createddate",
    "lastmodifieddate",
]

# Columns whose SuiteQL value must be normalized via TO_CHAR(..., 'YYYY-MM-DD...')
# rather than selected raw, per the account-locale-date-format quirk.
DATE_COLUMNS: dict[str, str] = {
    "trandate": "YYYY-MM-DD",
    "duedate": "YYYY-MM-DD",
    "createddate": "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"",
    "lastmodifieddate": "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"",
}
