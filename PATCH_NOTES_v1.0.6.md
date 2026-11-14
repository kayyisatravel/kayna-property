# PFMS V1.0.6 — Patch notes

## Perubahan utama

1. **Form restore diperkuat** (`core/form_state.py`): memulihkan kamar tidur/mandi, tipe properti, jumlah lantai, luas tapak, lebar dan akses jalan, kondisi fisik umum, kategori/deskripsi RAB. Data dari `input_data` dan `latest_analysis` digabung; alias payload lama didukung. Field tidak tersedia dikosongkan agar nilai objek sebelumnya tidak bocor.
2. **Luas tapak lantai dasar opsional** (`app.py`): bila diisi, digunakan untuk kuantitas atap. Bila kosong, Python memakai LB agregat / jumlah lantai dan memberi label asumsi.
3. **RAB lebih kontekstual** (`core/renovation_engine.py`, `services/gemini_parser.py`): konteks mencakup LT/LB, tipe properti, jumlah lantai, kamar tidur/mandi, kondisi fisik, lebar dan jenis akses, deskripsi serta foto.
4. **Auto category lebih aman**: kondisi belum diketahui menghasilkan inspeksi/persiapan, bukan asumsi renovasi ringan. Kondisi/lingkup yang eksplisit menentukan kategori.
5. **Koefisien screening transparan**: lantai/plafon 1,0 × LB; atap 1,25–1,35 × tapak; dinding 2,5–3,0 × LB; titik listrik LB/6 hanya allowance full MEP; puing 0,30–0,50 m³ × LB; truk default 5 m³. Renovasi ringan menggunakan allowance lokal low-confidence hanya bila bukti mendukung.
6. **Hard gate RAB**: scope wajib yang dilewatkan AI muncul sebagai placeholder tanpa harga. Baris wajib tanpa volume/harga menghalangi GO. Pekerjaan struktur tetap menunggu engineer.
7. **RAB item exclusion**: prioritas `Tidak diperlukan setelah ditinjau` dikeluarkan dari total RAB.

## File yang ditambahkan/diubah

- `app.py`
- `config.py`
- `core/form_state.py`
- `core/renovation_engine.py`
- `services/gemini_parser.py`
- `tests/test_form_restore_and_renovation_engine.py`
- `tests/test_gsheets_sanitization_and_rab.py`
- `docs/CALCULATION_RULES.md`
- `docs/USER_GUIDE.md`
- `docs/DEPLOYMENT_SMOKE_TEST.md`
- `docs/RENOVATION_ESTIMATOR.md` (baru)
- `README.md`
- `CHANGELOG.md`

## Penerapan

Ekstrak patch ke root repository, izinkan file yang sama ditimpa, lalu commit/push. Jangan menimpa `.streamlit/secrets.toml` asli. Setelah deploy, ikuti bagian 8 `docs/DEPLOYMENT_SMOKE_TEST.md`.

## Validasi

- `python -m compileall -q .` — lulus
- `pytest -q` — 68 passed
- Integrasi live Gemini, Google Sheets dan Streamlit Cloud belum dapat diuji tanpa kredensial/akun deployment pengguna.
