"""Increment-aware reverse bid search, including a ceiling below auction limit."""
from __future__ import annotations
from typing import Any
from .calculator import calculate_project
from .utils import to_float


def _meets(bid: float, exit_price: float, inputs: dict[str, Any], roi_target: float, cash_available: float | None, risk_ceiling: float | None) -> tuple[bool, dict[str, Any]]:
    result = calculate_project(bid, exit_price, inputs)
    roi = result.get("roi_pct")
    ok = roi is not None and roi >= roi_target and to_float(result.get("net_profit")) > 0
    if cash_available is not None:
        ok = ok and result.get("cash_requirement_including_reserve", result["capital_before_sale"]) <= cash_available
    if risk_ceiling is not None:
        ok = ok and bid <= risk_ceiling
    return ok, result


def find_maximum_bid(exit_price: float, inputs: dict[str, Any], minimum_bid: float, increment: float, roi_target: float, cash_available: float | None = None, risk_ceiling: float | None = None, upper_bound: float | None = None) -> dict[str, Any]:
    """Find highest bid meeting hurdle even when it is below auction limit.

    The old implementation returned None as soon as the auction limit failed,
    hiding the actual economic ceiling. This version searches from zero so the
    investor can see the ceiling and the gap to the auction limit.
    """
    minimum_bid = to_float(minimum_bid)
    increment = to_float(increment)
    if exit_price <= 0 or minimum_bid <= 0 or increment <= 0:
        return {"maximum_bid": None, "reason": "Harga exit, limit atau increment simulasi belum tersedia."}

    upper = upper_bound or max(minimum_bid * 10, exit_price * 2, minimum_bid + increment * 100)
    # If initial upper bound still meets the hurdle, expand it before searching.
    for _ in range(6):
        ok_upper, _ = _meets(upper, exit_price, inputs, roi_target, cash_available, risk_ceiling)
        if not ok_upper:
            break
        upper *= 2

    hi_steps = max(1, int(upper // increment))
    lo_steps = 0
    while lo_steps < hi_steps:
        mid_steps = (lo_steps + hi_steps + 1) // 2
        bid = mid_steps * increment
        ok, _ = _meets(bid, exit_price, inputs, roi_target, cash_available, risk_ceiling)
        if ok:
            lo_steps = mid_steps
        else:
            hi_steps = mid_steps - 1

    maximum = round(lo_steps * increment)
    if maximum <= 0:
        return {"maximum_bid": None, "at_limit": _meets(minimum_bid, exit_price, inputs, roi_target, cash_available, risk_ceiling)[1], "reason": f"Tidak ditemukan harga bid positif yang memenuhi ROI {roi_target:.1f}% dan batas risiko/pendanaan."}
    ok_limit, at_limit = _meets(minimum_bid, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    _, at_max = _meets(maximum, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    if maximum < minimum_bid:
        reason = f"Ceiling ekonomis {maximum:,.0f} berada di bawah limit {minimum_bid:,.0f}; jangan ikut bidding."
    elif not ok_limit:
        reason = "Nilai limit belum memenuhi seluruh hurdle; periksa ceiling dan pendanaan."
    else:
        reason = "Batas tertinggi yang memenuhi target ROI dan batasan yang diberikan."
    return {"maximum_bid": maximum, "at_limit": at_limit, "at_maximum": at_max, "limit_feasible": ok_limit, "reason": reason}


def build_bid_tiers(auction_limit: float, increment: float | None, conservative_exit: float, base_exit: float, inputs: dict[str, Any], cash_available: float | None, minimum_roi_pct: float = 25.0, mid_roi_pct: float = 35.0, risk_ceiling: float | None = None, simulation_step: float = 1_000.0) -> dict[str, Any]:
    if to_float(conservative_exit) <= 0 or to_float(auction_limit) <= 0:
        return {"increment_confirmed": bool(increment and increment > 0), "min_bid": auction_limit, "mid_bid": None, "max_bid": None, "walk_away_from": None, "reason": "Limit atau Conservative ARV belum tersedia; analisis biaya awal tetap dapat dilakukan."}

    increment_confirmed = bool(increment and increment > 0)
    step = to_float(increment) if increment_confirmed else max(1.0, to_float(simulation_step, 1_000.0))
    # Bid ceiling is first calculated economically. Cash sufficiency is shown as a
    # separate gate so lack of current funds does not mislabel an attractive asset
    # as economically DO NOT BID.
    mid = find_maximum_bid(conservative_exit, inputs, auction_limit, step, mid_roi_pct, None, risk_ceiling)
    maximum = find_maximum_bid(conservative_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling)
    base = find_maximum_bid(base_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling) if to_float(base_exit) > 0 else {}
    max_value = maximum.get("maximum_bid")
    walk_away = (max(auction_limit, max_value + step) if max_value is not None else auction_limit) if increment_confirmed else None
    return {
        "increment_confirmed": increment_confirmed,
        "increment_used_for_simulation": step,
        "increment_note": "Increment resmi/terverifikasi" if increment_confirmed else f"Simulasi menggunakan langkah komputasi Rp{step:,.0f}; bukan increment resmi. Konfirmasi pengumuman lelang sebelum bidding.",
        "min_bid": auction_limit,
        "mid_bid": mid.get("maximum_bid"), "mid_result": mid.get("at_maximum") or mid.get("at_limit"),
        "mid_roi_target": mid_roi_pct, "mid_limit_feasible": mid.get("limit_feasible"),
        "max_bid": max_value, "max_result": maximum.get("at_maximum") or maximum.get("at_limit"),
        "max_roi_target": minimum_roi_pct, "max_limit_feasible": maximum.get("limit_feasible"),
        "base_case_reference_bid": base.get("maximum_bid"),
        "walk_away_from": walk_away,
        "max_reason": maximum.get("reason"), "mid_reason": mid.get("reason"),
    }
