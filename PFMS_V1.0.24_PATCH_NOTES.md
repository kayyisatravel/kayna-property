# PFMS V1.0.24 — Patch Notes

## Perbaikan utama

1. `optional_date_picker` dan helper tanggal lain dipindahkan ke bagian awal `app.py`, sebelum authentication gate dan navigasi halaman. Ini memperbaiki error `NameError` pada field tanggal berakhir SHGB dan mengurangi risiko helper tidak didefinisikan pada jalur render lain.
2. Ditambahkan static scan berbasis Python `symtable` sebagai regression test untuk mendeteksi global name yang dipanggil tetapi tidak didefinisikan/diimpor.
3. Tanggal lelang dan batas setor tetap memakai date picker yang otomatis diprefill dari dokumen KPKNL dan tetap dapat dikoreksi. Tidak ada checkbox konfirmasi tambahan.
4. Batas pelunasan hanya informasi: estimasi lima hari kerja Senin–Jumat setelah tanggal menang aktual. Sebelum menang, tanggal lelang hanya dipakai sebagai simulasi. Kalender hari libur tahunan dihapus dari aturan kalkulasi agar tidak perlu patch tahunan; hari libur nasional/cuti bersama tidak otomatis dikecualikan. Dokumen atau konfirmasi resmi KPKNL tetap menentukan tenggat sebenarnya.
5. Analisis Objek Lelang menggunakan alur bertahap empat langkah. Tombol navigasi hanya memindahkan langkah; data dipertahankan dalam sesi. Penyimpanan permanen dilakukan setelah tombol Analisa/Update Data pada langkah terakhir muncul dan dijalankan.
6. Validasi langkah 1–4 dijalankan sebelum lanjut/analisis. Minimal tiga pembanding unik bersumber cukup untuk estimasi indikatif; keputusan GO dapat memerlukan minimal lima pembanding individual sesuai underwriting policy.
7. Uji regresi menambahkan pemeriksaan persist/restore state, helper date picker sebelum auth gate, no undefined global references, dan maksimal empat kolom UI.

## Kompatibilitas
- Upgrade dari V1.0.23.
- Tidak ada perubahan destruktif pada tab/header Google Sheets.
- Tidak menambah worksheet baru.
- Tidak menyertakan atau menimpa `.streamlit/secrets.toml`.

## Verifikasi
- `pytest -q`: 238 passed.
- `python -m compileall -q .`: passed.
- Static scan `symtable`: tidak ada global reference yang belum didefinisikan/diimpor.
- Full source dan patch overlay diuji terpisah.
- Live Streamlit Cloud / Google Sheets / Gemini tidak diuji dengan kredensial pengguna.
