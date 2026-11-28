## [1.0.25.2.1] - 2026-11-28

### Fixed
- Fix `StreamlitAPIException` in the Risk Register when legacy saved rows contain an all-null `hard_stop_confirmed` column inferred by Pandas as `float64`; all checkbox-backed columns are normalized to real boolean dtype before `st.data_editor`.
- Normalize all three analysis editors (Risk Register, Comparables, and Renovation RAB) before rendering and after edits: checkbox columns become boolean, numeric columns become numeric, selectbox values are constrained to configured options, text columns are stable, and comparable dates are passed as date values.
- Bump editor widget keys/schema markers so Streamlit does not reuse stale widget state from the prior column schema; imported/AI-updated rows clear the matching current widget key before rerun.
- Preserve the complete comparable editor schema when loading saved properties, including complex/underlying-property IDs, seller type and promotion verification fields that could previously be dropped during load.
- Parse legacy boolean text (`False`, `0`, `Tidak`, `True`, `Ya`) safely in risk and comparable calculations; string `"False"` is no longer treated as true.

### Compatibility
- No Google Sheets tab/header/schema migration. Existing snapshots are normalized in memory when loaded; stored history is not rewritten.
- No secrets or credentials are included.

### Verification
- Regression suite: **289 passed**.
- Python compilation passed for app, config, all core, reports, services, storage and tests.
- Static check confirms every analysis `st.data_editor` receives a normalized dataframe.
- Live Streamlit Cloud, Google Sheets and Gemini API integration was not performed in this environment.

## [1.0.25.2] - 2026-11-27

### Changed
- Reframe the underwriting flow as an AI Feasibility Co-Pilot: deterministic Python calculations, Gemini Flash senior-analyst interpretation, and explicit Owner decision authority.
- Separate model reference classification, bid readiness and Owner's final choice/rationale in the analysis screen and memorandum.
- Allow Owner FMV as-is / ARV assumptions with a written basis when comparable listings are unavailable; retain small-sample market values as provisional and keep as-is and post-renovation condition cohorts separate.
- Add a priced hidden-condition reserve for uninspected interiors and building-age / visual assessment notes; uncertainty is represented in the model rather than converted automatically into HOLD.
- Add allowance for renovation scope that cannot yet be accessed, measured or quoted; include the allowance in renovation cost and apply contingency to the modeled scope.
- Model additional cash by amount, source, expected date and status. Planned/unconfirmed funds and funds arriving after the auction are not counted as cleared bid-day liquidity; confirmed commitments remain provisional until received.
- Record Owner confirmation that SKPT/KPKNL announcement and property identity have been checked. Original certificate handover is tracked as an administrative/post-award follow-up rather than a duplicate pre-bid legal veto.
- Add deterministic Fast / Moderate / Stress feasibility scenarios and include the AI brief and Owner decision in downloadable investment memoranda and the existing analysis payload.
- Reserve DO NOT BID for explicit confirmed fatal legal/security/access/environmental hard stops or strongly evidenced structural economic failure. Incomplete but priceable friction generally becomes a condition / scenario / readiness item rather than an automatic investment HOLD.

### Compatibility
- No Google Sheets tab/header/schema migration. New inputs and outputs are stored in the existing analysis JSON payload/history.
- Preserve the V1.0.25 ranking, existing sequential workflow and user custom UI. V1.0.26 lifecycle and V1.0.27 same-property / relist detection are not included.
- `.streamlit/secrets.toml` is not included or overwritten.

### Verification
- Regression suite: **280 passed**.
- Python compilation / AST and release ZIP integrity checks: recorded in the V1.0.25.2 release notes after packaging.
- Live Streamlit Cloud, Google Sheets and Gemini API integration was not performed in this environment.

## [1.0.25.1] - 2026-11-27

### Changed
- Separate investment classification (GO / CONDITIONAL GO / HOLD / DO NOT BID) from bid readiness; cash shortage or missing official increment blocks bidding readiness without automatically removing the property's investment potential.
- Rework decision thresholds to default CONDITIONAL GO Project ROI ≥15%, GO ≥25%, target ROI 30%, minimum net profit Rp50 million, GO holding ≤180 days and CONDITIONAL GO ≤365 days.
- Add condition-matched FMV as-is and ARV-after-repair valuation cohorts. House exit values use ready-to-move comparables; as-is FMV uses current-condition comparables. Land-only exit uses land comparables.
- Keep mixed-condition estimates as provisional diagnostics only when matched exit evidence is insufficient; hold final valuation/MAO gates until at least 3 matched comparables and confidence ≥45 are available.
- Add 70% quick MAO screening, Full Cost MAO for CONDITIONAL GO, separate GO Full Cost ceiling, and 30% target bid reference.
- Pass current rules into the decision engine, repair explicit vacant-status parsing, and add explicit hard-stop flags for verified fatal legal, security and access/environment issues.
- Re-underwrite saved portfolio snapshots with current global policy thresholds while preserving historic property-specific inputs.

