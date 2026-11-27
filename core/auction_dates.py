"""Strict, deterministic parsing of auction dates extracted from official notices."""
from __future__ import annotations

import re
from datetime import date, datetime
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
    # A value may contain a field label or time suffix. Accept only exactly
    # one explicit calendar date token; multiple dates are ambiguous.
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


# Official Indonesian non-working days for 2026-2027 (national holidays + joint leave),
# based on the applicable SKB 3 Ministers. The auction organiser's specific
# operational calendar may differ; an explicit deadline in the KPKNL notice wins.
HOLIDAY_CALENDAR_VERSION = "SKB_3_MENTERI_2026_2027"
HOLIDAY_CALENDAR_SOURCES = {
    "2026": "https://www.setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2026",
    "2027": "https://setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2027",
}
INDONESIAN_NON_WORKING_DATES = {
    # 2026 national holidays and collective leave.
    "2026-01-01", "2026-01-16", "2026-02-16", "2026-02-17",
    "2026-03-18", "2026-03-19", "2026-03-20", "2026-03-21", "2026-03-22",
    "2026-03-23", "2026-03-24", "2026-04-03", "2026-04-05", "2026-05-01",
    "2026-05-14", "2026-05-15", "2026-05-27", "2026-05-28", "2026-05-31",
    "2026-06-01", "2026-06-16", "2026-08-17", "2026-08-25",
    "2026-12-24", "2026-12-25",
    # 2027 national holidays and collective leave (SKB 1205/2026, 3/2026, 2/2026).
    "2027-01-01", "2027-01-05", "2027-02-05", "2027-02-06",
    "2027-03-08", "2027-03-09", "2027-03-10", "2027-03-11", "2027-03-12",
    "2027-03-15", "2027-03-25", "2027-03-26", "2027-03-28", "2027-05-01",
    "2027-05-06", "2027-05-17", "2027-05-18", "2027-05-19", "2027-05-20",
    "2027-06-01", "2027-06-06", "2027-08-15", "2027-08-17",
    "2027-12-24", "2027-12-25", "2027-12-26",
}


def is_indonesian_working_day(value: date, extra_non_working_dates: set[str] | None = None) -> bool:
    """Weekdays excluding listed Indonesian national holidays and collective leave."""
    blocked = INDONESIAN_NON_WORKING_DATES | (extra_non_working_dates or set())
    return value.weekday() < 5 and value.isoformat() not in blocked


def add_working_days(start_date: Any, working_days: int, extra_non_working_dates: set[str] | None = None) -> date | None:
    """Count working days AFTER start_date; the auction date itself is day zero."""
    iso = normalize_auction_date(start_date)
    if not iso:
        return None
    current = date.fromisoformat(iso)
    remaining = max(0, int(working_days))
    while remaining:
        from datetime import timedelta
        current += timedelta(days=1)
        if is_indonesian_working_day(current, extra_non_working_dates):
            remaining -= 1
    return current


def derive_payment_deadline(
    auction_date: Any,
    *,
    auction_type: str = "",
    auction_limit: Any = None,
    explicit_deadline: Any = "",
    buyer_is_government_institution: bool = False,
) -> dict[str, str]:
    """Return a document deadline when explicit, otherwise the PMK 122/2023 rule.

    Ordinary property auctions: five working days after auction. Exceptions in
    PMK 122/2023 Article 88 are handled for scheduled special auctions (2 days),
    qualifying government/institutional buyers (14 days), and limits >= Rp500bn
    (14 days).
    """
    auction_iso = normalize_auction_date(auction_date)
    explicit_iso = normalize_auction_date(explicit_deadline)
    if explicit_iso:
        return {
            "payment_deadline": explicit_iso,
            "payment_deadline_basis": "Tanggal eksplisit pada dokumen KPKNL",
            "payment_deadline_source": "Dokumen KPKNL",
            "payment_deadline_rule_days": "",
        }
    if not auction_iso:
        return {"payment_deadline": "", "payment_deadline_basis": "Menunggu tanggal lelang", "payment_deadline_source": "Belum dapat dihitung", "payment_deadline_rule_days": ""}

    auction_type_norm = str(auction_type or "").strip().lower()
    limit_value = 0.0
    try:
        digits = re.sub(r"[^0-9]", "", str(auction_limit or "0"))
        limit_value = float(digits or 0)
    except (TypeError, ValueError):
        pass
    if "terjadwal khusus" in auction_type_norm:
        days, rule = 2, "PMK 122/2023 Pasal 88 ayat (2) huruf a — 2 hari kerja"
    elif buyer_is_government_institution or limit_value >= 500_000_000_000:
        days, rule = 14, "PMK 122/2023 Pasal 88 ayat (2) huruf b/c — 14 hari kerja"
    else:
        days, rule = 5, "PMK 122/2023 Pasal 88 ayat (1) — 5 hari kerja"
    due = add_working_days(auction_iso, days)
    calendar_years = set(range(date.fromisoformat(auction_iso).year, (due.year if due else date.fromisoformat(auction_iso).year) + 1))
    uncovered_years = sorted(calendar_years - {2026, 2027})
    coverage_note = (
        "; KALENDER LIBUR RESMI BELUM TERSEDIA UNTUK " + ", ".join(str(y) for y in uncovered_years) +
        " — hasil weekday-only provisional, verifikasi jadwal kerja KPKNL"
    ) if uncovered_years else ""
    return {
        "payment_deadline": due.isoformat() if due else "",
        "payment_deadline_basis": rule + f"; kalender {HOLIDAY_CALENDAR_VERSION}" + coverage_note,
        "payment_deadline_source": "Otomatis dari tanggal lelang",
        "payment_deadline_rule_days": str(days),
    }


DATE_FIELDS = {
    "auction_date": ("na_auction_date", "na_auction_date_picker", "na_auction_date_has_value"),
    "deposit_deadline": ("na_deposit_deadline", "na_deposit_deadline_picker", "na_deposit_deadline_has_value"),
    "payment_deadline": ("na_payment_deadline", "na_payment_deadline_picker", "na_payment_deadline_has_value"),
}


def apply_extracted_auction_dates(state: Any, extracted: dict[str, Any], *, document_hash: str = "") -> dict[str, str]:
    """Prefill editable date pickers and derive the payment deadline consistently.

    A new KPKNL document replaces prior extracted values. Auction/deposit dates
    remain editable, while payment deadline uses an explicit document date when
    available or the PMK working-day rule otherwise.
    """
    applied: dict[str, str] = {}
    for field in ("auction_date", "deposit_deadline"):
        state_key, picker_key, has_key = DATE_FIELDS[field]
        state[state_key] = ""
        state[has_key] = False  # retained for compatibility with saved V1.0.22 sessions
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
    if due_info["payment_deadline"]:
        applied["payment_deadline"] = due_info["payment_deadline"]

    if document_hash:
        state["na_auction_date_document_hash"] = document_hash
    state["na_auction_date_source_file"] = str(extracted.get("source_file_name") or "Dokumen KPKNL yang diunggah")
    evidence = extracted.get("field_evidence") if isinstance(extracted.get("field_evidence"), dict) else {}
    state["na_auction_date_evidence"] = {field: evidence.get(field) for field in ("auction_date", "deposit_deadline", "payment_deadline") if evidence.get(field)}
    return applied
