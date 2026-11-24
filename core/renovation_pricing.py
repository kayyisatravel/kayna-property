"""Deterministic regional screening rates for common auction-house repairs.

The catalogue is an underwriting aid, not an AHSP/HSPK, contractor quote or
billable BOQ. It provides low/base/high installed-work allowances for common
scopes around the Surabaya-Sidoarjo market. Unknown/structural scopes are not
priced by guessing; they require a measured scope or professional quote.
"""
from __future__ import annotations

import re
from typing import Any

PRICE_CATALOG_VERSION = "PFMS_SIDOARJO_SCREENING_2026_11_V2"
PRICE_CATALOG_BASIS = (
    "Pricebook screening internal PFMS untuk Surabaya–Sidoarjo, versi 2026.11. "
    "Nilai paket low/base/high adalah allowance underwriting bahan+upah dengan asumsi "
    "spesifikasi ekonomis-menengah; bukan tarif resmi pemerintah dan bukan quotation kontraktor. "
    "Acuan komponennya: SHS Sidoarjo TA 2026 (Perbup 27/2025) untuk sebagian harga bahan, "
    "serta metode AHSP Permen PUPR 8/2023 untuk kerangka HSD bahan, tenaga, alat, koefisien, "
    "biaya umum dan keuntungan. Harga komposit PFMS tetap perlu dikalibrasi dengan survei toko, "
    "upah tukang lokal, dan quotation kontraktor; jangan menyebut hasilnya sebagai SSH/HSPK resmi."
)
PRICE_CATALOG_REFERENCES = {
    "ssh_sidoarjo_2026": "https://sidoarjokab.go.id/berita/peraturan-bupati-sidoarjo-no-27-tahun-2025-1751631865",
    "hspk_sidoarjo_2026": "https://jdih.sidoarjokab.go.id/peraturan/202500200074/peraturan-bupati-no-75-tahun-2025-analisis-standar-belanja-dan-harga-satuan-poko",
    "ahsp_pupr_2023": "https://peraturan.bpk.go.id/Details/262345/permen-pupr-no-8-tahun-2023",
}
PRICE_CATALOG_ANCHORS = [
    {"item": "Cat tembok interior", "specification": "Perbup Sidoarjo 27/2025, SSH TA 2026", "unit": "kg", "rate": 39_600},
    {"item": "Cat tembok eksterior", "specification": "Perbup Sidoarjo 27/2025, SSH TA 2026", "unit": "kg", "rate": 55_800},
    {"item": "Cat plafon interior 5 kg", "specification": "Perbup Sidoarjo 27/2025, SSH TA 2026", "unit": "buah", "rate": 183_200},
    {"item": "Semen", "specification": "Perbup Sidoarjo 27/2025, SSH TA 2026", "unit": "sak", "rate": 65_000},
    {"item": "Pasir", "specification": "Perbup Sidoarjo 27/2025, SSH TA 2026", "unit": "m3", "rate": 235_000},
]

