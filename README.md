# Auction Flip Decision System v2

Aplikasi Streamlit untuk analisis investasi rumah lelang KPKNL. Desain alur utama:

**Input pengumuman KPKNL + survei lapangan → satu klik analisis Python → simpan snapshot ke Google Sheets → bandingkan shortlist → Gemini second opinion / HOLD ALL → cek kapasitas kas sebelum bidding.**

## Prinsip desain

1. **Sell first, buy second.** Harga keluar (exit) dianalisis sebelum menentukan batas bid.
2. **Python adalah sumber kebenaran angka.** Profit, ROI, total biaya, cash check, skenario penguasaan, maximum bid dan skor kelayakan dihitung deterministik.
3. **Gemini opsional.** Gemini hanya membantu ekstraksi dokumen, memo, dan review shortlist. Jika API 429, seluruh kalkulasi dan ranking dasar tetap bekerja.
4. **Persentase kelayakan bukan probabilitas.** Itu adalah indeks screening berbobot 0–100, bukan peluang pasti rumah laku/untung.
5. **Hard stop mengalahkan skor.** Identitas/legalitas, penguasaan, pajak, dana, atau pasar yang belum cukup jelas dapat menghasilkan HOLD walaupun indeks terlihat tinggi.
6. **Tidak ada asumsi tarif pajak yang disembunyikan.** Input biaya/pajak harus diverifikasi per lot, jenis transaksi, dan wilayah. PPN hanya diterapkan ketika user mengaktifkannya.
7. **Skenario pengosongan bersifat alternatif.** Biaya skenario kosong, kooperatif, sulit, dan eksekusi formal tidak dijumlahkan sebagai pengeluaran yang pasti terjadi bersamaan.
8. **Piutang bukan kas.** Piutang hanya ditampilkan, tidak dimasukkan sebagai dana siap bidding.

## Fitur v2

- Form data pengumuman lelang: KPKNL, kode lot, penjual, jenis lelang, jadwal, batas setor jaminan/pelunasan, limit, deposit, link, objek, sertifikat, LT/LB, NJOP.
- Form survei: status penghuni, verifikasi okupansi, legal, kondisi interior/eksterior, akses, banjir, struktur, atap, rembes, utilitas, catatan dan link foto.
- Comparable editor: harga penawaran vs transaksi, LT/LB, lokasi, kondisi, sertifikat, tanggal, URL dan catatan.
- Biaya dan risiko: bea lelang, BPHTB, PPN jika berlaku, legalitas, renovasi, tunggakan, kerahiman/pengosongan, holding, contingency, biaya jual, ROI minimum, profit minimum dan holding maksimum.
- Maximum bid: recommended ceiling dari exit konservatif; absolute maximum dari exit base; ditambah hard ceiling manual opsional.
- Keputusan GO / CONDITIONAL / HOLD / NO-GO dengan hard blockers.
- Google Sheets sebagai database utama; aplikasi membuat tab database otomatis jika spreadsheet kosong.
- Perbandingan multiobjek dan review Gemini untuk maksimal 8 objek sekaligus.
- Cashflow investor: saldo baseline + transaksi masuk/keluar setelah tanggal baseline; komitmen dan cadangan dikurangkan; piutang tidak dianggap kas.
- Koreksi manual di sheet sumber lalu tombol re-analysis untuk menghitung ulang data yang telah dikoreksi.
- Snapshot historis setiap analisis tidak ditimpa.

## Jalankan lokal (Windows)

1. Install Python 3.11 atau lebih baru.
2. Extract ZIP.
3. Buka folder `auction-flip-analyzer-v2` di VS Code atau terminal.
4. Buat virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. Copy `.streamlit/secrets.toml.example` menjadi `.streamlit/secrets.toml`, lalu isi konfigurasi. Jangan pernah commit file `secrets.toml`.
6. Jalankan:

   ```powershell
   streamlit run app.py
   ```

Aplikasi dapat dibuka tanpa Gemini. Untuk penyimpanan permanen, konfigurasi Google Sheets.

## Setup Google Sheets (database utama)

### A. Buat spreadsheet

