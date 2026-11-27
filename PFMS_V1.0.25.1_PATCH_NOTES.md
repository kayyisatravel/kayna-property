# PFMS V1.0.25.1 — Underwriting Decision & MAO Correction

## Scope

Corrects the V1.0.25 underwriting/ranking policy so **investment attractiveness** is distinct from **bid readiness**. Adds condition-matched FMV as-is and ARV-after-repair estimates, revised GO/CONDITIONAL GO/HOLD/DO NOT BID logic, and separate full-cost ceilings.

## Key changes

1. Separates `investment_status` from `bid_readiness` while retaining `decision.status` as a backward-compatible alias.
2. Implements default thresholds: CONDITIONAL GO ROI ≥15%, GO ROI ≥25%, target ROI 30%, minimum net project profit Rp50 million, GO holding ≤180 days and CONDITIONAL GO ≤365 days.
3. Rebalances evidence gates: at least 3 condition-matched exit comparables/confidence 45 for CONDITIONAL GO; at least 5 condition-matched comparables, 5 individual listing URLs with capture dates, and confidence 55 for GO.
4. Separates FMV as-is from ARV after repair. House exit valuation uses `Siap Huni` comparables; current as-is value uses the corresponding current-condition bucket. Land-only assets use `Hitung Tanah` comparables.
5. A mixed-condition proxy may remain available for partial diagnostics when condition-matched evidence is insufficient, but the status remains HOLD and final MAOs are withheld.
6. Separates MAO 70% quick screening, Full Cost MAO for CONDITIONAL GO, Full Cost MAO for GO, and target-ROI bid reference. Known PBB/utility/IPL/local arrears in the existing pre-sale-obligation field reduce the 70% MAO directly.
7. Keeps cash shortage, missing official increment, and final GO-grade listing evidence as Bid Readiness gates, rather than automatically erasing investment attractiveness.
8. Adds explicit user confirmation for non-mitigable legal, security, and access/environment hard stops; risk-register hard stops are explicit.
9. Makes a measurable, costed, mitigated critical non-legal risk eligible for CONDITIONAL GO; unresolved material legal risk remains HOLD.
10. Fixes the `run_underwriting()` → `evaluate_decision()` rules handoff and the vacant-status parsing bug for “Tidak Dihuni”. Adds explicit original-certificate handover and structural-safety verification, and maps cosmetic-only condition to the ready-to-move market bucket.
11. Makes ranking refresh use the current global policy thresholds while keeping historical property-specific analysis inputs intact.
12. Preserves Google Sheets tabs/headers and analysis history; pre-V1.0.25.1 snapshots without the new certificate/structure confirmations load as unverified until reviewed and re-analysed. No lifecycle/relist or same-property detection changes are included (those remain future work).

## Important interpretation

- CONDITIONAL GO is not permission to bid automatically. Bid Readiness must be READY.
- Asking prices are not treated as verified transactions; the existing negotiation haircut remains applied to asking comparables.
- Projected holding duration is a planning estimate, not observed neighborhood DOM.
- If condition-matched ARV evidence is inadequate, the model can display a provisional mixed-condition proxy for diagnostics, but it withholds final MAO and keeps the decision HOLD.

## Validation

- `python -m py_compile app.py config.py core/*.py tests/*.py` — passed.
- `python -m pytest -q` — **262 passed**.
- Static global-reference and layout safety tests — included in regression suite.
- ZIP integrity and package-content checks — to be recorded after release archive creation.
- Live Streamlit Cloud, Google Sheets and Gemini integration tests were not performed because deployment credentials/runtime are not available in this environment.

## Deployment

1. Back up the currently deployed V1.0.25 source.
2. Apply the V1.0.25.1 patch overlay to the repository root.
3. Do not replace `.streamlit/secrets.toml`; the patch does not contain user secrets.
4. Deploy and follow the release smoke test.
