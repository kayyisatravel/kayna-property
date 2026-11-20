# PFMS V1.0.10 — Guided Project Finance Input & Auction-Win Conversion

## Perubahan utama
- Input actual paid dan project budget dipindahkan dari dataframe editor ke formulir bertahap: kategori, subkategori, item/lingkup, nominal, serta tanggal. Date picker digunakan untuk tanggal pembayaran dan jatuh tempo.
- Dataframe realisasi dan Budget vs Actual pada halaman Properti Aktif sekarang bersifat read-only. Perubahan budget dilakukan melalui formulir edit setelah memilih item.
- Project Onboarding dibuat lebih ringkas: pengguna mendaftarkan identitas dan posisi proyek terlebih dahulu, lalu memasukkan histori pembayaran dan budget pada halaman Properti Aktif menggunakan formulir yang sama.
- Database & History menampilkan nama properti, alamat, kode lot, dan Property ID pada pilihan objek.
- Transisi prospect yang menang lelang menjadi WON mencatat harga menang, tanggal, dan deposit tanpa mengganti snapshot analisis. Objek otomatis tampil pada Properti Aktif. Penyimpanan progres pengelolaan dapat memindahkan WON menjadi ACTIVE.

## Kompatibilitas dan perlindungan data
- Tidak ada perubahan nama tab Google Sheets maupun urutan kolom lama.
- `COST_ACTUALS` dan `PROJECT_BUDGETS` tetap menggunakan skema V1.0.9; pilihan kategori/subkategori/item disimpan pada field yang sudah ada dan payload/details JSON.
- Project Onboarding tidak menghapus atau menimpa snapshot analisis lama ketika menggabungkan prospect dengan kode lot yang sama.
- Tidak ada migrasi wajib atau penghapusan data.

## Pengujian
- `python -m compileall -q .`: passed.
- `pytest -q`: 96 passed.
- Belum live-tested menggunakan kredensial Google Sheets dan Streamlit Cloud pengguna.
