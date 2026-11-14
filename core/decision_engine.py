from __future__ import annotations
from typing import Any
from .utils import to_float


def evaluate_decision(inputs: dict[str, Any], market: dict[str, Any], tiers: dict[str, Any], at_limit: dict[str, Any] | None = None, min_comps: int = 5) -> dict[str, Any]:
    prop = inputs.get("property", {}); survey = inputs.get("survey", {}); legal = inputs.get("legal", {})
    blockers, warnings = [], []
    limit = to_float(prop.get("auction_limit")); max_bid = tiers.get("max_bid")
    min_roi = to_float(inputs.get("rules", {}).get("minimum_roi_pct", 25))
    if not prop.get("lot_code") or not prop.get("address") or limit <= 0: blockers.append("Identitas lot, alamat atau nilai limit belum lengkap.")
    if to_float(prop.get("land_area")) <= 0: blockers.append("Luas tanah belum terverifikasi.")
    if to_float(prop.get("building_area")) <= 0 and prop.get("property_type") != "Tanah kosong": blockers.append("Luas bangunan belum terverifikasi.")
    if not survey.get("survey_status") or survey.get("survey_status") == "Belum Survei": blockers.append("Survei lapangan belum dilakukan.")
    if not legal.get("identity_verified"): blockers.append("Identitas objek dan dokumen hak belum diverifikasi.")
    if legal.get("dispute_detected"): blockers.append("Ada indikasi sengketa atau ketidaksesuaian kritis.")
    if not legal.get("tax_rules_verified"): blockers.append("Tarif dan dasar BPHTB/biaya lelang belum diverifikasi untuk wilayah dan jenis transaksi ini.")
    if not inputs.get("risk_reviewed", False): blockers.append("Risk register belum ditinjau dan dikonfirmasi pengguna.")
    if not inputs.get("costs", {}).get("cost_estimates_reviewed", False): blockers.append("Seluruh estimasi biaya belum ditinjau/dikonfirmasi pengguna; pastikan tidak ada komponen yang dibiarkan nol tanpa alasan.")
    # Mandatory RAB rows must have both a measurable quantity and conservative unit cost.
    # Conditional/optional inspection rows can remain blank, but must not be priced as zero.
    renovation_items = inputs.get("costs", {}).get("renovation_items", []) or []
    unpriced_required = [
        str(r.get("work_item") or r.get("item_code") or "Pekerjaan wajib")
        for r in renovation_items
        if str(r.get("priority") or "").lower() == "wajib"
        and (r.get("quantity") in (None, "") or r.get("unit_cost") in (None, ""))
    ]
    if unpriced_required:
        blockers.append("RAB masih memiliki pekerjaan wajib tanpa volume/harga konservatif: " + "; ".join(unpriced_required[:5]) + ". Lengkapi atau verifikasi sebelum GO.")
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
    financial_failure = roi_at_limit is not None and (to_float(roi_at_limit) < min_roi or (at_limit.get("net_profit") is not None and to_float(at_limit.get("net_profit")) <= 0))
    funding_failure = cash_need > cash_available or not cash_confirmed
    if not cash_confirmed: blockers.append("Real cash investor belum diperbarui/dikonfirmasi.")
    elif cash_need > cash_available: blockers.append(f"Kas siap investasi tidak mencukupi; kebutuhan {cash_need:,.0f}, tersedia {cash_available:,.0f}.")
    if financial_failure: blockers.append(f"Pada nilai limit, ROI konservatif {to_float(roi_at_limit):.1f}% tidak mencapai minimum {min_roi:.1f}%.")
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
    if market.get("valid_count", 0) >= min_comps and market.get("confidence", 0) < 70:
        warnings.append("Pasar memenuhi jumlah minimum, tetapi kualitas pembanding masih perlu ditinjau.")
    if survey.get("interior_inspected") is False:
        warnings.append("Interior belum diperiksa; risiko renovasi dapat berubah.")
    if status == "GO" and warnings: status = "CONDITIONAL GO"
    return {"status": status, "blockers": blockers, "warnings": warnings, "summary": "Memenuhi seluruh gate utama." if status == "GO" else ("Tidak layak mengikuti bidding berdasarkan batas finansial/hard stop." if status == "DO NOT BID" else "Data atau syarat kritis belum terpenuhi; jangan bidding dulu.")}
