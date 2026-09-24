# **buildops API Documentation**

BuildOps is a cloud-based field-service / job-costing platform for MEP
(mechanical, electrical, plumbing), FLS, and refrigeration contractors. It
exposes a public REST API (OpenAPI 3.0) covering CRM, inventory/procurement,
labor, and other domains. This documentation covers only the **`bills`**
object (Accounts Payable bill records from the Inventory/Procurement domain),
per the requested research scope.

Source of truth for this document is the local, read-only OpenAPI spec
checkout at `/home/alvin/_git/buildops/open-api-spec` (a private/internal
repo, not the public Stoplight docs site). All line-number citations below
refer to that checkout.

## **Authorization**

- **Single supported method: OAuth-style client-credentials → short-lived
  Bearer JWT.** This is the only auth method documented; there is no API-key
  or user-facing OAuth flow.
- **Token endpoint**: `POST /v1/auth/token` (no auth required on this call
  itself — `security: []`).
  - Request body (JSON): `{"clientId": "<client-id>", "clientSecret": "<client-secret>"}`
    (both required). An optional `tenantId` may be included to request a
    token scoped to a single tenant (see "Multi-tenant" note below).
  - Response body (JSON): `{"access_token": "<jwt>", "expires_in": 86400, "token_type": "Bearer"}`
    (all three fields required per schema).
  - Source: `reference/domains/general/api.yaml` lines 128–184;
    `docs/getting started/Authentication-Authorization-and-Scope.md` lines 28–54.
- **Every subsequent (non-auth) call** must include two headers:
  - `Authorization: Bearer <access_token>` — component parameter
    `Authorization`, required, `reference/domains/general/api.yaml` lines 27–34.
  - `tenantId: <tenant-uuid>` — component parameter `tenantId`, required,
    format `uuid`, `reference/domains/general/api.yaml` lines 35–43.
  - The security scheme applied to individual Bills operations is a bearer
    JWT scheme named `bearer` (see `security: [{"bearer": []}]` on each
    `/v2/bills*` operation, e.g. `reference/domains/inventory/inventory.json`
    lines 2129–2133).
- **Token lifetime**: `expires_in` is documented as `86400` seconds (24h) in
  the example response
  (`docs/getting started/Authentication-Authorization-and-Scope.md` line 51).
  The connector must re-authenticate (or refresh) before expiry; there is no
  documented refresh-token grant — re-run the client-credentials exchange.
- **Scope check (optional)**: `GET /v1/auth/scope` returns the tenant IDs the
  token is authorized for (`reference/domains/general/api.yaml` lines
  185–222). Not required for reading `bills`, but useful to validate a
  multi-tenant credential pair during connector setup.
- **OAuth note (per template convention)**: the connector stores `client_id`
  and `client_secret` as connection options and exchanges them for an access
  token at runtime on each run (or refresh-on-expiry); it does **not** run a
  user-facing OAuth authorization-code flow. There is no `refresh_token` in
  this API — the client-credentials exchange is repeated instead.
- **Servers** (`reference/domains/general/api.yaml` lines 13–17):
  - Production: `https://public-api.live.buildops.com`
  - Development: `https://public-api.dev.buildops.com`
  - The connector exposes a `base_url` connection option, **defaulting to the
    DEV server** (`https://public-api.dev.buildops.com`).

Example authentication request:

```shell
curl --request POST \
  --url '<base_url>/v1/auth/token' \
  --header 'Content-Type: application/json' \
  --data '{
        "clientId": "<client-id>",
        "clientSecret": "<client-secret>"
  }'
```

Example response:

```json
{
  "access_token": "<jwt>",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

Example authenticated call to read a bill:

```shell
curl --request GET \
  --url '<base_url>/v2/bills/<billId>?include=vendor&include=department' \
  --header 'Accept: application/json' \
  --header 'Authorization: Bearer <access_token>' \
  --header 'tenantId: <tenant-uuid>'
