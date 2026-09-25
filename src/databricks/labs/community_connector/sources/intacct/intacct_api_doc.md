# **Sage Intacct API Documentation**

## **API Selection: XML Gateway vs REST**

Sage Intacct exposes two distinct APIs:

| | XML Gateway ("Intacct Web Services") | REST API (developer.sage.com) |
|---|---|---|
| Endpoint | `POST https://api.intacct.com/ia/xml/xmlgw.phtml` | `https://api.intacct.com/ia/api/v1/...` (OAuth2) |
| Status | Legacy, but fully supported and still receives bug fixes | Current/recommended for **new** integrations |
| Object coverage | Comprehensive — every standard/custom object, including reporting-only views | Narrower — growing, but does **not** cover every object |

**Decision: use the XML Gateway (xmlgw.phtml) for all 5 in-scope tables.**

Rationale:
- Sage Intacct's own XML API reference explicitly states new integrations should prefer REST ("We recommend using the REST API for your client applications" — see Research Log), so REST was evaluated first for parity across `customers`, `vendors`, `invoices`, `bills`, and `gl_entries`.
- REST has direct, well-documented equivalents for 4 of the 5 tables: `CUSTOMER` → Customers (`/objects/accounts-receivable/customer`), `VENDOR` → Vendors (`/objects/accounts-payable/vendor`), `ARINVOICE` → Invoices (`/objects/accounts-receivable/invoice`), `APBILL` → Bills (`/objects/accounts-payable/bill`).
- **`gl_entries` breaks parity.** The table scope is "general ledger detail/entries," which in Intacct maps to `GLDETAIL` — the reporting view that joins *every* subledger's posted transactions (AP, AR, CM, GL, Inventory, etc.) into a single GL fact table. This is the object used by every third-party connector we found (Fivetran's Sage Intacct connector ships `gl_detail`, `gl_entry`, `gl_batch`; Airbyte's tracked feature request lists "General Ledger details" as a distinct stream from "General Ledger journal entries"). The REST API only exposes `general-ledger/journal-entry` and `general-ledger/journal-entry-line`, which correspond to `GLBATCH`/`GLENTRY` — i.e., only *manually posted journal entries*, not the full cross-subledger GL detail. A user report on the Sage Developer Community forum ("Seems impossible to retrieve GLDETAIL as opposed to GLENTRY") confirms there is no REST equivalent for `GLDETAIL`.
- Because one of the five required tables has no REST equivalent, REST does not have full parity for this batch. Per the research methodology's guidance to prefer a single, homogeneous API pattern across a batch of related tables, and since the XML Gateway covers all 5 objects (including `GLDETAIL`) with the *same* auth, pagination, and filtering model, **the XML Gateway is used for all 5 tables** rather than splitting the connector across two auth/pagination schemes.
- Trade-off accepted: XML Gateway auth is heavier (sender credentials + company session) and payloads are XML rather than JSON, but this is a one-time integration cost, and it avoids maintaining two parallel read paths for a single connector.

If a future batch only needs `customers`/`vendors`/`invoices`/`bills` (no `gl_entries`), REST would be the better choice for that narrower scope — noted here for future reference, not acted on in this doc.

---

## **Authorization**

**Chosen method: XML Gateway two-layer authentication (Web Services credentials + company session).**

Every request is an HTTP `POST` of an XML document to:

```
https://api.intacct.com/ia/xml/xmlgw.phtml
Content-Type: application/xml
```

The XML body has two authentication layers:

1. **`<control>` block** — identifies the *client application* itself:
   - `senderid` — permanent Web Services Sender ID issued by Sage Intacct to the ISV/integration.
   - `password` — the Sender ID's password.
   - `controlid` — caller-chosen correlation ID for this request.
   - `uniqueid` — `false` to allow retries/repeated execution; `true` to reject duplicate submissions.
   - `dtdversion` — must be `3.0`.
   - `includewhitespace` — `false` (recommended).

2. **`<operation>/<authentication>` block** — identifies the *company/user*:
   - Either **login credentials**: `login/userid`, `login/companyid`, `login/password`, optional `login/locationid` (multi-entity), **or**
   - A **session ID** obtained via the `getAPISession` function — the documented preferred approach: "use `getAPISession` to request a session ID and unique endpoint, then make all subsequent requests with this context." Sessions avoid re-sending the company password on every call and are tied to a dedicated endpoint returned by `getAPISession`.

The connector should call `getAPISession` once (with login credentials) at connector startup, cache the returned `sessionid` + endpoint, and use `<authentication><sessionid>` for all subsequent `read`/`query`/`readByQuery` calls, refreshing on session expiry.

### Connection Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sender_id` | string | Yes | Web Services Sender ID (per integration, issued by Sage Intacct). |
| `sender_password` | string | Yes | Password for the Sender ID. |
| `company_id` | string | Yes | Target Intacct company ID. |
| `user_id` | string | Yes | Intacct user ID with API + module permissions. |
| `user_password` | string | Yes | Password for `user_id` (used once, to obtain a session, not stored/reused per call if session caching is implemented). |
| `location_id` | string | No | Entity/location ID for multi-entity companies. |
| `session_id` | string | No (derived) | Obtained at runtime from `getAPISession`; cached and reused. |

