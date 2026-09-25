"""Table -> object mapping, schemas, and constants for the Intacct connector.

Field lists below are the "core, well-documented fields" from
``intacct_api_doc.md`` for each of the 5 in-scope objects. The doc notes
that a production implementation should call ``lookup`` at connector-init
time to discover the tenant's full (including custom) field list; this
connector hard-codes the documented core fields instead, matching the
pattern used by other connectors in this repo (e.g. example's ``metrics``
table) and keeping the simulator spec simple (no ``lookup`` endpoint to
model). See the TODO in ``intacct.py`` for promoting this to dynamic
``lookup``-based schema discovery.

Only object *headers* are modeled for ``invoices`` (ARINVOICE) and ``bills``
(APBILL) -- their line-item children (ARINVOICEITEM / APBILLITEM) are out of
scope for this batch (the requested table set is exactly the 5 tables below,
not line-item detail tables), and the doc flags the header/line FK field
name as unconfirmed ("TBD: verify via lookup on ARINVOICEITEM before
implementation").
"""

from __future__ import annotations

from pyspark.sql.types import (
    BooleanType,
    DateType,
    DecimalType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# Every table in this batch uses the same primary key and cursor field.
PRIMARY_KEY_FIELD = "RECORDNO"
CURSOR_FIELD = "WHENMODIFIED"

TABLE_TO_OBJECT: dict[str, str] = {
    "customers": "CUSTOMER",
    "vendors": "VENDOR",
    "invoices": "ARINVOICE",
    "bills": "APBILL",
    "gl_entries": "GLDETAIL",
}

OBJECT_TO_TABLE: dict[str, str] = {v: k for k, v in TABLE_TO_OBJECT.items()}

# XML Gateway pagination bounds (see "Pagination" in the API doc).
DEFAULT_PAGESIZE = 1000
MAX_PAGESIZE = 2000

# Retry/backoff for transport-level errors and heuristically-transient
# XML Gateway failures (e.g. the documented single-concurrent-job queueing).
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0  # seconds; doubled after each retry
RETRIABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
# Substrings of an Intacct <description>/<description2> that indicate a
# transient, retry-worthy condition (concurrency-queue timeout, generic
# "try again" guidance) rather than a real data/auth/programming error.
# The doc documents only the *behavior* (queue then error after ~30s), not
# a specific error code, so this is a conservative heuristic.
RETRIABLE_ERROR_KEYWORDS = (
    "try your request again",
    "try again",
    "concurrent",
    "busy",
    "please wait",
    "temporarily",
)

_DECIMAL = DecimalType(18, 4)


def _field(name: str, spark_type, nullable: bool = True) -> StructField:
    return StructField(name, spark_type, nullable=nullable)


CUSTOMER_FIELDS = [
    "RECORDNO",
    "CUSTOMERID",
    "NAME",
    "STATUS",
    "ONETIME",
    "CREDITLIMIT",
    "TAXID",
    "CUSTTYPE",
    "PARENTID",
    "TERMNAME",
    "CURRENCY",
    "ONHOLD",
    "TOTALDUE",
    "WHENCREATED",
    "WHENMODIFIED",
]

VENDOR_FIELDS = [
    "RECORDNO",
    "VENDORID",
    "NAME",
    "STATUS",
    "TOTALDUE",
    "CREDITLIMIT",
    "VENDTYPE",
    "PARENTID",
    "TAXID",
    "CURRENCY",
    "ONHOLD",
    "ONETIME",
    "WHENCREATED",
    "WHENMODIFIED",
]

ARINVOICE_FIELDS = [
    "RECORDNO",
    "CUSTOMERID",
    "CUSTOMERNAME",
    # Live `lookup` on ARINVOICE confirmed the doc's field names here were
    # wrong: INVOICENO/DATECREATED/DATEPOSTED/DATEDUE are not queryable on
    # this object -- a live `query` request fails with "The following
    # fields cannot be queried". The real fields (verified live) are
    # DOCNUMBER (business document number) and WHENPOSTED/WHENDUE, matching
    # the naming convention already used on APBILL.
    "DOCNUMBER",
    "WHENPOSTED",
    "WHENDUE",
    "WHENCREATED",
    "WHENMODIFIED",
    "TOTALENTERED",
    "TOTALPAID",
    "TOTALDUE",
    "TERMNAME",
    "STATE",
    "MODULEKEY",
    "CURRENCY",
]

APBILL_FIELDS = [
    "RECORDNO",
    "VENDORID",
    "RECORDID",
    "WHENCREATED",
    "WHENPOSTED",
    "WHENDUE",
    "WHENMODIFIED",
    "DESCRIPTION",
    "TERMNAME",
    "PAYMENTPRIORITY",
    "ONHOLD",
    "STATE",
    "CURRENCY",
    "BASECURR",
    "EXCHANGE_RATE",
    "MODULEKEY",
]

GLDETAIL_FIELDS = [
    "RECORDNO",
    "GLENTRYKEY",
    "ACCOUNTNO",
    "ACCOUNTTITLE",
    "AMOUNT",
    "DEBITAMOUNT",
    "CREDITAMOUNT",
    "TRX_AMOUNT",
    "TRX_DEBITAMOUNT",
    "TRX_CREDITAMOUNT",
    "BATCH_DATE",
    "BATCH_TITLE",
    "ENTRY_DATE",
    "WHENCREATED",
    "AUWHENCREATED",
    "WHENMODIFIED",
    "BOOKID",
    "MODULEKEY",
    "CLASSID",
    "CLASSNAME",
    "DEPARTMENTID",
    "DEPARTMENTTITLE",
    "LOCATIONID",
    "LOCATIONNAME",
    "PROJECTID",
    "PROJECTNAME",
    "SYMBOL",
    "LINE_NO",
    "DESCRIPTION",
]

TABLE_FIELDS: dict[str, list[str]] = {
    "customers": CUSTOMER_FIELDS,
    "vendors": VENDOR_FIELDS,
    "invoices": ARINVOICE_FIELDS,
    "bills": APBILL_FIELDS,
    "gl_entries": GLDETAIL_FIELDS,
}

TABLE_SCHEMAS: dict[str, StructType] = {
    "customers": StructType(
        [
            _field("RECORDNO", LongType(), nullable=False),
            _field("CUSTOMERID", StringType()),
            _field("NAME", StringType()),
            _field("STATUS", StringType()),
            _field("ONETIME", BooleanType()),
            _field("CREDITLIMIT", _DECIMAL),
            _field("TAXID", StringType()),
            _field("CUSTTYPE", StringType()),
            _field("PARENTID", StringType()),
            _field("TERMNAME", StringType()),
            _field("CURRENCY", StringType()),
            _field("ONHOLD", BooleanType()),
            _field("TOTALDUE", _DECIMAL),
            _field("WHENCREATED", DateType()),
            _field("WHENMODIFIED", TimestampType()),
        ]
    ),
    "vendors": StructType(
        [
            _field("RECORDNO", LongType(), nullable=False),
            _field("VENDORID", StringType()),
            _field("NAME", StringType()),
            _field("STATUS", StringType()),
            _field("TOTALDUE", _DECIMAL),
            _field("CREDITLIMIT", _DECIMAL),
            _field("VENDTYPE", StringType()),
            _field("PARENTID", StringType()),
            _field("TAXID", StringType()),
            _field("CURRENCY", StringType()),
            _field("ONHOLD", BooleanType()),
            _field("ONETIME", BooleanType()),
            _field("WHENCREATED", DateType()),
            _field("WHENMODIFIED", TimestampType()),
        ]
    ),
    "invoices": StructType(
        [
            _field("RECORDNO", LongType(), nullable=False),
            _field("CUSTOMERID", StringType()),
            _field("CUSTOMERNAME", StringType()),
            _field("DOCNUMBER", StringType()),
            _field("WHENPOSTED", DateType()),
            _field("WHENDUE", DateType()),
            _field("WHENCREATED", DateType()),
            _field("WHENMODIFIED", TimestampType()),
            _field("TOTALENTERED", _DECIMAL),
            _field("TOTALPAID", _DECIMAL),
            _field("TOTALDUE", _DECIMAL),
            _field("TERMNAME", StringType()),
            _field("STATE", StringType()),
            _field("MODULEKEY", StringType()),
            _field("CURRENCY", StringType()),
        ]
    ),
    "bills": StructType(
        [
            _field("RECORDNO", LongType(), nullable=False),
            _field("VENDORID", StringType()),
            _field("RECORDID", StringType()),
            _field("WHENCREATED", DateType()),
            _field("WHENPOSTED", DateType()),
            _field("WHENDUE", DateType()),
            _field("WHENMODIFIED", TimestampType()),
            _field("DESCRIPTION", StringType()),
            _field("TERMNAME", StringType()),
            _field("PAYMENTPRIORITY", StringType()),
            _field("ONHOLD", BooleanType()),
            _field("STATE", StringType()),
            _field("CURRENCY", StringType()),
            _field("BASECURR", StringType()),
            _field("EXCHANGE_RATE", _DECIMAL),
            _field("MODULEKEY", StringType()),
        ]
    ),
    "gl_entries": StructType(
        [
            # Unlike the other 4 objects, GLDETAIL.RECORDNO is NOT a clean
            # auto-incrementing integer -- live data shows composite string
            # values like "7-35---accrual" (batchkey-entrykey---bookid),
            # consistent with the doc's note that GLDETAIL is "a view, not
            # a table". GLENTRYKEY (confirmed live as a clean integer, e.g.
            # "35") is the real numeric FK back to GLENTRY.RECORDNO.
            _field("RECORDNO", StringType(), nullable=False),
            _field("GLENTRYKEY", LongType()),
            _field("ACCOUNTNO", StringType()),
            _field("ACCOUNTTITLE", StringType()),
            _field("AMOUNT", _DECIMAL),
            _field("DEBITAMOUNT", _DECIMAL),
            _field("CREDITAMOUNT", _DECIMAL),
            _field("TRX_AMOUNT", _DECIMAL),
            _field("TRX_DEBITAMOUNT", _DECIMAL),
            _field("TRX_CREDITAMOUNT", _DECIMAL),
            _field("BATCH_DATE", DateType()),
            _field("BATCH_TITLE", StringType()),
            _field("ENTRY_DATE", DateType()),
            # NOTE: on GLDETAIL, WHENCREATED is *not* a creation timestamp --
            # it's the user-entered transaction date (see doc). Kept as
            # DateType to match that semantic; use AUWHENCREATED for the
            # true record-creation audit timestamp.
            _field("WHENCREATED", DateType()),
            _field("AUWHENCREATED", TimestampType()),
            _field("WHENMODIFIED", TimestampType()),
            _field("BOOKID", StringType()),
            _field("MODULEKEY", StringType()),
            _field("CLASSID", StringType()),
            _field("CLASSNAME", StringType()),
            _field("DEPARTMENTID", StringType()),
            _field("DEPARTMENTTITLE", StringType()),
            _field("LOCATIONID", StringType()),
            _field("LOCATIONNAME", StringType()),
            _field("PROJECTID", StringType()),
            _field("PROJECTNAME", StringType()),
            _field("SYMBOL", StringType()),
            _field("LINE_NO", LongType()),
            _field("DESCRIPTION", StringType()),
        ]
    ),
}
