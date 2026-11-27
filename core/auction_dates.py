"""Date parsing and informational payment-date estimates for auction analysis.

The application intentionally does not embed a year-specific public-holiday
calendar. It estimates five Monday-to-Friday working days from the actual win
date (or, before an auction is won, from the scheduled auction date as a
planning proxy). The KPKNL notice / official confirmation remains authoritative.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

_MONTHS = {
    "januari": "01", "jan": "01", "februari": "02", "feb": "02",
    "maret": "03", "mar": "03", "april": "04", "apr": "04",
    "mei": "05", "juni": "06", "jun": "06", "juli": "07", "jul": "07",
    "agustus": "08", "agu": "08", "ags": "08", "september": "09", "sep": "09",
    "oktober": "10", "okt": "10", "november": "11", "nov": "11",
    "desember": "12", "des": "12",
}
_WEEKDAYS = r"(?:senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu)"


def normalize_auction_date(value: Any) -> str:
    """Normalize one explicit Indonesian date; never infer relative dates."""
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    if not raw or re.search(r"\b(\d+\s*(hari|jam)\s*(sebelum|setelah)|H-\d+)\b", raw, re.I):
        return ""
    text = raw.lower()
    text = re.sub(_WEEKDAYS + r"\s*,?\s*", "", text, flags=re.I)
    text = re.sub(r"\b(tanggal|tgl\.?|pada|hari|batas setor|setor uang jaminan|tanggal lelang)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:")
    for month, number in _MONTHS.items():
        text = re.sub(rf"\b{month}\b", number, text)
    text = re.sub(r"\s+", " ", text).strip()
    candidates = re.findall(
        r"(?<!\d)(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2}|\d{1,2}\s+[01]?\d\s+20\d{2})(?!\d)",
        text,
    )
    if len(candidates) != 1:
        return ""
    date_text = candidates[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %m %Y"):
        try:
            return datetime.strptime(date_text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def auction_date_evidence(extraction: dict[str, Any], field: str) -> str:
    evidence = extraction.get("field_evidence") or {}
    if not isinstance(evidence, dict):
        return ""
    return str(evidence.get(field) or "").strip()


def build_auction_date_provenance(extraction: dict[str, Any], field: str) -> dict[str, str]:
    value = normalize_auction_date(extraction.get(field))
    return {
        "value": value,
        "evidence": auction_date_evidence(extraction, field),
        "document_sha256": str(extraction.get("document_sha256") or ""),
        "source_file": str(extraction.get("source_file_name") or "Pengumuman lelang yang diunggah"),
    }


def is_indonesian_working_day(value: date, extra_non_working_dates: set[str] | None = None) -> bool:
    """Simple weekday-only estimate; public holidays are not auto-maintained."""
    blocked = extra_non_working_dates or set()
    return value.weekday() < 5 and value.isoformat() not in blocked


def add_working_days(start_date: Any, working_days: int, extra_non_working_dates: set[str] | None = None) -> date | None:
    """Count Monday-Friday working days AFTER start_date; start date is day 0."""
    iso = normalize_auction_date(start_date)
    if not iso:
        return None
    current = date.fromisoformat(iso)
    remaining = max(0, int(working_days))
    while remaining:
        current += timedelta(days=1)
        if is_indonesian_working_day(current, extra_non_working_dates):
            remaining -= 1
    return current


def derive_payment_deadline(
    auction_date: Any = "",
    *,
    win_date: Any = "",
    auction_type: str = "",
    auction_limit: Any = None,
    explicit_deadline: Any = "",
    buyer_is_government_institution: bool = False,
) -> dict[str, str]:
    """Return KPKNL's explicit date or a five-weekday internal planning estimate.

    Legacy keyword parameters are accepted for compatibility with saved V1.0.22
    data, but do not cause legal-exception or year-specific holiday calculations.
    """
    explicit_iso = normalize_auction_date(explicit_deadline)
    if explicit_iso:
        return {
            "payment_deadline": explicit_iso,
            "payment_deadline_basis": "Tanggal eksplisit yang tertulis pada dokumen KPKNL; ikuti dokumen resmi.",
            "payment_deadline_source": "Dokumen KPKNL",
            "payment_deadline_rule_days": "",
            "payment_deadline_reference_date": "",
        }

    actual_win_iso = normalize_auction_date(win_date)
    scheduled_iso = normalize_auction_date(auction_date)
    reference_iso = actual_win_iso or scheduled_iso
    if not reference_iso:
        return {
            "payment_deadline": "",
            "payment_deadline_basis": "Menunggu tanggal lelang atau tanggal menang aktual.",
            "payment_deadline_source": "Belum dapat dihitung",
            "payment_deadline_rule_days": "5",
            "payment_deadline_reference_date": "",
        }

    due = add_working_days(reference_iso, 5)
    if actual_win_iso:
        basis = (
            f"Estimasi internal: 5 hari kerja (Senin–Jumat) setelah tanggal menang {actual_win_iso}. "
            "Sabtu/Minggu dikecualikan; hari libur nasional/cuti bersama tidak dihitung otomatis. "
            "Bukan tenggat resmi—verifikasi pengumuman atau konfirmasi KPKNL."
        )
        source = "Informasi internal (perkiraan dari tanggal menang aktual)"
    else:
        basis = (
            f"Simulasi internal jika menang pada tanggal lelang {scheduled_iso}: 5 hari kerja (Senin–Jumat), bukan tenggat resmi. "
            "Sabtu/Minggu dikecualikan; hari libur nasional/cuti bersama tidak dihitung otomatis. "
            "Setelah menang, perbarui berdasarkan tanggal menang aktual dan verifikasi ke KPKNL."
        )
        source = "Informasi internal (simulasi dari tanggal lelang)"
    return {
        "payment_deadline": due.isoformat() if due else "",
        "payment_deadline_basis": basis,
        "payment_deadline_source": source,
        "payment_deadline_rule_days": "5",
        "payment_deadline_reference_date": reference_iso,
    }


DATE_FIELDS = {
    "auction_date": ("na_auction_date", "na_auction_date_picker", "na_auction_date_has_value"),
    "deposit_deadline": ("na_deposit_deadline", "na_deposit_deadline_picker", "na_deposit_deadline_has_value"),
    "payment_deadline": ("na_payment_deadline", "na_payment_deadline_picker", "na_payment_deadline_has_value"),
}


def apply_extracted_auction_dates(state: Any, extracted: dict[str, Any], *, document_hash: str = "") -> dict[str, str]:
    """Prefill editable auction/deposit dates and an informational payment estimate."""
    applied: dict[str, str] = {}
    for field in ("auction_date", "deposit_deadline"):
        state_key, picker_key, has_key = DATE_FIELDS[field]
        state[state_key] = ""
        state[has_key] = False
        state[f"{state_key}_user_edited"] = False
        state.pop(picker_key, None)
        iso = normalize_auction_date(extracted.get(field))
        if not iso:
            continue
        parsed = date.fromisoformat(iso)
        state[state_key] = iso
        state[picker_key] = parsed
        state[has_key] = True
        applied[field] = iso

    explicit_payment = normalize_auction_date(extracted.get("payment_deadline"))
    due_info = derive_payment_deadline(
        state.get("na_auction_date"),
        auction_type=extracted.get("auction_type") or "",
        auction_limit=extracted.get("auction_limit"),
        explicit_deadline=explicit_payment,
    )
    state["na_payment_deadline"] = due_info["payment_deadline"]
    state["na_payment_deadline_basis"] = due_info["payment_deadline_basis"]
    state["na_payment_deadline_source"] = due_info["payment_deadline_source"]
    state["na_payment_deadline_document_value"] = explicit_payment
    state["na_payment_deadline_document_auction_date"] = state.get("na_auction_date", "") if explicit_payment else ""
    state["na_payment_deadline_reference_date"] = due_info.get("payment_deadline_reference_date", "")
    if due_info["payment_deadline"]:
        applied["payment_deadline"] = due_info["payment_deadline"]

    if document_hash:
        state["na_auction_date_document_hash"] = document_hash
    state["na_auction_date_source_file"] = str(extracted.get("source_file_name") or "Dokumen KPKNL yang diunggah")
    evidence = extracted.get("field_evidence") if isinstance(extracted.get("field_evidence"), dict) else {}
    state["na_auction_date_evidence"] = {field: evidence.get(field) for field in ("auction_date", "deposit_deadline", "payment_deadline") if evidence.get(field)}
    return applied