### Compatibility
- No Google Sheets tab/header/schema migration. New decision and market fields are stored inside existing analysis JSON payloads.
- Historical snapshots remain intact; no V1.0.26 lifecycle or V1.0.27 same-property/Lot-Code matching changes are included.
- `.streamlit/secrets.toml` is not included or changed.

### Verification
- Python compile check passed.
- Regression suite: **257 passed**.
- Live Streamlit Cloud / Google Sheets / Gemini integration was not tested in this environment.

## [1.0.24] - 2026-11-27

### Fixed
- Defined the optional SHGB-rights expiry date picker before authentication gates and page routing, eliminating a `NameError` path when the legal form renders. Date helper declarations are now available regardless of which page branch is active.
- Added a Python `symtable` static regression test that scans all global references in `app.py` for missing definitions/imports (including names used inside nested functions).
- Preserved editable KPKNL auction/deposit date pickers. The payment-date information is now explicitly a weekday-only internal estimate: five Monday-to-Friday days after the actual win date; before the auction it is only a planning scenario based on the scheduled date. No annual holiday table is embedded or requires patch updates. The actual KPKNL notice/confirmation remains authoritative.

### Improved
- Simplified sequential workflow buttons to clear navigation actions: Data Lelang & Legal → Survei & Risiko → Pembanding → Biaya & RAB. The analysis/update button is only shown on the final step after required data, reviews, comparables and in-scope RAB rows are complete.
- Moved step-state persistence/restoration into pure tested helpers. Form values survive step navigation without copying temporary widget keys or upload objects; permanent Google Sheets save happens after the final analysis/update action.
- Clarified that three unique sourced comparables enable indicative analysis, while the underwriting GO gate may still require five stronger individual comparables.
- Added static layout regression test to ensure `st.columns()` calls do not exceed four columns.

### Compatibility and safeguards
- No Google Sheets tab/header/schema migrations. No annual holiday calendar to maintain. `.streamlit/secrets.toml` is not included in release packages.
- Local verification: `pytest -q` 238 passed; `python -m compileall -q .` passed; unresolved-global scan passed. Streamlit Cloud with the user's secrets/Google Sheets credentials was not live-tested.

## V1.0.22 — Kayna Flip Underwriting Policy & Time-Adjusted Returns

- Set Kayna underwriting defaults to minimum all-in Project ROI 20%, target ROI 30%, minimum net profit Rp50 million, ideal holding period 90 days, and maximum holding period 180 days; profit above the target ROI is not capped.
- Maximum-bid solver now requires all three economic gates at the same time: all-in Project ROI, minimum net profit, and maximum projected holding period. Missing duration cannot pass as a zero-day project.
- Base/Upper ARV maximum-bid outputs are sensitivity references; Quick Sale / conservative ARV remains the actionable hard-cap basis.
- Project ROI now uses net profit divided by total all-in cost including selling transaction costs. Pre-sale-capital ROI remains a separately labelled diagnostic.
- Added estimated annualized ROI equivalent for projections, explicitly distinguished from actual XIRR. Actual XIRR is calculated only from complete dated cashflows and reconciled selling costs.
- Separated primary/developer listings from the secondary/resale ARV pool when secondary evidence exists; primary offers remain competitive-market context. Promotion value is deducted only when its cash-equivalent amount is verified. Duplicate physical properties can be excluded by underlying property ID.
- Improved bidding tier explanations so ROI, minimum profit, funding and duration gates are all visible; 91–180 day projects receive a target-period warning, while >180 days fails underwriting.
- Preserved custom app UI, Google Sheets tabs/headers, cached reads and existing database records.
- Regression suite: 218 passed; Python compile check passed.

## [1.0.21] - 2026-11-25

