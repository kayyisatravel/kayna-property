from __future__ import annotations

import json
from copy import deepcopy

from config import DEFAULT_RULES
from core.calculator import calculate_project
from core.decision_engine import evaluate_decision
from core.feasibility import build_feasibility_scenarios
from core.underwriting import run_underwriting


def _sound_inputs():
    return {
        "property": {
            "lot_code": "LOT-COPILOT-1", "name": "Rumah Contoh", "address": "Waru, Sidoarjo",
            "auction_limit": 100_000_000, "bid_increment": 1_000_000,
            "land_area": 90, "building_area": 70, "njop": 100_000_000,
            "npoptkp_eligible": True, "property_type": "Rumah 1 lantai",
        },
        "survey": {
            "survey_status": "Sudah Survei - Kosong/Tidak Dihuni",
            "physical_condition": "Siap huni", "interior_inspected": True,
            "structure_verified_safe": True, "possession_cost": 2_000_000,
            "possession_risk_reserve": 2_000_000, "possession_months": 0.5,
        },
        "legal": {
            "identity_verified": True, "skpt_verified": True,
            "original_certificate_status": "Asli di bank/kreditur dan siap diserahkan",
            "dispute_detected": False, "tax_rules_verified": True,
        },
        "costs": {
            "renovation_cost": 10_000_000, "renovation_months": 1,
            "selling_months": 2, "legal_delay_months": 0.5,
            "monthly_holding_cost": 1_000_000, "marketing_cost": 1_000_000,
            "cost_estimates_reviewed": True, "renovation_items": [],
        },
        "comparables": [], "risk_register": [], "risk_reviewed": True,
        "rules": deepcopy(DEFAULT_RULES),
    }


def test_owner_arv_allows_feasibility_when_no_listing_can_be_found():
    data = _sound_inputs()
    data["owner_valuation"] = {
        "fmv_as_is_estimate": 390_000_000,
        "arv_estimate": 420_000_000,
        "basis": "Wawancara dua agen lokal dan pengalaman closing area sekitar",
    }
    cash = {"cash_confirmed": True, "cash_available_for_new_project": 300_000_000}
    result = run_underwriting(data, cash, deepcopy(DEFAULT_RULES))
    assert result["market"]["arv_after_repair"]["status"] == "OWNER_INPUT"
    assert result["market"]["arv_after_repair"]["value"] is None
    assert result["market"]["arv_after_repair"]["indicative_value"] == 420_000_000
    assert result["decision"]["mao_full_cost"] is not None
    assert result["decision"]["investment_status"] == "CONDITIONAL GO"
    assert result["decision"]["bid_readiness"].startswith("NOT READY")


def test_single_matched_comparable_remains_visible_as_provisional_not_validated():
    data = _sound_inputs()
    data["comparables"] = [{
        "name": "Listing setara", "address": "Komplek A, Waru", "price": 420_000_000,
        "land_area": 90, "building_area": 70, "condition": "Siap Huni",
        "source_platforms": "Portal listing", "price_type": "Asking aktif",
        "source_url": "https://example.test/listing-one", "source_url_scope": "Listing individual",
        "date_found": "2026-11-27",
    }]
    result = run_underwriting(data, {"cash_confirmed": True, "cash_available_for_new_project": 300_000_000}, deepcopy(DEFAULT_RULES))
    arv = result["market"]["arv_after_repair"]
    assert arv["comparable_count"] == 1
    assert arv["status"] == "PROVISIONAL"
    assert arv["value"] is None
    assert arv["indicative_value"] is not None
    assert result["decision"]["investment_status"] == "CONDITIONAL GO"


def test_unmatched_condition_pool_is_diagnostic_only_and_never_silently_becomes_arv():
    data = _sound_inputs()
    data["survey"]["physical_condition"] = "Renovasi sedang"
    data["comparables"] = [{
        "name": f"Rumah renovasi {i}", "address": f"Jalan Contoh {i}",
        "price": 350_000_000 + i * 2_000_000, "land_area": 90, "building_area": 70,
        "condition": "Butuh Renovasi", "source_url": f"https://example.test/r{i}",
        "source_url_scope": "Listing individual", "date_found": "2026-11-27",
    } for i in range(5)]
    result = run_underwriting(data, {"cash_confirmed": True, "cash_available_for_new_project": 300_000_000}, deepcopy(DEFAULT_RULES))
    assert result["market"]["arv_condition_comparable_count"] == 0
    assert result["market"]["mixed_pool_diagnostic"]["valid_count"] == 5
    assert result["market"]["arv_after_repair"]["status"] == "NO_DATA"
    assert result["at_limit"]["roi_pct"] is None
    assert result["decision"]["investment_status"] == "HOLD"


