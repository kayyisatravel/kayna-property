from core.renovation_engine import build_renovation_quantity_guidance, infer_renovation_category
from services.gemini_parser import renovation_estimate_to_rows


def test_primary_medium_category_is_not_overridden_by_conditional_heavy_warning():
    description = """
    Berdasarkan foto tampak depan properti di Perum TAS 3 Blok M6 No. 12,
    Desa Kepuhkemiri, Kecamatan Tulangan, kondisi bangunan masuk dalam kategori
    Renovasi Sedang. Struktur utama rumah sudah dikembangkan penuh hingga ke garis
    depan, namun bagian atap depan rusak dan dinding samping teras lembap.

    Catatan kritis: pastikan kondisi atap bagian dalam. Jika kebocoran merembet
    ke rangka atap utama, anggaran renovasi dapat bergeser dari Renovasi Sedang
    menuju Renovasi Berat.
    """
    category = infer_renovation_category(
        physical_condition="Belum diketahui",
        selected="Auto sesuai kondisi umum",
        condition_description=description,
    )
    assert category == "Renovasi Sedang"

    guidance = build_renovation_quantity_guidance({
        "land_area": 102,
        "building_area": 90,
        "floor_count": 1,
        "bedrooms": 3,
        "bathrooms": 2,
        "physical_condition": "Belum diketahui",
        "renovation_category": "Auto sesuai kondisi umum",
        "condition_description": description,
        "interior_inspected": False,
    })
    assert guidance["category"] == "Renovasi Sedang"
    assert "pernyataan kategori utama" in guidance["category_basis"].lower()
    assert not any(x["item_code"] == "HVY_STRUCT" for x in guidance["items"])


def test_medium_local_front_roof_damage_does_not_get_full_roof_quantity_or_full_roof_item_cost():
    guidance = build_renovation_quantity_guidance({
        "land_area": 102,
        "building_area": 90,
        "floor_count": 1,
        "physical_condition": "Belum diketahui",
        "renovation_category": "Auto sesuai kondisi umum",
        "condition_description": "Kategori Renovasi Sedang. Atap teras depan sisi kiri jebol dan dinding carport lembap.",
    })
    items = {x["item_code"]: x for x in guidance["items"]}
    assert items["MED_DEM_ROOF"]["quantity_high"] is None
    assert items["MED_NEW_ROOF"]["quantity_high"] is None
    assert items["VIS_FRONT_ROOF"]["quantity_base"] is None
    assert "ukur panjang" in items["VIS_FRONT_ROOF"]["quantity_basis"].lower()


def test_whole_roof_quantity_requires_explicit_whole_roof_replacement_scope():
    guidance = build_renovation_quantity_guidance({
        "land_area": 102,
        "building_area": 90,
        "floor_count": 1,
        "physical_condition": "Renovasi Sedang",
        "renovation_category": "Renovasi Sedang",
        "condition_description": "Inspeksi memastikan ganti seluruh atap rumah, bukan hanya kanopi depan.",
    })
    roof = next(x for x in guidance["items"] if x["item_code"] == "MED_NEW_ROOF")
    assert roof["quantity_low"] is not None
    assert roof["quantity_high"] is not None


def test_ai_rab_mapper_uses_local_front_roof_package_and_avoids_generic_duplicate():
    guidance = build_renovation_quantity_guidance({
        "land_area": 102,
        "building_area": 90,
        "physical_condition": "Renovasi Sedang",
        "renovation_category": "Renovasi Sedang",
        "condition_description": "Atap teras depan jebol; perbaikan lokal saja.",
    })
    mapped = renovation_estimate_to_rows({"items": [
        {"item_code": "MED_NEW_ROOF", "work_item": "Ganti atap generik", "unit_cost_low": 100_000, "unit_cost_conservative": 150_000},
        {"item_code": "VIS_FRONT_ROOF", "work_item": "Paket atap depan", "unit_cost_low": 100_000, "unit_cost_conservative": 150_000},
    ]}, guidance)
    assert len(mapped) == 1
    assert mapped[0]["item_code"] == "VIS_FRONT_ROOF"
    assert mapped[0]["quantity"] is None
    assert "ukur panjang" in mapped[0]["quantity_basis"].lower()


