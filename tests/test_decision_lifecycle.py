from core.decision_engine import evaluate_decision
from core.lifecycle import actual_project_summary


def test_missing_survey_holds():
    inputs = {"property":{"lot_code":"L1","address":"A","auction_limit":100},"survey":{"survey_status":"Belum Survei"},"legal":{"identity_verified":True},"rules":{"minimum_roi_pct":25},"finance":{"cash_confirmed":True,"cash_available_for_new_project":1_000_000}}
    market = {"valid_count":5,"confidence":80}
    tiers = {"increment_confirmed":True,"max_bid":150}
    result = evaluate_decision(inputs, market, tiers, {"roi_pct":35,"net_profit":35,"capital_before_sale":100})
    assert result["status"] == "HOLD"


def test_roi_below_target_is_do_not_bid():
    inputs = {"property":{"lot_code":"L1","address":"A","auction_limit":100},"survey":{"survey_status":"Sudah Survei - Kosong/Tidak Dihuni"},"legal":{"identity_verified":True},"rules":{"minimum_roi_pct":25},"finance":{"cash_confirmed":True,"cash_available_for_new_project":1_000_000}}
    market = {"valid_count":5,"confidence":80}
    tiers = {"increment_confirmed":True,"max_bid":None}
    result = evaluate_decision(inputs, market, tiers, {"roi_pct":12,"net_profit":10,"capital_before_sale":100})
    assert result["status"] == "DO NOT BID"


def test_sold_project_profit_calculation():
    costs = [{"category":"Acquisition","amount":200},{"category":"Renovation","amount":40},{"category":"Selling","amount":20}]
    result = actual_project_summary(costs, {"closing_price":350,"total_holding_months":4})
    assert result["total_actual_cost"] == 240
    assert result["net_profit_actual"] == 90


def test_all_gates_pass_returns_go():
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100, "land_area":90, "building_area":70, "property_type":"Rumah 1 lantai"},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "interior_inspected":True},
        "legal": {"identity_verified":True, "dispute_detected":False, "tax_rules_verified":True},
        "rules": {"minimum_roi_pct":25},
        "costs": {"cost_estimates_reviewed": True},
        "finance": {"cash_confirmed":True, "cash_available_for_new_project":1_000_000},
        "risk_reviewed": True,
    }
    market = {"valid_count":5, "confidence":85}
    tiers = {"increment_confirmed":True, "max_bid":150}
    result = evaluate_decision(inputs, market, tiers, {"roi_pct":35, "net_profit":35, "capital_before_sale":100, "cash_requirement_including_reserve":100})
    assert result["status"] == "GO"


def test_unverified_tax_rules_prevent_go():
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100, "land_area":90, "building_area":70},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "interior_inspected":True},
        "legal": {"identity_verified":True, "dispute_detected":False, "tax_rules_verified":False},
        "rules": {"minimum_roi_pct":25},
        "costs": {"cost_estimates_reviewed": True},
        "finance": {"cash_confirmed":True, "cash_available_for_new_project":1_000_000},
        "risk_reviewed": True,
    }
    result = evaluate_decision(inputs, {"valid_count":5,"confidence":85}, {"increment_confirmed":True,"max_bid":150}, {"roi_pct":35,"net_profit":35,"capital_before_sale":100,"cash_requirement_including_reserve":100})
    assert result["status"] == "HOLD"


def test_critical_open_risk_prevents_go():
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100, "land_area":90, "building_area":70},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "interior_inspected":True},
        "legal": {"identity_verified":True, "dispute_detected":False, "tax_rules_verified":True},
        "rules": {"minimum_roi_pct":25},
        "costs": {"cost_estimates_reviewed": True},
        "finance": {"cash_confirmed":True, "cash_available_for_new_project":1_000_000},
        "risk_reviewed": True,
        "risk_summary": {"critical_open":["Risiko penguasaan"], "invalid":[], "severe_unmitigated":[]},
    }
    result = evaluate_decision(inputs, {"valid_count":5,"confidence":85}, {"increment_confirmed":True,"max_bid":150}, {"roi_pct":35,"net_profit":35,"capital_before_sale":100,"cash_requirement_including_reserve":100})
    assert result["status"] == "HOLD"


def test_risk_summary_reserves_cash_and_flags_critical_risk():
    from core.risk_engine import summarize_risks
    result = summarize_risks([{"category":"Possession","risk_description":"Penghuni menolak keluar","probability_1_5":4,"impact_1_5":5,"cost_reserve":50_000_000,"critical":True,"mitigation":"Negosiasi dan pendampingan hukum","status":"Open"}])
    assert result["total_cash_reserve"] == 50_000_000
    assert result["maximum_severity"] == 20
    assert result["critical_open"] == ["Penghuni menolak keluar"]


def test_unreviewed_cost_estimates_prevent_go():
    inputs = {
        "property": {"lot_code":"L1", "address":"Alamat", "auction_limit":100, "land_area":90, "building_area":70},
        "survey": {"survey_status":"Sudah Survei - Kosong/Tidak Dihuni", "interior_inspected":True},
        "legal": {"identity_verified":True, "dispute_detected":False, "tax_rules_verified":True},
        "costs": {"cost_estimates_reviewed":False},
        "rules": {"minimum_roi_pct":25},
        "finance": {"cash_confirmed":True, "cash_available_for_new_project":1_000_000},
        "risk_reviewed": True,
    }
    result = evaluate_decision(inputs, {"valid_count":5,"confidence":85}, {"increment_confirmed":True,"max_bid":150}, {"roi_pct":35,"net_profit":35,"capital_before_sale":100,"cash_requirement_including_reserve":100})
    assert result["status"] == "HOLD"


def test_risk_editor_nan_values_are_reported_as_missing_not_crash():
    from core.risk_engine import summarize_risks
    result = summarize_risks([{"risk_description":"Risiko kosong","probability_1_5":float("nan"),"impact_1_5":float("nan"),"cost_reserve":float("nan")}])
    assert result["invalid"]
    assert result["total_cash_reserve"] == 0
