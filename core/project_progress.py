"""Transparent renovation work-progress calculation for active projects.

Progress is based on explicit per-work-line updates, weighted by the same
screening workday effort used by the renovation schedule. Payments are never
interpreted as physical completion.
"""
from __future__ import annotations

from typing import Any

from .renovation_schedule import estimate_item_duration
from .utils import parse_json, to_float

_DONE = {"selesai", "completed", "complete", "done"}
_STARTED = {"berjalan", "in progress", "progress", "ongoing"}
_NOT_STARTED = {"belum mulai", "not started", "pending"}
_EXCLUDE_WORDS = ("contingency", "cadangan", "reconciliation", "rekonsiliasi", "hidden condition reserve", "cadangan kondisi")


def budget_payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("payload")
    if isinstance(value, dict):
        return value
    parsed = parse_json(row.get("payload_json"), {})
    return parsed if isinstance(parsed, dict) else {}


def is_renovation_work_line(row: dict[str, Any]) -> bool:
    category = str(row.get("category") or "").strip().lower()
    if category not in {"renovasi", "renovation", "perbaikan/renovasi"} and "renovasi" not in category:
        return False
    text = " ".join(str(row.get(k) or "") for k in ("description", "subcategory" )).lower()
    payload = budget_payload(row)
    text += " " + " ".join(str(payload.get(k) or "") for k in ("baseline_key", "description", "work_item", "subcategory"))
    # A category-only budget line is not enough to infer a physical work item.
    meaningful = [token for token in text.split() if token not in {"renovasi", "renovation", "umum"}]
    return bool(meaningful) and not any(token in text for token in _EXCLUDE_WORDS)


def _progress_value(row: dict[str, Any]) -> tuple[float | None, str]:
    payload = budget_payload(row)
    raw = payload.get("work_progress_pct")
    status = str(payload.get("work_status") or "").strip().lower()
    if raw not in (None, ""):
        return max(0.0, min(100.0, to_float(raw))), status or "updated"
    if status in _DONE:
        return 100.0, status
    if status in _NOT_STARTED:
        return 0.0, status
    # Legacy budget rows marked Completed can safely be considered completed.
    if str(row.get("status") or "").strip().lower() in _DONE:
        return 100.0, "completed_legacy"
    return None, status or "unupdated"


def calculate_project_work_progress(
    budget_rows: list[dict[str, Any]] | None,
    milestone_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a duration-weighted lower-bound progress and tracking coverage.

    Unupdated work lines contribute zero to the lower-bound overall percentage,
    but are clearly counted as untracked. With no explicit work-line updates,
    percentage remains None instead of displaying a misleading 0%.
    """
    work_rows = [r for r in (budget_rows or []) if isinstance(r, dict) and is_renovation_work_line(r)]
    if work_rows:
        weighted_done = 0.0
        total_weight = 0.0
        tracked = 0
        items: list[dict[str, Any]] = []
        for row in work_rows:
            payload = budget_payload(row)
            work = {
                "work_item": row.get("description") or payload.get("work_item") or row.get("subcategory") or "Pekerjaan renovasi",
                "description": row.get("description") or "",
                "subcategory": row.get("subcategory") or "",
                "category": row.get("category") or "Renovasi",
                "quantity": payload.get("quantity") or row.get("quantity") or 1,
                "unit": payload.get("unit") or row.get("unit") or "ls",
            }
            duration = estimate_item_duration(work)
            weight = max(0.25, to_float(duration.get("base"), 1.0))
            progress, status = _progress_value(row)
            total_weight += weight
            if progress is not None:
                tracked += 1
                weighted_done += weight * progress
            items.append({
                "budget_item_id": row.get("budget_item_id"),
                "description": work["work_item"],
                "progress_pct": progress,
                "work_status": status,
                "weight_days": weight,
            })
        pct = (weighted_done / total_weight) if total_weight > 0 and tracked else None
        if tracked:
            return {
            "progress_pct": pct,
            "tracked_work_items": tracked,
            "total_work_items": len(work_rows),
            "coverage_pct": (tracked / len(work_rows) * 100.0) if work_rows else 0.0,
            "method": "duration_weighted_work_items",
            "items": items,
            }

    milestones = [m for m in (milestone_rows or []) if isinstance(m, dict)]
    if milestones:
        done = sum(1 for m in milestones if str(m.get("status") or "").strip().lower() in _DONE)
        started = sum(1 for m in milestones if str(m.get("status") or "").strip().lower() in _DONE | _STARTED | _NOT_STARTED)
        return {
            "progress_pct": done / len(milestones) * 100.0,
            "tracked_work_items": started,
            "total_work_items": len(milestones),
            "coverage_pct": started / len(milestones) * 100.0,
            "method": "milestone_count_fallback",
            "items": [],
        }

    return {
        "progress_pct": None,
        "tracked_work_items": 0,
        "total_work_items": len(work_rows),
        "coverage_pct": 0.0,
        "method": "not_recorded",
        "items": [],
    }
