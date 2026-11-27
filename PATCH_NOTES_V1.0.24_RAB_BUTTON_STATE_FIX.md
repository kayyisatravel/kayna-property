# PFMS V1.0.24 — RAB Button State Fix

## Tujuan
Memperbaiki error `streamlit.errors.StreamlitValueAssignmentNotAllowedError` yang muncul saat langkah **Biaya / RAB** dirender, khususnya pada tombol **Susun RAB awal dengan Gemini**.

## Diagnosis berbasis pemeriksaan source
Tombol aksi analisis menggunakan key berawalan `na_`, sama seperti input formulir yang disimpan saat berpindah langkah. State tombol yang ikut masuk ke payload pemulihan formulir berisiko dipulihkan sebagai nilai session state biasa. Streamlit tidak mengizinkan state tombol `st.button` diperlakukan seperti nilai input yang dapat di-restore.

Karena pesan error asli di Streamlit Cloud disamarkan, diagnosis ini didasarkan pada pola state dalam source dan lokasi traceback; belum diverifikasi melalui log server penuh.

## Perubahan
- Menambahkan daftar key tombol aksi pada alur Analisis Objek Lelang.
- Menghapus state tombol aksi dari `_na_persisted_form_state` setelah proses penyimpanan langkah.
- Membersihkan payload sebelum dan sesudah proses pemulihan state, termasuk untuk payload lama yang mungkin sudah menyimpan key tombol.
- Mempertahankan seluruh nilai input formulir, state foto survei, data pembanding, serta hasil RAB.

## Tidak diubah
- Tidak ada perubahan UI atau alur empat langkah.
- Tidak ada perubahan perhitungan underwriting, aturan keputusan, maupun prompt Gemini.
- Tidak ada perubahan skema Google Sheets.
- Tidak mengubah `.streamlit/secrets.toml` atau kredensial.

## Validasi lokal
- `python -m py_compile app.py` — lulus.
- AST parse dan pemeriksaan keberadaan sanitizer serta perbaikan foto survei sebelumnya — lulus.
- Integrasi langsung dengan Streamlit Cloud, Google Sheets, dan Gemini tidak dapat diuji dari lingkungan lokal ini.

## Penerapan
Ganti `app.py` di repository dengan file pada patch ini. Jangan mengganti file konfigurasi secrets. Setelah deploy, uji alur: Analisis objek → Pembanding → Evaluasi Gemini → Lanjut ke Biaya/RAB → kembali ke Pembanding → lanjut lagi ke Biaya/RAB.
