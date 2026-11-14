"""Deterministic renovation scope and quantity guidance for preliminary RAB.

These are screening coefficients, not SNI/AHSP universal constants. Each
quantity is labelled by its basis/confidence and must be checked against the
actual building, drawings and contractor measurement before approval.
"""
from __future__ import annotations
from math import ceil
from typing import Any
from .utils import to_float

CATEGORIES = [
    "Auto sesuai kondisi umum",
    "Renovasi Kosmetik",
    "Renovasi Ringan",
    "Renovasi Sedang",
    "Renovasi Berat",
    "Hitung Tanah",
]

COEFFICIENTS = {
    "floor_ceiling_per_lb": 1.00,
    "roof_area_factor_low": 1.25,
    "roof_area_factor_base": 1.30,
    "roof_area_factor_high": 1.35,
    "wall_paint_factor_low": 2.50,
    "wall_paint_factor_base": 2.75,
    "wall_paint_factor_high": 3.00,
    "electrical_point_per_m2": 1 / 6,
    "debris_m3_per_m2_low": 0.30,
    "debris_m3_per_m2_base": 0.40,
    "debris_m3_per_m2_high": 0.50,
    "truck_capacity_m3_default": 5.0,
}


def _item(code: str, name: str, unit: str, low: float | None, base: float | None,
          high: float | None, basis: str, confidence: str, note: str,
          priority: str = "Disarankan", conditional: bool = False) -> dict[str, Any]:
    return {
        "item_code": code, "work_item": name, "unit": unit,
        "quantity_low": round(low, 2) if low is not None else None,
        "quantity_base": round(base, 2) if base is not None else None,
        "quantity_high": round(high, 2) if high is not None else None,
        "quantity_basis": basis, "confidence": confidence,
        "notes": note, "priority": priority, "conditional": conditional,
    }


def infer_renovation_category(physical_condition: str = "", selected: str = "", condition_description: str = "") -> str:
    """Infer a renovation scope only from explicit user condition/description.

    Unknown condition defaults to an inspection-only package, not an assumed
    light renovation. A user-selected category always takes precedence.
    """
    if selected and selected != "Auto sesuai kondisi umum":
        return selected
    text = f"{physical_condition or ''} {condition_description or ''}".lower()
    if any(x in text for x in ["hitung tanah", "tanah kosong", "demolisi", "bangunan dianggap nol"]):
        return "Hitung Tanah"
    if any(x in text for x in ["renovasi berat", "perkuatan struktur", "tambah lantai", "ubah tata ruang", "fondasi baru", "kolom/balok"]):
        return "Renovasi Berat"
    if any(x in text for x in ["renovasi sedang", "ganti seluruh atap", "atap total", "renovasi total kamar mandi", "ganti seluruh plafon", "ganti seluruh keramik"]):
        return "Renovasi Sedang"
    if any(x in text for x in ["renovasi ringan", "perbaikan lokal", "genteng pecah", "keramik pecah", "kloset rusak", "atap bocor", "talang bocor"]):
        return "Renovasi Ringan"
    if any(x in text for x in ["renovasi kosmetik", "cat mengelupas", "pengecatan", "cat ulang", "plamir", "finishing kosmetik"]):
        return "Renovasi Kosmetik"
    if "siap huni" in text or "ready huni" in text:
        return "Renovasi Kosmetik"
    return "Auto sesuai kondisi umum"


