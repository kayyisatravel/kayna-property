"""Comparable validation and conservative market valuation."""
from __future__ import annotations
from statistics import median
from typing import Any
from datetime import date, datetime
from .utils import to_float, is_blank, normalize_text

VALID_PRICE_TYPES = {"Asking aktif", "Marked sold / perlu verifikasi", "Transaksi terverifikasi"}
VALID_CONDITIONS = {"Siap Huni", "Butuh Renovasi", "Hitung Tanah"}
VALID_ACCESS = {"2 Mobil", "1 Mobil", "Gang"}


def validate_comparable(row: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = []
    for field, label in [("name", "nama/alamat"), ("price", "harga"), ("land_area", "LT"), ("condition", "kondisi"), ("access", "akses"), ("source_url", "URL sumber"), ("date_found", "tanggal ditemukan")]:
        if is_blank(row.get(field)): errors.append(f"{label} belum diisi")
    if row.get("condition") != "Hitung Tanah" and is_blank(row.get("building_area")):
        errors.append("LB belum diisi (boleh kosong hanya untuk comparable Hitung Tanah)")
    if to_float(row.get("price")) <= 0: errors.append("harga harus lebih dari nol")
    if to_float(row.get("land_area")) <= 0: errors.append("LT harus lebih dari nol")
    if to_float(row.get("building_area")) < 0: errors.append("LB tidak boleh negatif")
    if row.get("condition") != "Hitung Tanah" and to_float(row.get("building_area")) <= 0: errors.append("LB harus lebih dari nol untuk properti selain Hitung Tanah")
    if row.get("condition") not in VALID_CONDITIONS: errors.append("kondisi tidak dikenali")
    if row.get("access") not in VALID_ACCESS: errors.append("akses tidak dikenali")
    if row.get("price_type", "Asking aktif") not in VALID_PRICE_TYPES: errors.append("jenis harga tidak dikenali")
    if not str(row.get("source_url", "")).startswith(("http://", "https://")): errors.append("URL sumber harus valid")
    if not is_blank(row.get("date_found")) and _recency_score(row.get("date_found")) is None:
        errors.append("tanggal ditemukan harus YYYY-MM-DD atau DD/MM/YYYY")
    return not errors, errors


def _parse_listing_date(value: Any) -> date | None:
    if is_blank(value):
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _recency_score(value: Any, today: date | None = None) -> int | None:
    parsed = _parse_listing_date(value)
    if parsed is None:
        return None
    age = max(0, ((today or date.today()) - parsed).days)
    if age <= 30: return 100
    if age <= 60: return 90
    if age <= 90: return 80
    if age <= 180: return 60
    return 35


def _weighted_median(values: list[tuple[float, float]]) -> float:
    if not values: return 0.0
    ordered = sorted(values, key=lambda x: x[0])
    total = sum(max(0.001, w) for _, w in ordered)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += max(0.001, weight)
        if cumulative >= total / 2: return value
    return ordered[-1][0]


def assess_comparables(comparables: list[dict[str, Any]], subject: dict[str, Any], negotiation_discount_pct: float = 10.0, quick_sale_discount_pct: float = 5.0) -> dict[str, Any]:
    subject_lt = to_float(subject.get("land_area")); subject_lb = to_float(subject.get("building_area"))
    rows, invalid, seen = [], [], set()
    for original in comparables:
        row = dict(original)
        ok, errors = validate_comparable(row)
        if not ok:
            invalid.append({"name": row.get("name", "(tanpa nama)"), "errors": errors}); continue
        url_key = normalize_text(row.get("source_url"))
        fallback_key = "|".join([normalize_text(row.get("name")), str(row.get("price")), str(row.get("land_area")), str(row.get("building_area"))])
        key = url_key or fallback_key
        if key in seen:
            invalid.append({"name": row.get("name"), "errors": ["duplikat URL/listing"]}); continue
        seen.add(key)
        lt, lb, price = to_float(row["land_area"]), to_float(row["building_area"]), to_float(row["price"])
        score = 100.0
        target_complex = normalize_text(subject.get("complex_name"))
        if target_complex and target_complex not in normalize_text(row.get("name")) and target_complex not in normalize_text(row.get("address")):
            score -= 15
        if subject_lt > 0: score -= min(20, abs(lt - subject_lt) / subject_lt * 30)
        if subject_lb > 0 and lb > 0: score -= min(15, abs(lb - subject_lb) / subject_lb * 25)
        target_cert = normalize_text(subject.get("certificate_type"))
        if target_cert and row.get("certificate") and target_cert != normalize_text(row.get("certificate")): score -= 5
        target_access = normalize_text(subject.get("access"))
        if target_access and row.get("access") and target_access != normalize_text(row.get("access")): score -= 5
        target_condition = normalize_text(subject.get("physical_condition"))
        if target_condition and row.get("condition") and target_condition not in normalize_text(row.get("condition")): score -= 5
        price_type = row.get("price_type", "Asking aktif")
        # Only verified transaction prices avoid negotiation discount; asking/marked-sold
        # listings remain unverified price indications and receive the discount.
        negotiated = price if price_type == "Transaksi terverifikasi" else price * (1 - negotiation_discount_pct / 100)
        manual_adj = to_float(row.get("adjustment_pct"))
        adjusted = negotiated * (1 + manual_adj / 100)
        # Each unit-price method is an independent estimate of the subject's TOTAL value.
        # We blend predictions; we never add land value and building value (which would double count).
        land_prediction = adjusted * subject_lt / lt if subject_lt > 0 and lt > 0 else None
        building_prediction = adjusted * subject_lb / lb if subject_lb > 0 and lb > 0 else None
        preds = [x for x in [land_prediction, building_prediction] if x is not None and x > 0]
        if not preds:
            invalid.append({"name": row.get("name"), "errors": ["LT/LB pembanding tidak cukup untuk normalisasi"]}); continue
        predicted_total = sum(preds) / len(preds)
        recency = _recency_score(row.get("date_found")) or 0
        recency_penalty = (100 - recency) * 0.20
        source_adjustment = 5 if price_type == "Transaksi terverifikasi" else (-8 if price_type == "Marked sold / perlu verifikasi" else -2)
        row_score = max(5.0, min(100.0, score - recency_penalty + source_adjustment))
        source_weight = 1.20 if price_type == "Transaksi terverifikasi" else (0.80 if price_type == "Marked sold / perlu verifikasi" else 1.00)
        weight = row_score / 100 * source_weight
        parsed_date = _parse_listing_date(row.get("date_found"))
        age_days = max(0, (date.today() - parsed_date).days) if parsed_date else None
        row.update({"similarity_score": round(row_score, 1), "recency_score": recency, "age_days": age_days, "source_weight": source_weight, "negotiated_price": round(negotiated), "adjusted_price": round(adjusted), "land_unit_price": round(adjusted / lt) if lt > 0 else None, "building_unit_price": round(adjusted / lb) if lb > 0 else None, "land_normalized_value": round(land_prediction) if land_prediction else None, "building_normalized_value": round(building_prediction) if building_prediction else None, "subject_normalized_value": round(predicted_total), "weight": round(weight, 3)})
        rows.append(row)
    count = len(rows)
    if count == 0:
        return {"valid_count": 0, "valid": [], "invalid": invalid, "base_exit": None, "conservative_exit": None, "optimistic_exit": None, "confidence": 0, "status": "INSUFFICIENT_DATA", "median_adjusted": None}
    weighted = [(r["subject_normalized_value"], r["weight"]) for r in rows]
    base = _weighted_median(weighted)
    simple_median = median([r["subject_normalized_value"] for r in rows])
    dispersion = (max(r["subject_normalized_value"] for r in rows) - min(r["subject_normalized_value"] for r in rows)) / max(base, 1)
    avg_score = sum(r["similarity_score"] for r in rows) / count
    confidence = max(0, min(100, avg_score - max(0, dispersion - 0.25) * 40 + min(10, count)))
    land_unit_median = median([r["land_unit_price"] for r in rows if r.get("land_unit_price")]) if any(r.get("land_unit_price") for r in rows) else None
    building_unit_median = median([r["building_unit_price"] for r in rows if r.get("building_unit_price")]) if any(r.get("building_unit_price") for r in rows) else None
    conservative = base * (1 - quick_sale_discount_pct / 100)
    optimistic = base * 1.05
    status = "READY" if count >= 5 and confidence >= 55 else "INSUFFICIENT_DATA"
    return {"valid_count": count, "valid": rows, "invalid": invalid, "base_exit": round(base), "conservative_exit": round(conservative), "optimistic_exit": round(optimistic), "confidence": round(confidence, 1), "simple_median": round(simple_median), "land_unit_price_median": round(land_unit_median) if land_unit_median else None, "building_unit_price_median": round(building_unit_median) if building_unit_median else None, "dispersion_pct": round(dispersion * 100, 1), "status": status, "negotiation_discount_pct": negotiation_discount_pct, "quick_sale_discount_pct": quick_sale_discount_pct}
