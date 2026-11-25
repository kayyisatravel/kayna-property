# PFMS V1.0.18 — Release Guide

Tanggal: 25 November 2026  
Basis upgrade: V1.0.17. Seluruh pricebook deterministik regional, subtotal RAB, serta parser tanggal eksplisit V1.0.17 dipertahankan.

## Ringkasan

V1.0.18 menambahkan hasil lelang sebagai data referensi, filter/sort lokal yang hemat kuota Google Sheets, estimasi durasi renovasi, reminder target penjualan, dan pemantauan budget. Penyesuaian tanggal lelang mengikuti masukan pengguna: dokumen KPKNL mengisi date picker secara otomatis, tetapi tanggal tetap bisa diedit.

## 1. Tanggal lelang dan batas setor

- Upload dan parse dokumen KPKNL akan mencoba mengisi tanggal pelaksanaan lelang dan batas setor uang jaminan.
- Field tetap date picker dan tidak dikunci. Setelah prefill, pengguna bisa mengganti tanggal.
- Tanggal pelunasan tetap merupakan field terpisah.
- Tanggal yang tidak ditemukan, formatnya ambigu, atau tidak memiliki dasar kutipan tidak ditebak; biarkan kosong dan isi manual setelah diperiksa.
- Parser menyimpan evidence kutipan dan hash dokumen sumber.

## 2. Konteks ekonomi regional di Investment Memo

Memo dapat memasukkan snapshot data resmi jika lokasi objek cocok dan tanggal publikasi masih dalam jendela kesegaran.

Snapshot versi `ID_EAST_JAVA_2026-11-25_V1` mencakup:
- BPS Kabupaten Sidoarjo: pertumbuhan ekonomi/PDRB riil 2025 sebesar 5,63%, rilis 6 Maret 2026.
- Bank Indonesia Jawa Timur: pertumbuhan ekonomi Triwulan II 2026 sebesar 5,72% yoy, publikasi 15 September 2026.
- Bank Indonesia: RPPI rumah primer Triwulan III 2026 +0,58% yoy serta penjualan rumah primer -8,43% yoy, rilis 6 November 2026.

Sumber yang dicantumkan pada memo:
- https://sidoarjokab.bps.go.id/id/pressrelease/2026/03/06/60/economic-growth-of-sidoarjo-regency-in-2025.html
- https://www.bi.go.id/id/publikasi/laporan/lpp/Pages/Laporan-Perekonomian-Provinsi-Jawa-Timur-Agustus-2026.aspx
- https://www.bi.go.id/en/publikasi/ruang-media/news-release/Pages/sp_2824426.aspx

PENTING: snapshot tersebut merupakan konteks makro resmi, bukan indeks transaksi rumah second di tingkat perumahan/desa. Tidak ada pengali otomatis untuk ARV, harga jual, atau holding period. Snapshot tidak melakukan web crawl real-time. Bila seluruh data tidak cocok atau telah kedaluwarsa, memo tidak memaksakan bagian analisis ekonomi.

## 3. Database harga menang lelang

Worksheet tambahan `AUCTION_OUTCOMES` menyimpan:
- status hasil: menang sendiri, pemenang lain dengan harga diketahui, tidak laku/tidak ada penawaran, dibatalkan, hasil belum diketahui;
- harga dan jenis harga (harga menang resmi, penawaran tertinggi, laporan pihak lain, estimasi);
- limit, tanggal lelang, identitas objek/lot, kualitas sumber, URL dan catatan;
- tidak mengumpulkan nama atau identitas pemenang.

Harga menang pihak lain dapat dipakai sebagai bukti transaksi lelang, tetapi jangan dicampur begitu saja dengan harga listing pasar sekunder. Filter hasil lelang berdasarkan status, urutan tanggal, dan nilai.

## 4. Explorer properti dan kuota Sheets

- Explorer menggunakan hasil baca Google Sheets yang dicache selama 300 detik.
- Filter teks, status, keputusan, nilai limit, dan sorting dijalankan di memori setelah pembacaan.
- Perubahan urutan/penyaringan tidak memanggil Google Sheets lagi.
- Penulisan data menghapus cache agar pembacaan berikutnya memperbarui hasil.
- Tombol refresh manual dapat meminta pembacaan baru dan menggunakan kuota API; gunakan ketika diperlukan saja.

## 5. Investment Memo

- Header: `KAYNA PROPERTY | PELAKSANA PROYEK`.
- Seluruh teks di dokumen DOCX, termasuk tabel, header, dan footer, memiliki ukuran minimal 11 pt.
- Nama file memuat nama properti, kode lot, dan property ID yang disanitasi.
- Memo memuat ringkasan, identitas dan jadwal lelang, pasar, pembanding, modal/profit, strategi bid, ekonomi regional jika ada, risiko, RAB, durasi renovasi, tata kelola dan penafian.
- Memo dibangun dari snapshot tersimpan dengan Python. Tidak ada panggilan Gemini tambahan untuk membuat dokumen.

## 6. Estimasi waktu renovasi

- Durasi dihitung deterministik dari volume BoQ, satuan dan produktivitas screening per kelompok pekerjaan.
- Menyediakan skenario cepat, dasar dan konservatif, serta fase pekerjaan.
- Asumsi standar: 6 hari kerja per minggu dan buffer waktu default 20%.
- Dipakai di halaman proyek aktif dan Investment Memo.
- Ini adalah estimasi jadwal awal, bukan janji kontraktor. Tidak memasukkan otomatis waktu tunggu material, cuaca, perizinan, approval, perubahan lingkup, atau keterlambatan vendor. Item yang tidak terpetakan ditandai.

## 7. Budget dan reminder

Formula:

`Sisa budget / (overrun) = Budget proyek sampai siap jual - Proyeksi biaya akhir`

- Positif berarti budget masih tersisa.
- Nol berarti proyeksi sama dengan budget.
- Negatif berarti proyeksi melewati budget.

Contoh: Rp253.856.000 - Rp246.643.344 = **+Rp7.212.656**.

Ambang alert awal:
- 70% proyeksi penggunaan budget: informasi/pantau.
- 85%: warning/mendekati batas.
- 100% atau lebih: critical/over budget.

Target penjualan harus dikonfirmasi dan disimpan oleh pengguna. Reminder akan muncul di halaman proyek aktif saat target mendekat (14 hari) atau terlewati. CTA menyarankan tinjau harga, listing, foto, dokumen dan follow-up. Alert anggaran menyarankan rekonsiliasi transaksi, tinjau forecast/komitmen, dan persetujuan perubahan budget.

Reminder bersifat in-app saat aplikasi dibuka; tidak mengirim email, push notification, atau melakukan pemeriksaan background otomatis.

## 8. Upgrade aman

1. Backup repository dan spreadsheet.
2. Extract patch V1.0.18 ke root source sebelumnya, atau gunakan full source jika memang instalasi bersih.
3. Jangan pernah menimpa `.streamlit/secrets.toml`.
4. Worksheet `AUCTION_OUTCOMES` bersifat additive. Jika belum ada, adapter DB mencoba membuat tab dan header melalui fungsi inisialisasi schema. Data historis lama tidak dihapus.
5. Commit/push ke GitHub dan tunggu deployment Streamlit Cloud selesai.
6. Uji satu file KPKNL, satu proyek aktif, satu hasil lelang pembanding, serta satu memo sebelum digunakan untuk keputusan baru.

## 9. Batas pengujian

Unit test, compile check, dan pengujian paket lokal bukan live test. Kredensial Gemini/Google Sheets dan deployment Streamlit Cloud milik pengguna belum diuji pada lingkungan ini.
