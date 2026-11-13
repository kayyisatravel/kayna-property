"""Pure Python project cost, ROI, and bid calculations."""
from __future__ import annotations
from typing import Any
from .utils import to_float


def bphtb_basis(bid_price: float, njop: float, mode: str = "max_bid_or_njop") -> float:
    if mode == "bid_only": return bid_price
    if mode == "njop_only": return njop
    return max(bid_price, njop)


def calculate_project(bid_price: float, exit_price: float, inputs: dict[str, Any]) -> dict[str, Any]:
    p = max(0.0, to_float(bid_price)); sale = max(0.0, to_float(exit_price))
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
    legal = sum(configured_cost(k) for k in ["bpn_pnbp_cost", "roya_cost", "other_acquisition_admin", "other_legal_cost"])
    legal += configured_cost("acquisition_notary_ppat_fee", 0.0)
    possession = to_float(survey.get("possession_cost"))
    renovation = to_float(costs.get("renovation_cost"))
    contingency = renovation * to_float(rules.get("renovation_contingency_pct", 15)) / 100
    hold_months = sum(to_float(v) for v in [survey.get("possession_months"), costs.get("legal_delay_months"), costs.get("renovation_months"), costs.get("selling_months")])
    holding = hold_months * to_float(costs.get("monthly_holding_cost", rules.get("monthly_holding_cost", 1_000_000)))
    other_before_sale = to_float(costs.get("other_presale_cost")) + to_float(costs.get("marketing_cost"))
    acquisition = p + buyer_fee + bphtb + legal
    capital_before_sale = acquisition + possession + renovation + contingency + holding + other_before_sale
    possession_risk_reserve = max(0.0, to_float(survey.get("possession_risk_reserve")))
    general_risk_reserve = max(0.0, to_float(survey.get("general_risk_reserve")))
    cash_requirement_including_reserve = capital_before_sale + possession_risk_reserve + general_risk_reserve
    pph = sale * to_float(rules.get("seller_final_tax_pct", 2.5)) / 100
    agent = sale * to_float(rules.get("seller_agent_pct", 2.5)) / 100
    ajb = sale * to_float(rules.get("seller_ajb_ppat_pct", 1.0)) / 100
    misc = to_float(rules.get("seller_misc_fixed", 5_000_000))
    selling = pph + agent + ajb + misc
    net_proceeds = sale - selling
    profit = net_proceeds - capital_before_sale
    roi = (profit / capital_before_sale * 100) if capital_before_sale > 0 else None
    annualized = ((1 + roi / 100) ** (12 / hold_months) - 1) * 100 if roi is not None and roi > -100 and hold_months > 0 else None
    return {
        "bid_price": p, "exit_price": sale, "buyer_auction_fee": buyer_fee, "bphtb_basis": bphtb_base, "bphtb": bphtb,
        "legal_bpn_cost": legal, "acquisition_cost": acquisition, "possession_cost": possession, "renovation_cost": renovation,
        "renovation_contingency": contingency, "holding_months": hold_months, "holding_cost": holding,
        "other_presale_cost": other_before_sale, "capital_before_sale": capital_before_sale,
        "possession_risk_reserve": possession_risk_reserve, "general_risk_reserve": general_risk_reserve,
        "cash_requirement_including_reserve": cash_requirement_including_reserve,
        "seller_final_tax": pph, "seller_agent": agent, "seller_ajb_ppat": ajb, "seller_misc": misc,
        "selling_cost": selling, "net_proceeds": net_proceeds, "net_profit": profit, "roi_pct": roi,
        "annualized_roi_pct": annualized, "total_cost_including_selling": capital_before_sale + selling,
    }
