from core.project_progress import calculate_project_work_progress, is_renovation_work_line
from reports.portfolio_context import build_portfolio_report_context


def test_work_progress_is_weighted_by_the_same_estimated_workday_basis():
    budgets = [
        {
            "budget_item_id": "B1", "category": "Renovasi", "subcategory": "Pengecatan",
            "description": "Pengecatan ulang dinding fasad", "budget_amount": 8_000_000,
            "payload": {"quantity": 90, "unit": "m2", "work_status": "Selesai", "work_progress_pct": 100},
        },
        {
            "budget_item_id": "B2", "category": "Renovasi", "subcategory": "Atap",
            "description": "Pemasangan atap kanopi", "budget_amount": 10_000_000,
            "payload": {"quantity": 18, "unit": "m2", "work_status": "Berjalan", "work_progress_pct": 50},
        },
    ]
    result = calculate_project_work_progress(budgets)
    assert result["total_work_items"] == 2
    assert result["tracked_work_items"] == 2
    assert result["coverage_pct"] == 100
    assert 60 < result["progress_pct"] < 90
    assert result["method"] == "duration_weighted_work_items"


def test_unupdated_work_items_do_not_display_false_zero_percent():
    budgets = [
        {"category": "Renovasi", "description": "Cat dinding", "payload": {"quantity": 50, "unit": "m2"}},
        {"category": "Renovasi", "description": "Perbaikan atap", "payload": {"quantity": 10, "unit": "m2"}},
    ]
    result = calculate_project_work_progress(budgets)
    assert result["progress_pct"] is None
    assert result["tracked_work_items"] == 0
    assert result["total_work_items"] == 2
    assert result["coverage_pct"] == 0


def test_partial_progress_is_a_lower_bound_and_reports_tracking_coverage():
    budgets = [
        {"category": "Renovasi", "description": "Pengecatan dinding", "payload": {"quantity": 40, "unit": "m2", "work_status": "Berjalan", "work_progress_pct": 50}},
        {"category": "Renovasi", "description": "Pemasangan atap kanopi", "payload": {"quantity": 18, "unit": "m2"}},
    ]
    result = calculate_project_work_progress(budgets)
    assert result["progress_pct"] is not None
    assert 0 < result["progress_pct"] < 50
    assert result["tracked_work_items"] == 1
    assert result["total_work_items"] == 2
    assert result["coverage_pct"] == 50


def test_category_only_renovation_budget_uses_existing_milestone_fallback():
    budgets = [{"category": "Renovasi", "budget_amount": 10_000_000}]
    milestones = [{"status": "Completed"}, {"status": "In Progress"}]
    result = calculate_project_work_progress(budgets, milestones)
    assert result["method"] == "milestone_count_fallback"
    assert result["progress_pct"] == 50


def test_financial_reserve_lines_are_not_counted_as_physical_renovation_tasks():
    assert not is_renovation_work_line({"category": "Renovasi", "description": "Contingency renovasi 15%"})
    assert not is_renovation_work_line({"category": "Renovasi", "description": "Cadangan kondisi tersembunyi"})


def test_portfolio_context_uses_work_items_instead_of_reporting_zero_when_untracked():
    properties = [{"property_id": "P1", "name": "Project 1", "lifecycle_status": "ACTIVE", "payload": {"project_stage": "Renovasi"}}]
    budgets = [
        {"property_id": "P1", "budget_item_id": "W1", "category": "Renovasi", "description": "Pengecatan fasad", "budget_amount": 5_000_000, "payload": {"quantity": 50, "unit": "m2", "work_status": "Selesai", "work_progress_pct": 100}},
        {"property_id": "P1", "budget_item_id": "W2", "category": "Renovasi", "description": "Pemasangan kanopi", "budget_amount": 8_000_000, "payload": {"quantity": 18, "unit": "m2", "work_status": "Berjalan", "work_progress_pct": 50}},
    ]
    result = build_portfolio_report_context(properties, [], budgets, [], [])
    active = result["active_projects"][0]
    assert active["progress_pct"] is not None
    assert active["tracked_work_items"] == 2
    assert active["total_work_items"] == 2
    assert active["progress_coverage_pct"] == 100
