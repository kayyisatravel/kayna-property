# PFMS V1.0.14 — BoQ Paste Parser & Category Recognition Fix

## Masalah yang diperbaiki

- BoQ yang ditempel dari Excel/Google Sheets dalam format tab-separated tidak dikenali oleh parser yang sebelumnya hanya membaca tabel Markdown dengan `|`.
- Frasa klasifikasi `Kategori Kondisi: Renovasi Sedang` tidak dikenali sebagai pernyataan kategori utama sehingga sistem jatuh kembali ke pilihan dropdown fisik yang lebih ringan.
- Pengguna tidak memperoleh umpan balik sebelum memanggil Gemini apakah baris BoQ berhasil dibaca.

## Perubahan

1. `core/user_boq.py`
   - Mendukung Markdown pipe table, TSV hasil salin Excel/Google Sheets, dan plain rows setelah header BoQ yang jelas.
   - Mempertahankan semua 16 volume/satuan dalam BoQ pengguna tanpa scaling otomatis dari LT/LB.
   - Menghindari parser menganggap teks narasi biasa sebagai BoQ; tetap memerlukan header atau bentuk baris yang dikenali.
2. `core/renovation_engine.py`
   - Mengakui `Kategori Kondisi: Renovasi Sedang`, `Kategori Fisik`, `Kondisi Fisik`, dan variasi label kategori utama yang umum.
   - Pernyataan kategori utama dalam deskripsi mengalahkan dropdown kondisi umum ketika kategori RAB tetap Auto. Pilihan kategori manual tetap menjadi override.
3. `app.py`
   - Menggunakan `app.py` yang diunggah pengguna sebagai baseline, termasuk penyesuaian tampilan Dashboard: metric 4 kolom dan angka realisasi proyek aktif, serta warna nilai metric.
   - Menambahkan pratinjau BoQ sebelum panggilan Gemini.
- Mengganti namespace cache RAB agar hasil parse lama dari V1.0.13 tidak digunakan ulang setelah upgrade.
   - Pesan bantuan parser menjelaskan format Markdown dan TSV, bukan hanya Markdown.
4. `config.py`
   - Versi aplikasi menjadi 1.0.14.

## Batasan dan aturan data

- Volume dari BoQ adalah input pengguna; sistem tidak mengubahnya dari foto atau ukuran properti. Perbedaan luas LT/LB hanya menghasilkan peringatan verifikasi.
- Harga satuan tetap estimasi screening Gemini sampai diverifikasi terhadap price book/quotation lokal.
- Item interior/MEP atau scope yang tidak didukung bukti tetap Bersyarat sampai inspeksi dan konfirmasi pengguna.
- RAB yang belum seluruh item lingkupnya memiliki harga satuan tetap dinyatakan parsial; subtotal tidak boleh disebut total RAB final.

## Pengujian

- Tambahan pengujian parser TSV 16 item.
- Tambahan pengujian kategori `Kategori Kondisi: Renovasi Sedang` terhadap dropdown `Renovasi Ringan`.
- Tambahan integrasi parser → estimator untuk memastikan 16 item tetap terbawa meskipun respons Gemini tidak mengembalikan baris BoQ.