### Example: obtaining a session

```xml
<?xml version="1.0" encoding="UTF-8"?>
<request>
  <control>
    <senderid>MY_SENDER_ID</senderid>
    <password>MY_SENDER_PASSWORD</password>
    <controlid>get_session_1</controlid>
    <uniqueid>false</uniqueid>
    <dtdversion>3.0</dtdversion>
    <includewhitespace>false</includewhitespace>
  </control>
  <operation>
    <authentication>
      <login>
        <userid>MY_USER_ID</userid>
        <companyid>MY_COMPANY_ID</companyid>
        <password>MY_USER_PASSWORD</password>
      </login>
    </authentication>
    <content>
      <function controlid="get_session_1_fn">
        <getAPISession/>
      </function>
    </content>
  </operation>
</request>
```

### Example: reading with a cached session

```xml
<request>
  <control>
    <senderid>MY_SENDER_ID</senderid>
    <password>MY_SENDER_PASSWORD</password>
    <controlid>read_customers_1</controlid>
    <uniqueid>false</uniqueid>
    <dtdversion>3.0</dtdversion>
  </control>
  <operation>
    <authentication>
      <sessionid>CACHED_SESSION_ID</sessionid>
    </authentication>
    <content>
      <function controlid="read_customers_1_fn">
        <query>
          <object>CUSTOMER</object>
          <select><field>RECORDNO</field><field>CUSTOMERID</field><field>NAME</field></select>
          <pagesize>1000</pagesize>
        </query>
      </function>
    </content>
  </operation>
</request>
```

**Notes**:
- OAuth is **not** applicable to the XML Gateway (that is a REST-API-only concept); no OAuth flow needs to be run or stored for this connector.
- All read functions in this doc (`read`, `query`, `readByQuery`, `readMore`, `lookup`, `inspect`) are non-mutating and safe to call repeatedly.

---

## **Object List**

The object list is **not enumerable via a single "list all tables" call in the same sense as a REST catalog**, but it is retrievable via the `inspect` function with a wildcard, which lists every standard and custom object visible to the company, regardless of subscription/permissions:

```xml
<inspect>
  <object>*</object>
</inspect>
```

For this connector, the object list is scoped to the 5 objects below (static, chosen for this batch):

| Table (connector name) | Intacct XML object | Category |
|---|---|---|
| `customers` | `CUSTOMER` | Accounts Receivable |
| `vendors` | `VENDOR` | Accounts Payable |
| `invoices` | `ARINVOICE` (+ line item `ARINVOICEITEM`) | Accounts Receivable |
| `bills` | `APBILL` (+ line item `APBILLITEM`) | Accounts Payable |
| `gl_entries` | `GLDETAIL` | General Ledger (cross-subledger reporting view) |

Note the distinction inside General Ledger: `GLBATCH` (journal entry header) and `GLENTRY` (journal entry line) only cover manually-posted journal entries; `GLDETAIL` is the view Sage Intacct recommends for full GL activity across all subledgers and is what this connector's `gl_entries` table targets.

---

## **Object Schema**

Schema for a given object is retrievable via the `lookup` function, which returns every field (ID, label, data type, required/read-only flag, enum values) plus relationships to other objects:

```xml
<lookup>
  <object>CUSTOMER</object>
</lookup>
```

Response (abridged) contains a `Field` list (`ID`, `LABEL`, `DESCRIPTION`, `REQUIRED`, `READONLY`, `DATATYPE`, `VALIDVALUES` for enums) and a `Relationship` list (`OBJECTPATH`, `OBJECTNAME`, `RELATIONSHIPTYPE`, `RELATEDBY`) usable for dot-notation joins in `query` (e.g., `VENDOR.CREDITLIMIT`, one level of nesting).

Because `lookup` output for these specific objects was not fully retrievable field-by-field in this research pass (some fields below are cross-referenced from the object doc pages plus the Intacct "Object glossary for custom reports," not a single raw `lookup` dump), the field lists below should be treated as **the core, well-documented fields** — the connector implementation should still call `lookup` at runtime/connector-init time to get the complete, tenant-specific field list (custom fields vary per company) rather than hard-coding only what's listed here.

### `customers` → `CUSTOMER`

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | Internal record number. **Primary key.** |
| `CUSTOMERID` | string | Business-facing unique customer ID (alternate key, usable with `readByName`). |
| `NAME` | string | Customer name. |
| `STATUS` | enum(string) | `active` \| `inactive`. Used for soft-delete/deactivation instead of hard delete. |
| `ONETIME` | boolean | One-time customer flag. |
| `CREDITLIMIT` | decimal/currency | Credit limit. |
| `TAXID` | string | Tax ID. |
| `CUSTTYPE` | string | Customer type ID (FK to customer type). |
| `PARENTID` | string | Parent customer ID (hierarchy). |
| `TERMNAME` | string | Payment term. |
| `CURRENCY` | string | Default currency code. |
| `ONHOLD` | boolean | On-hold flag. |
| `TOTALDUE` | decimal/currency | Current amount due (aggregate, computed). |
| `WHENCREATED` | date | Record creation date. |
| `WHENMODIFIED` | timestamp | **Cursor field for incremental sync.** |
| `DISPLAYCONTACT` / `BILLTO` / `SHIPTO` | struct (contact ref) | Related contact objects, one-level nested via relationship dot-notation. |