def build_renovation_quantity_guidance(context: dict[str, Any]) -> dict[str, Any]:
    """Build category-specific work catalog with quantity ranges from property facts."""
    lt = to_float(context.get("land_area"))
    lb = to_float(context.get("building_area"))
    floors = max(1, int(to_float(context.get("floor_count") or 1)))
    bedrooms = max(0, int(to_float(context.get("bedrooms"))))
    bathrooms = max(0, int(to_float(context.get("bathrooms"))))
    selected_category = str(context.get("renovation_category") or "Auto sesuai kondisi umum")
    physical_text = str(context.get("physical_condition") or "")
    description = str(context.get("condition_description") or "")
    category = infer_renovation_category(physical_text, selected_category, description)
    auto_mode = selected_category == "Auto sesuai kondisi umum"
    explicit_cosmetic_scope = (not auto_mode) or any(x in f"{physical_text} {description}".lower() for x in ["renovasi kosmetik", "cat mengelupas", "pengecatan", "cat ulang", "plamir"])
    explicit_ready_only = auto_mode and "siap huni" in physical_text.lower() and not description.strip()
    actual_footprint = to_float(context.get("building_footprint_m2"))
    footprint = actual_footprint if actual_footprint > 0 else (lb / floors if lb > 0 else None)
    roof_low = footprint * COEFFICIENTS["roof_area_factor_low"] if footprint else None
    roof_base = footprint * COEFFICIENTS["roof_area_factor_base"] if footprint else None
    roof_high = footprint * COEFFICIENTS["roof_area_factor_high"] if footprint else None
    wall_low = lb * COEFFICIENTS["wall_paint_factor_low"] if lb else None
    # More bedrooms usually imply more internal partitions/door reveals. This
    # only moves the midpoint within the user-provided 2.5–3.0 screening band;
    # it is not a measured wall take-off.
    wall_base_factor = min(3.0, 2.5 + max(0, bedrooms - 1) * 0.10) if bedrooms else 2.75
    wall_base = lb * wall_base_factor if lb else None
    wall_high = lb * COEFFICIENTS["wall_paint_factor_high"] if lb else None
    floor_ceiling = lb * COEFFICIENTS["floor_ceiling_per_lb"] if lb else None
    electrical_points = ceil(lb * COEFFICIENTS["electrical_point_per_m2"]) if lb else None
    debris_low = lb * COEFFICIENTS["debris_m3_per_m2_low"] if lb else None
    debris_base = lb * COEFFICIENTS["debris_m3_per_m2_base"] if lb else None
    debris_high = lb * COEFFICIENTS["debris_m3_per_m2_high"] if lb else None
    truck_capacity = to_float(context.get("truck_capacity_m3"), COEFFICIENTS["truck_capacity_m3_default"]) or 5.0
    items: list[dict[str, Any]] = []

    if category == "Renovasi Kosmetik":
        wall_priority = "Wajib" if explicit_cosmetic_scope else "Disarankan"
        ceiling_priority = "Wajib" if explicit_cosmetic_scope else "Disarankan"
        items += [
            _item("COS_PREP", "Pembersihan dan proteksi area kerja", "ls", 1, 1, 1, "Paket persiapan proyek", "Sedang", "Lumpsum; sesuaikan dengan luas, barang dan akses area kerja.", "Wajib" if explicit_cosmetic_scope else "Disarankan"),
            _item("COS_WALL", "Kupas cat lepas, plamir/aci lokal dan cat ulang dinding interior-eksterior", "m2", wall_low, wall_base, wall_high, f"LB × 2,5–3,0; titik tengah disesuaikan secara kasar dengan jumlah kamar tidur ({bedrooms or 'belum diisi'})", "Rendah", "Koefisien penyaringan awal, bukan pengukuran dinding. Koreksi setelah ukur keliling, tinggi, bukaan dan partisi.", wall_priority),
            _item("COS_CEILING", "Pengecatan plafon dan perbaikan nat/retak rambut lokal", "m2", floor_ceiling, floor_ceiling, floor_ceiling, "LB × 1,0 untuk cakupan plafon penuh", "Sedang", "Kurangi bila terdapat void, area terbuka atau plafon tidak seluruhnya dicat.", ceiling_priority),
            _item("COS_FLOOR", "Poles lantai ATAU pemasangan finishing vinyl/SPC di atas lantai eksisting", "m2", floor_ceiling, floor_ceiling, floor_ceiling, "LB × 1,0 jika seluruh lantai dipilih; pilih satu metode", "Sedang", "Conditional: pilih poles ATAU vinyl/SPC sesuai kondisi lantai; jangan hitung keduanya.", conditional=True),
            _item("COS_JOINERY", "Cat ulang kusen/daun pintu dan ganti aksesori minor", "unit", None, None, None, "Jumlah pintu/jendela harus dihitung saat survei; jumlah kamar hanya konteks, bukan hitungan unit pintu", "Rendah", "Isi jumlah unit aktual; tidak diturunkan otomatis dari LT/LB.", conditional=True),
        ]
    elif category == "Renovasi Ringan":
        # Screening allowances for localized repairs only. They are not assumed
        # to be needed: Gemini includes them only when description/photo or
        # user selection supports the scope. All remain low-confidence.
        roof_patch_low = roof_low * 0.05 if roof_low is not None else None
        roof_patch_base = roof_base * 0.10 if roof_base is not None else None
        roof_patch_high = roof_high * 0.15 if roof_high is not None else None
        ceiling_patch_low = lb * 0.03 if lb else None
        ceiling_patch_base = lb * 0.075 if lb else None
        ceiling_patch_high = lb * 0.10 if lb else None
        tile_patch_low = lb * 0.02 if lb else None
        tile_patch_base = lb * 0.04 if lb else None
        tile_patch_high = lb * 0.06 if lb else None
        items += [
            _item("LGT_ROOF", "Perbaikan lokal genteng/nok/talang/lisplang", "m2", roof_patch_low, roof_patch_base, roof_patch_high, "Allowance lokal 5–15% dari estimasi luas atap; ukur kerusakan aktual", "Rendah", "Bukan penggantian seluruh atap. Persentase hanya allowance screening bila ada indikasi kerusakan; foto fasad tidak cukup untuk memastikan kondisi atap.", conditional=True),
            _item("LGT_CEILING", "Bongkar dan ganti plafon lokal akibat bocor", "m2", ceiling_patch_low, ceiling_patch_base, ceiling_patch_high, "Allowance lokal 3–10% × LB; ukur batas area rusak", "Rendah", "Estimasi awal area lokal; wajib periksa plafon dan sumber kebocoran sebelum menetapkan volume.", conditional=True),
            _item("LGT_TILE", "Ganti keramik lokal teras/dapur/kamar mandi", "m2", tile_patch_low, tile_patch_base, tile_patch_high, "Allowance lokal 2–6% × LB; ukur area keramik yang rusak", "Rendah", "Tidak otomatis seluruh LB; persentase hanya allowance awal bila keramik memang perlu diganti.", conditional=True),
            _item("LGT_SANITARY", "Perbaikan/penggantian sanitair minor per kamar mandi", "set", bathrooms if bathrooms else None, bathrooms if bathrooms else None, bathrooms if bathrooms else None, "Jumlah kamar mandi × 1 paket pemeriksaan/perbaikan", "Rendah", "Jumlah kamar mandi hanya batas unit; item kloset/keran/wastafel harus dipilih sesuai kerusakan.", conditional=True),
            _item("LGT_ELEC", "Penggantian saklar, stopkontak dan armatur lampu lokal", "titik", None, None, None, "Titik rusak harus dihitung; bukan seluruh titik instalasi", "Rendah", "Jangan anggap seluruh instalasi perlu diganti.", conditional=True),
            _item("LGT_JOINERY", "Penggantian lokal daun pintu/jendela/aksesori", "unit", None, None, None, "Jumlah unit rusak harus dihitung", "Rendah", "Tidak dapat ditentukan dari LT/LB atau jumlah kamar saja.", conditional=True),
        ]
    elif category == "Renovasi Sedang":
        items += [
            _item("MED_DEM_ROOF", "Pembongkaran penutup/rangka atap eksisting", "m2", roof_low, roof_base, roof_high, "Luas tapak bangunan (LB ÷ jumlah lantai) × faktor atap 1,25–1,35", "Sedang", "Asumsi bentuk atap sederhana dan overhang umum; verifikasi bentuk, jurai, talang dan overhang.", "Wajib"),
            _item("MED_NEW_ROOF", "Rangka atap baja ringan, foil, penutup atap dan lisplang", "m2", roof_low, roof_base, roof_high, "Luas tapak bangunan × faktor geometri atap 1,25–1,35", "Sedang", "Faktor geometri bukan koefisien AHSP universal; ukur desain atap aktual.", "Wajib"),
            _item("MED_CEILING", "Pembongkaran dan pemasangan rangka/penutup plafon baru", "m2", floor_ceiling, floor_ceiling, floor_ceiling, "LB × 1,0 untuk seluruh plafon", "Sedang", "Kurangi area void/area tanpa plafon.", "Wajib"),
            _item("MED_FLOOR", "Pembongkaran dan pemasangan keramik/granit lantai baru", "m2", floor_ceiling, floor_ceiling, floor_ceiling, "LB × 1,0 untuk seluruh lantai", "Sedang", "Gunakan luas bersih area yang benar-benar diganti; keluarkan carport/teras bila berbeda.", "Wajib"),
            _item("MED_WALL", "Persiapan permukaan dan pengecatan dinding interior-eksterior", "m2", wall_low, wall_base, wall_high, "LB × 2,5–3,0 sebagai estimasi luas bidang cat gabungan", "Rendah", "Koefisien kasar; ukur bidang dinding aktual sebelum kontrak."),
            _item("MED_BATH", "Renovasi area basah lengkap per kamar mandi", "unit", bathrooms if bathrooms else None, bathrooms if bathrooms else None, bathrooms if bathrooms else None, "Satu unit per kamar mandi yang direnovasi", "Sedang", "Jumlah kamar mandi dari input pengguna; ukuran dan spesifikasi per unit perlu dicek.", "Wajib"),
            _item("MED_ELEC", "Penarikan ulang instalasi/titik listrik sebagai allowance awal", "titik", electrical_points, electrical_points, electrical_points, "LB ÷ 6 m², dibulatkan ke atas", "Rendah", "Hanya allowance screening. Bukan standar jumlah titik; final berdasarkan denah dan perhitungan teknisi listrik."),
            _item("MED_PLUMB", "Penggantian pipa air bersih/kotor", "m'", None, None, None, "Panjang jalur pipa harus diukur", "Rendah", "Tidak boleh dihitung dari LT/LB saja; perlu jalur dan titik plumbing.", conditional=True),
        ]
    elif category == "Renovasi Berat":
        items += [
            _item("HVY_DEM", "Pembongkaran dinding/komponen sesuai desain perubahan ruang", "m2", None, None, None, "Luas pembongkaran berdasarkan denah dan inspeksi", "Rendah", "Wajib ada scope/denah; jangan memperkirakan dari jumlah kamar saja.", "Wajib", True),
            _item("HVY_STRUCT", "Pekerjaan struktur: fondasi/kolom/balok/dak/perkuatan (perlu penilaian engineer)", "ls", None, None, None, "Desain dan perhitungan tenaga ahli struktur", "Rendah", "Tidak dapat dihitung aman dari LT/LB/foto; minta evaluasi engineer dan RAB kontraktor.", "Wajib", False),
            _item("HVY_WALL", "Pemasangan/perubahan dinding dan finishing", "m2", None, None, None, "Luas dinding sesuai denah baru", "Rendah", "Perlu gambar rencana dan pengukuran.", "Wajib", True),
            _item("HVY_ROOF", "Atap baru/perubahan bentuk atap", "m2", roof_low, roof_base, roof_high, "Tapak (LB ÷ lantai) × faktor 1,25–1,35", "Rendah", "Allowance awal saja; bentuk dan struktur atap harus direncanakan.", "Wajib", True),
            _item("HVY_FLOOR", "Pekerjaan lantai dan plafon setelah perubahan ruang", "m2", floor_ceiling, floor_ceiling, floor_ceiling, "LB × 1,0 sebagai luasan awal", "Rendah", "Perlu dikoreksi menggunakan denah akhir.", "Wajib", True),
            _item("HVY_ELEC", "Instalasi listrik baru sesuai denah dan kebutuhan beban", "titik", electrical_points, electrical_points, electrical_points, "LB ÷ 6 m² sebagai allowance awal", "Rendah", "Jumlah titik dan kapasitas harus dihitung teknisi; bukan standar final.", "Wajib", True),
            _item("HVY_BATH", "Pekerjaan area basah sesuai desain", "unit", bathrooms if bathrooms else None, bathrooms if bathrooms else None, bathrooms if bathrooms else None, "Jumlah kamar mandi yang diinput user", "Rendah", "Ukuran dan perubahan plumbing perlu desain.", conditional=True),
        ]
    elif category == "Hitung Tanah":
        residual = max(0.0, lt - footprint) if lt > 0 and footprint is not None else None
        truck_low = ceil(debris_low / truck_capacity) if debris_low is not None else None
        truck_base = ceil(debris_base / truck_capacity) if debris_base is not None else None
        truck_high = ceil(debris_high / truck_capacity) if debris_high is not None else None
        items += [
            _item("LAND_DISCONNECT", "Pengamanan dan pemutusan sementara listrik/air", "ls", 1, 1, 1, "1 paket", "Sedang", "Konfirmasi prosedur kepada PLN/PDAM dan kondisi sambungan.", "Wajib"),
            _item("LAND_DEMOLISH", "Pembongkaran total bangunan eksisting", "m2", lb, lb, lb, "LB agregat sebagai luas lantai yang dibongkar", "Sedang", "Gunakan LB total; fondasi/struktur bawah dapat menambah scope dan biaya.", "Wajib"),
            _item("LAND_DEBRIS", "Pengumpulan, pemuatan dan pembuangan puing", "m3", debris_low, debris_base, debris_high, "LB × 0,30–0,50 m³/m² sebagai screening volume puing", "Rendah", "Faktor sangat kasar; tergantung material, fondasi, pemilahan dan faktor pengembangan puing. Validasi dengan kontraktor/TPA.", "Wajib"),
            _item("LAND_TRUCK", "Ritase angkut puing (kapasitas rencana 5 m³/truk)", "rit", truck_low, truck_base, truck_high, "Volume puing ÷ kapasitas truk asumsi 5 m³, dibulatkan ke atas", "Rendah", "Kapasitas aktual 4–6 m³; isi sesuai truk dan akses lokasi.", "Wajib"),
            _item("LAND_CLEAR", "Pembersihan/pematangan lahan sisa", "m2", residual, residual, residual, "LT − tapak bangunan (LB ÷ jumlah lantai), jika seluruh area sisa perlu dibersihkan", "Rendah", "Maksimum indikatif; jangan dihitung sebagai biaya jika area sudah bersih/berpaving/tidak termasuk pekerjaan.", conditional=True),
            _item("LAND_FENCE", "Pagar pengaman sementara proyek", "m'", None, None, None, "Keliling batas lahan harus diukur", "Rendah", "Butuh pengukuran keliling dan ketentuan keselamatan lingkungan.", conditional=True),
        ]
    else:  # Auto / condition unknown: conservative inspection and small prep only.
        items += [
            _item("AUTO_INSPECT", "Inspeksi kondisi atap, plafon, dinding, lantai, utilitas dan area basah", "ls", 1, 1, 1, "1 paket inspeksi", "Sedang", "RAB konstruksi belum bisa dipastikan sebelum survei kondisi.", "Wajib"),
            _item("AUTO_CLEAN", "Pembersihan awal dan pengamanan area", "ls", 1, 1, 1, "1 paket", "Sedang", "Biaya persiapan minimal; belum termasuk renovasi yang belum diketahui.", "Disarankan"),
        ]

    return {
        "category": category, "category_selected_by_user": selected_category,
        "land_area": lt or None, "building_area": lb or None,
        "floor_count": floors, "building_footprint_estimate": round(footprint, 2) if footprint else None,
        "footprint_basis": "Luas tapak yang diinput pengguna" if actual_footprint > 0 else "LB agregat ÷ jumlah lantai (estimasi)",
        "property_type": context.get("property_type") or None,
        "bedrooms": bedrooms or None, "bathrooms": bathrooms or None,
        "wall_area_factor_base": wall_base_factor,
        "road_width_m": context.get("road_width_m"), "access": context.get("access") or None,
        "logistics_note": "Akses jalan/lebar jalan dipakai sebagai konteks mobilisasi dan harga satuan; tidak otomatis mengubah volume. Minta konfirmasi biaya angkut dari penyedia jasa.",
        "coefficients": COEFFICIENTS.copy(), "items": items,
        "warnings": _global_warnings(category, lb, lt, floors, actual_footprint),
        "method_note": "Koefisien adalah allowance penyaringan awal, bukan koefisien AHSP/SNI universal. Volume akhir wajib diukur dan disesuaikan gambar, spesifikasi, kondisi aktual, lokasi, metode kerja, bahan, tenaga dan alat.",
    }


