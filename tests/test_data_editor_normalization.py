from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from core.editor_normalization import (
    COMPARABLE_EDITOR_COLUMNS,
    RENOVATION_EDITOR_COLUMNS,
    RISK_EDITOR_COLUMNS,
    normalize_comparable_editor_frame,
    normalize_renovation_editor_frame,
    normalize_risk_editor_frame,
)
from core.market_engine import assess_comparables
from core.risk_engine import summarize_risks
from core.utils import to_bool


def test_legacy_risk_checkbox_columns_inferred_as_float_are_normalized_to_bool():
    # Reproduces legacy Sheets rows where newly added checkbox fields were null.
    legacy = pd.DataFrame([{
        "category": "Legal",
        "risk_description": "Klaim pihak ketiga",
        "probability_1_5": 3,
        "impact_1_5": 4,
        "cost_reserve": 0,
        "critical": np.nan,
        "hard_stop_confirmed": np.nan,
        "mitigation": "Verifikasi dokumen",
        "status": "Open",
    }])
    assert legacy["hard_stop_confirmed"].dtype.kind == "f"

    normalized = normalize_risk_editor_frame(legacy)

    assert normalized.columns.tolist() == RISK_EDITOR_COLUMNS
    assert normalized["hard_stop_confirmed"].dtype == np.dtype("bool")
    assert normalized["critical"].dtype == np.dtype("bool")
    assert normalized.loc[0, "hard_stop_confirmed"] is np.bool_(False) or not bool(normalized.loc[0, "hard_stop_confirmed"])
    assert not bool(normalized.loc[0, "critical"])


def test_risk_boolean_strings_are_parsed_safely_and_not_treated_as_true():
    normalized = normalize_risk_editor_frame(pd.DataFrame([
        {"risk_description": "legacy false", "critical": "False", "hard_stop_confirmed": "0", "status": "Open"},
        {"risk_description": "legacy true", "critical": "Ya", "hard_stop_confirmed": "true", "status": "Open"},
    ]))
    assert normalized["critical"].tolist() == [False, True]
    assert normalized["hard_stop_confirmed"].tolist() == [False, True]

    summary = summarize_risks(normalized.to_dict(orient="records"))
    assert summary["critical_open"] == ["legacy true"]
    assert summary["items"][0]["hard_stop_confirmed"] is False
    assert summary["items"][1]["hard_stop_confirmed"] is True


def test_risk_editor_normalization_is_idempotent_and_add_row_safe():
    frame = normalize_risk_editor_frame([{
        "category": "Fisik", "risk_description": "Interior belum diperiksa",
        "probability_1_5": "2", "impact_1_5": "3", "cost_reserve": "15000000",
        "critical": True, "hard_stop_confirmed": False, "mitigation": "Cadangan interior", "status": "Open",
    }])
    again = normalize_risk_editor_frame(frame)
    assert again.dtypes.astype(str).to_dict() == frame.dtypes.astype(str).to_dict()
    assert again.iloc[0].to_dict() == frame.iloc[0].to_dict()
    appended = normalize_risk_editor_frame(pd.concat([frame, pd.DataFrame([{
        "risk_description": "Risiko baru", "critical": None, "hard_stop_confirmed": None,
    }])], ignore_index=True))
    assert appended["hard_stop_confirmed"].dtype == np.dtype("bool")
    assert not bool(appended.loc[1, "hard_stop_confirmed"])


def test_comparable_checkbox_columns_and_all_editor_types_are_normalized():
    legacy = pd.DataFrame([{
        "name": "Rumah pembanding", "price": "450000000", "land_area": "90",
        "building_area": "70", "promotion_value_verified": np.nan,
        "ai_exclude_from_primary": np.nan, "listing_date": "2026-11-01",
        "date_found": "01/11/2026", "market_segment": None,
        "price_type": None,
    }])
    normalized = normalize_comparable_editor_frame(legacy)
    assert normalized.columns.tolist() == COMPARABLE_EDITOR_COLUMNS
    assert normalized["promotion_value_verified"].dtype == np.dtype("bool")
    assert normalized["ai_exclude_from_primary"].dtype == np.dtype("bool")
    assert normalized.loc[0, "price"] == 450_000_000
    assert normalized.loc[0, "land_area"] == 90
    assert normalized.loc[0, "listing_date"] == date(2026, 11, 1)
    assert normalized.loc[0, "date_found"] == date(2026, 11, 1)
    assert normalized.loc[0, "market_segment"] == "Tidak diketahui"
    assert normalized.loc[0, "price_type"] == "Asking aktif"