### `vendors` → `VENDOR`

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | **Primary key.** |
| `VENDORID` | string | Business-facing unique vendor ID (alternate key). |
| `NAME` | string | Vendor name (required). |
| `STATUS` | enum(string) | `active` \| `inactive`. |
| `TOTALDUE` | decimal/currency | Amount currently owed to this vendor. |
| `CREDITLIMIT` | decimal/currency | Credit limit. |
| `VENDTYPE` | string | Vendor type ID. |
| `PARENTID` | string | Parent vendor ID. |
| `TAXID` | string | Tax ID. |
| `CURRENCY` | string | Default currency code. |
| `ONHOLD` | boolean | Hold status. |
| `ONETIME` | boolean | One-time-use vendor flag. |
| `WHENCREATED` | date | Record creation date. |
| `WHENMODIFIED` | timestamp | **Cursor field for incremental sync.** |
| `PAYTOCONTACT` / `DISPLAYCONTACT` | struct (contact ref) | Related contact objects. |

### `invoices` → `ARINVOICE` (header) + `ARINVOICEITEM` (lines)

**Header (`ARINVOICE`):**

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | **Primary key.** |
| `CUSTOMERID` / `CUSTOMERNAME` | string | FK to `CUSTOMER`. |
| `DOCNUMBER` | string | Invoice number (business document number; not guaranteed globally unique — `RECORDNO` is the true PK). **Not** `INVOICENO`: a live `lookup`/`query` against `ARINVOICE` confirmed `INVOICENO`/`DATECREATED`/`DATEPOSTED`/`DATEDUE` are documented but not queryable (`errorno XL03000006`, "The following fields cannot be queried"); `DOCNUMBER` is the real field, matching the naming already used on `APBILL` below. |
| `WHENPOSTED`, `WHENDUE` | date | Lifecycle dates (see `DOCNUMBER` note above). |
| `WHENCREATED` | date | Record creation date. |
| `WHENMODIFIED` | timestamp | **Cursor field for incremental sync.** |
| `TOTALENTERED` / `AMOUNT` | decimal/currency | Total invoice amount. |
| `TOTALPAID` | decimal/currency | Amount paid to date. |
| `TOTALDUE` | decimal/currency | Outstanding balance. |
| `TERMNAME` | string | Payment terms. |
| `STATE` | enum(string) | Draft / Posted / Void / Paid, etc. — mutations show up as `WHENMODIFIED` bumps rather than hard deletes. |
| `MODULEKEY` | string | `4.AR` (native AR invoice) vs `8.SO` (Order Entry-originated invoice) — both surface as `ARINVOICE`. |
| `CURRENCY` | string | Transaction currency. |

**Lines (`ARINVOICEITEM`):**

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | **Primary key** of the line. |
| Foreign key back to header | integer | `TBD:` exact field name (documentation excerpts retrieved did not show the header-link field explicitly; likely `PRRECORDKEY`/`INVOICEKEY`-style FK, consistent with other Intacct header/line pairs). Verify via `lookup` on `ARINVOICEITEM` before implementation. |
| `ACCOUNTNO` / `ACCOUNTLABEL` | string | GL account for the line. |
| `AMOUNT` / `TRX_AMOUNT` | decimal/currency | Line amount (base currency / transaction currency). |
| `ENTRYDESCRIPTION` | string | Line description. |
| `LOCATIONID`, `DEPARTMENTID`, `PROJECTID`, `TASKID` | string | Dimension FKs. |
| `TAXENTRIES` | struct/array | Present for AU/GB/ZA tax jurisdictions. |

### `bills` → `APBILL` (header) + `APBILLITEM` (lines)

**Header (`APBILL`):**

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | **Primary key.** |
| `VENDORID` | string | FK to `VENDOR`. |
| `RECORDID` / `DOCNUMBER` | string | Business document number/vendor invoice number. |
| `WHENCREATED`, `WHENPOSTED`, `WHENDUE` | date | Lifecycle dates. |
| `WHENMODIFIED` | timestamp | **Cursor field for incremental sync.** |
| `DESCRIPTION` | string | Bill description/memo. |
| `TERMNAME` | string | Payment terms. |
| `PAYMENTPRIORITY` | string | Priority for scheduled payments. |
| `ONHOLD` | boolean | Hold flag. |
| `STATE` | enum(string) | `D` Draft, `PA` Partially Approved, `S` Submitted, `U` Declined, `A` Posted. Mutations bump `WHENMODIFIED`. |
| `CURRENCY`, `BASECURR`, `EXCHANGE_RATE` | string/decimal | Currency handling. |
| `MODULEKEY` | string | `3.AP` (native AP bill) vs `9.PO` (Purchasing-originated bill). |
| Custom fields | varies | Company-specific; discover via `lookup`. |

