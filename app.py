from __future__ import annotations
import hashlib, hmac, json, os, uuid
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from config import APP_NAME, APP_VERSION, DEFAULT_GEMINI_MODEL, DEFAULT_RULES, OCCUPANCY_DEFAULTS, DECISION_STATUSES, LIFECYCLE_STATUSES, PROJECT_STAGES, GOOGLE_SHEETS_CACHE_TTL
from core.utils import idr, pct, safe_json, parse_json, new_id, iso_now, to_float
from core.underwriting import run_underwriting
from core.liquidity import compute_liquidity
from core.lifecycle import actual_project_summary
from core.calculator import calculate_project
from services.gemini_parser import extract_auction_document, parse_comparable_narrative, review_investment, review_portfolio, file_sha256
from services.comparable_importer import parse_comparable_paste
from storage.gsheets_db import GoogleSheetsDB, SCHEMA
from storage.drive_storage import upload_file_to_drive
from reports.report_builder import build_analysis_markdown

st.set_page_config(page_title=APP_NAME, page_icon="🏠", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container{max-width:1580px;padding-top:1.2rem;padding-bottom:3rem}
[data-testid="stMetric"]{background:rgba(15,118,110,.055);border:1px solid rgba(15,118,110,.12);padding:.75rem 1rem;border-radius:13px}
.hero{padding:1.1rem 1.3rem;border:1px solid rgba(15,118,110,.20);border-radius:18px;background:linear-gradient(115deg,rgba(15,118,110,.10),rgba(14,116,144,.035))}
.small-muted{font-size:.82rem;color:#667085}
div.stButton>button{border-radius:10px;min-height:2.55rem;font-weight:600}
div[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden}
</style>
""", unsafe_allow_html=True)

# ------------------------- Common helpers / access -------------------------
def secret(key: str, default: Any = "") -> Any:
    try:
        v = st.secrets.get(key, default)
        return default if v is None else v
    except Exception:
        return os.getenv(key, default)

APP_PASSWORD = str(secret("APP_PASSWORD", "") or "")
if APP_PASSWORD:
    if not st.session_state.get("authenticated", False):
        st.markdown(f"<div class='hero'><h2>🏠 {APP_NAME}</h2><p>Investment underwriting dan pengelolaan aset properti lelang.</p></div>", unsafe_allow_html=True)
        with st.form("login"):
            pw = st.text_input("Password aplikasi", type="password")
            submit = st.form_submit_button("Masuk", use_container_width=True)
        if submit:
            if hmac.compare_digest(pw, APP_PASSWORD): st.session_state.authenticated = True; st.rerun()
            else: st.error("Password tidak sesuai.")
        st.stop()
else:
    st.error("Aplikasi dikunci karena APP_PASSWORD belum dikonfigurasi. Tambahkan APP_PASSWORD di Streamlit Secrets sebelum melanjutkan.")
    st.stop()


def fmt_date(value: Any) -> str:
    if not value: return "—"
    return str(value)[:10]


def safe_int(v: Any, default: int = 0) -> int:
    try: return int(float(v)) if v not in (None, "") else default
    except (TypeError, ValueError): return default


def record_payload(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("payload") if isinstance(row.get("payload"), dict) else parse_json(row.get("payload_json"), {})


def budget_actual_table(estimate: dict[str, Any], actual_rows: list[dict[str, Any]]) -> pd.DataFrame:
    actual = {}
    for row in actual_rows:
        key = str(row.get("category", "Lainnya")).strip().lower()
        actual[key] = actual.get(key, 0.0) + to_float(row.get("amount"))
    acquisition_actual = actual.get("pelunasan/akuisisi", 0.0) + actual.get("bpn/legal", 0.0)
    renovation_actual = actual.get("renovasi", 0.0)
    holding_actual = actual.get("holding", 0.0)
    marketing_actual = actual.get("marketing", 0.0) + actual.get("lainnya", 0.0)
    possession_actual = actual.get("penguasaan/kerahiman", 0.0)
    selling_actual = actual.get("selling", 0.0)
    rows = [
        {"Kategori": "Acquisition + BPN/Legal", "Anggaran": to_float(estimate.get("acquisition_cost")), "Aktual": acquisition_actual},
        {"Kategori": "Possession / Kerahiman", "Anggaran": to_float(estimate.get("possession_cost")), "Aktual": possession_actual},
        {"Kategori": "Renovation + Contingency", "Anggaran": to_float(estimate.get("renovation_cost")) + to_float(estimate.get("renovation_contingency")), "Aktual": renovation_actual},
        {"Kategori": "Holding", "Anggaran": to_float(estimate.get("holding_cost")), "Aktual": holding_actual},
        {"Kategori": "Marketing + Lainnya", "Anggaran": to_float(estimate.get("other_presale_cost")), "Aktual": marketing_actual},
        {"Kategori": "Selling", "Anggaran": to_float(estimate.get("selling_cost")), "Aktual": selling_actual},
    ]
    for row in rows:
        row["Varians (Aktual - Anggaran)"] = row["Aktual"] - row["Anggaran"]
    return pd.DataFrame(rows)

# ------------------------- Google Sheets connection ------------------------
@st.cache_resource(show_spinner=False)
def connect_sheets(spreadsheet_id: str, service_json: str):
    return GoogleSheetsDB(spreadsheet_id, json.loads(service_json))

@st.cache_data(ttl=GOOGLE_SHEETS_CACHE_TTL, show_spinner=False)
def cached_read(_repo, tab: str, spreadsheet_cache_key: str):
    # Include the spreadsheet ID in the cache key; _repo itself is excluded from hashing.
    return _repo.read_table(tab)

service_info = secret("google_service_account", {})
spreadsheet_id = str(secret("SPREADSHEET_ID", "") or "")
repo: GoogleSheetsDB | None = None
db_error = ""
if service_info and spreadsheet_id:
    try:
        repo = connect_sheets(spreadsheet_id, json.dumps(dict(service_info), sort_keys=True))
    except Exception as exc: db_error = str(exc)
else:
    db_error = "Google Sheets belum dikonfigurasi. Aplikasi berjalan dalam mode sesi sementara; data tidak permanen setelah sesi berakhir."

# Session fallback allows UI and tests without live credentials.
if "local_db" not in st.session_state:
    st.session_state.local_db = {k: [] for k in SCHEMA}


def read_table(tab: str, refresh: bool = False) -> list[dict[str, Any]]:
    if repo:
        if refresh: cached_read.clear()
        return cached_read(repo, tab, spreadsheet_id)
    return list(st.session_state.local_db.get(tab, []))


def append_record(tab: str, record: dict[str, Any]):
    if repo:
        repo.append_record(tab, record); cached_read.clear()
    else: st.session_state.local_db.setdefault(tab, []).append(record)


def upsert_record(tab: str, key: str, record: dict[str, Any]):
    if repo:
        repo.upsert_record(tab, key, record); cached_read.clear()
    else:
        rows = st.session_state.local_db.setdefault(tab, [])
        for i, old in enumerate(rows):
            if str(old.get(key)) == str(record.get(key)):
                rows[i] = record; break
        else: rows.append(record)


def log_event(entity: str, entity_id: str, action: str, details: dict[str, Any] | None = None):
    rec = {"history_id": new_id("LOG"), "timestamp": iso_now(), "entity": entity, "entity_id": entity_id, "action": action, "details_json": safe_json(details or {})}
    append_record("HISTORY", rec)

# ----------------------------- Session defaults ----------------------------
if "rules_local" not in st.session_state: st.session_state.rules_local = dict(DEFAULT_RULES)
if "current_analysis" not in st.session_state: st.session_state.current_analysis = None
if "current_inputs" not in st.session_state: st.session_state.current_inputs = None
if "loaded_property_id" not in st.session_state: st.session_state.loaded_property_id = ""
if "parse_info" not in st.session_state: st.session_state.parse_info = None
if "ai_review" not in st.session_state: st.session_state.ai_review = None


def get_rules() -> dict[str, Any]:
    rules = dict(st.session_state.rules_local)
    rows = read_table("RULES_CONFIG")
    for row in rows:
        try:
            value = row.get("value") if "value" in row else json.loads(row.get("value_json", "null"))
            if row.get("rule_key") == "GLOBAL" and isinstance(value, dict): rules.update(value)
            elif row.get("rule_key"): rules[row["rule_key"]] = value
        except Exception: pass
    return rules


def get_cash_data() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    profiles = read_table("CASH_POSITION")
    profile = record_payload(profiles[-1]) if profiles else {"real_cash": 0, "reserve_pct": 20, "cash_confirmed": False}
    if profiles:
        profile.setdefault("real_cash", to_float(profiles[-1].get("real_cash")))
        profile.setdefault("reserve_pct", to_float(profiles[-1].get("reserve_pct"), 20))
    events = read_table("CASHFLOW_EVENTS")
    future = [e for e in events if str(e.get("direction", "OUT")).upper() == "OUT" and (not e.get("outflow_date") or str(e.get("outflow_date"))[:10] >= date.today().isoformat()) and str(e.get("confirmed", True)).lower() not in {"false", "0"}]
    liquidity = compute_liquidity(to_float(profile.get("real_cash")), future, to_float(profile.get("reserve_pct", 20)), 0)
    liquidity["cash_confirmed"] = bool(profile.get("cash_confirmed", False))
    return profile, events, liquidity


def list_properties() -> list[dict[str, Any]]: return read_table("PROPERTIES")

def list_analyses() -> list[dict[str, Any]]: return read_table("ANALYSIS_HISTORY")


def save_property_record(property_id: str, input_data: dict[str, Any], decision_status: str, lifecycle_status: str = "PROSPECT", latest_analysis: dict[str, Any] | None = None):
    prop = input_data.get("property", {})
    existing = next((r for r in list_properties() if str(r.get("property_id")) == property_id), None)
    existing_payload = record_payload(existing) if existing else {}
    payload = {**existing_payload, "input_data": input_data, "latest_analysis": latest_analysis or existing_payload.get("latest_analysis")}
    rec = {
        "property_id": property_id, "created_at": existing.get("created_at", iso_now()) if existing else iso_now(), "updated_at": iso_now(),
        "lot_code": prop.get("lot_code", ""), "name": prop.get("name", ""), "address": prop.get("address", ""),
        "auction_date": prop.get("auction_date", ""), "auction_limit": prop.get("auction_limit", ""),
        "decision_status": decision_status, "lifecycle_status": lifecycle_status, "payload": payload,
    }
    upsert_record("PROPERTIES", "property_id", rec)
    log_event("PROPERTY", property_id, "UPSERT", {"decision_status": decision_status, "lifecycle_status": lifecycle_status})


def set_default(key: str, value: Any):
    if key not in st.session_state: st.session_state[key] = value


# ------------------------------- Sidebar -----------------------------------
st.sidebar.markdown(f"## 🏠 {APP_NAME}")
st.sidebar.caption(f"Version {APP_VERSION}")
if repo: st.sidebar.success("Google Sheets terhubung")
else: st.sidebar.warning("Mode lokal sementara" if not db_error else db_error[:180])
GEMINI_KEY = str(secret("GEMINI_API_KEY", "") or "")
GEMINI_MODEL = str(secret("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL)
st.sidebar.caption(f"AI: {GEMINI_MODEL} · {'aktif' if GEMINI_KEY else 'API key belum diatur'}")
page = st.sidebar.radio("Navigasi", ["Executive Dashboard", "New Auction Analysis", "Investor Cashflow", "Portfolio Comparison", "Active Properties", "Closed Projects & Track Record", "Database & History", "Settings & Rules"])
if st.sidebar.button("↻ Refresh Data", use_container_width=True):
    cached_read.clear()
    st.rerun()
st.sidebar.markdown("---")
st.sidebar.caption("Sell First Before Buying · Python financial engine · Gemini reviewer")

# ============================ PAGE 1: DASHBOARD ============================
if page == "Executive Dashboard":
    st.markdown(f"<div class='hero'><h1>Executive Dashboard</h1><p>Ringkasan peluang, likuiditas investor, modal pada aset aktif dan hasil investasi yang sudah terealisasi.</p></div>", unsafe_allow_html=True)
    properties = list_properties(); analyses = list_analyses(); cash_profile, events, liq = get_cash_data()
    active = [p for p in properties if p.get("lifecycle_status") in {"WON", "ACTIVE"}]
    sold = [p for p in properties if p.get("lifecycle_status") == "SOLD"]
    opps = [p for p in properties if p.get("lifecycle_status") in {"PROSPECT", "BID PLANNED", "BID SUBMITTED", "LOST", "WITHDRAWN"}]
    realized = []
    for p in sold:
        closing = next((x for x in read_table("SALES_CLOSING") if x.get("property_id") == p.get("property_id")), {})
        costs = [x for x in read_table("COST_ACTUALS") if x.get("property_id") == p.get("property_id")]
        realized.append(actual_project_summary(costs, closing))
    total_realized_profit = sum(x.get("net_profit_actual", 0) for x in realized)
    active_actual_cost = sum(to_float(x.get("amount")) for x in read_table("COST_ACTUALS") if any(p.get("property_id") == x.get("property_id") for p in active))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kas siap investasi", idr(liq["cash_available_for_new_project"]))
    k2.metric("Peluang tersimpan", len(opps))
    k3.metric("Aset aktif", len(active))
    k4.metric("Profit terealisasi", idr(total_realized_profit))
    st.markdown("### Kondisi portofolio")
    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.markdown("**Aset yang sedang dikelola**")
        if active:
            rows = []
            for p in active:
                pay = record_payload(p); inp = pay.get("input_data", {}); prop = inp.get("property", {})
                rows.append({"Property ID": p.get("property_id"), "Objek": p.get("name"), "Lifecycle": p.get("lifecycle_status"), "Status Analisis": p.get("decision_status"), "Limit": to_float(p.get("auction_limit")), "Tahap": pay.get("project_stage", "Settlement")})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else: st.info("Belum ada properti yang dimenangkan. Peluang GO tetap tersimpan sebagai prospek, bukan aset aktif.")
    with c2:
        st.markdown("**Distribusi keputusan analisis**")
        if analyses:
            df = pd.DataFrame([{"Keputusan": r.get("decision_status", "HOLD")} for r in analyses])
            st.bar_chart(df["Keputusan"].value_counts())
        else: st.info("Belum ada snapshot analisis.")
    st.markdown("### Pengingat keputusan")
    st.info("Sistem menyimpan semua status peluang. Hanya properti yang dimenangkan masuk ke Active Properties; setelah closing masuk Closed Projects.")

# =========================== PAGE 2: NEW ANALYSIS ==========================
elif page == "New Auction Analysis":
    st.title("New Auction Analysis")
    st.caption("Isi data pengumuman, survei, pasar dan biaya. Python menghitung; Gemini hanya membantu ekstraksi dan review bila dipanggil.")
    existing_props = list_properties()
    load_options = {"Buat objek baru": ""}
    for p in existing_props: load_options[f"{p.get('lot_code') or p.get('property_id')} · {p.get('name','')} [{p.get('decision_status','')}] "] = p.get("property_id")
    chosen_load = st.selectbox("Muat objek tersimpan untuk koreksi / analisis ulang", list(load_options.keys()))
    if st.button("Muat objek terpilih"):
        pid = load_options[chosen_load]
        if not pid:
            for state_key in list(st.session_state.keys()):
                if state_key.startswith("na_"):
                    del st.session_state[state_key]
            st.session_state.loaded_property_id = ""
            st.session_state.current_analysis = None
            st.session_state.current_inputs = None
            st.session_state.parse_info = None
            st.session_state.ai_review = None
            st.success("Form dibersihkan. Siap membuat analisis objek baru.")
            st.rerun()
        if pid:
            row = next(x for x in existing_props if x.get("property_id") == pid)
            payload = record_payload(row); data = payload.get("input_data", {})
            mapping = {
                "na_lot_code": data.get("property", {}).get("lot_code", ""), "na_name": data.get("property", {}).get("name", ""),
                "na_complex": data.get("property", {}).get("complex_name", ""), "na_address": data.get("property", {}).get("address", ""),
                "na_district": data.get("property", {}).get("district", ""), "na_province": data.get("property", {}).get("province", ""),
                "na_office": data.get("property", {}).get("auction_office", ""), "na_seller": data.get("property", {}).get("seller", ""),
                "na_auction_type": data.get("property", {}).get("auction_type", ""), "na_auction_date": data.get("property", {}).get("auction_date", ""),
                "na_limit": data.get("property", {}).get("auction_limit"), "na_deposit": data.get("property", {}).get("deposit_amount"),
                "na_increment": data.get("property", {}).get("bid_increment"), "na_certificate": data.get("property", {}).get("certificate_type", ""),
                "na_certificate_no": data.get("property", {}).get("certificate_no", ""), "na_land": data.get("property", {}).get("land_area"),
                "na_building": data.get("property", {}).get("building_area"), "na_njop": data.get("property", {}).get("njop"),
                "na_survey_status": data.get("survey", {}).get("survey_status", "Belum Survei"),
                "na_possession_cost": data.get("survey", {}).get("possession_cost", 25_000_000), "na_possession_months": data.get("survey", {}).get("possession_months", 6),
                "na_renovation_extra": data.get("costs", {}).get("renovation_extra_cost", data.get("costs", {}).get("renovation_cost", 0)), "na_renovation_months": data.get("costs", {}).get("renovation_months", 1),
                "na_selling_months": data.get("costs", {}).get("selling_months", 3), "na_monthly_holding": data.get("costs", {}).get("monthly_holding_cost", 1_000_000),
                "na_legal_verified": data.get("legal", {}).get("identity_verified", False), "na_dispute": data.get("legal", {}).get("dispute_detected", False),
                "na_costs_reviewed": data.get("costs", {}).get("cost_estimates_reviewed", False),
            }
            for k, v in mapping.items(): st.session_state[k] = v
            comparable_columns = ["name", "address", "price", "land_area", "building_area", "bedrooms", "bathrooms", "condition", "condition_detail", "access", "access_detail", "price_type", "certificate", "orientation", "electricity_watt", "water_source", "source_platforms", "source_evidence", "source_url", "listing_date", "date_found", "date_found_basis", "notes", "adjustment_pct"]
            risk_columns = ["category", "risk_description", "probability_1_5", "impact_1_5", "cost_reserve", "critical", "mitigation", "status"]
            loaded_comps = data.get("comparables", [])
            loaded_risks = data.get("risk_register", [])
            if loaded_comps:
                comp_frame = pd.DataFrame(loaded_comps)
                for column in comparable_columns:
                    if column not in comp_frame.columns:
                        comp_frame[column] = None
                st.session_state.na_comparables_editor = comp_frame[comparable_columns]
            else:
                st.session_state.na_comparables_editor = pd.DataFrame([{c: None for c in comparable_columns} for _ in range(5)])
            st.session_state.na_risk_editor = pd.DataFrame(loaded_risks) if loaded_risks else pd.DataFrame([{c: None for c in risk_columns}])
            renovation_columns = ["work_item", "quantity", "unit", "unit_cost", "notes"]
            loaded_reno = data.get("costs", {}).get("renovation_items", [])
            st.session_state.na_renovation_items_editor = pd.DataFrame(loaded_reno) if loaded_reno else pd.DataFrame([{c: None for c in renovation_columns} for _ in range(4)])
            st.session_state.na_risk_reviewed = bool(data.get("risk_reviewed", False))
            for widget_key in ["na_comparables_editor_widget", "na_risk_editor_widget", "na_renovation_items_widget"]:
                if widget_key in st.session_state: del st.session_state[widget_key]
            st.session_state.loaded_property_id = pid
            st.success("Data objek dimuat. Silakan koreksi dan analisis ulang.")
            st.rerun()

    uploaded = st.file_uploader("Upload pengumuman lelang (PDF, PNG, JPG, WEBP)", type=["pdf", "png", "jpg", "jpeg", "webp"], key="na_document")
    if st.button("Parse dengan Gemini AI", type="secondary", disabled=uploaded is None):
        try:
            mime = uploaded.type or "application/octet-stream"
            raw_document = uploaded.getvalue()
            digest = file_sha256(raw_document)
            cached_document = next((d for d in read_table("DOCUMENTS") if d.get("document_hash") == digest and d.get("extraction_json")), None)
            if cached_document:
                extracted = parse_json(cached_document.get("extraction_json"), {})
                st.info("Dokumen yang sama sudah pernah diparse. Hasil ekstraksi digunakan dari cache database; Gemini tidak dipanggil ulang.")
            else:
                if not GEMINI_KEY:
                    st.error("GEMINI_API_KEY belum dikonfigurasi dan belum ada hasil cache untuk dokumen ini. Isi Secrets atau gunakan pengisian manual.")
                    extracted = None
                else:
                    with st.spinner("Gemini membaca dokumen dan menilai fasad dalam satu permintaan..."):
                        extracted = extract_auction_document(GEMINI_KEY, raw_document, mime, uploaded.name, GEMINI_MODEL)
            if extracted is not None:
                st.session_state.parse_info = extracted
                field_map = {
                    "lot_code":"na_lot_code", "name":"na_name", "auction_office":"na_office", "seller":"na_seller", "auction_type":"na_auction_type",
                    "auction_date":"na_auction_date", "auction_time":"na_auction_time", "deposit_deadline":"na_deposit_deadline", "payment_deadline":"na_payment_deadline", "address":"na_address", "district":"na_district", "province":"na_province", "auction_limit":"na_limit",
                    "deposit_amount":"na_deposit", "bid_increment":"na_increment", "certificate_type":"na_certificate", "certificate_no":"na_certificate_no",
                    "land_area":"na_land", "building_area":"na_building", "njop":"na_njop", "auction_url":"na_auction_url", "property_type":"na_property_type", "bedrooms":"na_bedrooms", "bathrooms":"na_bathrooms", "rights_expiry":"na_rights_expiry",
                }
                for src, dst in field_map.items():
                    val = extracted.get(src)
                    if val not in (None, "") and (dst not in st.session_state or st.session_state.get(dst) in (None, "")): st.session_state[dst] = val
                st.session_state.na_facade_ai = extracted.get("facade_assessment") or ""
                st.session_state.na_extraction_evidence = extracted.get("field_evidence", {})
                st.session_state.na_extraction_conflicts = extracted.get("conflicts", [])
                st.success("Ekstraksi selesai. Nilai yang ditemukan sudah diisikan ke form; data yang tidak ditemukan dibiarkan kosong.")
                st.rerun()
        except Exception as exc: st.error(str(exc))
    if uploaded and not GEMINI_KEY: st.warning("GEMINI_API_KEY belum dikonfigurasi. Pengisian manual tetap tersedia.")
    if st.session_state.parse_info:
        with st.expander("Hasil parsing Gemini dan evidence", expanded=True):
            d = st.session_state.parse_info
            st.write(d.get("facade_assessment", "Tidak ada deskripsi fasad."))
            if d.get("facade_visible_findings"): st.write("Temuan terlihat:", d["facade_visible_findings"])
            if d.get("facade_unknowns"): st.write("Tidak dapat dipastikan:", d["facade_unknowns"])
            if d.get("conflicts"): st.warning("Konflik: " + "; ".join(d["conflicts"]))
            if d.get("field_evidence"): st.json(d["field_evidence"])

    st.markdown("---")
    t1, t2, t3, t4 = st.tabs(["① Data KPKNL & Legal", "② Survei & Penguasaan", "③ Comparable Pasar", "④ Biaya & Target"])
    with t1:
        st.subheader("Identitas lelang")
        c1,c2,c3 = st.columns(3)
        with c1:
            set_default("na_lot_code", ""); st.text_input("Kode lot", key="na_lot_code")
            set_default("na_name", ""); st.text_input("Nama objek", key="na_name")
            set_default("na_complex", ""); st.text_input("Nama kompleks/perumahan", key="na_complex")
            set_default("na_auction_date", ""); st.text_input("Tanggal lelang (YYYY-MM-DD)", key="na_auction_date")
            set_default("na_auction_time", ""); st.text_input("Jam lelang", key="na_auction_time")
        with c2:
            set_default("na_office", ""); st.text_input("KPKNL", key="na_office")
            set_default("na_seller", ""); st.text_input("Penjual/kreditur", key="na_seller")
            set_default("na_auction_type", ""); st.selectbox("Jenis lelang", ["", "Eksekusi Hak Tanggungan", "Eksekusi Pengadilan", "AYDA", "Lelang sukarela", "Lainnya"], key="na_auction_type")
            set_default("na_auction_url", ""); st.text_input("URL pengumuman lelang", key="na_auction_url")
            set_default("na_deposit_deadline", ""); st.text_input("Batas setor jaminan", key="na_deposit_deadline")
            set_default("na_payment_deadline", ""); st.text_input("Batas pelunasan", key="na_payment_deadline")
        with c3:
            set_default("na_address", ""); st.text_input("Alamat objek", key="na_address")
            set_default("na_district", ""); st.text_input("Desa/Kecamatan/Kabupaten", key="na_district")
            set_default("na_province", ""); st.text_input("Provinsi", key="na_province")
        st.markdown("**Nilai dan karakteristik objek**")
        c1,c2,c3,c4 = st.columns(4)
        with c1:
            set_default("na_limit", None); st.number_input("Nilai limit (Rp)", min_value=0, step=1_000_000, value=st.session_state.na_limit, key="na_limit")
            set_default("na_deposit", None); st.number_input("Uang jaminan (Rp)", min_value=0, step=1_000_000, value=st.session_state.na_deposit, key="na_deposit")
        with c2:
            set_default("na_increment", None); st.number_input("Kelipatan bid (Rp)", min_value=0, step=100_000, value=st.session_state.na_increment, key="na_increment", help="Wajib diverifikasi dari ketentuan penawaran lelang.")
            set_default("na_njop", None); st.number_input("NJOP (Rp)", min_value=0, step=1_000_000, value=st.session_state.na_njop, key="na_njop")
        with c3:
            set_default("na_land", None); st.number_input("Luas tanah (m²)", min_value=0.0, step=1.0, value=st.session_state.na_land, key="na_land")
            set_default("na_building", None); st.number_input("Luas bangunan (m²)", min_value=0.0, step=1.0, value=st.session_state.na_building, key="na_building")
        with c4:
            set_default("na_certificate", ""); st.selectbox("Jenis sertifikat", ["", "SHM", "SHGB/HGB", "Hak lain"], key="na_certificate")
            set_default("na_certificate_no", ""); st.text_input("Nomor sertifikat/hak", key="na_certificate_no")
        set_default("na_rights_expiry", ""); st.text_input("Masa berlaku SHGB (jika ada)", key="na_rights_expiry")
        c1,c2 = st.columns(2)
        with c1:
            set_default("na_bedrooms", None); st.number_input("Jumlah kamar tidur", min_value=0, step=1, value=st.session_state.na_bedrooms, key="na_bedrooms")
        with c2:
            set_default("na_bathrooms", None); st.number_input("Jumlah kamar mandi", min_value=0, step=1, value=st.session_state.na_bathrooms, key="na_bathrooms")
        set_default("na_property_type", ""); st.selectbox("Tipe properti", ["", "Rumah 1 lantai", "Rumah 2 lantai", "Cluster/modern", "Rumah kecil/standar", "Rumah besar", "Lainnya"], key="na_property_type")
        st.markdown("**Verifikasi legal (checkbox harus berdasarkan pemeriksaan pengguna)**")
        set_default("na_legal_verified", False); st.checkbox("Identitas objek dan dokumen hak sudah saya cocokkan", key="na_legal_verified")
        set_default("na_dispute", False); st.checkbox("Terdapat indikasi sengketa/ketidaksesuaian kritis", key="na_dispute")
        set_default("na_npoptkp_eligible", False); st.checkbox("Objek memenuhi syarat NPOPTKP/perolehan pertama (sudah diverifikasi)", key="na_npoptkp_eligible", help="Jika belum dapat diverifikasi, biarkan tidak dicentang agar estimasi BPHTB konservatif.")
        st.markdown("**Aturan pajak & biaya untuk wilayah objek**")
        current_rules_for_object = get_rules()
        tc1,tc2,tc3 = st.columns(3)
        with tc1:
            set_default("na_tax_region", st.session_state.get("na_district", "")); st.text_input("Wilayah aturan pajak (kabupaten/kota)", key="na_tax_region")
            set_default("na_bphtb_rate", float(current_rules_for_object["bphtb_rate_pct"])); st.number_input("Tarif BPHTB objek (%)", min_value=0.0, max_value=20.0, step=0.5, key="na_bphtb_rate")
        with tc2:
            set_default("na_npoptkp", safe_int(current_rules_for_object["npoptkp"])); st.number_input("NPOPTKP objek (Rp)", min_value=0, step=5_000_000, key="na_npoptkp")
            set_default("na_buyer_fee", float(current_rules_for_object["buyer_auction_fee_pct"])); st.number_input("Bea lelang pembeli (%)", min_value=0.0, max_value=20.0, step=0.5, key="na_buyer_fee")
        with tc3:
            set_default("na_tax_rule_source", ""); st.text_input("URL sumber aturan resmi", key="na_tax_rule_source")
            set_default("na_tax_verified", False); st.checkbox("Saya sudah memverifikasi tarif dan dasar pengenaan untuk objek ini", key="na_tax_verified")
    with t2:
        st.subheader("Survey status — gate utama")
        statuses = list(OCCUPANCY_DEFAULTS.keys())
        set_default("na_survey_status", "Belum Survei")
        prior_status = st.session_state.get("na_last_occupancy", st.session_state.na_survey_status)
        st.selectbox("Status survei dan penghuni", statuses, key="na_survey_status")
        if st.session_state.na_survey_status == "Belum Survei": st.error("PERINGATAN: Objek belum disurvei! Simulasi memakai asumsi biaya penguasaan tinggi. Keputusan final tetap HOLD.")
        if st.session_state.na_survey_status != prior_status:
            defaults = OCCUPANCY_DEFAULTS[st.session_state.na_survey_status]
            st.session_state.na_possession_cost = defaults["expected_cost"]
            st.session_state.na_possession_months = float(defaults["months"])
            st.session_state.na_possession_risk_reserve = defaults["risk_reserve"]
            st.session_state.na_last_occupancy = st.session_state.na_survey_status
        defaults = OCCUPANCY_DEFAULTS[st.session_state.na_survey_status]
        c1,c2,c3 = st.columns(3)
        with c1:
            set_default("na_possession_cost", defaults["expected_cost"]); st.number_input("Estimasi biaya penguasaan/pengosongan (Rp)", min_value=0, step=1_000_000, key="na_possession_cost")
        with c2:
            set_default("na_possession_months", float(defaults["months"])); st.number_input("Waktu penguasaan (bulan)", min_value=0.0, step=0.5, key="na_possession_months")
        with c3:
            set_default("na_possession_risk_reserve", defaults["risk_reserve"]); st.number_input("Cadangan risiko penguasaan (Rp)", min_value=0, step=1_000_000, key="na_possession_risk_reserve")
        set_default("na_survey_date", date.today().isoformat()); st.text_input("Tanggal survei", key="na_survey_date")
        set_default("na_road_width", None); st.number_input("Lebar jalan (meter)", min_value=0.0, step=0.5, value=st.session_state.na_road_width, key="na_road_width")
        set_default("na_access", ""); st.selectbox("Akses jalan", ["", "2 Mobil", "1 Mobil", "Gang"], key="na_access")
        set_default("na_physical_condition", "Belum diketahui"); st.selectbox("Kondisi fisik umum", ["Belum diketahui", "Siap huni", "Renovasi kosmetik", "Renovasi sedang", "Renovasi berat", "Hitung tanah"], key="na_physical_condition")
        set_default("na_interior_inspected", False); st.checkbox("Interior sudah diperiksa", key="na_interior_inspected")
        set_default("na_facade_manual", st.session_state.get("na_facade_ai", "")); st.text_area("Deskripsi fasad (hasil AI dapat diedit)", key="na_facade_manual", height=90)
        set_default("na_survey_notes", ""); st.text_area("Catatan survei, penghuni, RT/tetangga, utilitas, banjir, struktur", key="na_survey_notes", height=100)
        survey_photos = st.file_uploader("Foto hasil survei (opsional; pilih beberapa foto)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="na_survey_photos")
        st.caption("Foto survei tidak otomatis dikirim ke Gemini. Bila Google Drive archive diaktifkan, foto disimpan ke folder Drive dan metadata/hash dicatat di database.")
        st.markdown("### Risk register dan mitigasi")
        st.caption("Isi risiko yang ditemukan. Probabilitas dan dampak 1–5. Cadangan biaya hanya menambah kebutuhan likuiditas; tidak dianggap sebagai biaya profit sampai benar-benar digunakan.")
        risk_columns = ["category", "risk_description", "probability_1_5", "impact_1_5", "cost_reserve", "critical", "mitigation", "status"]
        if "na_risk_editor" not in st.session_state:
            st.session_state.na_risk_editor = pd.DataFrame([{c: None for c in risk_columns}])
        risk_edited = st.data_editor(st.session_state.na_risk_editor, num_rows="dynamic", use_container_width=True, key="na_risk_editor_widget", column_config={
            "category": st.column_config.TextColumn("Kategori"),
            "risk_description": st.column_config.TextColumn("Deskripsi risiko"),
            "probability_1_5": st.column_config.NumberColumn("Probabilitas (1–5)", min_value=1, max_value=5, step=1),
            "impact_1_5": st.column_config.NumberColumn("Dampak (1–5)", min_value=1, max_value=5, step=1),
            "cost_reserve": st.column_config.NumberColumn("Cadangan biaya (Rp)", min_value=0, format="Rp %.0f"),
            "critical": st.column_config.CheckboxColumn("Kritis?"),
            "mitigation": st.column_config.TextColumn("Mitigasi"),
            "status": st.column_config.SelectboxColumn("Status", options=["Open", "Mitigated", "Resolved"]),
        })
        st.session_state.na_risk_current = risk_edited.to_dict(orient="records")
        set_default("na_risk_reviewed", False)
        st.checkbox("Saya sudah meninjau risk register; semua risiko tambahan sudah dicatat atau tidak ada risiko tambahan yang diketahui.", key="na_risk_reviewed")
    with t3:
        st.subheader("Market comparables — AI narrative parser")
        st.caption("Tempel uraian listing apa adanya (boleh berupa narasi bernomor dan bullet seperti hasil riset Anda). Gemini akan menggabungkan setiap judul listing beserta bullet turunannya menjadi SATU baris properti di tabel. AI tidak membuat URL, tanggal publikasi, kondisi, atau akses yang tidak disebutkan.")
        set_default("na_comparable_paste", "")
        paste = st.text_area(
            "Paste narasi 5+ listing pasar",
            key="na_comparable_paste",
            height=270,
            placeholder="1. Rumah Hook Siap Huni...\n• Alamat & Posisi...\n• Harga Penawaran...\n• Spesifikasi Bangunan...\n• Sumber Listing...\n\n2. Rumah berikutnya...",
        )
        ai_col, csv_col = st.columns(2)
        with ai_col:
            parse_ai = st.button("🤖 Parse narasi dengan Gemini AI", type="primary", disabled=not bool(GEMINI_KEY), use_container_width=True)
        with csv_col:
            parse_csv = st.button("Impor CSV/TSV terstruktur", use_container_width=True)
        if not GEMINI_KEY:
            st.info("GEMINI_API_KEY belum dikonfigurasi. Input tabel manual/CSV tetap tersedia. Parsing narasi memerlukan Gemini API.")
        if parse_ai:
            try:
                narrative_digest = hashlib.sha256((paste or "").strip().encode("utf-8")).hexdigest()
                comparable_cache = st.session_state.setdefault("na_comparable_parse_cache", {})
                if narrative_digest in comparable_cache:
                    parsed_result = comparable_cache[narrative_digest]
                    st.info("Narasi identik sudah pernah diparsing pada sesi ini. Hasil cache digunakan; Gemini tidak dipanggil ulang.")
                else:
                    with st.spinner("Gemini mengelompokkan seluruh bullet ke masing-masing listing dan mengisi tabel..."):
                        parsed_result = parse_comparable_narrative(GEMINI_KEY, paste, GEMINI_MODEL)
                    comparable_cache[narrative_digest] = parsed_result
                parsed_rows = parsed_result.get("items", [])
                if not parsed_rows:
                    st.warning("Gemini tidak menemukan struktur listing. Pastikan setiap properti diawali nomor/judul yang jelas.")
                else:
                    st.session_state.na_comparables_editor = pd.DataFrame(parsed_rows)
                    st.session_state.na_comparable_parse_notes = parsed_result.get("parsing_notes", [])
                    st.session_state.na_comparable_parse_summary = {"count": len(parsed_rows), "captured_at": parsed_result.get("captured_at")}
                    if "na_comparables_editor_widget" in st.session_state:
                        del st.session_state["na_comparables_editor_widget"]
                    st.success(f"Berhasil diparsing menjadi {len(parsed_rows)} baris listing. Periksa dan koreksi hasil sebelum analisis.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Parsing comparable dengan Gemini gagal: {exc}")
        if parse_csv:
            try:
                parsed = parse_comparable_paste(paste)
                if not parsed:
                    st.warning("Format CSV/TSV tidak terbaca. Untuk narasi listing, gunakan tombol Parse narasi dengan Gemini AI.")
                else:
                    st.session_state.na_comparables_editor = pd.DataFrame(parsed)
                    if "na_comparables_editor_widget" in st.session_state:
                        del st.session_state["na_comparables_editor_widget"]
                    st.success(f"{len(parsed)} baris CSV/TSV dimuat. Periksa kembali setiap kolom.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Gagal membaca CSV/TSV: {exc}")
        if st.session_state.get("na_comparable_parse_summary"):
            summary = st.session_state.na_comparable_parse_summary
            st.caption(f"Parsing terakhir: {summary.get('count')} listing · tanggal tangkap sistem {summary.get('captured_at')}. Tanggal ini bukan tanggal publikasi iklan.")
            for note in st.session_state.get("na_comparable_parse_notes", []):
                st.warning(note)
        default_cols = ["name", "address", "complex_name", "price", "land_area", "building_area", "bedrooms", "bathrooms", "condition", "condition_detail", "access", "access_detail", "price_type", "certificate", "orientation", "electricity_watt", "water_source", "source_platforms", "source_evidence", "source_url", "listing_date", "date_found", "date_found_basis", "notes", "adjustment_pct"]
        if st.session_state.get("na_comparable_schema_version") != 2:
            if "na_comparables_editor_widget" in st.session_state:
                del st.session_state["na_comparables_editor_widget"]
            st.session_state.na_comparable_schema_version = 2
        if "na_comparables_editor" not in st.session_state:
            st.session_state.na_comparables_editor = pd.DataFrame([{c: None for c in default_cols} for _ in range(5)])
        else:
            comp_frame = st.session_state.na_comparables_editor.copy()
            for column in default_cols:
                if column not in comp_frame.columns:
                    comp_frame[column] = None
            st.session_state.na_comparables_editor = comp_frame[default_cols]
        st.caption("Baris dapat digunakan untuk valuasi indikatif jika nama, harga, minimal salah satu LT/LB, dan sumber listing tersedia. Untuk GO final, setiap comparable harus memiliki URL listing langsung dan tanggal ditemukan agar dapat ditelusuri. Kondisi, akses, LB, dan tanggal publikasi yang tidak disebutkan tidak akan ditebak; kekurangannya menurunkan confidence.")
        edited = st.data_editor(st.session_state.na_comparables_editor, num_rows="dynamic", use_container_width=True, key="na_comparables_editor_widget", column_config={
            "name": st.column_config.TextColumn("Nama listing"),
            "address": st.column_config.TextColumn("Alamat/lokasi"),
            "price": st.column_config.NumberColumn("Harga penawaran (Rp)", min_value=0, format="Rp %.0f"),
            "land_area": st.column_config.NumberColumn("LT (m²)", min_value=0),
            "building_area": st.column_config.NumberColumn("LB (m²)", min_value=0, help="Boleh kosong bila tidak tercantum; sistem dapat memakai pendekatan LT saja."),
            "condition": st.column_config.SelectboxColumn("Kondisi", options=["", "Siap Huni", "Butuh Renovasi", "Hitung Tanah"]),
            "access": st.column_config.SelectboxColumn("Akses", options=["", "2 Mobil", "1 Mobil", "Gang"]),
            "price_type": st.column_config.SelectboxColumn("Jenis harga", options=["Asking aktif", "Marked sold / perlu verifikasi", "Transaksi terverifikasi"]),
            "source_platforms": st.column_config.TextColumn("Portal/platform sumber"),
            "source_url": st.column_config.TextColumn("URL langsung (opsional)"),
            "listing_date": st.column_config.TextColumn("Tanggal iklan (jika diketahui)"),
            "date_found": st.column_config.TextColumn("Tanggal ditemukan"),
            "adjustment_pct": st.column_config.NumberColumn("Penyesuaian (%)", help="Hanya diisi dengan alasan yang dapat dijelaskan."),
        })
        st.session_state.na_comparables_current = edited.to_dict(orient="records")
        set_default("na_negotiation_discount", DEFAULT_RULES["negotiation_discount_pct"])
        set_default("na_quick_sale_discount", DEFAULT_RULES["quick_sale_discount_pct"])
        c1,c2 = st.columns(2)
        with c1: st.number_input("Negotiation discount listing aktif (%)", min_value=0.0, max_value=50.0, step=1.0, key="na_negotiation_discount")
        with c2: st.number_input("Quick-sale discount (%)", min_value=0.0, max_value=30.0, step=1.0, key="na_quick_sale_discount")
    with t4:
        st.subheader("Biaya proyek dan target")
        rules = get_rules()
        st.markdown("### RAB renovasi per item pekerjaan")
        renovation_columns = ["work_item", "quantity", "unit", "unit_cost", "notes"]
        if "na_renovation_items_editor" not in st.session_state:
            st.session_state.na_renovation_items_editor = pd.DataFrame([{c: None for c in renovation_columns} for _ in range(4)])
        renovation_edited = st.data_editor(st.session_state.na_renovation_items_editor, num_rows="dynamic", use_container_width=True, key="na_renovation_items_widget", column_config={
            "work_item": st.column_config.TextColumn("Pekerjaan"),
            "quantity": st.column_config.NumberColumn("Volume", min_value=0.0, step=1.0),
            "unit": st.column_config.TextColumn("Satuan"),
            "unit_cost": st.column_config.NumberColumn("Harga satuan (Rp)", min_value=0, format="Rp %.0f"),
            "notes": st.column_config.TextColumn("Catatan / sumber estimasi"),
        })
        st.session_state.na_renovation_items_current = renovation_edited.to_dict(orient="records")
        renovation_items = [r for r in st.session_state.na_renovation_items_current if str(r.get("work_item") or "").strip()]
        renovation_item_total = sum(max(0, to_float(r.get("quantity"))) * max(0, to_float(r.get("unit_cost"))) for r in renovation_items)
        c1,c2,c3 = st.columns(3)
        with c1:
            set_default("na_renovation_extra", 0); st.number_input("Tambahan renovasi di luar item (Rp)", min_value=0, step=500_000, key="na_renovation_extra")
            set_default("na_renovation_months", 1.0); st.number_input("Waktu renovasi (bulan)", min_value=0.0, step=0.5, key="na_renovation_months")
        with c2:
            set_default("na_monthly_holding", rules["monthly_holding_cost"]); st.number_input("Holding cost per bulan (Rp)", min_value=0, step=250_000, key="na_monthly_holding")
            set_default("na_selling_months", 3.0); st.number_input("Estimasi waktu penjualan (bulan)", min_value=0.0, step=0.5, key="na_selling_months")
        with c3:
            set_default("na_legal_delay_months", 1.0); st.number_input("Estimasi delay legalitas (bulan)", min_value=0.0, step=0.5, key="na_legal_delay_months")
            set_default("na_marketing_cost", 1_000_000); st.number_input("Biaya marketing (Rp)", min_value=0, step=250_000, key="na_marketing_cost")
        renovation_total = renovation_item_total + to_float(st.session_state.na_renovation_extra)
        st.metric("TOTAL RAB RENOVASI", idr(renovation_total), help="Total volume × harga satuan seluruh item + tambahan di luar daftar.")
        c1,c2 = st.columns(2)
        with c1:
            set_default("na_other_presale", 0); st.number_input("Biaya lain sebelum penjualan (Rp)", min_value=0, step=500_000, key="na_other_presale")
        with c2:
            set_default("na_risk_ceiling", None); st.number_input("Hard ceiling bid tambahan (opsional, Rp)", min_value=0, step=1_000_000, value=st.session_state.na_risk_ceiling, key="na_risk_ceiling")
        st.caption("Contingency renovasi dihitung otomatis oleh Python berdasarkan persentase Settings & Rules.")
        st.metric("Minimum ROI", "25%", help="Target wajib untuk seluruh periode proyek.")
        set_default("na_costs_reviewed", False)
        st.checkbox("Saya sudah meninjau seluruh estimasi biaya (termasuk BPN, penguasaan, setiap item renovasi, contingency, holding, marketing, dan biaya lain). Nilai nol adalah keputusan yang disengaja.", key="na_costs_reviewed")
        with st.expander("Asumsi biaya dan pajak (editable pada Settings & Rules)"):
            st.json(rules)

    if st.button("🚀 ANALISIS SEKARANG", type="primary", use_container_width=True):
        property_data = {
            "lot_code": st.session_state.na_lot_code, "name": st.session_state.na_name, "complex_name": st.session_state.na_complex,
            "address": st.session_state.na_address, "district": st.session_state.na_district, "province": st.session_state.na_province,
            "auction_office": st.session_state.na_office, "seller": st.session_state.na_seller, "auction_type": st.session_state.na_auction_type,
            "auction_date": st.session_state.na_auction_date, "auction_time": st.session_state.get("na_auction_time", ""), "deposit_deadline": st.session_state.get("na_deposit_deadline", ""), "payment_deadline": st.session_state.get("na_payment_deadline", ""), "auction_url": st.session_state.get("na_auction_url", ""),
            "auction_limit": st.session_state.na_limit, "deposit_amount": st.session_state.na_deposit, "bid_increment": st.session_state.na_increment,
            "certificate_type": st.session_state.na_certificate, "certificate_no": st.session_state.na_certificate_no, "rights_expiry": st.session_state.get("na_rights_expiry", ""),
            "land_area": st.session_state.na_land, "building_area": st.session_state.na_building, "njop": st.session_state.na_njop, "bedrooms": st.session_state.get("na_bedrooms"), "bathrooms": st.session_state.get("na_bathrooms"), "property_type": st.session_state.get("na_property_type", ""), "rights_expiry": st.session_state.get("na_rights_expiry", ""),
            "risk_adjusted_ceiling": st.session_state.na_risk_ceiling, "npoptkp_eligible": st.session_state.na_npoptkp_eligible,
        }
        survey_data = {"survey_status": st.session_state.na_survey_status, "occupancy_status": st.session_state.na_survey_status, "survey_date": st.session_state.na_survey_date, "possession_cost": st.session_state.na_possession_cost, "possession_risk_reserve": st.session_state.na_possession_risk_reserve, "possession_months": st.session_state.na_possession_months, "road_width_m": st.session_state.na_road_width, "access": st.session_state.na_access, "physical_condition": st.session_state.na_physical_condition, "interior_inspected": st.session_state.na_interior_inspected, "facade_description": st.session_state.na_facade_manual, "survey_notes": st.session_state.na_survey_notes}
        legal_data = {"identity_verified": st.session_state.na_legal_verified, "dispute_detected": st.session_state.na_dispute, "tax_rules_verified": st.session_state.na_tax_verified, "tax_region": st.session_state.na_tax_region, "tax_rule_source_url": st.session_state.na_tax_rule_source}
        renovation_items_data = [r for r in st.session_state.get("na_renovation_items_current", []) if str(r.get("work_item") or "").strip()]
        renovation_item_total = sum(max(0, to_float(r.get("quantity"))) * max(0, to_float(r.get("unit_cost"))) for r in renovation_items_data)
        renovation_extra_cost = to_float(st.session_state.na_renovation_extra)
        costs_data = {"renovation_cost": renovation_item_total + renovation_extra_cost, "renovation_items": renovation_items_data, "renovation_extra_cost": renovation_extra_cost, "renovation_months": st.session_state.na_renovation_months, "selling_months": st.session_state.na_selling_months, "legal_delay_months": st.session_state.na_legal_delay_months, "monthly_holding_cost": st.session_state.na_monthly_holding, "marketing_cost": st.session_state.na_marketing_cost, "other_presale_cost": st.session_state.na_other_presale, "cost_estimates_reviewed": bool(st.session_state.na_costs_reviewed)}
        comp_data = st.session_state.get("na_comparables_current", [])
        cash_profile, cash_events, liquidity = get_cash_data()
        if not cash_profile.get("cash_confirmed", False): liquidity["cash_confirmed"] = False
        else: liquidity["cash_confirmed"] = True
        rules = get_rules(); rules["negotiation_discount_pct"] = st.session_state.na_negotiation_discount; rules["quick_sale_discount_pct"] = st.session_state.na_quick_sale_discount
        rules["buyer_auction_fee_pct"] = st.session_state.na_buyer_fee; rules["bphtb_rate_pct"] = st.session_state.na_bphtb_rate; rules["npoptkp"] = st.session_state.na_npoptkp
        risk_data = [r for r in st.session_state.get("na_risk_current", []) if str(r.get("risk_description") or "").strip()]
        risk_reviewed = bool(st.session_state.na_risk_reviewed)
        inputs = {"property": property_data, "survey": survey_data, "legal": legal_data, "costs": costs_data, "comparables": comp_data, "risk_register": risk_data, "risk_reviewed": risk_reviewed}
        result = run_underwriting(inputs, liquidity, rules)
        property_id = st.session_state.loaded_property_id or new_id("PROP")
        analysis_id = new_id("ANL")
        snapshot = {"analysis_id": analysis_id, "property_id": property_id, "analyzed_at": iso_now(), "property": property_data, "survey": survey_data, "legal": legal_data, "costs": costs_data, "comparables": comp_data, "risk_reviewed": risk_reviewed, "risk_register": risk_data, "rules": rules, "liquidity": liquidity, "document_extraction": st.session_state.parse_info or {}, **result}
        st.session_state.current_analysis = snapshot; st.session_state.current_inputs = inputs; st.session_state.current_property_id = property_id
        st.session_state.ai_review = None
    snap = st.session_state.current_analysis
    if snap:
        st.markdown("---")
        decision = snap["decision"]; mkt = snap["market"]; tiers = snap["bidding"]; at = snap["at_limit"]
        st.subheader("Hasil Underwriting")
        if mkt.get("conservative_exit") is None:
            st.info("Analisis parsial berhasil dijalankan. ARV belum dapat dihitung karena data comparable atau luas objek belum cukup; biaya akuisisi/proyek pada nilai limit tetap dihitung. Status HOLD berarti jangan bidding sampai data pasar/luas dilengkapi.")
        elif mkt.get("status") != "READY":
            st.warning(
                "ARV dan simulasi bidding masih INDIKATIF. Untuk GO final diperlukan minimal lima comparable yang dapat digunakan, "
                "masing-masing memiliki URL listing langsung dan tanggal ditemukan, serta confidence minimal 55/100. "
                "Sistem tetap menampilkan indikasi kelayakan atau Walk Away, tetapi tidak akan memberikan GO."
            )
        if decision["status"] == "GO": st.success("GO — SELURUH GATE UTAMA TERPENUHI")
        elif decision["status"] == "CONDITIONAL GO": st.warning("CONDITIONAL GO — ADA SYARAT YANG HARUS DIPENUHI")
        elif decision["status"] == "DO NOT BID": st.error("DO NOT BID / TIDAK LAYAK")
        else: st.warning("HOLD — DATA / VERIFIKASI BELUM MEMADAI")
        st.write(decision["summary"])
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Conservative ARV", idr(mkt.get("conservative_exit")))
        k2.metric("Total modal @ limit", idr(at.get("capital_before_sale")))
        k3.metric("Net profit @ limit", idr(at.get("net_profit")))
        k4.metric("ROI @ limit", pct(at.get("roi_pct")))
        st.markdown("### Tangga bidding")
        tier_rows = []
        for label, bid, res in [
            ("Batas bawah / Limit", tiers.get("min_bid"), at),
            ("Batas tengah / Target ROI 35%", tiers.get("mid_bid"), tiers.get("mid_result")),
            ("Maximum bid / ROI 25%", tiers.get("max_bid"), tiers.get("max_result")),
        ]:
            cash_need_tier = res.get("cash_requirement_including_reserve") if res else None
            cash_available_now = to_float(snap.get("liquidity", {}).get("cash_available_for_new_project"))
            hurdle = 35 if "tengah" in label.lower() else 25
            if not res or bid is None or bid < to_float(snap["property"].get("auction_limit")):
                tier_status = "OVERPRICE / SKIP"
            elif cash_need_tier is not None and cash_need_tier > cash_available_now:
                tier_status = "KAS TIDAK CUKUP"
            elif res.get("roi_pct", -999) >= hurdle:
                tier_status = "LAYAK BID"
            else:
                tier_status = "OVERPRICE / SKIP"
            tier_rows.append({"Tier": label, "Harga bid": bid, "Total modal": res.get("capital_before_sale") if res else None, "Kebutuhan kas + cadangan": cash_need_tier, "Profit bersih": res.get("net_profit") if res else None, "ROI": res.get("roi_pct") if res else None, "Status": tier_status})
        st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True, column_config={"Harga bid": st.column_config.NumberColumn(format="Rp %.0f"), "Total modal": st.column_config.NumberColumn(format="Rp %.0f"), "Kebutuhan kas + cadangan": st.column_config.NumberColumn(format="Rp %.0f"), "Profit bersih": st.column_config.NumberColumn(format="Rp %.0f"), "ROI": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("Status tier menilai ROI dan kecukupan kas pada snapshot analisis ini. Keputusan final tetap mengikuti seluruh hard gate di bawah.")
        st.metric("WALK-AWAY — bidding harus berhenti mulai", idr(tiers.get("walk_away_from")))
        f1, f2, f3 = st.columns(3)
        f1.metric("Uang jaminan", idr(snap["property"].get("deposit_amount")))
        f2.metric("Estimasi kebutuhan kas proyek + cadangan risiko", idr(at.get("cash_requirement_including_reserve")))
        f3.metric("Kas tersedia investor", idr(snap.get("liquidity", {}).get("cash_available_for_new_project")))
        risk_summary = snap.get("risk_summary", {})
        st.caption(f"Risk register: {risk_summary.get('count',0)} risiko · Severity maksimum {risk_summary.get('maximum_severity',0)}/25 · Cadangan likuiditas risiko {idr(risk_summary.get('total_cash_reserve',0))}")
        if not tiers.get("increment_confirmed"): st.error("Kelipatan bid belum dikonfirmasi. Tangga bidding belum final.")
        st.markdown("### Validasi pasar")
        st.write(f"Comparable untuk valuasi indikatif: **{mkt.get('valid_count',0)}** · Comparable GO-grade (URL langsung + tanggal ditemukan): **{mkt.get('go_grade_count',0)} / 5** · Confidence index: **{mkt.get('confidence',0)}/100** · Status: **{mkt.get('status')}**")
        mc1,mc2 = st.columns(2); mc1.metric("Median indikasi harga / m² LT", idr(mkt.get("land_unit_price_median"))); mc2.metric("Median indikasi harga / m² LB", idr(mkt.get("building_unit_price_median")))
        if mkt.get("valid"): st.dataframe(pd.DataFrame(mkt["valid"]), use_container_width=True, hide_index=True)
        if mkt.get("invalid"): st.warning("Baris tidak valid: " + safe_json(mkt["invalid"]))
        st.markdown("### Rincian biaya pada nilai limit")
        cost_rows = [{"Komponen":"Harga bid", "Nilai":at.get("bid_price")}, {"Komponen":"Bea lelang", "Nilai":at.get("buyer_auction_fee")}, {"Komponen":"BPHTB", "Nilai":at.get("bphtb")}, {"Komponen":"PNBP/legal/BPN", "Nilai":at.get("legal_bpn_cost")}, {"Komponen":"Penguasaan", "Nilai":at.get("possession_cost")}, {"Komponen":"Cadangan risiko penguasaan (bukan biaya sampai terpakai)", "Nilai":at.get("possession_risk_reserve")}, {"Komponen":"Renovasi", "Nilai":at.get("renovation_cost")}, {"Komponen":"Contingency renovasi", "Nilai":at.get("renovation_contingency")}, {"Komponen":"Holding", "Nilai":at.get("holding_cost")}, {"Komponen":"Biaya penjualan", "Nilai":at.get("selling_cost")}, {"Komponen":"Profit bersih", "Nilai":at.get("net_profit")}]
        st.dataframe(pd.DataFrame(cost_rows), use_container_width=True, hide_index=True, column_config={"Nilai": st.column_config.NumberColumn(format="Rp %.0f")})
        if decision.get("blockers"):
            st.markdown("**Blockers**")
            for x in decision["blockers"]: st.error(x)
        if decision.get("warnings"):
            st.markdown("**Peringatan**")
            for x in decision["warnings"]: st.warning(x)
        st.markdown("### Review AI (opsional, menggunakan kuota Gemini)")
        if st.button("Review asumsi dan risiko dengan Gemini", disabled=not GEMINI_KEY):
            try:
                with st.spinner("Gemini mengkritisi data dan hasil Python..."):
                    st.session_state.ai_review = review_investment(GEMINI_KEY, GEMINI_MODEL, snap)
            except Exception as exc: st.error(str(exc))
        if st.session_state.ai_review:
            st.json(st.session_state.ai_review)
        report = build_analysis_markdown(snap)
        st.download_button("Unduh Investment Memo (Markdown)", report, file_name=f"investment-memo-{snap['property_id']}.md", mime="text/markdown")
        if st.button("💾 SIMPAN / UPDATE ANALISIS KE DATABASE", type="primary", use_container_width=True):
            propid = snap["property_id"]
            latest = {**snap, "ai_review": st.session_state.ai_review}
            old = next((p for p in list_properties() if p.get("property_id") == propid), None)
            lifecycle = old.get("lifecycle_status", "PROSPECT") if old else "PROSPECT"
            save_property_record(propid, st.session_state.current_inputs, decision["status"], lifecycle, latest)
            upsert_record("ANALYSIS_HISTORY", "analysis_id", {"analysis_id": snap["analysis_id"], "property_id": propid, "analyzed_at": snap["analyzed_at"], "decision_status": decision["status"], "eligibility_index_pct": snap["eligibility_index_pct"], "conservative_arv": mkt.get("conservative_exit"), "max_bid": tiers.get("max_bid"), "roi_at_limit_pct": at.get("roi_pct"), "payload": latest})
            upsert_record("SURVEYS", "survey_id", {"survey_id": f"{snap['analysis_id']}-SRV", "property_id": propid, "updated_at": iso_now(), "survey_status": snap["survey"].get("survey_status"), "occupancy_status": snap["survey"].get("occupancy_status"), "payload": snap["survey"]})
            upsert_record("COST_ESTIMATES", "estimate_id", {"estimate_id": f"{snap['analysis_id']}-CST", "property_id": propid, "analysis_id": snap["analysis_id"], "updated_at": iso_now(), "payload": {"costs": snap["costs"], "rules": snap["rules"]}})
            existing_risk_ids = {str(x.get("risk_id")) for x in read_table("RISK_REGISTER")}
            risk_records = []
            for idx, risk in enumerate(snap.get("risk_register", []), start=1):
                risk_id = f"{snap['analysis_id']}-RISK{idx:02d}"
                if risk_id in existing_risk_ids: continue
                risk_records.append({"risk_id": risk_id, "property_id": propid, "analysis_id": snap["analysis_id"], "category": risk.get("category"), "risk_description": risk.get("risk_description"), "probability_1_5": risk.get("probability_1_5"), "impact_1_5": risk.get("impact_1_5"), "severity_score": to_float(risk.get("probability_1_5")) * to_float(risk.get("impact_1_5")), "cost_reserve": risk.get("cost_reserve"), "critical": bool(risk.get("critical", False)), "mitigation": risk.get("mitigation"), "status": risk.get("status"), "created_at": iso_now()})
            if risk_records:
                if repo: repo.append_records("RISK_REGISTER", risk_records); cached_read.clear()
                else: st.session_state.local_db["RISK_REGISTER"].extend(risk_records)
            comps = []
            valid_names = {str(c.get("name")) for c in mkt.get("valid", [])}
            invalid_by_name = {str(x.get("name")): x.get("errors", []) for x in mkt.get("invalid", [])}
            existing_comparable_ids = {str(x.get("comparable_id")) for x in read_table("COMPARABLES")}
            for idx, c in enumerate(snap.get("comparables", []), start=1):
                cname = str(c.get("name", ""))
                comparable_id = f"{snap['analysis_id']}-CMP{idx:02d}"
                if comparable_id in existing_comparable_ids: continue
                comps.append({"comparable_id": comparable_id, "property_id": propid, "analysis_id": snap["analysis_id"], "name": c.get("name"), "price": c.get("price"), "land_area": c.get("land_area"), "building_area": c.get("building_area"), "price_type": c.get("price_type"), "source_url": c.get("source_url"), "date_found": c.get("date_found"), "payload": {**c, "validation_status": "VALID" if cname in valid_names else "INVALID", "validation_errors": invalid_by_name.get(cname, [])}})
            if comps:
                if repo: repo.save_comparables(comps); cached_read.clear()
                else: st.session_state.local_db["COMPARABLES"].extend(comps)
            if uploaded:
                digest = file_sha256(uploaded.getvalue())
                existing_doc = next((d for d in read_table("DOCUMENTS") if d.get("property_id") == propid and d.get("document_hash") == digest), None)
                if not existing_doc:
                    drive_folder_id = str(secret("DRIVE_FOLDER_ID", "") or "")
                    source_link = snap["property"].get("auction_url", "")
                    notes = "Dokumen digunakan untuk ekstraksi AI."
                    if drive_folder_id and service_info:
                        try:
                            drive_file = upload_file_to_drive(dict(service_info), drive_folder_id, uploaded.name, uploaded.type, uploaded.getvalue())
                            source_link = drive_file.get("web_view_link") or source_link
                            notes += f" Diarsipkan di Google Drive; file_id={drive_file.get('file_id')}."
                        except Exception as drive_exc:
                            notes += f" Arsip Drive gagal: {drive_exc}. File binary tidak tersimpan; simpan manual bila diperlukan."
                            st.warning(notes)
                    else:
                        notes += " DRIVE_FOLDER_ID belum diatur; file binary tidak disimpan permanen, hanya metadata dan hash."
                        st.warning(notes)
                    append_record("DOCUMENTS", {"document_id": new_id("DOC"), "property_id": propid, "file_name": uploaded.name, "mime_type": uploaded.type, "source_url": source_link, "document_hash": digest, "uploaded_at": iso_now(), "notes": notes, "extraction_json": safe_json(snap.get("document_extraction") or {})})
                elif existing_doc and not existing_doc.get("extraction_json") and snap.get("document_extraction"):
                    upsert_record("DOCUMENTS", "document_id", {**existing_doc, "extraction_json": safe_json(snap.get("document_extraction"))})
            for photo in (survey_photos or []):
                photo_bytes = photo.getvalue()
                photo_digest = file_sha256(photo_bytes)
                existing_photo = next((d for d in read_table("DOCUMENTS") if d.get("property_id") == propid and d.get("document_hash") == photo_digest), None)
                if existing_photo: continue
                photo_link = ""
                photo_notes = "Foto hasil survei lapangan."
                drive_folder_id = str(secret("DRIVE_FOLDER_ID", "") or "")
                if drive_folder_id and service_info:
                    try:
                        drive_file = upload_file_to_drive(dict(service_info), drive_folder_id, photo.name, photo.type, photo_bytes)
                        photo_link = drive_file.get("web_view_link", "")
                        photo_notes += f" Diarsipkan di Google Drive; file_id={drive_file.get('file_id')}."
                    except Exception as photo_exc:
                        photo_notes += f" Arsip Drive gagal: {photo_exc}; simpan manual bila diperlukan."
                        st.warning(photo_notes)
                else:
                    photo_notes += " DRIVE_FOLDER_ID belum diatur; file binary tidak tersimpan permanen, hanya metadata dan hash."
                append_record("DOCUMENTS", {"document_id": new_id("DOC"), "property_id": propid, "file_name": photo.name, "mime_type": photo.type, "source_url": photo_link, "document_hash": photo_digest, "uploaded_at": iso_now(), "notes": photo_notes, "extraction_json": ""})
            log_event("ANALYSIS", snap["analysis_id"], "SAVED", {"decision": decision["status"]})
            st.success("Analisis tersimpan. Seluruh status keputusan disimpan sebagai opportunity record.")
            st.session_state.loaded_property_id = propid

# ============================ PAGE 3: CASHFLOW =============================
elif page == "Investor Cashflow":
    st.title("Investor Cashflow & Liquidity")
    profile, events, liquidity = get_cash_data()
    st.caption("User menginput real cash dan kemungkinan pengeluaran. Sistem menghitung kapasitas investasi; sistem tidak membuat asumsi pengeluaran sendiri.")
    with st.form("cash_profile_form"):
        real_cash = st.number_input("Real cash saat ini (Rp)", min_value=0, step=1_000_000, value=safe_int(profile.get("real_cash")))
        reserve_pct = st.slider("Cadangan likuiditas minimum (%)", min_value=10, max_value=20, value=int(to_float(profile.get("reserve_pct", 20))))
        note = st.text_input("Catatan saldo / tanggal pembaruan", value=str(profile.get("note", "")))
        confirm = st.checkbox("Saya mengonfirmasi bahwa angka real cash di atas adalah kondisi terkini.", value=bool(profile.get("cash_confirmed", False)))
        save_cash = st.form_submit_button("Simpan posisi kas")
    if save_cash:
        payload = {"real_cash": real_cash, "reserve_pct": reserve_pct, "cash_confirmed": confirm, "note": note}
        upsert_record("CASH_POSITION", "profile_id", {"profile_id": "PRIMARY", "updated_at": iso_now(), "real_cash": real_cash, "reserve_pct": reserve_pct, "payload": payload})
        log_event("CASH_POSITION", "PRIMARY", "UPDATED", payload)
        st.success("Posisi kas investor diperbarui."); st.rerun()
    st.markdown("### Kemungkinan pengeluaran dana")
    st.caption("Masukkan hanya pengeluaran yang Anda perkirakan. Pengeluaran yang sudah terjadi seharusnya sudah tercermin pada real cash saat ini.")
    with st.form("outflow_form"):
        c1,c2,c3 = st.columns(3)
        with c1: out_desc = st.text_input("Keterangan pengeluaran")
        with c2: out_amount = st.number_input("Nominal (Rp)", min_value=0, step=500_000)
        with c3: out_date = st.date_input("Tanggal perkiraan", value=date.today())
        out_property = st.text_input("Property ID (opsional; untuk komitmen proyek aktif)")
        out_confirm = st.checkbox("Pengeluaran ini sudah saya rencanakan/konfirmasi", value=True)
        add_out = st.form_submit_button("Tambah kemungkinan pengeluaran")
    if add_out:
        if out_desc.strip() and out_amount > 0:
            append_record("CASHFLOW_EVENTS", {"event_id": new_id("CFE"), "profile_id": "PRIMARY", "property_id": out_property, "outflow_date": out_date.isoformat(), "direction": "OUT", "amount": out_amount, "description": out_desc, "confirmed": out_confirm, "created_at": iso_now()})
            log_event("CASHFLOW", "PRIMARY", "OUTFLOW_ADDED", {"description": out_desc, "amount": out_amount})
            st.success("Pengeluaran ditambahkan."); st.rerun()
        else: st.warning("Isi keterangan dan nominal lebih dari nol.")
    events = read_table("CASHFLOW_EVENTS")
    if events:
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
        with st.form("delete_outflow_form"):
            ids = [str(x.get("event_id")) for x in events]
            selected_event = st.selectbox("Hapus input pengeluaran yang tidak lagi berlaku", ids)
            delete_event = st.form_submit_button("Hapus pengeluaran terpilih")
        if delete_event:
            # Append a reversal/inactive marker; preserve audit history.
            original = next((x for x in events if str(x.get("event_id")) == str(selected_event)), None)
            if original:
                original["confirmed"] = False
                original["description"] = str(original.get("description", "")) + " [CANCELLED]"
                upsert_record("CASHFLOW_EVENTS", "event_id", original)
                log_event("CASHFLOW", selected_event, "CANCELLED", {})
                st.success("Pengeluaran dibatalkan; riwayat tetap tersimpan.")
                st.rerun()
    profile, events, liquidity = get_cash_data()
    st.markdown("### Posisi likuiditas terkini")
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Real cash", idr(liquidity["real_cash"]))
    k2.metric("Forecast outflow", idr(liquidity["forecast_outflows"]))
    k3.metric("Reserve", idr(liquidity["liquidity_reserve"]))
    k4.metric("Kas tersedia", idr(liquidity["cash_available_for_new_project"]))
    st.caption("Saldo kas tersedia = real cash – pengeluaran terkonfirmasi mendatang – reserve. Pengeluaran belum terkonfirmasi tidak mengurangi kapasitas.")
    st.markdown("### Referensi kebutuhan biaya aset aktif (tidak otomatis mengurangi kas)")
    active_rows = []
    for pr in [x for x in list_properties() if x.get("lifecycle_status") in {"WON", "ACTIVE"}]:
        pay = record_payload(pr); latest = pay.get("latest_analysis") or {}; win = pay.get("win_details", {})
        in_data = latest.get("calculation_inputs", {})
        if not in_data: in_data = {"property": latest.get("property", {}), "survey": latest.get("survey", {}), "costs": latest.get("costs", {}), "rules": latest.get("rules", {})}
        win_bid = to_float(win.get("win_price"), to_float(pr.get("auction_limit")))
        exit_price = to_float((latest.get("market") or {}).get("conservative_exit"))
        estimate = calculate_project(win_bid, exit_price, in_data) if win_bid > 0 and exit_price > 0 else {}
        actuals = [x for x in read_table("COST_ACTUALS") if x.get("property_id") == pr.get("property_id") and str(x.get("category", "")).lower() not in {"selling", "biaya penjualan"}]
        actual_sum = sum(to_float(x.get("amount")) for x in actuals)
        budget = to_float(estimate.get("capital_before_sale"))
        active_rows.append({"Objek":pr.get("name"),"Tahap":pay.get("project_stage","Settlement"),"Estimasi modal proyek":budget,"Biaya aktual tercatat":actual_sum,"Indikasi sisa estimasi":max(0,budget-actual_sum)})
    if active_rows:
        st.dataframe(pd.DataFrame(active_rows), use_container_width=True, hide_index=True, column_config={"Estimasi modal proyek":st.column_config.NumberColumn(format="Rp %.0f"),"Biaya aktual tercatat":st.column_config.NumberColumn(format="Rp %.0f"),"Indikasi sisa estimasi":st.column_config.NumberColumn(format="Rp %.0f")})
        st.info("Angka ini hanya referensi estimasi. Tambahkan pengeluaran mendatang sebagai Cashflow Event secara manual apabila memang Anda perkirakan/konfirmasikan akan keluar.")
    else: st.caption("Belum ada aset aktif.")

# ======================== PAGE 4: PORTFOLIO COMPARISON =====================
elif page == "Portfolio Comparison":
    st.title("Portfolio Decision Center")
    props = list_properties(); analyses = list_analyses(); _,_,liquidity = get_cash_data(); rules = get_rules()
    latest_by_pid = {}
    for a in analyses:
        pid = str(a.get("property_id"))
        if pid not in latest_by_pid or str(a.get("analyzed_at")) > str(latest_by_pid[pid].get("analyzed_at")): latest_by_pid[pid] = a
    prospect_props = [p for p in props if p.get("lifecycle_status") not in {"WON", "ACTIVE", "SOLD"} and p.get("property_id") in latest_by_pid]
    options = {f"{p.get('name','')} · {p.get('lot_code','')} · {p.get('decision_status','')} · {p.get('property_id')}": p.get("property_id") for p in prospect_props}
    selected_labels = st.multiselect("Pilih objek yang akan dibandingkan", list(options.keys()))
    if selected_labels and st.button("Bandingkan dengan cashflow terkini", type="primary"):
        rankings = []
        for label in selected_labels:
            pid = options[label]; snap = record_payload(latest_by_pid[pid])
            if not snap: continue
            data = {"property": snap.get("property", {}), "survey": snap.get("survey", {}), "legal": snap.get("legal", {}), "costs": snap.get("costs", {}), "comparables": snap.get("comparables", []), "risk_register": snap.get("risk_register", []), "risk_reviewed": snap.get("risk_reviewed", False)}
            # Current profile confirmation is refreshed; historic snapshot inputs remain immutable.
            liq = dict(liquidity); cash_profile, _, _ = get_cash_data(); liq["cash_confirmed"] = bool(cash_profile.get("cash_confirmed", False))
            new_result = run_underwriting(data, liq, snap.get("rules", rules))
            rankings.append({"property_id": pid, "name": data["property"].get("name"), "lot_code": data["property"].get("lot_code"), "decision_status": new_result["decision"]["status"], "eligibility_index_pct": new_result["eligibility_index_pct"], "conservative_arv": new_result["market"].get("conservative_exit"), "roi_at_limit_pct": new_result["at_limit"].get("roi_pct"), "net_profit_at_limit": new_result["at_limit"].get("net_profit"), "max_bid": new_result["bidding"].get("max_bid"), "walk_away_from": new_result["bidding"].get("walk_away_from"), "cash_need": new_result["at_limit"].get("cash_requirement_including_reserve"), "blockers": new_result["decision"].get("blockers"), "analysis": new_result})
        order = {"GO":0, "CONDITIONAL GO":1, "HOLD":2, "DO NOT BID":3}
        rankings.sort(key=lambda x: (order.get(x["decision_status"], 9), -x["eligibility_index_pct"]))
        st.session_state.portfolio_rankings = rankings
        st.session_state.portfolio_ai_review = None
    rankings = st.session_state.get("portfolio_rankings", [])
    if rankings:
        table = [{k:v for k,v in r.items() if k not in {"analysis", "blockers"}} for r in rankings]
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True, column_config={"conservative_arv": st.column_config.NumberColumn("Conservative ARV", format="Rp %.0f"), "net_profit_at_limit": st.column_config.NumberColumn("Profit @ limit", format="Rp %.0f"), "max_bid": st.column_config.NumberColumn("Maximum bid", format="Rp %.0f"), "walk_away_from": st.column_config.NumberColumn("Walk away", format="Rp %.0f"), "cash_need": st.column_config.NumberColumn("Modal dibutuhkan", format="Rp %.0f"), "eligibility_index_pct": st.column_config.NumberColumn("Indeks (%)", format="%.1f"), "roi_at_limit_pct": st.column_config.NumberColumn("ROI (%)", format="%.1f")})
        eligible = [x for x in rankings if x["decision_status"] in {"GO", "CONDITIONAL GO"}]
        if eligible: st.success(f"Kandidat Python teratas: {eligible[0]['name']} ({eligible[0]['decision_status']}). Indeks merupakan skor screening, bukan probabilitas profit.")
        else: st.warning("HOLD ALL — tidak ada objek dalam shortlist yang lolos gate Python.")
        if st.button("Review shortlist dengan Gemini (opsional)", disabled=not GEMINI_KEY):
            try:
                candidates = [{k:r.get(k) for k in ["property_id","name","decision_status","eligibility_index_pct","roi_at_limit_pct","net_profit_at_limit","cash_need","max_bid","walk_away_from","blockers"]} for r in rankings]
                st.session_state.portfolio_ai_review = review_portfolio(GEMINI_KEY, GEMINI_MODEL, candidates)
            except Exception as exc: st.error(str(exc))
        if st.session_state.get("portfolio_ai_review"): st.json(st.session_state.portfolio_ai_review)
        for r in rankings:
            with st.expander(f"{r['name']} · {r['decision_status']} — alasan/blocker"):
                for b in r.get("blockers", []): st.write("•", b)

# ============================ PAGE 5: ACTIVE ===============================
elif page == "Active Properties":
    st.title("Active Property Management")
    props = [p for p in list_properties() if p.get("lifecycle_status") in {"WON", "ACTIVE"}]
    if not props: st.info("Belum ada objek yang dimenangkan. Dari Database & History atau New Auction Analysis, tandai objek sebagai WON setelah hasil lelang diketahui.")
    else:
        options = {f"{p.get('name')} · {p.get('lot_code')} · {p.get('lifecycle_status')}": p for p in props}
        label = st.selectbox("Pilih aset aktif", list(options.keys())); p = options[label]; pid = p["property_id"]; payload = record_payload(p); input_data = payload.get("input_data", {}); prop_data = input_data.get("property", {})
        st.markdown(f"### {p.get('name')} · {p.get('lot_code')}")
        win = payload.get("win_details", {})
        active_actual_rows = [x for x in read_table("COST_ACTUALS") if x.get("property_id")==pid]
        active_actual_total = sum(to_float(x.get("amount")) for x in active_actual_rows if str(x.get("category", "")).lower() not in {"selling", "biaya penjualan"})
        latest = payload.get("latest_analysis") or {}
        calc_inputs = latest.get("calculation_inputs") or {"property":latest.get("property",{}),"survey":latest.get("survey",{}),"costs":latest.get("costs",{}),"rules":latest.get("rules",{})}
        winning_price = to_float(win.get("win_price", p.get("auction_limit")))
        conservative_exit = to_float((latest.get("market") or {}).get("conservative_exit"))
        active_estimate = calculate_project(winning_price, conservative_exit, calc_inputs) if winning_price > 0 and conservative_exit > 0 else {}
        estimate_capital = to_float(active_estimate.get("capital_before_sale"))
        remaining_estimate = estimate_capital - active_actual_total
        k1,k2,k3,k4 = st.columns(4); k1.metric("Harga menang", idr(winning_price)); k2.metric("Lifecycle", p.get("lifecycle_status")); k3.metric("Biaya aktual tercatat", idr(active_actual_total)); k4.metric("Indikasi modal tersisa", idr(remaining_estimate), delta="Over budget" if remaining_estimate < 0 else None, delta_color="inverse")
        st.caption(f"Estimasi modal awal pada harga menang: {idr(estimate_capital)}. Indikasi sisa bukan kewajiban otomatis; perbarui berdasarkan biaya/komitmen aktual.")
        st.markdown("### Budget vs actual per kategori")
        bva = budget_actual_table(active_estimate, active_actual_rows)
        st.dataframe(bva, use_container_width=True, hide_index=True, column_config={"Anggaran":st.column_config.NumberColumn(format="Rp %.0f"),"Aktual":st.column_config.NumberColumn(format="Rp %.0f"),"Varians (Aktual - Anggaran)":st.column_config.NumberColumn(format="Rp %.0f")})
        with st.form("win_update_form"):
            c1,c2,c3 = st.columns(3)
            with c1: win_price = st.number_input("Harga menang lelang (Rp)", min_value=0, step=1_000_000, value=safe_int(win.get("win_price", prop_data.get("auction_limit", 0))))
            with c2:
                try: win_date_default = date.fromisoformat(str(win.get("win_date") or date.today().isoformat())[:10])
                except ValueError: win_date_default = date.today()
                win_date = st.date_input("Tanggal menang", value=win_date_default)
            with c3: lifecycle_stage = st.selectbox("Tahap proyek", PROJECT_STAGES[:-1], index=PROJECT_STAGES[:-1].index(payload.get("project_stage", "Settlement")) if payload.get("project_stage") in PROJECT_STAGES[:-1] else 0)
            notes = st.text_area("Catatan progres")
            upd = st.form_submit_button("Simpan progres proyek")
        if upd:
            payload["win_details"] = {"win_price": win_price, "win_date": win_date.isoformat()}; payload["project_stage"] = lifecycle_stage; payload["progress_notes"] = notes
            rec = {**p, "updated_at": iso_now(), "lifecycle_status": "ACTIVE", "payload": payload}
            upsert_record("PROPERTIES", "property_id", rec); log_event("PROPERTY", pid, "STAGE_UPDATED", {"stage": lifecycle_stage}); st.success("Tahap proyek diperbarui."); st.rerun()
        st.markdown("### Catat pengeluaran aktual")
        st.info("Catat biaya yang benar-benar keluar. Uang jaminan yang diperhitungkan dalam harga pelunasan bukan biaya tambahan di atas harga menang: catat total pembelian satu kali (misalnya deposit + sisa pelunasan = harga menang), jangan mencatat deposit dan harga menang penuh sekaligus.")
        with st.form("actual_cost_form"):
            a1,a2,a3 = st.columns(3)
            with a1: category = st.selectbox("Kategori", ["Pelunasan/akuisisi", "BPN/Legal", "Penguasaan/Kerahiman", "Renovasi", "Holding", "Marketing", "Selling", "Lainnya"])
            with a2: amount = st.number_input("Nominal aktual (Rp)", min_value=0, step=500_000)
            with a3: txdate = st.date_input("Tanggal transaksi", value=date.today())
            desc = st.text_input("Deskripsi / vendor / bukti")
            receipt = st.text_input("URL bukti pembayaran (opsional)")
            addcost = st.form_submit_button("Tambah biaya aktual")
        if addcost:
            if amount > 0:
                append_record("COST_ACTUALS", {"actual_id": new_id("ACT"), "property_id": pid, "transaction_date": txdate.isoformat(), "category": category, "amount": amount, "description": desc, "receipt_url": receipt, "created_at": iso_now()})
                log_event("COST_ACTUAL", pid, "ADDED", {"amount": amount, "category": category}); st.success("Pengeluaran aktual dicatat."); st.rerun()
        milestones = [m for m in read_table("PROJECT_MILESTONES") if m.get("property_id") == pid]
        if milestones: st.dataframe(pd.DataFrame(milestones), use_container_width=True, hide_index=True)
        with st.form("milestone_form"):
            stage = st.selectbox("Milestone", PROJECT_STAGES)
            status = st.selectbox("Status", ["Not Started", "In Progress", "Completed", "Delayed"])
            planned = st.text_input("Tanggal rencana (YYYY-MM-DD)")
            actual = st.text_input("Tanggal aktual (YYYY-MM-DD)")
            milestone_note = st.text_input("Catatan")
            savem = st.form_submit_button("Simpan milestone")
        if savem:
            rec = {"milestone_id": new_id("MIL"), "property_id": pid, "stage": stage, "status": status, "planned_date": planned, "actual_date": actual, "notes": milestone_note, "updated_at": iso_now()}
            if repo: repo.save_milestone(rec); cached_read.clear()
            else:
                milestones_local = st.session_state.local_db.setdefault("PROJECT_MILESTONES", [])
                match = next((i for i, old in enumerate(milestones_local) if str(old.get("property_id")) == str(pid) and str(old.get("stage")) == str(stage)), None)
                if match is None: milestones_local.append(rec)
                else: milestones_local[match] = {**milestones_local[match], **rec}
            payload["project_stage"] = stage; upsert_record("PROPERTIES", "property_id", {**p, "updated_at": iso_now(), "payload": payload, "lifecycle_status": "ACTIVE"}); st.success("Milestone tersimpan."); st.rerun()
        st.markdown("### Closing / tandai terjual")
        with st.form("closing_form"):
            sold_date = st.date_input("Tanggal closing", value=date.today())
            listing_start = st.date_input("Tanggal mulai listing", value=date.today())
            closing_price = st.number_input("Harga closing (Rp)", min_value=0, step=1_000_000)
            selling_actual = st.number_input("Selling cost aktual (Rp)", min_value=0, step=250_000)
            total_months = st.number_input("Total holding aktual (bulan)", min_value=0.0, step=0.5)
            closing_notes = st.text_input("Catatan closing")
            actual_costs_confirmed = st.checkbox("Saya memastikan seluruh biaya aktual proyek sudah dicatat (akuisisi, BPN, penguasaan, renovasi, holding, marketing dan penjualan).")
            close = st.form_submit_button("Tandai SOLD / CLOSED")
        if close:
            if closing_price <= 0: st.error("Harga closing wajib diisi.")
            elif not actual_costs_confirmed: st.error("Konfirmasi kelengkapan biaya aktual diperlukan agar profit dan ROI closing tidak menyesatkan.")
            else:
                closing = {"property_id": pid, "sold_date": sold_date.isoformat(), "listing_start_date": listing_start.isoformat(), "closing_price": closing_price, "selling_cost_actual": selling_actual, "total_holding_months": total_months, "notes": closing_notes, "updated_at": iso_now(), "payload": {"closing_price": closing_price}}
                upsert_record("SALES_CLOSING", "property_id", closing)
                payload["project_stage"] = "Sold / Closed"
                upsert_record("PROPERTIES", "property_id", {**p, "updated_at": iso_now(), "lifecycle_status": "SOLD", "decision_status": p.get("decision_status", "GO"), "payload": payload})
                log_event("PROPERTY", pid, "SOLD", closing); st.success("Properti masuk Closed Projects."); st.rerun()

# ============================ PAGE 6: CLOSED ===============================
elif page == "Closed Projects & Track Record":
    st.title("Closed Projects & Track Record")
    sold = [p for p in list_properties() if p.get("lifecycle_status") == "SOLD"]
    if not sold: st.info("Belum ada aset berstatus SOLD.")
    else:
        summaries = []
        for p in sold:
            close = next((x for x in read_table("SALES_CLOSING") if x.get("property_id") == p.get("property_id")), {})
            costs = [x for x in read_table("COST_ACTUALS") if x.get("property_id") == p.get("property_id")]
            summary = actual_project_summary(costs, close)
            summaries.append({"Property ID": p.get("property_id"), "Objek": p.get("name"), "Lokasi": p.get("address"), "Tanggal Sold": close.get("sold_date"), "Harga Closing": summary["closing_price"], "Modal Aktual": summary["total_actual_cost"], "Profit Aktual": summary["net_profit_actual"], "ROI Aktual (%)": summary["roi_actual_pct"], "Holding (bulan)": summary["total_holding_months"]})
        df = pd.DataFrame(summaries)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={"Harga Closing": st.column_config.NumberColumn(format="Rp %.0f"), "Modal Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "Profit Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "ROI Aktual (%)": st.column_config.NumberColumn(format="%.1f%%")})
        total_profit = sum(to_float(x.get("Profit Aktual")) for x in summaries)
        k1,k2,k3 = st.columns(3); k1.metric("Total aset terjual", len(sold)); k2.metric("Total profit aktual", idr(total_profit)); k3.metric("Rata-rata ROI aktual", pct(df["ROI Aktual (%)"].dropna().mean() if df["ROI Aktual (%)"].notna().any() else None))
        selected = st.selectbox("Pilih proyek untuk melihat rincian biaya", [x.get("property_id") for x in sold])
        row = next(p for p in sold if p.get("property_id") == selected); costs = [x for x in read_table("COST_ACTUALS") if x.get("property_id") == selected]
        close = next((x for x in read_table("SALES_CLOSING") if x.get("property_id") == selected), {})
        st.markdown(f"### {row.get('name')} · {row.get('address')}")
        if costs: st.dataframe(pd.DataFrame(costs), use_container_width=True, hide_index=True)
        st.markdown("### Budget vs actual final")
        sold_payload = record_payload(row); sold_latest = sold_payload.get("latest_analysis") or {}; sold_win = sold_payload.get("win_details", {})
        sold_inputs = sold_latest.get("calculation_inputs") or {"property":sold_latest.get("property",{}),"survey":sold_latest.get("survey",{}),"costs":sold_latest.get("costs",{}),"rules":sold_latest.get("rules",{})}
        sold_bid = to_float(sold_win.get("win_price"), to_float(row.get("auction_limit")))
        sold_arv = to_float((sold_latest.get("market") or {}).get("conservative_exit"))
        sold_estimate = calculate_project(sold_bid, sold_arv, sold_inputs) if sold_bid > 0 and sold_arv > 0 else {}
        sold_bva = budget_actual_table(sold_estimate, costs)
        st.dataframe(sold_bva, use_container_width=True, hide_index=True, column_config={"Anggaran":st.column_config.NumberColumn(format="Rp %.0f"),"Aktual":st.column_config.NumberColumn(format="Rp %.0f"),"Varians (Aktual - Anggaran)":st.column_config.NumberColumn(format="Rp %.0f")})
        st.json(actual_project_summary(costs, close))
        st.download_button("Unduh track record CSV", df.to_csv(index=False).encode("utf-8-sig"), "closed-projects-track-record.csv", "text/csv")

# ============================ PAGE 7: DATABASE =============================
elif page == "Database & History":
    st.title("Database & History")
    props = list_properties()
    if props:
        df = pd.DataFrame([{k:p.get(k) for k in ["property_id","lot_code","name","address","auction_date","auction_limit","decision_status","lifecycle_status","updated_at"]} for p in props])
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={"auction_limit": st.column_config.NumberColumn(format="Rp %.0f")})
        selection = st.selectbox("Pilih objek", [p.get("property_id") for p in props])
        selected = next(p for p in props if p.get("property_id") == selection)
        with st.expander("Detail objek / lifecycle", expanded=True): st.json({**{k:v for k,v in selected.items() if k != "payload"}, "payload": record_payload(selected)})
        if selected.get("lifecycle_status") not in {"WON", "ACTIVE", "SOLD"}:
            with st.form("update_opportunity_status"):
                new_decision = st.selectbox("Decision status", DECISION_STATUSES, index=DECISION_STATUSES.index(selected.get("decision_status", "HOLD")) if selected.get("decision_status") in DECISION_STATUSES else 0)
                editable_lifecycle = [x for x in LIFECYCLE_STATUSES if x != "SOLD"]
                new_lifecycle = st.selectbox("Lifecycle status", editable_lifecycle, index=editable_lifecycle.index(selected.get("lifecycle_status", "PROSPECT")) if selected.get("lifecycle_status") in editable_lifecycle else 0)
                mark_win_price = st.number_input("Harga menang (isi bila lifecycle WON)", min_value=0, step=1_000_000)
                mark_win_date = st.date_input("Tanggal menang", value=date.today())
                update_status = st.form_submit_button("Update status objek")
            if update_status:
                if new_lifecycle == "WON" and mark_win_price <= 0:
                    st.error("Harga menang wajib diisi sebelum aset dipindahkan ke Active Properties.")
                else:
                    payload = record_payload(selected)
                    if new_lifecycle == "WON": payload["win_details"] = {"win_price": mark_win_price, "win_date": mark_win_date.isoformat()}
                    upsert_record("PROPERTIES", "property_id", {**selected, "decision_status": new_decision, "lifecycle_status": new_lifecycle, "updated_at": iso_now(), "payload": payload})
                    log_event("PROPERTY", selection, "STATUS_CHANGED", {"decision": new_decision, "lifecycle": new_lifecycle})
                    st.success("Status diperbarui.")
                    st.rerun()
    else: st.info("Database belum memiliki objek. Simpan analisis pertama dari menu New Auction Analysis.")
    st.markdown("### Riwayat perubahan")
    history = read_table("HISTORY")
    if history: st.dataframe(pd.DataFrame(history).sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else: st.info("Belum ada riwayat.")
    with st.expander("Ekspor database (CSV)"):
        tabs = list(SCHEMA.keys())
        tab = st.selectbox("Pilih tabel", tabs)
        records = read_table(tab)
        if records: st.download_button("Unduh CSV", pd.DataFrame(records).to_csv(index=False).encode("utf-8-sig"), f"{tab.lower()}.csv", "text/csv")
        else: st.caption("Tabel masih kosong.")

# ============================ PAGE 8: SETTINGS =============================
elif page == "Settings & Rules":
    st.title("Settings & Rules")
    st.caption("Default biaya adalah asumsi underwriting. Verifikasi regulasi dan quotation aktual sebelum mengambil keputusan.")
    rules = get_rules()
    with st.form("rules_form"):
        st.subheader("Acquisition & regional tax assumptions")
        c1,c2,c3 = st.columns(3)
        with c1:
            buyer_fee = st.number_input("Bea lelang pembeli (%)", min_value=0.0, max_value=20.0, value=to_float(rules["buyer_auction_fee_pct"]))
            bphtb_rate = st.number_input("BPHTB (%)", min_value=0.0, max_value=20.0, value=to_float(rules["bphtb_rate_pct"]))
            npoptkp = st.number_input("NPOPTKP (Rp)", min_value=0, step=5_000_000, value=safe_int(rules["npoptkp"]))
        with c2:
            basis_mode = st.selectbox("Dasar BPHTB (perlu verifikasi aturan daerah)", ["max_bid_or_njop", "bid_only", "njop_only"], index=["max_bid_or_njop","bid_only","njop_only"].index(rules.get("bphtb_basis_mode","max_bid_or_njop")))
            bpn = st.number_input("Estimasi PNBP BPN (Rp)", min_value=0, step=250_000, value=safe_int(rules["bpn_pnbp_cost"]))
            roya = st.number_input("Estimasi roya (Rp)", min_value=0, step=250_000, value=safe_int(rules["roya_cost"]))
        with c3:
            other_admin = st.number_input("Administrasi akuisisi lain (Rp)", min_value=0, step=250_000, value=safe_int(rules["other_acquisition_admin"]))
            notary_buy = st.number_input("Jasa PPAT/notaris akuisisi (default 0) (Rp)", min_value=0, step=250_000, value=safe_int(rules["acquisition_notary_ppat_fee"]))
        st.subheader("Selling costs")
        c1,c2,c3,c4 = st.columns(4)
        with c1: pph = st.number_input("PPh Final (%)", min_value=0.0, max_value=20.0, value=to_float(rules["seller_final_tax_pct"]))
        with c2: agent = st.number_input("Komisi agen (%)", min_value=0.0, max_value=20.0, value=to_float(rules["seller_agent_pct"]))
        with c3: ajb = st.number_input("Porsi AJB/PPAT penjual (%)", min_value=0.0, max_value=2.0, value=to_float(rules["seller_ajb_ppat_pct"]))
        with c4: misc = st.number_input("Misc selling cost (Rp)", min_value=0, step=250_000, value=safe_int(rules["seller_misc_fixed"]))
        st.subheader("Project & market assumptions")
        c1,c2,c3 = st.columns(3)
        with c1: holding = st.number_input("Holding cost / bulan (Rp)", min_value=0, step=250_000, value=safe_int(rules["monthly_holding_cost"]))
        with c2: contingency = st.number_input("Contingency renovasi (%)", min_value=0.0, max_value=100.0, value=to_float(rules["renovation_contingency_pct"]))
        with c3: negotiation = st.number_input("Negotiation discount (%)", min_value=0.0, max_value=50.0, value=to_float(rules["negotiation_discount_pct"]))
        c1,c2,c3 = st.columns(3)
        with c1: quick_sale = st.number_input("Quick-sale discount (%)", min_value=0.0, max_value=50.0, value=to_float(rules["quick_sale_discount_pct"]))
        with c2: min_roi = st.number_input("Minimum ROI seluruh proyek (%)", min_value=0.0, max_value=200.0, value=to_float(rules["minimum_roi_pct"]))
        with c3: mid_roi = st.number_input("Target ROI batas tengah (%)", min_value=0.0, max_value=300.0, value=to_float(rules["mid_roi_pct"]))
        save_rules = st.form_submit_button("Simpan rules")
    if save_rules:
        updated = {"buyer_auction_fee_pct":buyer_fee,"bphtb_rate_pct":bphtb_rate,"npoptkp":npoptkp,"bphtb_basis_mode":basis_mode,"bpn_pnbp_cost":bpn,"roya_cost":roya,"other_acquisition_admin":other_admin,"acquisition_notary_ppat_fee":notary_buy,"seller_final_tax_pct":pph,"seller_agent_pct":agent,"seller_ajb_ppat_pct":ajb,"seller_misc_fixed":misc,"monthly_holding_cost":holding,"renovation_contingency_pct":contingency,"negotiation_discount_pct":negotiation,"quick_sale_discount_pct":quick_sale,"minimum_roi_pct":min_roi,"mid_roi_pct":mid_roi}
        st.session_state.rules_local.update(updated)
        upsert_record("RULES_CONFIG", "rule_key", {"rule_key":"GLOBAL","value":updated,"updated_at":iso_now(),"source_note":"User-configured assumptions; verify by property jurisdiction/transaction."})
        log_event("RULES", "GLOBAL", "UPDATED", updated); st.success("Rules tersimpan."); st.rerun()
    st.markdown("### Konfigurasi API")
    st.code(f"GEMINI_MODEL = {GEMINI_MODEL}\nGEMINI_API_KEY = {'configured' if GEMINI_KEY else 'not configured'}\nSPREADSHEET_ID = {'configured' if spreadsheet_id else 'not configured'}", language="text")
    st.markdown("Gemini 3.5 Flash-Lite Free Tier tidak menyediakan Google Search grounding. V1 menggunakan comparable manual; jangan kirim data pribadi sensitif yang tidak diperlukan.")
