"""Deterministic break-even and financial stress-test calculations.

All outputs are calculated through the same project calculator used by the
underwriting engine. No AI-generated financial figures are accepted here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .calculator import calculate_project
from .utils import to_float


def _total_fixed_months(inputs: dict[str, Any]) -> float:
    survey = inputs.get("survey", {}) or {}
    costs = inputs.get("costs", {}) or {}
    return max(0.0, sum(to_float(survey.get(k)) for k in ("possession_months",)) + sum(
        to_float(costs.get(k)) for k in ("legal_delay_months", "renovation_months")
    ))


def _inputs_for_holding(inputs: dict[str, Any], total_months: float) -> dict[str, Any]:
    cloned = deepcopy(inputs)
    costs = cloned.setdefault("costs", {})
    costs["selling_months"] = max(0.0, max(0.0, float(total_months)) - _total_fixed_months(inputs))
    return cloned


def _inputs_for_renovation_overrun(inputs: dict[str, Any], overrun_pct: float) -> dict[str, Any]:
    cloned = deepcopy(inputs)
    factor = 1.0 + max(0.0, float(overrun_pct)) / 100.0
    costs = cloned.setdefault("costs", {})
    costs["renovation_cost"] = max(0.0, to_float(costs.get("renovation_cost"))) * factor
    costs["unverified_scope_allowance"] = max(0.0, to_float(costs.get("unverified_scope_allowance"))) * factor
    # Percent-based contingency and hidden-condition reserves are recomputed by
    # calculate_project. Explicit hidden reserve stays fixed as a cash reserve.
    return cloned


def _find_exit_price(
    bid_price: float,
    inputs: dict[str, Any],
    *,
    target_roi_pct: float | None = None,
    max_iterations: int = 80,
) -> float | None:
    """Find exit price for zero profit or a target project ROI using bisection."""
    bid = max(0.0, to_float(bid_price))
    target = 0.0 if target_roi_pct is None else float(target_roi_pct)

    def reached(price: float) -> bool:
        result = calculate_project(bid, price, inputs)
        if target_roi_pct is None:
            return to_float(result.get("net_profit"), -1e30) >= 0
        roi = result.get("roi_pct")
        return roi is not None and to_float(roi, -1e30) >= target

    low = 0.0
    result_at_zero = calculate_project(bid, low, inputs)
    if reached(low):
        return 0.0
    high = max(
        100_000_000.0,
        to_float(result_at_zero.get("capital_before_sale")) * 2.0,
        bid * 3.0,
    )
    for _ in range(32):
        if reached(high):
            break
        high *= 2.0
        if high > 1e15:
            return None
    else:
        return None
    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        if reached(mid):
            high = mid
        else:
            low = mid
    return round(high)


def _max_holding_months(
    bid_price: float,
    exit_price: float | None,
    inputs: dict[str, Any],
    target_roi_pct: float,
    *,
    search_cap_months: float = 120.0,
) -> dict[str, Any]:
    if exit_price is None or to_float(exit_price) <= 0:
        return {"months": None, "status": "NO_EXIT_VALUE"}
    fixed = _total_fixed_months(inputs)

    def roi_at(months: float) -> float | None:
        case_inputs = _inputs_for_holding(inputs, months)
        result = calculate_project(bid_price, exit_price, case_inputs)
        value = result.get("roi_pct")
        return to_float(value) if value is not None else None

    min_roi = roi_at(fixed)
    if min_roi is None or min_roi < target_roi_pct:
        return {"months": None, "status": "BELOW_HURDLE_AT_MINIMUM_DURATION", "roi_at_minimum_duration_pct": min_roi}
    cap_roi = roi_at(search_cap_months)
    if cap_roi is not None and cap_roi >= target_roi_pct:
        return {"months": search_cap_months, "status": "AT_LEAST_SEARCH_CAP", "search_cap_months": search_cap_months, "roi_at_search_cap_pct": cap_roi}

    low, high = fixed, max(fixed, search_cap_months)
    for _ in range(80):
        mid = (low + high) / 2.0
        value = roi_at(mid)
        if value is not None and value >= target_roi_pct:
            low = mid
        else:
            high = mid
    return {"months": round(low, 2), "status": "THRESHOLD_CROSSED", "roi_at_limit_pct": roi_at(low)}


def build_financial_stress_test(
    bid_price: float,
    conservative_exit: float | None,
    base_exit: float | None,
    calculation_inputs: dict[str, Any],
    *,
    minimum_roi_pct: float = 15.0,
    go_roi_pct: float = 25.0,
    stress_holding_months: float = 12.0,
    stress_sale_discount_pct: float = 10.0,
    stress_renovation_overrun_pct: float = 50.0,
    stress_extra_cost: float = 0.0,
    extreme_holding_months: float = 18.0,
    extreme_sale_discount_pct: float = 20.0,
) -> dict[str, Any]:
    """Return break-even, ROI hurdle prices, max holding tolerance and stress cases."""
    bid = max(0.0, to_float(bid_price))
    exit_base = to_float(base_exit) if base_exit not in (None, "") and to_float(base_exit) > 0 else None
    exit_conservative = to_float(conservative_exit) if conservative_exit not in (None, "") and to_float(conservative_exit) > 0 else exit_base
    if exit_base is None:
        exit_base = exit_conservative
    if bid <= 0 or not calculation_inputs:
        return {"available": False, "reason": "Harga bid atau input perhitungan belum tersedia.", "scenarios": []}

    break_even_price = _find_exit_price(bid, calculation_inputs)
    min_roi_price = _find_exit_price(bid, calculation_inputs, target_roi_pct=minimum_roi_pct)
    go_roi_price = _find_exit_price(bid, calculation_inputs, target_roi_pct=go_roi_pct)
    base_duration = _total_fixed_months(calculation_inputs) + to_float((calculation_inputs.get("costs") or {}).get("selling_months"))
    holding_tolerance = _max_holding_months(
        bid, exit_conservative, calculation_inputs, minimum_roi_pct
    )

    scenarios: list[dict[str, Any]] = []
    if exit_base is not None and exit_base > 0:
        stress_specs = [
            ("Dasar", 0.0, 0.0, max(base_duration, 0.1), 0.0, "ARV dasar, RAB dan holding sesuai input Owner."),
            ("Moderat Buruk", 5.0, 20.0, max(base_duration + 3.0, 9.0), 0.0, "Harga jual turun 5%, renovasi +20%, dan holding minimal 9 bulan."),
            ("Tekanan", max(0.0, stress_sale_discount_pct), max(0.0, stress_renovation_overrun_pct), max(base_duration, stress_holding_months), max(0.0, stress_extra_cost), "Menggunakan parameter tekanan yang dapat diubah Owner."),
            ("Ekstrem", max(0.0, extreme_sale_discount_pct), max(0.0, stress_renovation_overrun_pct), max(base_duration, extreme_holding_months), max(0.0, stress_extra_cost), "Harga jual dan biaya renovasi tertekan; holding diperpanjang."),
        ]
        for name, discount, overrun, months, extra_cost, assumption in stress_specs:
            case_inputs = _inputs_for_renovation_overrun(calculation_inputs, overrun)
            case_inputs = _inputs_for_holding(case_inputs, months)
            if extra_cost:
                costs = case_inputs.setdefault("costs", {})
                costs["other_presale_cost"] = to_float(costs.get("other_presale_cost")) + extra_cost
            sale = max(0.0, exit_base * (1.0 - discount / 100.0))
            result = calculate_project(bid, sale, case_inputs)
            scenarios.append({
                "scenario": name,
                "exit_price": result.get("exit_price"),
                "sale_discount_pct": discount,
                "renovation_overrun_pct": overrun,
                "holding_months": result.get("holding_months"),
                "capital_before_sale": result.get("capital_before_sale"),
                "total_cost_including_selling": result.get("total_cost_including_selling"),
                "cash_requirement": result.get("cash_requirement_including_reserve"),
                "net_profit": result.get("net_profit"),
                "roi_pct": result.get("roi_pct"),
                "annualized_roi_pct": result.get("annualized_roi_pct"),
                "assumption": assumption,
            })

    return {
        "available": break_even_price is not None,
        "bid_price": bid,
        "exit_price_reference": exit_conservative,
        "break_even_exit_price": break_even_price,
        "exit_price_for_minimum_roi": min_roi_price,
        "exit_price_for_go_roi": go_roi_price,
        "minimum_roi_pct": float(minimum_roi_pct),
        "go_roi_pct": float(go_roi_pct),
        "base_holding_months": round(base_duration, 2),
        "max_holding_tolerance": holding_tolerance,
        "scenarios": scenarios,
        "notes": [
            "Break-even exit price dihitung pada harga bid yang diuji dengan biaya penjualan dan seluruh biaya proyek pada input saat ini.",
            "Cadangan likuiditas yang belum terpakai tidak otomatis diperlakukan sebagai biaya; gunakan skenario pemakaian cadangan untuk stress tambahan.",
            "Maximum holding tolerance adalah titik estimasi saat Project ROI turun ke ambang minimum, dengan holding cost bulanan sesuai input.",
        ],
    }
