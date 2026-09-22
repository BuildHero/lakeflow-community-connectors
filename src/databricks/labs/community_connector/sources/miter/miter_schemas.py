"""Static schemas, metadata and endpoint wiring for the Miter connector.

Field lists are transcribed from the Miter OpenAPI spec (``info.version:
"2.0"``) response schemas — ``LedgerAccountResponse``,
``LedgerEntryResponse``, ``LedgerEntryLineItemResponse`` and
``LedgerMappingResponse`` — as documented in ``miter_api_doc.md``.
"""

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DateType,
    DoubleType,
    MapType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# --------------------------------------------------------------------------
# Connection / request constants
# --------------------------------------------------------------------------

# Miter production API. Staging (``https://api.staging.miter.com/api/v2``)
# is reachable with the same connector by setting the ``base_url``
# connection option — tokens are environment-specific and a production
# token is rejected by staging and vice versa.
DEFAULT_BASE_URL = "https://api.miter.com/api/v2"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0
RETRIABLE_STATUS_CODES = (429, 500, 502, 503, 504)

# ``limit`` accepts 1-1000, default 100 (OpenAPI spec).
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000

DEFAULT_MAX_RECORDS_PER_BATCH = 5000
DEFAULT_WINDOW_SECONDS = 86400
DEFAULT_MAX_PARTITIONS = 200
DEFAULT_PARENTS_PER_PARTITION = 20

# Every object in this API exposes ``updated_at`` and supports
# ``sort[field]=updated_at`` with ``after_exclusive``/``before_inclusive``.
CURSOR_FIELD = "updated_at"
PRIMARY_KEY = "id"

# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

LEDGER_LINE_ITEMS = "ledger_line_items"

# ``parent_table`` marks a nested resource: it has no global list endpoint
# and must be read once per parent record's id.
TABLE_ENDPOINTS = {
    "ledger_accounts": {"path": "/ledger_accounts"},
    "ledger_entries": {"path": "/ledger_entries"},
    LEDGER_LINE_ITEMS: {
        "path": "/ledger_entries/{parent_id}/line_items",
        "parent_table": "ledger_entries",
    },
    "ledger_mappings": {"path": "/ledger_mappings"},
}

SUPPORTED_TABLES = tuple(TABLE_ENDPOINTS)

# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

_LEDGER_ACCOUNTS_SCHEMA = StructType(
    [
        StructField("id", StringType(), False),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        StructField("custom_id", StringType(), True),
        StructField("label", StringType(), True),
        StructField("classification", StringType(), True),
        StructField("parent_account_id", StringType(), True),
        StructField("status", StringType(), True),
        StructField("is_selectable_by_team_members", BooleanType(), True),
    ]
)

_LEDGER_ENTRY_SOURCE_OBJECTS = StructType(
    [
        StructField("payroll_id", StringType(), True),
        StructField("check_payment_id", StringType(), True),
        StructField("recoded_timesheet_ids", ArrayType(StringType()), True),
        StructField("reimbursement_id", StringType(), True),
        StructField("reimbursement_ids", ArrayType(StringType()), True),
        StructField("expense_id", StringType(), True),
        StructField("stripe_inbound_transfer_id", StringType(), True),
        StructField("bill_ids", ArrayType(StringType()), True),
        StructField("equipment_timesheet_ids", ArrayType(StringType()), True),
    ]
)

_LEDGER_ENTRIES_SCHEMA = StructType(
    [
        StructField("id", StringType(), False),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        StructField("ledger_id", StringType(), True),
        StructField("entry_type", StringType(), True),
        StructField("posted_at", TimestampType(), True),
        StructField("description", StringType(), True),
        StructField("company_entity_id", StringType(), True),
        StructField("source_objects", _LEDGER_ENTRY_SOURCE_OBJECTS, True),
    ]
)

# ``ReferenceCustomFieldValue.value`` is ``anyOf`` string/number/boolean/
# array, so it is normalised to a string (JSON-encoded when non-scalar)
# before being handed to Spark.
_CUSTOM_FIELD_VALUE = StructType(
    [
        StructField("custom_field_id", StringType(), True),
        StructField("value", StringType(), True),
    ]
)

