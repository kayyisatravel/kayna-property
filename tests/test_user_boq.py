from core.user_boq import parse_user_boq_table, check_geometry_assumptions
from core.renovation_engine import infer_renovation_category
from services.gemini_parser import renovation_estimate_to_rows, estimate_missing_boq_unit_rates
import services.gemini_parser as gemini_parser
import json


def sample_boq():
    return '''
    Asumsi dimensi standar kavling: Luas Tanah 72 m² (6 m × 12 m) dan Luas Bangunan total ± 65 m².

    | No | Kelompok Pekerjaan | Item Pekerjaan Spesifik | Estimasi Volume | Satuan | Dasar Asumsi Perhitungan Dimensi |
    |---|---|---|---:|---|---|
    | I | Persiapan & Bongkaran | Pembersihan tumpukan peti kayu, sampah, dan area depan | 1,0 | Ls | Paket pembersihan area luar dan dalam rumah. |
    | | | Pembongkaran atap kanopi/teras depan yang jebol & keropos | 18,0 | m² | Lebar 6 m × kedalaman 3 m. |
    | II | Atap & Plafon | Pemasangan atap kanopi baru (rangka hollow/baja ringan + spandek) | 18,0 | m² | Mengganti seluruh penutup atap depan. |
    | | | Pemasangan flashing seng/waterproofing sambungan dinding tetangga | 12,0 | m' | 3 + 3 + 6 m. |
    | III | Dinding | Pelapisan waterproofing anti-rembes (dinding samping carport) | 24,0 | m² | 2 sisi × 4 m × 3 m. |
    | IV | Interior | Pengecatan ulang dinding interior rumah utama | 112,5 | m² | 2,5 × luas bangunan induk 45 m². |
    '''


def test_user_boq_parser_preserves_each_user_quantity_and_basis():
    rows = parse_user_boq_table(sample_boq())
    assert len(rows) == 6
    assert rows[0]["quantity"] == 1.0
    assert rows[1]["quantity"] == 18.0
    assert rows[2]["quantity"] == 18.0
    assert rows[3]["quantity"] == 12.0
    assert rows[4]["quantity"] == 24.0
    assert rows[5]["quantity"] == 112.5
    assert rows[1]["unit"] == "m²"
    assert rows[1]["quantity_basis"] == "Lebar 6 m × kedalaman 3 m."


def test_user_boq_rows_are_injected_even_if_gemini_omits_them():
    rows = parse_user_boq_table(sample_boq())
    mapped = renovation_estimate_to_rows({"items": [
        {"item_code": "USER_BOQ_001", "work_item": "Pembersihan", "unit_cost_low": 500_000, "unit_cost_conservative": 700_000}
    ]}, {}, rows)
    assert len(mapped) == len(rows)
    assert mapped[0]["quantity"] == 1.0
    assert mapped[0]["unit_cost"] == 700_000
    assert mapped[1]["quantity"] == 18.0
    assert mapped[1]["unit_cost"] is None
    assert "AI belum mengusulkan harga satuan" in mapped[1]["notes"]


def test_explicit_medium_description_wins_over_generic_light_physical_dropdown_when_auto_selected():
    description = "Objek masuk dalam kategori Renovasi Sedang. Atap teras rusak dan dinding lembap."
    assert infer_renovation_category("Renovasi Ringan", "Auto sesuai kondisi umum", description) == "Renovasi Sedang"
    assert infer_renovation_category("Renovasi Ringan", "Renovasi Ringan", description) == "Renovasi Ringan"


def test_geometry_mismatch_is_flagged_without_replacing_verified_property_dimensions():
    warnings = check_geometry_assumptions(sample_boq(), {"land_area": 102, "building_area": 90})
    assert len(warnings) == 2
    assert "LT 72" in warnings[0]
    assert "LB 65" in warnings[1]


def test_explicit_boq_scope_assigns_visible_damage_and_hidden_interior_separately():
    rows = parse_user_boq_table(sample_boq())
    by_name = {row["work_item"]: row for row in rows}
    roof_demo = by_name["Pembongkaran atap kanopi/teras depan yang jebol & keropos"]
    flashing = by_name["Pemasangan flashing seng/waterproofing sambungan dinding tetangga"]
    damp_wall = by_name["Pelapisan waterproofing anti-rembes (dinding samping carport)"]
    interior_paint = by_name["Pengecatan ulang dinding interior rumah utama"]
    assert roof_demo["priority"] == "Wajib"
    assert flashing["priority"] == "Wajib"
    assert damp_wall["priority"] == "Wajib"
    assert interior_paint["priority"] == "Bersyarat"
    assert roof_demo["subcategory"] == "Persiapan & Bongkaran"


