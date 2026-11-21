# PFMS V1.0.12 — RAB Evidence Guardrails & Auction Bid Logic Audit

## Tujuan
Audit dan perbaikan logika RAB renovasi, pemisahan estimasi dari fakta visual, kelengkapan RAB parsial, serta batas bidding agar tidak pernah menampilkan harga bid di bawah nilai limit lelang.

## Perbaikan RAB
- Kategori primer eksplisit pengguna/deskripsi diprioritaskan. Catatan risiko yang menyatakan renovasi *dapat* bergeser ke berat setelah inspeksi tidak otomatis mengubah kategori kondisi saat ini.
- Kerusakan lokal atap kanopi depan dipetakan ke satu scope lokal dengan volume kosong hingga diukur. Penggantian rangka bersyarat setelah inspeksi; penggantian seluruh atap tidak diasumsikan.
- Dinding lembap memakai satu scope khusus; paket dinding generik untuk bidang yang sama disupresi.
- Retak rabat beton carport tidak otomatis menghasilkan pekerjaan pemasangan keramik. Metode perbaikan ditetapkan setelah inspeksi.
- Pengecatan pagar dan fasad adalah opsi estetika/bersyarat, bukan kerusakan struktural atau perbaikan wajib.
- AI tidak boleh mengukur skala foto atau membuat volume custom dari gambar. Python memakai hint yang disetujui; item custom/tidak terukur tetap kosong sampai diukur.
- Struktur utama tidak boleh ditaksir dari foto fasad. Bila ada indikasi struktur, wajib evaluasi engineer dan RAB teknis terpisah.
- Interior yang tidak tampak tetap unknown. Skenario biaya interior tidak masuk RAB dasar sampai diperiksa dan dikonfirmasi.
- Status hunian tidak boleh disimpulkan dari tanaman, kain, ember, barang, pintu tertutup atau kondisi gelap. Sistem mencatat status dari survei pengguna, atau secara eksplisit menyebut belum diketahui.
- Subtotal item yang sudah punya kuantitas dan harga tidak ditampilkan sebagai total RAB lengkap. Setiap item yang dipertahankan dalam base budget harus memiliki kuantitas positif dan harga konservatif.

## Perbaikan bidding
- Bid legal selalu mulai dari auction limit, pada pola `limit + n × increment`.
- Jika ceiling ROI 35% berada di bawah limit, `mid_bid` dikosongkan. Ceiling teoritis hanya ditampilkan sebagai diagnostik dan bukan harga bid.
- Maximum bid dihitung untuk target ROI minimum 25% dan tidak boleh berada di bawah limit.
- Walk-away hanya tersedia jika increment resmi telah dikonfirmasi; walk-away adalah satu increment di atas maximum bid.
- Tanpa increment resmi, bid legal dan walk-away dikosongkan. Ceiling simulasi diberi label bukan harga bid.
- Kecukupan kas tetap dinilai terpisah dari kelayakan ekonomi harga bid.

## Kasus regression TAS 3 M6/12
Untuk narasi kategori Renovasi Sedang disertai atap kanopi lokal jebol, dinding carport lembap, rabat beton retak, pagar kusam dan interior belum terlihat, hasil yang diharapkan:
- Kategori tetap Renovasi Sedang.
- `VIS_FRONT_ROOF` dan `VIS_DAMP_WALL` ada satu kali, dengan quantity kosong sampai diukur.
- Kerangka atap, plafon, rabat carport, pagar dan pengecatan fasad tetap conditional/disarankan sesuai bukti dan inspeksi; tidak dihitung ganda.
- Tidak ada pekerjaan struktur berat atau penggantian seluruh atap hanya dari caveat risiko.
- Interior tetap skenario terpisah dan okupansi tidak disimpulkan dari foto.
- RAB tetap parsial jika item dasar belum diukur/diberi harga.

## Simulasi regression bidding
Dengan fixture pengujian (limit Rp160.000.000, conservative ARV Rp300.000.000, increment Rp1.000.000, biaya asumsi dalam `tests/test_logic_audit_fixes.py`):
- Ceiling teoritis ROI 35% sekitar Rp147.369.000, di bawah limit. `mid_bid=None`; nilai itu bukan harga bidding.
- Maximum bid ROI 25% pada tangga limit + increment sekitar Rp162.000.000.
- Walk-away sekitar Rp163.000.000.
Angka ini hanya hasil fixture regression, bukan rekomendasi untuk objek nyata.

## Keterbatasan harga satuan
Pemanggilan Gemini saat ini tidak menerima database harga real-time, HSPK/SSH Sidoarjo atau penawaran kontraktor. Karena itu harga AI adalah screening estimate generik, bukan standar harga lokal atau quotation. Untuk peningkatan akurasi selanjutnya perlu dibuat Price Book berisi spesifikasi, komponen bahan/upah/alat, wilayah, sumber, tanggal dan setidaknya dua quotation lokal yang sebanding.

Referensi eksternal yang relevan:
- Perbup Sidoarjo No. 27 Tahun 2025 menetapkan Standar Harga Satuan di lingkungan Pemerintah Kabupaten Sidoarjo TA 2026: https://sidoarjokab.go.id/berita/pengumuman/1751631865/0
- Permen PUPR No. 8 Tahun 2023 tentang pedoman penyusunan perkiraan biaya pekerjaan konstruksi masih berstatus berlaku di JDIH PUPR: https://jdih.pu.go.id/detail-dokumen/PermenPUPR-nomor-8-tahun-2023-Pedoman-Penyusunan-Perkiraan-Biaya-Pekerjaan-Konstruksi-Bidang-Pekerjaan-Umum-dan-Perumahan-Rakyat

## Kompatibilitas
- Tidak ada tab Google Sheets yang dihapus/diubah namanya.
- Tidak ada secrets atau kredensial yang ditambahkan.
- Snapshot underwriting dan data proyek lama tetap dapat dibaca.
- Perubahan hanya additive/logic guardrail pada source dan output AI.

## Pengujian
- `python -m compileall -q .`: passed.
- `pytest -q`: 122 passed.
- Uji layanan Google Sheets, Gemini API dan Streamlit Cloud secara live: belum dilakukan.
