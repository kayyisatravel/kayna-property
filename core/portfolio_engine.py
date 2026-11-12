"""Transparent screening score and portfolio ranking; not a probability model."""
from __future__ import annotations
from typing import Any


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def suitability_score(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Calculate a reproducible 0-100 suitability index from Python outputs.

    This is a screening score, not the probability of a successful resale.
    Hard blockers remain decision overrides even when the numeric score is high.
    """
    inputs = snapshot.get("inputs", {})
    results = snapshot.get("results", {})
    market = snapshot.get("market", {})
    decision = snapshot.get("decision", {})
    finance = inputs.get("finance", {})
    calculation = results.get("base_at_limit", {})
    risk = float(decision.get("weighted_risk_score", 3.0) or 3.0)

    target_roi = float(finance.get("minimum_roi_pct", 20) or 0)
    actual_roi = calculation.get("roi_pct")
    if actual_roi is None:
        roi_score = 0.0
    elif target_roi <= 0:
        roi_score = 100.0 if actual_roi >= 0 else 0.0
    else:
        roi_score = _clamp(float(actual_roi) / target_roi * 100)

    target_profit = float(finance.get("minimum_net_profit", 0) or 0)
    actual_profit = float(calculation.get("net_profit", 0) or 0)
    if target_profit <= 0:
        profit_score = 100.0 if actual_profit >= 0 else 0.0
    else:
        profit_score = _clamp(actual_profit / target_profit * 100)

    max_months = float(finance.get("maximum_holding_months", 12) or 12)
    actual_months = float(calculation.get("total_holding_months", 0) or 0)
    time_score = 100.0 if max_months <= 0 and actual_months == 0 else (
        _clamp((1 - actual_months / max_months) * 100) if max_months > 0 else 0.0
    )
    financial_score = 0.60 * roi_score + 0.25 * profit_score + 0.15 * time_score

    risk_score = _clamp((risk - 1.0) / 4.0 * 100)
    required_cash = float(calculation.get("pre_sale_investment", 0) or 0)
    available_cash = float(calculation.get("available_for_project", 0) or 0)
    funding_score = 100.0 if required_cash <= 0 else _clamp(available_cash / required_cash * 100)
    market_score = _clamp(float(market.get("confidence", 0) or 0))

    prop = inputs.get("property", {})
    survey = inputs.get("survey", {})
    fees = inputs.get("fees", {})
    evidence_checks = [
        bool(prop.get("identity_verified")),
        bool(prop.get("title_match")),
        prop.get("legal_status") == "Terverifikasi",
        bool(survey.get("occupancy_verified")),
        bool(fees.get("tax_rules_verified")),
        int(market.get("count", 0) or 0) >= 3,
        bool(survey.get("survey_date")),
        bool(prop.get("auction_url")),
    ]
    evidence_score = sum(evidence_checks) / len(evidence_checks) * 100

    weighted = (
        0.30 * financial_score
        + 0.25 * risk_score
        + 0.20 * funding_score
        + 0.15 * market_score
        + 0.10 * evidence_score
    )
    blockers = decision.get("blockers", []) or []
    # A modest evidence penalty makes missing critical evidence visible, but does
    # not replace the hard-stop status logic in the decision engine.
    weighted = _clamp(weighted - min(25.0, len(blockers) * 3.0))

    return {
        "score_pct": round(weighted, 1),
        "financial_score": round(financial_score, 1),
        "risk_score": round(risk_score, 1),
        "funding_score": round(funding_score, 1),
        "market_score": round(market_score, 1),
        "evidence_score": round(evidence_score, 1),
        "interpretation": "Indeks screening berbobot; bukan probabilitas keberhasilan atau jaminan keuntungan.",
    }


def rank_saved_objects(
    snapshots: list[dict[str, Any]],
    current_investor: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank saved objects; optionally re-run each one against the latest investor cash.

    The GSheets snapshot remains immutable. The returned ranking is a live projection,
    recalculated with today's cash/commitments/reserves when current_investor is supplied.
    """
    priority = {"GO": 0, "CONDITIONAL": 1, "HOLD": 2, "NO-GO": 3}
    ranked = []
    for item in snapshots:
        live_item = item
        if current_investor is not None:
            # Lazy import avoids a module cycle: analysis_engine itself imports suitability_score.
            from .analysis_engine import run_property_analysis
            live_item = run_property_analysis(item.get("inputs", {}), current_investor)
        decision = live_item.get("decision", {})
        suitability = live_item.get("suitability", {}) or suitability_score(live_item)
        bid_levels = live_item.get("results", {}).get("bidding_levels", {}) or {}
        row = {
            "object_id": live_item.get("object_id", ""),
            "name": live_item.get("inputs", {}).get("property", {}).get("name") or live_item.get("inputs", {}).get("property", {}).get("lot_code") or "Objek tanpa nama",
            "lot_code": live_item.get("inputs", {}).get("property", {}).get("lot_code", ""),
            "status": decision.get("status", "HOLD"),
            "score_pct": float(suitability.get("score_pct", 0) or 0),
            "base_roi_pct": live_item.get("results", {}).get("base_at_limit", {}).get("roi_pct"),
            "base_profit": live_item.get("results", {}).get("base_at_limit", {}).get("net_profit"),
            "required_cash": live_item.get("results", {}).get("base_at_limit", {}).get("pre_sale_investment"),
            "available_cash": live_item.get("results", {}).get("base_at_limit", {}).get("available_for_project"),
            "attractive_bid": bid_levels.get("attractive_max_bid"),
            "recommended_bid": bid_levels.get("recommended_ceiling", live_item.get("results", {}).get("recommended_max_bid", {}).get("maximum_bid")),
            "stop_from_bid": bid_levels.get("stop_from_bid"),
            "absolute_max_bid": bid_levels.get("base_case_reference_ceiling", live_item.get("results", {}).get("absolute_max_bid", {}).get("maximum_bid")),
            "market_confidence": live_item.get("market", {}).get("confidence", 0),
            "holding_months": live_item.get("results", {}).get("base_at_limit", {}).get("total_holding_months"),
            "blockers": decision.get("blockers", []),
            "snapshot": live_item,
        }
        ranked.append(row)
    ranked.sort(key=lambda r: (priority.get(r["status"], 9), -r["score_pct"]))
    for idx, row in enumerate(ranked, 1):
        row["rank"] = idx
    return ranked
