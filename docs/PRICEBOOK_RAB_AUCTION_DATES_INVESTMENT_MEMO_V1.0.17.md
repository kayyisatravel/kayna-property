# PFMS V1.0.17 — Pricebook, RAB, Auction Dates, and Investment Memo

## 1. Harga renovasi dibuat konsisten

Gemini tidak lagi menentukan harga satuan yang masuk ke perhitungan keuangan. Model digunakan untuk membaca dokumen, mengidentifikasi scope, membantu volume dan evidence; Python menentukan harga dari katalog berversi atau override manual. Harga yang tidak cocok dengan katalog dibiarkan kosong dan diberi pesan untuk meminta quotation atau memasukkan override yang disertai sumber.

Katalog internal `PFMS_SIDOARJO_SCREENING_2026_11_V2` berisi allowance low/base/high bahan+upah untuk lingkup renovasi rumah yang umum. Harga komposit ini merupakan screening underwriting, bukan daftar tarif resmi dan bukan quotation. Harga material dapat mengambil jangkar dari SSH Sidoarjo TA 2026; metode AHSP PUPR digunakan sebagai kerangka pemikiran untuk membangun HSD bahan, tenaga kerja, alat, koefisien, biaya langsung dan tidak langsung.

### Rujukan

- Perbup Sidoarjo No. 27 Tahun 2025 tentang Standar Harga Satuan Tahun Anggaran 2026: https://sidoarjokab.go.id/berita/peraturan-bupati-sidoarjo-no-27-tahun-2025-1751631865
- Perbup Sidoarjo No. 75 Tahun 2025 tentang Analisis Standar Belanja dan Harga Satuan Pokok Kegiatan Fisik: https://jdih.sidoarjokab.go.id/peraturan/202500200074/peraturan-bupati-no-75-tahun-2025-analisis-standar-belanja-dan-harga-satuan-poko
- Permen PUPR No. 8 Tahun 2023 tentang Pedoman Penyusunan Perkiraan Biaya Pekerjaan Konstruksi Bidang PUPR: https://peraturan.bpk.go.id/Details/262345/permen-pupr-no-8-tahun-2023

SSH pemerintah memuat komponen harga dan basis pengadaan pemerintah; AHSP memberi metode perhitungan. Keduanya tidak otomatis identik dengan harga borongan rumah privat. PFMS perlu dikalibrasi berkala dengan dua atau lebih penawaran vendor lokal dan biaya aktual proyek.

### Override manual

Jika pengguna mengubah salah satu nilai harga low/base/high dan sumber berubah menjadi `Override manual pengguna`, harga akan dikunci. Analisis ulang tidak menimpa harga tersebut. Pengguna sebaiknya menuliskan penyedia, tanggal quotation, spesifikasi, dan masa berlaku harga pada kolom catatan.

## 2. RAB dan subtotal

Tampilan RAB memiliki dua lapisan: editor untuk memasukkan atau mengubah volume/harga, dan rincian kalkulasi read-only yang dibuat Python. Setiap item menampilkan volume, unit rate, subtotal low/base/high dan status masuk anggaran. Subtotal dasar adalah `volume dipakai × harga satuan dasar`. Tabel kedua menjumlahkan subtotal per kelompok pekerjaan. Baris yang belum memiliki volume atau harga tetap terlihat; tidak boleh dianggap bernilai nol.

## 3. Tanggal lelang dan uang jaminan

Tanggal lelang dan batas setor uang jaminan diekstrak dari PDF/foto pengumuman yang diunggah. Field mempunyai evidence kutipan terpisah, dan aplikasi tidak lagi menyediakan date picker manual pada dua field tersebut. Batas pelunasan setelah menang tetap merupakan field tersendiri.

Parser hanya menerima satu tanggal kalender eksplisit. Teks relatif seperti H-1 atau “satu hari sebelum lelang” tidak dikonversi menjadi tanggal kalender. Jika tanggal tidak terbaca atau ambigu, aplikasi mengosongkan field dan menunjukkan evidence yang tersedia. Ini bukan live API/scraping KPKNL; pengguna harus mengunggah dokumen resmi terbaru. File yang pernah di-cache dengan schema lama perlu diparse ulang satu kali.

## 4. Investment Memo

Word dan Markdown dibuat dari snapshot hasil analisis dengan Python, bukan Gemini. Kontennya meliputi ringkasan eksekutif, jadwal dan evidence lelang, identitas aset, kondisi fisik dan legal, pasar dan pembanding, daftar RAB serta subtotal kelompok, proyeksi modal, skenario harga jual/profit/ROI, strategi bid, risk register, kesiapan pendanaan, checklist due diligence, asumsi dan batasan. Nama file memuat nama properti dan kode lot.

Memo adalah proposal screening untuk diskusi investor, bukan appraisal resmi, pendapat hukum, quotation, atau jaminan hasil. Data yang kosong tetap ditandai kosong; dokumen tidak boleh menciptakan data yang tidak ada.

## 5. Checklist deployment/regresi

1. Upload satu pengumuman lelang resmi yang berisi tanggal setor dan tanggal lelang. Cocokkan field dan kutipan evidence terhadap PDF. Pastikan tanggal pengumuman dan tanggal pelunasan tidak tertukar.
2. Upload pengumuman yang hanya memuat tanggal relatif atau scan tidak jelas. Pastikan field tanggal tetap kosong, bukan dihitung otomatis.
3. Jalankan RAB dengan scope yang mempunyai katalog. Pastikan Gemini tidak mengembalikan harga sebagai sumber kalkulasi dan pricebook menghasilkan angka yang sama untuk scope/unit yang sama.
4. Ubah harga satuan secara manual, jalankan analisis ulang, pastikan harga override tetap.
5. Coba scope yang tidak ada dalam katalog. Pastikan harga tidak dikarang; aplikasi meminta quotation atau override manual.
6. Cocokkan subtotal tiap baris dengan volume × harga satuan dan total kelompok pekerjaan dengan penjumlahan baris yang masuk scope.
7. Unduh DOCX dan Markdown. Pastikan nama file berisi nama properti/kode lot, serta dokumen memuat pricebook, RAB, pasar, jadwal lelang, risiko, modal, ROI dan due diligence.
8. Pastikan memo dibuat tanpa request Gemini tambahan.
9. Pastikan `PAYLOAD_CHUNKS` tetap dapat membaca snapshot lama, dan tidak ada tab/header Google Sheets yang dihapus.
10. Pastikan `.streamlit/secrets.toml` tetap utuh dan seluruh layout metrik maksimal empat kolom.

## 6. Batas pengujian

Uji unit dan integrasi lokal tidak membuktikan koneksi aktif ke Google Sheets, deployment Streamlit Cloud, atau kuota Gemini pada akun pengguna. Smoke test tersebut perlu dijalankan setelah deployment menggunakan satu objek uji yang tidak sensitif.
