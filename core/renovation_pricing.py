"""Deterministic regional screening rates for common auction-house repairs.

The catalogue is an underwriting aid, not an AHSP/HSPK, contractor quote or
billable BOQ. It provides low/base/high installed-work allowances for common
scopes around the Surabaya-Sidoarjo market. Unknown/structural scopes are not
priced by guessing; they require a measured scope or professional quote.
"""
from __future__ import annotations

import re
from typing import Any

PRICE_CATALOG_VERSION = "SURABAYA_SIDOARJO_SCREENING_2026_V1"
PRICE_CATALOG_BASIS = (
    "Katalog screening regional Surabaya–Sidoarjo 2026; kisaran paket bahan+upah "
    "untuk spesifikasi ekonomis-menengah. Disusun sebagai allowance investor, "
    "disilang-periksa dengan SSH Sidoarjo TA 2026 untuk referensi material dan "
    "referensi publik jasa renovasi regional; bukan HSPK/SSH all-in atau quotation vendor."
)

# Values are IDR per the unit in the mapping. Conservative is the central
# project-budget rate; high is an adverse but plausible screening allowance.
RATE_CATALOG: list[dict[str, Any]] = [
    {"key":"clean_debris", "patterns":[r"pembersihan.*(peti|sampah|barang|material|area depan)", r"angkut.*(puing|sampah|barang)", r"pembersihan dan pengangkutan", r"pembersihan.*area kerja", r"persiapan.*area kerja", r"proteksi area kerja"], "unit":"ls", "low":500_000, "base":900_000, "high":1_500_000, "confidence":"Sedang", "scope":"Pembersihan ringan area depan dan pengangkutan terbatas; volume barang besar/izin pengosongan menambah biaya."},
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
    {"key":"inspection_interior", "patterns":[r"inspeksi interior", r"cek.*(atap bagian dalam|plafon|listrik|pipa|kamar mandi)"], "unit":"ls", "low":350_000, "base":650_000, "high":1_000_000, "confidence":"Sedang", "scope":"Pemeriksaan visual dan uji fungsi dasar sebelum scope tersembunyi dipastikan; tidak termasuk perbaikan."},
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
    """Fill/standardise rate ranges without changing any row quantity.

    Mapped scopes use the deterministic regional catalogue in preference to a
    free-form model rate, so similar projects get reproducible budgets. Gemini
    suggestions are retained in notes as a cross-check. Unmapped scopes keep an
    AI suggestion (clearly labelled) or remain unpriced rather than guessed.
    """
    enriched: list[dict[str, Any]] = []
    for original in rows or []:
        row = dict(original)
        catalog = lookup_unit_rate(row.get("work_item", ""), row.get("unit", ""))
        if catalog and row.get("catalog_key") == catalog.get("catalog_key"):
            # Idempotent when the same row passes through the parser and the
            # post-guidance enrichment stage.
            enriched.append(row)
            continue
        if catalog:
            ai_low = row.get("unit_cost_low")
            ai_base = row.get("unit_cost")
            ai_high = row.get("unit_cost_high")
            row.update({k: v for k, v in catalog.items() if k in {"unit_cost_low", "unit_cost", "unit_cost_high", "price_source", "rate_basis", "catalog_key"}})
            notes = str(row.get("notes") or "")
            if ai_base not in (None, "", 0, "0"):
                try:
                    ai_val = float(ai_base)
                    base_val = float(row["unit_cost"])
                    pct = abs(ai_val - base_val) / max(base_val, 1) * 100
                    if pct >= 15:
                        notes += (
                            f" | Cross-check Gemini: rendah {ai_low or '—'}, tengah {ai_base}, atas {ai_high or '—'} / {row.get('unit')}; "
                            f"berbeda {pct:.0f}% dari rate katalog. Rate katalog dipakai agar konsisten."
                        )
                except (TypeError, ValueError):
                    pass
            if row.get("conditional") or str(row.get("priority") or "").lower() in {"disarankan", "bersyarat", "opsional"}:
                # A low-confidence scope allowance must not be upgraded merely
                # because the unit rate itself is commonly quoted.
                if str(row.get("confidence") or "").lower() != "rendah":
                    row["confidence"] = "Rendah"
            elif not row.get("confidence"):
                row["confidence"] = catalog.get("confidence", "Sedang")
            notes += " | Rate default katalog dipakai sebagai allowance modal; volume pengguna tidak diubah."
            row["notes"] = notes.strip(" |")
        elif row.get("unit_cost") not in (None, "", 0, "0"):
            row["price_source"] = row.get("price_source") or "Gemini (estimasi screening; belum diverifikasi lokal)"
            row["rate_basis"] = row.get("rate_basis") or "Saran harga Gemini; bukan quotation vendor/HSPK lokal."
        else:
            row["price_source"] = row.get("price_source") or "Belum tersedia — perlu estimasi manual/quotation"
        enriched.append(row)
    return enriched
