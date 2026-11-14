# AI Comparable Narrative Parser

## Intended input

Paste prose in which each property begins with a numbered heading and its bullets follow underneath, for example:

```text
1. Rumah Hook Siap Huni
- Alamat: ...
- Harga penawaran: Rp 550.000.000
- Spesifikasi: LT 123 m2, LB 100 m2, 2 KT, 2 KM
- Sertifikat: SHM
- Sumber: Rumah123 dan OLX Indonesia

2. Rumah Minimalis Full Renovasi
- Alamat: ...
- Harga penawaran: Rp 485.000.000
- Spesifikasi: LT 120 m2, LB 100 m2
- Sumber: Pinhome dan Brighton
```

The parser instruction explicitly groups the entire section under each numbered heading into one comparable record. It must not convert each bullet into a separate row.

## Parsing contract

- One numbered property heading = one output row. Python detects sequential numbered sections first and checks the number of Gemini rows against the detected section count; a mismatch is rejected rather than loaded into the table.
- Price is stored as integer IDR.
- LT/LB remain separate fields. Missing LB is `null`, not zero.
- Unknown condition/access/certificate remain blank.
- Source platform names and source evidence are preserved.
- A direct listing URL is only stored if supplied in the pasted text. The model must never construct a URL from a portal name.
- `date_found` is the local date the user parsed/imported the text. It is an audit/capture date, not the listing publication date.
- `listing_date` remains blank unless the pasted source explicitly provides it. The valuation freshness score uses `listing_date`; it does not treat the capture date as proof that the listing itself is newly published.
- The user must review the table before running underwriting.

## Comparable eligibility

For preliminary price normalization, a row needs a name/address, positive price, at least one comparable area (LT or LB), and source provenance (direct URL, platform name or source evidence). Missing LB, condition, access, certificate, publication date and direct URL lower quality/confidence instead of automatically discarding the listing.

Distinguish two counts: `valid_count` means rows usable for indicative valuation; `go_grade_count` means rows with a direct listing URL and capture date, so an auditor can return to the exact listing evidence. Five GO-grade comparable rows and market confidence of at least 55 are required for final GO. A portal name such as Pinhome or Rumah123 without the specific listing URL may be used provisionally but does not count as GO-grade. Therefore five parsed rows do not guarantee GO.

## Partial underwriting behavior

The `ANALISIS SEKARANG` action does not require every KPKNL field to be filled. When auction limit exists, Python can still calculate acquisition and project cost estimates. If no defensible ARV can be produced, profit and ROI stay `null` rather than treating sale price as Rp0; the status is HOLD because market exit cannot yet be tested.

If the available comparable evidence produces an indicative conservative ARV and the calculated economic maximum bid is already below the auction limit, the system can report DO NOT BID / WALK AWAY. With fewer than five comparable rows, without five GO-grade URLs, or with low confidence, that conclusion is explicitly preliminary and cannot become GO. If the subject property's land/building area and comparable evidence are both insufficient to estimate ARV, the application still calculates known costs but returns HOLD; it must not invent a sale price or fake a walk-away number.

## Quota and reliability

Comparable parsing is an explicit user-triggered Gemini request, not an automatic call on every edit or rerun. It uses the configured single model `gemini-3.5-flash-lite`, a fixed Pydantic schema without dynamic dictionary fields, and limited output tokens. API errors do not stop manual editing or Python underwriting.