```

## **Object List**

The object list for this connector is **static and scoped to a single
object for this research pass: `bills`** (the "Bills" tag in the Inventory
domain spec, `reference/domains/inventory/inventory.json`). The full
Inventory domain spec also documents Purchase Orders, Purchase Order
Receipts, Vendors, Products, etc., but per the requested scope, **only
`bills` is documented and implemented here** — see "Deferred Tables" at the
end of this document.

`bills` is a **top-level object**, not nested under another object in the
URL path (`/v2/bills`, `/v2/bills/{billId}`), although its response payload
can optionally embed related parent/child objects (purchase order, vendor,
job, project, department, employees, payment term, tax rate) via the
`include` query parameter — see "Read API for Data Retrieval" below. There
is no dynamic/discovery endpoint that enumerates available objects; the
object list is fixed by the OpenAPI spec's set of tagged paths.

Verified endpoints tagged `Bills` in `reference/domains/inventory/inventory.json`:

| Method | Path | Purpose | Lines |
|---|---|---|---|
| GET | `/v2/bills/{billId}` | Read a single bill by id | 2052–2138 |
| PATCH | `/v2/bills/{billId}` | Update a bill by id | 2139–2234 |
| DELETE | `/v2/bills/{billId}` | Delete a bill by id | 2235–2288 |
| POST | `/v2/bills` | Create a bill (+ lines) | 2290–2352 |
| POST | `/v2/bills/{billId}/void` | Void a bill | 2354–2416 |
| PUT | `/v2/bills/{billId}/export` | Mark bill for export | 2417–2479 |
| PUT | `/v2/bills/{billId}/post` | Mark bill posted | 2480–2542 |
| POST | `/v2/bills/{billId}/bypass` | Bypass a bill | 2543–2605 |
| POST | `/v1/bill-lines/bill/{billId}` | Create a bill line under a bill | 2606–2668+ |

**Confirmed: there is no supported list-bills endpoint.** The public
`buildhero-public-api` gateway routes `GET /v2/bills` to the inventory
service, but the backing controller
(`backend-services-ts/packages/procurement/src/adapters/controllers/bill/bill.controller.ts`)
has no `GET` list handler — listing exists internally only as
`POST bills/search`, which is **not** exposed by the public API, and the
published OpenAPI spec correspondingly has no `GET /v2/bills` (list)
operation (only `POST /v2/bills` for create — see table above and lines
2290–2353). This was confirmed by direct inspection of the backend routing
and controller source (internal repo, not the OpenAPI spec) in addition to
the absence of the operation in the spec.

**Implication for this connector**: the `bills` table is a **by-id read**
object, not a paginated list. It requires a caller-supplied set of bill IDs.

## **Object Schema**

Schema is **static**, defined by the `PublicBillResponseDto` component
schema (`reference/domains/inventory/inventory.json` lines 9834–10256),
returned by both `GET /v2/bills/{billId}` and `POST /v2/bills` (create).
There is no schema-discovery endpoint; the fields below are the complete,
enumerated set from the OpenAPI spec.

### `PublicBillResponseDto` (top-level fields)

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `id` | string (uuid) | required | Bill primary key |
| `tenantId` | string (uuid) | nullable | |
| `audit` | object → `AuditInfo` | required | See below |
| `billLines` | array of `PublicBillLineDto` | required, nullable | Line items; see below |
| `transactionDate` | integer (unix timestamp) | nullable | required key in schema but nullable |
| `billNumber` | string | required | e.g. `BILL-123` |
| `customIdentifier` | string | nullable | Alternate to `billNumber` |
| `description` | string | required | |
| `freight` | number | nullable | Freight cost |
| `tax` | number | nullable | Tax amount |
| `addedBy` | string | required | Free-text name of person who added the bill |
| `invoicedStatus` | string enum: `DoNotInvoice`, `Invoiced`, `NotInvoiced`, `PartiallyInvoiced` | nullable | |
| `accountingRefIdOfClass` | string | nullable | |
| `purchaseOrderReceiptId` | string (uuid) | nullable | FK to Purchase Order Receipt |
| `departmentId` | string (uuid) | nullable | FK to Department |
| `taxRateId` | string (uuid) | nullable | FK to Tax Rate |
| `vendorId` | string (uuid) | nullable | FK to Vendor |
| `jobId` | string (uuid) | nullable | FK to Job |
| `projectId` | string (uuid) | nullable | FK to Project |
| `vendorDocumentNumber` | string | required | External vendor doc/invoice number |
| `vendorDocumentAttachment` | object → `AttachmentDto` | nullable | See below |
| `orderedById` | string (uuid) | required | FK to Employee |
| `issuedBy` | integer (unix timestamp) | nullable | Despite the name, this is a **date**, not a person (see Known Quirks) |
| `postingDate` | integer (unix timestamp) | nullable | |
| `dueDate` | integer (unix timestamp) | nullable | |
| `version` | integer | nullable | Optimistic-concurrency version |
| `totalCost` | number | nullable | |
| `syncLog` | string | nullable | Accounting-integration sync log/error text |
| `syncStatus` | string enum → `SyncStatus`: `Syncing`, `InSync`, `SyncFailed`, `Bypassed` | nullable | |
| `accountingVersion` | string | nullable | |
| `isImported` | boolean | required | |
| `tenantCompanyId` | string (uuid) | nullable | |
| `purchaseOrderId` | string (uuid) | nullable | FK to Purchase Order |
| `approvalStatus` | string enum → `ApprovalStatus`: `Unreviewed`, `Approved`, `Review Needed`, `Rejected` | nullable | |
| `approvalNote` | string | nullable | |
| `approvalNoteById` | string (uuid) | nullable | FK to Employee |
| `approvalNoteDateTime` | integer (unix timestamp) | nullable | |
| `projectManagerId` | string (uuid) | nullable | FK to Employee |
| `paymentTermId` | string (uuid) | nullable | FK to Payment Term |
| `assignedToId` | string (uuid) | nullable | FK to Employee |
| `status` | string enum: `Exported`, `Pending`, `Posted`, `Void`, `Closed`, `Draft`, `Bypassed` | nullable | Bill workflow status |
| `createdByEmployeeId` | string (uuid) | nullable | FK to Employee |
| `isCreatedFromMobile` | boolean | nullable | |
| `addresses` | array of `AddressDto` | nullable | Billing/shipping addresses; see below |
| `purchaseOrder` | object → `PublicPurchaseOrderDto` | nullable | Only populated if `include=purchaseOrder` |
| `purchaseOrderReceipt` | object → `PublicPurchaseOrderReceiptDto` | nullable | Only populated if `include=purchaseOrderReceipt` |
| `vendor` | object → `PublicVendorDto` | nullable | Only populated if `include=vendor` |
| `job` | object → `PublicJobDto` | nullable | Only populated if `include=job` |
| `project` | object → `PublicProjectDto` | nullable | Only populated if `include=project` |
| `department` | object → `DepartmentDto` | nullable | Only populated if `include=department` |
| `orderedBy` | object → `EmployeeDto` | nullable | Only populated if `include=orderedBy` |
| `projectManager` | object → `EmployeeDto` | nullable | Only populated if `include=projectManager` |
| `assignedTo` | object → `EmployeeDto` | nullable | Only populated if `include=assignedTo` |
| `approvalNoteBy` | object → `EmployeeDto` | nullable | Only populated if `include=approvalNoteBy` |
| `paymentTerm` | object → `PaymentTermDto` | nullable | Only populated if `include=paymentTerm` |
| `taxRate` | object → `TaxRateDto` | nullable | Only populated if `include=taxRate` |

`required` array on `PublicBillResponseDto` (lines 10244–10255): `id`,
`audit`, `billLines`, `transactionDate`, `billNumber`, `description`,
`addedBy`, `vendorDocumentNumber`, `orderedById`, `isImported`. Note several
of these "required" fields are still individually marked `nullable: true`
in the spec (e.g. `transactionDate`) — required means "the key is always
present in the payload," not "never null."

**Note on nested relation objects**: `purchaseOrder`, `purchaseOrderReceipt`,
`vendor`, `job`, `project`, `department`, `orderedBy`, `projectManager`,
`assignedTo`, `approvalNoteBy`, `paymentTerm`, `taxRate` are large,
independently-modeled entities belonging to other tables/domains (Vendors,
Jobs, Projects, Departments, Employees, Payment Terms, Tax Rates, Purchase
Orders/Receipts). Their full field lists are **out of scope** for this
single-table (`bills`) research pass; they are referenced here only to
document that the `bills` schema can embed them via `include`. If a future
research pass adds those tables, their schemas should be documented in
those tables' own sections.

### `AuditInfo` (nested in `audit`, lines 6442–6485)

| Field | Type | Notes |
|---|---|---|
| `createdBy` | object → `UserAuditInfo` | |
| `createdDate` | string (nullable) | ISO-8601, e.g. `2023-05-30T13:16:46Z` |
| `createdDateTime` | number (nullable) | Unix millis, e.g. `1626240000000` |
| `lastUpdatedBy` | object → `UserAuditInfo` | |
| `lastUpdatedDate` | string (nullable) | ISO-8601 |
| `lastUpdatedDateTime` | string (nullable) | **Typed as `string` in the spec** despite holding a millis timestamp example (`1626240000000`) — likely a spec typo; treat as numeric-string / verify live |
| `deletedBy` | object → `UserAuditInfo` | |
| `deletedDate` | string (nullable) | ISO-8601; presence implies soft-delete tracking |
| `deletedDateTime` | number (nullable) | Unix millis |

`UserAuditInfo` schema itself was not expanded in this pass (referenced but
not read in detail); it is a small user-attribution sub-object. Mark as
`TBD:` if exact fields are needed — not required to build the `bills`
snapshot reader since only bill-level dates are used for schema mapping.

### `PublicBillLineDto` (nested array in `billLines`, lines 6899–7207)

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `id` | string (uuid) | required | |
| `tenantId` | string (uuid) | nullable | |
| `audit` | object → `AuditInfo` | required | |
| `description` | string | required | |
| `quantity` | number | required | |
| `lineNumber` | integer | required | |
| `unitCost` | number | required | |
| `unitCostWithTax` | number | required | |
| `unitPrice` | number | nullable | |
| `taxable` | boolean | nullable | |
| `markup` | number | nullable | Percentage |
| `itemGlGroupId` | string | nullable | |
| `taxRegionId` | string | nullable | |
| `taxCategoryId` | string | nullable | |
| `amount` | number | nullable | Line value excl. tax |
| `taxAmount` | number | nullable | Sales tax amount |
| `useTaxAmount` | number | nullable | |
| `totalAmount` | number | nullable | Value + taxes |
| `accountingSystemLineId` | string | required | |
| `billId` | string (uuid) | required | FK to parent bill |
| `purchaseOrderLineId` | string (uuid) | nullable | |
| `purchaseOrderReceiptLineId` | string (uuid) | nullable | |
| `productId` | string (uuid) | required | |
| `costCodeId` | string (uuid) | nullable | |
| `departmentId` | string (uuid) | nullable | |
| `version` | integer | nullable | |
| `invoicedStatus` | string enum: `DoNotInvoice`, `Invoiced`, `NotInvoiced`, `PartiallyInvoiced` | nullable | |
| `jobId` | string (uuid) | nullable | |
| `projectId` | string (uuid) | nullable | |
| `projectPhaseId` | string (uuid) | nullable | |
| `projectCostCodeId` | string (uuid) | nullable | |
| `unitOfMeasure` | string | nullable | |
| `jcPhaseId` | string (uuid) | nullable | |
| `jcCostTypeId` | string (uuid) | nullable | |
| `jobCostTypeId` | string (uuid) | nullable | |
| `revenueTypeId` | string | nullable | |
| `billingStatus` | string enum: `NotInvoiced`, `Billed`, `DoNotInvoice` | nullable | |
| `jobCloseoutDescription` | string | nullable | |
| `jobCloseoutTaxable` | integer | nullable | |
| `equipmentId` | string (uuid) | nullable | |
| `providerTaxCodeId` | string (uuid) | nullable | |
| `equipment` | object → `EquipmentDto` | nullable | `EquipmentDto` schema is an empty object (`{}`) in the spec — no sub-fields documented (line 6839–6842) |
| `lineType` | string enum: `Inventory`, `ItemNonInventory` | required | |
| `workTaxabilityTypeId` | string (uuid) | nullable | |
| `purchaseOrderReceiptLineBillLines` | array of `PublicQuantityBilledDto` | nullable | Quantity-billed reconciliation records; each has `id`, `audit`, `quantityBilled`, `purchaseOrderReceiptLineId`, `billLineId`, `purchaseOrderReceiptLine` (lines 6843–6897) |

`required` on `PublicBillLineDto` (lines 7196–7207): `id`, `audit`,
`description`, `quantity`, `lineNumber`, `unitCost`, `unitCostWithTax`,
`billId`, `productId`, `lineType`.

### `AddressDto` (nested array in `addresses`, lines 6135–6183)

| Field | Type | Notes |
|---|---|---|
| `id` | string | nullable; "Address ID for patches" |
| `addressLine2` | string | nullable |
| `city` | string | required |
| `state` | string | required |
| `zipcode` | string | required |
| `addressType` | string enum: `billingAddress`, `propertyAddress`, `shippingAddress`, `shipFromAddress` | required |

Note: the example payload embedded in `PublicBillResponseDto.addresses`
(line 6131–6139 area) shows keys `line1`, `region`, `postalCode` — these do
**not** match the actual `AddressDto` property names (`addressLine2`,
`state`, `zipcode`; there is no `line1`/`addressLine1` property documented
at all). This is a **spec inconsistency** — trust the `AddressDto` schema
definition (city/state/zipcode/addressType, +optional id/addressLine2) over
the example block. Flagged in Known Quirks.

### `AttachmentDto` (nested in `vendorDocumentAttachment`, lines 8491+)

| Field | Type | Notes |
|---|---|---|
| `id` | string | |
| `customFileName` | string | nullable |
| `fileName` | string | |
| `fileUrl` | string | |
| `fileSize` | number | nullable |
| `description` | string | nullable |
| `originalFileName` | string | nullable |
| `isUploaded` | boolean | nullable |
| `comment` | string | nullable |
| `hideFromTechniciansOnMobile` | boolean | nullable |

(Additional fields may exist further in the schema past line 8550; not
required for the `bills` table beyond the attachment's identifying/URL
fields captured above.)

## **Get Object Primary Keys**

- **Static, not retrievable via API.** Primary key for `bills` is the
  single field **`id`** (string, `uuid` format) — the same value passed as
  the `{billId}` path parameter to `GET /v2/bills/{billId}`
  (`reference/domains/inventory/inventory.json` lines 2052–2062, 9837–9841).
- `PublicBillLineDto.id` is the primary key of individual bill line items
  (nested, not surfaced as a separate table in this research pass).
- There is no composite key; `billNumber` / `customIdentifier` are
  human-facing identifiers, not guaranteed-unique primary keys in the spec.

## **Object's ingestion type**

- **`bills` ingestion type: `snapshot`.**
- Rationale: the only read path is `GET /v2/bills/{billId}`, a
  point-lookup by id. There is no list endpoint, no `updatedSince`/cursor
  query parameter, and no changes/delta feed for bills in the published
  spec. Each configured `bill_ids` value is fetched fresh on every run — the
  connector cannot incrementally discover new/changed bill ids on its own;
  the caller must supply the id set (see below). This matches the
  `snapshot` definition: "the object can only be read with a snapshot, no
  incremental read."
- Deletes: `DELETE /v2/bills/{billId}` exists but there is no way to
  discover which ids were deleted without already knowing the id (no
  list/delta feed) — delete detection is therefore also out of scope; a
  404 on a previously-known id is the only available signal (see below).

## **Read API for Data Retrieval**

- **Method**: `GET /v2/bills/{billId}`
  (`reference/domains/inventory/inventory.json` lines 2052–2138).
- **Path parameter**: `billId` (string, required) — the bill's `id`.
- **Query parameter**: `include` (array, optional), repeatable, each value
  one of the enum: `purchaseOrder`, `purchaseOrderReceipt`, `vendor`, `job`,
  `project`, `department`, `orderedBy`, `projectManager`, `assignedTo`,
  `approvalNoteBy`, `paymentTerm`, `taxRate` (lines 2064–2088). Standard
  OpenAPI array-in-query encoding is assumed (repeat `include=<value>` per
  item); this was not independently verified against a live call in this
  pass — mark `TBD: verify exact array serialization style (repeat vs
  comma-separated) against the live dev server` in Known Quirks.
- **Required connector table options** (since there is no list endpoint):
  - `bill_ids` (required): comma-separated list of bill UUIDs to fetch. The
    connector issues one `GET /v2/bills/{billId}` call per id.
  - `include` (optional): comma-separated subset of the enum above, applied
    identically to every id in `bill_ids`.
- **Pagination**: **not applicable** — each call returns exactly one bill
  object (or a 404). There is no page/cursor/limit parameter on this
  endpoint.
- **Incremental strategy**: none available server-side. Because ingestion
  type is `snapshot`, the connector re-fetches every id in `bill_ids` on
  each run. If the caller wants to track "changed since X," they must
  inspect `audit.lastUpdatedDateTime` / `audit.lastUpdatedDate` themselves
  after ingestion — the API does not accept a since-parameter to filter
  server-side for a single-id GET.
- **Deleted records**: no delete-feed endpoint. A bill that has been
  deleted (`DELETE /v2/bills/{billId}`) will return **404 Not Found** on
  subsequent `GET /v2/bills/{billId}` calls. The connector should surface a
  404 for a configured `bill_ids` entry as an explicit error/warning
  (configurable ignore-missing behavior is a connector implementation
  decision) rather than silently dropping the row, since there is no way to
  distinguish "deleted" from "never existed"/"wrong id" from this response
  alone.
- **Response envelope**: the endpoint returns the `PublicBillResponseDto`
  object directly (no wrapping `data`/`results` envelope) — see schema
  section above.
- **Error responses documented for this endpoint** (lines 2101–2127): `400`
  Bad Request, `401` Unauthorized, `403` Forbidden, `404` Not Found, `409`
  Conflict, `500` Internal Server Error, `502` Bad Gateway, `503` Service
  Unavailable, `504` Gateway Timeout. **None of these response entries
  include a `content`/schema block** in the Bills paths (only a bare
  `description` string per status code) — unlike the `financialos` domain,
  which documents a structured `ErrorResponse` schema (`error` object) for
  its 4xx/5xx responses (`reference/domains/financialos/api.yaml` lines
  367–374, 500–550). The Inventory domain's Bills error body shape is
  **`TBD`**: not documented in this spec file. The general-domain auth
  error responses (`reference/domains/general/api.yaml` lines 44–109) use a
  `{"error": string, "message": string}` shape, which may or may not apply
  to Inventory-domain errors — treat as an unverified assumption pending a
  live call.
- **Rate limits**: **`TBD`** — not documented anywhere in the Inventory
  domain spec or the general getting-started docs reviewed for this pass.
  The only rate-limit language found in the whole local OpenAPI checkout is
  in the unrelated `financialos` domain (`reference/domains/financialos/api.yaml`
  line 545: `429-Rate-Limited: 'Rate Limited: Back off (1s start, 60s cap).'`),
  which does not apply to Inventory/Bills endpoints (no `429` response is
  declared on any `/v2/bills*` operation). The connector should implement a
  conservative exponential backoff (e.g. starting at 1s, capping at 60s, as
  a defensive default mirroring the one documented rate-limit policy
  elsewhere in the API) and treat `429`/`5xx` as retryable, but this is a
  **recommendation, not a documented contract**, for the Bills endpoints.

Example request:

```shell
curl --request GET \
  --url '<base_url>/v2/bills/2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231?include=vendor&include=department&include=paymentTerm' \
  --header 'Accept: application/json' \
  --header 'Authorization: Bearer <access_token>' \
  --header 'tenantId: <tenant-uuid>'
