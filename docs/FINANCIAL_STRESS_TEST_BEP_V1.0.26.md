# Financial Stress Test & Break-Even Point — V1.0.26

## Definisi
- **Break-even exit price**: harga exit saat net project profit sama dengan nol, dengan biaya pra-penjualan dan biaya penjualan dihitung melalui `calculate_project`.
- **Exit price untuk ROI minimum / GO**: harga exit minimum yang menghasilkan Project ROI sesuai hurdle pada total biaya proyek termasuk biaya penjualan.
- **Maximum holding tolerance**: durasi holding maksimum yang masih menjaga Project ROI minimal pada hurdle minimum, memakai exit konservatif dan biaya holding bulanan.
- **Stress scenario**: simulasi deterministik dengan penyesuaian exit price, renovasi, durasi, dan biaya tambahan.

## Skenario Default
| Skenario | Diskon exit | Overrun renovasi | Holding |
|---|---:|---:|---|
| Dasar | 0% | 0% | Input dasar Owner |
| Moderat Buruk | -5% | +20% | Maksimum antara holding dasar +3 bulan atau 9 bulan |
| Tekanan | Input Owner | Input Owner | Input Owner |
| Ekstrem | Default -20% | Default +50% | Default 18 bulan |

Biaya tambahan pada skenario tekanan/ekstrem mengikuti input biaya tambahan Owner. Parameter ekstrem dapat diubah dari halaman Analisis.

## Interpretasi
- BEP bukan harga pasar atau jaminan bahwa aset dapat dijual pada harga tersebut.
- Maximum holding tolerance dibatasi pencarian 120 bulan; `AT_LEAST_SEARCH_CAP` berarti threshold belum turun sampai batas tersebut.
- Cadangan likuiditas yang belum digunakan tidak otomatis dianggap biaya; skenario penggunaan seluruh cadangan dapat dimodelkan dengan biaya tambahan bila relevan.
- Stress test bukan Monte Carlo dan tidak menghitung probabilitas statistik.