**Lines (`APBILLITEM`):**

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | **Primary key** of the line. |
| `ACCOUNTNO` / `ACCOUNTLABEL` | string | GL account for the line. |
| `TRX_AMOUNT` | decimal/currency | Transaction-currency line amount. |
| `ENTRYDESCRIPTION` | string | Line description. |
| `LOCATIONID`, `DEPARTMENTID`, `PROJECTID`, `TASKID` | string | Dimension FKs. |
| `TAXENTRIES` | struct/array | Present for AU/GB/ZA tax jurisdictions. |

### `gl_entries` → `GLDETAIL`

`GLDETAIL` is documented as "an API query against a view, not a table" — it surfaces posted transaction-level GL detail sourced from every subledger (AP, AR, CM, GL, Inventory, Order Entry, Purchasing, Project Accounting, Contracts), not just manually-posted journal entries.

| Field | Type | Notes |
|---|---|---|
| `RECORDNO` | integer | **Primary key** of the GL detail line. |
| `GLENTRYKEY` | integer | FK to `GLENTRY.RECORDNO` — links the detail row back to its owning journal-entry line, when the source is a GL journal entry. |
| `ACCOUNTNO`, `ACCOUNTTITLE` | string | GL account. |
| `AMOUNT`, `DEBITAMOUNT`, `CREDITAMOUNT` | decimal/currency | Base-currency amounts. |
| `TRX_AMOUNT`, `TRX_DEBITAMOUNT`, `TRX_CREDITAMOUNT` | decimal/currency | Transaction-currency amounts. |
| `BATCH_DATE`, `BATCH_TITLE` | date/string | Parent batch date/title. |
| `ENTRY_DATE` | date | Line entry date. |
| `WHENCREATED` | date | **Not** the usual creation-timestamp semantic here — per Sage's own docs, on `GLDETAIL` this is "the transaction date as entered by the user." |
| `AUWHENCREATED` | timestamp | The *actual* record-creation audit timestamp (added specifically because `WHENCREATED` is overloaded on this object). |
| `WHENMODIFIED` | timestamp | **Cursor field for incremental sync.** |
| `BOOKID` | string | `ACCRUAL`, `CASH`, or a user-defined book. |
| `MODULEKEY` | enum(string) | Source subledger: `2.GL`, `3.AP`, `4.AR`, `6.EE`, `7.INV`, `8.SO`, `9.PO`, `11.CM`, `48.PROJACCT`, `55.CONTRACT`. |
| `CLASSID`/`CLASSNAME`, `DEPARTMENTID`/`DEPARTMENTTITLE`, `LOCATIONID`/`LOCATIONNAME`, `PROJECTID`/`PROJECTNAME` | string | Dimensions. |
| `SYMBOL` | string | Journal symbol (via `JOURNAL.SYMBOL` relationship). |
| `LINE_NO` | integer | Line number within the batch. |
| `DESCRIPTION` | string | Line memo. |

**Performance note (from official docs):** always filter `GLDETAIL` queries by date/state/`WHENMODIFIED` — because it is a view over the whole ledger, unfiltered or loosely filtered queries "impacts performance" and can time out.

---

## **Get Object Primary Keys**

Primary keys are not returned by a dedicated "get primary key" call; they are derived from the `lookup` function's field list (the field flagged as the object's unique record identifier) combined with Sage Intacct's documented convention that **every standard object's true primary key is `RECORDNO`** (an internal, immutable, auto-incrementing integer). Business-facing "ID" fields (`CUSTOMERID`, `VENDORID`, invoice/bill document numbers) are alternate/natural keys usable with `readByName`, but are not guaranteed to be immutable in the same way `RECORDNO` is, so the connector should use `RECORDNO` as the primary key for all 5 tables:

| Table | Primary Key | Alternate Key |
|---|---|---|
| `customers` | `CUSTOMER.RECORDNO` | `CUSTOMERID` |
| `vendors` | `VENDOR.RECORDNO` | `VENDORID` |
| `invoices` | `ARINVOICE.RECORDNO` (header) / `ARINVOICEITEM.RECORDNO` (line) | `DOCNUMBER` (not unique) |
| `bills` | `APBILL.RECORDNO` (header) / `APBILLITEM.RECORDNO` (line) | `RECORDID`/`DOCNUMBER` (not unique) |
| `gl_entries` | `GLDETAIL.RECORDNO` | `GLENTRYKEY` (FK, not unique per se) |

Example confirming a PK via `lookup`:

```xml
<lookup>
  <object>APBILL</object>
</lookup>
```

The `Field` entries in the response for `RECORDNO` show `DATATYPE=INTEGER`, `READONLY=true` — consistent with it being a system-assigned primary key.

---

## **Object's ingestion type**

All 5 tables support `WHENMODIFIED`-based incremental reads. None of the 5 has a documented, reliable hard-delete tombstone feed in the XML Gateway (Sage explicitly recommends *deactivation* over deletion for `CUSTOMER`/`VENDOR`, and deletion of a record "already used in a transaction" is disallowed; AR/AP documents are voided/reversed rather than deleted, which is captured as a `STATE` change + `WHENMODIFIED` bump; `GLDETAIL` is a posted-transaction view where hard deletes are rare/exceptional). Full delete detection would require polling `AUDITHISTORY`/`readByQuery` on `AUDITHISTORY`, which is out of scope for this doc — noted as a known gap, not implemented as `cdc_with_deletes`.

