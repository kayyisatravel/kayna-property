from __future__ import annotations

from copy import deepcopy

from config import DEFAULT_RULES
from core.decision_engine import evaluate_decision
from core.maximum_bid import build_bid_tiers, calculate_rule_of_thumb_mao
from core.underwriting import run_underwriting


def _base_inputs():
    return {
        "property": {
            "lot_code": "LOT-TEST-25-1",
            "address": "Perumahan Contoh, Sidoarjo",
            "auction_limit": 150_000_000,
            "land_area": 90,
            "building_area": 70,
            "property_type": "Rumah 1 lantai",
        },
        "survey": {
            "survey_status": "Sudah Survei - Kosong/Tidak Dihuni",
            "physical_condition": "Siap huni",
            "interior_inspected": True,
            "structure_verified_safe": True,
            "possession_cost": 3_000_000,
            "possession_risk_reserve": 5_000_000,
            "possession_months": 0.5,
        },
        "legal": {
            "identity_verified": True,
            "dispute_detected": False,
            "tax_rules_verified": True,
            "original_certificate_status": "Asli di bank/kreditur dan siap diserahkan",
        },
        "costs": {"cost_estimates_reviewed": True, "renovation_items": []},
        "rules": dict(DEFAULT_RULES),
        "finance": {"cash_confirmed": True, "cash_available_for_new_project": 600_000_000},
        "risk_reviewed": True,
    }


def _market_ready():
    return {
        "valid_count": 5,
        "valuation_comparable_count": 5,
        "go_grade_count": 5,
        "confidence": 75,
        "status": "READY",
    }


def _tiers_ready():
    return {"increment_confirmed": True, "max_bid": 200_000_000, "max_economic_ceiling": 200_000_000}


def _at_limit(*, roi=30, profit=70_000_000, days=120, cash_need=300_000_000):
    return {
        "roi_pct": roi,
        "net_profit": profit,
        "capital_before_sale": 270_000_000,
        "cash_requirement_including_reserve": cash_need,
        "projected_holding_days": days,
        "renovation_cost": 40_000_000,
        "renovation_contingency": 8_000_000,
    }


def test_vacant_status_is_not_misread_as_occupied():
    result = evaluate_decision(_base_inputs(), _market_ready(), _tiers_ready(), _at_limit())
    assert result["investment_status"] == "GO"
    assert result["bid_readiness"] == "READY"
    assert not any("pengosongan" in item.lower() or "penghuni" in item.lower() for item in result["hold_reasons"])


def test_missing_original_certificate_is_post_award_note_and_unverified_structure_is_condition():
    inputs = _base_inputs()
    inputs["legal"]["original_certificate_status"] = "Belum diverifikasi"
    missing_original = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert missing_original["investment_status"] == "GO"
    assert not any(item["category"] == "LEGAL" for item in missing_original["bid_readiness_issues"])
    assert any("sertifikat asli" in item.lower() for item in missing_original["warnings"])

    inputs = _base_inputs()
    inputs["survey"]["structure_verified_safe"] = False
    missing_structure = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert missing_structure["investment_status"] == "CONDITIONAL GO"
    assert any("Struktur utama belum diverifikasi" in item for item in missing_structure["conditions"])
    assert any(item["category"] == "SURVEY" for item in missing_structure["bid_readiness_issues"])


def test_cosmetic_renovation_maps_to_ready_to_move_comparable_bucket():
    from core.underwriting import _subject_condition_bucket
    assert _subject_condition_bucket("Renovasi kosmetik", "Rumah 1 lantai") == "Siap Huni"


def test_conditional_roi_band_is_investable_and_can_be_bid_ready():
    result = evaluate_decision(_base_inputs(), _market_ready(), _tiers_ready(), _at_limit(roi=20))
    assert result["investment_status"] == "CONDITIONAL GO"
    assert result["bid_readiness"] == "READY"
    assert any("15.0" in item and "25.0" in item for item in result["conditions"])


def test_conditional_holding_window_is_181_to_365_days():
    inputs = _base_inputs()
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit(days=240))
    assert result["investment_status"] == "CONDITIONAL GO"
    assert result["bid_readiness"] == "READY"
    beyond = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit(days=366))
    assert beyond["investment_status"] == "HOLD"
    assert any("365 hari" in item for item in beyond["hold_reasons"])


