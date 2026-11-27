# SOP Tanggal KPKNL dan Batas Pelunasan — V1.0.23

## Prinsip sumber data
Tanggal lelang dan batas setor jaminan diekstrak dari dokumen KPKNL. Keduanya ditampilkan sebagai date picker yang dapat dikoreksi, tetapi tidak meminta checkbox untuk mengaktifkannya. Tanggal yang tidak terbaca atau ambigu tidak boleh ditebak.

## Batas pelunasan
Untuk lelang biasa, perhitungan default adalah lima hari kerja setelah tanggal lelang. Tanggal lelang dihitung sebagai hari ke-0. Sabtu, Minggu, hari libur nasional, dan cuti bersama pada kalender SKB 3 Menteri 2026–2027 dilewati. Untuk tahun di luar cakupan tersebut, sistem menandai hasil sebagai provisional karena daftar libur tahun tersebut belum tertanam; verifikasi kalender operasional KPKNL sebelum mengandalkan tanggal tersebut.

Bila dokumen KPKNL secara eksplisit menyebut tanggal pelunasan, tanggal dokumen menjadi sumber utama. Pengecualian PMK 122/2023 Pasal 88 juga diperhitungkan untuk lelang terjadwal khusus (2 hari kerja) serta pembeli instansi tertentu atau nilai limit minimal Rp500 miliar (14 hari kerja).

## Sinkronisasi data dan proposal
Tanggal, dasar perhitungan, serta nama file sumber disimpan di `property` pada snapshot analisis. Investment Proposal membaca nilai yang sama; tidak melakukan perhitungan tanggal kedua yang terpisah.

## Sumber resmi
- PMK 122 Tahun 2023, Pasal 88: https://www.djkn.kemenkeu.go.id/peraturan/baca/486/Peraturan-Menteri-Keuangan-Nomor-122-Tahun-2023.html
- SKB 3 Menteri hari libur/cuti bersama 2026: https://www.setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2026
- SKB 3 Menteri hari libur/cuti bersama 2027: https://setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2027
