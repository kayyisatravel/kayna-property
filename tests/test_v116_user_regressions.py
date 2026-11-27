import base64
import importlib.util
import importlib.machinery
import json
import os
import re
import sys
import types

# gspread is only required on deployment; keep storage tests fully offline.
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

import services.gemini_parser as gp
from core.market_engine import assess_comparables
from core.renovation_engine import deduplicate_generated_rab_rows
from storage.gsheets_db import GoogleSheetsDB, SCHEMA, _JSON_CHUNK_PREFIX


def _listing_narrative():
    return r'''10 Listing Pembanding Terpercaya

1\. Rumah Siap Huni Dekat Polsek di Perum TAS 6 Balongbendo (Brighton)
• Harga Penawaran. Rp 425.000.000 (nego).
• Spesifikasi. LT 90 m² / LB 45 m², 2 kamar tidur, 1 kamar mandi, SHM.
• Tanggal Posting. Katalog Aktif 2026.
• URL Individual Valid. brighton.co.id

2\. Rumah Tipe Papua — unit resmi klaster developer di Taman Anggun Sejahtera 6 Suwaluh (Pinhome)
• Harga Penawaran. Rp 430.000.000.
• Spesifikasi. LT 90 m² / LB 45 m², 2 kamar tidur, 1 kamar mandi, 1.300 Watt.
• URL Individual Valid. pinhome.id

3\. Rumah Tipe Bali sebagai tipe standar dasar developer di Taman Anggun Sejahtera 6 Suwaluh (Pinhome)
• Harga Penawaran. Rp 395.000.000.
• Spesifikasi. LT 90 m² / LB 36 m², 2 kamar tidur, 1 kamar mandi.
• URL Individual Valid. pinhome.id

4\. Rumah Baru Tipe 55/105 Siap Huni Row 3 Mobil dari developer di TAS 6 Suwaluh (Pinhome)
• Harga Penawaran. Rp 460.000.000.
• Spesifikasi. LT 105 m² / LB 55 m², 2 kamar tidur, 1 kamar mandi.
• URL Individual Valid. pinhome.id

5\. Rumah Blok A4/32 di Perum Taman Anggun Sejahtera 6 (Lamudi Pro)
• Harga Penawaran. Rp 375.000.000.
• Spesifikasi. LT 90 m² / LB 36–45 m², 2 kamar tidur, 1 kamar mandi.
• Tanggal Posting. 16 November 2026.
• URL Individual Valid. lamudi.co.id

6\. Rumah Siap Huni di Perum TAS 6 Balongbendo (Lamudi Pro)
• Harga Penawaran. Rp 363.500.000.
• Spesifikasi. LT 90 m² / LB 45 m², 2 kamar tidur, 1 kamar mandi.
• Tanggal Posting. 16 November 2026.
• URL Individual Valid. lamudi.co.id

7\. Rumah Bypass Krian TAS 6 Siap KPR (Rumah123 Verified)
• Harga Penawaran. Rp 457.000.000.
• Spesifikasi. LT 90 m² / LB 45 m², 2 kamar tidur, 1 kamar mandi.
• URL Individual Valid. rumah123.com

8\. Rumah Baru Tipe 40/90 di Taman Anggun Sejahtera 9 Balongbendo (Brighton)
• Harga Penawaran. Rp 395.000.000.
• Spesifikasi. LT 90 m² / LB 40 m², 2 kamar tidur, 1 kamar mandi.
• URL Individual Valid. https\://www\.brighton\.co\.id/cari-properti/view/perumtas-9-1

9\. Rumah Baru Type 36/72 di Taman Anggun Sejahtera 9 Balongbendo (Brighton)
• Harga Penawaran. Rp 400.000.000.
• Spesifikasi. LT 72 m² / LB 36 m², 2 kamar tidur, 1 kamar mandi.
• Tanggal Posting. 17 Juni 2026.
• URL Individual Valid. https\://www\.brighton\.co\.id/cari-properti/view/rumah-murah-dengan-luas-tanah-lebar-krian

10\. Rumah Blok A8 No. 12 Perum TAS 6 Suwaluh — Threads (Over Kredit)
• Harga/Skema. Ganti DP Rp 30.000.000 + lanjut cicilan KPR; estimasi setara Rp 380–410 juta.
• Spesifikasi. LT 90 m² / LB 45 m².
• Tanggal Posting. 30 Oktober 2026.
• URL Individual Valid. threads.net
'''


