# PFMS V1.0.20 — Patch Notes

## Proposal document
- Rename `Memorandum Investasi Properti` to `Proposal Investasi Properti`.
- Increase spacing between Kayna Property header and document body.
- Restore V1.0.18-like clean table design while retaining navy colours and minimum 11 pt font.
- Comparable table: full address | asking price | LT/LB | URL/source.
- Capital and selling-cost/profitability tables use numeric bid value as the first column. Strategy table also uses numeric bid values.
- Keep detailed RAB subtotals in full Rupiah, total row and task-level duration estimates.

## Active project progress
- Calculate duration-weighted physical progress from renovation work-item status in `PROJECT_BUDGETS`.
- Show status tracking coverage.
- Show “Belum diperbarui” rather than 0% when work statuses have not been entered.
- Do not infer physical progress from cash expenditure.
- Retain project milestones as fallback when measurable work rows are unavailable.

## Completed projects
- Improve separation of closing date, gross sale price, actual capital, selling costs, net profit and realized ROI.
- Include all known sale-cost categories in realized project financials.

## Compatibility
- No destructive Google Sheets schema changes.
- User credentials and `.streamlit/secrets.toml` are excluded.
- No new Gemini call required for proposal generation.

## Tests
- 198 tests passed. Python compilation succeeded. Full and patch packages validated separately. Live API/Streamlit credentials not tested.
