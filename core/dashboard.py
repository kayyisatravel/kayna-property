"""Cached-data dashboard view model for Kayna Property Management System.

This module is deliberately pure Python: it receives rows already read by the
application, performs no Google Sheets calls, and makes no AI calls.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .lifecycle import actual_project_summary
from .project_alerts import assess_project_alerts
from .project_progress import calculate_project_work_progress
from .utils import parse_json, to_float

SELLING_CATEGORIES = {"selling", "penjualan", "biaya penjualan", "pajak penjualan", "komisi agen"}
ACTIVE_STATUSES = {"WON", "ACTIVE"}
PROSPECT_STATUSES = {"PROSPECT", "BID PLANNED", "BID SUBMITTED"}


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("payload")
    if isinstance(value, dict):
        return value
    parsed = parse_json(row.get("payload_json"), {})
    return parsed if isinstance(parsed, dict) else {}


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _property_inputs(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _payload(row)
    input_data = payload.get("input_data") if isinstance(payload.get("input_data"), dict) else {}
    latest = payload.get("latest_analysis") if isinstance(payload.get("latest_analysis"), dict) else {}
    input_property = input_data.get("property") if isinstance(input_data.get("property"), dict) else {}
    latest_property = latest.get("property") if isinstance(latest.get("property"), dict) else {}
    # Prefer the live row, then persisted input form, then analysis snapshot.
    details = {**latest_property, **input_property, **row}
    return payload, details


def build_dashboard_view(
    properties: list[dict[str, Any]] | None,
    analyses: list[dict[str, Any]] | None,
    actual_rows: list[dict[str, Any]] | None,
    budget_rows: list[dict[str, Any]] | None,
    closing_rows: list[dict[str, Any]] | None,
    *,
    today: date,
    milestone_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build summary cards, upcoming deadlines and active project CTAs.

    The caller passes data from app-level cache_data reads. Sorting and filtering
    never trigger another Google Sheets request.
    """
    properties = [x for x in (properties or []) if isinstance(x, dict)]
    analyses = [x for x in (analyses or []) if isinstance(x, dict)]
    actual_rows = [x for x in (actual_rows or []) if isinstance(x, dict)]
    budget_rows = [x for x in (budget_rows or []) if isinstance(x, dict)]
    closing_rows = [x for x in (closing_rows or []) if isinstance(x, dict)]
    milestone_rows = [x for x in (milestone_rows or []) if isinstance(x, dict)]

    active = [p for p in properties if str(p.get("lifecycle_status") or "").upper() in ACTIVE_STATUSES]
    sold = [p for p in properties if str(p.get("lifecycle_status") or "").upper() == "SOLD"]
    prospects = [p for p in properties if str(p.get("lifecycle_status") or "").upper() in PROSPECT_STATUSES]

    auction_events: list[dict[str, Any]] = []
    for prop in prospects:
        _, details = _property_inputs(prop)
        name = prop.get("name") or details.get("name") or prop.get("lot_code") or "Properti lelang"
        lot = prop.get("lot_code") or details.get("lot_code") or ""
        status = str(prop.get("lifecycle_status") or "PROSPECT")
        for key, label in (("deposit_deadline", "Batas setor jaminan"), ("auction_date", "Tanggal lelang")):
            event_date = _as_date(details.get(key) or prop.get(key))
            if not event_date:
                continue
            days = (event_date - today).days
            # Keep near-term and overdue dates visible. Very old dates are not useful
            # on the first dashboard; still retain those up to 14 days overdue.
            if -14 <= days <= 60:
                auction_events.append({
                    "date": event_date.isoformat(), "date_obj": event_date,
                    "days": days, "event": label, "property": name,
                    "lot_code": lot, "status": status,
                    "urgency": "Lewat" if days < 0 else ("Hari ini" if days == 0 else f"{days} hari lagi"),
                })
    auction_events.sort(key=lambda x: (x["date_obj"], 0 if x["event"] == "Batas setor jaminan" else 1, x["property"]))

    active_summaries: list[dict[str, Any]] = []
    project_alerts: list[dict[str, Any]] = []
    active_ids = {str(p.get("property_id") or "") for p in active}
    active_actual_paid = 0.0
    active_budget_total = 0.0
    active_projected_total = 0.0
    active_commitments = 0.0
    for prop in active:
        pid = str(prop.get("property_id") or "")
        payload, details = _property_inputs(prop)
        name = prop.get("name") or details.get("name") or prop.get("lot_code") or pid
        actuals = [x for x in actual_rows if str(x.get("property_id") or "") == pid]
        budgets = [x for x in budget_rows if str(x.get("property_id") or "") == pid and str(x.get("status") or "Active").lower() not in {"cancelled", "archived"}]
        milestones = [x for x in milestone_rows if str(x.get("property_id") or "") == pid]
        progress = calculate_project_work_progress(budgets, milestones)
        project_actual = sum(to_float(x.get("amount")) for x in actuals if str(x.get("category") or "").strip().lower() not in SELLING_CATEGORIES)
        project_paid_all = sum(to_float(x.get("amount")) for x in actuals)
        budget_total = sum(max(0.0, to_float(x.get("budget_amount"))) for x in budgets if str(x.get("category") or "").strip().lower() not in SELLING_CATEGORIES)
        commitments = sum(max(0.0, to_float(x.get("committed_unpaid"))) for x in budgets if str(x.get("category") or "").strip().lower() not in SELLING_CATEGORIES)
        forecasts = sum(max(0.0, to_float(x.get("forecast_remaining"))) for x in budgets if str(x.get("category") or "").strip().lower() not in SELLING_CATEGORIES)
        projected = project_actual + commitments + forecasts
        target_date = _as_date(payload.get("planned_sale_date") or details.get("planned_sale_date") or payload.get("target_sale_date"))
        alerts = assess_project_alerts(
            today=today, target_sale_date=target_date, is_sold=False,
            budget_total=budget_total, projected_completion=projected,
        )["alerts"]
        for alert in alerts:
            project_alerts.append({**alert, "property": name, "property_id": pid})
        active_summaries.append({
            "property_id": pid, "property": name,
            "address": prop.get("address") or details.get("address") or "—",
            "stage": payload.get("project_stage") or payload.get("stage") or "Tahap belum dicatat",
            "target_sale_date": target_date.isoformat() if target_date else "",
            "actual_paid": project_paid_all,
            "project_actual": project_actual,
            "commitments": commitments,
            "forecast": forecasts,
            "projected_total": projected,
            "budget_total": budget_total,
            "budget_usage_pct": projected / budget_total * 100 if budget_total > 0 else None,
            "progress_pct": progress.get("progress_pct"),
            "progress_coverage_pct": progress.get("coverage_pct", 0.0),
            "tracked_work_items": progress.get("tracked_work_items", 0),
            "total_work_items": progress.get("total_work_items", 0),
            "progress_method": progress.get("method", "not_recorded"),
            "alerts": alerts,
        })
        active_actual_paid += project_paid_all
        active_budget_total += budget_total
        active_projected_total += projected
        active_commitments += commitments

    project_alerts.sort(key=lambda x: (0 if x.get("severity") == "critical" else 1 if x.get("severity") == "warning" else 2, x.get("property", "")))

    realized = []
    closing_by_id = {str(x.get("property_id") or ""): x for x in closing_rows}
    sold_ids = {str(x.get("property_id") or "") for x in sold}
    for pid in sold_ids:
        close = closing_by_id.get(pid)
        if not close:
            continue
        costs = [x for x in actual_rows if str(x.get("property_id") or "") == pid]
        realized.append(actual_project_summary(costs, close))
    realized_profit = sum(to_float(x.get("net_profit_actual")) for x in realized)

    decisions: dict[str, int] = {}
    for row in analyses:
        label = str(row.get("decision_status") or "HOLD").upper()
        decisions[label] = decisions.get(label, 0) + 1

    return {
        "as_of": today.isoformat(),
        "summary": {
            "prospects": len(prospects), "upcoming_auction_events": len([x for x in auction_events if x["days"] >= 0]),
            "active_projects": len(active), "sold_projects": len(sold),
            "realized_profit": realized_profit, "active_actual_paid": active_actual_paid,
            "active_budget_total": active_budget_total, "active_projected_total": active_projected_total,
            "active_commitments": active_commitments, "analysis_count": len(analyses),
        },
        "auction_events": auction_events[:8],
        "project_alerts": project_alerts[:12],
        "active_projects": sorted(active_summaries, key=lambda x: x["property"].lower()),
        "decision_distribution": decisions,
    }
