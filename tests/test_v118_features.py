from datetime import date
from io import BytesIO

import pytest

from core.auction_dates import apply_extracted_auction_dates
from core.auction_outcomes import build_auction_outcome_record, implied_discount_vs_limit
from core.project_alerts import assess_project_alerts
from core.renovation_schedule import estimate_renovation_duration
from reports.regional_economy import build_regional_economy_context, ECONOMY_SNAPSHOT_VERSION
from reports.report_builder import build_analysis_docx, property_filename


def test_kpknl_dates_prefill_editable_date_picker_state_and_can_be_overridden():
    state = {}
    applied = apply_extracted_auction_dates(
        state,
        {
            "auction_date": "2026-12-10",
            "deposit_deadline": "2026-12-09",
            "payment_deadline": "2026-12-24",
            "field_evidence": {"auction_date": {"quote": "Pelaksanaan 10 Desember 2026"}},
        },
        document_hash="abc123",
    )
    assert applied == {
        "auction_date": "2026-12-10",
        "deposit_deadline": "2026-12-09",
        "payment_deadline": "2026-12-24",
    }
    assert state["na_auction_date_picker"] == date(2026, 12, 10)
    assert state["na_auction_date_has_value"] is True
    # This helper deliberately does not lock user input. A later picker edit is valid.
    state["na_auction_date_picker"] = date(2026, 12, 11)
    state["na_auction_date"] = "2026-12-11"
    assert state["na_auction_date"] == "2026-12-11"
    assert state["na_auction_date_document_hash"] == "abc123"


def test_kpknl_invalid_or_ambiguous_date_is_not_guessed():
    state = {"na_auction_date": "2026-12-01", "na_auction_date_picker": date(2026, 12, 1), "na_auction_date_has_value": True}
    applied = apply_extracted_auction_dates(state, {"auction_date": "3 Desember 2026 atau 10 Desember 2026"})
    assert applied == {}
    assert state["na_auction_date"] == ""
    assert state["na_auction_date_has_value"] is False
    assert "na_auction_date_picker" not in state
    valid = apply_extracted_auction_dates({}, {"auction_date": "10 Desember 2026"})
    assert valid == {"auction_date": "2026-12-10"}


def test_other_winner_result_is_saved_as_market_reference_without_personal_data():
    row = build_auction_outcome_record(
        property_id="P-1", property_name="Rumah TAS", lot_code="A5-43",
        auction_date="2026-11-25", auction_limit=150_000_000,
        outcome_status="Pemenang lain - harga diketahui", winning_price=187_000_000,
        price_type="Harga menang resmi", source_grade="Dokumen resmi KPKNL",
        source_url="https://example.test/hasil",
    )
    assert row["winning_price"] == 187_000_000
    assert row["payload"]["is_market_evidence"] is True
    assert "winner_name" not in row and "winner_identity" not in row
    assert implied_discount_vs_limit(150_000_000, 187_000_000) == pytest.approx(24.6666667)


def test_auction_outcome_requires_price_type_and_source_grade():
    with pytest.raises(ValueError, match="Jenis harga wajib"):
        build_auction_outcome_record(
            outcome_status="Pemenang lain - harga diketahui", winning_price=200_000_000,
            source_grade="Dokumen resmi KPKNL",
        )
    with pytest.raises(ValueError, match="Kualitas sumber wajib"):
        build_auction_outcome_record(
            outcome_status="Tidak ada penawaran / tidak laku", winning_price=0,
            source_grade="",
        )


def test_renovation_schedule_returns_fast_base_and_slow_duration_by_rab_volume():
    result = estimate_renovation_duration([
        {"work_item": "Pembongkaran atap kanopi", "quantity": 18, "unit": "m²"},
        {"work_item": "Pemasangan atap galvalum baru", "quantity": 18, "unit": "m²"},
        {"work_item": "Cat ulang dinding fasad", "quantity": 50, "unit": "m²"},
        {"work_item": "Peremajaan instalasi listrik", "quantity": 15, "unit": "Titik"},
    ])
    assert result["available"] is True
    assert result["calendar_days"]["fast"] > 0
    assert result["calendar_days"]["fast"] <= result["calendar_days"]["base"] <= result["calendar_days"]["slow"]
    assert result["phases"]


def test_project_alerts_detect_overdue_sales_and_budget_overrun():
    result = assess_project_alerts(
        today=date(2026, 11, 25), target_sale_date=date(2026, 11, 10), is_sold=False,
        budget_total=253_856_000, projected_completion=260_000_000,
    )
    types = {x["type"] for x in result["alerts"]}
    assert types == {"sales_overdue", "budget_overrun"}
    assert result["budget_remaining"] == -6_144_000
    assert result["days_overdue"] == 15


def test_project_alerts_near_budget_thresholds():
    result = assess_project_alerts(
        today=date(2026, 11, 25), target_sale_date=None, is_sold=False,
        budget_total=100_000_000, projected_completion=85_000_000,
    )
    assert result["budget_remaining"] == 15_000_000
    assert result["alerts"][0]["type"] == "budget_near_limit"


