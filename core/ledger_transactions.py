"""Safe reconciliation helpers when a paid transaction is corrected."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
import json

COMMITMENT_SOURCE = "Pembayaran atas komitmen"
FORECAST_SOURCE = "Pembayaran dari forecast"


def _details(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    value = record.get("details_json", {})
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _adjustment(record: dict[str, Any] | None) -> tuple[str, str, float] | None:
    if not record:
        return None
    details = _details(record)
    source = str(details.get("payment_source") or "")
    field = "committed_unpaid" if source == COMMITMENT_SOURCE else "forecast_remaining" if source == FORECAST_SOURCE else ""
    budget_id = str(record.get("budget_item_id") or "").strip()
    amount = max(0.0, float(record.get("amount") or 0))
    if not field or not budget_id or amount <= 0:
        return None
    return budget_id, field, amount


def reconcile_budget_payment_change(
    budget_rows: list[dict[str, Any]],
    previous_transaction: dict[str, Any] | None,
    updated_transaction: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    """Return copied budget rows after reversing old and applying new payment linkage.

    Does not mutate caller data. Refuses a new allocation that exceeds the
    remaining linked commitment/forecast instead of silently clipping to zero.
    """
    rows = deepcopy(budget_rows or [])
    by_id = {str(row.get("budget_item_id")): row for row in rows}

    old_adjustment = _adjustment(previous_transaction)
    if old_adjustment:
        budget_id, field, amount = old_adjustment
        prior_budget = by_id.get(budget_id)
        if prior_budget is not None:
            prior_budget[field] = max(0.0, float(prior_budget.get(field) or 0)) + amount

    new_adjustment = _adjustment(updated_transaction)
    if new_adjustment:
        budget_id, field, amount = new_adjustment
        next_budget = by_id.get(budget_id)
        if next_budget is None:
            return rows, "Item anggaran yang ditautkan tidak ditemukan. Pilih item anggaran yang masih aktif atau lepaskan tautannya."
        available = max(0.0, float(next_budget.get(field) or 0))
        if amount > available:
            label = "komitmen belum dibayar" if field == "committed_unpaid" else "forecast tersisa"
            return rows, f"Nominal pembayaran ({amount:,.0f}) melebihi {label} yang tersedia ({available:,.0f}). Periksa nominal atau perbarui anggaran terlebih dahulu."
        next_budget[field] = available - amount

    return rows, None
