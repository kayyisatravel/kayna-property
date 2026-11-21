# Panduan Integrasi Analisis Pra-lelang ke Proyek Aktif — V1.0.13

## 1. Objek yang sudah dianalisis dan kemudian dimenangkan

1. Simpan hasil analisis terlebih dahulu melalui tombol **SIMPAN / UPDATE ANALISIS KE DATABASE**. Ini penting agar snapshot `latest_analysis` tersedia.
2. Buka **Database & Riwayat** dan pilih objek berdasarkan nama, lot, alamat, atau Property ID.
3. Pada bagian perubahan status, pilih lifecycle **WON** (atau **ACTIVE** bila proyek sudah masuk tahap pengelolaan), masukkan harga menang aktual, tanggal menang, serta bagian uang jaminan yang menjadi bagian dari harga menang.
4. Simpan. PFMS mempertahankan `decision_status` pra-lelang apa adanya, termasuk HOLD. Kemenangan yang diputuskan owner tidak mengubah riwayat keputusan sistem menjadi GO.
5. Jika belum ada budget manual/onboarding untuk properti tersebut, PFMS membuat baseline dari snapshot underwriting dan menghitung ulang harga akuisisi, bea pembeli, BPHTB serta biaya terkait dengan memakai harga menang aktual.
6. Objek muncul di **Properti Aktif**. Baseline ditampilkan sebagai anggaran awal; actual paid, committed unpaid, forecast remaining dan risk reserve tetap dipisahkan.

## 2. Mengapa keputusan HOLD tetap disimpan?

HOLD adalah hasil analisis pada saat sebelum bidding. Lifecycle WON/ACTIVE adalah fakta perjalanan proyek setelah owner memutuskan ikut lelang dan berhasil menang. Keduanya tidak bertentangan dan tidak boleh ditimpa satu sama lain.

Blocker pra-lelang, misalnya confidence comparable, interior belum diperiksa, atau keterbatasan kas saat itu, tetap tersedia di riwayat. Blocker tersebut tidak menjadi larangan untuk mengelola aset yang sudah dimenangkan.

## 3. Cara membaca posisi kas

- `pre_bid_cash_available` adalah snapshot historis ketika underwriting dilakukan.
- Kas siap investasi saat ini berasal dari **Investor Cashflow → Real cash saat ini** dikurangi outflow terkonfirmasi, komitmen belum dibayar proyek aktif, dan cadangan likuiditas.
- PFMS tidak membaca rekening bank secara langsung. Setelah pembayaran harga lelang, BPHTB, legalitas, kerohiman, atau renovasi, pengguna harus memperbarui real cash dengan saldo aktual.
- Jangan memasukkan kewajiban yang sama sebagai `CASHFLOW_EVENTS` dan `PROJECT_BUDGETS` sekaligus.

## 4. Cara merekonsiliasi biaya historis

Untuk setiap pembayaran yang sudah terjadi:

1. Tambahkan sebagai **Actual Paid** di halaman Properti Aktif.
2. Pilih kategori, subkategori, item, tanggal, dan nominal.
3. Jika pembayaran itu memang melunasi suatu budget/forecast/commitment, tautkan ke item budget tersebut dan pilih sumber pembayaran yang sesuai. Ini mengurangi komitmen/forecast item terkait.
4. Jika pembayaran adalah pekerjaan tambahan di luar budget, catat sebagai pengeluaran di luar budget; jangan tautkan ke scope yang tidak sesuai.
5. Koreksi transaksi lama melalui menu koreksi transaksi, bukan menambahkan baris baru untuk mengimbangi typo. Perubahan dicatat di audit history.

Jika ada actual paid yang belum tertaut, PFMS memberi peringatan karena actual tersebut mungkin menghitung pengeluaran yang sama sementara seluruh forecast item masih tersisa. Rekonsiliasi agar proyeksi penyelesaian tidak overstate.

## 5. Baseline parsial atau budget manual yang sudah ada

- Jika baseline dari analisis memiliki RAB tanpa harga/volume, baris itu tetap dibuat dengan status pending pricing. Angka proyeksi diberi label sementara sampai item dilengkapi.
- Jika sudah ada budget manual/Project Onboarding, PFMS tidak menambahkan baseline analisis secara otomatis karena berisiko double-count. Bandingkan data manual dengan snapshot analisis dan lakukan rekonsiliasi manual.
- Harga menang digunakan untuk baseline baru; harga limit dan hasil simulasi pra-lelang tidak menggantikan harga perolehan aktual.