| Table | Ingestion Type | Cursor Field | Rationale |
|---|---|---|---|
| `customers` | `cdc` | `WHENMODIFIED` | Updates flow through `WHENMODIFIED`; deactivation (not deletion) is the delete-equivalent, surfaced as a `STATUS` field change, not a tombstone. |
| `vendors` | `cdc` | `WHENMODIFIED` | Same as `customers`. |
| `invoices` | `cdc` | `WHENMODIFIED` | Voids/reversals are updates (`STATE` change), not deletes. |
| `bills` | `cdc` | `WHENMODIFIED` | Same as `invoices`. |
| `gl_entries` | `cdc` | `WHENMODIFIED` | Posted GL detail is largely append-only in practice (corrections are new offsetting entries), but the object does expose `WHENMODIFIED`, so `cdc` is used rather than `append` to also catch the rare in-place correction. |

`TBD:` Whether `AUDITHISTORY` polling should later be added to promote any of these to `cdc_with_deletes` — deferred; would need its own research pass since `AUDITHISTORY` is a cross-object generic log, not a per-object delete feed.

---

## **Read API for Data Retrieval**

### Functions available

| Function | Use | Notes |
|---|---|---|
| `read` | Fetch specific records by `RECORDNO` (`<keys>`). | Best for point lookups, not bulk incremental reads. |
| `readByName` | Fetch specific records by alternate key (e.g., `CUSTOMERID`). | Point lookups. |
| `query` | **Modern, XML-structured filtering/select/sort.** | Preferred for this connector — structured filters, `orderby`, aggregate functions, dot-notation joins. |
| `readByQuery` | **Legacy, string-based WHERE-clause filtering**, paired with `readMore` for pagination via `resultId`. | Still fully supported; simpler for straightforward `WHENMODIFIED >= X` filters. |
| `readMore` | Continues a prior `readByQuery`/`query` result set via `resultId`, without re-running the filter. | Use for subsequent pages within one connector run. |
| `lookup` | Discover object schema (fields, types, enums, relationships). | Call once per object at connector init to get the tenant's actual field list. |
| `inspect` | Discover all objects available. | Not needed at read time for this fixed-scope connector. |

Either `query` or `readByQuery` works for this connector; `query` is used in the examples below for its structured filter syntax and native `orderby`/pagination fields.

### Pagination

- `pagesize`: results per page. Default `100`, **maximum `2000`**.
- `offset`: number of matching records to skip (works with `query`).
- `readMore` + `resultId`: alternative pagination path from `readByQuery`; response carries `numremaining` — `0` means the last page has been retrieved.
- Response also carries `totalcount` (total matching records) and `count` (records in this page).

### Incremental filtering (CDC)

Every object exposes `WHENMODIFIED`; filter with `greaterthanorequalto`/`greaterthan` against the connector's last-synced-through timestamp, ordered ascending by `WHENMODIFIED` so the highest value seen becomes the next checkpoint.

### Example: incremental `query` for `bills`

```xml
<function controlid="read_bills_1">
  <query>
    <object>APBILL</object>
    <select>
      <field>RECORDNO</field>
      <field>VENDORID</field>
      <field>RECORDID</field>
      <field>WHENCREATED</field>
      <field>WHENDUE</field>
      <field>STATE</field>
      <field>WHENMODIFIED</field>
    </select>
    <filter>
      <greaterthan>
        <field>WHENMODIFIED</field>
        <value>04/19/2017 12:00:00</value>
      </greaterthan>
    </filter>
    <orderby>
      <order>
        <field>WHENMODIFIED</field>
        <ascending/>
      </order>
    </orderby>
    <pagesize>2000</pagesize>
    <offset>0</offset>
  </query>
</function>
```

### Example: paging with `readByQuery` + `readMore`

```xml
<function controlid="read_customers_1">
  <readByQuery>
    <object>CUSTOMER</object>
    <fields>RECORDNO,CUSTOMERID,NAME,STATUS,WHENMODIFIED</fields>
    <query>WHENMODIFIED &gt;= '01/01/2024 00:00:00'</query>
    <pagesize>1000</pagesize>
  </readByQuery>
</function>
```

Response includes `resultId` and `numremaining`; while `numremaining > 0`:

```xml
<function controlid="read_customers_1_more">
  <readMore>
    <resultId>7765623332WU1hh8CoA4QAAHxI9i8AAAAA5</resultId>
  </readMore>
</function>
```

### Example: filtered, dimension-heavy read for `gl_entries`

```xml
<function controlid="read_gl_detail_1">
  <query>
    <object>GLDETAIL</object>
    <select>
      <field>RECORDNO</field>
      <field>ACCOUNTNO</field>
      <field>AMOUNT</field>
      <field>TRX_AMOUNT</field>
      <field>BATCH_DATE</field>
      <field>MODULEKEY</field>
      <field>WHENMODIFIED</field>
    </select>
    <filter>
      <and>
        <greaterthan>
          <field>WHENMODIFIED</field>
          <value>04/19/2017 12:00:00</value>
        </greaterthan>
        <greaterthanorequalto>
          <field>BATCH_DATE</field>
          <value>01/01/2024</value>
        </greaterthanorequalto>
      </and>
    </filter>
    <pagesize>2000</pagesize>
  </query>
</function>
```