def test_explicit_hidden_condition_reserve_replaces_percentage_reserve():
    inputs = _sound_inputs()
    inputs["survey"]["interior_inspected"] = False
    inputs["costs"].update({
        "renovation_cost": 20_000_000,
        "renovation_contingency_pct": 15,
        "hidden_condition_reserve_pct": 10,
        "hidden_condition_reserve_amount": 7_000_000,
    })
    result = calculate_project(100_000_000, 420_000_000, inputs)
    assert result["renovation_base_cost"] == 20_000_000
    assert result["renovation_contingency"] == 3_000_000
    assert result["hidden_condition_reserve"] == 7_000_000
    assert result["hidden_condition_reserve_amount_input"] == 7_000_000


def test_percent_hidden_reserve_is_fallback_when_explicit_amount_is_not_entered():
    inputs = _sound_inputs()
    inputs["survey"]["interior_inspected"] = False
    inputs["costs"].update({"renovation_cost": 20_000_000, "hidden_condition_reserve_pct": 10, "hidden_condition_reserve_amount": 0})
    result = calculate_project(100_000_000, 420_000_000, inputs)
    assert result["hidden_condition_reserve"] == 2_000_000


def test_unmeasured_renovation_scope_is_added_to_cost_and_contingency():
    inputs = _sound_inputs()
    inputs["costs"].update({
        "renovation_cost": 20_000_000,
        "unverified_scope_allowance": 12_000_000,
        "renovation_contingency_pct": 20,
    })
    result = calculate_project(100_000_000, 420_000_000, inputs)
    assert result["renovation_base_cost"] == 20_000_000
    assert result["unverified_scope_allowance"] == 12_000_000
    assert result["renovation_cost"] == 32_000_000
    assert result["renovation_contingency"] == 6_400_000


def test_owner_visual_structure_assessment_and_hidden_reserve_are_conditions_not_automatic_hold():
    inputs = _sound_inputs()
    inputs["survey"].update({
        "interior_inspected": False, "structure_verified_safe": False,
        "owner_assessed_structure_safe": True, "building_age_years": 3,
    })
    inputs["costs"]["hidden_condition_reserve_amount"] = 10_000_000
    result = evaluate_decision(
        inputs, {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
                "go_grade_count": 5, "confidence": 75, "status": "READY"},
        {"increment_confirmed": True, "max_bid": 200_000_000},
        {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 120,
         "cash_requirement_including_reserve": 100_000_000},
    )
    assert result["investment_status"] == "CONDITIONAL GO"
    assert any("usia bangunan sekitar 3 tahun" in item for item in result["conditions"])
    assert any("cadangan eksplisit 10,000,000" in item for item in result["conditions"])
    assert any(item["category"] == "SURVEY" for item in result["bid_readiness_issues"])


def test_cash_gap_changes_bid_readiness_not_investment_attractiveness():
    inputs = _sound_inputs()
    inputs["finance"] = {"cash_confirmed": True, "cash_available_for_new_project": 20_000_000}
    market = {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
              "go_grade_count": 5, "confidence": 75, "status": "READY"}
    at_limit = {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 90,
                "cash_requirement_including_reserve": 100_000_000}
    result = evaluate_decision(inputs, market, {"increment_confirmed": True}, at_limit)
    assert result["investment_status"] == "GO"
    assert any(item["category"] == "CASH" for item in result["bid_readiness_issues"])
    assert result["bid_readiness"].startswith("NOT READY")


def test_confirmed_future_cash_is_provisional_until_cleared():
    inputs = _sound_inputs()
    inputs["finance"] = {
        "cash_confirmed": True, "cash_available_for_new_project": 50_000_000,
        "cash_available_for_new_project_at_auction": 150_000_000,
        "expected_cash_is_provisional": True,
    }
    market = {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
              "go_grade_count": 5, "confidence": 75, "status": "READY"}
    at_limit = {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 90,
                "cash_requirement_including_reserve": 100_000_000}
    result = evaluate_decision(inputs, market, {"increment_confirmed": True}, at_limit)
    assert result["investment_status"] == "GO"
    assert any(item["category"] == "CASH CONFIRMATION" for item in result["bid_readiness_issues"])
    assert result["bid_readiness"].startswith("NOT READY")


def test_uncertain_planned_cash_is_not_counted_for_auction():
    inputs = _sound_inputs()
    inputs["finance"] = {
        "cash_confirmed": True, "cash_available_for_new_project": 50_000_000,
        "cash_available_for_new_project_at_auction": 50_000_000,
        "expected_cash_is_provisional": False,
    }
    market = {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
              "go_grade_count": 5, "confidence": 75, "status": "READY"}
    at_limit = {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 90,
                "cash_requirement_including_reserve": 100_000_000}
    result = evaluate_decision(inputs, market, {"increment_confirmed": True}, at_limit)
    assert result["investment_status"] == "GO"
    assert any(item["category"] == "CASH" for item in result["bid_readiness_issues"])


