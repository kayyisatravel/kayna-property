from datetime import date
from io import BytesIO

from docx import Document

from core.dashboard import build_dashboard_view
from reports.report_builder import build_analysis_docx, build_analysis_markdown


def memo_snapshot():
    return {
        "property_id": "P-01", "analyzed_at": "2026-11-25T10:00:00+00:00",
        "property": {"name": "Rumah Uji", "lot_code": "U-01", "address": "Sidoarjo", "auction_limit": 150_000_000, "deposit_amount": 15_000_000},
        "liquidity": {"cash_available_for_new_project": 300_000_000},
        "decision": {"status": "CONDITIONAL GO", "summary": "Perlu verifikasi akhir."},
        "market": {"valid_count": 5, "confidence": 75, "conservative_exit": 350_000_000, "base_exit": 380_000_000, "optimistic_exit": 410_000_000, "valid": []},
        "at_limit": {
            "bid_price": 150_000_000, "buyer_auction_fee": 3_000_000, "bphtb": 3_500_000,
            "bpn_pnbp_cost": 2_000_000, "roya_cost": 1_000_000, "other_acquisition_admin": 1_500_000,
            "other_legal_cost": 500_000, "acquisition_notary_ppat_fee": 0, "possession_cost": 5_000_000,
            "renovation_cost": 30_000_000, "renovation_contingency": 4_500_000, "hidden_condition_reserve": 2_250_000,
            "holding_cost": 4_000_000, "marketing_cost": 2_000_000, "other_presale_cost_only": 1_000_000,
            "capital_before_sale": 210_250_000, "possession_risk_reserve": 5_000_000, "general_risk_reserve": 4_000_000,
            "cash_requirement_including_reserve": 219_250_000, "exit_price": 350_000_000, "seller_final_tax": 8_750_000,
            "seller_agent": 8_750_000, "seller_ajb_ppat": 3_500_000, "seller_misc": 5_000_000,
            "selling_cost": 26_000_000, "net_proceeds": 324_000_000, "net_profit": 113_750_000, "roi_pct": 54.1,
        },
        "bidding": {
            "min_bid": 150_000_000, "mid_bid": 160_000_000, "max_bid": 170_000_000,
            "mid_roi_target": 35, "max_roi_target": 25, "walk_away_from": 175_000_000,
            "mid_result": {"bid_price": 160_000_000, "capital_before_sale": 220_000_000, "buyer_auction_fee": 3_200_000,
                           "cash_requirement_including_reserve": 229_000_000, "possession_risk_reserve": 5_000_000,
                           "general_risk_reserve": 4_000_000, "exit_price": 350_000_000, "seller_final_tax": 8_750_000,
                           "seller_agent": 8_750_000, "seller_ajb_ppat": 3_500_000, "seller_misc": 5_000_000,
                           "selling_cost": 26_000_000, "net_proceeds": 324_000_000, "net_profit": 104_000_000, "roi_pct": 47.3},
            "max_result": {"bid_price": 170_000_000, "capital_before_sale": 230_000_000, "buyer_auction_fee": 3_400_000,
                           "cash_requirement_including_reserve": 239_000_000, "possession_risk_reserve": 5_000_000,
                           "general_risk_reserve": 4_000_000, "exit_price": 350_000_000, "seller_final_tax": 8_750_000,
                           "seller_agent": 8_750_000, "seller_ajb_ppat": 3_500_000, "seller_misc": 5_000_000,
                           "selling_cost": 26_000_000, "net_proceeds": 324_000_000, "net_profit": 94_000_000, "roi_pct": 40.8},
        },
        "costs": {"renovation_items": []},
    }


def test_proposal_includes_three_requested_financial_tables_for_all_bid_levels():
    snapshot = memo_snapshot()
    md = build_analysis_markdown(snapshot)
    for token in [
        "Rincian Total Modal per Level Bidding", "Kebutuhan Kas dan Cadangan Risiko",
        "Biaya Penjualan dan Hasil Bersih", "PNBP BPN", "Contingency renovasi",
        "TOTAL MODAL PRA-PENJUALAN", "TOTAL KEBUTUHAN KAS",
        "PENJUALAN BERSIH setelah biaya penjualan".lower(), "ROI PROYEK", "Kas tersedia",
    ]:
        assert token.lower() in md.lower()
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    tables = [tuple(c.text for c in t.rows[0].cells) for t in doc.tables]
    assert tables.count(("Komponen", "Limit · 150,0", "Tengah · 160,0", "Atas · 170,0")) >= 3
    content = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(" ".join(c.text for c in r.cells) for t in doc.tables for r in t.rows)
    assert "219,2" in content or "219.3" in content or "219,3" in content
    assert "Penjualan bersih" in content


