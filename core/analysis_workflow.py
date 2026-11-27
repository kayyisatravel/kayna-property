"""Pure validation helpers for the sequential auction-analysis workflow."""
from __future__ import annotations

from typing import Any

from core.utils import to_float


def analysis_step1_missing(state: Any) -> list[str]:
    """Return required acquisition/legal fields missing from step one."""
    missing: list[str] = []
    required_text = {
        "na_lot_code": "Kode lot",
        "na_name": "Nama objek",
        "na_address": "Alamat objek",
        "na_district": "Desa/kecamatan/kabupaten",
        "na_office": "KPKNL",
        "na_auction_date": "Tanggal lelang",
        "na_deposit_deadline": "Batas setor uang jaminan",
        "na_certificate": "Jenis sertifikat",
    }
    for key, label in required_text.items():
        if not str(state.get(key) or "").strip():
            missing.append(label)
    for key, label in (("na_limit", "Nilai limit"), ("na_deposit", "Uang jaminan"), ("na_land", "Luas tanah")):
        if to_float(state.get(key)) <= 0:
            missing.append(label)
    if state.get("na_property_type") != "Tanah kosong" and to_float(state.get("na_building")) <= 0:
        missing.append("Luas bangunan (kecuali tanah kosong)")
    return missing


def count_valid_comparables(rows: Any) -> int:
    """Count unique, minimally traceable property comparables."""
    if hasattr(rows, "to_dict") and callable(rows.to_dict):
        try:
            rows = rows.to_dict(orient="records")
        except TypeError:
            return 0
    if not isinstance(rows, list):
        return 0
    seen: set[Any] = set()
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        price = to_float(row.get("price"))
        area_ok = to_float(row.get("land_area")) > 0 or to_float(row.get("building_area")) > 0
        source_ok = bool(
            str(row.get("source_url") or "").strip()
            or str(row.get("source_platforms") or "").strip()
            or str(row.get("source_evidence") or "").strip()
        )
        if not (name and price > 0 and area_ok and source_ok):
            continue
        property_id = str(row.get("underlying_property_id") or "").strip().lower()
        unique_key: Any = property_id or (
            name.lower(), str(row.get("address") or "").strip().lower()
        )
        if unique_key in seen:
            continue
        seen.add(unique_key)
        count += 1
    return count


def persist_analysis_step_state(state: Any, step: int) -> int:
    """Persist current analysis inputs in session state before hiding a step.

    Streamlit widget keys and file-upload objects are excluded because the
    underlying values are either mirrored to plain ``na_*`` keys or remain
    mounted across steps. This avoids stale widget state and unnecessary
    non-serializable upload copies.
    """
    if not hasattr(state, "items"):
        raise TypeError("state must be a mapping-like session state")
    persisted = dict(state.get("_na_persisted_form_state", {}) or {})
    for key, value in list(state.items()):
        key_text = str(key)
        if not key_text.startswith("na_"):
            continue
        if any(marker in key_text for marker in ("_widget", "_picker")):
            continue
        if key_text in {"na_document", "na_survey_photos"}:
            continue
        persisted[key_text] = value
    state["_na_persisted_form_state"] = persisted
    target = max(1, min(4, int(step)))
    state["na_analysis_step"] = target
    return target


def restore_analysis_step_state(state: Any) -> None:
    """Restore values cleaned up by Streamlit when a step's widgets hide."""
    persisted = state.get("_na_persisted_form_state", {})
    if not isinstance(persisted, dict):
        return
    for key, value in persisted.items():
        if key not in state:
            state[key] = value