def _fake_comparable_response(api_key, model, prompt, **kwargs):
    count_match = re.search(r"Jumlah item wajib (\d+) dengan indeks global: ([\d, ]+)\.", prompt)
    assert count_match, prompt[:300]
    count = int(count_match.group(1))
    start = int(count_match.group(2).split(",")[0].strip())
    prices = [425_000_000, 430_000_000, 395_000_000, 460_000_000, 375_000_000, 363_500_000, 457_000_000, 395_000_000, 400_000_000, 390_000_000]
    areas = [(90,45),(90,45),(90,36),(105,55),(90,40.5),(90,45),(90,45),(90,40),(72,36),(90,45)]
    names = [
        "TAS6 Brighton dekat Polsek", "TAS6 Tipe Papua Pinhome", "TAS6 Tipe Bali Pinhome",
        "TAS6 Tipe 55/105 Pinhome", "TAS6 Blok A4/32 Lamudi", "TAS6 Lamudi Siap Huni",
        "TAS6 Bypass Rumah123", "TAS9 Tipe 40/90 Brighton", "TAS9 Type 36/72 Brighton",
        "TAS6 Blok A8 Over Kredit",
    ]
    items = []
    for index in range(start, start + count):
        lt, lb = areas[index - 1]
        items.append({
            "i": index, "n": names[index - 1], "p": prices[index - 1],
            "lt": lt, "lb": lb, "kt": 2, "km": 1, "src": ["Portal listing"],
            "pt": "Asking aktif",
        })
    return json.dumps({"items": items, "parsing_notes": []})


def test_v116_parses_markdown_escaped_ten_listing_headings_and_bare_domains(monkeypatch):
    monkeypatch.setattr(gp, "_client_call", _fake_comparable_response)
    parsed = gp.parse_comparable_narrative("fake-key", _listing_narrative())
    assert parsed["detected_sections"] == 10
    assert parsed["count"] == 10
    assert parsed["api_calls"] == 3
    assert parsed["items"][0]["source_url"] == "https://brighton.co.id"
    assert parsed["items"][0]["source_url_scope"] == "Portal/domain only"
    assert parsed["items"][4]["building_area"] == 40.5
    assert "midpoint 40.5 m²" in parsed["items"][4]["notes"]
    assert parsed["items"][7]["source_url"].endswith("/perumtas-9-1")
    assert parsed["items"][7]["source_url_scope"] == "Listing individual"
    assert parsed["items"][9]["price_type"] == "Over kredit / skema kewajiban"


def test_v116_nine_regular_listings_produce_estimate_and_overcredit_is_secondary(monkeypatch):
    monkeypatch.setattr(gp, "_client_call", _fake_comparable_response)
    parsed = gp.parse_comparable_narrative("fake-key", _listing_narrative())
    result = assess_comparables(
        parsed["items"],
        {"name": "Objek A5-43", "complex_name": "TAS 6", "land_area": 90, "building_area": 45, "bedrooms": 2, "bathrooms": 1},
    )
    assert result["valid_count"] == 9
    assert len(result["secondary_only"]) == 1
    assert result["estimate_status"] == "INDICATIVE_AVAILABLE"
    assert result["base_exit"] > 0
    assert result["conservative_exit"] < result["base_exit"] < result["optimistic_exit"]
    assert result["confidence"] < 65  # Four unknown-segment rows are only supplementary; primary rows are excluded from resale ARV.
    assert result["primary_competition_count"] == 5
    assert result["valuation_comparable_count"] == 4
    assert result["status"] == "PRELIMINARY"  # Only two URLs are individual listing details.
    assert result["go_grade_count"] == 0  # Individual URLs belong to excluded primary listings, not the resale ARV pool.


def test_v116_one_sided_user_wall_paint_keeps_only_missing_surface_allowance():
    user = [{"item_code": "USER_BOQ_001", "work_item": "Pengecatan ulang dinding interior seluruh ruangan", "quantity": 100, "unit": "m2"}]
    generated = [{
        "item_code": "COS_WALL", "work_item": "Kupas cat lepas, plamir/aci lokal dan cat ulang dinding interior-eksterior",
        "quantity_low": 80, "quantity": 120, "quantity_high": 160, "unit": "m2",
    }]
    kept, removed = deduplicate_generated_rab_rows(user + generated, user)
    remaining = next(r for r in kept if r.get("item_code") == "COS_WALL")
    assert "eksterior/fasad" in remaining["work_item"]
    assert (remaining["quantity_low"], remaining["quantity"], remaining["quantity_high"]) == (40, 60, 80)
    assert "50%" in remaining["quantity_basis"]
    assert removed == []


