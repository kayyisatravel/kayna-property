from __future__ import annotations
from typing import Any
from io import BytesIO
import re
from urllib.parse import urlparse
from datetime import date
from core.utils import idr, pct, to_float
from reports.regional_economy import build_regional_economy_context
from core.renovation_engine import rab_row_subtotals, summarize_rab_scope_totals

BRAND = "KAYNA PROPERTY"


def _property(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("property", {}) if isinstance(snapshot.get("property"), dict) else {}


def property_filename(snapshot: dict[str, Any], extension: str = "docx") -> str:
    p = _property(snapshot)
    raw = " ".join(str(x or "") for x in (p.get("name"), p.get("lot_code"), snapshot.get("property_id")))
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "properti"
    slug = slug[:90].strip("-")
    return f"investment-memo-{slug}.{extension.lstrip('.')}"


def _economy(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    p = _property(snapshot)
    location = " ".join(str(p.get(k) or "") for k in ("address", "district", "province"))
    return build_regional_economy_context(location)


def build_analysis_markdown(snapshot: dict[str, Any]) -> str:
    p = _property(snapshot); market = snapshot.get("market", {}); bid = snapshot.get("bidding", {}); limit = snapshot.get("at_limit", {}); decision = snapshot.get("decision", {})
    at = limit if isinstance(limit, dict) else {}
    mid_display = idr(bid.get("mid_bid")) if bid.get("mid_bid") is not None else (
        f"Belum ada bid legal; ceiling di bawah limit {idr(bid.get('mid_economic_ceiling'))} (diagnostik saja; ROI pada ceiling {pct((bid.get('mid_result') or {}).get('roi_pct'))})" if bid.get("mid_economic_ceiling") is not None else "Belum tersedia")
    max_display = idr(bid.get("max_bid")) if bid.get("max_bid") is not None else (
        f"TIDAK ADA BID; ceiling di bawah limit {idr(bid.get('max_economic_ceiling'))} (diagnostik saja; ROI pada ceiling {pct((bid.get('max_result') or {}).get('roi_pct'))})" if bid.get("max_economic_ceiling") is not None else "Belum tersedia")
    walk_display = idr(bid.get("walk_away_from")) if bid.get("walk_away_from") is not None else bid.get("walk_away_reason", "Belum tersedia")
    lines = [
        f"# {BRAND}", "**Pelaksana Proyek & Pengelola Investasi Properti**", "",
        f"# Investment Memo — {p.get('name') or p.get('lot_code') or 'Properti'}", "",
        f"Tanggal analisis: {snapshot.get('analyzed_at','')}", f"Property ID: {snapshot.get('property_id','')}", f"Keputusan underwriting: **{decision.get('status','HOLD')}**", "",
        "## 1. Ringkasan Eksekutif", str(decision.get("summary") or "Dokumen ini merangkum analisis investasi berdasarkan data dan asumsi yang tersedia."), "",
        "## 2. Identitas Objek", f"- Nama: {p.get('name','—')}", f"- Kode lot: {p.get('lot_code','—')}", f"- Alamat: {p.get('address','—')}", f"- Kantor lelang: {p.get('auction_office','—')}", f"- Tanggal lelang: {p.get('auction_date','—')}", f"- Batas setor jaminan: {p.get('deposit_deadline','—')}", f"- Limit: {idr(p.get('auction_limit'))}", f"- LT/LB: {p.get('land_area','—')} / {p.get('building_area','—')} m²", "",
        "## 3. Analisis Pasar", f"- Comparable valid: {market.get('valid_count',0)}", f"- Indeks kualitas data: {market.get('confidence','—')}/100", f"- ARV konservatif: {idr(market.get('conservative_exit'))}", f"- ARV dasar: {idr(market.get('base_exit'))}", f"- ARV optimistis: {idr(market.get('optimistic_exit'))}", "",
        "## 4. Proyeksi Keuangan", f"- Total modal sebelum biaya penjualan: {idr(at.get('capital_before_sale'))}", f"- Biaya penjualan: {idr(at.get('selling_cost'))}", f"- Estimasi profit bersih: {idr(at.get('net_profit'))}", f"- ROI proyek: {pct(at.get('roi_pct'))}", f"- Holding: {at.get('holding_months','—')} bulan", "",
        "## 5. Strategi Penawaran", f"- Limit/harga mulai: {idr(bid.get('min_bid'))}", f"- Bid tertinggi sasaran ROI 35%: {mid_display}", f"- Bid tertinggi sasaran ROI 25%: {max_display}", f"- Walk-away: {walk_display}", "",
    ]
    economy = _economy(snapshot)
    if economy:
        lines += ["## 6. Konteks Ekonomi Regional (Data Resmi)"]
        lines += [f"- {x['geography']} — {x['indicator']}: {x['value']} ({x['period']}, dipublikasikan {x['published']}); sumber: {x['source']} — {x['url']}" for x in economy["items"]]
        lines += [f"- Implikasi: {x}" for x in economy["advice"]]
        lines += [f"- Batasan: {economy['limitations']}", ""]
    else:
        lines += ["## 6. Konteks Ekonomi Regional", "Tidak disertakan karena snapshot data ekonomi resmi yang tersedia tidak cocok dengan lokasi objek atau telah melewati jendela kesegaran yang ditetapkan. Tidak ada asumsi ekonomi yang dibuat.", ""]
    # Add an auditable RAB view to the lightweight Markdown memo as well.
    costs = snapshot.get("costs", {}) if isinstance(snapshot.get("costs"), dict) else {}
    rab_rows = costs.get("renovation_items", []) if isinstance(costs.get("renovation_items"), list) else []
    lines += ["## 7. RAB dan Rincian Subtotal"]
    lines += ["| Kelompok | Pekerjaan | Volume | Harga satuan | Subtotal dasar |", "|---|---|---:|---:|---:|"]
    for row in rab_rows[:80]:
        q = to_float(row.get("quantity")); rate = to_float(row.get("unit_cost"))
        subtotal = q * rate if q > 0 and rate > 0 else None
        lines.append(f"| {row.get('subcategory') or '—'} | {row.get('work_item') or '—'} | {row.get('quantity') or '—'} {row.get('unit') or ''} | {idr(rate) if rate > 0 else 'Belum tersedia'} | {idr(subtotal) if subtotal is not None else 'Belum tersedia'} |")
    grouped = summarize_rab_scope_totals(rab_rows)
    if grouped:
        lines += ["", "### Subtotal menurut kelompok pekerjaan", "| Kelompok | Item | Subtotal rendah | Subtotal dasar | Subtotal atas |", "|---|---:|---:|---:|---:|"]
        for group in grouped:
            lines.append(f"| {group['Kelompok pekerjaan']} | {group['Jumlah item']} | {idr(group.get('Subtotal rendah (Rp)')) if group.get('Subtotal rendah (Rp)') is not None else 'Belum tersedia'} | {idr(group.get('Subtotal dasar (Rp)')) if group.get('Subtotal dasar (Rp)') is not None else 'Belum tersedia'} | {idr(group.get('Subtotal atas (Rp)')) if group.get('Subtotal atas (Rp)') is not None else 'Belum tersedia'} |")
    else:
        lines.append("Belum ada rincian BoQ/RAB yang tersimpan pada snapshot ini.")
    lines += ["", "## 8. Risk Register"]
    risks = snapshot.get("risk_register", []) or []
    if risks:
        lines += ["| Risiko | Probabilitas / Dampak | Cadangan | Mitigasi |", "|---|---:|---:|---|"]
        for risk in risks[:40]:
            lines.append(f"| {risk.get('risk_description') or '—'} | {risk.get('probability_1_5','—')} / {risk.get('impact_1_5','—')} | {idr(risk.get('cost_reserve'))} | {risk.get('mitigation') or '—'} |")
    else:
        lines.append("Tidak ada risiko yang dicatat dalam snapshot.")
    lines += ["", "## 9. Blocker & Peringatan"]
    lines += [f"- BLOCKER: {x}" for x in decision.get("blockers", [])] or ["- Tidak ada blocker utama yang tercatat."]
    lines += [f"- PERINGATAN: {x}" for x in decision.get("warnings", [])] or ["- Tidak ada peringatan tambahan."]
    from core.renovation_schedule import estimate_renovation_duration
    schedule = estimate_renovation_duration(rab_rows) if rab_rows else {"available": False}
    lines += ["", "## 10. Estimasi Durasi Renovasi"]
    if schedule.get("available"):
        lines.append(f"Durasi dasar {schedule['calendar_days']['base']} hari kalender; cepat {schedule['calendar_days']['fast']} hari; konservatif {schedule['calendar_days']['slow']} hari. Asumsi {schedule['working_days_per_week']} hari kerja/minggu dan buffer {schedule['buffer_pct']:.0f}%. Ini allowance jadwal, bukan jaminan kontraktor.")
        for phase in schedule.get("phases", []):
            lines.append(f"- {phase['phase']}: {phase['base_days']:.1f} hari kerja (dasar)")
    else:
        lines.append("Belum tersedia volume pekerjaan untuk estimasi durasi.")
    lines += ["", "## 11. Pelaksana Proyek", f"{BRAND} bertindak sebagai pelaksana proyek/pengelola investasi sesuai rencana kerja dan anggaran yang disetujui investor.", "", "## Penafian", "Dokumen ini merupakan alat bantu underwriting dan bukan appraisal resmi, pendapat hukum, jaminan keuntungan, atau quotation kontraktor. Harga listing bukan harga transaksi kecuali terverifikasi. Seluruh sumber, kondisi fisik, jadwal, dan asumsi wajib diperiksa sebelum keputusan investasi."]
    return "\n".join(lines)


def build_analysis_docx(snapshot: dict[str, Any]) -> bytes:
    """Create a professional investor memo. Every text run is >=11 pt."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    except Exception as exc:
        raise RuntimeError("Library python-docx belum tersedia. Tambahkan python-docx pada requirements.txt.") from exc

    p = _property(snapshot); market = snapshot.get("market", {}); bid = snapshot.get("bidding", {}); at = snapshot.get("at_limit", {}); decision = snapshot.get("decision", {})
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(.62); sec.bottom_margin = Inches(.62); sec.left_margin = Inches(.72); sec.right_margin = Inches(.72)
    styles = doc.styles
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        styles[name].font.name = "Aptos"
        styles[name].font.size = Pt(11 if name == "Normal" else (20 if name == "Title" else (13 if name.startswith("Heading") else 11)))
        if name.startswith("Heading"):
            styles[name].font.color.rgb = RGBColor(23, 43, 77)
    styles["Normal"].paragraph_format.space_after = Pt(4)

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run(f"{BRAND}  |  PELAKSANA PROYEK")
    run.bold = True; run.font.name = "Aptos"; run.font.size = Pt(11); run.font.color.rgb = RGBColor(15, 118, 110)
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = footer.add_run(f"{BRAND}  •  Investment Memo  •  {snapshot.get('analyzed_at','')}")
    fr.font.name = "Aptos"; fr.font.size = Pt(11); fr.font.color.rgb = RGBColor(80, 90, 100)

    title = doc.add_paragraph(style="Title"); title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    title.add_run("INVESTMENT MEMO")
    sub = doc.add_paragraph(); r = sub.add_run(str(p.get("name") or p.get("lot_code") or "Properti Lelang")); r.bold = True; r.font.size = Pt(15)
    meta = doc.add_paragraph(f"Tanggal analisis: {snapshot.get('analyzed_at','—')}   |   Property ID: {snapshot.get('property_id','—')}")
    meta.paragraph_format.space_after = Pt(8)
    doc.add_heading("Ringkasan Eksekutif", level=1)
    doc.add_paragraph(str(decision.get("summary") or "Analisis investasi berdasarkan data dan asumsi yang tersedia."))
    # Decision box as a shaded one-cell table.
    t = doc.add_table(rows=1, cols=2); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.cell(0,0).text = "KEPUTUSAN UNDERWRITING"
    t.cell(0,1).text = str(decision.get("status", "HOLD"))
    for cell in t.rows[0].cells:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for para in cell.paragraphs:
            for run in para.runs: run.font.size = Pt(11); run.bold = True

    def add_table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None):
        table = doc.add_table(rows=1, cols=len(headers)); table.style = "Light Shading Accent 1"; table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        for i, h in enumerate(headers): table.rows[0].cells[i].text = str(h)
        for row in rows:
            cells = table.add_row().cells
            for i, value in enumerate(row): cells[i].text = "—" if value is None or value == "" else str(value)
        # Repeat header rows on page breaks and prevent individual rows from splitting.
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        header_props = table.rows[0]._tr.get_or_add_trPr()
        repeat_header = OxmlElement("w:tblHeader"); repeat_header.set(qn("w:val"), "true"); header_props.append(repeat_header)
        for row in table.rows:
            tr_props = row._tr.get_or_add_trPr()
            cant_split = OxmlElement("w:cantSplit"); tr_props.append(cant_split)
            for idx, cell in enumerate(row.cells):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if widths and idx < len(widths):
                    cell.width = Inches(widths[idx])
                for para in cell.paragraphs:
                    para.paragraph_format.space_after = Pt(1)
                    para.paragraph_format.keep_together = True
                    for run in para.runs:
                        run.font.name = "Aptos"; run.font.size = Pt(11)
        return table

    doc.add_heading("1. Identitas dan Jadwal Lelang", level=1)
    add_table(["Parameter", "Data"], [
        ["Nama objek", p.get("name")], ["Kode lot", p.get("lot_code")], ["Alamat", p.get("address")],
        ["KPKNL", p.get("auction_office")], ["Tanggal lelang", p.get("auction_date")],
        ["Batas setor jaminan", p.get("deposit_deadline")], ["Batas pelunasan", p.get("payment_deadline")],
        ["Nilai limit", idr(p.get("auction_limit"))], ["LT / LB", f"{p.get('land_area','—')} / {p.get('building_area','—')} m²"],
        ["Sertifikat", p.get("certificate_type")],
    ])
    doc.add_heading("2. Penilaian Pasar dan Skenario Exit", level=1)
    add_table(["Indikator", "Nilai"], [
        ["Comparable valid", market.get("valid_count", 0)], ["Indeks kualitas data", f"{market.get('confidence','—')}/100"],
        ["ARV konservatif", idr(market.get("conservative_exit"))], ["ARV dasar", idr(market.get("base_exit"))], ["ARV optimistis", idr(market.get("optimistic_exit"))],
    ])
    comp_rows = market.get("valid") or snapshot.get("comparables") or []
    if comp_rows:
        doc.add_heading("Daftar Pembanding", level=2)
        rows = []
        for c in comp_rows[:20]:
            raw_url = str(c.get("source_url") or "").strip()
            host = urlparse(raw_url if raw_url.startswith(("http://", "https://")) else "https://" + raw_url).netloc if raw_url else ""
            host = host.removeprefix("www.") or str(c.get("source_platforms") or "—")[:24]
            price_m = to_float(c.get("price")) / 1_000_000
            price_label = f"Rp{price_m:,.1f} jt".replace(",", "X").replace(".", ",").replace("X", ".") if price_m else "—"
            area_label = f"{c.get('land_area') or '—'} / {c.get('building_area') or '—'}"
            distance_label = f"{to_float(c.get('distance_m')):,.0f} m".replace(",", ".") if c.get("distance_m") not in (None, "") else "—"
            rows.append([str(c.get("name") or "Pembanding")[:42], price_label, area_label, distance_label, host])
        add_table(["Pembanding", "Harga penawaran", "LT / LB m²", "Jarak", "Sumber"], rows, widths=[2.0, 1.15, 1.05, 0.85, 1.6])
    doc.add_heading("3. Struktur Modal dan Profitabilitas", level=1)
    add_table(["Komponen", "Nilai"], [
        ["Harga bid pada skenario", idr(at.get("bid_price"))], ["Total modal sebelum penjualan", idr(at.get("capital_before_sale"))],
        ["Biaya penjualan", idr(at.get("selling_cost"))], ["Net proceeds", idr(at.get("net_proceeds"))],
        ["Estimasi profit bersih", idr(at.get("net_profit"))], ["ROI", pct(at.get("roi_pct"))], ["Holding", f"{at.get('holding_months','—')} bulan"],
    ])
    doc.add_heading("4. Strategi Penawaran", level=1)
    add_table(["Level", "Nilai / Catatan"], [
        ["Limit / harga mulai", idr(bid.get("min_bid"))], ["Ceiling target ROI menengah", idr(bid.get("mid_bid") or bid.get("mid_economic_ceiling"))],
        ["Ceiling target ROI minimum", idr(bid.get("max_bid") or bid.get("max_economic_ceiling"))], ["Walk-away", idr(bid.get("walk_away_from")) if bid.get("walk_away_from") is not None else bid.get("walk_away_reason")],
    ])
    economy = _economy(snapshot)
    doc.add_heading("5. Konteks Ekonomi Regional", level=1)
    if economy:
        economy_rows = []
        for x in economy["items"]:
            area_indicator = f"{x['geography']}\n{x['indicator']}"
            value_period = f"{x['value']}\n{x['period']}\nRilis {x['published']}"
            economy_rows.append([area_indicator, value_period, x["source"]])
        add_table(["Wilayah / indikator", "Angka / periode", "Penerbit"], economy_rows, widths=[2.55, 2.05, 2.05])
        for advice in economy["advice"]: doc.add_paragraph(advice, style="List Bullet")
        doc.add_paragraph(economy["limitations"])
        # Keep references clickable without printing very long raw URLs that
        # waste memo space. The hyperlink target retains the full source URL.
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        def add_source_link(paragraph, label: str, url: str):
            rid = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
            hyperlink = OxmlElement("w:hyperlink"); hyperlink.set(qn("r:id"), rid)
            run = OxmlElement("w:r"); props = OxmlElement("w:rPr")
            fonts = OxmlElement("w:rFonts"); fonts.set(qn("w:ascii"), "Aptos"); fonts.set(qn("w:hAnsi"), "Aptos"); props.append(fonts)
            size = OxmlElement("w:sz"); size.set(qn("w:val"), "22"); props.append(size)
            color = OxmlElement("w:color"); color.set(qn("w:val"), "0563C1"); props.append(color)
            underline = OxmlElement("w:u"); underline.set(qn("w:val"), "single"); props.append(underline)
            run.append(props); text_el = OxmlElement("w:t"); text_el.text = label; run.append(text_el); hyperlink.append(run)
            paragraph._p.append(hyperlink)
        seen_source_urls = set()
        for src in economy["items"]:
            if src["url"] in seen_source_urls:
                continue
            seen_source_urls.add(src["url"])
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            prefix = paragraph.add_run("Sumber resmi: "); prefix.font.size = Pt(11)
            link_label = f"{src['source']} (rilis {src['published']})"
            add_source_link(paragraph, link_label, src["url"])
    else:
        doc.add_paragraph("Tidak disertakan: tidak tersedia snapshot resmi yang cocok dengan lokasi objek atau data telah melewati jendela kesegaran. Tidak ada asumsi ekonomi yang dipaksakan.")
    doc.add_heading("6. Risiko, Blocker, dan Mitigasi", level=1)
    for label, items in (("Blocker", decision.get("blockers", [])), ("Peringatan", decision.get("warnings", []))):
        doc.add_heading(label, level=2)
        if items:
            for item in items: doc.add_paragraph(str(item), style="List Bullet")
        else: doc.add_paragraph("Tidak ada catatan.")
    risk_items = snapshot.get("risk_register", [])
    if risk_items:
        risk_rows = []
        for r in risk_items[:20]:
            risk_rows.append([str(r.get("risk_description") or "Risiko")[:72], f"{r.get('probability_1_5','—')} / {r.get('impact_1_5','—')}", idr(r.get("cost_reserve")), str(r.get("mitigation") or "—")[:130]])
        add_table(["Risiko", "P / D", "Cadangan", "Mitigasi"], risk_rows, widths=[2.05, 0.7, 1.15, 2.75])
    doc.add_heading("7. RAB Ringkas", level=1)
    costs = snapshot.get("costs", {}) if isinstance(snapshot.get("costs"), dict) else {}
    renovation_rows = costs.get("renovation_items", []) if isinstance(costs.get("renovation_items"), list) else []
    if renovation_rows:
        add_table(["Kelompok", "Pekerjaan", "Volume", "Satuan", "Harga satuan", "Subtotal"], [[r.get("subcategory") or r.get("category"), r.get("work_item"), r.get("quantity"), r.get("unit"), idr(r.get("unit_cost")), idr(to_float(r.get("quantity"))*to_float(r.get("unit_cost")))] for r in renovation_rows[:60]])
    else:
        doc.add_paragraph("Rincian item RAB tidak tersedia pada snapshot memo ini.")
    from core.renovation_schedule import estimate_renovation_duration
    schedule = estimate_renovation_duration(renovation_rows) if renovation_rows else {"available": False}
    doc.add_heading("8. Estimasi Waktu Renovasi", level=1)
    if schedule.get("available"):
        doc.add_paragraph(f"Estimasi dasar {schedule['calendar_days']['base']} hari kalender; rentang cepat {schedule['calendar_days']['fast']} hari dan konservatif {schedule['calendar_days']['slow']} hari. Asumsi {schedule['working_days_per_week']} hari kerja per minggu, buffer {schedule['buffer_pct']:.0f}%, dan satu regu kecil per bidang kerja.")
        add_table(["Tahap", "Cepat (hari kerja)", "Dasar (hari kerja)", "Konservatif (hari kerja)"], [[x["phase"], round(x["fast_days"], 1), round(x["base_days"], 1), round(x["slow_days"], 1)] for x in schedule.get("phases", [])], widths=[3.1, 1.1, 1.1, 1.35])
        doc.add_paragraph("Durasi adalah estimasi penjadwalan dari volume BoQ, bukan jaminan kontraktor. Belum mencakup waktu tunggu material, cuaca, izin, perubahan lingkup, atau keterlambatan vendor.")
    else:
        doc.add_paragraph("Belum ada rincian volume pekerjaan yang cukup untuk menghitung durasi renovasi.")
    doc.add_heading("9. Pelaksana Proyek dan Tata Kelola", level=1)
    doc.add_paragraph(f"{BRAND} bertindak sebagai pelaksana proyek/pengelola investasi. Pengeluaran aktual, perubahan lingkup, komitmen vendor, dan keputusan perubahan budget harus dicatat pada sistem sebelum laporan keuangan proyek dianggap final.")
    doc.add_heading("Batasan dan Penafian", level=1)
    doc.add_paragraph("Memo ini adalah alat bantu underwriting, bukan appraisal resmi, nasihat hukum, atau jaminan hasil. Verifikasi harga transaksi, legalitas, kondisi fisik, biaya, dan jadwal sebelum bid.")

    # Enforce a minimum font size of 11pt across all content, including tables.
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if run.font.size is None or run.font.size.pt < 11: run.font.size = Pt(11)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if run.font.size is None or run.font.size.pt < 11: run.font.size = Pt(11)
    out = BytesIO(); doc.save(out); return out.getvalue()


# Backward-compatible API aliases retained for existing integrations.
def investment_memo_filename(snapshot: dict[str, Any], extension: str = "docx") -> str:
    return property_filename(snapshot, extension)

def build_investment_memo_docx(snapshot: dict[str, Any]) -> bytes:
    return build_analysis_docx(snapshot)

