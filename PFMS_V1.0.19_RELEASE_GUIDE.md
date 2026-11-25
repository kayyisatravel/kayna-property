# PFMS V1.0.19 — Release Guide

## Tujuan rilis
Meningkatkan Memorandum Investasi Properti agar menjadi dokumen underwriting yang mudah dibaca investor, dapat ditelusuri, dan konsisten dengan hasil hitung PFMS.

## Terminologi yang digunakan
- Judul: **Memorandum Investasi Properti** (Property Investment Memorandum).
- Branding: **KAYNA PROPERTY | PROPERTY INVESTMENT & PROJECT MANAGEMENT**.
- Istilah "Pelaksana Proyek" tidak dipakai karena dapat memberi kesan Kayna Property adalah kontraktor pelaksana konstruksi. Deskripsi baru lebih tepat untuk aktivitas akuisisi, pengelolaan investasi, koordinasi renovasi, anggaran, dan pemasaran aset.

## Isi dokumen
1. Ringkasan eksekutif dan identitas aset.
2. Tanggal analisis dalam WIB.
3. Informasi lelang, legalitas dan kondisi fisik dari data yang tersedia.
4. Pembanding pasar: harga penawaran, LT/LB, alamat lengkap, dan sumber. Kolom jarak tidak dicantumkan.
5. Tiga skenario bidding (limit, tengah, atas): estimasi modal, kas dan cadangan risiko, biaya penjualan, penjualan bersih, profit serta ROI.
6. Strategi penawaran dengan ROI target dan ROI simulasi.
7. RAB dengan subtotal tiap item, total, rentang harga dan estimasi hari kerja tiap item.
8. Estimasi jadwal renovasi/critical path. Durasi tiap item tidak dijumlahkan secara langsung karena beberapa pekerjaan dapat berjalan paralel.
9. Lampiran proyek aktif dan proyek selesai dari database.
10. Asumsi, sumber, keterbatasan dan penafian.

## Konteks ekonomi regional
Konteks ekonomi regional sengaja tidak dimasukkan pada V1.0.19. Modul yang tersedia sebelumnya berisi snapshot historis, bukan feed dinamis yang dapat divalidasi pada waktu pembuatan memo. Jangan menambahkan kesimpulan makro sampai ada provider resmi yang mengambil data terbaru, menyimpan tanggal publikasi/periode data, URL sumber, dan freshness check.

## Data portfolio
Lampiran aktif dan selesai dibuat dari tabel existing melalui fungsi baca yang telah memakai cache Google Sheets 300 detik. Tidak ada pemanggilan Gemini dan tidak ada penulisan portfolio context ke Sheets. Jika data milestone, biaya aktual, komitmen, budget, atau closing tidak tersedia, memo menampilkan status belum dicatat atau tanda kosong, bukan membuat asumsi.

## Durasi RAB
Durasi item memakai fungsi `estimate_item_duration()` yang sama dengan mesin estimasi durasi renovasi. Total durasi proyek mengikuti estimasi critical path dan mempertimbangkan pekerjaan yang berpotensi paralel. Karena itu total hari semua item tidak boleh dijumlahkan secara manual.

## Foto properti
Foto sengaja tidak ditanam otomatis ke memo. Ini menghindari ketergantungan pada file biner/Drive dan menjaga payload Google Sheets. User masih dapat melampirkan foto secara manual di luar sistem bila diperlukan untuk presentasi tertentu.

## Upgrade V1.0.18 ke V1.0.19
1. Backup repository dan Google Sheets.
2. Ekstrak upgrade patch ke root repository V1.0.18 dan timpa file yang berubah.
3. Jangan menimpa atau menghapus `.streamlit/secrets.toml`.
4. Commit dan push ke GitHub untuk deployment ulang Streamlit Cloud.
5. Uji satu memo analisis baru, lalu cek tanggal WIB, pembanding, tiga skenario bidding, total RAB, durasi item, dan lampiran portfolio.

Tidak diperlukan migrasi destruktif pada Google Sheets. Tidak ada tab/header existing yang dihapus atau diganti. Rilis ini belum diuji live dengan kredensial Gemini, Google Sheets, maupun deployment Streamlit Cloud milik pengguna.
