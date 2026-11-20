def test_project_budget_sheet_and_cost_actuals_extensions_are_additive():
    from storage.gsheets_db import SCHEMA
    assert "PROJECT_BUDGETS" in SCHEMA
    assert SCHEMA["COST_ACTUALS"][:8] == ["actual_id", "property_id", "transaction_date", "category", "amount", "description", "receipt_url", "created_at"]
    assert SCHEMA["COST_ACTUALS"][-5:] == ["budget_item_id", "subcategory", "vendor", "payment_method", "details_json"]