### Changed
- Add three complete financial schedules to the investment proposal for limit, middle and upper bidding scenarios: total capital through pre-sale, cash requirement and risk reserves, and sale costs/net proceeds/profit/ROI. These tables reuse the existing Python bidding scenario calculator.
- Upgrade the initial dashboard to a Kayna Property portfolio command center, with cached portfolio KPIs, upcoming auction/deposit deadlines, active-project cost/budget exposure, physical work progress and project alerts.
- Show physical renovation progress in the dashboard as a duration-weighted measure from explicit work-item status, with tracking coverage; milestone status is the fallback. Payments are not treated as physical progress.
- Keep the V1.0.18-style Word table design, move major financial/RAB/risk sections to clean page starts, and avoid forced page breaks between active and completed portfolio tables.

### Compatibility and safeguards
- Dashboard computations run from app-cached Google Sheets data; filtering/summary calculations do not add repeated Sheets reads or Gemini calls.
- No new Google Sheets tabs or destructive header/schema migrations. Existing payloads and analysis snapshots remain compatible.
- `.streamlit/secrets.toml` is not included or overwritten.

### Verification
- `pytest -q`: 203 passed.
- `python -m compileall -q .`: passed.
- Full source and V1.0.20 overlay patch validated separately.
- Word proposal rendered and visually checked; live Streamlit Cloud/Sheets credentials were not tested.

## [1.0.20] - 2026-11-25

### Changed
- Rename the external investor document to **Proposal Investasi Properti**, a clearer presentation-oriented title for private property-flipping opportunities.
- Restore the cleaner V1.0.18 table presentation while retaining the V1.0.19 navy palette and minimum 11 pt font. Add more vertical breathing room between the Kayna Property header and document body.
- Restructure the comparable table to four non-duplicative columns: full address, asking price, land/building area, and URL/source.
- Use numeric bid amounts as the first column in capital, sale-cost/profitability and bid-strategy tables; move descriptive scenario labels to notes.
- Show RAB unit prices and item subtotals in full Rupiah, add a final total row, and display low/base/high duration estimates per item using the same productivity engine as the renovation schedule.
- Calculate active-project physical renovation progress from duration-weighted work-item status in PROJECT_BUDGETS. Display tracking coverage and keep progress as “Belum diperbarui” when no physical status has been recorded; payment alone is not treated as physical progress. Existing milestone records remain a fallback when no measurable work lines exist.
- Separate completed-project closing date, sale value, actual capital, selling costs, profit and realized ROI in the portfolio appendix; fix sales-cost categories in realized project totals.

### Compatibility and safeguards
- Project work status/progress is stored additively in existing PROJECT_BUDGETS payload; no new Google Sheets tab, header or destructive schema migration is needed.
- Analysis snapshot, pricebook, auction dates, cash scenarios and underwriting calculations remain unchanged.
- Google Sheets portfolio context remains cached; memo generation is local Python and does not require a Gemini call.
- `.streamlit/secrets.toml` is not included or overwritten.

### Verification
- `pytest -q`: 198 passed.
- `python -m compileall -q .`: passed.
- DOCX rendered and visually reviewed across all pages; font minimum 11 pt and V1.0.18-like table styling retained.
- Full source and upgrade patch validated separately; live Streamlit Cloud, Google Sheets and Gemini credentials were not tested.

## [1.0.19] - 2026-11-25

### Changed
- Rebuild the investor document as `Memorandum Investasi Properti` / `Property Investment Memorandum` and brand Kayna Property as `Property Investment & Project Management` rather than a construction contractor.
- Convert analysis timestamps to Asia/Jakarta (WIB) in the report and export filenames using the property name and lot.
- Remove the fixed economic-context snapshot from the memorandum. Economic context is omitted until a live, source-verified and freshness-checked data provider is implemented.
- Replace comparable distance in the report with full address and source, using a compact four-column layout.
- Present capital, reserve/cash requirement, selling cost, net sale proceeds and profit across limit, middle and upper bid scenarios; strategy includes target and simulated ROI.
- Add a final RAB total row, low/base/high total range and fast/base/slow workday allowance per item. Per-item duration shares the same productivity classifier as the project critical-path schedule.
- Add a cached portfolio appendix for active projects (stage, milestone progress, budget, actuals, commitments/forecast and sale target) and completed projects (closing, actual capital, selling cost, net profit and realized ROI).
- Use a high-contrast navy visual system and a minimum 11 pt font throughout the Word memorandum.

### Safeguards
- Portfolio context is assembled from existing 300-second cached Google Sheets reads and embedded only in the download; it is not written back into analysis snapshots.
- No AI call is made to generate the report. The figures are taken from the saved underwriting snapshot and recorded project ledgers.
- Historical project financials are described as recorded data and are not presented as complete when transactions are missing.

