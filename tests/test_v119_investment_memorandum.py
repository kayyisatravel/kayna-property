import pytest
from io import BytesIO

from docx import Document

from core.renovation_schedule import estimate_item_duration, estimate_renovation_duration
from reports.report_builder import (
    BRAND_DESCRIPTOR,
    DOCUMENT_TITLE,
    _fmt_wib,
    build_analysis_docx,
    build_analysis_markdown,
    property_filename,
)


def sample_snapshot():
    return {
        "property_id": "PROP-TAS-A5-43",
        "analyzed_at": "2026-11-25T10:20:58+00:00",
        "property": {
            "name": "Rumah TAS 6 Blok A5-43",
            "lot_code": "A5-43",
            "address": "Perum Taman Anggun Sejahtera 6 Blok A5 No. 43, Desa Suwaluh, Kecamatan Balongbendo, Kabupaten Sidoarjo, Jawa Timur",
            "auction_office": "KPKNL Sidoarjo",
            "auction_date": "2026-12-10",
            "deposit_deadline": "2026-12-09",
            "auction_limit": 150_000_000,
            "land_area": 90,
            "building_area": 45,
            "certificate_type": "SHM",
        },
        "decision": {"status": "CONDITIONAL GO", "summary": "Peluang awal menarik setelah verifikasi okupansi dan legalitas.", "blockers": ["Verifikasi status penghuni"], "warnings": ["Harga penawaran bukan harga transaksi"]},
        "market": {
            "valid_count": 6, "confidence": 72,
            "conservative_exit": 350_000_000, "base_exit": 380_000_000, "optimistic_exit": 410_000_000,
            "valid": [{"name": "Rumah TAS 6 Blok A4/32", "price": 375_000_000, "land_area": 90, "building_area": 45,
                       "address": "Perum Taman Anggun Sejahtera 6 Blok A4/32, Desa Suwaluh, Balongbendo, Sidoarjo, Jawa Timur", "source_platforms": "Lamudi Pro"}],
        },
        "bidding": {
            "min_bid": 150_000_000, "mid_bid": 160_000_000, "max_bid": 170_000_000,
            "mid_roi_target": 35, "max_roi_target": 25, "walk_away_from": 175_000_000,
            "walk_away_reason": "Berhenti sebelum bid berikutnya.",
            "mid_result": {"bid_price": 160_000_000, "capital_before_sale": 240_000_000, "possession_risk_reserve": 10_000_000, "general_risk_reserve": 4_000_000, "cash_requirement_including_reserve": 254_000_000, "selling_cost": 11_400_000, "net_proceeds": 368_600_000, "net_profit": 128_600_000, "roi_pct": 53.58},
            "max_result": {"bid_price": 170_000_000, "capital_before_sale": 250_000_000, "possession_risk_reserve": 10_000_000, "general_risk_reserve": 4_000_000, "cash_requirement_including_reserve": 264_000_000, "selling_cost": 11_400_000, "net_proceeds": 368_600_000, "net_profit": 118_600_000, "roi_pct": 47.44},
        },
        "at_limit": {"bid_price": 150_000_000, "capital_before_sale": 230_000_000, "possession_risk_reserve": 10_000_000, "general_risk_reserve": 4_000_000, "cash_requirement_including_reserve": 244_000_000, "selling_cost": 11_400_000, "net_proceeds": 368_600_000, "net_profit": 138_600_000, "roi_pct": 60.26, "holding_months": 4},
        "costs": {"renovation_items": [
            {"subcategory": "Pengecatan", "work_item": "Cat fasad weatherproof", "quantity_low": 30, "quantity": 35, "quantity_high": 40, "unit": "m2", "unit_cost_low": 75_000, "unit_cost": 85_000, "unit_cost_high": 95_000},
            {"subcategory": "Atap", "work_item": "Pembongkaran dan pemasangan kanopi", "quantity_low": 18, "quantity": 18, "quantity_high": 18, "unit": "m2", "unit_cost_low": 120_000, "unit_cost": 150_000, "unit_cost_high": 180_000},
        ]},
        "risk_register": [{"risk_description": "Keterlambatan penguasaan fisik", "probability_1_5": 3, "impact_1_5": 4, "cost_reserve": 10_000_000, "mitigation": "Konfirmasi tertulis dan jadwal pengosongan."}],
        "portfolio_context": {
            "active_projects": [{"name": "TAS 3 Blok M6/12", "address": "Tulangan, Sidoarjo", "stage": "Renovation", "progress_pct": 60, "actual_paid": 50_000_000, "committed": 5_000_000, "forecast": 15_000_000, "budget_total": 80_000_000, "target_sale_date": "2027-01-15"}],
            "completed_projects": [{"name": "TAS 2 Blok A", "address": "Sidoarjo", "sold_date": "2026-08-20", "closing_price": 400_000_000, "total_actual_cost": 300_000_000, "selling_cost_actual": 10_000_000, "net_profit_actual": 90_000_000, "roi_actual_pct": 29.0322580645}],
        },
    }


