# PFMS V1.0.22 — Release Guide

## Rekomendasi kebijakan Kayna Property

V1.0.22 menerapkan default underwriting berikut:

| Parameter | Default |
|---|---:|
| Minimum Project ROI all-in | 20% |
| Target Project ROI all-in | 30% |
| Profit bersih minimum | Rp50.000.000 |
| Target holding period | 90 hari |
| Holding period maksimum | 180 hari |

Tidak ada batas maksimum keuntungan atau ROI. ROI 30% adalah target, bukan cap. Proyek dapat dinilai GO ketika ROI sekurang-kurangnya 20%, profit bersih sekurang-kurangnya Rp50 juta, durasi tidak melebihi 180 hari, kas cukup, dan seluruh gate data, legalitas, pasar, biaya, increment, serta risiko terpenuhi. Proyek 91–180 hari menerima peringatan; lebih dari 180 hari tidak lolos underwriting jika durasi dapat dihitung. Durasi yang tidak diketahui menghasilkan HOLD. Estimasi 90/180 hari saat ini menghitung fase pasca-menang/pelunasan: penguasaan, delay legal, renovasi, dan pemasaran/closing. Batas setor jaminan bukan tanggal pembayaran aktual; catat tanggal pembayaran uang jaminan yang benar-benar terjadi pada cashflow agar masuk dalam XIRR.

## Definisi keuangan

Project ROI utama dihitung secara all-in:

`Profit Bersih / (Modal Pra-Penjualan + Biaya Penjualan) × 100%`

Annualized ROI adalah ekuivalen matematis dari ROI proyek berdasarkan durasi asumsi. Angka itu bukan XIRR dan bukan jaminan return berulang. XIRR aktual hanya dihitung dari arus kas aktual yang seluruhnya bertanggal, tanggal closing, dan biaya penjualan yang sudah direkonsiliasi.

Maximum Bid yang dapat ditindaklanjuti menggunakan Quick Sale / Conservative ARV dan wajib memenuhi ROI minimum, profit minimum, durasi maksimum, hard ceiling risiko, kas, dan increment resmi. Base ARV dan Upper ARV digunakan sebagai sensitivitas, bukan hard-cap utama.

## Upgrade dari V1.0.21

1. Backup repository GitHub dan Google Sheets.
2. Ekstrak `pfms-v1.0.22-upgrade-patch.zip` ke root repository V1.0.21 dan izinkan file yang berubah ditimpa.
3. Jangan mengganti atau menghapus `.streamlit/secrets.toml`. File rahasia tidak disertakan dalam ZIP.
4. Commit dan push ke GitHub agar Streamlit Cloud melakukan deployment ulang.
5. Setelah deployment, buka Settings & Rules. Periksa Minimum ROI 20%, Target ROI 30%, Minimum Profit Rp50 juta, Target 90 hari, dan Maksimum 180 hari. Klik Simpan Asumsi untuk menyimpan kebijakan default yang sudah dimigrasikan ke RULES_CONFIG.
6. Jalankan satu analisis uji. Pastikan RAB, harga pembanding, pajak/biaya, legalitas, risk register, increment, tanggal, durasi, dan kas sudah lengkap sebelum menggunakan Maximum Bid.

## Perhatian pada data historis

- Analisis yang disimpan sebagai snapshot lama tidak diubah massal. Analisis ulang diperlukan untuk mendapatkan angka berdasarkan formula ROI all-in dan ambang V1.0.22.
- Jika ada custom rule, periksa Settings & Rules sebelum menyimpan. Migrasi hanya mengganti pasangan default lama 25% / 35%; nilai custom lain dipertahankan.
- Struktur tab/header Google Sheets lama tidak dihapus atau diubah secara destruktif.
- XIRR historis mungkin belum tersedia bila tanggal transaksi aktual belum dicatat. Jangan mengisi tanggal perkiraan ke ledger aktual hanya agar XIRR muncul.

## Validasi

Pengujian lokal: 218 regression tests passed dan Python compile check passed. Paket diuji dari full source dan dari patch yang ditumpangkan ke V1.0.21. Pengujian belum menggunakan kredensial Google Sheets/Gemini atau deployment Streamlit Cloud pengguna.

## Dokumen metodologi

Lihat `docs/KAYNA_FLIP_UNDERWRITING_POLICY_V1.0.22.md` untuk rincian gate, perhitungan ARV, ROI, XIRR, maximum bid, dan batasan model.