def test_v116_site_protection_is_suppressed_only_when_user_boq_also_explicitly_covers_it():
    cleanup_only = [{"item_code": "USER_BOQ_001", "work_item": "Pembersihan peti kayu, sampah, dan area depan"}]
    generated = [{"item_code": "COS_PREP", "work_item": "Pembersihan dan proteksi area kerja"}]
    kept, removed = deduplicate_generated_rab_rows(cleanup_only + generated, cleanup_only)
    prep = next(r for r in kept if r.get("item_code") == "COS_PREP")
    assert "Proteksi dan penyiapan area kerja" in prep["work_item"]
    assert removed == []

    cleanup_and_protection = [{"item_code": "USER_BOQ_001", "work_item": "Pembersihan barang bekas serta proteksi area kerja dengan penutup lantai dan kusen"}]
    kept, removed = deduplicate_generated_rab_rows(cleanup_and_protection + generated, cleanup_and_protection)
    assert all(r.get("item_code") != "COS_PREP" for r in kept)
    assert any(r.get("item_code") == "COS_PREP" for r in removed)
    assert "Proteksi/penyiapan area kerja" in next(r for r in removed if r["item_code"] == "COS_PREP")["reason"]


def test_v116_manual_500m_distance_works_across_village_names_without_coordinates():
    subject = {"land_area": 90, "building_area": 45, "complex_name": "TAS 6"}
    row = {
        "name": "Perumahan berbeda desa", "address": "Desa sebelah, Sidoarjo",
        "complex_name": "Perumahan Desa Sebelah", "price": 410_000_000,
        "land_area": 90, "building_area": 45, "distance_m": 500,
        "source_platforms": "Brighton", "source_url": "https://brighton.co.id",
        "source_url_scope": "Portal/domain only", "date_found": "2026-11-23",
    }
    result = assess_comparables([row], subject)
    assert result["valid_count"] == 1
    assert result["valid"][0]["distance_km"] == 0.5
    assert result["valid"][0]["proximity_score"] == 100
    assert result["valid"][0]["location_method"].startswith("Jarak garis lurus diinput")


def test_v116_boQ_authoritative_rows_deduplicate_generated_generic_scopes():
    names = [
        "Pengecatan ulang dinding fasad eksterior (cat weatherproof 2 lapis)",
        "Pengecatan ulang dinding interior seluruh ruangan (2 lapis)",
        "Pengecatan ulang plafon interior dan teras depan",
        "Pembersihan, pelumasan engsel/kunci, dan pengecekan karet kusen pintu & jendela",
        "Peremajaan dan pengecekan fungsi titik instalasi listrik (saklar, stopkontak, fitting lampu)",
        "Pembersihan keramik lantai dalam dan pengecekan nat keramik",
        "Servis ringan sanitair kamar mandi, keran air, dan pengecekan saluran air bersih/kotor",
        "Pembersihan peti kayu, sampah, dan area depan",
    ]
    user_rows = [{"item_code": f"USER_BOQ_{i:03d}", "work_item": name} for i, name in enumerate(names, 1)]
    generated = [
        {"item_code": "COS_WALL", "work_item": "Kupas cat lepas, plamir/aci lokal dan cat ulang dinding interior-eksterior"},
        {"item_code": "COS_CEILING", "work_item": "Pengecatan plafon dan perbaikan nat/retak rambut lokal"},
        {"item_code": "MED_ELEC", "work_item": "Pemeriksaan dan perbaikan instalasi listrik sesuai temuan"},
        {"item_code": "JOINERY_MAINTENANCE", "work_item": "Pembersihan dan pelumasan engsel/kunci pintu dan jendela"},
        {"item_code": "TILE_CLEANING", "work_item": "Pembersihan keramik lantai dan pengecekan nat"},
        {"item_code": "LGT_SANITARY", "work_item": "Perbaikan/penggantian sanitair minor per kamar mandi"},
        {"item_code": "COS_PREP", "work_item": "Pembersihan dan proteksi area kerja"},
        {"item_code": "MED_WATERPROOF", "work_item": "Waterproofing dinding samping carport untuk mengatasi rembes"},
    ]
    kept, removed = deduplicate_generated_rab_rows(user_rows + generated, user_rows)
    kept_codes = [r["item_code"] for r in kept]
    removed_codes = [r["item_code"] for r in removed]
    assert all(f"USER_BOQ_{i:03d}" in kept_codes for i in range(1, 9))
    assert set(removed_codes) == {"COS_WALL", "COS_CEILING", "MED_ELEC", "JOINERY_MAINTENANCE", "TILE_CLEANING", "LGT_SANITARY"}
    assert "COS_PREP" in kept_codes  # Distinct protection/area setup remains after removing overlapping cleaning component.
    prep = next(r for r in kept if r.get("item_code") == "COS_PREP")
    assert "di luar pembersihan/angkut barang" in prep["work_item"]
    assert "MED_WATERPROOF" in kept_codes  # Distinct repair scope remains.


