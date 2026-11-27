# PFMS V1.0.24 — Release Guide

## Upgrade
1. Backup repository GitHub `kayna-property` dan spreadsheet database.
2. Extract `pfms-v1.0.24-upgrade-patch.zip` ke root repository V1.0.23, overwrite hanya file yang disertakan dalam patch.
3. Jangan menimpa atau menghapus `.streamlit/secrets.toml`. File secrets lokal tidak disertakan dalam paket.
4. Commit dan push ke GitHub; tunggu deployment Streamlit selesai.
5. Buka app dan uji checklist di bawah sebelum menggunakannya untuk keputusan lelang.

## Alur Analisis Objek Lelang
1. **Data Lelang & Legal**: upload pengumuman KPKNL, periksa hasil ekstraksi, koreksi tanggal lewat date picker jika perlu, lalu lengkapi data wajib. Tombol `LANJUT KE SURVEI` baru aktif jika field wajib tahap 1 lengkap.
2. **Survei & Risiko**: pilih status survei/penghuni, periksa biaya penguasaan dan risk register, kemudian konfirmasi review. `Belum Survei` tetap dapat dipilih, tetapi menjadi peringatan risiko dan dapat menahan keputusan GO.
3. **Pembanding**: masukkan setidaknya tiga pembanding unik yang memiliki nama, harga, luas tanah atau bangunan, dan sumber. Tiga pembanding memungkinkan estimasi indikatif; underwriting GO dapat meminta lima pembanding individual yang lebih kuat.
4. **Biaya & RAB**: tinjau item, volume, harga satuan, biaya lain, contingency dan holding. Seluruh item RAB yang masuk lingkup harus memiliki volume dan harga; konfirmasikan review biaya.
5. Tombol **Analisa / Update Data** hanya tersedia setelah syarat akhir terpenuhi. Data antar langkah dipertahankan sementara di sesi aplikasi; penyimpanan permanen ke Google Sheets terjadi setelah analisis dijalankan.

## Tanggal KPKNL dan informasi pelunasan
- Tanggal lelang dan batas setor jaminan diprefill dari ekstraksi dokumen dan tetap editable melalui date picker. Jika tanggal tidak terbaca, date picker tidak menyimpan tanggal tebakan; isi/koreksi secara manual dari pengumuman.
- Estimasi lima hari kerja dihitung setelah tanggal menang aktual. Sebelum menang, aplikasi hanya menunjukkan simulasi dari tanggal lelang yang dijadwalkan.
- Estimasi menghitung Senin–Jumat dan tidak mengelola tanggal merah/cuti bersama. Ini bukan tenggat resmi. Selalu ikuti tanggal eksplisit pada pengumuman atau konfirmasi KPKNL. Tidak diperlukan patch tahunan untuk tabel hari libur.

## Checklist smoke test
- Login dan buka setiap menu utama.
- Buka Analisis Objek Lelang: pastikan tidak ada `NameError` pada tanggal hak SHGB.
- Isi langkah 1, tekan Lanjut, lalu kembali; pastikan isian tidak hilang.
- Lanjut langkah 2, 3, dan 4; pastikan setiap tombol hanya membuka langkah berikutnya setelah mandatory fields terpenuhi.
- Pastikan tombol Analisa/Update Data tidak muncul sebelum langkah 4 dan sebelum validasi akhir terpenuhi.
- Jalankan satu analisis uji; periksa hasil tersimpan ke Google Sheets dan proposal memakai data/snapshot yang sama.
- Uji satu objek dengan tanggal menang aktual dan pastikan informasi lima hari kerja dihitung dari tanggal tersebut.

## Batasan pengujian
Pengujian otomatis lokal tidak menggantikan smoke test di Streamlit Cloud. Kredensial Gemini, Google Sheets, hak akses spreadsheet, dan interaksi browser pada deployment milik pengguna tidak dapat diuji dari lingkungan build ini.
