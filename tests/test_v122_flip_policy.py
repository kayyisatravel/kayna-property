from __future__ import annotations

from config import DEFAULT_RULES, MIN_ROI_PCT, MID_ROI_PCT, MINIMUM_NET_PROFIT, TARGET_HOLDING_DAYS, MAX_HOLDING_DAYS
from core.calculator import calculate_project
from core.decision_engine import evaluate_decision
from core.lifecycle import actual_project_summary
from core.market_engine import assess_comparables
from core.maximum_bid import build_bid_tiers, find_maximum_bid


def _complete_decision_input():
    return {
        "property": {"lot_code": "KAYNA-01", "address": "Grabagan, Tulangan, Sidoarjo", "auction_limit": 150_000_000, "land_area": 90, "building_area": 40},
        "survey": {"survey_status": "Sudah Survei - Kosong/Tidak Dihuni", "physical_condition": "Siap huni", "interior_inspected": True, "structure_verified_safe":True},
        "legal": {"identity_verified": True, "original_certificate_status":"Asli di bank/kreditur dan siap diserahkan", "dispute_detected": False, "tax_rules_verified": True},
        "rules": dict(DEFAULT_RULES),
        "costs": {"cost_estimates_reviewed": True, "renovation_items": []},
        "finance": {"cash_confirmed": True, "cash_available_for_new_project": 1_000_000_000},
        "risk_reviewed": True,
    }


def _decision_at_limit(*, roi=25, profit=60_000_000, days=90):
    return {
        "roi_pct": roi,
        "net_profit": profit,
        "capital_before_sale": 200_000_000,
        "cash_requirement_including_reserve": 220_000_000,
        "projected_holding_days": days,
    }


def _market_ready():
    return {"valid_count": 5, "go_grade_count": 5, "confidence": 75, "status": "READY"}


def _tiers_ready():
    return {"increment_confirmed": True, "max_bid": 150_000_000}


def _comparable(name, price, segment, **overrides):
    row = {
        "name": name,
        "address": f"Perumahan contoh {name}",
        "price": price,
        "land_area": 90,
        "building_area": 40,
        "condition": "Siap Huni",
        "access": "1 Mobil",
        "certificate": "SHM",
        "price_type": "Asking aktif",
        "market_segment": segment,
        "source_platforms": "Listing individual test",
        "source_url": f"https://example.test/{name.replace(' ', '-').lower()}",
        "source_url_scope": "Listing individual",
        "date_found": "2026-11-25",
        "listing_date": "2026-11-20",
    }
    row.update(overrides)
    return row


def test_kayna_flip_policy_defaults_are_minimum_15_target_30_profit_50m_and_90_180_365_days():
    assert MIN_ROI_PCT == 15
    assert MID_ROI_PCT == 30
    assert DEFAULT_RULES["minimum_roi_pct"] == 15
    assert DEFAULT_RULES["conditional_minimum_roi_pct"] == 15
    assert DEFAULT_RULES["go_minimum_roi_pct"] == 25
    assert DEFAULT_RULES["conditional_maximum_holding_days"] == 365
    assert DEFAULT_RULES["mid_roi_pct"] == 30
    assert MINIMUM_NET_PROFIT == 50_000_000
    assert DEFAULT_RULES["minimum_net_profit"] == 50_000_000
    assert TARGET_HOLDING_DAYS == 90
    assert MAX_HOLDING_DAYS == 180


def test_roi_and_profit_below_investment_floor_are_hold_not_fatal_risk():
    inputs = _complete_decision_input()
    below_profit = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(roi=25, profit=49_999_999))
    below_roi = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(roi=19.99, profit=60_000_000))
    assert below_profit["status"] == "HOLD"
    assert any("minimum" in item.lower() for item in below_profit["hold_reasons"])
    assert below_roi["status"] == "CONDITIONAL GO"
    assert any("ROI" in item for item in below_roi["conditions"])
    assert below_roi["bid_readiness"] == "READY"


def test_25_roi_is_go_floor_under_new_investment_policy():
    inputs = _complete_decision_input()
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(roi=25, profit=60_000_000, days=90))
    assert result["status"] == "GO"
    assert result["minimum_roi_pct"] == 15
    assert result["conditional_minimum_roi_pct"] == 15
    assert result["go_minimum_roi_pct"] == 25
    assert result["target_roi_pct"] == 30
    assert any("belum mencapai target 30.0%" in item for item in result["warnings"])


def test_holding_91_days_warns_and_181_days_is_conditional_window():
    inputs = _complete_decision_input()
    in_review_window = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(days=91))
    over_limit = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(days=181))
    assert in_review_window["status"] == "GO"
    assert any("di atas target ideal 90 hari" in item for item in in_review_window["warnings"])
    assert over_limit["status"] == "CONDITIONAL GO"
    assert any("melewati target GO 180 hari" in item for item in over_limit["conditions"])
    beyond_conditional = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(days=366))
    assert beyond_conditional["status"] == "HOLD"
    assert any("melampaui asumsi maksimum 365 hari" in item for item in beyond_conditional["hold_reasons"])