def test_cash_shortfall_does_not_erase_investment_attractiveness_but_blocks_bid_readiness():
    inputs = _base_inputs()
    inputs["finance"]["cash_available_for_new_project"] = 100_000_000
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert result["investment_status"] == "GO"
    assert result["bid_readiness"].startswith("NOT READY")
    assert any(item["category"] == "CASH" for item in result["bid_readiness_issues"])


def test_three_comparables_can_support_conditional_but_not_go():
    inputs = _base_inputs()
    market = {
        "valid_count": 3,
        "valuation_comparable_count": 3,
        "go_grade_count": 2,
        "confidence": 50,
        "status": "PRELIMINARY",
    }
    result = evaluate_decision(inputs, market, _tiers_ready(), _at_limit())
    assert result["investment_status"] == "CONDITIONAL GO"
    assert result["bid_readiness"].startswith("NOT READY")
    assert any(item["category"] == "MARKET" for item in result["bid_readiness_issues"])


def test_fewer_than_three_valuation_comparables_is_conditional_not_automatic_hold():
    inputs = _base_inputs()
    market = {"valid_count": 2, "valuation_comparable_count": 2, "go_grade_count": 1, "confidence": 40, "status": "PRELIMINARY"}
    result = evaluate_decision(inputs, market, _tiers_ready(), _at_limit())
    assert result["investment_status"] == "CONDITIONAL GO"
    assert any(item["category"] == "MARKET" for item in result["bid_readiness_issues"])


def test_cooperative_occupant_requires_documented_possession_plan_before_bid_ready():
    inputs = _base_inputs()
    inputs["survey"]["survey_status"] = "Sudah Survei - Dihuni (Keluar Sukarela)"
    not_documented = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert not_documented["investment_status"] == "CONDITIONAL GO"
    assert not_documented["bid_readiness"].startswith("NOT READY")
    inputs["survey"]["possession_plan_confirmed"] = True
    documented = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert documented["investment_status"] == "CONDITIONAL GO"
    assert documented["bid_readiness"] == "READY"


def test_cash_for_keys_requires_cost_and_reserve_to_be_quantified():
    inputs = _base_inputs()
    inputs["survey"].update({
        "survey_status": "Sudah Survei - Dihuni (Minta Kompensasi)",
        "possession_cost": 0,
        "possession_risk_reserve": 0,
        "possession_plan_confirmed": True,
    })
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert result["investment_status"] == "CONDITIONAL GO"
    assert any("biaya pengosongan belum dianggarkan" in item.lower() for item in result["conditions"])
    assert any(item["category"] == "POSSESSION" for item in result["bid_readiness_issues"])


def test_confirmed_non_mitigable_legal_risk_is_do_not_bid():
    inputs = _base_inputs()
    inputs["legal"]["fatal_legal_issue_confirmed"] = True
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert result["investment_status"] == "DO NOT BID"
    assert result["hard_stops"]


def test_inspected_medium_renovation_with_adequate_contingency_is_conditional():
    inputs = _base_inputs()
    inputs["survey"]["physical_condition"] = "Renovasi sedang"
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert result["investment_status"] == "CONDITIONAL GO"


def test_medium_renovation_without_inspection_or_contingency_remains_conditional():
    inputs = _base_inputs()
    inputs["survey"]["physical_condition"] = "Renovasi sedang"
    inputs["survey"]["interior_inspected"] = False
    at_limit = _at_limit()
    at_limit["renovation_contingency"] = 0
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), at_limit)
    assert result["investment_status"] == "CONDITIONAL GO"
    assert any("Interior belum diinspeksi" in item for item in result["conditions"])
    assert any(item["category"] == "SURVEY" for item in result["bid_readiness_issues"])


def test_seventy_percent_mao_stays_below_arv_budget_after_costs():
    inputs = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 10_000_000, "possession_risk_reserve": 5_000_000, "general_risk_reserve": 0},
        "legal": {},
        "costs": {"renovation_cost": 30_000_000},
        "rules": {
            "buyer_auction_fee_pct": 2,
            "bphtb_rate_pct": 5,
            "npoptkp": 0,
            "bphtb_basis_mode": "bid_only",
            "bpn_pnbp_cost": 2_000_000,
            "roya_cost": 0,
            "other_acquisition_admin": 0,
            "acquisition_notary_ppat_fee": 0,
            "renovation_contingency_pct": 20,
        },
    }
    result = calculate_rule_of_thumb_mao(400_000_000, inputs, 70)
    assert result["status"] == "CALCULATED"
    assert result["mao"] is not None
    assert result["used_budget"] <= result["budget_ceiling"]
    assert result["budget_ceiling"] == 280_000_000


