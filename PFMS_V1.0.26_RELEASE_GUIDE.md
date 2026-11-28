# PFMS V1.0.26 — Release Guide & Deployment Smoke Test

## Target
Rilis gabungan V1.0.25.3 + V1.0.26. Terapkan satu kali, langsung dari repository V1.0.25.2.1. Jangan memasang patch V1.0.25.3 terpisah.

## Cara Deploy
1. Backup repository GitHub dan data Google Sheets.
2. Unduh `pfms-v1.0.26-combined-upgrade-patch.zip`.
3. Ekstrak ke root repository dan pertahankan struktur folder.
4. Jangan mengganti `.streamlit/secrets.toml`. ZIP hanya berisi `.streamlit/secrets.toml.example`.
5. Commit ke GitHub dan tunggu deployment Streamlit Cloud selesai.
6. Periksa sidebar menampilkan Version 1.0.26.

## Smoke Test A — Investment Memo & AI
1. Buka objek analisis yang memiliki 3+ comparable.
2. Jalankan ulang Feasibility Study.
3. Periksa tabel daftar pembanding: ada harga/m² bangunan dan tanah.
4. Klik Perbarui AI Feasibility Brief. Pastikan Gemini membahas konteks proyek aktif/komitmen portofolio jika ada.
5. Cocokkan narasi skenario Cepat, Moderat, dan Tekanan terhadap tabel Python.
6. Pastikan Bab 10 tidak ganda; Bab AI adalah 12 dan Portofolio 13.
7. Unduh DOCX, PDF, dan Markdown; pastikan ketiganya berisi nama objek dan skenario yang sama.
8. Pada Risk Register, periksa bahwa cadangan tambahan tidak menduplikasi item contingency RAB/hidden reserve.

## Smoke Test B — Financial Stress Test & BEP
1. Pastikan harga bid/limit dan satu nilai exit telah tersedia.
2. Periksa Break-even exit price tampil.
3. Salin nilai BEP dan gunakan kalkulator proyek; net profit di BEP harus mendekati Rp0.
4. Exit price ROI minimum dan ROI GO harus menghasilkan ROI setidaknya sebesar ambang yang ditampilkan (perbedaan pembulatan kecil diperbolehkan).
5. Periksa empat skenario: Dasar, Moderat Buruk, Tekanan, Ekstrem.
6. Ubah holding, diskon harga, dan overrun renovasi lalu jalankan analisis ulang; hasil stress harus ikut berubah.
7. Periksa maximum holding tolerance. Jika tampil `>=120 bulan`, berarti batas pencarian tercapai dan hasil bukan nilai tak terbatas.
8. Pastikan cadangan kas belum terpakai tidak dikurangkan lagi sebagai biaya aktual proyek.

## Smoke Test C — Data & Penyimpanan
1. Uji kembali Risk Register, Comparable, RAB, foto survei dan perpindahan antar-step.
2. Simpan analisis, muat ulang objek, dan pastikan data lama tetap terbaca.
3. Periksa Google Sheets: tidak ada header/tab yang berubah pada rilis ini.

## Catatan
Validasi lokal mencakup 298 automated tests, kompilasi, pembuatan/render DOCX dan PDF, serta integritas ZIP. Live integration dengan Google Sheets/Gemini/Streamlit Cloud belum dilakukan oleh pembuat patch. Jika muncul traceback baru, kirim traceback lengkap, nama tab/aksi, dan versi sidebar.

## File distribusi
- Upgrade patch: `pfms-v1.0.26-combined-upgrade-patch.zip`
- Full source: `property-flipper-management-system-v1.0.26.zip`
- Standalone app entry point: `pfms-v1.0.26-app.py` (untuk inspeksi; deployment tetap membutuhkan seluruh modul).
