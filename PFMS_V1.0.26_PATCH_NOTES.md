# PFMS V1.0.26 — Combined Investment Memo & Financial Stress Test Release

## Scope
Rilis ini menggabungkan pekerjaan V1.0.25.3 (Investment Memo & AI Consistency) dan V1.0.26 (Financial Stress Test & BEP) ke dalam satu versi terpadu. V1.0.26 adalah versi aplikasi yang harus digunakan; V1.0.25.3 tidak perlu dipasang terpisah.

## A. Investment Memo & AI Consistency
- Prompt Gemini menerima label skenario Python yang eksplisit, tabel stress-test Python, metrik harga per m² tanah/bangunan dari setiap comparable dan objek, serta konteks portofolio proyek aktif dan proyek selesai.
- Instruksi AI diperketat: jangan menukar nilai Cepat/Moderat/Tekanan; tingkat valuasi Konservatif/Dasar/Optimistis bukan nama skenario proyek; angka finansial tetap merujuk hasil Python.
- Harga per m² tanah dan bangunan ditambahkan pada memo Markdown dan Word serta diberikan kepada Gemini sebagai indikator, bukan uplift ARV otomatis.
- Penomoran memo diperbaiki: Pertimbangan Analis Senior Bab 12 dan Portofolio Bab 13; tidak ada dua Bab 10.
- Cadangan Risk Register diberi label cadangan kas tambahan. Memo dan UI menjelaskan bahwa cadangan tersebut berada di luar contingency RAB/hidden-condition reserve dan harus diperiksa agar lingkup risiko tidak dihitung dua kali. Cadangan belum terpakai adalah buffer likuiditas, bukan biaya aktual.
- Ekspor memo tersedia dalam Word (.docx), PDF (.pdf), dan Markdown (.md). PDF dirender dari konten memorandum yang sama agar struktur dan isi tidak berbeda.

## B. Financial Stress Test & BEP
- Break-even exit price: harga jual saat net project profit = 0, memakai `calculate_project` yang sama dengan underwriting.
- Exit price hurdle untuk ROI minimum dan ROI GO.
- Maximum holding tolerance: pencarian numerik durasi maksimum sampai Project ROI turun ke ambang minimum, menggunakan exit konservatif dan monthly holding cost input proyek. Batas pencarian 120 bulan; bila threshold belum terlewati, hasil diberi label minimal sebesar batas pencarian.
- Empat skenario stress: Dasar, Moderat Buruk (-5% harga, +20% renovasi, holding minimal 9 bulan), Tekanan (parameter Owner), dan Ekstrem (parameter Owner, default diskon 20%, overrun 50%, holding 18 bulan).
- Stress test menampilkan exit price, diskon jual, kenaikan renovasi, holding period, total biaya termasuk biaya jual, profit bersih, dan Project ROI.
- Pengaturan skenario dapat diubah dari halaman Analisis. Hasil dihitung ulang oleh Python.

## Sumber Angka dan Batasan
- Semua nilai finansial di BEP/stress-test dihitung oleh Python melalui kalkulator proyek, bukan Gemini.
- Gemini menerima data dan menginterpretasikannya; ia tidak boleh menjadi sumber angka baru.
- Break-even adalah titik impas matematis pada asumsi biaya yang dimasukkan, bukan bukti bahwa pasar akan menyerap aset pada harga tersebut.
- Maximum holding sensitif terhadap monthly holding cost, biaya keterlambatan, dan exit price.
- ROI proyek tidak sama dengan ROI modal Owner bila proyek menggunakan pembiayaan bersama; simulasi JV/waterfall belum termasuk rilis ini.
- PDF memakai ReportLab. `reportlab>=4.2,<5.0` telah ditambahkan ke requirements.

## Kompatibilitas
- Tidak ada perubahan skema/header Google Sheets.
- Tidak ada file `.streamlit/secrets.toml` yang disertakan atau ditimpa.
- Rilis mengubah `app.py`, `config.py`, `requirements.txt`, modul underwriting/stress test, Gemini payload/prompt, report builder, dan regression tests.

## Validasi Lokal
- `python -m py_compile` seluruh modul aplikasi: lulus.
- Automated test suite: **298 passed**.
- DOCX render: 6 halaman; seluruh halaman diperiksa secara visual, tidak ada clipping/overlap yang terlihat.
- PDF render: 4 halaman; seluruh halaman diperiksa secara visual, tabel dan footer terbaca.
- PDF parsing: jumlah halaman dan teks memorandum lolos tes.
- ZIP integrity dan pemeriksaan secrets/cache: lulus.

## Belum Diuji
Belum ada live integration test terhadap Streamlit Cloud, Google Sheets, atau Gemini API menggunakan credentials deployment pengguna. Uji Gemini pada automated test memakai respons mock.
