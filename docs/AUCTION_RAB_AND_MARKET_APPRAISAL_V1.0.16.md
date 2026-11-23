# PFMS V1.0.16 — SOP RAB Rumah Lelang dan Estimasi Pasar Indikatif

## 1. Tujuan sistem

PFMS adalah alat bantu underwriting investor/flipper, bukan sistem quantity surveyor kontraktor, arsitek, atau appraisal resmi. Keluaran harus memberi gambaran modal dan rentang nilai pasar yang berguna meskipun akses inspeksi dan data listing terbatas. Sistem wajib membedakan:

- fakta dari input pengguna;
- hasil parsing/observasi AI;
- allowance hasil koefisien atau katalog screening Python;
- asumsi/risiko yang belum bisa diverifikasi; dan
- angka aktual yang hanya boleh berasal dari realisasi atau bukti transaksi.

Jangan mengubah estimasi menjadi klaim aktual. Jangan pula meniadakan biaya hanya karena bagian bangunan belum bisa diperiksa.

## 2. SOP BoQ: pengguna adalah sumber lingkup utama

1. Baris `USER_BOQ_*` dan kuantitasnya dipertahankan sebagai dasar anggaran. Python tidak boleh menghapus, mengganti, atau menggandakan baris itu.
2. Baris generik dari AI/katalog Python dibandingkan berdasarkan *lingkup pekerjaan*, bukan hanya kata umum seperti "pembersihan" atau "cat".
3. Pekerjaan dinding interior, dinding fasad, plafon, listrik, servis engsel/kunci/kusen, pembersihan lantai/nat, dan sanitair yang sudah tercantum dalam BoQ akan menyingkirkan allowance generik yang mengulang lingkup sama.
4. Waterproofing, pembongkaran/penggantian, perbaikan plester, inspeksi, dan pekerjaan teknis lain tetap terpisah bila lingkupnya memang berbeda dari cat atau servis ringan.
5. Pembersihan puing/barang bekas tidak sama dengan proteksi lantai/kusen dan penyiapan area kerja. Bila BoQ hanya mencakup pembersihan, PFMS menyisakan allowance proteksi dengan nama/lingkup yang dipersempit. Bila BoQ secara eksplisit sudah mencakup proteksi area kerja juga, baris persiapan generik disingkirkan.
6. Setiap baris hasil deduplikasi yang disingkirkan dicatat pada hasil analisis dengan kode dan alasan. User BoQ tidak pernah menjadi baris yang disingkirkan.
7. Untuk pekerjaan yang tidak terlihat (plafon, atap tersembunyi, listrik, plumbing, sanitair), estimasikan allowance rendah/dasar/tinggi berdasar profil bangunan dan BoQ yang diberikan. Label keyakinan harus rendah/menengah bila belum diinspeksi; bukan berarti pekerjaan tersebut terbukti rusak.
8. Harga katalog screening bukan quotation. Verifikasi dengan setidaknya dua penawaran lokal atau data realisasi yang telah dikumpulkan. Jangan mengarang harga untuk item yang tidak punya unit/kuantitas yang kompatibel.

## 3. Penyimpanan payload Google Sheets

Google Sheets membatasi ukuran satu sel. PFMS V1.0.16 melakukan kompresi JSON; bila hasil tetap lebih besar dari batas aman satu sel, konten dikirim ke tab tambahan `PAYLOAD_CHUNKS` dalam potongan 40.000 karakter. Sel pada tab asal menyimpan pointer, bukan menghilangkan snapshot.

Ketika dibaca, aplikasi menggabungkan chunk, memeriksa jumlah dan urutan, lalu memvalidasi checksum. Jika ada chunk hilang/rusak, pembacaan akan gagal dengan pesan eksplisit agar snapshot tidak dianggap kosong. Retry menambahkan hanya chunk yang hilang bila penulisan sebelumnya terputus. Tab dan header lama tidak dihapus atau diganti. Setelah deployment, pastikan akun Google Sheets memiliki izin membuat tab tambahan atau gunakan tab `PAYLOAD_CHUNKS` yang sudah dibuat oleh admin.

## 4. SOP comparable pasar

### 4.1 Syarat minimal estimasi indikatif

Setiap pembanding setidaknya memiliki nama/identitas listing, harga positif, LT atau LB, serta platform/URL/kutipan sumber. Kondisi, sertifikat, akses, tanggal publikasi, dan URL detail meningkatkan kualitas, tetapi kekosongan salah satu kolom itu tidak otomatis menghapus listing dari kalkulasi indikatif.

- 3 atau lebih pembanding tunai yang lolos validasi minimum: tampilkan rentang estimasi indikatif.
- 1–2 pembanding: tampilkan estimasi awal dengan sampel terbatas dan haircut ketidakpastian lebih besar.
- 0 pembanding layak: belum dapat dihitung.
- Status indikatif terpisah dari status kelayakan final GO/READY.

### 4.2 URL dan kualitas bukti

URL homepage seperti `brighton.co.id`, `pinhome.id`, `lamudi.co.id`, atau `rumah123.com` dapat dicatat sebagai asal portal untuk screening indikatif. Homepage tidak membuktikan iklan individual dan tidak boleh disulap menjadi URL listing. Untuk status final READY/GO, PFMS meminta sekurangnya lima URL detail individual yang sudah dibuka dan dicocokkan secara manual oleh pengguna, serta tanggal ditemukan. Konfirmasi URL terikat pada nama, alamat, harga, LT, LB, dan URL; mengubah salah satu fakta membatalkan konfirmasi lama.

