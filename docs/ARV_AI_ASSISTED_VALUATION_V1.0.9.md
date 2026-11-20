# AI-Assisted ARV Valuation — PFMS V1.0.9

## Role separation

- Gemini 3.5 Flash-Lite reads irregular user-supplied listing information and provides a review of relevance, data gaps, outliers, and bounded adjustment suggestions.
- Python validates source fields, rejects duplicates/excluded observations, normalizes comparable prices to subject LT/LB, applies approved adjustment percentages, uses weighted median, optionally calibrates against paired local market/NJOP observations, and produces ARV outputs.
- Gemini does not invent listing URLs, publication dates, transaction prices, or missing property facts. It does not fetch live internet listing data in this feature; the user supplies listing evidence or narratives.

## AI review behavior

For up to 20 comparable rows per request, Gemini returns per-row:
- relevance score (0–100; quality index, not probability),
- suggested adjustment percent bounded to -20%..+20%,
- whether the row should be excluded from the primary indication,
- rationale, data gaps, and risk flags.

Suggestions are not applied automatically. User must click the apply action and may edit the resulting `adjustment_pct` and exclusion flag in the table. Python then recalculates.

## Sparse/random data

- One to four usable listings can still produce a preliminary indicative ARV if there is a valid normalization basis.
- Fewer observations result in a wider uncertainty haircut/range and lower confidence index.
- Five usable, traceable individual listings and date-found evidence plus confidence >=55 remain required for final GO in auction underwriting.
- Listing publication date is optional; it is different from the date the user found/captured the listing. Missing publication date reduces recency certainty but is not itself a GO hard gate.
- A target NJOP alone is not converted into market value with a generic multiplier. NJOP calibration is only blended into base ARV when enough local comparable observations have paired market price and NJOP.
- If no usable comparable price/normalization basis exists, ARV remains unavailable. PFMS must not fabricate a price from AI language alone.

## Conservative range

The engine calculates a weighted-median base indication and a separate data-uncertainty haircut based on sample size, score quality, and price dispersion. Conservative ARV uses the greater of the configured quick-sale discount and calculated data-uncertainty discount. It also returns indicative low/high bounds.

These ranges and confidence scores are heuristic screening aids, not statistical confidence intervals, appraisals, or a guarantee of transaction price. They must be back-tested against actual completed sales as the PFMS portfolio grows.