def test_known_property_arrears_reduce_the_70_percent_rule_mao():
    base = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 0, "possession_risk_reserve": 0, "general_risk_reserve": 0},
        "legal": {},
        "costs": {"renovation_cost": 0, "other_presale_cost": 0},
        "rules": {
            "buyer_auction_fee_pct": 0, "bphtb_rate_pct": 0, "npoptkp": 0,
            "bphtb_basis_mode": "bid_only", "bpn_pnbp_cost": 0,
            "roya_cost": 0, "other_acquisition_admin": 0,
            "acquisition_notary_ppat_fee": 0, "renovation_contingency_pct": 0,
        },
    }
    without_arrears = calculate_rule_of_thumb_mao(400_000_000, base, 70)
    with_arrears_inputs = deepcopy(base)
    with_arrears_inputs["costs"]["other_presale_cost"] = 12_000_000
    with_arrears = calculate_rule_of_thumb_mao(400_000_000, with_arrears_inputs, 70)
    assert with_arrears["mao"] == without_arrears["mao"] - 12_000_000


def test_bid_solver_has_separate_go_and_conditional_holding_windows():
    inputs = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 0, "possession_months": 0, "interior_inspected": True},
        "costs": {
            "renovation_cost": 0,
            "renovation_months": 1,
            "selling_months": 9,
            "legal_delay_months": 0,
            "monthly_holding_cost": 0,
            "marketing_cost": 0,
        },
        "rules": {**DEFAULT_RULES, "buyer_auction_fee_pct": 0, "bphtb_rate_pct": 0, "seller_final_tax_pct": 0, "seller_agent_pct": 0, "seller_ajb_ppat_pct": 0, "seller_misc_fixed": 0},
    }
    tiers = build_bid_tiers(
        100_000_000,
        1_000_000,
        500_000_000,
        500_000_000,
        inputs,
        None,
        minimum_roi_pct=15,
        mid_roi_pct=30,
        minimum_net_profit=50_000_000,
        maximum_holding_days=180,
        conditional_maximum_holding_days=365,
    )
    assert tiers["max_bid"] is not None
    assert tiers["maximum_holding_days_allowed"] == 365
    assert tiers["go_maximum_holding_days_allowed"] == 180
    assert tiers["mid_bid"] is None


def test_run_underwriting_passes_current_policy_thresholds_to_decision_engine():
    data = {
        "property": {"lot_code": "LOT-POLICY", "address": "Sidoarjo", "auction_limit": 100_000_000, "land_area": 90, "building_area": 70},
        "survey": {"survey_status": "Belum Survei", "physical_condition": "Belum diketahui"},
        "legal": {},
        "costs": {},
        "comparables": [],
        "risk_register": [],
        "risk_reviewed": False,
    }
    rules = {**DEFAULT_RULES, "conditional_minimum_roi_pct": 17, "go_minimum_roi_pct": 27, "minimum_roi_pct": 17}
    result = run_underwriting(data, {"cash_confirmed": True, "cash_available_for_new_project": 500_000_000}, rules)
    assert result["decision"]["conditional_minimum_roi_pct"] == 17
    assert result["decision"]["go_minimum_roi_pct"] == 27


def test_fmv_as_is_does_not_count_mixed_condition_proxy_as_matched_sample():
    data = _base_inputs()
    data["survey"]["physical_condition"] = "Siap huni"
    data["comparables"] = [
        {
            "name": f"Matched ready home {i}",
            "address": f"Ready home street {i}",
            "price": 350_000_000 + i * 5_000_000,
            "land_area": 90,
            "building_area": 70,
            "condition": "Siap Huni" if i == 0 else "Butuh Renovasi",
            "access": "1 Mobil",
            "price_type": "Asking aktif",
            "source_platforms": "Listing test",
            "source_url": f"https://example.test/mixed-{i}",
            "date_found": "2026-11-25",
        }
        for i in range(5)
    ]
    result = run_underwriting(data, {"cash_confirmed": True, "cash_available_for_new_project": 600_000_000}, data["rules"])
    assert result["market"]["comparable_pool_count"] == 5
    assert result["market"]["fmv_as_is"]["comparable_count"] == 1
    assert result["market"]["fmv_as_is"]["status"] == "PROVISIONAL"
    assert result["market"]["fmv_as_is"]["value"] is None