def rab_item_is_in_scope(item: dict[str, Any]) -> bool:
    """Exclude explicitly rejected work from the calculated RAB total."""
    priority = str(item.get("priority") or "").strip().lower()
    return not priority.startswith("tidak diperlukan")


def _global_warnings(category: str, lb: float, lt: float, floors: int, explicit_footprint: float = 0) -> list[str]:
    warnings = []
    if lb <= 0:
        warnings.append("Luas bangunan belum tersedia; volume pekerjaan berbasis LB tidak dihitung otomatis.")
    if lt <= 0:
        warnings.append("Luas tanah belum tersedia; volume pematangan lahan tidak dapat diperkirakan.")
    if floors > 1 and explicit_footprint <= 0:
        warnings.append("Untuk bangunan bertingkat, tapak atap diperkirakan dari LB agregat ÷ jumlah lantai; verifikasi karena luas tiap lantai dapat berbeda. Isi luas tapak lantai dasar bila diketahui.")
    if explicit_footprint > 0 and lt > 0 and explicit_footprint > lt * 1.10:
        warnings.append("Luas tapak yang diinput lebih besar dari LT secara material; periksa kembali angka atau definisi luasnya.")
    if category == "Renovasi Berat":
        warnings.append("Pekerjaan struktur wajib dinilai tenaga ahli/engineer. Estimasi AI tidak dapat menjadi dasar volume atau keselamatan struktur.")
    if category == "Hitung Tanah":
        warnings.append("Volume puing dan ritase hanya allowance awal; fondasi, beton, jenis material dan akses truk dapat mengubah hasil secara besar.")
    return warnings
