from __future__ import annotations
from typing import Any
from .utils import to_float
from .renovation_engine import rab_item_is_in_scope


def bid_reference_status(
    result: dict[str, Any] | None,
    minimum_roi_pct: float,
    target_roi_pct: float,
    minimum_net_profit: float,
    target_holding_days: float,
    maximum_holding_days: float,
    cash_need: float | None = None,
    cash_available: float | None = None,
    provisional: bool = False,
    cash_confirmed: bool = True,
) -> str:
    """Explain the limit-reference underwriting gates consistently in the UI."""
    result = result or {}
    roi = result.get("roi_pct")
    profit = result.get("net_profit")
    days = to_float(result.get("projected_holding_days"))
    if roi is None:
        return "ROI BELUM DAPAT DIHITUNG"
    if profit is None:
        return "PROFIT BERSIH BELUM DAPAT DIHITUNG"
    if to_float(roi) < minimum_roi_pct:
        return f"ROI ALL-IN {to_float(roi):.1f}% DI BAWAH MINIMUM {minimum_roi_pct:.1f}% — JANGAN BID"
    if to_float(profit) < minimum_net_profit:
        return f"PROFIT BERSIH {to_float(profit):,.0f} DI BAWAH MINIMUM Rp{minimum_net_profit:,.0f} — JANGAN BID"
    if days <= 0:
        return "DURASI PROYEK BELUM TERSEDIA — HOLD, JANGAN BID"
    if maximum_holding_days > 0 and days > maximum_holding_days:
        return f"DURASI {days:.0f} HARI MELEWATI BATAS {maximum_holding_days:.0f} HARI — JANGAN BID"
    if not cash_confirmed:
        return "ROI/PROFIT MEMENUHI SYARAT, TETAPI KAS INVESTOR BELUM DIKONFIRMASI — HOLD"
    if cash_need is not None and cash_available is not None and cash_need > cash_available:
        return "ROI/PROFIT MEMENUHI SYARAT, TETAPI KAS TIDAK CUKUP"
    notes = []
    if target_holding_days > 0 and days > target_holding_days:
        notes.append(f"durasi {days:.0f} hari di atas target ideal {target_holding_days:.0f} hari")
    if to_float(roi) < target_roi_pct:
        notes.append(f"ROI belum mencapai target {target_roi_pct:.1f}%")
    if provisional:
        notes.append("analisis masih indikatif")
    if notes:
        return "MEMENUHI GATE MINIMUM; PERLU PERHATIAN: " + "; ".join(notes).upper()
    return f"MEMENUHI GATE — ROI ALL-IN {to_float(roi):.1f}%, PROFIT ≥ Rp{minimum_net_profit:,.0f}, DURASI ≤ {maximum_holding_days:.0f} HARI"


