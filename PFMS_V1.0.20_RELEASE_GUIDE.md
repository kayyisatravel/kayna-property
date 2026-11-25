# PFMS V1.0.20 — Release Guide

## Purpose
This release refines the investor-facing proposal and corrects active-project renovation progress reporting while preserving the existing underwriting and project workflow.

## Proposal terminology and presentation
- The external-facing document is named **Proposal Investasi Properti**. This is easier to understand for both private investors and new investors than an internal-sounding memorandum.
- Kayna Property remains identified as **PROPERTY INVESTMENT & PROJECT MANAGEMENT**.
- The V1.0.19 navy palette and minimum 11 pt font are retained. Table layout returns to the cleaner V1.0.18-style shading and spacing. Header/body separation is increased.
- Comparable table columns: full address, asking price, LT/LB and URL/source.
- Capital, selling-cost/profitability and bid-strategy tables start with a numeric bid value; descriptive scenario labels are placed in notes.

## Renovation progress: how it is calculated
Progress is not inferred from the existence of a BoQ or from expenditure. For each measurable renovation work line in `PROJECT_BUDGETS`, the user records physical status: `Belum diperbarui`, `Belum mulai`, `Berjalan`, or `Selesai`. A running item may also receive an estimated completion percentage.

The project's aggregate progress is weighted by the estimated workdays for each line, using the same task-duration estimator as the RAB and overall renovation schedule. The UI shows both the weighted progress and the tracking coverage (`status updated / eligible work lines`).

- If no physical work status has been recorded, the report displays **Belum diperbarui**, not 0%.
- Payment amounts and invoice status do not count as physical completion.
- If a project has no measurable work lines, existing milestone records are used as a fallback.
- The overall renovation duration remains a critical-path estimate; summed task workdays can exceed the calendar duration because tasks may run in parallel.

For TAS 3 M6/12 or another active project, open project budget/renovation work items and update the physical status of each work line. Merely entering the work description/BoQ does not prove that the task has started or finished.

## RAB schedule
Each RAB row displays volume, unit rate, line subtotal and fast/base/slow estimated duration. The total row sums the same in-scope rows as the RAB; the project-level schedule uses the same productivity assumptions and dependency/parallel-work logic.

## Compatibility and deployment
- No new Google Sheets tab or destructive column migration is required. Progress fields are additive inside existing `PROJECT_BUDGETS` payloads.
- Google Sheets portfolio reads use the existing cache. Proposal generation is local Python and does not call Gemini.
- Back up the repository before upgrade. Extract the upgrade patch into the root of the V1.0.19 repository, commit and push.
- **Do not overwrite `.streamlit/secrets.toml`.** Keep `secrets.toml.example` as the template only.

## Verification scope and limitations
- Regression suite: 198 passed.
- Python compile check passed.
- DOCX rendered and visually reviewed page by page.
- Full ZIP and patch ZIP were tested from fresh extraction/overlay.
- Live Streamlit Cloud, Google Sheets credentials and Gemini credentials were not available for end-to-end deployment testing.
