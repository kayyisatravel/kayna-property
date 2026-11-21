# Deployment Smoke Test — wajib sebelum penggunaan nyata

## 1. Infrastruktur
- [ ] Buat private GitHub repository dan upload seluruh isi folder proyek.
- [ ] Pastikan `.streamlit/secrets.toml` lokal tidak ikut ter-upload.
- [ ] Buat Google Cloud project; aktifkan Google Sheets API.
- [ ] Buat Service Account dan bagikan spreadsheet ke `client_email` sebagai Editor.
- [ ] Impor `templates/property-flipper-gsheets-template.xlsx` ke Google Sheets.
- [ ] Set `APP_PASSWORD`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `SPREADSHEET_ID`, dan object `google_service_account` di Streamlit Secrets.
- [ ] Tambahkan `DRIVE_FOLDER_ID` hanya jika arsip file binary ke Drive diperlukan.
- [ ] Deploy `app.py` pada Streamlit Community Cloud.

## 2. Smoke test AI parser
- [ ] Upload satu pengumuman lelang yang sudah diketahui datanya.
- [ ] Klik Parse dengan Gemini AI.
- [ ] Cocokkan kode lot, lokasi, tanggal, limit, deposit, LT/LB, sertifikat dan kutipan evidence dengan sumber.
- [ ] Pastikan data tidak tersedia tetap kosong/null.
- [ ] Pastikan screenshot diproses dan PDF tetap dikirim sebagai PDF native.
- [ ] Klik parse ulang untuk file yang sama setelah disimpan; pastikan extraction cache digunakan.
- [ ] Pastikan error 429 tidak memicu retry berulang.

## 3. Smoke test underwriting
- [ ] Tempel narasi lima listing bernomor dengan bullet detail dan klik Parse narasi dengan Gemini AI.
- [ ] Pastikan lima judul listing menghasilkan tepat lima baris tabel; bullet alamat/harga/spesifikasi/sumber tidak menjadi baris terpisah.
- [ ] Pastikan LB, kondisi, akses, URL langsung, dan tanggal publikasi yang tidak disebut tetap kosong; jangan diisi tebakan.
- [ ] Pastikan source platform (misalnya Rumah123/Pinhome) dan kutipan sumber dipertahankan sebagai provenance.
- [ ] Masukkan atau koreksi URL langsung dan tanggal iklan jika tersedia.
- [ ] Pastikan lima comparable usable dapat dihitung secara indikatif dari nama, harga, minimal satu luas, dan provenance sumber.
- [ ] Pastikan GO final mensyaratkan minimal lima comparable GO-grade yang masing-masing memiliki URL listing langsung dan tanggal ditemukan, serta confidence minimal 55/100.
- [ ] Pastikan tanggal ditemukan hasil parsing tidak dianggap sebagai tanggal publikasi iklan untuk penilaian recency.
- [ ] Masukkan comparable duplikat dan data yang kurang; pastikan sistem menandai invalid.
- [ ] Uji status Belum Survei; keputusan harus HOLD.
- [ ] Uji legal dispute; keputusan harus DO NOT BID.
- [ ] Uji max bid di bawah auction limit; keputusan harus DO NOT BID dan ceiling di bawah limit harus tetap ditampilkan.
- [ ] Uji analisis dengan KPKNL data parsial dan tanpa comparable: biaya akuisisi/proyek tetap dihitung, ARV/profit/ROI null, status HOLD (bukan crash/false zero ARV).
- [ ] Uji analisis dengan 1–4 comparable: ARV dan ceiling indikatif boleh tampil, tetapi GO final tidak boleh diberikan.
- [ ] Uji increment kosong; keputusan tidak boleh GO.
- [ ] Pastikan maximum bid memenuhi minimum ROI 25% pada conservative ARV.
- [ ] Pastikan target batas tengah mengikuti ROI 35%.

## 4. Smoke test cashflow
- [ ] Input real cash dan konfirmasi saldo.
- [ ] Input forecast outflow confirmed dan unconfirmed.
- [ ] Pastikan hanya outflow confirmed yang mengurangi kas tersedia.
- [ ] Ubah reserve 10%, 15%, dan 20%; pastikan perubahan memengaruhi kas siap investasi.
- [ ] Pastikan estimasi biaya proyek aktif tidak otomatis mengurangi kas kecuali pengguna memasukkannya sebagai outflow/komitmen.

