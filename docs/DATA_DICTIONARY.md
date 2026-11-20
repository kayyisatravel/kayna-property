# Data Dictionary — Google Sheets V1

All related records use `property_id`; each immutable underwriting snapshot uses `analysis_id`. A property can have many analyses over time. Decision status and lifecycle status are separate dimensions.

| Tab | Primary key / relationship | Purpose |
|---|---|---|
| PROPERTIES | `property_id` | Master property, latest input payload, decision status, lifecycle status |
| SURVEYS | `survey_id`; `property_id` | Survey and occupancy payload snapshots |
| COMPARABLES | `comparable_id`; `property_id`, `analysis_id` | Raw comparable fields (including source_url_scope) plus complete payload/validation results; payload includes source platforms/evidence, listing date, capture date, condition/access detail and other extracted specs |
| COST_ESTIMATES | `estimate_id`; `property_id`, `analysis_id` | Cost assumptions and rules snapshot |
| RISK_REGISTER | `risk_id`; `property_id`, `analysis_id` | Risk category, probability, impact, cash reserve, mitigation and status |
| COST_ACTUALS | `actual_id`; `property_id`, optional `budget_item_id` | Actual paid transaction, receipt URL, vendor/payment method, and link to a budget item |
| PROJECT_BUDGETS | `budget_item_id`; `property_id` | Budget total, committed unpaid amount, forecast remaining amount, due date, vendor and status per project cost item |
| CASH_POSITION | `profile_id` | Latest user-confirmed real cash and reserve setting |
| CASHFLOW_EVENTS | `event_id`; `profile_id`, optional `property_id` | User-entered future outflow/inflow events and confirmation |
| PROJECT_MILESTONES | `milestone_id`; `property_id`, `stage` | Planned/actual project lifecycle dates and status |
| ANALYSIS_HISTORY | `analysis_id`; `property_id` | Immutable calculation result snapshot and decision |
| SALES_CLOSING | `property_id` | Sold date, listing start, closing price, selling cost and holding period |
| RULES_CONFIG | `rule_key` | Global user-managed rate and calculation assumptions |
| DOCUMENTS | `document_id`; `property_id` | File metadata, Drive link, hash and extraction JSON for re-use/cache |
| HISTORY | `history_id`; `entity_id` | Audit log of edits and workflow actions |

`PETUNJUK` exists only in the XLSX template and is not an application data tab.

## Status fields

Decision status: DRAFT, INCOMPLETE, HOLD, CONDITIONAL GO, GO, DO NOT BID.

Lifecycle status: PROSPECT, BID PLANNED, BID SUBMITTED, WON, LOST, WITHDRAWN, ACTIVE, SOLD.

The application saves all analyzed opportunities regardless of decision. Only properties marked WON/ACTIVE appear in Active Properties; SOLD properties appear in Closed Projects & Track Record. LOST/WITHDRAWN remain opportunity history.


## Project finance fields (V1.0.9)

- `COST_ACTUALS.amount` means money already paid. It must not contain unpaid commitments or forecasts. `budget_item_id` links the payment to a line in `PROJECT_BUDGETS`.
- `PROJECT_BUDGETS.budget_amount` is the total budget target for the cost line; `committed_unpaid` is the remaining amount already agreed with a vendor/party; `forecast_remaining` is the uncommitted estimate still expected. Do not put paid amounts into either outstanding field.
- The app reduces the selected outstanding bucket when a new payment is recorded against a linked budget item. The original payment remains as an auditable row in `COST_ACTUALS`.
- Active commitments from projects with lifecycle `WON` or `ACTIVE` are automatically deducted from investor cash availability. Do not enter the same commitment again in `CASHFLOW_EVENTS`.
- Project cost to completion through ready-to-market excludes the `Penjualan`/`Selling` category; selling costs are reported separately. Risk reserves are cash protections, not actual costs until spent.
