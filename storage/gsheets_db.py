"""Google Sheets CRUD adapter. One spreadsheet, normalized tabs, cached reads in app.py."""
from __future__ import annotations
from datetime import datetime
from typing import Any
import json
import random
import time
import gspread
from gspread.exceptions import WorksheetNotFound
from core.utils import safe_json, sheet_cell_value, new_id

SCHEMA: dict[str, list[str]] = {
    "PROPERTIES": ["property_id", "created_at", "updated_at", "lot_code", "name", "address", "auction_date", "auction_limit", "decision_status", "lifecycle_status", "payload_json"],
    "SURVEYS": ["survey_id", "property_id", "updated_at", "survey_status", "occupancy_status", "payload_json"],
    "COMPARABLES": ["comparable_id", "property_id", "analysis_id", "name", "price", "land_area", "building_area", "price_type", "source_url", "date_found", "payload_json"],
    "COST_ESTIMATES": ["estimate_id", "property_id", "analysis_id", "updated_at", "payload_json"],
    "RISK_REGISTER": ["risk_id", "property_id", "analysis_id", "category", "risk_description", "probability_1_5", "impact_1_5", "severity_score", "cost_reserve", "critical", "mitigation", "status", "created_at"],
    "COST_ACTUALS": ["actual_id", "property_id", "transaction_date", "category", "amount", "description", "receipt_url", "created_at"],
    "CASH_POSITION": ["profile_id", "updated_at", "real_cash", "reserve_pct", "payload_json"],
    "CASHFLOW_EVENTS": ["event_id", "profile_id", "property_id", "outflow_date", "direction", "amount", "description", "confirmed", "created_at"],
    "PROJECT_MILESTONES": ["milestone_id", "property_id", "stage", "status", "planned_date", "actual_date", "notes", "updated_at"],
    "ANALYSIS_HISTORY": ["analysis_id", "property_id", "analyzed_at", "decision_status", "eligibility_index_pct", "conservative_arv", "max_bid", "roi_at_limit_pct", "payload_json"],
    "SALES_CLOSING": ["property_id", "sold_date", "listing_start_date", "closing_price", "selling_cost_actual", "total_holding_months", "notes", "updated_at", "payload_json"],
    "RULES_CONFIG": ["rule_key", "value_json", "updated_at", "source_note"],
    "DOCUMENTS": ["document_id", "property_id", "file_name", "mime_type", "source_url", "document_hash", "uploaded_at", "notes", "extraction_json"],
    "HISTORY": ["history_id", "timestamp", "entity", "entity_id", "action", "details_json"],
}


def _col(n: int) -> str:
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _as_bool(v: Any) -> bool:
    return v is True or str(v).strip().lower() in {"true", "1", "yes", "ya"}


def _retry_google(fn, *args, **kwargs):
    """Truncated exponential backoff for Google Sheets 429 and transient 5xx."""
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(4):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            response = getattr(exc, "response", None) or getattr(exc, "resp", None)
            status = getattr(response, "status_code", None) or getattr(response, "status", None) or getattr(exc, "code", None)
            try: status = int(status) if status is not None else None
            except (TypeError, ValueError): status = None
            if status not in retryable or attempt == 3: raise
            headers = getattr(response, "headers", {}) or {}
            try: delay = float(headers.get("Retry-After")) if headers.get("Retry-After") else min(8.0, 0.8 * (2 ** attempt))
            except (TypeError, ValueError): delay = min(8.0, 0.8 * (2 ** attempt))
            time.sleep(delay + random.uniform(0, 0.25))


