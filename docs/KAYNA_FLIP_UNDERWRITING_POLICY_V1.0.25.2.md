# KAYNA Property — Underwriting & Co-Pilot Policy V1.0.25.2

**Release:** PFMS V1.0.25.2  
**Policy purpose:** provide a feasibility reference and explicit trade-offs while preserving Owner authority.

This policy is an internal underwriting framework. It is not a formal appraisal, legal opinion, tax opinion, engineering inspection, official auction instruction or guarantee of sale price.

## 1. Authority and outputs

PFMS presents three independent outputs:

- **Model Reference Status:** GO, CONDITIONAL GO, HOLD, DO NOT BID.
- **Bid Readiness:** READY / NOT READY with outstanding execution items.
- **Owner Decision:** GO, CONDITIONAL GO, HOLD, SKIP, DO NOT BID, or Belum diputuskan, with Owner rationale.

The model does not replace the Owner. If the Owner differs from the model, the decision and rationale are saved separately. An override of a confirmed hard stop remains prominently warned and should receive independent technical/legal review.

## 2. Status meanings

### GO

Strong economic case under the recorded assumptions, normally with Project ROI ≥25%, minimum net project profit Rp50 million, holding ≤180 days, no unresolved material friction, and strong market evidence. These are default policy thresholds, not universal market laws.

### CONDITIONAL GO

Fundamentally attractive or reasonably investable when frictions are assigned a price, allowance, mitigation path or explicit risk tolerance. Examples: ROI 15% to below 25%; one or two condition-matched listings; Owner valuation with stated basis; occupied but manageable possession; medium/heavy renovation with RAB; inaccessible interior with a hidden-condition reserve; incomplete accessible RAB scope represented by allowance; or a longer but bounded holding period. The brief describes the conditions that remain.

A provisional estimate may support a CONDITIONAL GO reference when there is a defensible exit assumption and positive economics. It does not become a verified appraisal or a permission to bid automatically.

### HOLD

Used when no defensible exit-value basis exists, ROI/profit cannot be calculated, economics fall below the Owner's minimum hurdle, expected holding exceeds the supported horizon, or a material unknown cannot yet be reasonably bounded. HOLD is a watchlist and information-option state; it does not delete the opportunity.

### DO NOT BID

Reserved for a confirmed non-mitigable legal defect, unacceptable confirmed physical/security threat, confirmed non-mitigable lawful-access/environmental issue, explicit confirmed hard-stop risk-register item, or strong condition-matched evidence showing the project remains structurally uneconomic even under a zero-acquisition-price diagnostic. An unverified rumor is not automatically a hard stop.

## 3. Bid Readiness is separate

Bid Readiness may remain NOT READY because of cash shortfall, provisional funds, unconfirmed official bid increment, due-diligence items, survey/inaccessible interior, cost confirmation, risk mitigation, market validation, or tax assumptions. These are preparation items and are shown separately from investment attractiveness. Owner retains the final decision; the system clearly discloses unresolved readiness items.

## 4. Market values and evidence

- **FMV as-is** describes the asset in its current condition.
- **ARV after repair** describes the planned exit condition.
- Do not silently mix different condition buckets to create a primary ARV. Mixed-pool values may be shown only as diagnostics.
- Comparable counts, direct URLs, capture dates and confidence index grade the evidence. An asking price remains an asking price, not a confirmed transaction.
- When relevant comps are unavailable, Owner may enter a separate FMV/ARV estimate and write its basis. Such values are Owner assumptions, not comparables; show low confidence and provisional labels.
- If neither comparable evidence nor an Owner exit-value basis exists, do not invent an ARV, profit, ROI or MAO.

Default evidence guide: 3 condition-matched observations and confidence ≥45 support a stronger CONDITIONAL GO case; GO normally requires 5 condition-matched observations, 5 direct individual listing URLs with capture dates and confidence ≥55. A smaller sample does not prevent indicative analysis when a defensible Owner valuation is supplied.

## 5. Physical and renovation uncertainty

- Owner may record building age and visual assessment when technical inspection is unavailable. These are explicitly Owner assessments, not engineering certification.
- If interior access is unavailable, use an explicit hidden-condition reserve or configured percentage fallback. It is included in the project cost; it is not proof of damage or proof of safety.
- Known renovation rows are costed normally. Unmeasured or inaccessible scope must use a priced allowance. Python adds that allowance to renovation cost and applies the configured contingency.
- Unpriced scope without allowance is visibly flagged, so the reported profit/ROI are not presented as complete.

## 6. Legal / SKPT treatment

The user may record that the SKPT and KPKNL auction announcement have been reviewed and the property identity/right matched. This is the Owner's dated verification record and supports the pre-bid identity review. It does not guarantee facts outside the SKPT, future events or undisclosed claims. Original certificate handover is an administrative/post-award follow-up and must not be counted as a duplicate legal defect if identity/SKPT checks are recorded. Confirmed material dispute/claim remains subject to independent legal evaluation and an explicit hard-stop decision.

## 7. Funding by date and certainty

Only cash available by the auction date supports bidding liquidity. Planned/unconfirmed amounts are not included. A committed amount before the auction can be shown as projected/provisional, but remains a confirmation item until actually received. Amounts expected after auction do not fund the bid.

## 8. Financial calculation

Project ROI = net project profit / total all-in project cost. Python is the numeric source of truth. MAO 70% is a quick screening reference; Full Cost MAO incorporates modeled acquisition, tax/transfer, arrears, possession, renovation, contingency, hidden-condition reserve, holding, marketing and sale costs and the required ROI/profit/horizon.

Fast / Moderate / Stress cases are deterministic sensitivity scenarios, not probability-weighted forecasts. PFMS does not claim a statistical Expected Value without reliable scenario probabilities and calibrated historical data.

## 9. Roles of Python and Gemini

Python performs data validation, comparable normalization, cost aggregation, cash timing, ROI/profit/MAO and scenario math. Gemini Flash interprets the structured evidence and narrative context, explains trade-offs and blind spots, and proposes options. Gemini must not invent facts or replace Python's financial values. If the API is unavailable, the Python study remains available.

Owner remains responsible for accepting the assumptions, evaluating external advice and choosing GO / CONDITIONAL GO / HOLD / SKIP / DO NOT BID.

## 10. Compatibility

No Google Sheets tab, header or schema migration is required. New fields are retained within existing analysis payloads/history. Auction lifecycle and same-property/relisting detection are outside this release.
