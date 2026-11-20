from core.ledger_transactions import reconcile_budget_payment_change, COMMITMENT_SOURCE, FORECAST_SOURCE


def test_new_payment_reduces_linked_commitment_without_mutating_original_rows():
    budgets = [{"budget_item_id": "B1", "committed_unpaid": 5_000_000, "forecast_remaining": 2_000_000}]
    transaction = {"budget_item_id": "B1", "amount": 2_000_000, "details_json": {"payment_source": COMMITMENT_SOURCE}}
    updated, error = reconcile_budget_payment_change(budgets, None, transaction)
    assert error is None
    assert updated[0]["committed_unpaid"] == 3_000_000
    assert budgets[0]["committed_unpaid"] == 5_000_000


def test_edit_reverses_previous_allocation_then_applies_new_allocation():
    budgets = [
        {"budget_item_id": "B1", "committed_unpaid": 3_000_000, "forecast_remaining": 0},
        {"budget_item_id": "B2", "committed_unpaid": 0, "forecast_remaining": 6_000_000},
    ]
    old = {"budget_item_id": "B1", "amount": 2_000_000, "details_json": {"payment_source": COMMITMENT_SOURCE}}
    new = {"budget_item_id": "B2", "amount": 4_000_000, "details_json": {"payment_source": FORECAST_SOURCE}}
    updated, error = reconcile_budget_payment_change(budgets, old, new)
    assert error is None
    assert updated[0]["committed_unpaid"] == 5_000_000
    assert updated[1]["forecast_remaining"] == 2_000_000


def test_reject_payment_larger_than_available_commitment():
    budgets = [{"budget_item_id": "B1", "committed_unpaid": 1_000_000, "forecast_remaining": 0}]
    transaction = {"budget_item_id": "B1", "amount": 2_000_000, "details_json": {"payment_source": COMMITMENT_SOURCE}}
    updated, error = reconcile_budget_payment_change(budgets, None, transaction)
    assert error and "melebihi" in error
    assert updated[0]["committed_unpaid"] == 1_000_000


def test_edit_legacy_transaction_without_payment_source_does_not_change_budget_balance():
    budgets = [{"budget_item_id": "B1", "committed_unpaid": 1_000_000, "forecast_remaining": 0}]
    old = {"budget_item_id": "B1", "amount": 2_000_000, "details_json": ""}
    new = {"budget_item_id": "B1", "amount": 2_000_000, "details_json": {"payment_source": "Pengeluaran di luar budget"}}
    updated, error = reconcile_budget_payment_change(budgets, old, new)
    assert error is None
    assert updated[0]["committed_unpaid"] == 1_000_000
