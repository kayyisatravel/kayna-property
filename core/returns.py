"""Time-aware investment return helpers.

XIRR is calculated only when dated cash flows are complete. Forecast underwriting
uses the clearly-labelled annualized project ROI; actual project XIRR is derived
from dated cost-ledger transactions and the closing proceeds.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Any, Iterable


def parse_cashflow_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text[:26], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def xirr(cashflows: Iterable[tuple[Any, float]], *, tolerance: float = 1e-9, max_iterations: int = 300) -> float | None:
    """Return annual XIRR as a percentage; None if dates/signs/root are invalid.

    A bisection solver is used rather than Newton iteration so the result is
    stable for uneven auction, renovation, and closing cash flows.
    """
    flows: list[tuple[date, float]] = []
    for raw_date, raw_amount in cashflows:
        parsed = parse_cashflow_date(raw_date)
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None
        if amount:
            flows.append((parsed, amount))
    if len(flows) < 2:
        return None
    flows.sort(key=lambda x: x[0])
    if not any(amount < 0 for _, amount in flows) or not any(amount > 0 for _, amount in flows):
        return None
    first_day = flows[0][0]

    def npv(rate: float) -> float:
        if rate <= -1.0:
            return float("inf")
        return sum(amount / ((1.0 + rate) ** ((day - first_day).days / 365.0)) for day, amount in flows)

    low, high = -0.9999, 1.0
    f_low, f_high = npv(low), npv(high)
    while f_low * f_high > 0 and high < 1_000_000:
        high = high * 2 + 1
        f_high = npv(high)
    if f_low * f_high > 0:
        return None
    for _ in range(max_iterations):
        mid = (low + high) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) <= tolerance or abs(high - low) <= tolerance:
            return mid * 100.0
        if f_low * f_mid <= 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return ((low + high) / 2.0) * 100.0
