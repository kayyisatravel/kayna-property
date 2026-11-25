"""Project cost ledger helpers: paid actuals, commitments, and forecast are kept separate."""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from .utils import to_float

SELLING_CATEGORIES = {"selling", "penjualan", "biaya penjualan", "pajak penjualan", "komisi agen"}


def summarize_project_ledger(
    actual_rows: list[dict[str, Any]],
    budget_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize project finances without treating budgets/reserves as paid costs.

    COST_ACTUALS contains paid transactions only. PROJECT_BUDGETS contains each
    work/package forecast and its unpaid commitment. A transaction can be linked
    to a budget line through budget_item_id.
    """
    actual_by_budget: dict[str, float] = defaultdict(float)
    actual_by_category: dict[str, float] = defaultdict(float)
    actual_paid_total = 0.0
    actual_project_cost = 0.0
    actual_selling_cost = 0.0
    for row in actual_rows or []:
        amount = max(0.0, to_float(row.get("amount")))
        category = str(row.get("category") or "Lainnya").strip()
        category_key = category.lower()
        actual_by_category[category] += amount
        actual_paid_total += amount
        if category_key in SELLING_CATEGORIES:
            actual_selling_cost += amount
        else:
            actual_project_cost += amount
        budget_id = str(row.get("budget_item_id") or "").strip()
        if budget_id:
            actual_by_budget[budget_id] += amount

    lines: list[dict[str, Any]] = []
    total_budget = total_committed = total_forecast = total_line_expected = 0.0
    committed_project = forecast_project = committed_selling = forecast_selling = 0.0
    for budget in budget_rows or []:
        if str(budget.get("status") or "Active") in {"Archived", "Cancelled"}:
            continue
        item_id = str(budget.get("budget_item_id") or "")
        planned = max(0.0, to_float(budget.get("budget_amount")))
        committed = max(0.0, to_float(budget.get("committed_unpaid")))
        forecast = max(0.0, to_float(budget.get("forecast_remaining")))
        paid = actual_by_budget.get(item_id, 0.0)
        expected = paid + committed + forecast
        variance = planned - expected if planned > 0 else None
        total_budget += planned
        total_committed += committed
        total_forecast += forecast
        total_line_expected += expected
        category_key = str(budget.get("category") or "Lainnya").strip().lower()
        if category_key in SELLING_CATEGORIES:
            committed_selling += committed
            forecast_selling += forecast
        else:
            committed_project += committed
            forecast_project += forecast
        lines.append({
            "budget_item_id": item_id,
            "category": budget.get("category", "Lainnya"),
            "subcategory": budget.get("subcategory", ""),
            "description": budget.get("description", ""),
            "budget_amount": planned,
            "actual_paid": paid,
            "committed_unpaid": committed,
            "forecast_remaining": forecast,
            "expected_at_completion": expected,
            "variance_at_completion": variance,  # positive = budget remaining; negative = over budget
            "vendor": budget.get("vendor", ""),
            "due_date": budget.get("due_date", ""),
            "status": budget.get("status", "Active"),
        })

    return {
        "actual_paid_total": actual_paid_total,
        "actual_project_cost": actual_project_cost,
        "actual_selling_cost": actual_selling_cost,
        "actual_by_category": dict(actual_by_category),
        "committed_unpaid_total": total_committed,
        "forecast_remaining_total": total_forecast,
        "committed_project_cost_total": committed_project,
        "forecast_project_cost_total": forecast_project,
        "committed_selling_total": committed_selling,
        "forecast_selling_total": forecast_selling,
        "budget_total": total_budget,
        "budget_lines": lines,
        "budgeted_completion_total": total_line_expected,
        # This includes paid project costs plus unpaid commitments/forecast. Selling
        # costs are separately reported because they generally occur at exit.
        "project_cost_at_completion_ex_selling": actual_project_cost + committed_project + forecast_project,
        "total_cash_to_complete_including_selling_actual": actual_paid_total + total_committed + total_forecast,
        "unlinked_actual_cost": sum(
            max(0.0, to_float(r.get("amount"))) for r in actual_rows or []
            if not str(r.get("budget_item_id") or "").strip()
        ),
    }
