from __future__ import annotations
from typing import Any
from .market_engine import assess_comparables
from .calculator import calculate_project
from .maximum_bid import build_bid_tiers, calculate_rule_of_thumb_mao
from .decision_engine import evaluate_decision
from .liquidity import evaluate_funding
from .risk_engine import summarize_risks
from .feasibility import build_feasibility_scenarios
from .renovation_engine import rab_item_is_in_scope
from .utils import to_float


def _subject_condition_bucket(physical_condition: Any, property_type: Any = "") -> str | None:
    """Map survey wording to the comparable-engine's controlled condition buckets."""
    text = str(physical_condition or "").strip().lower()
    property_kind = str(property_type or "").strip().lower()
    if "tanah kosong" in property_kind or "hitung tanah" in text:
        return "Hitung Tanah"
    if "siap huni" in text or "kosmetik" in text:
        # Cosmetic-only work is grouped with ready-to-move stock for market
        # matching; medium/heavy/light renovation remains in the renovation bucket.
        return "Siap Huni"
    if any(token in text for token in ("renovasi", "butuh perbaikan", "perlu perbaikan")):
        return "Butuh Renovasi"
    return None


def _market_estimate_summary(result: dict[str, Any], condition_bucket: str | None, owner_value: float | None = None) -> dict[str, Any]:
    count = int(to_float(result.get("valuation_comparable_count")))
    confidence = to_float(result.get("confidence"))
    sample_value = result.get("base_exit")
    sample_conservative = result.get("conservative_exit")
    has_owner_value = owner_value is not None and to_float(owner_value) > 0
    indicative_value = sample_value if sample_value is not None else (to_float(owner_value) if has_owner_value else None)
    indicative_conservative = sample_conservative if sample_conservative is not None else (to_float(owner_value) * 0.95 if has_owner_value else None)
    validated = count >= 3 and confidence >= 45 and not has_owner_value
    return {
        "condition_bucket": condition_bucket,
        "value": indicative_value if validated else None,
        "indicative_value": indicative_value,
        "conservative_value": indicative_conservative if validated else None,
        "indicative_conservative_value": indicative_conservative,
        "comparable_count": count,
        "go_grade_count": int(to_float(result.get("go_grade_count"))),
        "confidence": confidence,
        "status": "VALIDATED" if validated else "OWNER_INPUT" if has_owner_value and count == 0 else "PROVISIONAL" if count > 0 or has_owner_value else "NO_DATA",
        "valuation_mode": result.get("valuation_mode"),
        "source": "Owner estimate" if has_owner_value and count == 0 else "Condition-matched comparables",
        "sample_is_sufficient_for_conditional": count >= 3 and confidence >= 45,
    }


