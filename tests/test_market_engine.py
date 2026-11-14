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

