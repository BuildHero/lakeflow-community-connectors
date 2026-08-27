# Lakeflow NetSuite Community Connector

This documentation provides setup instructions and reference information for
the NetSuite source connector. The connector ingests vendor bill records
from a NetSuite account via SuiteQL (the SuiteTalk REST Web Services SQL
query endpoint).

## Prerequisites

- A NetSuite account with SuiteTalk REST Web Services enabled (Setup >
  Company > Enable Features > SuiteCloud tab).
- A NetSuite integration record with **Token-Based Authentication (TBA)**
  enabled, plus an access token issued for a user/role with permission to
  view vendor bills (Transactions > Bills, and SuiteAnalytics / SuiteQL
  execute permission).

## Setup

### Required Connection Parameters

To configure the connector, provide the following parameters in your
connector options:

| Parameter | Type | Required | Description | Example |
|---|---|---|---|---|
| `account_id` | String | Yes | NetSuite account ID. Production accounts are numeric; sandbox/other accounts append a suffix (e.g. `_SB1`). | `1234567` or `1234567_SB1` |
| `consumer_key` | String | Yes | Consumer key from the NetSuite integration record. | — |
| `consumer_secret` | String | Yes | Consumer secret paired with `consumer_key`. | — |
| `token_id` | String | Yes | Access token ID for the integration record + user/role. | — |
| `token_secret` | String | Yes | Access token secret paired with `token_id`. | — |
| `externalOptionsAllowList` | String | Yes | Comma-separated list of table-specific options to pass through. Must be set to: `max_records_per_batch,window_seconds,limit,start_timestamp` | `max_records_per_batch,window_seconds,limit,start_timestamp` |

This connector authenticates with **Token-Based Authentication (TBA)** only
(NetSuite's OAuth 1.0a-style HMAC-signed request scheme). It does not use
OAuth 2.0 — see "A note on authentication" below.

### Obtaining Credentials

1. In NetSuite, go to **Setup > Integration > Manage Integrations > New**
   and create an integration record with the **Token-Based Authentication**
   checkbox enabled under the SuiteCloud tab. Copy the generated
   `consumer_key` / `consumer_secret` immediately — NetSuite only shows
   them once.
2. Go to **Setup > Users/Roles > Access Tokens > New**, select the
   integration record from step 1, choose the user and role that should
   have API access (the role needs view permission on vendor bills), and
   save. Copy the generated `token_id` / `token_secret` immediately — same
   one-time-visibility rule applies.
3. Note your NetSuite **account ID** (visible in the account URL, or under
   Setup > Company > Company Information).

### A note on authentication

NetSuite is phasing out **new** TBA-based integrations starting with its
2027.1 release (existing TBA integrations keep working past that date).
NetSuite's alternative, OAuth 2.0, uses a certificate-based
machine-to-machine flow (the client signs a JWT with a private key
uploaded to NetSuite, rather than presenting a static client secret) —
materially different from a typical OAuth 2.0 client-credentials setup.
This connector uses TBA only for this release; migrating to NetSuite's
OAuth 2.0 is a known follow-up, not yet implemented.

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways
via the UI:
1. Follow the Lakeflow Community Connector UI flow from the "Add Data"
   page.
2. Select any existing Lakeflow Community Connector connection for this
   source or create a new one.
3. Set `externalOptionsAllowList` to
   `max_records_per_batch,window_seconds,limit,start_timestamp` to enable
   per-table configuration of these options.

The connection can also be created using the standard Unity Catalog API.

## Supported Objects

The connector supports one object in this release:

| Object | Primary Key | Ingestion Mode | Cursor Field | Delete Sync |
|---|---|---|---|---|
| `vendorbill` | `id` | CDC | `lastmodifieddate` | No |

### vendorbill

Vendor bill **header** records — sourced from NetSuite's built-in
`transaction` SuiteQL table, filtered to `type = 'VendBill'`. Fields
include the bill number (`tranid`), vendor (`entity`), dates (`trandate`,
`duedate`), currency and total (`currency`, `exchangerate`,
`foreigntotal`), status, memo, and NetSuite's internal `id` as the primary
key.

**Line-item detail is not included in this release.** A vendor bill's
individual line items live in a separate NetSuite table
(`transactionline`) and are not currently ingested by this connector; this
is a deliberate scope decision for the initial release, not an oversight.

**`subsidiary` may come back `null` on non-OneWorld accounts.** On
NetSuite accounts without OneWorld/multi-subsidiary enabled, `subsidiary`
isn't a valid SuiteQL column at all (verified live: NetSuite rejects it
with an HTTP 400 "Unknown identifier" error rather than returning null).
The connector detects this specific error on first use and automatically
falls back to omitting `subsidiary` from its query for the rest of that
run — the column is still declared in the schema, so it's always present
in output rows, just consistently `null` for accounts where NetSuite
doesn't support it. OneWorld accounts are unaffected and get real
subsidiary IDs as before. See `netsuite_api_doc.md` Known Quirks #7 for
the live-verified details.

