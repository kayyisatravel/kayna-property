# Property Flipper Management System (PFMS) — V1.0.4.3

Aplikasi Streamlit untuk underwriting rumah lelang, keputusan bidding, pengelolaan properti yang dimenangkan, dan pencatatan track record sampai aset terjual.

**Prinsip utama: SELL FIRST BEFORE BUYING.** Python menjadi sumber kebenaran semua kalkulasi; Gemini membantu ekstraksi dan review. Google Sheets menjadi database utama.

## Fitur V1

- Upload PDF/screenshot pengumuman lelang; Gemini 3.5 Flash-Lite mengekstrak metadata dan menilai kondisi fasad dalam satu panggilan terstruktur.
- Hasil ekstraksi otomatis mengisi field Streamlit. Data yang tidak ditemukan tetap kosong; pengguna memeriksa dan mengoreksi sebelum analisis.
- Form survei, status hunian, biaya dan waktu penguasaan, unggahan foto survei, dan risk register terpandu dengan preset risiko serta mitigasi yang dapat diedit.
- Draft RAB renovasi per pekerjaan dibuat dengan satu klik Gemini berdasarkan screenshot/PDF pengumuman, maksimal lima foto survei, deskripsi kondisi terkini dan data luas/lokasi. Harga satuan konservatif diisi sebagai estimasi indikatif, tetap dapat diedit dan wajib disetujui pengguna.
- Comparable pasar: tempel narasi beberapa listing (judul bernomor + bullet) lalu klik **Parse narasi dengan Gemini AI**. AI mengelompokkan setiap properti menjadi satu baris tabel terstruktur; CSV/TSV dan `st.data_editor` tetap tersedia sebagai alternatif. Listing divalidasi, dideduplikasi, diberi bobot kesetaraan/kebaruan, lalu dihitung menjadi conservative/base/optimistic ARV.
- Data comparable yang tidak disebutkan (misalnya LB, kondisi, akses, URL langsung, tanggal publikasi) tetap kosong dan menurunkan confidence; tidak diisi tebakan. Nama portal/sumber yang disebut pengguna disimpan sebagai provenance. Untuk GO final, lima comparable harus memiliki URL listing langsung dan tanggal ditemukan; portal name saja hanya cukup untuk valuasi indikatif.
- Analisis parsial tetap dapat dijalankan dengan data KPKNL seadanya. Sistem menghitung biaya yang sudah bisa dihitung; bila ARV belum tersedia, profit/ROI dibiarkan null dan status HOLD. Bila data pasar yang tersedia sudah menunjukkan ceiling bid di bawah limit, sistem dapat menampilkan DO NOT BID/Walk Away meski belum memenuhi gate GO.
- Financial engine Python: bea lelang, BPHTB, PNBP/BPN/roya/admin, penguasaan, renovasi, contingency, holding, biaya penjualan, profit, ROI proyek dan annualized ROI.
- Tangga bidding: limit, target ROI 35%, maximum bid ROI 25%, dan walk-away.
- Investor cashflow: real cash diinput user, outflow mendatang hanya mengurangi kapasitas bila dikonfirmasi user, cadangan likuiditas 10–20%.
- Simpan semua keputusan (GO, CONDITIONAL GO, HOLD, DO NOT BID) sebagai opportunity dan snapshot analisis.
- Lifecycle aset WON/ACTIVE/SOLD, milestones, biaya aktual, closing, dan track record.
- Google Sheets CRUD dengan normalisasi seluruh sel (NaN/Inf/pd.NA/NaT menjadi kosong/null), cache pembacaan 300 detik, manual refresh, batch append dan retry/backoff untuk error sementara.
- Gemini schema menggunakan model Pydantic dengan properti tetap (tidak memakai dynamic dictionary `additionalProperties`) agar kompatibel dengan Gemini Developer API.
- Optional Google Drive archive untuk dokumen dan foto.

## Struktur proyek

