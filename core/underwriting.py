from __future__ import annotations
from typing import Any
from .market_engine import assess_comparables
from .calculator import calculate_project
from .maximum_bid import build_bid_tiers
from .decision_engine import evaluate_decision
from .liquidity import evaluate_funding
from .risk_engine import summarize_risks
from .utils import to_float


def run_underwriting(data: dict[str, Any], liquidity: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    prop = data.get("property", {}); survey = data.get("survey", {}); legal = data.get("legal", {}); costs = data.get("costs", {})
    market_subject = {**prop, "access": survey.get("access"), "physical_condition": survey.get("physical_condition")}
    market = assess_comparables(data.get("comparables", []), market_subject, to_float(rules.get("negotiation_discount_pct", 10)), to_float(rules.get("quick_sale_discount_pct", 5)))
    risk_summary = summarize_risks(data.get("risk_register", []))
    survey_for_calculation = {**survey, "general_risk_reserve": risk_summary["total_cash_reserve"]}
    calculation_inputs = {"property": prop, "survey": survey_for_calculation, "legal": legal, "costs": costs, "rules": rules, "finance": liquidity}
    limit = to_float(prop.get("auction_limit")); increment = to_float(prop.get("bid_increment")) or None
    cash_available = to_float(liquidity.get("cash_available_for_new_project"))
    conservative_exit = market.get("conservative_exit")
    base_exit = market.get("base_exit")
    # Always calculate acquisition/project costs at the auction limit when known,
    # even if ARV is not yet available. Missing ARV yields null profit/ROI, not a
    # fabricated zero selling price or a false financial rejection.
    at_limit = calculate_project(limit, conservative_exit, calculation_inputs) if limit > 0 else {}
    tiers = build_bid_tiers(limit, increment, to_float(conservative_exit), to_float(base_exit), calculation_inputs, None, to_float(rules.get("minimum_roi_pct", 25)), to_float(rules.get("mid_roi_pct", 35)), to_float(prop.get("risk_adjusted_ceiling")) or None, to_float(rules.get("bid_simulation_step", 1_000)))
    funding = evaluate_funding(to_float(at_limit.get("cash_requirement_including_reserve")), to_float(prop.get("deposit_amount")), liquidity)
    decision_inputs = {**data, "risk_summary": risk_summary, "finance": {**liquidity, "cash_confirmed": bool(liquidity.get("cash_confirmed"))}}
    decision = evaluate_decision(decision_inputs, market, tiers, at_limit)
    # Suitability index is a transparent screening index, not probability of profit.
    roi = to_float(at_limit.get("roi_pct"), -100)
    financial_score = max(0, min(100, (roi / max(1, to_float(rules.get("minimum_roi_pct", 25)) * 1.5)) * 100))
    market_score = to_float(market.get("confidence"))
    legal_score = 100 if legal.get("identity_verified") and not legal.get("dispute_detected") else 25
    survey_score = 100 if survey.get("survey_status") and survey.get("survey_status") != "Belum Survei" else 10
    funding_score = 100 if funding.get("full_project_funded") else max(0, min(100, cash_available / max(1, to_float(at_limit.get("capital_before_sale"))) * 100))
    risk_score_pct = max(0.0, 100.0 - 4.0 * to_float(risk_summary.get("maximum_severity")))
    index = round(0.25 * financial_score + 0.15 * market_score + 0.15 * legal_score + 0.10 * survey_score + 0.20 * funding_score + 0.15 * risk_score_pct, 1)
    return {"market": market, "at_limit": at_limit, "bidding": tiers, "funding": funding, "risk_summary": risk_summary, "risk_register": risk_summary["items"], "decision": decision, "eligibility_index_pct": index, "calculation_inputs": calculation_inputs}