### Verification
- DOCX render and visual review completed on the generated sample memorandum.
- All report text runs are checked at 11 pt minimum; table headings use white on navy for contrast.
- Full regression and package/upgrade validation results are recorded in the V1.0.19 release notes.

## [1.0.18] - 2026-11-25

### Added
- Prefill editable KPKNL auction/deposit/payment date pickers from source-document extraction with evidence; ambiguous dates are not guessed.
- Add `AUCTION_OUTCOMES` reference records for the user's wins, other winners, unsold and cancelled auctions, with price type/source grade and without winner personal data.
- Add local Market & Auction Data explorer with filters, sorting and CSV export; Google Sheets reads use a 300-second cache.
- Add an optional official BPS/Bank Indonesia regional economic context snapshot; it is not used as an ARV multiplier and is omitted when stale or unmatched.
- Add deterministic BoQ-based renovation duration scenarios and phase schedule.
- Add in-app sale deadline reminders and budget monitoring alerts at 70%, 85% and 100%.
- Expand Investment Memo with Kayna Property header, >=11 pt DOCX font, property-based filenames, regional context, RAB and renovation schedule.

### Fixed
- Budget variance is `budget - projected completion`; positive is remaining budget and negative is forecast overrun.
- Sorting/filtering saved property and auction data runs in memory over cached data, avoiding repeated Google Sheets reads.
- Restore the V1.0.17 deterministic regional pricebook and per-item/per-scope RAB subtotals; Gemini prices are not used for project calculations.

### Verification
- Local unit tests and compile checks run; see release guide for scope and limitations.
- Live Streamlit Cloud/Gemini/Google Sheets credentials have not been tested.

## [1.0.17] - 2026-11-24

### Fixed
- Renovation unit rates used for financial calculations no longer depend on stochastic Gemini output. Python applies the versioned Sidoarjo-area screening pricebook, while unmatched scopes remain unpriced pending quotation/manual entry.
- Manual user price overrides are locked during re-analysis and cannot be silently replaced by the regional pricebook.
- User-facing RAB now provides line subtotals (quantity × unit rate) and subtotals by work group for low/base/high scenarios.
- Auction date and deposit deadline now populate from separately extracted official notice fields and evidence; relative dates are never inferred.

### Added
- Transparent Sidoarjo 2026 SSH component anchors and reference links in the RAB pricebook expander.
- Investment Memo reports include pricebook version/basis, source links, and auction-date evidence/provenance where available.
- Investment Memo Word/Markdown filenames contain a slug of the property name and lot code; report generation remains local Python without another Gemini call.
- Regression tests for price override locking and distinct auction/deposit/payment date extraction.

### Compatibility and safeguards
- No destructive Google Sheets schema migration; existing tabs and headers are preserved. Existing chunked payload feature remains additive.
- `.streamlit/secrets.toml` is not included or overwritten.
- Customized Dashboard styling and metric labels are preserved; no metric layout exceeds four columns.
- Date fields are extracted from the official document uploaded by the user, not live-scraped from KPKNL. Unclear/missing dates stay blank and show no inferred value.
- The PFMS pricebook is an internal screening allowance, not a government tariff or contractor quotation. Unmapped scopes require manual quotation/override.

### Verification
- `pytest -q`: 168 passed.
- `python -m compileall -q .`: passed.
- Live Streamlit Cloud, Gemini API and Google Sheets credential tests were not run in this environment.

## [1.0.16] - 2026-11-23

### Fixed
- Generated renovation rows that overlap explicit user BoQ tasks are removed by work-scope matching, while every user BoQ row is retained.
- Site preparation now distinguishes debris/old-item cleanup from protection of floors, doors, windows and work areas. COS_PREP is narrowed or suppressed according to what the user already budgets.
- A comparable URL review confirmation is invalidated when its property name, address, price, land area, building area or URL changes.
- Listing parser accepts backslash-escaped Markdown headings and URLs, bare portal domains, price ranges for building area, and over-credit text.
- Portal-root URLs no longer block indicative valuation. URL traceability remains a separate GO-grade evidence gate.
- Primary developer/new-build comparables have a lower weight than secondary/resale comparables. Over-credit/take-over listings are reported separately from cash-market comparables.

