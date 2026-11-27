from core.market_engine import assess_comparables, validate_comparable
from services.comparable_importer import parse_comparable_paste


def comp(i):
    return {"name":f"Listing {i}","address":f"Komplek A blok {i}","price":350_000_000+i*5_000_000,"land_area":100,"building_area":90,"condition":"Siap Huni","access":"1 Mobil","price_type":"Asking aktif","certificate":"SHM","source_url":f"https://example.com/{i}","source_platforms":"Rumah123","date_found":"2026-11-13","adjustment_pct":0}


def test_valid_comparable():
    ok, errors = validate_comparable(comp(1))
    assert ok and not errors


def test_market_needs_five_valid_rows():
    rows = [comp(i) for i in range(4)]
    m = assess_comparables(rows, {"land_area":100,"building_area":90})
    assert m["valid_count"] == 4
    assert m["status"] == "PRELIMINARY"


def test_five_rows_produce_conservative_below_base():
    rows = [comp(i) for i in range(5)]
    m = assess_comparables(rows, {"land_area":100,"building_area":90})
    assert m["valid_count"] == 5
    assert m["conservative_exit"] < m["base_exit"]


def test_paste_tsv_import():
    text = "Alamat / Nama Listing\tHarga Listing (IDR)\tLuas Tanah (m2)\tLuas Bangunan (m2)\tKondisi\tAkses Jalan\tURL Sumber\tTanggal Ditemukan\nListing A\tRp390.000.000\t100\t90\tSiap Huni\t1 Mobil\thttps://example.com/a\t2026-11-13"
    rows = parse_comparable_paste(text)
    assert len(rows) == 1
    assert rows[0]["price"] == 390_000_000
    assert rows[0]["land_area"] == 100


def test_missing_condition_or_access_is_kept_unknown_and_penalized():
    row = comp(1)
    row["condition"] = ""
    row["access"] = ""
    ok, errors = validate_comparable(row)
    assert ok, errors
    market = assess_comparables([row], {"land_area": 100, "building_area": 90})
    assert "kondisi" in market["valid"][0]["missing_quality_fields"]
    assert "akses" in market["valid"][0]["missing_quality_fields"]


def test_marked_sold_unverified_listing_still_gets_negotiation_discount():
    row = comp(1)
    row["price_type"] = "Marked sold / perlu verifikasi"
    market = assess_comparables([row], {"land_area":100,"building_area":90}, negotiation_discount_pct=10)
    assert market["valid"][0]["negotiated_price"] == round(row["price"] * .9)


def test_missing_condition_access_lb_and_direct_url_are_quality_penalties_not_auto_reject():
    row = comp(8)
    row.update({"building_area": None, "condition": None, "access": None, "source_url": "", "source_platforms": "Pinhome", "date_found": "2026-11-13"})
    ok, errors = validate_comparable(row)
    assert ok, errors
    market = assess_comparables([row], {"land_area": 100, "building_area": 90})
    assert market["valid_count"] == 1
    assert "LB" in market["valid"][0]["missing_quality_fields"]
    assert "URL sumber" in market["valid"][0]["missing_quality_fields"]


def test_source_platform_without_direct_url_is_accepted_as_provenance():
    row = comp(9)
    row.update({"source_url": "", "source_platforms": "Rumah123; OLX Indonesia"})
    ok, errors = validate_comparable(row)
    assert ok, errors



def test_five_direct_listings_with_capture_date_can_be_ready_without_publication_dates():
    rows = [comp(i) for i in range(5)]
    for row in rows:
        row["source_url_scope"] = "Listing individual"
        row["listing_date"] = ""
    market = assess_comparables(rows, {"land_area": 100, "building_area": 90})
    assert market["valid_count"] == 5
    assert market["go_grade_count"] == 5
    assert market["listing_date_missing_count"] == 5
    assert market["status"] == "READY"


def test_njop_reference_is_calibrated_from_at_least_three_local_pairs():
    rows = [comp(i) for i in range(5)]
    for row in rows:
        row["source_url_scope"] = "Listing individual"
        row["njop"] = 200_000_000
        row["listing_date"] = ""
    market = assess_comparables(
        rows,
        {"land_area": 100, "building_area": 90, "njop": 250_000_000},
        njop_market_weight_pct=10,
    )
    assert market["njop_comparable_count"] == 5
    assert market["njop_indicated_exit"] is not None
    assert market["njop_weight_pct_used"] == 10
    assert market["base_exit"] != market["comparable_base_exit"]