1. Buat Google Sheet baru dari akun Google Anda.
2. Copy Spreadsheet ID dari URL `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`.
3. Tidak perlu membuat tab manual. Aplikasi akan membuat dan mengisi header tab saat pertama tersambung.

### B. Buat Service Account

1. Buka Google Cloud Console dan pilih/buat project.
2. Aktifkan **Google Sheets API**.
3. Buat Service Account. Buat JSON key untuk service account tersebut.
4. Salin field JSON key ke section `[google_service_account]` pada Streamlit Secrets.
5. Bagikan spreadsheet kepada `client_email` Service Account dengan hak **Editor** karena aplikasi perlu menulis data.
6. Jangan mengaktifkan public link sharing untuk spreadsheet yang berisi data investasi.

### C. Secrets

Di Streamlit Community Cloud pilih app → **Settings → Secrets**, lalu isi bentuk TOML berikut. Masukkan seluruh field dari service-account JSON, bukan hanya contoh field di bawah.

```toml
APP_PASSWORD = "PASSWORD_KUAT"
SPREADSHEET_ID = "ID_SPREADSHEET"
GEMINI_API_KEY = "OPSIONAL"
GEMINI_MODEL = "gemini-3.5-flash-lite"

[google_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
ISI_PRIVATE_KEY_DENGAN_BARIS_ASLI
-----END PRIVATE KEY-----
"""
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

Untuk `private_key`, tempel isi key di antara tiga tanda kutip seperti contoh (baris asli/newline). Kode juga menormalisasi format escaped newline dari JSON jika diperlukan. Jangan menaruh key di source code atau GitHub.

### D. Struktur tab dibuat otomatis

| Tab | Fungsi |
|---|---|
| `MASTER_OBJEK` | Data pengumuman dan identitas tiap objek |
| `SURVEI` | Fakta survei lapangan |
| `BIAYA_RISIKO` | Parameter pajak, biaya, target ROI, dan skor risiko |
| `COMPARABLES` | Satu baris per pembanding; `active=TRUE` dipakai pada re-analysis |
| `SKENARIO_PENGUASAAN` | Skenario kosong/kooperatif/sulit/eksekusi formal |
| `INVESTOR` | Saldo baseline dan cadangan investor |
| `CASHFLOW` | Ledger transaksi masuk/keluar |
| `ANALISIS` | Snapshot lengkap setiap analisis |
| `RIWAYAT` | Log aktivitas aplikasi |

### E. Koreksi spreadsheet

Anda boleh mengoreksi field langsung di `MASTER_OBJEK`, `SURVEI`, `BIAYA_RISIKO`, `COMPARABLES`, dan `SKENARIO_PENGUASAAN`. Pada tab **Bandingkan & Ranking**, pilih objek lalu tekan **Muat koreksi GSheets & hitung ulang**. Sistem akan membaca data aktif dari tab sumber dan menyimpan snapshot analisis baru.

Jangan mengubah nama atau urutan header. Jangan mengubah `object_id`. Untuk comparable/skenario yang tidak dipakai lagi, ubah kolom `active` menjadi `FALSE`.

## Deploy GitHub → Streamlit Community Cloud

1. Buat repository GitHub baru, misalnya `auction-flip-decision-system`.
2. Upload seluruh isi folder ini ke root repository (bukan folder bersarang).
3. Pastikan `app.py` berada di root repository dan `requirements.txt` ikut terunggah.
4. Buka https://share.streamlit.io/ → **Create app**.
5. Pilih repository, branch `main`, main file path `app.py`.
6. Setelah app dibuat, buka **Settings → Secrets** dan tempel konfigurasi TOML Google Sheets serta password; tambahkan Gemini API key bila ingin.
7. Reboot app.

## Penggunaan harian

1. Masuk ke **Cashflow Investor** dan simpan saldo baseline serta cadangan.
2. Catat setiap cash in/out sejak tanggal baseline. Saldo kas hidup = baseline + transaksi masuk − transaksi keluar.
3. Piutang yang belum cair dicatat hanya sebagai informasi, bukan kas bidding.
4. Di **Analisis Baru**, input data KPKNL dan survei, lalu isi comparable dan parameter biaya.
5. Tekan **ANALISIS SEKARANG**. Tahap ini hanya memakai Python dan tidak memanggil Gemini.
6. Periksa biaya, ROI, maximum bid, blockers dan warnings.
7. Tekan **Simpan hasil analisis ke GSheets**.
8. Ulangi untuk objek lain.
9. Di **Bandingkan & Ranking**, centang beberapa objek untuk shortlist. Ranking Python langsung tersedia dan setiap objek dihitung ulang memakai saldo kas, komitmen, serta cadangan investor terkini. Snapshot histori tidak diubah. Tekan **Review Gemini shortlist** hanya bila perlu second opinion.
10. AI boleh menyarankan satu objek atau HOLD_ALL. AI tidak dapat mengubah hitungan Python; hard-stop HOLD/NO-GO tidak dapat diangkat oleh AI.

## Logika scoring dan keputusan

### Indeks Kelayakan (%)

Indeks screening dihitung dari:

- Kinerja finansial: 30% (pencapaian ROI, profit minimum, holding period)
- Skor risiko tertimbang: 25% (likuiditas 25%, legalitas 20%, penguasaan 20%, fisik 15%, pendanaan 15%, lingkungan 5%)
- Kecukupan dana: 20%
- Confidence comparable: 15%
- Kelengkapan bukti: 10%

Hard blockers mendapat penalti tambahan dan tetap memaksa status HOLD sesuai decision engine. Angka ini tidak boleh disebut probabilitas sukses.

### Maximum bid

- Recommended ceiling: numerical search atas exit konservatif.
- Absolute maximum: numerical search atas exit base.
- Batas dibatasi hard ceiling manual bila diisi.
- Kandidat bid harus lolos seluruh target profit, ROI, profit/bulan, holding period dan kapasitas kas.

### Cashflow

`Kas siap proyek baru = saldo baseline + net transaksi setelah baseline − sisa komitmen proyek yang belum dibayar − cadangan rumah tangga − cadangan risiko wajib`.
Piutang tidak ditambahkan. Komitmen hanya mencakup kewajiban yang belum dibayar dan belum dicatat sebagai transaksi OUT. Deposit lelang adalah kebutuhan kas sebelum bidding, tetapi tidak ditambahkan sekali lagi ke total biaya akuisisi bila diperhitungkan sebagai bagian pembayaran harga.

## Gemini Free & Error 429

- Default model adalah `gemini-3.5-flash-lite`.
- Aplikasi tidak memanggil Gemini setiap kali form dianalisis.
- AI hanya dipanggil atas tindakan user: ekstraksi dokumen, memo, dan review shortlist.
- Review shortlist memakai ringkasan paling banyak 8 objek, satu panggilan, output pendek dan cache sesi.
- Error 429 tidak diulang otomatis. Periksa RPM (requests/minute), TPM (tokens/minute), dan RPD (requests/day) di Google AI Studio → Rate limits. Batas diterapkan pada project, bukan masing-masing API key.
- Saat 429, Python ranking tetap tersedia.
- Google Search grounding tidak diaktifkan. Free-tier model ini tidak menyediakan Search grounding pada tabel harga standar; listing harus dimasukkan manual atau diverifikasi dari sumber web secara terpisah.
- Untuk data identitas sensitif, jangan kirim dokumen yang tidak perlu ke Gemini. Ketentuan Free tier menyatakan konten dapat digunakan untuk peningkatan produk Google.

## Batasan MVP

- Tidak melakukan scraping otomatis `lelang.go.id` atau portal properti.
- Tidak tersambung ke rekening bank. Ledger transaksi bersifat manual.
- Harga listing bukan harga transaksi; sumber dan status wajib dicatat.
- AI tidak melakukan appraisal, legal opinion, tax opinion, atau jaminan keberhasilan investasi.
- Simpanan permanen menggunakan Google Sheets; tanpa kredensial, mode sesi hanya sementara.

## Pengujian

Dari root folder:

```powershell
pytest -q
python -m compileall .
```

Gunakan data historis TAS 3 M6/12 dan Graha Properindo untuk validasi silang sebelum menjadikan hasil aplikasi sebagai dasar bidding riil.
