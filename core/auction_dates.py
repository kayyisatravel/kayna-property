"""Strict, deterministic parsing of auction dates extracted from official notices."""
from __future__ import annotations

import re
from datetime import datetime
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
