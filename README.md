# Auction Flip Decision System v2.1

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

## Fitur v2.1

- Form data pengumuman lelang: KPKNL, kode lot, penjual, jenis lelang, jadwal, batas setor jaminan/pelunasan, limit, deposit, link, objek, sertifikat, LT/LB, NJOP.
- **Auto-fill dokumen:** setelah PDF/gambar diunggah dan tombol ekstraksi Gemini ditekan, hasil JSON langsung dipetakan ke widget form. Tidak perlu copy-paste per kolom. Field yang tidak ditemukan tetap kosong; nilai manual yang sudah diisi dipertahankan kecuali user mengaktifkan opsi timpa.
- Field angka dokumen (limit, jaminan, LT/LB, NJOP, kamar) dapat benar-benar kosong sampai ditemukan/diisi; dropdown jenis lelang/sertifikat/properti diawali pilihan kosong agar default tidak dianggap fakta.
- Form survei: status penghuni, verifikasi okupansi, legal, kondisi interior/eksterior, akses, banjir, struktur, atap, rembes, utilitas, catatan dan link foto.
- Comparable editor: harga penawaran vs transaksi, LT/LB, lokasi, kondisi, sertifikat, tanggal, URL dan catatan.
- Biaya dan risiko: bea lelang, BPHTB, PPN jika berlaku, legalitas, renovasi, tunggakan, kerahiman/pengosongan, holding, contingency, biaya jual, ROI minimum, profit minimum dan holding maksimum.
- Bid ladder tiga zona: HIJAU (sangat menarik, ROI konservatif minimum +10 poin persentase), KUNING (masih memenuhi ROI minimum hingga ceiling disiplin), MERAH (WAJIB STOP mulai increment setelah ceiling; jika limit sendiri gagal maka STOP pada limit). Kelipatan bid ikut diekstrak bila tercantum. Jika belum dikonfirmasi, tangga hanya indikatif dengan fallback Rp1 juta dan keputusan HOLD. Referensi base-case ditampilkan terpisah dan bukan izin menaikkan bid.
- Keputusan GO / CONDITIONAL / HOLD / NO-GO dengan hard blockers.
- Google Sheets sebagai database utama; aplikasi membuat tab database otomatis jika spreadsheet kosong. Adapter memakai batch reads/writes, cache baca 20 detik, refresh paksa, dan exponential backoff untuk 429/5xx.
- Perbandingan multiobjek dan review Gemini untuk maksimal 8 objek sekaligus.
- Cashflow investor: saldo baseline + transaksi masuk/keluar setelah tanggal baseline; komitmen dan cadangan dikurangkan; piutang tidak dianggap kas.
- Koreksi manual di sheet sumber lalu tombol re-analysis untuk menghitung ulang data yang telah dikoreksi.
- Snapshot historis setiap analisis tidak ditimpa.

## Jalankan lokal (Windows)

1. Install Python 3.11 atau lebih baru. Dependensi menetapkan `streamlit>=1.44` karena form angka kosong memakai `st.number_input(value=None)`.
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
4. Di **Analisis Baru**, unggah PDF/gambar pengumuman. Tekan **Ekstrak & isi form otomatis dengan Gemini**; field yang berhasil dikenali akan terisi otomatis. Field yang tidak tercantum tetap kosong. Cocokkan hasil dengan dokumen asli.
5. Lengkapi bagian survei lapangan, comparable, parameter biaya, pajak, skenario penguasaan, dan target ROI.
6. Tekan **ANALISIS SEKARANG**. Tahap ini hanya memakai Python dan tidak memanggil Gemini.
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

## Google Sheets API quota dan optimasi

Google Sheets API standar membatasi 300 read request/menit/project dan 300 write request/menit/project; batas per user per project adalah 60 read dan 60 write request/menit. Google menghitung satu batch request sebagai satu request, walaupun batch berisi beberapa rentang. Selama batas per menit dipatuhi, dokumentasi menyebut tidak ada batas total request harian.

Implementasi repository pada build ini:

- `values_batch_get` membaca banyak tab sekaligus.
- `values_batch_update` menulis beberapa range/tab sekaligus.
- Cache read 20 detik per proses; tombol **Refresh data GSheets** menghapus cache dan membaca ulang.
- Save analysis normalnya menggunakan satu batch read dan satu batch write (bukan request terpisah untuk setiap sel).
- Error 429/500/502/503/504 memakai retry dengan exponential backoff terbatas dan menghormati `Retry-After` bila diberikan.
- Tidak ada polling otomatis berkala. Data dibaca ketika aplikasi berjalan atau saat user meminta refresh/analisis.

