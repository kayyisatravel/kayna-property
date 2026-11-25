# PFMS V1.0.19 — Patch Notes

## Memorandum Investasi Properti
- Judul dokumen menggunakan `Memorandum Investasi Properti` (Property Investment Memorandum).
- Timestamp analisis ditampilkan dalam zona waktu `Asia/Jakarta` (WIB).
- Tabel pembanding menampilkan alamat dan sumber; jarak tidak ditampilkan.
- Struktur modal, kebutuhan kas/cadangan risiko, biaya penjualan, penjualan bersih, profit, dan ROI ditampilkan untuk skenario limit, tengah, dan atas.
- Strategi penawaran mencantumkan ROI target dan ROI simulasi.
- RAB ringkas mencantumkan subtotal per item, total akhir, dan estimasi durasi tiap item menggunakan classifier produktivitas yang sama dengan jadwal renovasi.
- Konteks ekonomi regional statis dihilangkan. Tidak ada narasi makro jika provider dinamis yang tervalidasi dan segar belum tersedia.
- Lampiran menampilkan proyek aktif dan proyek selesai berdasarkan catatan yang tersedia.
- Tema visual navy berkontras tinggi, minimum font DOCX 11 pt.
- Branding: `KAYNA PROPERTY | PROPERTY INVESTMENT & PROJECT MANAGEMENT`.

## Akuntansi proyek
- Biaya pada kategori penjualan (termasuk pajak/komisi yang dipetakan ke kategori tersebut) dipisahkan dari modal proyek saat menghitung profit proyek selesai.

## Kompatibilitas dan batasan
- Tidak ada perubahan destruktif pada tab atau header Google Sheets.
- Portfolio context memakai tabel yang sudah ada dan cache baca Google Sheets 300 detik; tidak ditulis kembali ke snapshot atau database.
- Pembuatan memo memakai Python dan snapshot yang sudah ada; tidak memanggil Gemini.
- Foto properti tidak ditambahkan ke memo agar tidak menambah beban file/penyimpanan Google Sheets.
- Riwayat proyek hanya selengkap catatan milestone, biaya, budget, dan closing yang telah dimasukkan pengguna.
