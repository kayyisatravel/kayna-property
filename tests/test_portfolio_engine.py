from core.portfolio_engine import rank_saved_objects, suitability_score


def _snapshot(status="GO", score=80, oid="A"):
    return {
        "object_id": oid,
        "inputs": {"property": {"name": oid, "lot_code": oid}, "finance": {"minimum_roi_pct": 20, "maximum_holding_months": 12}},
        "results": {"base_at_limit": {"roi_pct": 25, "net_profit": 40_000_000, "total_holding_months": 4, "pre_sale_investment": 200_000_000, "available_for_project": 300_000_000},
                    "recommended_max_bid": {"maximum_bid": 150_000_000}, "absolute_max_bid": {"maximum_bid": 170_000_000}},
        "market": {"count": 5, "confidence": 80},
        "decision": {"status": status, "weighted_risk_score": 4, "blockers": []},
        "suitability": {"score_pct": score},
    }


def test_suitability_score_is_bounded():
    score = suitability_score(_snapshot())
    assert 0 <= score["score_pct"] <= 100
    assert "bukan probabilitas" in score["interpretation"].lower()


def test_rank_orders_go_before_hold_even_when_hold_score_higher():
    rows = rank_saved_objects([_snapshot("HOLD", 99, "B"), _snapshot("GO", 50, "A")])
    assert rows[0]["object_id"] == "A"
    assert rows[1]["object_id"] == "B"


def test_rank_returns_one_based_ranks():
    rows = rank_saved_objects([_snapshot("GO", 90, "A"), _snapshot("GO", 80, "B")])
    assert [r["rank"] for r in rows] == [1, 2]
