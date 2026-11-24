from __future__ import annotations

from core.auction_dates import normalize_auction_date
from core.renovation_engine import rab_row_subtotals, summarize_rab_scope_totals
from core.renovation_pricing import apply_regional_screening_rates, PRICE_CATALOG_VERSION
from reports.report_builder import investment_memo_filename, build_analysis_markdown, build_investment_memo_docx


def test_regional_pricebook_is_deterministic_and_overrides_ai_rates():
    row = {
        "item_code": "USER_BOQ_001", "work_item": "Pengecatan ulang dinding interior rumah utama",
        "quantity": 100, "unit": "m2", "unit_cost_low": 99_000, "unit_cost": 123_000,
        "unit_cost_high": 155_000, "priority": "Wajib",
    }
    first = apply_regional_screening_rates([row])[0]
    second = apply_regional_screening_rates([row])[0]
    assert first["unit_cost_low"] == second["unit_cost_low"] == 45_000
    assert first["unit_cost"] == second["unit_cost"] == 65_000
    assert first["unit_cost_high"] == second["unit_cost_high"] == 90_000
    assert first["price_book_version"] == PRICE_CATALOG_VERSION
    assert "Cross-check Gemini" in first["notes"]


def test_unmapped_gemini_rate_is_not_used_in_project_calculation():
    row = {
        "item_code": "USER_BOQ_099", "work_item": "Pekerjaan mikrostruktur khusus tanpa katalog",
        "quantity": 1, "unit": "paket", "unit_cost_low": 1_000_000, "unit_cost": 2_000_000,
        "unit_cost_high": 3_000_000, "priority": "Wajib",
    }
    priced = apply_regional_screening_rates([row])[0]
    assert priced["unit_cost_low"] is None
    assert priced["unit_cost"] is None
    assert priced["unit_cost_high"] is None
    assert "Cross-check Gemini" in priced["notes"]
    assert "quotation" in priced["rate_basis"].lower()


def test_tas_user_boq_common_scopes_are_all_mapped_in_stable_book():
    rows = [
        {"work_item": "Pembersihan, pelumasan engsel/kunci, dan pengecekan karet kusen pintu & jendela", "unit": "ls", "quantity": 1, "priority": "Wajib"},
        {"work_item": "Peremajaan dan pengecekan fungsi titik instalasi listrik (saklar, stopkontak, fitting lampu)", "unit": "titik", "quantity": 7, "priority": "Wajib"},
        {"work_item": "Pembersihan keramik lantai dalam dan pengecekan nat keramik", "unit": "m2", "quantity": 40, "priority": "Wajib"},
        {"work_item": "Servis ringan sanitair kamar mandi, keran air, dan pengecekan saluran air bersih/kotor", "unit": "ls", "quantity": 1, "priority": "Wajib"},
    ]
    priced = apply_regional_screening_rates(rows)
    assert all(r["unit_cost"] and r["unit_cost_low"] and r["unit_cost_high"] for r in priced)
    assert all(r["price_book_version"] == PRICE_CATALOG_VERSION for r in priced)


def test_rab_subtotals_calculate_per_item_and_per_group():
    rows = [
        {"subcategory": "Pengecatan", "work_item": "Cat fasad", "quantity_low": 30, "quantity": 35, "quantity_high": 40, "unit_cost_low": 50_000, "unit_cost": 70_000, "unit_cost_high": 90_000, "priority": "Wajib"},
        {"subcategory": "Pengecatan", "work_item": "Cat interior", "quantity_low": 90, "quantity": 100, "quantity_high": 110, "unit_cost_low": 40_000, "unit_cost": 60_000, "unit_cost_high": 80_000, "priority": "Wajib"},
        {"subcategory": "Pengecatan", "work_item": "Cat plafon", "quantity": 20, "unit_cost": 50_000, "priority": "Bersyarat"},
    ]
    assert rab_row_subtotals(rows[0])["subtotal_base"] == 2_450_000
    groups = summarize_rab_scope_totals(rows)
    assert len(groups) == 1
    assert groups[0]["Subtotal dasar (Rp)"] == 2_450_000 + 6_000_000
    assert groups[0]["Jumlah item"] == 2


def test_kpk_n_dates_parse_indonesian_months_without_relative_guessing():
    assert normalize_auction_date("Senin, 30 November 2026") == "2026-11-30"
    assert normalize_auction_date("Batas setor: 25-11-2026") == "2026-11-25"
    assert normalize_auction_date("2026/11/25") == "2026-11-25"
    assert normalize_auction_date("3 hari sebelum lelang") == ""
    assert normalize_auction_date("November 2026") == ""


