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
    """Validate minimum evidence needed for a usable price indication.

    Condition/access/LB/direct URL are quality attributes, not universal hard
    requirements. Some genuine listing narratives omit them; missing fields are
    penalized in confidence rather than causing the entire row to be discarded.
    """
    errors = []
    if is_blank(row.get("name")):
        errors.append("nama/alamat listing belum diisi")
    if to_float(row.get("price")) <= 0:
        errors.append("harga harus lebih dari nol")

    land = to_float(row.get("land_area"))
    building = to_float(row.get("building_area"))
    if land <= 0 and building <= 0:
        errors.append("LT atau LB minimal salah satu harus tersedia dan lebih dari nol")
    if land < 0 or building < 0:
        errors.append("LT/LB tidak boleh negatif")

    platforms = row.get("source_platforms") if not is_blank(row.get("source_platforms")) else (row.get("source_site") or "")
    evidence = row.get("source_evidence") if not is_blank(row.get("source_evidence")) else (row.get("source_reference") or "")
    url = "" if is_blank(row.get("source_url")) else str(row.get("source_url")).strip()
    has_platforms = bool(str(platforms).strip()) if not isinstance(platforms, list) else bool(platforms)
    if not url and not has_platforms and not str(evidence).strip():
        errors.append("sumber listing belum disebutkan (platform, URL, atau kutipan sumber wajib ada)")
    if url and not url.startswith(("http://", "https://")):
        errors.append("URL sumber tidak valid; kosongkan bila URL langsung memang tidak tersedia")

    if not is_blank(row.get("condition")) and row.get("condition") not in VALID_CONDITIONS:
        errors.append("kondisi tidak dikenali; gunakan Siap Huni / Butuh Renovasi / Hitung Tanah atau kosongkan")
    if not is_blank(row.get("access")) and row.get("access") not in VALID_ACCESS:
        errors.append("akses tidak dikenali; gunakan 2 Mobil / 1 Mobil / Gang atau kosongkan")
    price_type = row.get("price_type") if not is_blank(row.get("price_type")) else "Asking aktif"
    if price_type not in VALID_PRICE_TYPES:
        errors.append("jenis harga tidak dikenali")
    for date_field in ("date_found", "listing_date"):
        if not is_blank(row.get(date_field)) and _recency_score(row.get(date_field)) is None:
            errors.append(f"{date_field} harus YYYY-MM-DD atau DD/MM/YYYY")
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
        url_key = normalize_text(row.get("source_url")) if not is_blank(row.get("source_url")) else ""
        fallback_key = "|".join([normalize_text(row.get("name")), str(row.get("price")), str(row.get("land_area")), str(row.get("building_area"))])
        key = url_key or fallback_key
        if key in seen:
            invalid.append({"name": row.get("name"), "errors": ["duplikat URL/listing"]}); continue
        seen.add(key)
        lt, lb, price = to_float(row.get("land_area")), to_float(row.get("building_area")), to_float(row.get("price"))
        score = 100.0
        target_complex = normalize_text(subject.get("complex_name"))
        if target_complex and target_complex not in normalize_text(row.get("name")) and target_complex not in normalize_text(row.get("address")):
            score -= 15
        if subject_lt > 0: score -= min(20, abs(lt - subject_lt) / subject_lt * 30)
        if subject_lb > 0 and lb > 0: score -= min(15, abs(lb - subject_lb) / subject_lb * 25)
        target_cert = normalize_text(subject.get("certificate_type"))
        if target_cert and not is_blank(row.get("certificate")) and target_cert != normalize_text(row.get("certificate")): score -= 5
        target_access = normalize_text(subject.get("access"))
        if target_access and not is_blank(row.get("access")) and target_access != normalize_text(row.get("access")): score -= 5
        target_condition = normalize_text(subject.get("physical_condition"))
        if target_condition and not is_blank(row.get("condition")) and target_condition not in normalize_text(row.get("condition")): score -= 5
        price_type = row.get("price_type") if not is_blank(row.get("price_type")) else "Asking aktif"
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
        # Do not mistake the date the user copied/imported a listing for its publication
        # date. If listing_date is unknown, freshness remains uncertain and receives a
        # conservative default score; date_found is retained for audit only.
        recency_value = _recency_score(row.get("listing_date"))
        recency = recency_value if recency_value is not None else 35
        recency_penalty = (100 - recency) * 0.20
        missing_penalty = 0
        missing_fields = []
        for key, penalty, label in [
            ("condition", 7, "kondisi"), ("access", 5, "akses"),
            ("certificate", 3, "sertifikat"), ("building_area", 7, "LB"),
            ("source_url", 6, "URL sumber"), ("date_found", 3, "tanggal ditemukan"),
            ("listing_date", 4, "tanggal publikasi iklan"),
        ]:
            if is_blank(row.get(key)):
                missing_penalty += penalty
                missing_fields.append(label)
        url_scope = str(row.get("source_url_scope") or "")
        if str(row.get("source_url") or "").startswith(("http://", "https://")) and url_scope != "Listing individual":
            missing_penalty += 6
            missing_fields.append("URL belum membuktikan halaman listing individual")
        source_adjustment = 5 if price_type == "Transaksi terverifikasi" else (-8 if price_type == "Marked sold / perlu verifikasi" else -2)
        row_score = max(5.0, min(100.0, score - recency_penalty - missing_penalty + source_adjustment))
        source_weight = 1.20 if price_type == "Transaksi terverifikasi" else (0.80 if price_type == "Marked sold / perlu verifikasi" else 1.00)
        weight = row_score / 100 * source_weight
        parsed_date = _parse_listing_date(row.get("date_found"))
        age_days = max(0, (date.today() - parsed_date).days) if parsed_date else None
        row.update({"similarity_score": round(row_score, 1), "recency_score": recency, "age_days": age_days, "source_weight": source_weight, "missing_quality_fields": missing_fields, "negotiated_price": round(negotiated), "adjusted_price": round(adjusted), "land_unit_price": round(adjusted / lt) if lt > 0 else None, "building_unit_price": round(adjusted / lb) if lb > 0 else None, "land_normalized_value": round(land_prediction) if land_prediction else None, "building_normalized_value": round(building_prediction) if building_prediction else None, "subject_normalized_value": round(predicted_total), "weight": round(weight, 3)})
        rows.append(row)
    count = len(rows)
    if count == 0:
        return {"valid_count": 0, "go_grade_count": 0, "valid": [], "invalid": invalid, "base_exit": None, "conservative_exit": None, "optimistic_exit": None, "confidence": 0, "status": "INSUFFICIENT_DATA", "median_adjusted": None, "direct_url_count": 0}
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
    direct_url_count = sum(1 for r in rows if str(r.get("source_url") or "").startswith(("http://", "https://")))
    individual_listing_url_count = sum(1 for r in rows if str(r.get("source_url_scope") or "") == "Listing individual")
    # GO-grade evidence must be traceable to an individual source listing and carry
    # a system/user capture date. Portal names alone are enough for preliminary math,
    # but not enough for a final investment approval audit trail.
    go_grade_count = sum(
        1 for r in rows
        if str(r.get("source_url") or "").startswith(("http://", "https://"))
        and str(r.get("source_url_scope") or "") == "Listing individual"
        and not is_blank(r.get("date_found"))
    )
    status = "READY" if count >= 5 and go_grade_count >= 5 and confidence >= 55 else "PRELIMINARY"
    return {"valid_count": count, "go_grade_count": go_grade_count, "valid": rows, "invalid": invalid, "base_exit": round(base), "conservative_exit": round(conservative), "optimistic_exit": round(optimistic), "confidence": round(confidence, 1), "simple_median": round(simple_median), "land_unit_price_median": round(land_unit_median) if land_unit_median else None, "building_unit_price_median": round(building_unit_median) if building_unit_median else None, "dispersion_pct": round(dispersion * 100, 1), "direct_url_count": direct_url_count, "individual_listing_url_count": individual_listing_url_count, "status": status, "negotiation_discount_pct": negotiation_discount_pct, "quick_sale_discount_pct": quick_sale_discount_pct}