class GoogleSheetsDB:
    CACHE_TTL_SECONDS = 300

    def __init__(self, spreadsheet_id: str, service_account_info: dict[str, Any]):
        if not spreadsheet_id:
            raise ValueError("SPREADSHEET_ID belum diisi.")
        credentials = dict(service_account_info)
        if isinstance(credentials.get("private_key"), str):
            credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        self.client = _retry_google(gspread.service_account_from_dict, credentials)
        self.book = _retry_google(self.client.open_by_key, spreadsheet_id)
        self.sheets: dict[str, Any] = {}
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.sheets = {ws.title: ws for ws in _retry_google(self.book.worksheets)}
        for title, headers in SCHEMA.items():
            if title not in self.sheets:
                self.sheets[title] = _retry_google(self.book.add_worksheet, title=title, rows=2000, cols=max(20, len(headers)))
            ws = self.sheets[title]
            current = _retry_google(ws.row_values, 1)
            if not current:
                _retry_google(ws.update, range_name=f"A1:{_col(len(headers))}1", values=[headers], value_input_option="RAW")
            elif current[:len(headers)] == headers:
                # Exact schema or harmless extra columns to the right; keep them untouched.
                continue
            elif headers[:len(current)] == current:
                # Safe forward migration: only append newly introduced trailing columns.
                _retry_google(ws.update, range_name=f"A1:{_col(len(headers))}1", values=[headers], value_input_option="RAW")
            else:
                raise RuntimeError(f"Header tab {title} tidak sesuai template. Urutan/label kolom yang ada berbeda; jangan mengubah header secara manual.")

    def read_table(self, title: str) -> list[dict[str, Any]]:
        if title not in SCHEMA: raise KeyError(f"Tab tidak dikenal: {title}")
        rows = _retry_google(self.sheets[title].get_all_values)
        if len(rows) <= 1: return []
        headers = SCHEMA[title]
        output = []
        for row in rows[1:]:
            if not any(str(x).strip() for x in row): continue
            padded = row + [""] * (len(headers) - len(row))
            record = dict(zip(headers, padded[:len(headers)]))
            if "payload_json" in record:
                try: record["payload"] = json.loads(record.get("payload_json") or "{}")
                except Exception: record["payload"] = {}
            if "value_json" in record:
                try: record["value"] = json.loads(record.get("value_json") or "null")
                except Exception: record["value"] = None
            if "confirmed" in record: record["confirmed"] = _as_bool(record["confirmed"])
            output.append(record)
        return output

    def _row_values(self, title: str, record: dict[str, Any]) -> list[Any]:
        """Build strictly JSON-safe Sheets cells.

        Pandas data_editor returns NaN for blank numeric cells. gspread forwards
        row values through requests(json=...), whose JSON encoder rejects NaN/Inf.
        Sanitize every scalar (not only nested payload_json) before HTTP serialization.
        """
        if title not in SCHEMA:
            raise KeyError(title)
        values: list[Any] = []
        for col in SCHEMA[title]:
            value = record.get(col, "")
            if col == "payload_json" and "payload" in record:
                value = safe_json(record.get("payload", {}))
            elif col == "value_json" and "value" in record:
                value = safe_json(record["value"])
            else:
                value = sheet_cell_value(value)
            # Nested JSON fields are also normalized with allow_nan=False by safe_json.
            values.append(value)
        return values

    def append_record(self, title: str, record: dict[str, Any]) -> dict[str, Any]:
        if title not in SCHEMA: raise KeyError(title)
        row = self._row_values(title, record)
        _retry_google(self.sheets[title].append_row, row, value_input_option="RAW")
        return record

    def append_records(self, title: str, records: list[dict[str, Any]]) -> None:
        if not records: return
        _retry_google(self.sheets[title].append_rows, [self._row_values(title, r) for r in records], value_input_option="RAW")

    def upsert_record(self, title: str, key_field: str, record: dict[str, Any]) -> dict[str, Any]:
        rows = self.read_table(title)
        key = str(record.get(key_field, ""))
        ws = self.sheets[title]
        for idx, old in enumerate(rows, start=2):
            if str(old.get(key_field, "")) == key and key:
                end = _col(len(SCHEMA[title]))
                _retry_google(ws.update, range_name=f"A{idx}:{end}{idx}", values=[self._row_values(title, record)], value_input_option="RAW")
                return record
        self.append_record(title, record)
        return record

    def save_property(self, record: dict[str, Any]) -> None:
        self.upsert_record("PROPERTIES", "property_id", record)

    def save_analysis(self, record: dict[str, Any]) -> None:
        self.append_record("ANALYSIS_HISTORY", record)

    def save_comparables(self, records: list[dict[str, Any]]) -> None:
        self.append_records("COMPARABLES", records)

    def save_survey(self, record: dict[str, Any]) -> None:
        self.append_record("SURVEYS", record)

    def save_cost_estimate(self, record: dict[str, Any]) -> None:
        self.append_record("COST_ESTIMATES", record)

    def save_actual_cost(self, record: dict[str, Any]) -> None:
        self.append_record("COST_ACTUALS", record)

    def save_cash_position(self, record: dict[str, Any]) -> None:
        self.upsert_record("CASH_POSITION", "profile_id", record)

    def save_cashflow_event(self, record: dict[str, Any]) -> None:
        self.append_record("CASHFLOW_EVENTS", record)

    def save_milestone(self, record: dict[str, Any]) -> None:
        # Composite key is handled manually to keep one current milestone per property/stage.
        rows = self.read_table("PROJECT_MILESTONES")
        ws = self.sheets["PROJECT_MILESTONES"]
        for idx, old in enumerate(rows, start=2):
            if str(old.get("property_id")) == str(record.get("property_id")) and str(old.get("stage")) == str(record.get("stage")):
                _retry_google(ws.update, range_name=f"A{idx}:H{idx}", values=[self._row_values("PROJECT_MILESTONES", record)], value_input_option="RAW")
                return
        self.append_record("PROJECT_MILESTONES", record)

    def save_closing(self, record: dict[str, Any]) -> None:
        self.upsert_record("SALES_CLOSING", "property_id", record)

    def save_document(self, record: dict[str, Any]) -> None:
        self.append_record("DOCUMENTS", record)

    def log(self, entity: str, entity_id: str, action: str, details: dict[str, Any] | None = None) -> None:
        from core.utils import iso_now
        self.append_record("HISTORY", {"history_id": new_id("LOG"), "timestamp": iso_now(), "entity": entity, "entity_id": entity_id, "action": action, "details_json": safe_json(details or {})})

    def refresh(self) -> None:
        # gspread does not keep local worksheet values cached; Streamlit cache is cleared by caller.
        self.sheets = {ws.title: ws for ws in _retry_google(self.book.worksheets)}
