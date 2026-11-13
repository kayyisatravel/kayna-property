"""Risk-register scoring and liquidity reserve aggregation."""
from __future__ import annotations
from typing import Any
from .utils import to_float, is_blank

RESOLVED_STATES = {"resolved", "closed", "mitigated"}


def summarize_risks(risks: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = []
    total_cash_reserve = 0.0
    critical_open = []
    severe_unmitigated = []
    invalid = []
    for raw in risks or []:
        row = dict(raw)
        description = str(row.get("risk_description") or row.get("description") or "").strip()
        if not description:
            continue
        if is_blank(row.get("probability_1_5")) or is_blank(row.get("impact_1_5")) or is_blank(row.get("cost_reserve")):
            invalid.append(f"Probabilitas, dampak, dan cadangan biaya wajib diisi untuk risiko: {description}")
        probability = max(1, min(5, int(to_float(row.get("probability_1_5"), 1))))
        impact = max(1, min(5, int(to_float(row.get("impact_1_5"), 1))))
        severity = probability * impact
        status = str(row.get("status") or "Open").strip()
        critical = bool(row.get("critical", False))
        reserve = max(0.0, to_float(row.get("cost_reserve"), 0.0)) if status.lower() not in RESOLVED_STATES else 0.0
        total_cash_reserve += reserve
        mitigation = str(row.get("mitigation") or "").strip()
        item = {
            **row,
            "risk_description": description,
            "probability_1_5": probability,
            "impact_1_5": impact,
            "severity_score": severity,
            "critical": critical,
            "status": status,
            "cost_reserve": reserve,
            "mitigation": mitigation,
        }
        rows.append(item)
        if critical and status.lower() not in RESOLVED_STATES:
            critical_open.append(description)
        if severity >= 20 and not mitigation and status.lower() not in RESOLVED_STATES:
            severe_unmitigated.append(description)
    maximum = max((x["severity_score"] for x in rows), default=0)
    average = round(sum(x["severity_score"] for x in rows) / len(rows), 1) if rows else 0.0
    warnings = [f"Risiko berdampak tinggi (score ≥20) belum memiliki mitigasi: {x}" for x in severe_unmitigated]
    return {
        "items": rows,
        "count": len(rows),
        "maximum_severity": maximum,
        "average_severity": average,
        "total_cash_reserve": total_cash_reserve,
        "critical_open": critical_open,
        "severe_unmitigated": severe_unmitigated,
        "invalid": invalid,
        "warnings": warnings,
    }
