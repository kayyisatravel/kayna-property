"""Increment-aware reverse bid search."""
from __future__ import annotations
from typing import Any
from .calculator import calculate_project
from .utils import to_float


def _meets(bid: float, exit_price: float, inputs: dict[str, Any], roi_target: float, cash_available: float | None, risk_ceiling: float | None) -> tuple[bool, dict[str, Any]]:
    result = calculate_project(bid, exit_price, inputs)
    ok = result["roi_pct"] is not None and result["roi_pct"] >= roi_target and result["net_profit"] > 0
    if cash_available is not None: ok = ok and result.get("cash_requirement_including_reserve", result["capital_before_sale"]) <= cash_available
    if risk_ceiling is not None: ok = ok and bid <= risk_ceiling
    return ok, result


def find_maximum_bid(exit_price: float, inputs: dict[str, Any], minimum_bid: float, increment: float, roi_target: float, cash_available: float | None = None, risk_ceiling: float | None = None, upper_bound: float | None = None) -> dict[str, Any]:
    minimum_bid, increment = to_float(minimum_bid), to_float(increment)
    if exit_price <= 0 or minimum_bid <= 0 or increment <= 0:
        return {"maximum_bid": None, "reason": "Harga exit, limit atau increment belum tersedia."}
    upper = upper_bound or max(minimum_bid * 10, exit_price * 2)
    ok_min, at_limit = _meets(minimum_bid, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    if not ok_min:
        return {"maximum_bid": None, "at_limit": at_limit, "reason": f"Nilai limit sudah tidak memenuhi ROI {roi_target:.1f}% atau kebutuhan kas."}
    lo_steps = 0
    hi_steps = max(1, int((upper - minimum_bid) // increment))
    while lo_steps < hi_steps:
        mid = (lo_steps + hi_steps + 1) // 2
        bid = minimum_bid + mid * increment
        ok, _ = _meets(bid, exit_price, inputs, roi_target, cash_available, risk_ceiling)
        if ok: lo_steps = mid
        else: hi_steps = mid - 1
    maximum = minimum_bid + lo_steps * increment
    _, at_max = _meets(maximum, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    return {"maximum_bid": round(maximum), "at_limit": at_limit, "at_maximum": at_max, "reason": "Batas tertinggi sesuai ROI, likuiditas dan risk ceiling."}


def build_bid_tiers(auction_limit: float, increment: float | None, conservative_exit: float, base_exit: float, inputs: dict[str, Any], cash_available: float | None, minimum_roi_pct: float = 25.0, mid_roi_pct: float = 35.0, risk_ceiling: float | None = None) -> dict[str, Any]:
    if not increment or increment <= 0:
        return {"increment_confirmed": False, "min_bid": auction_limit, "mid_bid": None, "max_bid": None, "walk_away_from": None, "reason": "Kelipatan bid belum dikonfirmasi."}
    mid = find_maximum_bid(conservative_exit, inputs, auction_limit, increment, mid_roi_pct, cash_available, risk_ceiling)
    maximum = find_maximum_bid(conservative_exit, inputs, auction_limit, increment, minimum_roi_pct, cash_available, risk_ceiling)
    base = find_maximum_bid(base_exit, inputs, auction_limit, increment, minimum_roi_pct, cash_available, risk_ceiling)
    return {
        "increment_confirmed": True, "min_bid": auction_limit,
        "mid_bid": mid.get("maximum_bid"), "mid_result": mid.get("at_maximum") or mid.get("at_limit"),
        "mid_roi_target": mid_roi_pct,
        "max_bid": maximum.get("maximum_bid"), "max_result": maximum.get("at_maximum") or maximum.get("at_limit"),
        "max_roi_target": minimum_roi_pct,
        "base_case_reference_bid": base.get("maximum_bid"),
        # No valid maximum means there is no defensible walk-away threshold to display.
        "walk_away_from": (maximum["maximum_bid"] + increment) if maximum.get("maximum_bid") is not None else None,
        "max_reason": maximum.get("reason"), "mid_reason": mid.get("reason"),
    }
