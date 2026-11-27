# PFMS V1.0.22 — Patch Notes

## Kebijakan underwriting Kayna Property

- Default Minimum Project ROI all-in: **20%**.
- Default Target Project ROI all-in: **30%**. Tidak ada batas maksimum ROI.
- Minimum profit bersih: **Rp50.000.000**, setelah biaya akuisisi, renovasi, holding, dan biaya penjualan.
- Target holding period: **90 hari** dari komitmen modal/akuisisi hingga closing.
- Maximum holding period: **180 hari**.

## Perubahan perhitungan dan keputusan

- Maximum Bid wajib memenuhi ROI minimum, profit bersih minimum, dan durasi maksimum secara bersamaan.
- Durasi yang tidak tersedia tidak dianggap nol hari; status menjadi HOLD sampai asumsi waktu dilengkapi.
- Proyek 91–180 hari dapat memenuhi gate minimum tetapi mendapat peringatan karena melewati target ideal. Proyek >180 hari tidak lolos underwriting jika data durasinya dapat dihitung.
- ROI proyek menggunakan basis all-in termasuk biaya transaksi penjualan. ROI atas modal pra-penjualan tetap ditampilkan sebagai metrik diagnostik.
- Ditambahkan ROI tahunan ekuivalen estimasi, dibedakan dari XIRR aktual.
- XIRR aktual hanya tersedia bila seluruh arus kas memiliki tanggal, tanggal closing tersedia, dan biaya penjualan closing dapat direkonsiliasi dengan ledger.
- Hard-cap Maximum Bid menggunakan Quick Sale / Conservative ARV. Base dan Upper ARV tetap sebagai analisis sensitivitas.

## Perbaikan penilaian pasar

- Secondary/resale menjadi pool utama ARV ketika bukti sekunder tersedia.
- Listing primary/developer dipertahankan sebagai konteks kompetisi, tidak dicampur ke pool ARV secondary.
- Nilai promosi hanya mengurangi harga efektif apabila nominal manfaat tunainya diverifikasi.
- `underlying_property_id` digunakan untuk mencegah satu rumah yang diiklankan lintas portal dihitung sebagai beberapa comparable.
- Over-kredit tetap dipisahkan dari harga transaksi tunai sampai saldo kewajiban dan biaya take-over diverifikasi.

## UI dan data

- Penjelasan status bidding pada nilai limit memeriksa ROI, profit, durasi, dan konfirmasi kas.
- Pengaturan mencegah Target ROI lebih rendah daripada Minimum ROI.
- Konfigurasi lama 25% / 35% yang merupakan default V1.0.21 dimigrasikan menjadi 20% / 30%; nilai khusus pengguna selain pasangan default tersebut dipertahankan.
- Tidak ada tab atau header Google Sheets lama yang dihapus atau diubah secara destruktif.

## Pengujian

- Regression suite: **218 passed**.
- Python compile check: passed.
- Full source dan upgrade patch diuji terpisah setelah pengemasan.
- Live Google Sheets, Gemini API, dan Streamlit Cloud belum diuji dengan kredensial pengguna.
