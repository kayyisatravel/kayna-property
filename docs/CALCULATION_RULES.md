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


## 7. AI-assisted renovation RAB (V1.0.3)

- Gemini may draft itemized renovation work from uploaded auction PDF/screenshot, up to five survey photos, current user condition description and property context.
- The model must use only visible findings and explicit user descriptions. Hidden structural, roof, electrical, plumbing or interior defects must not be stated as confirmed from facade-only images; they go to `items_to_inspect`.
- Each line may include quantity/unit, low unit-cost estimate and conservative upper unit-cost estimate. Python uses the conservative upper unit cost in the editable `unit_cost` column.
- Unit rates are indicative estimates, not live contractor quotations or verified local supplier prices. User must review measurements, unit rates and scope before confirming cost estimates.
- Renovation contingency remains a separate Python calculation and must not be included in AI line items (avoid double counting).
- If quantity or unit cost is unknown, keep it blank and require user input.


## 8. Context-aware renovation estimator (V1.0.6)

### Inputs used
- General physical condition and selected renovation category.
- LT, LB, floor count, optional measured ground-floor footprint.
- Property type, bedroom and bathroom count.
- Road width/access, facade notes, survey notes, user-described defects and uploaded photos.

The AI may select applicable scope and suggest conservative unit rates. Python owns deterministic screening quantities. Access is context for mobilization/unit-rate review; it does not create an automatic volume multiplier. Bedroom count may move the wall-area midpoint within the screening interval only; it is not a measured wall take-off. Bathroom count is used as a possible count of bathroom work packages, not proof that each bathroom requires renovation.

### Screening quantity assumptions
| Work | Preliminary formula | Limitation |
|---|---|---|
| Floor / full ceiling | 1.0 × aggregate LB | Exclude voids, open areas, carport or areas not included in work.
| Roof | 1.25–1.35 × ground-floor footprint | Use measured footprint if supplied; otherwise estimate LB ÷ floor count. Actual shape, slope and overhang require measurement.
| Wall paint area | 2.5–3.0 × LB | Very rough combined internal/external surface allowance; midpoint within the range may be adjusted slightly by bedroom count. Verify perimeter, height, partitions and openings.
| Full electrical rewire points | ceil(LB ÷ 6) | Allowance only for medium/heavy scope; not an electrical standard. Final point count and load by electrical plan/technician. Not used for minor repairs.
| Demolition rubble | 0.30–0.50 m³ × LB | Very low-confidence screening; depends on masonry, concrete, foundation, separation, bulking and demolition method. Verify contractor/truck/landfill.
| Truck trips | ceil(rubble volume ÷ configured truck capacity), default 5 m³ | Actual payload and access may be 4–6 m³ or differ; verify local provider.
| Light roof repair | 5–15% × estimated roof area | Local-repair allowance only if supported by inspection/photos/description; not whole-roof replacement.
| Light ceiling patch | 3–10% × LB | Allowance only if damaged ceiling area is indicated; measure actual patch.
| Light tile patch | 2–6% × LB | Allowance only if damaged tiles are indicated; measure actual area.

These ratios are not SNI/AHSP universal coefficients and do not replace detailed quantity take-off. Permen PUPR No. 8 Tahun 2023 on AHSP requires preparation from work components and local conditions, including method/specification, labor, materials, and equipment. Use applicable local government HSPK/SSH and current market quotes for unit prices; AI price estimates remain indicative and must be checked.

### Category rules
- **Auto / condition unknown:** inspection and preparation only; no assumed repair scope.
- **Ready to occupy:** basic preparation and optional cosmetic scope; do not force full repaint if evidence does not support it.
- **Cosmetic:** when explicitly selected/inferred from explicit paint/finishing condition, preparation, wall and ceiling are required; floor method is either polishing OR vinyl/SPC, never both.
- **Light:** local repair scope only; low-confidence allowances are conditional and should be used only when indicated.
- **Medium:** broad replacement scope; roof area based on footprint, ceiling/floor by LB, bathroom packages by known count, electrical points are indicative only.
- **Heavy:** structural/foundation/column/beam/slab quantities and prices remain blank until assessed and designed by a competent engineer. No structural safety conclusion from photo/area alone.
- **Hitung Tanah:** demolition, rubble and land clearing are separate from renovation. Rubble and truck estimates are low confidence.

### Completeness gate
A missing required work item is inserted as an unpriced placeholder. Any required RAB line without conservative quantity and unit price blocks GO. Conditional/optional work remains visible when selected by AI/user, but an unneeded item can be removed or marked optional after review. Contingency is calculated separately by Python and must not be duplicated in line items.
