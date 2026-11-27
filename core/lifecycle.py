from __future__ import annotations
from typing import Any
import json
from .utils import to_float, iso_now
from .project_ledger import SELLING_CATEGORIES
from .returns import xirr, parse_cashflow_date


def actual_project_summary(actual_costs: list[dict[str, Any]], sale: dict[str, Any]) -> dict[str, Any]:
    categories: dict[str, float] = {}
    total_actual_cost = 0.0
    selling_cost_from_ledger = 0.0
    for row in actual_costs:
        amount = max(0.0, to_float(row.get("amount")))
        category = str(row.get("category", "Other"))
        categories[category] = categories.get(category, 0.0) + amount
        if category.strip().lower() in SELLING_CATEGORIES:
            selling_cost_from_ledger += amount
        else:
            total_actual_cost += amount
    sale_price = to_float(sale.get("closing_price"))
    # Prefer the closing form's total; otherwise use Selling ledger rows. Never count both.
    selling_actual = to_float(sale.get("selling_cost_actual")) or selling_cost_from_ledger
    net_profit = sale_price - selling_actual - total_actual_cost
    total_actual_cost_including_selling = total_actual_cost + selling_actual
    roi_pre_sale_capital = net_profit / total_actual_cost * 100 if total_actual_cost > 0 and sale_price > 0 else None
    roi = net_profit / total_actual_cost_including_selling * 100 if total_actual_cost_including_selling > 0 and sale_price > 0 else None
    duration = to_float(sale.get("total_holding_months"))
    annualized = ((1 + roi / 100) ** (12 / duration) - 1) * 100 if roi is not None and roi > -100 and duration > 0 else None

    # Actual XIRR requires a complete date for every cash cost. Gross closing
    # proceeds are positive at sold_date; selling costs come from the ledger when
    # present, otherwise the closing form's aggregate is posted on sold_date.
    sold_date = parse_cashflow_date(sale.get("sold_date"))
    dated_flows = []
    missing_cost_dates = 0
    ledger_selling_total = 0.0
    for row in actual_costs:
        amount = max(0.0, to_float(row.get("amount")))
        if amount <= 0:
            continue
        category = str(row.get("category", "Other")).strip().lower()
        if category in SELLING_CATEGORIES:
            ledger_selling_total += amount
        transaction_date = parse_cashflow_date(row.get("transaction_date") or row.get("date"))
        if transaction_date is None:
            missing_cost_dates += 1
        else:
            dated_flows.append((transaction_date, -amount))
    if selling_actual > 0 and ledger_selling_total <= 0 and sold_date is not None:
        dated_flows.append((sold_date, -selling_actual))
    if sale_price > 0 and sold_date is not None:
        dated_flows.append((sold_date, sale_price))
    xirr_actual = None
    explicit_selling_cost = max(0.0, to_float(sale.get("selling_cost_actual")))
    selling_reconciliation_gap = (abs(explicit_selling_cost - ledger_selling_total) if explicit_selling_cost > 0 and ledger_selling_total > 0 else 0.0)
    xirr_status = "Belum tersedia: tanggal closing belum tercatat" if sold_date is None else "Belum tersedia: arus kas belum memiliki tanggal lengkap"
    if selling_reconciliation_gap > max(1000.0, explicit_selling_cost * 0.01):
        xirr_status = "Belum tersedia: total biaya penjualan closing berbeda dari ledger; rekonsiliasi diperlukan"
    elif sold_date is not None and missing_cost_dates == 0 and dated_flows:
        xirr_actual = xirr(dated_flows)
        xirr_status = "Tersedia dari arus kas bertanggal" if xirr_actual is not None else "Tidak dapat dihitung: arus kas tidak membentuk satu tingkat pengembalian yang valid"
    return {
        "actual_cost_by_category": categories,
        "total_actual_cost": total_actual_cost,
        "total_actual_cost_including_selling": total_actual_cost_including_selling,
        "closing_price": sale_price,
        "selling_cost_actual": selling_actual,
        "net_profit_actual": net_profit,
        "roi_actual_pct": roi,
        "roi_on_presale_capital_actual_pct": roi_pre_sale_capital,
        "annualized_roi_actual_pct": annualized,
        "xirr_actual_pct": xirr_actual,
        "xirr_status": xirr_status,
        "xirr_cashflow_count": len(dated_flows),
        "xirr_missing_cost_date_count": missing_cost_dates,
        "selling_cost_reconciliation_gap": selling_reconciliation_gap,
        "total_holding_months": duration,
    }


def mark_property_won(existing: dict[str, Any], win_details: dict[str, Any]) -> dict[str, Any]:
    """Move an analyzed opportunity to WON without replacing its analysis snapshot."""
    if not isinstance(existing, dict) or not existing.get("property_id"):
        raise ValueError("Record properti tidak ditemukan.")
    win_price = to_float(win_details.get("win_price"))
    if win_price <= 0:
        raise ValueError("Harga menang wajib lebih besar dari nol.")
    payload = existing.get("payload") if isinstance(existing.get("payload"), dict) else None
    if payload is None:
        try:
            payload = json.loads(str(existing.get("payload_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    previous_win = payload.get("win_details") if isinstance(payload.get("win_details"), dict) else {}
    merged_payload = {**payload, "win_details": {**previous_win, **win_details}}
    return {
        **existing,
        "updated_at": iso_now(),
        "lifecycle_status": "WON",
        "payload": merged_payload,
    }
