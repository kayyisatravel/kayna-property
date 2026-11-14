# Changelog

## V1.0.0
- Modular Streamlit application for Indonesian auction-property underwriting and full property lifecycle tracking.
- Gemini structured document extraction and facade assessment.
- Manual comparable import, weighted valuation, and conservative/base/optimistic ARV.
- Python cost, ROI, holding, liquidity, risk, decision-gate, and maximum-bid engines.
- Google Sheets database adapter, snapshots, audit history, investor cashflow, active property lifecycle, and closed-project track record.
- 29 baseline unit tests.

## V1.0.1
- Added Gemini structured parser for numbered multi-bullet comparable narratives.
- Fixed Gemini Developer API schema compatibility by removing dynamic `additionalProperties` fields.
- Added partial underwriting: known costs calculate even when ARV is unavailable; profit/ROI remain null.
- Maximum-bid search can expose an economic ceiling below auction limit.
- Preserved the Streamlit integer input fix for cash and auction winning price.

## V1.0.2
- Python detects sequential numbered listing blocks and validates that Gemini returns exactly one comparable row per block; mismatches are rejected.
- Added clear distinction between comparable rows usable for indicative valuation and GO-grade rows with direct listing URL plus capture date.
- Listing freshness uses publication date only; import/capture date is audit metadata, not proof of a new listing.
- Partial KPKNL data can still be analyzed; a preliminary DO NOT BID/WALK AWAY is shown when the available indicative valuation proves the economic ceiling is below the auction limit.
- Added regression tests for parser section-count control, source traceability, conservative recency, and partial-data walk-away.
- Current test suite: 42 passed; Python compile check passed.

## V1.0.3 — Google Sheets JSON safety, AI-assisted RAB & guided risk register

- Fixed Google Sheets writes by normalizing every worksheet cell, including Pandas `NaN`, NumPy non-finite scalars, `pd.NA`, and `NaT`, before gspread serializes the request. Nested JSON payloads use strict `allow_nan=False` serialization.
- Added one-click AI-assisted renovation RAB drafting from the auction screenshot/PDF, up to five survey photos, current condition description, and property context. Gemini returns itemized work, quantities, unit ranges, conservative unit cost, evidence basis, confidence, assumptions, and inspection items.
- Conservative unit cost is prefilled into the existing Python RAB calculation column. The RAB stays editable and requires user review; the AI does not infer hidden structural/interior damage or claim live contractor quotations.
- Simplified risk register entry with selectable common-risk presets and editable suggested probability, impact, cash reserve, mitigation, and status.
- Risk and cost review confirmations are invalidated automatically when their respective input rows/values change.
- Added regression tests for Sheets JSON sanitation, direct gspread row serialization, Gemini RAB schema, conservative unit-cost mapping and partial RAB totals. Current test suite: 49 passed; Python compile check passed.


## V1.0.4 — Comparable parser hardening
- Support Markdown bold/link numbered headings such as `**1. [Title](URL)**`.
- Compact aliased Pydantic schema reduces JSON output size for multi-listing extraction.
- Increase comparable parser output allowance and batch larger input sets.
- Capture exact URLs deterministically from each original listing block; ignore Google kgmid links.
- Inspect Gemini finish reason and report MAX_TOKENS/truncated JSON explicitly; never load partial rows.
- Add regression tests for seven-listing Markdown input, URL mapping and MAX_TOKENS handling.

- Track `source_url_scope`; portal/category/venue URLs no longer count as individual listing URLs for GO-grade market evidence.


## V1.0.6 — Form restore & context-aware renovation estimator
- Hardened form restoration: deep-merge current input and latest analysis (including older/flat payload aliases) for bedrooms, bathrooms, property type, floor count, road width/access, and general physical condition. Missing values clear instead of leaking from the previously loaded property.
- Added optional ground-floor footprint input; roof quantities use measured footprint when available, otherwise LB divided by floors as a clearly labelled estimate.
- Renovation context now includes property type, bedrooms, bathrooms, general condition, LT/LB, floor count, road width/access, survey notes and user condition description. Bedroom count only adjusts the wall-area midpoint inside the rough 2.5–3.0 × LB screening band; bathroom count informs per-bath packages.
- Auto category with unknown condition now produces inspection/preparation guidance instead of assuming light renovation. Explicit cosmetic scope makes preparation, wall and ceiling work required; omitted required AI items become unpriced placeholders.
- Added low-confidence local repair allowances for light renovation and explicit warning that they must be measured; structural work remains unquantified until engineer/design review.
- Added regression tests. Current unit test suite: 68 passed; Python compile check passed.