Incremental sync uses `lastmodifieddate` with a sliding time window
(`window_seconds`) to stay under NetSuite's SuiteQL 100,000-row-per-query
ceiling on large accounts. Deletions/voids of vendor bills are **not**
synchronized in this release — deleted records only appear as gaps on the
next full comparison, not as explicit delete events.

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

These are set inside the `table_configuration` map alongside any
source-specific options:

| Option | Required | Description |
|---|---|---|
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. |
| `primary_keys` | No | List of columns to override the connector's default primary keys |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking |
| `cluster_by` | No | List of columns to cluster the destination Delta table by (Liquid Clustering) |

### NetSuite-specific `table_configuration` options (for `vendorbill`)

| Option | Required | Description |
|---|---|---|
| `window_seconds` | No | Size of the sliding `lastmodifieddate` time window per SuiteQL query, in seconds. Default: `86400` (1 day). Lower this on very high-volume accounts to stay under the 100,000-row SuiteQL query ceiling. |
| `max_records_per_batch` | No | Maximum records returned per `read_table` call (admission control). Default: `200`. |
| `limit` | No | SuiteQL page size (`limit` query parameter) used when paginating within a window. Default: `1000`. |
| `start_timestamp` | No | ISO-shaped timestamp (`YYYY-MM-DDTHH:MM:SSZ`) to use as the initial lower bound on the very first sync, when no checkpointed offset exists yet. **Despite the trailing `Z`, provide this in the account's own configured timezone, not true UTC** — NetSuite's SuiteQL renders `lastmodifieddate` in the account's timezone preference, live-verified to not always be UTC; see `netsuite_api_doc.md` Known Quirks #8. If omitted, the connector auto-discovers the oldest vendor bill's `lastmodifieddate`. |

## Data Type Mapping

| NetSuite SuiteQL wire type | Ingested type | Notes |
|---|---|---|
| Numeric string (e.g. `id`, `entity`, `currency`) | Long | NetSuite returns all values — including numbers — as JSON strings; the pipeline converts them. |
| Numeric string (e.g. `exchangerate`, `foreigntotal`) | Double | Same string-to-numeric conversion. |
| Date/timestamp string | String (ISO 8601-shaped) | The connector explicitly formats `trandate`, `duedate`, `createddate`, and `lastmodifieddate` as ISO 8601-shaped text in its query, to avoid NetSuite's account-locale date format ambiguity. **`createddate`/`lastmodifieddate`'s trailing `Z` is a formatting label, not a guarantee of true UTC** — live-verified (2026-08-25) to reflect the account's configured timezone preference instead; see `netsuite_api_doc.md` Known Quirks #8. |
| Plain string | String | — |

## How to Run

### Step 1: Clone/Copy the Source Connector Code
Follow the Lakeflow Community Connector UI, which will guide you through
setting up a pipeline using the selected source connector code.

### Step 2: Configure Your Pipeline
1. Update the `pipeline_spec` in the main pipeline file (e.g., `ingest.py`).
2. To tune incremental sync scoping for `vendorbill`, set
   `window_seconds` / `max_records_per_batch` / `limit` in its
   `table_configuration`:
```json
{
  "pipeline_spec": {
      "connection_name": "...",
      "object": [
        {
            "table": {
                "source_table": "vendorbill",
                "table_configuration": {
                    "window_seconds": "86400",
                    "max_records_per_batch": "200"
                }
            }
        }
      ]
  }
}
```
3. (Optional) Customize the source connector code if needed for special
   use cases.

### Step 3: Run and Schedule the Pipeline

#### Best Practices

- **Start Small**: Begin with a short `window_seconds` (e.g. 3600) to
  validate the pipeline before widening it.
- **Use Incremental Sync**: Reduces API calls and improves performance.
- **Set Appropriate Schedules**: Balance data freshness requirements with
  NetSuite's concurrency (default 15 simultaneous requests per account,
  shared across all integrations) and frequency (per-minute/per-day) API
  governance limits.

#### Troubleshooting

**Common Issues:**
- `401`/`403` errors usually mean the TBA credentials are wrong, the
  integration record's TBA checkbox isn't enabled, or the mapped role
  lacks vendor-bill view / SuiteQL execute permission.
- A `RuntimeError` about the SuiteQL 100,000-row ceiling means
  `window_seconds` is too large for the account's vendor-bill volume in
  that window — lower it.
- `subsidiary` reading `null` for every record is expected on accounts
  without OneWorld/multi-subsidiary enabled — see "vendorbill" above. It
  is not a connector error.

## References

- [SuiteTalk REST Web Services overview](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_1540391670.html)
- [Executing SuiteQL Queries Through REST Web Services](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157909186990.html)
- [OAuth 2.0 Client Credentials Setup](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html)
- See `netsuite_api_doc.md` in this directory for the full research log and
  known quirks.
