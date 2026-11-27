# PFMS V1.0.25.2 — Release Guide

## Recommended deployment path

This patch is designed for the GitHub repository running V1.0.25 (automatic ranking). It includes the V1.0.25.1 underwriting correction plus the V1.0.25.2 Co-Pilot updates, so you do not need to apply the earlier V1.0.25.1 patch separately.

1. Back up the current GitHub repository / create a branch from the working V1.0.25 deployment.
2. Extract `pfms-v1.0.25.2-ai-feasibility-copilot-upgrade-patch.zip` into the repository root and allow the relative paths to merge/overwrite.
3. Do **not** overwrite `.streamlit/secrets.toml`. The patch includes only the example secrets file, not a real credential file.
4. Commit and push. Check Streamlit Cloud deployment logs for startup/runtime errors.
5. Confirm the app displays version V1.0.25.2.

If the repository has custom changes beyond the supplied release, review the patch files before merging. The full-source ZIP is available as a clean reference project; do not overwrite user secrets or manually maintained data files.

## First smoke test

1. Open an existing property and run a feasibility study with existing comparable data.
2. Run another study with no comparable listings but enter an Owner ARV and its basis. Confirm the value is shown as `OWNER_INPUT` / provisional, not as a verified comparable.
3. Enter one or two condition-matched comparables. Confirm the indicative estimate remains visible and low sample is disclosed.
4. Mark interior as not inspected, enter building age / visual assessment and an explicit hidden-condition reserve. Confirm it becomes a priced condition, not an automatic HOLD.
5. Leave one renovation scope unmeasured and enter an unverified scope allowance. Confirm it appears in total renovation cost and contingency.
6. Add expected cash with a date before auction and status `Komitmen terkonfirmasi`. Confirm it is projected but remains `NOT READY — CASH CONFIRMATION` until cleared. Then test a planned/unconfirmed amount and an amount after auction; neither should be counted as bid-day cash.
7. Mark SKPT verified with a note. Confirm identity matching is recorded and original certificate handover appears as an administrative warning, not a duplicate legal readiness blocker.
8. Confirm the screen contains separate Model Reference Status, Bid Readiness, AI Feasibility Brief and Owner Decision.
9. Choose an Owner decision different from the model and enter a rationale. Download both Markdown and Word memoranda; confirm the Owner decision and rationale are included.
10. Save the analysis and confirm it is visible in existing history. No new Sheets tab/header should be created.

## Expected interpretation

- No comparable and no Owner ARV / FMV basis: PFMS cannot responsibly calculate ROI/MAO; HOLD is expected.
- No comparable but an Owner ARV estimate with a stated basis: provisional financial scenarios can be calculated; the market evidence remains low-confidence and Bid Readiness is not automatically READY.
- Incomplete but costed renovation scope: included through allowance and contingency; return is provisional until scope is inspected/quoted.
- Cash shortage: affects Bid Readiness, not the underlying investment attractiveness.
- Confirmed fatal legal/security/access/environmental hard stop: model reference DO NOT BID, with explicit warning if Owner overrides it.

## Test boundary

Local tests and static checks do not prove that Streamlit Cloud, Google Sheets credentials, or the live Gemini API work in the user's deployment. Please test those integrations in the deployed application before relying on it for an actual auction.
