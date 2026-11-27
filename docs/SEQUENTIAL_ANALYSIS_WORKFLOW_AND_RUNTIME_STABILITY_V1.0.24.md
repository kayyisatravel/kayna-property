# Sequential Analysis Workflow & Runtime Stability — V1.0.24

## Tujuan
Mengurangi kesalahan navigasi, kehilangan nilai form saat berpindah langkah, dan `NameError` akibat helper yang tidak tersedia pada jalur render.

## Desain alur

| Langkah | Isi | Syarat untuk lanjut |
|---|---|---|
| 1. Data Lelang & Legal | Dokumen KPKNL, jadwal, alamat, nilai limit/jaminan, luas, sertifikat | Identitas/kode lot, alamat, KPKNL, tanggal lelang, batas setor, sertifikat, limit, deposit, LT dan LB (kecuali tanah kosong) |
| 2. Survei & Risiko | Penghuni, kondisi fisik, akses, temuan, risk register | Status survei dipilih dan risk register ditinjau/dikonfirmasi |
| 3. Pembanding | Data listing/transaksi pembanding, segmen primary/secondary, sumber, spesifikasi | Minimal 3 pembanding unik dan traceable untuk estimasi indikatif |
| 4. Biaya & RAB | Renovasi, biaya akuisisi, legal, penguasaan, holding, contingency dan biaya lain | Review biaya dikonfirmasi dan seluruh item RAB dalam lingkup memiliki volume dan harga satuan |

Tombol `Analisa / Update Data` hanya muncul pada langkah 4 setelah semua syarat akhir terpenuhi. Tiga pembanding adalah ambang estimasi indikatif; standar underwriting GO dapat memerlukan lima pembanding individual dengan bukti lebih kuat.

## Persistensi sesi
`persist_analysis_step_state` menyimpan nilai `na_*` non-widget dalam session state sebelum langkah lama disembunyikan. Key sementara Streamlit (`_widget`, `_picker`) dan file uploader yang tetap mounted tidak disalin. `restore_analysis_step_state` mengembalikan nilai yang dibersihkan Streamlit tanpa menimpa nilai baru yang sudah ada.

Tombol navigasi tidak menulis data ke Google Sheets. Penyimpanan permanen terjadi saat analisis/update akhir berhasil dijalankan. Hal ini menghindari record setengah jadi akibat perpindahan langkah.

## Proteksi NameError
- Helper date picker dideklarasikan sebelum authentication gate (`st.stop`) dan sebelum page routing.
- Unit test memakai modul `symtable` untuk mencari global reference pada `app.py` yang tidak dideklarasikan atau diimpor.
- `compileall` dijalankan untuk seluruh file Python.

Static scan mengurangi risiko nama global yang hilang, tetapi tidak dapat menjamin tidak ada semua kemungkinan error runtime. Integrasi eksternal dan versi Streamlit tetap memerlukan smoke test setelah deployment.

## Informasi pelunasan
- Setelah tanggal menang aktual tersedia, aplikasi menghitung perkiraan lima hari Senin–Jumat setelah tanggal tersebut.
- Sebelum menang, tanggal lelang terjadwal hanya menjadi simulasi.
- Kalender hari libur tahunan tidak di-hardcode; tidak ada patch tahunan. Hari libur/cuti bersama dapat membuat estimasi weekday lebih cepat daripada tenggat resmi. Pengumuman/konfirmasi KPKNL adalah acuan final.
