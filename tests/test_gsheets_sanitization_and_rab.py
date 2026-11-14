import json
import math
import pandas as pd
import numpy as np

from core.utils import safe_json, sheet_cell_value
from services.gemini_parser import (
    RenovationRabExtraction, AuctionExtraction, ComparableExtraction,
    renovation_estimate_to_rows,
)


def _has_additional_properties(node):
    if isinstance(node, dict):
        if "additionalProperties" in node:
            return True
        return any(_has_additional_properties(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_additional_properties(v) for v in node)
    return False


def test_gsheets_cell_values_convert_nan_inf_and_pandas_na_to_blank():
    values = [
        sheet_cell_value(float("nan")),
        sheet_cell_value(float("inf")),
        sheet_cell_value(float("-inf")),
        sheet_cell_value(np.float64(float("nan"))),
        sheet_cell_value(pd.NA),
        sheet_cell_value(pd.NaT),
        sheet_cell_value(np.int64(123)),
    ]
    assert values == ["", "", "", "", "", "", 123]
    json.dumps(values, allow_nan=False)


def test_nested_payload_sanitizes_non_finite_and_pandas_missing_values():
    payload = {"blank_numeric": float("nan"), "infinite": float("inf"), "missing": pd.NA, "rows": [{"x": np.float64(float("nan"))}]}
    encoded = safe_json(payload)
    decoded = json.loads(encoded)
    assert decoded == {"blank_numeric": None, "infinite": None, "missing": None, "rows": [{"x": None}]}
    assert "NaN" not in encoded and "Infinity" not in encoded


def test_renovation_schema_has_no_dynamic_additional_properties():
    assert not _has_additional_properties(RenovationRabExtraction.model_json_schema())
    assert not _has_additional_properties(AuctionExtraction.model_json_schema())
    assert not _has_additional_properties(ComparableExtraction.model_json_schema())


def test_ai_rab_uses_conservative_unit_cost_in_existing_calculator_column():
    parsed = {"items": [{
        "work_item": "Perbaikan cat fasad", "scope_description": "Cat ulang area luar",
        "quantity": 40, "unit": "m2", "unit_cost_low": 25000,
        "unit_cost_conservative": 40000, "priority": "Wajib",
        "evidence_basis": "Fakta visual", "confidence": "Sedang", "notes": "Cat lama mengelupas"
    }]}
    rows = renovation_estimate_to_rows(parsed)
    assert len(rows) == 1
    assert rows[0]["unit_cost"] == 40000
    assert rows[0]["unit_cost_low"] == 25000
    assert rows[0]["quantity"] * rows[0]["unit_cost"] == 1_600_000


def test_rab_estimator_uses_uploaded_image_and_maps_conservative_cost(monkeypatch):
    import io
    from PIL import Image
    import services.gemini_parser as gp

    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), (180, 180, 180)).save(buffer, format="PNG")
    raw_image = buffer.getvalue()
    response = {
        "items": [{
            "work_item": "Pembersihan dan pengecatan ulang fasad",
            "scope_description": "Bersihkan permukaan dan cat area fasad yang terlihat mengelupas",
            "quantity": 35,
            "unit": "m2",
            "unit_cost_low": 30000,
            "unit_cost_conservative": 45000,
            "priority": "Wajib",
            "evidence_basis": "Fakta visual",
            "confidence": "Sedang",
            "notes": "Volume perlu diukur ulang saat survei."
        }],
        "assumptions": ["Harga satuan indikatif, bukan penawaran vendor."],
        "items_to_inspect": ["Kondisi atap dan instalasi listrik belum terlihat."],
        "overall_note": "Draft awal untuk ditinjau pengguna."
    }
    calls = {}

    def fake_call(api_key, model, prompt, **kwargs):
        calls["api_key"] = api_key
        calls["model"] = model
        calls["files"] = kwargs.get("extra_files")
        calls["schema"] = kwargs.get("schema")
        return json.dumps(response, ensure_ascii=False)

    monkeypatch.setattr(gp, "_client_call", fake_call)
    result = gp.estimate_renovation_rab(
        "fake-key",
        [(raw_image, "image/png", "foto-fasad.png")],
        "Cat fasad mengelupas dan pagar berkarat.",
        {"address": "Sidoarjo", "land_area": 100, "building_area": 80},
    )
    assert calls["model"] == gp.DEFAULT_MODEL
    assert len(calls["files"]) == 1
    assert calls["files"][0][1] == "image/jpeg"
    assert calls["schema"] is gp.RenovationRabExtraction
    assert result["editor_rows"][0]["unit_cost"] == 45000
    assert result["total_conservative_indicative"] == 1_575_000
    assert result["items_to_inspect"]


def test_gspread_row_values_are_json_safe_for_blank_numeric_comparables():
    import importlib
    import importlib.util
    import sys
    import types

    injected = []
    if importlib.util.find_spec("gspread") is None:
        fake = types.ModuleType("gspread")
        fake.__path__ = []
        fake.service_account_from_dict = lambda *_a, **_k: None
        exc_module = types.ModuleType("gspread.exceptions")
        class WorksheetNotFound(Exception):
            pass
        exc_module.WorksheetNotFound = WorksheetNotFound
        fake.exceptions = exc_module
        sys.modules["gspread"] = fake
        sys.modules["gspread.exceptions"] = exc_module
        injected = ["gspread", "gspread.exceptions"]

    try:
        module = importlib.import_module("storage.gsheets_db")
        db = object.__new__(module.GoogleSheetsDB)
        row = db._row_values("COMPARABLES", {
            "comparable_id": "CMP-1", "property_id": "PROP-1", "analysis_id": "ANL-1",
            "name": "Rumah pembanding", "price": float("nan"), "land_area": pd.NA,
            "building_area": np.float64(float("inf")), "price_type": "Asking aktif",
            "source_url": "", "date_found": "2026-11-14",
            "payload": {"price": float("nan"), "missing": pd.NA},
        })
        json.dumps(row, allow_nan=False)
        mapped = dict(zip(module.SCHEMA["COMPARABLES"], row))
        assert mapped["price"] == ""
        assert mapped["land_area"] == ""
        assert mapped["building_area"] == ""
        assert json.loads(mapped["payload_json"]) == {"price": None, "missing": None}
    finally:
        if injected:
            for name in injected:
                sys.modules.pop(name, None)


def test_rab_total_is_marked_partial_when_item_has_unknown_quantity_or_cost(monkeypatch):
    import json
    import services.gemini_parser as gp
    payload = {
        "items": [
            {"work_item":"Cat luar", "quantity":20, "unit":"m2", "unit_cost_low":25000, "unit_cost_conservative":40000},
            {"work_item":"Perbaikan atap", "quantity":None, "unit":"m2", "unit_cost_low":50000, "unit_cost_conservative":80000},
        ],
        "assumptions": [], "items_to_inspect": ["Atap perlu diperiksa"], "overall_note": "Draft"
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(payload))
    result = gp.estimate_renovation_rab("fake-key", [], "Cat luar mengelupas; kondisi atap belum dapat diukur.")
    assert result["total_conservative_indicative"] == 800000
    assert result["total_conservative_complete"] is False
    assert result["unpriced_items"] == ["Perbaikan atap"]
