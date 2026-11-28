"""Comparable validation and conservative market valuation."""
from __future__ import annotations
from statistics import median
from typing import Any
from datetime import date, datetime
from .utils import to_float, to_bool, is_blank, normalize_text

VALID_PRICE_TYPES = {"Asking aktif", "Marked sold / perlu verifikasi", "Transaksi terverifikasi", "Over kredit / skema kewajiban"}
VALID_CONDITIONS = {"Siap Huni", "Butuh Renovasi", "Hitung Tanah"}
VALID_ACCESS = {"2 Mobil", "1 Mobil", "Gang"}
VALID_MARKET_SEGMENTS = {"Secondary / resale", "Primary / developer", "Tidak diketahui"}
VALID_SELLER_TYPES = {"Pemilik", "Agen", "Developer", "Tidak diketahui"}


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


def _percentile(values: list[float], percentile: float) -> float:
    """Linear-interpolated percentile for small comparable samples."""
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    pos = max(0.0, min(1.0, percentile / 100.0)) * (len(clean) - 1)
    lo = int(pos)
    hi = min(len(clean) - 1, lo + 1)
    frac = pos - lo
    return clean[lo] * (1 - frac) + clean[hi] * frac



def _coordinate_pair(record: dict[str, Any]) -> tuple[float, float] | None:
    """Return valid decimal-degree coordinates when both values are present."""
    try:
        lat = float(record.get("latitude"))
        lon = float(record.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def haversine_distance_km(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    """Straight-line distance between two property pins (not road distance)."""
    import math
    ca, cb = _coordinate_pair(a), _coordinate_pair(b)
    if not ca or not cb:
        return None
    lat1, lon1 = map(math.radians, ca)
    lat2, lon2 = map(math.radians, cb)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, h)))


def _manual_distance_km(row: dict[str, Any]) -> float | None:
    """Read a user-entered straight-line distance when paired coordinates are unavailable."""
    meters = to_float(row.get("distance_m"))
    if meters > 0:
        return meters / 1000.0
    km = to_float(row.get("distance_km"))
    return km if km > 0 else None


def _proximity_score(distance_km: float | None) -> float | None:
    if distance_km is None:
        return None
    if distance_km <= 0.5: return 100.0
    if distance_km <= 1: return 95.0
    if distance_km <= 2: return 90.0
    if distance_km <= 5: return 80.0
    if distance_km <= 10: return 65.0
    if distance_km <= 20: return 45.0
    return 25.0

