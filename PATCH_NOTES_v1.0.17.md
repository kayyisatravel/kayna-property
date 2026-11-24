# PFMS V1.0.17 — Patch Notes

## Ringkasan
V1.0.17 menstabilkan harga renovasi, memperjelas RAB per baris dan per kelompok, mengambil tanggal lelang dari dokumen KPKNL yang diunggah, dan meningkatkan Investment Memo Word/Markdown. Tidak ada migrasi destruktif Google Sheets.

## Perubahan utama

1. **Pricebook deterministik regional**
   - Gemini tidak lagi mengirim harga satuan ke kalkulasi proyek.
   - Python menggunakan `PFMS_SIDOARJO_SCREENING_2026_11_V2` untuk scope yang dikenal.
   - Item yang belum tercakup pricebook tidak diberi angka AI; pengguna memasukkan quotation atau override manual.
   - Harga override manual dikunci dan tidak ditimpa saat analisis ulang.
   - UI menampilkan contoh jangkar SSH Sidoarjo TA 2026 dan referensi Perbup 27/2025, Perbup 75/2025, Permen PUPR 8/2023. Harga komposit PFMS tetap bukan tarif resmi SSH/HSPK.

2. **RAB lebih transparan**
   - Menampilkan harga satuan dan subtotal tiap baris untuk skenario rendah/dasar/atas.
   - Menampilkan subtotal per kelompok pekerjaan.
   - Grup tanpa rate low/base/high ditampilkan kosong/belum tersedia, bukan Rp0.

3. **Tanggal lelang otomatis dari dokumen**
   - Tanggal pelaksanaan lelang dan batas setor jaminan diekstrak secara terpisah.
   - Bukti kutipan dan nama file sumber disimpan/ditampilkan.
   - Tanggal relatif tidak dihitung sendiri. Bila ambigu/tidak terbaca, field dikosongkan.
   - Dokumen cache dengan skema lama akan diparse ulang satu kali.
   - Fitur membaca dokumen yang diunggah, bukan live scraping/API KPKNL.

4. **Investment Memo investor**
   - Word dan Markdown memuat ringkasan, jadwal/evidence lelang, profil aset, kondisi, legalitas, comparables, RAB dan subtotal, modal, skenario profit/ROI, strategi bid, risk register, pendanaan, due diligence dan batasan.
   - Nama file memuat nama properti dan lot code.
   - Dibuat secara lokal dengan Python dari snapshot analisis, tanpa Gemini API call tambahan.

5. **UX dan compatibility**
   - Kustomisasi dashboard pengguna tetap dipertahankan.
   - Seluruh layout metrik maksimal empat kolom.
   - Google Sheets existing tabs/headers tidak dihapus atau diganti; PAYLOAD_CHUNKS dari versi sebelumnya tetap digunakan.
   - `.streamlit/secrets.toml` tidak disertakan dalam paket.

## Pengujian
- `python -m compileall -q .` berhasil.
- `pytest -q`: 169 tes lulus.
- DOCX Investment Memo dibuat dari fixture pengujian dan dirender menjadi 3 halaman untuk inspeksi visual; tidak ditemukan clipping atau overlap.
- Live Streamlit Cloud, Gemini API, dan Google Sheets credentials pengguna belum diuji.
