from __future__ import annotations
from typing import Any
from core.utils import idr, pct


def build_analysis_markdown(snapshot: dict[str, Any]) -> str:
    p = snapshot.get("property", {}); market = snapshot.get("market", {}); bid = snapshot.get("bidding", {}); limit = snapshot.get("at_limit", {}); decision = snapshot.get("decision", {})
    mid_display = idr(bid.get("mid_bid")) if bid.get("mid_bid") is not None else (
        f"Belum ada bid legal; ceiling di bawah limit {idr(bid.get('mid_economic_ceiling'))} (diagnostik saja; ROI pada ceiling {pct((bid.get('mid_result') or {}).get('roi_pct'))})"
        if bid.get("mid_economic_ceiling") is not None else
        f"Belum ada bid legal; ceiling simulasi {idr(bid.get('mid_simulated_ceiling'))} (increment resmi belum dikonfirmasi)"
        if bid.get("mid_simulated_ceiling") is not None else "Belum tersedia"
    )
    max_display = idr(bid.get("max_bid")) if bid.get("max_bid") is not None else (
        f"TIDAK ADA BID; ceiling di bawah limit {idr(bid.get('max_economic_ceiling'))} (diagnostik saja; ROI pada ceiling {pct((bid.get('max_result') or {}).get('roi_pct'))})"
        if bid.get("max_economic_ceiling") is not None else
        f"Belum ada bid legal; ceiling simulasi {idr(bid.get('max_simulated_ceiling'))} (increment resmi belum dikonfirmasi)"
        if bid.get("max_simulated_ceiling") is not None else "Belum tersedia"
    )
    walk_display = idr(bid.get("walk_away_from")) if bid.get("walk_away_from") is not None else bid.get("walk_away_reason", "Belum tersedia")
    lines = [f"# Investment Memo — {p.get('name') or p.get('lot_code') or 'Properti'}", "", f"Tanggal analisis: {snapshot.get('analyzed_at','')}", f"Property ID: {snapshot.get('property_id','')}", f"Keputusan: **{decision.get('status','HOLD')}**", "", "## Identitas Objek", f"- Kode lot: {p.get('lot_code','')}", f"- Alamat: {p.get('address','')}", f"- Limit: {idr(p.get('auction_limit'))}", f"- LT/LB: {p.get('land_area','—')} / {p.get('building_area','—')} m²", "", "## Market Valuation", f"- Comparable valid: {market.get('valid_count',0)}", f"- Confidence index: {market.get('confidence','—')}/100", f"- Conservative ARV: {idr(market.get('conservative_exit'))}", f"- Base ARV: {idr(market.get('base_exit'))}", f"- Optimistic ARV: {idr(market.get('optimistic_exit'))}", "", "## Financial at Auction Limit", f"- Total modal sebelum penjualan: {idr(limit.get('capital_before_sale'))}", f"- Selling cost: {idr(limit.get('selling_cost'))}", f"- Net profit: {idr(limit.get('net_profit'))}", f"- ROI proyek: {pct(limit.get('roi_pct'))}", f"- Holding: {limit.get('holding_months','—')} bulan", "", "## Bidding Tiers", f"- Limit / harga mulai: {idr(bid.get('min_bid'))}", f"- Bid legal tertinggi untuk target ROI 35%: {mid_display}", f"- Bid legal tertinggi untuk target ROI 25%: {max_display}", f"- Walk-away: {walk_display}", "", "## Blockers"]
    lines += [f"- {x}" for x in decision.get("blockers", [])] or ["- Tidak ada blocker utama."]
    lines += ["", "## Warnings"]
    lines += [f"- {x}" for x in decision.get("warnings", [])] or ["- Tidak ada peringatan tambahan."]
    lines += ["", "## Catatan", "Dokumen ini adalah alat bantu underwriting, bukan appraisal, pendapat hukum, atau jaminan hasil investasi. Semua sumber dan asumsi perlu diverifikasi oleh investor."]
    return "\n".join(lines)
