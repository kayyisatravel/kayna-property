# PFMS V1.0.21 — Complete Investment Financial Schedules & Executive Dashboard

## Perubahan utama

### Proposal Investasi Properti
- Menambahkan tiga tabel keuangan lengkap untuk skenario bidding limit, tengah, dan atas.
- **Rincian Total Modal per Level Bidding** merinci harga bid hingga biaya pra-penjualan: bea lelang, BPHTB, PNBP BPN, roya, administrasi, legal, PPAT/notaris, penguasaan/kerohiman, RAB, contingency, hidden-condition reserve, holding, marketing, biaya lain, dan total modal.
- **Kebutuhan Kas dan Cadangan Risiko** menampilkan modal pra-penjualan, cadangan penguasaan, cadangan risiko umum, total kebutuhan kas, kas yang tersedia, surplus/kekurangan, serta uang jaminan sebagai kebutuhan kas awal yang tidak dihitung ganda sebagai modal.
- **Biaya Penjualan dan Hasil Bersih** menampilkan harga penjualan, PPh final, komisi agen, AJB/PPAT, biaya penjualan lain, total biaya jual, penjualan bersih, modal pra-penjualan, profit, dan ROI.
- Nilai berasal dari hasil perhitungan scenario calculator yang sama dengan aplikasi; tidak ada kalkulasi Gemini tambahan.
- Tabel menggunakan gaya V1.0.18 dengan banding bersih, ruang kolom yang lebih sesuai, baris total ter-highlight, serta pemisahan halaman untuk bagian keuangan/RAB/risiko agar tabel tidak terpotong secara tidak rapi.

### Ringkasan Utama
- Menambahkan model dashboard `core/dashboard.py` yang mengolah data yang sudah dibaca/cached oleh aplikasi.
- Menampilkan agenda tanggal lelang dan batas setor jaminan, pipeline prospek, jumlah proyek aktif dan selesai, kas siap investasi, profit terealisasi, biaya aktual/komitmen/forecast, dan peringatan budget/target jual.
- Proyek aktif kini menampilkan progres fisik berbobot durasi dan cakupan item pekerjaan yang sudah diperbarui. Status fisik berasal dari `PROJECT_BUDGETS` atau fallback milestone; pembayaran tidak dianggap bukti pekerjaan selesai.
- Branding halaman menjadi **KAYNA PROPERTY MANAGEMENT SYSTEM**.

## Efisiensi & kompatibilitas
- Ringkasan dashboard tidak memanggil Gemini.
- Pembacaan Google Sheets mengikuti cache 300 detik yang sudah ada. Sorting, agregasi, dan pembuatan agenda dilakukan lokal di Python.
- Tidak menambah worksheet baru dan tidak mengubah header Google Sheets lama.
- Snapshot dan data lama tetap dipertahankan. Tidak ada migrasi destruktif.
- `.streamlit/secrets.toml` tidak disertakan atau ditimpa.

## Validasi
- `pytest -q`: 203 passed.
- `python -m compileall -q .`: passed.
- Full source diuji dari ekstraksi bersih.
- Upgrade patch diuji di atas source V1.0.20 yang bersih.
- Contoh DOCX dirender dan diperiksa secara visual.
- Belum dilakukan live test dengan kredensial Google Sheets/Gemini atau deployment Streamlit Cloud pengguna.
