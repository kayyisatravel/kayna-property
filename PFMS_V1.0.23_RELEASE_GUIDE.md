# PFMS V1.0.23 — Release Guide

## Upgrade
1. Backup repository dan data Google Sheets.
2. Ekstrak patch ke root repository V1.0.22.
3. Jangan menimpa `.streamlit/secrets.toml`.
4. Commit dan push ke GitHub, lalu tunggu deployment Streamlit Cloud selesai.
5. Uji satu dokumen pengumuman KPKNL dan periksa tanggal lelang, tanggal batas setor, serta tanggal pelunasan.

## Alur tanggal
- Upload dokumen KPKNL dan klik Parse.
- Tanggal lelang dan tanggal batas setor otomatis mengisi date picker; pengguna dapat mengoreksinya. Tidak ada checkbox tambahan.
- Batas pelunasan dihitung otomatis: 5 hari kerja setelah lelang biasa, dengan kalender hari libur nasional/cuti bersama 2026–2027.
- Jika pengumuman KPKNL memuat batas pelunasan eksplisit, tanggal tersebut dipakai dan ditandai sebagai sumber dokumen.
- Jika tanggal lelang tidak terbaca, batas pelunasan tidak dihitung dan ditampilkan sebagai belum dapat dihitung.
- Kalender hari libur/cuti bersama resmi yang tertanam mencakup 2026–2027. Untuk tahun di luar cakupan, sistem menandai hasil sebagai provisional (hanya mengecualikan akhir pekan) dan meminta verifikasi jadwal kerja KPKNL.

## Dasar regulasi
PMK 122 Tahun 2023 Pasal 88: pelunasan harga lelang dan bea lelang paling lambat 5 hari kerja setelah pelaksanaan lelang. Pengecualian: lelang terjadwal khusus 2 hari kerja; pembeli instansi/lembaga tertentu dan limit minimal Rp500 miliar 14 hari kerja. Untuk dokumen yang memuat tenggat eksplisit, periksa dan ikuti ketentuan dokumen KPKNL.

## Smoke test
- Pastikan halaman Tangga Bidding tidak lagi menampilkan NameError.
- Pastikan date picker tanggal lelang dan batas setor tidak memiliki checkbox konfirmasi.
- Pastikan tanggal otomatis dapat diedit.
- Pastikan perubahan tanggal lelang memperbarui batas pelunasan otomatis.
- Buat Investment Proposal baru dan bandingkan tanggal serta dasar perhitungan dengan halaman analisis.
