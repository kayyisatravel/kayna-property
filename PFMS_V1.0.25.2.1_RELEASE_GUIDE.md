# PFMS V1.0.25.2.1 — Release & Deployment Guide

## Recommended upgrade
Use `pfms-v1.0.25.2.1-data-editor-fix-patch.zip` on top of the deployed PFMS V1.0.25.2 repository. The patch is an overlay: extract it into the repository root while preserving relative folders. Do not extract into a nested folder.

## Deployment steps
1. Create a GitHub backup/commit of the current deployed V1.0.25.2 source.
2. Extract the patch ZIP into the repository root and allow files to overwrite.
3. Review the changed files in GitHub before committing.
4. Keep `.streamlit/secrets.toml` unchanged. The patch does not include that file.
5. Commit and let Streamlit Cloud redeploy.
6. After startup, open the app and test the flows below.

## Smoke test (recommended order)
1. Open an existing saved property that has a historical Risk Register. Check that old rows display and the `Hard stop terverifikasi?` checkbox is editable. A blank legacy hard-stop value must appear unchecked.
2. Add a risk from the guided preset list; confirm the new row appears and the editor remains editable.
3. Edit probability, impact, cost reserve, Critical and Hard stop fields; navigate away and return to confirm values persist.
4. Load a property with old comparable rows. Confirm name, address, price, area, source, URL, market segment, seller type and promotion columns are retained.
5. Run comparable CSV/TSV import or Gemini parsing, then edit the resulting table.
6. Apply AI comparable review or the date-fill / URL-confirm action and confirm the editor does not restore stale rows.
7. Open Biaya & RAB, generate/import RAB rows, edit quantities/costs and selectboxes, then navigate away and back.
8. Save an analysis and reopen the object to verify Risk, Comparables and RAB remain intact.

## What this patch changes
- Normalizes all three analysis editor dataframes before `st.data_editor` and after editing.
- Handles legacy all-null checkbox fields inferred as float, not only `hard_stop_confirmed`.
- Uses fresh widget keys for changed schemas to avoid stale UI state.
- Preserves the complete comparable editor schema on saved-property load.
- Safely parses textual boolean values from older persisted records.

## Compatibility
- No Google Sheets worksheet/tab, header or schema migration.
- Historical analysis payloads are not rewritten; normalization occurs in application memory.
- No changes to underwriting, MAO, Gemini or financial policy.
- `.streamlit/secrets.toml` remains untouched.

## Validation status
Local compile passed; automated regression suite **289/289 passed**; ZIP CRC and forbidden-file checks passed. The Streamlit Cloud app, live Google Sheets and Gemini API were not available for integration testing in this environment. Run the smoke test above after deployment.
