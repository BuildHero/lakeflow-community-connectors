# **NetSuite API Documentation**

Scope for this pass: the **`vendorbill`** object only (per orchestrator
instruction — table scope was fixed to `vendorbill`, so no Airbyte/Fivetran
survey was needed to pick tables). Produced by internalizing the
`source-api-researcher` persona (`.claude/agents/source-api-researcher.md` +
the `research-source-api` skill) — this run had no live NetSuite account and
no user-provided documentation, so every claim below is web-research-derived
and cited in the Research Log. Gaps that could only be confirmed against a
live account are marked `TBD:`.

## **Authorization**

NetSuite's REST layer (SuiteTalk REST Web Services, which also serves the
SuiteQL query endpoint used below) supports two authentication methods.
**This connector uses Token-Based Authentication (TBA)** as its single
supported method for this phase; OAuth 2.0 is documented here for context
and flagged as the forward-looking migration path (see Known Quirks).

### Chosen method: Token-Based Authentication (TBA)

TBA is NetSuite's OAuth 1.0a-style scheme: every request carries an
`Authorization` header built from an HMAC-SHA256 signature over the request
method + URL + a fixed set of OAuth parameters, using four credentials:

| Credential | Where it comes from |
|---|---|
| `account_id` | NetSuite account ID (also the subdomain in the request URL) |
| `consumer_key` / `consumer_secret` | Created once per integration record: Setup > Integration > Manage Integrations > New, with **TBA** enabled |
| `token_id` / `token_secret` | Created per user/role: Setup > Users/Roles > Access Tokens > New, scoped to the integration record above |

Header shape (values illustrative):

```
Authorization: OAuth realm="1234567_SB1",
  oauth_consumer_key="<consumer_key>",
  oauth_token="<token_id>",
  oauth_signature_method="HMAC-SHA256",
  oauth_timestamp="1735000000",
  oauth_nonce="<random_string>",
  oauth_version="1.0",
  oauth_signature="<base64_hmac_sha256_signature>"
```

The signature base string is `METHOD&url_encode(base_url)&url_encode(sorted_oauth_params)`,
HMAC-SHA256-signed with key `url_encode(consumer_secret)&url_encode(token_secret)`.
TBA tokens do not expire on a fixed schedule — they remain valid until
revoked, or until the underlying user/role/integration record changes.

Example request (SuiteQL call, see below):

```
POST https://1234567.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql?limit=1000&offset=0
Authorization: OAuth realm="1234567", oauth_consumer_key="...", oauth_token="...",
  oauth_signature_method="HMAC-SHA256", oauth_timestamp="...", oauth_nonce="...",
  oauth_version="1.0", oauth_signature="..."
Content-Type: application/json
Prefer: transient

{"q": "SELECT id, tranid, entity, trandate, lastmodifieddate FROM transaction WHERE type = 'VendBill' ORDER BY lastmodifieddate ASC"}
```

### Alternative (not implemented): OAuth 2.0 Client Credentials (M2M)

NetSuite also supports OAuth 2.0. The **client-credentials-shaped** variant
NetSuite calls "OAuth 2.0 Client Credentials" is **not** a plain
`client_id` + `client_secret` POST to a token endpoint — it is a
**certificate-based JWT-bearer grant** (RFC 7523): the integration generates
an RSA key pair, uploads the public certificate to NetSuite under
*Setup > Integration > OAuth 2.0 Client Credentials Setup*, and the client
signs a JWT assertion with its private key on every token request instead of
presenting a static secret. This doesn't map cleanly onto this framework's
generic `connection.oauth: {flow: m2m, ...}` spec shape (which assumes a
plain client-credentials POST) without extending it to carry a private key /
JWT-signing step — out of scope for this phase. See Known Quirks for the
migration-timeline reason this matters.

## **Object List**

Static for this phase (single object in scope): **`vendorbill`**.

NetSuite itself exposes the full object list either via the REST record
catalog (`GET /services/rest/record/v1/metadata-catalog`) or, for SuiteQL
table names, via NetSuite's Records Catalog / SuiteAnalytics Connect schema
browser inside the account UI. Neither was queried for this pass since the
table scope was already fixed to `vendorbill`.

## **Object Schema**

`vendorbill` is modeled as **header-only** rows sourced from NetSuite's
built-in `transaction` SuiteQL table, filtered to `type = 'VendBill'`.

