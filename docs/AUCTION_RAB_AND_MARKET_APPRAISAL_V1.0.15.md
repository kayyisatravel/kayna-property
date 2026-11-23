# PFMS V1.0.15 — SOP Estimasi RAB Rumah Lelang & Pembanding Pasar

## 1. Tujuan dan batas penggunaan

PFMS adalah sistem underwriting investor rumah lelang, bukan aplikasi quantity surveyor, kontraktor, arsitek, atau penilai publik berizin. Tujuannya menghasilkan **estimasi modal proyek yang dapat dipakai untuk menyaring keputusan investasi**, dengan asumsi dan risiko yang dapat diaudit. Sistem tidak mengklaim bahwa nominalnya sama persis dengan tagihan akhir kontraktor.

Prinsipnya: **ketidakpastian harus ditampilkan dan diberi anggaran; jangan disamakan dengan biaya nol, tetapi juga jangan dinyatakan sebagai kerusakan yang sudah terbukti.**

## 2. SOP RAB untuk objek yang tidak bisa diperiksa penuh

PFMS menggunakan empat jenis perlakuan:

| Jenis pekerjaan | Perlakuan dalam sistem | Keyakinan |
|---|---|---|
| Kerusakan yang terlihat dan telah diukur | Masuk RAB dasar dengan volume dan harga indikatif | Sedang; naik bila diukur/ditawarkan kontraktor |
| Pekerjaan yang ditulis eksplisit pengguna dalam BoQ | Tetap masuk allowance modal selama volume dan satuan valid, walaupun akses inspeksi terbatas | Sedang atau Rendah sesuai sifat pekerjaan |
| Kondisi tersembunyi interior/MEP/struktur | Masuk bila pengguna sudah menganggarkan pekerjaan itu; jika belum, ditampilkan sebagai inspeksi/cadangan risiko yang terpisah | Rendah sampai diuji |
| Pekerjaan spekulatif yang belum punya volume atau dasar teknis | Tidak dipaksakan menjadi angka pasti; tampil sebagai Bersyarat/inspeksi | Rendah |

### Alur kerja yang disarankan

1. **Catat data resmi dan survei.** Isi LT, LB, lantai, jumlah kamar, akses/jalan, kondisi yang terlihat, status hunian dari survei, serta status inspeksi interior. Jangan menyatakan isi interior dari foto fasad.
2. **Susun BoQ screening.** Masukkan uraian, volume, dan satuan yang paling masuk akal. Contoh: luas atap kanopi dari perkiraan panjang × lebar; titik listrik dari jumlah titik yang akan diuji/diperemajakan; pekerjaan sanitair sebagai paket bila rincian komponen tidak dapat dilihat.
3. **Jangan menghapus scope hanya karena belum terlihat.** Baris eksplisit BoQ dengan volume/satuan valid tetap dihitung sebagai allowance. Tandai keyakinan Rendah untuk plafon interior, listrik, pipa, sanitair, dan pekerjaan lain yang perlu akses/tes. Setelah survei lebih lengkap, pengguna dapat menandai item tidak diperlukan atau mengganti volume/harga.
4. **Gunakan harga screening Python.** Sistem mencari pola pekerjaan dan satuannya pada katalog regional. Jika satuan tidak cocok (misalnya pekerjaan m² diberi satuan LS), harga tidak dipaksakan. Katalog mengeluarkan batas bawah, dasar dan atas, tanpa mengubah volume BoQ.
5. **Gemini sebagai pembantu, bukan kalkulator utama.** Gemini membantu mengurai scope dan menyediakan cross-check. Harga katalog yang cocok dipakai secara deterministik agar hasil berulang; harga AI disimpan sebagai pembanding catatan bila ada perbedaan signifikan. Aritmetika total tetap dilakukan Python.
6. **Tambahkan pemeriksaan dan cadangan.** Jika interior belum diperiksa, PFMS menghitung hidden-condition reserve dari persentase yang dapat diubah di Settings & Rules. Reserve ini terpisah dari contingency renovasi umum. Inspection allowance adalah biaya pemeriksaan, bukan biaya perbaikan.
7. **Cegah penghitungan ganda.** Item visual tambahan untuk kanopi, pagar, dinding rembes, pembersihan, fasad dan lantai tidak ditambahkan lagi bila scope yang sama sudah ada di BoQ. Skenario risiko interior tidak otomatis dijumlahkan; cocokkan per item dan tambahkan hanya kebutuhan yang belum dianggarkan.
8. **Validasi sebelum bid/anggaran dikunci.** Periksa harga bahan, upah, mobilisasi, akses, spesifikasi, volume aktual, biaya bongkar/angkut, pajak, biaya legal, penguasaan, holding dan pemasaran. Minta minimal dua penawaran lokal untuk pekerjaan signifikan.