def test_ai_cannot_invent_custom_work_quantities_from_photos_or_own_quantity_basis():
    mapped = renovation_estimate_to_rows({"items": [{
        "item_code": "CUSTOM_WALL_FIX", "work_item": "Perbaikan dinding", "quantity": 42,
        "quantity_basis": "AI memperkirakan 42 m2 dari foto", "unit": "m2",
        "unit_cost_low": 50_000, "unit_cost_conservative": 70_000,
    }]}, {})
    assert mapped[0]["quantity"] is None
    assert mapped[0]["quantity_low"] is None
    assert "tidak boleh mengukur skala dari foto" in mapped[0]["quantity_basis"].lower()


def test_conditional_rab_rows_are_excluded_from_base_total_until_user_confirms():
    from core.renovation_engine import rab_item_is_in_scope
    assert rab_item_is_in_scope({"priority": "Bersyarat", "conditional": True}) is False
    assert rab_item_is_in_scope({"priority": "Disarankan", "conditional": True}) is True
    assert rab_item_is_in_scope({"priority": "Wajib", "conditional": True}) is True
    assert rab_item_is_in_scope({"priority": "Tidak diperlukan setelah ditinjau"}) is False


def test_tas3_sample_rab_does_not_promote_hidden_heavy_works_or_duplicate_local_scopes(monkeypatch):
    import json
    import services.gemini_parser as gp

    description = """
    Berdasarkan foto tampak depan properti di Perum TAS 3 Blok M6 No. 12,
    kondisi bangunan masuk dalam kategori Renovasi Sedang. Atap teras depan
    galvalum sisi kiri rusak/jebol. Dinding dalam carport kanan cat mengelupas,
    berjamur dan rembes. Pagar besi tampak kokoh tetapi cat kusam. Lantai jalan
    masuk carport berupa rabat beton retak. Terdapat tumpukan peti kayu.
    Interior gelap dan belum terlihat. Catatan kritis: bila kebocoran merembet
    ke atap utama, kategori dapat bergeser menjadi Renovasi Berat.
    """
    response = {
        "items": [
            {"item_code":"VIS_FRONT_ROOF", "work_item":"Atap depan", "unit":"m2", "unit_cost_low":300000, "unit_cost_conservative":450000, "priority":"Wajib"},
            {"item_code":"MED_NEW_ROOF", "work_item":"Ganti atap umum", "unit":"m2", "unit_cost_low":300000, "unit_cost_conservative":450000, "priority":"Wajib"},
            {"item_code":"VIS_DAMP_WALL", "work_item":"Dinding rembes", "unit":"m2", "unit_cost_low":100000, "unit_cost_conservative":150000, "priority":"Wajib"},
            {"item_code":"MED_WALL", "work_item":"Dinding lembap generik", "unit":"m2", "unit_cost_low":100000, "unit_cost_conservative":150000, "priority":"Wajib"},
            {"item_code":"MED_CEILING", "work_item":"Plafon kemungkinan terdampak", "unit":"m2", "unit_cost_low":100000, "unit_cost_conservative":150000, "priority":"Bersyarat"},
            {"item_code":"VIS_CARPORT_FLOOR", "work_item":"Rabat beton carport", "unit":"m2", "unit_cost_low":100000, "unit_cost_conservative":150000, "priority":"Bersyarat"},
            {"item_code":"LGT_TILE", "work_item":"Pemasangan keramik", "unit":"m2", "unit_cost_low":150000, "unit_cost_conservative":200000, "priority":"Wajib"},
            {"item_code":"VIS_FENCE_PAINT", "work_item":"Cat pagar", "unit":"m2", "unit_cost_low":40000, "unit_cost_conservative":60000, "priority":"Bersyarat"},
            {"item_code":"HVY_STRUCT", "work_item":"Pekerjaan struktur (belum terbukti)", "unit":"ls", "quantity":1, "quantity_basis":"Tebakan AI dari foto", "unit_cost_low":5000000, "unit_cost_conservative":10000000, "priority":"Wajib"},
        ],
        "assumptions": ["RAB screening, perlu ukur dan verifikasi."],
        "items_to_inspect": ["Interior dan rangka atap utama"],
        "overall_note": "Draft RAB, bukan penawaran kontraktor.",
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(response))
    result = gp.estimate_renovation_rab(
        "fake-key", [], description,
        {"address":"Perum TAS 3, Kepuhkemiri, Tulangan, Sidoarjo", "land_area":102,
         "building_area":90, "floor_count":1, "bedrooms":3, "bathrooms":2,
         "physical_condition":"Belum diketahui", "renovation_category":"Auto sesuai kondisi umum",
         "interior_inspected":False},
    )
    rows = result["editor_rows"]
    codes = [x.get("item_code") for x in rows]
    assert result["category"] == "Renovasi Sedang"
    assert "HVY_STRUCT" not in codes
    assert codes.count("VIS_FRONT_ROOF") == 1
    assert "MED_NEW_ROOF" not in codes
    assert "LGT_TILE" not in codes
    assert codes.count("VIS_DAMP_WALL") == 1
    assert "MED_WALL" not in codes
    assert "HVY_STRUCT" not in codes
    conditional_ceiling = next(x for x in rows if x.get("item_code") == "MED_CEILING")
    assert conditional_ceiling["priority"] == "Bersyarat"
    assert result["total_conservative_complete"] is False