**Deferred: line-item detail.** A vendor bill's line items live in the
separate `transactionline` SuiteQL table (joined via
`transactionline.transaction = transaction.id`). Joining it in would fan out
one `transaction` row into N rows (one per line) — the connector would then
need to either (a) emit one row per line (changing the object's natural
grain and duplicating header fields, matching what Fivetran/Airbyte-style
tools call `transaction_line`), or (b) group lines into a nested array per
bill via two queries (list headers, then list lines `WHERE transaction IN
(...)`, per the "list parent, then list children" pattern in
`implement-connector`). Given the table scope for this phase is the single
name `vendorbill` (not `vendorbill` + `vendorbilllines`), this doc documents
**option (b) as deferred, not implemented** — the header-only object below
ships now; a follow-up batch would add a `lines` field or a sibling table.
**This is the "transaction/transactionline table shape" tradeoff flagged in
the connector's task brief — flagging it here for review, not resolving it
silently.**

Header fields (from `transaction`, `TBD:` where the exact column needs
live-account confirmation — SuiteQL's dialect matches Oracle SQL, and column
names below are corroborated by multiple community sources but not verified
against a live schema browse, since none was available):

| Field | SuiteQL column | Type (SuiteQL wire type) | Notes |
|---|---|---|---|
| `id` | `id` | string (numeric string) | Transaction internal ID |
| `tranid` | `tranid` | string | Human-readable bill number |
| `entity` | `entity` | string (numeric string) | Vendor internal ID (FK to `entity`/vendor table) |
| `trandate` | `trandate` | string | Bill (transaction) date. Emit via `TO_CHAR(trandate, 'YYYY-MM-DD')` — see Known Quirks on date-format ambiguity |
| `duedate` | `duedate` | string | Due date, same date-format caveat. `TBD:` confirm column is populated for `VendBill` (vs. derived from terms) |
| `status` | `status` | string | Raw status code (e.g. `VendBill:A` style internal value). Human-readable label requires `BUILTIN.DF(status)` — not applied here; deferred |
| `currency` | `currency` | string (numeric string) | Currency internal ID |
| `exchangerate` | `exchangerate` | string (numeric string) | Exchange rate to base currency |
| `foreigntotal` | `foreigntotal` | string (numeric string) | Bill total in transaction currency. `TBD:` confirm this is the correct total column for `VendBill` vs. `total`/computed-from-lines — could not verify against a live account |
| `memo` | `memo` | string | Free-text memo |
| `subsidiary` | `subsidiary` | string (numeric string) | Subsidiary internal ID (OneWorld accounts) |
| `terms` | `terms` | string (numeric string) | Payment terms internal ID |
| `postingperiod` | `postingperiod` | string (numeric string) | Accounting period internal ID |
| `approvalstatus` | `approvalstatus` | string (numeric string) | Approval workflow status, if enabled on the account. `TBD:` null on accounts without bill approvals enabled |
| `externalid` | `externalid` | string | Optional external ID set by integrations |
| `createddate` | `createddate` | string | Record creation timestamp |
| `lastmodifieddate` | `lastmodifieddate` | string | Last-modified timestamp — **cursor field** |

All values come back from SuiteQL as **JSON strings**, including numeric and
date/timestamp columns (confirmed by multiple example responses in
research — see Research Log). The connector returns raw parsed JSON (per
`implement-connector` rules) and declares proper Spark types in
`get_table_schema`; the framework's `parse_value` coercion (str → Long /
Double / Timestamp) handles the conversion.

## **Get Object Primary Keys**

