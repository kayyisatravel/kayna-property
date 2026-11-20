"""User-friendly category, subcategory and scope choices for project ledger forms."""
from __future__ import annotations

ACTUAL_CATEGORIES = [
    "Pelunasan/akuisisi", "Bea lelang", "BPHTB", "BPN/Legal",
    "Penguasaan/Kerahiman", "Renovasi", "Holding", "Marketing", "Selling", "Lainnya",
]

BUDGET_CATEGORIES = [
    "Akuisisi", "Bea lelang & pajak", "BPN/Legalitas", "Penguasaan/Kerahiman",
    "Renovasi", "Holding", "Marketing", "Penjualan", "Lainnya",
]

SUBCATEGORIES = {
    "Pelunasan/akuisisi": ["Uang jaminan/deposit", "Sisa pelunasan harga lelang", "Pelunasan harga perolehan", "Lainnya"],
    "Akuisisi": ["Uang jaminan/deposit", "Sisa pelunasan harga lelang", "Pelunasan harga perolehan", "Lainnya"],
    "Bea lelang": ["Bea lelang pembeli", "Administrasi lelang", "Lainnya"],
    "Bea lelang & pajak": ["Bea lelang pembeli", "BPHTB", "Pajak terkait perolehan", "Administrasi lelang", "Lainnya"],
    "BPHTB": ["BPHTB", "Administrasi/koreksi BPHTB", "Lainnya"],
    "BPN/Legal": ["Balik nama", "Roya", "Pengecekan sertifikat", "Pengukuran/peta bidang", "PPAT/notaris", "Salinan/dokumen", "Lainnya"],
    "BPN/Legalitas": ["Balik nama", "Roya", "Pengecekan sertifikat", "Pengukuran/peta bidang", "PPAT/notaris", "Salinan/dokumen", "Lainnya"],
    "Penguasaan/Kerahiman": ["Uang kerohiman", "Pengosongan/pemindahan barang", "Pengamanan/kunci", "Bantuan hukum", "Lainnya"],
    "Renovasi": [
        "Struktur", "Atap, rangka & talang", "Plafon", "Lantai/keramik", "Dinding & plester",
        "Pengecatan/finishing", "Pintu & jendela", "Listrik", "Air, pipa & sanitasi",
        "Kamar mandi", "Dapur", "Material umum", "Upah tukang", "Kontraktor/pengawasan",
        "Pembersihan & pembuangan", "Lainnya",
    ],
    "Holding": ["Listrik/PLN", "Air/PDAM", "IPL/keamanan", "PBB", "Perawatan/kebersihan", "Bunga/biaya modal", "Lainnya"],
    "Marketing": ["Foto/dokumentasi", "Iklan/listing", "Komisi agen", "Open house", "Lainnya"],
    "Selling": ["PPh Final penjualan", "Komisi agen", "PPAT/AJB", "Administrasi closing", "Lainnya"],
    "Penjualan": ["PPh Final penjualan", "Komisi agen", "PPAT/AJB", "Administrasi closing", "Lainnya"],
    "Lainnya": ["Biaya administrasi", "Biaya tak terduga", "Lainnya"],
}

SCOPE_OPTIONS = {
    "Uang jaminan/deposit": ["Deposit lelang (bagian dari harga menang)", "Deposit tambahan", "Lainnya"],
    "Sisa pelunasan harga lelang": ["Pelunasan setelah dikurangi deposit", "Lainnya"],
    "Bea lelang pembeli": ["Bea lelang pembeli", "Lainnya"],
    "BPHTB": ["Pembayaran BPHTB", "Kurang bayar/koreksi", "Lainnya"],
    "Balik nama": ["PNBP balik nama", "Administrasi balik nama", "Lainnya"],
    "Roya": ["PNBP roya", "Jasa pengurusan roya", "Lainnya"],
    "Uang kerohiman": ["Kompensasi pengosongan sukarela", "Bantuan pindahan", "Lainnya"],
    "Struktur": ["Perbaikan retak/struktur", "Kolom/balok", "Pondasi", "Lainnya"],
    "Atap, rangka & talang": ["Perbaikan genteng", "Penggantian genteng", "Rangka atap", "Nok/talang/waterproofing", "Lisplang", "Lainnya"],
    "Plafon": ["Perbaikan plafon", "Penggantian plafon", "Rangka plafon", "Lainnya"],
    "Lantai/keramik": ["Bongkar pasang keramik", "Pemasangan lantai baru", "Vinyl/SPC", "Poles lantai", "Lainnya"],
    "Pengecatan/finishing": ["Cat interior", "Cat eksterior", "Cat plafon", "Plamir/skim coat", "Lainnya"],
    "Listrik": ["Kabel/instalasi", "MCB/panel", "Stop kontak/saklar", "Lampu", "Lainnya"],
    "Air, pipa & sanitasi": ["Pipa air bersih", "Pipa pembuangan", "Pompa/tandon", "Kloset/kran", "Lainnya"],
    "Kamar mandi": ["Keramik kamar mandi", "Kloset", "Shower/kran", "Wastafel", "Waterproofing", "Lainnya"],
    "Dapur": ["Meja dapur", "Sink/kran", "Keramik backsplash", "Kabinet", "Lainnya"],
    "Pintu & jendela": ["Pintu", "Kusen", "Jendela", "Kunci/engsel", "Lainnya"],
    "Material umum": ["Pembelian material", "Pengiriman material", "Lainnya"],
    "Upah tukang": ["Upah harian", "Borongan pekerjaan", "Lembur", "Lainnya"],
    "Kontraktor/pengawasan": ["Termin kontraktor", "Pengawasan pekerjaan", "Lainnya"],
    "Listrik/PLN": ["Token/tagihan listrik", "Penyambungan/perubahan daya", "Lainnya"],
    "Air/PDAM": ["Tagihan air", "Sambungan/perbaikan", "Lainnya"],
    "IPL/keamanan": ["IPL", "Iuran keamanan/kebersihan", "Lainnya"],
    "Foto/dokumentasi": ["Foto properti", "Video/tur virtual", "Lainnya"],
    "Iklan/listing": ["Iklan portal properti", "Promosi media sosial", "Spanduk/papan jual", "Lainnya"],
    "Komisi agen": ["Komisi pemasaran", "Komisi closing", "Lainnya"],
}

DEFAULT_SCOPE_OPTIONS = ["Biaya utama", "Material", "Upah/jasa", "Administrasi", "Lainnya"]

def subcategory_options(category: str) -> list[str]:
    return list(SUBCATEGORIES.get(str(category or ""), ["Umum", "Lainnya"]))

def scope_options(category: str, subcategory: str) -> list[str]:
    options = SCOPE_OPTIONS.get(str(subcategory or ""))
    if options:
        return list(options)
    if str(subcategory or "") == "Lainnya" or str(category or "") == "Lainnya":
        return ["Biaya utama", "Material", "Upah/jasa", "Administrasi", "Lainnya"]
    return list(DEFAULT_SCOPE_OPTIONS)
