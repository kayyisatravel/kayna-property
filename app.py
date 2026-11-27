from __future__ import annotations
import hashlib, hmac, json, os, uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd
import streamlit as st

from config import APP_NAME, APP_VERSION, DEFAULT_GEMINI_MODEL, DEFAULT_RULES, OCCUPANCY_DEFAULTS, DECISION_STATUSES, LIFECYCLE_STATUSES, PROJECT_STAGES, GOOGLE_SHEETS_CACHE_TTL
from core.utils import idr, pct, safe_json, parse_json, new_id, iso_now, to_float
from core.underwriting import run_underwriting
from core.liquidity import compute_liquidity
from core.lifecycle import actual_project_summary, mark_property_won
from core.project_ledger import summarize_project_ledger
from core.project_alerts import assess_project_alerts
from core.dashboard import build_dashboard_view
from core.renovation_schedule import estimate_renovation_duration
from core.project_progress import budget_payload, calculate_project_work_progress
from core.auction_dates import apply_extracted_auction_dates, derive_payment_deadline
from core.decision_engine import bid_reference_status
from core.auction_outcomes import OUTCOME_STATUSES, PRICE_TYPES, SOURCE_GRADES, build_auction_outcome_record, implied_discount_vs_limit
from core.project_budget_seed import build_opening_budget_from_analysis
from core.ledger_transactions import reconcile_budget_payment_change
from core.project_form_options import ACTUAL_CATEGORIES, BUDGET_CATEGORIES, subcategory_options, scope_options
from core.onboarding import build_project_onboarding_records
from core.market_engine import assess_comparables
from core.form_state import form_state_from_input_data
from core.analysis_workflow import analysis_step1_missing, count_valid_comparables, persist_analysis_step_state, restore_analysis_step_state
from core.review_state import sync_review_confirmation
from core.user_boq import parse_user_boq_table
from core.renovation_engine import CATEGORIES as RENOVATION_CATEGORIES, rab_item_is_in_scope, infer_renovation_category, summarize_rab_totals, rab_row_subtotals, summarize_rab_scope_totals
from core.calculator import calculate_project
from services.gemini_parser import extract_auction_document, parse_comparable_narrative, review_investment, review_portfolio, estimate_renovation_rab, assess_market_with_ai, file_sha256
from services.comparable_importer import parse_comparable_paste
from storage.gsheets_db import GoogleSheetsDB, SCHEMA
from storage.drive_storage import upload_file_to_drive
from core.renovation_pricing import PRICE_CATALOG_VERSION, PRICE_CATALOG_BASIS, PRICE_CATALOG_REFERENCES, PRICE_CATALOG_ANCHORS
from reports.report_builder import build_analysis_markdown, build_analysis_docx, property_filename
from reports.portfolio_context import build_portfolio_report_context

st.set_page_config(page_title=APP_NAME, page_icon="🏠", layout="wide", initial_sidebar_state="expanded")

def jakarta_today() -> date:
    """Return local business date independent of the Streamlit server timezone."""
    return datetime.now(ZoneInfo("Asia/Jakarta")).date()


