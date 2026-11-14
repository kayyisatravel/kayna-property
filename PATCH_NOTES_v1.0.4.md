# Patch Notes — PFMS V1.0.4

## Fixed
- Markdown bold and linked numbered headings are recognized as separate comparable listings.
- Seven comparable narratives are parsed in two batches (4 + 3) to reduce response size.
- Compact aliased JSON schema reduces output length.
- Gemini finish reason is captured; `MAX_TOKENS` and incomplete JSON produce a clear error without populating partial rows.
- URLs are extracted from original input per listing. Google kgmid links are excluded.
- `source_url_scope` distinguishes individual listing pages from portal/category/venue pages. Only individual listing URLs count toward GO-grade evidence.
- Comparable table schema version updated to reset old Streamlit editor state and expose source URL scope.

## Files changed
- `services/gemini_parser.py`
- `app.py`
- `core/market_engine.py`
- `tests/test_comparable_ai_parser.py`
- `tests/test_market_engine.py`
- `config.py`
- `README.md`, `CHANGELOG.md`, `docs/COMPARABLE_AI_PARSER.md`, `docs/DATA_DICTIONARY.md`, `docs/CALCULATION_RULES.md`

## Deployment
Replace the files above in the existing GitHub repository, commit and push. No Google Sheets header change and no Secrets/API key change are required. Existing COMPARABLES payload_json already stores the new source_url_scope value.
