"""Central application defaults. Tax/legal rates are editable assumptions, not legal advice."""
APP_NAME = "Property Flipper Management System"
APP_VERSION = "1.0.2"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
MIN_ROI_PCT = 25.0
MID_ROI_PCT = 35.0
MIN_VALID_COMPARABLES_FOR_GO = 5
DEFAULT_NEGOTIATION_DISCOUNT_PCT = 10.0
DEFAULT_QUICK_SALE_DISCOUNT_PCT = 5.0
DEFAULT_LIQUIDITY_RESERVE_PCT = 20.0
GOOGLE_SHEETS_CACHE_TTL = 300

# These are initial assumptions for underwriting only. Verify the current rule for each lot/region.
DEFAULT_RULES = {
    "buyer_auction_fee_pct": 2.0,
    "bphtb_rate_pct": 5.0,
    "npoptkp": 80_000_000,
    "bphtb_basis_mode": "max_bid_or_njop",
    "bpn_pnbp_cost": 2_500_000,
    "roya_cost": 1_000_000,
    "other_acquisition_admin": 4_000_000,
    "acquisition_notary_ppat_fee": 0,
    "seller_final_tax_pct": 2.5,
    "seller_agent_pct": 2.5,
    "seller_ajb_ppat_pct": 1.0,
    "seller_misc_fixed": 5_000_000,
    "monthly_holding_cost": 1_000_000,
    "renovation_contingency_pct": 15.0,
    "minimum_roi_pct": MIN_ROI_PCT,
    "mid_roi_pct": MID_ROI_PCT,
    "negotiation_discount_pct": DEFAULT_NEGOTIATION_DISCOUNT_PCT,
    "quick_sale_discount_pct": DEFAULT_QUICK_SALE_DISCOUNT_PCT,
    "liquidity_reserve_pct": DEFAULT_LIQUIDITY_RESERVE_PCT,
}

OCCUPANCY_DEFAULTS = {
    "Belum Survei": {"expected_cost": 25_000_000, "risk_reserve": 100_000_000, "months": 6, "note": "Asumsi konservatif; HOLD sampai survei."},
    "Sudah Survei - Kosong/Tidak Dihuni": {"expected_cost": 3_000_000, "risk_reserve": 5_000_000, "months": 0.5, "note": "Cleaning, kunci, pengamanan awal."},
    "Sudah Survei - Dihuni (Keluar Sukarela)": {"expected_cost": 20_000_000, "risk_reserve": 10_000_000, "months": 1.5, "note": "Negosiasi dan perpindahan sukarela."},
    "Sudah Survei - Dihuni (Minta Kompensasi)": {"expected_cost": 25_000_000, "risk_reserve": 20_000_000, "months": 2.5, "note": "Estimasi kompensasi dan penundaan; editable."},
    "Sudah Survei - Dihuni (Menolak Keluar / Butuh Eksekusi)": {"expected_cost": 100_000_000, "risk_reserve": 100_000_000, "months": 9, "note": "Estimasi skenario formal yang sangat tidak pasti; wajib tinjau bantuan hukum."},
}

DECISION_STATUSES = ["DRAFT", "INCOMPLETE", "HOLD", "CONDITIONAL GO", "GO", "DO NOT BID"]
LIFECYCLE_STATUSES = ["PROSPECT", "BID PLANNED", "BID SUBMITTED", "WON", "LOST", "WITHDRAWN", "ACTIVE", "SOLD"]
PROJECT_STAGES = ["Settlement", "Possession & Legal", "Renovation", "Ready to Sell", "Listed for Sale", "Negotiation", "Sold / Closed"]
