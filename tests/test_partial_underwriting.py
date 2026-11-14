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


def test_partial_market_can_still_indicate_walk_away_below_limit():
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
    assert result["bidding"]["max_bid"] is not None
    assert result["bidding"]["max_bid"] < 500_000_000
    assert result["decision"]["status"] == "DO NOT BID"


def test_partial_kpknl_data_can_still_return_preliminary_do_not_bid():
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
    assert result["bidding"]["max_bid"] is not None
    assert result["bidding"]["max_bid"] < 500_000_000
    assert result["decision"]["status"] == "DO NOT BID"
