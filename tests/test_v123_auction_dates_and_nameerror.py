from datetime import date
from pathlib import Path

from core.auction_dates import (
    add_working_days,
    apply_extracted_auction_dates,
    derive_payment_deadline,
)
from core.decision_engine import bid_reference_status
from reports.report_builder import build_analysis_markdown


def test_standard_payment_deadline_is_five_working_days_after_auction():
    result = derive_payment_deadline("2026-11-27", auction_type="Eksekusi Hak Tanggungan", auction_limit=200_000_000)
    # Friday auction: Mon 30 Nov to Fri 4 Dec, counting the next workday as day 1.
    assert result["payment_deadline"] == "2026-12-04"
    assert result["payment_deadline_rule_days"] == "5"
    assert "5 hari kerja" in result["payment_deadline_basis"]


def test_payment_deadline_skips_weekends_and_indonesian_holidays_and_collective_leave():
    # Auction on 24 Dec 2026. 25 Dec is holiday and 24 Dec collective leave
    # is auction day itself; counting starts after auction, so Dec 28-31 and
    # Jan 4 are the five subsequent working days (Jan 1 is a holiday).
    assert add_working_days("2026-12-24", 5) == date(2027, 1, 4)


def test_payment_deadline_uses_explicit_kpknl_date_when_present():
    result = derive_payment_deadline(
        "2026-11-27", auction_type="Eksekusi Hak Tanggungan", auction_limit=200_000_000,
        explicit_deadline="10 Desember 2026",
    )
    assert result["payment_deadline"] == "2026-12-10"
    assert result["payment_deadline_source"] == "Dokumen KPKNL"


def test_payment_deadline_regulatory_exceptions_are_handled():
    special = derive_payment_deadline("2026-11-27", auction_type="Lelang Terjadwal Khusus")
    large_limit = derive_payment_deadline("2026-11-27", auction_limit=500_000_000_000)
    institutional = derive_payment_deadline("2026-11-27", buyer_is_government_institution=True)
    assert special["payment_deadline_rule_days"] == "2"
    assert large_limit["payment_deadline_rule_days"] == "14"
    assert institutional["payment_deadline_rule_days"] == "14"


def test_apply_extracted_dates_prefills_editable_date_values_and_derived_payment_date():
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
    assert state["na_payment_deadline_source"] == "Otomatis dari tanggal lelang"


def test_bid_reference_status_is_importable_and_usable():
    status = bid_reference_status(
        {"roi_pct": 25, "net_profit": 60_000_000, "projected_holding_days": 80},
        minimum_roi_pct=20, target_roi_pct=30, minimum_net_profit=50_000_000,
        target_holding_days=90, maximum_holding_days=180,
    )
    assert "MEMENUHI GATE MINIMUM" in status


def test_app_imports_bid_reference_status_and_has_no_redundant_auction_date_checkboxes():
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "from core.decision_engine import bid_reference_status" in app_source
    assert "Tanggal lelang sudah diketahui" not in app_source
    assert "Batas setor uang jaminan sudah diketahui" not in app_source
    assert "prefilled_editable_date_picker(\n                \"Tanggal lelang\"" in app_source
    assert "prefilled_editable_date_picker(\n                \"Batas setor uang jaminan\"" in app_source


def test_investment_memo_uses_same_derived_payment_deadline_and_basis_as_analysis():
    snapshot = {
        "property_id": "PROP-1", "analyzed_at": "2026-11-27T10:00:00+07:00",
        "property": {
            "name": "Rumah Contoh", "address": "Tulangan, Sidoarjo",
            "auction_date": "2026-11-27", "deposit_deadline": "2026-11-26",
            "payment_deadline": "2026-12-04",
            "payment_deadline_basis": "PMK 122/2023 Pasal 88 ayat (1) — 5 hari kerja; kalender SKB_3_MENTERI_2026_2027",
        },
        "decision": {"status": "HOLD", "summary": "Data sedang ditinjau."},
        "market": {}, "bidding": {}, "costs": {}, "comparables": [],
    }
    memo = build_analysis_markdown(snapshot)
    assert "Batas pelunasan: 4 Des 2026" in memo
    assert "PMK 122/2023 Pasal 88 ayat (1)" in memo
    assert "Dokumen sumber jadwal" in memo


def test_docx_proposal_includes_same_auction_dates_and_payment_deadline_basis():
    from io import BytesIO
    from zipfile import ZipFile
    from reports.report_builder import build_investment_memo_docx

    snapshot = {
        "property_id": "PROP-2", "analyzed_at": "2026-11-27T10:00:00+07:00",
        "property": {
            "name": "Rumah Uji KPKNL", "lot_code": "LOT-2", "address": "Sidoarjo",
            "auction_date": "2026-11-27", "deposit_deadline": "2026-11-26",
            "payment_deadline": "2026-12-04",
            "payment_deadline_basis": "PMK 122/2023 Pasal 88 ayat (1) — 5 hari kerja",
            "auction_date_source_file": "Pengumuman_KPKNL.pdf",
        },
        "decision": {"status": "HOLD", "summary": "Data uji."},
        "market": {}, "bidding": {}, "costs": {}, "comparables": [],
    }
    docx_bytes = build_investment_memo_docx(snapshot)
    with ZipFile(BytesIO(docx_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "4 Des 2026" in document_xml
    assert "5 hari kerja" in document_xml
    assert "Pengumuman_KPKNL.pdf" in document_xml
