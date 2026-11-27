# PFMS V1.0.25.2 — AI Feasibility Co-Pilot

## 1. Product principle

PFMS is an **AI-assisted feasibility analyst**, not an automated owner, legal authority, or bidding police. It assembles facts, Owner assumptions, deterministic calculations, downside scenarios, and risk mitigations into a feasibility brief. The Owner remains the final decision-maker.

The application shows three different outputs and never treats them as interchangeable:

1. **Model reference classification:** GO, CONDITIONAL GO, HOLD, or DO NOT BID.
2. **Bid Readiness:** READY or NOT READY, with the exact execution items still outstanding.
3. **Owner decision:** Belum diputuskan, GO, CONDITIONAL GO, HOLD, SKIP, or DO NOT BID, with an optional rationale. This choice is recorded separately from the model's assessment.

An Owner can choose differently from the model. When doing so, the app asks for a rationale and flags any decision that overrides a confirmed hard stop. The software does not silently rewrite the model's findings to match the Owner's choice.

## 2. Three-part analysis architecture

### Python Feasibility Engine — numeric source of truth

Python validates structured inputs, normalizes comparables, calculates acquisition/project/sale costs, funding needs, Project ROI, profit, holding time, MAO and bid ladders, and runs the Fast / Moderate / Stress scenarios. Exact financial values displayed in the report come from Python calculations, not Gemini-generated arithmetic.

### Gemini Flash — senior analyst / narrative co-pilot

Gemini receives a compact snapshot of the property, Owner inputs, Python outputs, market evidence quality, cash timing, risk register, scenario results and unresolved assumptions. It interprets trade-offs, identifies blind spots, explains what changes the outcome, and gives a reference recommendation. It must not invent missing facts, present asking prices as transactions, or calculate/replace financial figures.

When Gemini is unavailable or returns an error, the deterministic Python study remains available. The user can retry the narrative generation. Gemini's recommendation is advisory and is separately guarded against overriding a Python-confirmed hard stop or recommending GO when financial calculations are unavailable.

### Owner — final decision-maker

The Owner can compare the AI brief with local knowledge, negotiation relationships, available contractors, capital sources, current priorities and risk appetite. The selected Owner decision and rationale are recorded in the analysis snapshot and investment memorandum.

## 3. Incomplete information is modeled, not hidden

### Comparables are unavailable or difficult to find

The user may enter FMV as-is and/or ARV after repair as an **Owner estimate**, with a basis note (for example: agent interviews, recent local transactions known to the Owner, prior closings, or field judgment). This is not counted as a listing, transaction, or market-confidence point. Python can still calculate provisional profit, ROI, scenarios and MAO using the Owner value, but labels them OWNER_INPUT / provisional and the report explains the evidence limitation.

A small number of condition-matched comparables remains visible as an indicative estimate. FMV as-is and ARV after repair are calculated from separate condition buckets. Mixed-condition data may be shown as a diagnostic only; it is not silently promoted to the primary ARV. If neither a relevant comparable nor an Owner exit-value assumption exists, a meaningful ROI/MAO cannot be calculated and HOLD is appropriate until a defensible exit value is supplied.

The default evidence policy remains an advisory quality ladder: at least 3 condition-matched observations and confidence 45 for a stronger CONDITIONAL GO case; GO-grade market evidence ordinarily requires at least 5 condition-matched observations, 5 direct individual listing URLs with capture dates, and confidence 55. These thresholds grade evidence quality; they do not force the Owner to stop data collection or delete an opportunity.

### Interior inaccessible / building age and visible condition

The user may record building age, visual assessment of structure, inspection limits, and notes. A recent building age (such as 3 years) or visual assessment is an Owner assumption, not a technical certificate. If the interior has not been inspected, the user can enter an explicit hidden-condition reserve in rupiah or use the configured percentage fallback. This reserve is included in project costs; the system does not assert that hidden damage exists or that a reserve guarantees safety.

### Renovation scope cannot be fully measured

Known RAB items are calculated normally. For scope that cannot yet be accessed, measured or quoted, the user enters an **unverified scope allowance** and a renovation contingency. Python adds the allowance to renovation cost and applies contingency to the relevant renovation budget. Unpriced work with no allowance is explicitly flagged so the displayed profit is not mistaken for a complete project cost. The Owner may revise the allowance after inspection or contractor access.

