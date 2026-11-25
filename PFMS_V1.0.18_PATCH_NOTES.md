# PFMS V1.0.18 — Patch Notes

Tanggal rilis: 25 November 2026

## Added
- KPKNL document parsing prefills auction date, deposit deadline and payment deadline into editable date pickers, with field evidence and source document hash. Ambiguous dates are not guessed.
- Auction outcome reference records for the user's wins, another bidder's win, unsold/no-bid and cancelled auctions, including winning price, price type, source grade and URL; no personal winner identity is stored.
- Market & Auction Data explorer with text/status/value filters, sort by price/date/limit and CSV export. Data reads use 300-second Streamlit cache; local sorting/filtering does not create additional Sheets reads.
- Official regional economic context snapshot for Sidoarjo/East Java when geography and freshness checks pass. It is contextual only and does not automatically adjust property value.
- Deterministic renovation duration calculator from BoQ quantities and work-category productivity, with fast/base/conservative scenario, phase sequencing and schedule buffer.
- In-app target-sale reminders and budget usage alerts at 70%, 85% and 100% thresholds.
- Investment Memo now uses Kayna Property project-operator header, minimum 11pt DOCX text, property-based filenames, RAB and renovation schedule sections, and optional sourced regional-economic context.

## Changed
- Date fields are deliberately editable; KPKNL document data is an initial selection, not a lock.
- Budget variance is `budget - projected completion`: positive is remaining budget; negative is forecast overrun.
- Explorer reads cached worksheet data and applies filters/sorting in local memory to reduce Google Sheets API calls.
- Memo generation uses the saved analysis snapshot and Python; no extra Gemini call is required.

## Not included / limitations
- Economic snapshot is current only as of 2026-11-25 and is not a live feed. It does not represent secondary-home transaction prices at neighborhood level.
- In-app reminders appear when the user opens the project page; no email, push, or background scheduler is included.
- Renovation duration is an initial productivity-based estimate, not a contractor commitment.
- Google Sheets, Gemini and Streamlit Cloud live credentials have not been tested here.

## Safety and compatibility
- Additive `AUCTION_OUTCOMES` worksheet; no destructive removal of existing tabs/headers.
- Preserve `.streamlit/secrets.toml` during upgrade.
