from core.project_ledger import summarize_project_ledger
from core.onboarding import build_project_onboarding_records


def test_project_ledger_separates_paid_commitment_forecast_and_selling():
    actuals = [
        {"amount": 20_000_000, "category": "Renovasi", "budget_item_id": "BUD-1"},
        {"amount": 3_000_000, "category": "BPN/Legal", "budget_item_id": ""},
        {"amount": 4_000_000, "category": "Selling", "budget_item_id": ""},
    ]
    budgets = [{
        "budget_item_id": "BUD-1", "category": "Renovasi", "description": "Atap dan plafon",
        "budget_amount": 40_000_000, "committed_unpaid": 5_000_000,
        "forecast_remaining": 10_000_000, "status": "Active",
    }]
    result = summarize_project_ledger(actuals, budgets)
    assert result["actual_paid_total"] == 27_000_000
    assert result["actual_project_cost"] == 23_000_000
    assert result["actual_selling_cost"] == 4_000_000
    assert result["committed_unpaid_total"] == 5_000_000
    assert result["forecast_remaining_total"] == 10_000_000
    assert result["project_cost_at_completion_ex_selling"] == 38_000_000
    assert result["budget_lines"][0]["actual_paid"] == 20_000_000
    assert result["budget_lines"][0]["expected_at_completion"] == 35_000_000
    assert result["budget_lines"][0]["variance_at_completion"] == -5_000_000


def test_onboarding_creates_active_project_and_preserves_paid_vs_budget_records():
    result = build_project_onboarding_records(
        property_data={"name": "Rumah Uji", "address": "Sidoarjo", "lot_code": "LOT-01", "land_area": 100, "building_area": 80},
        win_details={"win_price": 170_000_000, "win_date": "2026-09-10"},
        project_stage="Renovation",
        project_notes="Renovasi berjalan",
        actual_transactions=[
            {"transaction_date": "2026-09-10", "category": "Pelunasan/akuisisi", "amount": 170_000_000, "description": "Harga perolehan"},
            {"transaction_date": "2026-09-11", "category": "Penguasaan/Kerahiman", "amount": 17_000_000, "description": "Kerahiman"},
        ],
        budget_items=[{"category": "Renovasi", "description": "Pekerjaan tersisa", "budget_amount": 40_000_000, "committed_unpaid": 5_000_000, "forecast_remaining": 10_000_000}],
    )
    prop = result["property"]
    assert prop["lifecycle_status"] == "ACTIVE"
    assert prop["decision_status"] == "INCOMPLETE"
    assert prop["payload"]["project_origin"] == "PROJECT_ONBOARDING"
    assert prop["payload"]["project_stage"] == "Renovation"
    assert result["property_id"] == prop["property_id"]
    assert len(result["actual_records"]) == 2
    assert len(result["budget_records"]) == 1
    assert result["actual_records"][0]["amount"] == 170_000_000


def test_onboarding_merges_existing_analysis_without_overwriting_snapshot():
    existing = {
        "property_id": "PROP-OLD", "created_at": "2026-01-01", "decision_status": "HOLD",
        "payload": {"latest_analysis": {"analysis_id": "ANL-OLD", "market": {"base_exit": 400_000_000}}, "input_data": {"property": {"name": "Old", "auction_limit": 100_000_000}}},
    }
    result = build_project_onboarding_records(
        property_data={"name": "Old", "address": "Alamat", "lot_code": "LOT-OLD"},
        win_details={"win_price": 120_000_000, "win_date": "2026-10-01"},
        project_stage="Renovation", project_notes="Legacy",
        actual_transactions=[], budget_items=[], existing_property=existing,
    )
    assert result["property"]["property_id"] == "PROP-OLD"
    assert result["property"]["decision_status"] == "HOLD"
    assert result["property"]["payload"]["latest_analysis"]["analysis_id"] == "ANL-OLD"
    assert result["property"]["payload"]["win_details"]["win_price"] == 120_000_000


def test_project_completion_excludes_unpaid_and_forecast_selling_costs():
    result = summarize_project_ledger(
        actual_rows=[
            {"amount": 100_000_000, "category": "Akuisisi"},
            {"amount": 2_000_000, "category": "Selling"},
        ],
        budget_rows=[
            {"budget_item_id": "B1", "category": "Renovasi", "budget_amount": 20_000_000,
             "committed_unpaid": 5_000_000, "forecast_remaining": 3_000_000},
            {"budget_item_id": "B2", "category": "Penjualan", "budget_amount": 8_000_000,
             "committed_unpaid": 4_000_000, "forecast_remaining": 2_000_000},
        ],
    )
    assert result["project_cost_at_completion_ex_selling"] == 108_000_000
    assert result["committed_unpaid_total"] == 9_000_000
    assert result["forecast_remaining_total"] == 5_000_000
    assert result["committed_selling_total"] == 4_000_000
    assert result["forecast_selling_total"] == 2_000_000
    assert result["total_cash_to_complete_including_selling_actual"] == 116_000_000


def test_penjualan_category_is_treated_as_exit_cost_not_pre_sale_project_cost():
    result = summarize_project_ledger(
        actual_rows=[{"amount": 7_000_000, "category": "Penjualan"}],
        budget_rows=[{"budget_item_id": "SELL-1", "category": "Penjualan", "budget_amount": 10_000_000,
                      "committed_unpaid": 1_000_000, "forecast_remaining": 2_000_000}],
    )
    assert result["actual_project_cost"] == 0
    assert result["actual_selling_cost"] == 7_000_000
    assert result["project_cost_at_completion_ex_selling"] == 0
    assert result["committed_selling_total"] == 1_000_000
    assert result["forecast_selling_total"] == 2_000_000