### Added
- Google Sheets `PAYLOAD_CHUNKS` tab for large compressed JSON payloads that exceed the single-cell limit; reads reassemble and checksum-verify the original content.
- Idempotent recovery for interrupted chunk writes, without deleting or truncating existing snapshots.
- Manual straight-line distance in metres for comparable listings when coordinates are unavailable; administrative boundaries are not hard filters.
- Separate `estimate_status` for indicative market estimation and `status` for final evidence readiness.

### Changed
- At least three valid cash-market comparables can produce an indicative range; final READY status still requires at least five confirmed individual listing URLs with captured dates and confidence index of at least 55.
- Market confidence is labelled as a data-quality index, not a probability that a sale will be achieved at the estimated value.
- All metric layouts remain at four columns maximum.

### Verification
- `pytest -q`: 160 passed.
- `python -m compileall -q .`: passed.
- Full ZIP and patch ZIP integrity checked after packaging.
- Live Streamlit Cloud, Gemini API and Google Sheets credentials were not tested in this environment.

## [1.0.15] - 2026-11-23

### Fixed
- Every explicit user BoQ row with a valid positive quantity and compatible unit remains in the underwriting RAB allowance by default. Omission of an optional quantity-basis note no longer makes a visible work item conditional.
- Hidden interior/MEP scopes are retained in the budget with lower confidence; they are not labelled as damage proven by the facade photo.
- Regional Python screening rates fill recognized work scopes when Gemini omits rates or returns incomplete prices. Original quantities and units remain unchanged; incompatible units are never silently coerced.
- Duplicate visual allowances for a new canopy frame and fence repaint are suppressed when those scopes already appear in the user's BoQ.
- Interior risk scenarios are labelled as sensitivity cases, not automatic add-ons, to reduce double counting with BoQ rows.
- Comparable scoring now uses subject/listing coordinates and Haversine distance across village/district/complex boundaries. Added bedroom, bathroom, road-width and orientation similarity indicators.

### Added
- Configurable hidden-condition reserve (default 7.5% of renovation base) when the interior is marked as not inspected; this is separate from the ordinary renovation contingency.
- Comparable-import aliases for latitude and longitude; the editor accepts subject and listing coordinates.
- Low/base/high deterministic screening rates for common TAS 3 style work scopes and distinct allowances for inspection of the terrace ceiling/rangka and unseen interior.
- Regression tests for explicit BoQ retention, regional price coverage, duplicate suppression and 500m cross-village comparables.

### Changed
- Dashboard, RAB and valuation metric rows use no more than four columns. User-customised dashboard label/layout remains intact.
- RAB total can be considered complete when all in-scope allowances have a valid quantity and base price, including explicit user BoQ items; additional excluded conditional guidance does not block completion.

### Compatibility
- Existing Google Sheets tabs and existing headers are preserved. No destructive migration is required. Existing per-project analysis snapshots and manually entered data remain readable.
- `.streamlit/secrets.toml` and credentials are not included in the package.

### Verification
- `pytest -q`: 148 passed.
- `python -m compileall -q .`: passed.
- ZIP integrity: checked.
- Live Streamlit Cloud, Gemini API and Google Sheets credential tests were not run in this environment.

## [1.0.13] - 2026-11-21

### Added
- Optional focused Gemini unit-rate pass for user-provided BoQ rows that remain unpriced after the initial visual RAB call.
- Separate three-band unit-rate estimates (low/conservative/high); conservative rate remains the value used by Python.
- Detailed documentation for user BoQ pricing and analysis-to-active lifecycle integration.

### Fixed
- Gemini RAB rows can now map to user-supplied BoQ by exact normalized work-item name when the model omits the stable item code; Python still preserves the user's quantity and unit.
- Prevent a user BoQ row matched by name from being re-injected as a duplicate unpriced row.
- Assumption-based interior ceiling repair remains conditional even if its description mentions water ingress; it is not treated as observed interior damage.
- Dashboard and active project views consume the analysis-derived opening budget when a stored prospect becomes WON/ACTIVE, while preserving the original pre-bid decision and cash snapshot as history.

### Compatibility
- No Google Sheets tab names or existing data columns are removed or renamed.
- Existing `PROJECT_BUDGETS`, `COST_ACTUALS`, `PROPERTIES` and analysis snapshots are reused; no destructive migration.
- Manual/onboarding budgets are not merged automatically with analysis baselines, to prevent double counting.

### Verification
- `python -m compileall -q .`: passed.
- `pytest -q`: 136 passed.
- Live Google Sheets, Streamlit Cloud and Gemini API calls were not run in this environment.

