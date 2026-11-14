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


## Memasukkan comparable dalam bentuk narasi

1. Cari listing dari portal properti dan salin uraian listing.
2. Gabungkan setiap listing dengan judul bernomor (1., 2., 3.) serta seluruh bullet informasinya.
3. Tempel seluruh teks ke kotak **Paste narasi 5+ listing**.
4. Klik **Parse narasi dengan Gemini AI**. Setiap judul listing beserta bullet turunannya harus menjadi satu baris tabel, bukan satu baris per bullet.
5. Periksa harga, LT/LB, kondisi, akses, sertifikat, platform sumber, URL, serta catatan. Nilai yang tidak disebutkan tetap kosong. AI tidak boleh membuat URL atau tanggal iklan.
6. `Tanggal ditemukan` dicatat oleh sistem sebagai tanggal impor; `Tanggal iklan` hanya diisi bila sumber menyebutkannya.
7. Listing dengan sumber platform tetapi tanpa URL langsung dapat dipakai sebagai indikasi awal; tambahkan URL langsung untuk memperkuat audit dan confidence.

## Analisis dengan data KPKNL belum lengkap

Tombol **ANALISIS SEKARANG** tidak menunggu semua field lengkap. Sistem menghitung komponen biaya yang tersedia. Jika ARV belum bisa dibangun, profit dan ROI ditampilkan sebagai belum tersedia (bukan dianggap nol), dan status menjadi HOLD. Jika data pasar yang ada sudah cukup untuk menunjukkan maximum bid di bawah nilai limit, hasil dapat menunjukkan DO NOT BID/Walk Away. Lima comparable dan seluruh hard gate tetap wajib untuk GO final.


### Catatan parser comparable berbentuk narasi
Tempel seluruh narasi listing bernomor (1., 2., 3.) beserta bullet di bawah masing-masing judul, lalu klik Parse narasi dengan Gemini AI. Sistem mendeteksi jumlah blok bernomor dan menolak hasil AI bila jumlah baris tidak sama, sehingga bullet tidak boleh berubah menjadi listing terpisah. Platform sumber seperti Rumah123/Pinhome disimpan sebagai provenance; URL langsung tidak dibuat-buat. Listing tanpa URL dapat masuk valuasi indikatif, tetapi tidak dihitung sebagai comparable GO-grade untuk persetujuan GO final.

Analisis parsial tetap dapat dijalankan dengan data KPKNL yang tersedia. Jika limit tersedia, biaya pada harga limit dihitung meskipun ARV belum dapat ditentukan. Profit/ROI akan ditampilkan sebagai belum tersedia, bukan Rp0. Jika ARV indikatif menunjukkan maximum bid di bawah limit, sistem dapat memberi DO NOT BID / WALK AWAY meskipun data belum lengkap; keputusan tersebut diberi label preliminary dan tidak dapat menjadi GO. Jika LT/LB objek dan comparable tidak cukup untuk valuasi, hasilnya HOLD karena batas ekonomi belum bisa dihitung secara bertanggung jawab.
