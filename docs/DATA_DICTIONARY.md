# Data Dictionary — Google Sheets V1

All related records use `property_id`; each immutable underwriting snapshot uses `analysis_id`. A property can have many analyses over time. Decision status and lifecycle status are separate dimensions.

| Tab | Primary key / relationship | Purpose |
|---|---|---|
| PROPERTIES | `property_id` | Master property, latest input payload, decision status, lifecycle status |
| SURVEYS | `survey_id`; `property_id` | Survey and occupancy payload snapshots |
| COMPARABLES | `comparable_id`; `property_id`, `analysis_id` | Raw comparable fields plus complete payload/validation results |
| COST_ESTIMATES | `estimate_id`; `property_id`, `analysis_id` | Cost assumptions and rules snapshot |
| RISK_REGISTER | `risk_id`; `property_id`, `analysis_id` | Risk category, probability, impact, cash reserve, mitigation and status |
| COST_ACTUALS | `actual_id`; `property_id` | Actual project cash outflow and receipt URL |
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