# Changelog

## [1.0.12] - 2026-11-21

### Fixed
- Renovation category inference now honours an explicit primary classification in the user's description and ignores a later conditional caveat that says it may become heavier after inspection.
- Local canopy/roof, damp-wall and rabat-carport work scopes now suppress overlapping generic roof/wall/floor tasks to prevent duplicate budgeting.
- Photo-based quantities for bespoke local defects remain blank until measured; AI-proposed custom quantities are never accepted as measured quantities.
- Structural work is not introduced for a medium renovation merely because the risk notes mention possible hidden structural damage. Heavy structural scope remains engineer-led.
- Partial RAB subtotal is explicitly separated from a complete RAB. Unpriced base-budget work keeps the analysis provisional/HOLD instead of making total capital look complete.
- Bid ladder cannot issue a target ROI bid below the auction limit. A below-limit theoretical ceiling is shown separately for diagnostics only.
- Legal bid and walk-away remain blank if the official auction increment has not been confirmed.
- Occupancy status cannot be inferred from photos or belongings; output now carries the user's survey status or explicit unknown status.

### Added
- Regression tests for the TAS 3 M6/12 RAB scenario, overlap prevention, hidden-work/occupancy guardrails, partial RAB completeness, and bid ceilings below the auction limit.
- Logic audit notes and deployment smoke tests for RAB scope, partial totals and bid-ladder validation.

### Changed
- Renovation pricing disclosure explains that AI prices are generic screening estimates, not live Sidoarjo price-book rates or contractor quotes unless those sources have been supplied.
- RAB documentation clarifies when inspections, conditional works and user-measured quantities enter the base budget.

### Compatibility
- No existing Google Sheets tab is renamed or removed. Existing table/column schema is unchanged by this audit patch; new AI explanatory fields are contained within existing JSON payloads.
- Existing underwriting snapshots and ledger records remain readable.

### Verification
- `python -m compileall -q .`: passed.
- `pytest -q`: 122 passed.
- Live Google Sheets, Streamlit Cloud and live Gemini calls are not run in this environment.

## [1.0.11] - 2026-11-21

### Added
- Dashboard portfolio budget visibility: active-project budget total, paid actual, unpaid commitment and remaining forecast by property.
- Paid-cost transaction correction form with explicit user confirmation, same transaction ID, before/after audit log, and safe reversal/reapplication of linked commitment/forecast balances.
- Confirmation checkboxes before saving project progress, new/edit budget items, paid transactions, milestones and closing lifecycle changes.
- Date picker controls cover auction date, deposit deadline, payment deadline, SHGB expiry, milestones, comparable publication date and date found; missing dates remain blank and day/month parsing is preserved.
- Condition-driven renovation RAB metadata: observed visual findings, causes to verify, interior unknowns, inspection plan and separate interior scenarios.
- Description-triggered RAB tasks for localized front canopy/roof damage, damp walls, carport floor cracks, fence repaint and front-area cleanup.

### Changed
- Active project budget editing and budget creation are collapsed by default; tables remain read-only unless the user explicitly opens an edit/add section.
- Successful paid-transaction, budget-add and milestone saves clear relevant form fields for the next entry.
- Renovation category is treated as a complexity label, not an instruction to replace every roof/floor/ceiling/bathroom in full. Medium renovation no longer forces whole-house scope by default.
- When localized front-roof damage is described, whole-roof quantity hints are disabled; local area must be measured.
- Interior conditions not visible in photos remain unknown. AI may describe separate interior scenarios/allowances, but those are excluded from the base RAB until inspected.
- Corrections to a paid transaction reconcile previously deducted commitment/forecast balances and reject deductions above the available balance rather than silently clipping to zero.

### Compatibility
- No Google Sheets tab names, column headers or existing column order changed.
- Existing COST_ACTUALS and PROJECT_BUDGETS fields are reused; no destructive migration.
- Existing RAB item rows and underwriting snapshots remain readable. New Gemini RAB fields are additive JSON payload fields.

### Verification
- `python -m compileall -q .`: passed.
- `pytest -q`: 103 passed.
- Live Google Sheets, Streamlit Cloud and live Gemini calls not run in this environment.

## [1.0.10] - 2026-11-20

### Added
- Guided category → subcategory → item/scope forms for historical and ongoing paid transactions and project budgets.
- Date pickers for transaction dates and optional budget due dates.
- Budget item edit form; existing dataframes are read-only views.
- Property name/address/lot-aware selector in Database & History.
- Explicit auction-win transition that preserves previous underwriting snapshots and stores winning price/date/deposit.

