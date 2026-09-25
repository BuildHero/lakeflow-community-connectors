# Lakeflow Sage Intacct Community Connector

This documentation describes how to configure and use the **Sage Intacct** Lakeflow community connector to ingest accounting data from Sage Intacct's XML Web Services Gateway into Databricks.

## Prerequisites

- **A Sage Intacct company** with the Accounts Receivable, Accounts Payable, and General Ledger modules enabled (the source of the `customers`, `vendors`, `invoices`, `bills`, and `gl_entries` tables).
- **A Web Services Sender ID and password**, issued by Sage Intacct to your organization or integration partner, and authorized for the target company. This identifies the calling application (distinct from any individual user account).
- **An Intacct user ID and password** with API access enabled and permissions on the Accounts Receivable, Accounts Payable, and General Ledger modules. The connector uses these once, at startup, to obtain an API session; it does not send the user's password on every call.
- **Network access**: the environment running the connector must be able to reach `https://api.intacct.com`.
- **Lakeflow / Databricks environment**: a workspace where you can register a Lakeflow community connector and run ingestion pipelines.

## Setup

### Required Connection Parameters

Provide the following **connection-level** options when configuring the connector. These correspond to the connection options exposed by the connector.

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `sender_id` | string | yes | Web Services Sender ID issued by Sage Intacct to your integration. Identifies the calling application to the XML Gateway. | `MYORG_SENDER` |
| `sender_password` | string | yes | Password for the Sender ID. | `********` |
| `company_id` | string | yes | Target Intacct company ID whose data will be read. | `MYCOMPANY` |
| `user_id` | string | yes | Intacct user ID with API access and AR/AP/GL module permissions. Used once to obtain an API session. | `api-user` |
| `user_password` | string | yes | Password for `user_id`. Used once to obtain a session; not stored or resent on every call. | `********` |
| `location_id` | string | no | Entity/location ID. Only needed for multi-entity companies where you want to scope reads to a specific location. | `100` |
| `base_url` | string | no | Base URL for the XML Gateway. Defaults to `https://api.intacct.com/ia/xml/xmlgw.phtml`. Override only for a custom/alternative endpoint. | `https://api.intacct.com/ia/xml/xmlgw.phtml` |
| `externalOptionsAllowList` | string | yes | Comma-separated list of table-specific option names that are allowed to be passed through to the connector. This connector supports table-specific options, so this parameter must be set. | `start_timestamp,window_seconds,max_records_per_batch,pagesize` |

The full list of supported table-specific options for `externalOptionsAllowList` is:
`start_timestamp,window_seconds,max_records_per_batch,pagesize`

> **Note**: There is no OAuth flow for this connector — the Sage Intacct XML Gateway authenticates with the Sender ID/password and user credentials above, not OAuth tokens.

### Obtaining the Required Parameters

- **Sender ID / Sender password**:
  1. If your organization does not already have a Web Services Sender ID, request one from your Sage Intacct account representative or implementation partner.
  2. Once issued, have a Sage Intacct company administrator authorize that Sender ID for the target company (in Intacct, under company setup / Web Services authorizations). Without this authorization step, requests using the Sender ID will be rejected even with valid user credentials.
- **User ID / password**:
  1. Use an existing Intacct user, or create a dedicated integration user in **Company → Users**.
  2. Grant the user **Web Services (API)** access and permissions to the Accounts Receivable, Accounts Payable, and General Ledger modules — at minimum, read/view permissions on Customers, Vendors, AR Invoices, AP Bills, and GL account activity.
  3. Note the `company_id` shown for the company you want to read from (and the `location_id` if the company is multi-entity and you want to scope reads to one location).

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:

1. Follow the **Lakeflow Community Connector** UI flow from the **Add Data** page.
2. Select any existing Lakeflow Community Connector connection for this source or create a new one.
3. Set `externalOptionsAllowList` to `start_timestamp,window_seconds,max_records_per_batch,pagesize` (required for this connector to pass table-specific options).

The connection can also be created using the standard Unity Catalog API.

## Supported Objects

The Sage Intacct connector exposes a **static list** of tables:

- `customers`
- `vendors`
- `invoices`
- `bills`
- `gl_entries`

`invoices` and `bills` cover only the AR invoice / AP bill **header** records (`ARINVOICE` / `APBILL`); line-item detail is not ingested by this connector.

### Object summary, primary keys, and ingestion mode