def test_user_boq_group_is_preserved_for_project_budget_categorisation():
    rows = parse_user_boq_table(sample_boq())
    mapped = renovation_estimate_to_rows({"items": []}, {}, rows)
    assert mapped[0]["subcategory"] == "Persiapan & Bongkaran"
    assert mapped[1]["subcategory"] == "Persiapan & Bongkaran"
    assert mapped[2]["subcategory"] == "Atap & Plafon"
    assert mapped[5]["subcategory"] == "Interior"


def test_tas3_example_boq_keeps_all_16_rows_and_separates_known_from_assumed_scope():
    description = '''
    Berdasarkan foto tampak depan properti, kategori utama Renovasi Sedang.
    | No | Kelompok Pekerjaan | Item Pekerjaan Spesifik (Sesuai Temuan Foto) | Estimasi Volume | Satuan | Dasar Asumsi Perhitungan Dimensi |
    |---|---|---|---:|---|---|
    | I | Persiapan & Bongkaran | Pembersihan tumpukan peti kayu, sampah, dan area depan | 1,0 | Ls | Paket pembersihan area luar dan dalam rumah. |
    | | | Pembongkaran atap kanopi/teras depan yang jebol & keropos | 18,0 | m² | Lebar kavling 6 m × kedalaman area depan 3 m. |
    | | | Pengikisan cat mengelupas & jamur pada dinding dalam teras | 24,0 | m² | 2 sisi dinding samping panjang 4 m × tinggi 3 m. |
    | II | Atap & Plafon | Pemasangan atap kanopi baru (rangka hollow/baja ringan + spandek) | 18,0 | m² | Lebar 6 m × kedalaman 3 m. |
    | | | Pemasangan flashing seng/waterproofing sambungan dinding tetangga | 12,0 | m' | 3 m + 3 m + 6 m. |
    | | | Penggantian plafon area teras/carport (rangka hollow + PVC/GRC) | 18,0 | m² | Area di bawah kanopi depan. |
    | | | Perbaikan/tambal sulam plafon interior akibat rembesan | 9,0 | m² | Asumsi 20% dari luas induk. |
    | III | Dinding & Pengecatan | Pelapisan waterproofing anti-rembes (dinding samping carport) | 24,0 | m² | Dua sisi dinding depan. |
    | | | Pengecatan ulang dinding fasad & teras (cat weatherproof) | 45,0 | m² | Fasad, pilar, pagar tembok dan teras. |
    | | | Pengecatan ulang dinding interior rumah utama | 112,5 | m² | Rasio 2,5 × luas induk 45 m². |
    | IV | Lantai & Halaman | Pemasangan keramik area carport & teras | 21,0 | m² | Lebar 6 m × panjang 3,5 m. |
    | | | Perapian taman kecil & pembersihan kanstin depan | 1,0 | Ls | Area sudut depan kiri. |
    | V | Besi, Kayu & Utilitas | Pengamplasan & pengecatan ulang pagar besi dorong + teralis depan | 9,6 | m² | Lebar muka 6 m × tinggi rata-rata 1,6 m. |
    | | | Pengecatan ulang kusen, daun pintu, dan jendela | 6,0 | Unit | Enam unit. |
    | | | Peremajaan titik instalasi listrik | 11,0 | Titik | Rasio 65 m² ÷ 6. |
    | | | Servis ringan sanitair kamar mandi, keran air, dan cek pompa | 1,0 | Ls | Paket fungsi dasar. |
    '''
    rows = parse_user_boq_table(description)
    assert len(rows) == 16
    assert [r["quantity"] for r in rows] == [1, 18, 24, 18, 12, 18, 9, 24, 45, 112.5, 21, 1, 9.6, 6, 11, 1]
    by_name = {r["work_item"]: r for r in rows}
    assert by_name["Pembongkaran atap kanopi/teras depan yang jebol & keropos"]["priority"] == "Wajib"
    assert by_name["Pelapisan waterproofing anti-rembes (dinding samping carport)"]["priority"] == "Wajib"
    assert by_name["Pengecatan ulang dinding interior rumah utama"]["priority"] == "Bersyarat"
    assert by_name["Peremajaan titik instalasi listrik"]["priority"] == "Bersyarat"


