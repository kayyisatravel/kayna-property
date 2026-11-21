"""Increment-aware reverse bid search with a strict auction-limit floor.

A theoretical economic ceiling below the auction limit is useful diagnostic
information, but it is never returned as an actionable/legal bid.
"""
from __future__ import annotations
from typing import Any
from .calculator import calculate_project
from .utils import to_float


def _meets(
    bid: float,
    exit_price: float,
    inputs: dict[str, Any],
    roi_target: float,
    cash_available: float | None,
    risk_ceiling: float | None,
) -> tuple[bool, dict[str, Any]]:
    result = calculate_project(bid, exit_price, inputs)
    roi = result.get("roi_pct")
    ok = roi is not None and roi >= roi_target and to_float(result.get("net_profit")) > 0
    if cash_available is not None:
        ok = ok and result.get("cash_requirement_including_reserve", result["capital_before_sale"]) <= cash_available
    if risk_ceiling is not None:
        ok = ok and bid <= risk_ceiling
    return ok, result


def _grid_ceiling(
    exit_price: float,
    inputs: dict[str, Any],
    anchor: float,
    step: float,
    roi_target: float,
    cash_available: float | None,
    risk_ceiling: float | None,
    upper_bound: float | None,
) -> tuple[float | None, dict[str, Any] | None]:
    """Find max feasible price on anchor + n*step, n >= 0."""
    if step <= 0:
        return None, None
    ok_anchor, result_anchor = _meets(anchor, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    if not ok_anchor:
        return None, result_anchor

    upper = upper_bound if upper_bound and upper_bound > anchor else max(anchor * 10, exit_price * 2, anchor + step * 100)
    for _ in range(8):
        ok_upper, _ = _meets(upper, exit_price, inputs, roi_target, cash_available, risk_ceiling)
        if not ok_upper:
            break
        upper *= 2

    hi_steps = max(0, int((upper - anchor) // step))
    lo_steps = 0
    while lo_steps < hi_steps:
        mid_steps = (lo_steps + hi_steps + 1) // 2
        candidate = anchor + mid_steps * step
        ok, _ = _meets(candidate, exit_price, inputs, roi_target, cash_available, risk_ceiling)
        if ok:
            lo_steps = mid_steps
        else:
            hi_steps = mid_steps - 1

    maximum = round(anchor + lo_steps * step, 2)
    _, at_maximum = _meets(maximum, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    return maximum, at_maximum


def find_maximum_bid(
    exit_price: float,
    inputs: dict[str, Any],
    minimum_bid: float,
    increment: float,
    roi_target: float,
    cash_available: float | None = None,
    risk_ceiling: float | None = None,
    upper_bound: float | None = None,
) -> dict[str, Any]:
    """Find the highest *admissible* bid, never below the auction limit.

    When the auction limit itself fails the hurdle, ``maximum_bid`` is None.
    ``economic_ceiling`` is returned separately as a diagnostic only; it must
    never be presented to the user as a bid price.
    """
    minimum_bid = to_float(minimum_bid)
    increment = to_float(increment)
    if exit_price <= 0 or minimum_bid <= 0 or increment <= 0:
        return {
            "maximum_bid": None,
            "economic_ceiling": None,
            "limit_feasible": False,
            "reason": "Harga exit, limit atau increment simulasi belum tersedia.",
        }

    ok_limit, at_limit = _meets(minimum_bid, exit_price, inputs, roi_target, cash_available, risk_ceiling)
    if not ok_limit:
        # Diagnostic only: search a theoretical ceiling from zero. This is not
        # anchored to the auction ladder and is intentionally not a bid price.
        diagnostic_step = min(increment, 1_000.0)
        economic_ceiling, at_ceiling = _grid_ceiling(
            exit_price, inputs, 0.0, diagnostic_step, roi_target,
            cash_available, risk_ceiling, upper_bound,
        )
        if economic_ceiling is not None and economic_ceiling < minimum_bid:
            reason = (
                f"Ceiling ekonomis indikatif {economic_ceiling:,.0f} berada di bawah limit "
                f"{minimum_bid:,.0f}; tidak ada harga bid yang memenuhi target ROI "
                f"{roi_target:.1f}% pada atau di atas limit."
            )
        else:
            reason = (
                f"Nilai limit {minimum_bid:,.0f} tidak memenuhi target ROI {roi_target:.1f}% "
                "atau melampaui batas risiko/pendanaan. Ceiling teoritis bukan harga bid yang sah."
            )
        return {
            "maximum_bid": None,
            "economic_ceiling": economic_ceiling,
            "at_limit": at_limit,
            "at_economic_ceiling": at_ceiling,
            "at_maximum": None,
            "limit_feasible": False,
            "reason": reason,
        }

    # For an admissible bid ladder, the auction limit is the anchor. This keeps
    # bids aligned to limit + n * increment, even when the limit is not a multiple
    # of the increment.
    maximum, at_maximum = _grid_ceiling(
        exit_price, inputs, minimum_bid, increment, roi_target,
        cash_available, risk_ceiling, upper_bound,
    )
    if maximum is None:
        return {
            "maximum_bid": None,
            "economic_ceiling": None,
            "at_limit": at_limit,
            "limit_feasible": False,
            "reason": "Tidak ditemukan bid legal yang memenuhi target ROI pada increment yang diberikan.",
        }
    return {
        "maximum_bid": maximum,
        "economic_ceiling": maximum,
        "at_limit": at_limit,
        "at_maximum": at_maximum,
        "limit_feasible": True,
        "reason": "Batas tertinggi pada tangga bid mulai dari limit yang memenuhi target ROI dan batas risiko/pendanaan.",
    }


def build_bid_tiers(
    auction_limit: float,
    increment: float | None,
    conservative_exit: float,
    base_exit: float,
    inputs: dict[str, Any],
    cash_available: float | None,
    minimum_roi_pct: float = 25.0,
    mid_roi_pct: float = 35.0,
    risk_ceiling: float | None = None,
    simulation_step: float = 1_000.0,
) -> dict[str, Any]:
    if to_float(conservative_exit) <= 0 or to_float(auction_limit) <= 0:
        return {
            "increment_confirmed": bool(increment and increment > 0),
            "min_bid": auction_limit,
            "mid_bid": None,
            "max_bid": None,
            "walk_away_from": None,
            "walk_away_reason": "Limit atau Conservative ARV belum tersedia.",
            "reason": "Limit atau Conservative ARV belum tersedia; analisis biaya awal tetap dapat dilakukan.",
        }

    increment_confirmed = bool(increment and increment > 0)
    step = to_float(increment) if increment_confirmed else max(1.0, to_float(simulation_step, 1_000.0))
    # Cash adequacy is a separate funding gate; bid ceilings are economic and
    # risk ceilings, so lack of current cash does not hide a viable price ladder.
    mid = find_maximum_bid(conservative_exit, inputs, auction_limit, step, mid_roi_pct, None, risk_ceiling)
    maximum = find_maximum_bid(conservative_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling)
    base = find_maximum_bid(base_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling) if to_float(base_exit) > 0 else {}

    max_value = maximum.get("maximum_bid")
    mid_value = mid.get("maximum_bid")
    # Without the auction's official increment, even a mathematically feasible
    # price is not an actionable bid ladder. Retain it only as a computation
    # estimate and explicitly withhold all legal bid values.
    mid_simulated_ceiling = mid_value if not increment_confirmed and mid.get("limit_feasible") else None
    max_simulated_ceiling = max_value if not increment_confirmed and maximum.get("limit_feasible") else None
    actionable_mid = mid_value if increment_confirmed else None
    actionable_max = max_value if increment_confirmed else None
    walk_away = round(actionable_max + step, 2) if actionable_max is not None else None
    if not increment_confirmed and not maximum.get("limit_feasible"):
        below_limit = maximum.get("economic_ceiling")
        if below_limit is not None and below_limit < auction_limit:
            walk_away_reason = (
                f"JANGAN BID: ceiling ekonomis indikatif {below_limit:,.0f} berada di bawah limit "
                f"{auction_limit:,.0f} untuk target ROI minimum {minimum_roi_pct:.1f}%. "
                "Selain itu, increment resmi belum dikonfirmasi; tidak ada bid legal atau walk-away final."
            )
        else:
            walk_away_reason = (
                f"JANGAN BID berdasarkan target ROI minimum {minimum_roi_pct:.1f}% atau hard ceiling. "
                "Increment resmi juga belum dikonfirmasi; tidak ada bid legal atau walk-away final."
            )
    elif not increment_confirmed:
        walk_away_reason = "Belum ada bid legal yang dapat ditampilkan: kelipatan bid resmi belum dikonfirmasi. Ceiling simulasi hanya referensi komputasi, bukan harga bid atau walk-away."
    elif actionable_max is None:
        walk_away_reason = (
            f"JANGAN BID: limit {auction_limit:,.0f} tidak memenuhi target ROI minimum "
            f"{minimum_roi_pct:.1f}% atau melewati hard ceiling. Tidak ada bid legal yang memenuhi syarat."
        )
    else:
        walk_away_reason = f"Berhenti sebelum memasukkan bid {walk_away:,.0f}; bid tertinggi yang memenuhi syarat adalah {actionable_max:,.0f}."

    return {
        "increment_confirmed": increment_confirmed,
        "increment_used_for_simulation": step,
        "increment_note": "Increment resmi/terverifikasi" if increment_confirmed else f"Simulasi menggunakan langkah komputasi Rp{step:,.0f}; bukan increment resmi. Konfirmasi pengumuman lelang sebelum bidding.",
        "min_bid": auction_limit,
        # Actionable bids only. A theoretical ceiling below the limit lives in a
        # separate field and is never labelled as a bid.
        "mid_bid": actionable_mid,
        "mid_economic_ceiling": mid.get("economic_ceiling") if not mid.get("limit_feasible") else None,
        "mid_simulated_ceiling": mid_simulated_ceiling,
        "mid_result": (
            mid.get("at_maximum") if mid.get("maximum_bid") is not None
            else mid.get("at_economic_ceiling") or mid.get("at_limit")
        ),
        "mid_limit_feasible": bool(mid.get("limit_feasible")),
        "mid_roi_target": mid_roi_pct,
        "mid_reason": mid.get("reason"),
        "max_bid": actionable_max,
        "max_economic_ceiling": maximum.get("economic_ceiling") if not maximum.get("limit_feasible") else None,
        "max_simulated_ceiling": max_simulated_ceiling,
        "max_result": (
            maximum.get("at_maximum") if max_value is not None
            else maximum.get("at_economic_ceiling") or maximum.get("at_limit")
        ),
        "max_limit_feasible": bool(maximum.get("limit_feasible")),
        "max_roi_target": minimum_roi_pct,
        "base_case_reference_bid": base.get("maximum_bid") if increment_confirmed else None,
        "base_case_simulated_ceiling": base.get("maximum_bid") if not increment_confirmed and base.get("limit_feasible") else None,
        "base_case_economic_ceiling": base.get("economic_ceiling") if not base.get("limit_feasible") else None,
        "walk_away_from": walk_away,
        "walk_away_reason": walk_away_reason,
        "max_reason": maximum.get("reason"),
    }
