# **Miter API Documentation**

## **Authorization**
- **Chosen method**: Static API token, sent as an HTTP Bearer token. Miter's OpenAPI spec declares a single security scheme (`HTTP_1`: `type: http`, `scheme: bearer`) and every operation requires it.
- **Auth placement**: HTTP header `Authorization: Bearer <API_TOKEN>` on every request. There is no OAuth flow — the connector stores the token as an opaque secret and sends it as-is; it does not exchange or refresh anything.
- **Obtaining a token**: The provided spec and Postman collection do not document the token-issuance UI (`TBD: no source covers where in the Miter app a company generates an API token`). Once a token exists, verify it works with `GET /ping`.
- **Token scopes**: Tokens are scoped per resource and action (e.g. `team_members:read`, `team_members:write`). `GET /ping` returns the token's `scopes`, so a token may not have read access to every object below — a `403` on an otherwise-valid request likely means the object is outside the token's granted scopes, not a connector bug.
- **Rate limits**: Also returned by `GET /ping` (`data.rate_limits`), per-token — see **Read API for Data Retrieval** below.

**Example request**:
```
GET https://api.miter.com/api/v2/ping
Authorization: Bearer <API_TOKEN>
Accept: application/json
```

**Example response** (`200 OK`):
```json
{
  "success": true,
  "data": {
    "company_id": "507f1f77bcf86cd799439011",
    "token_name": "My API Token",
    "scopes": ["team_members:read", "team_members:write"],
    "rate_limits": {
      "single_action_per_minute": 100,
      "bulk_action_per_minute": 60
    }
  }
}
```

## **Object List**
All objects live under the base URL `https://api.miter.com/api/v2` (per `servers` in the spec, and `baseUrl` in the Postman collection). The object list is **static** — it is the fixed set of resources declared in the OpenAPI spec; there is no discovery/introspection endpoint that enumerates readable objects at runtime.

Four objects are **nested under a parent object's ID** (path contains `{parent_id}`) — they must be listed once per parent record, not queried globally. Two further objects (`Pay Periods`, `Assignment Occurrences`) are **computed views** scoped to one parent record and a date range, not independently listable/paginated resources.

| Object | Endpoint | Category (spec tag) | Nested under |
|---|---|---|---|
| Activities | `GET /activities` | Activities |  |
| Allocation Rule Groups | `GET /allocation_rule_groups` | Allocation Rule Groups |  |
| Assignments | `GET /assignments` | Assignments |  |
| Bank Accounts | `GET /bank_accounts` | Bank Accounts |  |
| Bills | `GET /bills` | Bills |  |
| Budgets | `GET /budgets` | Budgets |  |
| Budgets → Budget Line Items | `GET /budgets/{parent_id}/line_items` | Budget > Budget Line Items | `budgets` |
| Burden Rates | `GET /burden_rates` | Burden Rates |  |
| Card Transactions | `GET /card_transactions` | Card Transactions |  |
| Certification Types → Certifications | `GET /certification_types/{parent_id}/certifications` | Certification Type > Certifications | `certification_types` |
| Certification Types | `GET /certification_types` | Certification Types |  |
| Classes | `GET /classes` | Classes |  |
| Company Benefits | `GET /company_benefits` | Company Benefits |  |
| Company Entities | `GET /company_entities` | Company Entities |  |
| Cost Types | `GET /cost_types` | Cost Types |  |
| Crews | `GET /crews` | Crews |  |
| Custom Earning Codes | `GET /custom_earning_codes` | Custom Earning Codes |  |
| Custom Tasks | `GET /custom_tasks` | Custom Tasks |  |
| Customers | `GET /customers` | Customers |  |
| Daily Reports | `GET /daily_reports` | Daily Reports |  |
| Departments | `GET /departments` | Departments |  |
| Employee Benefits | `GET /employee_benefits` | Employee Benefits |  |
| Equipment | `GET /equipment` | Equipment |  |
| Equipment Timesheets | `GET /equipment_timesheets` | Equipment Timesheets |  |
| Expense Cards | `GET /expense_cards` | Expense Cards |  |
| Expense Reimbursement Categories | `GET /expense_reimbursement_categories` | Expense Reimbursement Categories |  |
| Expense Reimbursements | `GET /expense_reimbursements` | Expense Reimbursements |  |
| Files | `GET /files` | Files |  |
| Fillable Templates | `GET /fillable_templates` | Fillable Templates |  |
| Form Submissions | `GET /form_submissions` | Form Submissions |  |
| Form Templates | `GET /form_templates` | Form Templates |  |
| Forms | `GET /forms` | Forms |  |
| Holiday Schedules | `GET /holiday_schedules` | Holiday Schedules |  |
| Integration Sync Items | `GET /integration_sync_items` | Integration Sync Items |  |
| Integration Syncs | `GET /integration_syncs` | Integration Syncs |  |
| Job Postings | `GET /job_postings` | Job Postings |  |
| Jobs | `GET /jobs` | Jobs |  |
| Leave Types | `GET /leave_types` | Leave Types |  |
| Ledger Accounts | `GET /ledger_accounts` | Ledger Accounts |  |
| Ledger Entries → Ledger Line Items | `GET /ledger_entries/{parent_id}/line_items` | Ledger Entry > Ledger Line Items | `ledger_entries` |
| Ledger Entries | `GET /ledger_entries` | Ledger Entries |  |
| Ledger Mappings | `GET /ledger_mappings` | Ledger Mappings |  |
| Locations | `GET /locations` | Locations |  |
| Message Templates | `GET /message_templates` | Message Templates |  |
| Notes | `GET /notes` | Notes |  |
| Team Member Onboarding Checklists | `GET /onboarding_checklists` | Team Member Onboarding Checklists |  |
| Overtime Rules | `GET /overtime_rules` | Overtime Rules |  |
| Pay Rate Groups | `GET /pay_rate_groups` | Pay Rate Groups |  |
| Pay Rate Groups → Classifications | `GET /pay_rate_groups/{parent_id}/classifications` | Pay Rate Group > Classifications | `pay_rate_groups` |
| Pay Rate Versions | `GET /pay_rate_versions` | Pay Rate Versions |  |
| Pay Schedules | `GET /pay_schedules` | Pay Schedules |  |
| Payroll Payments | `GET /payroll_payments` | Payroll Payments |  |
| Payrolls | `GET /payrolls` | Payrolls |  |
| Policies | `GET /policies` | Policies |  |
| Position Templates | `GET /position_templates` | Position Templates |  |
| Post Tax Deductions | `GET /post_tax_deductions` | Post Tax Deductions |  |
| Quantity Logs | `GET /quantity_logs` | Quantity Logs |  |
| Rate Differentials | `GET /rate_differentials` | Rate Differentials |  |
| Standard Classifications | `GET /standard_classifications` | Standard Classifications |  |
| Tax Filings | `GET /tax_filings` | Tax Filings |  |
| Team Members | `GET /team_members` | Team Members |  |
| Team Members → Onboarding Checklists | `GET /team_members/{parent_id}/onboarding_checklists` | Team Member > Onboarding Checklists | `team_members` |
| Third Party Cards | `GET /third_party_cards` | Third Party Cards |  |
| Time Off Policies | `GET /time_off_policies` | Time Off Policies |  |
| Time Off Requests | `GET /time_off_requests` | Time Off Requests |  |
| Timesheets | `GET /timesheets` | Timesheets |  |
| Trades | `GET /trades` | Trades |  |
| Vendors | `GET /vendors` | Vendors |  |
| Work Orders | `GET /work_orders` | Work Orders |  |
| Workers Comp Codes | `GET /workers_comp_codes` | Workers Comp Codes |  |
| Workers Comp Groups | `GET /workers_comp_groups` | Workers Comp Groups |  |
| Workplaces | `GET /workplaces` | Workplaces |  |
| Break Types | `GET /break_types` | Break Types |  |
| Card Balance | `GET /card_balance` | Card Balance |  |
| Pay Schedules → Pay Periods | `GET /pay_schedules/{id}/pay_periods` | Pay Schedules | `pay_schedules` |
| Assignments → Occurrences | `GET /assignments/{id}/occurrences` | Assignments | `assignments` |