### Additional cash arriving close to the auction

The user records amount, expected date, source and status. Only funds confirmed available by the auction date are included as cleared cash. A documented commitment before the auction may appear as provisional projected cash and remains a CASH CONFIRMATION item until it is actually received. Planned / uncertain funds are not counted. Funds arriving after the auction do not support the bid-day liquidity calculation.

### KPKNL / SKPT verification

The user can record that the SKPT has been checked and the land/object identity matched against the KPKNL auction announcement, together with the reference date/number. This is treated as the Owner's pre-bid identity-check record. It does not claim to guarantee that no fact, claim or litigation exists outside the document or after its date. Original certificate handover status is retained as an administrative/post-award follow-up, not a duplicate legal veto when SKPT / identity matching has been recorded.

## 4. Status logic: advisory classification vs execution readiness

### GO

Model reference for a strong economic case under the current assumptions, normally with Project ROI at least 25%, net project profit at least Rp50 million, projected holding up to 180 days, and few material unresolved frictions.

### CONDITIONAL GO

Model reference for an investable case where measurable frictions or assumptions remain. Examples include ROI 15% to below 25%, modest market evidence, occupied-but-manageable possession, medium/heavy renovation, uninspected interior with an explicit reserve, provisional Owner valuation, partial RAB with a priced scope allowance, or a bounded longer holding period. The AI brief must explain conditions and what the Owner must be comfortable accepting.

### HOLD

Used when a defensible exit value is unavailable, financial results cannot be calculated, economics fall below the minimum hurdle, holding assumptions exceed the supported horizon, or an important fact is so unclear that no reasonable cost/range can yet be assigned. HOLD is a watchlist / wait-for-information status, not deletion.

### DO NOT BID

Reserved for a confirmed fatal legal defect, confirmed unacceptable security threat, confirmed non-mitigable access/environmental issue, a confirmed risk-register hard stop, or strongly evidenced structural economic failure. An unverified allegation is not automatically a fatal hard stop.

### Bid Readiness

Bid Readiness is an execution checklist separate from investment attractiveness. Cash gaps, provisional cash, missing increment confirmation, unverified costs, survey gaps, possession plan, market verification and tax assumptions may leave Bid Readiness NOT READY even when the opportunity remains CONDITIONAL GO or GO. This tells the Owner what to prepare; it is not a substitute for the Owner's final decision. The app prominently warns when the Owner's choice overrides a confirmed hard stop.

## 5. Financial measures

- Project ROI = net project profit divided by total all-in project cost.
- FMV as-is and ARV after repair are separate values.
- MAO Rule of Thumb (default 70%) is only a quick screening reference.
- Full Cost MAO is solved by Python using the configured acquisition, taxes, legal/transfer, arrears, possession, renovation, contingency, hidden-condition reserve, holding, marketing and sale cost assumptions, subject to ROI/profit/duration requirements.
- When exit value, RAB or important costs are provisional, MAO and ROI remain visibly provisional.

The Fast / Moderate / Stress scenarios are deterministic sensitivity cases built from recorded assumptions. They are not probability-weighted forecasts. PFMS does not calculate a statistical Expected Value unless reliable scenario probabilities are supplied and calibrated historical data becomes available. Gemini may describe which assumptions matter most, but must not invent probabilities.

## 6. What is deterministic and what is AI reasoning?

IF/THEN logic is intentionally used for arithmetic, data validation, status thresholds, bid-readiness accounting and explicit confirmed hard stops. It is not the whole intelligence of the product. Gemini interprets the combined structured and narrative evidence, identifies trade-offs, explains consequences and proposes options. The Owner decides.

The AI does not replace:
- a formal property appraisal;
- a legal opinion or independent land-record review;
- a structural engineer / contractor inspection;
- a confirmed bank or investor funding source;
- official KPKNL auction conditions or local tax rules.

## 7. Compatibility and history

No Google Sheets tab, header, or schema migration is introduced. New details are saved in existing analysis payloads/history. Each analysis remains a snapshot of the assumptions and calculations at that time. Owner decision and rationale are stored separately from model status. V1.0.26 auction lifecycle and V1.0.27 same-property / relisting detection are not part of this release.
