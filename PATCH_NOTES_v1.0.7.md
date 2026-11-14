# PFMS V1.0.7 — Google Sheets write/update fix

## Gejala

Penyimpanan analisis gagal saat `GoogleSheetsDB.upsert_record()` memperbarui baris `PROPERTIES` melalui `worksheet.update()`. Traceback yang terlihat pengguna tidak memuat body respons Google, sehingga penyebab HTTP yang persis belum dapat dipastikan hanya dari traceback.

## Akar masalah yang paling mungkin ditangani

Kolom `PROPERTIES.payload_json` menyimpan gabungan `input_data` dan snapshot `latest_analysis`. Saat form memuat banyak comparable, item RAB, risk register, dan hasil perhitungan, isi satu sel dapat melewati batas Google Sheets sekitar 50.000 karakter. V1.0.7 mengompresi JSON panjang menggunakan gzip + base64 dengan marker versi, lalu otomatis mendekompresinya saat data dibaca.

## Perubahan tambahan

- Semua kolom JSON (`payload_json`, `value_json`, `details_json`, `extraction_json`) mendapat kompresi transparan bila melewati ambang.
- Nilai teks biasa yang terlalu panjang ditolak sebelum request dikirim; aplikasi tidak memotong data diam-diam.
- Error Google ditampilkan dengan HTTP status, pesan API, nama tab dan range bila tersedia.
- Save flow Streamlit menangkap error dan mengingatkan bahwa penulisan multi-tab bukan transaksi atomik; sebagian tab bisa saja sudah berhasil ditulis.
- JSON terkompresi dibaca otomatis menjadi JSON biasa untuk fitur load/reload.

## File berubah

- `storage/gsheets_db.py`
- `app.py`
- `config.py`
- `tests/test_gsheets_payload_compression.py`
- `README.md`
- `CHANGELOG.md`
- `docs/USER_GUIDE.md`
- `docs/DEPLOYMENT_SMOKE_TEST.md`

## Pengujian

- `pytest -q`: 74 passed
- `python -m compileall -q .`: passed

## Kompatibilitas

Tidak ada perubahan nama tab atau header Google Sheets. Data lama yang belum dikompresi tetap dapat dibaca. Setelah V1.0.7 menyimpan record terkompresi, jangan rollback ke V1.0.6 tanpa migrasi/dekompresi terlebih dahulu, karena versi lama tidak mengenali marker kompresi.

## Setelah deploy

1. Ganti file sesuai struktur patch atau deploy seluruh V1.0.7.
2. Jangan menimpa Streamlit Secrets.
3. Reboot aplikasi.
4. Coba simpan satu objek dengan comparable, RAB dan risk register lengkap.
5. Jika masih gagal, kirim HTTP status dan pesan Google baru yang sekarang ditampilkan aplikasi. Pesan itu akan membedakan error ukuran sel dari permission, range, atau grid limit.