```

Example (abbreviated) response:

```json
{
  "id": "2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231",
  "tenantId": "2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231",
  "audit": {
    "createdDate": "2023-05-30T13:16:46Z",
    "createdDateTime": 1626240000000,
    "lastUpdatedDate": "2023-05-30T13:16:46Z",
    "lastUpdatedDateTime": 1626240000000,
    "deletedDate": null,
    "deletedDateTime": null
  },
  "billLines": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "description": "Item description",
      "quantity": 10.5,
      "lineNumber": 1,
      "unitCost": 100.5,
      "unitCostWithTax": 110.5,
      "billId": "2cdc8ab1-6d50-49cc-ba14-54e4ac7ec231",
      "productId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "lineType": "Inventory"
    }
  ],
  "transactionDate": 1633027200,
  "billNumber": "BILL-123",
  "description": "Bill for purchased items",
  "addedBy": "John Doe",
  "vendorDocumentNumber": "VENDOR-123",
  "orderedById": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "Pending",
  "isImported": true
}
```

### Write API (test-only — not part of the read connector)

Per project convention, write-back is used only for test fixture setup, via
`POST /v2/bills` (lines 2290–2353), body schema `CreateBillDto` (lines
10684–10957), response `PublicBillResponseDto`.

`CreateBillDto` required fields (lines 10953–10956): **`departmentId`**,
**`vendorId`**.

`CreateBillDto` optional fields (selected; full property list at lines
10684–10952): `id` (client-supplied uuid, "mobile requirement"),
`description`, `freight`, `purchaseOrderId`, `purchaseOrderReceiptId`,
`taxRateId`, `jobId`, `projectId`, `vendorDocumentNumber`, `issuedBy`
(unix), `postingDate` (unix), `dueDate` (unix), `projectManagerId`,
`paymentTermId`, `assignedToId`, `orderedById`, `accountingRefId`,
`syncStatus` (enum `SyncStatus`), `isImported`, `isStandalone`, `total`,
`taxAmountOverridden`, `tax`, `totalCost`, `isUseTaxable`, `taxRegionId`,
`billLines` (array of `CreateBillLineRequestDto`), `status` (enum, same
values as response `status`), `createdByEmployeeId`, `isCreatedFromMobile`,
`addresses` (array of `AddressDto`), `amountDue`, `isRetainageApplicable`,
`isRetainageBill`, `defaultRetainagePercent`, `totalRetainageAmount`,
`retainageAmountUnbilled`, `parentBillId`.

`CreateBillLineRequestDto` (nested in `billLines`, lines 10471–10683)
required fields: `quantity`, `lineNumber`, `unitCost`, `productId`,
`departmentId`. Optional fields include `id`, `description`, `unitPrice`,
`taxable`, `markup`, `taxRegionId`, `taxAmountOverridden`,
`providerTaxCodeId`, `costCodeId`, `jobId`, `unitOfMeasure`,
`jobCostTypeId`, `revenueTypeId`, `projectPhaseId`, `projectCostCodeId`,
`projectCostType`, `projectId`, `purchaseOrderLineId`,
`purchaseOrderReceiptLineId`, `equipmentId`, `accountingSystemLineId`,
`isUseTaxable`, `workTaxabilityTypeId`, `jcPhaseId`, `jcCostTypeId`,
`billingStatus`, `retainagePercent`, `retainageAmount`.

Example create request (minimal, required fields only):

```shell
curl --request POST \
  --url '<base_url>/v2/bills' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer <access_token>' \
  --header 'tenantId: <tenant-uuid>' \
  --data '{
        "departmentId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "vendorId": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }'
```

Other write-adjacent endpoints exist (`PATCH /v2/bills/{billId}`,
`DELETE /v2/bills/{billId}`, `POST /v2/bills/{billId}/void`,
`PUT /v2/bills/{billId}/export`, `PUT /v2/bills/{billId}/post`,
`POST /v2/bills/{billId}/bypass`, `POST /v1/bill-lines/bill/{billId}`) —
documented in the "Object List" endpoint table above for completeness, but
not detailed further here since they are not needed for read-connector
implementation; `DELETE` is useful for cleaning up test fixtures created via
`POST /v2/bills`.

## **Field Type Mapping**

| API type | Spark/standard type | Notes |
|---|---|---|
| `string` (no format) | `string` | Free text, e.g. `description`, `billNumber` |
| `string`, `format: uuid` | `string` | All `*Id` foreign keys and the `id` primary key |
| `string` (enum) | `string` | e.g. `status`, `invoicedStatus`, `approvalStatus`, `syncStatus`, `lineType`, `billingStatus`, `addressType` — treat as plain string with a known value set; do not assume exhaustiveness across API versions |
| `integer` (unix timestamp fields: `transactionDate`, `issuedBy`, `postingDate`, `dueDate`, `approvalNoteDateTime`) | `timestamp` (convert from epoch **seconds**) | Spec `type: integer` with example values like `1633027200` (10-digit — seconds, not millis) |
| `number` (money/quantity fields: `freight`, `tax`, `totalCost`, `unitCost`, `unitPrice`, `amount`, `quantity`, `markup`, etc.) | `double`/`decimal` | No explicit currency-precision constraint documented; treat as double unless downstream requires fixed-point decimal |
| `boolean` | `boolean` | e.g. `isImported`, `isCreatedFromMobile`, `taxable` |
| `AuditInfo.createdDateTime` / `deletedDateTime` | `number`, unix **millis** (13-digit example `1626240000000`) | Note this is a **different unit** (millis) than the bill-level date fields above (seconds) — a documented inconsistency, see Known Quirks |
| `AuditInfo.createdDate` / `lastUpdatedDate` / `deletedDate` | `string`, ISO-8601 (`2023-05-30T13:16:46Z`) | `timestamp` after parsing |
| `AuditInfo.lastUpdatedDateTime` | spec says `type: string` but example is a 13-digit millis integer | **Spec inconsistency** — likely should be `number`; treat with care, verify against a live payload |
| Nested object fields (`audit`, `billLines[]`, `addresses[]`, `vendorDocumentAttachment`, `purchaseOrder`, `vendor`, etc.) | `struct`/`array<struct>` | Structs per the schemas documented above; relation objects (`vendor`, `job`, etc.) only populate when requested via `include` |
| `EquipmentDto` (nested in `billLines[].equipment`) | `struct` (empty) | Spec defines this as an empty object schema (`{}`) — no sub-fields documented anywhere in the file; if the live API actually returns fields here, this is undocumented and must be verified live |

### Known Quirks

**Verified against the live dev API (2026-09-24)** -- these supersede the
"assumed / TBD" notes below where they conflict:

- **`include` serialization**: the API honours only a single comma-separated
  value (`include=vendor,department`). The repeated-key form
  (`include=vendor&include=department`) returns HTTP 200 but embeds nothing.
  Unknown values return HTTP 400 `BadRequestException`
  (`Property "x" is not a valid property`).
- **Include-gated keys**: besides the 12 documented relations, `billLines`,
  `addresses` and `vendorDocumentAttachment` are also accepted `include`
  values, and GET omits these keys entirely unless requested (the documented
  "required" `billLines` is absent from a plain GET). POST responses embed
  `billLines`, `vendor` and `purchaseOrder`.
- **Undocumented response fields** (present on every GET): `uniqueBillNumber`,
  `accountingRefId`, `isStandalone`, `totalAmountPreTax`, `taxRegionId`,
  `isUseTaxable`, `useTaxTotal`, `taxAmountOverridden`, `isReceiptBound`,
  `vendorDocumentAttachmentId`, `amountDue`, `isRetainageApplicable`,
  `isRetainageBill`, `defaultRetainagePercent`, `totalRetainageAmount`,
  `retainageAmountUnbilled`, `parentBillId`, `vendorLocationId`,
  `vendorContactId`, `billToAddressId`, `shipToAddressId`, `shipFromAddressId`.
- **Timestamps**: `audit.createdDateTime` / `lastUpdatedDateTime` are JSON
  integers (13-digit epoch millis) -- `lastUpdatedDateTime` is NOT a string
  live. `audit.*Date` ISO fields are null. `audit.*By` are
  `{"username": ...}` objects. Create accepts and echoes 10-digit epoch
  seconds for `dueDate` / `postingDate` / `issuedBy`; `transactionDate` is
  dropped on create (server-managed, null on new bills).
- **Token**: `expires_in` is `10800` (3h), `token_type` is `bearer`.
- **Create / delete**: `POST /v2/bills` returns 201 and honours a
  client-supplied `id`; a bill line requires `lineNumber` and a `productId`
  UUID. `DELETE /v2/bills/{billId}` returns 204 with an empty body, after
  which GET returns 404 `NotFoundException` (`Bill not found`).


- **No list endpoint** for bills — `bills` must be read by id
  (`bill_ids` connector option), not paginated. See "Object List" section.
- **`AddressDto` example payload mismatch**: the example blocks attached to
  `PublicBillResponseDto.addresses` and `CreateBillDto.addresses` use keys
  `line1` / `region` / `postalCode`, which do not exist on the actual
  `AddressDto` schema (`city` / `state` / `zipcode`, no `line1`/`addressLine1`
  at all, only `addressLine2`). Trust the schema, not the example, but flag
  for live verification.
- **Timestamp unit inconsistency**: bill-level date fields
  (`transactionDate`, `issuedBy`, `postingDate`, `dueDate`,
  `approvalNoteDateTime`) use 10-digit **unix seconds** in their examples,
  while `AuditInfo.createdDateTime`/`deletedDateTime` use 13-digit **unix
  millis**, and `AuditInfo.lastUpdatedDateTime` is typed as a `string` but
  exemplified with a millis integer. Verify actual units live before
  building the timestamp-parsing logic.
- **`issuedBy` is a date, not a person**, despite its name (int/unix
  timestamp per schema, described as "the date the bill is required to be
  issued by").
- **Undocumented error body schema** for Bills endpoints (see "Read API"
  section) — 4xx/5xx responses have no `content` schema in the spec.
- **Undocumented rate limits** for Inventory/Bills endpoints — the only
  rate-limit contract in the local spec checkout belongs to the unrelated
  `financialos` domain.
- **`include` array query-param serialization** (repeat-key vs
  comma-separated) is assumed, not verified against a live call in this
  research pass.
- Two servers exist (prod `https://public-api.live.buildops.com`, dev
  `https://public-api.dev.buildops.com`); the connector's `base_url` option
  defaults to the **dev** URL per project instructions, not the OpenAPI
  spec's server-list ordering (which lists prod first).