def test_medium_local_canopy_package_is_required_but_frame_replacement_is_conditional():
    guidance = build_renovation_quantity_guidance({
        "land_area": 102, "building_area": 90, "floor_count": 1,
        "physical_condition": "Belum diketahui",
        "renovation_category": "Auto sesuai kondisi umum",
        "condition_description": "Kategori Renovasi Sedang. Atap teras depan galvalum jebol dan terangkat.",
    })
    items = {x["item_code"]: x for x in guidance["items"]}
    assert items["VIS_FRONT_ROOF"]["priority"] == "Wajib"
    assert items["VIS_FRONT_ROOF_FRAME"]["priority"] == "Bersyarat"
    assert items["VIS_FRONT_ROOF_FRAME"]["conditional"] is True


def test_missing_visual_specific_rab_rows_are_injected_even_if_ai_omits_them(monkeypatch):
    import json
    import services.gemini_parser as gp

    payload = {
        "items": [{
            "item_code": "COS_PREP", "work_item": "Persiapan", "quantity": 1, "unit": "ls",
            "unit_cost_low": 100000, "unit_cost_conservative": 150000, "priority": "Wajib",
        }],
        "assumptions": [], "items_to_inspect": [], "overall_note": "Draft",
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(payload))
    description = (
        "Kategori Renovasi Sedang. Atap teras depan galvalum jebol. "
        "Dinding carport kanan lembap dan berjamur. Rabat beton carport retak. "
        "Pagar besi kusam. Interior belum diperiksa."
    )
    result = gp.estimate_renovation_rab(
        "fake-key", [], description,
        {"land_area": 102, "building_area": 90, "floor_count": 1,
         "renovation_category": "Auto sesuai kondisi umum", "physical_condition": "Belum diketahui",
         "interior_inspected": False},
    )
    rows = {r.get("item_code"): r for r in result["editor_rows"]}
    for code in ("VIS_FRONT_ROOF", "VIS_DAMP_WALL", "VIS_CARPORT_FLOOR", "VIS_FRONT_ROOF_FRAME", "VIS_FENCE_PAINT", "INSPECT_INTERIOR"):
        assert code in rows
    assert rows["VIS_FRONT_ROOF"]["priority"] == "Wajib"
    assert rows["VIS_DAMP_WALL"]["priority"] == "Wajib"
    assert rows["VIS_CARPORT_FLOOR"]["priority"] == "Bersyarat"
    assert rows["VIS_FRONT_ROOF_FRAME"]["priority"] == "Bersyarat"
    assert rows["VIS_DAMP_WALL"]["quantity"] is None


