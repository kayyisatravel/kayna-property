# PFMS V1.0.11 — UX, Financial Ledger Safety & Condition-Driven Renovation RAB

## Perubahan utama

- Dashboard Utama kini menampilkan total anggaran aset berjalan selain aktual dibayar, komitmen belum dibayar dan forecast sisa. Setiap proyek aktif juga mempunyai rincian per properti.
- Riwayat biaya aktual dapat dikoreksi melalui form khusus. Koreksi mempertahankan `actual_id`, mencatat nilai sebelum/sesudah ke `HISTORY`, dan merekonsiliasi tautan pembayaran ke commitment/forecast.
- Penambahan/koreksi pembayaran, tambah/edit budget, update progres, milestone dan closing memerlukan konfirmasi pengguna.
- Tabel riwayat transaksi dan anggaran adalah tampilan; perubahan hanya melalui form yang disengaja. Form tambah/edit budget berada dalam expander tertutup secara default.
- Form pembayaran, penambahan budget dan milestone membersihkan field setelah berhasil disimpan.
- Semua field tanggal menggunakan date picker, termasuk tanggal terbit dan tanggal ditemukan pada comparable. Tanggal comparable lama diparse tanpa menukar urutan hari/bulan dan disimpan kembali dalam format ISO.
- Gemini RAB memisahkan temuan visual, dugaan penyebab, interior yang belum diketahui, rencana inspeksi dan skenario biaya interior dari RAB dasar.
- Renovation engine menggunakan deskripsi kerusakan untuk menambahkan scope lokal: atap depan/kanopi, pemeriksaan plafon terdampak, dinding lembap, rabat beton/carport, pengecatan pagar dan pembersihan area depan. Volume pekerjaan terukur tetap kosong hingga ada pengukuran aktual.
- Kategori Renovasi Sedang tidak lagi memaksa penggantian seluruh atap, plafon, lantai atau kamar mandi tanpa bukti.

## File berubah / ditambahkan

- `app.py`
- `config.py`
- `core/ledger_transactions.py` (baru)
- `core/renovation_engine.py`
- `services/gemini_parser.py`
- `docs/RENOVATION_ESTIMATOR.md`
- `docs/DEPLOYMENT_SMOKE_TEST.md`
- `docs/UX_FINANCIAL_LEDGER_AND_RAB_V1.0.11.md` (baru)
- `tests/test_condition_driven_renovation_guidance.py` (baru)
- `tests/test_ledger_transaction_reconciliation.py` (baru)
- `README.md`
- `CHANGELOG.md`

## Kompatibilitas dan catatan operasional

- Tidak ada tab Google Sheets, nama kolom/header, atau urutan kolom lama yang dihapus/diubah. Struktur yang digunakan tetap `COST_ACTUALS`, `PROJECT_BUDGETS`, `HISTORY`, dan tab eksisting lainnya.
- Tidak perlu mengubah Streamlit Secrets atau mengaktifkan OAuth/Google Drive.
- Google Sheets multi-tab bukan transaksi atomik. Bila proses simpan gagal di tengah jalan, periksa tab terkait sebelum mengulangi simpan.
- Skenario interior dari AI tidak otomatis dimasukkan ke RAB dasar atau budget proyek. Masukkan hanya setelah inspeksi/keputusan pengguna.
- Tanggal publikasi iklan dan tanggal ditemukan adalah dua field berbeda. Tanggal publikasi yang tidak diketahui boleh kosong; tanggal ditemukan mencatat kapan data dikumpulkan.

## Pengujian

- `python -m compileall -q .`: passed.
- `pytest -q`: 103 passed.
- Streamlit Cloud, Google Sheets live credentials dan Gemini API live belum diuji dari lingkungan ini. Jalankan `docs/DEPLOYMENT_SMOKE_TEST.md` setelah deploy.
