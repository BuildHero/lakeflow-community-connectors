# Lakeflow BuildOps Community Connector

This documentation describes how to configure and use the **BuildOps** Lakeflow community connector to ingest Accounts Payable **bills** from the BuildOps public REST API into Databricks.

BuildOps is a cloud-based field-service and job-costing platform for commercial contractors. The connector reads bill records and, on request through the `include` table option, their line items, addresses, vendor document attachment, and related records (vendor, job, project, purchase order, and so on) that BuildOps can embed in a bill response.

> **Important:** The BuildOps public API has no endpoint that lists bills. It can only return a single bill by its ID. Because of this, **you must tell the connector which bills to read** by setting the `bill_ids` table option. The connector cannot discover new bills on its own. See [How the `bills` table works](#how-the-bills-table-works).

## Prerequisites

- **BuildOps API credentials**: a **client ID** and **client secret** for the BuildOps public API. BuildOps issues these. Self-service creation is not available, so request them from BuildOps support or your BuildOps account manager.
- **BuildOps tenant ID**: the UUID of the BuildOps tenant (company) whose data you want to read. The credentials must be authorized for this tenant.
- **Bill IDs**: the UUIDs of the bills you want to ingest (see [Choosing bill IDs](#choosing-bill-ids)).
- **Network access**: the environment running the connector must be able to reach the BuildOps API host you use (`https://public-api.live.buildops.com` for production, or `https://public-api.dev.buildops.com` for the development environment).
- **Lakeflow / Databricks environment**: a workspace where you can register a Lakeflow community connector and run ingestion pipelines.

## Setup

### Required Connection Parameters

Provide the following **connection-level** options when configuring the connector:

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `client_id` | string | yes | BuildOps public API client ID. | `3f9c2a1e-...` |
| `client_secret` | string | yes | BuildOps public API client secret. Store it as a secret; do not commit it to source control. | `********` |
| `tenant_id` | string | yes | UUID of the BuildOps tenant to read from. Sent with every API request. | `2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231` |
| `base_url` | string | no | Base URL of the BuildOps public API. Defaults to the **development** server `https://public-api.dev.buildops.com`. **Set this to `https://public-api.live.buildops.com` to read production data.** | `https://public-api.live.buildops.com` |
| `externalOptionsAllowList` | string | yes | Comma-separated list of the table-specific options the connection passes through to the connector. This connector needs table-specific options (`bill_ids` is required), so this parameter must be set to exactly `bill_ids,include`. | `bill_ids,include` |

The full list of supported table-specific options for `externalOptionsAllowList` is:
`bill_ids,include`

> **Note**: `bill_ids` and `include` are **not** connection parameters. You set them per table under `table_configuration` in the pipeline spec. Their names must be listed in `externalOptionsAllowList` so the connection lets them through.

> **Note on `base_url`**: The default points to the BuildOps **development** environment, not production. If your credentials were issued for production, leave `base_url` unset and the token exchange fails (or reads the wrong environment). Always set `base_url` explicitly for production connections.

You do not supply an access token. When a pipeline runs, the connector exchanges `client_id` and `client_secret` for a short-lived bearer token (valid for about 24 hours) and renews it automatically. No browser sign-in or redirect URI is involved.

### Obtaining the Required Parameters

**Client ID and client secret**

1. Contact BuildOps support or your BuildOps account manager and request **public API credentials** for your company.
2. Say which environment you need (production, or the development/sandbox environment) and which tenant the credentials should cover.
3. BuildOps provides a client ID and a client secret. Store the secret securely, for example in a Databricks secret scope. Use the two values as `client_id` and `client_secret`.

**Tenant ID**

The tenant ID is the UUID that identifies your company's BuildOps tenant. BuildOps usually gives it to you along with the API credentials. If you have credentials but not the tenant ID, ask BuildOps support. You can also list the tenants your credentials are authorized for by calling the BuildOps scope endpoint:

```shell
# 1. Exchange the credentials for an access token
curl --request POST \
  --url 'https://public-api.live.buildops.com/v1/auth/token' \
  --header 'Content-Type: application/json' \
  --data '{"clientId": "<client-id>", "clientSecret": "<client-secret>"}'

# 2. List the tenant IDs the token is authorized for
curl --request GET \
  --url 'https://public-api.live.buildops.com/v1/auth/scope' \
  --header 'Authorization: Bearer <access_token>'
```

(For the development environment, use `https://public-api.dev.buildops.com`.)

**Base URL**

| Environment | `base_url` |
|---|---|
| Production | `https://public-api.live.buildops.com` |
| Development (connector default) | `https://public-api.dev.buildops.com` |

Credentials are specific to an environment. Production credentials do not work against the development server, and development credentials do not work against production.

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:

1. Follow the **Lakeflow Community Connector** UI flow from the **Add Data** page.
2. Select any existing Lakeflow Community Connector connection for this source or create a new one.
3. Set `externalOptionsAllowList` to `bill_ids,include`. This is required, because the `bills` table cannot be read without the `bill_ids` table option.

The connection can also be created using the standard Unity Catalog API.

## Supported Objects

The connector exposes a single, static table:

| Table | Description | Ingestion Type | Primary Key | Incremental Cursor | Delete Sync |
|---|---|---|---|---|---|
| `bills` | BuildOps Accounts Payable bills, with nested line items, addresses, audit information, and optional related records | `snapshot` | `id` (bill UUID, string) | n/a | No (see below) |

### How the `bills` table works

- **Reads by ID only.** The BuildOps public API offers `GET /v2/bills/{billId}` for reading a single bill. It has no endpoint for listing or searching bills. The connector therefore makes one API request for each ID in the `bill_ids` table option, and reads nothing else.
- **Snapshot ingestion.** Every pipeline run fetches every configured bill again. The result replaces the previous snapshot in the destination table, keyed on `id`:
  - Changes to a configured bill (status, amounts, lines, and so on) are picked up on the next run.
  - If you **remove** an ID from `bill_ids`, that bill is no longer in the snapshot, so the pipeline treats it as deleted on the next run. With `SCD_TYPE_1` the row is removed; with `SCD_TYPE_2` its history is closed out.
  - New bills created in BuildOps are **not** discovered automatically. Add their IDs to `bill_ids`.
- **Missing bills fail the run.** If any configured ID returns **HTTP 404** (the bill was deleted, belongs to a different tenant, or the ID is wrong), the connector stops and the pipeline update fails. It does not skip the bill. The error message names the ID. Remove or correct that ID in `bill_ids` and run the pipeline again.
- **No deletes feed.** BuildOps does not publish a feed of deleted bills, so the connector cannot detect deletions on its own. A 404 on a known ID is the only signal, and it surfaces as a failed run (see above).

### Choosing bill IDs

Each value in `bill_ids` is a BuildOps bill `id` (a UUID such as `2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231`). The human-facing bill number (for example `BILL-123`) is **not** accepted. Get bill IDs from a system that already knows them, such as a BuildOps report or export, your accounting integration, or a dataset you have already ingested.

### Schema highlights

The schema is static and follows the BuildOps `PublicBillResponseDto` definition, plus the fields the live API returns beyond that definition (for example `uniqueBillNumber`, `totalAmountPreTax`, `amountDue`, the retainage fields, and the vendor location / contact / address IDs). Columns keep the BuildOps camelCase field names.

- **Identifiers and foreign keys**: `id`, `tenantId`, `vendorId`, `jobId`, `projectId`, `departmentId`, `purchaseOrderId`, `purchaseOrderReceiptId`, `paymentTermId`, `taxRateId`, `orderedById`, `projectManagerId`, `assignedToId`, `approvalNoteById`, `createdByEmployeeId`, `tenantCompanyId`. All are UUID strings.
- **Status fields**: `status` (`Exported`, `Pending`, `Posted`, `Void`, `Closed`, `Draft`, `Bypassed`), `approvalStatus` (`Unreviewed`, `Approved`, `Review Needed`, `Rejected`), `invoicedStatus`, and `syncStatus` (`Syncing`, `InSync`, `SyncFailed`, `Bypassed`). They are stored as plain strings.
- **`billLines`**: an array of structs, one per line item. BuildOps only returns it when `include` lists `billLines`; otherwise the column is null. Each line carries its own `id`, quantities, costs, tax amounts, job-costing references, and `audit` struct. It also has a nested `purchaseOrderReceiptLineBillLines` array of quantity-billed reconciliation records.
- **`addresses`**: an array of structs (`id`, `addressLine1`, `addressLine2`, `city`, `state`, `zipcode`, `addressType`). `addressLine1` is not in the BuildOps schema definition. The connector includes it in case BuildOps returns it, and it is null otherwise. Returned only when `include` lists `addresses`.
- **`vendorDocumentAttachment`**: a struct with the attached vendor document's file name, URL, size, and flags. Returned only when `include` lists `vendorDocumentAttachment`; `vendorDocumentAttachmentId` is always returned.
- **`audit`**: a struct with created, last-updated, and deleted dates and user references. See [Data Type Mapping](#data-type-mapping) for the timestamp formats.
- **`issuedBy`** holds a **date** (the date the bill must be issued by), not a person.
- **Related-record columns**: `purchaseOrder`, `purchaseOrderReceipt`, `vendor`, `job`, `project`, `department`, `orderedBy`, `projectManager`, `assignedTo`, `approvalNoteBy`, `paymentTerm`, and `taxRate`. These are **JSON-string** columns. Each is null unless you request that relation through the `include` table option.

## Table Configurations

### Source & Destination

These are set directly under each `table` object in the pipeline spec:

| Option | Required | Description |
|---|---|---|
| `source_table` | Yes | Table name in the source system |
| `destination_catalog` | No | Target catalog (defaults to pipeline's default) |
| `destination_schema` | No | Target schema (defaults to pipeline's default) |
| `destination_table` | No | Target table name (defaults to `source_table`) |

### Common `table_configuration` options

These are set inside the `table_configuration` map alongside any source-specific options:

| Option | Required | Description |
|---|---|---|
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. Only applicable to tables with CDC or SNAPSHOT ingestion mode; APPEND_ONLY tables do not support this option. |
| `primary_keys` | No | List of columns to override the connector's default primary keys |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking |
| `cluster_by` | No | List of columns to cluster the destination Delta table by (Liquid Clustering). Consumed by the pipeline; not forwarded to the source. |

### Source-specific `table_configuration` options

The `bills` table supports these options:

| Option | Required | Description | Example |
|---|---|---|---|
| `bill_ids` | **Yes** | Comma-separated list of BuildOps bill UUIDs to read. The connector trims whitespace around each value and reads a repeated ID only once. If this option is missing or empty, the pipeline fails with an error that explains why it is required. | `2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231, 3fa85f64-5717-4562-b3fc-2c963f66afa6` |
| `include` | No | Comma-separated list of nested collections and related records to embed in each bill. The connector sends it to BuildOps as a single comma-separated `include` value. The same list applies to every bill in `bill_ids`. Values are case-insensitive and duplicates are ignored. An unrecognized value fails the pipeline with an error that lists the allowed values. | `vendor,job,paymentTerm` |

**Allowed `include` values:**

| `include` value | Populates column | Related record |
|---|---|---|
| `billLines` | `billLines` | The bill's line items (typed `ARRAY<STRUCT>`) |
| `addresses` | `addresses` | The bill's addresses (typed `ARRAY<STRUCT>`) |
| `vendorDocumentAttachment` | `vendorDocumentAttachment` | The attached vendor document (typed `STRUCT`) |
| `purchaseOrder` | `purchaseOrder` | The bill's purchase order |
| `purchaseOrderReceipt` | `purchaseOrderReceipt` | The purchase order receipt |
| `vendor` | `vendor` | The vendor |
| `job` | `job` | The job |
| `project` | `project` | The project |
| `department` | `department` | The department |
| `orderedBy` | `orderedBy` | The employee who ordered the items |
| `projectManager` | `projectManager` | The project manager (employee) |
| `assignedTo` | `assignedTo` | The employee the bill is assigned to |
| `approvalNoteBy` | `approvalNoteBy` | The employee who wrote the approval note |
| `paymentTerm` | `paymentTerm` | The payment term |
| `taxRate` | `taxRate` | The tax rate |

`billLines`, `addresses`, and `vendorDocumentAttachment` fill their typed columns. Every other included relation is stored as a **JSON string** in the column with the same name. Its fields are not expanded into typed columns. Parse it downstream with `from_json` (for example, `from_json(vendor, schema_of_json('<sample vendor JSON>'))`) or with the `:` path syntax (for example, `vendor:name`). Relations you do not request stay null. Every relation you include makes each bill response larger, so request only the relations you need.

## Data Type Mapping

| BuildOps type | Example fields | Databricks type | Notes |
|---|---|---|---|
| string / UUID | `id`, `billNumber`, `vendorId`, `description` | `STRING` | All IDs are UUID strings. |
| string enum | `status`, `approvalStatus`, `syncStatus`, `invoicedStatus`, `billLines[].lineType` | `STRING` | Stored as plain strings. The set of values may grow over time. |
| number | `totalCost`, `freight`, `tax`, `billLines[].unitCost`, `billLines[].quantity` | `DOUBLE` | Money and quantity values. Cast to `DECIMAL` downstream if you need fixed-point precision. |
| integer | `version`, `billLines[].lineNumber` | `BIGINT` | |
| boolean | `isImported`, `isCreatedFromMobile`, `billLines[].taxable` | `BOOLEAN` | |
| Unix timestamp, **seconds** | `transactionDate`, `issuedBy`, `postingDate`, `dueDate`, `approvalNoteDateTime` | `BIGINT` (raw epoch value) | Not converted to `TIMESTAMP`. Convert with `timestamp_seconds(transactionDate)`. |
| Unix timestamp, **milliseconds** | `audit.createdDateTime`, `audit.lastUpdatedDateTime`, `audit.deletedDateTime` | `BIGINT` (raw epoch value) | Convert with `timestamp_millis(audit.createdDateTime)`. BuildOps documents `lastUpdatedDateTime` as a string, but the API returns a number. |
| ISO-8601 date-time string | `audit.createdDate`, `audit.lastUpdatedDate`, `audit.deletedDate` | `STRING` | For example `2023-05-30T13:16:46Z`. Convert with `to_timestamp(...)`. Often null; prefer the `*DateTime` epoch fields. |
| object (documented) | `audit`, `vendorDocumentAttachment` | `STRUCT` | Nested objects are kept as structs. An empty object is stored as null. |
| array of objects | `billLines`, `addresses`, `billLines[].purchaseOrderReceiptLineBillLines` | `ARRAY<STRUCT>` | |
| object (undocumented shape) | `include` relation columns, `audit.createdBy` / `lastUpdatedBy` / `deletedBy`, `billLines[].equipment`, `billLines[].purchaseOrderReceiptLineBillLines[].purchaseOrderReceiptLine` | `STRING` (JSON) | BuildOps does not document these objects' fields, so the connector stores each one as a JSON string. Parse it downstream. |

**Why timestamps are kept as raw numbers:** the BuildOps API mixes timestamp units. Bill-level dates are epoch **seconds**, while the audit dates are epoch **milliseconds**. The connector keeps these values exactly as BuildOps returns them, so a unit mismatch in live data cannot break ingestion or produce wrong dates silently. Before you convert a column, check that its magnitude is what you expect: about 10 digits for seconds, about 13 digits for milliseconds.

## How to Run

### Step 1: Clone/Copy the Source Connector Code

Follow the Lakeflow Community Connector UI. It guides you through setting up a pipeline with the BuildOps source connector code.

### Step 2: Configure Your Pipeline

1. Update the `pipeline_spec` in the main pipeline file (e.g., `ingest.py`).
2. Add a `bills` table entry with the required `bill_ids` option and, if you want related records, the `include` option. Both values are plain comma-separated strings, not JSON arrays.

```json
{
  "pipeline_spec": {
    "connection_name": "buildops_connection",
    "object": [
      {
        "table": {
          "source_table": "bills",
          "table_configuration": {
            "bill_ids": "2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231,3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "include": "vendor,job,paymentTerm"
          }
        }
      }
    ]
  }
}
```

- `connection_name` must point to a Unity Catalog connection configured with `client_id`, `client_secret`, `tenant_id`, `base_url` (for production), and `externalOptionsAllowList` set to `bill_ids,include`.
- To read bills into separate destination tables, for example one table per project, add more `bills` entries with different `bill_ids` values and different `destination_table` names.

3. (Optional) Customize the source connector code if needed for special use cases.

### Step 3: Run and Schedule the Pipeline

Run the pipeline with your standard Lakeflow / Databricks orchestration, for example a scheduled job. Each run re-reads every configured bill.

#### Best Practices

- **Start small**: begin with a handful of bill IDs to validate the credentials, `tenant_id`, `base_url`, and data shape before you add more.
- **Point at the right environment**: set `base_url` to `https://public-api.live.buildops.com` for production. The default is the development server.
- **Keep `bill_ids` accurate**: one bad or deleted ID fails the whole run, so remove IDs for bills that were deleted in BuildOps.
- **Size the ID list with run time in mind**: the connector makes one API request per bill, one at a time, on every run. Long ID lists mean longer runs and more API traffic.
- **Request only the relations you need**: every `include` value makes each response larger.
- **Set appropriate schedules**: because the table is a full snapshot, schedule frequency multiplies directly into API calls. Balance freshness against API usage.
- **Rate limits**: BuildOps does not document rate limits for the bills endpoint. The connector retries HTTP 429 and 5xx responses and network errors up to 5 attempts. It uses exponential backoff that starts at 1 second and caps at 60 seconds, and it honors any `Retry-After` header.

#### Troubleshooting

**Common Issues:**

- **`missing required connection option(s)`**: `client_id`, `client_secret`, or `tenant_id` is missing or empty on the connection.
- **`BuildOps token exchange failed`**: the client ID or secret is wrong, or the credentials belong to a different environment than `base_url`. For example, production credentials fail against the default development URL. Check both values and set `base_url` explicitly.
- **HTTP 401 after re-authenticating**: the connector already retried once with a fresh token. The credentials are probably revoked or invalid. Contact BuildOps support.
- **HTTP 403 (forbidden) on a bill**: the credentials are not authorized for the configured `tenant_id`. Check the tenant ID, for example with the `/v1/auth/scope` call shown above.
- **HTTP 404 (not found) on a bill**: the ID in `bill_ids` does not exist in this tenant and environment. The bill may have been deleted, it may belong to another tenant, or the ID may be wrong or be a bill number instead of a UUID. Remove or correct the ID and run the pipeline again.
- **`requires the 'bill_ids' table option`**: `bill_ids` is missing from `table_configuration`, or `externalOptionsAllowList` on the connection does not include `bill_ids`, so the option is dropped before it reaches the connector.
- **`Invalid value(s) for the 'include' table option`**: one of the `include` values is not in the allowed list above. Check the spelling. Values are case-insensitive.
- **Related-record, `billLines`, `addresses`, or `vendorDocumentAttachment` column is null**: that value was not listed in `include`, `include` is not in `externalOptionsAllowList`, or the bill has no such related record.
- **Unexpected dates after conversion**: check whether the column is in seconds or milliseconds (see [Data Type Mapping](#data-type-mapping)) and use `timestamp_seconds` or `timestamp_millis` to match.

### Known Limitations

- **No list or discovery endpoint**: bills are read only by ID, so `bill_ids` is required and new bills are not picked up automatically.
- **No incremental sync**: the BuildOps API has no "changed since" filter for bills, so every run is a full snapshot of the configured IDs. To track changes yourself, compare `audit.lastUpdatedDate` / `audit.lastUpdatedDateTime` or `version` between runs, or use `SCD_TYPE_2`.
- **No deletes feed**: deletions in BuildOps cannot be detected directly. A deleted bill that is still in `bill_ids` causes a 404 and the run fails.
- **Timestamp unit quirks**: bill-level dates are epoch seconds and audit dates are epoch milliseconds. All of them are kept as raw values (see [Data Type Mapping](#data-type-mapping)).
- **Undocumented nested objects**: related records from `include`, audit user references, and equipment are stored as JSON strings, not typed structs, because BuildOps does not document their fields.
- **Single table**: only `bills` is supported. Other BuildOps objects, such as purchase orders, vendors, and jobs, are available only as JSON embedded through `include`.

## References

- Connector implementation: `src/databricks/labs/community_connector/sources/buildops/buildops.py`
- Connector API documentation and schema notes: `src/databricks/labs/community_connector/sources/buildops/buildops_api_doc.md`
- BuildOps public API servers:
  - Production: `https://public-api.live.buildops.com`
  - Development: `https://public-api.dev.buildops.com`
- BuildOps public API endpoints used by this connector:
  - `POST /v1/auth/token` (client-credentials token exchange)
  - `GET /v2/bills/{billId}` (read a single bill, with optional `include`)
- For API access, credentials, and tenant information, contact BuildOps support or your BuildOps account manager.
