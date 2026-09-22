# Lakeflow Miter Community Connector

This documentation provides setup instructions and reference information for the **Miter** source connector, which ingests general-ledger data from the Miter v2 REST API into Databricks.

This version of the connector covers Miter's four general-ledger objects: `ledger_accounts`, `ledger_entries`, `ledger_line_items`, and `ledger_mappings`. Other Miter objects (team members, payrolls, timesheets, jobs, and so on) are **not** available through this connector.

## Prerequisites

- **Miter account**: A Miter company account whose general-ledger data you want to replicate.
- **Miter API token**: A token issued for that company. Miter authenticates with a single HTTP Bearer token; there is no OAuth app to register and no client ID/secret.
  - Tokens are **scoped per resource and action**. The token must grant read access to ledger accounts, ledger entries, ledger line items, and ledger mappings — otherwise those objects return `403`.
  - Tokens are **environment-specific**: a token issued in Miter's staging environment is rejected by the production API, and vice versa.
- **Network access**: The environment running the pipeline must be able to reach `https://api.miter.com` (or `https://api.staging.miter.com` when using a staging token).
- **Databricks workspace**: A workspace where you can create a Unity Catalog connection and run a Lakeflow ingestion pipeline.

## Setup

### Required Connection Parameters

Provide the following parameters when creating the Unity Catalog connection for this connector:

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `api_token` | string (secret) | Yes | Miter API token, sent to the API as an `Authorization: Bearer` header. Must have read scopes for the ledger objects you intend to sync. | `mtr_live_xxx...` |
| `base_url` | string | No | Root URL of the Miter v2 REST API. Defaults to the production endpoint `https://api.miter.com/api/v2`. Set it to `https://api.staging.miter.com/api/v2` when `api_token` was issued in Miter's staging environment. | `https://api.staging.miter.com/api/v2` |
| `externalOptionsAllowList` | string | Yes | Comma-separated list of table-specific option names that the connection is allowed to pass through to the connector. This connector supports table-specific options, so this parameter must be set. | See the definitive list below. |

The full, definitive list of table-specific options for `externalOptionsAllowList` is:

```
page_size,window_seconds,max_partitions,max_records_per_batch,start_timestamp,lookback_seconds,max_pages,parent_ids,max_parents,parents_per_partition
```

> **Note**: The options above are **not** connection parameters. They are set per table in the pipeline specification under `table_configuration`, and each option name must appear in `externalOptionsAllowList` for the connection to forward it.

### Obtaining the Required Parameters

1. **API token** — Generate an API token for your company in the Miter application (Miter's token-issuance screen is documented in Miter's own product documentation; contact `support@miter.com` if you cannot find it or need a token with additional scopes).
2. **Verify the token and its scopes** — Call Miter's `/ping` endpoint with the token. The response reports the token's name, granted scopes, and its rate limits:

   ```
   GET https://api.miter.com/api/v2/ping
   Authorization: Bearer <API_TOKEN>
   Accept: application/json
   ```

   Confirm the returned `scopes` include read access to the ledger objects. A `403` on an otherwise-valid request means the object is outside the token's granted scopes.
3. **Base URL** — Leave `base_url` unset for production tokens. If your token was issued in Miter's staging environment, you **must** set `base_url` to `https://api.staging.miter.com/api/v2`; otherwise every request fails with `401`.
4. **Store the token securely** — Supply it as the `api_token` connection parameter; it is stored as a secret.

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:

1. Follow the **Lakeflow Community Connector** UI flow from the **Add Data** page.
2. Select any existing Lakeflow Community Connector connection for this source, or create a new one and supply `api_token` (and `base_url` if you are on staging).
3. Set `externalOptionsAllowList` to:
   `page_size,window_seconds,max_partitions,max_records_per_batch,start_timestamp,lookback_seconds,max_pages,parent_ids,max_parents,parents_per_partition`

The connection can also be created using the standard Unity Catalog API.

