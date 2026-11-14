from __future__ import annotations
from typing import Any
from core.utils import idr, pct


def build_analysis_markdown(snapshot: dict[str, Any]) -> str:
    p = snapshot.get("property", {}); market = snapshot.get("market", {}); bid = snapshot.get("bidding", {}); limit = snapshot.get("at_limit", {}); decision = snapshot.get("decision", {})
    lines = [f"# Investment Memo — {p.get('name') or p.get('lot_code') or 'Properti'}", "", f"Tanggal analisis: {snapshot.get('analyzed_at','')}", f"Property ID: {snapshot.get('property_id','')}", f"Keputusan: **{decision.get('status','HOLD')}**", "", "## Identitas Objek", f"- Kode lot: {p.get('lot_code','')}", f"- Alamat: {p.get('address','')}", f"- Limit: {idr(p.get('auction_limit'))}", f"- LT/LB: {p.get('land_area','—')} / {p.get('building_area','—')} m²", "", "## Market Valuation", f"- Comparable valid: {market.get('valid_count',0)}", f"- Confidence index: {market.get('confidence','—')}/100", f"- Conservative ARV: {idr(market.get('conservative_exit'))}", f"- Base ARV: {idr(market.get('base_exit'))}", f"- Optimistic ARV: {idr(market.get('optimistic_exit'))}", "", "## Financial at Auction Limit", f"- Total modal sebelum penjualan: {idr(limit.get('capital_before_sale'))}", f"- Selling cost: {idr(limit.get('selling_cost'))}", f"- Net profit: {idr(limit.get('net_profit'))}", f"- ROI proyek: {pct(limit.get('roi_pct'))}", f"- Holding: {limit.get('holding_months','—')} bulan", "", "## Bidding Tiers", f"- Limit: {idr(bid.get('min_bid'))}", f"- Target ROI 35%: {idr(bid.get('mid_bid'))}", f"- Maximum bid ROI 25%: {idr(bid.get('max_bid'))}", f"- Walk-away mulai: {idr(bid.get('walk_away_from'))}", "", "## Blockers"]
    lines += [f"- {x}" for x in decision.get("blockers", [])] or ["- Tidak ada blocker utama."]
    lines += ["", "## Warnings"]
    lines += [f"- {x}" for x in decision.get("warnings", [])] or ["- Tidak ada peringatan tambahan."]
    lines += ["", "## Catatan", "Dokumen ini adalah alat bantu underwriting, bukan appraisal, pendapat hukum, atau jaminan hasil investasi. Semua sumber dan asumsi perlu diverifikasi oleh investor."]
    return "\n".join(lines)