def test_missing_project_duration_is_a_condition_not_an_automatic_veto():
    inputs = _complete_decision_input()
    at_limit = _decision_at_limit()
    at_limit.pop("projected_holding_days")
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), at_limit)
    assert result["status"] == "CONDITIONAL GO"
    assert result["duration_missing"] is True
    assert any(item["category"] == "TIME" for item in result["bid_readiness_issues"])


def test_maximum_bid_obeys_roi_profit_and_duration_at_the_same_time():
    inputs = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 5_000_000, "possession_months": 0.5, "interior_inspected": True, "structure_verified_safe":True},
        "costs": {"renovation_cost": 30_000_000, "renovation_months": 1, "selling_months": 1.5,
                   "legal_delay_months": 0.5, "monthly_holding_cost": 1_000_000, "marketing_cost": 2_000_000},
        "rules": dict(DEFAULT_RULES),
    }
    tiers = build_bid_tiers(
        100_000_000, 1_000_000, 350_000_000, 400_000_000, inputs, None,
        minimum_roi_pct=20, mid_roi_pct=30, optimistic_exit=450_000_000,
        minimum_net_profit=50_000_000, maximum_holding_days=180,
    )
    assert tiers["max_bid"] is not None
    assert tiers["mid_bid"] is not None
    assert tiers["max_result"]["roi_pct"] >= 20
    assert tiers["max_result"]["net_profit"] >= 50_000_000
    assert tiers["max_result"]["projected_holding_days"] == 105
    assert tiers["mid_result"]["roi_pct"] >= 30
    next_increment = calculate_project(tiers["max_bid"] + 1_000_000, 350_000_000, inputs)
    assert next_increment["roi_pct"] < 20 or next_increment["net_profit"] < 50_000_000
    assert tiers["base_case_max_bid"] >= tiers["max_bid"]
    assert tiers["upper_case_max_bid"] >= tiers["base_case_max_bid"]


def test_maximum_bid_is_not_computable_when_duration_exceeds_180_days_or_is_missing():
    long_inputs = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 5_000_000, "possession_months": 4},
        "costs": {"renovation_cost": 30_000_000, "renovation_months": 1, "selling_months": 2,
                   "legal_delay_months": 0, "monthly_holding_cost": 1_000_000},
        "rules": dict(DEFAULT_RULES),
    }
    too_long = find_maximum_bid(400_000_000, long_inputs, 100_000_000, 1_000_000, 20)
    assert too_long["maximum_bid"] is None
    assert too_long["economic_ceiling"] is None
    assert "durasi melewati 180 hari" in too_long["reason"].lower()

    missing_duration = {
        "property": {"njop": 0, "npoptkp_eligible": False}, "survey": {}, "costs": {}, "rules": dict(DEFAULT_RULES)
    }
    missing = find_maximum_bid(400_000_000, missing_duration, 100_000_000, 1_000_000, 20)
    assert missing["maximum_bid"] is None
    assert "durasi proyek belum tersedia" in missing["reason"].lower()


def test_primary_developer_competition_does_not_pull_up_secondary_base_arv():
    subject = {"land_area": 90, "building_area": 40, "bedrooms": 2, "bathrooms": 1}
    secondary = [
        _comparable("Secondary A", 375_000_000, "Secondary / resale"),
        _comparable("Secondary B", 390_000_000, "Secondary / resale"),
        _comparable("Secondary C", 400_000_000, "Secondary / resale"),
    ]
    base_only = assess_comparables(secondary, subject)
    with_primary = assess_comparables(secondary + [
        _comparable("Primary D", 590_000_000, "Primary / developer"),
        _comparable("Primary E", 640_000_000, "Primary / developer"),
    ], subject)
    assert with_primary["base_exit"] == base_only["base_exit"]
    assert with_primary["valuation_comparable_count"] == 3
    assert with_primary["primary_competition_count"] == 2
    assert with_primary["primary_competition_median"] is not None
    assert all(not row["valuation_in_primary_arv"] for row in with_primary["valid"] if row["market_segment"] == "Primary / developer")


def test_promotion_value_only_adjusts_price_when_explicitly_verified():
    subject = {"land_area": 90, "building_area": 40}
    unverified = assess_comparables([
        _comparable("Promo unverified", 500_000_000, "Secondary / resale",
                    promotion_claims="Free BPHTB, KPR tanpa DP", promotion_value_verified=False,
                    verified_promotion_value=100_000_000)
    ], subject, negotiation_discount_pct=10)
    verified = assess_comparables([
        _comparable("Promo verified", 500_000_000, "Secondary / resale",
                    promotion_claims="Free biaya akad", promotion_value_verified=True,
                    verified_promotion_value=20_000_000)
    ], subject, negotiation_discount_pct=10)
    assert unverified["valid"][0]["effective_asking_price"] == 500_000_000
    assert unverified["valid"][0]["negotiated_price"] == 450_000_000
    assert verified["valid"][0]["effective_asking_price"] == 480_000_000
    assert verified["valid"][0]["negotiated_price"] == 432_000_000


