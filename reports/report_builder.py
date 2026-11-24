from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from core.utils import idr, pct, to_float
from core.renovation_engine import rab_item_is_in_scope, rab_row_subtotals, summarize_rab_scope_totals
from core.renovation_pricing import PRICE_CATALOG_VERSION, PRICE_CATALOG_REFERENCES, PRICE_CATALOG_BASIS


def safe_filename(value: Any, fallback: str = "properti") -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:70] or fallback)


def investment_memo_filename(snapshot: dict[str, Any], extension: str = "docx") -> str:
    prop = snapshot.get("property", {})
    label = prop.get("name") or prop.get("complex_name") or prop.get("lot_code") or "properti"
    lot = prop.get("lot_code") or snapshot.get("property_id") or "property"
    return f"investment-memo-{safe_filename(label)}-{safe_filename(lot)}.{extension.lstrip('.')}"


def _money(value: Any) -> str:
    return idr(value) if value not in (None, "") else "Belum tersedia"


def _list_lines(values: list[Any] | None, empty: str = "Tidak ada catatan.") -> list[str]:
    clean = [str(x).strip() for x in (values or []) if str(x or "").strip()]
    return [f"- {x}" for x in clean] if clean else [f"- {empty}"]


def _rab_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    costs = snapshot.get("costs", {}) or {}
    return [dict(x) for x in costs.get("renovation_items", []) or [] if isinstance(x, dict) and str(x.get("work_item") or "").strip()]


def _scenario_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    from core.calculator import calculate_project
    prop = snapshot.get("property", {}) or {}
    limit = to_float(prop.get("auction_limit"))
    market = snapshot.get("market", {}) or {}
    inputs = snapshot.get("calculation_inputs", {}) or {}
    if limit <= 0 or not inputs:
        return []
    output = []
    for label, key in (("Konservatif", "conservative_exit"), ("Dasar", "base_exit"), ("Optimistis", "optimistic_exit")):
        sale = market.get(key)
        if sale in (None, ""):
            continue
        calc = calculate_project(limit, to_float(sale), inputs)
        output.append({"Skenario": label, "Harga jual indikatif": to_float(sale), "Modal sebelum penjualan": calc.get("capital_before_sale"), "Biaya penjualan": calc.get("selling_cost"), "Laba bersih indikatif": calc.get("net_profit"), "ROI": calc.get("roi_pct")})
    return output


