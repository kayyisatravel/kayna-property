# Renovation Estimator — PFMS V1.0.6

Dokumen ini menjelaskan cara PFMS menggunakan profil objek dan kondisi bangunan untuk menyiapkan **draft RAB awal**. Ini bukan AHSP final, appraisal teknis, atau penawaran kontraktor.

## 1. Data yang digunakan

- Kondisi fisik umum yang dipilih user.
- Kategori/lingkup renovasi yang dipilih user (atau Auto).
- LT, LB, jumlah lantai, dan luas tapak lantai dasar jika diketahui.
- Tipe properti, jumlah kamar tidur dan kamar mandi.
- Lebar jalan dan akses kendaraan.
- Deskripsi kondisi aktual, deskripsi fasad hasil AI/survei, catatan survei.
- Foto yang diunggah (maksimal enam berkas dalam proses RAB, sesuai UI).

Gemini 3.5 Flash-Lite memilih lingkup pekerjaan yang didukung bukti dan menyarankan harga satuan rendah/konservatif. Python menghitung volume screening secara deterministik dari katalog; model tidak boleh mengganti formula volume untuk kode item yang dikenal.

### Peran setiap input

| Input | Penggunaan |
|---|---|
| LT | Pematangan lahan dan pemeriksaan luas tapak relatif terhadap bidang tanah |
| LB | Lantai/plafon, dinding, titik listrik allowance, dan volume puing |
| Luas tapak lantai dasar | Dasar yang lebih baik untuk menghitung luas atap |
| Jumlah lantai | Estimasi tapak atap ketika tapak aktual tidak diinput |
| Tipe properti | Konteks pemilihan scope, material/finishing dan harga satuan; bukan koefisien volume tersendiri |
| Jumlah kamar tidur | Konteks kompleksitas ruang; menggeser titik tengah estimasi area dinding hanya dalam rentang kasar |
| Jumlah kamar mandi | Jumlah maksimum paket area basah bila pekerjaan tersebut dipilih; tidak berarti setiap kamar mandi pasti rusak |
| Lebar/akses jalan | Konteks mobilisasi dan biaya angkut; tidak mengubah volume tanpa data pendukung |
| Kondisi fisik/deskripsi/foto | Menentukan kategori dan item yang relevan; kerusakan tersembunyi tidak boleh ditebak |

## 2. Kategori pekerjaan

### Auto sesuai kondisi umum
Jika kondisi belum diketahui, sistem hanya menyarankan inspeksi atap, plafon, dinding, lantai, utilitas dan area basah, serta persiapan/pembersihan. Sistem tidak otomatis menganggap objek memerlukan renovasi ringan.

Jika kondisi menyebut siap huni, item kosmetik dapat menjadi rekomendasi opsional. Jika user menyebut cat mengelupas/pengecatan, kategori kosmetik dapat diinferensikan. Pilihan kategori eksplisit dari user selalu mengalahkan inferensi.

### Renovasi Kosmetik
Scope utama saat kategori kosmetik dipilih eksplisit/inferensi berbukti:
- Persiapan dan proteksi.
- Pengikisan cat lepas, plamir/aci lokal, cat dinding.
- Cat plafon/perbaikan retak rambut lokal.
- Poles lantai **atau** vinyl/SPC (pilih salah satu).
- Cat kusen/pintu dan aksesori minor bila dibutuhkan.

Pekerjaan persiapan, dinding dan plafon menjadi scope wajib. Jika Gemini melewatkannya, Python menambahkan placeholder tanpa harga agar RAB tidak tampak lengkap secara palsu.

### Renovasi Ringan
Perbaikan lokal, bukan penggantian seluruh sistem. Katalog Python memberi allowance screening low-confidence bila AI memilih scope terkait:
- Atap lokal: 5–15% dari estimasi luas atap.
- Plafon lokal: 3–10% dari LB.
- Keramik lokal: 2–6% dari LB.
- Sanitair minor dapat mengacu pada jumlah kamar mandi bila ada bukti kerusakan.
- Titik listrik, kusen dan plumbing tetap harus diukur/diidentifikasi; tidak ditebak dari luas saja.

Allowance persentase tersebut adalah heuristic internal untuk estimasi awal, **bukan koefisien resmi**. Jika tidak ada bukti kerusakan, AI seharusnya tidak memasukkan item tersebut sebagai pekerjaan yang pasti.

### Renovasi Sedang
Menggunakan scope penggantian komponen utama sesuai kategori: pembongkaran/pembaruan atap, plafon dan lantai, kamar mandi, serta allowance instalasi listrik. Pipa hanya dihitung bila jalurnya dapat diukur. Struktur dan denah dianggap dipertahankan.

### Renovasi Berat
Pekerjaan struktur, pondasi, kolom, balok, dak, perubahan denah dan penambahan lantai tidak dapat diestimasi aman hanya dari LT/LB atau foto. Volume/harga item struktur dibiarkan kosong sampai ada pemeriksaan engineer, desain dan RAB penyedia jasa. Item struktur wajib yang belum dikuantifikasi akan membuat keputusan tetap HOLD.

