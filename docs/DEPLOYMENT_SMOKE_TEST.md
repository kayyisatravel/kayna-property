# Deployment Smoke Test — wajib sebelum penggunaan nyata

## 1. Infrastruktur
- [ ] Buat private GitHub repository dan upload seluruh isi folder proyek.
- [ ] Pastikan `.streamlit/secrets.toml` lokal tidak ikut ter-upload.
- [ ] Buat Google Cloud project; aktifkan Google Sheets API.
- [ ] Buat Service Account dan bagikan spreadsheet ke `client_email` sebagai Editor.
- [ ] Impor `templates/property-flipper-gsheets-template.xlsx` ke Google Sheets.
- [ ] Set `APP_PASSWORD`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `SPREADSHEET_ID`, dan object `google_service_account` di Streamlit Secrets.
- [ ] Tambahkan `DRIVE_FOLDER_ID` hanya jika arsip file binary ke Drive diperlukan.
- [ ] Deploy `app.py` pada Streamlit Community Cloud.

## 2. Smoke test AI parser
- [ ] Upload satu pengumuman lelang yang sudah diketahui datanya.
- [ ] Klik Parse dengan Gemini AI.
- [ ] Cocokkan kode lot, lokasi, tanggal, limit, deposit, LT/LB, sertifikat dan kutipan evidence dengan sumber.
- [ ] Pastikan data tidak tersedia tetap kosong/null.
- [ ] Pastikan screenshot diproses dan PDF tetap dikirim sebagai PDF native.
- [ ] Klik parse ulang untuk file yang sama setelah disimpan; pastikan extraction cache digunakan.
- [ ] Pastikan error 429 tidak memicu retry berulang.

## 3. Smoke test underwriting
- [ ] Masukkan minimal lima comparable valid dengan URL dan tanggal.
- [ ] Masukkan comparable duplikat dan data yang kurang; pastikan sistem menandai invalid.
- [ ] Uji status Belum Survei; keputusan harus HOLD.
- [ ] Uji legal dispute; keputusan harus DO NOT BID.
- [ ] Uji max bid di bawah auction limit; keputusan harus DO NOT BID.
- [ ] Uji increment kosong; keputusan tidak boleh GO.
- [ ] Pastikan maximum bid memenuhi minimum ROI 25% pada conservative ARV.
- [ ] Pastikan target batas tengah mengikuti ROI 35%.

## 4. Smoke test cashflow
- [ ] Input real cash dan konfirmasi saldo.
- [ ] Input forecast outflow confirmed dan unconfirmed.
- [ ] Pastikan hanya outflow confirmed yang mengurangi kas tersedia.
- [ ] Ubah reserve 10%, 15%, dan 20%; pastikan perubahan memengaruhi kas siap investasi.
- [ ] Pastikan estimasi biaya proyek aktif tidak otomatis mengurangi kas kecuali pengguna memasukkannya sebagai outflow/komitmen.

## 5. Smoke test lifecycle
- [ ] Simpan objek HOLD dan pastikan tetap ada di Database & History.
- [ ] Simpan ulang analisis objek yang sama; pastikan analysis snapshot baru tercatat dengan `analysis_id` berbeda.
- [ ] Tandai satu objek sebagai WON dan masukkan harga menang.
- [ ] Pastikan objek masuk Active Properties.
- [ ] Tambahkan biaya aktual dan milestone.
- [ ] Tutup properti sebagai SOLD dengan harga closing dan biaya aktual lengkap.
- [ ] Pastikan properti masuk Closed Projects dan hitung profit/ROI aktual.
- [ ] Cocokkan Budget vs Actual dan audit HISTORY.

## 6. Benchmark TAS 3 M6/12
Gunakan hanya angka dan dokumen yang sudah diverifikasi. Jangan mengisi biaya legal/pajak atau harga closing yang belum diketahui dengan angka rekaan. Bandingkan hasil aplikasi dengan lembar perhitungan manual sebelum menjadikan aplikasi dasar keputusan bidding.