def test_subject_njop_is_not_applied_without_three_comparable_njop_pairs():
    rows = [comp(i) for i in range(5)]
    for row in rows:
        row["source_url_scope"] = "Listing individual"
    rows[0]["njop"] = 180_000_000
    rows[1]["njop"] = 190_000_000
    market = assess_comparables(rows, {"land_area": 100, "building_area": 90, "njop": 250_000_000})
    assert market["njop_indicated_exit"] is None
    assert market["njop_weight_pct_used"] == 0
    assert market["base_exit"] == market["comparable_base_exit"]


def test_sparse_sample_produces_indicative_arv_with_wider_uncertainty_range():
    row = comp(101)
    row["source_url_scope"] = "Listing individual"
    market = assess_comparables([row], {"land_area": 100, "building_area": 90})
    assert market["status"] == "PRELIMINARY"
    assert market["valid_count"] == 1
    assert market["base_exit"] > 0
    assert market["conservative_exit"] < market["base_exit"]
    assert market["market_range_low"] <= market["base_exit"] <= market["market_range_high"]
    assert market["data_uncertainty_discount_pct"] >= 24
    assert market["conservative_discount_used_pct"] == 5
    assert market["confidence"] < 65


def test_more_consistent_comparables_reduce_uncertainty_haircut():
    one = assess_comparables([comp(1)], {"land_area": 100, "building_area": 90})
    many_rows = [comp(i) for i in range(1, 7)]
    for row in many_rows:
        row["source_url_scope"] = "Listing individual"
    many = assess_comparables(many_rows, {"land_area": 100, "building_area": 90})
    assert many["data_uncertainty_discount_pct"] < one["data_uncertainty_discount_pct"]


def test_ai_exclusion_is_applied_only_when_flag_is_explicitly_true():
    rows = [comp(1), comp(2)]
    rows[0]["ai_exclude_from_primary"] = True
    market = assess_comparables(rows, {"land_area": 100, "building_area": 90})
    assert market["valid_count"] == 1
    assert any("dikeluarkan dari indikasi utama" in " ".join(x["errors"]) for x in market["invalid"])


def test_outlier_is_flagged_and_downweighted_not_silently_removed():
    rows = [comp(i) for i in range(1, 6)]
    for row in rows:
        row["source_url_scope"] = "Listing individual"
    rows[-1]["price"] = 1_200_000_000
    market = assess_comparables(rows, {"land_area": 100, "building_area": 90})
    assert market["valid_count"] == 5
    outliers = [row for row in market["valid"] if row.get("outlier_flag")]
    assert outliers
    assert outliers[0]["weight"] < outliers[0]["similarity_score"] / 100


def test_cross_village_comparable_500m_away_is_high_proximity_even_if_complex_name_differs():
    from core.market_engine import haversine_distance_km, assess_comparables
    subject = {"land_area": 100, "building_area": 80, "complex_name": "Perumahan Target", "latitude": -7.450000, "longitude": 112.700000, "certificate_type": "SHM"}
    # About 0.5 km north; no administrative/complex match is required.
    comp = {"name": "Perumahan Desa Sebelah", "address": "Desa tetangga, Sidoarjo", "latitude": -7.445500, "longitude": 112.700000,
            "price": 400_000_000, "land_area": 100, "building_area": 80, "certificate": "SHM",
            "condition": "Siap Huni", "access": "1 Mobil", "price_type": "Asking aktif", "source_platforms": "OLX", "source_evidence": "Listing rumah", "date_found": "2026-11-23", "listing_date": "2026-11-15"}
    dist = haversine_distance_km(subject, comp)
    assert dist is not None and 0.45 <= dist <= 0.55
    result = assess_comparables([comp], subject)
    assert result["valid_count"] == 1
    row = result["valid"][0]
    assert row["distance_km"] <= 0.55
    assert row["proximity_score"] >= 95
    assert row["similarity_score"] > 85

def test_market_engine_exposes_distance_and_degrades_score_gradually_after_5km():
    from core.market_engine import assess_comparables
    subject = {"land_area": 100, "building_area": 80, "latitude": -7.450000, "longitude": 112.700000}
    base = {"name": "Comp", "price": 400_000_000, "land_area": 100, "building_area": 80, "price_type": "Transaksi terverifikasi",
            "source_platforms": "Broker", "source_evidence": "Harga transaksi", "condition": "Siap Huni", "access": "1 Mobil",
            "date_found": "2026-11-23", "listing_date": "2026-11-15"}
    near = {**base, "name": "Dekat beda desa", "latitude": -7.450000, "longitude": 112.704000}
    far = {**base, "name": "Jauh", "latitude": -7.450000, "longitude": 112.780000}
    r_near = assess_comparables([near], subject)["valid"][0]
    r_far = assess_comparables([far], subject)["valid"][0]
    assert r_near["distance_km"] < r_far["distance_km"]
    assert r_near["similarity_score"] > r_far["similarity_score"]
