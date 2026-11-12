from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from core.analysis_engine import run_property_analysis
from core.portfolio_engine import rank_saved_objects
from services.document_parser import extract_text
from services.gemini_client import (
    DEFAULT_MODEL,
    classify_gemini_error,
    extract_document_with_gemini,
    portfolio_adjudication,
    write_investment_memo,
)
from storage.gsheets_repository import GoogleSheetsRepository

st.set_page_config(
    page_title="Auction Flip Decision System",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- Theme & helpers -----------------------------
st.markdown(
    """
    <style>
      .block-container {max-width: 1540px; padding-top: 1.25rem; padding-bottom: 3rem;}
      h1, h2, h3 {letter-spacing: -0.025em;}
      div[data-testid="stMetric"] {background: rgba(120,130,140,.075); padding: .7rem .9rem; border-radius: 12px;}
      div[data-testid="stMetricLabel"] p {font-size: .84rem;}
      .muted {color:#748094; font-size:.86rem;}
      .hero {padding: 1.1rem 1.25rem; border:1px solid rgba(120,130,140,.25); border-radius:16px; background:linear-gradient(120deg, rgba(14,116,144,.08), rgba(16,185,129,.04));}
      .kpi-note {font-size:.78rem; color:#748094; margin-top:-.35rem;}
      .section-label {font-size:.76rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#64748b;}
      .status-pill {display:inline-block; border-radius:999px; padding:.22rem .7rem; font-weight:700; font-size:.82rem;}
      .stButton button {border-radius:10px; min-height:2.65rem;}
      div[data-testid="stDataFrame"] {border-radius:12px; overflow:hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)


def secret(key: str, default: Any = "") -> Any:
    try:
        value = st.secrets.get(key, default)
        return default if value is None else value
    except Exception:
        return os.getenv(key, default)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "ya", "y"}


def idr(value: Any, decimals: int = 0) -> str:
    if value in (None, ""):
        return "—"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp{abs(amount):,.{decimals}f}".replace(",", ".")


def pct(value: Any, decimals: int = 1) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def parse_json_cell(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def money_column_config(label: str, help_text: str = ""):
    return st.column_config.NumberColumn(label, min_value=0, step=1_000_000, format="Rp %.0f", help=help_text)


# ----------------------------- Access control ------------------------------
APP_PASSWORD = str(secret("APP_PASSWORD", "") or "")
if APP_PASSWORD:
    if not st.session_state.get("authenticated", False):
        st.markdown("<div class='hero'><h2>🏠 Auction Flip Decision System</h2><p>Akses terbatas untuk investor.</p></div>", unsafe_allow_html=True)
        with st.form("login_form"):
            password = st.text_input("Password aplikasi", type="password")
            ok = st.form_submit_button("Masuk", use_container_width=True)
        if ok:
            if hmac.compare_digest(password, APP_PASSWORD):
                st.session_state["authenticated"] = True
                st.rerun()
            st.error("Password tidak sesuai.")
        st.stop()
else:
    st.sidebar.warning("APP_PASSWORD belum diatur. Siapa pun yang memiliki URL dapat membuka aplikasi.")


# ------------------------------ Connections --------------------------------
@st.cache_resource(show_spinner=False)
def _connect_sheets(spreadsheet_id: str, service_account_json: str):
    return GoogleSheetsRepository(spreadsheet_id, json.loads(service_account_json))


@st.cache_resource(show_spinner=False)
def _gemini_config_marker(api_key: str, model: str):
    # No client is created here; marker is used only to avoid exposing the key to UI state.
    return {"configured": bool(api_key), "model": model}


repo: GoogleSheetsRepository | None = None
sheets_error = ""
try:
    service_account = secret("google_service_account", {})
    spreadsheet_id = str(secret("SPREADSHEET_ID", "") or "")
    if service_account and spreadsheet_id:
        service_json = json.dumps(dict(service_account), sort_keys=True)
        repo = _connect_sheets(spreadsheet_id, service_json)
    else:
        sheets_error = "Google Sheets belum dikonfigurasi. Aplikasi dapat diuji dalam mode sesi, tetapi data tidak tersimpan permanen."
except Exception as exc:
    sheets_error = f"Koneksi Google Sheets gagal: {exc}"

GEMINI_API_KEY = str(secret("GEMINI_API_KEY", "") or "")
GEMINI_MODEL = str(secret("GEMINI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL)
_gemini_marker = _gemini_config_marker(GEMINI_API_KEY, GEMINI_MODEL)


# ------------------------------- Session state -----------------------------
if "object_id" not in st.session_state:
    st.session_state.object_id = str(uuid.uuid4())
if "last_snapshot" not in st.session_state:
    st.session_state.last_snapshot = None
if "session_snapshots" not in st.session_state:
    st.session_state.session_snapshots = []
if "investor_profile_local" not in st.session_state:
    st.session_state.investor_profile_local = {
        "baseline_cash": 0.0, "baseline_date": date.today().isoformat(),
        "ongoing_commitments": 0.0, "household_reserve": 0.0,
        "risk_reserve": 0.0, "receivables_not_received": 0.0,
        "notes": "", "profile_confirmed": False,
    }
if "ai_cache" not in st.session_state:
    st.session_state.ai_cache = {}
if "ai_call_timestamps" not in st.session_state:
    st.session_state.ai_call_timestamps = []
if "ai_error_state" not in st.session_state:
    st.session_state.ai_error_state = ""
if "selected_compare_ids" not in st.session_state:
    st.session_state.selected_compare_ids = []


# ------------------------------ Data loading --------------------------------
def get_investor_profile() -> dict[str, Any]:
    profile = dict(st.session_state.investor_profile_local)
    if repo:
        try:
            saved = repo.get_investor_profile()
            if saved:
                profile.update(saved)
        except Exception as exc:
            st.sidebar.warning(f"Profil investor gagal dibaca: {exc}")
    return profile


def get_transactions() -> list[dict[str, Any]]:
    if repo:
        try:
            return repo.get_cashflow()
        except Exception:
            return []
    return st.session_state.get("cashflow_local", [])


def compute_cash_position(profile: dict[str, Any], transactions: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = as_float(profile.get("baseline_cash"))
    baseline_date = str(profile.get("baseline_date") or "1900-01-01")[:10]
    movements = 0.0
    included = 0
    for tx in transactions:
        tx_date = str(tx.get("transaction_date", ""))[:10]
        if tx_date and tx_date < baseline_date:
            continue
        amount = abs(as_float(tx.get("amount")))
        direction = str(tx.get("direction", "OUT")).upper()
        movements += amount if direction == "IN" else -amount
        included += 1
    live_cash = baseline + movements
    commitments = as_float(profile.get("ongoing_commitments"))
    household = as_float(profile.get("household_reserve"))
    risk = as_float(profile.get("risk_reserve"))
    available = live_cash - commitments - household - risk
    return {
        "baseline_cash": baseline, "movement_net": movements, "live_cash": live_cash,
        "ongoing_commitments": commitments, "household_reserve": household,
        "risk_reserve": risk, "receivables_not_received": as_float(profile.get("receivables_not_received")),
        "available_for_new": available, "transactions_counted": included,
        "profile_confirmed": as_bool(profile.get("profile_confirmed")),
    }


def saved_snapshots() -> list[dict[str, Any]]:
    saved = []
    if repo:
        try:
            saved = repo.list_latest_snapshots()
        except Exception as exc:
            st.warning(f"Gagal membaca data analisis dari Google Sheets: {exc}")
    # Local session snapshots are fallback only and are deduplicated against cloud data.
    cloud_ids = {str(x.get("object_id")) for x in saved}
    for snap in st.session_state.session_snapshots:
        if str(snap.get("object_id")) not in cloud_ids:
            saved.append(snap)
    return saved


investor_profile = get_investor_profile()
transactions = get_transactions()
cash_state = compute_cash_position(investor_profile, transactions)


# -------------------------------- Header -------------------------------------
head_left, head_right = st.columns([3, 1])
with head_left:
    st.title("Auction Flip Decision System")
    st.caption("Sell first, buy second · hitung dengan Python · simpan di Google Sheets · AI sebagai reviewer, bukan kalkulator")
with head_right:
    if repo:
        st.success("Google Sheets terhubung", icon="✅")
    else:
        st.warning("Mode sesi / belum tersambung", icon="⚠️")

if not repo:
    with st.expander("Mengaktifkan Google Sheets (wajib untuk penyimpanan permanen)", expanded=False):
        st.markdown(
            """
            1. Buat Google Sheet kosong, aktifkan **Google Sheets API** dan buat **Service Account** di Google Cloud.
            2. Bagikan spreadsheet kepada email Service Account dengan akses **Editor**.
            3. Di Streamlit Cloud → **App settings → Secrets**, isi konfigurasi berikut.
            4. Restart aplikasi. Tab database akan dibuat otomatis.
            """
        )
        st.code(
            'SPREADSHEET_ID = "ID_GOOGLE_SHEET"\n'
            'APP_PASSWORD = "PASSWORD_KUAT"\n'
            'GEMINI_API_KEY = "API_KEY_JIKA_Ada"\n'
            'GEMINI_MODEL = "gemini-3.5-flash-lite"\n\n'
            '[google_service_account]\n'
            'type = "service_account"\n'
            'project_id = "..."\n'
            'private_key_id = "..."\n'
            'private_key = """-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"""\n'
            'client_email = "...iam.gserviceaccount.com"\n'
            'client_id = "..."\n'
            'token_uri = "https://oauth2.googleapis.com/token"',
            language="toml",
        )
        st.caption("Jangan pernah mengunggah secrets.toml atau private key ke GitHub. Lihat README untuk langkah rinci.")


# -------------------------------- Dashboard ----------------------------------
tab_dashboard, tab_new, tab_compare, tab_cash, tab_data = st.tabs([
    "📊 Dashboard", "📝 Analisis Baru", "⚖️ Bandingkan & Ranking", "💰 Cashflow Investor", "🗄️ Database & Panduan"
])

snapshots = saved_snapshots()
ranked_all = rank_saved_objects(snapshots, cash_state)

with tab_dashboard:
    st.markdown("<div class='hero'><div class='section-label'>Investment command center</div><h2>Jangan membeli hanya karena harga limit terlihat murah.</h2><p>Analisis exit, seluruh biaya, risiko penguasaan, dan dana yang benar-benar tersedia sebelum menentukan bid.</p></div>", unsafe_allow_html=True)
    st.write("")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kas aktual terhitung", idr(cash_state["live_cash"]))
    c2.metric("Komitmen proyek berjalan", idr(cash_state["ongoing_commitments"]))
    c3.metric("Cadangan wajib", idr(cash_state["household_reserve"] + cash_state["risk_reserve"]))
    c4.metric("Dana tersedia proyek baru", idr(cash_state["available_for_new"]), delta="Bukan termasuk piutang")
    st.caption(f"Saldo dihitung dari saldo baseline + transaksi setelah {investor_profile.get('baseline_date', 'tanggal baseline')}. Piutang belum diterima {idr(cash_state['receivables_not_received'])} tidak dihitung sebagai kas siap pakai.")

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Portofolio tersimpan")
        if ranked_all:
            view = pd.DataFrame([{
                "Peringkat": r["rank"], "Objek": r["name"], "Lot": r["lot_code"],
                "Status": r["status"], "Indeks (%)": r["score_pct"],
                "ROI base": r["base_roi_pct"], "Kas dibutuhkan": r["required_cash"],
            } for r in ranked_all])
            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Indeks (%)": st.column_config.ProgressColumn("Indeks kelayakan", min_value=0, max_value=100, format="%.1f%%"),
                    "ROI base": st.column_config.NumberColumn(format="%.1f%%"),
                    "Kas dibutuhkan": st.column_config.NumberColumn(format="Rp %.0f"),
                },
            )
        else:
            st.info("Belum ada objek yang disimpan. Mulai dari tab Analisis Baru.")
    with right:
        st.subheader("Kontrol keputusan")
        if ranked_all:
            counts = {status: sum(1 for r in ranked_all if r["status"] == status) for status in ["GO", "CONDITIONAL", "HOLD", "NO-GO"]}
            m1, m2 = st.columns(2)
            m1.metric("Objek tersimpan", len(ranked_all))
            m2.metric("GO / Conditional", counts["GO"] + counts["CONDITIONAL"])
            st.write("Status portofolio")
            for label, count in counts.items():
                st.write(f"**{label}** · {count}")
            if counts["GO"] + counts["CONDITIONAL"] == 0:
                st.warning("Tidak ada objek yang layak dieksekusi berdasarkan data terbaru. HOLD SEMUA adalah keputusan yang valid.")
        else:
            st.info("Dashboard akan merangkum portofolio setelah hasil analisis disimpan.")
    st.divider()
    st.subheader("Alur kerja")
    flow_cols = st.columns(5)
    for col, title, desc in zip(flow_cols,
        ["1. Input KPKNL", "2. Survey lapangan", "3. Analisis sekali klik", "4. Simpan GSheets", "5. Bandingkan portofolio"],
        ["Salin data dari pengumuman resmi", "Masukkan fakta, foto, okupansi", "Python hitung pasar, biaya, ROI, bid", "Simpan snapshot & riwayat", "Pilih satu atau HOLD semua"]):
        with col:
            st.markdown(f"**{title}**")
            st.caption(desc)


# ------------------------------ New analysis --------------------------------
with tab_new:
    st.subheader("Buat analisis objek lelang")
    st.markdown("Isi dua kelompok data: **data dari pengumuman resmi KPKNL** dan **hasil survei Anda**. Field yang belum diketahui boleh dibiarkan kosong; sistem akan menandainya dan dapat memutuskan HOLD.")
    n1, n2 = st.columns([2, 1])
    with n1:
        st.caption(f"ID objek saat ini: `{st.session_state.object_id}`")
    with n2:
        if st.button("＋ Objek baru / reset form", use_container_width=True):
            st.session_state.object_id = str(uuid.uuid4())
            st.session_state.last_snapshot = None
            for key in list(st.session_state.keys()):
                if key.startswith("form_"):
                    del st.session_state[key]
            st.rerun()

    # Document helper is deliberately separate; normal calculation never calls Gemini.
    with st.expander("Bantuan dokumen pengumuman lelang (opsional)", expanded=False):
        uploaded = st.file_uploader("Unggah PDF atau gambar pengumuman lelang", type=["pdf", "png", "jpg", "jpeg", "webp"], key="auction_notice_upload")
        if uploaded:
            st.caption(f"File: {uploaded.name} · {uploaded.size:,} bytes")
            if uploaded.type == "application/pdf":
                if st.button("Baca teks PDF secara lokal (tanpa token Gemini)", key="extract_local_pdf"):
                    local_text = extract_text(uploaded.getvalue(), uploaded.name)
                    st.session_state["local_notice_text"] = local_text
                if st.session_state.get("local_notice_text"):
                    st.text_area("Teks hasil ekstraksi lokal — periksa lalu salin ke form", value=st.session_state.local_notice_text, height=180)
            if st.button("Ekstrak data dengan Gemini (menggunakan kuota)", key="extract_gemini_notice", disabled=not GEMINI_API_KEY):
                try:
                    with st.spinner("Gemini membaca dokumen..."):
                        extracted = extract_document_with_gemini(GEMINI_API_KEY, GEMINI_MODEL, uploaded.getvalue(), uploaded.type, uploaded.name)
                    st.session_state["gemini_extraction"] = extracted
                    st.success("Ekstraksi selesai. Periksa setiap nilai terhadap dokumen asli sebelum menyalin ke form.")
                except Exception as exc:
                    code, message = classify_gemini_error(exc)
                    st.session_state.ai_error_state = code
                    st.error(message)
            if st.session_state.get("gemini_extraction"):
                st.code(st.session_state.gemini_extraction, language="json")
        elif not GEMINI_API_KEY:
            st.caption("Tambahkan GEMINI_API_KEY di Streamlit Secrets untuk memakai ekstraksi AI. Analisis finansial tidak memerlukan Gemini.")

    default_comp_rows = pd.DataFrame([
        {"complex": "", "address": "", "distance_km": 0.0, "land_area": 0.0, "building_area": 0.0,
         "price": 0.0, "price_type": "Listing aktif", "condition": "Tidak diketahui", "property_type": "Tidak diketahui",
         "certificate": "Tidak diketahui", "date_found": date.today().isoformat(), "source_url": "", "notes": ""}
        for _ in range(3)
    ])
    default_scenarios = pd.DataFrame([
        {"scenario_key": "KOSONG", "label": "Kosong & diserahkan", "expected_cost": 0, "delay_months": 0, "reserve_cost": 0, "notes": ""},
        {"scenario_key": "KOOPERATIF", "label": "Penghuni kooperatif", "expected_cost": 0, "delay_months": 0, "reserve_cost": 0, "notes": ""},
        {"scenario_key": "SULIT", "label": "Penghuni sulit", "expected_cost": 0, "delay_months": 0, "reserve_cost": 0, "notes": ""},
        {"scenario_key": "EKSEKUSI_FORMAL", "label": "Pengosongan formal / eksekusi riil", "expected_cost": 0, "delay_months": 0, "reserve_cost": 0, "notes": ""},
    ])

    with st.form("property_analysis_form", clear_on_submit=False):
        st.markdown("<div class='section-label'>A · Data dari website resmi lelang KPKNL</div>", unsafe_allow_html=True)
        a1, a2, a3 = st.columns(3)
        with a1:
            lot_code = st.text_input("Kode lot / nomor lelang", key="form_lot_code")
            auction_office = st.text_input("KPKNL penyelenggara", key="form_auction_office", placeholder="Contoh: KPKNL Sidoarjo")
            auction_type = st.selectbox("Jenis lelang", ["Eksekusi Hak Tanggungan", "Eksekusi Pengadilan", "AYDA", "Lelang sukarela", "Lainnya / belum diketahui"], key="form_auction_type")
            seller = st.text_input("Penjual / kreditur", key="form_seller")
        with a2:
            object_name = st.text_input("Nama singkat objek", key="form_name", placeholder="Contoh: TAS 3 Blok M6 No. 12")
            complex_name = st.text_input("Nama perumahan / kompleks", key="form_complex_name")
            auction_date = st.date_input("Tanggal lelang", value=None, key="form_auction_date")
            auction_time = st.text_input("Jam / sesi lelang", key="form_auction_time", placeholder="Contoh: 10.00 WIB")
            auction_url = st.text_input("URL pengumuman resmi", key="form_auction_url")
        with a3:
            auction_limit = st.number_input("Nilai limit (Rp)", min_value=0, step=1_000_000, key="form_auction_limit")
            deposit_amount = st.number_input("Uang jaminan (Rp)", min_value=0, step=1_000_000, key="form_deposit_amount")
            deposit_deadline = st.text_input("Batas akhir setor jaminan", key="form_deposit_deadline")
            payment_deadline = st.text_input("Batas pelunasan setelah menang", key="form_payment_deadline")
            bid_increment = st.number_input("Kelipatan bid (Rp)", min_value=1, value=1_000_000, step=100_000, key="form_bid_increment")
            risk_adjusted_ceiling = st.number_input("Batas risiko tambahan / hard ceiling (Rp, opsional)", min_value=0, step=1_000_000, key="form_risk_ceiling")

        st.markdown("#### Identitas objek sesuai pengumuman")
        b1, b2, b3 = st.columns(3)
        with b1:
            address = st.text_input("Alamat objek", key="form_address")
            district = st.text_input("Desa / kecamatan / kabupaten", key="form_district")
            province = st.text_input("Provinsi", value="Jawa Timur", key="form_province")
            certificate_type = st.selectbox("Jenis sertifikat", ["Belum diketahui", "SHM", "SHGB/HGB", "Hak lain"], key="form_certificate_type")
        with b2:
            certificate_no = st.text_input("Nomor hak / sertifikat", key="form_certificate_no")
            rights_expiry = st.text_input("Masa berlaku hak (jika HGB)", key="form_rights_expiry", placeholder="Tanggal atau tahun")
            land_area = st.number_input("Luas tanah / LT (m²)", min_value=0.0, step=1.0, key="form_land_area")
            building_area = st.number_input("Luas bangunan / LB (m²)", min_value=0.0, step=1.0, key="form_building_area")
            njop = st.number_input("NJOP (Rp, bila diketahui)", min_value=0, step=1_000_000, key="form_njop")
        with b3:
            bedrooms = st.number_input("Kamar tidur", min_value=0, max_value=30, step=1, key="form_bedrooms")
            bathrooms = st.number_input("Kamar mandi", min_value=0, max_value=30, step=1, key="form_bathrooms")
            property_type = st.selectbox("Tipe rumah", ["Tidak diketahui", "Rumah 1 lantai", "Rumah 2 lantai", "Rumah kecil/standar", "Rumah besar", "Cluster/modern"], key="form_property_type")
            legal_status = st.selectbox("Status verifikasi legalitas", ["Belum terverifikasi", "Informasi sumber", "Informasi lapangan", "Terverifikasi", "Bertentangan"], key="form_legal_status")
        k1, k2, k3 = st.columns(3)
        with k1:
            identity_verified = st.checkbox("Alamat, nomor hak, dan identitas objek sudah dicocokkan", key="form_identity_verified")
        with k2:
            title_match = st.checkbox("Luas/data fisik cocok dengan dokumen", key="form_title_match")
        with k3:
            dispute_detected = st.checkbox("Ada indikasi sengketa / masalah hukum terbuka", key="form_dispute_detected")
        auction_object_description = st.text_area("Uraian objek sebagaimana tercantum di pengumuman", key="form_auction_object_description", height=75)
        property_notes = st.text_area("Catatan tambahan user / legal", key="form_property_notes", height=65)

        st.divider()
        st.markdown("<div class='section-label'>B · Hasil survei objek oleh user</div>", unsafe_allow_html=True)
        s1, s2, s3 = st.columns(3)
        with s1:
            survey_date = st.date_input("Tanggal survei", value=None, key="form_survey_date")
            surveyor = st.text_input("Nama / inisial surveyor", key="form_surveyor")
            occupancy_status = st.selectbox("Status hunian saat survei", ["Belum diketahui", "Kosong dan terverifikasi", "Penghuni kooperatif", "Penghuni sulit", "Pengosongan formal/eksekusi riil"], key="form_occupancy_status")
            occupancy_verified = st.checkbox("Status hunian benar-benar diverifikasi", key="form_occupancy_verified")
        with s2:
            physical_condition = st.selectbox("Kondisi fisik berdasarkan bukti", ["Tidak diketahui", "Siap huni", "Renovasi kosmetik", "Renovasi sedang", "Rusak berat"], key="form_physical_condition")
            exterior_inspected = st.checkbox("Eksterior/fasad diperiksa", key="form_exterior_inspected")
            interior_inspected = st.checkbox("Interior diperiksa", key="form_interior_inspected")
            access_type = st.selectbox("Akses kendaraan", ["Belum diketahui", "Mobil bisa masuk/parkir", "Mobil hanya sampai jalan utama", "Gang sempit / motor saja"], key="form_access_type")
            road_width_m = st.number_input("Lebar jalan depan (m)", min_value=0.0, step=0.5, key="form_road_width_m")
        with s3:
            flood_history = st.selectbox("Riwayat banjir", ["Belum diketahui", "Tidak ada indikasi setelah verifikasi", "Pernah / terindikasi"], key="form_flood_history")
            structure = st.selectbox("Kondisi struktur", ["Belum diperiksa", "Tidak terlihat indikasi", "Ada indikasi masalah", "Butuh pemeriksaan ahli"], key="form_structure")
            roof = st.selectbox("Atap / plafon", ["Belum diperiksa", "Baik secara visual", "Ada indikasi kerusakan", "Butuh pemeriksaan"], key="form_roof")
            damp = st.selectbox("Rembes / lembap", ["Belum diperiksa", "Tidak terlihat", "Ada indikasi", "Belum dapat dipastikan"], key="form_damp")
        u1, u2, u3 = st.columns(3)
        with u1:
            electricity = st.text_input("Listrik / daya", key="form_electricity")
        with u2:
            water = st.text_input("Sumber air", key="form_water")
        with u3:
            photo_links = st.text_input("Link folder foto / dokumen Drive", key="form_photo_links")
        physical_notes = st.text_area("Catatan lapangan: tetangga, pemegang kunci, kondisi, barang, utilitas, lingkungan", key="form_physical_notes", height=90)

        st.divider()
        st.markdown("<div class='section-label'>C · Comparable pasar</div>", unsafe_allow_html=True)
        st.caption("Masukkan minimal 3 pembanding yang relevan. Listing aktif adalah harga penawaran, bukan bukti harga transaksi.")
        comparables_df = st.data_editor(
            default_comp_rows,
            key="form_comparables_editor",
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "complex": st.column_config.TextColumn("Kompleks"),
                "address": st.column_config.TextColumn("Alamat / area"),
                "distance_km": st.column_config.NumberColumn("Jarak km", min_value=0.0, step=0.1),
                "land_area": st.column_config.NumberColumn("LT m²", min_value=0.0),
                "building_area": st.column_config.NumberColumn("LB m²", min_value=0.0),
                "price": money_column_config("Harga Rp"),
                "price_type": st.column_config.SelectboxColumn("Jenis harga", options=["Transaksi terverifikasi", "Terjual / marked sold", "Listing aktif", "Lelang", "Developer", "Informasi agen"]),
                "condition": st.column_config.SelectboxColumn("Kondisi", options=["Tidak diketahui", "Siap huni", "Renovasi kosmetik", "Renovasi sedang", "Rusak berat"]),
                "property_type": st.column_config.SelectboxColumn("Tipe", options=["Tidak diketahui", "Rumah 1 lantai", "Rumah 2 lantai", "Rumah kecil/standar", "Rumah besar", "Cluster/modern"]),
                "certificate": st.column_config.SelectboxColumn("Sertifikat", options=["Tidak diketahui", "SHM", "SHGB/HGB", "Hak lain"]),
                "date_found": st.column_config.TextColumn("Tanggal ditemukan (YYYY-MM-DD)"),
                "source_url": st.column_config.TextColumn("URL sumber"),
                "notes": st.column_config.TextColumn("Catatan"),
            },
        )

        st.divider()
        st.markdown("<div class='section-label'>D · Biaya, pajak, skenario penguasaan</div>", unsafe_allow_html=True)
        st.warning("Tarif pajak dan bea tidak diasumsikan otomatis. Isi hanya setelah dikonfirmasi untuk lot dan wilayah terkait; jika belum diverifikasi, keputusan akhir akan HOLD.")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            buyer_auction_fee_pct = st.number_input("Bea lelang pembeli (%)", min_value=0.0, step=0.1, key="form_buyer_fee_pct")
            bphtb_rate_pct = st.number_input("Tarif BPHTB (%)", min_value=0.0, step=0.1, key="form_bphtb_pct")
            npoptkp = st.number_input("NPOPTKP (Rp)", min_value=0, step=1_000_000, key="form_npoptkp")
        with f2:
            bphtb_basis_mode = st.selectbox("Dasar BPHTB (simulasi)", ["Harga bid", "Maksimum harga bid dan NJOP", "NJOP"], key="form_bphtb_basis")
            ppn_applicable = st.checkbox("PPN berlaku untuk transaksi ini (sudah diverifikasi)", key="form_ppn_applicable")
            ppn_rate_pct = st.number_input("Tarif PPN (%)", min_value=0.0, step=0.1, key="form_ppn_pct")
        with f3:
            seller_tax_pct = st.number_input("Pajak penjual (%)", min_value=0.0, step=0.1, key="form_seller_tax_pct")
            selling_agent_pct = st.number_input("Komisi agen (%)", min_value=0.0, step=0.1, key="form_agent_pct")
            tax_rules_verified = st.checkbox("Seluruh aturan pajak/biaya lot ini sudah dicek sumber resmi", key="form_tax_verified")
        with f4:
            certificate_legal_cost = st.number_input("Legalitas / balik nama (Rp)", min_value=0, step=1_000_000, key="form_certificate_cost")
            arrears_utilities_cost = st.number_input("Tunggakan utilitas / IPL / PBB (Rp)", min_value=0, step=1_000_000, key="form_arrears_cost")
            other_presale_cost = st.number_input("Biaya pra-penjualan lain (Rp)", min_value=0, step=1_000_000, key="form_other_presale")

        cst1, cst2, cst3 = st.columns(3)
        with cst1:
            renovation_cost = st.number_input("Total RAB renovasi (Rp)", min_value=0, step=1_000_000, key="form_renovation_cost")
            contingency_pct = st.number_input("Contingency renovasi/biaya (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0, key="form_contingency")
            marketing_cost = st.number_input("Marketing tetap (Rp)", min_value=0, step=500_000, key="form_marketing_cost")
        with cst2:
            monthly_holding_cost = st.number_input("Holding cost per bulan (Rp)", min_value=0, step=250_000, key="form_monthly_holding")
            renovation_months = st.number_input("Durasi renovasi (bulan)", min_value=0.0, step=0.5, key="form_renovation_months")
            sale_months_after_ready = st.number_input("Estimasi bulan jual setelah siap", min_value=0.0, step=0.5, key="form_sale_months")
        with cst3:
            other_selling_cost = st.number_input("Biaya penjualan lain (Rp)", min_value=0, step=500_000, key="form_other_selling")
            selected_possession_scenario = st.selectbox("Skenario penguasaan untuk base calculation", ["KOSONG", "KOOPERATIF", "SULIT", "EKSEKUSI_FORMAL"], format_func=lambda x: {"KOSONG":"Kosong & diserahkan", "KOOPERATIF":"Penghuni kooperatif", "SULIT":"Penghuni sulit", "EKSEKUSI_FORMAL":"Pengosongan formal / eksekusi riil"}[x], key="form_selected_possession")
            st.caption("Cadangan worst-case ditampilkan terpisah; skenario alternatif tidak dijumlahkan ke base case.")

        scenario_df = st.data_editor(
            default_scenarios,
            key="form_scenarios_editor",
            use_container_width=True,
            hide_index=True,
            disabled=["scenario_key", "label"],
            column_config={
                "scenario_key": st.column_config.TextColumn("Kode"),
                "label": st.column_config.TextColumn("Skenario"),
                "expected_cost": money_column_config("Biaya perkiraan Rp"),
                "delay_months": st.column_config.NumberColumn("Delay bulan", min_value=0.0, step=0.5),
                "reserve_cost": money_column_config("Cadangan tambahan Rp"),
                "notes": st.column_config.TextColumn("Catatan"),
            },
        )

        st.divider()
        st.markdown("<div class='section-label'>E · Target return & skor risiko</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.columns(4)
        with t1:
            minimum_roi_pct = st.number_input("ROI minimum (%)", min_value=0.0, max_value=500.0, value=20.0, step=1.0, key="form_min_roi")
            minimum_net_profit = st.number_input("Profit bersih minimum (Rp)", min_value=0, step=1_000_000, key="form_min_profit")
        with t2:
            minimum_profit_per_month = st.number_input("Profit minimum per bulan modal (Rp)", min_value=0, step=500_000, key="form_min_monthly_profit")
            maximum_holding_months = st.number_input("Maksimal holding (bulan)", min_value=0.5, value=12.0, step=0.5, key="form_max_holding")
        with t3:
            annual_opportunity_cost_pct = st.number_input("Biaya kesempatan modal tahunan (%)", min_value=0.0, step=0.5, key="form_opportunity_cost")
            conservative_haircut_pct = st.number_input("Diskon exit konservatif (%)", min_value=0.0, max_value=50.0, value=10.0, step=1.0, key="form_haircut")
        with t4:
            optimistic_premium_pct = st.number_input("Premium exit optimistis (%)", min_value=0.0, max_value=50.0, value=10.0, step=1.0, key="form_premium")
            st.caption("ROI dihitung terhadap modal pra-penjualan; biaya penjualan dikurangkan satu kali dari proceeds.")

        st.markdown("#### Skor risiko (1 buruk – 5 baik)")
        r1, r2, r3, r4, r5, r6 = st.columns(6)
        score_liquidity = r1.select_slider("Likuiditas", options=[1, 2, 3, 4, 5], value=3, key="form_score_liq")
        score_legal = r2.select_slider("Legalitas", options=[1, 2, 3, 4, 5], value=3, key="form_score_legal")
        score_possession = r3.select_slider("Penguasaan", options=[1, 2, 3, 4, 5], value=3, key="form_score_possession")
        score_physical = r4.select_slider("Fisik/renovasi", options=[1, 2, 3, 4, 5], value=3, key="form_score_physical")
        score_funding = r5.select_slider("Pendanaan", options=[1, 2, 3, 4, 5], value=3, key="form_score_funding")
        score_environment = r6.select_slider("Lingkungan", options=[1, 2, 3, 4, 5], value=3, key="form_score_environment")

        st.divider()
        submitted = st.form_submit_button("⚡ ANALISIS SEKARANG", type="primary", use_container_width=True)

    if submitted:
        def frame_records(frame: pd.DataFrame, required: list[str]) -> list[dict[str, Any]]:
            result = []
            if frame is None:
                return result
            for row in frame.to_dict(orient="records"):
                clean = {}
                for k, v in row.items():
                    if pd.isna(v):
                        clean[k] = None
                    elif hasattr(v, "item"):
                        clean[k] = v.item()
                    else:
                        clean[k] = v
                if any(clean.get(k) not in (None, "", 0, 0.0) for k in required):
                    result.append(clean)
            return result

        comps = frame_records(comparables_df, ["price"])
        scenarios = {}
        for row in scenario_df.to_dict(orient="records"):
            scenarios[str(row["scenario_key"])] = {
                "label": row.get("label", row["scenario_key"]), "cost": as_float(row.get("expected_cost")),
                "delay_months": as_float(row.get("delay_months")), "reserve_cost": as_float(row.get("reserve_cost")),
                "notes": str(row.get("notes", "")),
            }
        auction_date_value = auction_date.isoformat() if isinstance(auction_date, date) else ""
        survey_date_value = survey_date.isoformat() if isinstance(survey_date, date) else ""
        property_data = {
            "lot_code": lot_code, "auction_office": auction_office, "seller": seller, "auction_type": auction_type,
            "auction_date": auction_date_value, "auction_time": auction_time, "deposit_deadline": deposit_deadline,
            "payment_deadline": payment_deadline, "auction_url": auction_url, "auction_object_description": auction_object_description, "name": object_name,
            "complex_name": complex_name, "address": address, "district": district, "province": province,
            "auction_limit": auction_limit, "deposit_amount": deposit_amount, "bid_increment": bid_increment, "njop": njop,
            "risk_adjusted_ceiling": risk_adjusted_ceiling or None, "certificate_type": certificate_type,
            "certificate_no": certificate_no, "rights_expiry": rights_expiry, "land_area": land_area,
            "building_area": building_area, "bedrooms": bedrooms, "bathrooms": bathrooms, "property_type": property_type,
            "legal_status": legal_status, "identity_verified": identity_verified, "title_match": title_match,
            "dispute_detected": dispute_detected, "property_notes": property_notes,
        }
        survey_data = {
            "survey_date": survey_date_value, "surveyor": surveyor, "occupancy_status": occupancy_status,
            "occupancy_verified": occupancy_verified, "physical_condition": physical_condition,
            "exterior_inspected": exterior_inspected, "interior_inspected": interior_inspected,
            "road_width_m": road_width_m, "access_type": access_type, "flood_history": flood_history,
            "structure": structure, "roof": roof, "damp": damp, "electricity": electricity,
            "water": water, "physical_notes": physical_notes, "photo_links": photo_links,
        }
        fee_data = {
            "buyer_auction_fee_pct": buyer_auction_fee_pct, "bphtb_rate_pct": bphtb_rate_pct,
            "npoptkp": npoptkp, "bphtb_basis_mode": bphtb_basis_mode,
            "ppn_applicable": ppn_applicable, "ppn_rate_pct": ppn_rate_pct,
            "seller_tax_pct": seller_tax_pct, "selling_agent_pct": selling_agent_pct,
            "tax_rules_verified": tax_rules_verified,
        }
        cost_data = {
            "certificate_legal_cost": certificate_legal_cost, "renovation_cost": renovation_cost,
            "arrears_utilities_cost": arrears_utilities_cost, "selected_possession_scenario": selected_possession_scenario,
            "monthly_holding_cost": monthly_holding_cost, "renovation_months": renovation_months,
            "sale_months_after_ready": sale_months_after_ready, "contingency_pct": contingency_pct,
            "marketing_cost": marketing_cost, "other_presale_cost": other_presale_cost,
            "other_selling_cost": other_selling_cost,
        }
        targets = {
            "minimum_net_profit": minimum_net_profit, "minimum_roi_pct": minimum_roi_pct,
            "minimum_profit_per_month": minimum_profit_per_month, "maximum_holding_months": maximum_holding_months,
            "annual_opportunity_cost_pct": annual_opportunity_cost_pct,
            "conservative_haircut_pct": conservative_haircut_pct, "optimistic_premium_pct": optimistic_premium_pct,
        }
        risk_scores = {
            "liquidity": score_liquidity, "legal": score_legal, "possession": score_possession,
            "physical": score_physical, "funding": score_funding, "environment": score_environment,
        }
        inputs = {
            "object_id": st.session_state.object_id, "property": property_data, "survey": survey_data,
            "fees": fee_data, "costs": cost_data, "targets": targets, "risk_scores": risk_scores,
            "comparables": comps, "possession_scenarios": scenarios,
        }
        with st.spinner("Python sedang menghitung market range, seluruh biaya, skenario risiko, ROI, dan maximum bid..."):
            snapshot = run_property_analysis(inputs, cash_state)
        st.session_state.last_snapshot = snapshot
        st.session_state["last_saved_analysis_id"] = ""
        st.success("Analisis selesai. Hasil di bawah berasal dari mesin hitung Python; Gemini tidak dipanggil pada tahap ini.")

    snapshot = st.session_state.last_snapshot
    if snapshot:
        st.divider()
        st.subheader("Hasil analisis objek")
        decision = snapshot["decision"]
        status = decision["status"]
        if status == "GO":
            st.success(f"{status} · {decision['summary']}")
        elif status == "CONDITIONAL":
            st.warning(f"{status} · {decision['summary']}")
        elif status == "NO-GO":
            st.error(f"{status} · {decision['summary']}")
        else:
            st.info(f"{status} · {decision['summary']}")

        market = snapshot["market"]
        res = snapshot["results"]
        base = res["base_at_limit"]
        cons = res["conservative_at_limit"]
        o1, o2, o3, o4, o5 = st.columns(5)
        o1.metric("Indeks kelayakan", pct(snapshot["suitability"]["score_pct"]))
        o2.metric("Exit konservatif", idr(market.get("conservative_exit")))
        o3.metric("Exit base", idr(market.get("base_exit")))
        o4.metric("Profit bersih base @limit", idr(base.get("net_profit")))
        o5.metric("ROI base @limit", pct(base.get("roi_pct")))
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Modal pra-penjualan", idr(base.get("pre_sale_investment")))
        p2.metric("Kas tersedia proyek", idr(base.get("available_for_project")))
        p3.metric("Holding total", f"{base.get('total_holding_months', 0):.1f} bulan")
        p4.metric("Profit per bulan", idr(base.get("profit_per_month")))

        b1, b2, b3 = st.columns(3)
        b1.metric("Recommended bid ceiling", idr(res["recommended_max_bid"].get("maximum_bid")))
        b2.metric("Absolute maximum bid", idr(res["absolute_max_bid"].get("maximum_bid")))
        b3.metric("Uang jaminan (cash awal)", idr(property_data.get("deposit_amount") if 'property_data' in locals() else snapshot["inputs"]["property"].get("deposit_amount")))

        with st.expander("Rincian perhitungan biaya & return", expanded=True):
            rows = [
                ("Harga bid simulasi (limit)", base.get("bid_price")),
                ("Bea lelang pembeli", base.get("auction_fee")),
                ("BPHTB simulasi", base.get("bphtb")),
                ("PPN (hanya bila diaktifkan)", base.get("ppn")),
                ("Legalitas / sertifikat", base.get("certificate_legal_cost")),
                ("Renovasi", base.get("renovation_cost")),
                ("Biaya penguasaan skenario terpilih", base.get("possession_cost")),
                ("Tunggakan utilitas", base.get("arrears_utilities_cost")),
                ("Holding cost", base.get("holding_cost")),
                ("Contingency", base.get("contingency")),
                ("Opportunity cost modal (ekonomis)", base.get("opportunity_cost")),
                ("Biaya penjualan (dikurangkan satu kali)", base.get("selling_cost")),
                ("Net proceeds setelah selling cost", base.get("net_proceeds")),
                ("Profit bersih ekonomis", base.get("net_profit")),
            ]
            st.dataframe(pd.DataFrame(rows, columns=["Komponen", "Rupiah"]), use_container_width=True, hide_index=True,
                         column_config={"Rupiah": st.column_config.NumberColumn(format="Rp %.0f")})
            st.caption("Biaya penjualan dikurangkan dari proceeds satu kali. Deposit lelang ditampilkan sebagai kebutuhan kas awal, bukan biaya tambahan di atas harga bid.")

        with st.expander("Skenario pengosongan / penguasaan", expanded=False):
            possession = res.get("possession_comparison", {}).get("scenarios", [])
            if possession:
                st.dataframe(pd.DataFrame(possession), use_container_width=True, hide_index=True)
            else:
                st.caption("Belum ada skenario penguasaan yang dapat dihitung.")
            st.caption("Skenario-skenario ini alternatif, bukan dijumlahkan sekaligus. Cadangan worst-case perlu disiapkan terpisah.")

        with st.expander("Hard blockers dan peringatan", expanded=True):
            if decision.get("blockers"):
                st.error("Data kritis / hard blockers")
                for item in decision["blockers"]:
                    st.write(f"- {item}")
            else:
                st.success("Tidak ada hard blocker menurut input saat ini.")
            if decision.get("warnings"):
                st.warning("Peringatan")
                for item in decision["warnings"]:
                    st.write(f"- {item}")
            for item in decision.get("reasons", []):
                st.write(f"- {item}")

        with st.expander("Kualitas pembanding pasar", expanded=False):
            st.write(f"Jumlah comparable: **{market.get('count', 0)}** · Confidence: **{pct(market.get('confidence'))}**")
            if market.get("comparables"):
                st.dataframe(pd.DataFrame(market["comparables"]), use_container_width=True, hide_index=True)
            else:
                st.info("Belum ada pembanding berharga valid. Harga exit tidak akan ditebak.")

        save_col, down_col, memo_col = st.columns([1.2, 1, 1.2])
        with save_col:
            can_save = repo is not None and st.session_state.get("last_saved_analysis_id") != snapshot.get("analysis_id")
            if st.button("💾 Simpan hasil analisis ke GSheets", type="primary", use_container_width=True, disabled=not can_save):
                try:
                    repo.save_analysis(snapshot)
                    st.session_state.last_saved_analysis_id = snapshot.get("analysis_id")
                    st.success("Hasil analisis tersimpan. Snapshot lama tidak ditimpa; analisis terbaru menjadi versi aktif.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Gagal menyimpan ke Google Sheets: {exc}")
            if not repo:
                st.caption("Hubungkan Google Sheets untuk menyimpan permanen.")
        with down_col:
            st.download_button("⬇️ Unduh snapshot JSON", data=json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), file_name=f"analisis-{snapshot['object_id'][:8]}.json", mime="application/json", use_container_width=True)
        with memo_col:
            if st.button("✨ Buat memo Gemini", use_container_width=True, disabled=not GEMINI_API_KEY):
                fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
                cache_key = f"memo:{fingerprint}"
                if cache_key in st.session_state.ai_cache:
                    st.session_state.ai_memo = st.session_state.ai_cache[cache_key]
                    st.session_state.ai_memo_fingerprint = fingerprint
                else:
                    try:
                        if len(st.session_state.ai_call_timestamps) and (datetime.now().timestamp() - st.session_state.ai_call_timestamps[-1]) < 20:
                            raise RuntimeError("AI_COOLDOWN: beri jeda minimal 20 detik antar panggilan AI.")
                        with st.spinner("Gemini menulis memo ringkas..."):
                            memo = write_investment_memo(GEMINI_API_KEY, GEMINI_MODEL, snapshot)
                        st.session_state.ai_call_timestamps.append(datetime.now().timestamp())
                        st.session_state.ai_cache[cache_key] = memo
                        st.session_state.ai_memo = memo
                        st.session_state.ai_memo_fingerprint = fingerprint
                    except Exception as exc:
                        code, message = classify_gemini_error(exc)
                        st.session_state.ai_error_state = code
                        st.warning(message if code != "ERROR" else str(exc))
            if st.session_state.get("ai_memo") and st.session_state.get("ai_memo_fingerprint") == hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest():
                st.markdown(st.session_state.ai_memo)


# -------------------------- Portfolio comparison ----------------------------
with tab_compare:
    st.subheader("Perbandingan kelayakan beberapa objek")
    st.caption("Pilih objek yang sudah tersimpan. Ranking dasar dihitung Python dan dapat direproduksi; Gemini memberi second opinion satu kali untuk seluruh shortlist.")
    # Refresh button forces a clean repository read by rerun.
    top_a, top_b = st.columns([1, 4])
    with top_a:
        if st.button("↻ Refresh data GSheets", use_container_width=True):
            st.rerun()
    ranked_all = rank_saved_objects(snapshots, cash_state)
    if not ranked_all:
        st.info("Belum ada hasil analisis tersimpan. Simpan minimal satu analisis terlebih dahulu.")
    else:
        ranked_df = pd.DataFrame([{
            "Pilih": False, "Rank": row["rank"], "Objek": row["name"], "Kode lot": row["lot_code"],
            "Status Python": row["status"], "Indeks kelayakan (%)": row["score_pct"],
            "ROI base (%)": row["base_roi_pct"], "Profit base (Rp)": row["base_profit"],
            "Modal dibutuhkan (Rp)": row["required_cash"], "Kas tersedia (Rp)": row["available_cash"],
            "Confidence pasar (%)": row["market_confidence"], "Holding (bulan)": row["holding_months"],
            "object_id": row["object_id"],
        } for row in ranked_all])
        edited = st.data_editor(
            ranked_df,
            key="portfolio_selection_editor",
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in ranked_df.columns if c != "Pilih"],
            column_config={
                "Pilih": st.column_config.CheckboxColumn("Bandingkan", help="Pilih objek untuk shortlist Gemini."),
                "Indeks kelayakan (%)": st.column_config.ProgressColumn("Indeks kelayakan (%)", min_value=0, max_value=100, format="%.1f%%"),
                "ROI base (%)": st.column_config.NumberColumn(format="%.1f%%"),
                "Profit base (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Modal dibutuhkan (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "Kas tersedia (Rp)": st.column_config.NumberColumn(format="Rp %.0f"),
                "object_id": None,
            },
        )
        selected_ids = edited.loc[edited["Pilih"] == True, "object_id"].astype(str).tolist()
        selected_rows = [r for r in ranked_all if r["object_id"] in selected_ids]
        st.write(f"Objek dipilih: **{len(selected_rows)}** dari {len(ranked_all)}")
        st.caption("Persentase adalah indeks screening berbobot—bukan probabilitas objek pasti laku atau pasti untung. Ranking ini menghitung ulang tiap objek memakai cashflow dan cadangan investor terkini; snapshot historis tidak diubah. Status HOLD/NO-GO tetap mengalahkan skor angka.")

        if selected_rows:
            compare_detail = []
            for r in selected_rows:
                snapshot = r["snapshot"]
                cons = snapshot["results"].get("conservative_at_limit", {})
                base = snapshot["results"].get("base_at_limit", {})
                compare_detail.append({
                    "Objek": r["name"], "Status": r["status"], "Skor (%)": r["score_pct"],
                    "Exit konservatif": snapshot["market"].get("conservative_exit"),
                    "Exit base": snapshot["market"].get("base_exit"),
                    "Profit konservatif": cons.get("net_profit"), "ROI konservatif": cons.get("roi_pct"),
                    "Profit base": base.get("net_profit"), "ROI base": base.get("roi_pct"),
                    "Recommended bid": r["recommended_bid"], "Absolute max": r["absolute_max_bid"],
                    "Modal": r["required_cash"], "Confidence": r["market_confidence"],
                })
            st.dataframe(pd.DataFrame(compare_detail), use_container_width=True, hide_index=True,
                         column_config={
                             "Skor (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                             "Exit konservatif": st.column_config.NumberColumn(format="Rp %.0f"),
                             "Exit base": st.column_config.NumberColumn(format="Rp %.0f"),
                             "Profit konservatif": st.column_config.NumberColumn(format="Rp %.0f"),
                             "Profit base": st.column_config.NumberColumn(format="Rp %.0f"),
                             "ROI konservatif": st.column_config.NumberColumn(format="%.1f%%"),
                             "ROI base": st.column_config.NumberColumn(format="%.1f%%"),
                             "Recommended bid": st.column_config.NumberColumn(format="Rp %.0f"),
                             "Absolute max": st.column_config.NumberColumn(format="Rp %.0f"),
                             "Modal": st.column_config.NumberColumn(format="Rp %.0f"),
                         })

            ai_left, ai_right = st.columns([1, 3])
            with ai_left:
                run_ai = st.button("🧠 Review Gemini shortlist", type="primary", use_container_width=True, disabled=not GEMINI_API_KEY)
            with ai_right:
                if not GEMINI_API_KEY:
                    st.caption("Gemini belum dikonfigurasi. Ranking Python tetap bekerja tanpa AI.")
                else:
                    st.caption(f"Model: `{GEMINI_MODEL}` · hanya 1 request untuk semua objek terpilih · respons di-cache selama sesi.")
            if run_ai:
                if len(selected_rows) > 8:
                    st.warning("Shortlist dibatasi maksimal 8 objek untuk menghemat token. Pilih maksimal 8.")
                else:
                    fingerprint = hashlib.sha256(json.dumps([{k: r.get(k) for k in ["object_id", "score_pct", "status", "base_roi_pct", "base_profit", "required_cash", "available_cash", "blockers"]} for r in selected_rows], sort_keys=True, default=str).encode()).hexdigest()
                    cache_key = f"portfolio:{fingerprint}"
                    if cache_key in st.session_state.ai_cache:
                        st.session_state.ai_portfolio_result = st.session_state.ai_cache[cache_key]
                        st.session_state.ai_portfolio_fingerprint = fingerprint
                    else:
                        try:
                            if st.session_state.ai_call_timestamps and (datetime.now().timestamp() - st.session_state.ai_call_timestamps[-1]) < 20:
                                raise RuntimeError("AI_COOLDOWN: beri jeda minimal 20 detik antar panggilan AI.")
                            with st.spinner("Gemini menilai shortlist secara keseluruhan..."):
                                advice = portfolio_adjudication(GEMINI_API_KEY, GEMINI_MODEL, selected_rows)
                            st.session_state.ai_call_timestamps.append(datetime.now().timestamp())
                            st.session_state.ai_cache[cache_key] = advice
                            st.session_state.ai_portfolio_result = advice
                            st.session_state.ai_portfolio_fingerprint = fingerprint
                        except Exception as exc:
                            code, message = classify_gemini_error(exc)
                            st.session_state.ai_error_state = code
                            st.warning(message if code != "ERROR" else str(exc))
            current_portfolio_fingerprint = hashlib.sha256(json.dumps([{k: r.get(k) for k in ["object_id", "score_pct", "status", "base_roi_pct", "base_profit", "required_cash", "available_cash", "blockers"]} for r in selected_rows], sort_keys=True, default=str).encode()).hexdigest()
            advice = st.session_state.get("ai_portfolio_result") if st.session_state.get("ai_portfolio_fingerprint") == current_portfolio_fingerprint else None
            if advice:
                st.divider()
                if advice.get("recommendation") == "HOLD_ALL":
                    st.error("HOLD SEMUA OBJEK — jangan memaksakan bidding.")
                else:
                    selected_ai = next((r for r in selected_rows if r["object_id"] == advice.get("selected_object_id")), None)
                    if selected_ai:
                        st.success(f"Prioritas AI: {selected_ai['name']} · Python status {selected_ai['status']} · indeks {selected_ai['score_pct']:.1f}%")
                        if selected_ai["status"] in {"HOLD", "NO-GO"}:
                            st.error("Hard-stop Python tetap berlaku. Objek ini tidak boleh ditafsirkan sebagai rekomendasi bidding.")
                st.write(advice.get("reason", ""))
                if advice.get("ranking_comment"):
                    st.caption(advice["ranking_comment"])
                if advice.get("top_risks"):
                    st.markdown("**Risiko utama**")
                    for item in advice["top_risks"]:
                        st.write(f"- {item}")
                if advice.get("conditions_before_bid"):
                    st.markdown("**Syarat sebelum bidding**")
                    for item in advice["conditions_before_bid"]:
                        st.write(f"- {item}")
        else:
            st.info("Centang satu atau beberapa objek pada kolom Bandingkan untuk membuat shortlist.")

        st.divider()
        st.subheader("Koreksi langsung dari Google Sheets")
        st.caption("Anda dapat memperbaiki kolom MASTER_OBJEK, SURVEI, BIAYA_RISIKO, COMPARABLES dan SKENARIO_PENGUASAAN di spreadsheet. Pilih objek di bawah lalu jalankan analisis ulang agar koreksi spreadsheet masuk ke hasil terbaru.")
        if repo:
            options = {f"{r['name']} · {r['lot_code']} · {r['object_id'][:8]}": r["object_id"] for r in ranked_all}
            picked_label = st.selectbox("Objek yang akan dihitung ulang dari data GSheets", list(options.keys()), key="recalc_object_choice")
            if st.button("↻ Muat koreksi GSheets & hitung ulang", use_container_width=True):
                try:
                    object_id = options[picked_label]
                    edited_inputs = repo.load_object_inputs(object_id)
                    profile = get_investor_profile()
                    live_cash_state = compute_cash_position(profile, get_transactions())
                    # Normalize stored profile strings and retain manual live cash calculation.
                    recalculated = run_property_analysis(edited_inputs, live_cash_state)
                    repo.save_analysis(recalculated)
                    st.session_state.last_snapshot = recalculated
                    st.success("Data terbaru dari Google Sheets telah dihitung ulang dan disimpan sebagai snapshot baru.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Tidak dapat menghitung ulang dari spreadsheet: {exc}")


# ------------------------------ Investor cash -------------------------------
with tab_cash:
    st.subheader("Cashflow & kapasitas bidding investor")
    st.caption("Saldo kas dihitung dari saldo baseline + transaksi IN/OUT yang dicatat manual. Ini bukan koneksi rekening bank; perbarui transaksi agar angka tetap mutakhir.")
    profile = investor_profile
    current_cash_state = cash_state
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo kas sekarang", idr(current_cash_state["live_cash"]))
    m2.metric("Komitmen proyek", idr(current_cash_state["ongoing_commitments"]))
    m3.metric("Cadangan keluarga + risiko", idr(current_cash_state["household_reserve"] + current_cash_state["risk_reserve"]))
    m4.metric("Kas untuk proyek baru", idr(current_cash_state["available_for_new"]))
    st.divider()
    col_profile, col_tx = st.columns([1, 1])
    with col_profile:
        st.markdown("#### A. Saldo dan komitmen investor")
        with st.form("investor_profile_form"):
            baseline_cash = st.number_input("Saldo kas pada tanggal baseline (Rp)", min_value=0, step=1_000_000, value=int(as_float(profile.get("baseline_cash"))), key="cash_baseline_input")
            baseline_date = st.date_input("Tanggal saldo baseline", value=date.fromisoformat(str(profile.get("baseline_date") or date.today().isoformat())[:10]), key="cash_baseline_date")
            ongoing_commitments = st.number_input("Komitmen proyek yang BELUM dibayar (Rp)", min_value=0, step=1_000_000, value=int(as_float(profile.get("ongoing_commitments"))), key="cash_commitments_input", help="Isi hanya sisa kewajiban yang belum dicatat sebagai transaksi OUT di ledger. Jangan masukkan pembayaran yang sudah mengurangi saldo kas agar tidak dihitung dua kali.")
            household_reserve = st.number_input("Cadangan rumah tangga / kewajiban rutin (Rp)", min_value=0, step=1_000_000, value=int(as_float(profile.get("household_reserve"))), key="cash_household_input")
            risk_reserve = st.number_input("Cadangan risiko minimum yang tidak boleh dipakai (Rp)", min_value=0, step=1_000_000, value=int(as_float(profile.get("risk_reserve"))), key="cash_risk_input")
            receivables = st.number_input("Piutang belum diterima (Rp) — tidak dihitung sebagai kas", min_value=0, step=1_000_000, value=int(as_float(profile.get("receivables_not_received"))), key="cash_receivables_input")
            investor_notes = st.text_area("Catatan pendanaan", value=str(profile.get("notes", "")), key="cash_notes_input")
            confirmed = st.checkbox("Angka saldo baseline, komitmen, dan cadangan telah saya periksa", value=as_bool(profile.get("profile_confirmed")), key="cash_profile_confirmed")
            save_profile = st.form_submit_button("Simpan profil investor", type="primary", use_container_width=True)
        if save_profile:
            new_profile = {
                "baseline_cash": baseline_cash, "baseline_date": baseline_date.isoformat(),
                "ongoing_commitments": ongoing_commitments, "household_reserve": household_reserve,
                "risk_reserve": risk_reserve, "receivables_not_received": receivables,
                "notes": investor_notes, "profile_confirmed": confirmed,
            }
            st.session_state.investor_profile_local = new_profile
            if repo:
                try:
                    repo.save_investor_profile(new_profile)
                    st.success("Profil investor tersimpan di Google Sheets.")
                except Exception as exc:
                    st.error(f"Gagal menyimpan profil: {exc}")
            else:
                st.warning("Profil tersimpan untuk sesi ini saja karena Google Sheets belum tersambung.")
            st.rerun()
    with col_tx:
        st.markdown("#### B. Catat transaksi kas")
        with st.form("cashflow_transaction_form"):
            transaction_date = st.date_input("Tanggal transaksi", value=date.today(), key="tx_date")
            direction = st.selectbox("Arus", ["IN", "OUT"], format_func=lambda x: "Uang masuk" if x == "IN" else "Uang keluar", key="tx_direction")
            category = st.selectbox("Kategori", ["Modal masuk", "Hasil penjualan", "Pelunasan lelang", "Renovasi", "Legalitas", "Kerahiman/pengosongan", "Holding", "Marketing", "Operasional", "Lainnya"], key="tx_category")
            amount = st.number_input("Nominal transaksi (Rp)", min_value=0, step=500_000, key="tx_amount")
            description = st.text_input("Deskripsi transaksi", key="tx_description")
            related_object = st.text_input("ID objek terkait (opsional)", key="tx_object_id")
            tx_notes = st.text_input("Catatan", key="tx_notes")
            add_tx = st.form_submit_button("＋ Catat transaksi", use_container_width=True)
        if add_tx:
            tx = {
                "transaction_date": transaction_date.isoformat(), "direction": direction, "category": category,
                "description": description, "amount": amount, "object_id": related_object, "notes": tx_notes,
            }
            if repo:
                try:
                    repo.add_cashflow(tx)
                    st.success("Transaksi tersimpan di ledger Google Sheets.")
                except Exception as exc:
                    st.error(f"Gagal menyimpan transaksi: {exc}")
            else:
                st.session_state.setdefault("cashflow_local", []).append(tx)
                st.success("Transaksi tercatat untuk sesi ini.")
            st.rerun()
    st.divider()
    st.markdown("#### C. Riwayat cashflow")
    txs = transactions
    if txs:
        tx_df = pd.DataFrame(txs)
        st.dataframe(tx_df, use_container_width=True, hide_index=True)
        csv = tx_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Unduh ledger CSV", data=csv, file_name="cashflow-ledger.csv", mime="text/csv")
    else:
        st.info("Belum ada transaksi. Masukkan transaksi setelah tanggal baseline untuk memperbarui saldo terhitung.")
    st.info("Piutang belum cair sengaja dikecualikan dari kas siap bidding. Saat ada dua aset berjalan, masukkan seluruh komitmen dan cadangan agar sistem tidak mengalokasikan modal yang sama dua kali.")


# ------------------------------- Data / guide -------------------------------
with tab_data:
    st.subheader("Database, integrasi dan panduan")
    if repo:
        st.success("Google Sheets tersambung dan tab database telah diperiksa.")
        st.markdown("#### Tab yang dikelola aplikasi")
        schema_info = [
            ("MASTER_OBJEK", "Satu baris per objek: identitas dan data pengumuman KPKNL."),
            ("SURVEI", "Satu baris per objek: temuan lapangan, okupansi dan kondisi fisik."),
            ("BIAYA_RISIKO", "Satu baris per objek: pajak, biaya, target return dan skor risiko."),
            ("COMPARABLES", "Satu baris per pembanding; hanya baris active=TRUE yang dipakai."),
            ("SKENARIO_PENGUASAAN", "Empat alternatif penguasaan; tidak dijumlahkan sebagai biaya pasti."),
            ("INVESTOR", "Satu profil saldo baseline, komitmen dan cadangan."),
            ("CASHFLOW", "Ledger uang masuk/keluar untuk menghitung saldo sekarang."),
            ("ANALISIS", "Snapshot hasil per analisis; histori lama tidak ditimpa."),
            ("RIWAYAT", "Audit trail penyimpanan dan perubahan profil."),
        ]
        st.dataframe(pd.DataFrame(schema_info, columns=["Tab", "Fungsi"]), use_container_width=True, hide_index=True)
    else:
        st.warning(sheets_error or "Google Sheets belum dikonfigurasi.")
    st.markdown("#### Penanganan Gemini API 429")
    st.write("Analisis finansial, pencarian maximum bid, indeks kelayakan, dan ranking dasar berjalan tanpa Gemini. Gemini hanya dipanggil saat Anda secara eksplisit menekan tombol review shortlist, membuat memo, atau mengekstrak dokumen.")
    st.markdown(
        """
        - Model default: `gemini-3.5-flash-lite`.
        - Satu request untuk seluruh shortlist, maksimal 8 objek.
        - Output dibatasi, prompt hanya berisi ringkasan angka dan hard blockers.
        - Hasil yang sama di-cache selama sesi; tidak mengulang request otomatis setelah 429.
        - Jika kuota habis, ranking Python tetap dipakai dan keputusan HOLD tetap berlaku.
        - Cek RPM, TPM, RPD dan kuota project di Google AI Studio → Rate limits.
        """
    )
    if GEMINI_API_KEY:
        st.success(f"Gemini dikonfigurasi: {GEMINI_MODEL}")
    else:
        st.info("GEMINI_API_KEY belum diisi. Tidak menghalangi kalkulasi atau simpan ke Sheets.")
    st.markdown("#### Batasan dan prinsip keselamatan")
    st.write("Aplikasi tidak mengambil data lelang otomatis dari lelang.go.id; user mengisi berdasarkan pengumuman resmi. Aplikasi tidak memiliki koneksi rekening bank; saldo diperbarui melalui baseline dan ledger manual. Harga comparable tetap perlu verifikasi, dan angka persentase kelayakan bukan probabilitas keberhasilan.")
    st.write("Tarif pajak, bea, dan legalitas harus dikonfirmasi untuk jenis lelang, objek, dan wilayah masing-masing. Jika data kritis belum terverifikasi, keputusan sistem akan HOLD meskipun profit indikatif terlihat menarik.")
    st.markdown("#### Referensi teknis")
    st.markdown("- [Google Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)\n- [Google Sheets API limits](https://developers.google.com/workspace/sheets/api/limits)\n- [Streamlit: private Google Sheets](https://docs.streamlit.io/develop/tutorials/databases/private-gsheet)\n- [Streamlit Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)")

st.sidebar.divider()
st.sidebar.markdown("**Status layanan**")
st.sidebar.write(f"Google Sheets: {'Terhubung' if repo else 'Belum terhubung'}")
st.sidebar.write(f"Gemini: {'Aktif' if GEMINI_API_KEY else 'Opsional / belum diatur'}")
st.sidebar.write(f"Model: `{GEMINI_MODEL}`")
st.sidebar.caption("Build 2.0 · Python-first financial engine")