def run_underwriting(data: dict[str, Any], liquidity: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    prop = data.get("property", {}); survey = data.get("survey", {}); legal = data.get("legal", {}); costs = data.get("costs", {})
    comparables = list(data.get("comparables", []) or [])
    current_condition = _subject_condition_bucket(survey.get("physical_condition"), prop.get("property_type"))
    is_land_only = current_condition == "Hitung Tanah" or str(prop.get("property_type") or "").strip().lower() == "tanah kosong"
    exit_condition = "Hitung Tanah" if is_land_only else "Siap Huni"
    market_kwargs = (
        to_float(rules.get("negotiation_discount_pct", 10)),
        to_float(rules.get("quick_sale_discount_pct", 5)),
        to_float(rules.get("njop_market_weight_pct", 10)),
    )

    # The financial exit model is based on comparable properties in the intended
    # post-renovation condition (normally Siap Huni). Current/as-is value is
    # calculated separately from comparables matching the surveyed condition.
    exit_comparables = [
        row for row in comparables
        if str(row.get("condition") or "").strip().lower() == exit_condition.lower()
    ]
    market_subject_exit = {
        **prop,
        "access": survey.get("access"),
        "physical_condition": "Hitung tanah" if is_land_only else "Siap huni",
    }
    market_condition_matched = assess_comparables(exit_comparables, market_subject_exit, *market_kwargs)
    mixed_pool_diagnostic = assess_comparables(comparables, market_subject_exit, *market_kwargs) if comparables else None
    owner_valuation = data.get("owner_valuation", {}) or {}
    owner_arv = to_float(owner_valuation.get("arv_estimate")) or None
    owner_fmv = to_float(owner_valuation.get("fmv_as_is_estimate")) or None
    # Never silently mix unlike condition buckets into the post-renovation exit.
    # A small matched sample remains visible as provisional; if none exists, an
    # explicit Owner estimate may be used and is clearly labelled as such.
    if int(to_float(market_condition_matched.get("valuation_comparable_count"))) > 0:
        market = dict(market_condition_matched)
        exit_value_source = "condition_matched_comparables"
    elif owner_arv:
        market = dict(market_condition_matched)
        market.update({
            "base_exit": round(owner_arv),
            "conservative_exit": round(owner_arv * (1 - to_float(rules.get("quick_sale_discount_pct", 5)) / 100)),
            "optimistic_exit": round(owner_arv * 1.05),
            "market_range_low": round(owner_arv * 0.80),
            "market_range_high": round(owner_arv * 1.10),
            "confidence": min(35.0, to_float(market_condition_matched.get("confidence"))),
            "estimate_label": "Estimasi ARV dari Owner — belum diverifikasi pembanding",
        })
        exit_value_source = "owner_estimate"
    else:
        market = dict(market_condition_matched)
        exit_value_source = "unavailable"
    if mixed_pool_diagnostic:
        market["mixed_pool_diagnostic"] = {
            "base_exit": mixed_pool_diagnostic.get("base_exit"),
            "conservative_exit": mixed_pool_diagnostic.get("conservative_exit"),
            "valid_count": mixed_pool_diagnostic.get("valuation_comparable_count"),
            "confidence": mixed_pool_diagnostic.get("confidence"),
            "note": "Diagnostik gabungan seluruh bucket saja; tidak digunakan sebagai ARV/MAO karena kondisi exit tidak seragam.",
        }

    as_is_comparables = [
        row for row in comparables
        if current_condition and str(row.get("condition") or "").strip().lower() == current_condition.lower()
    ]
    if current_condition == exit_condition:
        # Use the explicit condition-matched assessment, not `market`, which
        # may be a mixed-condition fallback used only for partial diagnostics.
        market_as_is = market_condition_matched
    elif current_condition:
        market_subject_as_is = {
            **prop,
            "access": survey.get("access"),
            "physical_condition": current_condition,
        }
        market_as_is = assess_comparables(as_is_comparables, market_subject_as_is, *market_kwargs)
    else:
        market_as_is = {
            "base_exit": None, "conservative_exit": None,
            "valuation_comparable_count": 0, "go_grade_count": 0,
            "confidence": 0, "status": "INSUFFICIENT_DATA",
            "valuation_mode": None,
        }

    market["comparable_pool_count"] = len(comparables)
    market["arv_condition_bucket"] = exit_condition
    market["arv_condition_comparable_count"] = int(to_float(market_condition_matched.get("valuation_comparable_count")))
    market["arv_condition_confidence"] = to_float(market_condition_matched.get("confidence"))
    market["arv_after_repair"] = (
        None if is_land_only else _market_estimate_summary(
            market_condition_matched, exit_condition,
            owner_arv if int(to_float(market_condition_matched.get("valuation_comparable_count"))) == 0 else None,
        )
    )
    market["land_exit_value"] = (
        _market_estimate_summary(
            market_condition_matched, exit_condition,
            owner_arv if int(to_float(market_condition_matched.get("valuation_comparable_count"))) == 0 else None,
        ) if is_land_only else None
    )
    market["fmv_as_is"] = _market_estimate_summary(
        market_as_is, current_condition,
        owner_fmv if int(to_float(market_as_is.get("valuation_comparable_count"))) == 0 else None,
    )
    market["exit_value_source"] = exit_value_source
    market["owner_arv_estimate"] = owner_arv
    market["valuation_is_provisional"] = (
        int(to_float(market_condition_matched.get("valuation_comparable_count"))) < 3
        or to_float(market_condition_matched.get("confidence")) < 45
        or exit_value_source == "owner_estimate"
    )
    market["limit_to_fmv_as_is_pct"] = None
    fmv_summary = market.get("fmv_as_is") or {}
    fmv_as_is_value = to_float(fmv_summary.get("value") or fmv_summary.get("indicative_value"))
    auction_limit = to_float(prop.get("auction_limit"))
    if fmv_as_is_value > 0 and auction_limit > 0:
        market["limit_to_fmv_as_is_pct"] = round(auction_limit / fmv_as_is_value * 100, 1)
    # Final GO-grade status is based only on condition-matched exit comparables.
    matched_go_grade = int(to_float(market_condition_matched.get("go_grade_count")))
    matched_confidence = to_float(market_condition_matched.get("confidence"))
    market["go_grade_count"] = matched_go_grade
    market["confidence"] = matched_confidence
    market["confidence_band"] = "Baik" if matched_confidence >= 70 else "Cukup" if matched_confidence >= 55 else "Rendah"
    market["status"] = (
        "READY"
        if market["arv_condition_comparable_count"] >= 5 and matched_go_grade >= 5 and matched_confidence >= 55
        else "PRELIMINARY"
    )
    condition_note = (
        f"ARV exit memakai {len(exit_comparables)} listing dengan kondisi '{exit_condition}'. "
        f"FMV as-is memakai {len(as_is_comparables)} listing dengan kondisi '{current_condition or 'belum terklasifikasi'}'."
    )
    market.setdefault("quality_notes", []).append(condition_note)
    if len(exit_comparables) != len(comparables):
        market["quality_notes"].append(
            f"{len(comparables) - len(exit_comparables)} listing di luar bucket kondisi exit tidak dicampurkan ke ARV setelah renovasi."
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
    tiers = build_bid_tiers(
        limit, increment, to_float(conservative_exit), to_float(base_exit),
        calculation_inputs, None,
        to_float(rules.get("minimum_roi_pct", 20)),
        to_float(rules.get("mid_roi_pct", 30)),
        to_float(prop.get("risk_adjusted_ceiling")) or None,
        to_float(rules.get("bid_simulation_step", 1_000)),
        optimistic_exit=market.get("optimistic_exit"),
        minimum_net_profit=to_float(rules.get("minimum_net_profit", 50_000_000)),
        maximum_holding_days=to_float(rules.get("maximum_holding_days", 180)),
        conditional_maximum_holding_days=to_float(rules.get("conditional_maximum_holding_days", 365)),
        go_minimum_roi_pct=to_float(rules.get("go_minimum_roi_pct", 25)),
    )
    funding = evaluate_funding(to_float(at_limit.get("cash_requirement_including_reserve")), to_float(prop.get("deposit_amount")), liquidity)
    market_exit_valid = bool(conservative_exit and to_float(conservative_exit) > 0) and (
        int(to_float(market.get("arv_condition_comparable_count"))) >= 1 or exit_value_source == "owner_estimate"
    )
    market_exit_strong = (
        int(to_float(market.get("arv_condition_comparable_count"))) >= 3
        and to_float(market.get("arv_condition_confidence")) >= 45
    )
    # Do not classify an opportunity as structurally uneconomic from a
    # mixed-condition/low-sample proxy. Zero-bid economics are a hard stop only
    # when the exit valuation itself has adequate condition-matched evidence.
    no_bid_case = calculate_project(0.0, conservative_exit, calculation_inputs) if conservative_exit and market_exit_strong else {}
    # Pass the exact rules snapshot into the decision engine. Previously these
    # thresholds silently fell back to defaults because `rules` was omitted.
    decision_inputs = {
        **data,
        "rules": rules,
        "risk_summary": risk_summary,
        "finance": {**liquidity, "cash_confirmed": bool(liquidity.get("cash_confirmed"))},
    }
    decision = evaluate_decision(decision_inputs, market, tiers, at_limit, no_bid_case=no_bid_case)
    arv_summary = market.get("arv_after_repair") or {}
    if is_land_only:
        # Land-only exits use the condition-matched land valuation, not a house ARV.
        quick_sale_value_for_mao = conservative_exit if market_exit_valid else None
    else:
        quick_sale_value_for_mao = arv_summary.get("indicative_conservative_value")
    mao_rule_of_thumb = calculate_rule_of_thumb_mao(
        to_float(quick_sale_value_for_mao), calculation_inputs,
        to_float(rules.get("mao_rule_of_thumb_pct", 70.0)),
    )
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
    mao_full_cost = tiers.get("max_bid") if market_exit_valid else None
    if mao_full_cost is None and market_exit_valid:
        mao_full_cost = tiers.get("max_simulated_ceiling") or tiers.get("max_economic_ceiling")
    mao_go_full_cost = tiers.get("go_bid") if market_exit_valid else None
    if mao_go_full_cost is None and market_exit_valid:
        mao_go_full_cost = tiers.get("go_simulated_ceiling") or tiers.get("go_economic_ceiling")
    mao_target_roi_bid = tiers.get("mid_bid") if market_exit_valid else None
    if mao_target_roi_bid is None and market_exit_valid:
        mao_target_roi_bid = tiers.get("mid_simulated_ceiling") or tiers.get("mid_economic_ceiling")
    decision["mao_full_cost"] = mao_full_cost
    decision["mao_go_full_cost"] = mao_go_full_cost
    decision["mao_rule_of_thumb"] = mao_rule_of_thumb.get("mao")
    scenario_settings = data.get("scenario_settings", {}) or {}
    feasibility_scenarios = build_feasibility_scenarios(
        limit, conservative_exit, base_exit, calculation_inputs,
        stress_holding_months=to_float(scenario_settings.get("stress_holding_months", 12), 12),
        stress_sale_discount_pct=to_float(scenario_settings.get("stress_sale_discount_pct", 10), 10),
        stress_extra_cost=to_float(scenario_settings.get("stress_extra_cost", 0)),
    )
    return {
        "market": market,
        "at_limit": at_limit,
        "bidding": tiers,
        "funding": funding,
        "risk_summary": risk_summary,
        "risk_register": risk_summary["items"],
        "decision": decision,
        "eligibility_index_pct": index,
        "calculation_inputs": calculation_inputs,
        "feasibility_scenarios": feasibility_scenarios,
        "mao": {
            "rule_of_thumb": mao_rule_of_thumb,
            "is_provisional": bool(market.get("valuation_is_provisional") or not costs.get("cost_estimates_reviewed", False)),
            "full_cost": mao_full_cost,
            "go_full_cost": mao_go_full_cost,
            "target_roi_bid": mao_target_roi_bid,
            "full_cost_roi_floor_pct": to_float(rules.get("minimum_roi_pct", 15.0)),
            "go_roi_floor_pct": to_float(rules.get("go_minimum_roi_pct", 25.0)),
            "full_cost_minimum_profit": to_float(rules.get("minimum_net_profit", 50_000_000.0)),
        },
    }