_LEDGER_LINE_ITEMS_SCHEMA = StructType(
    [
        StructField("id", StringType(), False),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        StructField("ledger_entry_id", StringType(), True),
        StructField("account_type", StringType(), True),
        StructField("miter_type", StringType(), True),
        StructField("direction", StringType(), True),
        StructField("amount", DoubleType(), True),
        StructField("ledger_account_id", StringType(), True),
        StructField("description", StringType(), True),
        StructField("payroll_id", StringType(), True),
        StructField("voided_payroll_id", StringType(), True),
        StructField("payday", DateType(), True),
        StructField("team_member_id", StringType(), True),
        StructField("employment_type", StringType(), True),
        StructField("department_id", StringType(), True),
        StructField("location_id", StringType(), True),
        StructField("class_id", StringType(), True),
        StructField("company_entity_id", StringType(), True),
        StructField("job_id", StringType(), True),
        StructField("activity_id", StringType(), True),
        StructField("work_order_id", StringType(), True),
        StructField("workers_compensation_code_id", StringType(), True),
        StructField("timesheet_id", StringType(), True),
        StructField("equipment_timesheet_id", StringType(), True),
        StructField("equipment_id", StringType(), True),
        StructField("reimbursement_id", StringType(), True),
        StructField("reimbursement_date", DateType(), True),
        StructField("accrual_date", DateType(), True),
        StructField("classification_id", StringType(), True),
        StructField("pay_rate_group_id", StringType(), True),
        StructField("fringe_classification_id", StringType(), True),
        StructField("fringe_pay_rate_group_id", StringType(), True),
        StructField("burden_rate_id", StringType(), True),
        StructField("earning_type", StringType(), True),
        StructField("earning_date", DateType(), True),
        StructField("benefit_type", StringType(), True),
        StructField("hours", DoubleType(), True),
        StructField("void", BooleanType(), True),
        StructField("memo", StringType(), True),
        StructField("cost_type_id", StringType(), True),
        StructField("custom_earning_code_id", StringType(), True),
        StructField("custom_field_values", ArrayType(_CUSTOM_FIELD_VALUE), True),
        StructField("recoded", BooleanType(), True),
        StructField("manually_edited", BooleanType(), True),
    ]
)

# ``defaults`` / ``*_accounts`` are open-keyed objects whose values are
# nullable ledger-account ids — a map, not a fixed struct.
_LEDGER_MAPPINGS_SCHEMA = StructType(
    [
        StructField("id", StringType(), False),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
        StructField("name", StringType(), True),
        StructField("is_company_default", BooleanType(), True),
        StructField("defaults", MapType(StringType(), StringType()), True),
        StructField(
            "earning_type_accounts", MapType(StringType(), StringType()), True
        ),
        StructField(
            "benefit_type_expense_accounts",
            MapType(StringType(), StringType()),
            True,
        ),
        StructField(
            "benefit_type_liability_accounts",
            MapType(StringType(), StringType()),
            True,
        ),
    ]
)

TABLE_SCHEMAS = {
    "ledger_accounts": _LEDGER_ACCOUNTS_SCHEMA,
    "ledger_entries": _LEDGER_ENTRIES_SCHEMA,
    LEDGER_LINE_ITEMS: _LEDGER_LINE_ITEMS_SCHEMA,
    "ledger_mappings": _LEDGER_MAPPINGS_SCHEMA,
}

# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------

# No object in the Miter API supports delete detection (no tombstones, no
# soft-delete field, no audit-log endpoint), so every table is plain ``cdc``.
TABLE_METADATA = {
    table: {
        "primary_keys": [PRIMARY_KEY],
        "cursor_field": CURSOR_FIELD,
        "ingestion_type": "cdc",
    }
    for table in SUPPORTED_TABLES
}

# Struct-typed fields that the API may return as ``{}``; Spark requires
# ``None`` instead of an empty struct.
STRUCT_FIELDS = {
    "ledger_entries": ("source_objects",),
}
