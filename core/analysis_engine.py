"""Orchestration layer: inputs -> market -> costs -> maximum bid -> decision."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import uuid

from .calculator import calculate_project
from .maximum_bid import find_maximum_bid
from .occupancy import compare_possession_scenarios
from .market_engine import estimate_market_range
from .decision_engine import evaluate_decision
from .portfolio_engine import suitability_score


def run_property_analysis(inputs: dict[str, Any], investor: dict[str, Any]) -> dict[str, Any]:
    """Run one complete deterministic analysis. Gemini is intentionally not called here."""
    property_data = dict(inputs.get("property", {}))
    survey = dict(inputs.get("survey", {}))
    fees = dict(inputs.get("fees", {}))
    costs = dict(inputs.get("costs", {}))
    targets = dict(inputs.get("targets", {}))
    risk_scores = dict(inputs.get("risk_scores", {}))
    comparables = list(inputs.get("comparables", []) or [])
    possession_scenarios = dict(inputs.get("possession_scenarios", {}) or {})
    selected_key = str(costs.get("selected_possession_scenario", "")).strip()
    selected_scenario = possession_scenarios.get(selected_key, {})

    finance = {
        "cash_available": float(investor.get("live_cash", 0) or 0),
        "ongoing_project_commitments": float(investor.get("ongoing_commitments", 0) or 0),
        "household_operating_reserve": float(investor.get("household_reserve", 0) or 0),
        "mandatory_risk_reserve": float(investor.get("risk_reserve", 0) or 0),
        "minimum_net_profit": float(targets.get("minimum_net_profit", 0) or 0),
        "minimum_roi_pct": float(targets.get("minimum_roi_pct", 20) or 0),
        "minimum_profit_per_month": float(targets.get("minimum_profit_per_month", 0) or 0),
        "maximum_holding_months": float(targets.get("maximum_holding_months", 12) or 12),
        "annual_opportunity_cost_pct": float(targets.get("annual_opportunity_cost_pct", 0) or 0),
        "funding_data_confirmed": bool(investor.get("profile_confirmed", False)),
        "bid_increment": float(property_data.get("bid_increment", 1_000_000) or 1_000_000),
    }

    market = estimate_market_range(
        comparables,
        {
            "complex": property_data.get("complex_name", ""),
            "land_area": property_data.get("land_area", 0),
            "building_area": property_data.get("building_area", 0),
            "condition": survey.get("physical_condition", "Tidak diketahui"),
            "property_type": property_data.get("property_type", "Tidak diketahui"),
            "certificate": property_data.get("certificate_type", "Belum diketahui"),
        },
        conservative_haircut_pct=float(targets.get("conservative_haircut_pct", 10) or 0),
        optimistic_premium_pct=float(targets.get("optimistic_premium_pct", 10) or 0),
    )

    params = {
        "property": {
            **property_data,
            "occupancy_status": survey.get("occupancy_status", "Belum diketahui"),
            "occupancy_verified": bool(survey.get("occupancy_verified", False)),
            "condition": survey.get("physical_condition", "Tidak diketahui"),
            "interior_inspected": bool(survey.get("interior_inspected", False)),
            "legal_status": property_data.get("legal_status", "Belum terverifikasi"),
        },
        "fees": fees,
        "costs": {**costs, "possession_scenario_data": selected_scenario},
        "finance": finance,
        "market": market,
        "risk_scores": risk_scores,
    }

    bid = float(property_data.get("auction_limit", 0) or 0)
    conservative_exit = float(market.get("conservative_exit") or 0)
    base_exit = float(market.get("base_exit") or 0)
    optimistic_exit = float(market.get("optimistic_exit") or 0)

    conservative_at_limit = calculate_project(params, bid_price=bid, exit_price=conservative_exit)
    base_at_limit = calculate_project(params, bid_price=bid, exit_price=base_exit)
    optimistic_at_limit = calculate_project(params, bid_price=bid, exit_price=optimistic_exit)

    risk_ceiling = property_data.get("risk_adjusted_ceiling")
    risk_ceiling = float(risk_ceiling) if risk_ceiling not in (None, "", 0, "0") else None
    increment = float(property_data.get("bid_increment", 1_000_000) or 1_000_000)

    recommended = find_maximum_bid(
        params, conservative_exit, minimum_bid=bid, increment=increment,
        risk_ceiling=risk_ceiling, require_cash=True,
    ) if conservative_exit > 0 else {"maximum_bid": None, "reason": "Harga exit konservatif belum tersedia."}
    absolute = find_maximum_bid(
        params, base_exit, minimum_bid=bid, increment=increment,
        risk_ceiling=risk_ceiling, require_cash=True,
    ) if base_exit > 0 else {"maximum_bid": None, "reason": "Harga exit base belum tersedia."}

    possession_comparison = compare_possession_scenarios(
        params, bid, base_exit, possession_scenarios, selected_key
    ) if base_exit > 0 and possession_scenarios else {"scenarios": [], "selected": None}
    # Contingent reserves are cash buffers, not assumed expenses in the base case.
    possession_rows = possession_comparison.get("scenarios", [])
    reserve_by_key = {k: float(v.get("reserve_cost", 0) or 0) for k, v in possession_scenarios.items()}
    for row in possession_rows:
        reserve_need = reserve_by_key.get(row.get("scenario_key"), 0.0)
        row["additional_reserve_required"] = reserve_need
        row["cash_exposure_including_reserve"] = float(row.get("cash_investment_before_sale", 0) or 0) + reserve_need
    selected_reserve = reserve_by_key.get(selected_key, 0.0)
    worst_reserve = max(reserve_by_key.values(), default=0.0)
    possession_comparison["selected_reserve_required"] = selected_reserve
    possession_comparison["worst_case_reserve_required"] = worst_reserve
    possession_comparison["worst_case_cash_exposure"] = max(
        (float(row.get("cash_exposure_including_reserve", 0) or 0) for row in possession_rows), default=0.0
    )

    decision = evaluate_decision(
        params,
        conservative_at_limit,
        recommended.get("maximum_bid"),
        absolute.get("maximum_bid"),
        market,
    )
    if worst_reserve > float(investor.get("risk_reserve", 0) or 0):
        decision.setdefault("blockers", []).append(
            f"Cadangan risiko investor ({investor.get('risk_reserve', 0):,.0f}) lebih kecil daripada cadangan tambahan worst-case penguasaan ({worst_reserve:,.0f})."
        )
        decision["status"] = "HOLD"
        decision["summary"] = "Cadangan worst-case penguasaan belum didanai; tambah cadangan risiko atau revisi mitigasi."

    snapshot: dict[str, Any] = {
        "object_id": str(inputs.get("object_id") or uuid.uuid4()),
        "analysis_id": str(uuid.uuid4()),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "property": property_data,
            "survey": survey,
            "fees": fees,
            "costs": costs,
            "targets": targets,
            "risk_scores": risk_scores,
            "finance": finance,
            "comparables": comparables,
            "possession_scenarios": possession_scenarios,
        },
        "investor": investor,
        "market": market,
        "results": {
            "conservative_at_limit": conservative_at_limit,
            "base_at_limit": base_at_limit,
            "optimistic_at_limit": optimistic_at_limit,
            "recommended_max_bid": recommended,
            "absolute_max_bid": absolute,
            "possession_comparison": possession_comparison,
        },
        "decision": decision,
    }
    snapshot["suitability"] = suitability_score(snapshot)
    return snapshot