`GLDETAIL` **must** always be filtered (date range and/or `WHENMODIFIED`) — Sage's own docs warn that unfiltered queries against this view cause timeouts.

### Deletes

No dedicated "deleted records" endpoint exists for these 5 objects in the XML Gateway (unlike some other Intacct objects, e.g. platform custom objects, that do expose delete feeds). Detecting hard deletes would require polling the generic `AUDITHISTORY`/`ADVAUDITHISTORY` objects via `readByQuery` and filtering by operation type — out of scope for this doc; see "Object's ingestion type" above.

### Rate limits

- **Per-company concurrency (standard service tier)**: 1 concurrent API/CSV-import/offline-report job. A 2nd request queues; a 3rd+ concurrent request is held up to 30 seconds, then errors if no slot frees up. Premium service tiers raise this.
- **Platform-level connection throttling**: Sage documents that the API infrastructure processes a limited number of simultaneous requests per tenant (roughly ~5 of every 100 concurrent submissions execute immediately, others wait ~5 seconds) — this is a coarser, infra-level note distinct from the per-company job-queue limit above; both should be respected (serialize/backoff on `429`-equivalent XML error responses).
- **Request timeout**: ~15 minutes per request.
- **Recommended query bounds**: keep result sets under ~1,000 records per query where possible (beyond the hard `pagesize` max of 2000), and keep any single create/update/delete call under ~100 affected records.
- No documented per-day request cap was found for the XML Gateway specifically (unlike REST, which Sage ties to a "Performance Tier" transaction-count model — not applicable here since XML is being used).

---

## **Field Type Mapping**