def test_ai_boq_rows_match_by_exact_work_name_when_it_omits_user_item_code():
    rows = parse_user_boq_table(sample_boq())
    mapped = renovation_estimate_to_rows({"items": [
        {"work_item": "Pembersihan tumpukan peti kayu, sampah, dan area depan", "unit_cost_low": 450_000,
         "unit_cost_conservative": 600_000, "unit_cost_high": 750_000, "rate_basis": "Bahan dan tenaga kerja", "confidence": "Rendah"}
    ]}, {}, rows)
    assert len(mapped) == len(rows)
    first = mapped[0]
    assert first["item_code"] == "USER_BOQ_001"
    assert first["quantity"] == 1.0
    assert first["unit_cost_low"] == 450_000
    assert first["unit_cost"] == 600_000
    assert first["unit_cost_high"] == 750_000
    assert sum(1 for row in mapped if row["work_item"] == rows[0]["work_item"]) == 1


def test_assumption_based_interior_ceiling_repair_stays_conditional_even_if_text_mentions_water_leak():
    description = """
    | Kelompok Pekerjaan | Item Pekerjaan Spesifik | Estimasi Volume | Satuan | Dasar Asumsi Perhitungan Dimensi |
    |---|---|---:|---|---|
    | Atap & Plafon | Perbaikan/tambal sulam plafon interior akibat rembesan | 9,0 | m² | Asumsi 20% luas bangunan induk, interior belum diperiksa. |
    """
    row = parse_user_boq_table(description)[0]
    assert row["priority"] == "Bersyarat"
    assert row["conditional"] is True


def test_missing_boq_rate_second_pass_preserves_item_ids_and_returns_unit_rates(monkeypatch):
    rows = parse_user_boq_table(sample_boq())
    candidates = [rows[1]]
    response = {
        "items": [{
            "item_code": "USER_BOQ_002",
            "unit_cost_low": 250_000,
            "unit_cost_conservative": 325_000,
            "unit_cost_high": 400_000,
            "rate_basis": "Bahan penutup atap dan upah pemasangan termasuk; rangka besar tidak diasumsikan.",
            "materials_and_labor_included": True,
            "confidence": "Rendah",
            "notes": "Harga screening, wajib dibandingkan dengan penawaran lokal."
        }]
    }
    calls = {}
    def fake_client_call(api_key, model, prompt, **kwargs):
        calls["prompt"] = prompt
        calls["schema"] = kwargs.get("schema")
        return json.dumps(response)
    monkeypatch.setattr(gemini_parser, "_client_call", fake_client_call)
    result = estimate_missing_boq_unit_rates("test-key", candidates, {"location": "Sidoarjo"}, "gemini-3.5-flash-lite")
    assert result["requested_count"] == 1
    assert result["priced_count"] == 1
    assert result["items"][0]["item_code"] == "USER_BOQ_002"
    assert result["items"][0]["unit_cost"] == 325_000
    assert result["items"][0]["unit_cost_high"] == 400_000
    assert "bukan" in calls["prompt"].lower() and "HSPK/SSH" in calls["prompt"]


def test_all_16_user_boq_rows_keep_exact_quantity_when_gemini_returns_rates():
    description = '''
    | No | Kelompok Pekerjaan | Item Pekerjaan Spesifik | Estimasi Volume | Satuan | Dasar Asumsi Perhitungan Dimensi |
    |---|---|---|---:|---|---|
    | I | Atap | Pembongkaran atap kanopi depan | 18,0 | m² | Lebar 6 × kedalaman 3 m |
    | | | Pemasangan flashing | 12,0 | m' | 3 + 3 + 6 m |
    | II | Interior | Tambal sulam plafon interior akibat rembesan | 9,0 | m² | Asumsi 20% LB; interior belum diperiksa |
    '''
    rows = parse_user_boq_table(description)
    ai_items = [{
        "item_code": row["item_code"], "work_item": row["work_item"],
        "unit_cost_low": 100_000, "unit_cost_conservative": 125_000,
        "unit_cost_high": 150_000, "confidence": "Rendah"
    } for row in rows]
    mapped = renovation_estimate_to_rows({"items": ai_items}, {}, rows)
    assert len(mapped) == 3
    assert [r["quantity"] for r in mapped] == [18.0, 12.0, 9.0]
    assert len({r["item_code"] for r in mapped}) == 3
    assert all(r["unit_cost"] == 125_000 for r in mapped)
    assert mapped[2]["priority"] == "Bersyarat"