def test_skpt_owner_verification_is_recorded_without_claiming_absolute_legal_guarantee():
    inputs = _sound_inputs()
    inputs["legal"].update({"skpt_verified": True, "original_certificate_status": "Belum diverifikasi"})
    result = evaluate_decision(
        inputs, {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
                "go_grade_count": 5, "confidence": 75, "status": "READY"},
        {"increment_confirmed": True, "max_bid": 200_000_000},
        {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 90,
         "cash_requirement_including_reserve": 100_000_000},
    )
    assert result["investment_status"] == "GO"
    assert any("bukan jaminan" in warning for warning in result["warnings"])
    assert not any(item["category"] == "LEGAL" for item in result["bid_readiness_issues"])
    assert any("serah-terima sertifikat asli" in warning.lower() for warning in result["warnings"])


def test_skpt_verification_separates_property_identity_from_tax_cost_assumptions():
    inputs = _sound_inputs()
    inputs["legal"].update({"skpt_verified": True, "identity_verified": True,
                            "original_certificate_status": "Belum diverifikasi",
                            "tax_rules_verified": False})
    result = evaluate_decision(
        inputs, {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
                "go_grade_count": 5, "confidence": 75, "status": "READY"},
        {"increment_confirmed": True},
        {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 90,
         "cash_requirement_including_reserve": 100_000_000},
    )
    categories = {item["category"] for item in result["bid_readiness_issues"]}
    assert "LEGAL" not in categories
    assert "TAX / COST" in categories
    assert any("sertifikat asli" in warning.lower() for warning in result["warnings"])


def test_medium_renovation_remains_conditional_even_when_inspected_and_budgeted():
    inputs = _sound_inputs()
    inputs["survey"]["physical_condition"] = "Renovasi sedang"
    inputs["finance"] = {"cash_confirmed": True, "cash_available_for_new_project": 500_000_000}
    result = evaluate_decision(
        inputs, {"valuation_comparable_count": 5, "arv_condition_comparable_count": 5,
                "go_grade_count": 5, "confidence": 75, "status": "READY"},
        {"increment_confirmed": True, "max_bid": 200_000_000},
        {"roi_pct": 30, "net_profit": 70_000_000, "projected_holding_days": 120,
         "cash_requirement_including_reserve": 100_000_000},
    )
    assert result["investment_status"] == "CONDITIONAL GO"
    assert result["bid_readiness"] == "READY"


def test_co_pilot_scenarios_are_deterministic_and_stress_case_reduces_returns():
    inputs = _sound_inputs()
    scenarios = build_feasibility_scenarios(
        100_000_000, 380_000_000, 420_000_000,
        {"property": inputs["property"], "survey": inputs["survey"], "legal": inputs["legal"],
         "costs": inputs["costs"], "rules": inputs["rules"], "finance": {}},
        stress_holding_months=12, stress_sale_discount_pct=10,
        stress_extra_cost=20_000_000,
    )
    assert [item["scenario"] for item in scenarios] == ["Cepat", "Moderat", "Tekanan"]
    assert scenarios[0]["holding_days"] <= scenarios[1]["holding_days"]
    assert scenarios[2]["roi_pct"] < scenarios[1]["roi_pct"]
    assert scenarios[2]["net_profit"] < scenarios[1]["net_profit"]


def test_ai_feasibility_brief_prompt_uses_python_calculations_and_owner_authority(monkeypatch):
    import services.gemini_parser as gp
    captured = {}
    fake_response = {
        "executive_summary": "Skenario dasar menarik dengan beberapa friksi.",
        "financial_assessment": "ROI Python 30%.",
        "market_assessment": "ARV Owner masih provisional.",
        "execution_assessment": "Periksa penguasaan dan struktur.",
        "scenario_assessment": ["Skenario tekanan menurunkan profit."],
        "strengths": ["Margin cukup."], "value_drivers": ["Harga akuisisi."],
        "key_risks": ["Interior belum diperiksa."], "mitigations": ["Gunakan cadangan."],
        "assumptions_to_validate": ["Konfirmasi RAB."], "owner_options": ["GO", "SKIP"],
        "reference_recommendation": "CONDITIONAL GO", "recommendation_rationale": "Margin cukup namun ada friksi.",
        "owner_decision_authority": "Keputusan akhir berada pada Owner.",
    }
    def fake_call(api_key, model, prompt, schema=None, max_output_tokens=0):
        captured.update({"api_key": api_key, "model": model, "prompt": prompt, "schema": schema, "max_output_tokens": max_output_tokens})
        return json.dumps(fake_response)
    monkeypatch.setattr(gp, "_client_call", fake_call)
    brief = gp.build_ai_feasibility_brief("test-key", "gemini-flash-test", {
        "property": {"name": "Rumah Uji"},
        "at_limit": {"roi_pct": 30, "net_profit": 70_000_000},
        "market": {"base_exit": 420_000_000, "exit_value_source": "owner_estimate"},
        "feasibility_scenarios": [{"scenario": "Moderat", "roi_pct": 30}],
        "decision": {"investment_status": "CONDITIONAL GO", "bid_readiness": "NOT READY — CASH"},
    })
    assert brief["reference_recommendation"] == "CONDITIONAL GO"
    assert captured["model"] == "gemini-flash-test"
    assert "jangan bertindak sebagai hakim, polisi, atau veto otomatis" in captured["prompt"].lower()
    assert "jangan menghitung ulang angka keuangan" in captured["prompt"].lower()
    assert "pemilik/owner adalah pengambil keputusan akhir" in captured["prompt"].lower()