def assess_comparables(
    comparables: list[dict[str, Any]],
    subject: dict[str, Any],
    negotiation_discount_pct: float = 10.0,
    quick_sale_discount_pct: float = 5.0,
    njop_market_weight_pct: float = 10.0,
) -> dict[str, Any]:
    subject_lt = to_float(subject.get("land_area")); subject_lb = to_float(subject.get("building_area"))
    subject_njop = to_float(subject.get("njop"))
    subject_bedrooms = to_float(subject.get("bedrooms"))
    subject_bathrooms = to_float(subject.get("bathrooms"))
    subject_road_width = to_float(subject.get("road_width_m"))
    subject_orientation = normalize_text(subject.get("orientation"))
    rows, invalid, secondary_only, seen = [], [], [], set()
    seen_underlying_properties: set[str] = set()
    for original in comparables:
        row = dict(original)
        ok, errors = validate_comparable(row)
        if not ok:
            invalid.append({"name": row.get("name", "(tanpa nama)"), "errors": errors}); continue
        if to_bool(row.get("ai_exclude_from_primary", False)):
            invalid.append({"name": row.get("name", "(tanpa nama)"), "errors": ["dikeluarkan dari indikasi utama setelah pengguna meninjau saran AI"]})
            continue
        price_type = row.get("price_type") if not is_blank(row.get("price_type")) else "Asking aktif"
        if price_type == "Over kredit / skema kewajiban":
            secondary_only.append({
                "name": row.get("name", "(tanpa nama)"),
                "price": to_float(row.get("price")),
                "land_area": to_float(row.get("land_area")) or None,
                "building_area": to_float(row.get("building_area")) or None,
                "source_url": row.get("source_url", ""),
                "reason": "Skema DP + sisa kewajiban/cicilan bukan harga tunai yang setara. Perlu saldo pokok terkini, biaya take-over, tunggakan dan persetujuan kreditur sebelum dapat dikonversi.",
            })
            continue
        url_scope = str(row.get("source_url_scope") or "")
        # Prefer an explicit underlying-property key to deduplicate the same
        # physical house advertised across Facebook, Pinhome, portals, and agents.
        underlying_id = normalize_text(row.get("underlying_property_id"))
        if underlying_id and underlying_id in seen_underlying_properties:
            invalid.append({"name": row.get("name"), "errors": ["duplikat objek fisik (underlying_property_id)"]}); continue
        # A shared portal root is provenance, not a unique listing URL.
        url_key = normalize_text(row.get("source_url")) if not is_blank(row.get("source_url")) and url_scope == "Listing individual" else ""
        fallback_key = "|".join([
            normalize_text(row.get("address") or row.get("name")),
            str(round(to_float(row.get("price")) / 1_000_000)),
            str(round(to_float(row.get("land_area")))),
            str(round(to_float(row.get("building_area")))),
        ])
        key = underlying_id or url_key or fallback_key
        if key in seen:
            invalid.append({"name": row.get("name"), "errors": ["duplikat URL/objek listing"]}); continue
        seen.add(key)
        if underlying_id:
            seen_underlying_properties.add(underlying_id)
        lt, lb, price = to_float(row.get("land_area")), to_float(row.get("building_area")), to_float(row.get("price"))
        score = 100.0
        distance_km = haversine_distance_km(subject, row)
        distance_source = "Koordinat Haversine (jarak garis lurus)" if distance_km is not None else ""
        if distance_km is None:
            distance_km = _manual_distance_km(row)
            if distance_km is not None:
                distance_source = "Jarak garis lurus diinput pengguna (meter/km)"
        proximity_score = _proximity_score(distance_km)
        target_complex = normalize_text(subject.get("complex_name"))
        if proximity_score is not None:
            # Geographic proximity overrides administrative/complex-name mismatch:
            # a comparable 500m away remains highly relevant across village lines.
            score -= (100.0 - proximity_score) * 0.25
            distance_band = (
                "Sangat dekat (≤500 m)" if distance_km <= 0.5 else
                "Dekat (≤1 km)" if distance_km <= 1 else
                "Radius lokal (≤2 km)" if distance_km <= 2 else
                "Sekitar area (≤5 km)" if distance_km <= 5 else
                "Wilayah sekitar (≤10 km)" if distance_km <= 10 else
                "Perlu penyesuaian jarak (>10 km)"
            )
            location_method = distance_source
        else:
            distance_band = "Jarak belum terukur — koordinat diperlukan"
            location_method = "Nama/alamat; tidak ada koordinat berpasangan"
            if target_complex and target_complex not in normalize_text(row.get("name")) and target_complex not in normalize_text(row.get("address")):
                # Keep cross-complex listings eligible. This is only a mild
                # uncertainty penalty when coordinates cannot be compared.
                score -= 3
        if subject_lt > 0: score -= min(20, abs(lt - subject_lt) / subject_lt * 30)
        if subject_lb > 0 and lb > 0: score -= min(15, abs(lb - subject_lb) / subject_lb * 25)
        # Additional physical attributes used as similarity indicators; they
        # do not automatically alter price without an explicit adjustment.
        comp_bedrooms = to_float(row.get("bedrooms"))
        comp_bathrooms = to_float(row.get("bathrooms"))
        if subject_bedrooms > 0 and comp_bedrooms > 0:
            score -= min(5, abs(comp_bedrooms - subject_bedrooms) * 2.0)
        if subject_bathrooms > 0 and comp_bathrooms > 0:
            score -= min(4, abs(comp_bathrooms - subject_bathrooms) * 2.0)
        comp_road_width = to_float(row.get("road_width_m"))
        if subject_road_width > 0 and comp_road_width > 0:
            score -= min(5, abs(comp_road_width - subject_road_width) * 1.5)
        comp_orientation = normalize_text(row.get("orientation"))
        if subject_orientation and comp_orientation and subject_orientation != comp_orientation:
            score -= 1.5
        target_cert = normalize_text(subject.get("certificate_type"))
        if target_cert and not is_blank(row.get("certificate")) and target_cert != normalize_text(row.get("certificate")): score -= 5
        target_access = normalize_text(subject.get("access"))
        if target_access and not is_blank(row.get("access")) and target_access != normalize_text(row.get("access")): score -= 5
        target_condition = normalize_text(subject.get("physical_condition"))
        if target_condition and not is_blank(row.get("condition")) and target_condition not in normalize_text(row.get("condition")): score -= 5
        # A promotion is deducted only when its cash-equivalent value is verified
        # and explicitly entered. KPR-no-DP/free-fee claims are not blanket 20-25%
        # price discounts. Asking-price negotiation remains a separate assumption.
        promo_value = max(0.0, to_float(row.get("verified_promotion_value"))) if to_bool(row.get("promotion_value_verified", False)) else 0.0
        effective_price = max(0.0, price - min(price, promo_value))
        # Only verified closing/transaction prices avoid the negotiation haircut.
        negotiated = effective_price if price_type == "Transaksi terverifikasi" else effective_price * (1 - negotiation_discount_pct / 100)
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
        # date_found proves when the user collected the evidence; it is not the
        # listing publication date. When publication date is unavailable, retain a
        # moderate freshness score and a modest uncertainty penalty rather than
        # treating the listing as very old. This keeps genuine current research usable.
        recency_value = _recency_score(row.get("listing_date"))
        # Missing publication dates are common in portal snippets. They lower
        # freshness confidence modestly, but must not count twice as a severe
        # evidence defect when the user has just captured an active listing.
        recency = recency_value if recency_value is not None else 65
        recency_penalty = (100 - recency) * 0.20
        missing_penalty = 0
        missing_fields = []
        for key, penalty, label in [
            ("condition", 4, "kondisi"), ("access", 3, "akses"),
            ("certificate", 2, "sertifikat"), ("building_area", 5, "LB"),
            ("source_url", 5, "URL sumber"), ("date_found", 3, "tanggal ditemukan"),
            ("listing_date", 1, "tanggal publikasi iklan (tidak diketahui)"),
        ]:
            if is_blank(row.get(key)):
                missing_penalty += penalty
                missing_fields.append(label)
        url_scope = str(row.get("source_url_scope") or "")
        if str(row.get("source_url") or "").startswith(("http://", "https://")) and url_scope != "Listing individual":
            # A portal home page is usable provenance for indicative valuation;
            # it is weaker than an individual listing link, but not a reason to
            # withhold the estimate. The stronger individual-URL requirement
            # belongs to the final GO audit gate below.
            scope_penalty = 2 if url_scope == "Portal/domain only" else 4
            missing_penalty += scope_penalty
            missing_fields.append("URL portal belum membuktikan halaman listing individual")
        market_segment = str(row.get("market_segment") or "Tidak diketahui")
        if market_segment not in VALID_MARKET_SEGMENTS:
            market_segment = "Tidak diketahui"
        market_segment_factor = {
            "Secondary / resale": 1.00,
            "Primary / developer": 0.15,
            "Tidak diketahui": 0.35,
        }[market_segment]
        if market_segment == "Tidak diketahui":
            missing_penalty += 2
            missing_fields.append("segmen primary/secondary belum diketahui")
        source_adjustment = 5 if price_type == "Transaksi terverifikasi" else (-8 if price_type == "Marked sold / perlu verifikasi" else -2)
        row_score = max(5.0, min(100.0, score - recency_penalty - missing_penalty + source_adjustment))
        source_weight = 1.20 if price_type == "Transaksi terverifikasi" else (0.80 if price_type == "Marked sold / perlu verifikasi" else 1.00)
        weight = row_score / 100 * source_weight * market_segment_factor
        parsed_date = _parse_listing_date(row.get("date_found"))
        age_days = max(0, (date.today() - parsed_date).days) if parsed_date else None
        comparable_njop = to_float(row.get("njop"))
        row.update({
            "similarity_score": round(row_score, 1), "recency_score": recency, "age_days": age_days,
            "source_weight": source_weight, "market_segment": market_segment,
            "seller_type": row.get("seller_type") or "Tidak diketahui",
            "underlying_property_id": row.get("underlying_property_id") or "",
            "market_segment_factor": market_segment_factor, "missing_quality_fields": missing_fields,
            "original_asking_price": round(price),
            "verified_promotion_value_used": round(promo_value),
            "effective_asking_price": round(effective_price),
            "negotiated_price": round(negotiated), "adjusted_price": round(adjusted),
            "land_unit_price": round(adjusted / lt) if lt > 0 else None,
            "building_unit_price": round(adjusted / lb) if lb > 0 else None,
            "land_normalized_value": round(land_prediction) if land_prediction else None,
            "building_normalized_value": round(building_prediction) if building_prediction else None,
            "subject_normalized_value": round(predicted_total), "weight": round(weight, 3),
            "market_to_njop_ratio": round(adjusted / comparable_njop, 4) if comparable_njop > 0 else None,
            "distance_km": round(distance_km, 3) if distance_km is not None else None,
            "distance_band": distance_band,
            "proximity_score": round(proximity_score, 1) if proximity_score is not None else None,
            "location_method": location_method,
        })
        rows.append(row)
    total_valid_count = len(rows)
    if total_valid_count == 0:
        return {
            "valid_count": 0, "valuation_comparable_count": 0, "secondary_comparable_count": 0,
            "primary_competition_count": 0, "primary_competition_median": None,
            "go_grade_count": 0, "valid": [], "valuation_rows": [], "invalid": invalid, "secondary_only": secondary_only,
            "estimate_status": "INSUFFICIENT", "estimate_label": "Belum ada cukup data harga dan luas yang dapat dihitung",
            "base_exit": None, "comparable_base_exit": None, "njop_indicated_exit": None,
            "njop_comparable_count": 0, "njop_market_ratio": None, "subject_njop": subject_njop or None,
            "njop_weight_pct_used": 0.0, "conservative_exit": None, "optimistic_exit": None,
            "market_range_low": None, "market_range_high": None, "data_uncertainty_discount_pct": None,
            "conservative_discount_used_pct": None, "dispersion_iqr_pct": None,
            "confidence": 0, "status": "INSUFFICIENT_DATA", "median_adjusted": None,
            "direct_url_count": 0, "individual_listing_url_count": 0,
            "listing_date_missing_count": 0, "date_found_missing_count": 0,
            "unconfirmed_url_count": 0, "quality_notes": [],
        }

    secondary_rows = [r for r in rows if r.get("market_segment") == "Secondary / resale"]
    unknown_rows = [r for r in rows if r.get("market_segment") == "Tidak diketahui"]
    primary_rows = [r for r in rows if r.get("market_segment") == "Primary / developer"]
    # For a resale/auction subject, primary developer inventory is competition,
    # not a direct substitute for the resale ARV. Use secondary comparables first;
    # unknown-segment listings may supplement them at a reduced weight. If there
    # is no secondary evidence, unknown rows are used. Primary-only evidence is a
    # last-resort weak indication and is explicitly flagged.
    if secondary_rows:
        valuation_rows = list(secondary_rows)
        for row in unknown_rows:
            row["valuation_role"] = "Supplementary unknown segment (reduced weight)"
            row["weight"] = round(to_float(row.get("weight")) * 0.35, 3)
            valuation_rows.append(row)
        valuation_mode = "SECONDARY_LED"
    elif unknown_rows:
        valuation_rows = list(unknown_rows)
        valuation_mode = "UNKNOWN_SEGMENT_ONLY"
    else:
        valuation_rows = list(primary_rows)
        valuation_mode = "PRIMARY_ONLY_WEAK_PROXY"
    valuation_ids = {id(r) for r in valuation_rows}
    for row in rows:
        row["valuation_in_primary_arv"] = id(row) in valuation_ids
        if row.get("market_segment") == "Primary / developer":
            row["valuation_role"] = "Competition / developer ceiling; excluded from resale ARV while secondary evidence exists" if secondary_rows or unknown_rows else "Last-resort primary-only proxy; weak evidence"
        elif row.get("market_segment") == "Secondary / resale":
            row["valuation_role"] = "Primary resale comparable"
        elif row.get("valuation_role") is None:
            row["valuation_role"] = "Unknown segment"

    count = len(valuation_rows)
    normalized_values = [float(r["subject_normalized_value"]) for r in valuation_rows]
    q25 = _percentile(normalized_values, 25)
    q50 = _percentile(normalized_values, 50)
    q75 = _percentile(normalized_values, 75)
    iqr = max(0.0, q75 - q25)
    # Flag extreme observations for transparency and down-weight them in the
    # selected valuation pool. Primary listings remain visible as competition.
    if count >= 5 and iqr > 0:
        lower_fence, upper_fence = q25 - 1.5 * iqr, q75 + 1.5 * iqr
        for row in valuation_rows:
            value = to_float(row.get("subject_normalized_value"))
            row["outlier_flag"] = value < lower_fence or value > upper_fence
            if row["outlier_flag"]:
                row["weight"] = round(max(0.01, to_float(row.get("weight")) * 0.35), 3)
                row["valuation_note"] = "Observasi jauh dari rentang mayoritas; bobot diturunkan, perlu pemeriksaan manual."
            else:
                row["outlier_flag"] = False
                row["valuation_note"] = ""
    else:
        for row in valuation_rows:
            row["outlier_flag"] = False
            row["valuation_note"] = ""
    weighted = [(r["subject_normalized_value"], r["weight"]) for r in valuation_rows]
    comparable_base = _weighted_median(weighted)
    simple_median = median(normalized_values)
    primary_competition_values = [float(r["subject_normalized_value"]) for r in primary_rows]
    primary_competition_median = median(primary_competition_values) if primary_competition_values else None

    # NJOP is not market value and is never converted using an arbitrary national
    # multiplier. It is used as a secondary calibrated reference only when at least
    # three comparable properties also have their own NJOP values. The local
    # market-to-NJOP ratio is learned from those paired observations.
    njop_pairs = [
        (r["market_to_njop_ratio"], r["weight"])
        for r in valuation_rows
        if r.get("market_to_njop_ratio") is not None and r["market_to_njop_ratio"] > 0
    ]
    njop_market_ratio = _weighted_median(njop_pairs) if len(njop_pairs) >= 3 else None
    njop_indicated = subject_njop * njop_market_ratio if subject_njop > 0 and njop_market_ratio else None
    njop_weight_used = max(0.0, min(25.0, to_float(njop_market_weight_pct))) if njop_indicated is not None else 0.0
    base = comparable_base * (1 - njop_weight_used / 100) + (njop_indicated or 0) * (njop_weight_used / 100)
    # Sample dispersion informs the uncertainty band, not an arbitrary haircut
    # to the central market value. Quick-sale pricing is a separate, user-tunable
    # commercial decision. This prevents one comparable from automatically
    # forcing the central ARV down by 24% while still showing a wide risk range.
    spread = ((max(normalized_values) - min(normalized_values)) if count < 4 else iqr)
    dispersion = spread / max(comparable_base, 1)
    dispersion_iqr_pct = (iqr / max(comparable_base, 1)) * 100
    avg_score = sum(r["similarity_score"] for r in valuation_rows) / count
    sample_score = min(30.0, count * 3.3)
    dispersion_penalty = min(28.0, max(0.0, dispersion - 0.15) * 35.0)
    confidence = max(0.0, min(100.0, avg_score * 0.56 + sample_score - dispersion_penalty))
    if valuation_mode == "PRIMARY_ONLY_WEAK_PROXY":
        confidence = min(confidence, 40.0)
    land_unit_median = median([r["land_unit_price"] for r in valuation_rows if r.get("land_unit_price")]) if any(r.get("land_unit_price") for r in valuation_rows) else None
    building_unit_median = median([r["building_unit_price"] for r in valuation_rows if r.get("building_unit_price")]) if any(r.get("building_unit_price") for r in valuation_rows) else None
    if count == 1: sample_uncertainty = 24.0
    elif count == 2: sample_uncertainty = 18.0
    elif count == 3: sample_uncertainty = 14.0
    elif count == 4: sample_uncertainty = 11.0
    elif count == 5: sample_uncertainty = 9.0
    else: sample_uncertainty = max(5.0, 9.0 - (count - 5) * 0.5)
    quality_uncertainty = max(0.0, (85.0 - avg_score) * 0.06)
    spread_uncertainty = min(12.0, max(0.0, dispersion * 18.0))
    data_uncertainty_discount = min(35.0, sample_uncertainty + quality_uncertainty + spread_uncertainty)
    conservative_discount_used = max(0.0, min(50.0, to_float(quick_sale_discount_pct)))
    conservative = base * (1 - conservative_discount_used / 100)
    optimistic_uplift = min(25.0, max(5.0, data_uncertainty_discount * 0.65))
    optimistic = base * (1 + optimistic_uplift / 100)
    uncertainty_low = base * (1 - data_uncertainty_discount / 100)
    uncertainty_high = base * (1 + data_uncertainty_discount / 100)
    market_range_low = min(q25 if q25 > 0 else base, uncertainty_low)
    market_range_high = max(q75 if q75 > 0 else base, uncertainty_high, optimistic)
    direct_url_count = sum(1 for r in rows if str(r.get("source_url") or "").startswith(("http://", "https://")))
    individual_listing_url_count = sum(1 for r in rows if str(r.get("source_url_scope") or "") == "Listing individual")
    # GO-grade resale evidence is checked on the valuation pool, not on developer
    # competition listings that were deliberately excluded from secondary ARV.
    go_grade_count = sum(
        1 for r in valuation_rows
        if str(r.get("source_url") or "").startswith(("http://", "https://"))
        and str(r.get("source_url_scope") or "") == "Listing individual"
        and not is_blank(r.get("date_found"))
    )
    status = "READY" if count >= 5 and go_grade_count >= 5 and confidence >= 55 else "PRELIMINARY"
    listing_date_missing_count = sum(1 for r in rows if is_blank(r.get("listing_date")))
    date_found_missing_count = sum(1 for r in rows if is_blank(r.get("date_found")))
    unconfirmed_url_count = sum(
        1 for r in rows
        if str(r.get("source_url") or "").startswith(("http://", "https://"))
        and str(r.get("source_url_scope") or "") != "Listing individual"
    )
    quality_notes = ["Pembanding tidak dibatasi oleh desa/kecamatan/kompleks. Jika koordinat target dan pembanding tersedia, jarak garis lurus Haversine dipakai sebagai faktor relevansi; jarak 500 m mendapat skor kedekatan tertinggi. Jika koordinat tidak tersedia, jarak tidak dapat diklaim dan pengguna dianjurkan mengisinya."]
    if listing_date_missing_count:
        quality_notes.append(f"{listing_date_missing_count} listing tidak mencantumkan tanggal publikasi; ini mengurangi kepastian umur iklan, tetapi bukan syarat GO.")
    if date_found_missing_count:
        quality_notes.append(f"{date_found_missing_count} listing belum memiliki tanggal ditemukan/dikumpulkan.")
    if unconfirmed_url_count:
        quality_notes.append(f"{unconfirmed_url_count} URL belum dikonfirmasi sebagai halaman listing individual.")
    if secondary_rows and primary_rows:
        quality_notes.append(f"{len(primary_rows)} listing primary/developer dipisahkan sebagai informasi persaingan; tidak dicampur ke median ARV resale karena target underwriting diasumsikan rumah secondary/lelang.")
    if not secondary_rows and primary_rows and not unknown_rows:
        quality_notes.append("Tidak ada pembanding secondary yang teridentifikasi. Indikasi memakai listing primary sebagai proxy lemah dan confidence dibatasi; jangan jadikan satu-satunya dasar GO.")
    if unknown_rows:
        quality_notes.append(f"{len(unknown_rows)} listing belum memiliki klasifikasi primary/secondary; digunakan sebagai data tambahan dengan ketidakpastian lebih tinggi atau fallback.")
    verified_promotions = sum(1 for r in rows if to_float(r.get("verified_promotion_value_used")) > 0)
    unverified_promotion_claims = sum(1 for r in rows if str(r.get("promotion_claims") or "").strip() and to_float(r.get("verified_promotion_value_used")) <= 0)
    if unverified_promotion_claims:
        quality_notes.append(f"{unverified_promotion_claims} listing menyebut promosi tanpa nilai rupiah terverifikasi; tidak ada potongan harga promosi otomatis yang diterapkan.")

    return {
        "valid_count": total_valid_count, "valuation_comparable_count": count,
        "secondary_comparable_count": len(secondary_rows), "unknown_segment_count": len(unknown_rows),
        "primary_competition_count": len(primary_rows),
        "primary_competition_median": round(primary_competition_median) if primary_competition_median else None,
        "verified_promotion_count": verified_promotions,
        "unverified_promotion_claim_count": unverified_promotion_claims,
        "valuation_mode": valuation_mode,
        "go_grade_count": go_grade_count, "valid": rows, "valuation_rows": valuation_rows, "invalid": invalid, "secondary_only": secondary_only,
        "estimate_status": "INDICATIVE_AVAILABLE" if count >= 3 else "LOW_SAMPLE" if count > 0 else "INSUFFICIENT",
        "estimate_label": "Estimasi indikatif tersedia" if count >= 3 else "Estimasi awal dengan sampel terbatas" if count > 0 else "Belum ada cukup data harga dan luas yang dapat dihitung",
        "base_exit": round(base), "comparable_base_exit": round(comparable_base),
        "njop_indicated_exit": round(njop_indicated) if njop_indicated is not None else None,
        "njop_comparable_count": len(njop_pairs), "njop_market_ratio": round(njop_market_ratio, 4) if njop_market_ratio is not None else None,
        "subject_njop": subject_njop or None, "njop_weight_pct_used": njop_weight_used,
        "conservative_exit": round(conservative), "optimistic_exit": round(optimistic),
        "market_range_low": round(market_range_low), "market_range_high": round(market_range_high),
        "data_uncertainty_discount_pct": round(data_uncertainty_discount, 1),
        "conservative_discount_used_pct": round(conservative_discount_used, 1),
        "dispersion_iqr_pct": round(dispersion_iqr_pct, 1),
        "valuation_method": "Secondary-led weighted median + normalized land/building indicators + separate primary competition + NJOP calibration (if paired local data exists)",
        "valuation_note": "ARV indikatif. Quick-sale discount terpisah dari rentang ketidakpastian bukti; listing primary/developer dipisahkan dari resale ARV bila data secondary tersedia. Bukan appraisal dan bukan kepastian harga transaksi.",
        "confidence": round(confidence, 1),
        "confidence_band": "Baik" if confidence >= 70 else "Cukup" if confidence >= 55 else "Rendah",
        "simple_median": round(simple_median),
        "land_unit_price_median": round(land_unit_median) if land_unit_median else None,
        "building_unit_price_median": round(building_unit_median) if building_unit_median else None,
        "dispersion_pct": round(dispersion * 100, 1), "direct_url_count": direct_url_count,
        "individual_listing_url_count": individual_listing_url_count,
        "listing_date_missing_count": listing_date_missing_count,
        "date_found_missing_count": date_found_missing_count,
        "unconfirmed_url_count": unconfirmed_url_count, "quality_notes": quality_notes,
        "status": status, "negotiation_discount_pct": negotiation_discount_pct,
        "quick_sale_discount_pct": quick_sale_discount_pct,
    }