def test_theoretical_mid_ceiling_result_shows_roi_at_the_ceiling_not_roi_at_limit():
    from core.maximum_bid import build_bid_tiers
    from config import DEFAULT_RULES
    inputs = {
        "property": {"njop": 0, "npoptkp_eligible": False},
        "survey": {"possession_cost": 10_000_000, "possession_months": 1},
        "costs": {"renovation_cost": 20_000_000, "renovation_months": 1,
                   "selling_months": 3, "legal_delay_months": 0,
                   "monthly_holding_cost": 1_000_000, "marketing_cost": 2_000_000},
        "rules": dict(DEFAULT_RULES),
    }
    result = build_bid_tiers(160_000_000, 1_000_000, 300_000_000, 320_000_000, inputs, None, 25, 35)
    assert result["mid_bid"] is None
    assert result["mid_economic_ceiling"] < 160_000_000
    assert result["mid_result"]["bid_price"] == result["mid_economic_ceiling"]
    assert 34.9 <= result["mid_result"]["roi_pct"] <= 35.1


def test_unpriced_recommended_rab_item_blocks_final_go_until_priced_or_excluded():
    from core.decision_engine import evaluate_decision
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100, "land_area":90, "building_area":70},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "physical_condition":"Siap huni", "interior_inspected":True, "structure_verified_safe":True},
        "legal": {"identity_verified":True, "original_certificate_status":"Asli di bank/kreditur dan siap diserahkan", "dispute_detected":False, "tax_rules_verified":True},
        "rules": {"minimum_roi_pct":25},
        "costs": {"cost_estimates_reviewed":True, "renovation_items":[
            {"work_item":"Inspeksi plafon", "priority":"Disarankan", "quantity":1, "unit_cost":None}
        ]},
        "finance": {"cash_confirmed":True, "cash_available_for_new_project":1_000_000},
        "risk_reviewed":True,
    }
    result = evaluate_decision(
        inputs, {"valid_count":5,"go_grade_count":5,"confidence":85,"status":"READY"},
        {"increment_confirmed":True,"max_bid":150},
        {"roi_pct":35,"net_profit":60_000_000,"capital_before_sale":100,"cash_requirement_including_reserve":100,"projected_holding_days":90},
    )
    assert result["status"] == "HOLD"
    assert any("anggaran dasar tanpa volume/harga" in x for x in result["blockers"])


def test_conditional_or_not_required_rab_rows_do_not_block_final_go():
    from core.decision_engine import evaluate_decision
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100, "land_area":90, "building_area":70},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "physical_condition":"Siap huni", "interior_inspected":True, "structure_verified_safe":True},
        "legal": {"identity_verified":True, "original_certificate_status":"Asli di bank/kreditur dan siap diserahkan", "dispute_detected":False, "tax_rules_verified":True},
        "rules": {"minimum_roi_pct":25},
        "costs": {"cost_estimates_reviewed":True, "renovation_items":[
            {"work_item":"Rangka kanopi diperiksa kemudian", "priority":"Bersyarat", "quantity":None, "unit_cost":None},
            {"work_item":"Pemasangan keramik tidak diperlukan", "priority":"Tidak diperlukan setelah ditinjau", "quantity":None, "unit_cost":None},
        ]},
        "finance": {"cash_confirmed":True, "cash_available_for_new_project":1_000_000},
        "risk_reviewed":True,
    }
    result = evaluate_decision(
        inputs, {"valid_count":5,"go_grade_count":5,"confidence":85,"status":"READY"},
        {"increment_confirmed":True,"max_bid":150},
        {"roi_pct":35,"net_profit":60_000_000,"capital_before_sale":100,"cash_requirement_including_reserve":100,"projected_holding_days":90},
    )
    assert result["status"] == "GO"


