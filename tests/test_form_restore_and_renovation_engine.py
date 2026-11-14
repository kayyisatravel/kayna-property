from core.form_state import form_state_from_input_data
from core.renovation_engine import build_renovation_quantity_guidance, infer_renovation_category
from core.decision_engine import evaluate_decision


def test_load_restores_requested_property_and_survey_fields():
    data = {
        "property": {
            "lot_code": "LOT-1", "bedrooms": 3, "bathrooms": 2,
            "property_type": "Rumah 2 lantai", "floor_count": 2,
            "land_area": 120, "building_area": 150,
        },
        "survey": {
            "road_width_m": 6.5, "access": "1 Mobil",
            "physical_condition": "Renovasi ringan", "survey_status": "Sudah Survei - Kosong/Tidak Dihuni",
            "interior_inspected": True, "survey_notes": "Kondisi fasad cukup baik",
        },
        "costs": {"renovation_category": "Renovasi Ringan", "rab_condition_description": "Perlu ganti beberapa keramik"},
    }
    state = form_state_from_input_data(data)
    assert state["na_bedrooms"] == 3
    assert state["na_bathrooms"] == 2
    assert state["na_property_type"] == "Rumah 2 lantai"
    assert state["na_floor_count"] == 2
    assert state["na_road_width"] == 6.5
    assert state["na_access"] == "1 Mobil"
    assert state["na_physical_condition"] == "Renovasi ringan"
    assert state["na_renovation_category"] == "Renovasi Ringan"
    assert state["na_rab_condition_description"] == "Perlu ganti beberapa keramik"


def test_load_missing_fields_clears_previous_property_values():
    state = form_state_from_input_data({"property": {"name": "Objek baru"}, "survey": {}})
    assert state["na_bedrooms"] is None
    assert state["na_bathrooms"] is None
    assert state["na_property_type"] == ""
    assert state["na_road_width"] is None
    assert state["na_access"] == ""
    assert state["na_physical_condition"] == "Belum diketahui"


def test_two_storey_roof_estimate_uses_footprint_not_total_floor_area():
    guidance = build_renovation_quantity_guidance({
        "land_area": 100, "building_area": 160, "floor_count": 2,
        "physical_condition": "Renovasi sedang", "renovation_category": "Renovasi Sedang",
        "bedrooms": 4, "bathrooms": 2,
    })
    roof = next(x for x in guidance["items"] if x["item_code"] == "MED_NEW_ROOF")
    assert guidance["building_footprint_estimate"] == 80
    assert roof["quantity_low"] == 100
    assert roof["quantity_base"] == 104
    assert roof["quantity_high"] == 108


def test_mid_repair_does_not_assume_full_roof_or_electrical_replacement():
    guidance = build_renovation_quantity_guidance({
        "land_area": 90, "building_area": 60, "floor_count": 1,
        "physical_condition": "Renovasi ringan", "renovation_category": "Renovasi Ringan",
        "bedrooms": 2, "bathrooms": 1,
    })
    roof = next(x for x in guidance["items"] if x["item_code"] == "LGT_ROOF")
    electrical = next(x for x in guidance["items"] if x["item_code"] == "LGT_ELEC")
    # Minor roof repair has a low-confidence local allowance, not a full-roof replacement.
    full_roof_area = guidance["building_footprint_estimate"] * 1.30
    assert roof["quantity_base"] < full_roof_area
    assert electrical["quantity_base"] is None


def test_heavy_structural_work_is_never_auto_quantified_from_land_building_area():
    guidance = build_renovation_quantity_guidance({
        "land_area": 100, "building_area": 90, "physical_condition": "Renovasi berat",
        "renovation_category": "Renovasi Berat",
    })
    structural = next(x for x in guidance["items"] if x["item_code"] == "HVY_STRUCT")
    assert structural["quantity_base"] is None
    assert any("engineer" in w.lower() for w in guidance["warnings"])