## Supported Objects

The connector exposes a **static list** of four tables. Use the exact lowercase names below as `source_table`:

| Table | Source endpoint | Description | Ingestion Type | Primary Key | Incremental Cursor |
|---|---|---|---|---|---|
| `ledger_accounts` | `GET /ledger_accounts` | Chart-of-accounts entries (GL accounts), including classification, hierarchy, and active status. | `cdc` | `id` | `updated_at` |
| `ledger_entries` | `GET /ledger_entries` | Ledger entry headers — one per posted accounting event, with the Miter objects that generated it. | `cdc` | `id` | `updated_at` |
| `ledger_line_items` | `GET /ledger_entries/{ledger_entry_id}/line_items` | Individual debit/credit lines belonging to a ledger entry, with full cost-allocation dimensions. | `cdc` | `id` | `updated_at` |
| `ledger_mappings` | `GET /ledger_mappings` | Named GL mapping configurations: default accounts per ledger line type plus per-earning-type and per-benefit-type overrides. | `cdc` | `id` | `updated_at` |

### Incremental ingestion

All four tables are ingested incrementally in `cdc` (change-data-capture upsert) mode:

- The cursor field is `updated_at` for every table. Each run requests records whose `updated_at` is strictly greater than the previously committed cursor and less than or equal to the run's start time, sorted ascending.
- Records are upserted into the destination table on `id`. Rows that change in Miter are overwritten in place.
- On the first run, the starting point is either the `start_timestamp` you configure or — when that option is omitted — the timestamp of the oldest record in the table, which the connector discovers automatically so the initial backfill has a bounded lower edge.
- Long cursor ranges are split into time windows so history can be read in parallel and so each run makes bounded progress. See `window_seconds`, `max_partitions`, and `max_records_per_batch` below.

### No delete detection

**The Miter API provides no way to detect deleted records** — there is no `deleted_at` / `is_deleted` field, no tombstone or soft-delete marker, no deleted-records endpoint, and no webhook or audit-log endpoint on any object. As a result:

