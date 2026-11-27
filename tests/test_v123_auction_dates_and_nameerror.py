from datetime import date
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

from core.auction_dates import add_working_days, apply_extracted_auction_dates, derive_payment_deadline
from core.decision_engine import bid_reference_status
from reports.report_builder import build_analysis_markdown


def test_five_weekday_estimate_from_actual_win_date():
    result = derive_payment_deadline("2026-11-27", win_date="2026-12-01")
    assert result["payment_deadline"] == "2026-12-08"
    assert result["payment_deadline_rule_days"] == "5"
    assert "tanggal menang 2026-12-01" in result["payment_deadline_basis"]
    assert result["payment_deadline_source"].startswith("Informasi internal")


def test_preauction_deadline_is_only_a_scenario_from_scheduled_auction_date():
    result = derive_payment_deadline("2026-11-27")
    assert result["payment_deadline"] == "2026-12-04"
    assert "Simulasi internal jika menang" in result["payment_deadline_basis"]
    assert "bukan tenggat resmi" in result["payment_deadline_basis"]


def test_add_working_days_skips_weekends_but_does_not_embed_annual_holiday_data():
    # Weekday-only information. Public holidays/cuti bersama are deliberately
    # not guessed or maintained in code; official KPKNL date remains authority.
    assert add_working_days("2026-12-24", 5) == date(2026, 12, 31)
    assert add_working_days("2026-11-27", 5) == date(2026, 12, 4)


def test_explicit_kpknl_deadline_is_preserved_as_document_source():
    result = derive_payment_deadline("2026-11-27", explicit_deadline="10 Desember 2026")
    assert result["payment_deadline"] == "2026-12-10"
    assert result["payment_deadline_source"] == "Dokumen KPKNL"


def test_apply_extracted_dates_prefills_editable_date_values_and_estimate():
    state = {}
    applied = apply_extracted_auction_dates(
        state,
        {
            "auction_date": "27 November 2026",
            "deposit_deadline": "26 November 2026",
            "auction_type": "Eksekusi Hak Tanggungan",
            "auction_limit": 200_000_000,
            "payment_deadline": None,
            "field_evidence": {"auction_date": "Tanggal pelaksanaan 27 November 2026", "deposit_deadline": "Batas akhir setor 26 November 2026"},
        },
        document_hash="abc",
    )
    assert applied["auction_date"] == "2026-11-27"
    assert applied["deposit_deadline"] == "2026-11-26"
    assert applied["payment_deadline"] == "2026-12-04"
    assert state["na_auction_date_picker"] == date(2026, 11, 27)
    assert state["na_deposit_deadline_picker"] == date(2026, 11, 26)
    assert state["na_payment_deadline_source"].startswith("Informasi internal")


def test_bid_reference_status_is_importable_and_usable():
    status = bid_reference_status(
        {"roi_pct": 25, "net_profit": 60_000_000, "projected_holding_days": 80},
        minimum_roi_pct=20, target_roi_pct=30, minimum_net_profit=50_000_000,
        target_holding_days=90, maximum_holding_days=180,
    )
    assert "MEMENUHI GATE MINIMUM" in status


def test_optional_date_picker_helper_exists_and_is_called_for_shgb_expiry():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "def optional_date_picker(" in app_source
    assert 'optional_date_picker("Tanggal berakhir hak SHGB' in app_source


def test_auction_analysis_has_sequential_navigation_and_no_tabs():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "st.tabs([\"1 · Data lelang" not in app_source
    for label in (
        "LANJUT KE SURVEI",
        "LANJUT KE PEMBANDING",
        "LANJUT KE BIAYA / RAB",
        "SUSUN FEASIBILITY STUDY",
    ):
        assert label in app_source
    assert "_na_persisted_form_state" in app_source


def test_app_imports_bid_reference_status_and_optional_date_picker_is_defined():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "from core.decision_engine import bid_reference_status" in app_source
    assert "def optional_date_picker(" in app_source
    assert "Tanggal lelang sudah diketahui" not in app_source
    assert "Batas setor uang jaminan sudah diketahui" not in app_source


def test_investment_memo_labels_informational_payment_date_not_official_deadline():
    snapshot = {
        "property_id": "PROP-1", "analyzed_at": "2026-11-27T10:00:00+07:00",
        "property": {
            "name": "Rumah Contoh", "address": "Tulangan, Sidoarjo",
            "auction_date": "2026-11-27", "deposit_deadline": "2026-11-26",
            "payment_deadline": "2026-12-04",
            "payment_deadline_basis": "Simulasi internal jika menang pada tanggal lelang 2026-11-27: 5 hari kerja.",
            "payment_deadline_source": "Informasi internal (simulasi dari tanggal lelang)",
        },
        "decision": {"status": "HOLD", "summary": "Data sedang ditinjau."},
        "market": {}, "bidding": {}, "costs": {}, "comparables": [],
    }
    memo = build_analysis_markdown(snapshot)
    assert "Informasi perkiraan pelunasan" in memo
    assert "4 Des 2026" in memo
    assert "bukan tenggat resmi" in memo


def test_docx_proposal_includes_informational_payment_date_basis():
    from reports.report_builder import build_investment_memo_docx
    snapshot = {
        "property_id": "PROP-2", "analyzed_at": "2026-11-27T10:00:00+07:00",
        "property": {
            "name": "Rumah Uji KPKNL", "lot_code": "LOT-2", "address": "Sidoarjo",
            "auction_date": "2026-11-27", "deposit_deadline": "2026-11-26",
            "payment_deadline": "2026-12-04",
            "payment_deadline_basis": "Estimasi internal: 5 hari kerja setelah tanggal menang 2026-11-27; bukan tenggat resmi.",
            "payment_deadline_source": "Informasi internal (perkiraan)",
            "auction_date_source_file": "Pengumuman_KPKNL.pdf",
        },
        "decision": {"status": "HOLD", "summary": "Data uji."},
        "market": {}, "bidding": {}, "costs": {}, "comparables": [],
    }
    docx_bytes = build_investment_memo_docx(snapshot)
    with ZipFile(BytesIO(docx_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "4 Des 2026" in document_xml
    assert "Informasi perkiraan pelunasan" in document_xml
    assert "bukan tenggat resmi" in document_xml
    assert "Pengumuman_KPKNL.pdf" in document_xml
