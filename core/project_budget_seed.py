"""Create an immutable opening budget baseline from a saved pre-bid analysis.

The opening budget is a forecast, not a paid transaction. It is seeded once when
an analyzed opportunity becomes WON/ACTIVE. Actual payments are then recorded
in COST_ACTUALS and linked to these lines to reduce forecast_remaining.
"""
from __future__ import annotations

import re
from typing import Any

from .calculator import calculate_project
from .renovation_engine import rab_item_is_in_scope
from .utils import to_float


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "ITEM")).strip("_").upper()
    return text[:36] or "ITEM"


def build_opening_budget_from_analysis(
    snapshot: dict[str, Any] | None,
    property_id: str,
    win_price: float,
) -> dict[str, Any]:
    """Return stable, idempotent PROJECT_BUDGETS rows and baseline metadata.

    The seed uses the actual winning price, not the old auction limit. It
    recomputes buyer fee, BPHTB, legal cost, holding, and exit cost via the
    existing Python calculator. The saved underwriting snapshot is never
    altered. Unpriced RAB work is retained as a zero-budget pending-pricing
    line so it cannot silently disappear from the active project work scope.
    """
    snap = snapshot if isinstance(snapshot, dict) else {}
    if not snap or to_float(win_price) <= 0:
        return {"rows": [], "complete": False, "reason": "Snapshot analisis atau harga menang belum tersedia."}

    calc_inputs = snap.get("calculation_inputs")
    if not isinstance(calc_inputs, dict):
        calc_inputs = {
            "property": snap.get("property", {}),
            "survey": snap.get("survey", {}),
            "legal": snap.get("legal", {}),
            "costs": snap.get("costs", {}),
            "rules": snap.get("rules", {}),
        }
    market = snap.get("market", {}) if isinstance(snap.get("market"), dict) else {}
    exit_price = market.get("conservative_exit")
    estimate = calculate_project(float(win_price), exit_price, calc_inputs)
    costs = calc_inputs.get("costs", {}) if isinstance(calc_inputs.get("costs"), dict) else snap.get("costs", {})
    analysis_id = str(snap.get("analysis_id") or "ANALYSIS")
    rules = calc_inputs.get("rules", {}) if isinstance(calc_inputs.get("rules"), dict) else snap.get("rules", {})
    contingency_pct = to_float(rules.get("renovation_contingency_pct", 15), 15)

    rows: list[dict[str, Any]] = []

    def add(
        key: str, category: str, subcategory: str, description: str, amount: float,
        *, payload: dict[str, Any] | None = None, status: str = "Active",
    ) -> None:
        value = max(0.0, float(amount or 0))
        rows.append({
            "budget_item_id": f"{property_id}-BASE-{analysis_id}-{_slug(key)}",
            "property_id": property_id,
            "category": category,
            "subcategory": subcategory,
            "description": description,
            "budget_amount": round(value),
            "committed_unpaid": 0.0,
            # Until historical payments are entered and linked, the full amount
            # remains forecast. Linking a paid transaction reduces this balance.
            "forecast_remaining": round(value),
            "due_date": "",
            "vendor": "",
            "status": status,
            "updated_at": snap.get("analyzed_at") or "",
            "payload": {
                "entry_source": "PRE_BID_ANALYSIS_BASELINE",
                "analysis_id": analysis_id,
                "baseline_key": key,
                **(payload or {}),
            },
        })

    # Costs before exit, exactly summing to calculator capital_before_sale.
    add("ACQUISITION", "Akuisisi", "Pelunasan harga menang", "Harga menang / pokok perolehan", estimate.get("bid_price", win_price), payload={"calculation_field": "bid_price"})
    add("BUYER_FEE", "Bea lelang & pajak", "Bea lelang pembeli", "Bea lelang pembeli", estimate.get("buyer_auction_fee", 0), payload={"calculation_field": "buyer_auction_fee"})
    add("BPHTB", "Bea lelang & pajak", "BPHTB", "BPHTB berdasarkan harga menang dan aturan yang tersimpan", estimate.get("bphtb", 0), payload={"calculation_field": "bphtb"})

    legal_breakdown = [
        ("BPN_PNBP", "PNBP BPN", estimate.get("bpn_pnbp_cost", 0)),
        ("ROYA", "Roya", estimate.get("roya_cost", 0)),
        ("LEGAL_ADMIN", "Administrasi legal/BPN lain", estimate.get("other_acquisition_admin", 0)),
        ("OTHER_LEGAL", "Biaya legal lainnya", estimate.get("other_legal_cost", 0)),
        ("NOTARY_PPAT", "Notaris/PPAT akuisisi", estimate.get("acquisition_notary_ppat_fee", 0)),
    ]
    for key, label, amount in legal_breakdown:
        add(key, "BPN/Legalitas", label, label, amount, payload={"calculation_field": key.lower()})

    add("POSSESSION", "Penguasaan/Kerahiman", "Penguasaan dan pengosongan", "Estimasi biaya penguasaan/kerahiman dari analisis awal", estimate.get("possession_cost", 0), payload={"calculation_field": "possession_cost"})

    renovation_rows = costs.get("renovation_items", []) or []
    priced_renovation_total = 0.0
    pending_pricing = []
    for idx, item in enumerate(renovation_rows, start=1):
        if not isinstance(item, dict) or not rab_item_is_in_scope(item):
            continue
        name = str(item.get("work_item") or item.get("item_code") or f"Pekerjaan renovasi {idx}")
        qty = to_float(item.get("quantity"))
        rate = to_float(item.get("unit_cost"))
        priced = qty > 0 and rate > 0
        amount = qty * rate if priced else 0.0
        if priced:
            priced_renovation_total += amount
        else:
            pending_pricing.append(name)
        add(
            f"RENOVATION_{idx:03d}_{item.get('item_code') or name}",
            "Renovasi", str(item.get("subcategory") or "Pekerjaan renovasi"), name, amount,
            payload={
                "calculation_field": "renovation_items",
                "item_code": item.get("item_code"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "unit_cost": item.get("unit_cost"),
                "priority": item.get("priority"),
                "quantity_basis": item.get("quantity_basis"),
                "pending_pricing": not priced,
                "source_notes": item.get("notes", ""),
            },
        )

    extra_renovation = max(0.0, to_float(costs.get("renovation_extra_cost")))
    if extra_renovation > 0:
        add("RENOVATION_EXTRA", "Renovasi", "Pekerjaan tambahan", "Tambahan renovasi di luar rincian item", extra_renovation)
    calculated_renovation = max(0.0, to_float(estimate.get("renovation_cost")))
    # If stored RAB line totals differ from the cost value used by underwriting,
    # preserve the exact underwriting baseline as a reconciliation line. This
    # prevents silently changing the saved pre-bid total due to rounding/legacy.
    residual_renovation = calculated_renovation - priced_renovation_total - extra_renovation
    if abs(residual_renovation) > 1:
        add("RENOVATION_RECONCILIATION", "Renovasi", "Rekonsiliasi baseline analisis", "Penyesuaian agar baseline RAB sama dengan biaya renovasi yang dipakai underwriting", max(0.0, residual_renovation), payload={"calculation_field": "renovation_cost", "review_required": True})

    contingency = max(0.0, to_float(estimate.get("renovation_contingency")))
    add("RENOVATION_CONTINGENCY", "Renovasi", "Contingency", f"Contingency renovasi ({contingency_pct:g}%)", contingency, payload={"calculation_field": "renovation_contingency", "contingency_pct": contingency_pct})
    add("HOLDING", "Holding", "Biaya holding", "Estimasi biaya holding sampai properti siap dijual", estimate.get("holding_cost", 0), payload={"holding_months": estimate.get("holding_months")})
    add("MARKETING", "Marketing", "Pemasaran", "Estimasi biaya marketing", costs.get("marketing_cost", 0), payload={"calculation_field": "marketing_cost"})
    add("OTHER_PRESALE", "Lainnya", "Biaya sebelum penjualan", "Biaya lain sebelum penjualan", costs.get("other_presale_cost", 0), payload={"calculation_field": "other_presale_cost"})

    # Selling cost is intentionally visible as an exit budget, but excluded from
    # capital needed to bring the property to sale-ready condition.
    if estimate.get("selling_cost") is not None:
        add("SELLING", "Penjualan", "Biaya saat closing", "Estimasi biaya penjualan (terpisah dari modal sampai siap dijual)", estimate.get("selling_cost", 0), payload={"calculation_field": "selling_cost", "excluded_from_project_completion_capital": True})

    expected_project_total = sum(
        to_float(r.get("budget_amount")) for r in rows
        if str(r.get("category") or "").strip().lower() not in {"penjualan", "selling", "biaya penjualan"}
    )
    calculator_total = to_float(estimate.get("capital_before_sale"))
    baseline_warnings: list[str] = []
    if pending_pricing:
        baseline_warnings.append("Ada item RAB dalam lingkup yang belum memiliki harga/volume lengkap; baseline biaya renovasi masih parsial.")
    if not bool(costs.get("cost_estimates_reviewed", False)):
        baseline_warnings.append("Estimasi biaya pada analisis pra-lelang belum dikonfirmasi pengguna; periksa kembali baseline sebelum menggunakannya sebagai budget final.")
    complete = not pending_pricing and bool(costs.get("cost_estimates_reviewed", False)) and abs(expected_project_total - calculator_total) <= 2
    prebid_at_limit = snap.get("at_limit", {}) if isinstance(snap.get("at_limit"), dict) else {}
    return {
        "rows": rows,
        "analysis_id": analysis_id,
        "winning_price": float(win_price),
        "calculator_capital_before_sale": calculator_total,
        "seeded_project_budget_total": round(expected_project_total),
        "pending_pricing_items": pending_pricing,
        "baseline_complete": complete,
        "baseline_warnings": baseline_warnings,
        "pre_bid_capital_at_limit": prebid_at_limit.get("capital_before_sale"),
        "pre_bid_cash_need_at_limit": prebid_at_limit.get("cash_requirement_including_reserve"),
        "risk_reserves_not_budgeted": {
            "possession_risk_reserve": estimate.get("possession_risk_reserve", 0),
            "general_risk_reserve": estimate.get("general_risk_reserve", 0),
        },
        "pre_bid_decision_status": (snap.get("decision") or {}).get("status"),
        "pre_bid_cash_available": (snap.get("liquidity") or {}).get("cash_available_for_new_project"),
    }
