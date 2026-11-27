from core.underwriting import run_underwriting
from config import DEFAULT_RULES


def test_partial_kpknl_data_still_calculates_costs_and_returns_hold_without_arv():
    data = {
        "property": {"lot_code":"LOT-PARTIAL", "auction_limit":150_000_000},
        "survey": {"survey_status":"Belum Survei", "possession_cost":25_000_000, "possession_months":6},
        "legal": {},
        "costs": {"renovation_cost":20_000_000, "renovation_months":1, "selling_months":3, "monthly_holding_cost":1_000_000},
        "comparables": [],
        "risk_register": [],
        "risk_reviewed": False,
    }
    liquidity = {"real_cash":500_000_000, "cash_available_for_new_project":300_000_000, "cash_confirmed":True}
    result = run_underwriting(data, liquidity, dict(DEFAULT_RULES))
    assert result["at_limit"]["capital_before_sale"] > 150_000_000
    assert result["at_limit"]["roi_pct"] is None
    assert result["at_limit"]["net_profit"] is None
    assert result["decision"]["status"] == "HOLD"


def test_partial_market_can_still_indicate_hold_and_walk_away_below_limit():
    # The engine should expose an economic ceiling below the auction limit even
    # though fewer than five comparables means final GO is prohibited.
    data = {
        "property": {"lot_code":"LOT-PARTIAL", "address":"Alam Mutiara", "auction_limit":500_000_000, "bid_increment":1_000_000, "land_area":100, "building_area":80, "npoptkp_eligible":False},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "possession_cost":5_000_000, "possession_months":0.5},
        "legal": {"identity_verified":True, "tax_rules_verified":True},
        "costs": {"renovation_cost":20_000_000, "renovation_months":1, "selling_months":3, "monthly_holding_cost":1_000_000, "cost_estimates_reviewed":True},
        "comparables": [
            {"name":"Listing A","address":"Alam Mutiara","price":300_000_000,"land_area":100,"building_area":80,"source_platforms":"Rumah123","date_found":"2026-11-13","price_type":"Asking aktif"}
        ],
        "risk_register": [], "risk_reviewed": True,
    }
    liquidity = {"real_cash":1_000_000_000, "cash_available_for_new_project":800_000_000, "cash_confirmed":True}
    result = run_underwriting(data, liquidity, dict(DEFAULT_RULES))
    assert result["market"]["valid_count"] == 1
    assert result["bidding"]["max_bid"] is None
    assert result["bidding"]["max_economic_ceiling"] is not None
    assert result["bidding"]["max_economic_ceiling"] < 500_000_000
    assert result["decision"]["status"] == "HOLD"
    assert result["decision"]["bid_readiness"] != "READY"


def test_partial_kpknl_data_returns_hold_while_due_diligence_is_incomplete():
    # Minimal auction data: the limit and subject LT are known; LB, lot code,
    # address, survey and legal verification are not. With one indicative market
    # reference the engine can still expose a ceiling below limit (never GO).
    data = {
        "property": {"auction_limit": 500_000_000, "land_area": 100},
        "survey": {"survey_status": "Belum Survei", "possession_cost": 25_000_000, "possession_months": 6},
        "legal": {},
        "costs": {"renovation_cost": 20_000_000, "renovation_months": 1, "selling_months": 3, "monthly_holding_cost": 1_000_000},
        "comparables": [{"name":"Listing A", "address":"Alam Mutiara", "price":300_000_000, "land_area":100, "source_platforms":"Rumah123", "date_found":"2026-11-13", "price_type":"Asking aktif"}],
        "risk_register": [], "risk_reviewed": False,
    }
    liquidity = {"real_cash":1_000_000_000, "cash_available_for_new_project":800_000_000, "cash_confirmed":True}
    result = run_underwriting(data, liquidity, dict(DEFAULT_RULES))
    assert result["at_limit"]["capital_before_sale"] > 500_000_000
    assert result["bidding"]["max_bid"] is None
    assert result["bidding"]["max_economic_ceiling"] is not None
    assert result["bidding"]["max_economic_ceiling"] < data["property"]["auction_limit"]
    assert result["bidding"]["maximum_holding_days_allowed"] == 365
    assert result["bidding"]["go_maximum_holding_days_allowed"] == 180
    assert result["decision"]["status"] == "HOLD"
    assert result["decision"]["bid_readiness"] != "READY"


def test_partial_required_rab_marks_bid_tiers_provisional_and_keeps_known_costs_visible():
    data = {
        "property": {"lot_code":"LOT-RAB", "address":"Alamat", "auction_limit":100_000_000, "bid_increment":1_000_000, "land_area":100, "building_area":80, "property_type":"Rumah 1 lantai"},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "possession_cost":3_000_000, "possession_months":1, "interior_inspected":True},
        "legal": {"identity_verified":True, "tax_rules_verified":True},
        "costs": {"renovation_cost":5_000_000, "renovation_months":1, "selling_months":3, "monthly_holding_cost":1_000_000,
                   "cost_estimates_reviewed":True, "renovation_items":[{"work_item":"Perbaikan atap depan", "priority":"Wajib", "quantity":None, "unit_cost":250_000}]},
        "comparables": [], "risk_register": [], "risk_reviewed":True,
    }
    liquidity = {"real_cash":500_000_000, "cash_available_for_new_project":400_000_000, "cash_confirmed":True}
    result = run_underwriting(data, liquidity, dict(DEFAULT_RULES))
    assert result["at_limit"]["capital_before_sale"] > 100_000_000
    assert result["bidding"]["provisional"] is True
    assert any("RAB wajib belum lengkap" in x for x in result["bidding"]["provisional_reasons"])
    assert result["decision"]["status"] == "HOLD"