class _FakeWorksheet:
    def __init__(self, rows):
        self.rows = [list(row) for row in rows]

    def get_all_values(self):
        return [list(row) for row in self.rows]

    def append_rows(self, rows, **kwargs):
        self.rows.extend([list(row) for row in rows])

    def append_row(self, row, **kwargs):
        self.rows.append(list(row))


def test_v116_oversized_property_json_is_chunked_and_roundtrips_without_snapshot_loss():
    db = object.__new__(GoogleSheetsDB)
    db.sheets = {
        "PAYLOAD_CHUNKS": _FakeWorksheet([SCHEMA["PAYLOAD_CHUNKS"]]),
        "PROPERTIES": _FakeWorksheet([SCHEMA["PROPERTIES"]]),
    }
    large_text = base64.b64encode(os.urandom(70_000)).decode("ascii")
    payload = {"analysis_snapshot": {"long_text": large_text}, "preserve": True}
    row_values = db._row_values("PROPERTIES", {"property_id": "P-LARGE", "payload": payload})
    marker = row_values[SCHEMA["PROPERTIES"].index("payload_json")]
    assert marker.startswith(_JSON_CHUNK_PREFIX)
    assert len(marker) < 200
    assert len(db.sheets["PAYLOAD_CHUNKS"].rows) > 2
    db.sheets["PROPERTIES"].append_row(row_values)

    restored = db.read_table("PROPERTIES")
    assert restored[0]["payload"] == payload
    assert restored[0]["payload_json"].startswith("{")


def test_v116_chunked_payload_detects_missing_chunk_instead_of_returning_empty_snapshot():
    db = object.__new__(GoogleSheetsDB)
    db.sheets = {
        "PAYLOAD_CHUNKS": _FakeWorksheet([SCHEMA["PAYLOAD_CHUNKS"]]),
        "PROPERTIES": _FakeWorksheet([SCHEMA["PROPERTIES"]]),
    }
    large_text = base64.b64encode(os.urandom(70_000)).decode("ascii")
    row = db._row_values("PROPERTIES", {"property_id": "P-LARGE", "payload": {"data": large_text}})
    db.sheets["PROPERTIES"].append_row(row)
    db.sheets["PAYLOAD_CHUNKS"].rows.pop()
    try:
        db.read_table("PROPERTIES")
    except ValueError as exc:
        assert "Snapshot terpotong" in str(exc)
    else:
        raise AssertionError("Corrupt snapshot must not be read as an empty payload")


def test_v116_retry_repairs_missing_payload_chunk_instead_of_reusing_partial_write():
    db = object.__new__(GoogleSheetsDB)
    db.sheets = {
        "PAYLOAD_CHUNKS": _FakeWorksheet([SCHEMA["PAYLOAD_CHUNKS"]]),
        "PROPERTIES": _FakeWorksheet([SCHEMA["PROPERTIES"]]),
    }
    large_text = base64.b64encode(os.urandom(70_000)).decode("ascii")
    payload = {"keep": True, "data": large_text}
    row_values = db._row_values("PROPERTIES", {"property_id": "P-RETRY", "payload": payload})
    marker = row_values[SCHEMA["PROPERTIES"].index("payload_json")]
    assert marker.startswith(_JSON_CHUNK_PREFIX)
    # Simulate append interruption after one chunk; retry must append only missing parts.
    chunk_rows = db.sheets["PAYLOAD_CHUNKS"].rows
    assert len(chunk_rows) >= 3
    first_chunk = list(chunk_rows[1])
    db.sheets["PAYLOAD_CHUNKS"].rows = [chunk_rows[0], first_chunk]
    packed = __import__("storage.gsheets_db", fromlist=["_prepare_json_cell"])._prepare_json_cell(payload)
    retry_marker = db._store_chunked_payload(packed)
    assert retry_marker == marker
    db.sheets["PROPERTIES"].append_row(row_values)
    restored = db.read_table("PROPERTIES")
    assert restored[0]["payload"] == payload


def test_v116_primary_developer_comps_are_weighted_below_secondary_resale():
    subject = {"land_area": 90, "building_area": 45}
    base = {
        "name": "Listing serupa", "price": 400_000_000, "land_area": 90,
        "building_area": 45, "source_platforms": "Portal", "source_url": "https://portal.id",
        "source_url_scope": "Portal/domain only", "date_found": "2026-11-23",
    }
    secondary = assess_comparables([{**base, "market_segment": "Secondary / resale"}], subject)
    primary = assess_comparables([{**base, "market_segment": "Primary / developer"}], subject)
    unknown = assess_comparables([{**base, "market_segment": "Tidak diketahui"}], subject)
    sw = secondary["valid"][0]["weight"]
    pw = primary["valid"][0]["weight"]
    uw = unknown["valid"][0]["weight"]
    assert abs(pw / sw - 0.15) < 0.02
    assert pw < uw < sw