def doc_text(doc):
    chunks = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            chunks.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(chunks)


def test_analysis_timestamp_uses_wib_for_utc_timestamp():
    assert _fmt_wib("2026-11-25T10:20:58+00:00") == "25 November 2026, 17.20 WIB"
    assert _fmt_wib("2026-11-25") == "25 November 2026"


def test_memo_uses_full_comparable_address_and_no_distance_column():
    snapshot = sample_snapshot()
    markdown = build_analysis_markdown(snapshot)
    assert "Perum Taman Anggun Sejahtera 6 Blok A4/32" in markdown
    assert "| Jarak |" not in markdown
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    text = doc_text(doc)
    assert "Perum Taman Anggun Sejahtera 6 Blok A4/32" in text
    assert "Jarak" not in text


def test_memo_includes_limit_middle_and_upper_bid_scenarios_with_roi():
    snapshot = sample_snapshot()
    markdown = build_analysis_markdown(snapshot)
    for token in ["Bid pada Limit", "Skenario Tengah", "Skenario Atas", "25.0%", "35.0%", "60.3%", "53.6%", "47.4%", "Penjualan bersih"]:
        assert token in markdown
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    text = doc_text(doc)
    for token in ["Skenario Tengah", "Skenario Atas", "Target ROI", "ROI simulasi", "Kebutuhan Kas", "Penjualan bersih"]:
        assert token in text


def test_rab_has_total_row_and_item_work_duration_same_estimator_basis():
    snapshot = sample_snapshot()
    markdown = build_analysis_markdown(snapshot)
    assert "TOTAL RAB DASAR" in markdown
    assert "Durasi C/D/K" in markdown
    items = snapshot["costs"]["renovation_items"]
    duration = estimate_item_duration(items[0])
    schedule = estimate_renovation_duration(items)
    assert duration["base"] > 0
    assert schedule["available"] is True
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    text = doc_text(doc)
    assert "TOTAL" in text and "Total RAB dasar" in text
    assert "Durasi C/D/K" in text
    assert "Harga satuan (Rp)" in text
    assert "Subtotal dasar (Rp)" in text
    assert "2.975.000" in text
    assert "5.675.000" in text
    assert "critical path" in text.lower()


def test_dynamic_economy_snapshot_is_not_inserted_into_memo_until_live_source_available():
    snapshot = sample_snapshot()
    markdown = build_analysis_markdown(snapshot)
    assert "Konteks Ekonomi Regional" not in markdown
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    assert "Konteks Ekonomi Regional" not in doc_text(doc)


def test_portfolio_appendix_includes_active_progress_and_completed_realized_results():
    snapshot = sample_snapshot()
    markdown = build_analysis_markdown(snapshot)
    for token in ["Proyek Aktif", "TAS 3 Blok M6/12", "60%", "Proyek Selesai dan Hasil Aktual", "TAS 2 Blok A", "90.000.000"]:
        assert token in markdown
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    text = doc_text(doc)
    for token in ["TAS 3 Blok M6/12", "Progres: 60%", "TAS 2 Blok A", "Profit / ROI / XIRR aktual"]:
        assert token in text


