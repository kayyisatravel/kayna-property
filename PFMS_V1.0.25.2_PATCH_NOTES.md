# PFMS V1.0.25.2 — AI Feasibility Co-Pilot

## Purpose

Reframes PFMS from a rigid eligibility checklist into an AI-assisted feasibility study workflow. Python remains the numeric source of truth, Gemini Flash provides senior-analyst interpretation, and the Owner retains final decision authority.

## Main changes

1. **Three independent outputs:** model reference status, Bid Readiness and Owner decision/rationale. The Owner may choose differently; overrides of confirmed hard stops are explicitly highlighted.
2. **Gemini Feasibility Brief:** one-click flow runs Python underwriting first, then asks Gemini Flash to explain financial strength, market evidence, execution friction, assumptions, scenarios, risks, mitigations and Owner options. Gemini is not allowed to invent or replace Python financial values.
3. **Incomplete market data:** Owner may enter FMV as-is / ARV after repair without listing comps, with a basis note. One or two relevant comps remain visible as provisional diagnostics. Mixed-condition listings are not silently treated as ARV comps.
4. **Interior / building condition uncertainty:** Owner can record visual structural assessment and building age, then include a hidden-condition reserve. Lack of interior access becomes an explicit assumption/readiness item, not an automatic investment HOLD.
5. **Incomplete renovation access:** unverified scope allowance is added to renovation cost; contingency is applied to the renovation budget. Unpriced scope without an allowance stays clearly flagged.
6. **Cash timing:** additional funds can be recorded with amount, date, source and status. Planned/unconfirmed funds are not counted; commitments remain provisional until cleared; post-auction funds do not count for bidding.
7. **SKPT/KPKNL review:** Owner's SKPT check and object matching are recorded. Original certificate handover is retained as administrative/post-award follow-up, not a second legal veto where identity/SKPT has been verified.
8. **Decision logic:** incomplete but priceable frictions generally produce CONDITIONAL GO with caveats. HOLD is reserved for no defensible exit basis, insufficient economic return, excessive horizon, or material unknowns that cannot yet be priced. DO NOT BID requires a confirmed hard stop or strong structural economic failure.
9. **Scenario analysis:** deterministic Fast / Moderate / Stress cases and sensitivity inputs are presented. These are not probability-weighted Expected Value forecasts.
10. **Memorandum and storage:** AI brief, Owner decision and notes are included in the report and saved within the existing analysis payload. No Google Sheets tab/header/schema migration.

## What remains unchanged

- Existing sequential analysis workflow and primary application navigation.
- Google Sheets tabs and headers.
- Gemini default model configuration (`gemini-3.5-flash-lite`).
- V1.0.26 Auction Lifecycle and V1.0.27 same-property / different-Lot-Code detection are not included.
- `.streamlit/secrets.toml` is not included or overwritten.

## Validation

- `pytest -q`: **280 passed**.
- Python compilation and AST checks: passed (to be reconfirmed at packaging).
- ZIP integrity / package-content checks: to be recorded after archive creation.
- Live Streamlit Cloud, Google Sheets and Gemini integration was not performed because the deployment runtime and credentials are not available in this environment.