### Hitung Tanah
Menggunakan scope pemutusan utilitas, demolisi, pembuangan puing dan land clearing. Volume puing serta jumlah ritase merupakan allowance ber-confidence rendah dan wajib dikonfirmasi dengan kontraktor/pengelola pembuangan.

## 3. Koefisien kuantitas screening

| Pekerjaan | Rumus PFMS | Penilaian dan batas penggunaan |
|---|---|---|
| Lantai/plafon penuh | 1,0 × LB agregat | Titik awal. Kurangi void, area terbuka, carport/teras yang tidak dikerjakan. |
| Atap miring | 1,25–1,35 × luas tapak | Tapak aktual lebih diutamakan. Jika tidak tersedia, PFMS memakai LB ÷ jumlah lantai sebagai estimasi. Bentuk, kemiringan, jurai dan overhang harus dicek. |
| Dinding dua sisi | 2,5–3,0 × LB | Perkiraan kasar bidang cat gabungan, confidence rendah. Titik tengah default bergerak di dalam rentang menurut jumlah kamar tidur; ukur keliling, tinggi, partisi dan bukaan sebelum kontrak. |
| Titik listrik | ceil(LB ÷ 6) | Hanya allowance untuk penggantian instalasi penuh pada renovasi sedang/berat; bukan standar teknis atau desain final. Final berdasarkan denah titik, beban dan teknisi listrik. |
| Puing demolisi | 0,30–0,50 m³ × LB | Sangat kasar. Tergantung dinding, beton, lantai, fondasi, pemilahan, metode bongkar dan faktor pengembangan puing. |
| Ritase truk | ceil(volume puing ÷ kapasitas truk) | Default kapasitas 5 m³; aktual perlu dikonfirmasi (sering berbeda 4–6 m³ atau sesuai jenis kendaraan/akses). |

## 4. Koreksi teknis atas rasio awal

1. **Atap:** rasio 1,25–1,35 sebaiknya dikalikan luas tapak bangunan, bukan LB total pada rumah dua lantai. Luas tapak aktual dari site plan/pengukuran lebih baik. Bila tidak ada, LB dibagi jumlah lantai hanya pendekatan dan dapat salah bila luas tiap lantai berbeda.
2. **Dinding:** 2,5–3,0 × LB boleh menjadi allowance awal untuk luas bidang cat, tetapi bukan pengganti take-off dinding. Jumlah kamar tidur hanya proksi kasar kompleksitas partisi, bukan pengukuran.
3. **Titik listrik:** LB/6 adalah allowance screening, bukan standar jumlah titik yang wajib. Untuk renovasi ringan, jangan memakai rumus ini karena pekerjaan hanya penggantian titik lokal. Untuk penggantian total, perlu rencana instalasi dan pemeriksaan teknisi.
4. **Puing:** 0,3–0,5 m³/m² boleh dipakai untuk penyaringan awal, tetapi keandalan rendah. Volume puing lepas dapat dipengaruhi volume struktur, material, fondasi, pemilahan, dan metode bongkar. Konfirmasi ritase dan biaya buang secara lokal.
5. **Luas lantai/plafon:** LB × 1,0 hanya titik awal untuk cakupan penuh. Area yang tidak dikerjakan harus dikeluarkan.

## 5. Status RAB dan persetujuan pengguna

- Harga satuan dari Gemini adalah estimasi konservatif indikatif, bukan harga vendor real-time, bukan HSPK/HSP resmi, dan bukan penawaran kontraktor.
- Volume item yang memiliki katalog Python memakai quantity hint/rentang dari Python; volume item tersembunyi/tidak terukur tetap kosong.
- Scope wajib yang terlewat AI muncul sebagai placeholder tanpa harga.
- Baris dengan prioritas `Tidak diperlukan setelah ditinjau` tidak dihitung ke total RAB.
- Item wajib tanpa volume atau harga konservatif memblokir GO. Item opsional dapat tetap kosong jika memang tidak diperlukan dan telah ditinjau.
- Contingency dihitung terpisah oleh Python; jangan memasukkannya lagi dalam unit price AI.
- Semua volume dan harga harus diperiksa, dikoreksi, dan ditinjau pengguna sebelum analisis dianggap final.

## 6. Referensi teknis

Penyusunan estimasi biaya konstruksi pemerintah Indonesia mengacu antara lain pada **Permen PUPR No. 8 Tahun 2023 tentang Pedoman Penyusunan Perkiraan Biaya Pekerjaan Konstruksi Bidang Pekerjaan Umum dan Perumahan Rakyat**. Koefisien AHSP dan harga satuan harus mempertimbangkan metode/spesifikasi pekerjaan, tenaga kerja, bahan, peralatan, serta kondisi/lokasi pekerjaan. Rasio PFMS di atas bukan pengganti AHSP atau survei harga setempat.

- JDIH PUPR: https://jdih.pu.go.id/
- Untuk objek Sidoarjo, periksa SSH/HSPK dan standar harga pemerintah daerah yang berlaku pada tahun anggaran terkait, kemudian bandingkan dengan penawaran tukang/kontraktor setempat.
