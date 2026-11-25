# PFMS V1.0.21 — Release & Upgrade Guide

## Paket
- **Upgrade patch**: untuk repository V1.0.20 yang sudah berjalan.
- **Full source**: instalasi baru atau pemeriksaan seluruh source.

## Upgrade V1.0.20 ke V1.0.21
1. Backup repository GitHub dan spreadsheet database.
2. Unduh `pfms-v1.0.21-upgrade-patch.zip`.
3. Ekstrak patch ke root repository V1.0.20 dan izinkan file yang termasuk patch untuk ditimpa.
4. Jangan mengganti atau menghapus `.streamlit/secrets.toml`.
5. Commit dan push ke GitHub agar Streamlit Cloud melakukan deployment.
6. Buka Ringkasan Utama dan tekan **Refresh Data** jika masih melihat cache lama.
7. Buat proposal baru dan bandingkan tiga tabel keuangan dengan skenario pada halaman analisis.

## Uji dashboard
- Periksa agenda lelang dan batas setor dari tanggal yang tersimpan.
- Cocokkan kas siap investasi dan profit terealisasi dengan sumber.
- Periksa aktual, komitmen, forecast, budget, dan peringatan proyek aktif.
- Pastikan progres fisik berasal dari status kerja yang diperbarui; tanpa data, sistem menampilkan belum tersedia, bukan mengasumsikan selesai.

## Catatan kompatibilitas
Dashboard menggunakan tabel Google Sheets yang telah ada melalui cache aplikasi (300 detik pada konfigurasi standar). Tidak ada panggilan Gemini tambahan, worksheet baru, atau migrasi header destruktif. Tes lokal tidak menggantikan live test dengan kredensial Google Sheets/Gemini dan deployment Streamlit Cloud Anda.
