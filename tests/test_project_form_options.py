from core.project_form_options import ACTUAL_CATEGORIES, BUDGET_CATEGORIES, subcategory_options, scope_options


def test_renovation_ledger_options_are_hierarchical_and_specific():
    assert "Renovasi" in ACTUAL_CATEGORIES
    assert "Renovasi" in BUDGET_CATEGORIES
    assert "Atap, rangka & talang" in subcategory_options("Renovasi")
    assert "Penggantian genteng" in scope_options("Renovasi", "Atap, rangka & talang")


def test_other_category_has_a_manual_entry_option():
    assert "Lainnya" in subcategory_options("Lainnya")
    assert "Lainnya" in scope_options("Lainnya", "Lainnya")