```text
property-flipper-management-system/
├── app.py
├── config.py
├── core/
│   ├── calculator.py
│   ├── decision_engine.py
│   ├── lifecycle.py
│   ├── liquidity.py
│   ├── market_engine.py
│   ├── maximum_bid.py
│   ├── risk_engine.py
│   ├── underwriting.py
│   └── utils.py
├── services/
│   ├── comparable_importer.py
│   └── gemini_parser.py
├── storage/
│   ├── drive_storage.py
│   └── gsheets_db.py
├── reports/report_builder.py
├── templates/property-flipper-gsheets-template.xlsx
├── tests/
├── requirements.txt
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

## A. Menjalankan di Windows

Disarankan Python 3.11 atau 3.12.

1. Ekstrak ZIP ke folder lokal.
2. Buka PowerShell di folder proyek.
3. Buat virtual environment dan install dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Salin `.streamlit/secrets.toml.example` menjadi `.streamlit/secrets.toml`.
5. Isi konfigurasi `APP_PASSWORD`, Gemini, Google Sheets, dan service account seperti bagian berikut.
6. Jalankan:

```powershell
streamlit run app.py
```

Jika Google Sheets belum dikonfigurasi, aplikasi masuk mode sesi sementara. Data lokal tidak dijamin tersimpan setelah sesi/browser/app berakhir. Untuk penggunaan nyata, konfigurasikan Google Sheets.

## B. Menyiapkan Google Sheets

1. Buat atau pilih Google Cloud project.
2. Aktifkan **Google Sheets API**. Aktifkan **Google Drive API** hanya jika ingin arsip dokumen/foto ke Drive.
3. Buat Service Account di Google Cloud Console → IAM & Admin → Service Accounts.
4. Buat JSON key untuk service account. Simpan file JSON secara aman; jangan commit ke GitHub.
5. Buat Google Spreadsheet kosong atau impor `templates/property-flipper-gsheets-template.xlsx` ke Google Sheets.
6. Salin Spreadsheet ID dari URL. Contoh URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`.
7. Bagikan spreadsheet kepada `client_email` milik Service Account dengan akses **Editor**.
8. Jika memakai Google Drive archive, buat folder Drive, bagikan folder ke email Service Account sebagai Editor, lalu isi `DRIVE_FOLDER_ID`.
9. Isi `SPREADSHEET_ID` dan object `google_service_account` di Streamlit Secrets.

Saat aplikasi pertama kali terhubung, `gsheets_db.py` akan membuat tab yang belum ada dan menyiapkan header. Jika memakai template, nama tab dan urutan header jangan diubah.

### Batas Google Sheets API

Aplikasi memakai cache 300 detik, tombol Refresh Data, batch append untuk beberapa baris comparable/risk, dan exponential backoff pada 429/5xx. Batas standar Google Sheets API adalah 300 read/write request per menit per project dan 60 per menit per user per project. Batch request dihitung satu request. Ini bukan izin untuk membuat polling agresif; pertahankan manual refresh dan hindari refresh berulang.

## C. Menyiapkan Gemini API

1. Buka Google AI Studio: https://aistudio.google.com/apikey
2. Buat API key untuk Google Cloud project yang digunakan.
3. Masukkan API key di `GEMINI_API_KEY` pada Secrets.
4. Gunakan model default `gemini-3.5-flash-lite`.

Versi V1 sengaja menggunakan satu model saja tanpa fallback otomatis agar konsumsi kuota dapat dikendalikan. Model hanya dipanggil saat tombol Parse, Review Investasi atau Review Portfolio ditekan. Ekstraksi dokumen disimpan berdasarkan hash di tab DOCUMENTS agar file identik dapat memakai cache database setelah analisis disimpan.

Penanganan error:
- 429: berhenti tanpa retry otomatis; periksa RPM/TPM/RPD di AI Studio.
- 503/500/502/504: retry terbatas dengan jeda meningkat, lalu tampilkan error.
- Tidak ada Google Search grounding otomatis pada konfigurasi Free Tier V1. Comparable dimasukkan manual oleh pengguna.

**Privasi:** jangan unggah NIK, nomor rekening, tanda tangan, nomor telepon pribadi atau data sensitif debitur yang tidak diperlukan. Free Tier Google AI Studio dapat memiliki ketentuan penggunaan data untuk peningkatan produk; periksa ketentuan terbaru sebelum mengirim dokumen sensitif.

## D. Streamlit Community Cloud dan GitHub