- All four tables use `cdc` (incremental upsert) and **do not** support delete synchronization (`cdc_with_deletes`).
- If a record is deleted in Miter, it simply stops appearing in API responses; the row remains in the destination table indefinitely.
- If you need deletion accuracy, reconcile periodically by taking a full read of the table (clear the pipeline's stored progress, or read into a staging table with no `start_timestamp`) and diffing the set of `id` values against your destination table.

### `ledger_line_items` is a nested object

`ledger_line_items` has no global list endpoint in Miter. It is read **once per parent ledger entry**, so the connector first enumerates ledger-entry IDs and then issues one paginated request per parent.

- Parents are enumerated **unbounded by the child cursor**, because a line item can be updated long after its parent entry was; restricting parents to the current time window would silently drop those children. Every run therefore lists all ledger-entry IDs before reading line items.
- This makes `ledger_line_items` by far the most API-intensive table. Use `parent_ids`, `max_parents`, and `parents_per_partition` to control its cost and parallelism.
- Each line item carries `ledger_entry_id`, so it can be joined back to `ledger_entries`.

### Schema highlights

- **`ledger_entries.source_objects`** is a struct of references to the Miter objects that produced the entry (`payroll_id`, `check_payment_id`, `reimbursement_id`, `expense_id`, `bill_ids`, `recoded_timesheet_ids`, `equipment_timesheet_ids`, and related fields). Miter may return it as an empty object; the connector surfaces that as `null` rather than an empty struct.
- **`ledger_mappings.defaults`**, **`earning_type_accounts`**, **`benefit_type_expense_accounts`**, and **`benefit_type_liability_accounts`** are open-keyed objects — their keys are ledger line types, earning-type codes, or benefit-type codes, including customer-defined ones. They are ingested as `MAP<STRING, STRING>` (key → ledger account ID), not as fixed columns. Query them with map accessors, for example `defaults['cash']`.
- **`ledger_line_items.custom_field_values`** is an array of `{custom_field_id, value}` structs. Miter's `value` is polymorphic (string, number, boolean, or array), so it is normalized to a string; non-scalar values are JSON-encoded.
- **`ledger_line_items.amount`** and **`hours`** are doubles. Miter's API does not distinguish integers from decimals, so all numeric fields are ingested as `DOUBLE`.
- **`ledger_line_items`** carries a wide set of nullable cost-allocation dimension IDs (`job_id`, `activity_id`, `department_id`, `location_id`, `class_id`, `cost_type_id`, `company_entity_id`, `work_order_id`, and others). Most are `null` on any given row depending on how the line was generated.
- **`void`**, **`recoded`**, and **`manually_edited`** on `ledger_line_items` flag lines tied to voided payrolls, recoded lines, and manual edits — include them in downstream financial aggregations to avoid double-counting.

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
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. All four Miter tables use CDC ingestion, so both values are applicable. |
| `primary_keys` | No | List of columns to override the connector's default primary keys (`id` for every table) |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking (use `updated_at`) |
| `cluster_by` | No | List of columns to cluster the destination Delta table by (Liquid Clustering). Consumed by the pipeline; not forwarded to the source. |

### Source-specific `table_configuration` options

All options below are optional and apply to every table unless noted. Each one you use must also be listed in the connection's `externalOptionsAllowList`.

| Option | Type | Default | Applies to | Description |
|---|---|---|---|---|
| `start_timestamp` | ISO 8601 datetime string | (oldest record, discovered automatically) | All tables | Lower bound for the very first read. Set this to skip old history — for example `2025-01-01T00:00:00Z`. Ignored once the pipeline has committed progress. |
| `page_size` | integer | `100` | All tables | Records requested per API call. Valid range 1–1000; larger values are capped at 1000. |
| `window_seconds` | integer | `86400` (1 day) | All tables | Width of each time slice the cursor range is divided into. Smaller windows mean more, smaller units of work; larger windows mean fewer, heavier requests. |
| `max_partitions` | integer | `200` | All tables | Upper bound on the number of parallel time slices created per run. When the cursor range would produce more slices than this, the window is widened to fit. |
| `max_records_per_batch` | integer | `5000` | All tables except `ledger_line_items` | Caps how many records a single non-parallel read returns before committing progress and continuing on the next read. Not applied to `ledger_line_items`, whose per-parent fan-out must complete a whole window; use `window_seconds` to size those batches instead. |
| `lookback_seconds` | integer | `0` | All tables | Seconds subtracted from the resume point at query time, so records whose `updated_at` landed slightly behind an already-committed cursor are re-read. Re-read rows are upserted, not duplicated. Useful if you observe late-arriving updates. |
| `max_pages` | integer | `0` (unlimited) | All tables | Safety cap on the number of pages fetched per paginated request. Use a small value for smoke tests; leave at `0` for production or data will be silently truncated. |
| `parent_ids` | comma-separated string | (all ledger entries) | `ledger_line_items` only | Restricts the sync to line items belonging to these ledger-entry IDs. Skips the parent-enumeration pass entirely. |
| `max_parents` | integer | `0` (unlimited) | `ledger_line_items` only | Caps how many parent ledger entries are visited per run. Useful for bounding a first test run; leave at `0` for production or line items will be incomplete. |
| `parents_per_partition` | integer | `20` | `ledger_line_items` only | How many parent ledger entries each parallel unit of work handles. Lower values increase parallelism at the cost of more tasks. |

## Data Type Mapping

| Miter API type | Example fields | Databricks / Spark type | Notes |
|---|---|---|---|
| `string` | `label`, `description`, `memo`, `name` | `STRING` | |
| `string` (ObjectId) | `id`, `ledger_entry_id`, `ledger_account_id`, all `*_id` fields | `STRING` | 24-character hexadecimal identifiers; kept as strings. |
| `string` with `enum` | `classification`, `status`, `direction`, `account_type`, `entry_type`, `miter_type` | `STRING` | Stored as the raw enum value, for example `Asset`, `active`, `credit`. |
| `string` (datetime, ISO 8601) | `created_at`, `updated_at`, `posted_at` | `TIMESTAMP` | Parsed to UTC timestamps. |
| `string` (date, `YYYY-MM-DD`) | `payday`, `earning_date`, `accrual_date`, `reimbursement_date` | `DATE` | Date only, no time component. |
| `number` | `amount`, `hours` | `DOUBLE` | Miter does not distinguish integers from decimals, so `DOUBLE` is used for all numerics. |
| `boolean` | `void`, `recoded`, `manually_edited`, `is_company_default`, `is_selectable_by_team_members` | `BOOLEAN` | |
| `object` (fixed shape) | `ledger_entries.source_objects` | `STRUCT` | Nested structure is preserved, not flattened. Empty objects become `null`. |
| `object` (dynamic keys) | `ledger_mappings.defaults`, `earning_type_accounts`, `benefit_type_expense_accounts`, `benefit_type_liability_accounts` | `MAP<STRING, STRING>` | Key set is not fixed (includes customer-defined codes), so a map is used instead of a struct. |
| `array<string>` | `source_objects.bill_ids`, `source_objects.recoded_timesheet_ids` | `ARRAY<STRING>` | |
| `array<object>` | `ledger_line_items.custom_field_values` | `ARRAY<STRUCT<custom_field_id: STRING, value: STRING>>` | Polymorphic values are stringified; non-scalars are JSON-encoded. |
| Fields absent from the API's required set | most fields other than `id` | Same base type, nullable | Missing values are surfaced as `null`. |

## How to Run

### Step 1: Clone/Copy the Source Connector Code

Follow the Lakeflow Community Connector UI, which will guide you through setting up a pipeline using the Miter source connector code.

### Step 2: Configure Your Pipeline

1. Update the `pipeline_spec` in the main pipeline file (for example, `ingest.py`).
2. Reference the Unity Catalog connection you created and list the tables you want to ingest. Table-specific options go under `table_configuration`.

```json
{
  "pipeline_spec": {
    "connection_name": "miter_connection",
    "object": [
      {
        "table": {
          "source_table": "ledger_accounts",
          "table_configuration": {
            "start_timestamp": "2025-01-01T00:00:00Z"
          }
        }
      },
      {
        "table": {
          "source_table": "ledger_mappings"
        }
      },
      {
        "table": {
          "source_table": "ledger_entries",
          "table_configuration": {
            "start_timestamp": "2025-01-01T00:00:00Z",
            "page_size": "500",
            "window_seconds": "86400"
          }
        }
      },
      {
        "table": {
          "source_table": "ledger_line_items",
          "table_configuration": {
            "start_timestamp": "2025-01-01T00:00:00Z",
            "page_size": "500",
            "window_seconds": "604800",
            "parents_per_partition": "20"
          }
        }
      }
    ]
  }
}
```

3. (Optional) Customize the source connector code if needed for special use cases.

### Step 3: Run and Schedule the Pipeline

Run the pipeline with your standard Lakeflow / Databricks orchestration (for example, a scheduled job). On each run the connector resumes from the committed `updated_at` cursor per table, so schedules can be as frequent as your rate limits allow.

#### Best Practices

- **Start small**: Begin with `ledger_accounts` and `ledger_mappings` (small, fast tables) to validate the connection and data shape before adding `ledger_entries` and `ledger_line_items`.
- **Bound the initial backfill**: Set `start_timestamp` to the earliest accounting period you actually need. Without it, the first run reads the full history of the table.
- **Use incremental sync**: Leave the default `cdc` behavior in place — it reads only records changed since the last run, which minimizes API calls.
- **Budget for `ledger_line_items`**: This table requires one request series per ledger entry, plus a full enumeration of ledger-entry IDs on every run. For a company with many entries, expect its runtime and request count to dominate the pipeline. Consider running it on a less frequent schedule than the other tables, and use a larger `window_seconds` to reduce per-run overhead.
- **Respect Miter's rate limits**: Limits are **per token** and are reported by `GET /ping` under `rate_limits` (separate budgets for single-record and bulk/list endpoints — the API spec's illustrative values are 100/min and 60/min respectively). Exceeding them returns `429`. The connector retries `429`, `500`, `502`, `503`, and `504` responses with exponential backoff and honors `Retry-After`, but sustained throttling slows the pipeline. Stagger schedules, avoid running several Miter pipelines against the same token at once, and contact `support@miter.com` for a higher limit if needed.
- **Sync `ledger_entries` alongside `ledger_line_items`**: Line items reference `ledger_entry_id`; ingesting both keeps joins complete.
- **Plan for deletions**: Because Miter exposes no delete signal, schedule a periodic full reconciliation if deleted ledger records must disappear from your destination tables.
- **Keep `max_pages` and `max_parents` unset in production**: They are test-only guards. Non-zero values silently truncate results.

