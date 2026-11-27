"""Pure Python project cost, ROI, and bid calculations."""
from __future__ import annotations
from typing import Any
from .utils import to_float


def bphtb_basis(bid_price: float, njop: float, mode: str = "max_bid_or_njop") -> float:
    if mode == "bid_only": return bid_price
    if mode == "njop_only": return njop
    return max(bid_price, njop)


def calculate_project(bid_price: float, exit_price: float, inputs: dict[str, Any]) -> dict[str, Any]:
    p = max(0.0, to_float(bid_price))
    # Missing ARV must not be treated as an actual selling price of zero.
    sale = None if exit_price is None or str(exit_price).strip() == "" else max(0.0, to_float(exit_price))
    rules = inputs.get("rules", {}); costs = inputs.get("costs", {}); survey = inputs.get("survey", {}); prop = inputs.get("property", {})
    buyer_fee = p * to_float(rules.get("buyer_auction_fee_pct", 2)) / 100
    bphtb_base = bphtb_basis(p, to_float(prop.get("njop")), str(rules.get("bphtb_basis_mode", "max_bid_or_njop")))
    npoptkp = to_float(rules.get("npoptkp", 80_000_000)) if prop.get("npoptkp_eligible", False) else 0.0
    bphtb = max(0.0, bphtb_base - npoptkp) * to_float(rules.get("bphtb_rate_pct", 5)) / 100
    def configured_cost(key: str, default: float = 0.0) -> float:
        # Per-property estimate overrides the global rule only when explicitly supplied.
        value = costs.get(key)
        if value is None or value == "":
            value = rules.get(key, default)
        return max(0.0, to_float(value, default))

    # BPN PNBP, roya and admin defaults are stored in RULES_CONFIG; a per-property
    # value can override them. Acquisition notary/PPAT is zero by default because
    # the investor handles the BPN process independently.
    legal_breakdown = {
        "bpn_pnbp_cost": configured_cost("bpn_pnbp_cost"),
        "roya_cost": configured_cost("roya_cost"),
        "other_acquisition_admin": configured_cost("other_acquisition_admin"),
        "other_legal_cost": configured_cost("other_legal_cost"),
        "acquisition_notary_ppat_fee": configured_cost("acquisition_notary_ppat_fee", 0.0),
    }
    legal = sum(legal_breakdown.values())
    possession = to_float(survey.get("possession_cost"))
    # Unmeasured work is never treated as zero: the Owner may enter an explicit
    # allowance when access prevents a complete BoQ/inspection.
    unverified_scope_allowance = max(0.0, to_float(costs.get("unverified_scope_allowance")))
    renovation_base = max(0.0, to_float(costs.get("renovation_cost")))
    renovation = renovation_base + unverified_scope_allowance
    contingency = renovation * to_float(costs.get("renovation_contingency_pct", rules.get("renovation_contingency_pct", 15))) / 100
    reserve_default = rules.get("hidden_condition_reserve_pct", 7.5)
    hidden_condition_reserve_pct = max(0.0, to_float(costs.get("hidden_condition_reserve_pct", reserve_default)))
    # Additional uncertainty buffer for hidden interior/MEP conditions. This is
    # not a claim that hidden damage exists; it is a separate investor reserve.
    hidden_condition_reserve_amount = max(0.0, to_float(costs.get("hidden_condition_reserve_amount")))
    hidden_condition_reserve = (
        hidden_condition_reserve_amount
        if survey.get("interior_inspected") is False and hidden_condition_reserve_amount > 0
        else renovation * hidden_condition_reserve_pct / 100
        if survey.get("interior_inspected") is False else 0.0
    )
    # Underwriting uses a conservative sequential phase estimate from the
    # post-win/settlement project phases through sale closing. The actual
    # auction-deposit cashflow date is tracked separately for XIRR. One planning
    # month is standardized as 30 calendar days for the 90/180-day policy.
    hold_months = sum(to_float(v) for v in [survey.get("possession_months"), costs.get("legal_delay_months"), costs.get("renovation_months"), costs.get("selling_months")])
    projected_holding_days = int(round(hold_months * 30.0))
    target_holding_days = int(to_float(rules.get("target_holding_days", 90), 90))
    maximum_holding_days = int(to_float(rules.get("maximum_holding_days", 180), 180))
    holding = hold_months * to_float(costs.get("monthly_holding_cost", rules.get("monthly_holding_cost", 1_000_000)))
    other_before_sale = to_float(costs.get("other_presale_cost")) + to_float(costs.get("marketing_cost"))
    acquisition = p + buyer_fee + bphtb + legal
    capital_before_sale = acquisition + possession + renovation + contingency + hidden_condition_reserve + holding + other_before_sale
    possession_risk_reserve = max(0.0, to_float(survey.get("possession_risk_reserve")))
    general_risk_reserve = max(0.0, to_float(survey.get("general_risk_reserve")))
    cash_requirement_including_reserve = capital_before_sale + possession_risk_reserve + general_risk_reserve
    if sale is None:
        pph = agent = ajb = misc = selling = net_proceeds = profit = roi = annualized = None
    else:
        pph = sale * to_float(rules.get("seller_final_tax_pct", 2.5)) / 100
        agent = sale * to_float(rules.get("seller_agent_pct", 2.5)) / 100
        ajb = sale * to_float(rules.get("seller_ajb_ppat_pct", 1.0)) / 100
        misc = to_float(rules.get("seller_misc_fixed", 5_000_000))
        selling = pph + agent + ajb + misc
        net_proceeds = sale - selling
        profit = net_proceeds - capital_before_sale
        total_cost_including_selling = capital_before_sale + selling
        # Net project ROI uses the complete cost base, including taxes and
        # transaction expenses paid at sale. Keep the pre-sale-capital ratio as
        # a separate diagnostic so older comparisons remain explainable.
        roi_pre_sale_capital = (profit / capital_before_sale * 100) if capital_before_sale > 0 else None
        roi = (profit / total_cost_including_selling * 100) if total_cost_including_selling > 0 else None
        annualized = ((1 + roi / 100) ** (12 / hold_months) - 1) * 100 if roi is not None and roi > -100 and hold_months > 0 else None
    if sale is None:
        total_cost_including_selling = None
        roi_pre_sale_capital = None
    return {
        "bid_price": p, "exit_price": sale, "buyer_auction_fee": buyer_fee, "bphtb_basis": bphtb_base, "bphtb": bphtb,
        "legal_bpn_cost": legal, **legal_breakdown,
        "acquisition_cost": acquisition, "possession_cost": possession, "renovation_cost": renovation,
        "renovation_base_cost": renovation_base, "unverified_scope_allowance": unverified_scope_allowance,
        "renovation_contingency": contingency, "hidden_condition_reserve": hidden_condition_reserve,
        "hidden_condition_reserve_amount_input": hidden_condition_reserve_amount,
        "hidden_condition_reserve_pct": hidden_condition_reserve_pct if survey.get("interior_inspected") is False else 0.0,
        "holding_months": hold_months, "projected_holding_days": projected_holding_days,
        "target_holding_days": target_holding_days, "maximum_holding_days": maximum_holding_days,
        "within_target_holding_period": projected_holding_days <= target_holding_days if projected_holding_days > 0 else None,
        "within_maximum_holding_period": projected_holding_days <= maximum_holding_days if projected_holding_days > 0 else None,
        "holding_cost": holding,
        "other_presale_cost": other_before_sale, "capital_before_sale": capital_before_sale,
        "possession_risk_reserve": possession_risk_reserve, "general_risk_reserve": general_risk_reserve,
        "cash_requirement_including_reserve": cash_requirement_including_reserve,
        "seller_final_tax": pph, "seller_agent": agent, "seller_ajb_ppat": ajb, "seller_misc": misc,
        "selling_cost": selling, "net_proceeds": net_proceeds, "net_profit": profit, "roi_pct": roi,
        "roi_pre_sale_capital_pct": roi_pre_sale_capital,
        "annualized_roi_pct": annualized, "total_cost_including_selling": capital_before_sale + selling if selling is not None else None,
        "marketing_cost": max(0.0, to_float(costs.get("marketing_cost"))),
        "other_presale_cost_only": max(0.0, to_float(costs.get("other_presale_cost"))),
        "possession_risk_reserve": possession_risk_reserve,
        "general_risk_reserve": general_risk_reserve,
    }
