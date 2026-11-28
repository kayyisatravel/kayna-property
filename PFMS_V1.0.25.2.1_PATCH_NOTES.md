# PFMS V1.0.25.2.1 — Data Editor Runtime Compatibility Fix

## Issue
Saat membuka langkah Survei & Risiko, Streamlit menghentikan aplikasi dengan pesan bahwa `CheckboxColumn` untuk `hard_stop_confirmed` tidak cocok dengan tipe data `float`. Penyebabnya adalah baris Risk Register tersimpan dari versi lama dengan nilai kosong pada kolom checkbox. Ketika Pandas membentuk DataFrame dari data tersebut, kolom all-null dapat diinferensikan sebagai `float64`, sedangkan Streamlit mengharuskan kolom checkbox bertipe boolean.

## Changes
1. Added `core/editor_normalization.py` with explicit schemas and dtype normalization for all three `st.data_editor` inputs:
   - Risk Register: `critical` and `hard_stop_confirmed` are always `bool`; scores/reserves are numeric; status is constrained to supported options.
   - Comparable listings: both checkbox columns are always `bool`; price/area/coordinate fields are numeric; dates are Python `date` values; selectboxes are normalized.
   - Renovation RAB: quantity/cost fields are numeric; selectbox values are normalized; text columns are stable.
2. Normalize frames both when loading stored objects and immediately before each editor; normalize edited output again before using or persisting it.
3. Bump widget keys/schema markers and clear the current keys when preset/import/AI actions replace the underlying rows. This avoids stale Streamlit widget state being applied to the normalized schema.
4. Correct saved-comparable loading to preserve the full editor schema, including fields previously omitted by the narrower load-time column list.
5. Added safe boolean parsing for legacy values such as `"False"`, `"0"`, `"Tidak"`, `"True"` and `"Ya"` in risk and market calculations.
6. Update application version to `1.0.25.2.1`.

## Scope / compatibility
- No changes to underwriting thresholds, MAO formula, Gemini prompts, UI layout, business workflow, Google Sheets worksheet names, headers or schema.
- Existing stored rows are normalized in memory when loaded; original history is not mass-rewritten.
- New module and tests are included.
- `.streamlit/secrets.toml` is not included or overwritten.

## Verification
- `python -m py_compile` passed for application and Python modules.
- `pytest -q`: **289 passed**.
- Tests reproduce the legacy all-null checkbox column that becomes `float64`, confirm it becomes `bool`, cover the other checkbox columns, legacy string booleans, empty dataframes, placeholder rows, numeric/date/selectbox types, and ensure all three data editors are wired to normalized frames.
- ZIP integrity and package-content checks passed.

## Known limitation
The local execution environment did not have Streamlit installed, so a live Streamlit widget render was not performed. Streamlit Cloud + the user's Google Sheets records and secrets must still be smoke-tested after deployment. This patch addresses the reported dtype incompatibility and adjacent data-editor schema paths, but cannot promise that no unrelated runtime error can ever occur.