def test_demolition_rubble_volume_and_truck_trips_are_explicitly_low_confidence():
    guidance = build_renovation_quantity_guidance({
        "land_area": 120, "building_area": 80, "floor_count": 1,
        "physical_condition": "Hitung tanah", "renovation_category": "Hitung Tanah",
    })
    rubble = next(x for x in guidance["items"] if x["item_code"] == "LAND_DEBRIS")
    trucks = next(x for x in guidance["items"] if x["item_code"] == "LAND_TRUCK")
    assert rubble["quantity_low"] == 24
    assert rubble["quantity_base"] == 32
    assert rubble["quantity_high"] == 40
    assert rubble["confidence"] == "Rendah"
    assert trucks["quantity_base"] == 7


def test_unpriced_mandatory_renovation_row_blocks_go():
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100_000_000, "land_area":100, "building_area":80},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "interior_inspected":True},
        "legal": {"identity_verified":True, "tax_rules_verified":True, "dispute_detected":False},
        "costs": {"cost_estimates_reviewed":True, "renovation_items":[{"work_item":"Renovasi kamar mandi", "priority":"Wajib", "quantity":None, "unit_cost":1000000}]},
        "risk_reviewed":True, "risk_summary":{}, "finance":{"cash_available_for_new_project":1_000_000_000, "cash_confirmed":True},
    }
    market = {"valid_count":5, "go_grade_count":5, "confidence":80}
    tiers = {"increment_confirmed":True, "max_bid":200_000_000}
    at_limit = {"roi_pct":40, "net_profit":10_000_000, "cash_requirement_including_reserve":100_000_000}
    result = evaluate_decision(inputs, market, tiers, at_limit)
    assert result["status"] == "HOLD"
    assert any("RAB masih memiliki pekerjaan wajib" in x for x in result["blockers"])


def test_missing_mandatory_ai_rab_scope_is_added_as_unpriced_placeholder(monkeypatch):
    import json
    import services.gemini_parser as gp
    payload = {
        "items": [{
            "item_code": "COS_PREP", "work_item": "Persiapan", "quantity": 1, "unit": "ls",
            "unit_cost_low": 100000, "unit_cost_conservative": 150000, "priority": "Wajib",
        }],
        "assumptions": [], "items_to_inspect": [], "overall_note": "Draft",
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(payload))
    result = gp.estimate_renovation_rab(
        "fake-key", [], "Cat dinding mengelupas.",
        {"building_area": 80, "physical_condition": "Renovasi kosmetik", "renovation_category": "Renovasi Kosmetik"},
    )
    codes = {r.get("item_code") for r in result["editor_rows"]}
    assert "COS_WALL" in codes and "COS_CEILING" in codes
    wall = next(r for r in result["editor_rows"] if r.get("item_code") == "COS_WALL")
    assert wall["unit_cost"] is None
    assert result["total_conservative_complete"] is False
    assert any("Scope wajib belum diberi harga" in x for x in result["items_to_inspect"])


def test_restore_fields_from_latest_analysis_when_input_data_is_partial_or_legacy():
    latest = {
        "inputs": {
            "property": {"bedroom_count": "3", "bathroom_count": "2", "jenis_properti": "Rumah 1 lantai", "floor_count": 1},
            "survey": {"road_width": "6.5", "road_access": "2 Mobil", "general_physical_condition": "Renovasi sedang"},
        },
        "costs": {"renovation_category": "Renovasi Sedang"},
    }
    state = form_state_from_input_data({"property": {"lot_code": "LOT-X"}, "survey": {}}, latest)
    assert state["na_lot_code"] == "LOT-X"
    assert state["na_bedrooms"] == 3
    assert state["na_bathrooms"] == 2
    assert state["na_property_type"] == "Rumah 1 lantai"
    assert state["na_road_width"] == 6.5
    assert state["na_access"] == "2 Mobil"
    assert state["na_physical_condition"] == "Renovasi sedang"
    assert state["na_renovation_category"] == "Renovasi Sedang"