def test_memo_brand_and_title_are_professional_and_navy_high_contrast():
    snapshot = sample_snapshot()
    data = build_analysis_docx(snapshot)
    doc = Document(BytesIO(data))
    assert DOCUMENT_TITLE in doc.paragraphs[0].text
    assert BRAND_DESCRIPTOR in doc.sections[0].header.paragraphs[0].text
    assert property_filename(snapshot).startswith("proposal-investasi-properti-rumah-tas-6-blok-a5-43")
    sizes = []
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if run.font.size:
                sizes.append(run.font.size.pt)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if run.font.size:
                            sizes.append(run.font.size.pt)
    assert sizes and min(sizes) >= 11
    assert doc.tables[1].style.name == "Light Shading Accent 1"
    assert doc.sections[0].header.paragraphs[0].runs[0].font.color.rgb == (23, 43, 77)
    assert doc.sections[0].header_distance.inches < 0.3
    assert doc.sections[0].top_margin.inches >= 0.9
    assert "— juta" not in doc_text(doc)


def test_portfolio_context_builds_active_progress_and_closed_budget_arv_variance():
    from reports.portfolio_context import build_portfolio_report_context

    props = [
        {"property_id": "A", "name": "Project Active", "address": "Sidoarjo", "lifecycle_status": "ACTIVE",
         "payload": {"project_stage": "Renovation", "planned_sale_date": "2027-02-01"}},
        {"property_id": "S", "name": "Project Sold", "address": "Sidoarjo", "lifecycle_status": "SOLD",
         "payload": {"latest_analysis": {"market": {"base_exit": 400_000_000}}}},
    ]
    actuals = [
        {"property_id": "A", "category": "Renovasi", "amount": 40_000_000},
        {"property_id": "S", "category": "Renovasi", "amount": 280_000_000},
        {"property_id": "S", "category": "Penjualan", "amount": 8_000_000},
    ]
    budgets = [
        {"property_id": "A", "category": "Renovasi", "budget_amount": 80_000_000, "committed_unpaid": 5_000_000, "forecast_remaining": 20_000_000},
        {"property_id": "S", "category": "Renovasi", "budget_amount": 300_000_000},
        {"property_id": "S", "category": "Penjualan", "budget_amount": 10_000_000},
    ]
    milestones = [
        {"property_id": "A", "status": "Completed"},
        {"property_id": "A", "status": "In Progress"},
    ]
    closings = [{"property_id": "S", "sold_date": "2026-10-01", "closing_price": 390_000_000, "selling_cost_actual": 8_000_000, "total_holding_months": 3}]
    result = build_portfolio_report_context(props, actuals, budgets, milestones, closings, as_of="2026-11-25")
    active = result["active_projects"][0]
    assert active["progress_pct"] == 50
    assert active["actual_paid"] == 40_000_000
    assert active["target_sale_date"] == "2027-02-01"
    sold = result["completed_projects"][0]
    assert sold["base_arv"] == 400_000_000
    assert sold["closing_vs_base_arv_pct"] == pytest.approx(-2.5)
    assert sold["budget_project_total"] == 300_000_000
    assert sold["budget_variance_actual"] == 20_000_000


def test_comparable_and_bid_tables_have_compact_v118_layout_and_numeric_first_columns():
    snapshot = sample_snapshot()
    doc = Document(BytesIO(build_analysis_docx(snapshot)))
    tables = {tuple(cell.text for cell in table.rows[0].cells): table for table in doc.tables if table.rows}
    comparable_header = ("Alamat lengkap", "Harga penawaran", "LT / LB (m²)", "Rp/m² LB", "Rp/m² LT", "URL / sumber")
    assert comparable_header in tables
    assert len(tables[comparable_header].rows[0].cells) == 6
    scenario_headers = ("Komponen", "Limit · 150,0", "Tengah · 160,0", "Atas · 170,0")
    assert scenario_headers in tables
    for header in [scenario_headers]:
        assert len(tables[header].rows[0].cells) == 4
    for header in [
        ("Bid / ceiling (Rp juta)", "Target ROI", "ROI simulasi", "Catatan"),
    ]:
        assert header in tables



def test_comparable_source_cell_prefers_short_domain_to_long_repeated_address():
    snapshot = sample_snapshot()
    snapshot["market"]["valid"][0]["source_url"] = "https://www.brighton.co.id/cari-properti/view/perumtas-6-long-listing-url"
    markdown = build_analysis_markdown(snapshot)
    assert "brighton.co.id" in markdown
    assert "perumtas-6-long-listing-url" not in markdown