Primary key: **`id`** (the `transaction` table's internal ID). Unique per
transaction, stable across edits, never reused.

## **Object's ingestion type**

`vendorbill` → **`cdc`** (incremental upsert via `lastmodifieddate`, no
delete feed).

**Deletes not implemented.** NetSuite vendor bills can be deleted or voided.
Detecting deletions via SuiteQL requires querying system audit tables
(`systemnote` / the `deletedrecord` XML-only endpoint) which are a
materially different API shape (XML SOAP-only for `deletedrecord`, or a
noisy generic audit log for `systemnote`). `TBD:` a future batch should
research one of these paths before promising `cdc_with_deletes`. For this
phase, `read_table_deletes` is not implemented and ingestion type is `cdc`
only — matches the "Read operations only" / no-invention scope of this
research pass.

## **Read API for Data Retrieval**

**Endpoint:** `POST https://{account_id}.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql`

**Required headers:** `Content-Type: application/json`, `Prefer: transient`
(the latter tells NetSuite not to persist the query as a saved search),
plus the TBA `Authorization` header above.

**Request body:** `{"q": "<SuiteQL SELECT statement>"}` — optionally
`"params": [...]` for bound `?` placeholders (not used here; the connector
inlines a normalized ISO date-range filter directly, see Known Quirks on why
bound params were skipped for the date filter).

**Pagination:** `limit` and `offset` **query-string parameters on the URL**
(not in the body), e.g. `?limit=1000&offset=0`. Default page size 1000
if omitted. Hard cap: **100,000 total rows per query** — `offset` cannot
exceed 100,000. This is why the connector must scope each query with a
bounded time window (Strategy A / sliding window) rather than only
`ORDER BY lastmodifieddate ASC` with no upper bound: a NetSuite account with
more than 100k vendor bills modified since a fixed cursor would hit the
100k-row ceiling before the connector's own `max_records_per_batch` admission
control ever kicks in.

**Response shape:**

```json
{
  "links": [
    {"rel": "next", "href": ".../suiteql?limit=1000&offset=1000"},
    {"rel": "self", "href": ".../suiteql?limit=1000&offset=0"}
  ],
  "count": 1000,
  "hasMore": true,
  "items": [
    {"links": [], "id": "48213", "tranid": "VB-1042", "entity": "301",
     "trandate": "2026-06-01", "lastmodifieddate": "2026-06-02T14:03:00Z", "...": "..."}
  ],
  "offset": 0,
  "totalResults": 15000
}
```

**Example query used by the connector** (one call per `read_table`
pagination page, within a bounded `[since, until)` window):

```sql
SELECT id, tranid, entity, TO_CHAR(trandate, 'YYYY-MM-DD') AS trandate,
       TO_CHAR(duedate, 'YYYY-MM-DD') AS duedate, status, currency,
       exchangerate, foreigntotal, memo, subsidiary, terms, postingperiod,
       approvalstatus, externalid, createddate, lastmodifieddate
FROM transaction
WHERE type = 'VendBill'
  AND lastmodifieddate >= '2026-06-01T00:00:00Z'
  AND lastmodifieddate <  '2026-06-02T00:00:00Z'
ORDER BY lastmodifieddate ASC
```

with `?limit=<page size>&offset=<page offset>` on the URL for pagination
within that window.

**Incremental strategy:** Sliding time-window (Strategy A from
`implement-connector`), keyed on `lastmodifieddate`, ascending sort. A
`window_seconds` table option controls the window bound (default proposed:
86400 = 1 day) to keep each query's row count comfortably under the
100k-row/offset ceiling on large accounts. `max_records_per_batch` caps the
number of records returned per `read_table` call within the window (safe to
truncate client-side since `id` is a primary key and ingestion is `cdc` →
upsert). No documented ascending-sort limitation was found for SuiteQL
`ORDER BY` (standard SQL), so ascending sort by `lastmodifieddate` is used
directly — the fallback "full read + now() as next since" strategy is not
needed.

**Rate limits:** NetSuite enforces **concurrency** limits (default 15
simultaneous SOAP+REST+RESTlet requests per account, more with SuiteCloud
Plus licensing/higher tiers) and separate **frequency** limits (calls per
60-second and 24-hour windows — exact numbers are account/tier-dependent and
not published as a fixed constant; `TBD:` confirm against the target
account's tier). SuiteQL additionally caps any single query's total result
set at 100,000 rows. The connector should retry with backoff on HTTP 429
(and 500/503) — see `Field Type Mapping` for the retry table used.

## **Field Type Mapping**

| SuiteQL wire type | Spark type used | Notes |
|---|---|---|
| numeric string (e.g. `"48213"`) | `LongType` for IDs, `DoubleType` for rates/amounts | Framework's `parse_value` coerces the JSON string |
| date/timestamp string | `StringType` (ISO 8601 text, normalized via `TO_CHAR` in the query) | Kept as `StringType` rather than `TimestampType`/`DateType` because NetSuite's *native* `trandate`/`lastmodifieddate` wire format is governed by the account's date-format preference (`M/D/YYYY`, `D/M/YYYY`, locale-dependent) unless explicitly normalized — see Known Quirks. The connector always requests `TO_CHAR(..., 'YYYY-MM-DD'...)` so the value is a stable ISO string regardless of account locale; declaring `StringType` avoids relying on Spark's date parser handling every possible locale format for values that *aren't* normalized (e.g. if a future column is added without a `TO_CHAR` wrapper) |
| plain string | `StringType` | — |

Retry policy (`RETRIABLE_STATUS_CODES`, mirroring the `example` connector's
pattern): retry `429`, `500`, `503` with exponential backoff
(`INITIAL_BACKOFF=1s`, doubling, `MAX_RETRIES=5`); every request sets an
explicit `timeout` (20s) per `implement-connector`'s API-call best practices.

## Known Quirks

1. **TBA sunset timeline.** As of NetSuite's 2027.1 release, **new**
   TBA-based integrations can no longer be created (existing ones keep
   working). Today (2026-08-25) is before that cutoff, so TBA is fully
   supported for a new integration, but this is a real forward-looking risk:
   whoever operationalizes this connector past early 2027 should plan a
   migration to OAuth 2.0's certificate-based JWT-bearer M2M flow, which is
   architecturally different (private key + signed JWT assertion, not a
   static secret) from what this framework's generic `connection.oauth`
   spec block currently models. **Flagging this explicitly for Task 3/4
   review — this phase does not attempt the OAuth 2.0 path.**
2. **Account-locale date formats.** NetSuite's native date/datetime wire
   format for fields like `trandate` and `lastmodifieddate`, when *not*
   wrapped in `TO_CHAR(...)`, follows the account's configured date format
   (`M/D/YYYY h:mm am/pm` is a common default), not ISO 8601. The connector
   always wraps date/timestamp columns in `TO_CHAR(col, 'YYYY-MM-DD...')` in
   its SuiteQL query text specifically to avoid depending on account locale.
3. **All values are strings on the wire**, including numeric IDs and
   amounts — confirmed by multiple example SuiteQL REST responses in the
   research below. The connector relies on the framework's `parse_value`
   type coercion rather than casting client-side.
4. **100,000-row per-query ceiling** (`offset` cannot exceed 100,000) means
   any connector relying only on `ORDER BY lastmodifieddate ASC` with an
   unbounded `WHERE lastmodifieddate >= :since` will eventually break on a
   high-volume account. The sliding-window strategy documented above exists
   specifically to keep each query's total matching row count well under
   that ceiling.
5. **Transaction/transactionline shape decision** — see Object Schema above.
   Header-only for this phase; line-item join deferred and explicitly
   flagged rather than silently omitted.
6. **`foreigntotal` column confidence** — medium. Multiple integration blog
   posts reference totals being computed from `transactionline.amount`
   sums rather than a single reliable header total column across all
   transaction types; `foreigntotal` is the best single-column candidate
   found but is marked `TBD:` for live confirmation.

## Sources and References

| Source Type | URL | Accessed (UTC) | Confidence | What it confirmed |
|---|---|---|---|---|
| Official Docs | https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157909186990.html | 2026-08-25 | High | SuiteQL REST endpoint, method, headers (`Prefer: transient`), request/response body shape, `limit`/`offset` pagination, 100,000-row cap |
| Official Docs | https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_1540391670.html | 2026-08-25 | High | SuiteTalk REST Web Services overview |
| Official Docs | https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_164484956387.html | 2026-08-25 | High | Vendor Bill record concept (business object) |
| Official Docs | https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html | 2026-08-25 | High | OAuth 2.0 Client Credentials setup is certificate/JWT-based, not plain client-secret |
| Community (NetSuite Community) | https://community.oracle.com/netsuite/english/discussion/4510165/what-is-the-proper-payload-for-creating-a-vendor-bill-via-rest-api | 2026-08-25 | Medium | REST record endpoint `/record/v1/vendorBill` shape (write path, not used by this read-only connector) |
| Blog (Tim Dietrich) | https://timdietrich.me/blog/netsuite-suiteql-querying-transactions/ | 2026-08-25 | Medium | `transaction`/`transactionline` join pattern, `type` filter value `VendBill`, `BUILTIN.DF` for decoding coded fields |
| Blog (Houseblend) | https://www.houseblend.io/articles/netsuite-tba-oauth2-migration-2027 | 2026-08-25 | Medium | TBA-vs-OAuth2 comparison and 2027.1 new-integration cutoff |
| Blog (Houseblend) | https://www.houseblend.io/articles/netsuite-api-governance-guide | 2026-08-25 | Medium | Concurrency (default 15) and frequency governance model |
| Blog (Modern Treasury) | https://www.moderntreasury.com/journal/how-to-authenticate-to-netsuites-suitetalk-rest-web-services-api | 2026-08-25 | Medium | TBA request-signing mechanics |
| Blog (Satva Solutions) | https://satvasolutions.com/blog/netsuite-m2m-authentication-guide | 2026-08-25 | Medium | OAuth2 M2M certificate/JWT flow details |
| Blog / forum aggregation | search results for `"suiteql" REST API response "hasMore" "totalResults" "links"` | 2026-08-25 | Medium | Full example response envelope including `hasMore` and `links` array with `next`/`last`/`self` |
| Blog aggregation | search results for SuiteQL numeric-field-as-string behavior | 2026-08-25 | Medium | Confirms numeric fields (e.g. `id`) serialize as JSON strings |
| NetSuite Diagnostics blog | https://www.netsuitediagnostics.com/posts/suiteql-transactionline-mainline/ | 2026-08-25 | Medium | `transactionline.mainline` semantics, informs the deferred-lines decision |

No user-provided documentation was available. No official NetSuite Records
Catalog / schema browser was queried (requires a live account). All findings
above are secondary-source; live-account validation (Phase 2,
`/validate-connector`) should specifically re-verify the `foreigntotal`
column and the exact `duedate`/`approvalstatus` population behavior called
out as `TBD:` above.