def build_analysis_markdown(snapshot: dict[str, Any]) -> str:
    p = snapshot.get("property", {}) or {}
    survey = snapshot.get("survey", {}) or {}
    legal = snapshot.get("legal", {}) or {}
    costs = snapshot.get("costs", {}) or {}
    market = snapshot.get("market", {}) or {}
    bid = snapshot.get("bidding", {}) or {}
    limit = snapshot.get("at_limit", {}) or {}
    document_extraction = snapshot.get("document_extraction", {}) or {}
    field_evidence = document_extraction.get("field_evidence", {}) or {}
    decision = snapshot.get("decision", {}) or {}
    rab_rows = _rab_rows(snapshot)
    scenarios = _scenario_rows(snapshot)
    date_label = str(snapshot.get("analyzed_at") or "")
    lines = [
        f"# Investment Memorandum — {p.get('name') or p.get('lot_code') or 'Properti'}", "",
        "**Dokumen screening investasi properti lelang | Rahasia untuk pembahasan investor**", "",
        f"Tanggal analisis: {date_label}", f"Property ID: {snapshot.get('property_id', '')}",
        f"Status keputusan: **{decision.get('status', 'HOLD')}**", "",
        "## 1. Ringkasan Eksekutif", 
        f"Objek: {p.get('name') or p.get('lot_code') or 'Belum diberi nama'} — {p.get('address') or 'Alamat belum tersedia'}.",
        f"Limit lelang: **{_money(p.get('auction_limit'))}**. Indikasi ARV dasar: **{_money(market.get('base_exit'))}**; rentang konservatif–optimistis: {_money(market.get('conservative_exit'))} – {_money(market.get('optimistic_exit'))}.",
        f"Modal proyek sebelum penjualan pada harga limit: **{_money(limit.get('capital_before_sale'))}**. Laba bersih indikatif pada ARV konservatif: **{_money(limit.get('net_profit'))}**; ROI: **{pct(limit.get('roi_pct'))}**.",
        "Angka merupakan estimasi underwriting yang bergantung pada asumsi, bukan appraisal resmi, harga transaksi terverifikasi, atau penawaran kontraktor.", "",
        "## 2. Identitas dan Informasi Lelang",
        f"- Nama/kompleks: {p.get('name') or '—'} / {p.get('complex_name') or '—'}",
        f"- Kode lot: {p.get('lot_code') or '—'} | KPKNL: {p.get('auction_office') or '—'} | Penjual: {p.get('seller') or '—'}",
        f"- Alamat: {p.get('address') or '—'} | Kecamatan/desa: {p.get('district') or '—'}",
        f"- Jenis lelang: {p.get('auction_type') or '—'} | Tanggal/jam lelang: {p.get('auction_date') or '—'} {p.get('auction_time') or ''}",
        f"- Batas setor jaminan: {p.get('deposit_deadline') or '—'} | Batas pelunasan: {p.get('payment_deadline') or '—'}",
        f"- Evidence tanggal lelang: {field_evidence.get('auction_date') or 'Tidak tersedia'}",
        f"- Evidence batas setor jaminan: {field_evidence.get('deposit_deadline') or 'Tidak tersedia'}",
        f"- Sumber ekstraksi tanggal: {document_extraction.get('source_file_name') or 'Dokumen belum tercatat'} | Skema: {document_extraction.get('extraction_schema_version') or '—'}",
        f"- Uang jaminan: {_money(p.get('deposit_amount'))} | Limit: {_money(p.get('auction_limit'))} | Increment: {_money(p.get('bid_increment'))}",
        f"- LT/LB: {p.get('land_area') or '—'} / {p.get('building_area') or '—'} m² | Hak: {p.get('certificate_type') or '—'} {p.get('certificate_no') or ''}",
        f"- Link pengumuman: {p.get('auction_url') or '—'}", "",
        "## 3. Kondisi Fisik, Survei, dan Legalitas",
        f"- Status survei: {survey.get('survey_status') or '—'} | Status hunian: {survey.get('occupancy_status') or '—'} | Tanggal survei: {survey.get('survey_date') or '—'}",
        f"- Kondisi fisik: {survey.get('physical_condition') or '—'} | Akses: {survey.get('access') or '—'} | Lebar jalan: {survey.get('road_width_m') or '—'} m",
        f"- Interior diperiksa: {survey.get('interior_inspected')}",
        f"- Identitas/legalitas diverifikasi: {legal.get('identity_verified')} | Sengketa terdeteksi: {legal.get('dispute_detected')} | Pajak diverifikasi: {legal.get('tax_rules_verified')}",
        "Catatan survei:", *_list_lines([survey.get("survey_notes"), survey.get("facade_description")]), "",
        "## 4. Analisis Pasar dan ARV",
        f"- Listing yang dihitung: {market.get('valid_count', 0)} | Pembanding GO-grade: {market.get('go_grade_count', 0)} | Indeks kualitas data: {market.get('confidence', '—')}/100 ({market.get('confidence_band', '—')})",
        f"- ARV konservatif: {_money(market.get('conservative_exit'))} | Dasar: {_money(market.get('base_exit'))} | Optimistis: {_money(market.get('optimistic_exit'))}",
        f"- Median sederhana: {_money(market.get('simple_median'))} | Median tertimbang pembanding: {_money(market.get('median_adjusted'))}",
        f"- Haircut konservatif: {market.get('conservative_discount_used_pct', '—')}% | Diskon cepat jual: {market.get('quick_sale_discount_pct', '—')}% | Dispersi: {market.get('dispersion_pct', '—')}%", "",
        "### Daftar pembanding yang masuk perhitungan",
        "| Listing | Asking | LT/LB | Nilai normalisasi | Jarak | Skor | Sumber |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in market.get("valid", []) or []:
        lines.append(f"| {row.get('name') or '—'} | {_money(row.get('price'))} | {row.get('land_area') or '—'}/{row.get('building_area') or '—'} | {_money(row.get('subject_normalized_value'))} | {row.get('distance_km') if row.get('distance_km') is not None else '—'} km | {row.get('similarity_score', '—')} | {row.get('source_url') or row.get('source_platforms') or '—'} |")
    if not (market.get("valid") or []): lines.append("| Belum ada pembanding yang dapat dihitung | — | — | — | — | — | — |")
    lines += ["", "### Keterbatasan pembanding", *_list_lines(market.get("quality_notes"), "Tidak ada catatan kualitas data."), ""]

    lines += ["## 5. Rencana Renovasi dan RAB"]
    lines += [f"- Kategori: {costs.get('renovation_category') or '—'} | Biaya RAB + tambahan: {_money(costs.get('renovation_cost'))}", f"- Durasi renovasi: {costs.get('renovation_months', '—')} bulan | Kontingensi: {snapshot.get('rules', {}).get('renovation_contingency_pct', '—')}% | Hidden-condition reserve: {snapshot.get('rules', {}).get('hidden_condition_reserve_pct', '—')}%", f"- Versi pricebook: {PRICE_CATALOG_VERSION}", f"- Dasar pricebook: {PRICE_CATALOG_BASIS}", f"- Referensi SSH Sidoarjo 2026: {PRICE_CATALOG_REFERENCES['ssh_sidoarjo_2026']}", f"- Referensi ASB/HSPK Sidoarjo: {PRICE_CATALOG_REFERENCES['hspk_sidoarjo_2026']}", f"- Referensi metode AHSP PUPR: {PRICE_CATALOG_REFERENCES['ahsp_pupr_2023']}", "", "| Kelompok | Scope pekerjaan | Volume | Harga satuan dasar | Subtotal dasar | Keyakinan |", "|---|---|---:|---:|---:|---|"]
    for row in rab_rows:
        if not rab_item_is_in_scope(row):
            continue
        sub = rab_row_subtotals(row).get("subtotal_base")
        lines.append(f"| {row.get('subcategory') or '—'} | {row.get('work_item') or '—'} | {row.get('quantity') or '—'} {row.get('unit') or ''} | {_money(row.get('unit_cost'))} | {_money(sub)} | {row.get('confidence') or '—'} |")
    lines += ["", "### Subtotal per kelompok pekerjaan", "| Kelompok | Item | Subtotal rendah | Dasar | Atas |", "|---|---:|---:|---:|---:|"]
    for group in summarize_rab_scope_totals(rab_rows):
        lines.append(f"| {group['Kelompok pekerjaan']} | {group['Jumlah item']} | {_money(group['Subtotal rendah (Rp)'])} | {_money(group['Subtotal dasar (Rp)'])} | {_money(group['Subtotal atas (Rp)'])} |")
    lines += ["", "Pekerjaan yang belum masuk anggaran/masih belum lengkap:", *_list_lines((snapshot.get("bidding", {}) or {}).get("in_scope_rab_unpriced", []), "Tidak ada item RAB wajib yang belum terisi."), ""]

    lines += ["## 6. Proyeksi Modal dan Hasil Investasi", "| Komponen | Nilai |", "|---|---:|"]
    for label, key in [("Harga lelang/akuisisi", "bid_price"), ("Bea lelang pembeli", "buyer_auction_fee"), ("BPHTB", "bphtb"), ("BPN/legalitas", "legal_bpn_cost"), ("Penguasaan/kerohiman", "possession_cost"), ("Renovasi", "renovation_cost"), ("Contingency renovasi", "renovation_contingency"), ("Cadangan kondisi tersembunyi", "hidden_condition_reserve"), ("Holding", "holding_cost"), ("Marketing dan biaya lain", "other_presale_cost"), ("Total modal sebelum penjualan", "capital_before_sale"), ("Cadangan risiko tambahan", "cash_requirement_including_reserve")]:
        lines.append(f"| {label} | {_money(limit.get(key))} |")
    lines += ["", "### Skenario harga jual", "| Skenario | Harga jual | Modal sebelum jual | Biaya jual | Laba bersih | ROI |", "|---|---:|---:|---:|---:|---:|"]
    for row in scenarios:
        lines.append(f"| {row['Skenario']} | {_money(row['Harga jual indikatif'])} | {_money(row['Modal sebelum penjualan'])} | {_money(row['Biaya penjualan'])} | {_money(row['Laba bersih indikatif'])} | {pct(row['ROI'])} |")
    lines += ["", "## 7. Strategi Penawaran Lelang", f"- Harga limit: {_money(bid.get('min_bid'))}", f"- Bid indikatif untuk target ROI tengah: {_money(bid.get('mid_bid') or bid.get('mid_economic_ceiling'))}", f"- Bid indikatif maksimum untuk target ROI minimum: {_money(bid.get('max_bid') or bid.get('max_economic_ceiling'))}", f"- Walk-away: {_money(bid.get('walk_away_from')) if bid.get('walk_away_from') is not None else bid.get('walk_away_reason', '—')}", f"- Status provisional: {bid.get('provisional')}", *_list_lines(bid.get('provisional_reasons'), "Tidak ada alasan provisional."), ""]
    lines += ["## 8. Risk Register dan Mitigasi", "| Risiko | Probabilitas | Dampak | Cadangan | Mitigasi |", "|---|---:|---:|---:|---|"]
    for row in snapshot.get("risk_register", []) or []:
        lines.append(f"| {row.get('risk_description') or '—'} | {row.get('probability_1_5') or '—'}/5 | {row.get('impact_1_5') or '—'}/5 | {_money(row.get('cost_reserve'))} | {row.get('mitigation') or '—'} |")
    if not (snapshot.get("risk_register") or []): lines.append("| Belum ada risiko yang dicatat | — | — | — | — |")
    lines += ["", "## 9. Kebutuhan Modal dan Kesiapan Pendanaan", f"- Kas tersedia untuk proyek: {_money((snapshot.get('liquidity') or {}).get('cash_available_for_new_project'))}", f"- Kebutuhan kas termasuk cadangan: {_money((snapshot.get('funding') or {}).get('project_cash_need'))}", f"- Status pendanaan: {('Fully funded' if (snapshot.get('funding') or {}).get('full_project_funded') else 'Funding gap / not confirmed')}", "Uang jaminan merupakan kebutuhan kas di muka dan bagian dari pelunasan harga menang, bukan biaya tambahan yang boleh dihitung dua kali.", ""]
    lines += ["## 10. Syarat dan Checklist Sebelum Bidding", *_list_lines(decision.get("blockers"), "Tidak ada blocker tercatat; tetap periksa checklist due diligence."), "", "### Pemeriksaan wajib", "- Cocokkan objek fisik, alamat, sertifikat, luas, dan nomor hak.", "- Konfirmasi status penghuni dan biaya penguasaan; jangan mengandalkan foto.", "- Periksa batas setor jaminan, increment bid, batas pelunasan, dan ketentuan lelang resmi.", "- Verifikasi sekurang-kurangnya dua quotation renovasi dan harga jual pembanding.", "- Pastikan kas tersedia untuk akuisisi, renovasi, holding, pemasaran, dan cadangan risiko.", ""]
    lines += ["## 11. Asumsi dan Batasan", *_list_lines(decision.get("warnings"), "Tidak ada warning tambahan."), "", "Estimasi RAB menggunakan pricebook screening PFMS berversi jika tersedia; item yang tidak tercakup perlu harga manual/quotation. Estimasi ARV berasal dari pembanding yang dinormalisasi dan tidak sama dengan transaksi aktual. Hasil dapat berubah apabila data objek, harga penawaran, akses, atau kondisi tersembunyi berubah.", "", "**Pernyataan:** Dokumen ini adalah memorandum screening untuk diskusi investor. Bukan appraisal resmi, pendapat hukum, janji keuntungan, atau pengganti pemeriksaan lapangan dan quotation profesional."]
    return "\n".join(lines)


def build_investment_memo_docx(snapshot: dict[str, Any]) -> bytes:
    """Create a polished investor-facing DOCX without external AI calls."""
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p = snapshot.get("property", {}) or {}
    market = snapshot.get("market", {}) or {}
    decision = snapshot.get("decision", {}) or {}
    costs = snapshot.get("costs", {}) or {}
    bid = snapshot.get("bidding", {}) or {}
    limit = snapshot.get("at_limit", {}) or {}
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(0.62); sec.bottom_margin = Inches(0.62)
    sec.left_margin = Inches(0.68); sec.right_margin = Inches(0.68)

    styles = doc.styles
    styles["Normal"].font.name = "Aptos"; styles["Normal"].font.size = Pt(9)
    styles["Normal"].font.color.rgb = RGBColor(43, 55, 72)
    for style_name, size, color in (("Title", 24, "17324D"), ("Heading 1", 15, "0F766E"), ("Heading 2", 11, "17324D")):
        st = styles[style_name]; st.font.name = "Aptos Display"; st.font.size = Pt(size); st.font.bold = True; st.font.color.rgb = RGBColor.from_string(color)

    header = sec.header.paragraphs[0]
    header.text = "PROPERTY FLIPPER MANAGEMENT SYSTEM  |  INVESTMENT UNDERWRITING"
    header.style = styles["Caption"]
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.text = f"Confidential • PFMS {__import__('config').APP_VERSION} • {snapshot.get('property_id', '')}"
    footer.style = styles["Caption"]

    def shade(cell, fill: str) -> None:
        tc_pr = cell._tc.get_or_add_tcPr(); shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), fill); tc_pr.append(shd)

    def set_repeat_table_header(row) -> None:
        tr_pr = row._tr.get_or_add_trPr(); tbl_header = OxmlElement("w:tblHeader"); tbl_header.set(qn("w:val"), "true"); tr_pr.append(tbl_header)

    def table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None):
        t = doc.add_table(rows=1, cols=len(headers)); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.style = "Light Shading Accent 1"
        set_repeat_table_header(t.rows[0])
        for i, head in enumerate(headers):
            c = t.rows[0].cells[i]; c.text = str(head); shade(c, "17324D")
            for run in c.paragraphs[0].runs:
                run.font.bold = True; run.font.color.rgb = RGBColor(255,255,255); run.font.size = Pt(8)
        for row in rows:
            cells = t.add_row().cells
            for i, value in enumerate(row):
                cells[i].text = str(value if value not in (None, "") else "—")
                cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                for para in cells[i].paragraphs:
                    for run in para.runs: run.font.size = Pt(7.5)
        if widths:
            for r in t.rows:
                for i, w in enumerate(widths):
                    r.cells[i].width = Inches(w)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def bullet(text: Any):
        if str(text or "").strip(): doc.add_paragraph(str(text), style="List Bullet")

    # Cover / executive summary
    kicker = doc.add_paragraph(); kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = kicker.add_run("INVESTMENT MEMORANDUM"); r.bold = True; r.font.size = Pt(11); r.font.color.rgb = RGBColor(15,118,110)
    title = doc.add_paragraph(style="Title"); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run(str(p.get("name") or p.get("lot_code") or "Properti Lelang"))
    sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(str(p.get("address") or "Alamat belum tersedia")).italic = True
    meta = doc.add_paragraph(); meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(f"Property ID: {snapshot.get('property_id','—')}  •  Lot: {p.get('lot_code') or '—'}  •  Tanggal analisis: {snapshot.get('analyzed_at','—')}")
    status = doc.add_paragraph(); status.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = status.add_run(f"REKOMENDASI: {decision.get('status','HOLD')}"); rr.bold = True; rr.font.size = Pt(12); rr.font.color.rgb = RGBColor(15,118,110) if decision.get("status") == "GO" else RGBColor(166,91,19)
    doc.add_heading("1. Ringkasan Eksekutif", level=1)
    doc.add_paragraph(f"Objek ditawarkan melalui lelang dengan nilai limit {_money(p.get('auction_limit'))}. Estimasi ARV dasar {_money(market.get('base_exit'))}, sedangkan rentang konservatif–optimistis {_money(market.get('conservative_exit'))} sampai {_money(market.get('optimistic_exit'))}.")
    table(["Indikator", "Hasil"], [
        ["Keputusan underwriting", decision.get("status", "HOLD")],
        ["ARV konservatif / dasar / optimistis", f"{_money(market.get('conservative_exit'))} / {_money(market.get('base_exit'))} / {_money(market.get('optimistic_exit'))}"],
        ["Modal sebelum penjualan @ limit", _money(limit.get("capital_before_sale"))],
        ["Profit indikatif @ ARV konservatif", _money(limit.get("net_profit"))],
        ["ROI @ ARV konservatif", pct(limit.get("roi_pct"))],
        ["Indeks kualitas data pasar", f"{market.get('confidence','—')}/100"],
    ], [2.7, 4.1])
    doc.add_paragraph("Dokumen ini membantu investor memahami peluang, kebutuhan modal, batas penawaran, risiko, dan asumsi. Angka adalah estimasi screening, bukan appraisal atau quotation.")

    doc.add_heading("2. Identitas dan Jadwal Lelang", level=1)
    table(["Data", "Keterangan", "Data", "Keterangan"], [
        ["Nama / Kompleks", p.get("name"), "Kode lot", p.get("lot_code")],
        ["Alamat", p.get("address"), "KPKNL", p.get("auction_office")],
        ["Jenis lelang", p.get("auction_type"), "Penjual", p.get("seller")],
        ["Tanggal lelang", p.get("auction_date"), "Batas setor jaminan", p.get("deposit_deadline")],
        ["Batas pelunasan", p.get("payment_deadline"), "Jam lelang", p.get("auction_time")],
        ["Limit", _money(p.get("auction_limit")), "Uang jaminan", _money(p.get("deposit_amount"))],
        ["LT / LB", f"{p.get('land_area','—')} / {p.get('building_area','—')} m²", "Hak", f"{p.get('certificate_type','—')} {p.get('certificate_no','') }"],
    ], [1.15, 2.25, 1.25, 2.15])
    extraction = snapshot.get("document_extraction", {}) or {}
    evidence = extraction.get("field_evidence", {}) or {}
    doc.add_paragraph(
        f"Sumber dokumen: {extraction.get('source_file_name') or 'Tidak tercatat'} | "
        f"Evidence tanggal lelang: {evidence.get('auction_date') or 'Tidak tersedia'} | "
        f"Evidence batas setor: {evidence.get('deposit_deadline') or 'Tidak tersedia'}"
    )

    doc.add_heading("3. Kondisi Fisik, Survei, dan Legalitas", level=1)
    for text in [
        f"Status survei: {snapshot.get('survey',{}).get('survey_status','—')} | Status hunian: {snapshot.get('survey',{}).get('occupancy_status','—')} | Tanggal: {snapshot.get('survey',{}).get('survey_date','—')}",
        f"Kondisi fisik: {snapshot.get('survey',{}).get('physical_condition','—')} | Akses: {snapshot.get('survey',{}).get('access','—')} | Lebar jalan: {snapshot.get('survey',{}).get('road_width_m','—')} m",
        f"Interior diperiksa: {snapshot.get('survey',{}).get('interior_inspected')} | Identitas terverifikasi: {snapshot.get('legal',{}).get('identity_verified')} | Pajak diverifikasi: {snapshot.get('legal',{}).get('tax_rules_verified')}",
        f"Catatan survei: {snapshot.get('survey',{}).get('survey_notes') or 'Belum ada catatan'}",
    ]: bullet(text)

    doc.add_heading("4. Analisis Pasar dan Pembanding", level=1)
    doc.add_paragraph(f"Estimasi dasar {_money(market.get('base_exit'))}; konservatif {_money(market.get('conservative_exit'))}; optimistis {_money(market.get('optimistic_exit'))}. Jumlah pembanding dihitung {market.get('valid_count',0)}; GO-grade {market.get('go_grade_count',0)}; indeks kualitas data {market.get('confidence','—')}/100.")
    comps = []
    for row in market.get("valid", []) or []:
        comps.append([row.get("name") or "—", _money(row.get("price")), f"{row.get('land_area') or '—'}/{row.get('building_area') or '—'}", _money(row.get("subject_normalized_value")), f"{row.get('distance_km')} km" if row.get("distance_km") is not None else "—", str(row.get("source_url") or row.get("source_platforms") or "—")[:70]])
    table(["Listing", "Asking", "LT/LB", "Nilai indikatif", "Jarak", "Sumber"], comps or [["Belum ada data", "—", "—", "—", "—", "—"]], [1.55, 0.85, 0.55, 0.9, 0.55, 1.55])
    doc.add_paragraph("Metode: data harga dan luas dinormalisasi, kemiripan dan jarak digunakan sebagai bobot, listing outlier diturunkan bobotnya. Asking price tidak dianggap sama dengan harga transaksi.")

    doc.add_heading("5. Rencana Renovasi dan RAB", level=1)
    doc.add_paragraph(f"Estimasi biaya renovasi yang masuk modal: {_money(costs.get('renovation_cost'))}. Pricebook yang digunakan: {PRICE_CATALOG_VERSION}. Harga paket merupakan allowance screening bahan+upah berdasarkan scope dan satuan; bukan tarif resmi SSH/HSPK atau quotation kontraktor. Rate yang belum tercakup wajib dilengkapi dengan quotation atau override manual yang mencatat sumber.")
    doc.add_paragraph(f"Acuan komponen SSH Sidoarjo TA 2026: {PRICE_CATALOG_REFERENCES['ssh_sidoarjo_2026']} | ASB/HSPK Sidoarjo: {PRICE_CATALOG_REFERENCES['hspk_sidoarjo_2026']} | Metode AHSP PUPR: {PRICE_CATALOG_REFERENCES['ahsp_pupr_2023']}")
    rab = []
    for row in _rab_rows(snapshot):
        if not rab_item_is_in_scope(row): continue
        sub = rab_row_subtotals(row).get("subtotal_base")
        rab.append([row.get("subcategory") or "—", row.get("work_item") or "—", f"{row.get('quantity') or '—'} {row.get('unit') or ''}", _money(row.get("unit_cost")), _money(sub), row.get("confidence") or "—"])
    table(["Kelompok", "Pekerjaan", "Volume", "Harga/unit", "Subtotal", "Keyakinan"], rab or [["—", "Tidak ada item RAB", "—", "—", "—", "—"]], [0.8, 2.7, 0.7, 0.85, 0.9, 0.65])
    group_rows = [[x["Kelompok pekerjaan"], str(x["Jumlah item"]), _money(x["Subtotal rendah (Rp)"]), _money(x["Subtotal dasar (Rp)"]), _money(x["Subtotal atas (Rp)"]), str(x["Item belum lengkap"])] for x in summarize_rab_scope_totals(_rab_rows(snapshot))]
    doc.add_heading("Subtotal per kelompok", level=2)
    table(["Kelompok", "Item", "Rendah", "Dasar", "Atas", "Belum lengkap"], group_rows or [["—", "0", "—", "—", "—", "0"]], [1.45, 0.45, 1.2, 1.2, 1.2, 0.8])

    doc.add_heading("6. Proyeksi Modal dan Skenario Hasil", level=1)
    cost_rows = []
    for label, key in [("Harga lelang", "bid_price"), ("Bea lelang", "buyer_auction_fee"), ("BPHTB", "bphtb"), ("BPN/legalitas", "legal_bpn_cost"), ("Penguasaan/kerohiman", "possession_cost"), ("Renovasi", "renovation_cost"), ("Contingency", "renovation_contingency"), ("Cadangan kondisi tersembunyi", "hidden_condition_reserve"), ("Holding", "holding_cost"), ("Biaya lain pra-jual", "other_presale_cost"), ("Total modal sebelum penjualan", "capital_before_sale"), ("Kebutuhan kas termasuk cadangan", "cash_requirement_including_reserve")]: cost_rows.append([label, _money(limit.get(key))])
    table(["Komponen biaya", "Nilai"], cost_rows, [4.1, 2.7])
    scenario_rows = [[x["Skenario"], _money(x["Harga jual indikatif"]), _money(x["Laba bersih indikatif"]), pct(x["ROI"])] for x in _scenario_rows(snapshot)]
    doc.add_heading("Skenario harga jual @ limit", level=2)
    table(["Skenario", "Harga jual", "Profit bersih", "ROI"], scenario_rows or [["Data belum tersedia", "—", "—", "—"]], [1.7, 1.7, 1.7, 1.7])

    doc.add_heading("7. Strategi Penawaran", level=1)
    table(["Indikator bid", "Nilai / status"], [
        ["Harga limit", _money(bid.get("min_bid"))],
        ["Bid target ROI tengah", _money(bid.get("mid_bid") or bid.get("mid_economic_ceiling"))],
        ["Batas maksimum target ROI minimum", _money(bid.get("max_bid") or bid.get("max_economic_ceiling"))],
        ["Walk-away", _money(bid.get("walk_away_from")) if bid.get("walk_away_from") is not None else bid.get("walk_away_reason", "—")],
        ["Provisional", str(bid.get("provisional"))],
    ], [3.0, 3.8])
    for reason in bid.get("provisional_reasons", []) or []: bullet(reason)

    doc.add_heading("8. Risk Register dan Mitigasi", level=1)
    risks = snapshot.get("risk_register", []) or []
    risk_rows = [[x.get("risk_description") or "—", f"{x.get('probability_1_5') or '—'}/5", f"{x.get('impact_1_5') or '—'}/5", _money(x.get("cost_reserve")), x.get("mitigation") or "—"] for x in risks]
    table(["Risiko", "Prob.", "Dampak", "Cadangan", "Mitigasi"], risk_rows or [["Belum dicatat", "—", "—", "—", "—"]], [1.6, 0.5, 0.55, 1.0, 3.0])

    doc.add_heading("9. Pendanaan, Prasyarat, dan Due Diligence", level=1)
    bullet(f"Kas tersedia untuk proyek: {_money((snapshot.get('liquidity') or {}).get('cash_available_for_new_project'))}")
    bullet(f"Kebutuhan kas termasuk cadangan: {_money((snapshot.get('funding') or {}).get('project_cash_need'))}")
    bullet("Uang jaminan merupakan kebutuhan kas di muka dan bagian dari pelunasan harga menang, bukan biaya tambahan yang boleh dijumlahkan dua kali.")
    for item in (decision.get("blockers", []) or []): bullet(f"Blocker: {item}")
    for item in (decision.get("warnings", []) or []): bullet(f"Peringatan: {item}")
    for item in [
        "Cocokkan objek fisik, alamat, nomor hak, luas dan dokumen pengumuman.",
        "Konfirmasi status penghuni dan cara penguasaan secara langsung.",
        "Verifikasi tanggal lelang, batas setor jaminan, increment bid, dan batas pelunasan pada pengumuman resmi.",
        "Minta minimal dua quotation renovasi dan lakukan verifikasi komponen harga.",
        "Pastikan kas tersedia untuk akuisisi, renovasi, holding, pemasaran, dan cadangan risiko.",
    ]: bullet(item)

    doc.add_heading("10. Asumsi dan Pernyataan Pembatasan", level=1)
    doc.add_paragraph("Dokumen ini merupakan memorandum screening investasi yang disusun dari data yang dimasukkan pengguna dan perhitungan deterministik PFMS. Harga jual merupakan indikasi dari pembanding; harga renovasi merupakan allowance pricebook jika tersedia; pekerjaan tersembunyi tetap membawa ketidakpastian. Dokumen ini bukan appraisal resmi, pendapat hukum, quotation kontraktor, jaminan keuntungan, atau pengganti pemeriksaan lapangan.")
    doc.add_paragraph("Semua angka, sumber, status legalitas, pajak, kondisi bangunan dan asumsi waktu wajib diperiksa kembali sebelum bidding atau pencairan dana.")

    output = io.BytesIO(); doc.save(output); return output.getvalue()
