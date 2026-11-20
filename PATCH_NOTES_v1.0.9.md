# PFMS V1.0.9 — Project Onboarding, Project Ledger & AI-Assisted Market Review

## New capabilities

- New **Daftarkan Proyek Berjalan / Project Onboarding** page for properties already acquired or acquired before PFMS adoption.
- Existing prospect records can be merged by lot code; existing analysis snapshots are preserved.
- Onboarding stores paid opening transactions and separate budget/commitment/forecast line items.
- Active Properties now shows paid actual, unpaid commitment, forecast remaining, and projected completion cost, with editable budget lines and detailed payment ledger.
- Actual payments can be linked to budget items and reduce either the selected outstanding commitment or forecast bucket.
- Confirmed unpaid commitments from active project budgets automatically reduce investor cash availability.
- Google Sheets gets a new `PROJECT_BUDGETS` tab; `COST_ACTUALS` receives additive trailing detail columns.
- Gemini-assisted comparable review suggests relevance, data gaps, outlier flags and bounded price adjustments. Suggestions require user approval before application.
- Python market engine returns wider conservative haircut/range when the comparable sample is sparse or dispersed and flags extreme outliers for review/down-weighting.

## Compatibility / preserved behavior

- Existing auction-analysis workflow remains the primary path for new auction opportunities.
- Existing Google Sheets tab names and existing column order are not changed. New fields are appended to `COST_ACTUALS`; `PROJECT_BUDGETS` is a new worksheet.
- Existing `PROPERTIES`, `ANALYSIS_HISTORY`, `COMPARABLES`, `COST_ESTIMATES`, `RISK_REGISTER`, lifecycle, and history records remain readable.
- Existing calculation engine continues to calculate auction acquisition, BPHTB, renovation, contingency, holding, sale costs, profit and ROI. Market engine retains weighted-median basis and local NJOP pairing guard.
- No Google Drive/OAuth archive dependency added.

## Important financial rules

- Winning price in onboarding is descriptive. Actual acquisition cash-out must be entered in the paid transaction table.
- Deposit must not be double-counted against winning price.
- Actual, committed-unpaid, forecast, and risk reserve are kept separate.
- Do not enter the same active-project budget commitment again as a manual cashflow event.
- Listing price is not a verified transaction. The AI review does not invent missing market evidence.

## Tests

- `python -m compileall -q .`: passed.
- `pytest -q`: 92 passed.
- Live Gemini calls and live Google Sheets migration were not executed in this environment.
