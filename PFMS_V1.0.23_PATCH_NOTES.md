# PFMS V1.0.23 — Patch Notes

## Perbaikan
1. Menghapus checkbox “Tanggal lelang sudah diketahui” dan “Batas setor uang jaminan sudah diketahui”. Kedua tanggal diisikan dari ekstraksi dokumen KPKNL ke date picker yang tetap dapat diedit. Jika ekstraksi tanggal kosong/ambigu, sistem tidak menyimpan tanggal contoh; pengguna dapat memilih tanggal secara manual.
2. Batas pelunasan dihitung otomatis dari tanggal lelang. Default lelang biasa adalah 5 hari kerja setelah tanggal lelang sesuai PMK 122 Tahun 2023 Pasal 88 ayat (1).
3. Kalender kerja mengecualikan akhir pekan, hari libur nasional, dan cuti bersama 2026–2027 berdasarkan SKB 3 Menteri yang berlaku.
4. Tanggal pelunasan eksplisit yang terbaca pada dokumen KPKNL lebih diutamakan daripada hasil perhitungan otomatis.
5. Ditangani pengecualian PMK: lelang terjadwal khusus (2 hari kerja), pembeli instansi tertentu dan limit minimal Rp500 miliar (14 hari kerja).
6. Memperbaiki NameError `bid_reference_status` di halaman Tangga Bidding.
7. Investment Proposal menampilkan tanggal lelang, batas setor, batas pelunasan, dasar aturan/perhitungan, dan nama file sumber KPKNL dari data yang sama dengan analisis.

## Kompatibilitas
- Upgrade dari V1.0.22.
- Tidak mengubah atau menghapus worksheet/header Google Sheets.
- Tidak memasukkan `.streamlit/secrets.toml` ke paket.
- Belum live-tested dengan kredensial Google Sheets/Gemini pengguna.
