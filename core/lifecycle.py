from __future__ import annotations
from typing import Any
from .utils import to_float


def actual_project_summary(actual_costs: list[dict[str, Any]], sale: dict[str, Any]) -> dict[str, Any]:
    categories: dict[str, float] = {}
    total_actual_cost = 0.0
    selling_cost_from_ledger = 0.0
    for row in actual_costs:
        amount = max(0.0, to_float(row.get("amount")))
        category = str(row.get("category", "Other"))
        categories[category] = categories.get(category, 0.0) + amount
        if category.lower() in {"selling", "biaya penjualan"}:
            selling_cost_from_ledger += amount
        else:
            total_actual_cost += amount
    sale_price = to_float(sale.get("closing_price"))
    # Prefer the closing form's total; otherwise use Selling ledger rows. Never count both.
    selling_actual = to_float(sale.get("selling_cost_actual")) or selling_cost_from_ledger
    net_profit = sale_price - selling_actual - total_actual_cost
    roi = net_profit / total_actual_cost * 100 if total_actual_cost > 0 and sale_price > 0 else None
    duration = to_float(sale.get("total_holding_months"))
    annualized = ((1 + roi / 100) ** (12 / duration) - 1) * 100 if roi is not None and roi > -100 and duration > 0 else None
    return {"actual_cost_by_category": categories, "total_actual_cost": total_actual_cost, "closing_price": sale_price, "selling_cost_actual": selling_actual, "net_profit_actual": net_profit, "roi_actual_pct": roi, "annualized_roi_actual_pct": annualized, "total_holding_months": duration}
