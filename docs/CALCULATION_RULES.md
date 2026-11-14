# Calculation Rules — PFMS V1

## 1. Market valuation

Each valid comparable produces a separate estimate of the subject property's total value using land-area and, where available, building-area normalization. These two estimates are blended; they are never added together.

- Active asking and marked-sold/unverified prices receive the configured negotiation discount (default 10%).
- Verified transaction prices do not receive the negotiation discount.
- A manual adjustment percentage may be entered only with a documented reason.
- Comparable similarity is reduced for complex mismatch, land/building size mismatch, certificate mismatch, access mismatch, condition mismatch, stale date and unverified marked-sold status.
- Weighted median of normalized comparable values becomes base ARV.
- Conservative ARV = base ARV × (1 − quick-sale discount; default 5%).
- Optimistic ARV = base ARV × 1.05 as an indicative upside scenario only.
- Five usable comparables and confidence >=55 are required for GO. The score is a screening index, not a probability of sale. Fewer than five rows may still produce an indicative ARV and bid ceiling, but final status cannot be GO. If no subject area or no comparable valuation basis exists, ARV remains null; the system still calculates acquisition/project cost at the limit, while profit and ROI remain null and status is HOLD.

Comparable minimum validity for preliminary valuation requires name/address, positive price, at least one usable area (LT or LB), and source provenance (direct URL OR named source platform/evidence text). Condition, access, certificate, LB, direct URL, and listing publication date are quality attributes: if absent, they remain null and reduce confidence rather than causing the row to be split or discarded. LB may be blank when the source does not state it; the engine can use land-only normalization when subject LT is known. A comparable without LT can only be used for building normalization when subject LB and comparable LB are both known. A source platform name is provenance, not a substitute for a direct URL in evidence quality; the UI separately counts direct URLs. The date the user captures/imports data (`date_found`) is not the listing publication date (`listing_date`). Never fabricate either date.

Narrative comparable parsing groups all bullets under one numbered listing heading into one row. It must not treat each bullet as a separate comparable. AI extraction is subject to user review; it does not verify current listing availability.

## 2. Acquisition and project cost

For bid price P:

- Buyer auction fee = P × buyer auction fee rate.
- BPHTB basis is configurable; default mode is max(P, NJOP).
- NPOPTKP is deducted only if user confirms eligibility.
- BPHTB = max(0, basis − NPOPTKP) × BPHTB rate.
- Legal/BPN = PNBP + roya + other acquisition admin + any explicit legal cost. Acquisition notary/PPAT defaults to zero in this workflow.
- Renovation contingency = renovation budget × configured contingency rate (default 15%).
- Holding months = possession + legal delay + renovation + sale period.
- Holding cost = holding months × monthly holding cost.
- Possession expected costs, marketing and other pre-sale costs are added to capital before sale.

Risk reserves for possible possession/general risks are added to cash requirement, not to profit-cost denominator until those risks actually occur.

## 3. Selling costs and profit

- PPh final estimate = sale price × configured rate (default 2.5%).
- Agent = sale price × configured rate (default 2.5%).
- Seller-side AJB/PPAT estimate = sale price × configured rate (default 1%).
- Miscellaneous = configured fixed amount (default Rp5m).
- Net proceeds = exit price − selling costs.
- Project capital before sale = acquisition + BPN/legal + possession + renovation + contingency + holding + other pre-sale costs.
- Net profit = net proceeds − project capital before sale.
- ROI project = net profit / project capital before sale × 100%.
- Annualized ROI is informational only.

Selling costs must not be deducted twice. Closing ROI uses actual cash outflows excluding the selling ledger when the closing form already records an explicit selling-cost total; otherwise selling ledger rows are used.

## 4. Maximum bid and tiers

The numerical search tests bid prices from auction limit in confirmed increment steps.

- Mid bid: highest bid that meets target ROI 35% under conservative ARV, cash and risk ceilings.
- Maximum bid: highest bid that meets minimum project ROI 25% under conservative ARV, cash and risk ceilings.
- Walk-away: maximum bid + one confirmed increment. If maximum bid is below auction limit, walk-away begins at the auction limit (do not place the opening bid).
- If official bid increment is absent, the engine uses a clearly labelled Rp1,000 computation step only to estimate an economic ceiling. It does not claim an official walk-away increment; the user must confirm the lot's increment before bidding.
- If the auction limit itself fails the 25% ROI hurdle, no viable maximum bid exists and the system returns DO NOT BID.
- If the economic hurdle passes but available cash is insufficient, the decision is HOLD for funding, not a statement that market economics are unattractive.

## 5. Cash

Cash available for a new project:

`real cash − confirmed user-entered future outflows − active unpaid commitments − liquidity reserve`.

Liquidity reserve = real cash × reserve percentage (10–20%, default 20%). Active property estimates are displayed as reference only; they are not automatically deducted unless the user enters or confirms an outflow/commitment.

Auction deposit is a pre-auction liquidity timing requirement and is credited against settlement where auction rules allow. Actual ledger must record the purchase price only once.

## 6. Decision gates

GO requires, among other gates: property identity, survey, legal verification, local tax/auction rule verification, cost review confirmation, risk register review, at least five valid comparable listings, confidence >=55, confirmed bid increment, confirmed investor cash and adequate funding, plus ROI >=25% at limit.

CONDITIONAL GO can apply when primary gates pass but a manageable warning remains (for example, interior inspection pending).

HOLD applies when evidence, survey, cash confirmation, increments, taxes or critical mitigation are incomplete.

DO NOT BID applies when the limit fails the ROI hurdle, a legal dispute hard stop is reported, or a risk-adjusted ceiling is below auction limit.

These rules are conservative workflow controls, not legal/tax advice. Review rule inputs for every region and auction lot.
