from __future__ import annotations

from io import BytesIO
import json

from docx import Document

from core.calculator import calculate_project
from core.feasibility import build_feasibility_scenarios
from core.stress_test import build_financial_stress_test
from reports.report_builder import build_analysis_docx, build_analysis_markdown, build_analysis_pdf


def _inputs():
    return {
        "property": {"njop": 120_000_000, "npoptkp_eligible": False},
        "survey": {"possession_months": 1, "possession_cost": 5_000_000, "possession_risk_reserve": 5_000_000, "general_risk_reserve": 8_000_000},
        "legal": {},
        "costs": {
            "renovation_cost": 30_000_000,
            "unverified_scope_allowance": 5_000_000,
            "renovation_contingency_pct": 15,
            "renovation_months": 2,
            "legal_delay_months": 1,
            "selling_months": 3,
            "monthly_holding_cost": 1_000_000,
            "marketing_cost": 2_000_000,
            "other_presale_cost": 1_000_000,
        },
        "rules": {
            "buyer_auction_fee_pct": 2,
            "bphtb_rate_pct": 5,
            "npoptkp": 80_000_000,
            "bphtb_basis_mode": "max_bid_or_njop",
            "seller_final_tax_pct": 2.5,
            "seller_agent_pct": 2.5,
            "seller_ajb_ppat_pct": 1,
            "seller_misc_fixed": 5_000_000,
        },
    }


def _snapshot():
    inputs = _inputs()
    test = build_financial_stress_test(150_000_000, 380_000_000, 410_000_000, inputs,
                                       minimum_roi_pct=15, go_roi_pct=25)
    return {
        "property_id": "P-TEST", "analyzed_at": "2026-11-28T09:00:00+00:00",
        "property": {"name": "Rumah Uji", "lot_code": "LOT-1", "address": "Sidoarjo", "auction_limit": 150_000_000, "land_area": 90, "building_area": 60},
        "decision": {"status": "CONDITIONAL GO", "investment_status": "CONDITIONAL GO", "bid_readiness": "NOT READY — CASH", "summary": "Masih ada syarat.", "blockers": [], "warnings": []},
        "market": {"valid_count": 5, "confidence": 60, "conservative_exit": 380_000_000, "base_exit": 410_000_000, "optimistic_exit": 440_000_000,
                   "valid": [{"name": "Listing Pembanding", "price": 400_000_000, "land_area": 90, "building_area": 45, "address": "Sidoarjo", "source_url": "https://example.test/listing"}]},
        "at_limit": calculate_project(150_000_000, 380_000_000, inputs),
        "calculation_inputs": inputs,
        "financial_stress_test": test,
        "feasibility_scenarios": build_feasibility_scenarios(150_000_000, 380_000_000, 410_000_000, inputs),
        "ai_feasibility_brief": {"executive_summary": "Analisis AI uji", "reference_recommendation": "CONDITIONAL GO"},
        "portfolio_context": {"as_of": "2026-11-28", "active_projects": [{"name": "TAS 3 M6/12", "address": "Sidoarjo"}], "completed_projects": []},
        "bidding": {}, "costs": {"renovation_items": []},
        "risk_register": [],
    }


def test_bep_exit_price_returns_zero_net_profit_with_same_calculator():
    inputs = _inputs()
    result = build_financial_stress_test(150_000_000, 380_000_000, 410_000_000, inputs)
    assert result["available"] is True
    check = calculate_project(150_000_000, result["break_even_exit_price"], inputs)
    assert abs(check["net_profit"]) <= 2


def test_roi_hurdle_exit_prices_meet_target_project_roi():
    inputs = _inputs()
    result = build_financial_stress_test(150_000_000, 380_000_000, 410_000_000, inputs,
                                         minimum_roi_pct=15, go_roi_pct=25)
    at_15 = calculate_project(150_000_000, result["exit_price_for_minimum_roi"], inputs)
    at_25 = calculate_project(150_000_000, result["exit_price_for_go_roi"], inputs)
    assert at_15["roi_pct"] >= 15
    assert at_25["roi_pct"] >= 25


def test_stress_cases_are_ordered_and_downside_degrades_return():
    result = build_financial_stress_test(150_000_000, 380_000_000, 410_000_000, _inputs())
    rows = result["scenarios"]
    assert [x["scenario"] for x in rows] == ["Dasar", "Moderat Buruk", "Tekanan", "Ekstrem"]
    assert rows[1]["roi_pct"] < rows[0]["roi_pct"]
    assert rows[-1]["roi_pct"] <= rows[1]["roi_pct"]