## 5. Smoke test lifecycle
- [ ] Simpan objek HOLD dan pastikan tetap ada di Database & History.
- [ ] Simpan ulang analisis objek yang sama; pastikan analysis snapshot baru tercatat dengan `analysis_id` berbeda.
- [ ] Tandai satu objek sebagai WON dan masukkan harga menang.
- [ ] Pastikan objek masuk Active Properties.
- [ ] Tambahkan biaya aktual dan milestone.
- [ ] Tutup properti sebagai SOLD dengan harga closing dan biaya aktual lengkap.
- [ ] Pastikan properti masuk Closed Projects dan hitung profit/ROI aktual.
- [ ] Cocokkan Budget vs Actual dan audit HISTORY.

## 6. Benchmark TAS 3 M6/12
Gunakan hanya angka dan dokumen yang sudah diverifikasi. Jangan mengisi biaya legal/pajak atau harga closing yang belum diketahui dengan angka rekaan. Bandingkan hasil aplikasi dengan lembar perhitungan manual sebelum menjadikan aplikasi dasar keputusan bidding.


## 7. Regression V1.0.3 — Sheets save, RAB AI and guided risks
- [ ] Isi comparable dengan beberapa kolom angka kosong, simpan; pastikan tidak ada `InvalidJSONError` dan nilai kosong menjadi sel kosong di Sheets.
- [ ] Simpan risk register dengan satu baris kosong/diabaikan dan satu risiko terisi; pastikan tidak ada NaN di payload.
- [ ] Upload foto survei dan isi deskripsi aktual; klik `Susun RAB awal dengan Gemini`.
- [ ] Pastikan item RAB masuk sebagai satu baris per pekerjaan, memakai harga konservatif pada kolom `unit_cost`, dan tetap bisa diedit.
- [ ] Pastikan AI menandai bagian yang perlu inspeksi dan tidak menambahkan kerusakan interior/struktur yang tidak tampak atau tidak disebut.
- [ ] Ubah satu baris RAB setelah konfirmasi; pastikan checkbox tinjauan biaya kembali belum dicentang.
- [ ] Tambahkan risiko dari preset, ubah probabilitas/dampak/cadangan/mitigasi, dan pastikan risk review harus dikonfirmasi ulang setelah perubahan.


## 8. Smoke test form restore & renovation RAB (V1.0.6)
- [ ] Simpan objek dengan 3 kamar tidur, 2 kamar mandi, tipe Rumah 2 lantai, lebar jalan 6 m, akses 1 Mobil, kondisi Renovasi Sedang.
- [ ] Keluar/muat ulang objek yang sama dan pastikan seluruh pilihan tersebut kembali ke field masing-masing.
- [ ] Muat objek lain yang tidak punya field itu; pastikan nilai dari objek pertama tidak terbawa.
- [ ] Masukkan luas tapak aktual dan pastikan quantity atap memakai tapak tersebut; jika kosong, sistem memberi label estimasi LB/jumlah lantai.
- [ ] Uji Renovasi Kosmetik dan pastikan scope persiapan/dinding/plafon muncul; bila AI menghilangkan scope wajib, placeholder tanpa harga harus tampil.
- [ ] Uji Renovasi Ringan dan pastikan allowances lokal ber-confidence rendah tidak dianggap penggantian seluruh atap/MEP.
- [ ] Uji Auto + kondisi belum diketahui; sistem hanya memberikan inspeksi/persiapan, bukan mengasumsikan renovasi ringan.
- [ ] Uji Renovasi Berat; item struktur harus kosong dan meminta pemeriksaan engineer.
- [ ] Koreksi/hapus item RAB, centang ulang tinjauan biaya, analisis dan simpan snapshot baru.


## 9. Smoke test payload besar dan update Google Sheets (V1.0.7)
- [ ] Simpan satu properti dengan minimal lima comparable, risk register dan beberapa item RAB.
- [ ] Pastikan PROPERTIES tersimpan tanpa APIError.
- [ ] Pastikan `payload_json` panjang dapat dibaca kembali ke form melalui Database & History.
- [ ] Pastikan snapshot ANALYSIS_HISTORY dapat dibuka kembali tanpa terlihat marker kompresi pada UI.
- [ ] Ubah satu field dan lakukan update; pastikan satu baris PROPERTIES diperbarui dan snapshot analisis baru tercatat.
- [ ] Jika gagal, catat HTTP status/pesan Google yang ditampilkan; jangan menekan simpan berulang kali tanpa memeriksa baris yang mungkin sudah berhasil.


