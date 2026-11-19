# PFMS V1.0.8 — Review confirmation, market evidence, NJOP calibration, and investor-facing UX

## Baseline and compatibility

This release is based on the user-uploaded `property-flipper-management-system-v1.0.7.zip`.

- Existing Google Sheets tab names and headers are preserved.
- No migration or replacement of existing property, analysis, survey, cost, risk, comparable, cash, or history records is required.
- Existing JSON payload fields remain readable. New comparable NJOP fields and the NJOP weighting rule are optional additions in existing payload/config JSON.
- Existing Streamlit Secrets are not changed. Do not upload `.streamlit/secrets.toml` to GitHub.
- This release does not add OAuth or change Google Drive authentication/storage behavior.
- Existing Gemini model and request flow remain in place; the new UI controls do not make extra Gemini calls.

## Fixes and improvements

### 1. Review checkboxes
- Fixed Streamlit rerun behavior that could reset cost and risk review checkboxes before the user's click was retained.
- Review confirmations now remain checked while the reviewed data fingerprint remains unchanged.
- A material change in cost/tax/RAB inputs resets the cost confirmation; a material change in risk rows resets risk confirmation.
- Added unit tests for initialization, reruns, and invalidation after edits.

### 2. Comparable evidence and dates
- Clarified that listing publication date is optional and is not the same as the date found/collected.
- Added an explicit action to fill missing `date_found` values with the date the user records the market research, labelled as user-confirmed capture date.
- Added an explicit user confirmation step for URLs that the user has opened and verified as individual property listings. The action does not classify search/category or venue pages as individual listings.
- Missing publication dates now reduce evidence quality moderately, but do not independently prevent GO if other agreed evidence gates pass.
- Confidence under 70 is displayed as a quality warning, while the agreed threshold of 55 remains the minimum market confidence hard gate.
- The GO evidence gate still requires at least five usable comparable records, five direct individual listing URLs with a capture date, and confidence >=55.

### 3. NJOP as a calibrated secondary reference
- Added optional NJOP input on comparable rows and extraction/import aliases.
- The subject property's NJOP is not treated as market value and is not multiplied by an arbitrary universal factor.
- When at least three comparable rows contain both price and NJOP, Python derives a weighted local market-to-NJOP ratio and estimates an NJOP-indicated value for the subject property.
- The NJOP indication is blended into Base ARV using a configurable weight (default 10%, configurable up to 25%). If fewer than three paired observations exist, NJOP remains a visible reference and is not blended into ARV.
- The comparable-based ARV remains separately visible so the investor can see both bases.

### 4. Investor-facing financial explanation
- Added itemized capital breakdown: bid, buyer auction fee, BPHTB basis and amount, BPN/roya/admin/legal items, possession, renovation, contingency, holding, marketing, other pre-sale costs, and total project capital.
- Added separate tables for risk reserves, investor cash availability, selling costs, net proceeds, and net profit.
- Clarified that risk reserve is liquidity protection, not a project expense until spent; selling costs are deducted from proceeds, not double-counted in pre-sale capital; and deposit timing must be tracked separately.

### 5. User experience
- Updated the navigation labels and headings to clearer Indonesian wording while retaining internal page routing.
- Added a non-blocking workflow progress indicator and short onboarding guidance to the new analysis page.
- Reorganized result presentation around key investment metrics, market evidence, detailed financial breakdown, blockers, warnings, and definitions of decision statuses.
- Added Indonesian explanations and simplified wording for the primary data-entry tasks.

## Verification

- `python -m compileall -q .`: passed.
- `pytest -q`: 82 passed.
- These are local automated checks only. This release has not been live-tested against the user's Streamlit Cloud deployment, Google Sheets credentials, Gemini API key, or actual auction/comparable data.

## Deployment caution

Back up the current GitHub repository before applying this patch. Apply only the files listed in the upgrade patch; preserve the current `.streamlit/secrets.toml` in Streamlit Cloud. Do not overwrite secrets or replace the active deployment until the patch has been reviewed and smoke-tested.
