from __future__ import annotations
from typing import Any
from .utils import to_float


def compute_liquidity(real_cash: float, forecast_outflows: list[dict[str, Any]], reserve_pct: float, active_unpaid_commitments: float = 0.0) -> dict[str, Any]:
    cash = max(0.0, to_float(real_cash))
    planned = sum(max(0.0, to_float(x.get("amount"))) for x in forecast_outflows if x.get("confirmed", True))
    reserve = cash * max(0.0, min(100.0, to_float(reserve_pct))) / 100
    commitments = max(0.0, to_float(active_unpaid_commitments))
    available = cash - planned - commitments - reserve
    return {"real_cash": cash, "forecast_outflows": planned, "active_unpaid_commitments": commitments, "reserve_pct": reserve_pct, "liquidity_reserve": reserve, "cash_available_for_new_project": max(0.0, available), "surplus_shortfall": available}


def evaluate_funding(project_cash_need: float, deposit_amount: float, liquidity: dict[str, Any]) -> dict[str, Any]:
    available = to_float(liquidity.get("cash_available_for_new_project"))
    return {"project_cash_need": project_cash_need, "deposit_need": deposit_amount, "deposit_funded": available >= deposit_amount, "full_project_funded": available >= project_cash_need, "cash_surplus_after_project": available - project_cash_need}
