from core.renovation_engine import build_renovation_quantity_guidance


def test_medium_category_does_not_force_whole_house_roof_ceiling_floor_and_bathrooms():
    result = build_renovation_quantity_guidance({
        "building_area": 90,
        "land_area": 102,
        "floor_count": 1,
        "bathrooms": 2,
        "physical_condition": "Renovasi sedang",
        "renovation_category": "Renovasi Sedang",
        "condition_description": "Atap teras depan sisi kiri jebol dan dinding carport lembap/berjamur.",
        "interior_inspected": False,
    })
    items = {x["item_code"]: x for x in result["items"]}
    assert items["MED_DEM_ROOF"]["priority"] == "Bersyarat"
    assert items["MED_CEILING"]["conditional"] is True
    assert items["MED_FLOOR"]["conditional"] is True
    assert items["MED_BATH"]["conditional"] is True
    assert "VIS_FRONT_ROOF" in items
    assert "VIS_DAMP_WALL" in items
    assert "INSPECT_INTERIOR" in items


def test_visual_description_adds_specific_scope_without_inventing_quantity():
    result = build_renovation_quantity_guidance({
        "building_area": 90,
        "land_area": 102,
        "floor_count": 1,
        "physical_condition": "Renovasi sedang",
        "renovation_category": "Renovasi Sedang",
        "condition_description": "Kanopi depan galvalum rusak/jebol. Dinding kanan tampak lembap, jamur, cat mengelupas. Rabat beton carport retak. Pagar besi kusam.",
        "interior_inspected": False,
    })
    items = {x["item_code"]: x for x in result["items"]}
    # Measured construction scopes must remain blank until actual dimensions are known.
    for code in ["VIS_FRONT_ROOF", "VIS_DAMP_WALL", "VIS_CARPORT_FLOOR", "VIS_FENCE_PAINT"]:
        assert code in items
        assert items[code]["quantity_base"] is None
        assert "ukur" in items[code]["quantity_basis"].lower()
    # Inspection and cleaning are explicitly one LS package, not inferred damage quantities.
    assert items["INSPECT_INTERIOR"]["quantity_base"] == 1
    assert "inspeksi" in items["INSPECT_INTERIOR"]["quantity_basis"].lower()


def test_unknown_interior_is_not_treated_as_observed_damage():
    result = build_renovation_quantity_guidance({
        "building_area": 80,
        "land_area": 100,
        "renovation_category": "Auto sesuai kondisi umum",
        "physical_condition": "Belum diketahui",
        "condition_description": "Foto hanya tampak depan rumah.",
        "interior_inspected": False,
    })
    items = {x["item_code"]: x for x in result["items"]}
    assert "AUTO_INSPECT" in items
    assert "INSPECT_INTERIOR" not in items
    assert all("kerusakan interior" not in x.get("work_item", "").lower() for x in result["items"])
