# PFMS V1.0.12 — Logic Audit: Renovation RAB & Bidding

## Executive result
The audit corrects evidence classification and overlapping scopes in renovation RAB, the handling of incomplete estimates, occupancy inference, and bid prices below the auction limit. It does not claim that generic AI unit prices are local contractor quotes.

## 1. RAB logic defects and controls

| Potentially incorrect behaviour | Correct control in V1.0.12 |
|---|---|
| Caveat “may shift to heavy if inspection finds…” overrides primary Renovasi Sedang label | Explicit primary category statement is resolved before later risk/caveat text. |
| Local canopy roof damage creates whole-roof replacement quantity | Local front-roof line is used; whole-roof quantity is disabled unless full replacement is explicitly confirmed. |
| AI adds both special damp-wall line and generic medium wall line | Duplicate generic wall line is suppressed for the same wall surface. |
| Rabat beton cracks create automatic ceramic replacement | Ceramic line is suppressed absent explicit ceramic damage; carport repair remains conditional pending method/measurement. |
| AI guesses m²/volume using photo scale | Python catalog is authoritative for known work codes; custom/measured work volumes remain blank until field measurement. |
| Hidden structure/interior is treated as confirmed damage | Structural work remains engineer-led; interior scenarios/inspection remain separate from base RAB. |
| Belongings/plants/dark room used to infer occupancy | Occupancy is user survey data or explicit unknown; not inferred from image. |
| A small priced subtotal is displayed like a complete RAB | UI labels partial priced items as subtotal; complete RAB requires every in-scope row to have positive quantity and conservative rate. |

## 2. Correct handling of the TAS 3 M6/12 description

Expected category: **Renovasi Sedang**. It is a present condition classification, not a statement that all medium-category building systems require replacement.

Work scopes supported by evidence:
- Local damaged front canopy/galvalum: measure the affected canopy area; replacement of frame only if the frame itself is found damaged.
- Damp carport wall: locate the water source; measure affected wall surfaces; remove damaged finish, treat mould, repair plaster/waterproof and repaint after it is dry. Do not price the same surface again as a generic wall package.
- Porch ceiling: inspect where leakage could have reached. Replacing the ceiling is not a fact until damage is seen.
- Carport rabat concrete: inspect crack depth and base settlement; determine local patch vs recast/other treatment. Do not assume ceramic upgrade.
- Metal fence repaint: optional/conditional if it is a desired cosmetic improvement; no assumption of structural fence replacement.
- Front cleanup: a distinct allowance if removal is authorised and needed.
- Interior: inspection and separate normal/damaged scenarios; no hidden repair becomes base cost before inspection.
- Main structure: no structural strengthening or heavy category solely from the caveat. If inspection identifies structural concern, require engineer assessment.

Since canopy and damp-wall dimensions are absent, the correct RAB result is **incomplete**, not a fabricated Rp total. A subtotal of only fully quantified lines must be shown as a subtotal. User should measure dimensions and obtain local prices before approving.

## 3. Unit-price source limitations

The current RAB call provides Gemini with property context, photos and the user's description, but no live Sidoarjo price database, current HSPK/SSH extract, or contractor quotations. Therefore unit prices suggested by the model are screening estimates only. They must not be described as verified Sidoarjo local rates.

For a stronger future price engine, add a separate `PRICE_BOOK` with: work code, exact specification, material components, labor components, equipment, unit, location, source, source date, validity period, tax/transport notes and confidence. Price build-up should be deterministic in Python; Gemini classifies scope, maps descriptions to catalogue items and explains deviations. Official SSH/HSPK is a reference baseline, then validate residential-private-work rates with at least two like-for-like local quotes.

## 4. Bidding logic audit

- Auction limit is the legal lower bound for actionable bids.
- Mid target ROI (default 35%) means the highest bid at or above limit and on the confirmed increment ladder that meets the target. It is not the auction limit, nor may it be shown below the limit.
- If the theoretical ROI-35 ceiling is below the limit, `mid_bid` must be blank. Display the below-limit value only as “ceiling teoritis (bukan harga bid)”.
- Maximum bid (default 25% project ROI) is calculated from the auction limit plus n × official increment.
- Walk-away is one official increment above maximum bid. Do not issue it if increment is unknown.
- If increment is unknown, all bid prices remain non-actionable; a small computation step may be shown only as a simulation ceiling.
- Cash adequacy is a separate funding test. Lack of cash is not a reason to lower the economic bid ceiling; it produces HOLD for funding.

### Example regression
For the tested scenario with limit Rp160,000,000, Conservative ARV Rp300,000,000 and the fixture cost assumptions in `tests/test_logic_audit_fixes.py`, the ROI-35 theoretical ceiling is below limit (approximately Rp147.37m). Therefore the correct actionable mid bid is **None**, not Rp145m. With a confirmed Rp1m increment, the tested ROI-25 maximum is Rp162m and walk-away is Rp163m. These numbers are for the test fixture only, not a recommendation on an actual property.

## 5. Remaining limitations / no false claims

- AI cannot recover actual negotiated market price from listing text alone. Transaction evidence is required for factual realized price.
- A price estimate with one or two weak comparables remains wide-uncertainty and indicative.
- Photo-based scope selection is not structural inspection or quantity surveying.
- Local unit-price accuracy remains limited until a curated Sidoarjo price book and actual contractor quotes are added.
- Live Gemini, Google Sheets and Streamlit Cloud integration tests have not been run as part of this local code audit.
