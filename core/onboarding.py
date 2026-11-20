"""Helpers for registering properties acquired before PFMS was adopted."""
from __future__ import annotations
from typing import Any
from .utils import iso_now, new_id, to_float, is_blank, normalize_text


def build_project_onboarding_records(
    *,
    property_data: dict[str, Any],
    win_details: dict[str, Any],
    project_stage: str,
    project_notes: str,
    actual_transactions: list[dict[str, Any]],
    budget_items: list[dict[str, Any]],
    existing_property: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build additive records. Existing analysis snapshots are preserved."""
    name = str(property_data.get("name") or "").strip()
    address = str(property_data.get("address") or "").strip()
    win_price = to_float(win_details.get("win_price"))
    if not name:
        raise ValueError("Nama proyek wajib diisi.")
    if not address:
        raise ValueError("Alamat proyek wajib diisi.")
    if win_price <= 0:
        raise ValueError("Harga menang/perolehan wajib lebih dari nol.")

    property_id = str((existing_property or {}).get("property_id") or new_id("PROP"))
    now = iso_now()
    old_payload = (existing_property or {}).get("payload")
    if not isinstance(old_payload, dict):
        old_payload = {}
    old_input = old_payload.get("input_data") if isinstance(old_payload.get("input_data"), dict) else {}
    old_prop = old_input.get("property") if isinstance(old_input.get("property"), dict) else {}
    merged_property = {**old_prop, **property_data}
    merged_input = {**old_input, "property": merged_property}
    payload = {
        **old_payload,
        "input_data": merged_input,
        "project_stage": project_stage,
        "project_origin": "PROJECT_ONBOARDING",
        "project_onboarding": {
            "registered_at": now,
            "historical_project": True,
            "notes": project_notes,
            "onboarding_version": "1.0.9",
        },
        "win_details": {**old_payload.get("win_details", {}), **win_details},
    }
    record = {
        "property_id": property_id,
        "created_at": (existing_property or {}).get("created_at") or now,
        "updated_at": now,
        "lot_code": merged_property.get("lot_code", ""),
        "name": name,
        "address": address,
        "auction_date": merged_property.get("auction_date", ""),
        "auction_limit": merged_property.get("auction_limit", ""),
        # INCOMPLETE means PFMS did not run a historical underwriting decision;
        # lifecycle ACTIVE reflects the real, already-acquired project state.
        "decision_status": (existing_property or {}).get("decision_status") or "INCOMPLETE",
        "lifecycle_status": "ACTIVE",
        "payload": payload,
    }

    actual_records = []
    for row in actual_transactions or []:
        amount = to_float(row.get("amount"))
        if amount <= 0 or is_blank(row.get("category")):
            continue
        actual_records.append({
            "actual_id": new_id("ACT"),
            "property_id": property_id,
            "transaction_date": str(row.get("transaction_date") or "").strip(),
            "category": str(row.get("category") or "Lainnya").strip(),
            "amount": amount,
            "description": str(row.get("description") or "").strip(),
            "receipt_url": str(row.get("receipt_url") or "").strip(),
            "created_at": now,
            "budget_item_id": str(row.get("budget_item_id") or "").strip(),
            "subcategory": str(row.get("subcategory") or "").strip(),
            "vendor": str(row.get("vendor") or "").strip(),
            "payment_method": str(row.get("payment_method") or "").strip(),
            "details_json": {"entry_source": "PROJECT_ONBOARDING"},
        })

    budget_records = []
    for row in budget_items or []:
        planned = max(0.0, to_float(row.get("budget_amount")))
        committed = max(0.0, to_float(row.get("committed_unpaid")))
        forecast = max(0.0, to_float(row.get("forecast_remaining")))
        description = str(row.get("description") or "").strip()
        if not description and planned <= 0 and committed <= 0 and forecast <= 0:
            continue
        budget_records.append({
            "budget_item_id": new_id("BUD"),
            "property_id": property_id,
            "category": str(row.get("category") or "Lainnya").strip(),
            "subcategory": str(row.get("subcategory") or "").strip(),
            "description": description,
            "budget_amount": planned,
            "committed_unpaid": committed,
            "forecast_remaining": forecast,
            "due_date": str(row.get("due_date") or "").strip(),
            "vendor": str(row.get("vendor") or "").strip(),
            "status": str(row.get("status") or "Active").strip(),
            "updated_at": now,
            "payload": {"entry_source": "PROJECT_ONBOARDING"},
        })

    # Link opening transactions to a single matching budget line when category and
    # subcategory provide enough evidence. Ambiguous rows remain unlinked for review.
    category_aliases = {
        "pelunasan/akuisisi": "akuisisi",
        "bea lelang": "bea lelang & pajak",
        "bphtb": "bea lelang & pajak",
        "bpn/legal": "bpn/legalitas",
        "penguasaan/kerahiman": "penguasaan/kerahiman",
        "selling": "penjualan",
    }
    for actual in actual_records:
        if actual.get("budget_item_id"):
            continue
        actual_category = normalize_text(actual.get("category"))
        expected_category = category_aliases.get(actual_category, actual_category)
        candidates = [b for b in budget_records if normalize_text(b.get("category")) == expected_category]
        subcategory = normalize_text(actual.get("subcategory"))
        if subcategory:
            exact = [b for b in candidates if normalize_text(b.get("subcategory")) == subcategory]
            if len(exact) == 1:
                actual["budget_item_id"] = exact[0]["budget_item_id"]
                continue
        if len(candidates) == 1:
            actual["budget_item_id"] = candidates[0]["budget_item_id"]

    return {"property": record, "actual_records": actual_records, "budget_records": budget_records, "property_id": property_id}
