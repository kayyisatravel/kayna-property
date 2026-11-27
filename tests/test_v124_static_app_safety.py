from __future__ import annotations

import ast
import builtins
import symtable
from pathlib import Path

from core.analysis_workflow import analysis_step1_missing, count_valid_comparables, persist_analysis_step_state, restore_analysis_step_state


def _app_source() -> str:
    return Path("app.py").read_text(encoding="utf-8")


def test_all_app_global_references_are_defined_or_imported():
    """Catch NameError-class regressions such as a called-but-unimported helper."""
    source = _app_source()
    table = symtable.symtable(source, "app.py", "exec")
    module_names = set(table.get_identifiers()) | set(dir(builtins))
    unresolved: list[tuple[str, str, int]] = []

    def walk(scope):
        for symbol in scope.get_symbols():
            if symbol.is_global() and symbol.is_referenced() and symbol.get_name() not in module_names:
                unresolved.append((scope.get_name(), symbol.get_name(), scope.get_lineno()))
        for child in scope.get_children():
            walk(child)

    walk(table)
    assert unresolved == [], f"Unresolved global references in app.py: {unresolved}"


def test_date_picker_helpers_are_declared_before_authentication_gate():
    source = _app_source()
    auth_gate = source.index('APP_PASSWORD = str(secret("APP_PASSWORD", "") or "")')
    for function_name in ("jakarta_today", "as_date", "prefilled_editable_date_picker", "optional_date_picker"):
        declaration = source.index(f"def {function_name}(")
        assert declaration < auth_gate, f"{function_name} must be defined before auth gate / st.stop"
    assert 'optional_date_picker("Tanggal berakhir hak SHGB' in source


def test_analysis_step_1_requires_core_auction_and_property_fields():
    complete = {
        "na_lot_code": "LOT-1", "na_name": "Rumah Contoh",
        "na_address": "Grabagan, Tulangan, Sidoarjo", "na_district": "Tulangan, Sidoarjo",
        "na_office": "KPKNL Sidoarjo", "na_auction_date": "2026-12-01",
        "na_deposit_deadline": "2026-11-30", "na_certificate": "SHM",
        "na_limit": 180_000_000, "na_deposit": 18_000_000,
        "na_land": 90, "na_building": 40, "na_property_type": "Rumah 1 lantai",
    }
    assert analysis_step1_missing(complete) == []
    incomplete = {**complete, "na_auction_date": "", "na_limit": 0, "na_building": 0}
    missing = analysis_step1_missing(incomplete)
    assert "Tanggal lelang" in missing
    assert "Nilai limit" in missing
    assert "Luas bangunan (kecuali tanah kosong)" in missing


def test_comparable_gate_counts_unique_traceable_properties_only():
    rows = [
        {"name": "Rumah A", "address": "Blok A", "price": 350_000_000, "land_area": 90, "source_url": "https://example.com/a", "underlying_property_id": "A"},
        {"name": "Rumah A portal kedua", "address": "Blok A", "price": 355_000_000, "land_area": 90, "source_url": "https://example.com/a2", "underlying_property_id": "A"},
        {"name": "Rumah B", "address": "Blok B", "price": 375_000_000, "building_area": 40, "source_platforms": "Pinhome"},
        {"name": "Rumah C no source", "address": "Blok C", "price": 390_000_000, "land_area": 90},
        {"name": "Rumah D no price", "address": "Blok D", "land_area": 90, "source_platforms": "Facebook"},
    ]
    assert count_valid_comparables(rows) == 2


def test_analysis_page_uses_sequential_steps_and_defers_analysis_to_final_step():
    source = _app_source()
    assert "if active_step == 1:" in source
    assert "if active_step == 2:" in source
    assert "if active_step == 3:" in source
    assert "if active_step == 4:" in source
    assert 'st.button("🚀 ANALISA / UPDATE DATA"' in source
    assert "st.tabs([\"1 · Data lelang" not in source
    assert "_persist_and_go_analysis_step" in source


def test_step_navigation_persists_plain_values_and_restores_cleaned_widgets():
    state = {
        "na_lot_code": "LOT-9",
        "na_limit": 175_000_000,
        "na_comparables_current": [{"name": "A"}],
        "na_comparables_editor_widget": {"temporary": True},
        "na_auction_date_picker": "temporary-picker-value",
        "na_document": object(),
        "na_survey_photos": [object()],
        "unrelated": "keep",
    }
    assert persist_analysis_step_state(state, 2) == 2
    saved = state["_na_persisted_form_state"]
    assert saved["na_lot_code"] == "LOT-9"
    assert saved["na_limit"] == 175_000_000
    assert saved["na_comparables_current"] == [{"name": "A"}]
    assert "na_comparables_editor_widget" not in saved
    assert "na_auction_date_picker" not in saved
    assert "na_document" not in saved
    assert "na_survey_photos" not in saved

    # Simulate Streamlit cleaning keys for a hidden step; newer visible values win.
    state.pop("na_lot_code")
    state.pop("na_limit")
    state["na_limit"] = 180_000_000
    restore_analysis_step_state(state)
    assert state["na_lot_code"] == "LOT-9"
    assert state["na_limit"] == 180_000_000
    assert state["na_analysis_step"] == 2


def test_step_navigation_clamps_step_number_to_valid_range():
    state = {"na_lot_code": "LOT-1"}
    assert persist_analysis_step_state(state, 99) == 4
    assert state["na_analysis_step"] == 4
    assert persist_analysis_step_state(state, -3) == 1


def test_release_version_is_1024_and_column_layouts_do_not_exceed_four():
    config_text = Path("config.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.0.24"' in config_text
    tree = ast.parse(_app_source())
    oversized = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "columns"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value > 4:
            oversized.append((node.lineno, arg.value))
        elif isinstance(arg, (ast.List, ast.Tuple)) and len(arg.elts) > 4:
            oversized.append((node.lineno, len(arg.elts)))
    assert oversized == [], f"st.columns must have at most four columns: {oversized}"


def test_payment_date_ui_distinguishes_official_document_date_from_internal_estimate():
    source = _app_source()
    assert 'st.session_state.get("na_payment_deadline_source") == "Dokumen KPKNL"' in source
    assert "Batas pelunasan yang tertulis pada dokumen KPKNL" in source
    assert "Informasi internal jika menang pada tanggal lelang" in source
