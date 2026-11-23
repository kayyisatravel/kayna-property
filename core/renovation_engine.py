"""Deterministic renovation scope and quantity guidance for preliminary RAB.

These are screening coefficients, not SNI/AHSP universal constants. Each
quantity is labelled by its basis/confidence and must be checked against the
actual building, drawings and contractor measurement before approval.
"""
from __future__ import annotations
from math import ceil
import re
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


def _normalise_renovation_category(value: str) -> str | None:
    text = re.sub(r"[\*_`]+", "", str(value or "")).strip().lower()
    mapping = {
        "renovasi kosmetik": "Renovasi Kosmetik",
        "renovasi ringan": "Renovasi Ringan",
        "renovasi sedang": "Renovasi Sedang",
        "renovasi berat": "Renovasi Berat",
        "hitung tanah": "Hitung Tanah",
    }
    for label, canonical in mapping.items():
        if label in text:
            return canonical
    if "tanah kosong" in text or "land only" in text:
        return "Hitung Tanah"
    return None


def _infer_renovation_category_with_basis(
    physical_condition: str = "", selected: str = "", condition_description: str = ""
) -> tuple[str, str]:
    """Resolve the primary renovation class without being hijacked by caveats.

    Priority: explicit user selection, explicit survey condition, an explicit
    primary category statement in the description, then conservative evidence
    heuristics. Mentions inside a later risk/caveat section (e.g. "could shift to
    heavy renovation if... ") must not override the main classification.
    """
    selected_category = _normalise_renovation_category(selected)
    if selected_category and selected_category != "Auto sesuai kondisi umum":
        return selected_category, "Pilihan kategori RAB yang dikonfirmasi pengguna"

    clean = re.sub(r"[\*_`]+", "", str(condition_description or "")).strip()
    # Prefer an explicit statement about the primary category, usually near the
    # beginning of the property description. Do not scan risk notes as if they
    # describe current physical damage.
    primary_patterns = [
        # Common user wording in property reports, including "Kategori Kondisi: Renovasi Sedang".
        r"kategori\s*(?:kondisi|fisik|renovasi|utama)?\s*(?:properti)?\s*(?:adalah|:|-)?\s*(renovasi\s+(?:kosmetik|ringan|sedang|berat))",
        r"(?:masuk\s+dalam\s+kategori|masuk\s+kategori|kelas\s+renovasi)\s*(?:adalah|:|-)?\s*(renovasi\s+(?:kosmetik|ringan|sedang|berat))",
        r"(?:kondisi\s+(?:bangunan|fisik)|tingkat\s+renovasi)\s*(?:utama)?\s*(?:adalah|:|-)?\s*(renovasi\s+(?:kosmetik|ringan|sedang|berat))",
    ]
    for pattern in primary_patterns:
        match = re.search(pattern, clean[:1800], flags=re.IGNORECASE)
        if match:
            return _normalise_renovation_category(match.group(1)) or "Auto sesuai kondisi umum", "Pernyataan kategori utama dalam deskripsi"

    # A generic survey-condition dropdown may be a default/quick description.
    # When the detailed RAB narrative states a primary class, that explicit
    # classification wins. Only use the generic physical-condition value when
    # the narrative itself does not state a renovation class.
    physical_category = _normalise_renovation_category(physical_condition)
    if physical_category:
        return physical_category, "Kondisi fisik yang dipilih pengguna (tidak ada kategori lebih spesifik dalam deskripsi)"

    lower = clean.lower()
    # Risk/caveat sections often mention more severe future possibilities. Exclude
    # them from fallback classification unless the user explicitly selected a class.
    cut_positions = [lower.find(token) for token in ["catatan kritis", "perhatian utama", "risiko utama", "skenario risiko"] if lower.find(token) >= 0]
    evidence_text = lower[:min(cut_positions)] if cut_positions else lower

    if any(x in evidence_text for x in ["hitung tanah", "tanah kosong", "demolisi total", "bangunan dianggap nol"]):
        return "Hitung Tanah", "Indikasi lingkup demolisi/hitung tanah pada deskripsi"
    if any(x in evidence_text for x in ["perkuatan struktur", "fondasi baru", "kolom patah", "balok utama rusak", "tambah lantai", "ubah tata ruang struktural"]):
        return "Renovasi Berat", "Indikasi pekerjaan struktural eksplisit; wajib diverifikasi engineer"
    if any(x in evidence_text for x in ["ganti seluruh atap", "atap total", "renovasi total kamar mandi", "ganti seluruh plafon", "ganti seluruh keramik"]):
        return "Renovasi Sedang", "Indikasi penggantian sistem/elemen dalam lingkup luas"
    if any(x in evidence_text for x in ["renovasi ringan", "perbaikan lokal", "genteng pecah", "keramik pecah", "kloset rusak", "atap bocor", "talang bocor"]):
        return "Renovasi Ringan", "Indikasi perbaikan lokal; verifikasi keluasan pekerjaan"
    if any(x in evidence_text for x in ["renovasi kosmetik", "cat mengelupas", "pengecatan", "cat ulang", "plamir", "finishing kosmetik"]):
        return "Renovasi Kosmetik", "Indikasi pekerjaan finishing kosmetik"
    if "siap huni" in evidence_text or "ready huni" in evidence_text:
        return "Renovasi Kosmetik", "Indikasi kebutuhan persiapan/finishing ringan"
    return "Auto sesuai kondisi umum", "Belum ada dasar yang cukup untuk menetapkan kelas renovasi"


