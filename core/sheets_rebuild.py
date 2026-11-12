"""Convert editable Google Sheets rows back into the input object for re-analysis."""
from __future__ import annotations
from typing import Any


def _b(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "ya", "y"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (ValueError, TypeError):
        return default


def rebuild_inputs_from_sheets(object_row: dict[str, Any], survey_row: dict[str, Any], cost_row: dict[str, Any], comp_rows: list[dict[str, Any]], scenario_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Builds analysis inputs using editable columns, so sheet corrections are applied."""
    property_fields = [
        "object_id", "lot_code", "auction_office", "seller", "auction_type", "auction_date", "auction_time", "deposit_deadline", "payment_deadline", "auction_url", "auction_object_description",
        "name", "complex_name", "address", "district", "province", "auction_limit", "deposit_amount",
        "bid_increment", "njop", "certificate_type", "certificate_no", "rights_expiry", "land_area", "building_area",
        "bedrooms", "bathrooms", "property_type", "legal_status", "identity_verified", "title_match",
        "dispute_detected", "property_notes", "risk_adjusted_ceiling",
    ]
    property_data = {k: object_row.get(k, "") for k in property_fields}
    for key in ("auction_limit", "deposit_amount", "bid_increment", "njop", "land_area", "building_area", "bedrooms", "bathrooms", "risk_adjusted_ceiling"):
        property_data[key] = _f(property_data.get(key))
    for key in ("identity_verified", "title_match", "dispute_detected"):
        property_data[key] = _b(property_data.get(key))

    survey_fields = ["survey_date", "surveyor", "occupancy_status", "occupancy_verified", "physical_condition",
                     "exterior_inspected", "interior_inspected", "road_width_m", "access_type", "flood_history",
                     "structure", "roof", "damp", "electricity", "water", "physical_notes", "photo_links"]
    survey = {k: survey_row.get(k, "") for k in survey_fields}
    for key in ("occupancy_verified", "exterior_inspected", "interior_inspected"):
        survey[key] = _b(survey.get(key))
    survey["road_width_m"] = _f(survey.get("road_width_m"))

    fees = {
        "buyer_auction_fee_pct": _f(cost_row.get("buyer_auction_fee_pct")),
        "bphtb_rate_pct": _f(cost_row.get("bphtb_rate_pct")),
        "npoptkp": _f(cost_row.get("npoptkp")),
        "bphtb_basis_mode": cost_row.get("bphtb_basis_mode", "Harga bid"),
        "ppn_applicable": _b(cost_row.get("ppn_applicable")),
        "ppn_rate_pct": _f(cost_row.get("ppn_rate_pct")),
        "seller_tax_pct": _f(cost_row.get("seller_tax_pct")),
        "selling_agent_pct": _f(cost_row.get("selling_agent_pct")),
        "tax_rules_verified": _b(cost_row.get("tax_rules_verified")),
    }
    costs = {
        "certificate_legal_cost": _f(cost_row.get("certificate_legal_cost")),
        "renovation_cost": _f(cost_row.get("renovation_cost")),
        "arrears_utilities_cost": _f(cost_row.get("arrears_utilities_cost")),
        "selected_possession_scenario": cost_row.get("selected_possession_scenario", "KOSONG"),
        "monthly_holding_cost": _f(cost_row.get("monthly_holding_cost")),
        "renovation_months": _f(cost_row.get("renovation_months"), 2),
        "sale_months_after_ready": _f(cost_row.get("sale_months_after_ready"), 3),
        "contingency_pct": _f(cost_row.get("contingency_pct"), 10),
        "marketing_cost": _f(cost_row.get("marketing_cost")),
        "other_presale_cost": _f(cost_row.get("other_presale_cost")),
        "other_selling_cost": _f(cost_row.get("other_selling_cost")),
    }
    targets = {
        "minimum_net_profit": _f(cost_row.get("minimum_net_profit")),
        "minimum_roi_pct": _f(cost_row.get("minimum_roi_pct"), 20),
        "minimum_profit_per_month": _f(cost_row.get("minimum_profit_per_month")),
        "maximum_holding_months": _f(cost_row.get("maximum_holding_months"), 12),
        "annual_opportunity_cost_pct": _f(cost_row.get("annual_opportunity_cost_pct")),
        "conservative_haircut_pct": _f(cost_row.get("conservative_haircut_pct"), 10),
        "optimistic_premium_pct": _f(cost_row.get("optimistic_premium_pct"), 10),
    }
    risk_scores = {
        "liquidity": int(_f(cost_row.get("score_liquidity"), 3)),
        "legal": int(_f(cost_row.get("score_legal"), 3)),
        "possession": int(_f(cost_row.get("score_possession"), 3)),
        "physical": int(_f(cost_row.get("score_physical"), 3)),
        "funding": int(_f(cost_row.get("score_funding"), 3)),
        "environment": int(_f(cost_row.get("score_environment"), 3)),
    }
    comparables = []
    for row in comp_rows:
        if str(row.get("active", "TRUE")).strip().upper() not in {"TRUE", "1", "YA"}:
            continue
        comparables.append({
            "complex": row.get("complex", ""), "address": row.get("address", ""),
            "distance_km": _f(row.get("distance_km")), "land_area": _f(row.get("land_area")),
            "building_area": _f(row.get("building_area")), "price": _f(row.get("price")),
            "price_type": row.get("price_type", "Listing aktif"), "condition": row.get("condition", "Tidak diketahui"),
            "property_type": row.get("property_type", "Tidak diketahui"), "certificate": row.get("certificate", "Tidak diketahui"),
            "date_found": row.get("date_found", ""), "source_url": row.get("source_url", ""),
        })
    scenarios = {}
    for row in scenario_rows:
        key = str(row.get("scenario_key", "")).strip()
        if not key:
            continue
        scenarios[key] = {
            "label": row.get("label", key), "cost": _f(row.get("expected_cost")),
            "delay_months": _f(row.get("delay_months")), "reserve_cost": _f(row.get("reserve_cost")),
        }

    return {
        "object_id": object_row.get("object_id", ""),
        "property": property_data, "survey": survey, "fees": fees, "costs": costs,
        "targets": targets, "risk_scores": risk_scores, "comparables": comparables,
        "possession_scenarios": scenarios,
    }