## 10. Smoke test UX, actual ledger correction and visual RAB (V1.0.11)
- [ ] Buka Dashboard Utama; pastikan anggaran aset berjalan, aktual dibayar, komitmen belum dibayar, dan forecast tersisa tampil terpisah untuk seluruh proyek WON/ACTIVE.
- [ ] Buka Properti Aktif; pastikan tabel riwayat transaksi dan budget hanya-baca. Form input pembayaran, tambah budget dan edit budget berada pada expander/form yang jelas.
- [ ] Tambahkan satu transaksi historis bernilai kecil untuk uji; wajib centang konfirmasi, tanggal memakai date picker, dan setelah sukses field teks/nominal kembali kosong.
- [ ] Koreksi transaksi uji (ubah nominal/tanggal/kategori); pastikan `actual_id` tetap sama, nilai sebelum/sesudah tercatat di HISTORY, dan saldo commitment/forecast ditarik balik lalu diterapkan sesuai tautan baru.
- [ ] Uji koreksi yang melebihi saldo komitmen/forecast; aplikasi harus menolak sebelum mengubah transaksi atau budget.
- [ ] Pastikan item budget hanya dapat diedit setelah expander Edit dibuka secara sengaja; perubahan membutuhkan konfirmasi.
- [ ] Pastikan tanggal listing dan tanggal ditemukan pada comparable memakai DateColumn/date picker; tanggal kosong tetap kosong, dan tanggal `DD/MM/YYYY` lama tidak tertukar bulan/hari.
- [ ] Jalankan RAB dengan deskripsi contoh: kanopi depan galvalum jebol, dinding carport lembap/jamur, rabat beton retak, pagar besi kusam, peti kayu di depan, interior belum diperiksa.
- [ ] Pastikan AI/Python memunculkan scope lokal untuk atap depan, pemeriksaan plafon terdampak, dinding lembap, lantai carport, cat pagar dan pembersihan area depan; area yang harus diukur tidak diberi quantity seolah-olah sudah diketahui.
- [ ] Pastikan interior yang tidak terlihat ditampilkan sebagai unknown + inspection plan + skenario sensitivitas terpisah; jangan otomatis dimasukkan sebagai kerusakan atau biaya dasar.
- [ ] Periksa PATCH_NOTES V1.0.11 dan catat setiap perbedaan hasil sebelum penggunaan rutin.


## 11. Regression V1.0.12 — RAB evidence and bidding logic audit
- [ ] Use the TAS 3 M6/12 narrative with the primary statement Renovasi Sedang and a later caveat that it may become Renovasi Berat after inspection; ensure the current category remains Renovasi Sedang.
- [ ] Ensure front-canopy sheet replacement is one local item and no generic whole-roof replacement is costed on the same area.
- [ ] Ensure damp carport wall treatment is one item and no generic wall package duplicates the same wall area.
- [ ] Ensure rabat beton cracks do not trigger ceramic installation without explicit tile-damage evidence.
- [ ] Ensure fence repaint/facade repaint and hidden frame repair remain conditional until user confirms the scope.
- [ ] Ensure custom measured volumes are blank unless entered from field measurement; AI must not infer m² from photo scale.
- [ ] Ensure interior scenarios remain separate from base RAB and do not auto-add hidden defects to budget.
- [ ] Ensure occupancy status is not inferred from plants, buckets, cloths, belongings or dark rooms; use survey field or show unknown.
- [ ] If an in-scope base RAB item lacks measured quantity or conservative unit rate, label the RAB incomplete and prevent final GO. Partial subtotal must not be labelled total RAB.
- [ ] Bid case: limit Rp160.000.000, conservative ARV Rp300.000.000, ROI target 35%; ensure no actionable bid below limit is shown. If theoretical ceiling is below limit, show it only in the diagnostic column.
- [ ] Ensure maximum bid/ROI 25% is aligned to auction limit + confirmed official increment.
- [ ] Clear the official increment: no legal mid bid, maximum bid or walk-away is issued; any computation-only ceiling must be explicitly labelled simulation.
- [ ] Compare all displayed bid prices with official auction announcement and verify ROI against manual calculation before live bidding.
