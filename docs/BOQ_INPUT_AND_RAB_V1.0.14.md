# Panduan BoQ dan RAB — PFMS V1.0.14

## 1. Format input yang didukung

Deskripsi kondisi dan BoQ dapat ditempel di kolom **Deskripsi kondisi aktual dan pekerjaan yang terlihat/diperlukan**.

PFMS menerima:

- Tabel Markdown dengan kolom `Item Pekerjaan`, `Estimasi Volume`, dan `Satuan`.
- Tabel yang disalin langsung dari Excel/Google Sheets (kolom dipisahkan tab).
- Baris teks setelah header BoQ yang jelas, dengan volume dan satuan di akhir baris.

Contoh TSV:

```text
Item Pekerjaan\tEstimasi Volume\tSatuan
Pembongkaran atap kanopi depan\t18\tm²
Pemasangan flashing sambungan atap\t12\tm'
Pembersihan area depan\t1\tLs
```

Sebelum menekan tombol Gemini, periksa notifikasi **BoQ terdeteksi sebelum analisis** dan buka pratinjau untuk memastikan jumlah, nama, volume, dan satuan sesuai.

## 2. Kategori renovasi

Jika kolom kategori RAB dipilih **Auto sesuai kondisi umum**, sistem memprioritaskan pernyataan kategori utama dalam deskripsi, termasuk:

- `Kategori Kondisi: Renovasi Sedang`
- `Kategori Fisik: Renovasi Sedang`
- `Kondisi Bangunan: Renovasi Sedang`
- `Masuk dalam kategori Renovasi Sedang`

Pilihan kategori manual tetap mengesampingkan narasi. Jika ingin sistem mengikuti deskripsi, pilih Auto.

## 3. Kuantitas dan geometri

- Kuantitas eksplisit dari BoQ adalah input pengguna dan dipertahankan.
- Foto tidak digunakan untuk mengukur luas atau volume.
- LT/LB yang berbeda dari asumsi BoQ menghasilkan peringatan, bukan scaling otomatis.
- Periksa ulang volume, satuan, dan dasar pengukuran di lapangan sebelum menjadikannya kontrak pekerjaan.

## 4. Harga satuan

Gemini mengusulkan harga satuan rendah, konservatif, dan tinggi sebagai estimasi screening. Angka tersebut bukan quotation vendor dan bukan HSPK/SSH lokal terverifikasi.

Jika pemanggilan pertama belum mengisi seluruh harga satuan, PFMS menampilkan item yang belum terharga dan tombol untuk meminta estimasi harga satuan tambahan. Ini memakai satu pemanggilan Gemini terpisah. Tinjau dasar harga dan confidence sebelum menerima.

## 5. Status lingkup dan total RAB

Pekerjaan yang terlihat dan perlu untuk memperbaiki kerusakan dapat masuk Wajib. Pekerjaan kosmetik, interior yang tidak terlihat, struktur tersembunyi, atau instalasi yang belum diperiksa tetap Bersyarat sampai dikonfirmasi.

Item Bersyarat tidak masuk RAB dasar. Total RAB dinyatakan lengkap hanya jika semua item yang telah disetujui ke dalam lingkup memiliki volume dan harga satuan. Jika belum, angka yang ditampilkan adalah subtotal sementara, bukan total biaya renovasi.
