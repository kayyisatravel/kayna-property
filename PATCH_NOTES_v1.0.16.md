# PFMS V1.0.16 — Patch Notes

## Perbaikan utama

1. **Deduplikasi RAB berdasarkan lingkup.** Baris `USER_BOQ_*` menjadi sumber lingkup utama; pekerjaan generik AI/Python yang mengulang lingkup dihapus dengan alasan audit. Pembersihan barang bekas dipisahkan dari proteksi area kerja. Jika BoQ baru mencakup satu sisi dinding, allowance sisi yang belum masuk dipersempit menjadi 50% paket generik dan ditandai wajib ukur ulang.
2. **Penyimpanan Google Sheets untuk payload besar.** JSON dikompresi lalu, bila tetap lebih besar dari batas satu sel, dipotong menjadi chunk 40.000 karakter pada tab tambahan `PAYLOAD_CHUNKS`. Pembacaan menggabungkan dan memeriksa checksum. Retry memperbaiki chunk yang belum tertulis; snapshot tidak dihapus.
3. **Estimasi pasar tetap tampil saat sumber belum lengkap.** Tiga atau lebih pembanding tunai yang lolos validasi minimum dapat memberi indikasi pasar. Homepage portal diperbolehkan sebagai provenance screening, tetapi tidak dianggap URL listing individual. Status GO/READY tetap mensyaratkan setidaknya lima URL detail terkonfirmasi dengan tanggal dikumpulkan dan indeks kualitas minimal 55.
4. **Jarak lintas desa/kecamatan.** Jarak Haversine atau jarak garis lurus manual dalam meter dapat digunakan. Batas administrasi bukan hard filter.
5. **Segmen pasar dan over-kredit.** Primary/developer diberi bobot lebih rendah dari secondary/resale; over-kredit dipisahkan dari cash-market comparables.
6. **Validasi URL.** Mengubah nama, alamat, harga, LT, LB atau URL membatalkan konfirmasi URL detail sebelumnya.
7. **Tampilan.** Metrik maksimum empat kolom; dashboard kustom pengguna dipertahankan.

## Instalasi

Backup repository dan database terlebih dahulu. Ekstrak patch ke root repository V1.0.15, timpa file yang berubah, lalu commit/push. Jangan mengganti `.streamlit/secrets.toml`. Tab `PAYLOAD_CHUNKS` dibuat otomatis oleh `ensure_schema()` jika akun punya izin membuat worksheet.

## Tes

- `pytest -q`: 160 passed.
- `python -m compileall -q .`: passed.
- ZIP integrity: passed.
- Live Streamlit Cloud, Gemini dan Google Sheets user credentials tidak diuji.