## **Deferred Tables**

Per the requested research scope, **only `bills` was researched and
documented** in this pass. The Inventory domain spec
(`reference/domains/inventory/inventory.json`, 12,498 lines) also documents
many other objects/tags not investigated here, including but not limited
to: Purchase Orders, Purchase Order Receipts, Purchase Order Lines,
Purchase Order Receipt Lines, Vendors, Products, Departments, Payment
Terms, Tax Rates/Regions, Equipment, and Bill Lines as a possible
standalone table (currently only documented here as a nested array within
`bills`, via `POST /v1/bill-lines/bill/{billId}`). Other domains in the
repo (`account-management`, `labor`, `financialos`, `general`) are entirely
out of scope for this pass. These should be documented in their own
sections/batches if the `buildops` connector is expanded beyond `bills`.

## Research Log

| Source Type | URL / Path | Accessed (UTC) | Confidence | What it confirmed |
|---|---|---|---|
| User-provided / internal spec repo | `/home/alvin/_git/buildops/open-api-spec/reference/domains/general/api.yaml` | 2026-09-24 | Highest | Servers (prod/dev), `POST /v1/auth/token` request/response schema, `GET /v1/auth/scope`, required `Authorization`/`tenantId` headers, generic error response shapes for the auth domain |
| User-provided / internal spec repo | `/home/alvin/_git/buildops/open-api-spec/docs/getting started/Authentication-Authorization-and-Scope.md` | 2026-09-24 | Highest | Auth flow narrative, example curl requests/responses, token lifetime (86400s), multi-tenant scoped-token behavior |
| User-provided / internal spec repo | `/home/alvin/_git/buildops/open-api-spec/reference/domains/inventory/inventory.json` (lines 2052–2668, 3359–3367, 6135–6183, 6442–6485, 6839–7207, 8491–8550, 9599–9608, 9834–10256, 10257–10957) | 2026-09-24 | Highest | All Bills path operations (`GET/PATCH/DELETE /v2/bills/{billId}`, `POST /v2/bills`, void/export/post/bypass, bill-line create), `PublicBillResponseDto`, `PublicBillLineDto`, `CreateBillDto`, `CreateBillLineRequestDto`, `AuditInfo`, `AddressDto`, `AttachmentDto`, `SyncStatus`, `ApprovalStatus` schemas; absence of any `GET /v2/bills` list operation and absence of `429`/error-schema content on Bills responses |
| User-provided verified facts (orchestrator-supplied, pre-investigated) | Internal `backend-services-ts` repo (`packages/procurement/src/adapters/controllers/bill/bill.controller.ts`), not directly re-read in this pass | 2026-09-24 | Highest (pre-verified by requester) | Confirms no GET-list handler backs `GET /v2/bills`; listing exists only as internal `POST bills/search`, not exposed publicly — matches the spec's omission of a list operation |
| User-provided / internal spec repo | `/home/alvin/_git/buildops/open-api-spec/reference/domains/financialos/api.yaml` (lines 367–550) | 2026-09-24 | High | Confirms rate-limit (`429`, 1s–60s backoff) and structured `ErrorResponse` schema exist in a *different* domain (financialos), and are absent for Inventory/Bills — used to establish that Bills-specific rate limits/error schema are undocumented (`TBD`) |
| Repo convention reference | `/home/alvin/_git/buildops/lakeflow-community-connectors/.claude/worktrees/connector-buildops/src/databricks/labs/community_connector/sources/remberg/remberg_api_doc.md` | 2026-09-24 | Medium | Used only as a formatting/style reference for an existing accepted API doc in this repo; no BuildOps facts drawn from it |

No Airbyte, Fivetran, Singer, or public web documentation was consulted for
this pass — the task explicitly scoped research to the local, read-only
internal OpenAPI spec checkout (`/home/alvin/_git/buildops/open-api-spec`)
plus pre-verified facts supplied by the requester, since BuildOps' public
API is not indexed by these standard third-party connector catalogs at the
time of writing.