def test_low_sample_mixed_condition_proxy_cannot_trigger_do_not_bid():
    data = _base_inputs()
    data["costs"].update({"renovation_cost": 250_000_000, "renovation_months": 2, "selling_months": 3, "legal_delay_months": 1})
    data["survey"].update({"physical_condition": "Renovasi berat", "interior_inspected": True})
    data["comparables"] = [
        {
            "name": f"Renovation-only comparable {i}",
            "address": f"Perumahan contoh {i}",
            "price": 120_000_000 + i * 5_000_000,
            "land_area": 90,
            "building_area": 70,
            "condition": "Butuh Renovasi",
            "access": "1 Mobil",
            "price_type": "Asking aktif",
            "source_platforms": "Listing test",
            "source_url": f"https://example.test/renovation-{i}",
            "date_found": "2026-11-25",
        }
        for i in range(3)
    ]
    result = run_underwriting(data, {"cash_confirmed": True, "cash_available_for_new_project": 600_000_000}, data["rules"])
    assert result["market"]["arv_condition_comparable_count"] == 0
    assert result["decision"]["investment_status"] == "HOLD"
    assert not result["decision"]["hard_stops"]


def test_underwriting_separates_as_is_fmv_from_ready_to_move_arv():
    from datetime import date

    data = _base_inputs()
    data["survey"]["physical_condition"] = "Renovasi sedang"
    comps = []
    for idx in range(3):
        comps.append({
            "name": f"Rumah kondisi renovasi {idx + 1}",
            "address": f"Jalan Contoh As-Is No. {idx + 1}",
            "price": 320_000_000 + idx * 5_000_000,
            "land_area": 90,
            "building_area": 70,
            "condition": "Butuh Renovasi",
            "price_type": "Asking aktif",
            "market_segment": "Secondary / resale",
            "source_url": f"https://example.com/as-is-{idx + 1}",
            "source_url_scope": "Listing individual",
            "date_found": date.today().isoformat(),
            "listing_date": date.today().isoformat(),
        })
    for idx in range(3):
        comps.append({
            "name": f"Rumah siap huni {idx + 1}",
            "address": f"Jalan Contoh Ready No. {idx + 1}",
            "price": 420_000_000 + idx * 5_000_000,
            "land_area": 90,
            "building_area": 70,
            "condition": "Siap Huni",
            "price_type": "Asking aktif",
            "market_segment": "Secondary / resale",
            "source_url": f"https://example.com/ready-{idx + 1}",
            "source_url_scope": "Listing individual",
            "date_found": date.today().isoformat(),
            "listing_date": date.today().isoformat(),
        })
    data["comparables"] = comps
    result = run_underwriting(
        data,
        {"cash_confirmed": True, "cash_available_for_new_project": 700_000_000},
        dict(DEFAULT_RULES),
    )
    market = result["market"]
    assert market["fmv_as_is"]["comparable_count"] == 3
    assert market["fmv_as_is"]["condition_bucket"] == "Butuh Renovasi"
    assert market["fmv_as_is"]["value"] is not None
    assert market["arv_after_repair"]["comparable_count"] == 3
    assert market["arv_after_repair"]["condition_bucket"] == "Siap Huni"
    assert market["arv_after_repair"]["value"] is not None
    assert market["base_exit"] == market["arv_after_repair"]["value"]
    assert market["fmv_as_is"]["value"] < market["arv_after_repair"]["value"]
    assert market["limit_to_fmv_as_is_pct"] is not None


def test_unmatched_condition_comparables_do_not_qualify_as_arv_or_final_mao():
    from datetime import date

    data = _base_inputs()
    data["survey"]["physical_condition"] = "Renovasi sedang"
    data["comparables"] = [
        {
            "name": f"Comparable renovasi {idx + 1}",
            "address": f"Jalan Contoh Renovasi No. {idx + 1}",
            "price": 350_000_000 + idx * 5_000_000,
            "land_area": 90,
            "building_area": 70,
            "condition": "Butuh Renovasi",
            "price_type": "Asking aktif",
            "market_segment": "Secondary / resale",
            "source_url": f"https://example.com/renovasi-{idx + 1}",
            "source_url_scope": "Listing individual",
            "date_found": date.today().isoformat(),
            "listing_date": date.today().isoformat(),
        }
        for idx in range(5)
    ]
    result = run_underwriting(
        data,
        {"cash_confirmed": True, "cash_available_for_new_project": 700_000_000},
        dict(DEFAULT_RULES),
    )
    market = result["market"]
    assert market.get("valid_count", 0) == 0  # unmatched properties are not used as ARV samples
    assert market["mixed_pool_diagnostic"]["valid_count"] == 5
    assert market["arv_condition_comparable_count"] == 0
    assert market["arv_after_repair"]["status"] == "NO_DATA"
    assert market["arv_after_repair"]["value"] is None
    assert result["decision"]["investment_status"] == "HOLD"
    assert result["mao"]["rule_of_thumb"]["mao"] is None
    assert result["mao"]["full_cost"] is None


