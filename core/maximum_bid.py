"""Increment-aware maximum-bid solver for Kayna Property flip underwriting.

A bid is admissible only when the conservative exit case clears both the
minimum project ROI and minimum net-profit hurdle, stays within the maximum
holding period, and respects any risk-adjusted ceiling. Theoretical ceilings
below the auction limit are diagnostics, never legal/actionable bids.
"""
from __future__ import annotations
from typing import Any
from .calculator import calculate_project
from .utils import to_float


def calculate_rule_of_thumb_mao(
    arv: float,
    inputs: dict[str, Any],
    factor_pct: float = 70.0,
    rounding_step: float = 1_000.0,
) -> dict[str, Any]:
    """Solve the 70%-rule MAO while accounting for bid-dependent buyer taxes.

    MAO = factor * conservative ARV - buyer auction fee - BPHTB - fixed legal/
    transfer costs - possession/evacuation - renovation and its contingency.
    Holding, selling costs and investor profit remain inside the residual
    (100%-factor) buffer, matching the rule-of-thumb's intended use as a quick
    screen. The separate full-cost MAO is calculated by the ROI solver.
    """
    arv = max(0.0, to_float(arv))
    factor_pct = max(0.0, min(100.0, to_float(factor_pct, 70.0)))
    step = max(1.0, to_float(rounding_step, 1_000.0))
    budget_ceiling = arv * factor_pct / 100.0
    if arv <= 0 or budget_ceiling <= 0:
        return {"mao": None, "factor_pct": factor_pct, "arv_basis": arv, "status": "NO_ARV"}

    def fits(bid: float) -> tuple[bool, dict[str, Any]]:
        calc = calculate_project(bid, arv, inputs)
        cost_components = {
            "buyer_auction_fee": to_float(calc.get("buyer_auction_fee")),
            "bphtb": to_float(calc.get("bphtb")),
            "legal_transfer": to_float(calc.get("legal_bpn_cost")),
            # Known property-borne arrears/obligations (e.g. PBB, utilities,
            # IPL) are entered in other_presale_cost and must reduce the quick
            # MAO budget rather than being hidden inside the residual buffer.
            "known_other_presale_obligations": to_float(inputs.get("costs", {}).get("other_presale_cost")),
            "possession_evacuation": to_float(calc.get("possession_cost")),
            "renovation": to_float(calc.get("renovation_cost")),
            "renovation_contingency": to_float(calc.get("renovation_contingency")),
            "hidden_condition_reserve": to_float(calc.get("hidden_condition_reserve")),
            "possession_risk_reserve": to_float(calc.get("possession_risk_reserve")),
            "general_risk_reserve": to_float(calc.get("general_risk_reserve")),
        }
        used = bid + sum(cost_components.values())
        return used <= budget_ceiling + 1e-6, {"used_budget": used, "budget_ceiling": budget_ceiling, "cost_components": cost_components}

    ok_zero, zero_detail = fits(0.0)
    if not ok_zero:
        return {
            "mao": None, "factor_pct": factor_pct, "arv_basis": arv,
            "status": "COSTS_EXCEED_RULE_OF_THUMB_BUDGET", **zero_detail,
        }

    # Integer bisection, then floor to a user-friendly increment to ensure the
    # displayed screening MAO never exceeds the 70%-rule budget.
    low, high = 0.0, budget_ceiling
    for _ in range(64):
        mid = (low + high) / 2.0
        ok, _ = fits(mid)
        if ok:
            low = mid
        else:
            high = mid
    mao = max(0.0, (low // step) * step)
    _, detail = fits(mao)
    return {
        "mao": round(mao),
        "factor_pct": factor_pct,
        "arv_basis": arv,
        "status": "CALCULATED",
        **detail,
    }


def _meets(
    bid: float,
    exit_price: float,
    inputs: dict[str, Any],
    roi_target: float,
    cash_available: float | None,
    risk_ceiling: float | None,
    minimum_net_profit: float = 0.0,
    maximum_holding_days: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    result = calculate_project(bid, exit_price, inputs)
    roi = result.get("roi_pct")
    profit = to_float(result.get("net_profit"), float("-inf"))
    duration_days = to_float(result.get("projected_holding_days"))
    profit_ok = result.get("net_profit") is not None and profit >= max(0.0, minimum_net_profit)
    duration_ok = maximum_holding_days is None or (duration_days > 0 and duration_days <= maximum_holding_days)
    roi_ok = roi is not None and to_float(roi) >= roi_target
    ok = roi_ok and profit_ok and duration_ok
    result["minimum_net_profit_required"] = max(0.0, minimum_net_profit)
    result["meets_minimum_net_profit"] = bool(profit_ok)
    result["maximum_holding_days_allowed"] = maximum_holding_days
    result["within_maximum_holding_days"] = bool(duration_ok)
    result["duration_assumption_available"] = bool(duration_days > 0)
    result["meets_roi_target"] = bool(roi_ok)
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
    minimum_net_profit: float = 0.0,
    maximum_holding_days: float | None = None,
) -> tuple[float | None, dict[str, Any] | None]:
    """Find max feasible price on anchor + n*step, n >= 0."""
    if step <= 0:
        return None, None
    ok_anchor, result_anchor = _meets(anchor, exit_price, inputs, roi_target, cash_available, risk_ceiling, minimum_net_profit, maximum_holding_days)
    if not ok_anchor:
        return None, result_anchor

    upper = upper_bound if upper_bound and upper_bound > anchor else max(anchor * 10, exit_price * 2, anchor + step * 100)
    for _ in range(8):
        ok_upper, _ = _meets(upper, exit_price, inputs, roi_target, cash_available, risk_ceiling, minimum_net_profit, maximum_holding_days)
        if not ok_upper:
            break
        upper *= 2

    hi_steps = max(0, int((upper - anchor) // step))
    lo_steps = 0
    while lo_steps < hi_steps:
        mid_steps = (lo_steps + hi_steps + 1) // 2
        candidate = anchor + mid_steps * step
        ok, _ = _meets(candidate, exit_price, inputs, roi_target, cash_available, risk_ceiling, minimum_net_profit, maximum_holding_days)
        if ok:
            lo_steps = mid_steps
        else:
            hi_steps = mid_steps - 1

    maximum = round(anchor + lo_steps * step, 2)
    _, at_maximum = _meets(maximum, exit_price, inputs, roi_target, cash_available, risk_ceiling, minimum_net_profit, maximum_holding_days)
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
    minimum_net_profit: float | None = None,
    maximum_holding_days: float | None = None,
) -> dict[str, Any]:
    """Find the highest admissible bid, never below the auction limit.

    When a value is omitted, policy thresholds are read from ``inputs.rules``.
    This preserves compatibility with direct callers and saved underwriting
    snapshots while applying current Kayna defaults in the main workflow.
    """
    minimum_bid = to_float(minimum_bid)
    increment = to_float(increment)
    rules = inputs.get("rules", {}) if isinstance(inputs, dict) else {}
    if minimum_net_profit is None:
        minimum_net_profit = to_float(rules.get("minimum_net_profit", 0.0))
    if maximum_holding_days is None:
        configured_max_days = rules.get("maximum_holding_days")
        maximum_holding_days = to_float(configured_max_days) if configured_max_days not in (None, "") else None
    minimum_net_profit = max(0.0, to_float(minimum_net_profit))

    if exit_price <= 0 or minimum_bid <= 0 or increment <= 0:
        return {
            "maximum_bid": None,
            "economic_ceiling": None,
            "limit_feasible": False,
            "reason": "Harga exit, limit atau increment simulasi belum tersedia.",
        }

    ok_limit, at_limit = _meets(minimum_bid, exit_price, inputs, roi_target, cash_available, risk_ceiling, minimum_net_profit, maximum_holding_days)
    if not ok_limit:
        # Diagnostic only: search a theoretical ceiling from zero. This is not
        # anchored to the auction ladder and is intentionally not a bid price.
        diagnostic_step = min(increment, 1_000.0)
        economic_ceiling, at_ceiling = _grid_ceiling(
            exit_price, inputs, 0.0, diagnostic_step, roi_target,
            cash_available, risk_ceiling, upper_bound, minimum_net_profit, maximum_holding_days,
        )
        reasons = []
        if at_limit.get("roi_pct") is None or to_float(at_limit.get("roi_pct")) < roi_target:
            reasons.append(f"ROI di bawah {roi_target:.1f}%")
        if to_float(at_limit.get("net_profit"), float("-inf")) < minimum_net_profit:
            reasons.append(f"profit bersih di bawah Rp{minimum_net_profit:,.0f}")
        if maximum_holding_days is not None and to_float(at_limit.get("projected_holding_days")) <= 0:
            reasons.append("estimasi durasi proyek belum tersedia")
        elif maximum_holding_days is not None and to_float(at_limit.get("projected_holding_days")) > maximum_holding_days:
            reasons.append(f"durasi melewati {maximum_holding_days:.0f} hari")
        if risk_ceiling is not None and minimum_bid > risk_ceiling:
            reasons.append("melewati hard ceiling risiko")
        reason_detail = "; ".join(reasons) or "batas pendanaan/risiko tidak terpenuhi"
        if economic_ceiling is not None and economic_ceiling < minimum_bid:
            reason = (
                f"Ceiling ekonomis indikatif {economic_ceiling:,.0f} berada di bawah limit "
                f"{minimum_bid:,.0f}; {reason_detail}. Ceiling teoritis bukan harga bid yang sah."
            )
        else:
            reason = (
                f"Nilai limit {minimum_bid:,.0f} tidak memenuhi syarat: {reason_detail}. "
                "Ceiling teoritis bukan harga bid yang sah."
            )
        return {
            "maximum_bid": None,
            "economic_ceiling": economic_ceiling,
            "at_limit": at_limit,
            "at_economic_ceiling": at_ceiling,
            "at_maximum": None,
            "limit_feasible": False,
            "minimum_net_profit_required": minimum_net_profit,
            "maximum_holding_days_allowed": maximum_holding_days,
            "reason": reason,
        }

    maximum, at_maximum = _grid_ceiling(
        exit_price, inputs, minimum_bid, increment, roi_target,
        cash_available, risk_ceiling, upper_bound, minimum_net_profit, maximum_holding_days,
    )
    if maximum is None:
        return {
            "maximum_bid": None,
            "economic_ceiling": None,
            "at_limit": at_limit,
            "limit_feasible": False,
            "reason": "Tidak ditemukan bid legal yang memenuhi target ROI, profit minimum, durasi, dan batas risiko.",
        }
    return {
        "maximum_bid": maximum,
        "economic_ceiling": maximum,
        "at_limit": at_limit,
        "at_maximum": at_maximum,
        "limit_feasible": True,
        "minimum_net_profit_required": minimum_net_profit,
        "maximum_holding_days_allowed": maximum_holding_days,
        "reason": "Batas tertinggi pada tangga bid yang memenuhi target ROI, profit bersih minimum, durasi maksimum, dan batas risiko.",
    }


def build_bid_tiers(
    auction_limit: float,
    increment: float | None,
    conservative_exit: float,
    base_exit: float,
    inputs: dict[str, Any],
    cash_available: float | None,
    minimum_roi_pct: float = 15.0,
    mid_roi_pct: float = 30.0,
    risk_ceiling: float | None = None,
    simulation_step: float = 1_000.0,
    optimistic_exit: float | None = None,
    minimum_net_profit: float | None = None,
    maximum_holding_days: float | None = None,
    conditional_maximum_holding_days: float | None = None,
    go_minimum_roi_pct: float | None = None,
) -> dict[str, Any]:
    rules = inputs.get("rules", {}) if isinstance(inputs, dict) else {}
    if minimum_net_profit is None:
        minimum_net_profit = to_float(rules.get("minimum_net_profit", 0.0))
    if maximum_holding_days is None:
        configured_max_days = rules.get("maximum_holding_days")
        maximum_holding_days = to_float(configured_max_days) if configured_max_days not in (None, "") else None
    if conditional_maximum_holding_days is None:
        configured_conditional_days = rules.get("conditional_maximum_holding_days")
        conditional_maximum_holding_days = (
            to_float(configured_conditional_days)
            if configured_conditional_days not in (None, "")
            else maximum_holding_days
        )
    if to_float(conservative_exit) <= 0 or to_float(auction_limit) <= 0:
        return {
            "increment_confirmed": bool(increment and increment > 0),
            "min_bid": auction_limit,
            "mid_bid": None,
            "max_bid": None,
            "walk_away_from": None,
            "walk_away_reason": "Limit atau Quick Sale ARV belum tersedia.",
            "reason": "Limit atau Quick Sale ARV belum tersedia; analisis biaya awal tetap dapat dilakukan.",
        }

    increment_confirmed = bool(increment and increment > 0)
    step = to_float(increment) if increment_confirmed else max(1.0, to_float(simulation_step, 1_000.0))
    # Cash adequacy is a separate funding gate. The ceiling is economic; the
    # available-cash gate is presented independently in the underwriting view.
    go_hurdle = max(to_float(minimum_roi_pct), to_float(go_minimum_roi_pct if go_minimum_roi_pct is not None else rules.get("go_minimum_roi_pct", 25.0)))
    go = find_maximum_bid(conservative_exit, inputs, auction_limit, step, go_hurdle, None, risk_ceiling,
                          minimum_net_profit=minimum_net_profit, maximum_holding_days=maximum_holding_days)
    mid = find_maximum_bid(conservative_exit, inputs, auction_limit, step, mid_roi_pct, None, risk_ceiling,
                           minimum_net_profit=minimum_net_profit, maximum_holding_days=maximum_holding_days)
    maximum = find_maximum_bid(conservative_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling,
                               minimum_net_profit=minimum_net_profit, maximum_holding_days=conditional_maximum_holding_days)
    base = find_maximum_bid(base_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling,
                            minimum_net_profit=minimum_net_profit, maximum_holding_days=conditional_maximum_holding_days) if to_float(base_exit) > 0 else {}
    upper_exit = to_float(optimistic_exit) if optimistic_exit not in (None, "") else 0.0
    upper = find_maximum_bid(upper_exit, inputs, auction_limit, step, minimum_roi_pct, None, risk_ceiling,
                             minimum_net_profit=minimum_net_profit, maximum_holding_days=conditional_maximum_holding_days) if upper_exit > 0 else {}

    max_value = maximum.get("maximum_bid")
    mid_value = mid.get("maximum_bid")
    go_value = go.get("maximum_bid")
    go_simulated_ceiling = go_value if not increment_confirmed and go.get("limit_feasible") else None
    mid_simulated_ceiling = mid_value if not increment_confirmed and mid.get("limit_feasible") else None
    max_simulated_ceiling = max_value if not increment_confirmed and maximum.get("limit_feasible") else None
    actionable_go = go_value if increment_confirmed else None
    actionable_mid = mid_value if increment_confirmed else None
    actionable_max = max_value if increment_confirmed else None
    walk_away = round(actionable_max + step, 2) if actionable_max is not None else None
    if not increment_confirmed and not maximum.get("limit_feasible"):
        below_limit = maximum.get("economic_ceiling")
        if below_limit is not None and below_limit < auction_limit:
            walk_away_reason = (
                f"JANGAN BID: ceiling ekonomis indikatif {below_limit:,.0f} berada di bawah limit "
                f"{auction_limit:,.0f} untuk minimum ROI {minimum_roi_pct:.1f}% dan profit bersih "
                f"Rp{minimum_net_profit:,.0f}. Increment resmi belum dikonfirmasi."
            )
        else:
            walk_away_reason = (
                f"JANGAN BID: limit tidak memenuhi ROI minimum {minimum_roi_pct:.1f}%, "
                f"profit minimum Rp{minimum_net_profit:,.0f}, atau durasi maksimum {conditional_maximum_holding_days or 0:.0f} hari. "
                "Increment resmi juga belum dikonfirmasi."
            )
    elif not increment_confirmed:
        walk_away_reason = "Belum ada bid legal yang dapat ditampilkan: kelipatan bid resmi belum dikonfirmasi. Ceiling simulasi hanya referensi komputasi; bukan harga bid resmi."
    elif actionable_max is None:
        walk_away_reason = (
            f"JANGAN BID: limit {auction_limit:,.0f} tidak memenuhi ROI minimum {minimum_roi_pct:.1f}%, "
            f"profit bersih minimum Rp{minimum_net_profit:,.0f}, batas durasi, atau hard ceiling."
        )
    else:
        walk_away_reason = f"Berhenti sebelum memasukkan bid {walk_away:,.0f}; bid tertinggi yang memenuhi seluruh syarat adalah {actionable_max:,.0f}."

    return {
        "increment_confirmed": increment_confirmed,
        "increment_used_for_simulation": step,
        "increment_note": "Increment resmi/terverifikasi" if increment_confirmed else f"Simulasi menggunakan langkah komputasi Rp{step:,.0f}; bukan increment resmi. Konfirmasi pengumuman lelang sebelum bidding.",
        "min_bid": auction_limit,
        "go_bid": actionable_go,
        "go_economic_ceiling": go.get("economic_ceiling") if not go.get("limit_feasible") else None,
        "go_simulated_ceiling": go_simulated_ceiling,
        "go_result": go.get("at_maximum") if go_value is not None else go.get("at_economic_ceiling") or go.get("at_limit"),
        "go_limit_feasible": bool(go.get("limit_feasible")),
        "go_roi_target": go_hurdle,
        "go_reason": go.get("reason"),
        "mid_bid": actionable_mid,
        "mid_economic_ceiling": mid.get("economic_ceiling") if not mid.get("limit_feasible") else None,
        "mid_simulated_ceiling": mid_simulated_ceiling,
        "mid_result": mid.get("at_maximum") if mid.get("maximum_bid") is not None else mid.get("at_economic_ceiling") or mid.get("at_limit"),
        "mid_limit_feasible": bool(mid.get("limit_feasible")),
        "mid_roi_target": mid_roi_pct,
        "mid_reason": mid.get("reason"),
        "max_bid": actionable_max,
        "max_economic_ceiling": maximum.get("economic_ceiling") if not maximum.get("limit_feasible") else None,
        "max_simulated_ceiling": max_simulated_ceiling,
        "max_result": maximum.get("at_maximum") if max_value is not None else maximum.get("at_economic_ceiling") or maximum.get("at_limit"),
        "max_limit_feasible": bool(maximum.get("limit_feasible")),
        "max_roi_target": minimum_roi_pct,
        "minimum_net_profit_required": minimum_net_profit,
        "maximum_holding_days_allowed": conditional_maximum_holding_days,
        "go_maximum_holding_days_allowed": maximum_holding_days,
        "base_case_max_bid": base.get("maximum_bid") if increment_confirmed else None,
        "base_case_simulated_ceiling": base.get("maximum_bid") if not increment_confirmed and base.get("limit_feasible") else None,
        "base_case_economic_ceiling": base.get("economic_ceiling") if not base.get("limit_feasible") else None,
        "base_case_result": base.get("at_maximum") if base.get("maximum_bid") is not None else base.get("at_economic_ceiling") or base.get("at_limit"),
        "base_case_limit_feasible": bool(base.get("limit_feasible")),
        "upper_case_max_bid": upper.get("maximum_bid") if increment_confirmed else None,
        "upper_case_simulated_ceiling": upper.get("maximum_bid") if not increment_confirmed and upper.get("limit_feasible") else None,
        "upper_case_economic_ceiling": upper.get("economic_ceiling") if not upper.get("limit_feasible") else None,
        "upper_case_result": upper.get("at_maximum") if upper.get("maximum_bid") is not None else upper.get("at_economic_ceiling") or upper.get("at_limit"),
        "upper_case_limit_feasible": bool(upper.get("limit_feasible")),
        "base_case_reference_bid": base.get("maximum_bid") if increment_confirmed else None,
        "base_case_simulated_reference_bid": base.get("maximum_bid") if not increment_confirmed and base.get("limit_feasible") else None,
        "base_case_reference_result": base.get("at_maximum") if base.get("maximum_bid") is not None else base.get("at_economic_ceiling") or base.get("at_limit"),
        "walk_away_from": walk_away,
        "walk_away_reason": walk_away_reason,
        "max_reason": maximum.get("reason"),
    }
