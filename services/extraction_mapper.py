"""Map Gemini KPKNL extraction JSON directly into Streamlit form state."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, MutableMapping


def parse_extraction_json(raw: str | dict[str, Any]) -> dict[str, Any]:
    """Parse Gemini JSON, including one optional Markdown JSON fence."""
    if isinstance(raw, dict):
        data = raw
    else:
        cleaned = str(raw or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Hasil ekstraksi harus berupa object JSON.")
    # Accept either a flat payload or a wrapper {data: {...}}.
    nested = data.get("data")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in ("conflicts", "data_konflik", "field_evidence", "catatan_verifikasi"):
            if key in data and key not in merged:
                merged[key] = data[key]
        data = merged
    return data


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip() not in {"", "null", "None", "—", "-"}:
            return value
    return None


def _number(value: Any, *, money: bool = False) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if money else float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    original = text
    multiplier = 1
    if money:
        if re.search(r"\b(miliar|milyar|m|bn)\b", original):
            multiplier = 1_000_000_000
        elif re.search(r"\b(juta|jt|million)\b", original):
            multiplier = 1_000_000
        elif re.search(r"\b(ribu|rb|thousand)\b", original):
            multiplier = 1_000
    text = text.replace("rp", "").replace("idr", "").replace("m²", "").replace("m2", "").replace("meter persegi", "")
    text = re.sub(r"[^0-9,\.\-]", "", text)
    if not text:
        return None
    # Money normally comes from Gemini as integer rupiah; shorthand is supported as fallback.
    if money:
        if ("," in text or "." in text) and multiplier > 1:
            # Decimal value for shorthand, e.g. Rp1,5 miliar.
            normalized = text.replace(".", "").replace(",", ".") if ("," in text and "." in text) else text.replace(",", ".")
            try:
                return int(float(normalized) * multiplier)
            except ValueError:
                return None
        digits = re.sub(r"[^0-9\-]", "", text)
        try:
            return int(digits) * multiplier
        except ValueError:
            return None
    if "," in text and "." in text:
        # Indonesian convention 1.234,5
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        # Common DD-MM-YYYY / DD/MM/YYYY formats.
        match = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", text)
        if match:
            day, month, year = map(int, match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def _choice(value: Any, kind: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    low = text.lower()
    if kind == "certificate":
        if "shm" in low or "hak milik" in low:
            return "SHM"
        if "shgb" in low or "hgb" in low or "guna bangunan" in low:
            return "SHGB/HGB"
        if any(x in low for x in ("hpl", "hak pakai", "hak lain")):
            return "Hak lain"
        return None
    elif kind == "auction_type":
        if "tanggungan" in low or "hak tanggungan" in low:
            return "Eksekusi Hak Tanggungan"
        if "pengadilan" in low or "putusan" in low:
            return "Eksekusi Pengadilan"
        if "ayda" in low:
            return "AYDA"
        if "sukarela" in low:
            return "Lelang sukarela"
        return None
    elif kind == "property_type":
        if "2 lantai" in low or "dua lantai" in low:
            return "Rumah 2 lantai"
        if "1 lantai" in low or "satu lantai" in low:
            return "Rumah 1 lantai"
        if "cluster" in low or "modern" in low:
            return "Cluster/modern"
        if "besar" in low:
            return "Rumah besar"
        if "kecil" in low or "standar" in low:
            return "Rumah kecil/standar"
        return None
    return text


# canonical/existing form key : extraction aliases + converter
FIELD_MAP: dict[str, tuple[tuple[str, ...], str]] = {
    "form_lot_code": (("lot_code", "kode_lot", "nomor_lot", "nomor_lelang", "kode_lot_lelang"), "text"),
    "form_auction_office": (("auction_office", "kpknl", "KPKNL", "kantor_lelang"), "text"),
    "form_seller": (("seller", "penjual", "kreditur", "bank_penjual"), "text"),
    "form_auction_type": (("auction_type", "jenis_lelang", "tipe_lelang"), "auction_type"),
    "form_name": (("name", "nama_objek", "nama_singkat_objek", "object_name"), "text"),
    "form_complex_name": (("complex_name", "nama_perumahan", "perumahan", "kompleks", "nama_kompleks"), "text"),
    "form_auction_date": (("auction_date", "tanggal_lelang", "tgl_lelang"), "date"),
    "form_auction_time": (("auction_time", "jam_lelang", "waktu_lelang", "sesi_lelang"), "text"),
    "form_auction_url": (("auction_url", "url_pengumuman", "link_pengumuman"), "text"),
    "form_auction_limit": (("auction_limit", "nilai_limit_idr", "nilai_limit", "harga_limit"), "money"),
    "form_deposit_amount": (("deposit_amount", "uang_jaminan_idr", "uang_jaminan", "nilai_jaminan"), "money"),
    "form_bid_increment": (("bid_increment", "kelipatan_bid", "increment_bid", "kenaikan_bid", "kelipatan_penawaran"), "money"),
    "form_deposit_deadline": (("deposit_deadline", "batas_setor_jaminan", "batas_akhir_setor_jaminan"), "text"),
    "form_payment_deadline": (("payment_deadline", "batas_pelunasan", "batas_waktu_pelunasan"), "text"),
    "form_address": (("address", "alamat", "alamat_objek"), "text"),
    "form_district": (("district", "wilayah", "desa_kecamatan_kabupaten", "desa_kecamatan", "kelurahan_kecamatan_kabupaten"), "text"),
    "form_province": (("province", "provinsi"), "text"),
    "form_certificate_type": (("certificate_type", "jenis_sertifikat", "jenis_hak"), "certificate"),
    "form_certificate_no": (("certificate_no", "nomor_hak", "nomor_sertifikat", "nomor_shm_shgb"), "text"),
    "form_rights_expiry": (("rights_expiry", "masa_berlaku_hak", "tanggal_berakhir_hgb"), "text"),
    "form_land_area": (("land_area", "LT_m2", "lt_m2", "luas_tanah_m2", "luas_tanah"), "number"),
    "form_building_area": (("building_area", "LB_m2", "lb_m2", "luas_bangunan_m2", "luas_bangunan"), "number"),
    "form_njop": (("njop", "NJOP_idr", "njop_idr", "nilai_njop"), "money"),
    "form_bedrooms": (("bedrooms", "jumlah_kamar_tidur", "kamar_tidur", "kt"), "integer"),
    "form_bathrooms": (("bathrooms", "jumlah_kamar_mandi", "kamar_mandi", "km"), "integer"),
    "form_property_type": (("property_type", "tipe_properti", "jenis_bangunan"), "property_type"),
    "form_auction_object_description": (("auction_object_description", "uraian_objek", "deskripsi_objek", "keterangan_objek"), "text"),
    "form_property_notes": (("property_notes", "catatan_lain", "keterangan_lain", "catatan"), "text"),
}


def apply_extraction_to_form(
    extracted: str | dict[str, Any],
    state: MutableMapping[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Populate only fields with extracted values; preserve manual edits by default."""
    data = parse_extraction_json(extracted)
    filled: dict[str, Any] = {}
    skipped_existing: list[str] = []
    missing: list[str] = []
    empty_defaults = {"", None, 0, 0.0, "Belum diketahui", "Tidak diketahui", "Lainnya / belum diketahui"}

    for state_key, (aliases, kind) in FIELD_MAP.items():
        raw = _first(data, *aliases)
        if raw is None:
            missing.append(state_key)
            continue
        current = state.get(state_key)
        if not overwrite and current not in empty_defaults:
            skipped_existing.append(state_key)
            continue
        if kind == "text":
            value = str(raw).strip()
        elif kind == "money":
            value = _number(raw, money=True)
        elif kind == "number":
            value = _number(raw, money=False)
        elif kind == "integer":
            num = _number(raw, money=False)
            value = int(num) if num is not None else None
        elif kind == "date":
            value = _as_date(raw)
        elif kind in {"certificate", "auction_type", "property_type"}:
            value = _choice(raw, kind)
        else:
            value = raw
        if value is None or value == "":
            missing.append(state_key)
            continue
        state[state_key] = value
        filled[state_key] = value

    return {
        "filled": filled,
        "filled_count": len(filled),
        "skipped_existing": skipped_existing,
        "missing_count": len(missing),
        "missing_fields": missing,
        "conflicts": _first(data, "conflicts", "data_konflik", "konflik_data") or [],
        "field_evidence": data.get("field_evidence", {}),
        "verification_notes": _first(data, "catatan_verifikasi", "verification_notes", "catatan") or "",
    }
