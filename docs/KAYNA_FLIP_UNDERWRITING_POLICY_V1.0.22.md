# Kayna Property — Flip Underwriting Policy V1.0.22

## 1. Business objective

Kayna Property operates as a property flipper: acquire suitable auction properties at a sufficient discount, secure and improve them efficiently, then resell at a competitive price. Success is assessed by profit, all-in return, capital turnover, liquidity and risk—not by the number of properties acquired.

## 2. Default investment hurdles

| Parameter | Default | Meaning |
|---|---:|---|
| Minimum all-in Project ROI | 20% | Hard minimum underwriting gate |
| Target all-in Project ROI | 30% | Negotiation and bid target; not a maximum cap |
| Minimum net profit | Rp50,000,000 | Hard nominal profit gate after selling costs |
| Ideal holding period | 90 calendar days | Target from the post-win/settlement phase through closing; actual deposit outflow is dated separately for XIRR |
| Maximum holding period | 180 calendar days | Hard underwriting limit |

ROI above 30% is always welcome. The 30% target is not a profit cap and should never make an otherwise better project fail.

### Decision interpretation

- A project under 90 days can pass if all other underwriting gates are satisfied.
- A project taking 91–180 days may still pass the minimum gates, but is flagged for time/capital-turnover review and should not be treated as the preferred case.
- A project forecast above 180 days is DO NOT BID when the economics and duration are computable.
- Missing or unreliable duration assumptions produce HOLD, not an assumed zero-day pass.
- A GO decision also depends on market evidence, legal, occupancy, risk, cost completeness, bid increment and available cash. Passing ROI alone is never sufficient.

## 3. Definitions and formulas

### Project profit after selling costs

`Net Profit = Gross Sale Price - Selling Costs - Pre-sale Project Capital`

Pre-sale Project Capital includes auction price, buyer auction fee, BPHTB, acquisition/legal expenses, possession costs, renovation, contingency, hidden-condition reserve where applicable, holding costs, marketing and other approved pre-sale expenses.

Unspent risk reserves are part of cash planning, not realized expense. If a reserve is spent, the actual payment is included in project costs.

### All-in Project ROI

`All-in Project ROI = Net Profit / (Pre-sale Project Capital + Selling Costs) × 100%`

This is the primary ROI gate. PFMS also retains `ROI on Pre-sale Capital` as a diagnostic only; it is not the GO hurdle.

### Annualized ROI equivalent

For a projected scenario, PFMS may show the mathematical annualized equivalent:

`(1 + All-in Project ROI)^(12 / Holding Months) - 1`

This is an equivalent annual rate derived from a project ROI assumption. It is not actual XIRR, is not a guarantee that the return can be repeated, and should not be confused with a cashflow-based investor return.

### Actual XIRR

Actual XIRR is calculated only after the project is sold and all material outflows have valid transaction dates, closing proceeds have a valid sold date, and the closing selling-cost figure reconciles with the selling ledger. Missing dates or unreconciled selling costs withhold XIRR; PFMS must not invent dates.

## 4. Holding-period method

Projected holding days are currently estimated from the post-win / settlement phase by adding the sequential planning phases:

- possession / vacant handover;
- legal or administrative delay;
- renovation;
- marketing and sale closing.

One planning month is standardized as 30 calendar days. The sequential sum is a conservative planning assumption. If actual work can run in parallel, the user may reduce the phase assumptions only when the work plan supports it. The holding period is not reset when the property becomes ready-to-sell or when the listing goes live; it ends at sale closing/receipt of funds.

The auction deposit deadline is not treated as the actual deposit payment date. The current 90/180-day projection starts from the post-win/settlement project phases; record the actual deposit payment date in the cashflow ledger so it is included in XIRR. The 90/180-day calculation is a screening estimate. Actual project duration is measured using dated cashflow and lifecycle records.

## 5. ARV and comparable-property policy

The market engine follows a hybrid comparable-sales/listing-adjustment approach:

1. Secondary/resale evidence is the primary pool for a flipper's resale ARV.
2. Primary/developer listings are kept as competitive-market context and are not mixed into the secondary ARV when secondary evidence exists.
3. Unknown segment listings may be used as lower-weight supplementary evidence; a primary-only market produces a weak-proxy warning.
4. Verified closing prices are not given an arbitrary negotiation haircut. Active asking prices receive a separate configurable negotiation assumption.
5. Promotional benefits are deducted only when their cash-equivalent value is verified. KPR-no-DP or free-fee phrases are not blanket 20–25% price discounts.
6. Multiple portal advertisements for the same physical house should share an underlying property ID and must not be counted as independent comparables.
7. Over-credit listings are kept separate from cash asking/closing prices until outstanding debt and takeover obligations are verified.
8. ZNT and Cost Approach can cross-check land/building value when reliable local inputs exist; they are not blindly blended at fixed weights into ARV.

Weighted median and uncertainty ranges are preferred to a simple average of raw listing prices. The confidence/quality index is not the probability that a sale price will be achieved.

## 6. Maximum Bid policy

- Actionable Maximum Bid is solved using Quick Sale / conservative ARV.
- It must satisfy minimum all-in Project ROI, minimum net profit, maximum holding days, risk ceiling and legal auction increment.
- If the auction increment is not confirmed, the system may show a computational ceiling but must not present it as a legal bid.
- A theoretical ceiling below the auction limit is diagnostic only; it is never a valid bid.
- Base ARV and Upper ARV bid ceilings are sensitivity references, not the principal GO recommendation.
- Cash adequacy is displayed separately and must be satisfied before GO.

## 7. Risk and liquidity

Cash requirement may include possession and general risk reserves. Unspent reserves do not reduce forecast profit. Legal/occupancy risks, hidden interior/MEP works, incomplete RAB, market evidence and available cash remain independent decision gates. A high ROI does not override a critical legal or possession blocker.

## 8. Configurability and calibration

The default thresholds can be changed in Settings & Rules. Users should calibrate the policy only after reviewing completed Kayna projects, including actual closing price, actual total cost, days from first capital commitment to closing, selling duration, and XIRR. Do not lower thresholds merely to increase the number of GO opportunities.

This policy is an underwriting framework for business decisions, not an appraisal report, guaranteed return, or substitute for legal/tax verification.