PFMS tidak otomatis menelusuri/crawling halaman web dan tidak menyatakan sebuah iklan telah diverifikasi hanya karena teks mengandung tautan. Pengguna tetap perlu memeriksa apakah halaman individual cocok dengan harga, alamat, luas, dan foto yang dimasukkan.

### 4.3 Jarak dan lintas administrasi

Jarak garis lurus Haversine dipakai bila koordinat target dan pembanding tersedia. Jika tidak, pengguna dapat mengisi jarak garis lurus manual dalam meter. Jarak 500 m lintas desa/kecamatan tetap relevan; nama administrasi bukan batas keras. Jangan mengklaim jarak jika koordinat atau pengukuran manual tidak tersedia. Jarak garis lurus bukan jarak tempuh jalan.

### 4.4 Segmen pasar dan jenis harga

- `Secondary / resale`: rumah second/resale; faktor bobot 1,00.
- `Primary / developer`: stok baru/developer; faktor bobot 0,75 untuk target rumah resale.
- `Tidak diketahui`: faktor bobot 0,90 sampai segmen diperiksa.
- `Over kredit / skema kewajiban`: dipisah dari pembanding cash-market. Jangan menyamakan uang DP atau estimasi total skema cicilan dengan harga jual tunai tanpa pokok pinjaman tersisa, tenor/sisa cicilan, tunggakan, biaya take-over, dan kewajiban yang dialihkan.

Faktor bobot ini adalah kebijakan screening awal yang dapat dikalibrasi dari data lokal proyek-proyek selesai. Bukan adjustment appraisal yang berlaku universal.

### 4.5 Normalisasi dan pelaporan

PFMS menormalisasi indikasi harga dengan luas tanah/bangunan, lalu memberi bobot kualitas data, kedekatan, kesesuaian properti dan segmen pasar. Weighted median dipakai agar harga ekstrem tidak mendominasi. Nilai rendah/dasar/atas adalah rentang screening berbasis data yang dimasukkan; bukan probabilitas statistik, harga transaksi aktual, atau opini penilai publik.

Kolom "Indeks kualitas data" adalah skor mutu kelengkapan/keterlacakan data, bukan peluang jual pada harga tersebut. Selalu tampilkan listing yang masuk, penyesuaian, jarak, missing fields, outlier, dan sumbernya untuk audit manusia.

## 5. Pelajaran audit atas 10 listing TAS 6/TAS 9 yang diberikan pengguna

Data listing tersebut cukup untuk estimasi indikatif awal, tetapi tidak seluruhnya tervalidasi sebagai iklan individual. Dalam audit halaman eksternal tanggal 23 November 2026:

- Listing Brighton dekat Polsek pada Rp425 juta, LT90/LB45, 2KT/1KM dan SHM dapat dicocokkan ke halaman detail yang cocok dengan spesifikasi pokok tersebut.
- URL Brighton `/cari-properti/view/perumtas-9-1` yang disematkan pada entri Rp395 juta/LT90/LB40 justru menampilkan Rp300 juta/LT72/LB36 pada ringkasan halaman saat diperiksa. Jangan menyalin harga/luas entri tanpa mencocokkan halaman.
- URL Brighton `/cari-properti/view/rumah-murah-dengan-luas-tanah-lebar-krian` yang disematkan pada entri Rp400 juta/LT72/LB36 justru menampilkan Rp380 juta/LT90/LB40 ketika diperiksa.
- Halaman proyek Pinhome TAS 6 yang ditemukan menampilkan harga dan tipe unit developer yang berbeda dari angka Rp430 juta/Rp395 juta/Rp460 juta di narasi. Angka yang user masukkan masih boleh dihitung sebagai input sementara dengan sumber/segmen diberi tanda belum diverifikasi; jangan disebut terverifikasi dari halaman proyek tersebut.
- Entri Threads over-kredit DP Rp30 juta plus cicilan tidak digabung dalam rentang pasar tunai.

Audit tersebut bukan pengganti pemeriksaan berkala. Listing dapat berubah, ditarik, atau diiklankan ulang. Pengguna harus memperbarui data sebelum underwriting final.

## 6. Tampilan dan operasional

- Tidak ada baris metrik lebih dari empat kolom.
- Dashboard khusus pengguna (termasuk metrik realisasi budget proyek berjalan) dipertahankan.
- Sebelum simpan, lakukan backup database dan cek tab `PAYLOAD_CHUNKS` bila payload besar.
- Jangan hapus snapshot analisis ketika memperbaiki payload. Missing/corrupt chunk harus dipulihkan, bukan diganti dengan payload kosong.
- Periksa regression tests dan deployment smoke test setelah push ke Streamlit Cloud.

## 7. Keterbatasan

Hasil PFMS bukan appraisal KJPP, bukan RAB kontraktor final, bukan survey ukur, dan bukan legal due diligence. Estimasi dibuat agar investor memiliki kisaran modal dan nilai pasar untuk mengambil keputusan awal di bawah ketidakpastian akses inspeksi. Kualitasnya akan meningkat jika proyek selesai menyumbangkan harga pembelian bahan, upah, volume realisasi, nota, penawaran kontraktor, dan harga jual aktual ke basis data internal.
