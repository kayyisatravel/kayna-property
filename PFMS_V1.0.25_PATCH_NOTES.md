# PFMS V1.0.25 — Automatic Portfolio Ranking & Recommendation Score

## Scope
Mengubah halaman **Bandingkan Peluang Investasi** dari pemilihan objek secara manual menjadi ranking otomatis semua prospek yang masih aktif untuk ditelaah.

## Perubahan
1. Mengambil seluruh data `PROPERTIES` yang lifecycle-nya belum `WON`, `ACTIVE`, atau `SOLD`.
2. Mengambil analisis terakhir per `property_id` dari `ANALYSIS_HISTORY`.
3. Menjalankan ulang underwriting Python berdasarkan snapshot input historis (data properti, survei, legalitas, biaya, pembanding, dan risiko), sambil memperbarui posisi kas investor terkini.
4. Memasukkan status `GO` dan `CONDITIONAL GO` dengan tanggal lelang hari ini/masa depan ke shortlist eligible.
5. Menampilkan `HOLD`, `DO NOT BID`, tanggal lelang yang lewat, tanggal yang tidak tersedia, dan prospek tanpa analisis tersimpan secara terpisah dengan alasan tindak lanjut.
6. Menambahkan ranking Recommendation Score 0–100, rincian komponen skor, ringkasan kandidat prioritas, dan opsi review shortlist dengan Gemini.
7. Ranking di-cache berdasarkan perubahan prospek, analisis terakhir, aturan, dan posisi likuiditas. Tombol **Perbarui ranking sekarang** memaksa perhitungan ulang.

## Formula Recommendation Score

| Komponen | Bobot | Perhitungan ringkas |
|---|---:|---|
| ROI pada nilai limit | 25 | Dibandingkan dengan ROI minimum dan target yang tersimpan di Settings & Rules. Pada ambang minimum mendapat 50% bobot komponen; bobot penuh pada/di atas target. |
| Profit bersih pada limit | 15 | Skala terhadap profit bersih minimum; bobot penuh pada 2× ambang minimum. |
| Kecukupan kas | 20 | Kebutuhan kas + cadangan dibanding kas siap investasi. Kas harus terkonfirmasi; bobot penuh pada coverage 125%. |
| Status underwriting | 20 | GO = 20; CONDITIONAL GO = 12. Status lain tidak masuk shortlist. |
| Kualitas bukti pasar | 10 | Menggunakan confidence dari market engine (fallback pada jumlah pembanding ber-grade GO jika confidence tidak tersedia). |
| Durasi proyek | 10 | Bobot penuh pada/di bawah target holding; turun linear hingga nol pada batas maksimum. |

Recommendation Score adalah **alat prioritas telaah**, bukan probabilitas memperoleh keuntungan, bukan appraisal, dan bukan instruksi otomatis untuk bidding. Status underwriting tetap menjadi hard gate.

## Tidak diubah
- Tidak ada perubahan skema Google Sheets.
- Tidak ada perubahan modul underwriting, market engine, liquidity, atau keputusan GO/HOLD.
- Tidak ada perubahan alur empat langkah Analisis Objek Lelang.
- Tidak ada perubahan prompt Gemini untuk underwriting.
- Tidak mengubah `.streamlit/secrets.toml`, credentials, atau data pengguna.
- V1.0.26 lifecycle lelang dan V1.0.27 deteksi properti sama/Lot Code berbeda **belum diimplementasikan** dalam patch ini.

## Validasi lokal
- `python -m py_compile app.py` — lulus.
- AST parse — lulus.
- Targeted helper tests untuk parsing tanggal, skor GO/CONDITIONAL GO, dan kas belum terkonfirmasi — lulus.
- ZIP integrity — lulus.
- Belum dilakukan live integration test terhadap Streamlit Cloud, Google Sheets, atau Gemini karena lingkungan dan kredensial deployment tidak tersedia di sesi ini.

## Penerapan
1. Backup `app.py` yang sedang aktif di GitHub.
2. Ekstrak patch ZIP.
3. Ganti `app.py` pada repository dengan file di patch.
4. Jangan mengganti atau mengunggah `.streamlit/secrets.toml`.
5. Deploy ulang dan uji halaman **Bandingkan Peluang Investasi**.

## Skenario uji setelah deploy
1. Pastikan daftar otomatis memuat semua prospek yang memiliki analisis terakhir.
2. Pastikan GO dan CONDITIONAL GO dengan tanggal lelang belum lewat masuk shortlist.
3. Pastikan CONDITIONAL GO diberi keterangan syarat sebelum bidding.
4. Pastikan HOLD, DO NOT BID, tanggal lewat, tanggal kosong, dan belum ada analisis berada di tabel tindak lanjut.
5. Ubah posisi kas siap investasi/konfirmasi kas; pastikan ranking memperbarui kecukupan kas dan score.
6. Klik **Perbarui ranking sekarang**; pastikan perhitungan ulang berjalan tanpa menghapus snapshot analisis.
7. Pastikan fungsi Review shortlist dengan Gemini tetap opsional dan hanya menerima kandidat eligible.
