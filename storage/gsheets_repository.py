"""Google Sheets persistence adapter. Uses one private spreadsheet + service account."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import uuid
from typing import Any

import gspread
from gspread.exceptions import WorksheetNotFound

SCHEMA: dict[str, list[str]] = {
    "MASTER_OBJEK": [
        "object_id", "created_at", "updated_at", "lot_code", "auction_office", "seller", "auction_type",
        "auction_date", "auction_time", "deposit_deadline", "payment_deadline", "auction_url", "auction_object_description", "name", "complex_name", "address", "district", "province",
        "auction_limit", "deposit_amount", "bid_increment", "njop", "certificate_type", "certificate_no", "rights_expiry",
        "land_area", "building_area", "bedrooms", "bathrooms", "property_type", "legal_status", "identity_verified",
        "title_match", "dispute_detected", "property_notes", "risk_adjusted_ceiling",
    ],
    "SURVEI": [
        "object_id", "updated_at", "survey_date", "surveyor", "occupancy_status", "occupancy_verified",
        "physical_condition", "exterior_inspected", "interior_inspected", "road_width_m", "access_type", "flood_history",
        "structure", "roof", "damp", "electricity", "water", "physical_notes", "photo_links",
    ],
    "BIAYA_RISIKO": [
        "object_id", "updated_at", "buyer_auction_fee_pct", "bphtb_rate_pct", "npoptkp", "bphtb_basis_mode",
        "ppn_applicable", "ppn_rate_pct", "seller_tax_pct", "selling_agent_pct", "tax_rules_verified",
        "certificate_legal_cost", "renovation_cost", "arrears_utilities_cost", "selected_possession_scenario",
        "monthly_holding_cost", "renovation_months", "sale_months_after_ready", "contingency_pct", "marketing_cost",
        "other_presale_cost", "other_selling_cost", "minimum_net_profit", "minimum_roi_pct",
        "minimum_profit_per_month", "maximum_holding_months", "annual_opportunity_cost_pct",
        "conservative_haircut_pct", "optimistic_premium_pct", "score_liquidity", "score_legal", "score_possession",
        "score_physical", "score_funding", "score_environment",
    ],
    "COMPARABLES": [
        "row_id", "object_id", "analysis_id", "active", "complex", "address", "distance_km", "land_area",
        "building_area", "price", "price_type", "condition", "property_type", "certificate", "date_found",
        "source_url", "notes",
    ],
    "SKENARIO_PENGUASAAN": [
        "row_id", "object_id", "analysis_id", "active", "scenario_key", "label", "expected_cost",
        "delay_months", "reserve_cost", "notes",
    ],
    "INVESTOR": [
        "profile_id", "updated_at", "baseline_cash", "baseline_date", "ongoing_commitments", "household_reserve",
        "risk_reserve", "receivables_not_received", "notes", "profile_confirmed",
    ],
    "CASHFLOW": [
        "entry_id", "created_at", "transaction_date", "direction", "category", "description", "amount",
        "object_id", "notes",
    ],
    "ANALISIS": [
        "analysis_id", "object_id", "analyzed_at", "decision", "eligibility_score_pct", "auction_limit",
        "conservative_exit", "base_exit", "optimistic_exit", "net_profit_conservative", "roi_conservative_pct",
        "net_profit_base", "roi_base_pct", "holding_months", "required_cash", "available_for_project",
        "recommended_max_bid", "absolute_max_bid", "market_confidence", "blockers", "warnings", "snapshot_json",
    ],
    "RIWAYAT": ["timestamp", "entity", "entity_id", "action", "details"],
}



def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _clean(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (dict, list)):
        return _json(value)
    return value


def _retry_google_call(fn, *args, **kwargs):
    """Retry transient Google API 429/5xx responses with capped exponential backoff."""
    import random
    import time

    retryable = {429, 500, 502, 503, 504}
    for attempt in range(4):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            # gspread.APIError commonly exposes response.status_code;
            # googleapiclient HttpError exposes resp.status and code.
            response = getattr(exc, "response", None)
            response = response or getattr(exc, "resp", None)
            status = (
                getattr(response, "status_code", None)
                or getattr(response, "status", None)
                or getattr(exc, "status_code", None)
                or getattr(exc, "code", None)
            )
            try:
                status = int(status) if status is not None else None
            except (TypeError, ValueError):
                status = None
            if status not in retryable or attempt == 3:
                raise
            retry_after = None
            headers = getattr(response, "headers", None) or {}
            try:
                retry_after = float(headers.get("Retry-After")) if headers.get("Retry-After") else None
            except (TypeError, ValueError):
                retry_after = None
            delay = retry_after if retry_after is not None else min(8.0, 0.8 * (2 ** attempt))
            time.sleep(max(0.0, delay) + random.uniform(0.0, 0.25))


class GoogleSheetsRepository:
    """Quota-aware GSheets repository.

    Reads are cached per process for 20 seconds; multi-tab reads and writes use the
    Sheets values batch endpoints so a save is normally one read + one write request.
    """

    CACHE_TTL_SECONDS = 20.0

    def __init__(self, spreadsheet_id: str, service_account_info: dict[str, Any]):
        import time
        if not spreadsheet_id:
            raise ValueError("SPREADSHEET_ID belum diatur.")
        credentials = dict(service_account_info)
        private_key = credentials.get("private_key")
        if isinstance(private_key, str):
            credentials["private_key"] = private_key.replace("\\n", "\n")
        self.client = _retry_google_call(gspread.service_account_from_dict, credentials)
        self.book = _retry_google_call(self.client.open_by_key, spreadsheet_id)
        self._worksheet_cache: dict[str, Any] = {}
        self._raw_cache: dict[str, list[list[str]]] = {}
        self._cache_time: dict[str, float] = {}
        self._time = time
        self.ensure_schema()

    def ensure_schema(self) -> None:
        # Worksheet metadata is loaded once, instead of looking up each tab separately.
        worksheets = _retry_google_call(self.book.worksheets)
        self._worksheet_cache = {ws.title: ws for ws in worksheets}
        created: list[str] = []
        for title, headers in SCHEMA.items():
            if title not in self._worksheet_cache:
                ws = _retry_google_call(
                    self.book.add_worksheet,
                    title=title,
                    rows=1000,
                    cols=max(20, len(headers)),
                )
                self._worksheet_cache[title] = ws
                created.append(title)

        # Read all header rows in a single API call.
        header_ranges = [f"'{title}'!A1:{_col(len(headers))}1" for title, headers in SCHEMA.items()]
        response = _retry_google_call(self.book.values_batch_get, header_ranges)
        value_ranges = response.get("valueRanges", [])
        header_updates = []
        for (title, headers), item in zip(SCHEMA.items(), value_ranges):
            values = item.get("values", [])
            existing = values[0] if values else []
            if not existing:
                header_updates.append({
                    "range": f"'{title}'!A1:{_col(len(headers))}1",
                    "values": [headers],
                })
            elif existing[:len(headers)] != headers:
                raise RuntimeError(
                    f"Header tab {title} tidak sesuai template. Jangan mengubah nama/urutan kolom; "
                    "gunakan spreadsheet baru atau samakan header dengan template aplikasi."
                )
        if header_updates:
            _retry_google_call(
                self.book.values_batch_update,
                {"valueInputOption": "RAW", "data": header_updates},
            )
        # Header rows are now known; clear stale reads if the repository is reinitialised.
        self._raw_cache.clear()
        self._cache_time.clear()

    def _ws(self, name: str):
        try:
            return self._worksheet_cache[name]
        except KeyError as exc:
            raise KeyError(f"Tab Google Sheets tidak dikenal: {name}") from exc

    def _raw_values_many(self, names: list[str], *, force_refresh: bool = False) -> dict[str, list[list[str]]]:
        now = self._time.monotonic()
        unique = list(dict.fromkeys(names))
        missing = [
            name for name in unique
            if force_refresh
            or name not in self._raw_cache
            or now - self._cache_time.get(name, 0.0) > self.CACHE_TTL_SECONDS
        ]
        if missing:
            ranges = [f"'{name}'!A:{_col(len(SCHEMA[name]))}" for name in missing]
            response = _retry_google_call(self.book.values_batch_get, ranges)
            value_ranges = response.get("valueRanges", [])
            for name, item in zip(missing, value_ranges):
                values = item.get("values", []) or []
                # Normalise each row to strings without manufacturing trailing rows.
                self._raw_cache[name] = [[str(cell) for cell in row] for row in values]
                self._cache_time[name] = now
        return {name: self._raw_cache.get(name, []) for name in unique}

    @staticmethod
    def _to_records(values: list[list[str]]) -> list[dict[str, Any]]:
        if not values:
            return []
        headers = values[0]
        result: list[dict[str, Any]] = []
        for row in values[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            padded = row + [""] * max(0, len(headers) - len(row))
            result.append(dict(zip(headers, padded[:len(headers)])))
        return result

    def records_many(self, names: list[str], *, force_refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
        raw = self._raw_values_many(names, force_refresh=force_refresh)
        return {name: self._to_records(raw.get(name, [])) for name in dict.fromkeys(names)}

    def records(self, name: str, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        return self.records_many([name], force_refresh=force_refresh)[name]

    def _row_number(self, name: str, key_col: str, key_value: str, raw: list[list[str]]) -> int:
        headers = SCHEMA[name]
        key_idx = headers.index(key_col)
        for row_no, row in enumerate(raw[1:], start=2):
            padded = row + [""] * max(0, len(headers) - len(row))
            if str(padded[key_idx]) == str(key_value):
                return row_no
        # The next physical row after the last non-empty values row.
        return max(2, len(raw) + 1)

    def _batch_write(self, updates: list[dict[str, Any]]) -> None:
        if not updates:
            return
        _retry_google_call(
            self.book.values_batch_update,
            {"valueInputOption": "RAW", "data": updates},
        )
        self._invalidate_cache([self._sheet_name_from_range(item["range"]) for item in updates])

    @staticmethod
    def _sheet_name_from_range(a1_range: str) -> str:
        return a1_range.split("!", 1)[0].strip("'")

    def _invalidate_cache(self, names: list[str]) -> None:
        for name in names:
            self._raw_cache.pop(name, None)
            self._cache_time.pop(name, None)

    def clear_cache(self) -> None:
        """Force the next repository read to fetch current values from Google Sheets."""
        self._raw_cache.clear()
        self._cache_time.clear()

    def _upsert(self, name: str, key_col: str, key_value: str, row_dict: dict[str, Any]) -> None:
        raw = self._raw_values_many([name], force_refresh=True)[name]
        headers = SCHEMA[name]
        row_num = self._row_number(name, key_col, key_value, raw)
        values = [_clean(row_dict.get(header, "")) for header in headers]
        self._batch_write([{
            "range": f"'{name}'!A{row_num}:{_col(len(headers))}{row_num}",
            "values": [values],
        }])

    def _append_updates(self, name: str, rows: list[list[Any]], raw: list[list[str]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        start = max(2, len(raw) + 1)
        end = start + len(rows) - 1
        return [{
            "range": f"'{name}'!A{start}:{_col(len(SCHEMA[name]))}{end}",
            "values": rows,
        }]

    def save_investor_profile(self, profile: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = {"profile_id": "MAIN", **profile, "updated_at": now}
        raw = self._raw_values_many(["INVESTOR", "RIWAYAT"], force_refresh=True)
        row_no = self._row_number("INVESTOR", "profile_id", "MAIN", raw["INVESTOR"])
        profile_values = [_clean(row.get(h, "")) for h in SCHEMA["INVESTOR"]]
        updates = [{
            "range": f"'INVESTOR'!A{row_no}:{_col(len(SCHEMA['INVESTOR']))}{row_no}",
            "values": [profile_values],
        }]
        history = [[now, "INVESTOR", "MAIN", "UPDATE_PROFILE", "Profil kas investor diperbarui"]]
        updates += self._append_updates("RIWAYAT", history, raw["RIWAYAT"])
        self._batch_write(updates)

    def get_investor_profile(self) -> dict[str, Any] | None:
        rows = self.records("INVESTOR")
        return next((r for r in rows if r.get("profile_id") == "MAIN"), None)

    def add_cashflow(self, entry: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = {"entry_id": str(uuid.uuid4()), "created_at": now, **entry}
        raw = self._raw_values_many(["CASHFLOW", "RIWAYAT"], force_refresh=True)
        cash_rows = [[_clean(row.get(h, "")) for h in SCHEMA["CASHFLOW"]]]
        history = [[now, "CASHFLOW", row["entry_id"], "ADD_TRANSACTION", f"{entry.get('direction')} {entry.get('amount')}"]]
        updates = self._append_updates("CASHFLOW", cash_rows, raw["CASHFLOW"])
        updates += self._append_updates("RIWAYAT", history, raw["RIWAYAT"])
        self._batch_write(updates)

    def get_cashflow(self) -> list[dict[str, Any]]:
        return self.records("CASHFLOW")

    def save_analysis(self, snapshot: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        p = snapshot.get("inputs", {}).get("property", {})
        s = snapshot.get("inputs", {}).get("survey", {})
        f = snapshot.get("inputs", {}).get("fees", {})
        c = snapshot.get("inputs", {}).get("costs", {})
        t = snapshot.get("inputs", {}).get("targets", {})
        r = snapshot.get("inputs", {}).get("risk_scores", {})
        object_id = str(snapshot.get("object_id", ""))
        if not object_id:
            raise ValueError("object_id wajib tersedia sebelum menyimpan analisis.")
        analysis_id = str(snapshot.get("analysis_id", uuid.uuid4()))

        names = ["MASTER_OBJEK", "SURVEI", "BIAYA_RISIKO", "COMPARABLES", "SKENARIO_PENGUASAAN", "ANALISIS", "RIWAYAT"]
        raw = self._raw_values_many(names, force_refresh=True)
        updates: list[dict[str, Any]] = []

        master = {"object_id": object_id, "created_at": snapshot.get("created_at", now), "updated_at": now, **p}
        survey = {"object_id": object_id, "updated_at": now, **s}
        cost_row = {
            "object_id": object_id, "updated_at": now, **f, **c, **t,
            "score_liquidity": r.get("liquidity", 3), "score_legal": r.get("legal", 3),
            "score_possession": r.get("possession", 3), "score_physical": r.get("physical", 3),
            "score_funding": r.get("funding", 3), "score_environment": r.get("environment", 3),
        }
        for name, key, row_dict in [
            ("MASTER_OBJEK", "object_id", master),
            ("SURVEI", "object_id", survey),
            ("BIAYA_RISIKO", "object_id", cost_row),
        ]:
            row_no = self._row_number(name, key, object_id, raw[name])
            values = [_clean(row_dict.get(h, "")) for h in SCHEMA[name]]
            updates.append({
                "range": f"'{name}'!A{row_no}:{_col(len(SCHEMA[name]))}{row_no}",
                "values": [values],
            })

        # Historical comparable/scenario rows are immutable. Re-analysis loads only rows
        # whose analysis_id matches the latest ANALISIS record for this object.
        comp_rows = []
        for comp in snapshot.get("inputs", {}).get("comparables", []) or []:
            record = {"row_id": str(uuid.uuid4()), "object_id": object_id, "analysis_id": analysis_id, "active": True, **comp}
            comp_rows.append([_clean(record.get(h, "")) for h in SCHEMA["COMPARABLES"]])
        scenario_rows = []
        for key, item in (snapshot.get("inputs", {}).get("possession_scenarios", {}) or {}).items():
            record = {
                "row_id": str(uuid.uuid4()), "object_id": object_id, "analysis_id": analysis_id,
                "active": True, "scenario_key": key, "label": item.get("label", key),
                "expected_cost": item.get("cost", 0), "delay_months": item.get("delay_months", 0),
                "reserve_cost": item.get("reserve_cost", 0), "notes": item.get("notes", ""),
            }
            scenario_rows.append([_clean(record.get(h, "")) for h in SCHEMA["SKENARIO_PENGUASAAN"]])

        results = snapshot.get("results", {})
        conservative = results.get("conservative_at_limit", {})
        base = results.get("base_at_limit", {})
        recommended = results.get("recommended_max_bid", {})
        absolute = results.get("absolute_max_bid", {})
        market = snapshot.get("market", {})
        decision = snapshot.get("decision", {})
        row = {
            "analysis_id": analysis_id, "object_id": object_id, "analyzed_at": snapshot.get("analyzed_at", now),
            "decision": decision.get("status", "HOLD"),
            "eligibility_score_pct": snapshot.get("suitability", {}).get("score_pct", 0),
            "auction_limit": p.get("auction_limit", 0),
            "conservative_exit": market.get("conservative_exit", 0), "base_exit": market.get("base_exit", 0),
            "optimistic_exit": market.get("optimistic_exit", 0),
            "net_profit_conservative": conservative.get("net_profit", 0), "roi_conservative_pct": conservative.get("roi_pct", 0),
            "net_profit_base": base.get("net_profit", 0), "roi_base_pct": base.get("roi_pct", 0),
            "holding_months": base.get("total_holding_months", 0),
            "required_cash": base.get("pre_sale_investment", 0), "available_for_project": base.get("available_for_project", 0),
            "recommended_max_bid": recommended.get("maximum_bid", ""),
            "absolute_max_bid": absolute.get("maximum_bid", ""), "market_confidence": market.get("confidence", 0),
            "blockers": " | ".join(decision.get("blockers", []) or []),
            "warnings": " | ".join(decision.get("warnings", []) or []), "snapshot_json": snapshot,
        }
        analysis_values = [_clean(row.get(h, "")) for h in SCHEMA["ANALISIS"]]
        history_values = [[now, "OBJEK", object_id, "SAVE_ANALYSIS", f"{decision.get('status')} · {snapshot.get('suitability', {}).get('score_pct', 0)}%"]]
        updates += self._append_updates("COMPARABLES", comp_rows, raw["COMPARABLES"])
        updates += self._append_updates("SKENARIO_PENGUASAAN", scenario_rows, raw["SKENARIO_PENGUASAAN"])
        updates += self._append_updates("ANALISIS", [analysis_values], raw["ANALISIS"])
        updates += self._append_updates("RIWAYAT", history_values, raw["RIWAYAT"])
        self._batch_write(updates)

    def log(self, entity: str, entity_id: str, action: str, details: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        raw = self._raw_values_many(["RIWAYAT"], force_refresh=True)["RIWAYAT"]
        self._batch_write(self._append_updates("RIWAYAT", [[now, entity, entity_id, action, details]], raw))

    def list_latest_snapshots(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in self.records("ANALISIS"):
            raw = row.get("snapshot_json", "")
            if not raw:
                continue
            try:
                snapshot = json.loads(raw)
            except (ValueError, TypeError):
                continue
            oid = str(snapshot.get("object_id") or row.get("object_id") or "")
            stamp = str(snapshot.get("analyzed_at") or row.get("analyzed_at") or "")
            if oid and (oid not in latest or stamp > str(latest[oid].get("analyzed_at", ""))):
                latest[oid] = snapshot
        return list(latest.values())

    def load_object_inputs(self, object_id: str) -> dict[str, Any]:
        names = ["MASTER_OBJEK", "SURVEI", "BIAYA_RISIKO", "COMPARABLES", "SKENARIO_PENGUASAAN", "ANALISIS"]
        records = self.records_many(names, force_refresh=True)
        master = next((r for r in records["MASTER_OBJEK"] if r.get("object_id") == object_id), None)
        survey = next((r for r in records["SURVEI"] if r.get("object_id") == object_id), None)
        costs = next((r for r in records["BIAYA_RISIKO"] if r.get("object_id") == object_id), None)
        latest_analysis = max(
            (r for r in records["ANALISIS"] if r.get("object_id") == object_id),
            key=lambda r: str(r.get("analyzed_at", "")),
            default=None,
        )
        if not master or not survey or not costs:
            raise ValueError("Data objek tidak lengkap di MASTER_OBJEK/SURVEI/BIAYA_RISIKO.")
        latest_analysis_id = str((latest_analysis or {}).get("analysis_id", ""))
        comps = [r for r in records["COMPARABLES"] if r.get("object_id") == object_id and str(r.get("analysis_id", "")) == latest_analysis_id]
        scenarios = [r for r in records["SKENARIO_PENGUASAAN"] if r.get("object_id") == object_id and str(r.get("analysis_id", "")) == latest_analysis_id]
        from core.sheets_rebuild import rebuild_inputs_from_sheets
        return rebuild_inputs_from_sheets(master, survey, costs, comps, scenarios)


def _col(n: int) -> str:
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result