## 3. Harga screening bukan harga kontrak

Katalog V1.0.15 berisi rentang harga screening untuk pekerjaan umum (bahan + upah) dengan asumsi spesifikasi ekonomis–menengah dan konteks Surabaya–Sidoarjo. Nilai katalog adalah default analitis yang disimpan dalam kode agar tidak tergantung respons Gemini. Ia **bukan** HSPK/SSH resmi untuk semua item, bukan survei harga toko secara live, dan bukan quotation vendor.

Rujukan SSH/HSP Sidoarjo 2026 berguna untuk mengecek item bahan/upah yang memang tercantum pada daftar resmi, tetapi harga paket renovasi tertentu masih perlu dirakit sesuai volume, spesifikasi dan metode kerja. Harga lokal dapat berubah menurut merek/ketebalan bahan, tinggi/bentang, akses angkut, kondisi dasar, upah, volume kecil, dan waktu pengerjaan.

Untuk meningkatkan kedekatan ke aktual, setiap proyek yang selesai sebaiknya menyimpan **harga satuan realisasi** ke riwayat proyek: area, spesifikasi, volume, satuan, harga bahan, upah, mobilisasi, tanggal, vendor/nota, dan wilayah. Katalog screening dapat dikalibrasi dari median realisasi beberapa proyek yang sebanding; jangan mengganti rate hanya dari satu penawaran outlier.

## 4. Cara membaca total RAB

- **Batas bawah:** volume × harga screening rendah.
- **RAB dasar:** volume × harga dasar screening. Ini basis modal underwriting.
- **Batas atas:** volume × harga screening atas. Ini sensitivitas biaya, bukan quotation termahal.
- **Contingency renovasi:** persentase tambahan atas RAB dasar untuk variasi pelaksanaan umum.
- **Hidden-condition reserve:** cadangan terpisah saat interior belum diinspeksi; tidak menyatakan kerusakan tersembunyi pasti ada.
- **Inspection allowance:** biaya pemeriksaan plafon/rangka/interior. Tidak boleh dianggap mencakup perbaikannya.

Jika ada item yang tidak memiliki volume atau harga dan masih berstatus dalam lingkup, sistem tidak boleh memberi label total lengkap. Baris tersebut tetap terlihat untuk dilengkapi. Untuk item tak terukur yang di luar BoQ, lakukan pengukuran sebelum menyetujui total.

## 5. SOP pembanding pasar lintas desa/kecamatan

PFMS tidak menggugurkan listing hanya karena beda desa, kecamatan atau nama perumahan. Jika koordinat target dan listing tersedia, sistem menghitung jarak garis lurus dengan rumus Haversine:

- sampai 500 meter: skor kedekatan 100;
- sampai 1 km: 95;
- sampai 2 km: 90;
- sampai 5 km: 80;
- sampai 10 km: 65;
- sampai 20 km: 45;
- lebih dari 20 km: 25.

Jadi, listing 500 meter di desa/kecamatan berbeda tetap dapat menjadi pembanding sangat dekat. Jarak yang dipakai adalah **jarak garis lurus antarkoordinat**, bukan jarak tempuh jalan.

### Prosedur input

