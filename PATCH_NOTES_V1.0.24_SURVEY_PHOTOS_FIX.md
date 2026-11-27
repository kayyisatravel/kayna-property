# PFMS V1.0.24 — Survey Photos Step 2 → Step 4 Fix

## Scope
Single targeted runtime fix for the sequential New Auction Analysis workflow.

## Problem
When moving from Step 2 (Survei & Risiko) to Step 4 (Biaya & RAB), `survey_photos` was a local variable created only while Step 2 was rendered. Step 4 and the save routine still referenced that local variable, causing:

`NameError: survey_photos is not defined`

## Fix
- Before leaving Step 2, copy selected survey photos into `st.session_state["na_survey_photo_payloads"]` as bytes + MIME type + filename.
- Added `_get_survey_photo_payloads()` to read the persisted payload safely.
- Step 4 RAB now uses the persisted photo payloads (maximum 5 as before).
- Database save routine now uses the same persisted payloads.
- Existing Step-2 uploader key `na_survey_photos` is unchanged.
- No Google Sheets schema changes.
- No changes to underwriting rules, scoring, UI layout, or existing business logic beyond the runtime-safe photo state handoff.

## Validation
- `python -m py_compile` passed for the modified `app.py`.
- No `.streamlit/secrets.toml` included.
- This patch does not claim live Streamlit Cloud / Google Sheets / Gemini integration testing.