# Values are IDR per the unit in the mapping. Conservative is the central
# project-budget rate; high is an adverse but plausible screening allowance.
RATE_CATALOG: list[dict[str, Any]] = [
    {"key":"clean_debris", "patterns":[r"pembersihan.*(peti|sampah|barang|material|area depan)", r"angkut.*(puing|sampah|barang)", r"pembersihan dan pengangkutan", r"pembersihan.*area kerja", r"persiapan.*area kerja", r"proteksi area kerja", r"penyiapan area kerja", r"proteksi dan penyiapan area kerja"], "unit":"ls", "low":500_000, "base":900_000, "high":1_500_000, "confidence":"Sedang", "scope":"Pembersihan ringan area depan dan pengangkutan terbatas; volume barang besar/izin pengosongan menambah biaya."},
    {"key":"demolish_canopy", "patterns":[r"(pembongkaran|bongkar).*(atap|kanopi|teras|galvalum|spandek)"], "unit":"m2", "low":25_000, "base":45_000, "high":65_000, "confidence":"Sedang", "scope":"Bongkar penutup/komponen ringan dan kumpulkan puing; belum termasuk pengangkutan berat."},
    {"key":"scrape_mould", "patterns":[r"(pengikisan|kupas|kerok).*(cat|jamur|dinding)", r"treatment jamur", r"bersihkan.*jamur"], "unit":"m2", "low":25_000, "base":40_000, "high":60_000, "confidence":"Sedang", "scope":"Kupas cat lepas, bersihkan jamur dan persiapan permukaan; tidak mencakup plester ulang besar."},
    {"key":"canopy_full", "patterns":[r"(atap|kanopi).*(hollow|baja ringan).*(spandek|galvalum)", r"spandek.*(rangka|hollow)", r"pasang.*kanopi.*spandek"], "unit":"m2", "low":320_000, "base":410_000, "high":500_000, "confidence":"Sedang", "scope":"Paket rangka hollow/baja ringan sederhana dan penutup spandek/galvalum; spesifikasi tebal material, bentang dan finishing memengaruhi harga."},
    {"key":"canopy_roof_flashing_package", "patterns":[r"atap galvalum lokal.*(flashing|sambungan)", r"bongkar dan ganti.*atap.*flashing"], "unit":"m2", "low":360_000, "base":460_000, "high":575_000, "confidence":"Rendah", "scope":"Paket perbaikan lokal penutup atap plus allowance flashing; gunakan hanya bila flashing belum dibuat sebagai baris BoQ terpisah."},
    {"key":"flashing", "patterns":[r"flashing", r"talang.*sambungan.*dinding"], "unit":"m", "low":65_000, "base":95_000, "high":135_000, "confidence":"Sedang", "scope":"Flashing seng/metal sederhana dan sealant pada sambungan; panjang harus diukur."},
    {"key":"ceiling_pvc", "patterns":[r"(penggantian|pemasangan|ganti|pasang).*(plafon|langit).*(pvc|grc|hollow)", r"plafon.*(pvc|grc)"], "unit":"m2", "low":180_000, "base":230_000, "high":295_000, "confidence":"Sedang", "scope":"Rangka hollow ringan dan panel PVC/GRC ekonomis-menengah, terpasang; bukan plafon dekoratif."},
    {"key":"ceiling_patch", "patterns":[r"(perbaikan|tambal sulam|tambal|ganti lokal).*(plafon)", r"plafon.*(rembes|bocor|rusak)"], "unit":"m2", "low":100_000, "base":155_000, "high":225_000, "confidence":"Rendah", "scope":"Perbaikan lokal plafon termasuk bongkar terbatas, tambalan/penggantian material dan finishing cat; luas rusak perlu diverifikasi."},
    {"key":"ceiling_paint", "patterns":[r"(cat|pengecatan).*(plafon|langit-langit)", r"plafon.*(cat ulang|pengecatan)"], "unit":"m2", "low":35_000, "base":50_000, "high":75_000, "confidence":"Rendah", "scope":"Pengecatan plafon dengan persiapan ringan; tidak termasuk penggantian panel/rangka atau penanganan kebocoran."},
    {"key":"damp_wall_package", "patterns":[r"penanganan.*dinding.*(lembap|rembes)", r"perbaikan.*(plester|aci).*(waterproof|rembes)", r"dinding.*kupas.*jamur.*waterproof"], "unit":"m2", "low":150_000, "base":225_000, "high":325_000, "confidence":"Rendah", "scope":"Paket telusur ringan, kupas bidang rusak, treatment jamur, waterproofing, tambal plester/aci dan cat ulang terbatas."},
    {"key":"waterproof_wall", "patterns":[r"waterproofing", r"anti.?rembes", r"pelapisan.*kedap air"], "unit":"m2", "low":95_000, "base":150_000, "high":220_000, "confidence":"Rendah", "scope":"Aplikasi waterproofing dinding dengan persiapan permukaan normal; kerusakan plester besar dan sumber air tersembunyi dapat menambah biaya."},
    {"key":"exterior_paint", "patterns":[r"(cat|pengecatan).*(fasad|eksterior|teras).*(weatherproof|luar)?", r"weatherproof", r"cat ulang fasad"], "unit":"m2", "low":60_000, "base":85_000, "high":115_000, "confidence":"Sedang", "scope":"Persiapan ringan dan cat eksterior/weatherproof dua lapis; tidak termasuk perbaikan rembes/aci berat."},
    {"key":"interior_paint", "patterns":[r"cat.*(dinding )?interior", r"pengecatan.*interior", r"cat ulang dinding.*rumah utama"], "unit":"m2", "low":45_000, "base":65_000, "high":90_000, "confidence":"Rendah", "scope":"Persiapan ringan dan cat interior dua lapis; area lembap harus ditangani setelah sumber air dihentikan."},
    {"key":"tile_install", "patterns":[r"(pemasangan|pasang|ganti).*(keramik|ubin|lantai)", r"keramik.*(carport|teras|jalan masuk)"], "unit":"m2", "low":160_000, "base":230_000, "high":320_000, "confidence":"Sedang", "scope":"Allowance keramik ekonomis-menengah, perekat/spesi dan pemasangan; belum termasuk bongkar rabat beton atau perbaikan dasar yang amblas."},
    {"key":"garden", "patterns":[r"(perapian|perapihan|rapikan).*(taman|kanstin)", r"taman kecil"], "unit":"ls", "low":500_000, "base":1_000_000, "high":2_000_000, "confidence":"Rendah", "scope":"Perapian taman depan kecil dan kanstin existing; material tambahan besar dihitung terpisah."},
    {"key":"metal_paint", "patterns":[r"(cat|pengecatan|amplas).*(pagar|teralis|besi)", r"pagar besi"], "unit":"m2", "low":45_000, "base":65_000, "high":95_000, "confidence":"Sedang", "scope":"Persiapan karat ringan, primer anti-karat dan cat besi dua lapis; perbaikan engsel/rel tidak termasuk."},
    {"key":"joinery_paint", "patterns":[r"(cat|pengecatan).*(kusen|pintu|jendela)", r"kusen.*daun pintu"], "unit":"unit", "low":120_000, "base":180_000, "high":280_000, "confidence":"Rendah", "scope":"Cat ulang satu unit daun pintu/kusen/jendela ukuran standar; ukuran/bahan dan kondisi lama memengaruhi harga."},
    {"key":"electrical_point", "patterns":[r"(instalasi listrik|titik listrik|peremajaan.*listrik|penggantian.*stopkontak)", r"listrik.*titik"], "unit":"titik", "low":200_000, "base":275_000, "high":375_000, "confidence":"Rendah", "scope":"Allowance per titik untuk pengecekan/peremajaan minor dengan material standar; bukan penarikan ulang seluruh jalur atau kenaikan daya."},
    {"key":"sanitary_service", "patterns":[r"(servis|service|perbaikan).*(sanitair|saniter|keran|kamar mandi|pompa)", r"sanitair"], "unit":"ls", "low":650_000, "base":1_100_000, "high":1_800_000, "confidence":"Rendah", "scope":"Paket servis minor keran, flush, sifon dan pemeriksaan fungsi; penggantian kloset/pompa atau kebocoran pipa tersembunyi terpisah."},
    {"key":"floor_clean_grout", "patterns":[r"pembersihan.*(keramik|lantai).*(nat|floor)", r"bersihkan.*keramik.*nat", r"pembersihan keramik lantai"], "unit":"m2", "low":18_000, "base":28_000, "high":42_000, "confidence":"Sedang", "scope":"Pembersihan keramik existing dan pemeriksaan/perapian nat ringan; tidak termasuk ganti keramik atau regrouting penuh."},
    {"key":"joinery_service", "patterns":[r"(pembersihan|pelumasan|servis|service).*(engsel|kunci|kusen|pintu|jendela)", r"engsel.*kunci.*kusen", r"pengecekan karet kusen"], "unit":"ls", "low":350_000, "base":600_000, "high":950_000, "confidence":"Rendah", "scope":"Paket rumah untuk pembersihan dan pelumasan engsel/kunci serta pemeriksaan karet kusen; penggantian hardware dihitung terpisah."},
    {"key":"electrical_check_point", "patterns":[r"(pengecekan|pemeriksaan|peremajaan).*(fungsi|titik).*(instalasi listrik|saklar|stopkontak|fitting)", r"titik instalasi listrik"], "unit":"titik", "low":125_000, "base":200_000, "high":300_000, "confidence":"Rendah", "scope":"Pemeriksaan dan peremajaan minor per titik; tidak termasuk penarikan kabel utama, panel baru, atau kenaikan daya."},
    {"key":"inspection_interior", "patterns":[r"inspeksi interior", r"cek.*(atap bagian dalam|plafon|listrik|pipa|kamar mandi)"], "unit":"ls", "low":350_000, "base":650_000, "high":1_000_000, "confidence":"Sedang", "scope":"Pemeriksaan visual dan uji fungsi dasar sebelum scope tersembunyi dipastikan; tidak termasuk perbaikan."},
    {"key":"plumbing_check", "patterns":[r"(pemeriksaan|pengecekan|inspeksi).*(plumbing|pipa|saluran air)", r"cek.*saluran air bersih.*kotor"], "unit":"ls", "low":300_000, "base":500_000, "high":850_000, "confidence":"Rendah", "scope":"Pemeriksaan fungsi aliran dan kebocoran yang dapat diakses; tidak termasuk pembongkaran pipa tertanam."},
    {"key":"wall_patch_paint", "patterns":[r"(kupas|tambal|perbaikan).*(plamir|aci|plester).*(cat|pengecatan)", r"plamir.*aci lokal.*cat ulang"], "unit":"m2", "low":75_000, "base":115_000, "high":165_000, "confidence":"Rendah", "scope":"Tambal lokal plamir/aci dan cat pada bidang rusak ringan; tidak termasuk rembes aktif atau plesteran luas."},
    {"key":"inspection_ceiling", "patterns":[r"inspeksi plafon", r"inspeksi.*rangka.*teras", r"pemeriksaan.*plafon"], "unit":"ls", "low":250_000, "base":450_000, "high":750_000, "confidence":"Sedang", "scope":"Inspeksi plafon/rangka area teras dan indikasi rembes; tidak termasuk penggantian."},
]


