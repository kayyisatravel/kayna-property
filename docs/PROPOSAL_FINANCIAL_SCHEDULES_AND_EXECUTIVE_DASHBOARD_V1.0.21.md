# Panduan Proposal dan Ringkasan Utama V1.0.21

## 1. Tiga tabel keuangan di Proposal Investasi Properti

Seluruh tabel menggunakan hasil `_scenario_rows(snapshot)` yang sama dengan calculator underwriting. Kolom skenario diidentifikasi dengan nilai bid numerik dan label Limit/Tengah/Atas.

### Rincian Total Modal per Level Bidding

Baris biaya mencakup harga bid, bea lelang, BPHTB, biaya BPN/roya, administrasi akuisisi, legalitas, notaris/PPAT akuisisi, penguasaan/kerohiman, renovasi, contingency, cadangan kondisi tersembunyi, holding, marketing, dan biaya pra-penjualan lain. Total merupakan modal sampai aset siap dipasarkan; biaya penjualan disajikan terpisah.

### Kebutuhan Kas dan Cadangan Risiko

Menampilkan total modal pra-penjualan ditambah cadangan risiko penguasaan dan cadangan risiko umum. Kas siap investasi dibandingkan terhadap total kebutuhan untuk menunjukkan surplus atau kekurangan. Uang jaminan ditampilkan sebagai kebutuhan kas awal; nilainya bukan biaya tambahan karena diperhitungkan dalam pembayaran harga lelang.

### Biaya Penjualan dan Hasil Bersih

Menampilkan asumsi harga jual, PPh final, komisi agen, biaya PPAT/AJB penjual, biaya jual lain, total biaya penjualan, penjualan bersih setelah biaya jual, modal pra-penjualan, profit, dan ROI.

## 2. Ringkasan Utama

Dashboard mengolah tabel yang telah tersedia: PROPERTIES, ANALYSIS_HISTORY, COST_ACTUALS, PROJECT_BUDGETS, SALES_CLOSING, CASH_POSITION, CASHFLOW_EVENTS, serta PROJECT_MILESTONES. Pembacaan tetap menggunakan mekanisme cache `cached_read` dengan TTL yang dikonfigurasi (300 detik pada pengaturan standar). Tidak ada panggilan Gemini untuk membentuk dashboard.

Agenda lelang menampilkan batas setor jaminan dan tanggal lelang yang berada pada rentang 14 hari terlewat hingga 60 hari ke depan. Peringatan proyek menampilkan target penjualan yang mendekat/terlewat dan proyeksi penggunaan anggaran yang mendekati/melebihi budget.

Progres fisik dihitung dari status item kerja pada anggaran renovasi dan dibobot berdasarkan perkiraan hari kerja. Cakupan pembaruan status ditampilkan agar angka tidak dianggap lebih pasti daripada datanya. Bila tidak ada status pekerjaan yang diperbarui, progres ditampilkan sebagai belum tersedia. Milestone menjadi fallback untuk proyek lama yang belum memiliki rincian work item.
