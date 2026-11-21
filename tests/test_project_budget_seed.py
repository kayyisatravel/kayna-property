from core.project_budget_seed import build_opening_budget_from_analysis


def test_opening_budget_uses_winning_price_and_reconciles_to_python_project_capital():
    snapshot = {
        "analysis_id": "ANL-TEST",
        "analyzed_at": "2026-11-21T10:00:00+07:00",
        "decision": {"status": "HOLD"},
        "liquidity": {"cash_available_for_new_project": 154_000_000},
        "market": {"conservative_exit": 400_000_000},
        "property": {"auction_limit": 160_000_000, "njop": 150_000_000, "npoptkp_eligible": False},
        "survey": {"possession_cost": 17_000_000, "possession_months": 0, "possession_risk_reserve": 5_000_000, "general_risk_reserve": 2_000_000},
        "costs": {
            "renovation_cost": 40_000_000,
            "renovation_items": [
                {"item_code": "ROOF", "work_item": "Perbaikan atap", "quantity": 20, "unit": "m2", "unit_cost": 1_000_000, "priority": "Wajib"},
                {"item_code": "INTERIOR", "work_item": "Cat interior bersyarat", "quantity": 30, "unit": "m2", "unit_cost": 200_000, "priority": "Bersyarat"},
                {"item_code": "UNKNOWN", "work_item": "Pekerjaan belum dihargai", "quantity": 1, "unit": "ls", "unit_cost": None, "priority": "Wajib"},
            ],
            "renovation_extra_cost": 20_000_000,
            "monthly_holding_cost": 1_000_000,
            "renovation_months": 2,
            "selling_months": 0,
            "legal_delay_months": 0,
            "marketing_cost": 1_000_000,
            "other_presale_cost": 2_000_000,
            "cost_estimates_reviewed": False,
        },
        "rules": {
            "buyer_auction_fee_pct": 2, "bphtb_rate_pct": 5, "npoptkp": 80_000_000,
            "npoptkp_eligible": False, "bphtb_basis_mode": "max_bid_or_njop",
            "bpn_pnbp_cost": 2_000_000, "roya_cost": 500_000,
            "other_acquisition_admin": 500_000, "other_legal_cost": 0,
            "acquisition_notary_ppat_fee": 0, "renovation_contingency_pct": 15,
            "seller_final_tax_pct": 2.5, "seller_agent_pct": 2.5,
            "seller_ajb_ppat_pct": 1, "seller_misc_fixed": 5_000_000,
        },
    }
    result = build_opening_budget_from_analysis(snapshot, "PROP-TEST", 170_000_000)
    rows = result["rows"]
    assert rows
    assert next(x for x in rows if x["payload"]["baseline_key"] == "ACQUISITION")["budget_amount"] == 170_000_000
    assert result["pending_pricing_items"] == ["Pekerjaan belum dihargai"]
    non_selling = sum(x["budget_amount"] for x in rows if x["category"] != "Penjualan")
    assert non_selling == result["calculator_capital_before_sale"]
    assert result["pre_bid_decision_status"] == "HOLD"
    assert result["pre_bid_cash_available"] == 154_000_000


def test_opening_budget_does_not_recalculate_when_analysis_snapshot_missing():
    result = build_opening_budget_from_analysis({}, "PROP-X", 120_000_000)
    assert result["rows"] == []
    assert result["complete"] is False


def test_opening_budget_exposes_pre_bid_cash_as_historical_and_flags_unconfirmed_estimates():
    snapshot = {
        "analysis_id": "ANL-HOLD-CASH",
        "analyzed_at": "2026-11-21T10:00:00+07:00",
        "decision": {"status": "HOLD"},
        "liquidity": {"cash_available_for_new_project": 154_000_000},
        "at_limit": {"capital_before_sale": 190_000_000, "cash_requirement_including_reserve": 200_000_000},
        "market": {"conservative_exit": 350_000_000},
        "property": {"auction_limit": 160_000_000, "njop": 150_000_000},
        "survey": {"possession_cost": 0, "possession_months": 0},
        "costs": {"renovation_cost": 0, "renovation_items": [], "cost_estimates_reviewed": False},
        "rules": {"buyer_auction_fee_pct": 2, "bphtb_rate_pct": 5, "renovation_contingency_pct": 15,
                  "seller_final_tax_pct": 2.5, "seller_agent_pct": 2.5, "seller_ajb_ppat_pct": 1, "seller_misc_fixed": 0},
    }
    result = build_opening_budget_from_analysis(snapshot, "PROP-HOLD", 165_000_000)
    assert result["pre_bid_decision_status"] == "HOLD"
    assert result["pre_bid_cash_available"] == 154_000_000
    assert result["pre_bid_capital_at_limit"] == 190_000_000
    assert result["winning_price"] == 165_000_000
    assert result["baseline_complete"] is False
    assert any("belum dikonfirmasi" in x.lower() for x in result["baseline_warnings"])