def test_dashboard_view_surfaces_upcoming_auction_and_deposit_deadlines():
    properties = [{
        "property_id": "A", "name": "Rumah Balongbendo", "lot_code": "A-1", "lifecycle_status": "PROSPECT",
        "auction_date": "2026-12-10", "payload": {"input_data": {"property": {"deposit_deadline": "2026-12-08"}}},
    }]
    view = build_dashboard_view(properties, [], [], [], [], today=date(2026, 11, 25))
    assert view["summary"]["prospects"] == 1
    assert view["summary"]["upcoming_auction_events"] == 2
    assert [x["event"] for x in view["auction_events"]] == ["Batas setor jaminan", "Tanggal lelang"]
    assert view["auction_events"][0]["days"] == 13


def test_dashboard_view_creates_budget_and_sales_deadline_alerts_without_sheets_calls():
    properties = [{
        "property_id": "ACTIVE-1", "name": "TAS 3 M6/12", "lifecycle_status": "ACTIVE",
        "payload": {"planned_sale_date": "2026-11-10", "project_stage": "Renovation"},
    }]
    actuals = [{"property_id": "ACTIVE-1", "category": "Renovasi", "amount": 80_000_000}]
    budgets = [{"property_id": "ACTIVE-1", "category": "Renovasi", "budget_amount": 100_000_000,
                "committed_unpaid": 10_000_000, "forecast_remaining": 20_000_000}]
    view = build_dashboard_view(properties, [], actuals, budgets, [], today=date(2026, 11, 25))
    alerts = view["project_alerts"]
    assert any(a["type"] == "sales_overdue" for a in alerts)
    assert any(a["type"] == "budget_overrun" for a in alerts)
    project = view["active_projects"][0]
    assert project["projected_total"] == 110_000_000


def test_dashboard_does_not_count_selling_budget_as_project_cost():
    properties = [{"property_id": "A", "lifecycle_status": "ACTIVE", "payload": {"planned_sale_date": "2027-02-01"}}]
    budgets = [
        {"property_id": "A", "category": "Renovasi", "budget_amount": 100_000_000},
        {"property_id": "A", "category": "Penjualan", "budget_amount": 15_000_000},
    ]
    view = build_dashboard_view(properties, [], [], budgets, [], today=date(2026, 11, 25))
    assert view["active_projects"][0]["budget_total"] == 100_000_000


def test_dashboard_view_includes_duration_weighted_physical_progress():
    properties = [{
        "property_id": "ACTIVE-PROGRESS", "name": "Proyek TAS", "lifecycle_status": "ACTIVE",
        "payload": {"planned_sale_date": "2027-02-01"},
    }]
    budgets = [
        {"property_id": "ACTIVE-PROGRESS", "category": "Renovasi", "description": "Pengecatan dinding interior", "quantity": 100, "unit": "m2",
         "payload": {"work_item": "Pengecatan dinding interior", "quantity": 100, "unit": "m2", "work_status": "Selesai"}},
        {"property_id": "ACTIVE-PROGRESS", "category": "Renovasi", "description": "Pemasangan keramik carport", "quantity": 30, "unit": "m2",
         "payload": {"work_item": "Pemasangan keramik carport", "quantity": 30, "unit": "m2", "work_status": "Berjalan", "work_progress_pct": 50}},
        {"property_id": "ACTIVE-PROGRESS", "category": "Renovasi", "description": "Servis sanitair kamar mandi", "quantity": 1, "unit": "ls",
         "payload": {"work_item": "Servis sanitair kamar mandi", "quantity": 1, "unit": "ls"}},
    ]
    view = build_dashboard_view(properties, [], [], budgets, [], today=date(2026, 11, 25))
    project = view["active_projects"][0]
    assert project["progress_pct"] is not None
    assert project["tracked_work_items"] == 2
    assert project["total_work_items"] == 3
    assert 0 < project["progress_pct"] < 100
    assert round(project["progress_coverage_pct"]) == 67
