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
from core.lifecycle import actual_project_summary, mark_property_won
from core.project_ledger import summarize_project_ledger
from core.ledger_transactions import reconcile_budget_payment_change
from core.project_form_options import ACTUAL_CATEGORIES, BUDGET_CATEGORIES, subcategory_options, scope_options
from core.onboarding import build_project_onboarding_records
from core.market_engine import assess_comparables
from core.form_state import form_state_from_input_data
from core.review_state import sync_review_confirmation
from core.renovation_engine import CATEGORIES as RENOVATION_CATEGORIES, rab_item_is_in_scope, infer_renovation_category
from core.calculator import calculate_project
from services.gemini_parser import extract_auction_document, parse_comparable_narrative, review_investment, review_portfolio, estimate_renovation_rab, assess_market_with_ai, file_sha256
from services.comparable_importer import parse_comparable_paste
from storage.gsheets_db import GoogleSheetsDB, SCHEMA
from storage.drive_storage import upload_file_to_drive
from reports.report_builder import build_analysis_markdown

st.set_page_config(page_title=APP_NAME, page_icon="🏠", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
:root{--pfms-ink:#172B4D;--pfms-muted:#667085;--pfms-line:#E5EAF0;--pfms-brand:#0F766E;--pfms-soft:#F5F8FA}
.block-container{max-width:1480px;padding-top:1.05rem;padding-bottom:3rem}
[data-testid="stMetric"]{background:#F7FAFC;border:1px solid #E5EAF0;padding:.8rem 1rem;border-radius:14px;min-height:112px}
[data-testid="stMetricLabel"]{color:#526174;font-weight:600}
[data-testid="stMetricValue"]{color:var(--pfms-ink)}
.hero{padding:1.35rem 1.5rem;border:1px solid #DCE8E7;border-radius:18px;background:linear-gradient(115deg,#F0F8F7,#F7FAFC);margin-bottom:1rem}
.hero h1,.hero h2{color:var(--pfms-ink);margin-bottom:.3rem}
.hero p{color:#526174;margin-bottom:0}
.small-muted{font-size:.85rem;color:var(--pfms-muted)}
.stTabs [data-baseweb="tab-list"]{gap:8px;border-bottom:1px solid var(--pfms-line)}
.stTabs [data-baseweb="tab"]{height:48px;padding:0 14px;border-radius:10px 10px 0 0;font-weight:600}
div.stButton>button,div.stDownloadButton>button{border-radius:10px;min-height:2.55rem;font-weight:600}
div[data-testid="stDataFrame"]{border:1px solid var(--pfms-line);border-radius:12px;overflow:hidden}
div[data-testid="stExpander"]{border:1px solid var(--pfms-line);border-radius:12px}
[data-testid="stAlert"]{border-radius:12px}
section[data-testid="stSidebar"]{border-right:1px solid var(--pfms-line)}
section[data-testid="stSidebar"] [data-testid="stRadio"] label{padding-top:.18rem;padding-bottom:.18rem}
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
    acquisition_actual = sum(actual.get(k, 0.0) for k in ["pelunasan/akuisisi", "bea lelang", "bphtb", "bpn/legal", "bpn/legalitas"])
    renovation_actual = actual.get("renovasi", 0.0)
    holding_actual = actual.get("holding", 0.0)
    marketing_actual = actual.get("marketing", 0.0) + actual.get("lainnya", 0.0)
    possession_actual = actual.get("penguasaan/kerahiman", 0.0)
    selling_actual = sum(actual.get(k, 0.0) for k in ["selling", "penjualan", "biaya penjualan", "pajak penjualan", "komisi agen"])
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

# Guided risk library: defaults are conservative planning placeholders, not official tariffs.
RISK_PRESETS = {
    "Penghuni belum bersedia mengosongkan objek": {"category":"Penguasaan", "risk_description":"Penghuni belum bersedia mengosongkan objek", "probability_1_5":4, "impact_1_5":5, "cost_reserve":100_000_000, "critical":True, "mitigation":"Verifikasi penghuni dan dasar penguasaan; negosiasi sukarela terdokumentasi; konsultasi bantuan hukum sebelum bidding.", "status":"Open"},
    "Dokumen/identitas objek belum cocok": {"category":"Legalitas", "risk_description":"Dokumen atau identitas fisik objek belum cocok dengan pengumuman/sertifikat", "probability_1_5":3, "impact_1_5":5, "cost_reserve":25_000_000, "critical":True, "mitigation":"Cocokkan alamat, nomor hak, luas, peta bidang dan objek fisik; minta klarifikasi tertulis sebelum bidding.", "status":"Open"},
    "Potensi sengketa atau klaim pihak ketiga": {"category":"Legalitas", "risk_description":"Potensi sengketa, sita lain, atau klaim pihak ketiga belum terselesaikan", "probability_1_5":2, "impact_1_5":5, "cost_reserve":50_000_000, "critical":True, "mitigation":"Telusuri dokumen dan status hak; konsultasi hukum independen; jangan bidding selama klaim material belum jelas.", "status":"Open"},
    "Interior belum diperiksa": {"category":"Fisik/Renovasi", "risk_description":"Interior belum diperiksa sehingga kerusakan tersembunyi belum diketahui", "probability_1_5":4, "impact_1_5":4, "cost_reserve":30_000_000, "critical":False, "mitigation":"Lakukan inspeksi interior dan dokumentasikan atap, plafon, lantai, kamar mandi, listrik, air serta indikasi rembes.", "status":"Open"},
    "Indikasi kebocoran/kerusakan atap": {"category":"Fisik/Renovasi", "risk_description":"Terdapat indikasi kebocoran atau kerusakan atap/talang", "probability_1_5":3, "impact_1_5":4, "cost_reserve":20_000_000, "critical":False, "mitigation":"Inspeksi saat/ setelah hujan; cek genteng, nok, talang, rangka dan plafon; minta penawaran tukang.", "status":"Open"},
    "Indikasi masalah struktur": {"category":"Fisik/Renovasi", "risk_description":"Terdapat retak/indikasi masalah struktur yang perlu diperiksa tenaga kompeten", "probability_1_5":2, "impact_1_5":5, "cost_reserve":40_000_000, "critical":True, "mitigation":"Minta pemeriksaan teknis; jangan menyimpulkan struktur aman hanya dari foto; tahan keputusan sampai temuan dinilai.", "status":"Open"},
    "Banjir/genangan lingkungan": {"category":"Lingkungan", "risk_description":"Riwayat banjir atau genangan di lingkungan belum terverifikasi", "probability_1_5":3, "impact_1_5":4, "cost_reserve":20_000_000, "critical":False, "mitigation":"Tanya RT/tetangga; cek elevasi, drainase, bekas genangan dan riwayat hujan.", "status":"Open"},
    "Akses jalan/parkir membatasi pembeli": {"category":"Pasar/Lokasi", "risk_description":"Akses jalan atau parkir membatasi segmen calon pembeli", "probability_1_5":3, "impact_1_5":3, "cost_reserve":5_000_000, "critical":False, "mitigation":"Ukur lebar jalan dan uji akses kendaraan; sesuaikan comparable serta strategi/harga jual.", "status":"Open"},
    "Biaya renovasi berpotensi membengkak": {"category":"Fisik/Renovasi", "risk_description":"RAB masih indikatif dan berpotensi membengkak setelah pekerjaan dibuka", "probability_1_5":4, "impact_1_5":4, "cost_reserve":20_000_000, "critical":False, "mitigation":"Rinci volume pekerjaan; minta minimal dua penawaran; gunakan contingency terpisah dan approval sebelum pekerjaan tambah.", "status":"Open"},
    "Keterlambatan legalitas/penguasaan": {"category":"Waktu/Holding", "risk_description":"Pengurusan legalitas atau penguasaan berpotensi lebih lama dari rencana", "probability_1_5":3, "impact_1_5":4, "cost_reserve":15_000_000, "critical":False, "mitigation":"Buat checklist dokumen dan milestone; sediakan jadwal buffer; hitung ulang holding cost jika terlambat.", "status":"Open"},
    "Harga pasar/comparable kurang kuat": {"category":"Pasar/Likuiditas", "risk_description":"Comparable belum cukup setara atau harga masih berupa asking price", "probability_1_5":4, "impact_1_5":4, "cost_reserve":0, "critical":True, "mitigation":"Tambah listing yang setara, verifikasi status dan tanggal, cari bukti transaksi atau konfirmasi agen.", "status":"Open"},
    "Tunggakan utilitas/PBB/IPL": {"category":"Biaya/Administrasi", "risk_description":"Tunggakan listrik, air, PBB, IPL atau kewajiban lingkungan belum diketahui", "probability_1_5":3, "impact_1_5":3, "cost_reserve":10_000_000, "critical":False, "mitigation":"Minta informasi pengelola/instansi; cek rekening, PBB dan bukti pembayaran; masukkan tunggakan aktual.", "status":"Open"},
}

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
    active_property_ids = {str(p.get("property_id")) for p in read_table("PROPERTIES") if p.get("lifecycle_status") in {"WON", "ACTIVE"}}
    budget_rows = [b for b in read_table("PROJECT_BUDGETS") if str(b.get("property_id")) in active_property_ids and str(b.get("status") or "Active") not in {"Cancelled", "Archived"}]
    active_commitments = sum(max(0.0, to_float(b.get("committed_unpaid"))) for b in budget_rows)
    liquidity = compute_liquidity(to_float(profile.get("real_cash")), future, to_float(profile.get("reserve_pct", 20)), active_commitments)
    liquidity["cash_confirmed"] = bool(profile.get("cash_confirmed", False))
    liquidity["active_budget_commitment_count"] = sum(1 for b in budget_rows if to_float(b.get("committed_unpaid")) > 0)
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


def as_date(value: Any, fallback: date | None = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return fallback or date.today()


def optional_date_picker(label: str, value: Any, key: str) -> str:
    """Date picker with an explicit empty state; never invent a missing date."""
    existing = str(value or "").strip()
    has_value = st.checkbox(f"{label} sudah diketahui", value=bool(existing), key=f"{key}_has_value")
    selected = st.date_input(label, value=as_date(existing), disabled=not has_value, key=f"{key}_picker")
    return selected.isoformat() if has_value else ""


def comparable_date_for_editor(value: Any) -> date | None:
    """Parse stored comparable dates without confusing day/month order."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def comparable_date_to_iso(value: Any) -> str | None:
    """Normalize DateColumn return values for JSON/Sheets persistence."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    return raw or None


# ------------------------------- Sidebar -----------------------------------
st.sidebar.markdown(f"## 🏠 {APP_NAME}")
st.sidebar.caption(f"Version {APP_VERSION}")
if repo: st.sidebar.success("Database terhubung")
else: st.sidebar.warning("Mode sementara · database belum terhubung" if not db_error else db_error[:180])
GEMINI_KEY = str(secret("GEMINI_API_KEY", "") or "")
GEMINI_MODEL = str(secret("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL)
st.sidebar.caption(f"Asisten AI: {'Siap digunakan' if GEMINI_KEY else 'Belum diaktifkan'}")
page_labels = {
    "🏠 Ringkasan utama": "Executive Dashboard",
    "➕ Analisis objek lelang": "New Auction Analysis",
    "📥 Daftarkan proyek berjalan": "Project Onboarding",
    "💰 Kas & kemampuan investasi": "Investor Cashflow",
    "⚖️ Bandingkan peluang": "Portfolio Comparison",
    "🏘️ Properti aktif": "Active Properties",
    "✅ Proyek selesai & hasil": "Closed Projects & Track Record",
    "🗂️ Database & riwayat": "Database & History",
    "⚙️ Pengaturan sistem": "Settings & Rules",
}
selected_page_label = st.sidebar.radio("MENU UTAMA", list(page_labels.keys()))
page = page_labels[selected_page_label]
if st.sidebar.button("↻ Refresh Data", use_container_width=True):
    cached_read.clear()
    st.rerun()
st.sidebar.markdown("---")
st.sidebar.caption("Analisis terukur · Risiko terlihat · Keputusan dapat diaudit")

# ============================ PAGE 1: DASHBOARD ============================
if page == "Executive Dashboard":
    st.markdown(f"<div class='hero'><h1>Ringkasan Utama</h1><p>Pantau peluang lelang, kesiapan kas, properti yang sedang dikelola, dan hasil investasi yang sudah terealisasi.</p></div>", unsafe_allow_html=True)
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
    active_ids = {str(p.get("property_id")) for p in active}
    active_budget_rows = [b for b in read_table("PROJECT_BUDGETS") if str(b.get("property_id")) in active_ids and str(b.get("status") or "Active") not in {"Cancelled", "Archived"}]
    active_budget_total = sum(max(0.0, to_float(b.get("budget_amount"))) for b in active_budget_rows)
    active_budget_committed = sum(max(0.0, to_float(b.get("committed_unpaid"))) for b in active_budget_rows)
    active_budget_forecast = sum(max(0.0, to_float(b.get("forecast_remaining"))) for b in active_budget_rows)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kas siap investasi", idr(liq["cash_available_for_new_project"]), help="Kas aktual dikurangi pengeluaran yang dikonfirmasi dan cadangan likuiditas.")
    k2.metric("Peluang tersimpan", len(opps))
    k3.metric("Aset aktif", len(active))
    k4.metric("Realisasi aset berjalan", idr(active_actual_cost), help="Budget yang sudah dipakai pada seluruh proyek WON/ACTIVE")
    #k5.metric("Profit terealisasi", idr(total_realized_profit))
    st.caption(f"Dari anggaran aset aktif: komitmen belum dibayar {idr(active_budget_committed)} · forecast pekerjaan tersisa {idr(active_budget_forecast)}.")
    st.markdown("### Kondisi portofolio")
    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.markdown("**Aset yang sedang dikelola**")
        if active:
            rows = []
            for p in active:
                pay = record_payload(p); inp = pay.get("input_data", {}); prop = inp.get("property", {})
                pb = [b for b in active_budget_rows if str(b.get("property_id")) == str(p.get("property_id"))]
                ac = [x for x in read_table("COST_ACTUALS") if str(x.get("property_id")) == str(p.get("property_id"))]
                rows.append({"Objek": p.get("name"), "Lifecycle": p.get("lifecycle_status"), "Status Analisis": p.get("decision_status"), "Limit": to_float(p.get("auction_limit")), "Anggaran berjalan": sum(to_float(b.get("budget_amount")) for b in pb), "Aktual dibayar": sum(to_float(x.get("amount")) for x in ac), "Komitmen": sum(to_float(b.get("committed_unpaid")) for b in pb), "Forecast sisa": sum(to_float(b.get("forecast_remaining")) for b in pb), "Tahap": pay.get("project_stage", "Settlement")})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, column_config={"Limit": st.column_config.NumberColumn(format="Rp %.0f"), "Anggaran berjalan": st.column_config.NumberColumn(format="Rp %.0f"), "Aktual dibayar": st.column_config.NumberColumn(format="Rp %.0f"), "Komitmen": st.column_config.NumberColumn(format="Rp %.0f"), "Forecast sisa": st.column_config.NumberColumn(format="Rp %.0f")})
        else: st.info("Belum ada properti yang dimenangkan. Semua peluang yang dianalisis tetap tersimpan sebagai prospek, termasuk yang berstatus HOLD atau DO NOT BID.")
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
    st.markdown("<div class='hero'><h1>Analisis Objek Lelang</h1><p>Ikuti empat langkah di bawah. Isi data yang diketahui, periksa hasil AI, lalu jalankan analisis untuk melihat kelayakan, total modal, kebutuhan kas, dan batas maksimal bidding.</p></div>", unsafe_allow_html=True)
    with st.expander("Panduan singkat untuk pengguna baru", expanded=False):
        st.markdown("""
        **Cara menggunakan halaman ini**
        1. **Data lelang & legalitas:** unggah pengumuman bila ada, periksa hasil ekstraksi, lalu lengkapi data objek.
        2. **Survei & risiko:** masukkan kondisi fisik, status penghuni, hasil pemeriksaan, dan risiko yang relevan.
        3. **Harga pasar:** masukkan listing pembanding. Tanggal terbit iklan boleh kosong; tanggal ditemukan berarti tanggal listing dikumpulkan.
        4. **Biaya & RAB:** periksa setiap komponen biaya, lalu centang konfirmasi setelah selesai meninjau.

        Klik **Analisis Sekarang** untuk menghitung. Klik **Simpan / Update Analisis** agar hasil tercatat di database.
        """)
    # Non-blocking progress indicator: it shows the user's place in the workflow,
    # but never prevents analysis of partial data.
    loaded_comp_rows = st.session_state.get("na_comparables_current")
    if loaded_comp_rows is None:
        loaded_comp_rows = st.session_state.get("na_comparables_editor")
    if isinstance(loaded_comp_rows, pd.DataFrame):
        comp_progress_rows = loaded_comp_rows.to_dict(orient="records")
    elif isinstance(loaded_comp_rows, list):
        comp_progress_rows = loaded_comp_rows
    else:
        comp_progress_rows = []
    comparable_progress_count = sum(
        1 for row in comp_progress_rows
        if str(row.get("name") or "").strip() and to_float(row.get("price")) > 0
        and (to_float(row.get("land_area")) > 0 or to_float(row.get("building_area")) > 0)
    )
    steps_done = [
        bool(st.session_state.get("na_lot_code") and st.session_state.get("na_address") and to_float(st.session_state.get("na_limit")) > 0),
        bool(st.session_state.get("na_survey_status") and st.session_state.get("na_survey_status") != "Belum Survei"),
        comparable_progress_count >= 5,
        bool(st.session_state.get("na_costs_reviewed", False) and st.session_state.get("na_risk_reviewed", False)),
    ]
    completed_steps = sum(steps_done)
    st.progress(completed_steps / 4, text=f"Kemajuan pengisian: {completed_steps} dari 4 langkah memiliki data utama")
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
            payload = record_payload(row)
            latest_saved = payload.get("latest_analysis") or {}
            data = payload.get("input_data") or {
                "property": latest_saved.get("property", {}),
                "survey": latest_saved.get("survey", {}),
                "legal": latest_saved.get("legal", {}),
                "costs": latest_saved.get("costs", {}),
                "comparables": latest_saved.get("comparables", []),
                "risk_register": latest_saved.get("risk_register", []),
                "risk_reviewed": latest_saved.get("risk_reviewed", False),
                "rules": latest_saved.get("rules", {}),
            }
            mapping = form_state_from_input_data(data, latest_saved)
            for k, v in mapping.items():
                st.session_state[k] = v
            st.session_state.na_last_occupancy = mapping.get("na_survey_status", "Belum Survei")
            st.session_state.na_risk_reviewed = bool(data.get("risk_reviewed", latest_saved.get("risk_reviewed", False)))
            comparable_columns = ["name", "address", "price", "njop", "land_area", "building_area", "bedrooms", "bathrooms", "condition", "condition_detail", "access", "access_detail", "price_type", "certificate", "orientation", "electricity_watt", "water_source", "source_platforms", "source_evidence", "source_url", "source_url_scope", "listing_date", "date_found", "date_found_basis", "notes", "adjustment_pct", "ai_adjustment_rationale", "ai_exclude_from_primary"]
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
            renovation_columns = ["item_code", "work_item", "quantity_low", "quantity", "quantity_high", "quantity_basis", "unit", "unit_cost_low", "unit_cost", "unit_cost_high", "priority", "evidence_basis", "confidence", "notes"]
            loaded_reno = data.get("costs", {}).get("renovation_items", [])
            reno_frame = pd.DataFrame(loaded_reno) if loaded_reno else pd.DataFrame([{c: None for c in renovation_columns} for _ in range(4)])
            for column in renovation_columns:
                if column not in reno_frame.columns:
                    reno_frame[column] = None
            st.session_state.na_renovation_items_editor = reno_frame[renovation_columns]
            st.session_state.na_rab_estimate = data.get("costs", {}).get("renovation_ai_estimate")
            st.session_state.na_risk_reviewed = bool(data.get("risk_reviewed", False))
            for widget_key in ["na_comparables_editor_widget", "na_risk_editor_widget", "na_renovation_items_widget", "na_risk_editor_widget_v103", "na_renovation_items_widget_v103"]:
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
    t1, t2, t3, t4 = st.tabs(["1 · Data lelang & legal", "2 · Survei & risiko", "3 · Harga pembanding", "4 · Biaya & RAB"])
    with t1:
        st.subheader("Identitas lelang")
        c1,c2,c3 = st.columns(3)
        with c1:
            set_default("na_lot_code", ""); st.text_input("Kode lot", key="na_lot_code")
            set_default("na_name", ""); st.text_input("Nama objek", key="na_name")
            set_default("na_complex", ""); st.text_input("Nama kompleks/perumahan", key="na_complex")
            set_default("na_auction_date", "")
            st.session_state.na_auction_date = optional_date_picker("Tanggal lelang", st.session_state.na_auction_date, "na_auction_date")
            set_default("na_auction_time", ""); st.text_input("Jam lelang", key="na_auction_time")
        with c2:
            set_default("na_office", ""); st.text_input("KPKNL", key="na_office")
            set_default("na_seller", ""); st.text_input("Penjual/kreditur", key="na_seller")
            set_default("na_auction_type", ""); st.selectbox("Jenis lelang", ["", "Eksekusi Hak Tanggungan", "Eksekusi Pengadilan", "AYDA", "Lelang sukarela", "Lainnya"], key="na_auction_type")
            set_default("na_auction_url", ""); st.text_input("URL pengumuman lelang", key="na_auction_url")
            set_default("na_deposit_deadline", "")
            st.session_state.na_deposit_deadline = optional_date_picker("Batas setor jaminan", st.session_state.na_deposit_deadline, "na_deposit_deadline")
            set_default("na_payment_deadline", "")
            st.session_state.na_payment_deadline = optional_date_picker("Batas pelunasan", st.session_state.na_payment_deadline, "na_payment_deadline")
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
        set_default("na_rights_expiry", "")
        st.session_state.na_rights_expiry = optional_date_picker("Tanggal berakhir hak SHGB (jika ada)", st.session_state.na_rights_expiry, "na_rights_expiry")
        c1,c2 = st.columns(2)
        with c1:
            set_default("na_bedrooms", None); st.number_input("Jumlah kamar tidur", min_value=0, step=1, value=st.session_state.na_bedrooms, key="na_bedrooms")
        with c2:
            set_default("na_bathrooms", None); st.number_input("Jumlah kamar mandi", min_value=0, step=1, value=st.session_state.na_bathrooms, key="na_bathrooms")
        set_default("na_property_type", ""); property_type_options = ["", "Rumah 1 lantai", "Rumah 2 lantai", "Cluster/modern", "Rumah kecil/standar", "Rumah besar", "Ruko", "Tanah kosong", "Lainnya"]
        if st.session_state.na_property_type and st.session_state.na_property_type not in property_type_options: property_type_options.append(st.session_state.na_property_type)
        st.selectbox("Tipe properti", property_type_options, key="na_property_type")
        set_default("na_floor_count", 1); st.number_input("Jumlah lantai bangunan", min_value=1, max_value=5, step=1, key="na_floor_count", help="Digunakan untuk memperkirakan tapak atap dari luas bangunan total. Periksa bila luas tiap lantai berbeda.")
        set_default("na_building_footprint", None); st.number_input("Luas tapak lantai dasar (m², opsional)", min_value=0.0, step=1.0, value=st.session_state.na_building_footprint, key="na_building_footprint", help="Isi jika diketahui dari site plan/pengukuran. Lebih akurat untuk luas atap daripada LB dibagi jumlah lantai.")
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
        st.subheader("Survei lapangan dan kondisi penghuni")
        st.caption("Catat hanya hal yang benar-benar diketahui dari survei atau sumber yang dapat Anda jelaskan. Status belum survei akan menahan keputusan final.")
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
        set_default("na_survey_date", date.today().isoformat())
        survey_date_value = st.date_input("Tanggal survei", value=as_date(st.session_state.na_survey_date), disabled=st.session_state.na_survey_status == "Belum Survei", key="na_survey_date_picker")
        st.session_state.na_survey_date = "" if st.session_state.na_survey_status == "Belum Survei" else survey_date_value.isoformat()
        set_default("na_road_width", None); st.number_input("Lebar jalan (meter)", min_value=0.0, step=0.5, value=st.session_state.na_road_width, key="na_road_width")
        set_default("na_access", ""); st.selectbox("Akses jalan", ["", "2 Mobil", "1 Mobil", "Gang"], key="na_access")
        set_default("na_physical_condition", "Belum diketahui")
        physical_options = ["Belum diketahui", "Siap huni", "Renovasi kosmetik", "Renovasi ringan", "Renovasi sedang", "Renovasi berat", "Hitung tanah"]
        if st.session_state.na_physical_condition and st.session_state.na_physical_condition not in physical_options: physical_options.append(st.session_state.na_physical_condition)
        st.selectbox("Kondisi fisik umum", physical_options, key="na_physical_condition")
        set_default("na_interior_inspected", False); st.checkbox("Interior sudah diperiksa", key="na_interior_inspected")
        set_default("na_facade_manual", st.session_state.get("na_facade_ai", "")); st.text_area("Deskripsi fasad (hasil AI dapat diedit)", key="na_facade_manual", height=90)
        set_default("na_survey_notes", ""); st.text_area("Catatan survei, penghuni, RT/tetangga, utilitas, banjir, struktur", key="na_survey_notes", height=100)
        survey_photos = st.file_uploader("Foto hasil survei (opsional; pilih beberapa foto)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="na_survey_photos")
        st.caption("Foto survei tidak otomatis dikirim ke Gemini. Bila Google Drive archive diaktifkan, foto disimpan ke folder Drive dan metadata/hash dicatat di database.")
        st.markdown("### Risk register dan mitigasi")
        st.caption("Pilih risiko yang relevan; sistem mengisi deskripsi, skor awal, mitigasi dan cadangan indikatif. Anda tetap dapat mengubah seluruh nilai. Cadangan risiko menambah kebutuhan kas, bukan biaya profit sampai benar-benar terpakai.")
        risk_columns = ["category", "risk_description", "probability_1_5", "impact_1_5", "cost_reserve", "critical", "mitigation", "status"]
        if "na_risk_editor" not in st.session_state:
            st.session_state.na_risk_editor = pd.DataFrame(columns=risk_columns)
        with st.container(border=True):
            st.markdown("**Tambah risiko dari daftar terpandu**")
            selected_risk = st.selectbox("Pilih risiko umum", [""] + list(RISK_PRESETS.keys()), key="na_risk_preset_choice")
            if st.button("＋ Tambahkan risiko terpilih", disabled=not selected_risk, key="na_add_risk_preset"):
                rows_now = st.session_state.na_risk_editor.to_dict(orient="records")
                existing_desc = {str(r.get("risk_description", "")).strip().lower() for r in rows_now}
                preset = dict(RISK_PRESETS[selected_risk])
                if preset["risk_description"].strip().lower() not in existing_desc:
                    rows_now.append(preset)
                    st.session_state.na_risk_editor = pd.DataFrame(rows_now, columns=risk_columns)
                    st.session_state.na_risk_reviewed = False
                    st.session_state.na_risk_reviewed_signature = ""
                    for widget_key in ["na_risk_editor_widget", "na_risk_editor_widget_v103"]:
                        if widget_key in st.session_state:
                            del st.session_state[widget_key]
                    st.rerun()
                else:
                    st.info("Risiko tersebut sudah ada di register.")
            st.caption("Cadangan yang terisi otomatis adalah placeholder konservatif untuk membantu mulai mengisi, bukan tarif resmi. Ubah sesuai kondisi objek dan estimasi yang dapat dipertanggungjawabkan.")
        risk_frame = st.session_state.na_risk_editor.copy()
        for col in risk_columns:
            if col not in risk_frame.columns: risk_frame[col] = None
        risk_edited = st.data_editor(risk_frame[risk_columns], num_rows="dynamic", use_container_width=True, key="na_risk_editor_widget_v103", column_config={
            "category": st.column_config.TextColumn("Kategori"),
            "risk_description": st.column_config.TextColumn("Risiko / temuan"),
            "probability_1_5": st.column_config.NumberColumn("Kemungkinan (1–5)", min_value=1, max_value=5, step=1),
            "impact_1_5": st.column_config.NumberColumn("Dampak (1–5)", min_value=1, max_value=5, step=1),
            "cost_reserve": st.column_config.NumberColumn("Cadangan kas (Rp)", min_value=0, format="Rp %.0f"),
            "critical": st.column_config.CheckboxColumn("Kritis?"),
            "mitigation": st.column_config.TextColumn("Mitigasi / tindakan"),
            "status": st.column_config.SelectboxColumn("Status", options=["Open", "Mitigated", "Resolved"]),
        })
        st.session_state.na_risk_current = risk_edited.to_dict(orient="records")
        if len(risk_edited):
            st.caption("Skor risiko dihitung otomatis: kemungkinan × dampak. Skor 20–25 ditandai sangat tinggi. Risiko kritis yang masih terbuka akan menahan keputusan GO.")
        risk_signature = hashlib.sha256(safe_json(st.session_state.na_risk_current).encode("utf-8")).hexdigest()
        sync_review_confirmation(st.session_state, "na_risk_reviewed", "na_risk_reviewed_signature", risk_signature)
        st.checkbox("Saya sudah meninjau risiko yang relevan dan mitigasinya; saya memahami bahwa risiko yang belum terselesaikan dapat menahan keputusan GO.", key="na_risk_reviewed")
    with t3:
        st.subheader("Data pembanding harga pasar")
        st.caption("Masukkan listing rumah yang benar-benar dapat ditelusuri. Satu listing = satu baris. Gemini membantu membaca narasi, tetapi tidak boleh mengarang harga, ukuran, URL, maupun tanggal.")
        st.info("Tanggal publikasi iklan tidak wajib tersedia. **Tanggal ditemukan** adalah tanggal Anda mengumpulkan atau mencatat listing di PFMS. URL harus mengarah ke iklan rumah tertentu, bukan halaman pencarian atau daftar kategori.")
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
        default_cols = ["name", "address", "complex_name", "price", "njop", "land_area", "building_area", "bedrooms", "bathrooms", "condition", "condition_detail", "access", "access_detail", "price_type", "certificate", "orientation", "electricity_watt", "water_source", "source_platforms", "source_evidence", "source_url", "source_url_scope", "listing_date", "date_found", "date_found_basis", "notes", "adjustment_pct", "ai_adjustment_rationale", "ai_exclude_from_primary"]
        if st.session_state.get("na_comparable_schema_version") != 3:
            if "na_comparables_editor_widget" in st.session_state:
                del st.session_state["na_comparables_editor_widget"]
            st.session_state.na_comparable_schema_version = 3
        if "na_comparables_editor" not in st.session_state:
            st.session_state.na_comparables_editor = pd.DataFrame([{c: None for c in default_cols} for _ in range(5)])
        else:
            comp_frame = st.session_state.na_comparables_editor.copy()
            for column in default_cols:
                if column not in comp_frame.columns:
                    comp_frame[column] = None
            st.session_state.na_comparables_editor = comp_frame[default_cols]
        st.caption("Baris dapat digunakan untuk valuasi indikatif jika nama, harga, minimal salah satu LT/LB, dan sumber listing tersedia. Untuk GO final, setiap comparable harus memiliki URL iklan individual dan tanggal ditemukan. URL pencarian, agregator, dan halaman kompleks tidak dihitung sebagai iklan individual. Kondisi, akses, LB, dan tanggal publikasi yang tidak disebutkan tidak akan ditebak; kekurangannya menurunkan confidence.")
        comparable_editor_input = st.session_state.na_comparables_editor.copy()
        # Streamlit DateColumn expects date-like values; normalize back to ISO strings after editing.
        for date_col in ("listing_date", "date_found"):
            if date_col in comparable_editor_input.columns:
                comparable_editor_input[date_col] = comparable_editor_input[date_col].apply(comparable_date_for_editor)
        edited = st.data_editor(comparable_editor_input, num_rows="dynamic", use_container_width=True, key="na_comparables_editor_widget", column_config={
            "name": st.column_config.TextColumn("Nama listing"),
            "address": st.column_config.TextColumn("Alamat/lokasi"),
            "price": st.column_config.NumberColumn("Harga listing (Rp)", min_value=0, format="Rp %.0f"),
            "njop": st.column_config.NumberColumn("NJOP pembanding (Rp, opsional)", min_value=0, format="Rp %.0f", help="Isi hanya bila Anda benar-benar memiliki NJOP/SPPT pembanding tersebut."),
            "land_area": st.column_config.NumberColumn("LT (m²)", min_value=0),
            "building_area": st.column_config.NumberColumn("LB (m²)", min_value=0, help="Boleh kosong bila tidak tercantum; sistem dapat memakai pendekatan LT saja."),
            "condition": st.column_config.SelectboxColumn("Kondisi", options=["", "Siap Huni", "Butuh Renovasi", "Hitung Tanah"]),
            "access": st.column_config.SelectboxColumn("Akses", options=["", "2 Mobil", "1 Mobil", "Gang"]),
            "price_type": st.column_config.SelectboxColumn("Jenis harga", options=["Asking aktif", "Marked sold / perlu verifikasi", "Transaksi terverifikasi"]),
            "source_platforms": st.column_config.TextColumn("Portal/platform sumber"),
            "source_url": st.column_config.TextColumn("URL sumber (dari input)"),
            "source_url_scope": st.column_config.SelectboxColumn("Jenis halaman sumber", options=["", "Listing individual", "Portal pencarian/kategori", "Halaman venue/kompleks", "Perlu verifikasi"], help="Untuk GO final, pilih Listing individual hanya bila URL benar-benar membuka iklan rumah tertentu."),
            "listing_date": st.column_config.DateColumn("Tanggal terbit iklan (opsional)", format="DD/MM/YYYY", help="Kosongkan bila tanggal publikasi tidak tersedia."),
            "date_found": st.column_config.DateColumn("Tanggal ditemukan / dikumpulkan", format="DD/MM/YYYY", help="Tanggal Anda menemukan/mencatat listing; gunakan tombol isi tanggal untuk mengisi tanggal hari ini bila sesuai."),
            "date_found_basis": st.column_config.TextColumn("Dasar tanggal ditemukan", disabled=True),
            "adjustment_pct": st.column_config.NumberColumn("Penyesuaian (%)", help="Penyesuaian total harga pembanding agar sebanding dengan target; harus memiliki alasan."),
            "ai_adjustment_rationale": st.column_config.TextColumn("Alasan saran AI", disabled=True, help="Catatan dari Gemini. Periksa sebelum menggunakan penyesuaian."),
            "ai_exclude_from_primary": st.column_config.CheckboxColumn("Keluarkan dari valuasi utama?", help="Hanya aktif bila Anda menyetujui saran untuk mengeluarkan listing ini dari pembanding utama."),
        })
        edited_normalized = edited.copy()
        for date_col in ("listing_date", "date_found"):
            if date_col in edited_normalized.columns:
                edited_normalized[date_col] = edited_normalized[date_col].apply(comparable_date_to_iso)
        st.session_state.na_comparables_editor = edited_normalized.copy()
        st.session_state.na_comparables_current = edited_normalized.to_dict(orient="records")
        st.markdown("#### Pemeriksaan kualitas listing dengan AI (opsional)")
        st.caption("Gemini membantu menilai relevansi setiap listing, menemukan data yang janggal, dan menyarankan penyesuaian hanya bila perbedaannya terlihat pada input. Gemini tidak mencari harga transaksi yang tidak tersedia dan tidak menetapkan ARV akhir. Python tetap menghitung valuasi.")
        market_review_rows = edited_normalized.to_dict(orient="records")
        market_review_positions = [i for i, row in enumerate(market_review_rows) if str(row.get("name") or "").strip() and to_float(row.get("price")) > 0 and (to_float(row.get("land_area")) > 0 or to_float(row.get("building_area")) > 0)]
        market_review_comps = [market_review_rows[i] for i in market_review_positions]
        market_review_subject = {
            "name": st.session_state.get("na_name", ""), "address": st.session_state.get("na_address", ""),
            "complex_name": st.session_state.get("na_complex", ""), "land_area": st.session_state.get("na_land"),
            "building_area": st.session_state.get("na_building"), "certificate_type": st.session_state.get("na_certificate", ""),
            "physical_condition": st.session_state.get("na_physical_condition", ""), "access": st.session_state.get("na_access", ""),
            "road_width_m": st.session_state.get("na_road_width"), "njop": st.session_state.get("na_njop"),
        }
        market_review_sig = hashlib.sha256(safe_json({"subject": market_review_subject, "comparables": market_review_comps}).encode("utf-8")).hexdigest()
        if st.button("🧠 Evaluasi kualitas & penyesuaian listing dengan Gemini", disabled=not bool(GEMINI_KEY) or not market_review_comps or len(market_review_comps) > 20, key="na_market_ai_review"):
            try:
                with st.spinner("Gemini menilai relevansi, perbedaan spesifikasi, dan anomali listing..."):
                    python_precheck = assess_comparables(market_review_comps, market_review_subject, to_float(st.session_state.get("na_negotiation_discount", DEFAULT_RULES["negotiation_discount_pct"])), to_float(st.session_state.get("na_quick_sale_discount", DEFAULT_RULES["quick_sale_discount_pct"])), to_float(get_rules().get("njop_market_weight_pct", 10)))
                    ai_result = assess_market_with_ai(GEMINI_KEY, GEMINI_MODEL, market_review_subject, market_review_comps, python_precheck)
                st.session_state.na_market_ai_assessment = ai_result
                st.session_state.na_market_ai_signature = market_review_sig
                st.session_state.na_market_ai_positions = market_review_positions
                st.success("Review AI selesai. Saran belum diterapkan ke perhitungan; tinjau tabel dan pilih Terapkan bila Anda menyetujuinya.")
            except Exception as exc:
                st.error(f"Evaluasi pasar dengan Gemini gagal: {exc}")
        saved_market_review = st.session_state.get("na_market_ai_assessment")
        if saved_market_review:
            review_current = st.session_state.get("na_market_ai_signature") == market_review_sig
            applied_review_current = st.session_state.get("na_market_ai_applied_signature") == market_review_sig
            if not review_current and not applied_review_current:
                st.warning("Data target/listing sudah berubah sejak review AI terakhir. Jalankan evaluasi ulang sebelum menggunakan saran sebelumnya.")
            else:
                st.info(saved_market_review.get("overall_assessment") or "Review pasar tersedia.")
                if saved_market_review.get("limitations"):
                    for limitation in saved_market_review.get("limitations", []): st.caption("Batasan: " + str(limitation))
                judgement_rows = []
                for item in saved_market_review.get("items", []):
                    judgement_rows.append({"Baris": item.get("source_index"), "Relevansi": item.get("relevance_score"), "Saran penyesuaian (%)": item.get("suggested_adjustment_pct"), "Keluarkan dari indikasi utama?": item.get("exclude_from_primary"), "Alasan": item.get("reason"), "Data belum tersedia": ", ".join(item.get("data_gaps", []))})
                if judgement_rows:
                    st.dataframe(pd.DataFrame(judgement_rows), use_container_width=True, hide_index=True)
                st.caption(saved_market_review.get("warning", "Saran AI perlu diperiksa pengguna."))
                if applied_review_current:
                    st.success("Saran AI sudah diterapkan pada tabel pembanding. Periksa kembali nilai penyesuaian sebelum analisis.")
                elif st.button("Terapkan saran penyesuaian AI ke kolom tabel (masih dapat diedit)", key="na_apply_market_ai", disabled=not review_current):
                    rows_to_update = st.session_state.na_comparables_editor.to_dict(orient="records")
                    positions = st.session_state.get("na_market_ai_positions", [])
                    applied = 0
                    for item in saved_market_review.get("items", []):
                        source_idx = int(item.get("source_index") or 0) - 1
                        if source_idx < 0 or source_idx >= len(positions): continue
                        target_pos = positions[source_idx]
                        if target_pos >= len(rows_to_update): continue
                        rows_to_update[target_pos]["ai_exclude_from_primary"] = bool(item.get("exclude_from_primary"))
                        rows_to_update[target_pos]["ai_adjustment_rationale"] = str(item.get("reason") or "Saran AI")
                        if not item.get("exclude_from_primary"):
                            rows_to_update[target_pos]["adjustment_pct"] = float(item.get("suggested_adjustment_pct") or 0)
                            applied += 1
                    st.session_state.na_comparables_editor = pd.DataFrame(rows_to_update)
                    if "na_comparables_editor_widget" in st.session_state: del st.session_state["na_comparables_editor_widget"]
                    applied_rows = [row for row in rows_to_update if str(row.get("name") or "").strip() and to_float(row.get("price")) > 0 and (to_float(row.get("land_area")) > 0 or to_float(row.get("building_area")) > 0)]
                    applied_signature = hashlib.sha256(safe_json({"subject": market_review_subject, "comparables": applied_rows}).encode("utf-8")).hexdigest()
                    st.session_state.na_market_ai_applied_signature = applied_signature
                    st.session_state.na_costs_reviewed = False
                    st.success(f"Saran penyesuaian diterapkan pada {applied} listing. Mohon periksa kembali angka dan alasannya sebelum Analisis Sekarang.")
                    st.rerun()
        market_action_1, market_action_2 = st.columns(2)
        with market_action_1:
            if st.button("Isi tanggal ditemukan untuk baris yang masih kosong", use_container_width=True, key="na_fill_capture_dates"):
                rows_to_update = edited_normalized.to_dict(orient="records")
                changed = 0
                for comp in rows_to_update:
                    if str(comp.get("name") or "").strip() and to_float(comp.get("price")) > 0 and not str(comp.get("date_found") or "").strip():
                        comp["date_found"] = date.today().isoformat()
                        comp["date_found_basis"] = "Dikonfirmasi pengguna: tanggal dikumpulkan di PFMS"
                        changed += 1
                st.session_state.na_comparables_editor = pd.DataFrame(rows_to_update)
                if "na_comparables_editor_widget" in st.session_state: del st.session_state["na_comparables_editor_widget"]
                st.success(f"Tanggal ditemukan diisi untuk {changed} baris. Tanggal publikasi iklan tetap tidak diubah.")
                st.rerun()
        with market_action_2:
            url_review_material = [
                {"name": str(row.get("name") or "").strip(), "url": str(row.get("source_url") or "").strip()}
                for row in edited_normalized.to_dict(orient="records")
                if str(row.get("source_url") or "").strip()
            ]
            url_review_signature = hashlib.sha256(safe_json(url_review_material).encode("utf-8")).hexdigest()
            sync_review_confirmation(st.session_state, "na_confirm_individual_urls", "na_confirm_individual_urls_signature", url_review_signature)
            confirm_individual_urls = st.checkbox("Saya sudah membuka URL dan memastikan setiap link yang relevan adalah iklan properti individual.", key="na_confirm_individual_urls")
            if st.button("Konfirmasi URL sebagai listing individual", disabled=not confirm_individual_urls, use_container_width=True, key="na_confirm_url_scope"):
                rows_to_update = edited_normalized.to_dict(orient="records")
                changed = 0
                for comp in rows_to_update:
                    url = str(comp.get("source_url") or "").strip()
                    scope = str(comp.get("source_url_scope") or "")
                    if url.startswith(("http://", "https://")) and scope not in {"Portal pencarian/kategori", "Halaman venue/kompleks"}:
                        comp["source_url_scope"] = "Listing individual"
                        changed += 1
                st.session_state.na_comparables_editor = pd.DataFrame(rows_to_update)
                if "na_comparables_editor_widget" in st.session_state: del st.session_state["na_comparables_editor_widget"]
                st.success(f"{changed} URL ditandai sebagai listing individual berdasarkan konfirmasi Anda.")
                st.rerun()
        set_default("na_negotiation_discount", DEFAULT_RULES["negotiation_discount_pct"])
        set_default("na_quick_sale_discount", DEFAULT_RULES["quick_sale_discount_pct"])
        c1,c2 = st.columns(2)
        with c1: st.number_input("Negotiation discount listing aktif (%)", min_value=0.0, max_value=50.0, step=1.0, key="na_negotiation_discount")
        with c2: st.number_input("Quick-sale discount (%)", min_value=0.0, max_value=30.0, step=1.0, key="na_quick_sale_discount")
    with t4:
        st.subheader("Biaya proyek dan target")
        rules = get_rules()
        st.markdown("### RAB renovasi — AI-assisted draft")
        st.caption("Pilih kelas pekerjaan terlebih dahulu. Python menyiapkan scope dan rentang volume dari LT/LB, luas tapak (jika diketahui), jumlah lantai, tipe properti serta jumlah kamar. Gemini menilai foto/deskripsi dan mengusulkan harga satuan konservatif. Semua hasil tetap draft untuk diperiksa.")
        set_default("na_renovation_category", "Auto sesuai kondisi umum")
        rab_category_options = RENOVATION_CATEGORIES
        if st.session_state.na_renovation_category not in rab_category_options: rab_category_options = rab_category_options + [st.session_state.na_renovation_category]
        st.selectbox("Kategori / lingkup RAB", rab_category_options, key="na_renovation_category", help="Kategori menentukan paket pekerjaan. Untuk renovasi berat, kuantitas struktur tetap wajib dari desain/engineer.")
        set_default("na_rab_condition_description", "")
        st.text_area("Deskripsi kondisi aktual dan pekerjaan yang terlihat/diperlukan", key="na_rab_condition_description", height=115, placeholder="Deskripsi singkat cukup: misalnya rumah lama, cat mengelupas, atap perlu diganti, kamar mandi 1 unit perlu renovasi; interior sebagian belum diperiksa...")
        available_rab_files: list[tuple[bytes, str, str]] = []
        if uploaded is not None:
            available_rab_files.append((uploaded.getvalue(), uploaded.type or "application/octet-stream", uploaded.name))
        for photo in (survey_photos or [])[:5]:
            available_rab_files.append((photo.getvalue(), photo.type or "image/jpeg", photo.name))
        st.caption(f"Berkas visual tersedia untuk RAB: {len(available_rab_files)} (dokumen lelang + maksimal 5 foto survei). Bila foto fasad saja, AI tidak boleh menyimpulkan interior/struktur/MEP rusak.")
        rab_inputs_sufficient = bool(st.session_state.get("na_building") or st.session_state.get("na_land") or available_rab_files or st.session_state.na_rab_condition_description.strip())
        if st.button("✨ Susun RAB awal dengan Gemini", type="secondary", disabled=not GEMINI_KEY or not rab_inputs_sufficient, key="na_generate_rab"):
            context = {
                "address": st.session_state.get("na_address", ""), "district": st.session_state.get("na_district", ""),
                "land_area": st.session_state.get("na_land"), "building_area": st.session_state.get("na_building"),
                "building_footprint_m2": st.session_state.get("na_building_footprint"),
                "property_type": st.session_state.get("na_property_type", ""), "floor_count": st.session_state.get("na_floor_count", 1),
                "bedrooms": st.session_state.get("na_bedrooms"), "bathrooms": st.session_state.get("na_bathrooms"),
                "physical_condition": st.session_state.get("na_physical_condition", ""),
                "interior_inspected": bool(st.session_state.get("na_interior_inspected", False)),
                "occupancy_status": st.session_state.get("na_survey_status", "Belum Survei"),
                "renovation_category": st.session_state.get("na_renovation_category", "Auto sesuai kondisi umum"),
                "road_width_m": st.session_state.get("na_road_width"), "access": st.session_state.get("na_access", ""),
                "facade_description": st.session_state.get("na_facade_manual", ""),
                "survey_notes": st.session_state.get("na_survey_notes", ""),
                "condition_description": st.session_state.get("na_rab_condition_description", ""),
            }
            rab_description = "\n".join(x for x in [st.session_state.na_rab_condition_description.strip(), "Deskripsi fasad: " + context["facade_description"] if context["facade_description"] else "", "Catatan survei: " + context["survey_notes"] if context["survey_notes"] else ""] if x)
            cache_material = rab_description + safe_json(context) + "|" + "|".join(file_sha256(f[0]) for f in available_rab_files)
            cache_key = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()
            cache = st.session_state.setdefault("na_rab_cache", {})
            try:
                if cache_key in cache:
                    rab_result = cache[cache_key]
                    st.info("Hasil RAB untuk input dan foto yang sama digunakan dari cache; Gemini tidak dipanggil ulang.")
                else:
                    with st.spinner("Gemini menilai foto dan deskripsi, lalu menyusun draft RAB per pekerjaan..."):
                        rab_result = estimate_renovation_rab(GEMINI_KEY, available_rab_files, rab_description, context, GEMINI_MODEL)
                    cache[cache_key] = rab_result
                st.session_state.na_rab_estimate = rab_result
                st.session_state.na_renovation_items_editor = pd.DataFrame(rab_result.get("editor_rows", []))
                st.session_state.na_costs_reviewed = False
                for widget_key in ["na_renovation_items_widget", "na_renovation_items_widget_v103"]:
                    if widget_key in st.session_state:
                        del st.session_state[widget_key]
                st.session_state.na_rab_accepted_pending = True
                st.rerun()
            except Exception as exc:
                st.error(f"RAB AI gagal dibuat: {exc}. Anda tetap dapat mengisi RAB secara manual.")
        if not GEMINI_KEY:
            st.info("GEMINI_API_KEY belum diatur. RAB manual tetap tersedia.")
        rab_estimate = st.session_state.get("na_rab_estimate")
        if rab_estimate:
            with st.expander("Ringkasan asumsi dan batasan RAB dari Gemini", expanded=True):
                st.write(f"Kategori RAB: **{rab_estimate.get('category', 'Belum ditentukan')}**")
                if rab_estimate.get("category_basis"):
                    st.caption("Dasar klasifikasi: " + str(rab_estimate.get("category_basis")))
                if rab_estimate.get("total_conservative_complete", False):
                    st.metric("Total RAB konservatif indikatif (seluruh item dalam lingkup terisi)", idr(rab_estimate.get("total_conservative_indicative")))
                else:
                    st.metric("Subtotal item yang sudah memiliki volume dan harga", idr(rab_estimate.get("subtotal_conservative_priced_items", rab_estimate.get("total_conservative_indicative"))))
                    st.metric("Total RAB lengkap", "Belum dapat ditentukan")
                    st.caption(f"Item terisi: {rab_estimate.get('priced_item_count', 0)} dari {rab_estimate.get('in_scope_item_count', 0)} item yang masih dalam lingkup.")
                if rab_estimate.get("visual_findings"):
                    st.markdown("**Temuan yang benar-benar terlihat**")
                    for finding in rab_estimate["visual_findings"]: st.write(f"• {finding}")
                if rab_estimate.get("likely_causes_to_verify"):
                    st.markdown("**Kemungkinan penyebab — masih perlu diverifikasi**")
                    for cause in rab_estimate["likely_causes_to_verify"]: st.write(f"• {cause}")
                if rab_estimate.get("interior_unknowns"):
                    st.markdown("**Bagian interior yang belum dapat dinilai dari foto**")
                    for unknown in rab_estimate["interior_unknowns"]: st.write(f"• {unknown}")
                if rab_estimate.get("occupancy_unknowns"):
                    st.markdown("**Status hunian — tidak dapat disimpulkan dari foto**")
                    for unknown in rab_estimate["occupancy_unknowns"]: st.write(f"• {unknown}")
                if rab_estimate.get("inspection_plan"):
                    st.markdown("**Urutan pemeriksaan lapangan yang disarankan**")
                    for step in rab_estimate["inspection_plan"]: st.write(f"• {step}")
                scenarios = rab_estimate.get("interior_scenarios") or []
                if scenarios:
                    st.markdown("**Skenario biaya interior (di luar total RAB dasar)**")
                    for scenario in scenarios:
                        low, high = scenario.get("cost_low"), scenario.get("cost_high")
                        cost_label = f"{idr(low)} – {idr(high)}" if low is not None and high is not None else "Belum cukup dasar untuk menaksir nominal"
                        st.markdown(f"**{scenario.get('scenario_name', 'Skenario')}** · {cost_label} · Keyakinan: {scenario.get('confidence', 'Rendah')}")
                        for assumption in scenario.get("assumptions", []): st.caption(f"Asumsi: {assumption}")
                        for work in scenario.get("potential_work_items", []): st.write(f"• {work}")
                    st.info("Skenario interior tidak otomatis masuk total RAB atau anggaran. Gunakan sebagai sensitivitas/cadangan sampai kondisi interior diperiksa.")
                guidance = rab_estimate.get("quantity_guidance", {})
                if guidance:
                    st.caption(f"Profil volume: LT {guidance.get('land_area') or '—'} m² · LB {guidance.get('building_area') or '—'} m² · {guidance.get('floor_count', 1)} lantai · {guidance.get('bedrooms') or '—'} KT · {guidance.get('bathrooms') or '—'} KM")
                    st.caption(guidance.get("method_note", ""))
                if not rab_estimate.get("total_conservative_complete", False):
                    st.warning("Total RAB masih parsial karena volume atau harga satuan belum terisi pada sebagian pekerjaan. Lengkapi kolom tersebut sebelum mengonfirmasi anggaran.")
                    if rab_estimate.get("unpriced_items"):
                        st.caption("Pekerjaan yang belum masuk total: " + "; ".join(rab_estimate["unpriced_items"]))
                for note in rab_estimate.get("assumptions", []): st.write(f"• {note}")
                if rab_estimate.get("items_to_inspect"):
                    st.warning("Perlu inspeksi sebelum final: " + "; ".join(rab_estimate["items_to_inspect"]))
                if rab_estimate.get("overall_note"): st.caption(rab_estimate["overall_note"])
                if rab_estimate.get("pricing_basis_disclosure"):
                    st.warning(rab_estimate.get("pricing_basis_disclosure"))
                st.caption(rab_estimate.get("estimation_basis", "Draft AI; wajib diverifikasi."))
        renovation_columns = ["item_code", "work_item", "quantity_low", "quantity", "quantity_high", "quantity_basis", "unit", "unit_cost_low", "unit_cost", "unit_cost_high", "priority", "evidence_basis", "confidence", "notes"]
        if "na_renovation_items_editor" not in st.session_state:
            st.session_state.na_renovation_items_editor = pd.DataFrame([{c: None for c in renovation_columns} for _ in range(4)])
        renovation_frame = st.session_state.na_renovation_items_editor.copy()
        for col in renovation_columns:
            if col not in renovation_frame.columns: renovation_frame[col] = None
        renovation_edited = st.data_editor(renovation_frame[renovation_columns], num_rows="dynamic", use_container_width=True, key="na_renovation_items_widget_v103", column_config={
            "item_code": st.column_config.TextColumn("Kode scope", disabled=True),
            "work_item": st.column_config.TextColumn("Pekerjaan"),
            "quantity_low": st.column_config.NumberColumn("Vol. rendah", min_value=0.0, step=1.0),
            "quantity": st.column_config.NumberColumn("Volume dipakai", min_value=0.0, step=1.0, help="Volume konservatif yang dipakai Python untuk menghitung RAB; dapat Anda koreksi."),
            "quantity_high": st.column_config.NumberColumn("Vol. atas", min_value=0.0, step=1.0),
            "quantity_basis": st.column_config.TextColumn("Dasar estimasi volume", disabled=True),
            "unit": st.column_config.TextColumn("Satuan"),
            "unit_cost_low": st.column_config.NumberColumn("Harga satuan rendah (Rp)", min_value=0, format="Rp %.0f"),
            "unit_cost": st.column_config.NumberColumn("Harga satuan konservatif (Rp)", min_value=0, format="Rp %.0f", help="Nilai inilah yang dipakai Python untuk menghitung RAB."),
            "unit_cost_high": st.column_config.NumberColumn("Batas atas (Rp)", min_value=0, format="Rp %.0f"),
            "priority": st.column_config.SelectboxColumn("Prioritas", options=["Wajib", "Disarankan", "Bersyarat", "Opsional", "Tidak diperlukan setelah ditinjau"]),
            "evidence_basis": st.column_config.SelectboxColumn("Dasar", options=["Fakta visual", "Deskripsi pengguna", "Asumsi kuantitas"]),
            "confidence": st.column_config.SelectboxColumn("Keyakinan", options=["Tinggi", "Sedang", "Rendah"]),
            "notes": st.column_config.TextColumn("Catatan / asumsi / sumber"),
        })
        st.session_state.na_renovation_items_current = renovation_edited.to_dict(orient="records")
        renovation_items = [r for r in st.session_state.na_renovation_items_current if str(r.get("work_item") or "").strip()]
        renovation_item_total = sum(max(0, to_float(r.get("quantity"))) * max(0, to_float(r.get("unit_cost"))) for r in renovation_items if rab_item_is_in_scope(r))
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
        in_scope_rab_rows = [r for r in renovation_items if rab_item_is_in_scope(r)]
        unpriced_rab_rows = [r for r in in_scope_rab_rows if r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, "")]
        if unpriced_rab_rows:
            st.metric("Subtotal RAB terisi (belum total akhir)", idr(renovation_total))
            st.warning(f"RAB belum lengkap: {len(unpriced_rab_rows)} item dalam lingkup belum memiliki volume atau harga satuan. Total biaya renovasi belum dapat dipastikan.")
            with st.expander("Lihat pekerjaan yang belum dapat dihitung"):
                for row in unpriced_rab_rows:
                    st.write(f"• {row.get('work_item', 'Pekerjaan tanpa nama')} — volume: {row.get('quantity') or 'belum diisi'} {row.get('unit') or ''}; harga satuan: {idr(row.get('unit_cost')) if row.get('unit_cost') not in (None, '') else 'belum diisi'}")
        else:
            st.metric("TOTAL RAB RENOVASI (seluruh item dalam lingkup sudah terisi)", idr(renovation_total), help="Total volume × harga satuan seluruh item dalam lingkup + tambahan di luar daftar.")
        c1,c2 = st.columns(2)
        with c1:
            set_default("na_other_presale", 0); st.number_input("Biaya lain sebelum penjualan (Rp)", min_value=0, step=500_000, key="na_other_presale")
        with c2:
            set_default("na_risk_ceiling", None); st.number_input("Hard ceiling bid tambahan (opsional, Rp)", min_value=0, step=1_000_000, value=st.session_state.na_risk_ceiling, key="na_risk_ceiling")
        st.caption("Contingency renovasi dihitung otomatis oleh Python berdasarkan persentase Settings & Rules.")
        st.metric("Minimum ROI", "25%", help="Target wajib untuk seluruh periode proyek.")
        rules_for_cost_review = get_rules()
        cost_review_payload = {
            "renovation_items": st.session_state.get("na_renovation_items_current", []),
            "renovation_extra": st.session_state.get("na_renovation_extra", 0),
            "renovation_months": st.session_state.get("na_renovation_months", 0),
            "selling_months": st.session_state.get("na_selling_months", 0),
            "legal_delay_months": st.session_state.get("na_legal_delay_months", 0),
            "holding_monthly": st.session_state.get("na_monthly_holding", 0),
            "marketing": st.session_state.get("na_marketing_cost", 0),
            "other_presale": st.session_state.get("na_other_presale", 0),
            "possession": st.session_state.get("na_possession_cost", 0),
            "possession_reserve": st.session_state.get("na_possession_risk_reserve", 0),
            "auction_limit": st.session_state.get("na_limit"),
            "buyer_fee_pct": st.session_state.get("na_buyer_fee"),
            "bphtb_rate_pct": st.session_state.get("na_bphtb_rate"),
            "npoptkp": st.session_state.get("na_npoptkp"),
            "npoptkp_eligible": st.session_state.get("na_npoptkp_eligible"),
            "njop": st.session_state.get("na_njop"),
            "bphtb_basis_mode": rules_for_cost_review.get("bphtb_basis_mode"),
            "bpn_legal_rules": {k: rules_for_cost_review.get(k) for k in ["bpn_pnbp_cost", "roya_cost", "other_acquisition_admin", "other_legal_cost", "acquisition_notary_ppat_fee"]},
            "selling_rules": {k: rules_for_cost_review.get(k) for k in ["seller_final_tax_pct", "seller_agent_pct", "seller_ajb_ppat_pct", "seller_misc_fixed"]},
            "contingency_pct": rules_for_cost_review.get("renovation_contingency_pct"),
        }
        cost_signature = hashlib.sha256(safe_json(cost_review_payload).encode("utf-8")).hexdigest()
        sync_review_confirmation(st.session_state, "na_costs_reviewed", "na_costs_reviewed_signature", cost_signature)
        st.checkbox("Saya sudah meninjau seluruh estimasi biaya (BPN, penguasaan, setiap item RAB, contingency, holding, marketing dan biaya lain). Nilai nol adalah keputusan yang disengaja.", key="na_costs_reviewed")
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
            "land_area": st.session_state.na_land, "building_area": st.session_state.na_building, "building_footprint_m2": st.session_state.get("na_building_footprint"), "njop": st.session_state.na_njop, "bedrooms": st.session_state.get("na_bedrooms"), "bathrooms": st.session_state.get("na_bathrooms"), "property_type": st.session_state.get("na_property_type", ""), "floor_count": st.session_state.get("na_floor_count", 1), "rights_expiry": st.session_state.get("na_rights_expiry", ""),
            "risk_adjusted_ceiling": st.session_state.na_risk_ceiling, "npoptkp_eligible": st.session_state.na_npoptkp_eligible,
        }
        survey_data = {"survey_status": st.session_state.na_survey_status, "occupancy_status": st.session_state.na_survey_status, "survey_date": st.session_state.na_survey_date, "possession_cost": st.session_state.na_possession_cost, "possession_risk_reserve": st.session_state.na_possession_risk_reserve, "possession_months": st.session_state.na_possession_months, "road_width_m": st.session_state.na_road_width, "access": st.session_state.na_access, "physical_condition": st.session_state.na_physical_condition, "interior_inspected": st.session_state.na_interior_inspected, "facade_description": st.session_state.na_facade_manual, "survey_notes": st.session_state.na_survey_notes}
        legal_data = {"identity_verified": st.session_state.na_legal_verified, "dispute_detected": st.session_state.na_dispute, "tax_rules_verified": st.session_state.na_tax_verified, "tax_region": st.session_state.na_tax_region, "tax_rule_source_url": st.session_state.na_tax_rule_source}
        renovation_items_data = [r for r in st.session_state.get("na_renovation_items_current", []) if str(r.get("work_item") or "").strip()]
        renovation_item_total = sum(max(0, to_float(r.get("quantity"))) * max(0, to_float(r.get("unit_cost"))) for r in renovation_items_data if rab_item_is_in_scope(r))
        renovation_extra_cost = to_float(st.session_state.na_renovation_extra)
        costs_data = {"renovation_cost": renovation_item_total + renovation_extra_cost, "renovation_items": renovation_items_data, "renovation_ai_estimate": st.session_state.get("na_rab_estimate"), "renovation_extra_cost": renovation_extra_cost, "renovation_category": st.session_state.get("na_renovation_category", "Auto sesuai kondisi umum"), "rab_condition_description": st.session_state.get("na_rab_condition_description", ""), "renovation_months": st.session_state.na_renovation_months, "selling_months": st.session_state.na_selling_months, "legal_delay_months": st.session_state.na_legal_delay_months, "monthly_holding_cost": st.session_state.na_monthly_holding, "marketing_cost": st.session_state.na_marketing_cost, "other_presale_cost": st.session_state.na_other_presale, "cost_estimates_reviewed": bool(st.session_state.na_costs_reviewed)}
        comp_data = st.session_state.get("na_comparables_current", [])
        cash_profile, cash_events, liquidity = get_cash_data()
        if not cash_profile.get("cash_confirmed", False): liquidity["cash_confirmed"] = False
        else: liquidity["cash_confirmed"] = True
        rules = get_rules(); rules["negotiation_discount_pct"] = st.session_state.na_negotiation_discount; rules["quick_sale_discount_pct"] = st.session_state.na_quick_sale_discount
        rules["buyer_auction_fee_pct"] = st.session_state.na_buyer_fee; rules["bphtb_rate_pct"] = st.session_state.na_bphtb_rate; rules["npoptkp"] = st.session_state.na_npoptkp
        risk_data = [r for r in st.session_state.get("na_risk_current", []) if str(r.get("risk_description") or "").strip()]
        risk_reviewed = bool(st.session_state.na_risk_reviewed)
        market_ai_subject_now = {
            "name": property_data.get("name", ""), "address": property_data.get("address", ""),
            "complex_name": property_data.get("complex_name", ""), "land_area": property_data.get("land_area"),
            "building_area": property_data.get("building_area"), "certificate_type": property_data.get("certificate_type", ""),
            "physical_condition": survey_data.get("physical_condition", ""), "access": survey_data.get("access", ""),
            "road_width_m": survey_data.get("road_width_m"), "njop": property_data.get("njop"),
        }
        market_ai_rows_now = [row for row in comp_data if str(row.get("name") or "").strip() and to_float(row.get("price")) > 0 and (to_float(row.get("land_area")) > 0 or to_float(row.get("building_area")) > 0)]
        market_ai_signature_now = hashlib.sha256(safe_json({"subject": market_ai_subject_now, "comparables": market_ai_rows_now}).encode("utf-8")).hexdigest()
        has_current_ai_review = market_ai_signature_now in {st.session_state.get("na_market_ai_signature"), st.session_state.get("na_market_ai_applied_signature")}
        market_ai_assessment = st.session_state.get("na_market_ai_assessment") if has_current_ai_review else None
        inputs = {"property": property_data, "survey": survey_data, "legal": legal_data, "costs": costs_data, "comparables": comp_data, "risk_register": risk_data, "risk_reviewed": risk_reviewed, "market_ai_assessment": market_ai_assessment}
        result = run_underwriting(inputs, liquidity, rules)
        property_id = st.session_state.loaded_property_id or new_id("PROP")
        analysis_id = new_id("ANL")
        snapshot = {"analysis_id": analysis_id, "property_id": property_id, "analyzed_at": iso_now(), "property": property_data, "survey": survey_data, "legal": legal_data, "costs": costs_data, "comparables": comp_data, "risk_reviewed": risk_reviewed, "risk_register": risk_data, "market_ai_assessment": market_ai_assessment, "rules": rules, "liquidity": liquidity, "document_extraction": st.session_state.parse_info or {}, **result}
        st.session_state.current_analysis = snapshot; st.session_state.current_inputs = inputs; st.session_state.current_property_id = property_id
        st.session_state.ai_review = None
    snap = st.session_state.current_analysis
    if snap:
        st.markdown("---")
        decision = snap["decision"]; mkt = snap["market"]; tiers = snap["bidding"]; at = snap["at_limit"]
        st.subheader("Ringkasan hasil analisis")
        if mkt.get("conservative_exit") is None:
            st.info("Analisis biaya tetap berhasil dihitung, tetapi ARV belum dapat diperkirakan karena data harga pembanding atau luas objek belum cukup. Lengkapi data pasar sebelum memakai simulasi bidding sebagai dasar keputusan.")
        elif mkt.get("status") != "READY":
            st.warning(
                f"Estimasi ARV dan simulasi bidding masih bersifat indikatif. Saat ini terdapat {mkt.get('valid_count', 0)} comparable yang dapat dihitung, "
                f"{mkt.get('go_grade_count', 0)} dari minimal 5 memiliki URL listing individual yang terkonfirmasi dan tanggal ditemukan, "
                f"serta confidence {mkt.get('confidence', 0)}/100 (batas minimum 55). "
                "Tanggal publikasi iklan boleh tidak tersedia; yang diperlukan adalah tanggal ketika listing dikumpulkan/ditemukan."
            )
        if decision["status"] == "GO": st.success("GO — SELURUH GATE UTAMA TERPENUHI")
        elif decision["status"] == "CONDITIONAL GO": st.warning("CONDITIONAL GO — ADA SYARAT YANG HARUS DIPENUHI")
        elif decision["status"] == "DO NOT BID": st.error("DO NOT BID / TIDAK LAYAK")
        else: st.warning("HOLD — DATA / VERIFIKASI BELUM MEMADAI")
        st.write(decision["summary"])
        if mkt.get("base_exit"):
            st.info(f"ARV Dasar indikatif: {idr(mkt.get('base_exit'))} · ARV Konservatif: {idr(mkt.get('conservative_exit'))} · Rentang model: {idr(mkt.get('market_range_low'))} – {idr(mkt.get('market_range_high'))}. Haircut ketidakpastian data: {mkt.get('conservative_discount_used_pct', '—')}%. Indeks kualitas data bukan probabilitas harga tercapai.")
        if snap.get("market_ai_assessment"):
            with st.expander("Catatan evaluasi listing oleh Gemini", expanded=False):
                st.write(snap["market_ai_assessment"].get("overall_assessment", ""))
                for point in snap["market_ai_assessment"].get("key_value_drivers", []): st.write("•", point)
                for limitation in snap["market_ai_assessment"].get("limitations", []): st.caption("Batasan: " + str(limitation))
                st.caption("Saran AI yang sudah diterapkan tercatat pada kolom penyesuaian listing. Hasil ini bukan verifikasi transaksi dan bukan appraisal.")
        required_rab_missing = tiers.get("required_rab_unpriced", [])
        in_scope_rab_missing = tiers.get("in_scope_rab_unpriced", required_rab_missing)
        cost_review_pending = not bool(snap.get("costs", {}).get("cost_estimates_reviewed", False))
        financial_inputs_partial = bool(in_scope_rab_missing or cost_review_pending)
        k1,k2,k3,k4,k5 = st.columns(5)
        k1.metric("ARV konservatif", idr(mkt.get("conservative_exit")), help="Estimasi harga keluar konservatif setelah quick-sale discount.")
        k2.metric("ARV dasar", idr(mkt.get("base_exit")), help="Estimasi nilai pasar dasar dari comparable dan, bila tersedia, referensi NJOP terkalibrasi.")
        k3.metric("Modal sementara / data terisi" if financial_inputs_partial else "Total modal proyek", idr(at.get("capital_before_sale")), help="Jika RAB wajib belum lengkap atau biaya belum dikonfirmasi, angka ini hanya total komponen yang sudah terdata; belum merupakan total modal akhir.")
        k4.metric("Profit indikatif" if financial_inputs_partial else "Estimasi profit bersih", idr(at.get("net_profit")))
        k5.metric("ROI indikatif" if financial_inputs_partial else "ROI proyek", pct(at.get("roi_pct")))
        if tiers.get("provisional_reasons"):
            st.warning("Tangga bidding dan hasil profit/ROI masih INDIKATIF. Dasar yang belum final: " + "; ".join(tiers.get("provisional_reasons", [])) + ". Jangan gunakan sebagai instruksi bidding final.")
        st.markdown("### Tangga bidding")
        tier_rows = []
        tier_specs = [
            ("Nilai limit (patokan awal)", tiers.get("min_bid"), None, None, at, "LIMIT_REFERENCE", True),
            ("Target ROI 35%", tiers.get("mid_bid"), tiers.get("mid_economic_ceiling"), tiers.get("mid_simulated_ceiling"), tiers.get("mid_result"), 35.0, tiers.get("mid_limit_feasible", False)),
            ("Maximum bid / ROI 25%", tiers.get("max_bid"), tiers.get("max_economic_ceiling"), tiers.get("max_simulated_ceiling"), tiers.get("max_result"), 25.0, tiers.get("max_limit_feasible", False)),
        ]
        cash_available_now = to_float(snap.get("liquidity", {}).get("cash_available_for_new_project"))
        auction_limit_now = to_float(snap["property"].get("auction_limit"))
        for label, bid, economic_ceiling, simulated_ceiling, res, hurdle, feasible in tier_specs:
            cash_need_tier = res.get("cash_requirement_including_reserve") if res else None
            if hurdle == "LIMIT_REFERENCE":
                limit_roi = to_float(res.get("roi_pct"), -999) if res else -999
                min_roi_target = to_float(snap.get("rules", {}).get("minimum_roi_pct", 25))
                if limit_roi < 0:
                    tier_status = "ROI LIMIT BELUM DAPAT DIHITUNG"
                elif limit_roi < min_roi_target:
                    tier_status = f"ROI LIMIT {limit_roi:.1f}% DI BAWAH TARGET {min_roi_target:.1f}% — JANGAN BID"
                elif cash_need_tier is not None and cash_need_tier > cash_available_now:
                    tier_status = "ROI LIMIT MEMENUHI TARGET, TETAPI KAS TIDAK CUKUP"
                elif tiers.get("provisional"):
                    tier_status = f"ROI LIMIT MEMENUHI {min_roi_target:.1f}%, TETAPI ANALISIS MASIH INDIKATIF"
                else:
                    tier_status = f"ROI LIMIT MEMENUHI TARGET MINIMUM {min_roi_target:.1f}%"
            elif not tiers.get("increment_confirmed"):
                tier_status = "INCREMENT RESMI BELUM DIKONFIRMASI — BELUM ADA BID LEGAL"
            elif bid is None or not feasible:
                tier_status = f"TIDAK ADA BID LEGAL YANG MEMENUHI ROI {hurdle:.0f}%"
            elif bid < auction_limit_now:
                # Defensive guard: an impossible sub-limit price must never be shown
                # as an actionable bid, even if an older snapshot has legacy values.
                tier_status = "TIDAK VALID — DI BAWAH LIMIT"
                bid = None
            elif cash_need_tier is not None and cash_need_tier > cash_available_now:
                tier_status = "KAS TIDAK CUKUP"
            elif not res or to_float(res.get("roi_pct"), -999) < hurdle:
                tier_status = "HURDLE TIDAK TERCAPAI"
            elif tiers.get("provisional"):
                tier_status = "SIMULASI INDIKATIF — DATA PENDUKUNG BELUM FINAL"
            else:
                tier_status = "LAYAK SECARA EKONOMI"
            tier_rows.append({
                "Tier": label,
                "Harga bid / nilai acuan": bid,
                "Ceiling teoritis di bawah limit (bukan harga bid)": economic_ceiling if bid is None else None,
                "Ceiling simulasi (increment belum resmi)": simulated_ceiling if not tiers.get("increment_confirmed") else None,
                "Total modal pada referensi": res.get("capital_before_sale") if res else None,
                "Kebutuhan kas + cadangan": cash_need_tier,
                "Profit bersih pada referensi": res.get("net_profit") if res else None,
                "ROI pada referensi": res.get("roi_pct") if res else None,
                "Status": tier_status,
            })
        st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True, column_config={
            "Harga bid / nilai acuan": st.column_config.NumberColumn(format="Rp %.0f"),
            "Ceiling teoritis di bawah limit (bukan harga bid)": st.column_config.NumberColumn(format="Rp %.0f"),
            "Ceiling simulasi (increment belum resmi)": st.column_config.NumberColumn(format="Rp %.0f"),
            "Total modal pada referensi": st.column_config.NumberColumn(format="Rp %.0f"),
            "Kebutuhan kas + cadangan": st.column_config.NumberColumn(format="Rp %.0f"),
            "Profit bersih pada referensi": st.column_config.NumberColumn(format="Rp %.0f"),
            "ROI pada referensi": st.column_config.NumberColumn(format="%.1f%%"),
        })
        st.caption("Bid legal selalu dimulai dari nilai limit dan mengikuti kelipatan resmi. Jika increment belum dikonfirmasi, sistem hanya menampilkan ceiling simulasi komputasi; angka tersebut bukan bid resmi dan tidak boleh dipakai sebagai walk-away.")
        if tiers.get("walk_away_from") is not None:
            st.metric("WALK-AWAY — bid berikutnya yang harus dihindari", idr(tiers.get("walk_away_from")))
        else:
            st.error(tiers.get("walk_away_reason", "Tidak ada harga bid yang memenuhi kriteria. Jangan ikut bidding sebelum syarat diperbaiki."))
        f1, f2, f3 = st.columns(3)
        f1.metric("Uang jaminan", idr(snap["property"].get("deposit_amount")))
        f2.metric("Estimasi kebutuhan kas proyek + cadangan risiko", idr(at.get("cash_requirement_including_reserve")))
        f3.metric("Kas tersedia investor", idr(snap.get("liquidity", {}).get("cash_available_for_new_project")))
        risk_summary = snap.get("risk_summary", {})
        st.caption(f"Risk register: {risk_summary.get('count',0)} risiko · Severity maksimum {risk_summary.get('maximum_severity',0)}/25 · Cadangan likuiditas risiko {idr(risk_summary.get('total_cash_reserve',0))}")
        if not tiers.get("increment_confirmed"): st.error("Kelipatan bid belum dikonfirmasi. Tangga bidding belum final.")
        st.markdown("### Kualitas data pasar")
        market_cols = st.columns(4)
        market_cols[0].metric("Comparable terpakai", f"{mkt.get('valid_count', 0)} listing")
        market_cols[1].metric("URL individual", f"{mkt.get('go_grade_count', 0)} / 5")
        market_cols[2].metric("Confidence pasar", f"{mkt.get('confidence', 0)}/100")
        market_cols[3].metric("Sebaran estimasi", f"{mkt.get('dispersion_pct', 0)}%")
        if mkt.get("quality_notes"):
            for note in mkt["quality_notes"]: st.caption("• " + note)
        st.caption("Tanggal terbit iklan yang tidak diketahui hanya menurunkan keyakinan umur listing. Syarat kelengkapan untuk GO adalah lima URL iklan individual yang telah dikonfirmasi dan memiliki tanggal ditemukan.")
        mc1,mc2 = st.columns(2)
        mc1.metric("Median indikasi harga / m² tanah", idr(mkt.get("land_unit_price_median")))
        mc2.metric("Median indikasi harga / m² bangunan", idr(mkt.get("building_unit_price_median")))
        if mkt.get("subject_njop"):
            if mkt.get("njop_indicated_exit"):
                st.info(f"Referensi NJOP terkalibrasi: {idr(mkt.get('njop_indicated_exit'))}. Rasio pasar/NJOP lokal dihitung dari {mkt.get('njop_comparable_count')} comparable yang memiliki pasangan harga dan NJOP; kontribusinya {mkt.get('njop_weight_pct_used')}% pada ARV dasar.")
            else:
                st.info(f"NJOP objek tercatat sebesar {idr(mkt.get('subject_njop'))}. Sistem belum menemukan minimal 3 comparable dengan data NJOP untuk mengkalibrasi rasio pasar/NJOP, sehingga NJOP ditampilkan sebagai referensi dan belum dicampurkan ke ARV.")
        elif mkt.get("njop_indicated_exit"):
            st.info(f"Indikasi berbasis NJOP pembanding: {idr(mkt.get('njop_indicated_exit'))}. Isi NJOP objek agar referensi ini dapat dihitung untuk properti target.")
        if mkt.get("valid"):
            with st.expander("Lihat seluruh comparable, penyesuaian dan dasar confidence", expanded=False):
                market_view = pd.DataFrame(mkt["valid"])
                preferred_market_cols = [c for c in ["name", "address", "price", "negotiated_price", "land_area", "building_area", "njop", "source_url", "source_url_scope", "date_found", "listing_date", "similarity_score", "missing_quality_fields", "subject_normalized_value", "market_to_njop_ratio"] if c in market_view.columns]
                st.dataframe(market_view[preferred_market_cols], use_container_width=True, hide_index=True)
        if mkt.get("invalid"):
            with st.expander("Listing yang belum dapat dihitung", expanded=False):
                st.dataframe(pd.DataFrame(mkt["invalid"]), use_container_width=True, hide_index=True)
        st.markdown("### Rincian total modal pada nilai limit")
        cost_rows = [
            {"Kelompok": "Akuisisi", "Komponen": "Harga bid / nilai limit", "Nilai": at.get("bid_price")},
            {"Kelompok": "Akuisisi", "Komponen": "Bea lelang pembeli", "Nilai": at.get("buyer_auction_fee")},
            {"Kelompok": "Akuisisi", "Komponen": "Dasar perhitungan BPHTB", "Nilai": at.get("bphtb_basis")},
            {"Kelompok": "Akuisisi", "Komponen": "BPHTB", "Nilai": at.get("bphtb")},
            {"Kelompok": "Legalitas / BPN", "Komponen": "PNBP BPN", "Nilai": at.get("bpn_pnbp_cost")},
            {"Kelompok": "Legalitas / BPN", "Komponen": "Roya", "Nilai": at.get("roya_cost")},
            {"Kelompok": "Legalitas / BPN", "Komponen": "Administrasi akuisisi", "Nilai": at.get("other_acquisition_admin")},
            {"Kelompok": "Legalitas / BPN", "Komponen": "Biaya legal lain", "Nilai": at.get("other_legal_cost")},
            {"Kelompok": "Legalitas / BPN", "Komponen": "PPAT/notaris akuisisi", "Nilai": at.get("acquisition_notary_ppat_fee")},
            {"Kelompok": "Legalitas / BPN", "Komponen": "Subtotal legalitas / BPN", "Nilai": at.get("legal_bpn_cost")},
            {"Kelompok": "Penguasaan", "Komponen": "Biaya penguasaan / kerohiman", "Nilai": at.get("possession_cost")},
            {"Kelompok": "Renovasi", "Komponen": "RAB renovasi", "Nilai": at.get("renovation_cost")},
            {"Kelompok": "Renovasi", "Komponen": "Contingency renovasi", "Nilai": at.get("renovation_contingency")},
            {"Kelompok": "Holding", "Komponen": f"Holding ({at.get('holding_months', 0)} bulan)", "Nilai": at.get("holding_cost")},
            {"Kelompok": "Pra-penjualan", "Komponen": "Marketing", "Nilai": at.get("marketing_cost")},
            {"Kelompok": "Pra-penjualan", "Komponen": "Biaya lain sebelum penjualan", "Nilai": at.get("other_presale_cost_only")},
            {"Kelompok": "TOTAL", "Komponen": "TOTAL MODAL PROYEK (sebelum biaya penjualan)", "Nilai": at.get("capital_before_sale")},
        ]
        st.dataframe(pd.DataFrame(cost_rows), use_container_width=True, hide_index=True, column_config={"Nilai": st.column_config.NumberColumn(format="Rp %.0f")})
        st.markdown("### Kebutuhan kas dan cadangan risiko")
        cash_rows = [
            {"Komponen": "Total modal proyek", "Nilai": at.get("capital_before_sale"), "Keterangan": "Biaya yang diperkirakan keluar sampai properti siap dijual."},
            {"Komponen": "Cadangan risiko penguasaan", "Nilai": at.get("possession_risk_reserve"), "Keterangan": "Cadangan likuiditas; bukan biaya proyek sampai benar-benar terpakai."},
            {"Komponen": "Cadangan risiko lain", "Nilai": at.get("general_risk_reserve"), "Keterangan": "Jumlah cadangan dari risk register yang belum ditutup."},
            {"Komponen": "TOTAL KEBUTUHAN KAS + CADANGAN", "Nilai": at.get("cash_requirement_including_reserve"), "Keterangan": "Dibandingkan dengan kas siap investasi."},
        ]
        st.dataframe(pd.DataFrame(cash_rows), use_container_width=True, hide_index=True, column_config={"Nilai": st.column_config.NumberColumn(format="Rp %.0f")})
        liquidity_rows = [
            {"Komponen": "Real cash investor", "Nilai": snap.get("liquidity", {}).get("real_cash")},
            {"Komponen": "Pengeluaran mendatang yang dikonfirmasi", "Nilai": snap.get("liquidity", {}).get("forecast_outflows")},
            {"Komponen": "Komitmen aktif yang belum dibayar", "Nilai": snap.get("liquidity", {}).get("active_unpaid_commitments")},
            {"Komponen": "Cadangan likuiditas investor", "Nilai": snap.get("liquidity", {}).get("liquidity_reserve")},
            {"Komponen": "KAS SIAP INVESTASI", "Nilai": snap.get("liquidity", {}).get("cash_available_for_new_project")},
        ]
        st.dataframe(pd.DataFrame(liquidity_rows), use_container_width=True, hide_index=True, column_config={"Nilai": st.column_config.NumberColumn(format="Rp %.0f")})
        st.caption("Uang jaminan ditampilkan terpisah sebagai kebutuhan kas di muka sesuai pengumuman lelang; jangan dijumlahkan lagi ke total modal bila sudah diperhitungkan sebagai bagian pelunasan.")
        if at.get("selling_cost") is not None:
            st.markdown("### Biaya penjualan dan hasil bersih")
            selling_rows = [
                {"Komponen": "PPh Final penjual", "Nilai": at.get("seller_final_tax")},
                {"Komponen": "Komisi agen", "Nilai": at.get("seller_agent")},
                {"Komponen": "AJB / PPAT penjual", "Nilai": at.get("seller_ajb_ppat")},
                {"Komponen": "Biaya penjualan lain", "Nilai": at.get("seller_misc")},
                {"Komponen": "TOTAL BIAYA PENJUALAN", "Nilai": at.get("selling_cost")},
                {"Komponen": "Hasil penjualan setelah biaya penjualan", "Nilai": at.get("net_proceeds")},
                {"Komponen": "PROFIT BERSIH PROYEK", "Nilai": at.get("net_profit")},
            ]
            st.dataframe(pd.DataFrame(selling_rows), use_container_width=True, hide_index=True, column_config={"Nilai": st.column_config.NumberColumn(format="Rp %.0f")})
        with st.expander("Cara membaca angka keuangan", expanded=False):
            st.markdown("""
            - **Total modal proyek** adalah harga bid dan semua biaya sebelum penjualan, termasuk contingency dan holding.
            - **Cadangan risiko** ditambahkan pada kebutuhan kas agar dana tersedia bila risiko terjadi. Cadangan tersebut tidak masuk profit sebagai biaya sampai benar-benar digunakan.
            - **Biaya penjualan** dipotong dari hasil penjualan; tidak ditambahkan lagi ke modal sebelum penjualan.
            - **Kebutuhan kas + cadangan** dibandingkan dengan **kas siap investasi**. Uang jaminan adalah kebutuhan waktu awal dan tidak boleh dihitung dua kali.
            """)
        with st.expander("Arti status keputusan", expanded=False):
            st.markdown("""
            - **GO:** seluruh hard gate yang ditetapkan sudah terpenuhi. Tetap lakukan pemeriksaan akhir sebelum bidding.
            - **CONDITIONAL GO:** secara awal layak, tetapi masih ada pemeriksaan penting yang perlu diselesaikan.
            - **HOLD:** data atau konfirmasi penting belum lengkap. Jangan bidding sebelum blocker diselesaikan.
            - **DO NOT BID:** batas ekonomi atau risiko utama menunjukkan objek tidak layak dibeli pada nilai limit.
            """)
        if decision.get("blockers"):
            st.markdown("### Hal yang harus diselesaikan sebelum bidding")
            for x in decision["blockers"]: st.error(x)
        if decision.get("warnings"):
            st.markdown("### Catatan kualitas data dan risiko")
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
            try:
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
            except Exception as save_exc:
                st.error("Gagal menyimpan analisis ke Google Sheets. Tidak semua tab mungkin sudah tersimpan; periksa Database & History sebelum menekan simpan ulang.")
                st.code(str(save_exc))

# ======================== PAGE 3: PROJECT ONBOARDING =======================
elif page == "Project Onboarding":
    st.markdown("<div class='hero'><h1>Daftarkan Proyek Berjalan</h1><p>Masukkan properti yang sudah dimenangkan atau diperoleh sebelum PFMS digunakan. Anda tidak perlu mengulang analisis lelang; catat posisi proyek dan transaksi yang sudah benar-benar terjadi.</p></div>", unsafe_allow_html=True)
    st.info("Gunakan halaman ini untuk proyek yang sudah diperoleh. Keputusan analisis historis tidak dibuat ulang: PFMS menandai asal data sebagai Project Onboarding dan lifecycle sebagai ACTIVE.")
    with st.expander("Panduan pencatatan agar angka tidak terhitung dua kali", expanded=False):
        st.markdown("""
        - **Harga menang** adalah informasi nilai perolehan. Pembayaran harga perolehan dicatat satu kali pada formulir Realisasi Biaya setelah proyek dibuat.
        - Jika deposit menjadi bagian harga menang, catat deposit + sisa pelunasan sehingga totalnya sama dengan harga menang. Jangan mencatat deposit dan harga menang penuh sekaligus.
        - **Sudah dibayar** hanya untuk uang yang benar-benar keluar, termasuk pembayaran historis sebelum PFMS digunakan.
        - **Komitmen belum dibayar** adalah kewajiban yang sudah disepakati. **Forecast tersisa** adalah estimasi biaya yang belum menjadi komitmen.
        - Budget dan forecast bukan pengeluaran aktual. Seluruh pembayaran dan item anggaran ditambahkan setelah proyek terdaftar, di menu Properti Aktif.
        """)
    with st.form("project_onboarding_form_v110", clear_on_submit=False):
        st.markdown("### 1. Identitas properti")
        c1, c2 = st.columns(2)
        with c1:
            onboard_name = st.text_input("Nama proyek / nama properti *", placeholder="Contoh: TAS 3 Blok M6 No. 12")
            onboard_lot = st.text_input("Kode lot / nomor objek lelang (opsional)")
            onboard_address = st.text_input("Alamat lengkap *")
            onboard_district = st.text_input("Kecamatan / kabupaten")
            onboard_province = st.text_input("Provinsi", value="Jawa Timur")
        with c2:
            onboard_certificate = st.selectbox("Jenis sertifikat", ["", "SHM", "SHGB", "HGB", "Lainnya"])
            onboard_certificate_no = st.text_input("Nomor sertifikat (opsional)")
            onboard_land = st.number_input("Luas tanah (m²)", min_value=0.0, step=1.0)
            onboard_building = st.number_input("Luas bangunan (m²)", min_value=0.0, step=1.0)
            onboard_njop = st.number_input("NJOP (Rp, opsional)", min_value=0, step=1_000_000)
        st.markdown("### 2. Informasi perolehan dan posisi proyek")
        c1, c2, c3 = st.columns(3)
        with c1:
            onboard_win_price = st.number_input("Harga menang / harga perolehan (Rp) *", min_value=0, step=1_000_000)
            onboard_limit = st.number_input("Nilai limit lelang (Rp, opsional)", min_value=0, step=1_000_000)
        with c2:
            onboard_win_date = st.date_input("Tanggal menang / perolehan", value=date.today())
            onboard_deposit = st.number_input("Uang jaminan (informasi, bukan biaya tambahan)", min_value=0, step=500_000)
        with c3:
            onboard_stage = st.selectbox("Tahap proyek saat ini", PROJECT_STAGES[:-1], index=2)
            onboard_property_type = st.selectbox("Jenis properti", ["Rumah tinggal", "Ruko", "Tanah", "Apartemen", "Lainnya"])
        onboard_notes = st.text_area("Catatan kondisi awal dan progres saat ini", height=90, placeholder="Contoh: penguasaan sudah clean and clear; renovasi berlangsung; atap/plafon selesai; pekerjaan kamar mandi masih berjalan...")
        st.markdown("### 3. Pencatatan keuangan setelah proyek didaftarkan")
        st.info("Agar input lebih mudah, proyek didaftarkan terlebih dahulu. Setelah tersimpan, buka Properti Aktif untuk memasukkan setiap pembayaran historis dan setiap item anggaran/komitmen melalui formulir bertahap (Kategori → Subkategori → Item/Lingkup). Tabel di Properti Aktif hanya menjadi tampilan, bukan tempat mengetik.")
        onboard_submit = st.form_submit_button("Daftarkan proyek ke PFMS", type="primary", use_container_width=True)
    if onboard_submit:
        property_data = {
            "lot_code": onboard_lot.strip(), "name": onboard_name.strip(), "address": onboard_address.strip(),
            "district": onboard_district.strip(), "province": onboard_province.strip(),
            "auction_limit": onboard_limit or None, "land_area": onboard_land or None,
            "building_area": onboard_building or None, "njop": onboard_njop or None,
            "certificate_type": onboard_certificate, "certificate_no": onboard_certificate_no.strip(),
            "property_type": onboard_property_type,
        }
        win_details = {"win_price": onboard_win_price, "win_date": onboard_win_date.isoformat(), "deposit_amount": onboard_deposit or None}
        # Safely merge with an existing prospect when the same lot code is already in PFMS.
        existing_matches = []
        for existing_row in list_properties():
            same_lot = onboard_lot.strip() and str(existing_row.get("lot_code") or "").strip().lower() == onboard_lot.strip().lower()
            same_name_address = str(existing_row.get("name") or "").strip().lower() == onboard_name.strip().lower() and str(existing_row.get("address") or "").strip().lower() == onboard_address.strip().lower()
            if same_lot or (not onboard_lot.strip() and same_name_address):
                existing_matches.append(existing_row)
        if len(existing_matches) > 1:
            st.error("Ditemukan lebih dari satu record yang mungkin merupakan properti yang sama. Periksa Database & Riwayat terlebih dahulu agar tidak membuat duplikasi.")
        elif existing_matches and existing_matches[0].get("lifecycle_status") in {"WON", "ACTIVE", "SOLD"}:
            st.error(f"Properti ini sudah terdaftar dengan status {existing_matches[0].get('lifecycle_status')} (ID: {existing_matches[0].get('property_id')}). Gunakan halaman Properti Aktif untuk memperbarui biaya dan progres, bukan mendaftarkannya ulang.")
        else:
            try:
                records = build_project_onboarding_records(
                    property_data=property_data,
                    win_details=win_details,
                    project_stage=onboard_stage,
                    project_notes=onboard_notes,
                    actual_transactions=[],
                    budget_items=[],
                    existing_property=existing_matches[0] if existing_matches else None,
                )
                upsert_record("PROPERTIES", "property_id", records["property"])
                for actual_record in records["actual_records"]:
                    append_record("COST_ACTUALS", actual_record)
                for budget_record in records["budget_records"]:
                    upsert_record("PROJECT_BUDGETS", "budget_item_id", budget_record)
                log_event("PROPERTY", records["property_id"], "PROJECT_ONBOARDED", {
                    "actual_transaction_count": len(records["actual_records"]),
                    "budget_line_count": len(records["budget_records"]),
                    "project_stage": onboard_stage,
                })
                cached_read.clear()
                st.success(f"Proyek berhasil didaftarkan. Property ID: {records['property_id']}. Status proyek: ACTIVE · Tahap: {onboard_stage}.")
                st.info("Langkah berikutnya: buka Properti Aktif, pilih proyek ini, lalu masukkan pembayaran historis dan item budget satu per satu melalui formulir yang dipandu. Tabel hanya untuk melihat data.")
            except Exception as exc:
                st.error(f"Proyek belum berhasil disimpan: {exc}")

# ============================ PAGE 4: CASHFLOW =============================
elif page == "Investor Cashflow":
    st.markdown("<div class='hero'><h1>Kas & Kemampuan Investasi</h1><p>Perbarui kas aktual dan catat pengeluaran yang benar-benar sudah Anda rencanakan atau konfirmasi.</p></div>", unsafe_allow_html=True)
    profile, events, liquidity = get_cash_data()
    st.caption("Sistem tidak mengarang pengeluaran. Kas siap investasi dihitung dari kas aktual dikurangi pengeluaran terkonfirmasi, komitmen aktif, dan cadangan likuiditas.")
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
    st.caption("Saldo kas tersedia = real cash – pengeluaran terkonfirmasi mendatang – komitmen belum dibayar dari budget aset aktif – reserve. Forecast yang belum dikomitmen tidak otomatis mengurangi kas.")
    st.markdown("### Rincian proyeksi biaya aset aktif")
    active_rows = []
    for pr in [x for x in list_properties() if x.get("lifecycle_status") in {"WON", "ACTIVE"}]:
        pay = record_payload(pr); latest = pay.get("latest_analysis") or {}; win = pay.get("win_details", {})
        in_data = latest.get("calculation_inputs", {})
        if not in_data: in_data = {"property": latest.get("property", {}), "survey": latest.get("survey", {}), "costs": latest.get("costs", {}), "rules": latest.get("rules", {})}
        win_bid = to_float(win.get("win_price"), to_float(pr.get("auction_limit")))
        exit_price = to_float((latest.get("market") or {}).get("conservative_exit"))
        estimate = calculate_project(win_bid, exit_price, in_data) if win_bid > 0 and exit_price > 0 else {}
        actuals = [x for x in read_table("COST_ACTUALS") if x.get("property_id") == pr.get("property_id") and str(x.get("category", "")).lower() not in {"selling", "penjualan", "biaya penjualan", "pajak penjualan", "komisi agen"}]
        actual_sum = sum(to_float(x.get("amount")) for x in actuals)
        budget = to_float(estimate.get("capital_before_sale"))
        active_rows.append({"Objek":pr.get("name"),"Tahap":pay.get("project_stage","Settlement"),"Estimasi modal proyek":budget,"Biaya aktual tercatat":actual_sum,"Indikasi sisa estimasi":max(0,budget-actual_sum)})
    if active_rows:
        st.dataframe(pd.DataFrame(active_rows), use_container_width=True, hide_index=True, column_config={"Estimasi modal proyek":st.column_config.NumberColumn(format="Rp %.0f"),"Biaya aktual tercatat":st.column_config.NumberColumn(format="Rp %.0f"),"Indikasi sisa estimasi":st.column_config.NumberColumn(format="Rp %.0f")})
        st.info("Komitmen belum dibayar yang sudah dimasukkan pada budget proyek otomatis mengurangi kas siap investasi. Jangan input komitmen yang sama lagi sebagai Cashflow Event; forecast yang belum dikomitmen tetap menjadi informasi proyek dan belum mengurangi kas.")
    else: st.caption("Belum ada aset aktif.")

# ======================== PAGE 4: PORTFOLIO COMPARISON =====================
elif page == "Portfolio Comparison":
    st.markdown("<div class='hero'><h1>Bandingkan Peluang Investasi</h1><p>Bandingkan beberapa objek berdasarkan estimasi profit, ROI, risiko, dan kemampuan kas secara bersamaan.</p></div>", unsafe_allow_html=True)
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

# ============================ PAGE 6: ACTIVE ===============================
elif page == "Active Properties":
    st.markdown("<div class='hero'><h1>Properti Aktif</h1><p>Pantau uang yang sudah keluar, kewajiban belum dibayar, perkiraan biaya tersisa, dan progres pekerjaan setiap proyek.</p></div>", unsafe_allow_html=True)
    props = [p for p in list_properties() if p.get("lifecycle_status") in {"WON", "ACTIVE"}]
    if not props:
        st.info("Belum ada proyek aktif. Gunakan menu Daftarkan Proyek Berjalan untuk memasukkan proyek yang sudah diperoleh, atau tandai peluang lelang sebagai WON setelah menang.")
    else:
        options = {f"{p.get('name')} · {p.get('lot_code') or p.get('property_id')} · {p.get('lifecycle_status')}": p for p in props}
        label = st.selectbox("Pilih proyek yang ingin dikelola", list(options.keys()))
        p = options[label]; pid = p["property_id"]
        payload = record_payload(p)
        input_data = payload.get("input_data", {})
        prop_data = input_data.get("property", {}) if isinstance(input_data, dict) else {}
        win = payload.get("win_details", {})
        active_actual_rows = [x for x in read_table("COST_ACTUALS") if x.get("property_id") == pid]
        project_budget_rows = [x for x in read_table("PROJECT_BUDGETS") if x.get("property_id") == pid]
        ledger = summarize_project_ledger(active_actual_rows, project_budget_rows)
        latest = payload.get("latest_analysis") or {}
        calc_inputs = latest.get("calculation_inputs") or {"property": latest.get("property", {}), "survey": latest.get("survey", {}), "costs": latest.get("costs", {}), "rules": latest.get("rules", {})}
        winning_price = to_float(win.get("win_price", p.get("auction_limit")))
        conservative_exit = to_float((latest.get("market") or {}).get("conservative_exit"))
        active_estimate = calculate_project(winning_price, conservative_exit, calc_inputs) if winning_price > 0 and conservative_exit > 0 else {}
        estimate_capital = to_float(active_estimate.get("capital_before_sale"))
        actual_project_cost = ledger["actual_project_cost"]
        committed_total = ledger["committed_unpaid_total"]
        forecast_total = ledger["forecast_remaining_total"]
        projected_completion = ledger["project_cost_at_completion_ex_selling"]
        if not project_budget_rows and estimate_capital > actual_project_cost:
            fallback_remaining = max(0.0, estimate_capital - actual_project_cost)
            projected_completion = estimate_capital
        else:
            fallback_remaining = 0.0
        stage_now = payload.get("project_stage", "Settlement")
        st.markdown(f"### {p.get('name')} · {p.get('address') or 'Alamat belum diisi'}")
        origin = payload.get("project_origin") or payload.get("project_onboarding", {}).get("onboarding_version")
        if origin == "PROJECT_ONBOARDING":
            st.caption("Asal data: Project Onboarding · Proyek sudah diperoleh sebelum/di luar alur analisis baru PFMS. Status INCOMPLETE pada keputusan underwriting bukan berarti aset belum dimenangkan.")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total aktual dibayar", idr(ledger["actual_paid_total"]))
        k2.metric("Komitmen belum dibayar", idr(committed_total))
        k3.metric("Forecast sisa biaya", idr(forecast_total if project_budget_rows else fallback_remaining))
        k4.metric("Proyeksi modal s.d. siap dijual", idr(projected_completion), help="Biaya proyek sampai siap dipasarkan, tidak termasuk biaya penjualan dan cadangan risiko yang belum terpakai.")
        st.caption(f"Harga menang/perolehan tercatat: {idr(winning_price)} · Tahap proyek: {stage_now}. Biaya penjualan aktual dipisahkan dari modal proyek sampai selesai.")

        st.markdown("### 1. Posisi anggaran dan realisasi")
        if project_budget_rows:
            budget_display = pd.DataFrame(ledger["budget_lines"])
            if not budget_display.empty:
                st.dataframe(budget_display, use_container_width=True, hide_index=True, column_config={
                    "budget_amount": st.column_config.NumberColumn("Budget total", format="Rp %.0f"),
                    "actual_paid": st.column_config.NumberColumn("Sudah dibayar", format="Rp %.0f"),
                    "committed_unpaid": st.column_config.NumberColumn("Komitmen belum dibayar", format="Rp %.0f"),
                    "forecast_remaining": st.column_config.NumberColumn("Forecast tersisa", format="Rp %.0f"),
                    "expected_at_completion": st.column_config.NumberColumn("Estimasi akhir", format="Rp %.0f"),
                    "variance_at_completion": st.column_config.NumberColumn("Selisih vs budget", format="Rp %.0f"),
                })
            st.caption(f"Total budget: {idr(ledger['budget_total'])} · Sudah dibayar: {idr(ledger['actual_paid_total'])} · Komitmen: {idr(committed_total)} · Forecast: {idr(forecast_total)}")
            if ledger.get("unlinked_actual_cost", 0) > 0:
                st.warning(f"Ada {idr(ledger['unlinked_actual_cost'])} realisasi yang belum ditautkan ke item budget. Angka ini tetap masuk total biaya aktual, tetapi tidak muncul pada kolom aktual per baris budget.")
        elif active_estimate:
            st.info("Belum ada rincian budget/komitmen per item. Angka perkiraan sisa di atas berasal dari snapshot underwriting lama. Tambahkan budget tiap pekerjaan di bawah agar laporan Budget vs Actual lebih akurat.")
            bva = budget_actual_table(active_estimate, active_actual_rows)
            st.dataframe(bva, use_container_width=True, hide_index=True, column_config={"Anggaran": st.column_config.NumberColumn(format="Rp %.0f"), "Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "Varians (Aktual - Anggaran)": st.column_config.NumberColumn(format="Rp %.0f")})
        else:
            st.warning("Belum ada budget per item. Isi anggaran dan forecast sisa pekerjaan agar total biaya sampai selesai dapat dihitung dari kondisi proyek yang sebenarnya.")

        st.markdown("### 2. Perbarui progres proyek")
        with st.form("win_update_form_v110"):
            c1, c2, c3 = st.columns(3)
            with c1:
                win_price = st.number_input("Harga menang / perolehan (Rp)", min_value=0, step=1_000_000, value=safe_int(win.get("win_price", prop_data.get("auction_limit", 0))))
            with c2:
                try: win_date_default = date.fromisoformat(str(win.get("win_date") or date.today().isoformat())[:10])
                except ValueError: win_date_default = date.today()
                win_date = st.date_input("Tanggal menang / perolehan", value=win_date_default)
            with c3:
                stage_options = PROJECT_STAGES[:-1]
                stage_index = stage_options.index(stage_now) if stage_now in stage_options else 0
                lifecycle_stage = st.selectbox("Tahap proyek saat ini", stage_options, index=stage_index)
            notes = st.text_area("Catatan progres proyek", value=str(payload.get("progress_notes") or payload.get("project_onboarding", {}).get("notes") or ""))
            progress_confirm = st.checkbox("Saya sudah memeriksa harga, tanggal dan tahap proyek yang akan disimpan.", key=f"progress_confirm_{pid}")
            upd = st.form_submit_button("Simpan progres proyek")
        if upd and not progress_confirm:
            st.warning("Centang konfirmasi setelah memastikan perubahan data proyek sudah benar.")
        if upd and progress_confirm:
            payload["win_details"] = {**win, "win_price": win_price, "win_date": win_date.isoformat()}
            payload["project_stage"] = lifecycle_stage
            payload["progress_notes"] = notes
            upsert_record("PROPERTIES", "property_id", {**p, "updated_at": iso_now(), "lifecycle_status": "ACTIVE", "payload": payload})
            log_event("PROPERTY", pid, "STAGE_UPDATED", {"stage": lifecycle_stage})
            st.success("Tahap proyek diperbarui."); cached_read.clear(); st.rerun()

        st.markdown("### 3. Catat realisasi biaya")
        st.caption("Catat satu transaksi untuk setiap pembayaran yang benar-benar sudah keluar. Formulir ini terpisah dari tabel riwayat. Sebelum tersimpan, sistem memvalidasi saldo komitmen/forecast bila transaksi ditautkan ke item budget.")
        actual_category = st.selectbox("1. Kategori biaya", ACTUAL_CATEGORIES, key=f"actual_category_{pid}")
        actual_subcategory_options = subcategory_options(actual_category)
        actual_subcategory = st.selectbox("2. Subkategori", actual_subcategory_options, key=f"actual_subcategory_{pid}_{actual_category}")
        actual_scope_options = scope_options(actual_category, actual_subcategory)
        actual_scope_choice = st.selectbox("3. Item / lingkup biaya", actual_scope_options, key=f"actual_scope_{pid}_{actual_category}_{actual_subcategory}")
        actual_scope_custom = st.text_input("Tuliskan item/lingkup lain", key=f"actual_scope_custom_{pid}", placeholder="Contoh: 25 genteng, upah pasang kamar mandi") if actual_scope_choice == "Lainnya" else ""
        actual_scope_text = actual_scope_custom.strip() if actual_scope_choice == "Lainnya" else actual_scope_choice
        budget_choices = {"(Tidak ditautkan ke item budget)": ""}
        for budget in project_budget_rows:
            if str(budget.get("status") or "Active") not in {"Cancelled", "Archived"}:
                budget_choices[f"{budget.get('category')} · {budget.get('subcategory') or 'Umum'} · {budget.get('description')} · {budget.get('budget_item_id')}"] = str(budget.get("budget_item_id"))
        with st.form(f"actual_cost_form_v111_{pid}"):
            a1, a2 = st.columns(2)
            with a1:
                txdate = st.date_input("Tanggal pembayaran", value=date.today(), key=f"actual_txdate_{pid}")
                amount = st.number_input("Nominal yang sudah dibayar (Rp)", min_value=0, step=500_000, key=f"actual_amount_{pid}")
                vendor = st.text_input("Penerima / vendor", placeholder="Nama toko, tukang, kontraktor, instansi", key=f"actual_vendor_{pid}")
            with a2:
                linked_budget_label = st.selectbox("Tautkan ke item anggaran (opsional)", list(budget_choices.keys()), key=f"actual_budget_link_{pid}")
                payment_source = st.selectbox("Pembayaran ini mengurangi", ["Pengeluaran di luar budget", "Pembayaran atas komitmen", "Pembayaran dari forecast"], key=f"actual_payment_source_{pid}", help="Pilih komitmen atau forecast hanya bila pembayaran benar-benar mengurangi saldo item tersebut.")
                payment_method = st.selectbox("Metode pembayaran", ["Transfer", "Tunai", "QRIS", "Debit/kartu", "Lainnya"], key=f"actual_payment_method_{pid}")
                receipt = st.text_input("URL bukti pembayaran (opsional)", key=f"actual_receipt_{pid}")
            payment_note = st.text_area("Catatan tambahan (opsional)", height=68, key=f"actual_payment_note_{pid}")
            confirm_payment = st.checkbox("Saya sudah memeriksa tanggal, kategori, nominal, dan penerima pembayaran.", key=f"confirm_payment_{pid}")
            addcost = st.form_submit_button("Simpan pembayaran", type="primary", use_container_width=True)
        if addcost:
            linked_budget_id = budget_choices[linked_budget_label]
            new_transaction = {
                "actual_id": new_id("ACT"), "property_id": pid,
                "transaction_date": txdate.isoformat(), "category": actual_category,
                "amount": amount, "description": actual_scope_text + (f" — {payment_note.strip()}" if payment_note.strip() else ""),
                "receipt_url": receipt, "created_at": iso_now(), "budget_item_id": linked_budget_id,
                "subcategory": actual_subcategory, "vendor": vendor, "payment_method": payment_method,
                "details_json": {"entry_source": "ACTIVE_PROPERTY_LEDGER", "payment_source": payment_source, "item_scope": actual_scope_text, "additional_note": payment_note.strip()},
            }
            if not confirm_payment:
                st.warning("Centang konfirmasi setelah memeriksa data pembayaran.")
            elif amount <= 0:
                st.warning("Nominal pembayaran harus lebih dari nol.")
            elif not actual_scope_text:
                st.warning("Item/lingkup biaya perlu diisi agar riwayat mudah ditelusuri.")
            elif payment_source != "Pengeluaran di luar budget" and not linked_budget_id:
                st.warning("Pilih item anggaran jika pembayaran akan mengurangi komitmen atau forecast.")
            else:
                reconciled_budgets, allocation_error = reconcile_budget_payment_change(project_budget_rows, None, new_transaction)
                if allocation_error:
                    st.error(allocation_error)
                else:
                    try:
                        append_record("COST_ACTUALS", new_transaction)
                        for updated_budget in reconciled_budgets:
                            original_budget = next((b for b in project_budget_rows if b.get("budget_item_id") == updated_budget.get("budget_item_id")), None)
                            if original_budget and (to_float(original_budget.get("committed_unpaid")) != to_float(updated_budget.get("committed_unpaid")) or to_float(original_budget.get("forecast_remaining")) != to_float(updated_budget.get("forecast_remaining"))):
                                upsert_record("PROJECT_BUDGETS", "budget_item_id", {**updated_budget, "updated_at": iso_now()})
                        log_event("COST_ACTUAL", new_transaction["actual_id"], "ADDED", {"property_id": pid, "amount": amount, "category": actual_category, "budget_item_id": linked_budget_id, "payment_source": payment_source})
                        for field_key in [f"actual_txdate_{pid}", f"actual_amount_{pid}", f"actual_vendor_{pid}", f"actual_budget_link_{pid}", f"actual_payment_source_{pid}", f"actual_payment_method_{pid}", f"actual_receipt_{pid}", f"actual_payment_note_{pid}", f"confirm_payment_{pid}", f"actual_scope_custom_{pid}"]:
                            st.session_state.pop(field_key, None)
                        st.success("Pembayaran berhasil dicatat. Formulir dikosongkan untuk transaksi berikutnya.")
                        cached_read.clear(); st.rerun()
                    except Exception as exc:
                        st.error(f"Penyimpanan pembayaran/budget belum lengkap. Periksa riwayat transaksi dan item budget sebelum mencoba ulang. Detail: {exc}")

        st.markdown("### 4. Riwayat pembayaran proyek")
        if active_actual_rows:
            actual_display = pd.DataFrame(active_actual_rows)
            display_cols = [c for c in ["transaction_date", "category", "subcategory", "description", "vendor", "amount", "payment_method", "receipt_url", "budget_item_id"] if c in actual_display.columns]
            st.dataframe(actual_display[display_cols], use_container_width=True, hide_index=True, column_config={"amount": st.column_config.NumberColumn("Jumlah dibayar", format="Rp %.0f")})
            transaction_options = {
                f"{x.get('transaction_date','—')} · {x.get('category','Lainnya')} · {x.get('description','')} · {idr(x.get('amount'))} · {x.get('actual_id')}": x
                for x in active_actual_rows
            }
            with st.expander("Koreksi transaksi yang sudah tercatat", expanded=False):
                selected_transaction_label = st.selectbox("Pilih transaksi yang akan dikoreksi", list(transaction_options.keys()), key=f"edit_actual_select_{pid}")
                selected_transaction = transaction_options[selected_transaction_label]
                edit_flag_key = f"show_edit_actual_{pid}"
                if st.button("Edit transaksi terpilih", key=f"open_edit_actual_{pid}"):
                    st.session_state[edit_flag_key] = True
                if st.session_state.get(edit_flag_key, False):
                    txid = str(selected_transaction.get("actual_id") or "legacy")
                    tx_details = parse_json(selected_transaction.get("details_json"), {})
                    prior_category = str(selected_transaction.get("category") or "Lainnya")
                    edit_categories = list(ACTUAL_CATEGORIES)
                    if prior_category not in edit_categories: edit_categories.append(prior_category)
                    edit_subcats = subcategory_options(prior_category)
                    prior_subcat = str(selected_transaction.get("subcategory") or "")
                    if prior_subcat and prior_subcat not in edit_subcats: edit_subcats.append(prior_subcat)
                    with st.form(f"edit_actual_form_{pid}_{txid}"):
                        st.caption(f"Transaksi: {txid}. Koreksi akan memperbarui transaksi yang sama dan mencatat perubahan di audit history.")
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            edit_tx_date = st.date_input("Tanggal pembayaran", value=as_date(selected_transaction.get("transaction_date")), key=f"edit_tx_date_{pid}_{txid}")
                            edit_amount = st.number_input("Nominal pembayaran (Rp)", min_value=0, step=500_000, value=safe_int(selected_transaction.get("amount")), key=f"edit_amount_{pid}_{txid}")
                            edit_vendor = st.text_input("Penerima / vendor", value=str(selected_transaction.get("vendor") or ""), key=f"edit_vendor_{pid}_{txid}")
                            edit_category = st.selectbox("Kategori", edit_categories, index=edit_categories.index(prior_category), key=f"edit_category_{pid}_{txid}")
                            edit_subcat_options = subcategory_options(edit_category)
                            if prior_subcat and prior_subcat not in edit_subcat_options: edit_subcat_options.append(prior_subcat)
                            edit_subcategory = st.selectbox("Subkategori", edit_subcat_options, index=edit_subcat_options.index(prior_subcat) if prior_subcat in edit_subcat_options else 0, key=f"edit_subcategory_{pid}_{txid}_{edit_category}")
                        with ec2:
                            existing_budget_id = str(selected_transaction.get("budget_item_id") or "")
                            edit_budget_choices = dict(budget_choices)
                            if existing_budget_id and existing_budget_id not in edit_budget_choices.values():
                                edit_budget_choices[f"(Item budget lama) · {existing_budget_id}"] = existing_budget_id
                            current_budget_label = next((k for k, v in edit_budget_choices.items() if v == existing_budget_id), list(edit_budget_choices.keys())[0])
                            edit_budget_label = st.selectbox("Item anggaran", list(edit_budget_choices.keys()), index=list(edit_budget_choices.keys()).index(current_budget_label), key=f"edit_budget_link_{pid}_{txid}")
                            old_source = str(tx_details.get("payment_source") or "Pengeluaran di luar budget")
                            edit_source_options = ["Pengeluaran di luar budget", "Pembayaran atas komitmen", "Pembayaran dari forecast"]
                            if old_source not in edit_source_options: old_source = edit_source_options[0]
                            edit_payment_source = st.selectbox("Mengurangi saldo", edit_source_options, index=edit_source_options.index(old_source), key=f"edit_payment_source_{pid}_{txid}")
                            methods = ["Transfer", "Tunai", "QRIS", "Debit/kartu", "Lainnya"]
                            old_method = str(selected_transaction.get("payment_method") or "Transfer")
                            if old_method not in methods: old_method = "Lainnya"
                            edit_method = st.selectbox("Metode pembayaran", methods, index=methods.index(old_method), key=f"edit_payment_method_{pid}_{txid}")
                            edit_receipt = st.text_input("URL bukti pembayaran", value=str(selected_transaction.get("receipt_url") or ""), key=f"edit_receipt_{pid}_{txid}")
                        edit_item_scope = st.text_input("Item / lingkup biaya", value=str(tx_details.get("item_scope") or selected_transaction.get("description") or ""), key=f"edit_scope_{pid}_{txid}")
                        edit_note = st.text_area("Catatan tambahan", value=str(tx_details.get("additional_note") or ""), key=f"edit_note_{pid}_{txid}")
                        edit_confirm = st.checkbox("Saya yakin koreksi data transaksi ini sudah benar.", key=f"edit_confirm_{pid}_{txid}")
                        save_transaction_edit = st.form_submit_button("Simpan koreksi transaksi")
                    if save_transaction_edit:
                        new_budget_id = edit_budget_choices[edit_budget_label]
                        updated_transaction = {
                            **selected_transaction, "transaction_date": edit_tx_date.isoformat(), "category": edit_category,
                            "subcategory": edit_subcategory, "amount": edit_amount, "vendor": edit_vendor,
                            "receipt_url": edit_receipt, "payment_method": edit_method,
                            "budget_item_id": new_budget_id,
                            "description": edit_item_scope.strip() + (f" — {edit_note.strip()}" if edit_note.strip() else ""),
                            "details_json": {"entry_source": tx_details.get("entry_source", "ACTIVE_PROPERTY_LEDGER"), "payment_source": edit_payment_source, "item_scope": edit_item_scope.strip(), "additional_note": edit_note.strip()},
                            "updated_at": iso_now(),
                        }
                        if not edit_confirm:
                            st.warning("Centang konfirmasi setelah memeriksa seluruh perubahan.")
                        elif edit_amount <= 0 or not edit_item_scope.strip():
                            st.warning("Nominal harus lebih dari nol dan item/lingkup tidak boleh kosong.")
                        elif edit_payment_source != "Pengeluaran di luar budget" and not new_budget_id:
                            st.warning("Pilih item budget jika pembayaran akan mengurangi komitmen atau forecast.")
                        else:
                            updated_budgets, reconcile_error = reconcile_budget_payment_change(project_budget_rows, selected_transaction, updated_transaction)
                            if reconcile_error:
                                st.error(reconcile_error)
                            else:
                                before = {k: selected_transaction.get(k) for k in ["transaction_date", "category", "subcategory", "description", "amount", "vendor", "budget_item_id", "payment_method"]}
                                upsert_record("COST_ACTUALS", "actual_id", updated_transaction)
                                for updated_budget in updated_budgets:
                                    original_budget = next((b for b in project_budget_rows if b.get("budget_item_id") == updated_budget.get("budget_item_id")), None)
                                    if original_budget and (to_float(original_budget.get("committed_unpaid")) != to_float(updated_budget.get("committed_unpaid")) or to_float(original_budget.get("forecast_remaining")) != to_float(updated_budget.get("forecast_remaining"))):
                                        upsert_record("PROJECT_BUDGETS", "budget_item_id", {**updated_budget, "updated_at": iso_now()})
                                after = {k: updated_transaction.get(k) for k in before}
                                log_event("COST_ACTUAL", txid, "CORRECTED", {"property_id": pid, "before": before, "after": after})
                                st.session_state[edit_flag_key] = False
                                st.success("Transaksi diperbarui. Riwayat perubahan tersimpan di Database & Riwayat.")
                                cached_read.clear(); st.rerun()
                    if st.button("Tutup mode edit", key=f"close_edit_actual_{pid}"):
                        st.session_state[edit_flag_key] = False
                        st.rerun()
        else:
            st.info("Belum ada transaksi pembayaran proyek.")

        st.markdown("### 4. Anggaran, komitmen, dan forecast pekerjaan")
        st.caption("Tabel berikut hanya untuk melihat data. Untuk menambah atau mengubah angka, gunakan formulir di bawah. Budget adalah batas/rencana biaya; komitmen adalah kewajiban yang sudah disepakati; forecast adalah biaya tersisa yang belum dikomitmen.")
        if project_budget_rows:
            budget_display = pd.DataFrame(ledger["budget_lines"])
            if not budget_display.empty:
                st.dataframe(budget_display, use_container_width=True, hide_index=True, column_config={
                    "budget_amount": st.column_config.NumberColumn("Anggaran", format="Rp %.0f"),
                    "actual_paid": st.column_config.NumberColumn("Sudah dibayar", format="Rp %.0f"),
                    "committed_unpaid": st.column_config.NumberColumn("Komitmen belum dibayar", format="Rp %.0f"),
                    "forecast_remaining": st.column_config.NumberColumn("Forecast tersisa", format="Rp %.0f"),
                    "expected_at_completion": st.column_config.NumberColumn("Estimasi total item", format="Rp %.0f"),
                    "variance_at_completion": st.column_config.NumberColumn("Selisih vs anggaran", format="Rp %.0f"),
                })
            st.caption(f"Total anggaran: {idr(ledger['budget_total'])} · Aktual: {idr(ledger['actual_paid_total'])} · Komitmen: {idr(committed_total)} · Forecast: {idr(forecast_total)}")
            with st.expander("Edit item anggaran yang sudah ada", expanded=False):
                budget_edit_options = {f"{b.get('category')} · {b.get('subcategory') or 'Umum'} · {b.get('description')} · {b.get('budget_item_id')}": b for b in project_budget_rows if str(b.get("status") or "Active") not in {"Cancelled", "Archived"}}
                if budget_edit_options:
                    selected_budget_label = st.selectbox("Pilih item anggaran untuk diperbarui", list(budget_edit_options.keys()), key=f"budget_edit_select_{pid}")
                    selected_budget = budget_edit_options[selected_budget_label]
                    current_budget_category = str(selected_budget.get("category") or "Lainnya")
                    edit_budget_category = st.selectbox("Kategori item terpilih", BUDGET_CATEGORIES, index=BUDGET_CATEGORIES.index(current_budget_category) if current_budget_category in BUDGET_CATEGORIES else len(BUDGET_CATEGORIES)-1, key=f"budget_edit_category_{pid}_{selected_budget.get('budget_item_id')}")
                    edit_subcategory_options = subcategory_options(edit_budget_category)
                    current_budget_subcategory = str(selected_budget.get("subcategory") or edit_subcategory_options[0])
                    edit_budget_subcategory = st.selectbox("Subkategori item terpilih", edit_subcategory_options, index=edit_subcategory_options.index(current_budget_subcategory) if current_budget_subcategory in edit_subcategory_options else 0, key=f"budget_edit_subcategory_{pid}_{selected_budget.get('budget_item_id')}_{edit_budget_category}")
                    try:
                        due_default = date.fromisoformat(str(selected_budget.get("due_date") or date.today().isoformat())[:10])
                        has_due_default = bool(selected_budget.get("due_date"))
                    except ValueError:
                        due_default = date.today(); has_due_default = False
                    with st.form(f"budget_edit_form_{pid}_{selected_budget.get('budget_item_id')}"):
                        st.caption(f"Memperbarui: {selected_budget.get('description')} · {selected_budget.get('budget_item_id')}")
                        edit_budget_description = st.text_input("Nama item / lingkup biaya", value=str(selected_budget.get("description") or ""))
                        e1, e2 = st.columns(2)
                        with e1:
                            edit_budget_amount = st.number_input("Anggaran total item (Rp)", min_value=0, step=500_000, value=safe_int(selected_budget.get("budget_amount")))
                            edit_committed = st.number_input("Komitmen belum dibayar (Rp)", min_value=0, step=500_000, value=safe_int(selected_budget.get("committed_unpaid")))
                            edit_forecast = st.number_input("Forecast belum dikomitmen (Rp)", min_value=0, step=500_000, value=safe_int(selected_budget.get("forecast_remaining")))
                        with e2:
                            edit_vendor = st.text_input("Vendor / kontraktor", value=str(selected_budget.get("vendor") or ""))
                            edit_has_due = st.checkbox("Ada tanggal jatuh tempo", value=has_due_default)
                            edit_due_date = st.date_input("Tanggal jatuh tempo", value=due_default, disabled=not edit_has_due)
                            edit_status = st.selectbox("Status item", ["Active", "Completed", "Archived", "Cancelled"], index=["Active", "Completed", "Archived", "Cancelled"].index(selected_budget.get("status", "Active")) if selected_budget.get("status", "Active") in ["Active", "Completed", "Archived", "Cancelled"] else 0)
                        edit_budget_confirm = st.checkbox("Saya yakin perubahan item anggaran ini sudah benar.", key=f"budget_edit_confirm_{pid}_{selected_budget.get('budget_item_id')}")
                        save_budget_edit = st.form_submit_button("Simpan perubahan item anggaran")
                    if save_budget_edit and not edit_budget_confirm:
                        st.warning("Centang konfirmasi setelah memeriksa perubahan anggaran.")
                    elif save_budget_edit:
                        updated_budget = {**selected_budget, "category": edit_budget_category, "subcategory": edit_budget_subcategory, "description": edit_budget_description.strip(), "budget_amount": edit_budget_amount, "committed_unpaid": edit_committed, "forecast_remaining": edit_forecast, "vendor": edit_vendor, "due_date": edit_due_date.isoformat() if edit_has_due else "", "status": edit_status, "updated_at": iso_now()}
                        before = {k: selected_budget.get(k) for k in ["category", "subcategory", "description", "budget_amount", "committed_unpaid", "forecast_remaining", "vendor", "due_date", "status"]}
                        upsert_record("PROJECT_BUDGETS", "budget_item_id", updated_budget)
                        after = {k: updated_budget.get(k) for k in before}
                        log_event("PROJECT_BUDGET", selected_budget.get("budget_item_id"), "UPDATED", {"property_id": pid, "before": before, "after": after})
                        st.success("Item anggaran berhasil diperbarui."); cached_read.clear(); st.rerun()
        else:
            st.info("Belum ada item anggaran. Tambahkan budget per lingkup agar PFMS dapat menghitung sisa kebutuhan proyek secara lebih akurat.")

        with st.expander("Tambah item anggaran / komitmen / forecast", expanded=False):
            budget_category = st.selectbox("1. Kategori anggaran", BUDGET_CATEGORIES, key=f"budget_new_category_{pid}")
            budget_subcategory_options = subcategory_options(budget_category)
            budget_subcategory = st.selectbox("2. Subkategori", budget_subcategory_options, key=f"budget_new_subcategory_{pid}_{budget_category}")
            budget_scope_options = scope_options(budget_category, budget_subcategory)
            budget_scope_choice = st.selectbox("3. Item / lingkup anggaran", budget_scope_options, key=f"budget_new_scope_{pid}_{budget_category}_{budget_subcategory}")
            budget_scope_custom = st.text_input("Tuliskan item/lingkup lain", key=f"budget_new_scope_custom_{pid}", placeholder="Contoh: penggantian seluruh genteng dan nok") if budget_scope_choice == "Lainnya" else ""
            budget_scope_text = budget_scope_custom.strip() if budget_scope_choice == "Lainnya" else budget_scope_choice
            with st.form(f"project_budget_add_form_{pid}"):
                b1, b2 = st.columns(2)
                with b1:
                    budget_amount = st.number_input("Anggaran total item (Rp)", min_value=0, step=500_000, key=f"budget_amount_{pid}")
                    committed_unpaid = st.number_input("Komitmen yang sudah disepakati, belum dibayar (Rp)", min_value=0, step=500_000, key=f"budget_commit_{pid}")
                    forecast_remaining = st.number_input("Perkiraan biaya tersisa yang belum dikomitmen (Rp)", min_value=0, step=500_000, key=f"budget_forecast_{pid}")
                with b2:
                    budget_vendor = st.text_input("Vendor / kontraktor (opsional)", key=f"budget_vendor_{pid}")
                    budget_has_due = st.checkbox("Ada tanggal jatuh tempo", key=f"budget_has_due_{pid}")
                    budget_due_date = st.date_input("Tanggal jatuh tempo", value=date.today(), disabled=not budget_has_due, key=f"budget_due_{pid}")
                budget_confirm = st.checkbox("Saya sudah memeriksa anggaran, komitmen dan forecast yang akan disimpan.", key=f"budget_confirm_{pid}")
                add_budget = st.form_submit_button("Tambah item anggaran", type="primary", use_container_width=True)
            if add_budget:
                if not budget_confirm:
                    st.warning("Centang konfirmasi setelah memeriksa seluruh angka.")
                elif not budget_scope_text:
                    st.warning("Item/lingkup anggaran wajib dipilih atau ditulis.")
                elif budget_amount <= 0 and committed_unpaid <= 0 and forecast_remaining <= 0:
                    st.warning("Isi minimal salah satu: anggaran, komitmen, atau forecast.")
                else:
                    budget_rec = {
                        "budget_item_id": new_id("BUD"), "property_id": pid,
                        "category": budget_category, "subcategory": budget_subcategory,
                        "description": budget_scope_text, "budget_amount": budget_amount,
                        "committed_unpaid": committed_unpaid, "forecast_remaining": forecast_remaining,
                        "due_date": budget_due_date.isoformat() if budget_has_due else "", "vendor": budget_vendor, "status": "Active",
                        "updated_at": iso_now(), "payload": {"entry_source": "ACTIVE_PROPERTY_BUDGET", "item_scope": budget_scope_text},
                    }
                    upsert_record("PROJECT_BUDGETS", "budget_item_id", budget_rec)
                    log_event("PROJECT_BUDGET", budget_rec["budget_item_id"], "ADDED", {"property_id": pid, "category": budget_category, "subcategory": budget_subcategory, "item_scope": budget_scope_text})
                    for field_key in [f"budget_scope_custom_{pid}", f"budget_amount_{pid}", f"budget_commit_{pid}", f"budget_forecast_{pid}", f"budget_vendor_{pid}", f"budget_has_due_{pid}", f"budget_due_{pid}", f"budget_confirm_{pid}"]:
                        st.session_state.pop(field_key, None)
                    st.success("Item anggaran berhasil ditambahkan. Formulir dikosongkan untuk item berikutnya.")
                    cached_read.clear(); st.rerun()

        st.markdown("### 6. Milestone proyek")
        milestones = [m for m in read_table("PROJECT_MILESTONES") if m.get("property_id") == pid]
        if milestones: st.dataframe(pd.DataFrame(milestones), use_container_width=True, hide_index=True)
        with st.form(f"milestone_form_v111_{pid}"):
            m1, m2 = st.columns(2)
            with m1:
                milestone_stage = st.selectbox("Tahap milestone", PROJECT_STAGES)
                has_planned = st.checkbox("Tanggal rencana tersedia", key=f"milestone_has_planned_{pid}")
                milestone_planned_value = st.date_input("Tanggal rencana", value=date.today(), disabled=not has_planned, key=f"milestone_planned_{pid}")
            with m2:
                milestone_status = st.selectbox("Status milestone", ["Not Started", "In Progress", "Completed", "Delayed"])
                has_actual = st.checkbox("Tanggal aktual tersedia", key=f"milestone_has_actual_{pid}")
                milestone_actual_value = st.date_input("Tanggal aktual", value=date.today(), disabled=not has_actual, key=f"milestone_actual_{pid}")
            milestone_note = st.text_input("Catatan milestone", key=f"milestone_note_{pid}")
            milestone_confirm = st.checkbox("Saya sudah memeriksa tahap dan tanggal milestone.", key=f"milestone_confirm_{pid}")
            save_milestone = st.form_submit_button("Simpan milestone")
        if save_milestone and not milestone_confirm:
            st.warning("Centang konfirmasi setelah memeriksa milestone.")
        if save_milestone and milestone_confirm:
            milestone_planned = milestone_planned_value.isoformat() if has_planned else ""
            milestone_actual = milestone_actual_value.isoformat() if has_actual else ""
            rec = {"milestone_id": new_id("MIL"), "property_id": pid, "stage": milestone_stage, "status": milestone_status, "planned_date": milestone_planned, "actual_date": milestone_actual, "notes": milestone_note, "updated_at": iso_now()}
            if repo: repo.save_milestone(rec); cached_read.clear()
            else:
                milestones_local = st.session_state.local_db.setdefault("PROJECT_MILESTONES", [])
                match = next((i for i, old in enumerate(milestones_local) if str(old.get("property_id")) == str(pid) and str(old.get("stage")) == str(milestone_stage)), None)
                if match is None: milestones_local.append(rec)
                else: milestones_local[match] = {**milestones_local[match], **rec}
            payload["project_stage"] = milestone_stage
            upsert_record("PROPERTIES", "property_id", {**p, "updated_at": iso_now(), "payload": payload, "lifecycle_status": "ACTIVE"})
            log_event("PROJECT_MILESTONE", rec["milestone_id"], "SAVED", {"property_id": pid, "stage": milestone_stage, "status": milestone_status})
            for field_key in [f"milestone_has_planned_{pid}", f"milestone_planned_{pid}", f"milestone_has_actual_{pid}", f"milestone_actual_{pid}", f"milestone_note_{pid}", f"milestone_confirm_{pid}"]:
                st.session_state.pop(field_key, None)
            st.success("Milestone tersimpan. Formulir dikosongkan untuk milestone berikutnya."); st.rerun()

        st.markdown("### 7. Penjualan / closing")
        with st.form("closing_form_v109"):
            c1, c2, c3 = st.columns(3)
            with c1:
                sold_date = st.date_input("Tanggal closing", value=date.today())
                listing_start = st.date_input("Tanggal mulai listing", value=date.today())
            with c2:
                closing_price = st.number_input("Harga closing (Rp)", min_value=0, step=1_000_000)
                selling_actual = st.number_input("Biaya penjualan aktual (Rp)", min_value=0, step=250_000)
            with c3:
                total_months = st.number_input("Total holding aktual (bulan)", min_value=0.0, step=0.5)
                actual_costs_confirmed = st.checkbox("Saya memastikan seluruh biaya aktual proyek sudah dicatat.")
            closing_notes = st.text_input("Catatan closing")
            closing_confirm = st.checkbox("Saya yakin ingin menandai properti ini SOLD / CLOSED.")
            close = st.form_submit_button("Tandai SOLD / CLOSED")
        if close:
            if closing_price <= 0: st.error("Harga closing wajib diisi.")
            elif not actual_costs_confirmed: st.error("Konfirmasi kelengkapan biaya aktual diperlukan agar profit dan ROI closing tidak menyesatkan.")
            elif not closing_confirm: st.error("Centang konfirmasi sebelum mengubah lifecycle menjadi SOLD.")
            else:
                closing = {"property_id": pid, "sold_date": sold_date.isoformat(), "listing_start_date": listing_start.isoformat(), "closing_price": closing_price, "selling_cost_actual": selling_actual, "total_holding_months": total_months, "notes": closing_notes, "updated_at": iso_now(), "payload": {"closing_price": closing_price}}
                upsert_record("SALES_CLOSING", "property_id", closing)
                payload["project_stage"] = "Sold / Closed"
                upsert_record("PROPERTIES", "property_id", {**p, "updated_at": iso_now(), "lifecycle_status": "SOLD", "decision_status": p.get("decision_status", "GO"), "payload": payload})
                log_event("PROPERTY", pid, "SOLD", closing); st.success("Properti masuk Proyek Selesai."); st.rerun()

# ============================ PAGE 6: CLOSED ===============================
elif page == "Closed Projects & Track Record":
    st.markdown("<div class='hero'><h1>Proyek Selesai & Hasil Investasi</h1><p>Evaluasi harga jual, biaya aktual, laba, dan ROI yang benar-benar terealisasi.</p></div>", unsafe_allow_html=True)
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
    st.markdown("<div class='hero'><h1>Database & Riwayat</h1><p>Telusuri seluruh prospek, analisis, status proyek, dan perubahan yang pernah dicatat.</p></div>", unsafe_allow_html=True)
    props = list_properties()
    if props:
        df = pd.DataFrame([{k:p.get(k) for k in ["property_id","lot_code","name","address","auction_date","auction_limit","decision_status","lifecycle_status","updated_at"]} for p in props])
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={"auction_limit": st.column_config.NumberColumn(format="Rp %.0f")})
        property_options = {
            f"{p.get('name') or 'Tanpa nama'} · {p.get('lot_code') or 'Tanpa kode lot'} · {p.get('address') or 'Alamat belum diisi'} · ID {p.get('property_id')}": p
            for p in props
        }
        selected_label = st.selectbox("Pilih properti (nama, lokasi, kode lot)", list(property_options.keys()))
        selected = property_options[selected_label]
        selection = selected.get("property_id")
        with st.expander("Detail objek / lifecycle", expanded=True): st.json({**{k:v for k,v in selected.items() if k != "payload"}, "payload": record_payload(selected)})
        if selected.get("lifecycle_status") not in {"WON", "ACTIVE", "SOLD"}:
            st.markdown("#### Catat hasil lelang")
            st.caption("Jika objek berhasil Anda menangkan, ubah lifecycle menjadi WON. Snapshot analisis, comparable, dan keputusan sebelum lelang tetap dipertahankan. Objek otomatis muncul di Properti Aktif untuk pencatatan pelunasan, penguasaan, renovasi, dan biaya aktual.")
            existing_payload = record_payload(selected)
            existing_win = existing_payload.get("win_details", {}) if isinstance(existing_payload.get("win_details"), dict) else {}
            try: default_win_date = date.fromisoformat(str(existing_win.get("win_date") or date.today().isoformat())[:10])
            except ValueError: default_win_date = date.today()
            with st.form(f"update_opportunity_status_{selection}"):
                new_decision = st.selectbox("Status keputusan analisis", DECISION_STATUSES, index=DECISION_STATUSES.index(selected.get("decision_status", "HOLD")) if selected.get("decision_status") in DECISION_STATUSES else 0)
                editable_lifecycle = [x for x in LIFECYCLE_STATUSES if x not in {"SOLD"}]
                new_lifecycle = st.selectbox("Status perjalanan properti", editable_lifecycle, index=editable_lifecycle.index(selected.get("lifecycle_status", "PROSPECT")) if selected.get("lifecycle_status") in editable_lifecycle else 0, help="WON = berhasil menang lelang. ACTIVE = proyek sudah masuk tahap pengelolaan/penyelesaian.")
                mark_win_price = st.number_input("Harga menang / harga perolehan (Rp)", min_value=0, step=1_000_000, value=safe_int(existing_win.get("win_price", selected.get("auction_limit", 0))))
                mark_win_date = st.date_input("Tanggal menang", value=default_win_date)
                mark_win_deposit = st.number_input("Uang jaminan yang menjadi bagian harga menang (Rp)", min_value=0, step=500_000, value=safe_int(existing_win.get("deposit_amount", 0)))
                update_status = st.form_submit_button("Simpan status dan data kemenangan", type="primary")
            if update_status:
                if new_lifecycle in {"WON", "ACTIVE"}:
                    try:
                        updated_record = mark_property_won(selected, {"win_price": mark_win_price, "win_date": mark_win_date.isoformat(), "deposit_amount": mark_win_deposit or None})
                        updated_record["decision_status"] = new_decision
                        if new_lifecycle == "ACTIVE": updated_record["lifecycle_status"] = "ACTIVE"
                        upsert_record("PROPERTIES", "property_id", updated_record)
                        log_event("PROPERTY", selection, "AUCTION_WON", {"decision": new_decision, "lifecycle": updated_record["lifecycle_status"], "win_price": mark_win_price, "win_date": mark_win_date.isoformat()})
                        st.success("Objek berhasil dipindahkan ke portofolio proyek. Buka Properti Aktif untuk mencatat realisasi dan anggaran.")
                        cached_read.clear(); st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                else:
                    upsert_record("PROPERTIES", "property_id", {**selected, "decision_status": new_decision, "lifecycle_status": new_lifecycle, "updated_at": iso_now()})
                    log_event("PROPERTY", selection, "STATUS_CHANGED", {"decision": new_decision, "lifecycle": new_lifecycle})
                    st.success("Status diperbarui."); cached_read.clear(); st.rerun()
        elif selected.get("lifecycle_status") in {"WON", "ACTIVE"}:
            st.info("Objek sudah menjadi proyek berjalan. Status WON menandakan kemenangan lelang; setelah masuk pengelolaan/renovasi, status akan menjadi ACTIVE. Kelola keuangan dan tahap proyek melalui menu Properti Aktif.")
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
    st.markdown("<div class='hero'><h1>Pengaturan Sistem & Asumsi</h1><p>Atur asumsi biaya dan ambang keputusan. Perubahan di sini dapat memengaruhi analisis berikutnya.</p></div>", unsafe_allow_html=True)
    st.caption("Tarif dan biaya adalah asumsi underwriting yang harus diverifikasi untuk setiap wilayah dan transaksi.")
    rules = get_rules()
    with st.form("rules_form"):
        st.subheader("Biaya akuisisi dan asumsi pajak daerah")
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
        st.subheader("Biaya penjualan")
        c1,c2,c3,c4 = st.columns(4)
        with c1: pph = st.number_input("PPh Final (%)", min_value=0.0, max_value=20.0, value=to_float(rules["seller_final_tax_pct"]))
        with c2: agent = st.number_input("Komisi agen (%)", min_value=0.0, max_value=20.0, value=to_float(rules["seller_agent_pct"]))
        with c3: ajb = st.number_input("Porsi AJB/PPAT penjual (%)", min_value=0.0, max_value=2.0, value=to_float(rules["seller_ajb_ppat_pct"]))
        with c4: misc = st.number_input("Misc selling cost (Rp)", min_value=0, step=250_000, value=safe_int(rules["seller_misc_fixed"]))
        st.subheader("Asumsi proyek dan pasar")
        c1,c2,c3 = st.columns(3)
        with c1: holding = st.number_input("Holding cost / bulan (Rp)", min_value=0, step=250_000, value=safe_int(rules["monthly_holding_cost"]))
        with c2: contingency = st.number_input("Contingency renovasi (%)", min_value=0.0, max_value=100.0, value=to_float(rules["renovation_contingency_pct"]))
        with c3: negotiation = st.number_input("Negotiation discount (%)", min_value=0.0, max_value=50.0, value=to_float(rules["negotiation_discount_pct"]))
        c1,c2,c3 = st.columns(3)
        with c1: quick_sale = st.number_input("Quick-sale discount (%)", min_value=0.0, max_value=50.0, value=to_float(rules["quick_sale_discount_pct"]))
        with c2: min_roi = st.number_input("Minimum ROI seluruh proyek (%)", min_value=0.0, max_value=200.0, value=to_float(rules["minimum_roi_pct"]))
        with c3: mid_roi = st.number_input("Target ROI batas tengah (%)", min_value=0.0, max_value=300.0, value=to_float(rules["mid_roi_pct"]))
        njop_market_weight = st.number_input("Bobot referensi NJOP terkalibrasi (%)", min_value=0.0, max_value=25.0, value=to_float(rules.get("njop_market_weight_pct", 10.0)), help="Hanya aktif bila minimal 3 comparable memiliki data harga dan NJOP pembanding. NJOP tidak pernah diperlakukan sebagai harga pasar langsung.")
        save_rules = st.form_submit_button("Simpan asumsi", use_container_width=True)
    if save_rules:
        updated = {"buyer_auction_fee_pct":buyer_fee,"bphtb_rate_pct":bphtb_rate,"npoptkp":npoptkp,"bphtb_basis_mode":basis_mode,"bpn_pnbp_cost":bpn,"roya_cost":roya,"other_acquisition_admin":other_admin,"acquisition_notary_ppat_fee":notary_buy,"seller_final_tax_pct":pph,"seller_agent_pct":agent,"seller_ajb_ppat_pct":ajb,"seller_misc_fixed":misc,"monthly_holding_cost":holding,"renovation_contingency_pct":contingency,"negotiation_discount_pct":negotiation,"quick_sale_discount_pct":quick_sale,"minimum_roi_pct":min_roi,"mid_roi_pct":mid_roi,"njop_market_weight_pct":njop_market_weight}
        st.session_state.rules_local.update(updated)
        upsert_record("RULES_CONFIG", "rule_key", {"rule_key":"GLOBAL","value":updated,"updated_at":iso_now(),"source_note":"User-configured assumptions; verify by property jurisdiction/transaction."})
        log_event("RULES", "GLOBAL", "UPDATED", updated); st.success("Rules tersimpan."); st.rerun()
    st.markdown("### Konfigurasi API")
    st.code(f"GEMINI_MODEL = {GEMINI_MODEL}\nGEMINI_API_KEY = {'configured' if GEMINI_KEY else 'not configured'}\nSPREADSHEET_ID = {'configured' if spreadsheet_id else 'not configured'}", language="text")
    st.markdown("Gemini 3.5 Flash-Lite Free Tier tidak menyediakan Google Search grounding. V1 menggunakan comparable manual; jangan kirim data pribadi sensitif yang tidak diperlukan.")
