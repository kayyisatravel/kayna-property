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


class GoogleSheetsRepository:
    def __init__(self, spreadsheet_id: str, service_account_info: dict[str, Any]):
        if not spreadsheet_id:
            raise ValueError("SPREADSHEET_ID belum diatur.")
        credentials = dict(service_account_info)
        private_key = credentials.get("private_key")
        if isinstance(private_key, str):
            # Accept both actual multiline TOML values and JSON-style escaped \n sequences.
            credentials["private_key"] = private_key.replace("\\n", "\n")
        self.client = gspread.service_account_from_dict(credentials)
        self.book = self.client.open_by_key(spreadsheet_id)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        for title, headers in SCHEMA.items():
            try:
                ws = self.book.worksheet(title)
            except WorksheetNotFound:
                ws = self.book.add_worksheet(title=title, rows=1000, cols=max(20, len(headers)))
            existing = ws.row_values(1)
            if not existing:
                ws.update(range_name=f"A1:{_col(len(headers))}1", values=[headers], value_input_option="RAW")
            elif existing[:len(headers)] != headers:
                raise RuntimeError(
                    f"Header tab {title} tidak sesuai template. Jangan mengubah nama/urutan kolom; "
                    "gunakan sheet baru atau samakan header dengan template aplikasi."
                )

    def _ws(self, name: str):
        return self.book.worksheet(name)

    def records(self, name: str) -> list[dict[str, Any]]:
        ws = self._ws(name)
        values = ws.get_all_values()
        if not values:
            return []
        headers = values[0]
        result: list[dict[str, Any]] = []
        for row in values[1:]:
            if not any(str(x).strip() for x in row):
                continue
            padded = row + [""] * (len(headers) - len(row))
            result.append(dict(zip(headers, padded[:len(headers)])))
        return result

    def _upsert(self, name: str, key_col: str, key_value: str, row_dict: dict[str, Any]) -> None:
        headers = SCHEMA[name]
        ws = self._ws(name)
        values = [_clean(row_dict.get(h, "")) for h in headers]
        key_idx = headers.index(key_col) + 1
        matches = ws.findall(str(key_value), in_column=key_idx)
        if matches:
            row_number = matches[0].row
            ws.update(range_name=f"A{row_number}:{_col(len(headers))}{row_number}", values=[values], value_input_option="RAW")
        else:
            ws.append_row(values, value_input_option="RAW")

    def save_investor_profile(self, profile: dict[str, Any]) -> None:
        row = {"profile_id": "MAIN", **profile, "updated_at": datetime.now(timezone.utc).isoformat()}
        self._upsert("INVESTOR", "profile_id", "MAIN", row)
        self.log("INVESTOR", "MAIN", "UPDATE_PROFILE", "Profil kas investor diperbarui")

    def get_investor_profile(self) -> dict[str, Any] | None:
        rows = self.records("INVESTOR")
        return next((r for r in rows if r.get("profile_id") == "MAIN"), None)

    def add_cashflow(self, entry: dict[str, Any]) -> None:
        row = {"entry_id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **entry}
        ws = self._ws("CASHFLOW")
        ws.append_row([_clean(row.get(h, "")) for h in SCHEMA["CASHFLOW"]], value_input_option="RAW")
        self.log("CASHFLOW", row["entry_id"], "ADD_TRANSACTION", f"{entry.get('direction')} {entry.get('amount')}")

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
        analysis_id = str(snapshot.get("analysis_id", uuid.uuid4()))

        master = {
            "object_id": object_id, "created_at": snapshot.get("created_at", now), "updated_at": now,
            **p,
        }
        self._upsert("MASTER_OBJEK", "object_id", object_id, master)
        survey = {"object_id": object_id, "updated_at": now, **s}
        self._upsert("SURVEI", "object_id", object_id, survey)

        cost_row = {
            "object_id": object_id, "updated_at": now, **f, **c, **t,
            "score_liquidity": r.get("liquidity", 3), "score_legal": r.get("legal", 3),
            "score_possession": r.get("possession", 3), "score_physical": r.get("physical", 3),
            "score_funding": r.get("funding", 3), "score_environment": r.get("environment", 3),
        }
        self._upsert("BIAYA_RISIKO", "object_id", object_id, cost_row)

        # Mark prior comparable/scenario rows inactive for this object; the new analysis becomes current.
        for sheet_name in ("COMPARABLES", "SKENARIO_PENGUASAAN"):
            ws = self._ws(sheet_name)
            headers = SCHEMA[sheet_name]
            object_col = headers.index("object_id") + 1
            active_col = headers.index("active") + 1
            values = ws.get_all_values()
            to_update = []
            for row_no, row in enumerate(values[1:], 2):
                padded = row + [""] * (len(headers) - len(row))
                if padded[object_col - 1] == object_id and str(padded[active_col - 1]).upper() == "TRUE":
                    to_update.append({"range": f"{_col(active_col)}{row_no}", "values": [["FALSE"]]})
            if to_update:
                ws.batch_update(to_update, value_input_option="RAW")

        comp_ws = self._ws("COMPARABLES")
        comp_rows = []
        for comp in snapshot.get("inputs", {}).get("comparables", []) or []:
            row = {
                "row_id": str(uuid.uuid4()), "object_id": object_id, "analysis_id": analysis_id, "active": True,
                **comp,
            }
            comp_rows.append([_clean(row.get(h, "")) for h in SCHEMA["COMPARABLES"]])
        if comp_rows:
            comp_ws.append_rows(comp_rows, value_input_option="RAW")

        scenario_ws = self._ws("SKENARIO_PENGUASAAN")
        scenario_rows = []
        for key, item in (snapshot.get("inputs", {}).get("possession_scenarios", {}) or {}).items():
            row = {
                "row_id": str(uuid.uuid4()), "object_id": object_id, "analysis_id": analysis_id,
                "active": True, "scenario_key": key, "label": item.get("label", key),
                "expected_cost": item.get("cost", 0), "delay_months": item.get("delay_months", 0),
                "reserve_cost": item.get("reserve_cost", 0), "notes": item.get("notes", ""),
            }
            scenario_rows.append([_clean(row.get(h, "")) for h in SCHEMA["SKENARIO_PENGUASAAN"]])
        if scenario_rows:
            scenario_ws.append_rows(scenario_rows, value_input_option="RAW")

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
            "warnings": " | ".join(decision.get("warnings", []) or []),
            "snapshot_json": snapshot,
        }
        analysis_ws = self._ws("ANALISIS")
        analysis_ws.append_row([_clean(row.get(h, "")) for h in SCHEMA["ANALISIS"]], value_input_option="RAW")
        self.log("OBJEK", object_id, "SAVE_ANALYSIS", f"{decision.get('status')} · {snapshot.get('suitability', {}).get('score_pct', 0)}%")

    def log(self, entity: str, entity_id: str, action: str, details: str) -> None:
        row = [datetime.now(timezone.utc).isoformat(), entity, entity_id, action, details]
        self._ws("RIWAYAT").append_row(row, value_input_option="RAW")

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
        master = next((r for r in self.records("MASTER_OBJEK") if r.get("object_id") == object_id), None)
        survey = next((r for r in self.records("SURVEI") if r.get("object_id") == object_id), None)
        costs = next((r for r in self.records("BIAYA_RISIKO") if r.get("object_id") == object_id), None)
        if not master or not survey or not costs:
            raise ValueError("Data objek tidak lengkap di MASTER_OBJEK/SURVEI/BIAYA_RISIKO.")
        comps = [r for r in self.records("COMPARABLES") if r.get("object_id") == object_id and str(r.get("active", "")).upper() == "TRUE"]
        scenarios = [r for r in self.records("SKENARIO_PENGUASAAN") if r.get("object_id") == object_id and str(r.get("active", "")).upper() == "TRUE"]
        from core.sheets_rebuild import rebuild_inputs_from_sheets
        return rebuild_inputs_from_sheets(master, survey, costs, comps, scenarios)


def _col(n: int) -> str:
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result
