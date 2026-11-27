"""Deterministic feasibility scenarios used by the AI co-pilot.

All amounts are calculated by Python. The language model may interpret these
results but must never invent or replace the financial figures.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from .calculator import calculate_project
from .utils import to_float


def _set_total_holding_months(inputs: dict[str, Any], target_months: float) -> dict[str, Any]:
    cloned = deepcopy(inputs)
    survey = cloned.setdefault("survey", {})
    costs = cloned.setdefault("costs", {})
    fixed_months = sum(to_float(survey.get(k)) for k in ("possession_months",))
    fixed_months += sum(to_float(costs.get(k)) for k in ("legal_delay_months", "renovation_months"))
    # The scenario's selling period absorbs the remaining duration. If fixed
    # execution phases already exceed the target, keep the physically realistic
    # duration instead of making the project appear faster than possible.
    costs["selling_months"] = max(0.0, float(target_months) - fixed_months)
    return cloned


def build_feasibility_scenarios(
    bid_price: float,
    conservative_exit: float | None,
    base_exit: float | None,
    calculation_inputs: dict[str, Any],
    *,
    stress_holding_months: float = 12.0,
    stress_sale_discount_pct: float = 10.0,
    stress_extra_cost: float = 0.0,
) -> list[dict[str, Any]]:
    """Build fast/base/stress cases for the same proposed bid price."""
    if conservative_exit is None and base_exit is None:
        return [
            {"scenario": "Cepat", "holding_months": 3, "net_profit": None, "roi_pct": None, "message": "Belum ada dasar nilai exit. Masukkan ARV asumsi Owner atau pembanding."},
            {"scenario": "Moderat", "holding_months": None, "net_profit": None, "roi_pct": None, "message": "Belum ada dasar nilai exit. Masukkan ARV asumsi Owner atau pembanding."},
            {"scenario": "Tekanan", "holding_months": stress_holding_months, "net_profit": None, "roi_pct": None, "message": "Belum ada dasar nilai exit. Masukkan ARV asumsi Owner atau pembanding."},
        ]

    conservative = to_float(conservative_exit if conservative_exit is not None else base_exit)
    base = to_float(base_exit if base_exit is not None else conservative_exit)
    base_months = sum(to_float(v) for v in [
        calculation_inputs.get("survey", {}).get("possession_months"),
        calculation_inputs.get("costs", {}).get("legal_delay_months"),
        calculation_inputs.get("costs", {}).get("renovation_months"),
        calculation_inputs.get("costs", {}).get("selling_months"),
    ])
    fast_inputs = _set_total_holding_months(calculation_inputs, 3.0)
    base_inputs = deepcopy(calculation_inputs)
    stress_inputs = _set_total_holding_months(calculation_inputs, max(3.0, float(stress_holding_months)))
    stress_cost = max(0.0, to_float(stress_extra_cost))
    stress_inputs.setdefault("costs", {})["other_presale_cost"] = (
        to_float(stress_inputs["costs"].get("other_presale_cost")) + stress_cost
    )
    stress_sale = max(0.0, base * (1.0 - max(0.0, to_float(stress_sale_discount_pct)) / 100.0))

    cases = [
        ("Cepat", conservative, fast_inputs, "Penjualan cepat; tetap dibatasi waktu penguasaan dan renovasi yang tidak dapat dipangkas."),
        ("Moderat", base, base_inputs, "Menggunakan estimasi nilai dasar dan durasi proyek yang diinput."),
        ("Tekanan", stress_sale, stress_inputs, "Harga jual turun dan masa penjualan memanjang; tambahan biaya tekanan diterapkan bila diisi."),
    ]
    output: list[dict[str, Any]] = []
    for name, sale, inputs, message in cases:
        result = calculate_project(bid_price, sale, inputs)
        output.append({
            "scenario": name,
            "exit_price": result.get("exit_price"),
            "holding_months": result.get("holding_months"),
            "holding_days": result.get("projected_holding_days"),
            "total_capital": result.get("capital_before_sale"),
            "cash_requirement": result.get("cash_requirement_including_reserve"),
            "net_profit": result.get("net_profit"),
            "roi_pct": result.get("roi_pct"),
            "annualized_roi_pct": result.get("annualized_roi_pct"),
            "selling_cost": result.get("selling_cost"),
            "assumption": message,
        })
    return output