| Intacct `DATATYPE` (from `lookup`) | Spark Data Type | Notes |
|---|---|---|
| `TEXT` | `StringType` | Free text / IDs / names. |
| `ENUM` | `StringType` | Constrained value list (`VALIDVALUES` in `lookup` response); map as string, not a Spark enum. |
| `INTEGER` | `LongType` | `RECORDNO` and other internal IDs. |
| `DECIMAL` / currency fields (`AMOUNT`, `TRX_AMOUNT`, `CREDITLIMIT`, etc.) | `DecimalType` (or `DoubleType` if precision requirements are relaxed) | Currency amounts carry both base-currency (`AMOUNT`) and transaction-currency (`TRX_AMOUNT`) variants. |
| `BOOLEAN` | `BooleanType` | Represented in XML as `true`/`false`. |
| `DATE` | `DateType` | Format `mm/dd/yyyy` in requests/responses. |
| `TIMESTAMP` (e.g. `WHENMODIFIED`, `AUWHENCREATED`) | `TimestampType` | Format `mm/dd/yyyy hh:mm:ss`; used as the incremental cursor. |
| Relationship/struct fields (e.g. `BILLTO`, `SHIPTO`, `PAYTOCONTACT`) | `StructType` | Resolved via one level of relationship dot-notation (`lookup`'s `Relationship.OBJECTPATH`); Intacct limits traversal depth to one hop through `query`'s dot notation. |
| Line-item collections (`ARINVOICEITEMS`, `APBILLITEMS`, `TAXENTRIES`) | `ArrayType(StructType(...))` | Nested repeating groups under a header record; alternatively modeled as separate child tables (as this doc does for `ARINVOICEITEM`/`APBILLITEM`). |

Constraints/behaviors:
- `RECORDNO` fields are read-only, system-generated, auto-incrementing integers — never supplied on read paths, always present on responses.
- `WHENCREATED` has ordinary creation-date semantics on `CUSTOMER`/`VENDOR`/`ARINVOICE`/`APBILL`, but on `GLDETAIL` it means the **user-entered transaction date**, not a system timestamp — use `AUWHENCREATED` on `GLDETAIL` if a true creation-audit timestamp is needed.
- Enum fields' valid values are tenant-configurable in some cases (e.g., custom `STATE` values); always confirm via `lookup` rather than hard-coding the value list.

---

## **Sources and References**

| Source | URL | Confidence |
|---|---|---|
| Official docs — XML Web Services overview | https://developer.intacct.com/web-services/ | High |
| Official docs — XML request structure | https://developer.intacct.com/web-services/requests/ | High |
| Official docs — Queries (`query`/`readByQuery`/pagination/`lookup`) | https://developer.intacct.com/web-services/queries/ | High |
| Official docs — Code/usage examples | https://developer.intacct.com/web-services/code-examples/ | High |
| Official docs — XML API Reference index | https://developer.intacct.com/api/ | High |
| Official docs — Objects (list-all via `inspect`, `lookup`) | https://developer.intacct.com/api/platform-services/objects/ | High |
| Official docs — Customers | https://developer.intacct.com/api/accounts-receivable/customers/ | High |
| Official docs — Invoices (ARINVOICE) | https://developer.intacct.com/api/accounts-receivable/invoices/ | High |
| Official docs — Vendors | https://developer.intacct.com/api/accounts-payable/vendors/ | High |
| Official docs — Bills (APBILL) | https://developer.intacct.com/api/accounts-payable/bills/ | High |
| Official docs — General Ledger category index | https://developer.intacct.com/api/general-ledger/ | High |
| Official docs — General Ledger Details (GLDETAIL) | https://developer.intacct.com/api/general-ledger/general-ledger-detail/ | High |
| Official docs — Journal Entries (GLBATCH/GLENTRY) | https://developer.intacct.com/api/general-ledger/journal-entries/ | High |
| Official docs — FAQ (concurrency/throughput) | https://developer.intacct.com/support/faq/ | High |
| Official docs — Audit Trails | https://developer.intacct.com/api/company-console/audit-trails/ | Medium |
| Official Intacct help — General Ledger objects glossary | https://www.intacct.com/ia/docs/en_US/help_action/Reporting/Object_glossary_for_custom_reports/general_ledger_objects.htm | Medium (high-level only; field list cross-checked via search snippets, not a direct fetch) |
| Sage Developer Portal — REST API essentials (blocked from direct fetch; used for the "REST is recommended" framing only, corroborated by developer.intacct.com/api/) | https://developer.sage.com/intacct/docs/1/sage-intacct-rest-api/api-essentials | Low (403 on fetch; not independently verified, treated as directionally consistent with other sources) |
| Sage Developer Community forum — GLDETAIL not retrievable via REST | https://developer-community.sage.com/topic/1416-%F0%9F%90%9B-seems-impossible-to-retrieve-gldetail-as-opposed-to-glentry/ | Medium (title/snippet only, page blocked from direct fetch; decisive for the API-selection decision, so flagged clearly) |
| Fivetran — Sage Intacct connector docs (reference implementation) | https://fivetran.com/docs/connectors/applications/sage-intacct | Medium — confirms `gl_detail`/`gl_entry`/`gl_batch`/`ap_bill`/`ar_invoice` as the real-world table set. |
| Fivetran dbt package — general ledger model (reference implementation) | https://github.com/fivetran/dbt_sage_intacct | Medium |
| getknit.dev — Sage Intacct REST vs XML integration guide (third-party blog) | https://www.getknit.dev/blog/sage-intacct-api-integration-guide-in-depth | Low — used only for corroborating REST's OAuth2 model and the "REST-only new features" framing; not authoritative. |
| satvasolutions.com — Sage Intacct REST API guide (third-party blog) | https://satvasolutions.com/blog/sage-intacct-rest-api-integration-guide | Low — used only for REST OAuth2/`/query` filter-operator/pagination shape, to describe what was rejected. |
| Airbyte GitHub — "New Source: Sage Intacct" feature request (community/OSS signal, not a shipped connector) | https://github.com/airbytehq/airbyte/issues/2307 | Low — corroborates that "General Ledger details" (GLDETAIL) is treated as a separate stream from "General Ledger journal entries" (GLENTRY) by other integration builders. |

Where sources conflicted or a page could not be directly fetched (`developer.sage.com` returned HTTP 403 to both `WebFetch` and `curl` in this research session, apparently due to bot protection), the officially-fetchable `developer.intacct.com` XML documentation was treated as authoritative, and REST-API claims were cross-checked against at least one third-party blog plus WebSearch snippets before being used — consistent with this being enough to make (and document) the API-selection decision, without needing to fully document the REST API's request/response shapes in detail (since it was not the API chosen for implementation).

---

## Research Log

| Source Type | URL | Accessed (UTC) | Confidence | What it confirmed |
|---|---|---|---|---|
| Official Docs | https://developer.intacct.com/web-services/ | 2026-09-23 | High | XML Gateway endpoint, two-layer auth, `getAPISession`, concurrency/timeout notes. |
| Official Docs | https://developer.intacct.com/web-services/requests/ | 2026-09-23 | High | `<control>`/`<operation>`/`<content>` structure, `dtdversion`, `uniqueid`, `transaction`. |
| Official Docs | https://developer.intacct.com/web-services/queries/ | 2026-09-23 | High | `query` vs `readByQuery`, filter operators, `pagesize`/`offset`/`readMore`/`resultId`, `orderby`, `lookup`. |
| Official Docs | https://developer.intacct.com/web-services/code-examples/ | 2026-09-23 | High | Example `readByQuery` shape, `<control>`/`<authentication>` example payloads. |
| Official Docs | https://developer.intacct.com/api/ | 2026-09-23 | High | Confirms this section is the *legacy* XML reference; explicit "we recommend REST for client applications" statement; category list. |
| Official Docs | https://developer.intacct.com/api/platform-services/objects/ | 2026-09-23 | High | `inspect` (list all objects), `lookup` (schema + relationships) function shapes. |
| Official Docs | https://developer.intacct.com/api/accounts-receivable/customers/ | 2026-09-23 | High | `CUSTOMER` fields, PK (`RECORDNO`), relationships, example `read`/`query`. |
| Official Docs | https://developer.intacct.com/api/accounts-payable/vendors/ | 2026-09-23 | High | `VENDOR` fields, PK, relationships, example `read`/`query`. |
| Official Docs | https://developer.intacct.com/api/accounts-receivable/invoices/ | 2026-09-23 | High | `ARINVOICE` object, fields, `MODULEKEY` (4.AR vs 8.SO), pagination defaults/max. |
| Official Docs | https://developer.intacct.com/api/accounts-payable/bills/ | 2026-09-23 | High | `APBILL`/`APBILLITEM` objects, fields, `STATE` enum values, `MODULEKEY` (3.AP vs 9.PO). |
| Official Docs | https://developer.intacct.com/api/general-ledger/ | 2026-09-23 | High | Full list of General Ledger category objects (confirms `GLDETAIL`, `Journal Entries`, `Account Balances`, etc. are distinct docs). |
| Official Docs | https://developer.intacct.com/api/general-ledger/general-ledger-detail/ | 2026-09-23 | High | `GLDETAIL` is a view (not a table); `MODULEKEY` enum values; performance/filtering warning. |
| Official Docs | https://developer.intacct.com/api/general-ledger/journal-entries/ | 2026-09-23 | High | `GLBATCH`/`GLENTRY` objects, PK, `WHENMODIFIED`, example `create`. |
| Official Docs | https://developer.intacct.com/support/faq/ | 2026-09-23 | High | Standard-tier concurrency limit (1 concurrent job, 30s queue then error). |
| WebSearch snippets | (query: "developer.intacct.com whenmodified incremental changes query object") | 2026-09-23 | Medium | `WHENMODIFIED` is a generically-supported incremental filter across objects; example filter syntax. |
| WebSearch snippets | (query: "Sage Intacct GLDETAIL fields ENTRY_DATE WHENCREATED WHENMODIFIED RECORDNO TRX_AMOUNT DOCUMENT field list") | 2026-09-23 | Medium | Full `GLDETAIL` field list including `AUWHENCREATED`, `WHENMODIFIED`, `GLENTRYKEY`; the `WHENCREATED` semantic override on this object. |
| WebSearch snippets | (query re: XML-to-REST object map, GLDETAIL vs GLENTRY) | 2026-09-23 | Medium | Points to `https://developer.sage.com/intacct/docs/1/sage-intacct-rest-api/get-started/xml-rest-object-map` and a Sage Developer Community forum thread confirming `GLDETAIL` has no REST equivalent — decisive for the API-selection decision. |
| Official docs (fetch blocked, HTTP 403; via WebSearch summary) | https://developer.sage.com/intacct/docs/1/sage-intacct-rest-api/api-essentials | 2026-09-23 | Low | REST base URL pattern, OAuth2, general shape — used only to evaluate/reject REST, not to document it in depth. |
| Reference implementation (blog) | https://www.getknit.dev/blog/sage-intacct-api-integration-guide-in-depth | 2026-09-23 | Low | REST vs XML auth comparison, "REST gets all new features" framing, REST 2000-record query cap. |
| Reference implementation (blog) | https://satvasolutions.com/blog/sage-intacct-rest-api-integration-guide | 2026-09-23 | Low | REST OAuth2 token lifetime, `/query` endpoint filter operators (`$eq`/`$gt`/`$lt`/`$in`), `audit.modifiedDateTime` incremental filter, `start`/`pageSize` pagination. |
| Reference implementation (docs) | https://fivetran.com/docs/connectors/applications/sage-intacct | 2026-09-23 | Medium | Confirms real-world Sage Intacct connectors ship `gl_detail`, `gl_entry`, `gl_batch`, `ap_bill`/`ap_bill_item`, `ar_invoice`/`ar_invoice_item` as the practical table set — validates mapping `gl_entries` → `GLDETAIL`. |
| Reference implementation (GitHub) | https://github.com/fivetran/dbt_sage_intacct | 2026-09-23 | Medium | GL detail/entry/batch table relationships used downstream for financial statements. |
| Community signal (GitHub issue) | https://github.com/airbytehq/airbyte/issues/2307 | 2026-09-23 | Low | Independent confirmation that "GL details" and "GL journal entries" are treated as separate streams by another integration vendor. |

**Gaps / `TBD`s carried into the doc above:**
- Exact FK field name linking `ARINVOICEITEM` lines back to their `ARINVOICE` header was not confirmed from the fetched excerpts — flagged `TBD:` in the Object Schema section; verify via `lookup` on `ARINVOICEITEM` before implementation.
- Whether any delete-tombstone feed exists for these 5 objects beyond generic `AUDITHISTORY` polling was not found in the fetched docs — ingestion type left as `cdc`, not `cdc_with_deletes`, with the gap called out explicitly.
- `developer.sage.com` (the REST API's actual documentation host) returned HTTP 403 to every direct `WebFetch`/`curl` attempt in this session (Cloudflare-style bot protection); REST API details in this doc are therefore sourced from WebSearch result snippets and third-party blogs only, which is sufficient to support the API-selection decision (REST rejected due to missing `GLDETAIL` parity) but should not be treated as a complete REST API reference.