### Changed
- Project Onboarding now creates the project record first; historical expenses and budget lines are added through the same guided forms in Active Properties.
- WON and ACTIVE lifecycle statuses are described as separate steps; both remain visible in Active Properties.

### Compatibility
- No existing Google Sheets tab names or existing column order changed.
- Existing ledger fields are reused; no destructive migration.

### Verification
- `python -m compileall -q .`: passed.
- `pytest -q`: 96 passed.
- Live Google Sheets / Streamlit Cloud integration not run.

## [1.0.9] - 2026-11-20

### Added
- Project Onboarding for properties already won/acquired before PFMS adoption; preserves existing analysis snapshots when merging a stored prospect.
- Project Financial Ledger with separate Actual Paid, Committed Unpaid, Forecast Remaining, and risk reserve concepts.
- Active-project budget lines, budget-vs-actual summaries, transaction linking, and automatic reduction of a selected unpaid budget bucket when recording payment.
- New `PROJECT_BUDGETS` Google Sheets tab and additive detail columns in `COST_ACTUALS`; updated workbook template.
- Optional Gemini market-comparable review with bounded, explainable suggestions that require explicit user approval before Python recalculates ARV.
- Wider data-uncertainty range and conservative haircut for small/dispersed comparable samples; extreme observations remain visible and are down-weighted for review.

### Changed
- Market publication date is distinct from user capture date; missing publication date is uncertainty, not a standalone GO hard stop. Five traceable individual URLs with capture dates plus confidence threshold remain required for GO.
- Active-project projected completion cost excludes selling costs; selling cash commitments/forecast remain separately identifiable.

### Compatibility
- Existing auction-analysis workflow, Google Sheets tab names, and existing column order remain intact. New sheet/columns are additive.
- Existing financial acquisition/profit/ROI formulae remain in place; ARV inputs are now more conservative when evidence is sparse.

### Verification
- `python -m compileall -q .`: passed.
- `pytest -q`: 92 passed.
- Live Google Sheets migration and live Gemini API calls were not run in this environment.

## V1.0.7
- Compress long JSON cells using a versioned gzip/base64 marker and transparently decode on read to stay below Google Sheets per-cell character limits.
- Add preflight validation for overlong non-JSON cells.
- Surface Google API HTTP status and response message with tab/range context.
- Catch save errors in the UI and warn that earlier table writes may have succeeded.
- Add round-trip and error-diagnostic regression tests.


## V1.0.0
- Modular Streamlit application for Indonesian auction-property underwriting and full property lifecycle tracking.
- Gemini structured document extraction and facade assessment.
- Manual comparable import, weighted valuation, and conservative/base/optimistic ARV.
- Python cost, ROI, holding, liquidity, risk, decision-gate, and maximum-bid engines.
- Google Sheets database adapter, snapshots, audit history, investor cashflow, active property lifecycle, and closed-project track record.
- 29 baseline unit tests.

## V1.0.1
- Added Gemini structured parser for numbered multi-bullet comparable narratives.
- Fixed Gemini Developer API schema compatibility by removing dynamic `additionalProperties` fields.
- Added partial underwriting: known costs calculate even when ARV is unavailable; profit/ROI remain null.
- Maximum-bid search can expose an economic ceiling below auction limit.
- Preserved the Streamlit integer input fix for cash and auction winning price.

## V1.0.2
- Python detects sequential numbered listing blocks and validates that Gemini returns exactly one comparable row per block; mismatches are rejected.
- Added clear distinction between comparable rows usable for indicative valuation and GO-grade rows with direct listing URL plus capture date.
- Listing freshness uses publication date only; import/capture date is audit metadata, not proof of a new listing.
- Partial KPKNL data can still be analyzed; a preliminary DO NOT BID/WALK AWAY is shown when the available indicative valuation proves the economic ceiling is below the auction limit.
- Added regression tests for parser section-count control, source traceability, conservative recency, and partial-data walk-away.
- Current test suite: 42 passed; Python compile check passed.

## V1.0.3 — Google Sheets JSON safety, AI-assisted RAB & guided risk register

