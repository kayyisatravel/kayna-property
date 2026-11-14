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