def test_facade_colour_repaint_is_a_separate_optional_scope_not_merged_into_damp_wall():
    guidance = build_renovation_quantity_guidance({
        "land_area": 102, "building_area": 90, "floor_count": 1,
        "renovation_category": "Renovasi Sedang",
        "condition_description": "Fasad biru toska mencolok dengan aksen merah. Dinding carport kanan lembap dan mengelupas.",
    })
    items = {x["item_code"]: x for x in guidance["items"]}
    assert "VIS_DAMP_WALL" in items
    assert "VIS_FACADE_REPAINT" in items
    assert items["VIS_FACADE_REPAINT"]["priority"] == "Bersyarat"
    assert items["VIS_FACADE_REPAINT"]["quantity_base"] is None
    assert "kurangi bidang lembap" in items["VIS_FACADE_REPAINT"]["quantity_basis"].lower()


def test_occupancy_is_never_inferred_from_photo_or_belongings(monkeypatch):
    import json
    import services.gemini_parser as gp

    payload = {
        "items": [], "visual_findings": [], "likely_causes_to_verify": [],
        "interior_unknowns": [], "occupancy_unknowns": [], "interior_scenarios": [],
        "inspection_plan": [], "assumptions": [], "items_to_inspect": [],
        "overall_note": "Foto fasad saja.",
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(payload))
    result = gp.estimate_renovation_rab(
        "fake-key", [], "Rumah tampak gelap; ada ember dan pot di depan.",
        {"occupancy_status": "Belum Survei", "physical_condition": "Belum diketahui"},
    )
    assert any("tidak dapat dipastikan dari foto" in x.lower() for x in result["occupancy_unknowns"])


def test_occupancy_survey_status_is_echoed_as_user_evidence_not_ai_photo_conclusion(monkeypatch):
    import json
    import services.gemini_parser as gp

    payload = {
        "items": [], "visual_findings": [], "likely_causes_to_verify": [],
        "interior_unknowns": [], "occupancy_unknowns": [], "interior_scenarios": [],
        "inspection_plan": [], "assumptions": [], "items_to_inspect": [],
        "overall_note": "Berdasarkan survei pengguna.",
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(payload))
    status = "Sudah Survei — Kosong/Tidak Dihuni"
    result = gp.estimate_renovation_rab(
        "fake-key", [], "Atap depan rusak.",
        {"occupancy_status": status, "physical_condition": "Renovasi Sedang"},
    )
    assert any(status in x and "pilihan survei pengguna" in x.lower() for x in result["occupancy_unknowns"])


def test_tas3_explicit_boq_suppresses_duplicate_visual_allowances(monkeypatch):
    import json
    import services.gemini_parser as gp

    description = """
    Kategori Kondisi: Renovasi Sedang
    Lokasi Perum TAS 3 Blok M6 No. 12, Sidoarjo. Atap kanopi jebol, pagar besi kusam. Interior belum diperiksa.
    | No | Item Pekerjaan | Estimasi Volume | Satuan |
    |---|---|---:|---|
    | 1 | Pembersihan peti kayu dan sampah area depan | 1 | Ls |
    | 2 | Pemasangan atap kanopi baru rangka hollow dan spandek | 18 | m² |
    | 3 | Cat pagar besi dorong dan teralis | 9.6 | m² |
    """
    response = {
        "items": [
            {"item_code":"USER_BOQ_001", "work_item":"Pembersihan peti kayu dan sampah area depan", "unit":"ls", "unit_cost_low":500000, "unit_cost_conservative":900000, "unit_cost_high":1500000},
            {"item_code":"USER_BOQ_002", "work_item":"Pemasangan atap kanopi baru rangka hollow dan spandek", "unit":"m2", "unit_cost_low":320000, "unit_cost_conservative":410000, "unit_cost_high":500000},
            {"item_code":"USER_BOQ_003", "work_item":"Cat pagar besi dorong dan teralis", "unit":"m2", "unit_cost_low":45000, "unit_cost_conservative":65000, "unit_cost_high":95000},
            {"item_code":"VIS_FRONT_ROOF_FRAME", "work_item":"Ganti rangka kanopi depan", "unit":"m", "unit_cost_low":100000, "unit_cost_conservative":150000, "unit_cost_high":200000, "priority":"Bersyarat"},
            {"item_code":"VIS_FENCE_PAINT", "work_item":"Pengecatan pagar besi", "unit":"m2", "unit_cost_low":45000, "unit_cost_conservative":65000, "unit_cost_high":95000, "priority":"Bersyarat"},
        ],
        "assumptions": [], "items_to_inspect": [], "overall_note": "Draft screening."
    }
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(response))
    result = gp.estimate_renovation_rab(
        "fake-key", [], description,
        {"address":"Perum TAS 3, Tulangan, Sidoarjo", "land_area":102, "building_area":90,
         "floor_count":1, "physical_condition":"Belum diketahui",
         "renovation_category":"Auto sesuai kondisi umum", "interior_inspected":False},
    )
    codes = [row.get("item_code") for row in result["editor_rows"]]
    assert "USER_BOQ_001" in codes and "USER_BOQ_002" in codes and "USER_BOQ_003" in codes
    assert "VIS_FRONT_ROOF_FRAME" not in codes
    assert "VIS_FENCE_PAINT" not in codes
    assert len([row for row in result["editor_rows"] if str(row.get("item_code", "")).startswith("USER_BOQ_")]) == 3


