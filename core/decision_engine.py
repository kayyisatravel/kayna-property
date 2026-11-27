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


def _contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    text = str(value or "").strip().lower()
    return any(term in text for term in terms)


def evaluate_decision(
    inputs: dict[str, Any],
    market: dict[str, Any],
    tiers: dict[str, Any],
    at_limit: dict[str, Any] | None = None,
    min_comps: int = 5,
    no_bid_case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify investment attractiveness separately from permission to bid.

    `status` is retained as a backward-compatible alias for `investment_status`.
    Cash, auction increment, and final GO-grade market evidence affect
    `bid_readiness`; they do not by themselves erase an otherwise investable
    opportunity. Unknown material facts still produce HOLD, and explicit,
    non-mitigable risks produce DO NOT BID.
    """
    prop = inputs.get("property", {}) or {}
    survey = inputs.get("survey", {}) or {}
    legal = inputs.get("legal", {}) or {}
    costs = inputs.get("costs", {}) or {}
    rules = inputs.get("rules", {}) or {}
    risk_summary = inputs.get("risk_summary", {}) or {}
    finance = inputs.get("finance", {}) or {}
    at_limit = at_limit or {}
    no_bid_case = no_bid_case or {}

    # Policy thresholds. The legacy minimum_roi_pct remains the minimum
    # actionable-bid hurdle; investment classification has its own 15%/25%
    # thresholds so they can be tuned without silently changing bid math.
    min_conditional_roi = max(0.0, to_float(rules.get("conditional_minimum_roi_pct", 15.0)))
    go_roi = max(min_conditional_roi, to_float(rules.get("go_minimum_roi_pct", 25.0)))
    bid_min_roi = max(0.0, to_float(rules.get("minimum_roi_pct", 20.0)))
    min_profit = max(0.0, to_float(rules.get("minimum_net_profit", 50_000_000.0)))
    target_days = max(0.0, to_float(rules.get("target_holding_days", 90.0)))
    go_max_days = max(1.0, to_float(rules.get("maximum_holding_days", 180.0)))
    conditional_max_days = max(go_max_days, to_float(rules.get("conditional_maximum_holding_days", 365.0)))
    conditional_market_confidence = max(0.0, to_float(rules.get("conditional_market_confidence_pct", 45.0)))
    go_market_confidence = max(conditional_market_confidence, to_float(rules.get("go_market_confidence_pct", 55.0)))
    conditional_min_comps = max(1, int(to_float(rules.get("conditional_min_comparables", 3))))
    go_min_comps = max(conditional_min_comps, int(to_float(rules.get("go_min_comparables", min_comps))))
    renovation_contingency_min = max(0.0, to_float(rules.get("renovation_contingency_min_pct", 15.0)))
    heavy_renovation_contingency_min = max(renovation_contingency_min, to_float(rules.get("heavy_renovation_contingency_min_pct", 20.0)))

    hold_reasons: list[str] = []
    hard_stops: list[str] = []
    conditions: list[str] = []
    readiness_issues: list[dict[str, str]] = []
    warnings: list[str] = []

    def add_hold(message: str, category: str = "DATA") -> None:
        if message not in hold_reasons:
            hold_reasons.append(message)
        readiness_issues.append({"category": category, "message": message})

    def add_condition(message: str, category: str = "MITIGATION", readiness_required: bool = True) -> None:
        if message not in conditions:
            conditions.append(message)
        if readiness_required:
            readiness_issues.append({"category": category, "message": message})

    def add_readiness(message: str, category: str) -> None:
        if not any(x["message"] == message for x in readiness_issues):
            readiness_issues.append({"category": category, "message": message})

    # --- Fatal / non-mitigable risks (explicit confirmation only) ---
    if bool(legal.get("fatal_legal_issue_confirmed", False)):
        hard_stops.append("Cacat hukum/gugatan material telah dikonfirmasi sebagai risiko yang tidak dapat dimitigasi.")
    if bool(survey.get("fatal_security_threat_confirmed", False)):
        hard_stops.append("Ancaman keamanan atau perlawanan fisik yang tidak dapat diterima telah dikonfirmasi.")
    if bool(prop.get("fatal_access_or_environment_confirmed", False)):
        hard_stops.append("Akses legal atau kondisi lingkungan fatal telah dikonfirmasi.")

    risk_items = list(risk_summary.get("items") or [])
    for risk in risk_items:
        if bool(risk.get("hard_stop_confirmed", False)):
            description = str(risk.get("risk_description") or "Risiko fatal terkonfirmasi").strip()
            hard_stops.append(f"Hard stop terkonfirmasi: {description}.")

    # --- Core data / due-diligence completeness: unknown means HOLD ---
    limit = to_float(prop.get("auction_limit"))
    if not prop.get("lot_code") or not prop.get("address") or limit <= 0:
        add_hold("Identitas lot, alamat atau nilai limit belum lengkap.", "LEGAL")
    if to_float(prop.get("land_area")) <= 0:
        add_hold("Luas tanah belum terverifikasi.", "LEGAL")
    if to_float(prop.get("building_area")) <= 0 and prop.get("property_type") != "Tanah kosong":
        add_hold("Luas bangunan belum terverifikasi.", "LEGAL")

    survey_status = str(survey.get("survey_status") or survey.get("occupancy_status") or "").strip()
    if not survey_status or survey_status == "Belum Survei":
        add_hold("Survei lapangan belum dilakukan; kondisi interior, fisik, akses dan penghuni belum cukup diketahui.", "SURVEY")
    if not str(survey.get("physical_condition") or "").strip() or _contains_any(survey.get("physical_condition"), ("belum diketahui",)):
        add_hold("Kondisi fisik umum belum diketahui dari survei.", "SURVEY")
    if not bool(survey.get("structure_verified_safe", False)):
        add_hold("Struktur utama/pondasi/dinding penopang belum diperiksa dan dinyatakan bebas dari kerusakan struktural fatal.", "SURVEY")
    if not legal.get("identity_verified"):
        add_hold("Identitas objek dan dokumen hak belum diverifikasi.", "LEGAL")
    original_doc_status = str(legal.get("original_certificate_status") or "").strip()
    if original_doc_status != "Asli di bank/kreditur dan siap diserahkan":
        add_hold("Lokasi dan kesiapan penyerahan dokumen asli sertifikat belum dikonfirmasi pada bank/kreditur.", "LEGAL")
    if legal.get("dispute_detected"):
        add_hold("Ada indikasi sengketa/ketidaksesuaian kritis yang belum diklarifikasi.", "LEGAL")
    if not legal.get("tax_rules_verified"):
        add_hold("Tarif dan dasar BPHTB/biaya lelang belum diverifikasi untuk wilayah dan jenis transaksi ini.", "LEGAL")
    if not inputs.get("risk_reviewed", False):
        add_hold("Risk register belum ditinjau dan dikonfirmasi pengguna.", "MITIGATION")
    if not costs.get("cost_estimates_reviewed", False):
        add_hold("Estimasi biaya proyek belum ditinjau/dikonfirmasi pengguna.", "MITIGATION")

    renovation_items = costs.get("renovation_items", []) or []
    unpriced_in_scope = [
        str(r.get("work_item") or r.get("item_code") or "Pekerjaan dalam anggaran")
        for r in renovation_items
        if rab_item_is_in_scope(r)
        and (r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, ""))
    ]
    if unpriced_in_scope:
        add_hold(
            "RAB masih memiliki pekerjaan wajib atau item anggaran dasar tanpa volume/harga konservatif dalam lingkup: "
            + "; ".join(unpriced_in_scope[:5]) + ". Lengkapi RAB atau ubah scope setelah verifikasi.",
            "MITIGATION",
        )

    if risk_summary.get("invalid"):
        for item in risk_summary["invalid"][:5]:
            add_hold(str(item), "MITIGATION")
    if risk_summary.get("severe_unmitigated"):
        add_hold(
            "Ada risiko severity ≥20 tanpa rencana mitigasi: "
            + "; ".join(risk_summary["severe_unmitigated"][:3]),
            "MITIGATION",
        )

    # Critical risks are not automatically fatal. A measured, priced and
    # mitigatable issue can remain CONDITIONAL GO; unknown legal/identity issues
    # still HOLD until verified. Explicit hard_stop_confirmed is DO NOT BID.
    critical_open = list(risk_summary.get("critical_open") or [])
    critical_item_map = {
        str(item.get("risk_description") or "").strip(): item
        for item in risk_items
        if str(item.get("risk_description") or "").strip()
    }
    for description in critical_open:
        item = critical_item_map.get(str(description).strip(), {})
        category = str(item.get("category") or "").lower()
        text = str(description or "").lower()
        legal_risk = any(word in category or word in text for word in (
            "legal", "legalitas", "sengketa", "sita", "klaim pihak ketiga", "dokumen", "sertifikat", "hak ganda"
        ))
        if legal_risk:
            add_hold(f"Risiko legal material masih terbuka: {description}.", "LEGAL")
        elif item and str(item.get("mitigation") or "").strip() and to_float(item.get("cost_reserve")) > 0:
            add_condition(f"Risiko kritis perlu ditangani sesuai mitigasi dan cadangan Rp{to_float(item.get('cost_reserve')):,.0f}: {description}.", "MITIGATION")
        else:
            add_hold(f"Risiko kritis belum memiliki mitigasi dan cadangan biaya yang memadai: {description}.", "MITIGATION")

    # --- Market evidence ---
    # The minimum comparable count and confidence must refer to the exact
    # condition cohort used for the exit valuation, not the wider mixed pool.
    valuation_count = int(to_float(market.get("arv_condition_comparable_count", market.get("valuation_comparable_count", market.get("valid_count", 0)))))
    go_grade_count = int(to_float(market.get("go_grade_count", 0)))
    confidence = to_float(market.get("arv_condition_confidence", market.get("confidence")))
    if valuation_count < conditional_min_comps:
        add_hold(
            f"Comparable untuk valuasi indikatif baru {valuation_count}; minimal {conditional_min_comps} pembanding setara diperlukan.",
            "MARKET",
        )
    elif confidence < conditional_market_confidence:
        add_hold(
            f"Confidence bukti pasar {confidence:.1f}/100 masih di bawah batas indikatif {conditional_market_confidence:.1f}/100.",
            "MARKET",
        )
    elif valuation_count < go_min_comps or go_grade_count < go_min_comps or confidence < go_market_confidence or market.get("status") != "READY":
        add_condition(
            f"Bukti pasar cukup untuk penilaian bersyarat, tetapi belum mencapai standar GO: {go_grade_count} dari {go_min_comps} listing individual bertanggal; confidence {confidence:.1f}/100.",
            "MARKET",
        )
        add_readiness("Standar bukti pasar final belum terpenuhi (minimal lima URL listing individual dengan tanggal ditemukan dan confidence sesuai kebijakan).", "MARKET")

    # --- Financial viability at the current auction limit ---
    roi = at_limit.get("roi_pct")
    profit = at_limit.get("net_profit")
    duration_days = to_float(at_limit.get("projected_holding_days"))
    no_bid_profit = no_bid_case.get("net_profit")
    if roi is None or profit is None:
        add_hold("ARV atau perhitungan profit/ROI konservatif belum tersedia.", "MARKET")
    else:
        roi_value = to_float(roi)
        profit_value = to_float(profit)
        if no_bid_profit is not None and to_float(no_bid_profit) <= 0:
            hard_stops.append("Secara struktural proyek tidak menghasilkan profit bahkan pada simulasi harga akuisisi nol; jangan diteruskan.")
        elif roi_value < min_conditional_roi or profit_value < min_profit:
            add_hold(
                f"Ekonomi pada nilai limit belum memenuhi batas bersyarat: Project ROI {roi_value:.1f}% (minimum {min_conditional_roi:.1f}%) dan profit Rp{profit_value:,.0f} (minimum Rp{min_profit:,.0f}). Pertimbangkan menunggu limit lelang ulang atau perubahan asumsi yang dapat dibuktikan.",
                "ECONOMICS",
            )
        elif roi_value < go_roi:
            add_condition(
                f"Project ROI {roi_value:.1f}% berada pada rentang CONDITIONAL GO {min_conditional_roi:.1f}–<{go_roi:.1f}%; patuhi MAO dan jangan mengejar harga saat bidding.",
                "ECONOMICS",
                readiness_required=False,
            )

    risk_ceiling = prop.get("risk_adjusted_ceiling")
    if risk_ceiling not in (None, "", 0, "0") and to_float(risk_ceiling) < limit:
        add_hold("Nilai limit melampaui hard ceiling bid yang ditetapkan investor; tunggu limit lelang ulang atau ubah batas hanya setelah analisis ulang.", "ECONOMICS")

    if duration_days <= 0:
        add_hold("Estimasi durasi proyek belum tersedia.", "SURVEY")
    elif duration_days > conditional_max_days:
        add_hold(
            f"Estimasi durasi proyek {duration_days:.0f} hari melebihi batas bersyarat {conditional_max_days:.0f} hari; biaya modal dan risiko penjualan terlalu panjang.",
            "ECONOMICS",
        )
    elif duration_days > go_max_days:
        add_condition(
            f"Estimasi holding period {duration_days:.0f} hari melewati target GO {go_max_days:.0f} hari; siapkan buffer biaya modal dan skenario exit.",
            "ECONOMICS",
            readiness_required=False,
        )
    elif target_days > 0 and duration_days > target_days:
        warnings.append(f"Estimasi durasi {duration_days:.0f} hari di atas target ideal {target_days:.0f} hari.")

    # --- Occupancy and physical work profile ---
    survey_status_normalized = survey_status.lower()
    # Important: the official vacant status contains the substring "dihuni"
    # inside "Tidak Dihuni". Classify explicit vacant wording before checking
    # for occupied wording to avoid treating every vacant house as occupied.
    is_vacant = "kosong" in survey_status_normalized or "tidak dihuni" in survey_status_normalized
    is_occupied = "dihuni" in survey_status_normalized and not is_vacant
    possession_plan_confirmed = bool(survey.get("possession_plan_confirmed", False))

    if "menolak keluar" in survey_status_normalized or "butuh eksekusi" in survey_status_normalized:
        add_hold("Penghuni belum kooperatif dan skenario pengosongan memerlukan eksekusi; tahan sampai jalur hukum, waktu, dan biaya dapat diverifikasi.", "SURVEY")
    elif is_occupied:
        if "keluar sukarela" in survey_status_normalized:
            add_condition(
                "Objek masih berpenghuni dan berpotensi dikosongkan sukarela; rencana, jadwal, dan pembiayaannya harus terdokumentasi.",
                "SURVEY",
                readiness_required=not possession_plan_confirmed,
            )
        elif "minta kompensasi" in survey_status_normalized:
            if to_float(survey.get("possession_cost")) > 0 and to_float(survey.get("possession_risk_reserve")) > 0:
                add_condition(
                    "Objek masih berpenghuni dan memerlukan kompensasi; pastikan skenario cash-for-keys, jadwal, dan dana cadangan telah disepakati/terdokumentasi.",
                    "SURVEY",
                    readiness_required=not possession_plan_confirmed,
                )
            else:
                add_hold("Objek berpenghuni meminta kompensasi, tetapi biaya dan cadangan pengosongan belum terukur.", "SURVEY")
        else:
            add_hold("Status penghuni belum menunjukkan rencana pengosongan yang kooperatif dan terukur.", "SURVEY")
        if not possession_plan_confirmed:
            add_readiness("Rencana pengosongan/cash-for-keys belum dikonfirmasi dan didokumentasikan.", "POSSESSION")

    physical = str(survey.get("physical_condition") or "").lower()
    is_heavy_renovation = "renovasi berat" in physical
    is_medium_renovation = "renovasi sedang" in physical
    is_light_renovation = "renovasi ringan" in physical
    is_cosmetic = "kosmetik" in physical
    is_ready_condition = "siap huni" in physical or is_cosmetic
    if is_medium_renovation or is_heavy_renovation:
        if not bool(survey.get("interior_inspected", False)):
            add_hold("Renovasi sedang/berat belum diperiksa dari interior; inspeksi teknis diperlukan sebelum menetapkan biaya dan margin.", "SURVEY")
        else:
            renovation_cost = max(0.0, to_float(at_limit.get("renovation_cost")))
            contingency_amount = max(0.0, to_float(at_limit.get("renovation_contingency")))
            actual_contingency_pct = (contingency_amount / renovation_cost * 100.0) if renovation_cost > 0 else 0.0
            required_pct = heavy_renovation_contingency_min if is_heavy_renovation else renovation_contingency_min
            if actual_contingency_pct + 1e-9 < required_pct:
                add_hold(
                    f"Contingency RAB {actual_contingency_pct:.1f}% di bawah minimum kebijakan {required_pct:.1f}% untuk renovasi {'berat' if is_heavy_renovation else 'sedang'}.",
                    "MITIGATION",
                )
            else:
                add_condition("Renovasi sedang/berat telah diinspeksi; pertahankan contingency dan kontrol perubahan pekerjaan.", "MITIGATION", readiness_required=False)
    elif is_light_renovation:
        add_condition("Objek memerlukan renovasi ringan; pastikan seluruh item dan volume masuk RAB.", "MITIGATION", readiness_required=False)
    elif not is_ready_condition and prop.get("property_type") != "Tanah kosong":
        add_hold("Kondisi bangunan belum cukup jelas untuk mengestimasi pekerjaan renovasi.", "SURVEY")

    if survey_status and survey_status != "Belum Survei" and survey.get("interior_inspected") is False and prop.get("property_type") != "Tanah kosong":
        add_hold("Interior belum diperiksa; risiko tersembunyi belum cukup diketahui untuk keputusan investasi final.", "SURVEY")

    # --- Bid readiness is independent from asset attractiveness ---
    cash_need = to_float(at_limit.get("cash_requirement_including_reserve", at_limit.get("capital_before_sale")))
    cash_available = to_float(finance.get("cash_available_for_new_project", finance.get("cash_available")))
    cash_confirmed = bool(finance.get("cash_confirmed"))
    if not cash_confirmed:
        add_readiness("Kas investor belum diperbarui/dikonfirmasi.", "CASH")
    elif cash_need > cash_available:
        add_readiness(f"Kas siap investasi kurang Rp{cash_need - cash_available:,.0f}; kebutuhan Rp{cash_need:,.0f}, tersedia Rp{cash_available:,.0f}.", "CASH")

    if roi is not None and to_float(roi) < bid_min_roi:
        add_readiness(f"ROI {to_float(roi):.1f}% di bawah minimum Project ROI untuk bidding {bid_min_roi:.1f}%.", "ECONOMICS")
    elif profit is not None and to_float(profit) < min_profit:
        add_readiness(f"Profit bersih di bawah minimum Rp{min_profit:,.0f}.", "ECONOMICS")

    max_bid = tiers.get("max_bid")
    max_economic_ceiling = tiers.get("max_economic_ceiling")
    simulated_ceiling = tiers.get("max_simulated_ceiling")
    mao_full_cost = max_bid if max_bid is not None else simulated_ceiling if simulated_ceiling is not None else max_economic_ceiling
    if max_economic_ceiling is not None and to_float(max_economic_ceiling) < limit:
        add_readiness(
            f"Nilai limit Rp{limit:,.0f} berada di atas MAO Full Cost sekitar Rp{to_float(max_economic_ceiling):,.0f}; jangan mengikuti bidding pada harga ini.",
            "ECONOMICS",
        )
    elif max_bid is None and simulated_ceiling is None and max_economic_ceiling is None and not tiers.get("increment_confirmed"):
        add_readiness("MAO Full Cost belum dapat diubah menjadi batas bid karena increment lelang resmi belum dikonfirmasi.", "AUCTION DATA")
    if not tiers.get("increment_confirmed"):
        add_readiness("Kelipatan bid resmi belum dikonfirmasi dari pengumuman lelang.", "AUCTION DATA")

    if not legal.get("identity_verified") or not legal.get("tax_rules_verified") or legal.get("dispute_detected"):
        add_readiness("Verifikasi legalitas, status sengketa, atau aturan pajak objek belum tuntas.", "LEGAL")
    if survey_status == "Belum Survei" or not survey.get("interior_inspected", False):
        add_readiness("Survei dan/atau pemeriksaan interior belum memadai untuk eksekusi bidding.", "SURVEY")
    if not inputs.get("risk_reviewed", False) or risk_summary.get("critical_open") or risk_summary.get("severe_unmitigated"):
        add_readiness("Mitigasi risiko belum dituntaskan dan ditinjau kembali.", "MITIGATION")
    if not costs.get("cost_estimates_reviewed", False) or unpriced_in_scope:
        add_readiness("Biaya proyek/RAB belum sepenuhnya terverifikasi.", "MITIGATION")

    # --- Final classification ---
    hard_stops = list(dict.fromkeys(hard_stops))
    if hard_stops:
        investment_status = "DO NOT BID"
    elif hold_reasons:
        investment_status = "HOLD"
    elif conditions:
        investment_status = "CONDITIONAL GO"
    else:
        investment_status = "GO"

    # Only a fully underwritten and executable opportunity is bid-ready.
    # CONDITIONAL GO can be READY when its mitigation conditions are priced,
    # evidenced and reflected in the financial model.
    if investment_status in {"HOLD", "DO NOT BID"}:
        bid_readiness = "NOT READY — DUE DILIGENCE"
    elif readiness_issues:
        categories = list(dict.fromkeys(x["category"] for x in readiness_issues))
        bid_readiness = f"NOT READY — {categories[0]}" if len(categories) == 1 else "NOT READY — MULTIPLE GATES"
    else:
        bid_readiness = "READY"

    if roi is not None and to_float(roi) >= bid_min_roi and to_float(roi) < to_float(rules.get("mid_roi_pct", 30.0)):
        warnings.append(
            f"Project ROI memenuhi minimum bidding {bid_min_roi:.1f}%, tetapi belum mencapai target {to_float(rules.get('mid_roi_pct', 30.0)):.1f}%; jaga MAO dan walk-away price."
        )
    if market.get("valid_count", 0) >= go_min_comps and market.get("confidence", 0) < 70:
        warnings.append(f"Confidence pasar {market.get('confidence', 0)}/100 masih di bawah rekomendasi kualitas 70/100.")

    summary_by_status = {
        "GO": "Secara fundamental layak dieksekusi. Pastikan Bid Readiness berstatus READY sebelum memasukkan penawaran.",
        "CONDITIONAL GO": "Secara fundamental menarik dengan syarat terukur. Selesaikan mitigasi dan pastikan Bid Readiness READY sebelum bidding.",
        "HOLD": "Tunda keputusan. Ada informasi material, verifikasi, atau batas ekonomi yang belum memadai; pertahankan dalam watchlist.",
        "DO NOT BID": "Ada hard stop yang telah dikonfirmasi atau proyek tidak memiliki jalur ekonomi yang layak; hindari bidding.",
    }
    return {
        "status": investment_status,  # Backward-compatible alias used by reports and existing Sheets rows.
        "investment_status": investment_status,
        "bid_readiness": bid_readiness,
        "bid_readiness_ready": bid_readiness == "READY",
        "bid_readiness_issues": readiness_issues,
        "hold_reasons": list(dict.fromkeys(hold_reasons)),
        "hard_stops": hard_stops,
        "conditions": list(dict.fromkeys(conditions)),
        "blockers": list(dict.fromkeys(hold_reasons + hard_stops)),
        "warnings": list(dict.fromkeys(warnings)),
        "summary": summary_by_status[investment_status],
        "minimum_roi_pct": bid_min_roi,
        "conditional_minimum_roi_pct": min_conditional_roi,
        "go_minimum_roi_pct": go_roi,
        "target_roi_pct": to_float(rules.get("mid_roi_pct", 30.0)),
        "minimum_net_profit": min_profit,
        "target_holding_days": target_days,
        "maximum_holding_days": go_max_days,
        "conditional_maximum_holding_days": conditional_max_days,
        "projected_holding_days": duration_days,
        "duration_missing": duration_days <= 0,
        "mao_full_cost": mao_full_cost,
    }