def test_fmv_as_is_does_not_claim_indicative_value_from_one_comparable():
    from datetime import date

    data = _base_inputs()
    data["survey"]["physical_condition"] = "Renovasi sedang"
    data["comparables"] = [{
        "name": "Satu comparable as-is",
        "address": "Jalan Contoh As-Is No. 1",
        "price": 320_000_000,
        "land_area": 90,
        "building_area": 70,
        "condition": "Butuh Renovasi",
        "price_type": "Asking aktif",
        "market_segment": "Secondary / resale",
        "source_url": "https://example.com/as-is-one",
        "source_url_scope": "Listing individual",
        "date_found": date.today().isoformat(),
        "listing_date": date.today().isoformat(),
    }] + [{
        "name": f"Rumah siap huni {idx + 1}",
        "address": f"Jalan Contoh Ready No. {idx + 1}",
        "price": 420_000_000 + idx * 5_000_000,
        "land_area": 90,
        "building_area": 70,
        "condition": "Siap Huni",
        "price_type": "Asking aktif",
        "market_segment": "Secondary / resale",
        "source_url": f"https://example.com/ready-one-{idx + 1}",
        "source_url_scope": "Listing individual",
        "date_found": date.today().isoformat(),
        "listing_date": date.today().isoformat(),
    } for idx in range(3)]
    result = run_underwriting(
        data,
        {"cash_confirmed": True, "cash_available_for_new_project": 700_000_000},
        dict(DEFAULT_RULES),
    )
    fmv = result["market"]["fmv_as_is"]
    assert fmv["comparable_count"] == 1
    assert fmv["status"] == "PROVISIONAL"
    assert fmv["value"] is None
    assert fmv["indicative_value"] is not None
    assert result["market"]["limit_to_fmv_as_is_pct"] is not None  # indicative ratio is labelled provisional, not validated


def test_confirmed_fatal_access_or_environment_is_do_not_bid():
    inputs = _base_inputs()
    inputs["property"]["fatal_access_or_environment_confirmed"] = True
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _at_limit())
    assert result["investment_status"] == "DO NOT BID"
    assert any("Akses legal atau kondisi lingkungan fatal" in item for item in result["hard_stops"])


def test_bid_tiers_separate_conditional_ceiling_go_ceiling_and_target_bid():
    inputs = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 0, "possession_months": 0, "interior_inspected": True},
        "costs": {
            "renovation_cost": 10_000_000,
            "renovation_months": 1,
            "selling_months": 3,
            "legal_delay_months": 0,
            "monthly_holding_cost": 0,
            "marketing_cost": 0,
        },
        "rules": {
            **DEFAULT_RULES,
            "buyer_auction_fee_pct": 0,
            "bphtb_rate_pct": 0,
            "seller_final_tax_pct": 0,
            "seller_agent_pct": 0,
            "seller_ajb_ppat_pct": 0,
            "seller_misc_fixed": 0,
        },
    }
    tiers = build_bid_tiers(
        100_000_000,
        1_000_000,
        600_000_000,
        600_000_000,
        inputs,
        None,
        minimum_roi_pct=15,
        mid_roi_pct=30,
        minimum_net_profit=50_000_000,
        maximum_holding_days=180,
        conditional_maximum_holding_days=365,
        go_minimum_roi_pct=25,
    )
    assert tiers["max_bid"] is not None
    assert tiers["go_bid"] is not None
    assert tiers["go_roi_target"] == 25
    assert tiers["mid_roi_target"] == 30
    assert tiers["maximum_holding_days_allowed"] == 365
    assert tiers["go_maximum_holding_days_allowed"] == 180
