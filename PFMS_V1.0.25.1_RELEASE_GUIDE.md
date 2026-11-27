# PFMS V1.0.25.1 — Release & Smoke-Test Guide

## Apply the patch

1. Back up the current deployed V1.0.25 repository/source.
2. Extract the V1.0.25.1 patch ZIP over the repository root, preserving the folder structure.
3. Commit and deploy using the existing Streamlit Cloud workflow.
4. Do **not** overwrite or upload `.streamlit/secrets.toml`. The patch has no live API keys or user credentials.

## First-run checks

1. Open Settings & Rules. Confirm policy defaults are 15% CONDITIONAL GO, 25% GO, 30% target ROI, Rp50m minimum project profit, 180-day GO, 365-day CONDITIONAL GO and 70% MAO screening factor.
2. If the existing global rules are pre-V2 and the legacy minimum ROI is exactly 20%, the policy migration changes that legacy value to 15%. Non-default custom values are retained. If you had intentionally configured exactly 20%, review and restore that value if needed before saving settings.
3. Historical analyses created before V1.0.25.1 do not contain explicit original-certificate custody/handover or structural-safety confirmation. They are restored as unverified and will remain HOLD until the new fields are reviewed and the analysis is updated. Their original snapshots are not overwritten.
4. Open an analysed property. Confirm FMV as-is and ARV-after-repair are displayed separately. The valuation cohort should identify the condition bucket used.
5. Confirm the original certificate is stated as held by the bank/creditor and ready for handover, and confirm the main structure has been inspected as free of fatal structural defects. Without both, the decision should remain HOLD.
6. For a property with fewer than 3 condition-matched exit comparables, confirm the app labels any mixed-condition price only as a provisional proxy and withholds final MAO values.
7. Confirm the decision card shows Investment Status and Bid Readiness separately.
8. Confirm the bid ladder shows GO minimum ROI, GO target ROI, and CONDITIONAL GO MAO as distinct rows.
9. Change investor cash position. Confirm cash shortage can make Bid Readiness NOT READY without automatically changing an otherwise eligible investment status.
10. For occupied assets, confirm the documented possession/cash-for-keys plan is required before Bid Readiness can become READY.
11. Confirm explicit fatal legal, security, and access/environment flags produce DO NOT BID; unverified indications remain HOLD.
12. Open Bandingkan Peluang. Confirm it re-underwrites saved historical snapshots using current policy thresholds and shows FMV/ARV/MAO information without changing the original analysis snapshot.

## Regression checks

Run locally:

```bash
python -m py_compile app.py config.py core/*.py tests/*.py
python -m pytest -q
```

Expected suite result for the prepared source: **262 passed**.

## Known limitations

- No live integration test has been performed against Streamlit Cloud, the user's Google Sheet, or Gemini credentials.
- Projected holding days are calculated from user-entered phase durations, standardized at 30 days/month. They are not observed market Days on Market.
- FMV/ARV are comparable-based indications, not formal appraisals or completed transaction confirmations.
- Current patch does not implement V1.0.26 auction lifecycle or V1.0.27 detection of the same physical property across different Lot Codes.
