# User BoQ dan RAB AI-assisted — PFMS V1.0.13

## 1. Format input yang didukung

Tempelkan tabel Markdown dengan kolom yang setara dengan:
- Kelompok pekerjaan
- Item pekerjaan
- Estimasi volume
- Satuan
- Dasar asumsi perhitungan dimensi

Sistem mempertahankan nama pekerjaan, kelompok, kuantitas dan satuan yang disediakan pengguna. Setiap baris menjadi satu item `USER_BOQ_nnn`.

## 2. Urutan bukti volume

1. Volume BoQ hasil ukur/konfirmasi pengguna.
2. Katalog kuantitas Python yang dihitung dari data properti dan koefisien screening.
3. Untuk pekerjaan custom yang tidak mempunyai dasar kuantitas, volume tetap kosong sampai diukur.

AI tidak mengukur skala dari foto dan tidak mengubah kuantitas BoQ pengguna.

## 3. Klasifikasi pekerjaan

- Wajib: terkait kerusakan yang terlihat atau sudah dikonfirmasi.
- Disarankan: pekerjaan yang layak dipertimbangkan untuk pemulihan fungsi/area.
- Bersyarat: pekerjaan yang bergantung pada kondisi tersembunyi, asumsi, upgrade atau konfirmasi pengguna; tidak masuk RAB dasar sampai diputuskan.
- Opsional: pekerjaan tambahan yang dapat dipilih pengguna.
- Tidak diperlukan setelah ditinjau: dikeluarkan dari total setelah pengguna benar-benar menolaknya.

Pekerjaan interior/MEP dari foto fasad saja, seperti plafon interior akibat rembesan, cat interior, kamar mandi, listrik dan pipa, tetap Bersyarat sampai ada inspeksi. Apabila hasil inspeksi memastikan kerusakan, pengguna dapat mengubah prioritas.

## 4. Harga satuan AI

- Gemini dapat memberi `unit_cost_low`, `unit_cost_conservative`, dan `unit_cost_high`.
- Python memakai `unit_cost_conservative` × volume untuk subtotal.
- Jika AI tidak mengembalikan harga untuk semua baris, semua baris tetap ditampilkan dengan volume pengguna dan harga kosong.
- Gunakan tombol **Lengkapi harga satuan yang kosong dengan Gemini** untuk satu panggilan tambahan khusus harga. Panggilan ini menggunakan kuota Gemini.
- Estimasi AI adalah screening estimate, bukan penawaran kontraktor atau harga resmi Sidoarjo. Periksa spesifikasi, bahan, tenaga, alat, transport/mobilisasi, pembongkaran, pembuangan, akses dan metode kerja. Dapatkan penawaran lokal yang sebanding untuk budget final.

## 5. Membaca total RAB

- Subtotal terhitung hanya mencakup baris dalam lingkup yang mempunyai volume dan harga konservatif.
- Baris Bersyarat tidak masuk total dasar sampai diputuskan.
- Bila ada baris dasar yang belum mempunyai volume/harga, total lengkap ditampilkan sebagai belum dapat ditentukan.
- Jangan menggunakan subtotal parsial sebagai total renovasi atau basis final ROI/bidding.
- Contingency dihitung terpisah sesuai aturan yang dikonfigurasi.
- Skenario interior yang belum diperiksa tetap dipisahkan dari RAB dasar.

## 6. Peringatan dimensi

Jika deskripsi BoQ menyebut LT/LB berbeda dari data properti yang tersimpan lebih dari toleransi, PFMS memberi peringatan. Data properti tidak ditimpa dan volume BoQ tidak diskalakan otomatis. Pastikan mana yang merupakan data dokumen properti dan mana yang hanya asumsi untuk pekerjaan tertentu.
