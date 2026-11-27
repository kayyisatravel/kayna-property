# KAYNA Property — Investment Underwriting Policy V2

**PFMS release:** V1.0.25.1  
**Policy key:** `KAYNA_FLIP_POLICY_V2`  
**Purpose:** classify investment attractiveness separately from permission/readiness to bid.

This is an internal investment policy and model assumption set. It is not a property appraisal, legal opinion, tax opinion, or guarantee of sale price.

## 1. Two independent decisions

PFMS returns two separate outputs:

1. **Investment Status** — GO, CONDITIONAL GO, HOLD, or DO NOT BID.
2. **Bid Readiness** — READY or NOT READY with one or more identified gates.

A property can be attractive enough to keep pursuing while not yet ready for an actual auction bid. Cash shortage, unconfirmed official bid increment, or incomplete final-grade market evidence can block Bid Readiness without automatically erasing investment attractiveness. Unknown material facts remain HOLD; confirmed non-mitigable hard stops remain DO NOT BID.

## 2. Investment classifications

### GO — Layak Eksekusi Penuh

GO requires all relevant core due-diligence and economic gates to pass. Default policy thresholds:

- Project ROI at the auction limit is at least **25%**.
- Net project profit is at least **Rp50,000,000**.
- Projected post-win holding period is at most **180 days**.
- At least **5 condition-matched exit comparables**, at least 5 individual listing URLs with capture dates, and market confidence of at least **55/100**.
- Identity/legal documents and applicable tax/auction assumptions have been reviewed.
- Survey, physical condition, interior, occupancy, risk register, and in-scope RAB/costs have been reviewed.
- Default GO physical profile is vacant and ready/cosmetic condition, with no unresolved material risk.

A GO label is not itself an auction instruction. `Bid Readiness` must also be READY.

### CONDITIONAL GO — Layak dengan Syarat Tertentu

CONDITIONAL GO is used when the property is fundamentally investable, but one or more measurable mitigations are required. Default thresholds:

- Project ROI at least **15%** but below the GO threshold of 25%, or a measured manageable friction such as cooperative possession, renovation, moderate market evidence, or an extended but bounded holding period.
- Net project profit at least **Rp50,000,000**.
- Projected holding period no more than **365 days**.
- At least **3 condition-matched exit comparables** and market confidence of at least **45/100**.
- Mitigations must be stated, priced where applicable, supported by evidence, and reflected in the project calculation.
- Medium/heavy renovation requires interior/technical inspection and a renovation contingency of at least **15% / 20%** respectively under the current defaults.
- Occupied assets require a documented voluntary possession/cash-for-keys plan, cost, schedule, and reserve before Bid Readiness can become READY.

CONDITIONAL GO does not permit bidding while required mitigations or readiness gates are outstanding.

### HOLD — Tunda & Observasi

HOLD applies when there is no confirmed fatal issue, but the current information, economics, or timing does not support a responsible decision. Examples:

- Fewer than 3 suitable condition-matched exit comparables or market confidence below 45/100.
- Survey, physical condition, legal identity, tax basis, project costs, risk review, or material RAB scope is unknown/unreviewed.
- Project ROI below 15%, net profit below Rp50 million, or projected holding period over 365 days.
- A relevant dispute/claim indication remains unclarified.
- The auction limit is above an investor-set hard ceiling/MAO.

HOLD is a watchlist state, not an instruction to delete or forget the opportunity. A future relist, price reduction, new survey, or verified information can trigger a new analysis while preserving the old snapshot.

### DO NOT BID — Tolak Mutlak

DO NOT BID requires a confirmed hard stop or a structurally uneconomic project. Examples include:

- Confirmed material legal defect or litigation/claim assessed as non-mitigable.
- Confirmed unacceptable physical threat/security risk.
- Confirmed absence of legal access or permanent environmental hazard that cannot be economically mitigated.
- A user-confirmed non-mitigable hard-stop risk-register item.
- The model's zero-acquisition-price scenario still produces non-positive net project profit after the modeled project/sale costs.

An unverified rumor or incomplete information is HOLD, not automatically DO NOT BID.

## 3. Market valuation — FMV as-is vs ARV after repair

PFMS separates two valuation views:

- **FMV as-is:** value indication using comparables in the property's current physical-condition bucket (`Siap Huni`, `Butuh Renovasi`, or `Hitung Tanah`). Cosmetic-only renovation is grouped with `Siap Huni` comparables; light/medium/heavy renovation remains `Butuh Renovasi`.
- **ARV after repair:** value indication using comparables in the intended exit condition. For a renovated house this is normally `Siap Huni`; for land-only it is `Hitung Tanah`.

A value is shown as an indicative condition-matched estimate only when the relevant cohort has at least 3 valuation comparables and confidence of at least 45/100. A smaller sample may be retained as an explicitly low-sample diagnostic but is not presented as a validated FMV/ARV.