Untuk satu investor yang memasukkan data manual, desain ini seharusnya jauh dari 60 request/menit per user, kecuali ada loop, banyak pengguna serentak, atau request lain dari project yang sama. Batas resmi dapat berubah; cek dokumentasi Google sebelum memperbesar beban.

**Catatan biaya terbaru (12 November 2026):** dokumentasi Google menyebut penggunaan standar Sheets API tidak dikenakan biaya tambahan, tetapi juga menyatakan pelampauan kuota request direncanakan dapat dikenakan biaya ke akun billing Google Cloud pada akhir 2026. Karena itu jangan sengaja melewati batas; batching/cache/backoff di atas ditujukan untuk tetap di bawah kuota. Service account dihitung sebagai satu akun pengguna untuk batas per-user. <https://developers.google.com/workspace/sheets/api/limits>

## Gemini Free & Error 429

- Default model adalah `gemini-3.5-flash-lite`.
- Aplikasi tidak memanggil Gemini setiap kali form dianalisis.
- AI hanya dipanggil atas tindakan user: ekstraksi dokumen, memo, dan review shortlist.
- Review shortlist memakai ringkasan paling banyak 8 objek, satu panggilan, output pendek dan cache sesi.
- Error 429 tidak diulang otomatis. Periksa RPM (requests/minute), TPM (tokens/minute), dan RPD (requests/day) di Google AI Studio → Rate limits. Batas diterapkan pada project, bukan masing-masing API key.
- Saat 429, Python ranking tetap tersedia.
- Google Search grounding tidak diaktifkan di build ini. `gemini-3.5-flash-lite` mencantumkan kemampuan Search grounding, tetapi akses/kuotanya mengikuti tier dan project; error 429 yang dialami user membuat fitur riset listing otomatis sengaja ditunda agar tidak menghabiskan kuota. Comparable dimasukkan manual beserta URL dan tanggal verifikasi. Aktifkan hanya setelah entitlement dan batas pemakaian project benar-benar dikonfirmasi di AI Studio.
- Untuk data identitas sensitif, jangan kirim dokumen yang tidak perlu ke Gemini. Ketentuan Free tier menyatakan konten dapat digunakan untuk peningkatan produk Google.

## File `.py` yang mengatur tiap fungsi

| File | Bagian/fungsi yang diubah atau menjadi titik pengaturan |
|---|---|
| `app.py` | Blok upload dokumen dan tombol ekstraksi (cari `Ekstrak & isi form otomatis`); widget form menggunakan `form_*`; tampilan 3 zona bidding di bagian hasil analisis; tabel `Bandingkan & Ranking`; penjelasan kuota pada tab panduan. |
| `services/gemini_client.py` | `extract_document_with_gemini()` untuk prompt/schema ekstraksi; `DEFAULT_MODEL`; `classify_gemini_error()` untuk 429; fungsi memo/review AI. |
| `services/extraction_mapper.py` | `FIELD_MAP` untuk nama field/alias; `_choice()` untuk enum; `_number()` dan `_as_date()` untuk konversi nilai; `apply_extraction_to_form()` mengisi session state form. |
| `storage/gsheets_repository.py` | `CACHE_TTL_SECONDS`; `_raw_values_many()` untuk batch read dan cache; `_batch_write()` untuk batch write; `_retry_google_call()` untuk 429/5xx; `save_analysis()` untuk penyimpanan snapshot. |
| `core/maximum_bid.py` | `find_maximum_bid()` menguji batas tertinggi yang lolos ROI/profit/holding/kas. |
| `core/analysis_engine.py` | `run_property_analysis()` membentuk `bidding_levels`: zona hijau, ceiling disiplin, first stop increment, dan referensi base. Ubah `attractive_buffer` untuk mengatur jarak ROI zona hijau (+10 poin secara default). |
| `core/portfolio_engine.py` | `suitability_score()` dan `rank_saved_objects()` untuk indeks kelayakan/ranking dinamis memakai cashflow terkini. |
| `core/sheets_rebuild.py` | Mengubah baris GSheets yang dikoreksi menjadi input untuk analisis ulang. |

Setelah mengubah file, jalankan `pytest -q` dari root proyek. Untuk menguji mapper khusus: `pytest -q tests/test_extraction_mapper.py`.

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