def as_date(value: Any, fallback: date | None = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return fallback or date.today()


def _mark_date_picker_edited(state_key: str) -> None:
    st.session_state[f"{state_key}_user_edited"] = True


def prefilled_editable_date_picker(label: str, value: Any, key: str, *, help_text: str = "") -> str:
    """Date picker prefilled from source documents, without a redundant checkbox.

    When the source date is unavailable, today's date is only a visual starting
    point and is NOT persisted until the user changes the date.
    """
    existing = str(value or "").strip()
    widget_key = f"{key}_picker"
    edited_key = f"{key}_user_edited"
    if widget_key not in st.session_state:
        st.session_state[widget_key] = as_date(existing) if existing else jakarta_today()
        st.session_state[edited_key] = False
    selected = st.date_input(
        label, key=widget_key, on_change=_mark_date_picker_edited, args=(key,), help=help_text or None
    )
    if existing or bool(st.session_state.get(edited_key)):
        return selected.isoformat() if isinstance(selected, (date, datetime)) else ""
    return ""


def optional_date_picker(label: str, value: Any, key: str) -> str:
    """Render an optional date picker; blank remains genuinely blank."""
    widget_key = f"{key}_optional_picker"
    parsed = as_date(value) if value not in (None, "") else None
    if widget_key not in st.session_state:
        st.session_state[widget_key] = parsed
    selected = st.date_input(label, value=st.session_state.get(widget_key), key=widget_key, format="DD/MM/YYYY")
    return selected.isoformat() if isinstance(selected, (date, datetime)) else ""

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
section[data-testid="stSidebar"] {
    border-right: 1px solid rgba(255, 255, 255, 0.12);
    background: linear-gradient(160deg, #10243E 0%, #173B5B 62%, #0F766E 100%) !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    padding: .32rem .45rem;
    border-radius: 8px;
    font-weight: 550;
    transition: background-color 0.2s ease;
}
.kayna-sidebar-brand {
    padding: 1rem .9rem;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.16);
    backdrop-filter: blur(8px);
    color: #FFF;
    margin: .15rem 0 .8rem;
    box-shadow: 0 8px 22px rgba(10, 22, 38, 0.18);
}
.kayna-sidebar-brand .kp-mark{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border:1px solid rgba(255,255,255,.45);border-radius:9px;font-weight:850;letter-spacing:.04em;margin-bottom:.6rem}
.kayna-sidebar-brand strong{display:block;color:#FFF;font-size:.92rem;letter-spacing:.035em;line-height:1.35}
.kayna-sidebar-brand small{display:block;color:#D9E5EF;margin-top:.35rem;font-size:.69rem;letter-spacing:.08em}
.kayna-pagebar{display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.48rem .8rem;margin:0 0 .9rem;border:1px solid #E2E8F0;border-radius:10px;background:#FFFFFF;color:#526174;font-size:.76rem}
.kayna-pagebar b{color:#172B4D;letter-spacing:.08em}
.kayna-pagebar span:last-child{font-weight:650;color:#0F766E}
.kayna-dashboard-hero{position:relative;overflow:hidden;padding:2rem 2.15rem;border-radius:22px;margin:.15rem 0 1.1rem;background:linear-gradient(118deg,#10243E 0%,#173B5B 58%,#0F766E 100%);box-shadow:0 12px 30px rgba(16,36,62,.14);color:#FFFFFF}
.kayna-dashboard-hero:after{content:"";position:absolute;right:-56px;top:-110px;width:290px;height:290px;border:1px solid rgba(255,255,255,.13);border-radius:50%;box-shadow:0 0 0 34px rgba(255,255,255,.035),0 0 0 70px rgba(255,255,255,.025)}
.kayna-kicker{font-size:.76rem;letter-spacing:.19em;font-weight:800;color:#B9D8D5;margin-bottom:.65rem}
.kayna-dashboard-hero h1{font-size:2.05rem;line-height:1.15;color:#FFFFFF;margin:0 0 .45rem;font-weight:800}
.kayna-dashboard-hero p{font-size:.98rem;color:#D7E4EF;margin:0 0 .95rem;letter-spacing:.02em}
.kayna-hero-foot{font-size:.88rem;color:#F2F7FA;max-width:780px;line-height:1.55}
.kayna-summary-strip{display:flex;flex-wrap:wrap;gap:1.3rem;padding:.85rem 1rem;border:1px solid #DFE7EF;border-radius:13px;background:#F6F8FB;color:#334155;margin:.35rem 0 1.25rem;font-size:.86rem}
.kayna-summary-strip b{color:#172B4D}
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
        {"Kategori": "Renovation + Contingency + Hidden Reserve", "Anggaran": to_float(estimate.get("renovation_cost")) + to_float(estimate.get("renovation_contingency")) + to_float(estimate.get("hidden_condition_reserve")), "Aktual": renovation_actual},
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
else:
    for _tab_name in SCHEMA:
        st.session_state.local_db.setdefault(_tab_name, [])


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


def seed_opening_budget_for_won_property(property_record: dict[str, Any], win_price: float) -> dict[str, Any]:
    """Seed an active-project baseline from the preserved analysis snapshot.

    Idempotent by stable item IDs. It refuses to merge automatically into
    pre-existing manual/onboarding budgets because doing so could double-count
    costs. Existing analysis history and its original decision are preserved.
    """
    pid = str(property_record.get("property_id") or "")
    payload = record_payload(property_record)
    latest = payload.get("latest_analysis") if isinstance(payload.get("latest_analysis"), dict) else None
    if not latest:
        return {"seeded": 0, "reason": "Tidak ada snapshot underwriting tersimpan; gunakan input Project Onboarding/budget manual."}
    existing_rows = [x for x in read_table("PROJECT_BUDGETS") if str(x.get("property_id")) == pid]
    existing_baseline = [
        x for x in existing_rows
        if str((x.get("payload") or {}).get("entry_source", "") if isinstance(x.get("payload"), dict) else parse_json(x.get("payload_json"), {}).get("entry_source", "")) == "PRE_BID_ANALYSIS_BASELINE"
    ]
    if existing_rows and not existing_baseline:
        return {"seeded": 0, "reason": "Sudah ada anggaran manual/onboarding. Baseline analisis tidak ditambahkan otomatis agar tidak menggandakan anggaran; lakukan rekonsiliasi manual."}

    baseline = build_opening_budget_from_analysis(latest, pid, win_price)
    if not baseline.get("rows"):
        return {"seeded": 0, "reason": baseline.get("reason", "Baseline tidak dapat dibuat.")}
    existing_ids = {str(x.get("budget_item_id")) for x in existing_rows}
    created = 0
    for row in baseline["rows"]:
        if str(row.get("budget_item_id")) in existing_ids:
            continue
        upsert_record("PROJECT_BUDGETS", "budget_item_id", row)
        created += 1
    payload["opening_budget_baseline"] = {
        "analysis_id": baseline.get("analysis_id"),
        "seeded_at": iso_now(),
        "source": "PRE_BID_ANALYSIS",
        "baseline_project_budget_total": baseline.get("seeded_project_budget_total"),
        "calculator_capital_before_sale": baseline.get("calculator_capital_before_sale"),
        "baseline_complete": baseline.get("baseline_complete"),
        "baseline_warnings": baseline.get("baseline_warnings", []),
        "pending_pricing_items": baseline.get("pending_pricing_items", []),
        "pre_bid_capital_at_limit": baseline.get("pre_bid_capital_at_limit"),
        "pre_bid_cash_need_at_limit": baseline.get("pre_bid_cash_need_at_limit"),
        "winning_price_used_for_baseline": baseline.get("winning_price"),
        "risk_reserves_not_budgeted": baseline.get("risk_reserves_not_budgeted", {}),
        "pre_bid_decision_status": baseline.get("pre_bid_decision_status"),
        "pre_bid_cash_available": baseline.get("pre_bid_cash_available"),
    }
    upsert_record("PROPERTIES", "property_id", {**property_record, "updated_at": iso_now(), "payload": payload})
    log_event("PROJECT_BUDGET", pid, "OPENING_BASELINE_SEEDED", {"analysis_id": baseline.get("analysis_id"), "created_rows": created, "baseline_complete": baseline.get("baseline_complete"), "pending_pricing_items": baseline.get("pending_pricing_items", [])})
    return {"seeded": created, **baseline}

# ----------------------------- Session defaults ----------------------------
if "rules_local" not in st.session_state: st.session_state.rules_local = dict(DEFAULT_RULES)
if "current_analysis" not in st.session_state: st.session_state.current_analysis = None
if "current_inputs" not in st.session_state: st.session_state.current_inputs = None
if "loaded_property_id" not in st.session_state: st.session_state.loaded_property_id = ""
if "parse_info" not in st.session_state: st.session_state.parse_info = None
if "ai_review" not in st.session_state: st.session_state.ai_review = None


def get_rules() -> dict[str, Any]:
    rules = {**DEFAULT_RULES, **dict(st.session_state.rules_local)}
    rows = read_table("RULES_CONFIG")
    stored_global_rules: dict[str, Any] = {}
    for row in rows:
        try:
            value = row.get("value") if "value" in row else json.loads(row.get("value_json", "null"))
            if row.get("rule_key") == "GLOBAL" and isinstance(value, dict):
                stored_global_rules = dict(value)
                rules.update(value)
            elif row.get("rule_key"): rules[row["rule_key"]] = value
        except Exception: pass
    # One-time migration: only untouched V1.0.21 defaults (25% / 35%) are
    # moved to the newly agreed Kayna flip policy (20% / 30%). Custom values
    # are preserved. New profit/time gates are additive and user-editable.
    if stored_global_rules.get("investment_policy_version") != "KAYNA_FLIP_POLICY_V1":
        if to_float(rules.get("minimum_roi_pct"), 20) == 25 and to_float(rules.get("mid_roi_pct"), 30) == 35:
            rules["minimum_roi_pct"] = 20.0
            rules["mid_roi_pct"] = 30.0
        rules.setdefault("minimum_net_profit", 50_000_000)
        rules.setdefault("target_holding_days", 90)
        rules.setdefault("maximum_holding_days", 180)
        rules["investment_policy_version"] = "KAYNA_FLIP_POLICY_V1"
        st.session_state.rules_local.update({k: rules[k] for k in ["minimum_roi_pct", "mid_roi_pct", "minimum_net_profit", "target_holding_days", "maximum_holding_days", "investment_policy_version"]})
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


def build_memo_portfolio_context(current_property_id: str = "") -> dict[str, Any]:
    """Build a compact portfolio appendix using only cached Google Sheets reads."""
    return build_portfolio_report_context(
        list_properties(),
        read_table("COST_ACTUALS"),
        read_table("PROJECT_BUDGETS"),
        read_table("PROJECT_MILESTONES"),
        read_table("SALES_CLOSING"),
        as_of=jakarta_today().isoformat(),
    )

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


# Action widgets are transient controls, not form values. The step-state helper
# persists `na_*` values between steps, so explicitly keep button states out of
# that payload. Restoring a saved st.button key can raise
# StreamlitValueAssignmentNotAllowedError when the button is rendered again.
_ANALYSIS_ACTION_WIDGET_KEYS = frozenset({
    "na_go_step_2",
    "na_market_ai_review",
    "na_generate_rab",
    "na_add_risk_preset",
    "na_back_step_1",
    "na_go_step_3",
    "na_apply_market_ai",
    "na_fill_capture_dates",
    "na_confirm_url_scope",
    "na_back_step_2",
    "na_go_step_4",
    "na_back_step_3",
    "na_run_underwriting",
})


def _strip_analysis_action_widget_state() -> None:
    """Remove transient button values from the saved multi-step form payload."""
    saved = st.session_state.get("_na_persisted_form_state")
    if isinstance(saved, dict):
        for widget_key in _ANALYSIS_ACTION_WIDGET_KEYS:
            saved.pop(widget_key, None)


def _persist_and_go_analysis_step(step: int) -> None:
    """Save current step values in session state, then move to the next step.

    Survey photos are uploaded by a Step-2 widget. Streamlit may discard widget
    state when that widget is not rendered on the next rerun, so copy the files
    into a non-widget session-state payload before leaving Step 2. This keeps
    the existing Step-2 uploader intact while allowing Step 4/RAB and the save
    routine to access the same survey photos safely. Button states are excluded
    because they are transient actions and cannot be restored as form values.
    """
    if safe_int(step, 1) >= 3:
        survey_photos = st.session_state.get("na_survey_photos") or []
        if survey_photos:
            st.session_state["na_survey_photo_payloads"] = [
                {
                    "bytes": photo.getvalue(),
                    "mime_type": photo.type or "image/jpeg",
                    "name": photo.name,
                }
                for photo in survey_photos
            ]
        elif "na_survey_photo_payloads" not in st.session_state:
            st.session_state["na_survey_photo_payloads"] = []
    persist_analysis_step_state(st.session_state, step)
    _strip_analysis_action_widget_state()


def _get_survey_photo_payloads() -> list[dict[str, Any]]:
    """Return persisted survey-photo payloads without depending on Step-2 widget scope."""
    return list(st.session_state.get("na_survey_photo_payloads") or [])


def _restore_analysis_form_state() -> None:
    # Clean any action-button values left by older app sessions before the
    # generic form-state restoration gets a chance to rehydrate them.
    _strip_analysis_action_widget_state()
    restore_analysis_step_state(st.session_state)
    _strip_analysis_action_widget_state()


def _indonesian_date_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Belum dapat dihitung"
    try:
        d = date.fromisoformat(raw[:10])
        months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        return f"{d.day} {months[d.month - 1]} {d.year}"
    except ValueError:
        return raw


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
st.sidebar.markdown("<div class='kayna-sidebar-brand'><span class='kp-mark'>KP</span><strong>KAYNA PROPERTY MANAGEMENT SYSTEM</strong><small>INVESTMENT · AUCTION · PROJECT CONTROL</small></div>", unsafe_allow_html=True)
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
    "📊 Explorer & hasil lelang": "Market & Auction Data",
    "🏘️ Properti aktif": "Active Properties",
    "✅ Proyek selesai & hasil": "Closed Projects & Track Record",
    "🗂️ Database & riwayat": "Database & History",
    "⚙️ Pengaturan sistem": "Settings & Rules",
}
selected_page_label = st.sidebar.radio("MENU UTAMA", list(page_labels.keys()))
page = page_labels[selected_page_label]
st.markdown(f"<div class='kayna-pagebar'><b>KAYNA PROPERTY MANAGEMENT SYSTEM</b><span>{selected_page_label}</span></div>", unsafe_allow_html=True)
if st.sidebar.button("↻ Refresh Data", use_container_width=True):
    cached_read.clear()
    st.rerun()
st.sidebar.markdown("---")
st.sidebar.caption("Analisis terukur · Risiko terlihat · Keputusan dapat diaudit")

# ============================ PAGE 1: DASHBOARD ============================
if page == "Executive Dashboard":
    st.markdown("""
    <div class='kayna-dashboard-hero'>
      <div class='kayna-kicker'>KAYNA PROPERTY MANAGEMENT SYSTEM</div>
      <h1>Portfolio Command Center</h1>
      <p>Investment intelligence · Auction pipeline · Project control · Realized performance</p>
      <div class='kayna-hero-foot'>Pusat kendali peluang lelang, kesiapan modal, pekerjaan aktif, tenggat, dan hasil investasi Kayna Property.</div>
    </div>
    """, unsafe_allow_html=True)
    properties = list_properties()
    analyses = list_analyses()
    cash_profile, events, liq = get_cash_data()
    actual_rows = read_table("COST_ACTUALS")
    budget_rows = read_table("PROJECT_BUDGETS")
    closing_rows = read_table("SALES_CLOSING")
    milestone_rows = read_table("PROJECT_MILESTONES")
    dashboard = build_dashboard_view(
        properties, analyses, actual_rows, budget_rows, closing_rows,
        today=jakarta_today(), milestone_rows=milestone_rows,
    )
    summary = dashboard["summary"]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kas siap investasi", idr(liq["cash_available_for_new_project"]), help="Kas aktual dikurangi pengeluaran terkonfirmasi, komitmen aktif, dan cadangan likuiditas.")
    k2.metric("Agenda lelang / jaminan 60 hari", summary["upcoming_auction_events"], help="Jumlah tenggat setor jaminan dan tanggal lelang yang akan datang.")
    k3.metric("Proyek aktif", summary["active_projects"])
    k4.metric("Profit proyek terealisasi", idr(summary["realized_profit"]), help="Akumulasi profit aktual dari proyek berstatus SOLD dengan data closing.")
    st.markdown(
        f"<div class='kayna-summary-strip'><span><b>{summary['prospects']}</b> peluang tersimpan</span>"
        f"<span><b>{summary['sold_projects']}</b> proyek selesai</span>"
        f"<span><b>{summary['analysis_count']}</b> snapshot analisis</span>"
        f"<span><b>{idr(summary['active_actual_paid'])}</b> pengeluaran aktual proyek aktif</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Prioritas dan agenda")
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("**Tindakan yang perlu diperhatikan**")
        if dashboard["project_alerts"]:
            for alert in dashboard["project_alerts"][:8]:
                msg = f"**{alert.get('property', 'Proyek')}** · {alert.get('title', 'Peringatan proyek')}\n\n{alert.get('action', '')}"
                if alert.get("severity") == "critical":
                    st.error(msg)
                elif alert.get("severity") == "warning":
                    st.warning(msg)
                else:
                    st.info(msg)
        else:
            st.success("Belum ada target penjualan atau anggaran proyek yang memerlukan tindakan segera berdasarkan data yang tercatat.")
    with right:
        st.markdown("**Jadwal lelang dan batas setor terdekat**")
        if dashboard["auction_events"]:
            agenda_rows = [{
                "Tanggal": fmt_date(x["date"]), "Agenda": x["event"],
                "Properti": x["property"], "Kode lot": x["lot_code"] or "—",
                "Waktu": x["urgency"],
            } for x in dashboard["auction_events"]]
            st.dataframe(pd.DataFrame(agenda_rows), use_container_width=True, hide_index=True, height=300)
        else:
            st.info("Belum ada jadwal lelang atau batas setor jaminan dalam 60 hari ke depan pada database.")

    st.markdown("### Kinerja proyek yang sedang dikelola")
    if dashboard["active_projects"]:
        project_rows = [{
            "Properti": x["property"], "Tahap": x["stage"],
            "Progres fisik (%)": round(x["progress_pct"], 1) if x.get("progress_pct") is not None else None,
            "Cakupan status (%)": round(x["progress_coverage_pct"], 1),
            "Aktual dibayar": x["actual_paid"], "Komitmen": x["commitments"],
            "Forecast tersisa": x["forecast"], "Proyeksi biaya selesai": x["projected_total"],
            "Budget proyek": x["budget_total"] or None,
            "Penggunaan budget (%)": round(x["budget_usage_pct"], 1) if x["budget_usage_pct"] is not None else None,
            "Target jual": fmt_date(x["target_sale_date"]) if x["target_sale_date"] else "Belum ditetapkan",
        } for x in dashboard["active_projects"]]
        project_df = pd.DataFrame(project_rows)
        st.dataframe(project_df, use_container_width=True, hide_index=True, column_config={
            "Aktual dibayar": st.column_config.NumberColumn(format="Rp %.0f"),
            "Komitmen": st.column_config.NumberColumn(format="Rp %.0f"),
            "Forecast tersisa": st.column_config.NumberColumn(format="Rp %.0f"),
            "Proyeksi biaya selesai": st.column_config.NumberColumn(format="Rp %.0f"),
            "Budget proyek": st.column_config.NumberColumn(format="Rp %.0f"),
            "Penggunaan budget (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "Progres fisik (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "Cakupan status (%)": st.column_config.NumberColumn(format="%.1f%%"),
        })
    else:
        st.info("Belum ada proyek aktif. Properti yang dimenangkan akan muncul di sini setelah dipindahkan ke lifecycle WON atau ACTIVE.")

    st.markdown("### Distribusi keputusan underwriting")
    if dashboard["decision_distribution"]:
        dist_col, detail_col = st.columns([1, 1.25])
        with dist_col:
            decision_series = pd.Series(dashboard["decision_distribution"], name="Jumlah snapshot")
            st.bar_chart(decision_series)
        with detail_col:
            dist_rows = [{"Status keputusan": key, "Jumlah": value} for key, value in sorted(dashboard["decision_distribution"].items())]
            st.dataframe(pd.DataFrame(dist_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Snapshot analisis belum tersedia. Mulai dari menu Analisis Objek Lelang untuk membangun pipeline peluang.")
    st.caption("Dashboard menggunakan data Google Sheets yang sudah di-cache oleh aplikasi. Filter, tabel, dan perhitungan ringkasan tidak memanggil Gemini dan tidak menambah worksheet baru.")

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

        Gunakan tombol di bagian bawah setiap langkah untuk melanjutkan. Tombol **Analisa / Update Data** muncul pada langkah terakhir setelah seluruh data wajib terisi.
        """)
    if "na_analysis_step" not in st.session_state:
        st.session_state.na_analysis_step = 1
    st.markdown("**Alur analisis bertahap** · Selesaikan data wajib pada setiap langkah sebelum melanjutkan.")
    st.caption("Data tiap langkah dipertahankan sementara di sesi aplikasi saat Anda berpindah langkah. Penyimpanan permanen ke Google Sheets dilakukan setelah Anda menjalankan Analisa / Update Data di langkah terakhir.")
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
            st.session_state["_na_persisted_form_state"] = {}
            st.session_state["na_analysis_step"] = 1
            st.session_state.pop("na_rights_expiry_optional_picker", None)
            st.session_state.loaded_property_id = ""
            st.session_state.current_analysis = None
            st.session_state.current_inputs = None
            for date_key in ("na_auction_date", "na_deposit_deadline"):
                st.session_state.pop(f"{date_key}_picker", None)
                st.session_state[f"{date_key}_user_edited"] = False
            st.session_state.pop("na_rights_expiry_optional_picker", None)
            st.session_state.parse_info = None
            st.session_state.ai_review = None
            st.success("Form dibersihkan. Siap membuat analisis objek baru.")
            st.rerun()
        if pid:
            st.session_state["_na_persisted_form_state"] = {}
            st.session_state["na_analysis_step"] = 1
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
            for date_key in ("na_auction_date", "na_deposit_deadline"):
                st.session_state.pop(f"{date_key}_picker", None)
                st.session_state[f"{date_key}_user_edited"] = False
            st.session_state.pop("na_rights_expiry_optional_picker", None)
            st.session_state.na_last_occupancy = mapping.get("na_survey_status", "Belum Survei")
            st.session_state.na_risk_reviewed = bool(data.get("risk_reviewed", latest_saved.get("risk_reviewed", False)))
            comparable_columns = ["name", "address", "latitude", "longitude", "distance_m", "market_segment", "price", "njop", "land_area", "building_area", "bedrooms", "bathrooms", "condition", "condition_detail", "access", "access_detail", "price_type", "certificate", "orientation", "electricity_watt", "water_source", "source_platforms", "source_evidence", "source_url", "source_url_scope", "listing_date", "date_found", "date_found_basis", "notes", "adjustment_pct", "ai_adjustment_rationale", "ai_exclude_from_primary"]
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
            renovation_columns = ["item_code", "subcategory", "work_item", "quantity_low", "quantity", "quantity_high", "quantity_basis", "unit", "unit_cost_low", "unit_cost", "unit_cost_high", "price_source", "priority", "evidence_basis", "confidence", "notes"]
            loaded_reno = data.get("costs", {}).get("renovation_items", [])
            reno_frame = pd.DataFrame(loaded_reno) if loaded_reno else pd.DataFrame([{c: None for c in renovation_columns} for _ in range(4)])
            for column in renovation_columns:
                if column not in reno_frame.columns:
                    reno_frame[column] = None
            st.session_state.na_renovation_items_editor = reno_frame[renovation_columns]
            st.session_state.na_rab_estimate = data.get("costs", {}).get("renovation_ai_estimate")
            st.session_state.na_risk_reviewed = bool(data.get("risk_reviewed", False))
            for widget_key in ["na_comparables_editor_widget", "na_risk_editor_widget", "na_renovation_items_widget", "na_risk_editor_widget_v103", "na_renovation_items_widget_v103", "na_renovation_items_widget_v104"]:
                if widget_key in st.session_state: del st.session_state[widget_key]
            st.session_state.loaded_property_id = pid
            st.success("Data objek dimuat. Silakan koreksi dan analisis ulang.")
            st.rerun()

    _restore_analysis_form_state()
    uploaded = st.file_uploader("Upload pengumuman lelang (PDF, PNG, JPG, WEBP)", type=["pdf", "png", "jpg", "jpeg", "webp"], key="na_document")
    if st.button("Parse dengan Gemini AI", type="secondary", disabled=uploaded is None):
        try:
            mime = uploaded.type or "application/octet-stream"
            raw_document = uploaded.getvalue()
            digest = file_sha256(raw_document)
            cached_document = next((d for d in read_table("DOCUMENTS") if d.get("document_hash") == digest and d.get("extraction_json")), None)
            cached_extraction = parse_json(cached_document.get("extraction_json"), {}) if cached_document else {}
            if cached_document and cached_extraction.get("extraction_schema_version") == "AUCTION_EXTRACT_V2":
                extracted = cached_extraction
                st.info("Dokumen yang sama sudah pernah diparse dengan skema tanggal terbaru. Hasil cache digunakan; Gemini tidak dipanggil ulang.")
            else:
                if cached_document:
                    st.info("Dokumen pernah diparse dengan skema lama. Dokumen diparse ulang satu kali agar tanggal KPKNL dan evidence terbaca dengan benar.")
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
                    "auction_time":"na_auction_time", "address":"na_address", "district":"na_district", "province":"na_province", "auction_limit":"na_limit",
                    "deposit_amount":"na_deposit", "bid_increment":"na_increment", "certificate_type":"na_certificate", "certificate_no":"na_certificate_no",
                    "land_area":"na_land", "building_area":"na_building", "njop":"na_njop", "auction_url":"na_auction_url", "property_type":"na_property_type", "bedrooms":"na_bedrooms", "bathrooms":"na_bathrooms", "rights_expiry":"na_rights_expiry",
                }
                for src, dst in field_map.items():
                    val = extracted.get(src)
                    if val not in (None, "") and (dst not in st.session_state or st.session_state.get(dst) in (None, "")): st.session_state[dst] = val
                # KPKNL dates prefill editable date pickers. A newly parsed source
                # document refreshes those values; users may edit them afterward.
                apply_extracted_auction_dates(st.session_state, extracted, document_hash=digest)
                st.session_state.na_auction_date_provenance = {
                    "source_file": extracted.get("source_file_name") or uploaded.name,
                    "document_sha256": extracted.get("document_sha256") or digest,
                    "auction_date_evidence": (extracted.get("field_evidence") or {}).get("auction_date", ""),
                    "deposit_deadline_evidence": (extracted.get("field_evidence") or {}).get("deposit_deadline", ""),
                }
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
    if "na_analysis_step" not in st.session_state:
        st.session_state.na_analysis_step = 1
    active_step = max(1, min(4, safe_int(st.session_state.na_analysis_step, 1)))
    step_titles = ["Data Lelang & Legal", "Survei & Risiko", "Harga Pembanding", "Biaya & RAB"]
    step_cols = st.columns(4)
    for step_index, step_title in enumerate(step_titles, start=1):
        with step_cols[step_index - 1]:
            if step_index < active_step:
                st.success(f"✓ LANGKAH {step_index}\n{step_title}")
            elif step_index == active_step:
                st.info(f"● LANGKAH {step_index}\n{step_title}")
            else:
                st.caption(f"LANGKAH {step_index}\n{step_title}")
    st.progress(active_step / 4, text=f"Langkah {active_step} dari 4 · Selesaikan tahapan secara berurutan")
    # Keep the optional survey uploader mounted across all steps so files are
    # not discarded when Streamlit cleans widgets from hidden sections.
    
    if active_step == 1:
        st.subheader("Identitas lelang")
        c1,c2,c3 = st.columns(3)
        with c1:
            set_default("na_lot_code", ""); st.text_input("Kode lot", key="na_lot_code")
            set_default("na_name", ""); st.text_input("Nama objek", key="na_name")
            set_default("na_complex", ""); st.text_input("Nama kompleks/perumahan", key="na_complex")
            set_default("na_auction_date", "")
            st.session_state.na_auction_date = prefilled_editable_date_picker(
                "Tanggal lelang", st.session_state.na_auction_date, "na_auction_date",
                help_text="Terisi otomatis dari dokumen KPKNL. Tetap dapat dikoreksi melalui date picker."
            )
            set_default("na_auction_time", ""); st.text_input("Jam lelang", key="na_auction_time")
        with c2:
            set_default("na_office", ""); st.text_input("KPKNL", key="na_office")
            set_default("na_seller", ""); st.text_input("Penjual/kreditur", key="na_seller")
            set_default("na_auction_type", ""); st.selectbox("Jenis lelang", ["", "Eksekusi Hak Tanggungan", "Eksekusi Pengadilan", "AYDA", "Lelang sukarela", "Lainnya"], key="na_auction_type")
            set_default("na_auction_url", ""); st.text_input("URL pengumuman lelang", key="na_auction_url")
            set_default("na_deposit_deadline", "")
            st.session_state.na_deposit_deadline = prefilled_editable_date_picker(
                "Batas setor uang jaminan", st.session_state.na_deposit_deadline, "na_deposit_deadline",
                help_text="Terisi otomatis dari dokumen KPKNL. Tetap dapat dikoreksi melalui date picker."
            )
            # Pre-win display is a scenario only. The actual estimate is refreshed
            # from the real win date in the WON/ACTIVE workflow.
            current_auction_date = st.session_state.get("na_auction_date", "")
            document_payment_date = st.session_state.get("na_payment_deadline_document_value", "")
            document_payment_auction_date = st.session_state.get("na_payment_deadline_document_auction_date", "")
            explicit_payment_date = document_payment_date if current_auction_date and current_auction_date == document_payment_auction_date else ""
            payment_due = derive_payment_deadline(
                current_auction_date,
                auction_type=st.session_state.get("na_auction_type", ""),
                auction_limit=st.session_state.get("na_limit", 0),
                explicit_deadline=explicit_payment_date,
            )
            st.session_state.na_payment_deadline = payment_due.get("payment_deadline", "")
            st.session_state.na_payment_deadline_basis = payment_due.get("payment_deadline_basis", "")
            st.session_state.na_payment_deadline_source = payment_due.get("payment_deadline_source", "")
            if st.session_state.na_payment_deadline:
                if st.session_state.get("na_payment_deadline_source") == "Dokumen KPKNL":
                    st.info(f"**Batas pelunasan yang tertulis pada dokumen KPKNL:** {_indonesian_date_label(st.session_state.na_payment_deadline)}. Ikuti dokumen resmi tersebut.")
                else:
                    st.info(f"**Informasi internal jika menang pada tanggal lelang:** perkiraan lima hari kerja jatuh pada {_indonesian_date_label(st.session_state.na_payment_deadline)}. Ini bukan tenggat resmi.")
                st.caption(st.session_state.na_payment_deadline_basis)
            else:
                st.caption("Perkiraan lima hari kerja akan muncul setelah tanggal lelang diketahui.")
            if st.session_state.get("na_auction_date_document_hash"):
                st.caption("Tanggal lelang dan setor jaminan diisi otomatis dari dokumen KPKNL. Keduanya tetap dapat dikoreksi melalui date picker.")
        with c3:
            set_default("na_address", ""); st.text_input("Alamat objek", key="na_address")
            set_default("na_district", ""); st.text_input("Desa/Kecamatan/Kabupaten", key="na_district")
            set_default("na_province", ""); st.text_input("Provinsi", key="na_province")
        coord1, coord2 = st.columns(2)
        with coord1:
            set_default("na_latitude", None); st.number_input("Latitude objek (opsional)", min_value=-90.0, max_value=90.0, value=st.session_state.na_latitude, step=0.000001, format="%.6f", key="na_latitude", help="Salin koordinat pin objek dari Google Maps. Dipakai untuk mencari pembanding berdasar radius, bukan batas administrasi.")
        with coord2:
            set_default("na_longitude", None); st.number_input("Longitude objek (opsional)", min_value=-180.0, max_value=180.0, value=st.session_state.na_longitude, step=0.000001, format="%.6f", key="na_longitude", help="Salin koordinat pin objek dari Google Maps.")
        st.caption("Untuk pembanding lintas desa/kecamatan, isi latitude dan longitude objek serta masing-masing listing. Sistem mengukur jarak garis lurus; batas administrasi tidak otomatis menggugurkan listing.")
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
        step1_missing = analysis_step1_missing(st.session_state)
        if step1_missing:
            st.warning("Lengkapi data wajib sebelum melanjutkan: " + "; ".join(step1_missing))
        st.button("LANJUT KE SURVEI →", type="primary", use_container_width=True,
                  disabled=bool(step1_missing), on_click=_persist_and_go_analysis_step, args=(2,), key="na_go_step_2")

    if active_step == 2:
        st.subheader("Survei lapangan dan kondisi penghuni")
        st.caption("Catat hanya hal yang benar-benar diketahui dari survei atau sumber yang dapat Anda jelaskan. Status belum survei akan menahan keputusan final.")
        statuses = list(OCCUPANCY_DEFAULTS.keys())
        set_default("na_survey_status", "Belum Survei")
        prior_status = st.session_state.get("na_last_occupancy", st.session_state.na_survey_status)
        st.selectbox("Status survei dan penghuni", statuses, key="na_survey_status")
        survey_photos = st.file_uploader("Foto hasil survei (opsional; pilih beberapa foto)", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="na_survey_photos")
        st.caption("Foto survei tidak otomatis dikirim ke Gemini. Bila Google Drive archive diaktifkan, foto disimpan ke folder Drive dan metadata/hash dicatat di database.")
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
        st.session_state.na_risk_editor = risk_edited.copy()
        if len(risk_edited):
            st.caption("Skor risiko dihitung otomatis: kemungkinan × dampak. Skor 20–25 ditandai sangat tinggi. Risiko kritis yang masih terbuka akan menahan keputusan GO.")
        risk_signature = hashlib.sha256(safe_json(st.session_state.na_risk_current).encode("utf-8")).hexdigest()
        sync_review_confirmation(st.session_state, "na_risk_reviewed", "na_risk_reviewed_signature", risk_signature)
        st.checkbox("Saya sudah meninjau risiko yang relevan dan mitigasinya; saya memahami bahwa risiko yang belum terselesaikan dapat menahan keputusan GO.", key="na_risk_reviewed")
        st.session_state.na_risk_editor = risk_edited.copy()
        step2_missing = []
        if not st.session_state.get("na_survey_status"):
            step2_missing.append("Pilih status survei/penghuni (Belum Survei juga merupakan pilihan yang sah)")
        if not st.session_state.get("na_risk_reviewed", False):
            step2_missing.append("Tinjau dan konfirmasi risk register")
        if step2_missing:
            st.warning("Selesaikan tahap survei: " + "; ".join(step2_missing))
        b2, b2next = st.columns(2)
        with b2:
            st.button("← KEMBALI KE DATA LELANG", use_container_width=True, on_click=_persist_and_go_analysis_step, args=(1,), key="na_back_step_1")
        with b2next:
            st.button("LANJUT KE PEMBANDING →", type="primary", use_container_width=True,
                      disabled=bool(step2_missing), on_click=_persist_and_go_analysis_step, args=(3,), key="na_go_step_3")

    if active_step == 3:
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
        default_cols = ["name", "address", "complex_name", "underlying_property_id", "latitude", "longitude", "distance_m", "market_segment", "seller_type", "price", "njop", "land_area", "building_area", "bedrooms", "bathrooms", "condition", "condition_detail", "access", "access_detail", "price_type", "promotion_claims", "promotion_value_verified", "verified_promotion_value", "certificate", "orientation", "electricity_watt", "water_source", "source_platforms", "source_evidence", "source_url", "source_url_scope", "listing_date", "date_found", "date_found_basis", "notes", "adjustment_pct", "ai_adjustment_rationale", "ai_exclude_from_primary"]
        if st.session_state.get("na_comparable_schema_version") != 7:
            if "na_comparables_editor_widget" in st.session_state:
                del st.session_state["na_comparables_editor_widget"]
            st.session_state.na_comparable_schema_version = 7
        if "na_comparables_editor" not in st.session_state:
            st.session_state.na_comparables_editor = pd.DataFrame([{c: None for c in default_cols} for _ in range(5)])
        else:
            comp_frame = st.session_state.na_comparables_editor.copy()
            for column in default_cols:
                if column not in comp_frame.columns:
                    comp_frame[column] = None
            st.session_state.na_comparables_editor = comp_frame[default_cols]
        st.caption("Untuk estimasi indikatif dibutuhkan minimal 3 pembanding unik yang memiliki nama, harga, minimal salah satu LT/LB, dan sumber yang dapat ditelusuri. Keputusan GO dapat mensyaratkan minimal 5 pembanding individual yang lebih kuat. Untuk rumah lelang/resale, tandai segmen Secondary atau Primary. Listing developer dipisahkan sebagai kompetisi bila tersedia pembanding secondary. Promo hanya mengurangi harga efektif bila nilai rupiahnya benar-benar terverifikasi. Gunakan ID objek fisik yang sama untuk mencegah rumah yang sama dihitung dua kali lintas portal.")
        comparable_editor_input = st.session_state.na_comparables_editor.copy()
        # Streamlit DateColumn expects date-like values; normalize back to ISO strings after editing.
        for date_col in ("listing_date", "date_found"):
            if date_col in comparable_editor_input.columns:
                comparable_editor_input[date_col] = comparable_editor_input[date_col].apply(comparable_date_for_editor)
        edited = st.data_editor(comparable_editor_input, num_rows="dynamic", use_container_width=True, key="na_comparables_editor_widget", column_config={
            "name": st.column_config.TextColumn("Nama listing"),
            "address": st.column_config.TextColumn("Alamat/lokasi"),
            "latitude": st.column_config.NumberColumn("Latitude", min_value=-90.0, max_value=90.0, format="%.6f", help="Koordinat pin properti dari Google Maps. Opsional, tetapi diperlukan untuk mengukur jarak lintas desa/kecamatan."),
            "longitude": st.column_config.NumberColumn("Longitude", min_value=-180.0, max_value=180.0, format="%.6f", help="Koordinat pin properti dari Google Maps. Opsional, tetapi diperlukan untuk mengukur jarak lintas desa/kecamatan."),
            "distance_m": st.column_config.NumberColumn("Jarak lurus (meter)", min_value=0, step=50, help="Isi jarak garis lurus dari objek target ke pembanding bila koordinat tidak diisi. Batas desa/kecamatan tidak membatasi pembanding."),
            "underlying_property_id": st.column_config.TextColumn("ID objek fisik (anti-duplikat)", help="Gunakan ID yang sama bila satu rumah dipasang di beberapa portal/agen. Opsional; jangan gunakan ID listing portal."),
            "market_segment": st.column_config.SelectboxColumn("Segmen pasar", options=["Tidak diketahui", "Secondary / resale", "Primary / developer"], help="Secondary menjadi pembanding utama untuk objek rumah lelang/resale. Primary dipisahkan sebagai kompetisi pasar."),
            "seller_type": st.column_config.SelectboxColumn("Jenis penjual", options=["", "Pemilik", "Agen", "Developer", "Tidak diketahui"]),
            "price": st.column_config.NumberColumn("Harga listing (Rp)", min_value=0, format="Rp %.0f"),
            "njop": st.column_config.NumberColumn("NJOP pembanding (Rp, opsional)", min_value=0, format="Rp %.0f", help="Isi hanya bila Anda benar-benar memiliki NJOP/SPPT pembanding tersebut."),
            "land_area": st.column_config.NumberColumn("LT (m²)", min_value=0),
            "building_area": st.column_config.NumberColumn("LB (m²)", min_value=0, help="Boleh kosong bila tidak tercantum; sistem dapat memakai pendekatan LT saja."),
            "condition": st.column_config.SelectboxColumn("Kondisi", options=["", "Siap Huni", "Butuh Renovasi", "Hitung Tanah"]),
            "access": st.column_config.SelectboxColumn("Akses", options=["", "2 Mobil", "1 Mobil", "Gang"]),
            "price_type": st.column_config.SelectboxColumn("Jenis harga", options=["Asking aktif", "Marked sold / perlu verifikasi", "Transaksi terverifikasi", "Over kredit / skema kewajiban"]),
            "promotion_claims": st.column_config.TextColumn("Klaim promosi (teks)"),
            "promotion_value_verified": st.column_config.CheckboxColumn("Nilai promo terverifikasi?", help="Centang hanya jika ada bukti nominal manfaat yang benar-benar mengurangi pengeluaran pembeli."),
            "verified_promotion_value": st.column_config.NumberColumn("Nilai promo terverifikasi (Rp)", min_value=0, format="Rp %.0f"),
            "source_platforms": st.column_config.TextColumn("Portal/platform sumber"),
            "source_url": st.column_config.TextColumn("URL sumber (dari input)"),
            "source_url_scope": st.column_config.SelectboxColumn("Jenis halaman sumber", options=["", "Listing individual", "Portal/domain only", "Portal pencarian/kategori", "Halaman venue/kompleks", "Perlu verifikasi"], help="Domain utama portal cukup sebagai sumber untuk valuasi indikatif, tetapi hanya URL listing individual yang dapat dihitung untuk audit gate GO."),
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
            "latitude": st.session_state.get("na_latitude"), "longitude": st.session_state.get("na_longitude"),
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
            # Any material comparable change invalidates prior URL review. A user
            # must not be able to confirm a URL once, then edit price/area/address
            # and accidentally keep that old confirmation attached to new facts.
            url_review_material = [
                {
                    "name": str(row.get("name") or "").strip(),
                    "address": str(row.get("address") or "").strip(),
                    "price": to_float(row.get("price")),
                    "land_area": to_float(row.get("land_area")),
                    "building_area": to_float(row.get("building_area")),
                    "url": str(row.get("source_url") or "").strip(),
                }
                for row in edited_normalized.to_dict(orient="records")
                if str(row.get("source_url") or "").strip()
            ]
            url_review_signature = hashlib.sha256(safe_json(url_review_material).encode("utf-8")).hexdigest()
            sync_review_confirmation(st.session_state, "na_confirm_individual_urls", "na_confirm_individual_urls_signature", url_review_signature)
            confirm_individual_urls = st.checkbox(
                "Saya sudah membuka satu per satu URL dan memastikan halaman tersebut menampilkan rumah yang sesuai dengan nama, harga, LT/LB dan lokasi pada barisnya (bukan homepage portal atau halaman pencarian).",
                key="na_confirm_individual_urls",
            )
            if st.button("Konfirmasi URL detail yang benar-benar cocok", disabled=not confirm_individual_urls, use_container_width=True, key="na_confirm_url_scope"):
                from urllib.parse import urlparse
                rows_to_update = edited_normalized.to_dict(orient="records")
                changed = 0
                skipped = 0
                for comp in rows_to_update:
                    url = str(comp.get("source_url") or "").strip()
                    scope = str(comp.get("source_url_scope") or "")
                    path = (urlparse(url).path or "").strip("/") if url.startswith(("http://", "https://")) else ""
                    explicitly_portal = scope in {"Portal/domain only", "Portal pencarian/kategori", "Halaman venue/kompleks"}
                    if url.startswith(("http://", "https://")) and path and not explicitly_portal:
                        comp["source_url_scope"] = "Listing individual"
                        changed += 1
                    elif url:
                        skipped += 1
                st.session_state.na_comparables_editor = pd.DataFrame(rows_to_update)
                if "na_comparables_editor_widget" in st.session_state: del st.session_state["na_comparables_editor_widget"]
                st.success(f"{changed} URL dengan halaman detail ditandai sebagai listing individual. {skipped} URL homepage/portal tetap bukan listing individual.")
                st.rerun()
        set_default("na_negotiation_discount", DEFAULT_RULES["negotiation_discount_pct"])
        set_default("na_quick_sale_discount", DEFAULT_RULES["quick_sale_discount_pct"])
        c1,c2 = st.columns(2)
        with c1: st.number_input("Negotiation discount listing aktif (%)", min_value=0.0, max_value=50.0, step=1.0, key="na_negotiation_discount")
        with c2: st.number_input("Quick-sale discount (%)", min_value=0.0, max_value=30.0, step=1.0, key="na_quick_sale_discount")
        step3_count = count_valid_comparables(st.session_state.get("na_comparables_current", []))
        step3_missing = [] if step3_count >= 3 else [f"Minimal 3 pembanding unik dengan harga, LT/LB, dan sumber yang dapat ditelusuri (saat ini {step3_count})"]
        if step3_missing:
            st.warning("Lengkapi data pembanding: " + "; ".join(step3_missing))
        b3, b3next = st.columns(2)
        with b3:
            st.button("← KEMBALI KE SURVEI", use_container_width=True, on_click=_persist_and_go_analysis_step, args=(2,), key="na_back_step_2")
        with b3next:
            st.button("LANJUT KE BIAYA / RAB →", type="primary", use_container_width=True,
                      disabled=bool(step3_missing), on_click=_persist_and_go_analysis_step, args=(4,), key="na_go_step_4")

    if active_step == 4:
        st.subheader("Biaya proyek dan target")
        rules = get_rules()
        st.markdown("### RAB renovasi — AI-assisted draft")
        st.caption("Masukkan deskripsi kondisi dan, bila tersedia, tabel BoQ berisi Item Pekerjaan, Estimasi Volume, dan Satuan. Volume BoQ pengguna dipertahankan; jika BoQ tidak diberikan, Python menyiapkan allowance awal dari LT/LB dan profil rumah. Gemini membantu menilai lingkup serta mengusulkan harga satuan. Semua hasil tetap draft untuk diperiksa.")
        set_default("na_renovation_category", "Auto sesuai kondisi umum")
        rab_category_options = RENOVATION_CATEGORIES
        if st.session_state.na_renovation_category not in rab_category_options: rab_category_options = rab_category_options + [st.session_state.na_renovation_category]
        st.selectbox("Kategori / lingkup RAB", rab_category_options, key="na_renovation_category", help="Pilih Auto agar kategori utama dalam deskripsi rinci dibaca AI/Python. Pilihan manual akan mengesampingkan kategori pada narasi. Untuk pekerjaan struktur, volume tetap wajib dari desain/engineer.")
        set_default("na_rab_condition_description", "")
        st.text_area("Deskripsi kondisi aktual dan pekerjaan yang terlihat/diperlukan", key="na_rab_condition_description", height=115, placeholder="Tempel kondisi properti dan tabel BoQ. Format Markdown atau tabel yang disalin dari Excel/Google Sheets (tab-separated) didukung.")
        boq_preview_rows = parse_user_boq_table(st.session_state.get("na_rab_condition_description", ""))
        if boq_preview_rows:
            st.success(f"BoQ terdeteksi sebelum analisis: {len(boq_preview_rows)} item. Nama pekerjaan, volume, dan satuan dari input Anda akan dipertahankan.")
            with st.expander("Pratinjau BoQ yang akan dikirim ke Gemini", expanded=False):
                st.dataframe(pd.DataFrame([{"Kelompok": r.get("subcategory"), "Item pekerjaan": r.get("work_item"), "Volume": r.get("quantity"), "Satuan": r.get("unit"), "Status awal": r.get("priority")} for r in boq_preview_rows]), use_container_width=True, hide_index=True)
        elif any(token in st.session_state.get("na_rab_condition_description", "").lower() for token in ["estimasi volume", "item pekerjaan", "boq"]):
            st.warning("Teks tampaknya memuat BoQ, tetapi belum ada baris yang terbaca. Pastikan header memuat Item Pekerjaan, Estimasi Volume, dan Satuan. Anda boleh memakai tabel Markdown dengan tanda | atau menempel langsung tabel Excel/Google Sheets yang dipisahkan tab.")
        available_rab_files: list[tuple[bytes, str, str]] = []
        if uploaded is not None:
            available_rab_files.append((uploaded.getvalue(), uploaded.type or "application/octet-stream", uploaded.name))
        for photo in _get_survey_photo_payloads()[:5]:
            available_rab_files.append((photo["bytes"], photo.get("mime_type") or "image/jpeg", photo.get("name") or "survey-photo.jpg"))
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
            cache_material = "RAB_PARSER_V1.0.16|" + rab_description + safe_json(context) + "|" + "|".join(file_sha256(f[0]) for f in available_rab_files)
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
                for widget_key in ["na_renovation_items_widget", "na_renovation_items_widget_v103", "na_renovation_items_widget_v104"]:
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
                if rab_estimate.get("rab_deduplication"):
                    with st.expander(f"Pemeriksaan duplikasi scope ({len(rab_estimate.get('rab_deduplication', []))} baris generik disatukan dengan BoQ)", expanded=False):
                        for duplicate in rab_estimate.get("rab_deduplication", []):
                            st.write(f"• {duplicate.get('item_code')}: {duplicate.get('work_item')} — {duplicate.get('reason')}")
                if rab_estimate.get("user_boq_count", 0):
                    st.success(f"BoQ pengguna terbaca: {rab_estimate.get('user_boq_count')} baris. {rab_estimate.get('user_boq_priced_count', rab_estimate.get('user_boq_model_priced_count', 0))} baris sudah memiliki harga konservatif; {rab_estimate.get('user_boq_catalog_priced_count', 0)} di antaranya diisi katalog screening Python. Kuantitas BoQ dipertahankan persis.")
                    st.caption("Baris BoQ eksplisit tetap menjadi allowance modal meskipun interior/komponen belum dapat diinspeksi. Keyakinan diturunkan untuk pekerjaan tersembunyi; keluarkan hanya setelah inspeksi membuktikan tidak diperlukan. Harga katalog/Gemini adalah rentang screening, bukan quotation atau HSPK all-in.")
                    if rab_estimate.get("user_boq_unpriced_items"):
                        with st.expander(f"Lihat {len(rab_estimate.get('user_boq_unpriced_items', []))} item BoQ yang belum memiliki harga satuan"):
                            for unpriced_name in rab_estimate.get("user_boq_unpriced_items", []):
                                st.write(f"• {unpriced_name}")
                elif "estimasi volume" in str(st.session_state.get("na_rab_condition_description", "")).lower():
                    st.error("BoQ belum terbaca. V1.0.16 mendukung tabel Markdown (|) dan tabel tab-separated hasil salin dari Excel/Google Sheets. Periksa header Item Pekerjaan, Estimasi Volume, Satuan serta setiap baris memiliki volume dan satuan.")
                for category_note in rab_estimate.get("category_warnings", []):
                    st.warning(category_note)
                for geometry_note in rab_estimate.get("geometry_warnings", []):
                    st.warning(geometry_note)
                if rab_estimate.get("total_conservative_complete", False):
                    st.success("Seluruh item dalam lingkup sudah memiliki volume dan harga dasar screening. Angka berikut adalah allowance underwriting, bukan nilai kontrak final.")
                    if rab_estimate.get("total_range_complete", False):
                        r1, r2, r3 = st.columns(3)
                        r1.metric("RAB batas bawah", idr(rab_estimate.get("total_low_indicative")))
                        r2.metric("RAB dasar", idr(rab_estimate.get("total_conservative_indicative")))
                        r3.metric("RAB batas atas", idr(rab_estimate.get("total_high_indicative")))
                    else:
                        st.metric("RAB dasar", idr(rab_estimate.get("total_conservative_indicative")))
                        st.caption("Sebagian baris tidak mempunyai batas bawah/atas yang memadai; rentang total tidak ditampilkan agar tidak menyesatkan.")
                else:
                    st.metric("Subtotal item yang sudah memiliki volume dan harga", idr(rab_estimate.get("subtotal_conservative_priced_items", rab_estimate.get("total_conservative_indicative"))))
                    st.metric("Total allowance RAB", "Masih ada scope perlu ukur/harga")
                    st.caption(f"Item terisi: {rab_estimate.get('priced_item_count', 0)} dari {rab_estimate.get('in_scope_item_count', 0)} item dalam anggaran. Item tak terukur tidak boleh dianggap nol.")
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
                    st.markdown("**Skenario risiko interior (sensitivitas, bukan tambahan otomatis)**")
                    for scenario in scenarios:
                        low, high = scenario.get("cost_low"), scenario.get("cost_high")
                        cost_label = f"{idr(low)} – {idr(high)}" if low is not None and high is not None else "Belum cukup dasar untuk menaksir nominal"
                        st.markdown(f"**{scenario.get('scenario_name', 'Skenario')}** · {cost_label} · Keyakinan: {scenario.get('confidence', 'Rendah')}")
                        for assumption in scenario.get("assumptions", []): st.caption(f"Asumsi: {assumption}")
                        for work in scenario.get("potential_work_items", []): st.write(f"• {work}")
                    st.info(rab_estimate.get("interior_scenario_note", "Skenario ini tidak otomatis ditambahkan ke total RAB. Cocokkan daftar pekerjaannya dengan BoQ; tambahkan hanya item/selisih biaya yang belum dianggarkan agar tidak terjadi penghitungan ganda."))
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
        renovation_columns = ["item_code", "subcategory", "work_item", "quantity_low", "quantity", "quantity_high", "quantity_basis", "unit", "unit_cost_low", "unit_cost", "unit_cost_high", "price_source", "priority", "evidence_basis", "confidence", "notes"]
        if "na_renovation_items_editor" not in st.session_state:
            st.session_state.na_renovation_items_editor = pd.DataFrame([{c: None for c in renovation_columns} for _ in range(4)])
        renovation_frame = st.session_state.na_renovation_items_editor.copy()
        for col in renovation_columns:
            if col not in renovation_frame.columns: renovation_frame[col] = None
        rate_source_rows = st.session_state.get("na_renovation_items_current") or st.session_state.na_renovation_items_editor.to_dict(orient="records")
        current_rab_rows = [r for r in rate_source_rows if str(r.get("work_item") or "").strip()]
        missing_user_rate_rows = [r for r in current_rab_rows if str(r.get("item_code") or "").startswith("USER_BOQ_") and (r.get("unit_cost") in (None, "") or to_float(r.get("unit_cost")) <= 0)]
        if missing_user_rate_rows:
            st.info(
                f"{len(missing_user_rate_rows)} item belum tercakup pricebook PFMS versi {PRICE_CATALOG_VERSION}. "
                "Harga kosong tidak diisi dengan tebakan Gemini agar hasil RAB tetap konsisten. Masukkan harga override dari minimal dua penawaran lokal atau lampirkan dasar harga yang dapat diperiksa."
            )
        renovation_edited = st.data_editor(renovation_frame[renovation_columns], num_rows="dynamic", use_container_width=True, key="na_renovation_items_widget_v104", column_config={
            "item_code": st.column_config.TextColumn("Kode scope", disabled=True),
            "subcategory": st.column_config.TextColumn("Kelompok pekerjaan", disabled=True),
            "work_item": st.column_config.TextColumn("Pekerjaan"),
            "quantity_low": st.column_config.NumberColumn("Vol. rendah", min_value=0.0, step=1.0),
            "quantity": st.column_config.NumberColumn("Volume dipakai", min_value=0.0, step=1.0, help="Volume konservatif yang dipakai Python untuk menghitung RAB; dapat Anda koreksi."),
            "quantity_high": st.column_config.NumberColumn("Vol. atas", min_value=0.0, step=1.0),
            "quantity_basis": st.column_config.TextColumn("Dasar estimasi volume", disabled=True),
            "unit": st.column_config.TextColumn("Satuan"),
            "unit_cost_low": st.column_config.NumberColumn("Harga satuan rendah (Rp)", min_value=0, format="Rp %.0f"),
            "unit_cost": st.column_config.NumberColumn("Harga satuan konservatif (Rp)", min_value=0, format="Rp %.0f", help="Nilai inilah yang dipakai Python untuk menghitung RAB."),
            "unit_cost_high": st.column_config.NumberColumn("Batas atas (Rp)", min_value=0, format="Rp %.0f"),
            "price_source": st.column_config.TextColumn("Sumber harga", disabled=True),
            "priority": st.column_config.SelectboxColumn("Prioritas", options=["Wajib", "Disarankan", "Bersyarat", "Opsional", "Tidak diperlukan setelah ditinjau"]),
            "evidence_basis": st.column_config.SelectboxColumn("Dasar", options=["Fakta visual", "Deskripsi pengguna", "Asumsi kuantitas"]),
            "confidence": st.column_config.SelectboxColumn("Keyakinan", options=["Tinggi", "Sedang", "Rendah"]),
            "notes": st.column_config.TextColumn("Catatan / asumsi / sumber"),
        })
        edited_rab_rows = renovation_edited.to_dict(orient="records")
        original_rab_by_code = {str(r.get("item_code") or ""): r for r in rate_source_rows}
        for edited_row in edited_rab_rows:
            code = str(edited_row.get("item_code") or "")
            original = original_rab_by_code.get(code, {})
            changed_rate = any(
                to_float(edited_row.get(field)) != to_float(original.get(field))
                for field in ("unit_cost_low", "unit_cost", "unit_cost_high")
            )
            if changed_rate and any(edited_row.get(field) not in (None, "") for field in ("unit_cost_low", "unit_cost", "unit_cost_high")):
                edited_row["price_source"] = "Override manual pengguna"
                note = str(edited_row.get("notes") or "")
                if "Harga satuan diubah manual oleh pengguna" not in note:
                    edited_row["notes"] = (note + " | Harga satuan diubah manual oleh pengguna; dokumentasikan penawaran/rujukan harga.").strip(" |")
        st.session_state.na_renovation_items_current = edited_rab_rows
        st.session_state.na_renovation_items_editor = pd.DataFrame(edited_rab_rows, columns=renovation_columns)
        updated_estimate = dict(st.session_state.get("na_rab_estimate") or {})
        if updated_estimate:
            updated_estimate["editor_rows"] = edited_rab_rows
            updated_estimate.update(summarize_rab_totals(edited_rab_rows))
            st.session_state.na_rab_estimate = updated_estimate
        current_rab_rows = [r for r in st.session_state.na_renovation_items_current if str(r.get("work_item") or "").strip()]
        renovation_items = current_rab_rows
        renovation_item_total = sum(max(0, to_float(r.get("quantity"))) * max(0, to_float(r.get("unit_cost"))) for r in renovation_items if rab_item_is_in_scope(r))
        # Read-only calculated view: deterministic line subtotals and grouped totals.
        detailed_rows = []
        for row in renovation_items:
            sub = rab_row_subtotals(row)
            detailed_rows.append({
                "Kode": row.get("item_code"), "Kelompok scope": row.get("subcategory"), "Pekerjaan": row.get("work_item"),
                "Volume dipakai": row.get("quantity"), "Satuan": row.get("unit"),
                "Harga satuan dasar (Rp)": row.get("unit_cost"), "Subtotal dasar (Rp)": sub.get("subtotal_base"),
                "Subtotal rendah (Rp)": sub.get("subtotal_low"), "Subtotal atas (Rp)": sub.get("subtotal_high"),
                "Status": "Masuk RAB" if rab_item_is_in_scope(row) else str(row.get("priority") or "Di luar RAB"),
            })
        st.markdown("#### Rincian biaya hasil perhitungan Python")
        st.caption("Subtotal per baris = volume dipakai × harga satuan. Harga dari pricebook regional berversi digunakan bila scope dan satuan cocok; item yang tidak tercakup ditandai untuk quotation/override. Item bersyarat tetap terlihat sesuai scope yang disetujui.")
        with st.expander("Dasar acuan harga dan versi pricebook", expanded=False):
            st.write(f"**Versi:** {PRICE_CATALOG_VERSION}")
            st.write(PRICE_CATALOG_BASIS)
            st.markdown(f"- [SSH Sidoarjo TA 2026 — Perbup 27/2025]({PRICE_CATALOG_REFERENCES['ssh_sidoarjo_2026']})")
            st.markdown(f"- [ASB/HSPK Sidoarjo — Perbup 75/2025]({PRICE_CATALOG_REFERENCES['hspk_sidoarjo_2026']})")
            st.markdown(f"- [Pedoman AHSP — Permen PUPR 8/2023]({PRICE_CATALOG_REFERENCES['ahsp_pupr_2023']})")
            st.markdown("**Contoh jangkar harga komponen dari SSH Sidoarjo TA 2026**")
            anchor_frame = pd.DataFrame(PRICE_CATALOG_ANCHORS).rename(columns={"item": "Komponen", "specification": "Sumber", "unit": "Satuan", "rate": "Harga SSH 2026 (Rp)"})
            st.dataframe(anchor_frame, use_container_width=True, hide_index=True, column_config={"Harga SSH 2026 (Rp)": st.column_config.NumberColumn(format="Rp %.0f")})
            st.caption("Jangkar SSH di atas adalah harga komponen, bukan harga pekerjaan terpasang. Pricebook PFMS adalah estimasi screening bahan+upah, bukan SSH/HSPK all-in atau quotation vendor. Override manual pengguna dipertahankan saat analisis ulang.")
        if detailed_rows:
            st.dataframe(pd.DataFrame(detailed_rows), use_container_width=True, hide_index=True, column_config={
                "Harga satuan dasar (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Subtotal dasar (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Subtotal rendah (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Subtotal atas (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
            })
        grouped_rows = summarize_rab_scope_totals(renovation_items)
        st.markdown("#### Subtotal menurut kelompok pekerjaan")
        if grouped_rows:
            st.dataframe(pd.DataFrame(grouped_rows), use_container_width=True, hide_index=True, column_config={
                "Subtotal rendah (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Subtotal dasar (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Subtotal atas (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
            })
        c1,c2,c3 = st.columns(3)
        with c1:
            set_default("na_renovation_extra", 0); st.number_input("Tambahan renovasi di luar item (Rp)", min_value=0, step=500_000, key="na_renovation_extra")
            set_default("na_renovation_months", 1.0); st.number_input("Waktu renovasi (bulan)", min_value=0.0, step=0.5, key="na_renovation_months")
        with c2:
            set_default("na_monthly_holding", rules["monthly_holding_cost"]); st.number_input("Holding cost per bulan (Rp)", min_value=0, step=250_000, key="na_monthly_holding")
            set_default("na_selling_months", 1.0); st.number_input("Estimasi waktu penjualan (bulan)", min_value=0.0, step=0.5, key="na_selling_months")
        with c3:
            set_default("na_legal_delay_months", 0.5); st.number_input("Estimasi delay legalitas (bulan)", min_value=0.0, step=0.5, key="na_legal_delay_months")
            set_default("na_marketing_cost", 1_000_000); st.number_input("Biaya marketing (Rp)", min_value=0, step=250_000, key="na_marketing_cost")
        renovation_total = renovation_item_total + to_float(st.session_state.na_renovation_extra)
        in_scope_rab_rows = [r for r in renovation_items if rab_item_is_in_scope(r)]
        unpriced_rab_rows = [r for r in in_scope_rab_rows if r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, "")]
        if unpriced_rab_rows:
            st.metric("Subtotal sementara — bukan total RAB", idr(renovation_total))
            st.error(f"RAB BELUM LENGKAP: {len(unpriced_rab_rows)} item wajib/disarankan dalam lingkup belum memiliki volume atau harga satuan. Angka subtotal tidak boleh digunakan sebagai estimasi total renovasi atau dasar final ROI/bidding.")
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
        policy_rules = get_rules()
        st.metric("ROI minimum / target", f"{policy_rules.get('minimum_roi_pct', 20):.0f}% / {policy_rules.get('mid_roi_pct', 30):.0f}%", help="Project ROI minimum sebagai gate GO; target ROI adalah sasaran negosiasi/bid. Tidak ada batas maksimum keuntungan.")
        st.caption(f"Kebijakan Kayna: profit bersih minimum {idr(policy_rules.get('minimum_net_profit', 50_000_000))} · ROI all-in minimum/target {policy_rules.get('minimum_roi_pct', 20):.0f}%/{policy_rules.get('mid_roi_pct', 30):.0f}% · durasi ideal/maksimum {policy_rules.get('target_holding_days', 90)}/{policy_rules.get('maximum_holding_days', 180)} hari. ROI di atas target tidak dibatasi.")
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
            "hidden_condition_reserve_pct": rules_for_cost_review.get("hidden_condition_reserve_pct", 7.5),
        }
        cost_signature = hashlib.sha256(safe_json(cost_review_payload).encode("utf-8")).hexdigest()
        sync_review_confirmation(st.session_state, "na_costs_reviewed", "na_costs_reviewed_signature", cost_signature)
        st.checkbox("Saya sudah meninjau seluruh estimasi biaya (BPN, penguasaan, setiap item RAB, contingency, holding, marketing dan biaya lain). Nilai nol adalah keputusan yang disengaja.", key="na_costs_reviewed")
        with st.expander("Asumsi biaya dan pajak (editable pada Settings & Rules)"):
            st.json(rules)

    analysis_ready = False
    if active_step == 4:
        final_missing = []
        if not st.session_state.get("na_risk_reviewed", False):
            final_missing.append("Konfirmasi review risiko pada Langkah 2")
        if count_valid_comparables(st.session_state.get("na_comparables_current", [])) < 3:
            final_missing.append("Minimal 3 pembanding unik dan bersumber")
        if not st.session_state.get("na_costs_reviewed", False):
            final_missing.append("Konfirmasi review biaya pada Langkah 4")
        final_rab_rows = [r for r in st.session_state.get("na_renovation_items_current", []) if rab_item_is_in_scope(r) and str(r.get("work_item") or "").strip()]
        final_unpriced = [r for r in final_rab_rows if r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, "") or to_float(r.get("unit_cost")) <= 0]
        if final_unpriced:
            final_missing.append(f"{len(final_unpriced)} item RAB dalam lingkup belum memiliki volume/harga satuan")
        if final_missing:
            st.warning("Analisis belum dapat dijalankan. Selesaikan: " + "; ".join(final_missing))
        else:
            analysis_ready = st.button("🚀 ANALISA / UPDATE DATA", type="primary", use_container_width=True, key="na_run_underwriting")
        st.button("← KEMBALI KE PEMBANDING", use_container_width=True, on_click=_persist_and_go_analysis_step, args=(3,), key="na_back_step_3")
    if analysis_ready:
        property_data = {
            "lot_code": st.session_state.na_lot_code, "name": st.session_state.na_name, "complex_name": st.session_state.na_complex,
            "address": st.session_state.na_address, "district": st.session_state.na_district, "province": st.session_state.na_province,
            "auction_office": st.session_state.na_office, "seller": st.session_state.na_seller, "auction_type": st.session_state.na_auction_type,
            "auction_date": st.session_state.na_auction_date, "auction_time": st.session_state.get("na_auction_time", ""), "deposit_deadline": st.session_state.get("na_deposit_deadline", ""), "payment_deadline": st.session_state.get("na_payment_deadline", ""), "auction_url": st.session_state.get("na_auction_url", ""),
            "auction_date_evidence": st.session_state.get("na_auction_date_evidence", {}), "auction_date_document_hash": st.session_state.get("na_auction_date_document_hash", ""),
            "auction_date_source_file": st.session_state.get("na_auction_date_source_file", ""),
            "payment_deadline_basis": st.session_state.get("na_payment_deadline_basis", ""), "payment_deadline_source": st.session_state.get("na_payment_deadline_source", ""),
            "payment_deadline_document_value": st.session_state.get("na_payment_deadline_document_value", ""),
            "payment_deadline_document_auction_date": st.session_state.get("na_payment_deadline_document_auction_date", ""),
            "auction_limit": st.session_state.na_limit, "deposit_amount": st.session_state.na_deposit, "bid_increment": st.session_state.na_increment,
            "certificate_type": st.session_state.na_certificate, "certificate_no": st.session_state.na_certificate_no, "rights_expiry": st.session_state.get("na_rights_expiry", ""),
            "land_area": st.session_state.na_land, "building_area": st.session_state.na_building, "building_footprint_m2": st.session_state.get("na_building_footprint"), "njop": st.session_state.na_njop,
            "latitude": st.session_state.get("na_latitude"), "longitude": st.session_state.get("na_longitude"), "bedrooms": st.session_state.get("na_bedrooms"), "bathrooms": st.session_state.get("na_bathrooms"), "property_type": st.session_state.get("na_property_type", ""), "floor_count": st.session_state.get("na_floor_count", 1), "rights_expiry": st.session_state.get("na_rights_expiry", ""),
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
            "latitude": property_data.get("latitude"), "longitude": property_data.get("longitude"),
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
            st.info("ARV belum dapat dihitung karena belum ada listing dengan harga dan luas yang dapat dinormalisasi. Anda tetap dapat menyimpan draft dan memperbaiki data pembanding.")
        else:
            st.info(
                f"{mkt.get('estimate_label', 'Estimasi pasar indikatif tersedia')}: {mkt.get('valid_count', 0)} pembanding masuk ke perhitungan. "
                f"Indikasi dasar {idr(mkt.get('base_exit'))}; konservatif {idr(mkt.get('conservative_exit'))}; "
                f"rentang model {idr(mkt.get('market_range_low'))}–{idr(mkt.get('market_range_high'))}. "
                "Ini estimasi underwriting, bukan appraisal resmi atau harga transaksi terverifikasi."
            )
            if mkt.get("status") != "READY":
                st.warning(
                    f"Estimasi sudah tersedia, tetapi bukti belum memenuhi gate audit keputusan GO: "
                    f"{mkt.get('go_grade_count', 0)} dari minimal 5 URL listing individual yang dapat ditelusuri. "
                    f"Indeks kualitas bukti {mkt.get('confidence', 0)}/100 ({mkt.get('confidence_band', 'Rendah')}); bukan probabilitas harga tercapai. Status HOLD pada tahap ini membatasi keputusan bidding final, bukan menghapus hasil estimasi harga pasar."
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
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("ARV konservatif", idr(mkt.get("conservative_exit")), help="Estimasi harga keluar konservatif setelah quick-sale discount.")
        k2.metric("ARV dasar", idr(mkt.get("base_exit")), help="Estimasi nilai pasar dasar dari comparable dan, bila tersedia, referensi NJOP terkalibrasi.")
        k3.metric("Modal sementara / data terisi" if financial_inputs_partial else "Total modal proyek", idr(at.get("capital_before_sale")), help="Jika RAB dalam lingkup belum lengkap atau biaya belum dikonfirmasi, angka ini hanya total komponen yang sudah terdata; belum merupakan total modal akhir.")
        k4.metric("Profit indikatif" if financial_inputs_partial else "Estimasi profit bersih", idr(at.get("net_profit")))
        roi_cols = st.columns(3)
        roi_cols[1].metric("ROI all-in indikatif" if financial_inputs_partial else "ROI proyek all-in", pct(at.get("roi_pct")), help="Profit bersih dibagi total biaya proyek all-in, termasuk biaya transaksi penjualan.")
        if tiers.get("provisional_reasons"):
            st.warning("Tangga bidding dan hasil profit/ROI masih INDIKATIF. Dasar yang belum final: " + "; ".join(tiers.get("provisional_reasons", [])) + ". Jangan gunakan sebagai instruksi bidding final.")
        st.markdown("### Tangga bidding")
        tier_rows = []
        policy_min_roi = to_float(snap.get("rules", {}).get("minimum_roi_pct", 20))
        policy_target_roi = to_float(snap.get("rules", {}).get("mid_roi_pct", 30))
        policy_min_profit = to_float(snap.get("rules", {}).get("minimum_net_profit", 50_000_000))
        policy_target_days = to_float(snap.get("rules", {}).get("target_holding_days", 90))
        policy_max_days = to_float(snap.get("rules", {}).get("maximum_holding_days", 180))
        tier_specs = [
            ("Nilai limit (patokan awal)", tiers.get("min_bid"), None, None, at, "LIMIT_REFERENCE", True),
            (f"Target ROI {policy_target_roi:.0f}%", tiers.get("mid_bid"), tiers.get("mid_economic_ceiling"), tiers.get("mid_simulated_ceiling"), tiers.get("mid_result"), policy_target_roi, tiers.get("mid_limit_feasible", False)),
            (f"Maximum bid / ROI minimum {policy_min_roi:.0f}%", tiers.get("max_bid"), tiers.get("max_economic_ceiling"), tiers.get("max_simulated_ceiling"), tiers.get("max_result"), policy_min_roi, tiers.get("max_limit_feasible", False)),
        ]
        cash_available_now = to_float(snap.get("liquidity", {}).get("cash_available_for_new_project"))
        auction_limit_now = to_float(snap["property"].get("auction_limit"))
        for label, bid, economic_ceiling, simulated_ceiling, res, hurdle, feasible in tier_specs:
            cash_need_tier = res.get("cash_requirement_including_reserve") if res else None
            if hurdle == "LIMIT_REFERENCE":
                tier_status = bid_reference_status(
                    res, policy_min_roi, policy_target_roi, policy_min_profit,
                    policy_target_days, policy_max_days, cash_need_tier,
                    cash_available_now, bool(tiers.get("provisional")),
                    bool(snap.get("liquidity", {}).get("cash_confirmed", False)),
                )
            elif not tiers.get("increment_confirmed"):
                tier_status = "INCREMENT RESMI BELUM DIKONFIRMASI — BELUM ADA BID LEGAL"
            elif bid is None or not feasible:
                reason_key = "mid_reason" if hurdle == policy_target_roi else "max_reason"
                tier_status = str(tiers.get(reason_key) or f"TIDAK ADA BID LEGAL YANG MEMENUHI ROI {hurdle:.0f}%")
            elif bid < auction_limit_now:
                # Defensive guard: an impossible sub-limit price must never be shown
                # as an actionable bid, even if an older snapshot has legacy values.
                tier_status = "TIDAK VALID — DI BAWAH LIMIT"
                bid = None
            elif cash_need_tier is not None and cash_need_tier > cash_available_now:
                tier_status = "KAS TIDAK CUKUP"
            elif not res or to_float(res.get("roi_pct"), -999) < hurdle or to_float(res.get("net_profit"), -999) < policy_min_profit or not (0 < to_float(res.get("projected_holding_days")) <= policy_max_days):
                tier_status = "GATE ROI, PROFIT MINIMUM, ATAU DURASI TIDAK TERPENUHI"
            elif tiers.get("provisional"):
                tier_status = "SIMULASI INDIKATIF — DATA PENDUKUNG BELUM FINAL"
            elif to_float(res.get("projected_holding_days")) > policy_target_days:
                tier_status = f"LAYAK PADA BATAS MINIMUM, TETAPI DURASI {to_float(res.get('projected_holding_days')):.0f} HARI DI ATAS TARGET IDEAL"
            else:
                tier_status = "LAYAK SECARA EKONOMI — SELURUH GATE TERPENUHI"
            tier_rows.append({
                "Tier": label,
                "Harga bid / nilai acuan": bid,
                "Ceiling teoritis di bawah limit (bukan harga bid)": economic_ceiling if bid is None else None,
                "Ceiling simulasi (increment belum resmi)": simulated_ceiling if not tiers.get("increment_confirmed") else None,
                "Total modal pada referensi": res.get("capital_before_sale") if res else None,
                "Kebutuhan kas + cadangan": cash_need_tier,
                "Profit bersih pada referensi": res.get("net_profit") if res else None,
                "ROI proyek all-in pada referensi": res.get("roi_pct") if res else None,
                "ROI tahunan ekuivalen (estimasi)": res.get("annualized_roi_pct") if res else None,
                "Durasi proyek (hari)": res.get("projected_holding_days") if res else None,
                "Status": tier_status,
            })
        st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True, column_config={
            "Harga bid / nilai acuan": st.column_config.NumberColumn(format="Rp %.0f"),
            "Ceiling teoritis di bawah limit (bukan harga bid)": st.column_config.NumberColumn(format="Rp %.0f"),
            "Ceiling simulasi (increment belum resmi)": st.column_config.NumberColumn(format="Rp %.0f"),
            "Total modal pada referensi": st.column_config.NumberColumn(format="Rp %.0f"),
            "Kebutuhan kas + cadangan": st.column_config.NumberColumn(format="Rp %.0f"),
            "Profit bersih pada referensi": st.column_config.NumberColumn(format="Rp %.0f"),
            "ROI proyek all-in pada referensi": st.column_config.NumberColumn(format="%.1f%%"),
            "ROI tahunan ekuivalen (estimasi)": st.column_config.NumberColumn(format="%.1f%%"),
        })
        st.caption("Bid legal selalu dimulai dari nilai limit dan mengikuti kelipatan resmi. Quick Sale ARV digunakan sebagai dasar hard-cap konservatif. Semua maximum bid harus memenuhi ROI minimum, profit bersih minimum, dan batas durasi.")
        scenario_caps = [
            {"Skenario ARV": "Quick Sale / konservatif", "ARV": mkt.get("conservative_exit"), "Maximum Bid": tiers.get("max_bid"), "Project ROI target (%)": tiers.get("max_roi_target"), "Profit minimum (Rp)": tiers.get("minimum_net_profit_required")},
            {"Skenario ARV": "Base ARV", "ARV": mkt.get("base_exit"), "Maximum Bid": tiers.get("base_case_max_bid"), "Project ROI target (%)": tiers.get("max_roi_target"), "Profit minimum (Rp)": tiers.get("minimum_net_profit_required")},
            {"Skenario ARV": "Upper ARV", "ARV": mkt.get("optimistic_exit"), "Maximum Bid": tiers.get("upper_case_max_bid"), "Project ROI target (%)": tiers.get("max_roi_target"), "Profit minimum (Rp)": tiers.get("minimum_net_profit_required")},
        ]
        st.markdown("#### Sensitivitas Maximum Bid berdasarkan ARV")
        st.dataframe(pd.DataFrame(scenario_caps), use_container_width=True, hide_index=True, column_config={"ARV": st.column_config.NumberColumn(format="Rp %.0f"), "Maximum Bid": st.column_config.NumberColumn(format="Rp %.0f"), "Profit minimum (Rp)": st.column_config.NumberColumn(format="Rp %.0f"), "Project ROI target (%)": st.column_config.NumberColumn(format="%.1f%%")})
        duration_days = to_float(at.get("projected_holding_days"))
        target_days = to_float(snap.get("rules", {}).get("target_holding_days", 90))
        max_days = to_float(snap.get("rules", {}).get("maximum_holding_days", 180))
        if duration_days > 0:
            status_duration = "On target" if duration_days <= target_days else ("Perlu evaluasi" if duration_days <= max_days else "Melewati batas maksimum")
            st.caption(f"Estimasi durasi pasca-menang/pelunasan sampai closing: {duration_days} hari · target {target_days:.0f} hari · maksimum {max_days:.0f} hari · status: {status_duration}.")
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
        market_cols[2].metric("Indeks kualitas data", f"{mkt.get('confidence', 0)}/100")
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
            with st.expander("Lihat seluruh comparable, penyesuaian dan dasar kualitas data", expanded=False):
                market_view = pd.DataFrame(mkt["valid"])
                preferred_market_cols = [c for c in ["name", "address", "price", "negotiated_price", "land_area", "building_area", "njop", "source_url", "source_url_scope", "date_found", "listing_date", "market_segment", "market_segment_factor", "distance_km", "distance_band", "proximity_score", "similarity_score", "missing_quality_fields", "subject_normalized_value", "market_to_njop_ratio"] if c in market_view.columns]
                st.dataframe(market_view[preferred_market_cols], use_container_width=True, hide_index=True)
        if mkt.get("invalid"):
            with st.expander("Listing yang belum dapat dihitung", expanded=False):
                st.dataframe(pd.DataFrame(mkt["invalid"]), use_container_width=True, hide_index=True)
        if mkt.get("secondary_only"):
            with st.expander("Referensi sekunder — tidak dicampur sebagai harga tunai", expanded=False):
                st.dataframe(pd.DataFrame(mkt["secondary_only"]), use_container_width=True, hide_index=True)
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
            {"Kelompok": "Renovasi", "Komponen": "Cadangan kondisi tersembunyi (interior belum diinspeksi)", "Nilai": at.get("hidden_condition_reserve")},
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
        # Portfolio appendix is assembled from the app's cached Sheets reads.
        # It is only embedded in the downloaded report and is not persisted in
        # ANALYSIS_HISTORY, keeping the underwriting snapshot compact.
        memo_snapshot = {**snap, "portfolio_context": build_memo_portfolio_context(snap.get("property_id", ""))}
        report = build_analysis_markdown(memo_snapshot)
        memo_docx = build_analysis_docx(memo_snapshot)
        memo_col1, memo_col2 = st.columns(2)
        with memo_col1:
            st.download_button("Unduh Memorandum Investasi (Word)", memo_docx, file_name=property_filename(memo_snapshot, "docx"), mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
        with memo_col2:
            st.download_button("Unduh Memorandum Investasi (Markdown)", report, file_name=property_filename(memo_snapshot, "md"), mime="text/markdown", use_container_width=True)
        st.caption("Memo menggunakan font minimum 11 pt, identitas KAYNA PROPERTY, tiga skenario bidding, RAB dan durasi per item, serta lampiran proyek aktif dan rekam jejak closing yang tersimpan. Data ekonomi makro tidak dimasukkan karena belum tersedia feed dinamis yang dapat diverifikasi saat pembuatan dokumen.")
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
                    elif existing_doc and snap.get("document_extraction"):
                        existing_extraction = parse_json(existing_doc.get("extraction_json"), {})
                        new_extraction = snap.get("document_extraction") or {}
                        if new_extraction.get("extraction_schema_version") == "AUCTION_EXTRACT_V2" and existing_extraction.get("extraction_schema_version") != "AUCTION_EXTRACT_V2":
                            upsert_record("DOCUMENTS", "document_id", {**existing_doc, "extraction_json": safe_json(new_extraction), "file_name": uploaded.name, "mime_type": uploaded.type, "source_url": source_link})
                for photo in _get_survey_photo_payloads():
                    photo_bytes = photo["bytes"]
                    photo_name = photo.get("name") or "survey-photo.jpg"
                    photo_mime_type = photo.get("mime_type") or "image/jpeg"
                    photo_digest = file_sha256(photo_bytes)
                    existing_photo = next((d for d in read_table("DOCUMENTS") if d.get("property_id") == propid and d.get("document_hash") == photo_digest), None)
                    if existing_photo: continue
                    photo_link = ""
                    photo_notes = "Foto hasil survei lapangan."
                    drive_folder_id = str(secret("DRIVE_FOLDER_ID", "") or "")
                    if drive_folder_id and service_info:
                        try:
                            drive_file = upload_file_to_drive(dict(service_info), drive_folder_id, photo_name, photo_mime_type, photo_bytes)
                            photo_link = drive_file.get("web_view_link", "")
                            photo_notes += f" Diarsipkan di Google Drive; file_id={drive_file.get('file_id')}."
                        except Exception as photo_exc:
                            photo_notes += f" Arsip Drive gagal: {photo_exc}; simpan manual bila diperlukan."
                            st.warning(photo_notes)
                    else:
                        photo_notes += " DRIVE_FOLDER_ID belum diatur; file binary tidak tersimpan permanen, hanya metadata dan hash."
                    append_record("DOCUMENTS", {"document_id": new_id("DOC"), "property_id": propid, "file_name": photo_name, "mime_type": photo_mime_type, "source_url": photo_link, "document_hash": photo_digest, "uploaded_at": iso_now(), "notes": photo_notes, "extraction_json": ""})
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
            onboard_payment_info = derive_payment_deadline(win_date=onboard_win_date.isoformat())
            st.caption(f"Informasi estimasi 5 hari kerja setelah menang: {_indonesian_date_label(onboard_payment_info['payment_deadline'])}. Bukan tenggat resmi; verifikasi ke KPKNL.")
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
        onboard_payment_info = derive_payment_deadline(win_date=onboard_win_date.isoformat())
        win_details = {"win_price": onboard_win_price, "win_date": onboard_win_date.isoformat(), "deposit_amount": onboard_deposit or None, "payment_deadline_info": onboard_payment_info["payment_deadline"], "payment_deadline_info_basis": onboard_payment_info["payment_deadline_basis"]}
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
elif page == "Market & Auction Data":
    st.markdown("<div class='hero'><h1>Explorer Properti & Database Hasil Lelang</h1><p>Telusuri data yang sudah tersimpan dengan filter dan pengurutan lokal. Hasil lelang yang dimenangkan pihak lain dapat disimpan sebagai referensi harga pasar.</p></div>", unsafe_allow_html=True)
    # Each worksheet is read once through the existing 5-minute Streamlit cache.
    # All filtering/sorting below runs in memory; changing a filter does not call Sheets again.
    saved_properties = list_properties()
    auction_outcomes = read_table("AUCTION_OUTCOMES")
    explore_tab, outcome_tab = st.tabs(["Data objek tersimpan", "Database hasil lelang"])
    with explore_tab:
        if not saved_properties:
            st.info("Belum ada data properti tersimpan.")
        else:
            explore_rows = []
            for prop in saved_properties:
                prop_payload = record_payload(prop)
                latest = prop_payload.get("latest_analysis") if isinstance(prop_payload.get("latest_analysis"), dict) else {}
                market_data = latest.get("market") if isinstance(latest.get("market"), dict) else {}
                at_data = latest.get("at_limit") if isinstance(latest.get("at_limit"), dict) else {}
                explore_rows.append({
                    "Property ID": prop.get("property_id"), "Nama properti": prop.get("name"), "Kode lot": prop.get("lot_code"),
                    "Alamat": prop.get("address"), "Status perjalanan": prop.get("lifecycle_status"), "Keputusan": prop.get("decision_status"),
                    "Tanggal lelang": prop.get("auction_date"), "Nilai limit": to_float(prop.get("auction_limit")),
                    "ARV dasar": to_float(market_data.get("base_exit")), "ARV konservatif": to_float(market_data.get("conservative_exit")),
                    "ROI pada limit (%)": to_float(at_data.get("roi_pct")), "Diubah": prop.get("updated_at"),
                })
            frame = pd.DataFrame(explore_rows)
            f1, f2, f3 = st.columns(3)
            status_values = ["Semua"] + sorted(x for x in frame["Status perjalanan"].dropna().astype(str).unique() if x)
            decision_values = ["Semua"] + sorted(x for x in frame["Keputusan"].dropna().astype(str).unique() if x)
            selected_status = f1.selectbox("Filter status", status_values, key="explorer_status")
            selected_decision = f2.selectbox("Filter keputusan", decision_values, key="explorer_decision")
            search_text = f3.text_input("Cari nama / alamat / lot", key="explorer_search")
            f4, f5 = st.columns(2)
            sort_label = f4.selectbox("Urutkan berdasarkan", ["Tanggal terdekat dari hari ini", "Tanggal paling jauh dari hari ini", "Tanggal lelang paling awal", "Tanggal lelang paling akhir", "Nilai limit termurah", "Nilai limit termahal", "ARV dasar tertinggi", "ROI tertinggi", "Update terbaru"], key="explorer_sort")
            minimum_price = f5.number_input("Limit minimum (Rp, 0 = semua)", min_value=0, step=10_000_000, value=0, key="explorer_min_limit")
            if selected_status != "Semua": frame = frame[frame["Status perjalanan"] == selected_status]
            if selected_decision != "Semua": frame = frame[frame["Keputusan"] == selected_decision]
            if search_text.strip():
                mask = frame[["Nama properti", "Kode lot", "Alamat"]].fillna("").astype(str).apply(lambda col: col.str.contains(search_text.strip(), case=False, regex=False)).any(axis=1)
                frame = frame[mask]
            if minimum_price > 0: frame = frame[frame["Nilai limit"] >= minimum_price]
            frame["_auction_dt"] = pd.to_datetime(frame["Tanggal lelang"], errors="coerce")
            frame["_updated_dt"] = pd.to_datetime(frame["Diubah"], errors="coerce")
            today_ts = pd.Timestamp(jakarta_today())
            frame["_distance"] = (frame["_auction_dt"] - today_ts).abs().dt.days
            if sort_label == "Tanggal terdekat dari hari ini":
                frame = frame.sort_values(["_distance", "_auction_dt"], ascending=[True, True], na_position="last")
            elif sort_label == "Tanggal paling jauh dari hari ini":
                frame = frame.sort_values("_distance", ascending=False, na_position="last")
            elif sort_label == "Tanggal lelang paling awal": frame = frame.sort_values("_auction_dt", ascending=True, na_position="last")
            elif sort_label == "Tanggal lelang paling akhir": frame = frame.sort_values("_auction_dt", ascending=False, na_position="last")
            elif sort_label == "Nilai limit termurah": frame = frame.sort_values("Nilai limit", ascending=True)
            elif sort_label == "Nilai limit termahal": frame = frame.sort_values("Nilai limit", ascending=False)
            elif sort_label == "ARV dasar tertinggi": frame = frame.sort_values("ARV dasar", ascending=False)
            elif sort_label == "ROI tertinggi": frame = frame.sort_values("ROI pada limit (%)", ascending=False)
            else: frame = frame.sort_values("_updated_dt", ascending=False, na_position="last")
            visible_cols = ["Nama properti", "Kode lot", "Alamat", "Status perjalanan", "Keputusan", "Tanggal lelang", "Nilai limit", "ARV dasar", "ARV konservatif", "ROI pada limit (%)"]
            st.caption(f"Menampilkan {len(frame)} dari {len(explore_rows)} objek. Filter dan pengurutan dilakukan lokal dari data cache; tidak menambah pemanggilan Google Sheets untuk setiap perubahan filter.")
            st.dataframe(frame[visible_cols], use_container_width=True, hide_index=True, column_config={
                "Nilai limit": st.column_config.NumberColumn(format="Rp %.0f"), "ARV dasar": st.column_config.NumberColumn(format="Rp %.0f"),
                "ARV konservatif": st.column_config.NumberColumn(format="Rp %.0f"), "ROI pada limit (%)": st.column_config.NumberColumn(format="%.1f%%"),
            })
            st.download_button("Unduh hasil filter CSV", frame[visible_cols].to_csv(index=False).encode("utf-8-sig"), "pfms-property-explorer.csv", "text/csv")
    with outcome_tab:
        st.markdown("### Catat hasil lelang, termasuk bila dimenangkan peserta lain")
        property_link_options = {"Tidak ditautkan ke objek tersimpan": None}
        for prop in saved_properties:
            property_link_options[f"{prop.get('name') or 'Properti'} · {prop.get('lot_code') or prop.get('property_id')}"] = prop
        linked_label = st.selectbox("Hubungkan ke objek tersimpan (opsional)", list(property_link_options.keys()), key="auction_result_link")
        linked = property_link_options[linked_label]
        with st.form("auction_outcome_capture_form"):
            a1, a2, a3 = st.columns(3)
            with a1:
                result_name = st.text_input("Nama properti", value=str((linked or {}).get("name") or ""))
                result_lot = st.text_input("Kode lot / nomor objek", value=str((linked or {}).get("lot_code") or ""))
                result_address = st.text_input("Alamat / perumahan", value=str((linked or {}).get("address") or ""))
            with a2:
                result_auction_date = st.date_input("Tanggal lelang", value=as_date((linked or {}).get("auction_date")))
                result_limit = st.number_input("Nilai limit (Rp)", min_value=0, step=1_000_000, value=safe_int((linked or {}).get("auction_limit", 0)))
                result_status = st.selectbox("Hasil lelang", OUTCOME_STATUSES)
            with a3:
                result_price = st.number_input("Harga menang / penawaran tertinggi (Rp)", min_value=0, step=1_000_000, value=0, help="Masukkan 0 hanya bila tidak ada harga yang diketahui atau lelang dibatalkan.")
                result_price_type = st.selectbox("Jenis harga", [""] + PRICE_TYPES)
                result_source_grade = st.selectbox("Kualitas sumber", SOURCE_GRADES)
            result_url = st.text_input("URL bukti hasil lelang (opsional)")
            result_note = st.text_area("Catatan / kutipan bukti (tanpa data pribadi pemenang)", height=80)
            result_confirm = st.checkbox("Saya sudah memeriksa harga, tanggal, status dan sumber hasil lelang.")
            save_outcome = st.form_submit_button("Simpan hasil lelang sebagai referensi", type="primary")
        if save_outcome:
            if not result_confirm:
                st.warning("Konfirmasi pemeriksaan data terlebih dahulu.")
            else:
                try:
                    existing_match = next((r for r in auction_outcomes if (linked and str(r.get("property_id")) == str(linked.get("property_id")) and str(r.get("auction_date"))[:10] == result_auction_date.isoformat()) or (not linked and str(r.get("lot_code", "")).strip().lower() == result_lot.strip().lower() and result_lot.strip() and str(r.get("auction_date"))[:10] == result_auction_date.isoformat())), None)
                    rec = build_auction_outcome_record(
                        property_id=(linked or {}).get("property_id", ""), property_name=result_name, lot_code=result_lot, address=result_address,
                        auction_date=result_auction_date.isoformat(), auction_limit=result_limit, outcome_status=result_status,
                        winning_price=result_price, price_type=result_price_type, source_grade=result_source_grade, source_url=result_url, source_note=result_note,
                        outcome_id=(existing_match or {}).get("outcome_id"),
                    )
                    upsert_record("AUCTION_OUTCOMES", "outcome_id", rec)
                    log_event("AUCTION_OUTCOME", rec["outcome_id"], "UPSERTED", {"property_id": rec["property_id"], "outcome_status": rec["outcome_status"], "winning_price": rec["winning_price"], "source_grade": rec["source_grade"]})
                    st.success("Hasil lelang tersimpan. Data dapat dipakai sebagai referensi historis tanpa mengubah status proyek/prospek terkait.")
                    cached_read.clear(); st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        st.markdown("### Riwayat harga hasil lelang")
        if auction_outcomes:
            outcome_frame = pd.DataFrame(auction_outcomes)
            status_filter = st.selectbox("Filter hasil", ["Semua"] + sorted(outcome_frame["outcome_status"].dropna().astype(str).unique().tolist()), key="auction_outcome_status_filter")
            sort_result = st.selectbox("Urutkan hasil", ["Tanggal terbaru", "Tanggal terlama", "Harga menang termurah", "Harga menang tertinggi"], key="auction_outcome_sort")
            if status_filter != "Semua": outcome_frame = outcome_frame[outcome_frame["outcome_status"] == status_filter]
            outcome_frame["_date"] = pd.to_datetime(outcome_frame["auction_date"], errors="coerce")
            outcome_frame["_price"] = pd.to_numeric(outcome_frame["winning_price"], errors="coerce")
            if sort_result == "Tanggal terbaru": outcome_frame = outcome_frame.sort_values("_date", ascending=False, na_position="last")
            elif sort_result == "Tanggal terlama": outcome_frame = outcome_frame.sort_values("_date", ascending=True, na_position="last")
            elif sort_result == "Harga menang termurah": outcome_frame = outcome_frame.sort_values("_price", ascending=True, na_position="last")
            else: outcome_frame = outcome_frame.sort_values("_price", ascending=False, na_position="last")
            show_cols = [c for c in ["property_name", "lot_code", "address", "auction_date", "auction_limit", "outcome_status", "winning_price", "price_type", "source_grade", "source_url", "source_note"] if c in outcome_frame.columns]
            st.dataframe(outcome_frame[show_cols], use_container_width=True, hide_index=True, column_config={"auction_limit": st.column_config.NumberColumn("Limit", format="Rp %.0f"), "winning_price": st.column_config.NumberColumn("Harga menang / tertinggi", format="Rp %.0f")})
            st.download_button("Unduh database hasil lelang CSV", outcome_frame[show_cols].to_csv(index=False).encode("utf-8-sig"), "pfms-auction-outcomes.csv", "text/csv")
        else:
            st.info("Belum ada hasil lelang yang dicatat. Anda dapat menyimpan harga pemenang lain sebagai referensi sekalipun Anda tidak menang.")

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
        committed_total = ledger["committed_project_cost_total"]
        forecast_total = ledger["forecast_project_cost_total"]
        selling_committed = ledger.get("committed_selling_total", 0.0)
        selling_forecast = ledger.get("forecast_selling_total", 0.0)
        selling_budget = sum(to_float(x.get("budget_amount")) for x in project_budget_rows if str(x.get("category") or "").strip().lower() in {"penjualan", "selling", "biaya penjualan", "pajak penjualan", "komisi agen"})
        projected_completion = ledger["project_cost_at_completion_ex_selling"]
        if not project_budget_rows and estimate_capital > actual_project_cost:
            fallback_remaining = max(0.0, estimate_capital - actual_project_cost)
            projected_completion = estimate_capital
        else:
            fallback_remaining = 0.0
        stage_now = payload.get("project_stage", "Settlement")
        st.markdown(f"### {p.get('name')} · {p.get('address') or 'Alamat belum diisi'}")

        # Schedule estimate is based on the saved RAB quantities. If the original
        # analysis is unavailable, fall back to renovation budget items without
        # inventing measured quantities.
        schedule_items = []
        latest_costs_for_schedule = latest.get("costs", {}) if isinstance(latest.get("costs"), dict) else {}
        schedule_items = [x for x in latest_costs_for_schedule.get("renovation_items", []) if isinstance(x, dict)]
        if not schedule_items:
            for budget_row in project_budget_rows:
                if str(budget_row.get("category") or "").strip().lower() != "renovasi":
                    continue
                row_payload = budget_row.get("payload") if isinstance(budget_row.get("payload"), dict) else parse_json(budget_row.get("payload_json"), {})
                if str(row_payload.get("baseline_key") or "").upper().find("CONTINGENCY") >= 0 or "cadangan" in str(budget_row.get("description") or "").lower():
                    continue
                schedule_items.append({"work_item": budget_row.get("description"), "quantity": row_payload.get("quantity"), "unit": row_payload.get("unit")})
        schedule_estimate = estimate_renovation_duration(schedule_items) if schedule_items else {"available": False}
        with st.expander("Estimasi durasi renovasi otomatis", expanded=False):
            if schedule_estimate.get("available"):
                dfast, dbase, dslow = st.columns(3)
                dfast.metric("Cepat", f"{schedule_estimate['calendar_days']['fast']} hari kalender")
                dbase.metric("Dasar", f"{schedule_estimate['calendar_days']['base']} hari kalender")
                dslow.metric("Konservatif", f"{schedule_estimate['calendar_days']['slow']} hari kalender")
                st.dataframe(pd.DataFrame(schedule_estimate.get("phases", [])), use_container_width=True, hide_index=True, column_config={
                    "fast_days": st.column_config.NumberColumn("Cepat (hari kerja)", format="%.1f"),
                    "base_days": st.column_config.NumberColumn("Dasar (hari kerja)", format="%.1f"),
                    "slow_days": st.column_config.NumberColumn("Konservatif (hari kerja)", format="%.1f"),
                })
                st.caption(f"Asumsi: {schedule_estimate['crew_assumption']} Kalender memakai {schedule_estimate['working_days_per_week']} hari kerja/minggu dan buffer {schedule_estimate['buffer_pct']:.0f}%. Tidak termasuk waktu tunggu material, cuaca, izin, perubahan lingkup, atau keterlambatan vendor.")
                if schedule_estimate.get("unmapped_items"):
                    st.warning(f"{schedule_estimate['unmapped_items']} item belum dikenali jenis pekerjaannya dan memakai allowance umum. Periksa kembali klasifikasi serta volumenya.")
            else:
                st.info("Durasi belum dapat dihitung karena daftar item/volume renovasi belum tersedia. Lengkapi BoQ atau rincian budget pekerjaan renovasi.")

        # User-editable target date: use initial underwriting holding estimate as a
        # suggestion only; do not activate overdue alerts until the user saves it.
        stored_target = None
        try:
            stored_target = date.fromisoformat(str(payload.get("planned_sale_date") or "")[:10])
        except (TypeError, ValueError):
            stored_target = None
        suggested_target = None
        try:
            start_for_target = date.fromisoformat(str(win.get("win_date") or "")[:10])
            planned_months = to_float((latest.get("at_limit") or {}).get("holding_months", active_estimate.get("holding_months", 0)))
            if planned_months > 0:
                suggested_target = start_for_target + timedelta(days=round(planned_months * 30.44))
        except (TypeError, ValueError):
            suggested_target = None
        target_picker_default = stored_target or suggested_target or date.today()
        with st.expander("Target waktu penjualan & pengingat", expanded=not bool(stored_target)):
            with st.form(f"planned_sale_target_form_{pid}"):
                target_enabled = st.checkbox("Aktifkan target tanggal properti terjual", value=bool(stored_target), key=f"planned_sale_enabled_{pid}")
                planned_sale_input = st.date_input("Target tanggal closing/terjual", value=target_picker_default, disabled=not target_enabled, key=f"planned_sale_date_picker_{pid}")
                if suggested_target and not stored_target:
                    st.caption(f"Saran awal dari holding pada analisis pra-lelang: {suggested_target.isoformat()}. Anda dapat mengubah tanggal ini sesuai rencana aktual.")
                save_sale_target = st.form_submit_button("Simpan target penjualan")
            if save_sale_target:
                if target_enabled:
                    payload["planned_sale_date"] = planned_sale_input.isoformat()
                    payload["planned_sale_target_source"] = "USER_CONFIRMED"
                else:
                    payload.pop("planned_sale_date", None)
                    payload.pop("planned_sale_target_source", None)
                upsert_record("PROPERTIES", "property_id", {**p, "updated_at": iso_now(), "payload": payload})
                log_event("PROPERTY", pid, "SALE_TARGET_UPDATED", {"planned_sale_date": payload.get("planned_sale_date")})
                cached_read.clear(); st.rerun()
        current_target_date = stored_target

        origin = payload.get("project_origin") or payload.get("project_onboarding", {}).get("onboarding_version")
        if origin == "PROJECT_ONBOARDING":
            st.caption("Asal data: Project Onboarding · Proyek sudah diperoleh sebelum/di luar alur analisis baru PFMS. Keputusan INCOMPLETE pada onboarding tidak berarti aset belum dimenangkan.")

        # A pre-bid analysis is an immutable historical decision snapshot. It is
        # not the active project's current cash position or a lifecycle blocker.
        baseline_meta = payload.get("opening_budget_baseline") if isinstance(payload.get("opening_budget_baseline"), dict) else {}
        baseline_rows_exist = any(
            (x.get("payload") or {}).get("entry_source") == "PRE_BID_ANALYSIS_BASELINE"
            if isinstance(x.get("payload"), dict) else parse_json(x.get("payload_json"), {}).get("entry_source") == "PRE_BID_ANALYSIS_BASELINE"
            for x in project_budget_rows
        )
        if latest and not baseline_rows_exist:
            if not project_budget_rows:
                with st.container(border=True):
                    st.markdown("**Anggaran awal dari hasil analisis pra-lelang belum dibuat**")
                    st.caption("PFMS dapat memindahkan anggaran hasil analisis ke baseline proyek aktif. Harga perolehan akan dihitung ulang memakai harga menang, bukan limit lelang. Snapshot keputusan awal tidak diubah.")
                    if st.button("Buat baseline anggaran dari analisis pra-lelang", key=f"seed_opening_budget_{pid}", type="primary"):
                        seed_result = seed_opening_budget_for_won_property(p, winning_price)
                        if seed_result.get("seeded", 0) > 0 or seed_result.get("rows"):
                            st.success(f"Baseline anggaran dibuat: {seed_result.get('seeded', 0)} item. Harga perolehan yang digunakan {idr(winning_price)}.")
                            if seed_result.get("pending_pricing_items"):
                                st.warning("Ada item RAB yang belum memiliki harga satuan: " + "; ".join(seed_result["pending_pricing_items"][:8]))
                        else:
                            st.warning(seed_result.get("reason", "Baseline belum dapat dibuat."))
                        cached_read.clear(); st.rerun()
            else:
                st.warning("Sudah ada anggaran manual/Project Onboarding. Baseline analisis tidak digabung otomatis agar tidak menggandakan biaya. Bandingkan anggaran manual dengan snapshot analisis sebelum melakukan rekonsiliasi.")

        if latest:
            with st.expander("Riwayat keputusan underwriting pra-lelang (arsip historis)", expanded=False):
                prebid_decision = latest.get("decision", {}) if isinstance(latest.get("decision"), dict) else {}
                prebid_liquidity = latest.get("liquidity", {}) if isinstance(latest.get("liquidity"), dict) else {}
                prebid_at_limit = latest.get("at_limit", {}) if isinstance(latest.get("at_limit"), dict) else {}
                prebid_cash = baseline_meta.get("pre_bid_cash_available", prebid_liquidity.get("cash_available_for_new_project"))
                st.caption(f"Analisis dibuat: {latest.get('analyzed_at', '—')} · Keputusan saat itu: {baseline_meta.get('pre_bid_decision_status') or prebid_decision.get('status') or p.get('decision_status', '—')}")
                pc1, pc2, pc3 = st.columns(3)
                pc1.metric("Kas siap investasi saat pra-lelang", idr(prebid_cash))
                pc2.metric("Kebutuhan kas pada limit saat pra-lelang", idr(prebid_at_limit.get("cash_requirement_including_reserve")))
                pc3.metric("Modal proyek pada limit awal", idr(prebid_at_limit.get("capital_before_sale")))
                st.caption(f"Anggaran baseline proyek aktif dihitung ulang memakai harga menang {idr(winning_price)} (bukan nilai limit {idr((latest.get('property') or {}).get('auction_limit', p.get('auction_limit')))}). Harga menang digunakan untuk menghitung ulang bea lelang dan BPHTB.")
                if prebid_decision.get("summary"):
                    st.write(prebid_decision["summary"])
                if prebid_decision.get("blockers"):
                    st.markdown("**Blocker yang tercatat sebelum bidding**")
                    for blocker in prebid_decision.get("blockers", []):
                        st.write(f"• {blocker}")
                st.info("Ini adalah catatan keputusan dan posisi kas pada saat sebelum lelang. Status HOLD tetap disimpan sebagai audit, tetapi tidak menghalangi pengelolaan proyek yang sudah dimenangkan. Posisi kas saat ini harus diperbarui melalui menu Investor Cashflow; jangan memakai angka pra-lelang sebagai saldo sekarang.")
        if baseline_meta:
            if baseline_meta.get("pending_pricing_items"):
                st.warning("Baseline anggaran berasal dari analisis awal tetapi masih parsial. Item tanpa harga: " + "; ".join(baseline_meta.get("pending_pricing_items", [])[:8]))
            for baseline_warning in baseline_meta.get("baseline_warnings", []):
                st.warning(baseline_warning)
            if baseline_meta.get("risk_reserves_not_budgeted"):
                reserves = baseline_meta.get("risk_reserves_not_budgeted", {})
                reserve_total = to_float(reserves.get("possession_risk_reserve")) + to_float(reserves.get("general_risk_reserve"))
                if reserve_total > 0:
                    st.caption(f"Cadangan risiko pra-lelang yang dicatat terpisah dari budget: {idr(reserve_total)}. Cadangan bukan pengeluaran aktual.")
        current_cash_profile, _current_cash_events, current_liquidity = get_cash_data()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total aktual dibayar", idr(ledger["actual_paid_total"]))
        k2.metric("Komitmen biaya proyek", idr(committed_total))
        k3.metric("Forecast biaya proyek tersisa", idr(forecast_total if project_budget_rows else fallback_remaining))
        completion_label = "Proyeksi modal sementara*" if baseline_meta and (not baseline_meta.get("baseline_complete", False) or baseline_meta.get("pending_pricing_items")) else "Proyeksi modal s.d. siap dijual"
        k4.metric(completion_label, idr(projected_completion), help="Aktual biaya proyek + komitmen + forecast pekerjaan tersisa; tidak termasuk biaya penjualan dan cadangan risiko yang belum terpakai. Jika baseline RAB masih memiliki harga/volume kosong, angka ini sementara dan berpotensi lebih rendah dari modal akhir.")
        if completion_label.endswith("*"):
            st.caption("*Proyeksi masih parsial karena ada item RAB awal yang belum terharga/terukur. Lengkapi baseline atau forecast di tabel anggaran sebelum memakai angka ini untuk keputusan baru.")
        st.caption(f"Harga menang/perolehan tercatat: {idr(winning_price)} · Tahap proyek: {stage_now} · Budget biaya penjualan terpisah {idr(selling_budget)} (komitmen {idr(selling_committed)}; forecast {idr(selling_forecast)}).")
        st.caption(f"Kas siap investasi portofolio saat ini: {idr(current_liquidity.get('cash_available_for_new_project'))}. Ini posisi kas terakhir yang Anda input pada Investor Cashflow, bukan angka snapshot pra-lelang. Perbarui saldo setelah pembayaran akuisisi/renovasi agar angka tetap sesuai rekening nyata; PFMS tidak mengakses rekening bank otomatis.")

        st.markdown("### 1. Posisi anggaran dan realisasi")
        project_progress_milestones = [m for m in read_table("PROJECT_MILESTONES") if str(m.get("property_id") or "") == str(pid)]
        project_progress_summary = calculate_project_work_progress(project_budget_rows, project_progress_milestones)
        if project_progress_summary.get("progress_pct") is not None:
            progress_value = max(0.0, min(100.0, float(project_progress_summary["progress_pct"])))
            coverage = project_progress_summary.get("coverage_pct", 0.0)
            st.progress(progress_value / 100.0, text=f"Progres renovasi berbobot: {progress_value:.0f}%")
            st.caption(f"Pembaruan progres tersedia untuk {project_progress_summary.get('tracked_work_items', 0)} dari {project_progress_summary.get('total_work_items', 0)} item. Data yang belum diperbarui diperlakukan 0% untuk perhitungan progres minimum; cakupan data saat ini {coverage:.0f}%.")
        else:
            st.info("Item renovasi sudah tersedia, tetapi progres fisik belum dicatat. Perbarui Status fisik pekerjaan dan persentasenya pada formulir Edit item anggaran. Sistem tidak menyimpulkan progres dari jumlah uang yang sudah dibayar.")
        if project_budget_rows:
            budget_display = pd.DataFrame(ledger["budget_lines"])
            if not budget_display.empty:
                progress_by_budget = {}
                for budget_row in project_budget_rows:
                    progress_payload = budget_payload(budget_row)
                    work_status = str(progress_payload.get("work_status") or ("Selesai" if str(budget_row.get("status") or "").lower() == "completed" else "Belum diperbarui"))
                    progress_value = progress_payload.get("work_progress_pct")
                    if progress_value in (None, "") and work_status == "Selesai":
                        progress_value = 100
                    if progress_value in (None, "") and work_status == "Belum mulai":
                        progress_value = 0
                    progress_by_budget[str(budget_row.get("budget_item_id") or "")] = f"{safe_int(progress_value)}% · {work_status}" if progress_value not in (None, "") else work_status
                if "budget_item_id" in budget_display.columns:
                    budget_display["progres_fisik"] = budget_display["budget_item_id"].astype(str).map(progress_by_budget).fillna("Belum diperbarui")
                st.dataframe(budget_display, use_container_width=True, hide_index=True, column_config={
                    "budget_amount": st.column_config.NumberColumn("Budget total", format="Rp %.0f"),
                    "actual_paid": st.column_config.NumberColumn("Sudah dibayar", format="Rp %.0f"),
                    "committed_unpaid": st.column_config.NumberColumn("Komitmen belum dibayar", format="Rp %.0f"),
                    "forecast_remaining": st.column_config.NumberColumn("Forecast tersisa", format="Rp %.0f"),
                    "expected_at_completion": st.column_config.NumberColumn("Estimasi akhir", format="Rp %.0f"),
                    "variance_at_completion": st.column_config.NumberColumn("Sisa budget / (overrun)", format="Rp %.0f"),
                })
            project_budget_total = sum(to_float(x.get("budget_amount")) for x in project_budget_rows if str(x.get("category") or "").strip().lower() not in {"penjualan", "selling", "biaya penjualan", "pajak penjualan", "komisi agen"})
            st.caption(f"Budget biaya proyek sampai siap jual: {idr(project_budget_total)} · Actual paid proyek: {idr(ledger['actual_project_cost'])} · Komitmen proyek: {idr(committed_total)} · Forecast proyek: {idr(forecast_total)}. Budget penjualan {idr(selling_budget)} dicatat terpisah.")
            budget_cta = assess_project_alerts(today=jakarta_today(), target_sale_date=current_target_date, is_sold=False, budget_total=project_budget_total, projected_completion=projected_completion)
            b1, b2, b3 = st.columns(3)
            b1.metric("Budget sampai siap jual", idr(project_budget_total))
            b2.metric("Proyeksi biaya akhir", idr(projected_completion))
            b3.metric("Sisa budget / (overrun)", idr(budget_cta.get("budget_remaining")), help="Budget dikurangi proyeksi biaya akhir. Positif berarti masih ada sisa; negatif berarti proyeksi melewati budget.")
            if budget_cta.get("budget_remaining") is not None:
                if budget_cta["budget_remaining"] < 0:
                    st.error(f"Budget terlampaui: proyeksi biaya lebih tinggi {idr(abs(budget_cta['budget_remaining']))} dari budget yang disetujui.")
                elif budget_cta.get("budget_usage_pct", 0) >= 85:
                    st.warning(f"Anggaran mendekati batas: {budget_cta['budget_usage_pct']:.1f}% sudah terpakai oleh proyeksi. Tinjau pekerjaan tambahan sebelum membuat komitmen baru.")
                elif budget_cta.get("budget_usage_pct", 0) >= 70:
                    st.info(f"Pemantauan budget: proyeksi sudah {budget_cta['budget_usage_pct']:.1f}% dari budget.")
            if ledger.get("unlinked_actual_cost", 0) > 0:
                st.warning(f"Ada {idr(ledger['unlinked_actual_cost'])} realisasi yang belum ditautkan ke item budget. Jika transaksi tersebut sebenarnya merupakan pembayaran atas pekerjaan yang sudah masuk forecast/komitmen, buka 'Koreksi transaksi yang sudah tercatat', tautkan ke item budget yang sesuai, lalu pilih sumber pembayaran yang benar. Jika memang pekerjaan tambahan di luar budget, biarkan tidak tertaut. Transaksi yang seharusnya mengurangi forecast tetapi dibiarkan tidak tertaut dapat membuat proyeksi biaya akhir terlihat terlalu tinggi.")
        elif active_estimate:
            st.info("Belum ada rincian budget/komitmen per item. Angka perkiraan sisa di atas berasal dari snapshot underwriting lama. Tambahkan budget tiap pekerjaan di bawah agar laporan Budget vs Actual lebih akurat.")
            bva = budget_actual_table(active_estimate, active_actual_rows)
            st.dataframe(bva, use_container_width=True, hide_index=True, column_config={"Anggaran": st.column_config.NumberColumn(format="Rp %.0f"), "Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "Varians (Aktual - Anggaran)": st.column_config.NumberColumn(format="Rp %.0f")})
        else:
            st.warning("Belum ada budget per item. Isi anggaran dan forecast sisa pekerjaan agar total biaya sampai selesai dapat dihitung dari kondisi proyek yang sebenarnya.")

        # Sale-date reminders are independent of budget-row availability. A project
        # may have a confirmed target sale date before a detailed project budget is built.
        if current_target_date:
            sale_cta = assess_project_alerts(today=jakarta_today(), target_sale_date=current_target_date, is_sold=False, budget_total=0, projected_completion=0)
            for alert in sale_cta.get("alerts", []):
                if alert["severity"] == "critical": st.error(f"{alert['title']}. {alert['action']}")
                else: st.warning(f"{alert['title']}. {alert['action']}")
        else:
            st.caption("Pengingat keterlambatan penjualan belum aktif. Tetapkan target tanggal penjualan di bagian Target waktu penjualan & pengingat.")

        st.markdown("### 2. Perbarui progres proyek")
        with st.form("win_update_form_v110"):
            c1, c2, c3 = st.columns(3)
            with c1:
                win_price = st.number_input("Harga menang / perolehan (Rp)", min_value=0, step=1_000_000, value=safe_int(win.get("win_price", prop_data.get("auction_limit", 0))))
            with c2:
                try: win_date_default = date.fromisoformat(str(win.get("win_date") or date.today().isoformat())[:10])
                except ValueError: win_date_default = date.today()
                win_date = st.date_input("Tanggal menang / perolehan", value=win_date_default)
                win_payment_info = derive_payment_deadline(win_date=win_date.isoformat())
                st.caption(f"Informasi estimasi pelunasan 5 hari kerja: {_indonesian_date_label(win_payment_info['payment_deadline'])}. Bukan tenggat resmi; periksa pengumuman/konfirmasi KPKNL.")
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
            win_payment_info = derive_payment_deadline(win_date=win_date.isoformat())
            payload["win_details"] = {**win, "win_price": win_price, "win_date": win_date.isoformat(), "payment_deadline_info": win_payment_info["payment_deadline"], "payment_deadline_info_basis": win_payment_info["payment_deadline_basis"]}
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
        budget_by_id = {}
        for budget in project_budget_rows:
            if str(budget.get("status") or "Active") not in {"Cancelled", "Archived"}:
                choice_label = f"{budget.get('category')} · {budget.get('subcategory') or 'Umum'} · {budget.get('description')} · {budget.get('budget_item_id')}"
                budget_choices[choice_label] = str(budget.get("budget_item_id"))
                budget_by_id[str(budget.get("budget_item_id"))] = budget
        link_key = f"actual_budget_link_{pid}"
        source_key = f"actual_payment_source_{pid}"

        def _suggest_payment_source_for_selected_budget() -> None:
            selected_label_now = st.session_state.get(link_key, "(Tidak ditautkan ke item budget)")
            selected_id_now = budget_choices.get(selected_label_now, "")
            selected_budget_now = budget_by_id.get(selected_id_now, {})
            if to_float(selected_budget_now.get("forecast_remaining")) > 0:
                st.session_state[source_key] = "Pembayaran dari forecast"
            elif to_float(selected_budget_now.get("committed_unpaid")) > 0:
                st.session_state[source_key] = "Pembayaran atas komitmen"
            else:
                st.session_state[source_key] = "Pengeluaran di luar budget"

        if link_key not in st.session_state:
            st.session_state[link_key] = "(Tidak ditautkan ke item budget)"
        if source_key not in st.session_state:
            st.session_state[source_key] = "Pengeluaran di luar budget"
        linked_budget_label = st.selectbox("Tautkan pembayaran ke item anggaran (opsional)", list(budget_choices.keys()), key=link_key, on_change=_suggest_payment_source_for_selected_budget)
        payment_source = st.selectbox("Pembayaran ini mengurangi", ["Pengeluaran di luar budget", "Pembayaran atas komitmen", "Pembayaran dari forecast"], key=source_key, help="Jika Anda memilih item anggaran, sistem otomatis menyarankan pengurangan forecast atau komitmen yang masih tersedia. Periksa kembali sebelum menyimpan.")
        with st.form(f"actual_cost_form_v111_{pid}"):
            a1, a2 = st.columns(2)
            with a1:
                txdate = st.date_input("Tanggal pembayaran", value=date.today(), key=f"actual_txdate_{pid}")
                amount = st.number_input("Nominal yang sudah dibayar (Rp)", min_value=0, step=500_000, key=f"actual_amount_{pid}")
                vendor = st.text_input("Penerima / vendor", placeholder="Nama toko, tukang, kontraktor, instansi", key=f"actual_vendor_{pid}")
            with a2:
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
        st.caption("Progres fisik tiap pekerjaan dapat diperbarui pada formulir edit item anggaran. Persentase proyek dihitung berbobot estimasi hari kerja per item; pembayaran tidak dianggap bukti pekerjaan selesai. Item yang belum diperbarui ditampilkan sebagai cakupan data yang belum lengkap.")
        st.caption("Tabel berikut hanya untuk melihat data. Untuk menambah atau mengubah angka, gunakan formulir di bawah. Budget adalah batas/rencana biaya; komitmen adalah kewajiban yang sudah disepakati; forecast adalah biaya tersisa yang belum dikomitmen.")
        if project_budget_rows:
            budget_display = pd.DataFrame(ledger["budget_lines"])
            if not budget_display.empty:
                progress_by_budget = {}
                for budget_row in project_budget_rows:
                    progress_payload = budget_payload(budget_row)
                    work_status = str(progress_payload.get("work_status") or ("Selesai" if str(budget_row.get("status") or "").lower() == "completed" else "Belum diperbarui"))
                    progress_value = progress_payload.get("work_progress_pct")
                    if progress_value in (None, "") and work_status == "Selesai":
                        progress_value = 100
                    if progress_value in (None, "") and work_status == "Belum mulai":
                        progress_value = 0
                    progress_by_budget[str(budget_row.get("budget_item_id") or "")] = f"{safe_int(progress_value)}% · {work_status}" if progress_value not in (None, "") else work_status
                if "budget_item_id" in budget_display.columns:
                    budget_display["progres_fisik"] = budget_display["budget_item_id"].astype(str).map(progress_by_budget).fillna("Belum diperbarui")
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
                            edit_status = st.selectbox("Status anggaran", ["Active", "Completed", "Archived", "Cancelled"], index=["Active", "Completed", "Archived", "Cancelled"].index(selected_budget.get("status", "Active")) if selected_budget.get("status", "Active") in ["Active", "Completed", "Archived", "Cancelled"] else 0)
                            selected_budget_payload = budget_payload(selected_budget)
                            saved_work_status = str(selected_budget_payload.get("work_status") or ("Selesai" if str(selected_budget.get("status") or "").lower() == "completed" else "Belum diperbarui"))
                            work_status_options = ["Belum diperbarui", "Belum mulai", "Berjalan", "Selesai"]
                            if saved_work_status not in work_status_options:
                                saved_work_status = "Belum diperbarui"
                            edit_work_status = st.selectbox(
                                "Status fisik pekerjaan",
                                work_status_options,
                                index=work_status_options.index(saved_work_status),
                                key=f"work_status_{pid}_{selected_budget.get('budget_item_id')}",
                                help="Status fisik terpisah dari status pembayaran/anggaran. Pembayaran tidak otomatis dianggap pekerjaan selesai.",
                            )
                            saved_work_pct = max(0, min(100, safe_int(selected_budget_payload.get("work_progress_pct"), 0)))
                            if edit_work_status == "Berjalan":
                                edit_work_progress_pct = st.slider(
                                    "Progres fisik item (%)", 0, 100, saved_work_pct,
                                    key=f"work_progress_{pid}_{selected_budget.get('budget_item_id')}",
                                )
                            elif edit_work_status == "Selesai":
                                edit_work_progress_pct = 100
                                st.caption("Progres fisik otomatis 100% untuk item berstatus Selesai.")
                            elif edit_work_status == "Belum mulai":
                                edit_work_progress_pct = 0
                            else:
                                edit_work_progress_pct = None
                        edit_budget_confirm = st.checkbox("Saya yakin perubahan item anggaran ini sudah benar.", key=f"budget_edit_confirm_{pid}_{selected_budget.get('budget_item_id')}")
                        save_budget_edit = st.form_submit_button("Simpan perubahan item anggaran")
                    if save_budget_edit and not edit_budget_confirm:
                        st.warning("Centang konfirmasi setelah memeriksa perubahan anggaran.")
                    elif save_budget_edit:
                        updated_payload = dict(selected_budget_payload)
                        if edit_work_status == "Belum diperbarui":
                            updated_payload.pop("work_status", None)
                            updated_payload.pop("work_progress_pct", None)
                        else:
                            updated_payload["work_status"] = edit_work_status
                            updated_payload["work_progress_pct"] = edit_work_progress_pct
                        updated_budget = {**selected_budget, "category": edit_budget_category, "subcategory": edit_budget_subcategory, "description": edit_budget_description.strip(), "budget_amount": edit_budget_amount, "committed_unpaid": edit_committed, "forecast_remaining": edit_forecast, "vendor": edit_vendor, "due_date": edit_due_date.isoformat() if edit_has_due else "", "status": edit_status, "payload": updated_payload, "updated_at": iso_now()}
                        before = {k: selected_budget.get(k) for k in ["category", "subcategory", "description", "budget_amount", "committed_unpaid", "forecast_remaining", "vendor", "due_date", "status"]}
                        before["work_status"] = selected_budget_payload.get("work_status")
                        before["work_progress_pct"] = selected_budget_payload.get("work_progress_pct")
                        upsert_record("PROJECT_BUDGETS", "budget_item_id", updated_budget)
                        after = {k: updated_budget.get(k) for k in before if k in updated_budget}
                        after["work_status"] = updated_payload.get("work_status")
                        after["work_progress_pct"] = updated_payload.get("work_progress_pct")
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
            summaries.append({"Property ID": p.get("property_id"), "Objek": p.get("name"), "Lokasi": p.get("address"), "Tanggal Sold": close.get("sold_date"), "Harga Closing": summary["closing_price"], "Modal Pra-Penjualan Aktual": summary["total_actual_cost"], "Total Biaya All-in Aktual": summary["total_actual_cost_including_selling"], "Profit Aktual": summary["net_profit_actual"], "ROI Aktual All-in (%)": summary["roi_actual_pct"], "ROI Tahunan Ekuivalen Aktual (%)": summary["annualized_roi_actual_pct"], "XIRR Aktual (%)": summary["xirr_actual_pct"], "Status XIRR": summary["xirr_status"], "Holding (bulan)": summary["total_holding_months"]})
        df = pd.DataFrame(summaries)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={"Harga Closing": st.column_config.NumberColumn(format="Rp %.0f"), "Modal Pra-Penjualan Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "Total Biaya All-in Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "Profit Aktual": st.column_config.NumberColumn(format="Rp %.0f"), "ROI Aktual All-in (%)": st.column_config.NumberColumn(format="%.1f%%"), "ROI Tahunan Ekuivalen Aktual (%)": st.column_config.NumberColumn(format="%.1f%%"), "XIRR Aktual (%)": st.column_config.NumberColumn(format="%.1f%%")})
        total_profit = sum(to_float(x.get("Profit Aktual")) for x in summaries)
        k1,k2,k3 = st.columns(3); k1.metric("Total aset terjual", len(sold)); k2.metric("Total profit aktual", idr(total_profit)); k3.metric("Rata-rata ROI aktual", pct(df["ROI Aktual All-in (%)"].dropna().mean() if df["ROI Aktual All-in (%)"].notna().any() else None))
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
                new_decision = st.selectbox("Status keputusan analisis (arsip pra-lelang)", DECISION_STATUSES, index=DECISION_STATUSES.index(selected.get("decision_status", "HOLD")) if selected.get("decision_status") in DECISION_STATUSES else 0, help="Saat lifecycle menjadi WON/ACTIVE, sistem mempertahankan keputusan yang sudah tercatat sebelum bidding. Kemenangan berdasarkan keputusan owner tidak otomatis mengubah HOLD menjadi GO.")
                editable_lifecycle = [x for x in LIFECYCLE_STATUSES if x not in {"SOLD"}]
                new_lifecycle = st.selectbox("Status perjalanan properti", editable_lifecycle, index=editable_lifecycle.index(selected.get("lifecycle_status", "PROSPECT")) if selected.get("lifecycle_status") in editable_lifecycle else 0, help="WON = berhasil menang lelang. ACTIVE = proyek sudah masuk tahap pengelolaan/penyelesaian.")
                mark_win_price = st.number_input("Harga menang / harga perolehan (Rp)", min_value=0, step=1_000_000, value=safe_int(existing_win.get("win_price", selected.get("auction_limit", 0))))
                mark_win_date = st.date_input("Tanggal menang", value=default_win_date)
                mark_payment_info = derive_payment_deadline(win_date=mark_win_date.isoformat())
                st.caption(f"Informasi estimasi pelunasan 5 hari kerja: {_indonesian_date_label(mark_payment_info['payment_deadline'])}. Bukan tenggat resmi; verifikasi ke KPKNL.")
                mark_win_deposit = st.number_input("Uang jaminan yang menjadi bagian harga menang (Rp)", min_value=0, step=500_000, value=safe_int(existing_win.get("deposit_amount", 0)))
                update_status = st.form_submit_button("Simpan status dan data kemenangan", type="primary")
            if update_status:
                if new_lifecycle in {"WON", "ACTIVE"}:
                    try:
                        mark_payment_info = derive_payment_deadline(win_date=mark_win_date.isoformat())
                        updated_record = mark_property_won(selected, {"win_price": mark_win_price, "win_date": mark_win_date.isoformat(), "deposit_amount": mark_win_deposit or None, "payment_deadline_info": mark_payment_info["payment_deadline"], "payment_deadline_info_basis": mark_payment_info["payment_deadline_basis"]})
                        if new_lifecycle == "ACTIVE": updated_record["lifecycle_status"] = "ACTIVE"
                        # Preserve the decision made before bidding (including HOLD).
                        # Winning by owner discretion must not rewrite the historical
                        # underwriting decision as GO.
                        preserved_decision = selected.get("decision_status") or ((record_payload(selected).get("latest_analysis") or {}).get("decision") or {}).get("status") or "INCOMPLETE"
                        updated_record["decision_status"] = preserved_decision
                        upsert_record("PROPERTIES", "property_id", updated_record)
                        seed_result = seed_opening_budget_for_won_property(updated_record, mark_win_price)
                        log_event("PROPERTY", selection, "AUCTION_WON", {"pre_bid_decision_preserved": preserved_decision, "lifecycle": updated_record["lifecycle_status"], "win_price": mark_win_price, "win_date": mark_win_date.isoformat(), "budget_items_seeded": seed_result.get("seeded", 0), "budget_seed_reason": seed_result.get("reason")})
                        if seed_result.get("seeded", 0) > 0 or seed_result.get("rows"):
                            success_text = f"Objek berhasil dipindahkan ke portofolio proyek. Keputusan pra-lelang {preserved_decision} tetap disimpan sebagai arsip. Baseline anggaran dibuat dari harga menang {idr(mark_win_price)} ({seed_result.get('seeded', 0)} item)."
                            st.success(success_text)
                            if seed_result.get("pending_pricing_items"):
                                st.warning("Baseline memiliki item RAB yang belum terharga: " + "; ".join(seed_result["pending_pricing_items"][:8]))
                        else:
                            st.success(f"Objek berhasil dipindahkan ke portofolio proyek. Keputusan pra-lelang {preserved_decision} tetap disimpan.")
                            if seed_result.get("reason"):
                                st.warning(seed_result["reason"])
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
        c1,c2,c3,c4 = st.columns(4)
        with c1: quick_sale = st.number_input("Quick-sale discount (%)", min_value=0.0, max_value=50.0, value=to_float(rules["quick_sale_discount_pct"]))
        with c2: min_roi = st.number_input("Minimum Project ROI (%)", min_value=0.0, max_value=200.0, value=to_float(rules["minimum_roi_pct"]), help="Batas minimum dihitung dari profit bersih dibagi total biaya all-in, termasuk biaya penjualan. Ini bukan batas maksimum keuntungan.")
        with c3: mid_roi = st.number_input("Target Project ROI (%)", min_value=0.0, max_value=300.0, value=to_float(rules["mid_roi_pct"]))
        with c4: min_profit = st.number_input("Profit bersih minimum (Rp)", min_value=0, step=5_000_000, value=safe_int(rules.get("minimum_net_profit", 50_000_000)))
        c1,c2,c3 = st.columns(3)
        with c1: target_days = st.number_input("Target durasi ideal (hari)", min_value=30, max_value=180, step=15, value=int(to_float(rules.get("target_holding_days", 90))))
        with c2: max_days = st.number_input("Batas maksimum durasi (hari)", min_value=90, max_value=365, step=15, value=int(to_float(rules.get("maximum_holding_days", 180))))
        with c3: hidden_reserve = st.number_input("Cadangan interior belum diinspeksi (%)", min_value=0.0, max_value=50.0, value=to_float(rules.get("hidden_condition_reserve_pct", 7.5)), help="Tambahan cadangan modal di luar contingency renovasi ketika interior belum dapat diperiksa.")
        njop_market_weight = st.number_input("Bobot referensi NJOP terkalibrasi (%)", min_value=0.0, max_value=25.0, value=to_float(rules.get("njop_market_weight_pct", 10.0)), help="Hanya aktif bila minimal 3 comparable memiliki data harga dan NJOP pembanding. NJOP tidak pernah diperlakukan sebagai harga pasar langsung.")
        save_rules = st.form_submit_button("Simpan asumsi", use_container_width=True)
    if save_rules:
        if mid_roi < min_roi:
            st.error("Target Project ROI tidak boleh lebih rendah dari minimum Project ROI.")
            st.stop()
        if max_days < target_days:
            st.error("Batas maksimum durasi tidak boleh lebih pendek dari target ideal.")
            st.stop()
        updated = {"buyer_auction_fee_pct":buyer_fee,"bphtb_rate_pct":bphtb_rate,"npoptkp":npoptkp,"bphtb_basis_mode":basis_mode,"bpn_pnbp_cost":bpn,"roya_cost":roya,"other_acquisition_admin":other_admin,"acquisition_notary_ppat_fee":notary_buy,"seller_final_tax_pct":pph,"seller_agent_pct":agent,"seller_ajb_ppat_pct":ajb,"seller_misc_fixed":misc,"monthly_holding_cost":holding,"renovation_contingency_pct":contingency,"hidden_condition_reserve_pct":hidden_reserve,"negotiation_discount_pct":negotiation,"quick_sale_discount_pct":quick_sale,"minimum_roi_pct":min_roi,"mid_roi_pct":mid_roi,"minimum_net_profit":min_profit,"target_holding_days":target_days,"maximum_holding_days":max_days,"investment_policy_version":"KAYNA_FLIP_POLICY_V1","njop_market_weight_pct":njop_market_weight}
        st.session_state.rules_local.update(updated)
        upsert_record("RULES_CONFIG", "rule_key", {"rule_key":"GLOBAL","value":updated,"updated_at":iso_now(),"source_note":"User-configured assumptions; verify by property jurisdiction/transaction."})
        log_event("RULES", "GLOBAL", "UPDATED", updated); st.success("Rules tersimpan."); st.rerun()
    st.markdown("### Konfigurasi API")
    st.code(f"GEMINI_MODEL = {GEMINI_MODEL}\nGEMINI_API_KEY = {'configured' if GEMINI_KEY else 'not configured'}\nSPREADSHEET_ID = {'configured' if spreadsheet_id else 'not configured'}", language="text")
    st.markdown("Gemini 3.5 Flash-Lite Free Tier tidak menyediakan Google Search grounding. V1 menggunakan comparable manual; jangan kirim data pribadi sensitif yang tidak diperlukan.")