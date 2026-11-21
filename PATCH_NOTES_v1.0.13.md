# PFMS V1.0.13 — User BoQ Pricing Reliability & Analysis-to-Active Integration

## Tujuan
Memperbaiki jalur RAB yang menggunakan BoQ rinci dari pengguna serta memastikan data hasil analisis pra-lelang menjadi baseline anggaran proyek aktif ketika objek dimenangkan, tanpa mengubah snapshot keputusan pra-lelang atau menghitung kas historis sebagai posisi kas saat ini.

## Perbaikan RAB / BoQ
- Parser Markdown mempertahankan seluruh baris, kelompok/subkelompok, volume, satuan, dan dasar asumsi yang diberikan pengguna. Volume tidak ditimpa atau diskalakan otomatis dari luas properti.
- Pemetaan hasil Gemini lebih toleran terhadap item_code yang tidak dikembalikan model: setelah pencocokan ID, sistem mencoba pencocokan nama pekerjaan yang dinormalisasi secara persis. Ini mengurangi kasus harga AI terlepas dari kuantitas BoQ yang benar.
- Jika Gemini menghilangkan baris BoQ, Python tetap menambahkan baris dengan quantity asli dan harga kosong. Baris tidak dihapus atau diberi harga fiktif.
- Skema RAB menerima tiga tingkat harga: `unit_cost_low`, `unit_cost_conservative` (dipakai sebagai harga satuan utama), dan `unit_cost_high`.
- Ditambahkan tombol opsional untuk satu panggilan Gemini tambahan yang hanya menaksir harga satuan BoQ yang masih kosong. Tombol tidak mengubah nama, kuantitas, satuan, atau prioritas; setiap harga tetap screening estimate dan tidak diklaim sebagai SSH/HSPK/quotation lokal.
- Item tersembunyi/interior yang volumenya didasarkan pada asumsi, seperti tambal plafon interior akibat rembesan tetapi interior belum diperiksa, default-nya Bersyarat dan tidak masuk RAB dasar. Jika hasil inspeksi aktual telah mengonfirmasi kerusakan, pengguna dapat mengubah prioritasnya.
- Dasar geometri yang berbeda dari data properti resmi tetap dipertahankan sebagai asumsi BoQ dan menghasilkan peringatan. Sistem tidak mengubah LT/LB fakta properti atau mengalikan volume diam-diam.
- Ringkasan RAB menampilkan jumlah baris BoQ, jumlah baris harga yang dikembalikan AI, serta daftar item yang masih belum terharga.

## Integrasi Analisis → WON/ACTIVE
- Ketika objek analisis dipindahkan ke WON/ACTIVE, snapshot underwriting, status keputusan pra-lelang (termasuk HOLD), comparable, blocker, dan kas pra-lelang dipertahankan sebagai arsip.
- Jika belum ada budget manual/Project Onboarding, sistem membuat baseline `PROJECT_BUDGETS` dari snapshot analisis dan menghitung ulang komponen akuisisi menggunakan harga menang aktual, bukan limit.
- Anggaran awal hasil analisis muncul pada Dashboard dan Properti Aktif; biaya penjualan tetap dipisahkan dari biaya proyek sampai siap jual.
- Kas pra-lelang, misalnya Rp154 juta pada contoh pengguna, hanya ditampilkan pada riwayat underwriting pra-lelang. Posisi kas saat ini berasal dari Investor Cashflow dan harus diperbarui manual karena tidak ada koneksi bank.
- Jika project sudah mempunyai budget manual/onboarding, sistem tidak menggabungkan baseline otomatis agar tidak menghitung biaya dua kali. Dibutuhkan rekonsiliasi manual.
- Transaksi historis yang belum ditautkan ke budget tetap terhitung sebagai actual paid, tetapi dapat membuat forecast tampak terlalu besar. Pengguna diarahkan menautkan pembayaran ke item budget yang sama bila memang membayar scope yang telah dianggarkan.

## Kompatibilitas
- Tidak ada tab Google Sheets yang dihapus atau diganti nama.
- Tidak ada kolom existing yang dihapus atau urutan kolom inti diubah.
- Tidak ada perubahan pada rumus profit/ROI atau batas bidding V1.0.12.
- Semua perubahan database bersifat additive dan memakai `PROJECT_BUDGETS`, `COST_ACTUALS`, `PROPERTIES`, serta snapshot yang sudah ada.
- Tidak ada OAuth/Google Drive archive baru. Streamlit Secrets tidak diubah.

## Keterbatasan yang harus dipahami
- Estimasi harga unit Gemini bukan harga pasar vendor terverifikasi dan bukan HSPK/SSH resmi. Untuk anggaran final, bandingkan minimal dua penawaran lokal dengan spesifikasi dan waktu yang sama.
- Foto tampak depan tidak membuktikan kondisi interior, rangka atap utama, MEP, sanitair, atau struktur. Pekerjaan tersembunyi tetap kondisional sampai inspeksi.
- BoQ contoh menyebut LT 72 m² dan LB total 65 m². Data proyek TAS 3 M6/12 yang pernah dicatat sebelumnya adalah LT 102 m² dan LB 90 m². PFMS akan menampilkan mismatch dan mempertahankan data properti tersimpan; pengguna harus mengonfirmasi data mana yang benar dan apakah kuantitas BoQ memang untuk area pekerjaan, bukan luas total bangunan.
- Gemini rate-only fallback adalah satu panggilan API tambahan yang hanya berjalan setelah pengguna menekan tombol; ini menggunakan kuota.

## Pengujian
- `python -m compileall -q .`: passed.
- `pytest -q`: 136 passed.
- Live Google Sheets, Streamlit Cloud, dan Gemini API dengan kredensial pengguna: belum dijalankan pada lingkungan ini.
