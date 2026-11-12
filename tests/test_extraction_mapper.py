from datetime import date

from services.extraction_mapper import apply_extraction_to_form, parse_extraction_json


def test_gemini_extraction_populates_matching_form_fields_and_keeps_missing_blank():
    extracted = {
        "lot_code": "001/LELANG/KPKNL/2026",
        "auction_office": "KPKNL Sidoarjo",
        "auction_type": "Lelang Eksekusi Hak Tanggungan",
        "auction_limit": 150_000_000,
        "deposit_amount": "Rp30.000.000",
        "bid_increment": "Rp5.000.000",
        "auction_date": "2026-11-20",
        "certificate_type": "SHM",
        "certificate_no": "12345",
        "land_area": "90 m2",
        "building_area": None,
        "province": "Jawa Timur",
        "property_type": "Rumah tinggal 1 lantai",
    }
    state = {
        "form_lot_code": "", "form_auction_office": "", "form_auction_type": "",
        "form_auction_limit": None, "form_deposit_amount": None, "form_bid_increment": None, "form_auction_date": None,
        "form_certificate_type": "", "form_certificate_no": "", "form_land_area": None,
        "form_building_area": None, "form_province": "", "form_property_type": "",
    }

    summary = apply_extraction_to_form(extracted, state)

    assert state["form_lot_code"] == "001/LELANG/KPKNL/2026"
    assert state["form_auction_office"] == "KPKNL Sidoarjo"
    assert state["form_auction_type"] == "Eksekusi Hak Tanggungan"
    assert state["form_auction_limit"] == 150_000_000
    assert state["form_deposit_amount"] == 30_000_000
    assert state["form_bid_increment"] == 5_000_000
    assert state["form_auction_date"] == date(2026, 11, 20)
    assert state["form_certificate_type"] == "SHM"
    assert state["form_land_area"] == 90.0
    assert state["form_building_area"] is None
    assert "form_building_area" in summary["missing_fields"]
    assert summary["filled_count"] >= 10


def test_manual_values_are_preserved_unless_overwrite_is_enabled():
    extracted = {"name": "Objek dari dokumen", "auction_limit": 200_000_000}
    state = {"form_name": "Nama hasil input manual", "form_auction_limit": 180_000_000}

    first = apply_extraction_to_form(extracted, state, overwrite=False)
    assert state["form_name"] == "Nama hasil input manual"
    assert state["form_auction_limit"] == 180_000_000
    assert len(first["skipped_existing"]) == 2

    second = apply_extraction_to_form(extracted, state, overwrite=True)
    assert state["form_name"] == "Objek dari dokumen"
    assert state["form_auction_limit"] == 200_000_000
    assert second["filled_count"] == 2


def test_missing_and_unknown_enums_are_not_invented():
    state = {"form_auction_type": "", "form_certificate_type": "", "form_property_type": ""}
    summary = apply_extraction_to_form(
        {"auction_type": "Jenis tidak jelas", "certificate_type": "Sertifikat tidak terbaca", "property_type": None},
        state,
    )
    assert state == {"form_auction_type": "", "form_certificate_type": "", "form_property_type": ""}
    assert summary["filled_count"] == 0
    assert summary["missing_count"] >= 3


def test_money_shorthand_is_supported_as_fallback():
    state = {"form_auction_limit": None}
    apply_extraction_to_form({"auction_limit": "Rp1,5 miliar"}, state)
    assert state["form_auction_limit"] == 1_500_000_000


def test_markdown_fenced_json_is_accepted():
    data = parse_extraction_json('```json\n{"lot_code":"X-01"}\n```')
    assert data["lot_code"] == "X-01"