| Table | Description | Ingestion Type | Primary Key | Incremental Cursor |
|---|---|---|---|---|
| `customers` | AR customer master records | `cdc` (upsert) | `RECORDNO` | `WHENMODIFIED` |
| `vendors` | AP vendor master records | `cdc` (upsert) | `RECORDNO` | `WHENMODIFIED` |
| `invoices` | AR invoice headers (amounts, dates, status, customer link) | `cdc` (upsert) | `RECORDNO` | `WHENMODIFIED` |
| `bills` | AP bill headers (amounts, dates, status, vendor link) | `cdc` (upsert) | `RECORDNO` | `WHENMODIFIED` |
| `gl_entries` | Posted general-ledger detail across every subledger (AP, AR, GL, and others) | `cdc` (upsert) | `RECORDNO` | `WHENMODIFIED` |

`RECORDNO` is Intacct's internal, system-generated, immutable record number for each object and is used as the primary key rather than a business-facing ID (e.g. `CUSTOMERID`, `VENDORID`, invoice/bill numbers), which are not guaranteed unique.

**Delete handling**: Sage Intacct does not expose a delete-tombstone feed for these five objects, so this connector does not support delete synchronization (`cdc_with_deletes`). Records are not typically hard-deleted in Intacct once used in a transaction — customers/vendors are deactivated (surfaced as a `STATUS` change) and invoices/bills are voided or reversed (surfaced as a `STATE` change) — both of which are picked up as ordinary updates via `WHENMODIFIED`.

**Schema highlights**:
- On `customers` and `vendors`, `STATUS` (`active`/`inactive`) reflects deactivation rather than deletion.
- On `invoices`, `STATE` and `MODULEKEY` (native AR invoice vs. Order-Entry-originated) indicate document lifecycle and origin.
- On `bills`, `STATE` (draft/submitted/approved/posted/declined) and `MODULEKEY` (native AP bill vs. Purchasing-originated) work the same way.
- On `gl_entries`, `WHENCREATED` is **not** a creation timestamp — Sage documents it as the user-entered transaction date on this object. Use `AUWHENCREATED` if you need the true record-creation audit timestamp. `MODULEKEY` identifies which subledger (AP, AR, GL, Cash Management, etc.) originated the posted line.

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
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. Applicable since all 5 tables use CDC ingestion. |
| `primary_keys` | No | List of columns to override the connector's default primary keys (`RECORDNO`) |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking |
| `cluster_by` | No | List of columns to cluster the destination Delta table by (Liquid Clustering). Consumed by the pipeline; not forwarded to the source. |

### Special `table_configuration` options

These options are specific to this connector and control how each incremental read is windowed against the Intacct XML Gateway. They apply to all 5 tables:

| Option | Required | Description |
|---|---|---|
| `start_timestamp` | No | ISO-8601 timestamp used as the initial cursor for a table's very first sync, when no prior offset exists. If omitted, the connector automatically discovers and starts from the oldest existing record for that table. Ignored on subsequent runs once an offset has been checkpointed. |
| `window_seconds` | No | Size, in seconds, of the sliding `WHENMODIFIED` time window read per batch. Defaults to `86400` (1 day). Sage Intacct recommends always bounding queries against `gl_entries` (`GLDETAIL`) by date/time, since it is a cross-subledger reporting view and unfiltered queries can time out; narrower windows also reduce the chance of hitting page-size limits on very active companies. |
| `max_records_per_batch` | No | Caps the number of records returned per read call for a table. Defaults to the API's maximum page size (`2000`). |
| `pagesize` | No | Page size used for each underlying API call to the XML Gateway. Defaults to `1000`; capped at Intacct's documented maximum of `2000`. |

## Data Type Mapping

Sage Intacct field types are mapped to Spark types as follows:

| Intacct Data Type | Example Fields | Spark Type | Notes |
|---|---|---|---|
| `TEXT` | `CUSTOMERID`, `NAME`, `DESCRIPTION`, `STATE` | `StringType` | Includes enum-like fields (e.g. `STATUS`, `MODULEKEY`), which are represented as their raw string value. |
| `INTEGER` | `RECORDNO`, `GLENTRYKEY`, `LINE_NO` | `LongType` | All identifiers are stored as 64-bit integers to avoid overflow. |
| `DECIMAL` / currency | `AMOUNT`, `TRX_AMOUNT`, `CREDITLIMIT`, `TOTALDUE`, `EXCHANGE_RATE` | `DecimalType(18, 4)` | Base-currency and transaction-currency amounts are both preserved as separate columns where the source object exposes both. |
| `BOOLEAN` | `ONHOLD`, `ONETIME` | `BooleanType` | Intacct's XML `true`/`false` values are normalized to native booleans. |
| `DATE` | `WHENCREATED`, `DATEPOSTED`, `BATCH_DATE`, `ENTRY_DATE` | `DateType` | Intacct's `mm/dd/yyyy` wire format is normalized to ISO-8601 before being cast. On `gl_entries`, `WHENCREATED` holds the user-entered transaction date rather than a creation date — see the schema highlights above. |
| `TIMESTAMP` | `WHENMODIFIED`, `AUWHENCREATED` | `TimestampType` | Intacct's `mm/dd/yyyy hh:mm:ss` wire format is normalized to ISO-8601. `WHENMODIFIED` is the incremental cursor for every table. |