def evaluate_decision(inputs: dict[str, Any], market: dict[str, Any], tiers: dict[str, Any], at_limit: dict[str, Any] | None = None, min_comps: int = 5) -> dict[str, Any]:
    prop = inputs.get("property", {}); survey = inputs.get("survey", {}); legal = inputs.get("legal", {})
    blockers, warnings = [], []
    limit = to_float(prop.get("auction_limit")); max_bid = tiers.get("max_bid")
    rules = inputs.get("rules", {})
    min_roi = to_float(rules.get("minimum_roi_pct", 20))
    min_profit = max(0.0, to_float(rules.get("minimum_net_profit", 0)))
    target_days = to_float(rules.get("target_holding_days", 90))
    maximum_days = to_float(rules.get("maximum_holding_days", 180))
    if not prop.get("lot_code") or not prop.get("address") or limit <= 0: blockers.append("Identitas lot, alamat atau nilai limit belum lengkap.")
    if to_float(prop.get("land_area")) <= 0: blockers.append("Luas tanah belum terverifikasi.")
    if to_float(prop.get("building_area")) <= 0 and prop.get("property_type") != "Tanah kosong": blockers.append("Luas bangunan belum terverifikasi.")
    if not survey.get("survey_status") or survey.get("survey_status") == "Belum Survei": blockers.append("Survei lapangan belum dilakukan.")
    if not legal.get("identity_verified"): blockers.append("Identitas objek dan dokumen hak belum diverifikasi.")
    if legal.get("dispute_detected"): blockers.append("Ada indikasi sengketa atau ketidaksesuaian kritis.")
    if not legal.get("tax_rules_verified"): blockers.append("Tarif dan dasar BPHTB/biaya lelang belum diverifikasi untuk wilayah dan jenis transaksi ini.")
    if not inputs.get("risk_reviewed", False): blockers.append("Risk register belum ditinjau dan dikonfirmasi pengguna.")
    if not inputs.get("costs", {}).get("cost_estimates_reviewed", False): blockers.append("Seluruh estimasi biaya belum ditinjau/dikonfirmasi pengguna; pastikan tidak ada komponen yang dibiarkan nol tanpa alasan.")
    # Any item that the user keeps in the base budget (Wajib/Disarankan/Opsional)
    # must have a measured positive quantity and conservative unit rate. A user
    # may remove unconfirmed scope by selecting Bersyarat or Tidak diperlukan.
    renovation_items = inputs.get("costs", {}).get("renovation_items", []) or []
    unpriced_in_scope = [
        str(r.get("work_item") or r.get("item_code") or "Pekerjaan dalam anggaran")
        for r in renovation_items
        if rab_item_is_in_scope(r)
        and (r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, ""))
    ]
    if unpriced_in_scope:
        blockers.append(
            "RAB masih memiliki pekerjaan wajib atau item anggaran dasar tanpa volume/harga konservatif: "
            + "; ".join(unpriced_in_scope[:5])
            + ". Lengkapi volume dan harga, atau ubah menjadi Bersyarat/Tidak diperlukan jika belum disetujui setelah verifikasi."
        )
    risk_summary = inputs.get("risk_summary", {})
    if risk_summary.get("invalid"):
        blockers.extend(risk_summary["invalid"][:5])
    if risk_summary.get("critical_open"):
        blockers.append("Risiko kritis belum dimitigasi/ditutup: " + "; ".join(risk_summary["critical_open"][:3]))
    if risk_summary.get("severe_unmitigated"):
        blockers.append("Ada risiko dengan severity ≥20 tanpa rencana mitigasi: " + "; ".join(risk_summary["severe_unmitigated"][:3]))
    if market.get("valid_count", 0) < min_comps: blockers.append(f"Comparable yang dapat dipakai untuk valuasi indikatif baru {market.get('valid_count', 0)}; minimal {min_comps}.")
    if market.get("go_grade_count", 0) < min_comps:
        blockers.append(f"Comparable yang dapat ditelusuri untuk persetujuan GO baru {market.get('go_grade_count', 0)}; minimal {min_comps} URL listing langsung dengan tanggal ditemukan.")
    if market.get("confidence", 0) < 55: blockers.append("Confidence data pasar di bawah batas awal 55/100.")
    if not tiers.get("increment_confirmed"): blockers.append("Kelipatan bid belum dikonfirmasi.")
    at_limit = at_limit or {}
    roi_at_limit = at_limit.get("roi_pct")
    cash_need = to_float(at_limit.get("cash_requirement_including_reserve", at_limit.get("capital_before_sale")))
    cash_available = to_float(inputs.get("finance", {}).get("cash_available_for_new_project", inputs.get("finance", {}).get("cash_available")))
    cash_confirmed = bool(inputs.get("finance", {}).get("cash_confirmed"))
    profit_at_limit = at_limit.get("net_profit")
    duration_days = to_float(at_limit.get("projected_holding_days"))
    duration_missing = bool(maximum_days > 0 and duration_days <= 0)
    duration_failure = bool(maximum_days > 0 and duration_days > maximum_days)
    roi_failure = roi_at_limit is not None and to_float(roi_at_limit) < min_roi
    profit_failure = profit_at_limit is not None and to_float(profit_at_limit) < min_profit
    # A time overrun is a hard NO-GO only when a usable ARV makes the financial
    # comparison computable. Missing ARV remains HOLD/incomplete, never a fake fail.
    duration_failure_applies = duration_failure and roi_at_limit is not None and profit_at_limit is not None
    financial_failure = bool(roi_failure or profit_failure or duration_failure_applies)
    funding_failure = cash_need > cash_available or not cash_confirmed
    if not cash_confirmed: blockers.append("Real cash investor belum diperbarui/dikonfirmasi.")
    elif cash_need > cash_available: blockers.append(f"Kas siap investasi tidak mencukupi; kebutuhan {cash_need:,.0f}, tersedia {cash_available:,.0f}.")
    if roi_failure: blockers.append(f"Pada nilai limit, Project ROI all-in konservatif {to_float(roi_at_limit):.1f}% di bawah minimum {min_roi:.1f}%.")
    if profit_failure: blockers.append(f"Profit bersih konservatif pada nilai limit {to_float(profit_at_limit):,.0f} belum mencapai minimum Rp{min_profit:,.0f}.")
    if duration_missing:
        blockers.append("Estimasi durasi proyek belum tersedia; lengkapi asumsi penguasaan, legalitas, renovasi, dan pemasaran sebelum keputusan bidding.")
    elif duration_failure: blockers.append(f"Estimasi durasi proyek {duration_days:.0f} hari melewati batas maksimum {maximum_days:.0f} hari.")
    elif duration_days > target_days > 0:
        warnings.append(f"Estimasi durasi {duration_days:.0f} hari berada di atas target ideal {target_days:.0f} hari; evaluasi okupansi, legalitas, renovasi, dan pemasaran.")
    if max_bid is None and not financial_failure and not funding_failure:
        blockers.append("Maximum bid belum dapat ditentukan; periksa increment dan batas risiko.")
    if max_bid is not None and max_bid < limit: financial_failure = True
    risk_ceiling = prop.get("risk_adjusted_ceiling")
    risk_failure = risk_ceiling not in (None, "", 0, "0") and to_float(risk_ceiling) < limit
    if legal.get("dispute_detected") or financial_failure or risk_failure:
        if risk_failure: blockers.append("Risk-adjusted ceiling berada di bawah nilai limit.")
        status = "DO NOT BID"
    elif blockers:
        status = "HOLD"
    else:
        status = "GO"
    if roi_at_limit is not None and to_float(roi_at_limit) >= min_roi and to_float(roi_at_limit) < to_float(rules.get("mid_roi_pct", 30)):
        warnings.append(f"Project ROI all-in memenuhi minimum {min_roi:.1f}%, tetapi belum mencapai target {to_float(rules.get('mid_roi_pct', 30)):.1f}%. Pertimbangkan penurunan bid atau perbaikan biaya sebelum bidding.")
    if market.get("valid_count", 0) >= min_comps and market.get("confidence", 0) < 70:
        reasons = []
        if market.get("listing_date_missing_count", 0):
            reasons.append(f"{market.get('listing_date_missing_count')} listing tidak mencantumkan tanggal terbit")
        if market.get("unconfirmed_url_count", 0):
            reasons.append(f"{market.get('unconfirmed_url_count')} URL belum dikonfirmasi sebagai listing individual")
        if market.get("date_found_missing_count", 0):
            reasons.append(f"{market.get('date_found_missing_count')} listing belum memiliki tanggal ditemukan")
        suffix = (" Penyebab utama: " + "; ".join(reasons) + ".") if reasons else " Periksa kemiripan lokasi/luas, kondisi, akses, serta sebaran harga pembanding."
        warnings.append(f"Jumlah comparable telah memenuhi minimum, tetapi confidence pasar {market.get('confidence', 0)}/100 masih di bawah 70/100.{suffix}")
    if survey.get("interior_inspected") is False:
        warnings.append("Interior belum diperiksa; risiko renovasi dapat berubah.")
        if status == "GO":
            status = "CONDITIONAL GO"
    summary = "Memenuhi seluruh gate utama." if status == "GO" else ("Tidak layak mengikuti bidding berdasarkan batas finansial, profit minimum, durasi maksimum, atau hard stop." if status == "DO NOT BID" else "Data atau syarat kritis belum terpenuhi; jangan bidding dulu.")
    return {"status": status, "blockers": blockers, "warnings": warnings, "summary": summary,
            "minimum_roi_pct": min_roi, "target_roi_pct": to_float(rules.get("mid_roi_pct", 30)),
            "minimum_net_profit": min_profit, "target_holding_days": target_days,
            "maximum_holding_days": maximum_days, "projected_holding_days": duration_days, "duration_missing": duration_missing}
