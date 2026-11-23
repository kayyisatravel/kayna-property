# PFMS V1.0.15 — Auction RAB Allowances & Geographic Comparables

## Main fixes
- Explicit user BoQ rows remain in the cost allowance, even when some work areas are hidden or access-restricted. Missing quantity-basis prose no longer marks otherwise measurable user-entered work as conditional.
- Hidden interior/MEP scopes are retained with low confidence. The system separates inspection costs from repair allowances and applies a configurable hidden-condition reserve when interior is not inspected.
- Python regional screening catalogue fills common work-item rates using compatible units and low/base/high values. It does not overwrite user quantity or silently convert units.
- User BoQ scopes suppress duplicate visual guidance where the same work is already budgeted (e.g., canopy frame included in new canopy installation; gate repaint already listed).
- Interior scenarios are described as sensitivities, not automatic additions to base RAB.
- Comparable evaluation can use coordinate distance across village/district/project boundaries. Distance is Haversine straight-line distance; 500m comparables receive top proximity score.
- Similarity adds bedrooms, bathrooms, road width and orientation. Users can add reasoned adjustment percentages; AI advice remains reviewable rather than auto-applied.
- All metric rows use at most four columns. Custom dashboard metric for active-project realised budget is preserved.

## TAS 3 screening regression
Using the 16-item TAS 3 M6/12 BoQ and a mock Gemini response with no item rates, Python fills all 16 compatible BoQ rates and adds two distinct inspection allowances (terrace ceiling/rangka and interior). No duplicate fence-paint or canopy-frame rows are added.

| Measure | Result |
|---|---:|
| BoQ rows priced | 16 / 16 |
| In-scope rows, including 2 inspections | 18 / 18 |
| Screening range low | Rp36.372.000 |
| Screening base | Rp52.261.000 |
| Screening range high | Rp72.757.000 |

The total above excludes ordinary renovation contingency, hidden-condition reserve, auction/acquisition, possession, legal, holding and selling costs. Catalog rates remain screening assumptions—not verified local contractor quotes or official private-project HSPK.

## Verification
- `pytest -q`: 150 passed.
- `python -m compileall -q .`: passed.
- ZIP integrity checked at packaging.
- Live Streamlit Cloud / Gemini / Google Sheets credential calls were not performed.

## Compatibility
- No existing Google Sheets tab names or headers were removed/renamed.
- No credentials or `.streamlit/secrets.toml` are included.
- Upgrade is additive; backup existing repository before overlaying the patch.
