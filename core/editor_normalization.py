"""Type-safe pandas frames for Streamlit data_editor widgets.

Legacy Google Sheets snapshots often contain all-null columns. Pandas may infer
those columns as float64, which is incompatible with Streamlit CheckboxColumn.
These helpers normalize each editor schema before it reaches Streamlit and
again after edits, while preserving valid values from older snapshots.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd

RISK_EDITOR_COLUMNS = [
    "category", "risk_description", "probability_1_5", "impact_1_5",
    "cost_reserve", "critical", "hard_stop_confirmed", "mitigation", "status",
]

COMPARABLE_EDITOR_COLUMNS = [
    "name", "address", "complex_name", "underlying_property_id", "latitude",
    "longitude", "distance_m", "market_segment", "seller_type", "price",
    "njop", "land_area", "building_area", "bedrooms", "bathrooms", "condition",
    "condition_detail", "access", "access_detail", "price_type", "promotion_claims",
    "promotion_value_verified", "verified_promotion_value", "certificate", "orientation",
    "electricity_watt", "water_source", "source_platforms", "source_evidence",
    "source_url", "source_url_scope", "listing_date", "date_found", "date_found_basis",
    "notes", "adjustment_pct", "ai_adjustment_rationale", "ai_exclude_from_primary",
]

RENOVATION_EDITOR_COLUMNS = [
    "item_code", "subcategory", "work_item", "quantity_low", "quantity",
    "quantity_high", "quantity_basis", "unit", "unit_cost_low", "unit_cost",
    "unit_cost_high", "price_source", "priority", "evidence_basis", "confidence", "notes",
]

RISK_SELECT_OPTIONS = {"status": ["Open", "Mitigated", "Resolved"]}
COMPARABLE_SELECT_OPTIONS = {
    "market_segment": ["Tidak diketahui", "Secondary / resale", "Primary / developer"],
    "seller_type": ["", "Pemilik", "Agen", "Developer", "Tidak diketahui"],
    "condition": ["", "Siap Huni", "Butuh Renovasi", "Hitung Tanah"],
    "access": ["", "2 Mobil", "1 Mobil", "Gang"],
    "price_type": [
        "Asking aktif", "Marked sold / perlu verifikasi", "Transaksi terverifikasi",
        "Over kredit / skema kewajiban",
    ],
    "source_url_scope": [
        "", "Listing individual", "Portal/domain only", "Portal pencarian/kategori",
        "Halaman venue/kompleks", "Perlu verifikasi",
    ],
}
RENOVATION_SELECT_OPTIONS = {
    "priority": ["Wajib", "Disarankan", "Bersyarat", "Opsional", "Tidak diperlukan setelah ditinjau"],
    "evidence_basis": ["Fakta visual", "Deskripsi pengguna", "Asumsi kuantitas"],
    "confidence": ["Tinggi", "Sedang", "Rendah"],
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _to_bool(value: Any, default: bool = False) -> bool:
    if _is_missing(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "ya", "benar", "on", "aktif"}:
        return True
    if text in {"0", "false", "f", "no", "n", "tidak", "salah", "off", "nonaktif", ""}:
        return False
    return default


def _to_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value)


def _to_date(value: Any) -> date | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _base_frame(frame: Any, columns: Iterable[str]) -> pd.DataFrame:
    columns = list(columns)
    if isinstance(frame, pd.DataFrame):
        result = frame.copy()
    elif isinstance(frame, list):
        result = pd.DataFrame(frame)
    else:
        result = pd.DataFrame()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.Series([None] * len(result), index=result.index, dtype="object")
    # Reindex to a stable schema. Extra fields are held in the source snapshot;
    # only fields intentionally presented by this editor are sent to Streamlit.
    return result.reindex(columns=columns).copy()


def _normalize_bool_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        frame[column] = frame[column].map(lambda value: _to_bool(value, False)).astype("bool")


def _normalize_number_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")


def _normalize_text_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        frame[column] = frame[column].map(_to_text).astype("object")


def _normalize_select_columns(
    frame: pd.DataFrame,
    option_map: dict[str, list[str]],
    defaults: dict[str, str],
) -> None:
    for column, options in option_map.items():
        valid = set(options)
        default = defaults.get(column, options[0] if options else "")
        frame[column] = frame[column].map(
            lambda value: (text if (text := _to_text(value)) in valid else default)
        ).astype("object")


def normalize_risk_editor_frame(frame: Any) -> pd.DataFrame:
    result = _base_frame(frame, RISK_EDITOR_COLUMNS)
    _normalize_number_columns(result, ["probability_1_5", "impact_1_5", "cost_reserve"])
    _normalize_bool_columns(result, ["critical", "hard_stop_confirmed"])
    _normalize_text_columns(result, ["category", "risk_description", "mitigation"])
    _normalize_select_columns(result, RISK_SELECT_OPTIONS, {"status": "Open"})
    return result


def normalize_comparable_editor_frame(frame: Any) -> pd.DataFrame:
    result = _base_frame(frame, COMPARABLE_EDITOR_COLUMNS)
    _normalize_number_columns(result, [
        "latitude", "longitude", "distance_m", "price", "njop", "land_area",
        "building_area", "bedrooms", "bathrooms", "verified_promotion_value",
        "electricity_watt", "adjustment_pct",
    ])
    _normalize_bool_columns(result, ["promotion_value_verified", "ai_exclude_from_primary"])
    _normalize_text_columns(result, [
        "name", "address", "complex_name", "underlying_property_id", "condition_detail",
        "access_detail", "promotion_claims", "certificate", "orientation", "water_source",
        "source_platforms", "source_evidence", "source_url", "date_found_basis", "notes",
        "ai_adjustment_rationale",
    ])
    _normalize_select_columns(result, COMPARABLE_SELECT_OPTIONS, {
        "market_segment": "Tidak diketahui", "seller_type": "", "condition": "",
        "access": "", "price_type": "Asking aktif", "source_url_scope": "",
    })
    for column in ("listing_date", "date_found"):
        result[column] = result[column].map(_to_date).astype("object")
    return result


def normalize_renovation_editor_frame(frame: Any) -> pd.DataFrame:
    result = _base_frame(frame, RENOVATION_EDITOR_COLUMNS)
    _normalize_number_columns(result, [
        "quantity_low", "quantity", "quantity_high", "unit_cost_low", "unit_cost", "unit_cost_high",
    ])
    _normalize_text_columns(result, [
        "item_code", "subcategory", "work_item", "quantity_basis", "unit", "price_source", "notes",
    ])
    _normalize_select_columns(result, RENOVATION_SELECT_OPTIONS, {
        "priority": "Wajib", "evidence_basis": "Asumsi kuantitas", "confidence": "Rendah",
    })
    return result