- Fixed Google Sheets writes by normalizing every worksheet cell, including Pandas `NaN`, NumPy non-finite scalars, `pd.NA`, and `NaT`, before gspread serializes the request. Nested JSON payloads use strict `allow_nan=False` serialization.
- Added one-click AI-assisted renovation RAB drafting from the auction screenshot/PDF, up to five survey photos, current condition description, and property context. Gemini returns itemized work, quantities, unit ranges, conservative unit cost, evidence basis, confidence, assumptions, and inspection items.
- Conservative unit cost is prefilled into the existing Python RAB calculation column. The RAB stays editable and requires user review; the AI does not infer hidden structural/interior damage or claim live contractor quotations.
- Simplified risk register entry with selectable common-risk presets and editable suggested probability, impact, cash reserve, mitigation, and status.
- Risk and cost review confirmations are invalidated automatically when their respective input rows/values change.
- Added regression tests for Sheets JSON sanitation, direct gspread row serialization, Gemini RAB schema, conservative unit-cost mapping and partial RAB totals. Current test suite: 49 passed; Python compile check passed.


## V1.0.4 — Comparable parser hardening
- Support Markdown bold/link numbered headings such as `**1. [Title](URL)**`.
- Compact aliased Pydantic schema reduces JSON output size for multi-listing extraction.
- Increase comparable parser output allowance and batch larger input sets.
- Capture exact URLs deterministically from each original listing block; ignore Google kgmid links.
- Inspect Gemini finish reason and report MAX_TOKENS/truncated JSON explicitly; never load partial rows.
- Add regression tests for seven-listing Markdown input, URL mapping and MAX_TOKENS handling.

- Track `source_url_scope`; portal/category/venue URLs no longer count as individual listing URLs for GO-grade market evidence.


## V1.0.6 — Form restore & context-aware renovation estimator
- Hardened form restoration: deep-merge current input and latest analysis (including older/flat payload aliases) for bedrooms, bathrooms, property type, floor count, road width/access, and general physical condition. Missing values clear instead of leaking from the previously loaded property.
- Added optional ground-floor footprint input; roof quantities use measured footprint when available, otherwise LB divided by floors as a clearly labelled estimate.
- Renovation context now includes property type, bedrooms, bathrooms, general condition, LT/LB, floor count, road width/access, survey notes and user condition description. Bedroom count only adjusts the wall-area midpoint inside the rough 2.5–3.0 × LB screening band; bathroom count informs per-bath packages.
- Auto category with unknown condition now produces inspection/preparation guidance instead of assuming light renovation. Explicit cosmetic scope makes preparation, wall and ceiling work required; omitted required AI items become unpriced placeholders.
- Added low-confidence local repair allowances for light renovation and explicit warning that they must be measured; structural work remains unquantified until engineer/design review.
- Added regression tests. Current unit test suite: 68 passed; Python compile check passed.

## [1.0.8] - 2026-11-19
### Added
- Investor-facing Indonesian navigation, workflow guidance, progress indicator, market-quality explanation, and detailed capital/cash/selling-cost tables.
- Optional comparable NJOP input and locally calibrated NJOP-to-market reference when at least three comparable price/NJOP pairs are available.
- User-confirmed date-found helper and individual-listing URL attestation.
### Changed
- Missing listing publication dates are treated as uncertainty rather than a GO hard stop; date found remains distinct and required for GO evidence.
- Market confidence >=55 remains the hard threshold; scores below 70 display quality warnings without independently blocking GO.
### Fixed
- Cost and risk review confirmations persist across Streamlit reruns and reset only when their underlying reviewed data changes.

## V1.0.14 — 2026-11-21
- Fixed BoQ parser for Excel/Google Sheets tab-separated paste and flattened plain rows.
- Fixed category inference for explicit labels such as `Kategori Kondisi: Renovasi Sedang`.
- Added pre-Gemini BoQ preview to catch parsing issues before API usage.
- Bumped the RAB cache namespace so old parse results are not reused after this parser upgrade.
- Preserved the user's customised Dashboard layout in the supplied `app.py`.


## [1.0.23] - 2026-11-27
### Fixed
- Fixed NameError in Bidding Ladder by importing `bid_reference_status` from `core.decision_engine`.
- Removed redundant “date already known” checkboxes for auction and deposit dates; KPKNL document extraction pre-fills editable date pickers.
### Added
- Automatic payment deadline using five working days after ordinary auctions under PMK 122/2023 Article 88, with regulatory exceptions and a 2026–2027 Indonesian non-working-day calendar.
- Explicit KPKNL payment deadline takes precedence over the calculated deadline.
- Payment deadline basis and KPKNL source filename are carried into the saved property record and Investment Proposal.