#### Troubleshooting

**Common Issues:**

- **`401` on every request** — The token is invalid, revoked, or was issued in the wrong environment. Most often this means a staging token is being used against production: set `base_url` to `https://api.staging.miter.com/api/v2`. Verify the token with `GET /ping`.
- **`403` on a specific table** — The token lacks the read scope for that object. Check the `scopes` reported by `GET /ping` and request a token with ledger read access.
- **`429 Too many requests`** — Miter's per-token rate limit was exceeded. The connector backs off and retries, but if the run still fails, reduce concurrency, increase `window_seconds` (fewer, larger requests), lower the schedule frequency, or request a higher limit from Miter.
- **`404` while reading `ledger_line_items`** — A parent ledger-entry ID no longer exists (it was deleted between enumeration and the child read), or a manually supplied `parent_ids` value is wrong. Remove stale IDs from `parent_ids`.
- **`ledger_line_items` is slow or times out** — This table fans out over every ledger entry. Increase `page_size` (up to 1000), increase `parents_per_partition` to reduce task overhead or decrease it to increase parallelism, raise `window_seconds`, and set `start_timestamp` to avoid re-reading old history.
- **Rows missing after an initial run with test options in place** — `max_pages` or `max_parents` was left at a non-zero value. Reset them to `0` and re-run a full backfill.
- **Deleted records still present in the destination** — Expected: Miter has no delete detection. Reconcile with a periodic full read as described above.
- **Recently updated rows appear one run late** — The cursor range of each run is capped at the moment the run started, so records changed mid-run are picked up on the next run. If you see updates consistently arriving behind the cursor, set `lookback_seconds` (for example `300`) to re-read a small trailing window.
- **`ledger_mappings` columns look empty** — `defaults` and the `*_accounts` fields are maps, not structs. Access them with a key, for example `defaults['employee_earnings']`, rather than dot notation.

## References

- Connector implementation: `src/databricks/labs/community_connector/sources/miter/miter.py`
- Table schemas and metadata: `src/databricks/labs/community_connector/sources/miter/miter_schemas.py`
- Connector specification (connection parameters and allowlist): `src/databricks/labs/community_connector/sources/miter/connector_spec.yaml`
- Source API research notes and full field reference: `src/databricks/labs/community_connector/sources/miter/miter_api_doc.md`
- Miter API (v2) endpoints used by this connector:
  - Production base URL: `https://api.miter.com/api/v2`
  - Staging base URL: `https://api.staging.miter.com/api/v2`
  - `GET /ping` — token name, scopes, and rate limits
  - `GET /ledger_accounts`, `GET /ledger_entries`, `GET /ledger_entries/{id}/line_items`, `GET /ledger_mappings`
- Miter API reference (OpenAPI spec and Postman collection) and higher rate limits: contact `support@miter.com`
