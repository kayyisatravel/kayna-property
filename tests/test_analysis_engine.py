from core.analysis_engine import run_property_analysis


def test_analysis_runs_without_gemini_and_keeps_hard_stop():
    inputs = {
        "object_id": "test-1",
        "property": {"name": "Test House", "complex_name": "Kompleks A", "auction_limit": 150_000_000, "deposit_amount": 30_000_000,
                     "bid_increment": 1_000_000, "land_area": 90, "building_area": 70, "certificate_type": "SHM",
                     "legal_status": "Belum terverifikasi", "identity_verified": False, "title_match": False,
                     "dispute_detected": False, "njop": 130_000_000},
        "survey": {"occupancy_status": "Belum diketahui", "occupancy_verified": False, "physical_condition": "Tidak diketahui", "interior_inspected": False},
        "fees": {"buyer_auction_fee_pct": 0, "bphtb_rate_pct": 0, "npoptkp": 0, "ppn_applicable": False,
                 "ppn_rate_pct": 0, "seller_tax_pct": 0, "selling_agent_pct": 0, "tax_rules_verified": False},
        "costs": {"certificate_legal_cost": 10_000_000, "renovation_cost": 20_000_000, "arrears_utilities_cost": 0,
                  "selected_possession_scenario": "KOOPERATIF", "monthly_holding_cost": 1_000_000,
                  "renovation_months": 2, "sale_months_after_ready": 3, "contingency_pct": 10,
                  "marketing_cost": 1_000_000, "other_presale_cost": 0, "other_selling_cost": 0},
        "targets": {"minimum_roi_pct": 20, "minimum_net_profit": 10_000_000, "minimum_profit_per_month": 0, "maximum_holding_months": 12},
        "risk_scores": {"liquidity": 3, "legal": 2, "possession": 2, "physical": 3, "funding": 4, "environment": 3},
        "comparables": [
            {"complex": "Kompleks A", "distance_km": 0.2, "land_area": 90, "building_area": 70, "price": 350_000_000, "price_type": "Listing aktif", "condition": "Siap huni", "property_type": "Rumah 1 lantai", "certificate": "SHM", "date_found": "2026-11-01"},
            {"complex": "Kompleks A", "distance_km": 0.5, "land_area": 90, "building_area": 75, "price": 360_000_000, "price_type": "Listing aktif", "condition": "Siap huni", "property_type": "Rumah 1 lantai", "certificate": "SHM", "date_found": "2026-11-01"},
            {"complex": "Kompleks B", "distance_km": 1.0, "land_area": 95, "building_area": 70, "price": 370_000_000, "price_type": "Terjual / marked sold", "condition": "Siap huni", "property_type": "Rumah 1 lantai", "certificate": "SHM", "date_found": "2026-10-20"},
        ],
        "possession_scenarios": {
            "KOSONG": {"label": "Kosong", "cost": 1_000_000, "delay_months": 0.5},
            "KOOPERATIF": {"label": "Kooperatif", "cost": 5_000_000, "delay_months": 1},
            "SULIT": {"label": "Sulit", "cost": 20_000_000, "delay_months": 3},
            "EKSEKUSI_FORMAL": {"label": "Formal", "cost": 70_000_000, "delay_months": 9},
        },
    }
    investor = {"live_cash": 500_000_000, "ongoing_commitments": 0, "household_reserve": 20_000_000,
                "risk_reserve": 20_000_000, "profile_confirmed": True}
    snapshot = run_property_analysis(inputs, investor)
    assert snapshot["object_id"] == "test-1"
    assert snapshot["market"]["base_exit"] > 0
    assert snapshot["decision"]["status"] == "HOLD"
    assert snapshot["suitability"]["score_pct"] >= 0
    assert snapshot["inputs"]["finance"]["minimum_roi_pct"] == 20
    assert snapshot["inputs"]["finance"]["minimum_net_profit"] == 10_000_000


def test_portfolio_recalculates_saved_object_with_current_cash():
    from core.portfolio_engine import rank_saved_objects

    inputs = {
        "object_id": "live-cash-test",
        "property": {"name": "Cash Test", "complex_name": "Kompleks A", "auction_limit": 150_000_000,
                     "bid_increment": 1_000_000, "land_area": 90, "building_area": 70,
                     "certificate_type": "SHM", "legal_status": "Terverifikasi", "identity_verified": True,
                     "title_match": True, "dispute_detected": False, "njop": 130_000_000,
                     "auction_url": "https://example.invalid/lot"},
        "survey": {"occupancy_status": "Kosong dan terverifikasi", "occupancy_verified": True,
                   "physical_condition": "Siap huni", "interior_inspected": True,
                   "survey_date": "2026-11-01"},
        "fees": {"buyer_auction_fee_pct": 0, "bphtb_rate_pct": 0, "npoptkp": 0,
                 "ppn_applicable": False, "ppn_rate_pct": 0, "seller_tax_pct": 0,
                 "selling_agent_pct": 0, "tax_rules_verified": True},
        "costs": {"certificate_legal_cost": 1_000_000, "renovation_cost": 5_000_000,
                  "monthly_holding_cost": 500_000, "renovation_months": 1,
                  "sale_months_after_ready": 2, "contingency_pct": 5,
                  "selected_possession_scenario": "KOSONG"},
        "targets": {"minimum_roi_pct": 15, "minimum_net_profit": 5_000_000,
                    "minimum_profit_per_month": 0, "maximum_holding_months": 12},
        "risk_scores": {"liquidity": 4, "legal": 4, "possession": 4, "physical": 4,
                        "funding": 4, "environment": 4},
        "comparables": [
            {"complex": "Kompleks A", "distance_km": 0.1, "land_area": 90, "building_area": 70,
             "price": 350_000_000, "price_type": "Transaksi terverifikasi", "condition": "Siap huni",
             "property_type": "Rumah 1 lantai", "certificate": "SHM", "date_found": "2026-11-01"},
            {"complex": "Kompleks A", "distance_km": 0.2, "land_area": 90, "building_area": 70,
             "price": 355_000_000, "price_type": "Listing aktif", "condition": "Siap huni",
             "property_type": "Rumah 1 lantai", "certificate": "SHM", "date_found": "2026-11-01"},
            {"complex": "Kompleks B", "distance_km": 0.8, "land_area": 95, "building_area": 75,
             "price": 360_000_000, "price_type": "Listing aktif", "condition": "Siap huni",
             "property_type": "Rumah 1 lantai", "certificate": "SHM", "date_found": "2026-11-01"},
        ],
        "possession_scenarios": {"KOSONG": {"label": "Kosong", "cost": 0, "delay_months": 0, "reserve_cost": 0}},
    }
    rich_cash = {"live_cash": 500_000_000, "ongoing_commitments": 0, "household_reserve": 0,
                 "risk_reserve": 0, "profile_confirmed": True}
    snapshot = run_property_analysis(inputs, rich_cash)
    old_available = snapshot["results"]["base_at_limit"]["available_for_project"]
    poor_cash = {"live_cash": 10_000_000, "ongoing_commitments": 0, "household_reserve": 0,
                 "risk_reserve": 0, "profile_confirmed": True}
    ranked = rank_saved_objects([snapshot], poor_cash)
    assert old_available == 500_000_000
    assert ranked[0]["available_cash"] == 10_000_000
    assert ranked[0]["snapshot"]["results"]["base_at_limit"]["available_for_project"] == 10_000_000