1. Buat repository GitHub (disarankan private).
2. Upload seluruh isi folder proyek, termasuk folder `.streamlit` tetapi **jangan** mengunggah `secrets.toml` yang asli. File `.gitignore` sudah mengecualikannya.
3. Buka https://share.streamlit.io/ dan masuk dengan GitHub.
4. Pilih **Create app**.
5. Pilih repository, branch `main`, dan main file path `app.py`.
6. Deploy.
7. Buka **App settings → Secrets**, lalu tempel isi secrets TOML.
8. Reboot aplikasi setelah mengubah secrets atau dependencies.

`APP_PASSWORD` wajib diisi. Aplikasi akan mengunci akses bila password belum diatur. Gunakan password kuat dan jangan membagikannya.

## E. Contoh Streamlit Secrets

Lihat `.streamlit/secrets.toml.example`. Bentuknya:

```toml
APP_PASSWORD = "GANTI_PASSWORD_KUAT"
GEMINI_API_KEY = "API_KEY_GOOGLE_AI_STUDIO"
GEMINI_MODEL = "gemini-3.5-flash-lite"
SPREADSHEET_ID = "ID_GOOGLE_SPREADSHEET"
DRIVE_FOLDER_ID = "ID_FOLDER_DRIVE_OPSIONAL"

[google_service_account]
type = "service_account"
project_id = "PROJECT_ID"
private_key_id = "PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "SERVICE_ACCOUNT_EMAIL"
client_id = "CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "URL_CERTIFICATE"
```

Jangan pernah menaruh API key/private key pada `app.py`, GitHub, screenshot atau laporan yang dibagikan.

## F. Cara menggunakan aplikasi

1. Isi **Investor Cashflow** dengan real cash aktual, persentase cadangan 10–20%, dan kemungkinan outflow mendatang yang memang Anda perkirakan. Hanya outflow yang dikonfirmasi yang mengurangi kas siap investasi.
2. Buka **New Auction Analysis**, buat objek baru, upload pengumuman KPKNL dan klik **Parse dengan Gemini AI**. Periksa seluruh field hasil parsing; nilai kosong harus diisi hanya bila Anda mempunyai sumber.
3. Lengkapi survei, status okupansi, biaya/timing penguasaan, risk register, legal verification dan foto survei.
4. Paste narasi minimal lima listing terbaru, satu listing per judul bernomor beserta bullet detailnya, lalu klik **Parse narasi dengan Gemini AI**. Periksa tabel hasilnya. AI tidak membuat URL atau tanggal publikasi yang tidak ada. Sumber portal (misalnya Rumah123/Pinhome) dapat dipakai sebagai provenance awal; tambahkan URL langsung dan tanggal iklan bila tersedia. CSV/TSV terstruktur dan editor manual juga didukung. Listing dengan LB/kondisi/akses tidak tercantum tetap dapat dipakai sebagai indikasi dengan penalti confidence; properti hitung tanah dapat tidak memiliki LB.
5. Isi RAB, durasi, holding, biaya lain, dan pastikan checkbox estimasi biaya telah ditinjau.
6. Klik **ANALISIS SEKARANG**. Hasil Python menampilkan ARV, modal, profit, ROI, tier bidding dan blockers.
7. Klik **SIMPAN / UPDATE ANALISIS KE DATABASE**. Semua status tersimpan, bukan hanya GO.
8. Jika menang lelang, buka **Database & History**, ubah lifecycle menjadi WON, dan isi harga menang. Aset akan muncul di **Active Properties**.
9. Catat pengeluaran aktual, milestone, tanggal, progres dan bukti. Tandai SOLD setelah harga closing dan seluruh biaya aktual sudah dicatat.
10. Buka **Closed Projects & Track Record** untuk melihat profit/ROI aktual dan durasi.

## G. Kebijakan perhitungan yang ditanam pada V1