def test_ai_brief_receives_individual_comparable_observations_for_senior_review(monkeypatch):
    import services.gemini_parser as gp
    captured = {}
    fake_response = {
        "executive_summary": "Indikasi awal.", "financial_assessment": "Mengikuti Python.",
        "market_assessment": "Satu listing masih indikatif.", "execution_assessment": "Perlu cross-check.",
        "scenario_assessment": [], "strengths": [], "value_drivers": [], "key_risks": [],
        "mitigations": [], "assumptions_to_validate": [], "owner_options": ["HOLD", "SKIP"],
        "reference_recommendation": "REVIEW", "recommendation_rationale": "Sampel terbatas.",
    }
    def fake_call(api_key, model, prompt, schema=None, max_output_tokens=0):
        captured["prompt"] = prompt
        return json.dumps(fake_response)
    monkeypatch.setattr(gp, "_client_call", fake_call)
    gp.build_ai_feasibility_brief("test-key", "test-model", {
        "market": {"valid": [{"name": "Listing Rumah Setara", "price": 410000000,
                                "condition": "Siap Huni", "source_url": "https://example.test/house"}]},
        "at_limit": {"roi_pct": 20, "net_profit": 55_000_000},
        "decision": {"investment_status": "CONDITIONAL GO"},
    })
    assert "Listing Rumah Setara" in captured["prompt"]
    assert "listing asking price" in captured["prompt"].lower()


def test_feasibility_memorandum_carries_ai_brief_and_owner_decision():
    from reports.report_builder import build_analysis_markdown
    snapshot = {
        "property": {"name": "Rumah Uji", "lot_code": "LOT-1", "address": "Waru"},
        "decision": {"status": "CONDITIONAL GO", "investment_status": "CONDITIONAL GO",
                     "bid_readiness": "NOT READY — CASH", "summary": "Masih ada syarat."},
        "owner_decision": "GO", "owner_decision_notes": "Saya memiliki jalur cash-for-keys dan dana tambahan.",
        "market": {}, "bidding": {}, "costs": {},
        "ai_feasibility_brief": {
            "executive_summary": "Studi kelayakan AI.",
            "financial_assessment": "ROI skenario moderat 30%.",
            "reference_recommendation": "CONDITIONAL GO", "recommendation_rationale": "Risiko bisa diberi harga.",
            "key_risks": ["Status penghuni."], "mitigations": ["Cadangan pengosongan."],
            "owner_options": ["GO dengan MAO", "SKIP"],
        },
    }
    report = build_analysis_markdown(snapshot)
    assert "Keputusan akhir Owner: **GO**" in report
    assert "Saya memiliki jalur cash-for-keys" in report
    assert "Studi kelayakan AI." in report
    assert "Keputusan final tetap pada Owner." in report


def test_ai_brief_cannot_recommend_go_when_python_confirms_hard_stop(monkeypatch):
    import services.gemini_parser as gp
    fake_response = {
        "executive_summary": "Ada peluang finansial.",
        "financial_assessment": "Angka mengikuti Python.",
        "market_assessment": "Pasar indikatif.",
        "execution_assessment": "Ada hambatan legal.",
        "scenario_assessment": [], "strengths": [], "value_drivers": [],
        "key_risks": ["Gugatan material."], "mitigations": [],
        "assumptions_to_validate": [], "owner_options": ["HOLD", "SKIP"],
        "reference_recommendation": "GO", "recommendation_rationale": "Margin tampak tinggi.",
    }
    monkeypatch.setattr(gp, "_client_call", lambda *a, **k: json.dumps(fake_response))
    result = gp.build_ai_feasibility_brief("test-key", "test-model", {
        "at_limit": {"roi_pct": 30, "net_profit": 70_000_000},
        "decision": {"investment_status": "DO NOT BID", "hard_stops": ["Gugatan material terkonfirmasi."]},
    })
    assert result["reference_recommendation"] == "DO NOT BID"
    assert "hard stop terkonfirmasi" in result["recommendation_rationale"].lower()
