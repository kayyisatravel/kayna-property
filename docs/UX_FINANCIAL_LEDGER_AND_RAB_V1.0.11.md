# PFMS V1.0.11 — UX, Financial Ledger Safety & Renovation Review

## 1. Dashboard portofolio aktif

Dashboard merangkum jumlah anggaran pada baris `PROJECT_BUDGETS` aktif untuk semua property dengan lifecycle WON/ACTIVE. Anggaran (budget) berbeda dari actual paid. Dashboard menampilkan total budget, aktual dibayar, komitmen belum dibayar dan forecast tersisa. Komitmen dan forecast tidak boleh dijumlahkan lagi sebagai actual paid.

## 2. Input aktual dan budget

- Dataframe adalah tampilan read-only.
- Input actual paid: kategori → subkategori → item/lingkup → tanggal → nominal → vendor → payment method → tautan budget opsional.
- Simpan membutuhkan checkbox konfirmasi dan nilai pembayaran lebih dari nol.
- Setelah berhasil, kontrol input transaksi dikosongkan untuk pencatatan berikutnya.
- Budget/edit budget berada di expander tertutup secara default; pengguna membuka hanya ketika akan membuat/mengubah data.
- Budget item baru membutuhkan setidaknya satu nominal positif di antara budget, commitment, atau forecast.

## 3. Koreksi transaksi pembayaran

Di Riwayat pembayaran proyek, pengguna memilih transaksi lalu membuka "Koreksi transaksi yang sudah tercatat". Koreksi mempertahankan `actual_id` yang sama dan menambahkan event `CORRECTED` ke `HISTORY` yang berisi nilai sebelum dan sesudah. Tidak ada tombol hapus transaksi.

Jika transaksi lama pernah mengurangi komitmen/forecast, engine membalik alokasi lama terlebih dahulu, lalu menerapkan alokasi baru. Engine menolak koreksi yang melebihi saldo komitmen/forecast yang tersedia. Ini mencegah saldo menjadi negatif atau biaya terhitung terpotong diam-diam.

## 4. Konfirmasi sebelum menyimpan

Konfirmasi digunakan pada update progress, tambah/koreksi pembayaran, tambah/edit budget, milestone, serta closing SOLD. Konfirmasi adalah pengaman kesalahan input; bukan pengganti bukti transfer, invoice, kuitansi atau validasi legal/teknis.

## 5. Tanggal

Tanggal lelang, batas setor jaminan, batas pelunasan, masa berlaku hak, tanggal survei, tanggal menang/perolehan, tanggal pembayaran, jatuh tempo, milestone, tanggal listing dan closing menggunakan date picker. Tanggal yang belum diketahui harus dibiarkan kosong melalui kontrol "sudah diketahui"; jangan mengisi tanggal perkiraan sebagai tanggal faktual.

## 6. Estimasi RAB berbasis deskripsi

Kategori renovasi adalah label kompleksitas, bukan instruksi untuk memasukkan seluruh scope kategori. Gemini memetakan kerusakan yang tampak ke pekerjaan spesifik; Python menjaga formula volume yang dapat dihitung; item tak terukur tetap kosong. Skenario interior yang tidak terlihat disajikan terpisah dari base RAB.

Foto fasad dapat mendukung temuan atap depan, dinding luar/teras, pagar, lantai carport dan area depan. Foto fasad tidak membuktikan kondisi bagian dalam rumah, struktur tersembunyi, instalasi listrik, pipa, septic tank atau kamar mandi. Untuk hal tersebut PFMS menyediakan inspection plan dan skenario sensitivitas interior ber-confidence rendah.

## 7. Batasan integrasi

Unit tests dan compile checks dilakukan secara lokal. Deploy belum dianggap terverifikasi sebelum pengguna memeriksa koneksi Google Sheets, hak tulis tab `COST_ACTUALS`/`PROJECT_BUDGETS`/`HISTORY`, rendering form, dan respons Gemini aktual di Streamlit Cloud.
