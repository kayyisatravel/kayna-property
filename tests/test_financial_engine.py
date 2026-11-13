from core.calculator import calculate_project
from core.maximum_bid import find_maximum_bid, build_bid_tiers
from core.liquidity import compute_liquidity, evaluate_funding
from core.underwriting import run_underwriting
from core.lifecycle import actual_project_summary
from config import DEFAULT_RULES


def base_inputs():
    return {
        "property": {"njop": 100_000_000, "npoptkp_eligible": True},
        "survey": {"possession_cost": 20_000_000, "possession_months": 1},
        "costs": {"renovation_cost": 30_000_000, "renovation_months": 1, "selling_months": 3, "monthly_holding_cost": 1_000_000, "legal_delay_months": 1},
        "rules": dict(DEFAULT_RULES),
    }


def test_buyer_fee_and_bphtb():
    result = calculate_project(200_000_000, 400_000_000, base_inputs())
    assert result["buyer_auction_fee"] == 4_000_000
    assert result["bphtb"] == 6_000_000  # (200m - 80m) * 5%


def test_npoptkp_not_applied_without_confirmation():
    data = base_inputs(); data["property"]["npoptkp_eligible"] = False
    result = calculate_project(200_000_000, 400_000_000, data)
    assert result["bphtb"] == 10_000_000


def test_selling_costs():
    result = calculate_project(200_000_000, 400_000_000, base_inputs())
    assert result["seller_final_tax"] == 10_000_000
    assert result["seller_agent"] == 10_000_000
    assert result["seller_ajb_ppat"] == 4_000_000
    assert result["seller_misc"] == 5_000_000
    assert result["selling_cost"] == 29_000_000


def test_roi_is_project_period_not_annualized():
    result = calculate_project(200_000_000, 400_000_000, base_inputs())
    expected = result["net_profit"] / result["capital_before_sale"] * 100
    assert result["roi_pct"] == expected
    assert result["annualized_roi_pct"] is not None


def test_maximum_bid_meets_roi_hurdle():
    data = base_inputs()
    maxbid = find_maximum_bid(500_000_000, data, 100_000_000, 1_000_000, 25, 1_000_000_000)
    assert maxbid["maximum_bid"] is not None
    assert maxbid["at_maximum"]["roi_pct"] >= 25
    next_bid = maxbid["maximum_bid"] + 1_000_000
    assert calculate_project(next_bid, 500_000_000, data)["roi_pct"] < 25


def test_cash_reserve_and_user_outflow():
    liq = compute_liquidity(500_000_000, [{"amount": 45_000_000, "confirmed": True}], 20)
    assert liq["cash_available_for_new_project"] == 355_000_000


def test_unconfirmed_outflow_not_subtracted():
    liq = compute_liquidity(500_000_000, [{"amount": 45_000_000, "confirmed": False}], 20)
    assert liq["cash_available_for_new_project"] == 400_000_000


def test_selling_cost_actual_not_double_counted():
    summary = actual_project_summary([
        {"category":"Acquisition", "amount":200_000_000},
        {"category":"Renovation", "amount":30_000_000},
        {"category":"Selling", "amount":20_000_000},
    ], {"closing_price":400_000_000, "total_holding_months":5})
    assert summary["total_actual_cost"] == 230_000_000
    assert summary["selling_cost_actual"] == 20_000_000
    assert summary["net_profit_actual"] == 150_000_000


def test_bpn_cost_defaults_are_included_from_global_rules():
    data = base_inputs()
    data["costs"] = {"renovation_cost": 0}
    result = calculate_project(200_000_000, 400_000_000, data)
    assert result["legal_bpn_cost"] == 7_500_000


def test_property_specific_bpn_cost_overrides_global_rules():
    data = base_inputs()
    data["costs"] = {"bpn_pnbp_cost": 1_000_000, "roya_cost": 500_000, "other_acquisition_admin": 0, "acquisition_notary_ppat_fee": 0}
    result = calculate_project(200_000_000, 400_000_000, data)
    assert result["legal_bpn_cost"] == 1_500_000


def test_bpn_self_managed_notary_default_zero():
    data = base_inputs()
    result = calculate_project(200_000_000, 400_000_000, data)
    assert data["rules"]["acquisition_notary_ppat_fee"] == 0
    assert result["legal_bpn_cost"] == 7_500_000


def test_missing_max_bid_does_not_falsely_show_walk_away_at_limit():
    data = base_inputs()
    result = build_bid_tiers(500_000_000, 1_000_000, 300_000_000, 320_000_000, data, 1_000_000_000, 25, 35)
    assert result["max_bid"] is None
    assert result["walk_away_from"] is None


def test_general_risk_reserve_increases_cash_requirement_not_project_cost():
    data = base_inputs()
    data["survey"]["general_risk_reserve"] = 15_000_000
    result = calculate_project(200_000_000, 400_000_000, data)
    assert result["cash_requirement_including_reserve"] == result["capital_before_sale"] + result["possession_risk_reserve"] + 15_000_000
    assert result["capital_before_sale"] == calculate_project(200_000_000, 400_000_000, base_inputs())["capital_before_sale"]


def test_safe_json_converts_non_finite_values_to_null():
    import json, math
    from core.utils import safe_json
    payload = {"a": float("nan"), "b": [float("inf"), 2], "c": float("-inf")}
    result = json.loads(safe_json(payload))
    assert result == {"a": None, "b": [None, 2], "c": None}
