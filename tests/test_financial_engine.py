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


def test_economic_ceiling_below_limit_is_not_returned_as_an_actionable_bid():
    data = base_inputs()
    result = build_bid_tiers(500_000_000, 1_000_000, 300_000_000, 320_000_000, data, 1_000_000_000, 25, 35)
    assert result["max_bid"] is None
    assert result["max_economic_ceiling"] is not None
    assert result["max_economic_ceiling"] < 500_000_000
    assert result["walk_away_from"] is None
    assert "JANGAN BID" in result["walk_away_reason"]


def test_mid_roi_target_below_limit_is_not_shown_as_a_bid_price():
    from core.calculator import calculate_project
    data = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 10_000_000, "possession_months": 1},
        "costs": {"renovation_cost": 20_000_000, "renovation_months": 1, "selling_months": 3, "legal_delay_months": 0, "monthly_holding_cost": 1_000_000, "marketing_cost": 2_000_000},
        "rules": dict(DEFAULT_RULES),
    }
    roi_at_limit = calculate_project(160_000_000, 300_000_000, data)["roi_pct"]
    result = build_bid_tiers(160_000_000, 1_000_000, 300_000_000, 320_000_000, data, None, 25, 35)
    assert 25 <= roi_at_limit < 35
    assert result["mid_bid"] is None
    assert result["mid_economic_ceiling"] < 160_000_000
    assert result["max_bid"] >= 160_000_000
    assert result["max_result"]["roi_pct"] >= 25


def test_bid_increment_grid_is_anchored_to_auction_limit_not_zero():
    data = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {}, "costs": {}, "rules": dict(DEFAULT_RULES),
    }
    result = build_bid_tiers(160_500_000, 1_000_000, 500_000_000, 520_000_000, data, None, 25, 35)
    assert result["max_bid"] >= 160_500_000
    assert (result["max_bid"] - 160_500_000) % 1_000_000 == 0
    assert result["walk_away_from"] == result["max_bid"] + 1_000_000


def test_missing_arv_still_calculates_project_cost_without_false_zero_sale():
    result = calculate_project(150_000_000, None, base_inputs())
    assert result["capital_before_sale"] > 150_000_000
    assert result["roi_pct"] is None
    assert result["net_profit"] is None
    assert result["selling_cost"] is None


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


def test_missing_bid_increment_never_exposes_simulation_as_a_legal_bid():
    data = base_inputs()
    result = build_bid_tiers(100_000_000, None, 500_000_000, 550_000_000, data, None, 25, 35)
    assert result["max_bid"] is None
    assert result["mid_bid"] is None
    assert result["max_simulated_ceiling"] is not None
    assert result["mid_simulated_ceiling"] is not None
    assert result["max_economic_ceiling"] is None  # limit itself clears 25%; this is a simulation, not a below-limit ceiling
    assert result["increment_confirmed"] is False
    assert result["walk_away_from"] is None
    assert "bukan harga bid" in result["walk_away_reason"].lower()
    assert "bukan increment resmi" in result["increment_note"]


def test_calculator_exposes_legal_cost_components_without_changing_legal_total():
    from core.calculator import calculate_project
    inputs = {
        "property": {"njop": 100_000_000},
        "survey": {},
        "costs": {},
        "rules": {
            "buyer_auction_fee_pct": 2, "bphtb_rate_pct": 5, "npoptkp": 0,
            "bphtb_basis_mode": "bid_only", "bpn_pnbp_cost": 2_000_000,
            "roya_cost": 1_000_000, "other_acquisition_admin": 500_000,
            "other_legal_cost": 250_000, "acquisition_notary_ppat_fee": 0,
        },
    }
    result = calculate_project(100_000_000, None, inputs)
    assert result["legal_bpn_cost"] == 3_750_000
    assert result["bpn_pnbp_cost"] + result["roya_cost"] + result["other_acquisition_admin"] + result["other_legal_cost"] + result["acquisition_notary_ppat_fee"] == result["legal_bpn_cost"]


def test_hidden_condition_reserve_is_added_only_when_interior_not_inspected():
    from core.calculator import calculate_project
    from config import DEFAULT_RULES
    base = {"property": {"njop": 0, "npoptkp_eligible": False}, "survey": {"interior_inspected": False},
            "costs": {"renovation_cost": 40_000_000}, "rules": dict(DEFAULT_RULES)}
    unseen = calculate_project(100_000_000, None, base)
    assert unseen["hidden_condition_reserve"] == 3_000_000
    assert unseen["capital_before_sale"] >= unseen["acquisition_cost"] + 40_000_000 + unseen["renovation_contingency"] + 3_000_000
    inspected = {**base, "survey": {"interior_inspected": True}}
    known = calculate_project(100_000_000, None, inspected)
    assert known["hidden_condition_reserve"] == 0
    legacy = {**base, "survey": {}}
    legacy_result = calculate_project(100_000_000, None, legacy)
    assert legacy_result["hidden_condition_reserve"] == 0