Only header-level, scalar fields are modeled for this connector version — nested contact/dimension objects and invoice/bill line items are not ingested.

## How to Run

### Step 1: Clone/Copy the Source Connector Code

Follow the Lakeflow Community Connector UI, which will guide you through setting up a pipeline using the Sage Intacct connector code.

### Step 2: Configure Your Pipeline

1. Update the `pipeline_spec` in your main pipeline file (e.g., `ingest.py`).
2. Reference the Unity Catalog connection configured with your Sender ID and user credentials, and list the tables you want to ingest.

```json
{
  "pipeline_spec": {
    "connection_name": "intacct_connection",
    "object": [
      {
        "table": {
          "source_table": "customers"
        }
      },
      {
        "table": {
          "source_table": "vendors"
        }
      },
      {
        "table": {
          "source_table": "invoices",
          "table_configuration": {
            "start_timestamp": "2024-01-01T00:00:00+00:00",
            "window_seconds": "86400"
          }
        }
      },
      {
        "table": {
          "source_table": "bills",
          "table_configuration": {
            "window_seconds": "86400"
          }
        }
      },
      {
        "table": {
          "source_table": "gl_entries",
          "table_configuration": {
            "start_timestamp": "2024-01-01T00:00:00+00:00",
            "window_seconds": "3600",
            "max_records_per_batch": "2000"
          }
        }
      }
    ]
  }
}
```

3. (Optional) Customize the source connector code if needed for special use cases.

### Step 3: Run and Schedule the Pipeline

#### Best Practices

- **Start small**: begin by syncing `customers` and `vendors` (smaller, slower-changing tables) before adding `invoices`, `bills`, and `gl_entries`.
- **Narrow the window for high-volume tables**: `gl_entries` is a cross-subledger reporting view and can be large in active companies. If a run is slow or times out, reduce `window_seconds` (and/or `pagesize` / `max_records_per_batch`) so each batch scopes a smaller time range.
- **Set a `start_timestamp` for large history**: on the first backfill of a long-lived company, either omit `start_timestamp` to pull full history from the oldest record, or set it to a recent cutoff to limit how much history is ingested initially.
- **Respect the per-company concurrency limit**: Sage Intacct's standard service tier allows only **one concurrent API job per company**. A second request queues, and a third or later request waits up to ~30 seconds before erroring. Avoid running multiple pipelines (or many parallel table syncs) against the same Intacct company at the same time; schedule them sequentially or stagger their start times instead.

#### Troubleshooting

**Common Issues:**

- **Authentication/session errors**: verify `sender_id`/`sender_password` are correct and that the Sender ID has been authorized for the target `company_id` by a company administrator; verify `user_id`/`user_password` are correct and that the user has API access enabled.
- **Permission errors on specific tables**: if some tables sync but others fail, confirm the Intacct user has module permissions (view/read) for Accounts Receivable, Accounts Payable, and General Ledger as applicable to the failing table.
- **Timeouts or slow syncs on `gl_entries`**: reduce `window_seconds` — Sage's own guidance is that unfiltered or loosely time-filtered queries against this object can be slow, since it aggregates every subledger's posted activity.
- **Requests failing under load / concurrency errors**: another job may already be running against the same company (see the concurrency note above); retry after the current job finishes, or avoid scheduling overlapping runs.
- **Multi-entity companies missing expected records**: if the target company has multiple entities/locations, set `location_id` to scope reads to the correct entity.

## References

- Connector implementation: `src/databricks/labs/community_connector/sources/intacct/intacct.py`
- Connector API research: `src/databricks/labs/community_connector/sources/intacct/intacct_api_doc.md`
- Official docs — XML Web Services overview: https://developer.intacct.com/web-services/
- Official docs — XML request structure: https://developer.intacct.com/web-services/requests/
- Official docs — Queries (`query`/`readByQuery`/pagination/`lookup`): https://developer.intacct.com/web-services/queries/
- Official docs — Customers: https://developer.intacct.com/api/accounts-receivable/customers/
- Official docs — Invoices (ARINVOICE): https://developer.intacct.com/api/accounts-receivable/invoices/
- Official docs — Vendors: https://developer.intacct.com/api/accounts-payable/vendors/
- Official docs — Bills (APBILL): https://developer.intacct.com/api/accounts-payable/bills/
- Official docs — General Ledger Details (GLDETAIL): https://developer.intacct.com/api/general-ledger/general-ledger-detail/
- Official docs — FAQ (concurrency/throughput): https://developer.intacct.com/support/faq/
