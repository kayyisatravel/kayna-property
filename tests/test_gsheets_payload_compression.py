import json
import importlib.util
import importlib.machinery
import sys
import types

# gspread is supplied by requirements.txt in deployment; stub import for offline unit tests.
if importlib.util.find_spec("gspread") is None:
    fake = types.ModuleType("gspread")
    fake.__path__ = []
    fake.__spec__ = importlib.machinery.ModuleSpec("gspread", loader=None, is_package=True)
    fake.service_account_from_dict = lambda *_a, **_k: None
    exc_module = types.ModuleType("gspread.exceptions")
    exc_module.__spec__ = importlib.machinery.ModuleSpec("gspread.exceptions", loader=None)
    class WorksheetNotFound(Exception):
        pass
    exc_module.WorksheetNotFound = WorksheetNotFound
    fake.exceptions = exc_module
    sys.modules["gspread"] = fake
    sys.modules["gspread.exceptions"] = exc_module

from storage.gsheets_db import _encode_json_cell, _decode_json_cell, GoogleSheetsDB, SCHEMA


def test_large_payload_json_is_compressed_below_google_cell_limit_and_roundtrips():
    payload = {"comparables": [{"name": f"Rumah {i}", "description": "Informasi listing lengkap " * 40, "price": i * 1000} for i in range(250)], "note": "snapshot"}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = _encode_json_cell(raw, tab="PROPERTIES", column="payload_json")
    assert encoded.startswith("__PFMS_GZIP_JSON_V1__:")
    assert len(encoded) < 50_000
    assert json.loads(_decode_json_cell(encoded)) == payload


def test_small_json_remains_plain_json():
    raw = '{"a":1}'
    encoded = _encode_json_cell(raw, tab="PROPERTIES", column="payload_json")
    assert encoded == raw
    assert _decode_json_cell(encoded) == raw


def test_non_json_long_cell_is_rejected_with_actionable_message():
    try:
        _encode_json_cell("x" * 50_100, tab="PROPERTIES", column="name")
    except ValueError as exc:
        assert "PROPERTIES.name" in str(exc)
        assert "Google Sheets" in str(exc)
    else:
        raise AssertionError("Expected long scalar cell to be rejected")


def test_row_values_compresses_payload_dict():
    db = object.__new__(GoogleSheetsDB)
    payload = {"snapshot": "some detail " * 3000}
    row = db._row_values("PROPERTIES", {"property_id":"P1", "payload":payload})
    header = SCHEMA["PROPERTIES"]
    encoded = row[header.index("payload_json")]
    assert encoded.startswith("__PFMS_GZIP_JSON_V1__:")
    assert json.loads(_decode_json_cell(encoded)) == payload


def test_gspread_error_diagnostic_includes_http_status_and_message():
    from storage.gsheets_db import _google_error_detail
    class Response:
        status_code = 400
        def json(self):
            return {"error": {"code":400,"message":"Invalid value at A1"}}
    class ApiError(Exception):
        response = Response()
    detail = _google_error_detail(ApiError("APIError"))
    assert "400" in detail
    assert "Invalid value at A1" in detail


def test_read_table_transparently_decompresses_payload_json():
    db = object.__new__(GoogleSheetsDB)
    payload = {"input_data": {"property": {"name": "Rumah Uji"}}, "latest_analysis": {"comparables": ["x"] * 3000}}
    encoded = _encode_json_cell(json.dumps(payload, ensure_ascii=False), tab="PROPERTIES", column="payload_json")

    class FakeWorksheet:
        def get_all_values(self):
            return [SCHEMA["PROPERTIES"], ["P-1", "", "", "L-1", "Rumah Uji", "Alamat", "", "100000000", "HOLD", "PROSPECT", encoded]]

    db.sheets = {"PROPERTIES": FakeWorksheet()}
    rows = db.read_table("PROPERTIES")
    assert rows[0]["payload"] == payload
    assert not rows[0]["payload_json"].startswith("__PFMS_GZIP_JSON_V1__:")