def test_full_tas3_16_row_boq_yields_complete_screening_total_with_two_inspection_allowances(monkeypatch):
    import json
    import services.gemini_parser as gp
    from tests.test_user_boq import LATEST_TAS3_BOQ

    description = LATEST_TAS3_BOQ + """
    Atap teras depan galvalum tampak jebol/terangkat. Dinding samping carport cat mengelupas dan berjamur.
    Pagar besi kokoh namun kusam. Terdapat tumpukan peti kayu/sampah di area depan.
    Interior dan instalasi belum dapat diinspeksi. Status hunian dari survei: Dihuni (Minta Kompensasi).
    """
    response = {"items": [], "assumptions": [], "items_to_inspect": [], "overall_note": "Draft RAB screening."}
    monkeypatch.setattr(gp, "_client_call", lambda *args, **kwargs: json.dumps(response))
    result = gp.estimate_renovation_rab(
        "fake-key", [], description,
        {"address":"Perum TAS 3 Blok M6 No. 12, Tulangan, Sidoarjo", "land_area":102,
         "building_area":90, "floor_count":1, "bedrooms":3, "bathrooms":2,
         "physical_condition":"Renovasi Sedang", "renovation_category":"Auto sesuai kondisi umum",
         "interior_inspected":False, "occupancy_status":"Sudah Survei - Dihuni (Minta Kompensasi)"},
    )
    rows = result["editor_rows"]
    user_rows = [r for r in rows if str(r.get("item_code", "")).startswith("USER_BOQ_")]
    scope = [r for r in rows if gp._is_rab_item_in_scope(r)] if hasattr(gp, "_is_rab_item_in_scope") else rows
    assert len(user_rows) == 16
    assert len([r for r in user_rows if r.get("unit_cost") and r.get("unit_cost_low") and r.get("unit_cost_high")]) == 16
    assert "VIS_FENCE_PAINT" not in [r.get("item_code") for r in rows]
    assert "VIS_FRONT_ROOF_FRAME" not in [r.get("item_code") for r in rows]
    assert "VIS_CEILING_CHECK" in [r.get("item_code") for r in rows]
    assert "INSPECT_INTERIOR" in [r.get("item_code") for r in rows]
    assert result["total_conservative_complete"] is True
    assert result["total_range_complete"] is True
    assert result["in_scope_item_count"] == 18
    assert result["priced_item_count"] == 18
    assert result["user_boq_priced_count"] == 16
    assert result["total_low_indicative"] == 36_372_000
    assert result["total_conservative_indicative"] == 52_261_000
    assert result["total_high_indicative"] == 72_757_000
