# Patch PFMS V1.0.2 — AI Comparable Parser & Partial Underwriting

Extract this ZIP at the root of the existing GitHub repository and allow the included files to overwrite the old versions. Keep your actual Streamlit Secrets out of GitHub.

## Main files replaced

- `app.py` — new Gemini narrative-parsing button, expanded comparable editor, partial-analysis messaging, and preserves the earlier cashflow integer fix.
- `services/gemini_parser.py` — one row per numbered listing, Pydantic schema for comparables, no dynamic `additionalProperties` in auction/comparable schemas.
- `services/comparable_importer.py` — retains CSV/TSV import and source provenance fields.
- `core/market_engine.py` — incomplete comparable attributes lower confidence instead of fragmenting/discarding otherwise usable listings.
- `core/calculator.py` — absent ARV remains `None`; costs still calculate and profit/ROI do not become false negative values.
- `core/maximum_bid.py` — economic ceiling can be displayed below auction limit; without confirmed increment, a Rp1,000 calculation step is labelled indicative and no official walk-away increment is claimed.
- `core/underwriting.py` — always calculates available costs at limit even when ARV is unavailable.
- `config.py` — version 1.0.2.

The ZIP also includes updated docs and regression tests. A further evidence gate distinguishes rows usable for preliminary valuation from GO-grade comparable records (each needs a direct listing URL and capture date). Listing capture date is not treated as listing publication date. After upload, allow Streamlit Cloud to redeploy, then run the deployment smoke test.

## Required live checks

1. Paste five numbered multi-bullet listings and click **Parse narasi dengan Gemini AI**; expect exactly five table rows.
2. Verify missing LB/condition/access/direct URL/publication date are blank, not guessed.
3. Try analysis with no comparable rows; cost breakdown should appear, profit/ROI should be unavailable, and status should be HOLD.
4. Try one to four comparable rows that indicate max bid below limit; the system may show preliminary DO NOT BID, but must never show GO.
5. Confirm that final GO requires at least five GO-grade comparable rows with direct listing URLs and capture dates, confidence >=55, and all other hard gates.


## Additional changes in V1.0.2
- The parser detects sequential numbered listing sections in Python and verifies Gemini returns exactly one row per section; mismatches are rejected rather than filling a fragmented table.
- Comparable source URLs are not fabricated. Portal/platform provenance permits preliminary valuation, but final GO requires five direct listing URLs plus capture dates.
- Capture date is no longer used as a proxy for listing publication recency.
- Partial KPKNL inputs continue to run the known-cost calculation; a preliminary Walk Away is permitted if the indicative ARV proves the economic ceiling is below the limit.
