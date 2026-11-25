"""Compact portfolio appendix for investor memorandum exports."""
from __future__ import annotations
from typing import Any

from core.lifecycle import actual_project_summary
from core.project_ledger import summarize_project_ledger
from core.utils import parse_json, to_float

SELLING_CATEGORIES = {"selling", "penjualan", "biaya penjualan", "pajak penjualan", "komisi agen"}


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("payload")
    return value if isinstance(value, dict) else parse_json(row.get("payload_json"), {})


def build_portfolio_report_context(
    properties: list[dict[str, Any]] | None,
    actual_rows: list[dict[str, Any]] | None,
    budget_rows: list[dict[str, Any]] | None,
    milestone_rows: list[dict[str, Any]] | None,
    closing_rows: list[dict[str, Any]] | None,
    *,
    as_of: str = "",
) -> dict[str, Any]:
    """Build active and realized project summaries from supplied cached rows.

    This function performs no Google Sheets reads and no AI calls. The caller is
    responsible for supplying the app's cached table contents.
    """
    actual_rows = actual_rows or []
    budget_rows = budget_rows or []
    milestone_rows = milestone_rows or []
    closing_rows = closing_rows or []
    active_projects: list[dict[str, Any]] = []
    completed_projects: list[dict[str, Any]] = []

    for prop in properties or []:
        pid = str(prop.get("property_id") or "")
        payload = _payload(prop)
        status = str(prop.get("lifecycle_status") or "").upper()
        project_actuals = [x for x in actual_rows if str(x.get("property_id") or "") == pid]
        project_budgets = [x for x in budget_rows if str(x.get("property_id") or "") == pid]
        project_milestones = [x for x in milestone_rows if str(x.get("property_id") or "") == pid]

        if status in {"WON", "ACTIVE"}:
            ledger = summarize_project_ledger(project_actuals, project_budgets)
            done = sum(1 for x in project_milestones if str(x.get("status") or "").strip().lower() in {"completed", "complete", "done", "selesai"})
            progress_pct = (done / len(project_milestones) * 100.0) if project_milestones else None
            latest = payload.get("latest_analysis") if isinstance(payload.get("latest_analysis"), dict) else {}
            active_projects.append({
                "property_id": pid,
                "name": prop.get("name") or prop.get("lot_code") or pid,
                "address": prop.get("address") or "Alamat belum dicatat",
                "lifecycle_status": status,
                "stage": payload.get("project_stage") or "Tahap belum dicatat",
                "progress_pct": progress_pct,
                "completed_milestones": done,
                "total_milestones": len(project_milestones),
                "actual_paid": ledger.get("actual_paid_total", 0),
                "actual_project_cost": ledger.get("actual_project_cost", 0),
                "actual_selling_cost": ledger.get("actual_selling_cost", 0),
                "committed": ledger.get("committed_unpaid_total", 0),
                "forecast": ledger.get("forecast_remaining_total", 0),
                "budget_total": ledger.get("budget_total", 0),
                "expected_completion": ledger.get("budgeted_completion_total", 0),
                "target_sale_date": payload.get("planned_sale_date") or "",
                "analysis_id": latest.get("analysis_id") or "",
            })
        elif status == "SOLD":
            closing = next((x for x in closing_rows if str(x.get("property_id") or "") == pid), {})
            if not closing:
                continue
            realized = actual_project_summary(project_actuals, closing)
            latest = payload.get("latest_analysis") if isinstance(payload.get("latest_analysis"), dict) else {}
            market = latest.get("market") if isinstance(latest.get("market"), dict) else {}
            base_arv = to_float(market.get("base_exit"))
            closing_price = to_float(realized.get("closing_price"))
            budget_project_total = sum(
                max(0.0, to_float(row.get("budget_amount")))
                for row in project_budgets
                if str(row.get("category") or "").strip().lower() not in SELLING_CATEGORIES
                and str(row.get("status") or "Active") not in {"Cancelled", "Archived"}
            )
            actual_project_cost = to_float(realized.get("total_actual_cost"))
            completed_projects.append({
                "property_id": pid,
                "name": prop.get("name") or prop.get("lot_code") or pid,
                "address": prop.get("address") or "Alamat belum dicatat",
                "sold_date": closing.get("sold_date") or "",
                "closing_price": closing_price,
                "total_actual_cost": actual_project_cost,
                "selling_cost_actual": realized.get("selling_cost_actual", 0),
                "net_profit_actual": realized.get("net_profit_actual", 0),
                "roi_actual_pct": realized.get("roi_actual_pct"),
                "total_holding_months": realized.get("total_holding_months", 0),
                "base_arv": base_arv or None,
                "closing_vs_base_arv_pct": ((closing_price / base_arv - 1) * 100) if base_arv > 0 and closing_price > 0 else None,
                "budget_project_total": budget_project_total or None,
                "budget_variance_actual": (budget_project_total - actual_project_cost) if budget_project_total > 0 else None,
            })

    active_projects.sort(key=lambda x: (x.get("name") or "").lower())
    completed_projects.sort(key=lambda x: str(x.get("sold_date") or ""), reverse=True)
    return {"as_of": as_of, "active_projects": active_projects, "completed_projects": completed_projects}
