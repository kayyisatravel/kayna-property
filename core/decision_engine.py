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
        return f"ROI ALL-IN {to_float(roi):.1f}% DI BAWAH HURDLE {minimum_roi_pct:.1f}% — REVIEW HARGA BID / MAO"
    if to_float(profit) < minimum_net_profit:
        return f"PROFIT BERSIH {to_float(profit):,.0f} DI BAWAH TARGET REFERENSI Rp{minimum_net_profit:,.0f} — REVIEW MAO / PERTIMBANGKAN WALK-AWAY"
    if days <= 0:
        return "DURASI PROYEK BELUM TERSEDIA — MASUKKAN ASUMSI HOLDING / SKENARIO"
    if maximum_holding_days > 0 and days > maximum_holding_days:
        return f"DURASI {days:.0f} HARI MELEWATI HORIZON REFERENSI {maximum_holding_days:.0f} HARI — UJI SKENARIO BIAYA MODAL"
    if not cash_confirmed:
        return "POSISI KAS BELUM DIKONFIRMASI — PERBARUI POSISI KAS SEBELUM KEPUTUSAN BID"
    if cash_need is not None and cash_available is not None and cash_need > cash_available:
        return "PROYEKSI KAS BELUM MENUTUP KEBUTUHAN — TINJAU SUMBER DANA / SKALA BID"
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
    """Produce an advisory investment view and a separate execution-readiness view.

    Missing information is normally expressed as an assumption, uncertainty,
    scenario or follow-up item, not an automatic veto. Only explicitly confirmed
    non-mitigable risks become DO NOT BID. The Owner's decision is stored apart
    from this model-generated reference status.
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

    min_conditional_roi = max(0.0, to_float(rules.get("conditional_minimum_roi_pct", 15.0)))
    go_roi = max(min_conditional_roi, to_float(rules.get("go_minimum_roi_pct", 25.0)))
    bid_min_roi = max(0.0, to_float(rules.get("minimum_roi_pct", 15.0)))
    min_profit = max(0.0, to_float(rules.get("minimum_net_profit", 50_000_000.0)))
    target_days = max(0.0, to_float(rules.get("target_holding_days", 90.0)))
    go_max_days = max(1.0, to_float(rules.get("maximum_holding_days", 180.0)))
    conditional_max_days = max(go_max_days, to_float(rules.get("conditional_maximum_holding_days", 365.0)))
    conditional_market_confidence = max(0.0, to_float(rules.get("conditional_market_confidence_pct", 45.0)))
    go_market_confidence = max(conditional_market_confidence, to_float(rules.get("go_market_confidence_pct", 55.0)))
    conditional_min_comps = max(1, int(to_float(rules.get("conditional_min_comparables", 3))))
    go_min_comps = max(conditional_min_comps, int(to_float(rules.get("go_min_comparables", min_comps))))

    conditions: list[str] = []
    warnings: list[str] = []
    hard_stops: list[str] = []
    readiness_issues: list[dict[str, str]] = []

    def add_condition(message: str) -> None:
        if message and message not in conditions:
            conditions.append(message)

    def add_warning(message: str) -> None:
        if message and message not in warnings:
            warnings.append(message)

    def add_readiness(message: str, category: str) -> None:
        if message and not any(x["message"] == message for x in readiness_issues):
            readiness_issues.append({"category": category, "message": message})

    # 1) Explicit and confirmed hard stops only.
    if bool(legal.get("fatal_legal_issue_confirmed", False)):
        hard_stops.append("Cacat hukum/gugatan material telah dikonfirmasi sebagai risiko yang tidak dapat dimitigasi.")
    if bool(survey.get("fatal_security_threat_confirmed", False)):
        hard_stops.append("Ancaman keamanan atau perlawanan fisik yang tidak dapat diterima telah dikonfirmasi.")
    if bool(prop.get("fatal_access_or_environment_confirmed", False)):
        hard_stops.append("Akses legal atau kondisi lingkungan fatal telah dikonfirmasi.")
    for risk in list(risk_summary.get("items") or []):
        if bool(risk.get("hard_stop_confirmed", False)):
            desc = str(risk.get("risk_description") or "Risiko fatal terkonfirmasi").strip()
            hard_stops.append(f"Hard stop terkonfirmasi: {desc}.")

    # 2) Investment facts and uncertainty become advisory conditions.
    limit = to_float(prop.get("auction_limit"))
    if not prop.get("lot_code") or not prop.get("address") or limit <= 0:
        add_condition("Identitas lot, alamat, atau limit masih perlu dilengkapi sebelum analisis transaksi dapat dianggap final.")
    if to_float(prop.get("land_area")) <= 0:
        add_condition("Luas tanah belum diisi atau belum dicocokkan dengan dokumen objek.")
    if to_float(prop.get("building_area")) <= 0 and prop.get("property_type") != "Tanah kosong":
        add_condition("Luas bangunan belum tersedia; lakukan verifikasi saat survei atau dari dokumen pendukung.")

    survey_status = str(survey.get("survey_status") or survey.get("occupancy_status") or "").strip()
    if not survey_status or survey_status == "Belum Survei":
        add_condition("Survei lapangan belum dilakukan. Model tetap membuat skenario, tetapi asumsi penghuni, akses, dan kondisi fisik harus diperlakukan sebagai ketidakpastian tinggi.")
        add_readiness("Survei lapangan belum dilakukan atau belum dicatat.", "SURVEY")
    physical = str(survey.get("physical_condition") or "").strip()
    if not physical or _contains_any(physical, ("belum diketahui",)):
        add_condition("Kondisi fisik belum terverifikasi. Gunakan allowance risiko dan hindari menganggap komponen yang belum terlihat bernilai nol.")
        add_readiness("Kondisi fisik bangunan belum diketahui.", "SURVEY")

    structure_verified = bool(survey.get("structure_verified_safe", False))
    owner_structure_assessed = bool(survey.get("owner_assessed_structure_safe", False))
    if not structure_verified:
        if owner_structure_assessed:
            age = survey.get("building_age_years")
            age_text = f" (usia bangunan sekitar {to_float(age):g} tahun menurut Owner)" if age not in (None, "") else ""
            add_condition("Struktur belum diperiksa tenaga teknis; Owner menggunakan penilaian visual/usia bangunan" + age_text + ". Pertahankan cadangan hidden-condition dan lakukan pemeriksaan bila akses memungkinkan.")
        else:
            add_condition("Struktur utama belum diverifikasi secara teknis. Sistem memasukkannya sebagai ketidakpastian, bukan menyimpulkan bangunan rusak.")
        add_readiness("Pemeriksaan struktur belum dilakukan secara teknis.", "SURVEY")

    skpt_verified = bool(legal.get("skpt_verified", False))
    identity_verified = bool(legal.get("identity_verified", False)) or skpt_verified
    if skpt_verified:
        add_warning("Owner menyatakan SKPT/KPKNL telah diperiksa dan sesuai. Ini meningkatkan keyakinan administrasi, tetapi bukan jaminan bahwa tidak pernah/akan ada gugatan atau klaim di luar informasi yang tercatat.")
    elif not identity_verified:
        add_condition("Pencocokan identitas objek dan dokumen belum dikonfirmasi pengguna; status KPKNL/SKPT dapat dicatat sebagai dasar verifikasi.")
        add_readiness("Pencocokan identitas objek/SKPT belum dicatat.", "LEGAL")

    original_doc_status = str(legal.get("original_certificate_status") or "").strip()
    if original_doc_status != "Asli di bank/kreditur dan siap diserahkan":
        add_warning(
            "Status fisik dan mekanisme serah-terima sertifikat asli perlu dikonfirmasi kepada bank/kreditur. "
            "Ini tindak lanjut administrasi/pasca-lelang, bukan otomatis cacat hak atau alasan menahan analisis, "
            "terutama bila Owner telah memeriksa SKPT dan kecocokan objek pada pengumuman KPKNL."
        )
        # Original-certificate logistics are tracked as a post-award operational
        # follow-up. Pre-bid legal identity is checked separately through SKPT /
        # KPKNL document matching or the explicit identity-verification field.
    if legal.get("dispute_detected"):
        add_condition("Ada indikasi sengketa/ketidaksesuaian yang masih perlu ditelusuri. Tentukan apakah indikasi tersebut material sebelum keputusan eksekusi.")
        add_readiness("Indikasi sengketa/ketidaksesuaian belum ditutup dengan verifikasi.", "LEGAL")
    if not legal.get("tax_rules_verified"):
        add_warning("Tarif/dasar BPHTB dan biaya lelang masih memakai asumsi konfigurasi. Verifikasi pada pengumuman lelang dan Perda yang berlaku; selisih biaya perlu masuk sensitivitas biaya proyek.")
        add_readiness("Asumsi tarif pajak dan biaya transaksi belum diverifikasi; validasi dasar BPHTB/biaya lelang.", "TAX / COST")

    if not inputs.get("risk_reviewed", False):
        add_warning("Risk register belum ditinjau menyeluruh. AI akan menandai potensi blind spot dan Owner perlu memutuskan risiko mana yang diterima atau dimitigasi.")
        add_readiness("Risk register belum ditinjau.", "RISK")
    if not costs.get("cost_estimates_reviewed", False):
        add_warning("RAB dan biaya lain belum mendapat konfirmasi akhir Owner; angka biaya/profit masih dapat berubah.")
        add_readiness("Estimasi biaya/RAB belum dikonfirmasi.", "COST")

    renovation_items = costs.get("renovation_items", []) or []
    unpriced_in_scope = [
        str(r.get("work_item") or r.get("item_code") or "Pekerjaan dalam anggaran")
        for r in renovation_items
        if rab_item_is_in_scope(r)
        and (r.get("quantity") in (None, "") or to_float(r.get("quantity")) <= 0 or r.get("unit_cost") in (None, "") or to_float(r.get("unit_cost")) <= 0)
    ]
    scope_allowance = to_float(costs.get("unverified_scope_allowance"))
    if unpriced_in_scope:
        if scope_allowance > 0:
            add_condition(f"Ada {len(unpriced_in_scope)} item RAB yang belum dapat diukur/harga. Owner memasukkan allowance Rp{scope_allowance:,.0f}; bandingkan allowance dengan temuan lapangan ketika akses tersedia.")
        else:
            add_condition(f"Ada {len(unpriced_in_scope)} item RAB yang belum dapat diukur/harga. Angka profit belum memasukkan pekerjaan tak terukur; isi allowance atau tampilkan skenario biaya tambahan.")
        add_readiness("Sebagian lingkup renovasi belum diukur/di-quote.", "COST")

    for item in (risk_summary.get("invalid") or [])[:5]:
        add_condition("Data risk register perlu diperbaiki: " + str(item))
    for desc in (risk_summary.get("severe_unmitigated") or [])[:8]:
        add_condition("Risiko berdampak tinggi belum memiliki mitigasi terukur: " + str(desc))
        add_readiness("Mitigasi risiko berdampak tinggi belum ditinjau ulang.", "RISK")
    for desc in (risk_summary.get("critical_open") or [])[:8]:
        add_condition("Risiko kritis tercatat masih terbuka: " + str(desc) + ". Tinjau apakah dapat diberi harga, dimitigasi, dialihkan, atau harus ditolak.")
        add_readiness("Terdapat risiko kritis yang masih berstatus terbuka.", "RISK")

    # 3) Market evidence grades confidence; it does not erase an indicative view.
    valuation_count = int(to_float(market.get("arv_condition_comparable_count", market.get("valuation_comparable_count", market.get("valid_count", 0)))))
    go_grade_count = int(to_float(market.get("go_grade_count", 0)))
    confidence = to_float(market.get("arv_condition_confidence", market.get("confidence")))
    owner_arv = to_float(market.get("owner_arv_estimate"))
    if valuation_count <= 0 and owner_arv <= 0:
        add_condition("Belum ada pembanding exit se-kondisi maupun estimasi ARV manual Owner. Sistem belum dapat menghitung profit/MAO yang bermakna.")
        add_readiness("Dasar nilai exit/ARV belum tersedia.", "MARKET")
    elif valuation_count < conditional_min_comps or confidence < conditional_market_confidence:
        add_condition(f"Sampel pasar masih terbatas ({valuation_count} pembanding se-kondisi; confidence {confidence:.1f}/100). Nilai tetap ditampilkan sebagai indikasi dengan rentang ketidakpastian lebih lebar, bukan appraisal.")
        add_readiness("Bukti pasar se-kondisi masih terbatas; validasi listing/transaksi tambahan bila tersedia.", "MARKET")
    elif valuation_count < go_min_comps or go_grade_count < go_min_comps or confidence < go_market_confidence or market.get("status") != "READY":
        add_condition(f"Bukti pasar mendukung penilaian awal tetapi belum memenuhi standar audit GO ({go_grade_count} URL listing individual bertanggal; confidence {confidence:.1f}/100). Pertimbangkan cross-check tambahan.")
        add_readiness("Bukti pasar belum mencapai standar audit GO.", "MARKET")
    if 55 <= confidence < 70:
        add_warning(f"Indeks kualitas bukti pasar {confidence:.1f}/100 berada pada kategori cukup; ini indeks kelengkapan/kecocokan data, bukan probabilitas harga jual tercapai.")

    # 4) Financial attractiveness at current auction limit.
    roi = at_limit.get("roi_pct")
    profit = at_limit.get("net_profit")
    duration_days = to_float(at_limit.get("projected_holding_days"))
    no_bid_profit = no_bid_case.get("net_profit")
    if roi is None or profit is None:
        add_condition("Profit dan ROI belum dapat dihitung karena dasar nilai exit/ARV belum tersedia. Masukkan ARV asumsi Owner atau data pasar yang lebih relevan.")
        add_readiness("Analisis profit/ROI belum memiliki dasar nilai exit.", "ECONOMICS")
    else:
        roi_value = to_float(roi)
        profit_value = to_float(profit)
        robust_market = valuation_count >= 3 and confidence >= conditional_market_confidence
        if robust_market and no_bid_profit is not None and to_float(no_bid_profit) <= 0:
            hard_stops.append("Model ekonomi konservatif menunjukkan proyek tidak menghasilkan profit bahkan pada skenario akuisisi Rp0; validasi ulang input dan pertimbangkan tidak melanjutkan objek.")
        elif roi_value < 0 or profit_value < 0:
            if robust_market:
                add_condition(f"Pada limit saat ini, skenario konservatif menghasilkan profit negatif ({roi_value:.1f}% ROI). Harga limit perlu turun atau asumsi biaya/exit harus berubah berdasarkan bukti.")
                add_readiness("Ekonomi pada limit saat ini negatif; jangan menawar pada harga tersebut.", "ECONOMICS")
            else:
                add_condition(f"Skenario indikatif menunjukkan profit negatif ({roi_value:.1f}% ROI), tetapi bukti pasar belum cukup kuat untuk menyimpulkan aset tidak ekonomis. Uji ulang dengan data exit/ARV yang lebih baik.")
        elif roi_value < min_conditional_roi or profit_value < min_profit:
            add_condition(f"Return indikatif pada limit berada di bawah batas bersyarat (ROI {roi_value:.1f}% vs minimum {min_conditional_roi:.1f}%; profit Rp{profit_value:,.0f} vs minimum Rp{min_profit:,.0f}). Evaluasi harga limit, MAO, atau strategi exit.")
            add_readiness("Return pada limit belum memenuhi hurdle investasi yang ditetapkan Owner.", "ECONOMICS")
        elif roi_value < go_roi:
            add_condition(f"Project ROI {roi_value:.1f}% berada pada rentang CONDITIONAL GO ({min_conditional_roi:.1f}%–<{go_roi:.1f}%). MAO dan walk-away price harus dipatuhi.")

    if duration_days <= 0:
        add_condition("Durasi proyek belum tersedia atau belum terisi; bandingkan skenario 3, 6, dan 12 bulan.")
        add_readiness("Durasi proyek belum ditentukan.", "TIME")
    elif duration_days > conditional_max_days:
        add_condition(f"Estimasi holding period {duration_days:.0f} hari melampaui asumsi maksimum {conditional_max_days:.0f} hari; skenario ini membutuhkan kajian ulang biaya modal/exit.")
        add_readiness("Holding period melampaui horizon kebijakan.", "TIME")
    elif duration_days > go_max_days:
        add_condition(f"Estimasi holding period {duration_days:.0f} hari melewati target GO {go_max_days:.0f} hari; pertahankan buffer biaya modal.")
    elif duration_days > target_days:
        add_warning(f"Durasi proyek {duration_days:.0f} hari di atas target ideal {target_days:.0f} hari; uji sensitivitas biaya modal.")
    if roi is not None and to_float(roi) < to_float(rules.get("mid_roi_pct", 30.0)):
        add_warning(f"ROI belum mencapai target {to_float(rules.get('mid_roi_pct', 30.0)):.1f}%.")

    # 5) Execution considerations.
    status_norm = survey_status.lower()
    is_vacant = "kosong" in status_norm or "tidak dihuni" in status_norm
    is_occupied = "dihuni" in status_norm and not is_vacant
    if is_occupied:
        poss_cost = to_float(survey.get("possession_cost"))
        poss_reserve = to_float(survey.get("possession_risk_reserve"))
        plan = bool(survey.get("possession_plan_confirmed"))
        if "menolak keluar" in status_norm or "butuh eksekusi" in status_norm:
            add_condition("Objek masih berpenghuni dan kemungkinan memerlukan proses pengosongan formal. Simulasikan biaya/waktu hukum dan jangan menganggap negosiasi pasti berhasil.")
            add_readiness("Strategi penguasaan dan skenario alternatif belum dikonfirmasi.", "POSSESSION")
        elif poss_cost > 0 or poss_reserve > 0:
            add_condition("Objek masih berpenghuni. Estimasi cash-for-keys/pengosongan telah masuk model; pastikan rencana, waktu, dan skenario gagal negosiasi diperhitungkan.")
            if not plan:
                add_readiness("Rencana cash-for-keys/pengosongan belum didokumentasikan.", "POSSESSION")
        else:
            add_condition("Objek masih berpenghuni tetapi biaya pengosongan belum dianggarkan.")
            add_readiness("Biaya pengosongan belum dianggarkan.", "POSSESSION")

    physical_norm = physical.lower()
    if "renovasi sedang" in physical_norm or "renovasi berat" in physical_norm:
        renovation_label = "renovasi berat" if "berat" in physical_norm else "renovasi sedang"
        add_condition(f"Objek membutuhkan {renovation_label}; nilai, mutu pekerjaan, durasi, dan risiko rework perlu diawasi walaupun RAB telah disusun.")
        contingency_pct = to_float(costs.get("renovation_contingency_pct", rules.get("renovation_contingency_pct", 15)))
        required_pct = to_float(rules.get("heavy_renovation_contingency_min_pct", 20)) if "berat" in physical_norm else to_float(rules.get("renovation_contingency_min_pct", 15))
        if contingency_pct < required_pct:
            add_condition(f"Contingency renovasi {contingency_pct:.1f}% berada di bawah panduan internal {required_pct:.1f}%; Owner dapat menaikkan allowance sesuai ketidakpastian scope.")
        if not bool(survey.get("interior_inspected")):
            reserve_amount = to_float(costs.get("hidden_condition_reserve_amount"))
            reserve_pct = to_float(costs.get("hidden_condition_reserve_pct", rules.get("hidden_condition_reserve_pct", 7.5)))
            reserve_label = f"cadangan eksplisit {reserve_amount:,.0f}" if reserve_amount > 0 else f"cadangan {reserve_pct:.1f}% dari allowance renovasi"
            add_condition(f"Interior belum diinspeksi; ketidakpastian fisik dimodelkan melalui {reserve_label}. Buffer ini bukan bukti bahwa kerusakan pasti ada.")
            add_readiness("Interior belum diinspeksi; keputusan Owner perlu mempertimbangkan cadangan dan batas inspeksi.", "SURVEY")
    elif survey.get("interior_inspected") is False and prop.get("property_type") != "Tanah kosong":
        reserve_amount = to_float(costs.get("hidden_condition_reserve_amount"))
        reserve_pct = to_float(costs.get("hidden_condition_reserve_pct", rules.get("hidden_condition_reserve_pct", 7.5)))
        reserve_label = f"cadangan eksplisit {reserve_amount:,.0f}" if reserve_amount > 0 else f"cadangan {reserve_pct:.1f}% dari allowance renovasi"
        add_condition(f"Interior belum diinspeksi; ketidakpastian fisik dimodelkan melalui {reserve_label}.")
        add_readiness("Interior belum diinspeksi; keputusan Owner perlu mempertimbangkan cadangan dan batas inspeksi.", "SURVEY")

    # 6) Bid readiness: cash now vs confirmed cash by auction date.
    cash_need = to_float(at_limit.get("cash_requirement_including_reserve", at_limit.get("capital_before_sale")))
    cash_now = to_float(finance.get("cash_available_for_new_project", finance.get("cash_available")))
    cash_by_auction = to_float(finance.get("cash_available_for_new_project_at_auction", cash_now))
    cash_confirmed = bool(finance.get("cash_confirmed"))
    expected_cash_pending = max(0.0, cash_by_auction - cash_now) if bool(finance.get("expected_cash_is_provisional")) else 0.0
    if not cash_confirmed:
        add_readiness("Posisi kas saat ini belum dikonfirmasi.", "CASH")
    if cash_need > cash_by_auction:
        add_readiness(f"Kas yang tersedia/proyeksi pada tanggal lelang masih kurang Rp{cash_need - cash_by_auction:,.0f}; kebutuhan Rp{cash_need:,.0f}, kas saat lelang Rp{cash_by_auction:,.0f}.", "CASH")
    elif expected_cash_pending > 0:
        add_readiness(f"Dana tambahan Rp{expected_cash_pending:,.0f} merupakan komitmen yang belum cleared. Dana ini membantu proyeksi kas saat lelang, tetapi harus benar-benar masuk/tersedia sebelum penawaran.", "CASH CONFIRMATION")
    if bool(finance.get("expected_cash_after_auction")):
        add_readiness("Dana tambahan dijadwalkan setelah tanggal lelang sehingga tidak dihitung sebagai sumber kas untuk bidding ini.", "CASH TIMING")

    if roi is not None and to_float(roi) < bid_min_roi:
        add_readiness(f"ROI indikatif {to_float(roi):.1f}% di bawah hurdle bid {bid_min_roi:.1f}% pada limit saat ini.", "ECONOMICS")
    if profit is not None and to_float(profit) < min_profit:
        add_readiness(f"Profit indikatif Rp{to_float(profit):,.0f} di bawah batas referensi Rp{min_profit:,.0f}.", "ECONOMICS")

    max_economic_ceiling = tiers.get("max_economic_ceiling")
    if max_economic_ceiling is not None and limit > 0 and to_float(max_economic_ceiling) < limit:
        add_readiness(f"Limit Rp{limit:,.0f} lebih tinggi daripada MAO Full Cost indikatif Rp{to_float(max_economic_ceiling):,.0f}; gunakan walk-away price.", "ECONOMICS")
    if not tiers.get("increment_confirmed"):
        add_readiness("Kelipatan bid resmi belum dicatat dari pengumuman lelang.", "AUCTION DATA")

    # A non-zero exit based on a small sample can support indicative analysis,
    # but it must not be silently promoted to a final bidding instruction.
    if market.get("valuation_is_provisional", False):
        add_readiness("Valuasi exit masih provisional/owner assumption; cross-check nilai sebelum mengirim penawaran.", "MARKET")

    hard_stops = list(dict.fromkeys(hard_stops))
    conditions = list(dict.fromkeys(conditions))
    warnings = list(dict.fromkeys(warnings))
    if hard_stops:
        investment_status = "DO NOT BID"
    elif roi is None or profit is None:
        investment_status = "HOLD"
    else:
        roi_value = to_float(roi)
        profit_value = to_float(profit)
        if roi_value < min_conditional_roi or profit_value < min_profit:
            investment_status = "HOLD"
        elif duration_days > conditional_max_days:
            investment_status = "HOLD"
        elif roi_value < go_roi or duration_days > go_max_days or conditions:
            investment_status = "CONDITIONAL GO"
        else:
            investment_status = "GO"

    categories = list(dict.fromkeys(x["category"] for x in readiness_issues))
    if hard_stops:
        bid_readiness = "NOT READY — HARD STOP"
    elif readiness_issues:
        bid_readiness = f"NOT READY — {categories[0]}" if len(categories) == 1 else "NOT READY — MULTIPLE ITEMS"
    else:
        bid_readiness = "READY"

    summaries = {
        "GO": "Skenario dasar menunjukkan daya tarik investasi tinggi pada asumsi yang tersedia. Ini referensi analitis, bukan persetujuan otomatis, jaminan hasil, atau pengganti keputusan Owner.",
        "CONDITIONAL GO": "Fundamental ekonomi tampak menarik, tetapi terdapat friksi/ketidakpastian yang perlu diberi harga, strategi, atau toleransi risiko. Owner dapat lanjut, menegosiasikan batas bid, menunda, atau skip.",
        "HOLD": "Dengan asumsi yang saat ini dapat dipertanggungjawabkan, dasar exit belum memadai atau return belum memenuhi hurdle Owner. Pertahankan sebagai opsi/watchlist dan uji perubahan harga, biaya, atau informasi.",
        "DO NOT BID": "Terdapat hard stop yang telah dikonfirmasi atau bukti ekonomi kuat bahwa objek tidak layak secara struktural. Ini peringatan kuat bagi Owner; setiap override perlu alasan dan pemeriksaan independen.",
    }
    return {
        "status": investment_status,
        "investment_status": investment_status,
        "bid_readiness": bid_readiness,
        "bid_readiness_ready": bid_readiness == "READY",
        "bid_readiness_issues": readiness_issues,
        "hold_reasons": (conditions if investment_status == "HOLD" else []),
        "hard_stops": hard_stops,
        "conditions": conditions,
        "blockers": hard_stops,
        "warnings": warnings,
        "summary": summaries[investment_status],
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
        "mao_full_cost": tiers.get("max_bid"),
        "owner_is_final_decision_maker": True,
        "market_sample_count": valuation_count,
        "market_confidence": confidence,
    }
