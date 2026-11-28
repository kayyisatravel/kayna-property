# Streamlit Data Editor Type Safety — PFMS V1.0.25.2.1

Each `st.data_editor` column has a pandas dtype contract. A `CheckboxColumn` must be backed by boolean data; `NumberColumn` by numeric data; `DateColumn` by date values; `SelectboxColumn` values must be compatible with the configured options. Legacy rows with missing values may cause Pandas to infer a nullable checkbox column as `float64`.

PFMS now applies normalization to Risk Register, Comparable and Renovation RAB frames at load/render boundaries. The same normalization is applied to the returned edited dataframe before scoring, market valuation, RAB calculations or serialization.

| Editor | Checkbox fields | Numeric fields | Selectbox/date fields |
|---|---|---|---|
| Risk Register | `critical`, `hard_stop_confirmed` → bool | probability, impact, reserve → float | status → allowed risk states |
| Comparables | `promotion_value_verified`, `ai_exclude_from_primary` → bool | price, areas, coordinates, etc. → float | segments/condition/access/price type → allowed options; listing dates → date |
| Renovation RAB | none | quantities and unit costs → float | priority/evidence/confidence → allowed options |

Widget keys are versioned when the schema changes. The application clears the current key before rerunning after import, preset insertion or AI actions that replace dataframe contents. This prevents stale widget state from being reapplied to the new schema.

Legacy boolean text is parsed semantically (`false`, `0`, `tidak` → false; `true`, `1`, `ya` → true); unknown values default to false for safety.