def _sample_snapshot():
    return {
        "property_id": "PROP-123", "analyzed_at": "2026-11-24 10:00",
        "property": {"name": "Rumah TAS Contoh Blok A5-43", "lot_code": "A5-43", "address": "Suwaluh, Balongbendo, Sidoarjo", "auction_office": "KPKNL Sidoarjo", "auction_date": "2026-12-03", "deposit_deadline": "2026-11-30", "auction_limit": 200_000_000, "deposit_amount": 40_000_000, "land_area": 90, "building_area": 45},
        "market": {"valid_count": 3, "go_grade_count": 1, "confidence": 68, "confidence_band": "Cukup", "conservative_exit": 330_000_000, "base_exit": 365_000_000, "optimistic_exit": 390_000_000, "valid": [{"name": "Listing A", "price": 375_000_000, "land_area": 90, "building_area": 45, "subject_normalized_value": 360_000_000, "distance_km": 0.5, "similarity_score": 92, "source_url": "https://example.com/listing-a"}]},
        "bidding": {"min_bid": 200_000_000, "mid_economic_ceiling": 205_000_000, "max_economic_ceiling": 210_000_000, "walk_away_reason": "Batas ceiling", "provisional": True, "provisional_reasons": ["Sampel pasar masih terbatas"]},
        "at_limit": {"bid_price": 200_000_000, "capital_before_sale": 250_000_000, "net_profit": 40_000_000, "roi_pct": 16, "selling_cost": 15_000_000, "renovation_cost": 20_000_000, "renovation_contingency": 3_000_000, "hidden_condition_reserve": 1_500_000, "buyer_auction_fee": 4_000_000, "bphtb": 5_000_000, "legal_bpn_cost": 2_000_000, "possession_cost": 5_000_000, "holding_cost": 5_000_000, "other_presale_cost": 1_000_000, "cash_requirement_including_reserve": 260_000_000},
        "costs": {"renovation_cost": 20_000_000, "renovation_months": 1, "renovation_items": [{"item_code": "USER_BOQ_001", "subcategory": "Pengecatan", "work_item": "Cat fasad", "quantity": 35, "unit": "m2", "unit_cost": 70_000, "unit_cost_low": 50_000, "unit_cost_high": 90_000, "priority": "Wajib", "confidence": "Sedang"}]},
        "rules": {"renovation_contingency_pct": 15, "hidden_condition_reserve_pct": 7.5},
        "decision": {"status": "HOLD", "blockers": ["Identitas objek belum diverifikasi"], "warnings": ["Harga listing berupa asking"]},
        "survey": {"survey_status": "Sudah Survei", "occupancy_status": "Belum diketahui", "interior_inspected": False},
        "legal": {"identity_verified": False, "tax_rules_verified": False},
        "risk_register": [{"risk_description": "Interior belum diperiksa", "probability_1_5": 4, "impact_1_5": 4, "cost_reserve": 20_000_000, "mitigation": "Inspeksi sebelum renovasi"}],
        "liquidity": {"cash_available_for_new_project": 300_000_000},
        "funding": {"project_cash_need": 260_000_000, "full_project_funded": True},
        "calculation_inputs": {"property": {"auction_limit": 200_000_000}, "rules": {}, "costs": {}, "survey": {}},
    }


def test_investment_memo_filename_uses_property_name_and_docx_is_generated():
    snap = _sample_snapshot()
    assert "rumah-tas-contoh-blok-a5-43" in investment_memo_filename(snap)
    assert "A5-43" not in investment_memo_filename(snap)  # slugified
    md = build_analysis_markdown(snap)
    assert "Ringkasan Eksekutif" in md and "Subtotal dasar" in md and "Risk Register" in md
    docx_bytes = build_investment_memo_docx(snap)
    assert docx_bytes[:2] == b"PK"
    assert len(docx_bytes) > 10_000


def test_manual_price_override_remains_locked_against_regional_catalog():
    row = {
        "item_code": "USER_BOQ_010",
        "work_item": "Pengecatan ulang dinding interior rumah utama",
        "quantity": 100,
        "unit": "m2",
        "unit_cost_low": 72_000,
        "unit_cost": 88_000,
        "unit_cost_high": 105_000,
        "price_source": "Override manual pengguna",
        "priority": "Wajib",
        "notes": "Berdasarkan penawaran mandor lokal 22 Nov 2026",
    }
    priced = apply_regional_screening_rates([row])[0]
    assert priced["unit_cost_low"] == 72_000
    assert priced["unit_cost"] == 88_000
    assert priced["unit_cost_high"] == 105_000
    assert priced["manual_price_locked"] is True
    assert "katalog tidak menimpa" in priced["notes"].lower()


def test_auction_document_extractor_requests_distinct_explicit_date_evidence(monkeypatch):
    import json
    import services.gemini_parser as parser
    captured = {}

    def fake_client_call(api_key, model, prompt, file_bytes, mime_type, schema, max_output_tokens):
        captured["prompt"] = prompt
        return json.dumps({
            "auction_date": "Kamis, 3 Desember 2026",
            "deposit_deadline": "30 November 2026",
            "payment_deadline": "5 Desember 2026",
            "field_evidence": {
                "auction_date": "Pelaksanaan lelang: 3 Desember 2026",
                "deposit_deadline": "Setor jaminan paling lambat 30 November 2026",
            },
        })

    monkeypatch.setattr(parser, "_client_call", fake_client_call)
    result = parser.extract_auction_document("test-key", b"%PDF-test", "application/pdf", "pengumuman.pdf")
    assert result["extraction_schema_version"] == "AUCTION_EXTRACT_V2"
    assert result["auction_date"] == "2026-12-03"
    assert result["deposit_deadline"] == "2026-11-30"
    assert result["payment_deadline"] == "2026-12-05"
    assert "Jangan menukar tanggal pengumuman" in captured["prompt"]
    assert "field_evidence.auction_date" in captured["prompt"]


def test_group_subtotal_shows_unknown_as_blank_not_zero():
    rows = [{
        "subcategory": "Plumbing", "work_item": "Pekerjaan khusus belum terukur",
        "quantity": 1, "unit": "ls", "unit_cost": None,
        "priority": "Wajib",
    }]
    group = summarize_rab_scope_totals(rows)[0]
    assert group["Subtotal dasar (Rp)"] is None
    assert group["Subtotal rendah (Rp)"] is None
    assert group["Subtotal atas (Rp)"] is None
    assert group["Item belum lengkap"] == 1
