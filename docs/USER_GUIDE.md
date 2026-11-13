# User Guide — PFMS V1

## First-time setup

1. Deploy and set `APP_PASSWORD`.
2. Connect Google Sheets and update data.
3. Enter real cash on Investor Cashflow and confirm it.
4. Adjust reserve percentage between 10% and 20%.
5. Review Settings & Rules for the object's region and auction type.

## Analyze an auction lot

1. Select New Auction Analysis → Buat objek baru.
2. Upload the auction notice/screenshot. Press Parse dengan Gemini AI.
3. Review every auto-filled field and evidence. Fill missing values only from reliable sources.
4. Complete survey status, occupancy, condition, interior inspection, risk register and cost estimates.
5. Paste comparable data with header columns. Validate each row and URL.
6. Check local tax/auction rule source and review cost assumptions.
7. Press ANALISIS SEKARANG.
8. Review blockers, warnings, conservative ARV, ROI, maximum bid and walk-away.
9. Save the analysis even when decision is HOLD/DO NOT BID if you want to preserve the opportunity record.

## Copy-paste comparable table

Recommended columns (tab-separated):

`Alamat / Nama Listing | Harga Listing (IDR) | Luas Tanah (m2) | Luas Bangunan (m2) | Kondisi | Akses Jalan | Status Harga | Sertifikat | URL Sumber | Tanggal Ditemukan`

Use valid categories:
- Kondisi: `Siap Huni`, `Butuh Renovasi`, `Hitung Tanah`.
- Akses: `2 Mobil`, `1 Mobil`, `Gang`.
- Status Harga: `Asking aktif`, `Marked sold / perlu verifikasi`, `Transaksi terverifikasi`.

Do not label a portal's marked-sold status as verified transaction unless you have evidence. Missing condition/access is left blank and the row is invalid until corrected.

## After winning an auction

1. Open Database & History.
2. Change lifecycle to WON and enter actual winning price and win date.
3. Open Active Properties.
4. Record actual expenses as they occur. Record purchase acquisition exactly once; deposit credited to settlement is not an extra cost on top of total winning price.
5. Update project stage and milestones.
6. Add actual legal, possession, renovation, holding, marketing and selling expenses.
7. When sold, enter closing price, selling cost and total holding months; confirm actual cost completeness.

## Notes

- Keep the Google Sheets schema/header names unchanged.
- Update real cash regularly. Forecast outflows are only deducted when marked confirmed.
- Historical analyses are immutable snapshots; analyze again to create a new snapshot.
- Use Drive archive if original documents/photos must persist. Without Drive archive, file binaries are not retained, only metadata and hashes.