Where condition-matched exit evidence is insufficient, PFMS may retain a mixed-condition proxy for partial diagnostic calculations. That proxy is explicitly marked as provisional; the decision remains HOLD for the market gate, and neither MAO 70% nor MAO Full Cost is presented as a final bidding ceiling.

The limit-to-FMV-as-is percentage is displayed as an analytical indicator, not as a standalone hard gate. MAO and the all-in project calculation govern the price ceiling.

Asking prices are not represented as completed transactions. The market engine applies the configured negotiation haircut to asking observations; a confirmed transaction price is treated differently. The user should continue to seek agent/owner transaction confirmation where available.

## 4. MAO and bid ceilings

### Quick screening — 70% rule

The configurable rule-of-thumb factor defaults to **70%** of the conservative quick-sale exit estimate. PFMS solves the maximum bid so that:

`bid + buyer auction fee + BPHTB + legal/transfer costs + known property-borne arrears/obligations + possession/evacuation + renovation + renovation contingency + hidden-condition reserve + other risk reserves <= 70% × conservative exit value`

Known PBB, electricity, water, IPL, security or local administrative arrears are entered in the existing **Tunggakan & kewajiban lain sebelum penjualan** field and reduce the MAO directly. Marketing and holding costs remain inside the residual 30% buffer in this quick screen; they are fully included in the separate Full Cost MAO. The factor is an internal rule of thumb, not a universal market standard.

### Full-cost MAO

The full-cost solver uses the Python project calculator, including buyer costs/taxes, legal acquisition costs, possession, renovation and contingency, hidden-condition reserve, holding cost, marketing/presale cost, selling taxes/fees, the minimum net profit and the required Project ROI.

PFMS shows three distinct reference ceilings:

- **MAO Full Cost — CONDITIONAL GO:** default minimum Project ROI 15%, profit minimum Rp50 million, maximum 365 days.
- **MAO Full Cost — GO:** default minimum Project ROI 25%, profit minimum Rp50 million, maximum 180 days.
- **Target bid:** default target Project ROI 30%, maximum 180 days.

The official auction increment must be confirmed before any calculated ceiling can be considered an actionable bid. If the increment is not confirmed, simulated ceilings are diagnostics only.

### Return definition

`Project ROI = net project profit / total all-in project cost × 100%`

Total all-in cost includes acquisition, project/possession/holding/presale cost and modeled selling transaction costs. Pre-sale-capital ROI and annualized equivalents remain separate diagnostic measures; estimated annualized ROI is not actual XIRR.

## 5. Duration and market liquidity

Projected holding duration sums the estimated possession, legal-delay, renovation, and selling phases. The calculator uses a standardized 30-day month. Default policy is 180 days for GO and 365 days for CONDITIONAL GO.

This is a **projected holding-period proxy**, not observed market Days on Market (DOM). The current source data model does not contain a verified historical DOM dataset, so PFMS does not claim that a neighborhood's actual average DOM is under six months. The selling-month estimate should be supported by local listing/sales research and reviewed by the user.

## 6. Risk handling

- A critical risk may be CONDITIONAL GO only when the issue is measurable, mitigation is documented, and the required cash reserve is entered.
- Legal/identity risks that remain unresolved are HOLD.
- Only a confirmed, non-mitigable issue is marked as a hard stop/DO NOT BID.
- The generic comparable-quality risk preset is not itself a critical hard stop; market-engine evidence thresholds remain authoritative. This avoids double-counting the same market weakness in both the risk register and market gate.

## 7. Liquidity and Bid Readiness

Bid Readiness requires the investor's cash position to be confirmed and sufficient for the modeled project cash requirement including reserves. It also requires the official bid increment, due-diligence and legal/tax checks, reviewed project costs/RAB, and possession mitigation where relevant.

Cash shortfall is an execution/funding gate. It can leave a GO/CONDITIONAL GO opportunity on the watchlist as NOT READY, but never permits an actual bid.

## 8. Default policy settings

| Setting | Default |
|---|---:|
| CONDITIONAL GO minimum Project ROI | 15% |
| GO minimum Project ROI | 25% |
| Target Project ROI | 30% |
| Minimum net project profit | Rp50,000,000 |
| Ideal holding period | 90 days |
| GO maximum holding period | 180 days |
| CONDITIONAL GO maximum holding period | 365 days |
| Conditional market sample | 3 comparables, confidence 45/100 |
| GO market sample | 5 condition-matched comparables, 5 individual listing URLs with capture dates, confidence 55/100 |
| Renovation contingency — medium | 15% |
| Renovation contingency — heavy | 20% |
| MAO rule-of-thumb factor | 70% |

These settings are editable assumptions and must be calibrated to the investor's cost structure, region, lot, and current auction/municipal rules.

## 9. Data compatibility

V1.0.25.1 adds decision/valuation fields inside existing analysis JSON payloads. It does not add or rename Google Sheets tabs/headers and does not delete or overwrite historical analysis snapshots. Old analysis snapshots remain historical; ranking recalculates them with the current global policy keys while retaining their original property, survey, legal, costs, comparables, and risk inputs.