def test_explicit_floor_footprint_takes_precedence_for_roof_area():
    guidance = build_renovation_quantity_guidance({
        "land_area": 120, "building_area": 150, "building_footprint_m2": 75,
        "floor_count": 2, "physical_condition": "Renovasi sedang",
        "renovation_category": "Renovasi Sedang", "bedrooms": 3, "bathrooms": 2,
    })
    roof = next(x for x in guidance["items"] if x["item_code"] == "MED_NEW_ROOF")
    assert guidance["building_footprint_estimate"] == 75
    assert roof["quantity_low"] == 93.75
    assert roof["quantity_base"] == 97.5
    assert roof["quantity_high"] == 101.25
    assert "diinput pengguna" in guidance["footprint_basis"]


def test_light_renovation_uses_low_confidence_local_allowances_not_full_replacement():
    guidance = build_renovation_quantity_guidance({
        "land_area": 100, "building_area": 80, "floor_count": 1,
        "physical_condition": "Renovasi ringan", "renovation_category": "Renovasi Ringan",
        "bedrooms": 3, "bathrooms": 2,
    })
    roof = next(x for x in guidance["items"] if x["item_code"] == "LGT_ROOF")
    ceiling = next(x for x in guidance["items"] if x["item_code"] == "LGT_CEILING")
    tile = next(x for x in guidance["items"] if x["item_code"] == "LGT_TILE")
    assert (roof["quantity_low"], roof["quantity_base"], roof["quantity_high"]) == (5.0, 10.4, 16.2)
    assert (ceiling["quantity_low"], ceiling["quantity_base"], ceiling["quantity_high"]) == (2.4, 6.0, 8.0)
    assert (tile["quantity_low"], tile["quantity_base"], tile["quantity_high"]) == (1.6, 3.2, 4.8)
    assert roof["confidence"] == ceiling["confidence"] == tile["confidence"] == "Rendah"
    assert roof["conditional"] and ceiling["conditional"] and tile["conditional"]


def test_unknown_condition_auto_category_only_recommends_inspection_not_light_repairs():
    guidance = build_renovation_quantity_guidance({
        "land_area": 100, "building_area": 80, "physical_condition": "Belum diketahui",
        "renovation_category": "Auto sesuai kondisi umum",
    })
    assert guidance["category"] == "Auto sesuai kondisi umum"
    codes = {x["item_code"] for x in guidance["items"]}
    assert codes == {"AUTO_INSPECT", "AUTO_CLEAN"}


def test_bedroom_count_moves_wall_area_midpoint_only_within_screening_band():
    two = build_renovation_quantity_guidance({"building_area": 100, "bedrooms": 2, "physical_condition": "Renovasi kosmetik", "renovation_category": "Renovasi Kosmetik"})
    four = build_renovation_quantity_guidance({"building_area": 100, "bedrooms": 4, "physical_condition": "Renovasi kosmetik", "renovation_category": "Renovasi Kosmetik"})
    wall_two = next(x for x in two["items"] if x["item_code"] == "COS_WALL")
    wall_four = next(x for x in four["items"] if x["item_code"] == "COS_WALL")
    assert wall_two["quantity_base"] == 260
    assert wall_four["quantity_base"] == 280
    assert wall_two["quantity_low"] == wall_four["quantity_low"] == 250
    assert wall_two["quantity_high"] == wall_four["quantity_high"] == 300



def test_explicitly_rejected_rab_item_is_excluded_from_project_cost():
    from core.renovation_engine import rab_item_is_in_scope
    assert rab_item_is_in_scope({"priority": "Wajib"}) is True
    assert rab_item_is_in_scope({"priority": "Opsional"}) is True
    assert rab_item_is_in_scope({"priority": "Tidak diperlukan setelah ditinjau"}) is False