def test_market_engine_handles_legacy_boolean_text_without_excluding_comp_or_applying_promo():
    comps = [{
        "name": "Rumah resale", "address": "Waru", "price": 450_000_000,
        "land_area": 90, "building_area": 70, "condition": "Siap Huni",
        "market_segment": "Secondary / resale", "price_type": "Transaksi terverifikasi",
        "source_platforms": "Portal listing", "source_url": "https://example.test/rumah-1",
        "promotion_value_verified": "false", "verified_promotion_value": 50_000_000,
        "ai_exclude_from_primary": "false",
    }]
    normalized = normalize_comparable_editor_frame(comps).to_dict(orient="records")
    subject = {"land_area": 90, "building_area": 70, "physical_condition": "Siap Huni"}
    result = assess_comparables(normalized, subject)
    assert result["valid_count"] == 1


def test_renovation_editor_normalizes_legacy_numeric_and_selectbox_columns():
    legacy = pd.DataFrame([{
        "item_code": "USER_BOQ_1", "work_item": "Pengecatan", "quantity": "10",
        "unit_cost": "25000", "priority": None, "evidence_basis": None, "confidence": None,
    }])
    normalized = normalize_renovation_editor_frame(legacy)
    assert normalized.columns.tolist() == RENOVATION_EDITOR_COLUMNS
    assert normalized["quantity"].dtype.kind == "f"
    assert normalized["unit_cost"].dtype.kind == "f"
    assert normalized.loc[0, "priority"] == "Wajib"
    assert normalized.loc[0, "evidence_basis"] == "Asumsi kuantitas"
    assert normalized.loc[0, "confidence"] == "Rendah"


def test_bool_parser_handles_common_legacy_values():
    assert to_bool("False") is False
    assert to_bool("0") is False
    assert to_bool("Tidak") is False
    assert to_bool("True") is True
    assert to_bool("Ya") is True
    assert to_bool(np.nan) is False
    assert to_bool(None) is False


def test_every_analysis_data_editor_receives_a_normalized_frame():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "risk_frame = normalize_risk_editor_frame(st.session_state.na_risk_editor)" in source
    assert "st.data_editor(risk_frame," in source
    assert "comparable_editor_input = normalize_comparable_editor_frame(st.session_state.na_comparables_editor)" in source
    assert "st.data_editor(comparable_editor_input," in source
    assert "renovation_frame = normalize_renovation_editor_frame(st.session_state.na_renovation_items_editor)" in source
    assert "st.data_editor(renovation_frame," in source
    # Each CheckboxColumn's underlying columns are explicitly normalized to bool.
    assert '_normalize_bool_columns(result, ["critical", "hard_stop_confirmed"])' in Path("core/editor_normalization.py").read_text(encoding="utf-8")
    assert '_normalize_bool_columns(result, ["promotion_value_verified", "ai_exclude_from_primary"])' in Path("core/editor_normalization.py").read_text(encoding="utf-8")


def test_empty_and_placeholder_frames_keep_checkbox_columns_boolean():
    empty_risk = normalize_risk_editor_frame(pd.DataFrame(columns=RISK_EDITOR_COLUMNS))
    placeholder_risk = normalize_risk_editor_frame([{column: None for column in RISK_EDITOR_COLUMNS}])
    empty_comps = normalize_comparable_editor_frame(pd.DataFrame(columns=COMPARABLE_EDITOR_COLUMNS))
    placeholder_comps = normalize_comparable_editor_frame([{column: None for column in COMPARABLE_EDITOR_COLUMNS}])
    for frame in (empty_risk, placeholder_risk):
        assert frame["critical"].dtype == np.dtype("bool")
        assert frame["hard_stop_confirmed"].dtype == np.dtype("bool")
    for frame in (empty_comps, placeholder_comps):
        assert frame["promotion_value_verified"].dtype == np.dtype("bool")
        assert frame["ai_exclude_from_primary"].dtype == np.dtype("bool")
