from __future__ import annotations
from typing import Any
from .market_engine import assess_comparables
from .calculator import calculate_project
from .maximum_bid import build_bid_tiers
from .decision_engine import evaluate_decision
from .liquidity import evaluate_funding
from .risk_engine import summarize_risks
from .renovation_engine import rab_item_is_in_scope
from .utils import to_float


def run_underwriting(data: dict[str, Any], liquidity: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    prop = data.get("property", {}); survey = data.get("survey", {}); legal = data.get("legal", {}); costs = data.get("costs", {})
    market_subject = {**prop, "access": survey.get("access"), "physical_condition": survey.get("physical_condition")}
    market = assess_comparables(
        data.get("comparables", []), market_subject,
        to_float(rules.get("negotiation_discount_pct", 10)),
        to_float(rules.get("quick_sale_discount_pct", 5)),
        to_float(rules.get("njop_market_weight_pct", 10)),
    )
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
    # Keep calculated ceilings visible for screening, but explicitly mark them
    # provisional whenever core evidence/costs have not been reviewed. A partial
    # RAB can understate capital and overstate ROI even though the decision gate
    # correctly prevents a final GO.
    provisional_reasons: list[str] = []
    if market.get("status") != "READY":
        provisional_reasons.append("data pasar belum memenuhi standar GO-grade")
    elif to_float(market.get("confidence")) < 70:
        provisional_reasons.append("confidence pasar masih di bawah rekomendasi kualitas 70/100")
    if not bool(costs.get("cost_estimates_reviewed", False)):
        provisional_reasons.append("estimasi biaya belum dikonfirmasi pengguna")
    renovation_rows = costs.get("renovation_items", []) or []
    in_scope_rab_unpriced = [
        str(r.get("work_item") or r.get("item_code") or "Pekerjaan dalam anggaran")
        for r in renovation_rows
        if rab_item_is_in_scope(r)
        and (r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, ""))
    ]
    required_rab_unpriced = [
        str(r.get("work_item") or r.get("item_code") or "Pekerjaan wajib")
        for r in renovation_rows
        if str(r.get("priority") or "").lower() == "wajib"
        and (r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, ""))
    ]
    if in_scope_rab_unpriced:
        provisional_reasons.append("RAB wajib belum lengkap / item anggaran dasar belum lengkap: " + "; ".join(in_scope_rab_unpriced[:4]))
    if not bool(data.get("risk_reviewed", False)):
        provisional_reasons.append("risk register belum ditinjau pengguna")
    if not bool(legal.get("identity_verified", False)):
        provisional_reasons.append("identitas objek/legalitas belum diverifikasi")
    if not bool(legal.get("tax_rules_verified", False)):
        provisional_reasons.append("tarif pajak/biaya transaksi belum diverifikasi")
    if not tiers.get("increment_confirmed"):
        provisional_reasons.append("kelipatan bid resmi belum dikonfirmasi")
    tiers["provisional"] = bool(provisional_reasons)
    tiers["provisional_reasons"] = provisional_reasons
    tiers["required_rab_unpriced"] = required_rab_unpriced
    tiers["in_scope_rab_unpriced"] = in_scope_rab_unpriced
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