- Minimum ROI proyek: 25% untuk keseluruhan holding period; bukan annualized.
- Target ROI bidding tengah: 35%.
- Conservative ARV menjadi dasar utama maximum bid.
- Asking aktif dan marked-sold yang belum terverifikasi mendapat negotiation discount; transaksi terverifikasi tidak.
- Quick-sale discount default 5% dari base ARV.
- Bea lelang pembeli default 2% sebagai asumsi awal untuk lelang eksekusi yang sesuai; harus diverifikasi per jenis lelang.
- BPHTB default 5%; basis dan NPOPTKP mengikuti konfigurasi wilayah/eligibilitas dan wajib diverifikasi. NPOPTKP tidak digunakan bila pengguna belum mengonfirmasi syarat perolehan.
- PNBP/BPN 2,5 juta + roya 1 juta + administrasi lain 4 juta sebagai default estimasi yang dapat diubah. Jasa notaris/PPAT akuisisi default 0 karena pengguna mengurus BPN sendiri.
- Selling default: PPh Final 2,5%, agen 2,5%, porsi AJB/PPAT penjual 1%, misc 5 juta; semua dapat diubah dan harus diverifikasi terhadap transaksi aktual.
- Risk reserve meningkatkan cash requirement, bukan biaya profit sampai risiko benar-benar terjadi.
- Deposit adalah kebutuhan likuiditas pra-lelang dan dikreditkan terhadap pelunasan bila aturan lot menyatakan demikian; jangan mencatatnya dua kali dalam biaya aktual.
- Max bid dicari dengan numerical search dan pembulatan increment. Walk-away dimulai satu increment di atas maximum bid.

Lihat `docs/CALCULATION_RULES.md` untuk uraian formula, `docs/DATA_DICTIONARY.md` untuk struktur database, `docs/USER_GUIDE.md` untuk alur penggunaan, `docs/COMPARABLE_AI_PARSER.md` untuk cara memasukkan narasi listing, dan `docs/DEPLOYMENT_SMOKE_TEST.md` untuk pengujian deployment. Riwayat perubahan ada di `CHANGELOG.md`.

## H. Pengujian

Jalankan:

```powershell
pytest -q
python -m compileall -q .
```

Suite pengujian V1.0.3 mencakup 49 unit test untuk kalkulasi BPHTB/biaya penjualan/BPN, ROI, maximum bid, cash reserve, lifecycle closing, validasi comparable, risk register, JSON sanitization untuk Google Sheets, schema Gemini RAB dan pemetaan item RAB. Ikuti `docs/DEPLOYMENT_SMOKE_TEST.md` untuk verifikasi integrasi akun setelah deploy.

## I. Catatan V1.0.4 — parser comparable

- Heading `**1. [Nama listing](URL)**` dan `**2. Nama listing**` kini dikenali sebagai blok terpisah.
- Satu listing dapat memiliki banyak bullet; bullet tidak dipecah menjadi baris properti.
- Schema Gemini menggunakan key JSON ringkas dan `max_output_tokens=4096`; input lebih dari lima listing diproses dalam batch maksimum empat.
- URL portal diambil dari teks asli per blok. URL Google Knowledge Panel `kgmid` tidak dianggap sebagai URL listing. URL portal kategori/venue tetap perlu diperiksa apakah mengarah ke iklan individual.
- Jika Gemini tetap berhenti dengan `MAX_TOKENS` atau JSON tidak lengkap, parser menolak keseluruhan hasil dan tidak mengisi tabel dengan data parsial.

## J. Batasan yang diketahui

- Belum ada scraping otomatis situs KPKNL.
- V1 tidak mengandalkan automatic web search untuk comparable. User mencari listing dan menempelkan narasi; Gemini hanya menstrukturkan teks yang diberikan, bukan memverifikasi bahwa listing masih aktif atau benar.
- Integrasi Google Sheets/Gemini/Drive harus diuji dengan akun dan credentials milik Anda saat deployment. Unit tests lokal tidak membuktikan bahwa cloud credentials sudah benar.
- Jika Google Sheets tidak dikonfigurasi, mode lokal hanya session memory dan bukan arsip permanen.
- Foto/dokumen binary diarsipkan permanen hanya bila `DRIVE_FOLDER_ID` dan akses Drive dikonfigurasi. Tanpa itu, aplikasi mencatat metadata dan hash serta memberi peringatan.
- Estimasi pajak, lelang, legal, BPN, dan waktu pengosongan bukan pendapat hukum atau kepastian biaya. Verifikasi pengumuman, peraturan terkini, KPKNL, BPN dan ahli terkait sebelum transaksi.

## Lisensi dan tanggung jawab

Aplikasi ini adalah alat bantu internal untuk underwriting. Keputusan pembelian tetap tanggung jawab investor. Jangan memperlakukan hasil AI sebagai appraisal, pendapat hukum, atau jaminan profit.