1. Masukkan pin koordinat properti target (latitude/longitude desimal) dari Google Maps.
2. Masukkan koordinat pin masing-masing rumah pembanding. Kolom tersedia pada editor dan import CSV/TSV. Tanpa pasangan koordinat, sistem tidak mengarang jarak; data tetap dapat dinilai dengan informasi alamat dan kompleks, tetapi jaraknya diberi status belum terukur.
3. Kumpulkan beberapa listing sekitar, termasuk lintas batas administrasi; utamakan listing individual dan tanggal yang dapat ditelusuri.
4. Lengkapi LT/LB, jumlah KT/KM, lebar jalan, orientasi, sertifikat, akses dan kondisi bila tersedia.
5. Sistem memberi skor kemiripan dan menampilkan jarak per listing. Faktor fisik/legal yang berbeda mengurangi kemiripan dan bobot; luas tanah/bangunan dipakai untuk normalisasi nilai indikatif.
6. Penyesuaian nominal (`adjustment_pct`) harus memiliki alasan: misalnya kondisi siap huni versus butuh renovasi, akses gang versus jalan lebar, perbedaan legalitas, atau fitur bangunan. Gemini boleh memberi saran berdasar data yang diisi, tetapi saran tidak diterapkan sebelum pengguna memeriksa dan menyetujuinya.
7. Estimasi indikasi memakai weighted median, rentang dan pengurangan bobot outlier. Asking price diberi diskon negosiasi sesuai aturan; transaksi terverifikasi tidak dipotong diskon negosiasi yang sama. Listing dengan bukti lebih lemah menurunkan confidence. Urutan ini selaras secara metodologis dengan pendekatan pasar: kumpulkan data pembanding, bandingkan faktor relevan, lakukan penyesuaian agar setara, tentukan indikasi, beri bobot, lalu rekonsiliasi. Lihat [PMK 99 Tahun 2024 — Pasal 29 dan ketentuan metode perbandingan data pasar](https://www.djkn.kemenkeu.go.id/peraturan/baca/514/Peraturan-Menteri-Keuangan-Republik-Indonesia-Nomor-99-Tahun-2024.html).

### Hal yang harus dihindari

- Jangan memilih pembanding hanya karena nama perumahan sama jika lokasinya jauh atau karakteristiknya tidak sebanding.
- Jangan menolak pembanding dekat hanya karena beda desa/kecamatan.
- Jangan mencampur asking price, marked-sold belum terverifikasi dan transaksi aktual seolah memiliki kualitas bukti sama.
- Jangan menganggap skor kemiripan sebagai penyesuaian rupiah. Untuk perbedaan fitur yang berdampak harga, isikan penyesuaian persentase dengan alasan atau tinjau saran AI secara manual.
- Jangan menganggap output sebagai appraisal resmi. Hasil tetap indikasi underwriting yang perlu ditinjau terhadap kondisi pasar dan bukti transaksi.

## 6. Tampilan dan kompatibilitas

Semua baris metrik dibatasi maksimal empat kolom. Dashboard mempertahankan modifikasi pengguna, termasuk metrik **Realisasi Budget proyek berjalan**. Tidak ada penggantian nama tab Google Sheets, tidak ada penghapusan kolom lama, dan tidak diperlukan migrasi destruktif.

## 7. Uji penerimaan untuk TAS 3 M6/12

Dengan 16 baris BoQ TAS 3 M6/12 yang dicatat, parser harus:

- membaca 16 item;
- mempertahankan 16 volume dan satuan persis seperti input;
- memberi rate screening rendah/dasar/atas pada 16 item yang cocok di katalog;
- mempertahankan semua 16 item dalam lingkup allowance;
- menandai item tersembunyi seperti plafon interior, cat interior, kelistrikan dan sanitair dengan keyakinan Rendah;
- tidak menggandakan pengecatan pagar atau rangka kanopi baru jika sudah ada dalam BoQ;
- tetap dapat memasukkan inspeksi plafon/rangka serta inspeksi interior sebagai scope tersendiri.

Dalam simulasi deterministik atas daftar 16 item, total screening item BoQ (belum termasuk inspeksi tambahan, contingency, hidden reserve, mobilisasi, legalitas, dan biaya kepemilikan) adalah:

| Tingkat | Total indikatif |
|---|---:|
| Batas bawah | Rp35.772.000 |
| Dasar | Rp51.161.000 |
| Batas atas | Rp71.007.000 |

Nominal ini menguji fungsi katalog dan integritas perhitungan; bukan pengesahan harga riil atau hasil survei vendor. Pengguna tetap harus membandingkan spesifikasi dan penawaran setempat sebelum menetapkan budget proyek.