def test_underlying_property_id_prevents_cross_portal_duplicate_weight():
    subject = {"land_area": 90, "building_area": 40}
    rows = [
        _comparable("Listing Facebook", 390_000_000, "Secondary / resale", underlying_property_id="HOUSE-001"),
        _comparable("Listing Portal", 390_000_000, "Secondary / resale", underlying_property_id="HOUSE-001", source_url="https://example.test/other-portal"),
    ]
    result = assess_comparables(rows, subject)
    assert result["valid_count"] == 1
    assert any("duplikat objek fisik" in " ".join(row["errors"]) for row in result["invalid"])


def test_actual_xirr_uses_dated_cashflows_and_never_fabricates_missing_dates():
    actual_costs = [
        {"category": "Acquisition", "amount": 100_000_000, "transaction_date": "2025-01-01"},
        {"category": "Renovation", "amount": 10_000_000, "transaction_date": "2025-07-01"},
        {"category": "Selling", "amount": 20_000_000, "transaction_date": "2026-01-01"},
    ]
    sale = {"closing_price": 140_000_000, "selling_cost_actual": 20_000_000, "sold_date": "2026-01-01", "total_holding_months": 12}
    result = actual_project_summary(actual_costs, sale)
    assert result["net_profit_actual"] == 10_000_000
    assert result["xirr_actual_pct"] is not None
    assert 9 < result["xirr_actual_pct"] < 10
    assert result["xirr_status"] == "Tersedia dari arus kas bertanggal"

    missing_date = actual_project_summary(
        [{"category": "Acquisition", "amount": 100_000_000}, {"category": "Renovation", "amount": 10_000_000, "transaction_date": "2025-07-01"}],
        {"closing_price": 140_000_000, "sold_date": "2026-01-01", "total_holding_months": 12},
    )
    assert missing_date["xirr_actual_pct"] is None
    assert "tanggal lengkap" in missing_date["xirr_status"].lower()


def test_actual_xirr_is_withheld_when_closing_selling_cost_does_not_reconcile_to_ledger():
    result = actual_project_summary(
        [
            {"category": "Acquisition", "amount": 100_000_000, "transaction_date": "2025-01-01"},
            {"category": "Selling", "amount": 5_000_000, "transaction_date": "2025-06-01"},
        ],
        {"closing_price": 140_000_000, "selling_cost_actual": 10_000_000, "sold_date": "2025-06-01", "total_holding_months": 5},
    )
    assert result["xirr_actual_pct"] is None
    assert result["selling_cost_reconciliation_gap"] == 5_000_000
    assert "rekonsiliasi diperlukan" in result["xirr_status"].lower()


def test_limit_reference_status_reports_all_in_profit_duration_and_cash_gates():
    from core.decision_engine import bid_reference_status

    result = {
        "roi_pct": 25.0,
        "net_profit": 60_000_000,
        "projected_holding_days": 120,
    }
    status = bid_reference_status(
        result, minimum_roi_pct=20, target_roi_pct=30,
        minimum_net_profit=50_000_000, target_holding_days=90,
        maximum_holding_days=180, provisional=False,
    )
    assert "MEMENUHI GATE MINIMUM" in status
    assert "ROI BELUM MENCAPAI TARGET 30.0%" in status
    assert "DURASI 120 HARI DI ATAS TARGET IDEAL 90 HARI" in status

    below_profit = bid_reference_status(
        {**result, "net_profit": 49_000_000}, 20, 30, 50_000_000, 90, 180
    )
    assert "PROFIT BERSIH" in below_profit and "REVIEW MAO" in below_profit

    too_long = bid_reference_status(
        {**result, "projected_holding_days": 181}, 20, 30, 50_000_000, 90, 180
    )
    assert "MELEWATI" in too_long and "UJI SKENARIO" in too_long

    no_duration = bid_reference_status(
        {"roi_pct": 25, "net_profit": 60_000_000}, 20, 30, 50_000_000, 90, 180
    )
    assert "BELUM TERSEDIA" in no_duration and "ASUMSI HOLDING" in no_duration


def test_roi_above_target_is_never_capped_or_penalized():
    inputs = _complete_decision_input()
    result = evaluate_decision(inputs, _market_ready(), _tiers_ready(), _decision_at_limit(roi=55, profit=100_000_000, days=75))
    assert result["status"] == "GO"
    assert not any("di atas target" in item.lower() for item in result["warnings"])


def test_limit_reference_status_requires_confirmed_investor_cash():
    from core.decision_engine import bid_reference_status

    status = bid_reference_status(
        {"roi_pct": 30, "net_profit": 60_000_000, "projected_holding_days": 90},
        minimum_roi_pct=20, target_roi_pct=30, minimum_net_profit=50_000_000,
        target_holding_days=90, maximum_holding_days=180,
        cash_need=200_000_000, cash_available=500_000_000,
        cash_confirmed=False,
    )
    assert "BELUM DIKONFIRMASI" in status and "KEPUTUSAN BID" in status
