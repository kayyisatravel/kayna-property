# PFMS V1.0.3 — Patch notes

## Masalah 1 — `requests.exceptions.InvalidJSONError` saat menyimpan comparable/risk/RAB

Penyebab: blank numeric cells from `st.data_editor` become Pandas `NaN`. The old Sheets adapter sanitized nested JSON payloads but passed direct worksheet cell values unchanged to gspread. `requests` rejects `NaN`/`Infinity` because it serializes JSON with `allow_nan=False`.

Perbaikan:
- `core/utils.py`: added `json_safe_value()` and `sheet_cell_value()`; handles `NaN`, positive/negative infinity, NumPy scalars, `pd.NA`, `pd.NaT`, Decimal and dates.
- `storage/gsheets_db.py`: `_row_values()` sanitizes every cell before `append_row`, `append_rows` or `update`.
- Nested `payload_json`/`value_json` continue to use strict JSON (`allow_nan=False`).

## Fitur 2 — AI-assisted renovation RAB

- `services/gemini_parser.py`: added fixed Pydantic schema `RenovationRabExtraction`, `estimate_renovation_rab()` and `renovation_estimate_to_rows()`.
- Supports the KPKNL screenshot/PDF plus up to five survey photos and the user's current condition description in one explicit Gemini request.
- Uses `unit_cost_conservative` in the existing Python `unit_cost` field. Lower and upper unit rates, evidence basis, confidence and notes remain visible/editable.
- Hidden damage is not invented. Items requiring inspection are listed separately.
- RAB is a draft, uses indicative (not live vendor) pricing and must be reviewed. Missing volume/unit costs make the total partial, not silently zero.
- `app.py`: added RAB description field, generate button, same-input session cache, RAB summary, editable expanded table, and persistence of AI estimate in cost payload.

## UX 3 — Guided risk register

- `app.py`: added selectable common-risk presets for occupancy, legal, structure, roof, flood, access, renovation overrun, holding delay, market comparables and unpaid utilities.
- Presets prefill editable probability, impact, reserve estimate, criticality and mitigation.
- The suggested reserves are planning placeholders, not official tariffs.
- Risk and cost review confirmations are reset whenever their underlying inputs change.

## Files changed

- `app.py`
- `core/utils.py`
- `services/gemini_parser.py`
- `storage/gsheets_db.py`
- `tests/test_gsheets_sanitization_and_rab.py`
- `README.md`
- `CHANGELOG.md`
- `docs/CALCULATION_RULES.md`
- `docs/USER_GUIDE.md`
- `docs/DEPLOYMENT_SMOKE_TEST.md`

## Apply

Recommended: replace the repository contents with the complete V1.0.3 package. If applying as a patch, preserve the folder structure and upload each changed file to the matching path. Do not upload `.streamlit/secrets.toml` or account credentials.
