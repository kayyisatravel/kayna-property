# PFMS V1.0.8 — Panduan UX dan membaca hasil

## Alur analisis

1. **Data lelang & legal** — masukkan data resmi lelang, identitas objek, luas, NJOP jika tersedia, serta verifikasi legal dan aturan pajak.
2. **Survei & risiko** — catat status survei/penghuni, kondisi fisik, temuan, risiko, mitigasi, serta konfirmasi bahwa risk register sudah ditinjau.
3. **Harga pembanding** — masukkan listing satu per satu atau gunakan parser narasi. Bedakan tanggal publikasi iklan dengan tanggal saat data ditemukan/dikumpulkan. Tanggal publikasi boleh kosong; jangan mengarang tanggal.
4. **Biaya & RAB** — tinjau setiap item pekerjaan, biaya legal/BPN, penguasaan, contingency, holding, marketing, dan biaya lain. Nilai nol harus merupakan keputusan yang disengaja.
5. **Analisis dan simpan** — jalankan Python underwriting, baca blockers/peringatan, lalu simpan snapshot ke database.

Progress bar hanya membantu orientasi; tidak menggantikan hard gate underwriting.

## Standar comparable

Comparable boleh digunakan untuk indikasi awal bila memiliki identitas listing, harga positif, minimal satu ukuran LT/LB, dan sumber. Untuk GO, tetap dibutuhkan minimal lima listing yang masing-masing memiliki URL langsung ke iklan individual, tanggal ditemukan/dikumpulkan, dan confidence pasar minimal 55/100.

Tanggal publikasi iklan bersifat opsional. Tanggal ditemukan adalah tanggal pengguna mengumpulkan/mencatat listing, bukan tanggal listing diterbitkan. Tombol pengisian tanggal hanya mengisi tanggal saat pengguna melakukan pencatatan; pengguna harus memastikan tanggal tersebut sesuai kenyataan.

Tombol konfirmasi URL individual adalah pernyataan pengguna bahwa URL telah dibuka dan memang menuju iklan rumah tertentu. Jangan konfirmasi URL pencarian, kategori, portal umum, atau halaman kompleks sebagai listing individual.

## Interpretasi NJOP

NJOP bukan harga pasar. Sistem hanya mengkalibrasi indikasi berbasis NJOP jika minimal tiga comparable memiliki pasangan data harga dan NJOP. Rasio lokal tersebut menghasilkan indikasi target dan dapat dicampurkan ke Base ARV dengan bobot pengaturan. Jika data pasangan tidak cukup, NJOP ditampilkan sebagai referensi dan tidak dipaksakan menjadi ARV.

## Arti angka keuangan

- **Total modal proyek:** pengeluaran yang diperkirakan sampai properti siap dipasarkan, sebelum biaya penjualan.
- **Cadangan risiko:** kebutuhan likuiditas untuk kejadian yang mungkin muncul; tidak menjadi biaya profit sampai benar-benar digunakan.
- **Biaya penjualan:** dikurangkan dari hasil penjualan untuk memperoleh net proceeds; tidak dijumlahkan dua kali ke modal sebelum penjualan.
- **Kebutuhan kas + cadangan:** total modal proyek ditambah cadangan risiko yang belum terpakai.
- **Kas siap investasi:** real cash dikurangi pengeluaran mendatang terkonfirmasi dan cadangan likuiditas.
- **Uang jaminan:** kebutuhan kas di muka sesuai ketentuan lelang; perhatikan mekanisme pengkreditannya dan jangan dihitung dua kali.

## Keputusan

- **GO:** seluruh hard gate yang dikodekan telah terpenuhi; tetap lakukan pemeriksaan akhir sebelum bidding.
- **CONDITIONAL GO:** secara awal layak, tetapi ada pemeriksaan penting yang masih harus diselesaikan.
- **HOLD:** data atau konfirmasi penting belum lengkap. Jangan bidding sebelum blocker diselesaikan.
- **DO NOT BID:** batas ekonomi atau hard stop risiko menunjukkan objek tidak layak pada nilai limit.