def test_max_holding_tolerance_reports_threshold_or_no_tolerance_explicitly():
    result = build_financial_stress_test(150_000_000, 380_000_000, 410_000_000, _inputs(), minimum_roi_pct=15)
    tolerance = result["max_holding_tolerance"]
    assert tolerance["status"] in {"THRESHOLD_CROSSED", "AT_LEAST_SEARCH_CAP", "BELOW_HURDLE_AT_MINIMUM_DURATION"}
    if tolerance["status"] == "THRESHOLD_CROSSED":
        assert tolerance["months"] > 0


def test_feasibility_scenario_ids_make_valuation_mapping_explicit():
    rows = build_feasibility_scenarios(150_000_000, 380_000_000, 410_000_000, _inputs())
    assert [x["scenario_id"] for x in rows] == ["FAST_CONSERVATIVE", "BASE_MODERATE", "STRESS_DISCOUNTED"]
    assert rows[0]["valuation_reference"] == "ARV konservatif"
    assert rows[1]["valuation_reference"] == "ARV dasar"
    assert rows[2]["valuation_reference"] == "ARV dasar dikurangi diskon tekanan"


def test_memo_includes_stress_test_bep_and_price_per_sqm_and_numbering():
    snapshot = _snapshot()
    markdown = build_analysis_markdown(snapshot)
    for token in ["Break-Even Point", "Break-even exit price", "Maximum holding tolerance", "Harga/m² LB", "Harga/m² LT", "## 12. Pertimbangan Analis Senior", "## 13. Portofolio"]:
        assert token in markdown
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert "7. Financial Stress Test dan Break-Even Point" in headings
    assert "11. Blocker dan Peringatan" in headings
    assert "12. Pertimbangan Analis Senior — AI Feasibility Co-Pilot" in headings
    assert "13. Portofolio dan Rekam Jejak Kayna Property" in headings
    all_text = "\n".join(headings) + "\n" + "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    assert "Rp/m² LB" in all_text


def test_pdf_export_is_valid_and_contains_memo_text():
    pdf_bytes = build_analysis_pdf(_snapshot())
    assert pdf_bytes[:8] == b"%PDF-1.4" or pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 5_000
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        assert len(reader.pages) >= 2
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "Break-Even Point" in text
        assert "Rumah Uji" in text
    except ImportError:
        # PDF bytes signature/size remain a minimal integration check if pypdf
        # is not installed in a deployment-oriented environment.
        pass


def test_ai_brief_receives_stress_test_scenario_labels_and_portfolio_context(monkeypatch):
    import services.gemini_parser as gp
    captured = {}
    fake = {
        "executive_summary": "Skenario perlu ditelaah.", "financial_assessment": "Gunakan tabel Python.",
        "market_assessment": "Harga per meter menjadi indikator.", "execution_assessment": "Perhatikan kas portofolio.",
        "scenario_assessment": [], "strengths": [], "value_drivers": [], "key_risks": [], "mitigations": [],
        "assumptions_to_validate": [], "owner_options": ["GO", "HOLD"],
        "reference_recommendation": "REVIEW", "recommendation_rationale": "Menunggu evaluasi Owner.",
    }
    def fake_call(api_key, model, prompt, schema=None, max_output_tokens=0):
        captured["prompt"] = prompt
        return json.dumps(fake)
    monkeypatch.setattr(gp, "_client_call", fake_call)
    gp.build_ai_feasibility_brief("x", "flash", {
        "property": {"name": "Rumah Uji", "land_area": 90, "building_area": 60, "auction_limit": 150_000_000},
        "market": {"valid": [{"name": "Comp", "price": 400_000_000, "land_area": 90, "building_area": 45}], "confidence": 60},
        "financial_stress_test": {"scenarios": [{"scenario": "Ekstrem", "roi_pct": -2}]},
        "feasibility_scenarios": [{"scenario": "Moderat", "scenario_id": "BASE_MODERATE", "exit_price": 410_000_000}],
        "portfolio_context": {"active_projects": [{"name": "TAS 3 M6/12", "committed": 13_000_000}], "completed_projects": []},
        "at_limit": {"roi_pct": 30, "net_profit": 70_000_000}, "decision": {},
    })
    prompt = captured["prompt"]
    assert "scenario_results_python" in prompt
    assert "financial_stress_test_python" in prompt
    assert "portfolio_context" in prompt
    assert "ask_or_adjusted_price_per_sqm_building" in prompt
    assert "jangan menukar angka antarbaris" in prompt.lower()


def test_holding_tolerance_without_exit_is_not_misreported_as_below_hurdle():
    snapshot = _snapshot()
    snapshot["financial_stress_test"]["max_holding_tolerance"] = {"months": None, "status": "NO_EXIT_VALUE"}
    markdown = build_analysis_markdown(snapshot)
    assert "Belum ada nilai exit konservatif" in markdown
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    all_text = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(
        cell.text for table in doc.tables for row in table.rows for cell in row.cells
    )
    assert "Belum ada nilai exit konservatif" in all_text