def infer_renovation_category(physical_condition: str = "", selected: str = "", condition_description: str = "") -> str:
    """Infer the primary scope; later conditional risk notes do not override it."""
    category, _basis = _infer_renovation_category_with_basis(physical_condition, selected, condition_description)
    return category


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
    category, category_basis = _infer_renovation_category_with_basis(physical_text, selected_category, description)
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
        # A medium category describes complexity, not automatic whole-house replacement.
        # Full-area packages stay optional unless the description explicitly confirms them.
        full_roof_confirmed = any(x in description.lower() for x in [
            "ganti seluruh atap rumah", "penggantian seluruh atap", "seluruh atap utama rusak",
            "atap utama harus diganti seluruh", "penggantian total atap rumah",
        ])
        medium_roof_low = roof_low if full_roof_confirmed else None
        medium_roof_base = roof_base if full_roof_confirmed else None
        medium_roof_high = roof_high if full_roof_confirmed else None
        medium_roof_basis = (
            "Luas tapak × faktor atap 1,25–1,35; tetap perlu ukur bidang atap dan desain"
            if full_roof_confirmed else
            "Volume dikosongkan sampai pengguna mengonfirmasi seluruh atap memang diganti; kerusakan lokal wajib diukur terpisah"
        )
        items += [
            _item("MED_DEM_ROOF", "Pembongkaran penutup/rangka atap eksisting (hanya area yang dikonfirmasi rusak)", "m2", medium_roof_low, medium_roof_base, medium_roof_high, medium_roof_basis, "Rendah", "Jangan gunakan luas seluruh atap untuk kerusakan kanopi/teras lokal. Wajib inspeksi rangka dan sambungan.", "Bersyarat", True),
            _item("MED_NEW_ROOF", "Pemasangan rangka/penutup atap dan flashing pada area yang diperbaiki", "m2", medium_roof_low, medium_roof_base, medium_roof_high, medium_roof_basis, "Rendah", "Pilih material dan hitung luas setelah pengukuran. Penggantian atap utama hanya jika inspeksi membuktikan kerusakan meluas.", "Bersyarat", True),
            _item("MED_CEILING", "Perbaikan/penggantian plafon pada area terdampak kebocoran", "m2", None, None, None, "Ukur luasan plafon yang lapuk/berjamur setelah sumber bocor diperbaiki", "Rendah", "Tidak otomatis seluruh LB; buka/inspeksi bagian yang berubah warna atau melendut.", "Bersyarat", True),
            _item("MED_FLOOR", "Perbaikan atau penggantian lantai/keramik pada area yang rusak", "m2", None, None, None, "Ukur area lantai rusak, bukan otomatis seluruh LB", "Rendah", "Pilih perbaikan lokal atau penggantian penuh berdasarkan kondisi keramik dan elevasi.", "Bersyarat", True),
            _item("MED_WALL", "Perbaikan plester, waterproofing dan finishing dinding yang lembap", "m2", None, None, None, "Ukur bidang dinding yang terkena lembap setelah sumber air ditemukan", "Rendah", "Jangan hanya mengecat sebelum sumber rembes ditemukan dan bidang cukup kering.", "Bersyarat", True),
            _item("MED_BATH", "Perbaikan/renovasi kamar mandi sesuai temuan inspeksi", "unit", None, None, None, "Isi hanya kamar mandi yang benar-benar memerlukan pekerjaan", "Rendah", "Jumlah kamar mandi di rumah bukan bukti semua unit harus direnovasi.", "Bersyarat", True),
            _item("MED_ELEC", "Pemeriksaan dan perbaikan instalasi listrik sesuai temuan", "titik", None, None, None, "Inventarisasi titik, panel dan jalur oleh teknisi", "Rendah", "Jangan menganggap seluruh instalasi perlu ditarik ulang tanpa pemeriksaan.", "Bersyarat", True),
            _item("MED_PLUMB", "Perbaikan pipa air bersih/kotor sesuai jalur yang bermasalah", "m'", None, None, None, "Panjang jalur pipa harus diukur", "Rendah", "Tidak boleh dihitung dari LT/LB saja; perlu jalur dan titik plumbing.", "Bersyarat", True),
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


    # Add narrowly scoped line items when the narrative describes localized defects.
    # These have no inferred area: user/contractor must measure before approving budget.
    desc = f"{physical_text} {description}".lower()
    def add_custom_hint(code: str, name: str, unit: str, basis: str, note: str, priority: str = "Wajib", conditional: bool = False):
        if not any(str(existing.get("item_code")) == code for existing in items):
            items.append(_item(code, name, unit, None, None, None, basis, "Rendah", note, priority, conditional))

    roof_front_terms = any(x in desc for x in ["atap teras", "kanopi", "atap depan", "galvalum", "spandek", "atap seng"])
    roof_damage_terms = any(x in desc for x in ["jebol", "rusak", "terangkat", "keropos", "bocor", "retak", "hilang"])
    if roof_front_terms and roof_damage_terms:
        explicit_ceiling_damage = any(x in desc for x in ["plafon lapuk", "plafon rusak", "plafon jebol", "plafon berjamur", "plafon melendut", "plafon mengelupas"])
        for existing in items:
            code = str(existing.get("item_code"))
            if code in {"MED_DEM_ROOF", "MED_NEW_ROOF", "LGT_ROOF"}:
                existing["quantity_low"] = None
                existing["quantity_base"] = None
                existing["quantity_high"] = None
                existing["quantity_basis"] = "Kerusakan yang disebut hanya lokal pada teras/kanopi depan; ukur panjang × lebar area rusak, jangan gunakan persentase atau luas seluruh atap."
                existing["notes"] = str(existing.get("notes") or "") + " Volume allowance atap umum dinonaktifkan karena deskripsi menunjukkan kerusakan lokal; jangan hitung seluruh atap."
            if code == "LGT_CEILING" and not explicit_ceiling_damage:
                existing["quantity_low"] = None
                existing["quantity_base"] = None
                existing["quantity_high"] = None
                existing["quantity_basis"] = "Plafon belum terlihat rusak; inspeksi bagian yang terkena bocor dan ukur setelah sumber air diperbaiki."
                existing["notes"] = str(existing.get("notes") or "") + " Jangan menghitung plafon rusak hanya dari dugaan kebocoran atap."
        add_custom_hint("VIS_FRONT_ROOF", "Bongkar dan ganti penutup atap galvalum lokal pada teras/kanopi depan, termasuk pemasangan flashing", "m2", "Ukur panjang × lebar proyeksi bidang kanopi/teras yang rusak di lapangan", "Gunakan satu scope lokal untuk penutup atap dan flashing. Tidak termasuk penggantian rangka; jangan hitung lagi item atap generik untuk bidang yang sama. Jangan gunakan luas seluruh atap rumah.")
        add_custom_hint("VIS_FRONT_ROOF_FRAME", "Perbaikan/penggantian rangka atap teras/kanopi depan jika inspeksi membuktikan rusak", "m'", "Ukur panjang elemen rangka yang benar-benar perlu diperbaiki/diganti setelah pemeriksaan", "Bersyarat: foto penutup yang jebol tidak membuktikan rangka ikut rusak. Masukkan ke base RAB hanya setelah rangka diperiksa.", "Bersyarat", True)
        add_custom_hint("VIS_CEILING_CHECK", "Inspeksi plafon dan rangka area teras/carport yang mungkin terkena bocor", "ls", "1 paket inspeksi area terdampak", "Pemeriksaan wajib sebelum memutuskan bongkar/ganti plafon; penggantian plafon hanya jika ditemukan kerusakan.", "Disarankan", True)
        for inspection_item in items:
            if inspection_item.get("item_code") == "VIS_CEILING_CHECK":
                inspection_item["quantity_low"] = inspection_item["quantity_base"] = inspection_item["quantity_high"] = 1

    damp_terms = any(x in desc for x in ["rembes", "lembap", "lembab", "jamur", "bercak putih", "cat mengelupas", "mengelupas parah"])
    if damp_terms:
        add_custom_hint("VIS_DAMP_WALL", "Penanganan bidang dinding lembap: telusuri sumber air, kupas cat/plester rusak, treatment jamur, waterproofing, perbaikan plester dan cat ulang", "m2", "Ukur bidang terdampak per sisi dan tinggi; pisahkan bidang luar/dalam dan jangan menghitung seluruh dinding tanpa bukti", "Ini lingkup khusus untuk area lembap yang terlihat/disebut. Telusuri talang, sambungan atap, pipa dan dinding tetangga sebelum finishing. Jangan hitung ulang area yang sama pada paket dinding umum.")

    if any(x in desc for x in ["rabat beton", "lantai carport", "carport retak", "beton retak", "jalan masuk retak"]):
        add_custom_hint("VIS_CARPORT_FLOOR", "Perbaikan rabat beton/lantai carport retak dan finishing", "m2", "Ukur bidang retak; tentukan apakah tambal lokal atau bongkar-pasang", "Bersyarat: periksa retak permukaan vs penurunan dasar dan ukur area. Jangan otomatis memasang keramik; pindahkan ke base RAB setelah metode perbaikan dipilih.", "Bersyarat", True)


    concrete_floor_terms = any(x in desc for x in ["rabat beton", "lantai carport retak", "carport retak", "beton retak"])
    explicit_tile_damage = any(x in desc for x in ["keramik pecah", "keramik retak", "keramik terangkat", "keramik lepas", "ganti keramik"])
    if concrete_floor_terms and not explicit_tile_damage:
        for existing in items:
            if str(existing.get("item_code")) == "LGT_TILE":
                existing["quantity_low"] = None
                existing["quantity_base"] = None
                existing["quantity_high"] = None
                existing["quantity_basis"] = "Permukaan yang disebut adalah rabat beton/carport, bukan keramik; ukur area retak dan tentukan tambal, recast atau finishing setelah inspeksi."
                existing["notes"] = str(existing.get("notes") or "") + " Jangan otomatis mengusulkan pemasangan keramik untuk rabat beton yang retak."

    if any(x in desc for x in ["pagar besi", "cat pagar", "pagar kusam"]):
        add_custom_hint("VIS_FENCE_PAINT", "Pembersihan karat ringan, primer dan pengecatan ulang pagar besi", "m2", "Ukur bidang pagar/teralis atau hitung paket setelah survei", "Bersyarat/opsional: pagar tampak masih lurus dan terpasang; cek karat, engsel, rel dan mekanisme pintu. Pengecatan tidak wajib jika pengguna tidak memilih perapian tampilan.", "Bersyarat", True)


    # Whole-front facade colour refresh is an aesthetic option, not a repair fact.
    # Keep it distinct from the damp-wall treatment and exclude that same surface
    # to prevent double-counting paint/plaster on the carport wall.
    facade_refresh_terms = any(x in desc for x in ["mencolok", "warna netral", "cat ulang seluruh fasad", "pengecatan ulang fasad", "kombinasi warna", "aksen merah"])
    if facade_refresh_terms:
        add_custom_hint("VIS_FACADE_REPAINT", "Pengecatan ulang fasad luar dengan warna pilihan pengguna", "m2", "Ukur setiap bidang fasad luar; kurangi bidang lembap yang sudah dihitung pada VIS_DAMP_WALL dan area bukaan", "Pekerjaan estetika/opsional, bukan kerusakan wajib. Tidak termasuk treatment rembesan dan tidak boleh menghitung ulang bidang yang sama dengan VIS_DAMP_WALL.", "Bersyarat", True)

    if any(x in desc for x in ["tumpukan", "puing", "sampah", "peti kayu", "barang bekas"]):
        add_custom_hint("VIS_FRONT_CLEAN", "Pembersihan dan pengangkutan barang/material bekas di area depan", "ls", "1 paket sesuai volume dan jenis barang", "Pisahkan barang milik pihak lain dari sampah; pastikan izin pengangkutan sebelum dibuang.", "Disarankan", True)
        for cleaning_item in items:
            if cleaning_item.get("item_code") == "VIS_FRONT_CLEAN":
                cleaning_item["quantity_low"] = cleaning_item["quantity_base"] = cleaning_item["quantity_high"] = 1

    if not bool(context.get("interior_inspected", False)) and category != "Auto sesuai kondisi umum":
        add_custom_hint("INSPECT_INTERIOR", "Inspeksi interior: atap bagian dalam, plafon, dinding, lantai, listrik, pipa dan kamar mandi", "ls", "1 paket inspeksi sebelum finalisasi RAB interior", "Interior tidak terlihat dari foto fasad. Ini adalah biaya/pekerjaan inspeksi, bukan asumsi semua elemen rusak.", "Disarankan", True)
        for inspection_item in items:
            if inspection_item.get("item_code") == "INSPECT_INTERIOR":
                inspection_item["quantity_low"] = inspection_item["quantity_base"] = inspection_item["quantity_high"] = 1

    return {
        "category": category, "category_selected_by_user": selected_category,
        "category_basis": category_basis,
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
    """Return true only for confirmed base-budget work.

    Conditional items remain visible in the RAB editor, but do not inflate the
    base RAB or block completeness until a user confirms them by changing the
    priority from "Bersyarat" to Wajib/Disarankan/Opsional.
    """
    priority = str(item.get("priority") or "").strip().lower()
    if priority.startswith("tidak diperlukan"):
        return False
    if priority in {"bersyarat", "conditional", "belum dikonfirmasi"}:
        return False
    return True


def summarize_rab_totals(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Recompute RAB subtotals/completeness from the editable line items.

    Used after the initial AI pass and again after manual/second-pass rate edits,
    so the displayed totals cannot remain stale after a user changes a price.
    """
    rows = [dict(row) for row in (items or []) if isinstance(row, dict)]
    in_scope = [row for row in rows if rab_item_is_in_scope(row)]

    def priced(field: str) -> list[dict[str, Any]]:
        return [
            row for row in in_scope
            if to_float(row.get("quantity")) > 0 and to_float(row.get(field)) > 0
        ]

    low_rows = priced("unit_cost_low")
    base_rows = priced("unit_cost")
    high_rows = priced("unit_cost_high")
    unpriced = [
        str(row.get("work_item") or "Pekerjaan tanpa nama")
        for row in in_scope
        if to_float(row.get("quantity")) <= 0 or to_float(row.get("unit_cost")) <= 0
    ]
    base_complete = bool(in_scope) and not unpriced
    range_complete = base_complete and len(low_rows) == len(in_scope) and len(high_rows) == len(in_scope)

    def amount(group: list[dict[str, Any]], field: str) -> int | None:
        if not group:
            return None
        return round(sum(to_float(row.get("quantity")) * to_float(row.get(field)) for row in group))

    return {
        "total_low_indicative": amount(low_rows, "unit_cost_low"),
        "total_conservative_indicative": amount(base_rows, "unit_cost"),
        "total_high_indicative": amount(high_rows, "unit_cost_high"),
        "subtotal_low_priced_items": amount(low_rows, "unit_cost_low"),
        "subtotal_conservative_priced_items": amount(base_rows, "unit_cost"),
        "unpriced_items": unpriced,
        "unpriced_item_count": len(unpriced),
        "priced_item_count": len(base_rows),
        "in_scope_item_count": len(in_scope),
        "excluded_items": [
            str(row.get("work_item") or "Pekerjaan tanpa nama")
            for row in rows if not rab_item_is_in_scope(row)
        ],
        "total_conservative_complete": base_complete,
        "total_range_complete": range_complete,
        "user_boq_priced_count": sum(
            1 for row in in_scope
            if str(row.get("item_code") or "").startswith("USER_BOQ_")
            and to_float(row.get("quantity")) > 0 and to_float(row.get("unit_cost")) > 0
        ),
        "user_boq_catalog_priced_count": sum(
            1 for row in in_scope
            if str(row.get("item_code") or "").startswith("USER_BOQ_")
            and str(row.get("price_source") or "").startswith("Katalog screening")
        ),
    }


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