**Known quirks**:
- `Card Balance` (`GET /card_balance`) returns a single object (the company's current spend-card balance), not a list — there is no `results` array and no `id`.
- `Break Types` (`GET /break_types`) returns the full set of configured break types in one unpaginated call (company-level config, typically a handful of rows).
- `Pay Periods` (`GET /pay_schedules/{id}/pay_periods`) and `Assignment Occurrences` (`GET /assignments/{id}/occurrences`) are derived/computed on the fly from a parent record plus a date range; they are not independently paginated or sortable.

## **Object Schema**
There is no schema-discovery endpoint (e.g. no `OPTIONS`/`describe` call) — object shapes are **static** and fully defined by the response schemas in the provided OpenAPI spec (`miter-openapi.json`, `info.version: "2.0"`). The field tables below were extracted directly from each endpoint's success-response schema (`200.content.application/json.schema.properties.data...`).

Every list endpoint wraps its rows in the same envelope:
```json
{
  "success": true,
  "data": {
    "size": 100,
    "next_page": "<objectid-or-null>",
    "results": [ { /* object fields, one per row below */ } ]
  }
}
```

A handful of response schemas (`BankAccountResponse`, `PolicyResponse`, `PostTaxDeductionResponse`, `CardTransactionResponse`, `BreakType`) are **polymorphic** (`oneOf`/`anyOf`/`allOf` of several sub-shapes, e.g. a bank account can be a `company`, `team_member`, or `vendor` account with slightly different fields). For those, the table below is the **union of all variant fields** — not every field is present on every row; consult the discriminant field noted for that object.

Field types below are simplified from the OpenAPI schema (see **Field Type Mapping** for the full mapping rule). `_id`-suffixed fields are Miter ObjectIds (24-character hex strings) referencing another object — where the prefix matches an object name in the list above, it references that object's `id`.

### Activities (`ActivityResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The label of the activity. |
| `job_id` | string (objectid, nullable) |  | The parent job ID of the activity. |
| `pay_rate_type` | enum[default,custom,pw,prg] | yes | The type of pay rate for the activity. |
| `prevailing_wage` | boolean \| null | yes | Whether the activity is prevailing wage. |
| `non_standard_overtime` | boolean \| null | yes | Whether the activity is non-standard overtime. |
| `pay_rate_always_on` | boolean \| null | yes | Whether the activity is pay rate always on. |
| `company_activity` | boolean \| null | yes | Whether the activity is a company activity. |
| `cost_code` | string |  | The cost code of the activity. |
| `workers_compensation_code_id` | string (objectid, nullable) |  | The ID of the workers' compensation code associated with the activity. |
| `fringe_rate` | number \| null |  | The fringe rate of the activity. |
| `overtime_rule_id` | string (objectid, nullable) |  | The overtime rule ID of the activity. |
| `pay_rate` | number \| null |  | The pay rate of the activity. |
| `pay_rate_group_id` | string (objectid, nullable) |  | The pay rate group ID of the activity. |
| `standard_classification_id` | string (objectid, nullable) |  | The standard classification ID of the activity. |
| `qualification_level` | string \| null |  | The qualification level of the activity. |
| `non_billable` | boolean \| null | yes | Whether the activity is non-billable. |
| `equipment_maintenance` | boolean \| null | yes | If true, hours logged on this activity are tracked as equipment maintenance instead of equipment usage. This setting on the activity cannot be edited after the activity is created — to change it,... |
| `ignore_in_ot_calculations` | boolean \| null |  | Whether the activity is ignored in OT calculations. |
| `scopes` | array<enum[timesheets,expenses,reimbursements,quantities]> | yes | The scopes of the activity. |
| `integration_metadata_by_system` | object |  |  |

### Allocation Rule Groups (`AllocationRuleGroupResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the allocation rule group. |
| `type` | enum[salary] | yes | The type of allocation. |
| `rules` | array<object> | yes | The allocation rules in this group. |

### Assignments (`AssignmentResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `title` | string | yes | The title of the assignment. |
| `description` | string \| null |  | An optional longer description of the assignment. |
| `starts_at` | timestamp | yes | When the assignment starts, as an ISO-8601 datetime (UTC). |
| `ends_at` | timestamp | yes | When the assignment ends, as an ISO-8601 datetime (UTC). |
| `address` | object |  | The address where the assignment takes place. |
| `type` | enum[ancestor,non-recurring-child,recurring-child] | yes | The role this record plays in a recurrence series: `ancestor` is the series template, `recurring-child` is a generated occurrence, `non-recurring-child` is a one-off. |
| `team_member_ids` | array<string (objectid)> | yes | IDs of team members assigned. |
| `job_id` | string (objectid, nullable) |  | The ID of the job the assignment is for. |
| `activity_id` | string (objectid, nullable) |  | The ID of the activity the assignment is for. |
| `work_order_id` | string (objectid, nullable) |  | The ID of the work order the assignment is associated with. |
| `equipment_ids` | array \| null |  | IDs of equipment assigned to the assignment. |
| `certification_type_ids` | array \| null |  | IDs of certification types required for the assignment. |
| `rate_differential_id` | string (objectid, nullable) |  | The ID of the rate differential applied to the assignment. |
| `ancestor_assignment_id` | string (objectid, nullable) |  | For child occurrences, the ID of the ancestor assignment they were generated from. |
| `original_starts_at` | timestamp |  | For a rescheduled recurring occurrence, the originally scheduled start time as an ISO-8601 datetime (UTC). |
| `recurrence_config` | object |  | Recurrence rules for ancestor assignments. |
| `custom_color` | string \| null |  | An optional color override used when rendering the assignment. |

### Bank Accounts (`BankAccountResponse`)
_Polymorphic response — union of all variant fields shown._

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `account_number_last_4` | string | yes | The last four digits of the bank account number. |
| `account_subtype` | enum[checking,savings] | yes | Whether the account is a checking or savings account. |
| `routing_number` | string \| null |  | The routing number of the bank account. |
| `ledger_account_id` | string (objectid, nullable) |  | The ID of the ledger account this bank account is booked to. |
| `name` | string \| null | yes | A display name for the bank account, derived from the linked institution or Plaid account name. Null when no name could be derived. |
| `verification_status` | enum[verified,reconnect_required,unverified,disabled] | yes | The verification state of the bank account. `verified` accounts can be used for payments. `unverified` accounts are still pending verification. `reconnect_required` means the Plaid connection has... |
| `disabled_reason` | string \| null | yes | The reason payments to and from this account are currently failing, as reported by our payments provider. Common values: `validation_failed`, `failed_payment`, `verification_pending`, `noc_received`,... |
| `reconnect_required` | boolean | yes | Whether the account's bank connection needs to be re-linked before payments can proceed. |
| `connection` | enum[plaid,manual] | yes | How the bank account is connected in Miter: `plaid` for accounts linked through Miter's Plaid integration, `manual` for accounts entered by hand, including legacy accounts whose Plaid link is held by... |
| `owner` | string | yes |  |
| `team_member_id` | string (objectid) |  | The ID of the team member who owns this bank account. Null only in the brief window while a newly linked account's team member record is still syncing. |
| `vendor_id` | string (objectid) |  | The ID of the vendor who owns this bank account. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity that pays from this account. |

### Bills (`BillResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `invoiced_on_date` | date | yes | The date the bill was invoiced, as an ISO-8601 date string. |
| `due_date` | date |  | The date payment is due to the vendor, as an ISO-8601 date string. |
| `vendor_id` | string (objectid, nullable) |  | The ID of the vendor this bill was issued by. Absent on drafts that have not been matched to a vendor yet. |
| `invoice_number` | string |  | The vendor's invoice number. |
| `description` | string \| null |  | Free-text description or memo for the bill. |
| `status` | enum | yes | The status of the bill. |
| `payment_method` | enum[ach,check,manual] | yes | How the bill is paid. |
| `line_items` | array<object> | yes | The cost lines that make up this bill. |
| `bank_account_id` | string (objectid, nullable) |  | The company bank account used to fund this bill's payment. |
| `file_ids` | array<string (objectid)> | yes | IDs of files attached to this bill. |
| `payroll_id` | string (objectid, nullable) |  | Set when the bill was generated from a payroll liability. |
| `payroll_payment_id` | string (objectid, nullable) |  | The payroll payment this bill's liability was generated from. |
| `scheduled_at` | timestamp |  | Midnight, company-local, on the day payment is scheduled to start. |
| `payment_initiated_at` | timestamp |  | When the bill was submitted for payment processing. |
| `creation_source` | enum[dashboard_individual,email_forward,payroll_liability] |  | How the bill entered Miter — manual entry, an inbound email, or a payroll liability. |
| `custom_field_values` | array<object> |  | Custom field values on the bill. |

### Budgets (`BudgetResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `job_id` | string (objectid) | yes | The ID of the job this budget belongs to. |
| `type` | enum[production,cost] | yes | The type of budget. `production` budgets track estimated quantities; `cost` budgets track dollar amounts. Immutable after creation. |

### Budgets → Budget Line Items (`BudgetLineItemResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `job_id` | string (objectid) | yes | The ID of the job (or sub-job of the budget's job) this line item belongs to. Immutable after creation. |
| `activity_id` | string (objectid) | yes | The ID of the activity this line item tracks. Immutable after creation. |
| `description` | string |  | A human-readable description for the line item. |
| `notes` | string |  | Free-text notes for the line item (e.g. change order references). User-owned: never overwritten by integration syncs. |
| `unit_of_measure` | enum |  | The unit of measure for the estimated quantity. Omitted when the stored value is unset or unrecognized. |
| `estimated_quantity` | number |  | The estimated quantity. Must be provided together with `unit_cost`, or in lieu of `amount`. |
| `unit_cost` | number |  | The cost per unit. Must be provided together with `estimated_quantity`, or in lieu of `amount`. |
| `amount` | number |  | The total amount for this line item. Provide either `amount` directly, or both `unit_cost` and `estimated_quantity`. |
| `cost_type_id` | string (objectid) |  | The ID of the cost type for this line item. |
| `department_id` | string (objectid) |  | The ID of the department for this line item. |
| `location_id` | string (objectid) |  | The ID of the location for this line item. |
| `class_id` | string (objectid) |  | The ID of the class for this line item. |
| `budget_id` | string (objectid) | yes | The ID of the parent budget. Read-only; set from the URL when the line item is created. |
| `version` | number | yes | The revision number of this line item. Every update creates a new line item document with `version + 1`; the previous version is kept in the database for history but has `latest: false`. |
| `latest` | boolean | yes | Whether this row is the latest version for its `(job_id, activity_id)` within the budget. Read-only; maintained by the service on each update. |

### Burden Rates (`BurdenRateResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The human-readable label for the burden rate. |
| `rate` | number | yes | The numeric burden rate amount. |
| `rate_type` | enum[per_hour,percent,percent_of_std_earnings,lump_sum] | yes | How the rate is applied. |
| `overtime_multipliers` | object |  | Overtime / double-overtime multipliers, when the rate varies by overtime tier. |
| `earning_type_scope` | enum[all,hourly,non_hourly] | yes | Which earning types the burden rate applies to. |
| `job_scope` | enum[all,all_jobs,all_jobs_except,certain_jobs,no_job,public_jobs,private_jobs] | yes | Which jobs the burden rate applies to. |
| `activity_scope` | string \| null |  | Which activities the burden rate applies to. |
| `activity_id` | string (objectid, nullable) |  | The ID of the activity this burden rate is allocated to. |
| `cost_type_id` | string (objectid, nullable) |  | The ID of the cost type this burden rate is allocated to. |
| `expense_cost_type_id` | string (objectid, nullable) |  | The ID of the cost type used when expensing the burden rate. |
| `credit_cost_type_id` | string (objectid, nullable) |  | The ID of the cost type used when crediting the burden rate. |
| `debit_account_id` | string (objectid, nullable) |  | The ID of the ledger account debited for the burden rate. |
| `credit_account_id` | string (objectid, nullable) |  | The ID of the ledger account credited for the burden rate. |
| `included_job_ids` | array \| null |  | Jobs the burden rate is restricted to (when `job_scope` is `certain_jobs`). |
| `excluded_job_ids` | array \| null |  | Jobs the burden rate excludes (when `job_scope` is `all_jobs_except`). |
| `included_activity_ids` | array \| null |  | Activities the burden rate is restricted to. |
| `excluded_activity_ids` | array \| null |  | Activities the burden rate excludes. |
| `lump_sum_distribution_mode` | string \| null |  | For `rate_type: lump_sum`, how the lump sum is distributed across earnings. |
| `lump_sum_distribution_job_ids` | array \| null |  | For `rate_type: lump_sum` with `job_costed_only`, specific jobs to include. |

### Card Transactions (`CardTransactionResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `amount` | number | yes | The amount of the card transaction (in dollars). Can be negative for refunds. |
| `merchant_name` | string | yes | The name of the merchant. |
| `date` | date | yes | The date of the card transaction. |
| `custom_id` | string | yes | The custom ID of the card transaction. |
| `file_ids` | array<string (objectid)> | yes | The IDs of the files associated with the card transaction. |
| `team_member_id` | string (objectid, nullable) |  | The ID of the team member who made the card transaction. |
| `department_id` | string (objectid, nullable) |  | The ID of the department assigned to the transaction. |
| `location_id` | string (objectid, nullable) |  | The ID of the location assigned to the transaction. |
| `class_id` | string (objectid, nullable) |  | The ID of the class assigned to the transaction. |
| `job_id` | string (objectid, nullable) |  | The ID of the job assigned to the transaction. |
| `activity_id` | string (objectid, nullable) |  | The ID of the activity assigned to the transaction. |
| `cost_type_id` | string (objectid, nullable) |  | The ID of the cost type assigned to the transaction. |
| `ledger_account_id` | string (objectid, nullable) |  | The ID of the ledger account assigned to the transaction. |
| `equipment_id` | string (objectid, nullable) |  | The ID of the equipment assigned to the transaction. |
| `card_transaction_category_id` | string (objectid, nullable) |  | The ID of the card transaction category assigned to the transaction. |
| `submitter_note` | string \| null |  | The note added by the submitting team member for the card transaction. |
| `merchant_info` | object |  | Merchant city, state, country, and category. |
| `approval_status` | enum[unapproved,denied,approved] | yes | The approval status of the card transaction. |
| `purchase_status` | enum[pending,closed,declined,reversed] | yes | The purchase status of the card transaction. |
| `voided` | boolean | yes | Whether the card transaction has been voided (reversed, removed, or merged away). Defaults to false. |
| `currency` | string | yes | The ISO 4217 currency code of the card transaction. |
| `source` | string \| null |  | The last 4 digits of the card used for the transaction. |
| `approver_note` | string \| null |  | The note added by the approver for the card transaction. |
| `posted_date` | date |  | The date the card transaction settled. Distinct from `date`, which is the date the transaction was made. |
| `type` | string | yes |  |
| `third_party_card_id` | string \| null |  | The ID of the third party card associated with the transaction. |
| `merge_info` | object \| null |  | Reconciliation details, present when an imported card transaction has been merged into this transaction. Null when no merge has occurred. |
| `merged_into_id` | string (objectid, nullable) |  | For an imported card transaction that has been reconciled into a feed transaction, the ID of the surviving feed transaction it was merged into. The inverse of `merge_info.merged_from_imported_id`.... |
| `custom_field_values` | array<object> |  | Custom field values on the card transaction. |

### Certification Types → Certifications (`CertificationResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes | The team member this certification is assigned to. |
| `certification_type_id` | string (objectid) | yes | The certification type ID. |
| `submitted` | boolean \| null |  | Whether the certification has been submitted. |
| `custom_field_values` | array \| null |  | Answers for custom fields defined on the certification type. |
| `file_upload_values` | array \| null |  | File upload field answers. |
| `expires_at` | string \| null |  | Expiration date/time as an ISO-8601 string, if applicable. |
| `completed_at` | timestamp |  | When the certification was completed, as an ISO-8601 datetime (UTC). |

### Certification Types (`CertificationTypeResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `title` | string | yes | Display name of the certification type. |
| `description` | string \| null |  | Longer description of the certification type. |
| `expires` | boolean | yes | Whether certifications of this type can expire. |
| `automatic_request_on_expiration` | boolean | yes | Whether Miter should automatically request renewal when a certification expires. |
| `source` | enum[external,learning] | yes | How this certification type is provisioned (e.g. external vs learning). |
| `custom_fields` | array<object> | yes | Non-file custom fields (text, select, etc.) |
| `file_uploads` | array<object> | yes | File- and photo-type custom fields |

### Classes (`ClassResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string \| null |  | The name of the class. |
| `code` | string \| null |  | A short code identifying the class. |
| `status` | string \| null |  | Whether the class is active or inactive. |
| `parent_class_id` | string (objectid, nullable) |  | The ID of the parent class, if this class is nested under another. |
| `ledger_mapping_id` | string (objectid, nullable) |  | The ID of the ledger mapping associated with the class. |

### Company Benefits (`CompanyBenefitResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `company_entity_id` | string (objectid, nullable) |  | Company entity this plan is offered under. Null when offered to all entities. |
| `benefit_type` | enum | yes | The kind of benefit plan, e.g. 125_medical, 401k, hsa. |
| `description` | string \| null |  | Free-text description of the benefit plan. |
| `effective_start` | date |  | The date this benefit plan takes effect, as an ISO-8601 date string. |
| `effective_end` | date |  | The date this benefit plan ends, as an ISO-8601 date string. Null if ongoing. |
| `employee_contribution_amount` | number \| null |  | Flat amount the team member contributes each paycheck, in dollars. Null when percent-based. |
| `employee_contribution_percent` | number \| null |  | Percent of pay the team member contributes each paycheck. Null when a flat amount is used. |
| `company_contribution_amount` | number \| null |  | Flat amount the company contributes each paycheck, in dollars. Null when percent-based. |
| `company_contribution_percent` | number \| null |  | Percent of pay the company contributes each paycheck. Null when a flat amount is used. |
| `contribution_period` | string \| null |  | Set to monthly when the period amounts below are monthly totals spread across paychecks. Null when contributions are per paycheck. |
| `employee_period_amount` | number \| null |  | Monthly total the team member contributes, in dollars. Only set when contribution_period is monthly. |
| `company_period_amount` | number \| null |  | Monthly total the company contributes, in dollars. Only set when contribution_period is monthly. |
| `hsa_contribution_limit` | string \| null |  | Which IRS annual HSA limit applies. Only set for HSA benefits. |
| `per_hour_employee_contribution` | boolean \| null |  | True when the team member's flat contribution is applied per hour worked instead of per paycheck. |
| `per_hour_company_contribution` | boolean \| null |  | True when the company's flat contribution is applied per hour worked instead of per paycheck. |
| `plan_number` | string \| null |  | The plan or policy number used on reports. |
| `fringe_offset_behavior` | enum[non_bonafide,auto_offset,straight_time_offset,reg_only_offset] | yes | How company contributions offset prevailing-wage fringe obligations. |
| `overtime_multipliers` | object |  |  |
| `imputed_earning_amount` | number \| null |  | Taxable imputed earning added for this benefit, in dollars. Only applies to some insurance benefits. |
| `imputed_earning_auto_calculate` | boolean \| null |  | True when the imputed earning is derived each payroll from coverage_amount and the team member's age. |
| `coverage_amount` | number \| null |  | Total group-term life coverage, in dollars. Used to calculate the imputed earning. |
| `employee_liability_ledger_account_id` | string (objectid, nullable) |  | Ledger account that team member contributions post to. |
| `company_liability_ledger_account_id` | string (objectid, nullable) |  | Ledger account that company contributions post to as a liability. |
| `expense_ledger_account_id` | string (objectid, nullable) |  | Ledger account that company contributions post to as an expense. |
| `cost_type_id` | string (objectid, nullable) |  | Cost type that company contributions are job-costed under. |

### Company Entities (`CompanyEntityResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the company entity. |
| `legal_name` | string \| null |  | The legal name of the company entity. |
| `custom_id` | string \| null |  | A customer-provided identifier for the company entity. |
| `fein` | string \| null |  | Federal Employer Identification Number. |
| `email` | string \| null |  | Primary contact email for the company entity. |
| `phone` | string \| null |  | Primary contact phone for the company entity. |
| `address` | object |  | Primary business address. |
| `signer_name` | string \| null |  | Name of the authorized signer on payroll documents. |
| `signer_title` | string \| null |  | Title of the authorized signer on payroll documents. |
| `is_non_profit` | boolean \| null |  | Whether the company entity is registered as a non-profit. |
| `payroll_enabled` | boolean \| null |  | Whether payroll is enabled for the company entity. |
| `default_workplace_id` | string (objectid, nullable) |  | The ID of the default workplace for the company entity. Null if no valid default workplace is assigned. |
| `ledger_mapping_id` | string (objectid, nullable) |  | The ID of the ledger mapping associated with the company entity. |
| `timezone` | string \| null |  | Default IANA timezone for the company entity. |
| `workers_compensation_info` | object |  | Workers compensation policy information. |

### Cost Types (`CostTypeResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The human-readable label for the cost type. |
| `code` | string \| null |  | A short code identifying the cost type. |
| `ledger_account_id` | string (objectid, nullable) |  | The ID of the ledger account this cost type is booked to. |
| `scopes` | array<enum[timesheets,expense_management]> | yes | Where the cost type can be applied (timesheets, expense management, or both). |
| `integration_metadata_by_system` | object |  |  |

### Crews (`CrewResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the crew. |
| `lead_team_member_id` | string (objectid) | yes | The ID of the team member who leads this crew. |
| `team_member_ids` | array<string (objectid)> | yes | The IDs of team members in this crew. |
| `timesheet_policy_id` | string (objectid, nullable) |  | The ID of the timesheet policy applied to the crew. |

### Custom Earning Codes (`CustomEarningCodeResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the custom earning code. |
| `code` | string | yes | The short code identifier for this earning. |
| `earning_type` | enum | yes | The earning type classification. |
| `settings` | object | yes | Settings controlling how this earning code interacts with payroll. |
| `rate_differential_ids` | array \| null |  | Associated rate differential IDs. |
| `time_off_policy_id` | string (objectid, nullable) |  | Associated time-off policy ID, if any. |
| `eligible_team_member_groups` | array \| null |  | Team member groups eligible for this earning code. |

### Custom Tasks (`CustomTaskResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `title` | string | yes | The custom task title. |
| `description` | string \| null |  | Optional details for the custom task. |
| `onboarding_config` | object \| null |  | Configuration used when this custom task is used in onboarding checklists. |
| `offboarding_config` | object \| null |  | Configuration used when this custom task is used in offboarding checklists. |
| `due_days_from_start` | number \| null |  | Deprecated field retained for backwards compatibility. Use onboarding_config.default_due_days_from_start. |

### Customers (`CustomerResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the customer. |
| `custom_id` | string \| null |  | A customer-provided identifier. |
| `phone` | string \| null |  | The customer's phone number. |
| `status` | enum[active,inactive] |  | Whether the customer is active or inactive. |

### Daily Reports (`DailyReportResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `identifier` | number | yes | Auto-incremented daily report number, scoped to the company. |
| `status` | enum[unapproved,approved] | yes | The approval status of the daily report. |
| `job_id` | string (objectid) | yes | The job this daily report is associated with. |
| `start_date` | string | yes | The start date of the daily report (ISO date string). |
| `end_date` | string | yes | The end date of the daily report (ISO date string). |
| `supervisor_id` | string (objectid, nullable) |  | The ID of the supervising team member. |
| `creator_id` | string (objectid) | yes | The ID of the team member who created the daily report. |
| `signature_status` | enum[not_signed,partially_signed,signed] | yes | The e-signature status of the daily report. |
| `notes` | array<object> | yes | Notes attached to the daily report. |
| `work_items` | array<object> | yes | Work items recorded on the daily report. |
| `weather` | array<object> |  | Hourly weather observations for the daily report's location. |
| `timesheet_ids` | array<string (objectid)> | yes | IDs of timesheets associated with this daily report. |
| `equipment_timesheet_ids` | array<string (objectid)> | yes | IDs of equipment timesheets associated with this daily report. |
| `custom_field_values` | array<object> |  | Custom field values on the daily report. |
| `department_id` | string (objectid, nullable) |  | The department associated with this daily report. |
| `location_id` | string (objectid, nullable) |  | The location associated with this daily report. |

### Departments (`DepartmentResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the department. |
| `custom_id` | string \| null |  | A customer-provided identifier for the department. |
| `department_head_id` | string (objectid, nullable) |  | The ID of the team member who leads the department. |
| `ledger_mapping_id` | string (objectid, nullable) |  | The ID of the ledger mapping associated with the department. |
| `expense_policy_id` | string (objectid, nullable) |  | The ID of the expense policy applied to the department. |
| `reimbursement_policy_id` | string (objectid, nullable) |  | The ID of the reimbursement policy applied to the department. |
| `timesheet_policy_id` | string (objectid, nullable) |  | The ID of the timesheet policy applied to the department. |
| `time_off_request_policy_id` | string (objectid, nullable) |  | The ID of the time off request policy applied to the department. |
| `team_member_change_request_policy_id` | string (objectid, nullable) |  | The ID of the team member change request policy applied to the department. |
| `daily_report_policy_id` | string (objectid, nullable) |  | The ID of the daily report policy applied to the department. |

### Employee Benefits (`EmployeeBenefitResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes | The team member enrolled in this benefit. |
| `company_benefit_id` | string (objectid, nullable) |  | The company benefit plan this enrollment was created from, if any. |
| `benefit_type` | enum | yes | The kind of benefit plan, e.g. 125_medical, 401k, hsa. |
| `description` | string \| null |  | Free-text description of the benefit enrollment. |
| `effective_start` | date | yes | The date this benefit enrollment takes effect, as an ISO-8601 date string. |
| `effective_end` | date |  | The date this benefit enrollment ends, as an ISO-8601 date string. Null if ongoing. |
| `employee_contribution_amount` | number \| null |  | Flat amount the team member contributes each paycheck, in dollars. Null when percent-based. |
| `employee_contribution_percent` | number \| null |  | Percent of pay the team member contributes each paycheck. Null when a flat amount is used. |
| `company_contribution_amount` | number \| null |  | Flat amount the company contributes each paycheck, in dollars. Null when percent-based. |
| `company_contribution_percent` | number \| null |  | Percent of pay the company contributes each paycheck. Null when a flat amount is used. |
| `contribution_period` | string \| null |  | Set to monthly when the period amounts below are monthly totals spread across paychecks. Null when contributions are per paycheck. |
| `employee_period_amount` | number \| null |  | Monthly total the team member contributes, in dollars. Only set when contribution_period is monthly. |
| `company_period_amount` | number \| null |  | Monthly total the company contributes, in dollars. Only set when contribution_period is monthly. |
| `hsa_contribution_limit` | string \| null |  | Which IRS annual HSA limit applies. Only set for HSA benefits. |
| `per_hour_employee_contribution` | boolean \| null |  | True when the team member's flat contribution is applied per hour worked instead of per paycheck. |
| `per_hour_company_contribution` | boolean \| null |  | True when the company's flat contribution is applied per hour worked instead of per paycheck. |
| `plan_number` | string \| null |  | The plan or policy number used on reports. |
| `fringe_offset_behavior` | enum[non_bonafide,auto_offset,straight_time_offset,reg_only_offset] | yes | How company contributions offset prevailing-wage fringe obligations. |
| `overtime_multipliers` | object |  |  |
| `imputed_earning_amount` | number \| null |  | Taxable imputed earning added for this benefit, in dollars. Only applies to some insurance benefits. |
| `imputed_earning_auto_calculate` | boolean \| null |  | True when the imputed earning is derived each payroll from coverage_amount and the team member's age. |
| `coverage_amount` | number \| null |  | Total group-term life coverage, in dollars. Used to calculate the imputed earning. |
| `employee_liability_ledger_account_id` | string (objectid, nullable) |  | Ledger account that team member contributions post to. |
| `company_liability_ledger_account_id` | string (objectid, nullable) |  | Ledger account that company contributions post to as a liability. |
| `expense_ledger_account_id` | string (objectid, nullable) |  | Ledger account that company contributions post to as an expense. |
| `cost_type_id` | string (objectid, nullable) |  | Cost type that company contributions are job-costed under. |
| `contribution_limits` | array \| null |  | IRS or plan contribution limits that apply to this benefit enrollment. |
| `vendor_id` | string (objectid, nullable) |  | Vendor paid for this benefit through bill pay, if any. |

### Equipment (`EquipmentResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the equipment. |
| `notes` | string \| null |  | Optional notes for the equipment. |
| `code` | string \| null |  | The code used to identify the equipment in external systems. |
| `status` | string \| null |  | The status of the equipment. |
| `cost_rate` | number \| null |  | Cost rate in dollars per hour. |
| `company_entity_id` | string (objectid, nullable) |  | The company entity that owns this equipment. |
| `team_member_id` | string (objectid, nullable) |  | The team member this equipment is assigned to. |
| `default_cost_type_id` | string (objectid, nullable) |  | The cost type applied to this equipment's time by default. |

### Equipment Timesheets (`EquipmentTimesheetResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `equipment_id` | string (objectid) | yes | The ID of the equipment this timesheet tracks. |
| `team_member_id` | string (objectid, nullable) |  | The ID of the team member operating the equipment. |
| `timesheet_id` | string (objectid, nullable) |  | The ID of the associated labor timesheet, if any. |
| `job_id` | string (objectid, nullable) |  | The ID of the job the equipment was used on. |
| `activity_id` | string (objectid, nullable) |  | The ID of the activity the equipment was used for. |
| `work_order_id` | string (objectid, nullable) |  | The ID of the work order the equipment was used on. |
| `notes` | string \| null |  | Notes about the equipment usage. |
| `equipment_status` | string \| null |  | The operational status of the equipment during this period. |
| `quantity` | number |  | The quantity of equipment units. Defaults to 1. |
| `clock_in` | timestamp | yes | When the equipment usage started, as an ISO-8601 datetime (UTC). |
| `clock_out` | timestamp | yes | When the equipment usage ended, as an ISO-8601 datetime (UTC). |
| `hours` | number | yes | Total hours of equipment usage. |
| `date` | date |  | The date of the equipment timesheet (ISO date string). |
| `status` | enum[unapproved,approved,processing,paid] | yes | The payroll processing status. |
| `approval_status` | enum[unapproved,approved] | yes | The approval status of the equipment timesheet. |
| `custom_field_values` | array<object> |  | Custom field values on the equipment timesheet. |

### Expense Cards (`ExpenseCardResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `card_last_four` | string | yes | The last 4 digits of the card number. |
| `status` | enum[active,inactive,canceled] | yes | The status of the card. |
| `team_member_id` | string (objectid) | yes | The ID of the team member associated with the card. |
| `approver_team_member_id` | string (objectid, nullable) |  | The ID of the team member responsible for approving transactions on the card. |

### Expense Reimbursement Categories (`ExpenseReimbursementCategoryResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the category. |
| `is_default` | boolean | yes | Whether this is the company's default reimbursement category. |
| `status` | enum[active,inactive] | yes | Whether the category is available for new reimbursements. Inactive categories stay visible in settings. Defaults to `active` on create. |
| `is_taxable` | boolean \| null |  | Default taxability for reimbursements in this category. Reimbursements can override this. Only applies when the payout method is payroll. |
| `payout_method` | string \| null |  | Default payout method for reimbursements in this category. |
| `amount` | object \| null |  | Optional preset amount applied to new reimbursements in this category. |
| `mileage_rate` | number \| null |  | Optional mileage rate (in dollars per mile) for mileage reimbursements in this category. |
| `default_commute_deduction` | string \| null |  | Default commute deduction for mileage reimbursements in this category. `one_way` subtracts the one-way commute; `round_trip` subtracts double. |

### Expense Reimbursements (`ExpenseReimbursementResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes | The ID of the team member this reimbursement is for. |
| `date` | date |  | The date the expense was incurred, as an ISO-8601 date string. |
| `type` | enum[mileage,out_of_pocket,payroll_correction] | yes | The type of reimbursement. |
| `status` | enum[unapproved,pending,denied,approved,processing,paid,failed] | yes | The approval/payout status of the reimbursement. |
| `amount` | number | yes | The amount of the reimbursement (in dollars). |
| `is_taxable` | boolean | yes | Whether the reimbursement is taxable. |
| `memo` | string \| null |  | Memo describing the expense. |
| `vendor_name` | string \| null |  | The name of the vendor. |
| `tax` | number \| null |  | The tax amount included in the reimbursement (in dollars). |
| `payout_method` | enum[payroll,ach,manual] |  | How the reimbursement is paid out. |
| `approver_note` | string \| null |  | An optional note left by the approver of the reimbursement. |
| `file_ids` | array<string (objectid)> | yes | IDs of files (e.g., receipts) attached to the reimbursement. |
| `job_id` | string (objectid, nullable) |  | The ID of the job assigned to the reimbursement. |
| `activity_id` | string (objectid, nullable) |  | The ID of the activity assigned to the reimbursement. |
| `cost_type_id` | string (objectid, nullable) |  | The ID of the cost type assigned to the reimbursement. |
| `class_id` | string (objectid, nullable) |  | The ID of the class assigned to the reimbursement. |
| `location_id` | string (objectid, nullable) |  | The ID of the location assigned to the reimbursement. |
| `department_id` | string (objectid, nullable) |  | The ID of the department assigned to the reimbursement. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity assigned to the reimbursement. |
| `expense_account_id` | string (objectid, nullable) |  | The ID of the ledger account the reimbursement is booked to. |
| `expense_reimbursement_category_id` | string (objectid, nullable) |  | The ID of the expense reimbursement category. |
| `correction_payroll_id` | string (objectid, nullable) |  | If the reimbursement was generated from a payroll correction, the ID of the corrected payroll. |
| `timesheet_ids` | array<string (objectid)> |  | IDs of timesheets the reimbursement was generated from (per diem reimbursements). |
| `per_diem_rate_id` | string (objectid, nullable) |  | If this is a per diem reimbursement, the ID of the per diem rate. |
| `per_diem_rate_cadence` | enum[hourly,daily] |  | The cadence of the per diem rate (hourly or daily). |
| `per_diem_rate_amount` | number \| null |  | The per diem rate amount snapshot at the time of reimbursement. |
| `distance_traveled_to_jobsite` | number \| null |  | Distance traveled to the jobsite, in miles. |
| `mileage_detail` | object |  | Mileage details, present for `type: mileage` reimbursements. |
| `creation_method` | enum[dashboard_individual,dashboard_bulk,dashboard_duplicate,mobile_app_individual,dashboard_bulk_import,automatic_per_diem] |  | How the reimbursement was created. |
| `is_self_submitted` | boolean | yes | Whether the reimbursement was submitted by the team member themselves. |
| `custom_fields` | array<object> |  | Custom field values attached to the reimbursement. |

### Files (`FileResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string \| null |  | A readable label for the file. |
| `original_name` | string \| null |  | The original name of the file. |
| `parent_id` | string |  | The ID of the parent object the file is associated with. |
| `parent_type` | enum |  | The type of the parent entity the file is associated with. |
| `mime_type` | string \| null |  | The MIME type of the file. |
| `sensitive` | boolean |  | Whether the file is sensitive. Only applicable to team member documents. |
| `content_base64` | string | yes | The base64 encoded content of the file. |

### Fillable Templates (`FillableTemplateResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The display name of the fillable template. A fillable template defines mappings and checklist configuration on top of file records. |
| `original_file_id` | string (objectid) | yes | The `/api/v2/files` ID of the original source document this template is based on (for example, the uploaded base PDF). |
| `fillable_file_id` | string (objectid) | yes | The `/api/v2/files` ID of the generated fillable document created from the original source file. This is the file record used when rendering or assigning the fillable version. |
| `onboarding_config` | object \| null |  | Optional onboarding configuration for where this template is used. |

### Form Submissions (`FormSubmissionResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes | The submission ID. |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `form_id` | string (objectid) |  | The ID of the form that the submission is tied to. |
| `status` | string \| null |  | The status of the submission. |
| `team_member_id` | string (objectid) |  | The ID of the team member who filled out the submission. |
| `answers` | array<object> | yes | The answers to the form. |
| `completed_at` | timestamp |  | The timestamp when the submission was completed. |

### Form Templates (`FormTemplateResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the form template. |
| `form_id` | string (objectid, nullable) |  | The ID of the form used by this template. |
| `module` | enum[performance,recruiting,safety] | yes | The module this template belongs to. |

### Forms (`FormResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `parent_id` | string (objectid) | yes | The ID of the parent object the form is connected to. |
| `parent_type` | enum | yes | The type of the parent object (e.g. company, job, performance_review_cycle, writeup_template). |
| `miter_module` | string \| null |  | The Miter module the form is connected to (e.g. performance, recruiting). |
| `name` | string | yes | The name of the form. |
| `description` | string \| null |  | A short description of the form. |
| `components` | array<object> | yes | The form components (sections and fields) that define the form structure. |
| `sensitive` | boolean \| null |  | Whether the form is marked as sensitive. |

### Holiday Schedules (`HolidayScheduleResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `title` | string | yes | The name of the holiday schedule. |
| `is_default` | boolean | yes | Whether this is the company's default holiday schedule. |
| `custom_holidays` | array<object> | yes | Custom holidays defined on the schedule. |
| `enabled_predefined_holidays` | array<object> | yes | Predefined holidays enabled on the schedule. |
| `fringe_offset_hours_per_year` | number \| null |  | Annual fringe offset hours. |
| `fringe_offset_behavior` | enum[non_bonafide,auto_offset,straight_time_offset,reg_only_offset] | yes | How fringe offset hours are applied. |
| `min_tenure` | number \| null |  | Minimum tenure in days before a team member qualifies for the schedule. |

### Integration Sync Items (`IntegrationSyncResultResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `integration_sync_id` | string (objectid) | yes | The integration sync this result belongs to. |
| `label` | string \| null |  | Optional label (e.g. job name, team member name). |
| `status` | enum[success,error,warning,skipped] | yes | Result status. |
| `message` | string \| null |  | Optional message (e.g. error or warning details). |
| `item_id` | string | yes | Maps to external ID or internal Miter ID, depending on whether this is a pull or a push. |

### Integration Syncs (`IntegrationSyncResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `integration_key` | enum | yes | The integration type (e.g. service_titan, qbo). |
| `company_entity_id` | string \| null |  | Reserved for future use; always undefined. |
| `status` | enum[success,error,warning,skipped,pending] | yes | Sync status. |
| `entity` | enum | yes | The entity being synced (e.g. jobs, team_members). |
| `direction` | enum[pull,push] | yes | Whether the sync is push or pull. |
| `trigger` | enum[manual,automatic,scheduled,daily] | yes | What triggered the sync. Exposed as 'scheduled' for legacy 'daily' triggers. |
| `error_message` | string \| null |  | Error message when status is error or warning. |

### Job Postings (`JobPostingResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `title` | string | yes | The job posting title. |
| `description` | string | yes | The job posting description. |
| `custom_id` | TBD: untyped in spec | yes | A customer-provided requisition identifier. |
| `pay` | object \| null |  | Pay range configuration. |
| `workplace` | object | yes | Workplace configuration. |
| `min_years_of_experience` | number \| null |  | Minimum years of experience required. |
| `employment_type` | enum[full_time,part_time,contract,intern] | yes | Employment type. |
| `question_form_id` | string (objectid, nullable) |  | The ID of the question form. |
| `question_form_template_id` | string (objectid, nullable) |  | The ID of the question form template. |
| `require_resume` | boolean \| null |  | Whether a resume is required. |
| `status` | enum[active,inactive] | yes | The posting status. |
| `interest_form` | boolean | yes | Whether this is an interest form. |
| `hiring_team` | array \| null |  | Hiring team member groups. |
| `hiring_manager_team_member_id` | string (objectid, nullable) |  | The hiring manager's team member ID. |

### Jobs (`JobResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the job. |
| `parent_job_id` | string (objectid, nullable) |  | The ID of the parent job, if this job is a subjob. |
| `location_id` | string (objectid, nullable) |  | The ID of the location associated with the job. |
| `description` | string \| null |  | The description of the job. |
| `start_date` | date |  | The job's start date, as a YYYY-MM-DD date. |
| `status` | enum[active,inactive] | yes | The status of the job. |
| `is_ocip` | boolean |  | Whether the job is an OCIP job. |
| `has_custom_activities` | boolean |  | Whether the job has custom activities. |
| `activity_ids` | array<string (objectid)> |  | IDs of the activities available for use on this job (its selectable activities). Providing this list enables custom activities on the job and replaces the job's current activities in full, rather... |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity associated with the job. |
| `department_id` | string (objectid, nullable) |  | The ID of the department associated with the job. |
| `class_id` | string (objectid, nullable) |  | The ID of the class associated with the job. |
| `supervisor_team_member_ids` | array<string (objectid)> |  | Team member IDs for supervisors assigned to this job. |
| `superintendent_team_member_ids` | array<string (objectid)> |  | Team member IDs for superintendents assigned to this job. |
| `project_manager_team_member_ids` | array<string (objectid)> |  | Team member IDs for project managers assigned to this job. |
| `certified_payroll_report_info` | object \| null |  | Present if the job is elgible for CPR inclusion. |
| `geo_fence_override_settings` | object |  | Geofence override behavior for this job. Use 'radius' to set a custom radius, 'fence' for a polygon boundary, or 'ignore' to disable geofence checks entirely. |
| `custom_id` | string | yes | The job's unique customizable ID, used to identify the job in external systems (called "code" in Miter). |
| `address` | object |  | The address of the job. |
| `pay_rate_group_id` | string (objectid, nullable) |  | The ID of the pay rate group assigned to the job. Only set when the job uses a single pay rate group; null when the job selects pay rate groups by trade, uses all of them, or has none. |
| `custom_field_values` | array<object> |  | Custom field values on the job. |
| `integration_metadata_by_system` | object |  |  |

### Leave Types (`LeaveTypeResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The display label for this leave type. |
| `config` | object | yes | Configuration for how this leave type affects payroll, notifications, and time-off policies. |

### Ledger Accounts (`LedgerAccountResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `custom_id` | string | yes | An optional identifier used to reference this account in external systems. |
| `label` | string | yes | The display label for the ledger account. |
| `classification` | enum[Asset,Equity,Expense,Liability,Revenue,NonPosting,Unknown] | yes | The accounting classification of the ledger account. Defaults to `Unknown` on create. |
| `parent_account_id` | string (objectid) | yes | The id of the parent ledger account, if this account is a child of another. |
| `status` | enum[active,inactive] | yes | Whether the ledger account is active. Defaults to `active` on create. |
| `is_selectable_by_team_members` | boolean | yes | Whether team members can select this account when categorizing transactions. Defaults to `true` on create. |

### Ledger Entries → Ledger Line Items (`LedgerEntryLineItemResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `ledger_entry_id` | string (objectid) | yes | The ID of the parent ledger entry. |
| `account_type` | enum[income,expense,asset,liability,equity] | yes | The account type classification for this line item. |
| `miter_type` | enum | yes | The Miter-specific categorization of this line item. |
| `direction` | enum[credit,debit] | yes | Whether this line item is a credit or debit. |
| `amount` | number | yes | The monetary amount of the line item. |
| `ledger_account_id` | string (objectid, nullable) |  | The ID of the ledger account this line item is mapped to. |
| `description` | string \| null |  | Human-readable description of the line item. |
| `payroll_id` | string (objectid, nullable) |  | The ID of the payroll associated with this line item. |
| `voided_payroll_id` | string (objectid, nullable) |  | The ID of the voided payroll associated with this line item. |
| `payday` | date |  | The pay date associated with this line item (YYYY-MM-DD). |
| `team_member_id` | string (objectid, nullable) |  | The ID of the team member associated with this line item. |
| `employment_type` | string \| null |  | The employment type of the team member for this line item. |
| `department_id` | string (objectid, nullable) |  | The ID of the department associated with this line item. |
| `location_id` | string (objectid, nullable) |  | The ID of the location associated with this line item. |
| `class_id` | string (objectid, nullable) |  | The ID of the class associated with this line item. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity associated with this line item. |
| `job_id` | string (objectid, nullable) |  | The ID of the job associated with this line item. |
| `activity_id` | string (objectid, nullable) |  | The ID of the activity associated with this line item. |
| `work_order_id` | string (objectid, nullable) |  | The ID of the work order associated with this line item. |
| `workers_compensation_code_id` | string (objectid, nullable) |  | The ID of the workers' compensation code associated with this line item. |
| `timesheet_id` | string (objectid, nullable) |  | The ID of the timesheet associated with this line item. |
| `equipment_timesheet_id` | string (objectid, nullable) |  | The ID of the equipment timesheet associated with this line item. |
| `equipment_id` | string (objectid, nullable) |  | The ID of the equipment associated with this line item. |
| `reimbursement_id` | string (objectid, nullable) |  | The ID of the reimbursement associated with this line item. |
| `reimbursement_date` | date |  | The date of the reimbursement (YYYY-MM-DD). |
| `accrual_date` | date |  | The accrual date for this line item (YYYY-MM-DD). |
| `classification_id` | string (objectid, nullable) |  | The ID of the classification associated with this line item. |
| `pay_rate_group_id` | string (objectid, nullable) |  | The ID of the pay rate group associated with this line item. |
| `fringe_classification_id` | string (objectid, nullable) |  | The ID of the fringe classification associated with this line item. |
| `fringe_pay_rate_group_id` | string (objectid, nullable) |  | The ID of the fringe pay rate group associated with this line item. |
| `burden_rate_id` | string (objectid, nullable) |  | The ID of the burden rate associated with this line item. |
| `earning_type` | string \| null |  | The type of earning (e.g., regular, overtime, bonus). |
| `earning_date` | date |  | The date the earning was accrued (YYYY-MM-DD). |
| `benefit_type` | string \| null |  | The type of benefit (e.g., 401k, hsa, 125_medical). |
| `hours` | number \| null |  | The number of hours associated with this line item. |
| `void` | boolean \| null |  | Whether this line item is associated with a voided entry. |
| `memo` | string \| null |  | A memo or note attached to this line item. |
| `cost_type_id` | string (objectid, nullable) |  | The ID of the cost type associated with this line item. |
| `custom_earning_code_id` | string (objectid, nullable) |  | The ID of the custom earning code associated with this line item. |
| `custom_field_values` | array<object> |  | Custom field values assigned to this line item. |
| `recoded` | boolean \| null |  | Whether this line item has been recoded. |
| `manually_edited` | boolean \| null |  | Whether this line item has been manually edited. |

### Ledger Entries (`LedgerEntryResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `ledger_id` | string (objectid) | yes | The ID of the ledger this entry belongs to. |
| `entry_type` | enum | yes | The type of event this ledger entry records. |
| `posted_at` | timestamp | yes | When the ledger entry was posted, as an ISO-8601 datetime (UTC). |
| `description` | string | yes | Human-readable description of the ledger entry. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity this ledger entry is associated with. |
| `source_objects` | object | yes | References to the Miter objects that generated this ledger entry. |

### Ledger Mappings (`LedgerMappingResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | Human-readable name for the ledger mapping. |
| `is_company_default` | boolean | yes | Whether this mapping is the company-wide default. |
| `defaults` | object |  | Baseline ledger account IDs keyed by ledger line type (e.g., `cash`, `employee_earnings`, `benefit_liabilities`). Each value is the GL account this mapping writes to for that line type when no... |
| `earning_type_accounts` | object |  | Per-earning-type ledger account ID overrides. Keys are built-in earning type codes (e.g., `regular`, `overtime`) or customer-defined custom earning type codes. Overrides `defaults.employee_earnings`... |
| `benefit_type_expense_accounts` | object |  | Per-benefit-type ledger account ID overrides for **employer expense** entries (overrides `defaults.employer_benefit_contributions`). |
| `benefit_type_liability_accounts` | object |  | Per-benefit-type ledger account ID overrides for **liability** entries (overrides `defaults.benefit_liabilities`). |

### Locations (`LocationResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string \| null |  | The name of the location. |
| `status` | string \| null |  | Whether the location is active or inactive. |
| `custom_id` | string \| null |  | A customer-provided identifier for the location. |
| `parent_location_id` | string (objectid, nullable) |  | The ID of the parent location, if this location is nested under another. |
| `supervisor_ids` | array<string (objectid)> |  | IDs of team members supervising the location. |
| `superintendent_ids` | array<string (objectid)> |  | IDs of team members serving as superintendents of the location. |
| `project_manager_ids` | array<string (objectid)> |  | IDs of team members serving as project managers of the location. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity the location belongs to. |
| `ledger_mapping_id` | string (objectid, nullable) |  | The ID of the ledger mapping associated with the location. |
| `expense_policy_id` | string (objectid, nullable) |  | The ID of the expense policy applied to the location. |
| `reimbursement_policy_id` | string (objectid, nullable) |  | The ID of the reimbursement policy applied to the location. |
| `timesheet_policy_id` | string (objectid, nullable) |  | The ID of the timesheet policy applied to the location. |
| `time_off_request_policy_id` | string (objectid, nullable) |  | The ID of the time off request policy applied to the location. |
| `team_member_change_request_policy_id` | string (objectid, nullable) |  | The ID of the team member change request policy applied to the location. |
| `daily_report_policy_id` | string (objectid, nullable) |  | The ID of the daily report policy applied to the location. |

### Message Templates (`MessageTemplateResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of the message template. |
| `module` | enum[recruiting,team] | yes | The module this template belongs to. |
| `raw_html` | string | yes | The raw HTML content of the template. |
| `smart_fields` | array<enum[candidate_first_name,candidate_last_name,sender_first_name,sender_last_name,job_posting_title]> | yes | Smart field placeholders used in this template. |

### Notes (`NoteResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `parent_id` | string (objectid) | yes | The ID of the parent record this note is attached to. |
| `parent_type` | enum[team_member,file,job_application,payroll,timesheet_group] | yes | The kind of record this note is attached to. |
| `content` | string | yes | The note text. |
| `author_name` | string | yes | Display name of the user who authored the note. |
| `author_user_id` | string (objectid) | yes | The ID of the user who authored the note. |

### Team Member Onboarding Checklists (`OnboardingChecklistResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string | yes | The ID of the team member this checklist belongs to. |
| `completed_at` | timestamp \| null | yes | The date and time the checklist was completed, or null if not yet completed. |
| `tasks` | array<object> | yes | The list of onboarding tasks in this checklist. |

### Overtime Rules (`OvertimeRuleResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | Human-readable label for the overtime rule. |
| `precedence` | number | yes | Ordering used to determine which rule applies when multiple match. |
| `timezone` | string | yes | IANA timezone the rule's thresholds are evaluated in. |
| `items` | array<object> | yes | Per-day-of-week threshold configurations. |
| `weekly_overtime_threshold` | number |  | Weekly hours above which hours are classified as overtime. |
| `weekly_double_overtime_threshold` | number \| null |  | Weekly hours above which hours are classified as double overtime. |
| `prevent_time_type_downgrades` | boolean \| null |  | When true, no threshold may lower a team member's time type during a day; once hours reach `overtime` or `double_overtime` classification, they cannot be reclassified to a lower tier. Because... |
| `notes` | string \| null |  | Free-form notes about the rule. |

### Pay Rate Groups (`PayRateGroupResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The human-readable label for the pay rate group. |
| `custom_id` | string \| null |  | A customer-provided identifier for the pay rate group. |
| `trade_id` | string (objectid, nullable) |  | The ID of the trade associated with the pay rate group. |
| `holiday_schedule_id` | string (objectid, nullable) |  | The ID of the holiday schedule applied to the pay rate group. |
| `cpr_wage_determination_no` | string \| null |  | The CPR (Certified Payroll Report) wage determination number for WH-347. |
| `current_pay_rate_group_version_id` | string (objectid) | yes | The ID of the pay rate group version that is currently effective. |

### Pay Rate Groups → Classifications (`ClassificationResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The human-readable label for the classification (e.g. trade or work title). |
| `pay_rate_group_id` | string (objectid) | yes | The ID of the pay rate group this classification belongs to. |
| `pay_rate_group_version_id` | string (objectid) | yes | The ID of the pay rate group version this classification belongs to. |
| `standard_classification_id` | string (objectid, nullable) |  | The ID of the standard classification this classification maps to. |
| `effective_at` | date | yes | The date this classification becomes effective, as an ISO-8601 date string. |
| `custom_id` | string \| null |  | A customer-provided identifier for the classification. |
| `base_rates` | object | yes | The hourly base rates for the classification. |
| `fringe_rates` | object |  | The hourly fringe rates for the classification, if configured. |
| `contributions` | array<object> | yes | The employer contribution lines that make up the classification's fringe package (e.g. health & welfare, pension, cash-in-lieu). Mirrors the Contributions section shown in the dashboard. |
| `deductions` | array<object> | yes | The fringe deduction lines withheld from the worker (e.g. union dues, benefit deductions). Mirrors the Deductions section shown in the dashboard. |
| `taxable_earnings_in_percent_fringe_deductions` | array \| null |  | Taxable earning types included in this classification's %-based fringe deduction base. Set to null to inherit the company default. |

### Pay Rate Versions (`PayRateVersionResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes | The team member id for this pay rate. |
| `pay_type` | enum[salary,hourly] | yes | Whether this is a hourly or salary pay rate. |
| `pay_rate` | number | yes | The pay rate. |
| `salary_rate_display` | string \| null |  | Display preference for salary rates; pay_rate is annualized regardless. Null for hourly. |
| `notes` | string \| null |  | Free-form admin note on the version. |
| `changed_at` | number \| null |  | When this change was recorded timestamp in epoch seconds. |
| `effective_at` | date | yes | When this change was effective in ISO date string format (e.g. 2026-04-01). |

### Pay Schedules (`PayScheduleResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `company_entity_id` | string (objectid) | yes | The ID of the company entity this pay schedule belongs to. |
| `label` | string | yes | The label of the pay schedule. |
| `pay_frequency` | enum[weekly,biweekly,semimonthly,monthly,quarterly,annually] | yes | How often the schedule pays out. |
| `first_payday` | date | yes | An anchor payday for the schedule, as an ISO-8601 date string. |
| `first_period_end` | date | yes | The end of the pay period associated with the anchor payday, as an ISO-8601 date string. |
| `second_payday` | date |  | For semimonthly schedules, the second anchor payday in the month, as an ISO-8601 date string. |
| `workweek_end_day` | integer | yes | The day of the week the workweek ends on (1 = Monday, 7 = Sunday). |
| `is_company_entity_default` | boolean | yes | Whether this is the default pay schedule for the company entity. |
| `status` | enum[active,inactive] | yes | Whether the pay schedule is active or inactive. |
| `bank_account_id` | string (objectid, nullable) |  | The ID of the bank account funding payrolls on this schedule. |

### Payroll Payments (`PayrollPaymentResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `payroll_id` | string (objectid) | yes | The ID of the payroll run this payment belongs to. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity that paid this payment. Null on old payments the multi-entity backfill could not map to an entity. |
| `pay_schedule_id` | string (objectid, nullable) |  | The ID of the pay schedule the payroll ran on. Null for off-cycle payrolls. |
| `team_member_id` | string (objectid) | yes | The ID of the team member who was paid. |
| `payment_type` | enum[employee,contractor] | yes | Whether the team member was paid as an employee (taxes withheld) or as a contractor (gross, no withholding). |
| `payroll_type` | enum[regular,off_cycle,amendment,third_party_sick_pay,balancing,historical] | yes | The type of payroll this payment rode on. `historical` payments record pay from before the company moved to Miter. |
| `status` | enum[draft,pending,processing,paid,partially_paid,failed] | yes | Where the payment is in its lifecycle, mirroring its payroll. `paid` means the money went out. |
| `pay_frequency` | enum[weekly,biweekly,semimonthly,monthly,quarterly,annually] | yes | How often the payroll's pay schedule pays out. |
| `period_start` | date | yes | The first day of the pay period the payment covers. |
| `period_end` | date | yes | The last day of the pay period the payment covers. |
| `payday` | date | yes | The date the team member was paid. |
| `payment_method` | string \| null |  | How the payment was delivered. |
| `payment_reference` | string \| null |  | A short Miter-generated identifier for this payment. Appears on certified payroll reports and as the check voucher number in accounting exports. |
| `paper_check_number` | string \| null |  | The paper check number, when the payment was delivered by paper check. |
| `gross_pay` | number \| null |  | Total taxable and non-taxable earnings before deductions, excluding imputed earnings and reimbursements. |
| `net_pay` | number \| null |  | Take-home pay after taxes, benefits, and deductions. Null until the payroll has been calculated. |
| `reimbursement_total` | number \| null |  | Total reimbursements paid on this payment. Reimbursements are not taxed. |
| `is_void` | boolean | yes | Whether this payment is the reversing entry that voids another payment, rather than an original payment. |
| `voided` | boolean | yes | Whether this payment was voided. The reversing entry is a separate payment with `is_void` set to true. |
| `void_requested` | boolean | yes | Whether a void was requested for this payment but has not finished processing. |
| `ach_reversal_reason` | string \| null |  | Why the direct deposit for this payment was reversed. |
| `corrected_by_payment_id` | string (objectid, nullable) |  | The ID of the payment that replaced this one after it was voided. Null when this payment was not corrected. |
| `paid_time_off_balance_hours` | number \| null |  | The team member's paid time off balance after this payment was applied. |
| `sick_balance_hours` | number \| null |  | The team member's sick time balance after this payment was applied. |
| `earnings` | array<object> | yes | The earning lines that make up this payment's gross pay. |
| `reimbursements` | array<object> | yes | The reimbursement lines on this payment. |
| `taxes` | array<object> | yes | The tax lines on this payment, both employee-withheld and employer-paid. Empty for contractor payments and until the payroll has been calculated. |
| `benefits` | array<object> | yes | The benefit contributions on this payment. Empty for contractor payments. |
| `post_tax_deductions` | array<object> | yes | The post-tax deduction lines on this payment. Empty for contractor payments. |
| `time_off_logs` | array<object> | yes | Time off accrued, used, and paid out on this payment, broken out by policy. |
| `warnings` | array<object> | yes | Conditions on the payment that need attention. Empty when there is nothing to flag. |
| `refunds` | array<object> | yes | Direct deposits on this payment that were returned undelivered. |
| `timesheet_ids` | array<string (objectid)> |  | The IDs of the timesheets whose hours feed this payment's earnings. |
| `expense_reimbursement_ids` | array<string (objectid)> |  | The IDs of the expense reimbursements paid on this payment. |
| `time_off_request_ids` | array<string (objectid)> |  | The IDs of the time off requests paid on this payment. |

### Payrolls (`PayrollResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `company_entity_id` | string (objectid) | yes | The ID of the company entity the payroll was run for. |
| `type` | enum[regular,off_cycle,amendment,third_party_sick_pay,balancing,historical] | yes | The type of payroll. `historical` payrolls record pay that happened before the company moved to Miter. |
| `status` | enum[draft,pending,processing,paid,partially_paid,failed] | yes | Where the payroll is in its lifecycle. |
| `label` | string \| null |  | An optional label describing the payroll. |
| `pay_schedule_id` | string (objectid, nullable) |  | The ID of the pay schedule the payroll was run on. Null for off-cycle payrolls. |
| `period_start` | date | yes | The first day of the pay period the payroll covers. |
| `period_end` | date | yes | The last day of the pay period the payroll covers. |
| `payday` | date | yes | The date employees and contractors are paid. |
| `pay_frequency` | enum[weekly,biweekly,semimonthly,monthly,quarterly,annually] | yes | How often the payroll's pay schedule pays out. |
| `processing_period` | enum[one_day,two_day,three_day,four_day] | yes | How many business days before payday the payroll must be approved. |
| `funding_payment_method` | string \| null |  | How the payroll is funded. |
| `approval_deadline` | timestamp |  | The deadline for approving the payroll so it funds on time. |
| `approved_at` | timestamp |  | When the payroll was approved. Null until it is approved. |
| `reopen_deadline` | timestamp |  | The deadline for reopening an approved payroll to make changes. |
| `first_workweek_start` | date |  | The first day of the first workweek in the pay period, which can precede `period_start` when a workweek straddles two periods. |
| `is_void` | boolean | yes | Whether this payroll is a void that reverses another payroll. This is the reversing payroll, not the one that was reversed; the payroll it reverses is `voided_payroll_id`. |
| `voided_payroll_id` | string (objectid, nullable) |  | For a void payroll, the ID of the payroll it reverses. To find out whether a given payroll was itself reversed, list payrolls filtered by `voided_payroll_id` set to that payroll's ID. |
| `corrected_payroll_id` | string (objectid, nullable) |  | For a corrective off-cycle payroll, the ID of the payroll it corrects. |
| `correction_completed` | boolean \| null |  | For a corrective off-cycle payroll, whether the correction has been finished. Null on payrolls that aren't corrections. |
| `bank_account_id` | string (objectid, nullable) |  | The ID of the bank account debited to fund the payroll. |
| `is_manually_locked` | boolean | yes | Whether the payroll has been locked, which prevents further changes to it. |
| `is_fully_manual` | boolean | yes | Whether every earning on the payroll was entered by hand rather than pulled from timesheets. |
| `has_ever_failed` | boolean | yes | Whether the payroll has ever been in a failed status, even if it has since succeeded. |
| `payday_notification_sent` | boolean | yes | Whether the payday notification has been sent to the team members on the payroll. |
| `payday_notifications_enabled` | boolean \| null |  | Whether payday notifications are turned on for this payroll. |
| `time_off_balances_updated` | boolean | yes | Whether time off balances have been updated to reflect the time off paid on the payroll. |
| `warnings` | array<object> |  | Conditions on the payroll that need attention. Empty when there is nothing to flag. |
| `off_cycle_options` | object |  | Options that apply only to off-cycle payrolls. Null on every other payroll type. |
| `inclusion_options` | object |  | Which optional earnings were pulled into the payroll when it was generated. |
| `totals` | object |  | Monetary totals for the payroll. Null until the payroll has been calculated. |
| `timesheet_ids` | array<string (objectid)> |  | The IDs of the timesheets paid on this payroll. |
| `expense_reimbursement_ids` | array<string (objectid)> |  | The IDs of the expense reimbursements paid on this payroll. |
| `time_off_request_ids` | array<string (objectid)> |  | The IDs of the time off requests paid on this payroll. |

### Policies (`PolicyResponse`)
_Polymorphic response — union of all variant fields shown._

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | Human-readable name of the policy. |
| `type` | string | yes |  |
| `rules` | array<object> | yes | Approval rules for expense submissions. |
| `config` | object \| null |  |  |
| `is_workflow_schema` | boolean |  |  |
| `approval_rules` | array<object> |  | Approval rules for the workflow-schema timesheet policy. |
| `field_rules` | array<object> |  | Field visibility rules for the workflow-schema timesheet policy. |
| `break_policy_id` | string (objectid, nullable) |  |  |

### Position Templates (`PositionTemplateResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `title` | string | yes | The title of the position template. |
| `description` | string \| null |  | A description of the position. |
| `team_member_fields` | array<object> | yes | Configured team member fields for this position. |
| `custom_fields` | array \| null |  | Configured custom fields for this position. |

### Post Tax Deductions (`PostTaxDeductionResponse`)
_Polymorphic response — union of all variant fields shown._

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes | The ID of the team member this deduction applies to. |
| `description` | string | yes | Free-text description of the deduction. |
| `effective_start` | date | yes | The date this deduction takes effect, as an ISO-8601 date string. |
| `effective_end` | date |  | The date this deduction ends, as an ISO-8601 date string. Null if ongoing. |
| `is_401k_loan` | boolean | yes | Whether this deduction repays a 401(k) loan. |
| `deduction_period` | string \| null |  | Monthly when period_amount is a monthly total spread across paychecks; null when the deduction applies per paycheck. |
| `period_amount` | number \| null |  | The monthly deduction amount, when deduction_period is monthly. |
| `ledger_account_id` | string (objectid, nullable) |  | The ID of the ledger account this deduction posts to. |
| `vendor_id` | string (objectid, nullable) |  | Set when this deduction is paid out to a vendor through bill pay. |
| `correction_payroll_id` | string (objectid, nullable) |  | Set when the deduction was generated automatically to recover an overpayment from a payroll correction. |
| `deduction_type` | string | yes |  |
| `miscellaneous` | object |  | Deduction details specific to a miscellaneous post-tax deduction. |
| `child_support` | object |  | Deduction details specific to a child support post-tax deduction. |
| `miscellaneous_garnishment` | object |  | Deduction details specific to a miscellaneous garnishment post-tax deduction. |

### Quantity Logs (`QuantityLogResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `status` | enum[unapproved,approved] | yes | The status of the quantity log. |
| `quantity` | number | yes | The quantity produced |
| `date` | date | yes | The date of the quantity log. |
| `job_id` | string (objectid) | yes | The ID of the job. |
| `activity_id` | string (objectid) | yes | The ID of the activity. |
| `unit_of_measure` | string \| null | yes | The unit of measure for the quantity log, derived from the latest production budget line item for the job and activity pair. Cost budget line items are never used. Null when no production budget line... |
| `notes` | string \| null |  | Optional notes attached to the quantity log. |
| `team_member_id` | string (objectid, nullable) |  | The ID of the team member who installed the quantities. |
| `timesheet_id` | string (objectid, nullable) |  | The ID of the timesheet the quantity log is associated with. |
| `daily_report_id` | string (objectid, nullable) |  | The ID of the daily report the quantity log is associated with. |
| `location_id` | string (objectid, nullable) |  | The ID of the location the quantity log is associated with. |
| `department_id` | string (objectid, nullable) |  | The ID of the department the quantity log is associated with. |
| `class_id` | string (objectid, nullable) |  | The ID of the class the quantity log is associated with. |
| `cost_type_id` | string (objectid, nullable) |  | The ID of the cost type the quantity log is associated with. |
| `material_id` | string (objectid, nullable) |  | The ID of the material installed. |

### Rate Differentials (`RateDifferentialResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | The display label for this rate differential. |
| `type` | enum[percentage,dollar] | yes | The type of rate differential: percentage or dollar amount. |
| `value` | number | yes | The differential value (percentage or dollar amount). |
| `create_separate_earning` | boolean | yes | Whether to create a separate earning line for this differential. |
| `overtime_multipliers` | object \| null |  | Overtime multiplier overrides. |
| `include_taxable_fringes` | boolean \| null |  | Whether to include taxable fringes in the percentage calculation. |
| `triggers` | array \| null |  | Triggers that apply this differential. |

### Standard Classifications (`StandardClassificationResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string \| null |  | The human-readable label for the standard classification. |

### Tax Filings (`TaxFilingResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `company_entity_id` | string (objectid) | yes | The ID of the company entity the filing is made for. |
| `label` | string | yes | Display name of the filing. |
| `year` | number | yes | The tax year the filing covers. |
| `period` | enum | yes | The period within the tax year the filing covers. |
| `period_start` | date | yes | The first day of the period the filing covers. |
| `period_end` | date | yes | The last day of the period the filing covers. |
| `jurisdiction` | string \| null |  | The region the filing is made to: `fed`, or a lowercase two-letter US state code. Null when none is recorded. |
| `status` | enum[pending,submitted,filed,blocked] | yes | Where the filing is in its lifecycle. |
| `due_at` | date |  | The date the filing is due to the agency. Omitted when the agency sets no deadline. |
| `filed_at` | timestamp |  | When the filing was submitted to the agency. Omitted until it is filed. |
| `closed_at` | timestamp |  | When the filing closed for on-time processing. Omitted while it is still open. |
| `filing_attempts` | number \| null |  | How many times the filing has been submitted to the agency. |
| `amends_tax_filing_ids` | array<string (objectid)> | yes | The IDs of the tax filings this filing amends. Empty unless this filing is itself an amendment. |
| `amended_by_tax_filing_ids` | array<string (objectid)> | yes | The IDs of the tax filings that amend this one. Empty when it has not been amended. |
| `blocked_reasons` | array \| null |  | Why the filing is blocked, and how to resolve it. Null when the filing is not blocked. |
| `support_requested` | boolean | yes | Whether the company has asked Miter for help with this filing. |

### Team Members (`TeamMemberResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `full_name` | string | yes | The team member's full name. |
| `custom_id` | string | yes | The team member's unique customizable ID, used to identify the team member in external systems (sometimes called "friendly ID" in Miter). |
| `employment_status` | string | yes | The team member's employment status. |
| `first_name` | string | yes | The team member's first name. |
| `middle_name` | string \| null |  | The team member's middle name. |
| `preferred_name` | string \| null |  | The team member's preferred name. |
| `last_name` | string | yes | The team member's last name. |
| `work_email` | string \| null |  | The team member's email address. |
| `personal_email` | string \| null |  | The team member's personal email address. |
| `work_phone` | string \| null |  | The team member's work phone number. |
| `sms_phone_preference` | enum[personal,work] |  | Which phone number text messages are sent to. If the team member only has one phone number, that one will be used regardless of the preference. |
| `date_of_birth` | date |  | The team member's date of birth (ISO date string). |
| `personal_phone` | string \| null |  | The team member's personal phone number. |
| `company_entity_id` | string (objectid) | yes | The ID of the company entity the team member belongs to. |
| `employment_type` | enum[employee,contractor] | yes | Whether the team member is an employee or contractor. |
| `employment_category` | string \| null |  | Whether the team member is full-time or part-time. |
| `employment_term` | string \| null |  | Whether the team member is temporary, seasonal, or permanent. |
| `title` | string \| null |  | The team member's job title. |
| `start_date` | date |  | The team member's start date (ISO date string). |
| `end_date` | date |  | The team member's end date if terminated (ISO date string). |
| `original_start_date` | date |  | The team member's original start date (ISO date string). |
| `termination_date` | date |  | The team member's termination date if terminated (ISO date string). |
| `standard_classification_id` | string (objectid, nullable) |  | The ID of the team member's effective standard classification: the classification mapped to the team member's default pay rate group (`pay_rate_group_standard_classifications[pay_rate_group_id]`),... |
| `pay_rate_group_id` | string (objectid, nullable) |  | The ID of the team member's pay rate group. |
| `time_off_request_policy_id` | string (objectid, nullable) |  | The ID of the time off request policy applied to this team member. |
| `default_job_id` | string (objectid, nullable) |  | The default job ID for this team member. |
| `default_activity_id` | string (objectid, nullable) |  | The default activity ID for this team member. |
| `default_cost_type_id` | string (objectid, nullable) |  | The default cost type ID for this team member. |
| `default_overtime_rule_id` | string (objectid, nullable) |  | The default overtime rule ID for this team member. |
| `default_trade_id` | string (objectid, nullable) |  | The default trade ID for this team member. |
| `department_id` | string (objectid, nullable) |  | The ID of the department the team member belongs to. |
| `location_id` | string (objectid, nullable) |  | The ID of the location the team member belongs to. |
| `class_id` | string (objectid, nullable) |  | The ID of the class the team member belongs to. |
| `workers_compensation_code_id` | string (objectid, nullable) |  | The ID of the workers' compensation code assigned to this team member. |
| `holiday_schedule_id` | string (objectid, nullable) |  | The ID of the holiday schedule applied to this team member. |
| `pay_schedule_id` | string (objectid) | yes | The ID of the pay schedule the team member is paid on. |
| `emergency_contacts` | array \| null |  | The team member's emergency contacts. |
| `overtime_exempt` | boolean \| null |  | Whether the team member is exempt from overtime. |
| `demographics` | object \| null |  | The team member's demographic information. |
| `reports_to_id` | string (objectid, nullable) |  | The team member ID of this team member's direct manager. |
| `primary_workplace_id` | string (objectid) | yes | The ID of the team member's primary workplace. |
| `additional_workplace_ids` | array<string (objectid)> |  | IDs of any additional workplaces the team member is assigned to (beyond their primary workplace). |
| `benefits_eligibility_status` | string \| null |  | The team member's benefits eligibility status. |
| `termination_reason` | object |  | The system code (or custom termination reason ID) for the team member's most recent dismissal. |
| `termination_note` | string |  | A custom note added to the team member's most recent dismissal. |
| `eligible_for_rehire` | enum[eligible,ineligible,needs_review] |  | Whether the team member is eligible for rehire. |
| `address` | object |  | The team member's residential address. |
| `mailing_address` | object |  | The team member's mailing address (if different from residential). |
| `pay_rate_group_standard_classifications` | object |  | Read-only map of standard classification IDs keyed by pay rate group ID, covering every pay rate group the team member has been mapped under (including groups they are no longer paid under). To... |
| `custom_field_values` | array \| null |  | The team member's custom field values. |
| `enrolled_in_payroll` | boolean | yes | Whether the team member is enrolled in payroll. |
| `payroll_status` | string \| null | yes | The team member's payroll onboarding status, sourced from our payroll system. `completed` means fully onboarded, `needs_attention` and `blocking` mean onboarding steps remain, and `null` means the... |
| `ssn_last_four` | string \| null |  | The last four digits of the team member's Social Security number. |
| `time_off` | object \| null |  |  |

### Team Members → Onboarding Checklists (`OnboardingChecklistResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string | yes | The ID of the team member this checklist belongs to. |
| `completed_at` | timestamp \| null | yes | The date and time the checklist was completed, or null if not yet completed. |
| `tasks` | array<object> | yes | The list of onboarding tasks in this checklist. |

### Third Party Cards (`ThirdPartyCardResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `card_last_four` | string | yes | The last 4 digits of the card number. |
| `team_member_id` | string (objectid) | yes | The ID of the team member associated with the card. |
| `approver_team_member_id` | string (objectid, nullable) |  | The ID of the team member responsible for approving transactions on the card. |
| `custom_id` | string | yes | A customer-facing identifier for the card (from Plaid, Astrada, or generated for imported cards). |
| `external_vendor` | enum[plaid,astrada,imported] | yes | The source of the card: Plaid, Astrada, or imported. |
| `card_name` | string |  | The name of the card (Plaid/Astrada). |
| `financial_institution` | string |  | The financial institution that issued the card. |
| `card_program_id` | string | yes | The ID of the card program associated with the card. |
| `external_data` | object |  | Card data from the network. |
| `cardholder` | object |  | Cardholder details from the network. |

### Time Off Policies (`TimeOffPolicyResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `type` | enum[vacation,sick] | yes | The type of time off policy. |
| `name` | string | yes | The display name of the policy. |
| `levels` | array<object> | yes | The levels (tiers) configured for this policy. |
| `accrue_on_davis_bacon_jobs` | boolean \| null |  | Whether time off accrues on Davis-Bacon jobs. |
| `custom_earning_code` | string \| null |  | A custom earning code associated with this policy. |
| `payout_on_dismissal` | boolean \| null |  | Whether accrued time off is paid out when a team member is dismissed. |
| `accrue_on_dismissal` | boolean \| null |  | Whether time off continues to accrue during the dismissal process. |

### Time Off Requests (`TimeOffRequestResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes | The ID of the team member who submitted the request. |
| `time_off_policy_id` | string (objectid) | yes | The ID of the time off policy the request is against. |
| `start_date` | date | yes | The first date the team member is requesting off, as an ISO-8601 date string. |
| `end_date` | date | yes | The last date the team member is requesting off, as an ISO-8601 date string. |
| `total_hours` | number | yes | The total number of time-off hours requested across all scheduled days. |
| `status` | enum[unapproved,approved,processing,denied,paid] | yes | The status of the time off request. |
| `schedule` | array<object> | yes | Per-day breakdown of the requested time off. |
| `team_member_note` | string \| null |  | An optional note left by the team member when submitting the request. |
| `company_note` | string \| null |  | An optional note left by the approver of the request. |
| `approved_or_denied_at` | timestamp |  | When the request was approved or denied, as an ISO-8601 datetime (UTC). |
| `approved_or_denied_by_user_id` | string (objectid, nullable) |  | The ID of the user who approved or denied the request. |
| `department_id` | string (objectid, nullable) |  | The ID of the department associated with the request. |
| `company_entity_id` | string (objectid, nullable) |  | The ID of the company entity associated with the request. |

### Timesheets (`TimesheetResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `team_member_id` | string (objectid) | yes |  |
| `job_id` | string (objectid, nullable) |  |  |
| `activity_id` | string (objectid, nullable) |  |  |
| `work_order_id` | string (objectid, nullable) |  | The ID of the work order this timesheet is associated with. Fetch valid IDs from GET /work_orders. When the work order is linked to a job, Miter forces the timesheet onto that job: submitting a... |
| `workers_compensation_code_id` | string (objectid, nullable) |  | The ID of the workers' compensation code set directly on this timesheet. Fetch valid IDs from GET /workers_comp_codes; submitting an ID that does not exist in your company returns a 404. When set, it... |
| `notes` | string \| null |  | Optional notes attached to the timesheet. |
| `custom_id` | TBD: untyped in spec | yes | The customer-supplied stable identifier for this timesheet. Used to deduplicate upserts |
| `clock_in` | timestamp | yes |  |
| `clock_out` | timestamp | yes |  |
| `hours` | number | yes |  |
| `status` | enum[approved,unapproved,draft,processing,paid] | yes |  |
| `earning_type` | string \| null |  | The REG/OT/DOT earning classification for this timesheet. This field is null until the timesheet is paid and Miter applies OT/DOT rules, unless it was explicitly set during creation or update. For... |
| `custom_earning_code_id` | string (objectid, nullable) |  | The ID of a custom earning code to apply to this timesheet. Fetch valid codes from GET /custom_earning_codes. Use this field for company-specific earning classifications; earning_type controls... |
| `time_off_policy_id` | string (objectid, nullable) |  | For policy-scoped time off earning types (`pto`, `sick`), the ID of the time off policy that governs this earning. Null for standard earning types or when no governing policy is recorded. |
| `custom_field_values` | array<object> |  | Custom field values on the timesheet. |
| `crew_ids` | array \| null |  | The IDs of the crews the team member belonged to when this timesheet was recorded. Snapshotted at creation and re-cached when the team member changes, so historical timesheets stay associated with... |
| `break_time` | object | yes |  |
| `integration_metadata_by_system` | object |  |  |
| `current_break_policy_id` | string (objectid) | yes | The break policy that currently governs this timesheet. Derived at read time from the timesheet's team member, job, department, and location assignments (not stored), so it always reflects the... |
| `classification_id` | string (objectid) | yes | The classification set on this timesheet, overriding the one Miter would otherwise derive from the activity, job, pay rate group, and team member. Null when none is set; see classification_excluded.... |
| `classification_excluded` | boolean | yes | True when this timesheet is deliberately marked as having no classification, so Miter derives none. When false and classification_id is null, Miter derives the classification. |
| `standard_classification_id` | string (objectid) | yes | The standard classification set directly on this timesheet. Takes precedence over the team member's standard classification when Miter resolves a pay rate within a pay rate group. Fetch valid IDs... |

### Trades (`TradeResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string \| null |  | The name of the trade. |
| `washington_lni_trade` | string \| null |  | Washington LNI trade code, used in CPR XML generation. |
| `alaska_aashtoware_craft_code` | string \| null |  | Deprecated. Alaska AASHTOWare craft code is now configured per classification rather than per trade, and is not exposed here. Always null. |

### Vendors (`VendorResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The vendor's display name. |
| `custom_id` | string | yes | Your identifier for this vendor — unique per company, used for upserts. |
| `description` | string \| null |  | Free-text description of the vendor. |
| `default_payment_method` | string \| null |  | Preferred payout method when paying this vendor (ach or check). |
| `bank_account_id` | string (objectid, nullable) |  | The vendor's active ACH bank account ID, if one is configured. |
| `paper_check_config` | object |  | Paper-check remit-to configuration, if the vendor is paid by check. |
| `team_member_id` | string (objectid, nullable) |  | The team member this vendor is linked to, if any (1099 contractor pattern). |
| `default_ledger_account_id` | string (objectid, nullable) |  | Default ledger account ID applied to bills from this vendor. |
| `default_department_id` | string (objectid, nullable) |  | Default department ID applied to bills from this vendor. |
| `default_location_id` | string (objectid, nullable) |  | Default location ID applied to bills from this vendor. |
| `default_class_id` | string (objectid, nullable) |  | Default class ID applied to bills from this vendor. |

### Work Orders (`WorkOrderResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `custom_id` | string | yes | A customer-provided identifier for the work order. |
| `name` | string \| null |  | Display name of the work order. |
| `equipment_ids` | array \| null |  | IDs of equipment associated with the work order. |
| `job_id` | string (objectid, nullable) |  | The ID of the job this work order is linked to, set when the work order is synced from a connected system that ties it to a job. Read-only. When set, timesheets associated with this work order are... |
| `integration_metadata_by_system` | object |  |  |

### Workers Comp Codes (`WorkersCompCodeResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `label` | string | yes | Human-readable label for the workers' compensation code. |
| `code` | string | yes | The workers' compensation code identifier (typically the NCCI/state class code). |
| `premium_rate` | number \| null |  | The premium rate associated with this code. |
| `premium_rate_type` | enum[hourly,percentage] | yes | How `premium_rate` is applied (hourly amount or percentage of wages). |

### Workers Comp Groups (`WorkersCompGroupResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string | yes | The name of this workers compensation group. |
| `type` | enum[state_and_pay_rate,state,job_and_cost_code,pay_rate] | yes | How this group maps workers compensation codes. |
| `default_workers_compensation_code_id` | string (objectid, nullable) |  | The default workers compensation code ID when no mapping matches. |
| `mappings` | array<object> | yes | Mapping rules that determine which workers compensation code to use. |

### Workplaces (`WorkplaceResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (objectid) | yes |  |
| `created_at` | timestamp | yes |  |
| `updated_at` | timestamp | yes |  |
| `name` | string \| null |  | The name of the workplace. |
| `company_entity_id` | string (objectid) | yes | The ID of the company entity this workplace belongs to. |
| `is_company_entity_default` | boolean | yes | Whether this is the default workplace for the company entity. |
| `address` | object |  | The physical address of the workplace. |

### Card Balance (`CardBalanceResponse`)
| Field | Type | Required | Description |
|---|---|---|---|
| `currency` | string | yes | The ISO 4217 currency code of the balance amounts. |
| `available_balance` | number | yes | The current available balance of the Miter card account, in dollars. |
| `pending_inbound_balance` | number | yes | Funds being added to the Miter card account that have not yet settled, in dollars. Not yet available to spend. |
| `pending_outbound_balance` | number | yes | Funds leaving the Miter card account that have not yet settled, in dollars. Already reserved and not available to spend. |

### Break Types (`BreakType`)
_Polymorphic response — union of all variant fields shown; the `level` field is the discriminant (`company` vs `policy`)._

| Field | Type | Required | Description |
|---|---|---|---|
| `level` | string | yes |  |
| `id` | string | yes | The value to submit as break_type_id. A company-settings break-type key. |
| `label` | string | yes | Human-readable name of the break type. |
| `paid` | boolean | yes | Whether breaks of this type are paid. |
| `break_policy_id` | string (objectid) |  | The break policy this break type belongs to. The break type is only valid on timesheets that this policy governs. |
| `break_policy_name` | string |  | Human-readable name of the break policy. |

### Pay Periods (`PayPeriod`)
| Field | Type | Required | Description |
|---|---|---|---|
| `period_start` | date | yes | First day of the pay period (inclusive), as an ISO-8601 date string. |
| `period_end` | date | yes | Last day of the pay period (inclusive), as an ISO-8601 date string. |

### Assignment Occurrences (`AssignmentOccurrence`)
| Field | Type | Required | Description |
|---|---|---|---|
| `original_starts_at` | timestamp | yes | The stable identifier for this occurrence, as an ISO-8601 datetime (UTC). Pass this value as `original_starts_at` to `PUT /assignments/{id}/modify_occurrence` to edit this occurrence. For a modified... |
| `starts_at` | timestamp | yes | When this occurrence currently starts, as an ISO-8601 datetime (UTC). |
| `ends_at` | timestamp | yes | When this occurrence currently ends, as an ISO-8601 datetime (UTC). |
| `assignment_id` | string (objectid) \| null | yes | The ID of the materialized one-off assignment backing this occurrence when it has been individually modified (via modify_occurrence); null for occurrences still generated from the recurrence rule. |

## **Get Object Primary Keys**
The primary key is **static and uniform**: every object's `id` field (a 24-character hexadecimal MongoDB ObjectId, e.g. `507f1f77bcf86cd799439011`) is its primary key. This is declared once in the spec (the `ResponseId`/`ReferenceId` schemas) and reused across all 72 standard objects — there is no per-object primary-key lookup endpoint because it never varies.

**Exceptions** (objects with no `id` field, confirmed by checking their response schema for the presence of `id`):

| Object | Primary key |
|---|---|
| Card Balance | None — singleton, one row per company. Always fetch-and-replace, never keyed. |
| Pay Periods | None — composite natural key: (`pay_schedule_id` path parameter, `period_start`). |
| Assignment Occurrences | None — composite natural key: (`assignment_id` path parameter, `original_starts_at`, which the spec calls the occurrence's "stable identifier"). |

Nested objects (Budget Line Items, Certifications, Ledger Line Items, Pay Rate Group Classifications, Team Member Onboarding Checklists) also use `id` as their primary key — it is unique globally, not just within the parent.

## **Object's ingestion type**
Every standard object supports `sort[field]=updated_at` with `after_exclusive`/`after_inclusive` cursors and page-based pagination (see **Read API** below), which is sufficient for `cdc` (incremental upsert) ingestion.

**No object in this API supports delete detection** — there is no soft-delete/`deleted_at` field on any schema and no `deleted-records` or webhook/audit-log endpoint anywhere in the spec (confirmed by scanning all 152 component schemas and all 241 path+method combinations). This makes every object at best `cdc`, never `cdc_with_deletes`, regardless of whether the object has a `DELETE` operation.

| Object | Ingestion type | Cursor field | Notes |
|---|---|---|---|
| Activities | `cdc` | `updated_at` | |
| Allocation Rule Groups | `cdc` | `updated_at` | |
| Assignments | `cdc` | `updated_at` | |
| Bank Accounts | `cdc` | `updated_at` | Supports `DELETE /bank_accounts/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Bills | `cdc` | `updated_at` | |
| Budgets | `cdc` | `updated_at` | |
| Budgets → Budget Line Items | `cdc` | `updated_at` | Supports `DELETE /budgets/{parent_id}/line_items/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Burden Rates | `cdc` | `updated_at` | |
| Card Transactions | `cdc` | `updated_at` | |
| Certification Types → Certifications | `cdc` | `updated_at` | |
| Certification Types | `cdc` | `updated_at` | |
| Classes | `cdc` | `updated_at` | |
| Company Benefits | `cdc` | `updated_at` | |
| Company Entities | `cdc` | `updated_at` | |
| Cost Types | `cdc` | `updated_at` | |
| Crews | `cdc` | `updated_at` | Supports `DELETE /crews/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Custom Earning Codes | `cdc` | `updated_at` | |
| Custom Tasks | `cdc` | `updated_at` | |
| Customers | `cdc` | `updated_at` | |
| Daily Reports | `cdc` | `updated_at` | |
| Departments | `cdc` | `updated_at` | |
| Employee Benefits | `cdc` | `updated_at` | |
| Equipment | `cdc` | `updated_at` | |
| Equipment Timesheets | `cdc` | `updated_at` | Supports `DELETE /equipment_timesheets/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Expense Cards | `cdc` | `updated_at` | |
| Expense Reimbursement Categories | `cdc` | `updated_at` | |
| Expense Reimbursements | `cdc` | `updated_at` | Supports `DELETE /expense_reimbursements/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Files | `cdc` | `updated_at` | |
| Fillable Templates | `cdc` | `updated_at` | |
| Form Submissions | `cdc` | `updated_at` | |
| Form Templates | `cdc` | `updated_at` | |
| Forms | `cdc` | `updated_at` | |
| Holiday Schedules | `cdc` | `updated_at` | |
| Integration Sync Items | `cdc` | `updated_at` | |
| Integration Syncs | `cdc` | `updated_at` | |
| Job Postings | `cdc` | `updated_at` | |
| Jobs | `cdc` | `updated_at` | |
| Leave Types | `cdc` | `updated_at` | |
| Ledger Accounts | `cdc` | `updated_at` | |
| Ledger Entries → Ledger Line Items | `cdc` | `updated_at` | |
| Ledger Entries | `cdc` | `updated_at` | |
| Ledger Mappings | `cdc` | `updated_at` | |
| Locations | `cdc` | `updated_at` | |
| Message Templates | `cdc` | `updated_at` | |
| Notes | `cdc` | `updated_at` | |
| Team Member Onboarding Checklists | `cdc` | `updated_at` | |
| Overtime Rules | `cdc` | `updated_at` | |
| Pay Rate Groups | `cdc` | `updated_at` | |
| Pay Rate Groups → Classifications | `cdc` | `updated_at` | |
| Pay Rate Versions | `cdc` | `updated_at` | |
| Pay Schedules | `cdc` | `updated_at` | |
| Payroll Payments | `cdc` | `updated_at` | |
| Payrolls | `cdc` | `updated_at` | |
| Policies | `cdc` | `updated_at` | |
| Position Templates | `cdc` | `updated_at` | |
| Post Tax Deductions | `cdc` | `updated_at` | |
| Quantity Logs | `cdc` | `updated_at` | |
| Rate Differentials | `cdc` | `updated_at` | |
| Standard Classifications | `cdc` | `updated_at` | |
| Tax Filings | `cdc` | `updated_at` | |
| Team Members | `cdc` | `updated_at` | |
| Team Members → Onboarding Checklists | `cdc` | `updated_at` | Supports `DELETE /team_members/{parent_id}/onboarding_checklists/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Third Party Cards | `cdc` | `updated_at` | |
| Time Off Policies | `cdc` | `updated_at` | |
| Time Off Requests | `cdc` | `updated_at` | |
| Timesheets | `cdc` | `updated_at` | Supports `DELETE /timesheets/{id}` — hard delete, **no tombstone**. A deleted row simply stops appearing; periodic full-snapshot reconciliation is the only way to detect removal. |
| Trades | `cdc` | `updated_at` | |
| Vendors | `cdc` | `updated_at` | |
| Work Orders | `cdc` | `updated_at` | |
| Workers Comp Codes | `cdc` | `updated_at` | |
| Workers Comp Groups | `cdc` | `updated_at` | |
| Workplaces | `cdc` | `updated_at` | |
| Break Types | `snapshot` | — | No `sort`/`page`/`limit` params — the endpoint always returns the complete, unpaginated set. |
| Card Balance | `snapshot` | — | No `id`/list — always a full snapshot read. |
| Pay Schedules → Pay Periods | `snapshot` | — | Computed from the pay schedule's config + a date range; not independently trackable — re-derive per parent `pay_schedule_id`. |
| Assignments → Occurrences | `snapshot` | — | Computed from the assignment's recurrence rule + a date range; not independently trackable — re-derive per parent `assignment_id`. |

## **Read API for Data Retrieval**

### Uniform list pattern

All 72 standard objects (and the two nested-collection variants) are read the same way: `GET <path>` returns `{success, data: {size, next_page, results}}`, and support the same five query parameters:

| Param | Style | Description |
|---|---|---|
| `filters` | `deepObject` (e.g. `filters[team_member_id]=507f...`) | Exact-match / `in`-list filters. Field names are **object-specific** — see the `filters` column in **Object List** below, or the per-object `filters` schema in the OpenAPI spec. Filters accept either a single value or an array of values (OR semantics) for most fields. Omitted → no filtering. |
| `sort[field]` | form | Which timestamp field to sort and range-filter on. Always `created_at` or `updated_at`; a few objects add one more option (`Timesheets`: `clock_in`; `Pay Rate Versions`: `effective_at`; `Payroll Payments`: `payday`; `Time Off Requests`: `start_date`). Default: `updated_at`. |
| `sort[direction]` | form | `ascending` or `descending`. Default: `descending`. |
| `sort[before_exclusive]` / `sort[before_inclusive]` / `sort[after_exclusive]` / `sort[after_inclusive]` | form, ISO-8601 datetime | Range-bound the `sort[field]` value. This **is** the incremental-sync mechanism — there is no separate `since` parameter. |
| `limit` | form | Page size, `1`–`1000`, default `100`. |
| `page` | form | Opaque cursor — pass the previous response's `data.next_page` verbatim. `null`/absent starts from the beginning. |
| `output_fields` | form (comma-separated) | Sparse fieldset: restrict the response to only these top-level fields (`id` is always included). Reduces payload size; safe to use once the connector knows an object's full field list. |

Single-record reads use `GET <path>/{id}` and return `{success, data: <object>}` (no envelope wrapper) — no query parameters.

### Example: incremental list request

```
GET /team_members?sort[field]=updated_at&sort[direction]=ascending&sort[after_exclusive]=2025-01-01T00:00:00Z&limit=100
Authorization: Bearer <API_TOKEN>
Accept: application/json
```

```json
{
  "success": true,
  "data": {
    "size": 100,
    "next_page": "507f1f77bcf86cd799439011",
    "results": [
      {
        "id": "507f191e810c19729de860ea",
        "created_at": "2024-11-03T14:22:01Z",
        "updated_at": "2025-01-02T09:10:44Z",
        "full_name": "Jane Doe",
        "employment_status": "active",
        "employment_type": "employee",
        "work_email": "jane.doe@example.com"
      }
    ]
  }
}
```

### Example: filtered request (`deepObject` filters)

```
GET /timesheets?filters[team_member_id]=507f191e810c19729de860ea&sort[field]=updated_at&sort[direction]=ascending&limit=100
Authorization: Bearer <API_TOKEN>
```

### Pagination + incremental sync algorithm

```python
def sync(resource, checkpoint=None, page_size=100):
    params = {
        "sort[field]": "updated_at",
        "sort[direction]": "ascending",
        "limit": page_size,
    }
    if checkpoint:
        params["sort[after_exclusive]"] = checkpoint

    page_cursor = None
    max_updated_at = checkpoint
    while True:
        if page_cursor:
            params["page"] = page_cursor
        resp = get(resource, params)
        body = resp.json()["data"]
        for row in body["results"]:
            emit(row)
            max_updated_at = max(max_updated_at, row["updated_at"]) if max_updated_at else row["updated_at"]
        page_cursor = body["next_page"]
        if page_cursor is None:
            break
    return max_updated_at  # persist as next run's checkpoint
```

**Caveats**:
- `after_exclusive` is strictly `>`. Persist the checkpoint as the **last-seen `updated_at`** and always resume with `after_exclusive` (not `after_inclusive`) to avoid reprocessing the boundary row, while still catching any row that was updated again after being read at the exact same timestamp on a prior run (rare given millisecond-resolution timestamps, but the API does not guarantee uniqueness of `updated_at` across rows).
- If a row is updated *during* a paginated run and its `updated_at` moves past the current page window, cursor-based pagination on a monotonic ascending sort will still surface it — either on the current run (if it moves forward into an unread page) or the next run (if it moves out ahead of the whole window). This is a normal property of timestamp-cursor pagination, not specific to this API.
- `nested resources` (Budget Line Items, Certifications, Ledger Line Items, Pay Rate Group Classifications, Team Member Onboarding Checklists) must be synced **once per parent record** — there is no global `filters[<parent>_id]=*` wildcard, so the connector must iterate known parent IDs (from that parent object's own sync) and issue one paginated `GET .../{parent_id}/<child>` per parent.

### Deleted records

Not supported anywhere in this API. No object exposes a `deleted_at`/`is_deleted` field, and there is no `deleted-records`, webhook, or audit-log endpoint (checked across all 152 schemas and all paths). For the 7 objects that expose a `DELETE` operation (see **Object's ingestion type**), a deleted row is simply absent from future list responses with no trace — the only way to detect the deletion is to periodically diff a full snapshot of `id`s against the connector's previously-synced set.

### Rate limits

Rate limits are **per-token**, not fixed/global — discover them by calling `GET /ping` and reading `data.rate_limits`:

| Limit | Applies to | Example value |
|---|---|---|
| `single_action_per_minute` | Single-record endpoints, e.g. `GET /team_members/{id}` | `100`/min (per the spec's example; actual value is per-token) |
| `bulk_action_per_minute` | List/batch endpoints, e.g. `GET /team_members` | `60`/min (per the spec's example; actual value is per-token) |

Exceeding a limit returns `429` with `{"success": false, "error": "Too many requests, please try again later."}`. The connector should call `GET /ping` once at startup to learn the token's actual limits and pace bulk list requests accordingly; contact `support@miter.com` for higher limits.

### Error handling

Every error response shares one shape: `{"success": false, "error": "<message>"}`.

| Status | Meaning | Action |
|---|---|---|
| `400` | Invalid query/path parameter (e.g. wrong type, unsupported filter) | Do not retry; fix the request. |
| `401` | Token invalid/revoked | Do not retry; re-authenticate. |
| `403` | Token lacks the scope for this object/company | Do not retry; surface as "object not accessible with this token." |
| `404` | Unknown object id / unknown parent id (for nested resources) | Do not retry. |
| `429` | Rate limit exceeded | Retry with backoff, paced to the token's `rate_limits`. |
| `500` | Internal server error | Retry with exponential backoff. |

## **Field Type Mapping**
| Spec type / format | Meaning | Spark type |
|---|---|---|
| `string` | Plain text | `StringType` |
| `string`, `format: objectid` | 24-char hex MongoDB ObjectId (`ReferenceId`/`ResponseId`); primary keys and all `_id` foreign keys | `StringType` |
| `string`, `format: datetime` (`ReferenceDateTime`/`ResponseDateTime`) | ISO-8601 datetime, `Z` or numeric UTC offset | `TimestampType` |
| `string`, `format: date` (`ReferenceDate`) | ISO-8601 date, no time component (e.g. `date_of_birth`, `period_start`) | `DateType` |
| `string` with `enum` | Fixed set of string values (see each field's table entry for the set) | `StringType` |
| `number` | Used for both integer counts and decimal money amounts; the spec does not distinguish `integer` from `float` | `DoubleType` (safe superset; narrow to `LongType` per-field only where the description confirms a whole-number count, e.g. `size`) |
| `boolean` | true/false | `BooleanType` |
| `object` (nested, fixed shape, e.g. `address`, `demographics`, `termination_reason`) | Struct with known sub-fields | `StructType` (build sub-fields from the nested schema) |
| `object` (dynamic keys, e.g. `integration_metadata_by_system`, `custom_field_values`) | Map keyed by an external-system name or a custom-field id, not enumerable from the spec | `MapType(StringType, StringType)` or store as a JSON string — key set is **not** part of the static schema (`TBD: no source enumerates all possible integration_metadata_by_system keys`) |
| `array<string \| objectid>` | List of scalars/references (e.g. `additional_workplace_ids`, `file_ids`) | `ArrayType(StringType)` |
| `array<object>` | List of structs (e.g. `emergency_contacts`, `custom_field_values`) | `ArrayType(StructType)` |
| Field absent from `required` | Optional/nullable in practice | Mark the Spark field `nullable=true` |
| Polymorphic response (`oneOf`/`anyOf` object) | Row shape depends on a discriminant field (e.g. `Bank Accounts.owner`, `Break Types.level`) | Union all variant fields into one `StructType` with every field nullable; use the discriminant to know which subset is populated on a given row |

## **Sources and References**

| Source | Type | Confidence | What it confirmed |
|---|---|---|---|
| `miter-openapi.json` (OpenAPI 3.1.0, `info.version: "2.0"`, provided by the user, copied into `sources/miter/miter-openapi.json`) | User-provided official spec | Highest | All endpoints, request/response schemas, auth scheme, filters/sort/pagination parameters, error shapes, rate-limit shape. |
| `miter-postman-collection.json` (Postman Collection v2.1.0, provided by the user, copied into `sources/miter/miter-postman-collection.json`) | User-provided official collection | Highest | Cross-referenced the OpenAPI spec's endpoints, base URL (`https://api.miter.com/api/v2`), Bearer-auth header usage, and `deepObject` query-string encoding (e.g. `sort[field]=updated_at`). Every endpoint present in the spec was also present in the collection (72 list endpoints matched); no discrepancies found between the two sources. |

No external documentation (public API docs, Airbyte/Singer/dltHub implementations, or blog posts) was consulted — both user-provided sources are official, mutually consistent, and together fully cover the read surface, satisfying the two-source cross-reference requirement without external research.

### Research Log

| Source Type | URL | Accessed (UTC) | Confidence | What it confirmed |
|---|---|---|---|---|
| User-provided documentation | local file: `sources/miter/miter-openapi.json` | 2026-09-18 | High | Every endpoint's path, method, params, request/response schema, security scheme, error shapes. |
| User-provided documentation | local file: `sources/miter/miter-postman-collection.json` | 2026-09-18 | High | Base URL, Bearer-auth header, real query-string encoding for `filters`/`sort`, one example response body per endpoint. |

**Known gaps** (marked `TBD` inline above and repeated here for visibility):
- Where/how a company generates a Miter API token (not covered by either source).
- The full set of possible keys under `integration_metadata_by_system` and `custom_field_values` (dynamic, external-system-dependent, not enumerable from the static schema).
- Two fields (`JobPostingResponse.custom_id`, `TimesheetResponse.custom_id`) have no `type` in the spec at all.
- Actual numeric rate-limit values per token tier (the spec only shows illustrative examples; real limits must be read from each token's own `GET /ping` response).
