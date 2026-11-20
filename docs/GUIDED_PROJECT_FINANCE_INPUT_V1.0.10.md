# Guided Project Finance Input — PFMS V1.0.10

## Prinsip UI
Dataframe pada halaman Properti Aktif hanya digunakan untuk membaca dan meninjau hasil. Pengguna memasukkan data melalui form satu transaksi/item pada satu waktu. Ini mengurangi kesalahan tanggal, kategori, penautan budget, serta ketidaksengajaan mengubah beberapa baris sekaligus.

## Realisasi pembayaran historis dan baru
Setiap transaksi wajib memiliki tanggal, kategori, subkategori, item/lingkup dan nominal positif. Penerima/vendor, metode pembayaran, URL bukti, dan catatan tambahan bersifat opsional. Tanggal memakai date picker.

Kategori disusun secara bertingkat: Pelunasan/akuisisi, Bea lelang, BPHTB, BPN/Legal, Penguasaan/Kerahiman, Renovasi, Holding, Marketing, Selling, dan Lainnya. Pilihan subkategori menyesuaikan kategori. Pilihan item/lingkup disesuaikan dengan subkategori; pilihan Lainnya membuka input teks.

Untuk pembayaran yang terkait dengan item budget, pilih item yang sesuai dan tentukan apakah pembayaran mengurangi komitmen belum dibayar, forecast tersisa, atau merupakan biaya di luar budget. Pengurangan dilakukan hanya jika pengguna memilih sumber yang sesuai.

## Budget dan outstanding
Budget baru juga memakai kategori, subkategori dan item/lingkup bertingkat. Pengguna mengisi budget total, committed unpaid, forecast remaining, vendor, serta due date opsional. Tanggal jatuh tempo menggunakan date picker.

Item lama dipilih dari daftar dan diubah melalui form terpisah; tabel tidak diedit langsung. Angka `budget_amount`, `committed_unpaid`, dan `forecast_remaining` harus tetap dipahami sebagai tiga konsep berbeda. Jangan memasukkan actual paid ke outstanding.

## Perubahan status hasil lelang
Untuk prospect yang dimenangkan, gunakan Database & History dan pilih lifecycle WON. Form mencatat win price, tanggal menang, dan deposit. Helper `mark_property_won` mempertahankan payload analisis (termasuk latest_analysis) dan hanya menambahkan/menyegarkan `win_details` serta lifecycle. WON muncul pada Properti Aktif. Saat progres pengelolaan disimpan, lifecycle menjadi ACTIVE.

`decision_status` tetap terpisah dari `lifecycle_status`: status keputusan analisis historis tidak ditulis ulang hanya karena objek berhasil dimenangkan.