def _norm_unit(value: Any) -> str:
    u = str(value or "").strip().lower().replace("²", "2").replace("³", "3").replace("’", "'")
    u = re.sub(r"\s+", "", u)
    aliases = {"m2":"m2", "m^2":"m2", "meter2":"m2", "m3":"m3", "m^3":"m3", "m'":"m", "mtr":"m", "meter":"m", "ls":"ls", "l.s.":"ls", "l.s":"ls", "bh":"buah", "buah":"buah", "unit":"unit", "titik":"titik", "set":"set", "paket":"ls"}
    return aliases.get(u, u)


def lookup_unit_rate(work_item: str, unit: str) -> dict[str, Any] | None:
    """Return the first confidently matched installed-work screening rate."""
    text = re.sub(r"\s+", " ", str(work_item or "").lower()).strip()
    target_unit = _norm_unit(unit)
    for entry in RATE_CATALOG:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in entry["patterns"]):
            if target_unit != entry["unit"]:
                # Unit aliases such as 'm²' / 'm'' are normalised above. A
                # mismatch is not coerced: never price m2 work as a lump sum.
                continue
            return {
                "unit_cost_low": int(entry["low"]),
                "unit_cost": int(entry["base"]),
                "unit_cost_high": int(entry["high"]),
                "price_source": f"Katalog screening regional 2026 ({entry['key']})",
                "rate_basis": f"{PRICE_CATALOG_BASIS} Lingkup: {entry['scope']}",
                "confidence": entry["confidence"],
                "catalog_key": entry["key"],
            }
    return None