def test_regional_economy_context_only_uses_matching_current_published_sources():
    result = build_regional_economy_context("Balongbendo, Kabupaten Sidoarjo, Jawa Timur", date(2026, 11, 25))
    assert result is not None
    assert result["version"] == ECONOMY_SNAPSHOT_VERSION
    assert any("Sidoarjo" in row["geography"] for row in result["items"])
    assert all(row["url"].startswith("https://") for row in result["items"])
    assert "tidak mengukur harga" in result["items"][0]["interpretation"] or result["limitations"]


def test_regional_economy_context_is_omitted_for_unmatched_or_stale_data():
    assert build_regional_economy_context("Bali", date(2026, 11, 25)) is None
    assert build_regional_economy_context("Sidoarjo", date(2028, 12, 31)) is None


def test_investment_memo_docx_has_kayna_brand_minimum_11pt_and_property_filename():
    snapshot = {
        "property_id": "PROP-123",
        "analyzed_at": "2026-11-25",
        "property": {"name": "Rumah TAS 6 Blok A5-43", "lot_code": "A5-43", "address": "Balongbendo, Sidoarjo"},
        "decision": {"status": "HOLD", "summary": "Perlu verifikasi dokumen."},
        "market": {"valid_count": 3, "confidence": 71, "conservative_exit": 350_000_000, "base_exit": 380_000_000, "optimistic_exit": 410_000_000},
        "bidding": {"min_bid": 150_000_000, "mid_bid": 160_000_000, "max_bid": 165_000_000, "walk_away_from": 170_000_000},
        "at_limit": {"capital_before_sale": 250_000_000, "selling_cost": 10_000_000, "net_profit": 90_000_000, "roi_pct": 36, "holding_months": 4},
        "costs": {"renovation_items": [{"subcategory": "Pengecatan", "work_item": "Cat fasad", "quantity": 35, "unit": "m2", "unit_cost": 85_000}]},
    }
    data = build_analysis_docx(snapshot)
    assert data[:2] == b"PK"
    assert property_filename(snapshot).startswith("investment-memo-rumah-tas-6-blok-a5-43")
    from docx import Document
    doc = Document(BytesIO(data))
    assert "KAYNA PROPERTY" in doc.sections[0].header.paragraphs[0].text
    sizes = []
    for paragraph in doc.paragraphs:
        sizes.extend(run.font.size.pt for run in paragraph.runs if run.font.size)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    sizes.extend(run.font.size.pt for run in paragraph.runs if run.font.size)
    for section in doc.sections:
        for part in (section.header, section.footer):
            for paragraph in part.paragraphs:
                sizes.extend(run.font.size.pt for run in paragraph.runs if run.font.size)
    assert sizes and min(sizes) >= 11


def test_budget_remaining_sign_matches_budget_less_forecast_example():
    budget_total = 253_856_000
    projected_cost = 246_643_344
    result = assess_project_alerts(
        today=date(2026, 11, 25), target_sale_date=None, is_sold=False,
        budget_total=budget_total, projected_completion=projected_cost,
    )
    assert result["budget_remaining"] == 7_212_656
    assert result["budget_usage_pct"] == pytest.approx(97.1587, rel=1e-4)
    assert result["alerts"][0]["type"] == "budget_near_limit"


def test_v118_google_sheets_schema_adds_auction_outcomes_without_removing_chunk_support():
    from storage.gsheets_db import SCHEMA
    assert "AUCTION_OUTCOMES" in SCHEMA
    assert "PAYLOAD_CHUNKS" in SCHEMA
    assert "winning_price" in SCHEMA["AUCTION_OUTCOMES"]
    assert "data" in SCHEMA["PAYLOAD_CHUNKS"]


def test_v118_pricebook_rates_are_deterministic_and_unmapped_ai_rates_are_not_used():
    from core.renovation_pricing import apply_regional_screening_rates, PRICE_CATALOG_VERSION
    rows = [
        {"item_code":"USER_BOQ_001", "work_item":"Pengecatan ulang dinding fasad eksterior weatherproof 2 lapis", "quantity":35, "unit":"m2", "unit_cost":99_999, "unit_cost_low":80_000, "unit_cost_high":120_000},
        {"item_code":"USER_BOQ_002", "work_item":"Pekerjaan struktur khusus belum ada detail desain", "quantity":1, "unit":"ls", "unit_cost":8_000_000, "unit_cost_low":6_000_000, "unit_cost_high":10_000_000},
    ]
    first = apply_regional_screening_rates(rows)
    second = apply_regional_screening_rates(rows)
    assert first[0]["unit_cost"] == second[0]["unit_cost"]
    assert first[0]["price_book_version"] == PRICE_CATALOG_VERSION
    # Unknown scope retains AI values only in notes; no financial rate is accepted.
    assert first[1]["unit_cost"] is None
    assert "Cross-check Gemini" in first[1]["notes"]
