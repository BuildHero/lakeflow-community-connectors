"""Schemas, metadata, and constants for the BuildOps connector.

The only table is ``bills``, whose shape is the ``PublicBillResponseDto``
component of the BuildOps public OpenAPI spec (Inventory domain). See
``buildops_api_doc.md`` for field-level provenance.

Type choices worth calling out (see "Known Quirks" in the API doc):

* Bill-level unix-timestamp fields (``transactionDate``, ``issuedBy``,
  ``postingDate``, ``dueDate``, ``approvalNoteDateTime``) are documented as
  epoch **seconds** while ``audit.createdDateTime`` / ``deletedDateTime`` are
  epoch **millis**. Both are kept as raw ``LongType`` epochs rather than
  ``TimestampType`` so a unit mismatch on real data cannot fail parsing or
  silently produce dates in the year 50000.
  Verified live (2026-09-24): the dev API accepts and echoes 10-digit epoch
  seconds for ``dueDate`` / ``postingDate`` / ``issuedBy``, and the audit
  ``*DateTime`` fields are 13-digit epoch millis.
* ``audit.lastUpdatedDateTime`` is typed ``string`` in the OpenAPI spec, but the
  live API returns a JSON integer (epoch millis), so it is ``LongType`` like
  ``createdDateTime`` (the framework's integer parser also accepts a numeric
  string, should the documented shape ever appear).
* ISO-8601 audit dates (``createdDate`` etc.) are ``StringType``; live they
  are always null.
* Objects whose schemas are not documented -- the ``include``-only relation
  objects (``vendor``, ``job``, ...), ``UserAuditInfo`` (``audit.createdBy``
  etc.), ``EquipmentDto`` (an empty ``{}`` schema in the spec) and
  ``PublicQuantityBilledDto.purchaseOrderReceiptLine`` -- are ``StringType``
  columns holding the raw JSON object. The connector JSON-encodes them before
  handing records to the framework (whose ``StringType`` parser would
  otherwise emit a Python ``repr``). Downstream users can ``from_json`` them.
"""

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Connection defaults / HTTP tuning
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://public-api.dev.buildops.com"
TOKEN_PATH = "/v1/auth/token"
BILL_PATH = "/v2/bills/{bill_id}"
BILLS_PATH = "/v2/bills"

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
RETRIABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Refresh the cached token this many seconds before it expires (capped at half
# the token lifetime for very short-lived tokens).
TOKEN_REFRESH_MARGIN_SECONDS = 300
DEFAULT_TOKEN_TTL_SECONDS = 86400

# ---------------------------------------------------------------------------
# Table options
# ---------------------------------------------------------------------------

# Values accepted by the ``include`` query parameter of GET /v2/bills/{billId}.
# The live API expects ONE comma-separated value (``include=vendor,job``); the
# repeated-key form (``include=vendor&include=job``) is silently ignored.
# Verified live: besides the 12 documented relations, ``billLines``,
# ``addresses`` and ``vendorDocumentAttachment`` are also include-gated -- GET
# omits those keys entirely unless they are requested. Unknown values -> 400.
BILL_INCLUDE_VALUES = (
    "billLines",
    "addresses",
    "vendorDocumentAttachment",
    "purchaseOrder",
    "purchaseOrderReceipt",
    "vendor",
    "job",
    "project",
    "department",
    "orderedBy",
    "projectManager",
    "assignedTo",
    "approvalNoteBy",
    "paymentTerm",
    "taxRate",
)

# ---------------------------------------------------------------------------
# Nested struct types
# ---------------------------------------------------------------------------

# AuditInfo. ``createdBy`` / ``lastUpdatedBy`` / ``deletedBy`` reference the
# undocumented ``UserAuditInfo`` object and are carried as JSON strings.
AUDIT_INFO_SCHEMA = StructType(
    [
        StructField("createdBy", StringType(), True),
        StructField("createdDate", StringType(), True),
        StructField("createdDateTime", LongType(), True),
        StructField("lastUpdatedBy", StringType(), True),
        StructField("lastUpdatedDate", StringType(), True),
        StructField("lastUpdatedDateTime", LongType(), True),
        StructField("deletedBy", StringType(), True),
        StructField("deletedDate", StringType(), True),
        StructField("deletedDateTime", LongType(), True),
    ]
)

# PublicQuantityBilledDto (billLines[].purchaseOrderReceiptLineBillLines[]).
QUANTITY_BILLED_SCHEMA = StructType(
    [
        StructField("id", StringType(), True),
        StructField("audit", AUDIT_INFO_SCHEMA, True),
        StructField("quantityBilled", DoubleType(), True),
        StructField("purchaseOrderReceiptLineId", StringType(), True),
        StructField("billLineId", StringType(), True),
        StructField("purchaseOrderReceiptLine", StringType(), True),
    ]
)

# PublicBillLineDto (billLines[]).
BILL_LINE_SCHEMA = StructType(
    [
        StructField("id", StringType(), True),
        StructField("tenantId", StringType(), True),
        StructField("audit", AUDIT_INFO_SCHEMA, True),
        StructField("description", StringType(), True),
        StructField("quantity", DoubleType(), True),
        StructField("lineNumber", LongType(), True),
        StructField("unitCost", DoubleType(), True),
        StructField("unitCostWithTax", DoubleType(), True),
        StructField("unitPrice", DoubleType(), True),
        StructField("taxable", BooleanType(), True),
        StructField("markup", DoubleType(), True),
        StructField("itemGlGroupId", StringType(), True),
        StructField("taxRegionId", StringType(), True),
        StructField("taxCategoryId", StringType(), True),
        StructField("amount", DoubleType(), True),
        StructField("taxAmount", DoubleType(), True),
        StructField("useTaxAmount", DoubleType(), True),
        StructField("totalAmount", DoubleType(), True),
        StructField("accountingSystemLineId", StringType(), True),
        StructField("billId", StringType(), True),
        StructField("purchaseOrderLineId", StringType(), True),
        StructField("purchaseOrderReceiptLineId", StringType(), True),
        StructField("productId", StringType(), True),
        StructField("costCodeId", StringType(), True),
        StructField("departmentId", StringType(), True),
        StructField("version", LongType(), True),
        StructField("invoicedStatus", StringType(), True),
        StructField("jobId", StringType(), True),
        StructField("projectId", StringType(), True),
        StructField("projectPhaseId", StringType(), True),
        StructField("projectCostCodeId", StringType(), True),
        StructField("unitOfMeasure", StringType(), True),
        StructField("jcPhaseId", StringType(), True),
        StructField("jcCostTypeId", StringType(), True),
        StructField("jobCostTypeId", StringType(), True),
        StructField("revenueTypeId", StringType(), True),
        StructField("billingStatus", StringType(), True),
        StructField("jobCloseoutDescription", StringType(), True),
        StructField("jobCloseoutTaxable", LongType(), True),
        StructField("equipmentId", StringType(), True),
        StructField("providerTaxCodeId", StringType(), True),
        StructField("equipment", StringType(), True),
        StructField("lineType", StringType(), True),
        StructField("workTaxabilityTypeId", StringType(), True),
        StructField(
            "purchaseOrderReceiptLineBillLines",
            ArrayType(QUANTITY_BILLED_SCHEMA, True),
            True,
        ),
    ]
)

# AddressDto (addresses[]). ``addressLine1`` is not in the documented
# AddressDto schema (only ``addressLine2`` is), but the omission looks like a
# spec gap; it is declared defensively and is simply null when absent.
ADDRESS_SCHEMA = StructType(
    [
        StructField("id", StringType(), True),
        StructField("addressLine1", StringType(), True),
        StructField("addressLine2", StringType(), True),
        StructField("city", StringType(), True),
        StructField("state", StringType(), True),
        StructField("zipcode", StringType(), True),
        StructField("addressType", StringType(), True),
    ]
)

# AttachmentDto (vendorDocumentAttachment).
ATTACHMENT_SCHEMA = StructType(
    [
        StructField("id", StringType(), True),
        StructField("customFileName", StringType(), True),
        StructField("fileName", StringType(), True),
        StructField("fileUrl", StringType(), True),
        StructField("fileSize", DoubleType(), True),
        StructField("description", StringType(), True),
        StructField("originalFileName", StringType(), True),
        StructField("isUploaded", BooleanType(), True),
        StructField("comment", StringType(), True),
        StructField("hideFromTechniciansOnMobile", BooleanType(), True),
    ]
)

# ---------------------------------------------------------------------------
# bills (PublicBillResponseDto)
# ---------------------------------------------------------------------------

BILLS_SCHEMA = StructType(
    [
        StructField("id", StringType(), False),
        StructField("tenantId", StringType(), True),
        StructField("audit", AUDIT_INFO_SCHEMA, True),
        StructField("billLines", ArrayType(BILL_LINE_SCHEMA, True), True),
        StructField("transactionDate", LongType(), True),
        StructField("billNumber", StringType(), True),
        StructField("customIdentifier", StringType(), True),
        StructField("description", StringType(), True),
        StructField("freight", DoubleType(), True),
        StructField("tax", DoubleType(), True),
        StructField("addedBy", StringType(), True),
        StructField("invoicedStatus", StringType(), True),
        StructField("accountingRefIdOfClass", StringType(), True),
        StructField("purchaseOrderReceiptId", StringType(), True),
        StructField("departmentId", StringType(), True),
        StructField("taxRateId", StringType(), True),
        StructField("vendorId", StringType(), True),
        StructField("jobId", StringType(), True),
        StructField("projectId", StringType(), True),
        StructField("vendorDocumentNumber", StringType(), True),
        StructField("vendorDocumentAttachment", ATTACHMENT_SCHEMA, True),
        StructField("orderedById", StringType(), True),
        StructField("issuedBy", LongType(), True),
        StructField("postingDate", LongType(), True),
        StructField("dueDate", LongType(), True),
        StructField("version", LongType(), True),
        StructField("totalCost", DoubleType(), True),
        StructField("syncLog", StringType(), True),
        StructField("syncStatus", StringType(), True),
        StructField("accountingVersion", StringType(), True),
        StructField("isImported", BooleanType(), True),
        StructField("tenantCompanyId", StringType(), True),
        StructField("purchaseOrderId", StringType(), True),
        StructField("approvalStatus", StringType(), True),
        StructField("approvalNote", StringType(), True),
        StructField("approvalNoteById", StringType(), True),
        StructField("approvalNoteDateTime", LongType(), True),
        StructField("projectManagerId", StringType(), True),
        StructField("paymentTermId", StringType(), True),
        StructField("assignedToId", StringType(), True),
        StructField("status", StringType(), True),
        StructField("createdByEmployeeId", StringType(), True),
        StructField("isCreatedFromMobile", BooleanType(), True),
        # Fields returned by the live API but absent from the documented
        # PublicBillResponseDto (observed 2026-09-24 on the dev tenant). Types
        # follow the observed values; fields only ever seen as null follow
        # their CreateBillDto counterpart / naming. ``taxAmountOverridden`` is
        # a StringType because its type could not be observed (always null)
        # and a string column is lossless for either a flag or an amount.
        StructField("uniqueBillNumber", StringType(), True),
        StructField("accountingRefId", StringType(), True),
        StructField("isStandalone", BooleanType(), True),
        StructField("totalAmountPreTax", DoubleType(), True),
        StructField("taxRegionId", StringType(), True),
        StructField("isUseTaxable", BooleanType(), True),
        StructField("useTaxTotal", DoubleType(), True),
        StructField("taxAmountOverridden", StringType(), True),
        StructField("isReceiptBound", BooleanType(), True),
        StructField("vendorDocumentAttachmentId", StringType(), True),
        StructField("amountDue", DoubleType(), True),
        StructField("isRetainageApplicable", BooleanType(), True),
        StructField("isRetainageBill", BooleanType(), True),
        StructField("defaultRetainagePercent", DoubleType(), True),
        StructField("totalRetainageAmount", DoubleType(), True),
        StructField("retainageAmountUnbilled", DoubleType(), True),
        StructField("parentBillId", StringType(), True),
        StructField("vendorLocationId", StringType(), True),
        StructField("vendorContactId", StringType(), True),
        StructField("billToAddressId", StringType(), True),
        StructField("shipToAddressId", StringType(), True),
        StructField("shipFromAddressId", StringType(), True),
        # ``addresses`` (like ``billLines`` and ``vendorDocumentAttachment``)
        # is only returned when requested via the ``include`` table option.
        StructField("addresses", ArrayType(ADDRESS_SCHEMA, True), True),
        # include-only relation objects (JSON strings; null unless requested
        # through the ``include`` table option).
        StructField("purchaseOrder", StringType(), True),
        StructField("purchaseOrderReceipt", StringType(), True),
        StructField("vendor", StringType(), True),
        StructField("job", StringType(), True),
        StructField("project", StringType(), True),
        StructField("department", StringType(), True),
        StructField("orderedBy", StringType(), True),
        StructField("projectManager", StringType(), True),
        StructField("assignedTo", StringType(), True),
        StructField("approvalNoteBy", StringType(), True),
        StructField("paymentTerm", StringType(), True),
        StructField("taxRate", StringType(), True),
    ]
)

TABLE_SCHEMAS = {
    "bills": BILLS_SCHEMA,
}

TABLE_METADATA = {
    "bills": {
        "primary_keys": ["id"],
        "ingestion_type": "snapshot",
    },
}

SUPPORTED_TABLES = list(TABLE_SCHEMAS.keys())