def apply_regional_screening_rates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply a versioned, deterministic pricebook to RAB rows.

    Gemini may identify scopes, but AI-generated unit rates are never used in
    the project's financial calculations. When a scope is not mapped, its AI
    rate is retained only as a note for human review and the budget rate stays
    empty until a manual quote/override is entered.
    """
    enriched: list[dict[str, Any]] = []
    for original in rows or []:
        row = dict(original)
        # A deliberate user override is locked across recalculation and future
        # parser passes. New catalogue versions must never silently overwrite it.
        is_manual_override = (
            str(row.get("price_source") or "").strip().lower().startswith("override manual pengguna")
            and any(row.get(k) not in (None, "") for k in ("unit_cost_low", "unit_cost", "unit_cost_high"))
        )
        if is_manual_override:
            row["manual_price_locked"] = True
            row.setdefault("price_book_version", PRICE_CATALOG_VERSION)
            row["notes"] = (str(row.get("notes") or "") +
                " | Harga override manual dikunci; katalog tidak menimpa harga ini. Pastikan sumber quotation/rujukan tercatat.").strip(" |")
            enriched.append(row)
            continue
        catalog = lookup_unit_rate(row.get("work_item", ""), row.get("unit", ""))
        if catalog:
            already_current = (
                row.get("catalog_key") == catalog.get("catalog_key")
                and row.get("price_book_version") == PRICE_CATALOG_VERSION
                and all(int(to_num(row.get(field))) == int(catalog[cat_field]) for field, cat_field in (
                    ("unit_cost_low", "unit_cost_low"), ("unit_cost", "unit_cost"), ("unit_cost_high", "unit_cost_high")
                ))
            )
            if not already_current:
                ai_values = {k: row.get(k) for k in ("unit_cost_low", "unit_cost", "unit_cost_high")}
                row.update({k: v for k, v in catalog.items() if k in {
                    "unit_cost_low", "unit_cost", "unit_cost_high", "price_source", "rate_basis", "catalog_key", "confidence"
                }})
                row["price_book_version"] = PRICE_CATALOG_VERSION
                row["price_book_as_of"] = "2026-11-24"
                ai_base = ai_values.get("unit_cost")
                try:
                    if ai_base not in (None, "", 0, "0"):
                        ai_val = float(ai_base); base_val = float(row["unit_cost"])
                        pct = abs(ai_val - base_val) / max(base_val, 1) * 100
                        if pct >= 15:
                            row["notes"] = (str(row.get("notes") or "") +
                                f" | Cross-check Gemini (tidak dipakai): rendah {ai_values.get('unit_cost_low') or '—'}, "
                                f"dasar {ai_base}, atas {ai_values.get('unit_cost_high') or '—'}; selisih {pct:.0f}% "
                                "dari pricebook PFMS. Angka pricebook dipakai agar hasil konsisten.").strip(" |")
                except (TypeError, ValueError):
                    pass
            row["price_source"] = f"Katalog screening regional PFMS Sidoarjo 2026.11 ({catalog['catalog_key']})"
            row["price_book_version"] = PRICE_CATALOG_VERSION
            row["price_book_as_of"] = "2026-11-24"
            row["rate_basis"] = catalog.get("rate_basis")
            if row.get("conditional") or str(row.get("priority") or "").lower() in {"disarankan", "bersyarat", "opsional"}:
                row["confidence"] = "Rendah"
            elif not row.get("confidence"):
                row["confidence"] = catalog.get("confidence", "Sedang")
            row["notes"] = (str(row.get("notes") or "") +
                " | Harga dihitung oleh Python dari pricebook berversi; tidak berubah akibat variasi respons Gemini.").strip(" |")
        else:
            ai_values = [row.get("unit_cost_low"), row.get("unit_cost"), row.get("unit_cost_high")]
            ai_note = ""
            if any(v not in (None, "", 0, "0") for v in ai_values):
                ai_note = ("Cross-check Gemini (informasi saja, tidak dihitung): "
                    f"{ai_values[0] or '—'} / {ai_values[1] or '—'} / {ai_values[2] or '—'} per {row.get('unit') or 'unit'}. "
                    "Masukkan rate manual setelah memperoleh rujukan/quotation.")
            row["unit_cost_low"] = None
            row["unit_cost"] = None
            row["unit_cost_high"] = None
            row["price_source"] = "Belum tercakup pricebook — perlu override/quotation"
            row["price_book_version"] = PRICE_CATALOG_VERSION
            row["price_book_as_of"] = "2026-11-24"
            row["confidence"] = "Rendah"
            row["rate_basis"] = "Tidak ada pasangan katalog yang aman untuk item dan satuan ini. Jangan gunakan angka AI sebagai biaya proyek; masukkan quotation atau override manual."
            if ai_note:
                row["notes"] = (str(row.get("notes") or "") + " | " + ai_note).strip(" |")
        enriched.append(row)
    return enriched


def to_num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

