from core.sheets_rebuild import rebuild_inputs_from_sheets


def test_sheets_rebuild_uses_editable_fields():
    master = {"object_id": "X", "auction_limit": "150000000", "njop": "130000000", "land_area": "90", "identity_verified": "TRUE", "legal_status": "Terverifikasi"}
    survey = {"occupancy_status": "Kosong dan terverifikasi", "occupancy_verified": "TRUE", "physical_condition": "Siap huni"}
    costs = {"buyer_auction_fee_pct": "0", "bphtb_rate_pct": "5", "tax_rules_verified": "TRUE", "renovation_cost": "25000000", "minimum_roi_pct": "20", "score_legal": "4"}
    comps = [{"active": "TRUE", "price": "350000000", "land_area": "90", "building_area": "70"}, {"active": "FALSE", "price": "999999999"}]
    scenarios = [{"scenario_key": "KOSONG", "label": "Kosong", "expected_cost": "1000000", "delay_months": "0.5", "reserve_cost": "2000000", "active": "TRUE"}]
    inputs = rebuild_inputs_from_sheets(master, survey, costs, comps, scenarios)
    assert inputs["property"]["auction_limit"] == 150000000
    assert inputs["property"]["njop"] == 130000000
    assert inputs["property"]["identity_verified"] is True
    assert inputs["costs"]["renovation_cost"] == 25000000
    assert len(inputs["comparables"]) == 1
    assert inputs["possession_scenarios"]["KOSONG"]["reserve_cost"] == 2000000
