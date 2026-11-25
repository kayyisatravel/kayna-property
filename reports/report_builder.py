from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import re
from typing import Any
from zoneinfo import ZoneInfo

from core.utils import idr, pct, to_float
from core.renovation_engine import rab_item_is_in_scope, rab_row_subtotals, summarize_rab_scope_totals
from core.renovation_schedule import estimate_item_duration, estimate_renovation_duration

BRAND = "KAYNA PROPERTY"
BRAND_DESCRIPTOR = "PROPERTY INVESTMENT & PROJECT MANAGEMENT"
DOCUMENT_TITLE = "MEMORANDUM INVESTASI PROPERTI"
NAVY = "172B4D"
NAVY_DARK = "10243E"
TEAL = "0F766E"
PALE = "EEF3F8"
MID_GREY = "667085"


def _property(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("property", {}) if isinstance(snapshot.get("property"), dict) else {}


def _fmt_wib(value: Any) -> str:
    """Display analysis timestamps in Asia/Jakarta, preserving date-only values."""
    raw = str(value or "").strip()
    if not raw:
        return "—"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            only_date = datetime.strptime(raw, "%Y-%m-%d").date()
            months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            return f"{only_date.day} {months[only_date.month - 1]} {only_date.year}"
        except ValueError:
            return raw
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # App timestamps are generated on a UTC-hosted Streamlit runtime.
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ZoneInfo("Asia/Jakarta"))
        months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        return f"{local.day} {months[local.month - 1]} {local.year}, {local:%H.%M} WIB"
    except (ValueError, TypeError, OverflowError):
        return raw


def _as_rows(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def property_filename(snapshot: dict[str, Any], extension: str = "docx") -> str:
    p = _property(snapshot)
    raw = " ".join(str(x or "") for x in (p.get("name"), p.get("lot_code"), snapshot.get("property_id")))
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "properti"
    slug = slug[:90].strip("-")
    return f"investment-memo-{slug}.{extension.lstrip('.')}"


def _scenario_target_roi(snapshot: dict[str, Any], scenario_name: str) -> float:
    """Return the configured ROI target for the matching bid scenario."""
    bid = snapshot.get("bidding") if isinstance(snapshot.get("bidding"), dict) else {}
    rules = snapshot.get("rules") if isinstance(snapshot.get("rules"), dict) else {}
    minimum = to_float(rules.get("minimum_roi_pct"), 25.0)
    if scenario_name == "Bid pada Limit":
        return minimum
    if scenario_name == "Skenario Tengah":
        return to_float(bid.get("mid_roi_target"), to_float(rules.get("mid_roi_pct"), 35.0))
    return to_float(bid.get("max_roi_target"), minimum)


def _scenario_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    p = _property(snapshot)
    bid = snapshot.get("bidding") if isinstance(snapshot.get("bidding"), dict) else {}
    at = snapshot.get("at_limit") if isinstance(snapshot.get("at_limit"), dict) else {}
    specs = [
        ("Bid pada Limit", bid.get("min_bid") or p.get("auction_limit"), at, "Harga limit lelang", True),
        ("Skenario Tengah", bid.get("mid_bid"), bid.get("mid_result"), f"Target ROI {to_float(bid.get('mid_roi_target'), 35):.1f}%", bid.get("mid_bid") is not None),
        ("Skenario Atas", bid.get("max_bid"), bid.get("max_result"), f"Target ROI minimum {to_float(bid.get('max_roi_target'), 25):.1f}%", bid.get("max_bid") is not None),
    ]
    out: list[dict[str, Any]] = []
    for name, bid_value, result, note, legal_bid in specs:
        result = result if isinstance(result, dict) else {}
        amount = to_float(bid_value) or to_float(result.get("bid_price"))
        # A ceiling below the auction limit may be a diagnostic only, not a legal bid.
        if name != "Bid pada Limit" and bid_value is None and amount > 0:
            note = f"Ceiling indikatif; bukan bid legal. {note}"
        out.append({"name": name, "bid": amount or None, "result": result, "note": note, "legal_bid": bool(legal_bid)})
    return out


def _sum_rab(rab_rows: list[dict[str, Any]]) -> dict[str, Any]:
    included = [r for r in rab_rows if rab_item_is_in_scope(r)]
    levels = {"low": "subtotal_low", "base": "subtotal_base", "high": "subtotal_high"}
    result: dict[str, Any] = {"count": len(included), "priced": {}, "totals": {}}
    for level, key in levels.items():
        vals = [rab_row_subtotals(row).get(key) for row in included]
        known = [v for v in vals if v is not None]
        result["priced"][level] = len(known)
        result["totals"][level] = sum(known) if known else None
    result["complete_base"] = result["priced"]["base"] == result["count"]
    return result


def build_analysis_markdown(snapshot: dict[str, Any]) -> str:
    p = _property(snapshot)
    market = snapshot.get("market", {}) if isinstance(snapshot.get("market"), dict) else {}
    bid = snapshot.get("bidding", {}) if isinstance(snapshot.get("bidding"), dict) else {}
    decision = snapshot.get("decision", {}) if isinstance(snapshot.get("decision"), dict) else {}
    costs = snapshot.get("costs", {}) if isinstance(snapshot.get("costs"), dict) else {}
    rab_rows = _as_rows(costs.get("renovation_items"))
    scenarios = _scenario_rows(snapshot)
    lines = [
        f"# {DOCUMENT_TITLE}", f"**{BRAND} | {BRAND_DESCRIPTOR}**", "",
        f"## {p.get('name') or p.get('lot_code') or 'Properti Lelang'}", "",
        f"Tanggal analisis: {_fmt_wib(snapshot.get('analyzed_at'))}",
        f"Property ID: {snapshot.get('property_id', '—')}",
        f"Keputusan underwriting: **{decision.get('status', 'HOLD')}**", "",
        "## 1. Ringkasan Eksekutif", str(decision.get("summary") or "Analisis investasi berdasarkan data dan asumsi yang tersedia."), "",
        "## 2. Identitas dan Jadwal Lelang",
        f"- Alamat: {p.get('address', '—')}", f"- KPKNL: {p.get('auction_office', '—')}",
        f"- Tanggal lelang: {p.get('auction_date', '—')}", f"- Batas setor jaminan: {p.get('deposit_deadline', '—')}",
        f"- Limit: {idr(p.get('auction_limit'))}", f"- LT/LB: {p.get('land_area', '—')} / {p.get('building_area', '—')} m²", "",
        "## 3. Penilaian Pasar",
        f"- Pembanding valid: {market.get('valid_count', 0)}", f"- Indeks kualitas data: {market.get('confidence', '—')}/100",
        f"- ARV konservatif: {idr(market.get('conservative_exit'))}", f"- ARV dasar: {idr(market.get('base_exit'))}",
        f"- ARV optimistis: {idr(market.get('optimistic_exit'))}", "",
    ]
    comparables = _as_rows(market.get("valid") or snapshot.get("comparables"))
    if comparables:
        lines += ["### Daftar Pembanding", "| Listing | Harga | LT/LB (m²) | Alamat lengkap | Sumber |", "|---|---:|---:|---|---|"]
        for comp in comparables[:20]:
            address = comp.get("address") or comp.get("full_address") or comp.get("location") or "Alamat tidak dicantumkan"
            lines.append(f"| {comp.get('name') or 'Pembanding'} | {idr(comp.get('price'))} | {comp.get('land_area', '—')}/{comp.get('building_area', '—')} | {address} | {comp.get('source_platforms') or comp.get('source_url') or '—'} |")
        lines.append("")

    lines += ["## 4. Struktur Modal per Skenario Bid", "| Skenario | Harga bid / indikatif | Modal sebelum penjualan | Cadangan risiko | Total kebutuhan kas | Status bid |", "|---|---:|---:|---:|---:|---|"]
    for sc in scenarios:
        r = sc["result"]
        reserve = to_float(r.get("possession_risk_reserve")) + to_float(r.get("general_risk_reserve"))
        lines.append(f"| {sc['name']} | {idr(sc['bid']) if sc['bid'] else 'Tidak tersedia'} | {idr(r.get('capital_before_sale')) if r else '—'} | {idr(reserve) if r else '—'} | {idr(r.get('cash_requirement_including_reserve')) if r else '—'} | {'Bid dapat digunakan' if sc['legal_bid'] else 'Simulasi / belum ada bid legal'} |")
    lines += ["", "## 5. Biaya Penjualan dan Profitabilitas", "| Skenario | Biaya penjualan | Penjualan bersih | Profit bersih | ROI |", "|---|---:|---:|---:|---:|"]
    for sc in scenarios:
        r = sc["result"]
        lines.append(f"| {sc['name']} | {idr(r.get('selling_cost')) if r else '—'} | {idr(r.get('net_proceeds')) if r else '—'} | {idr(r.get('net_profit')) if r else '—'} | {pct(r.get('roi_pct')) if r else '—'} |")
    lines += ["", "## 6. Strategi Penawaran", "| Level | Nilai bid / ceiling | Target ROI | ROI hasil simulasi | Catatan |", "|---|---:|---:|---:|---|"]
    for sc in scenarios:
        r = sc["result"]
        target = f"{_scenario_target_roi(snapshot, sc['name']):.1f}%"
        lines.append(f"| {sc['name']} | {idr(sc['bid']) if sc['bid'] else '—'} | {target} | {pct(r.get('roi_pct')) if r else '—'} | {sc['note']} |")
    walk = bid.get("walk_away_from")
    lines.append(f"| Walk-away | {idr(walk) if walk is not None else '—'} | — | — | {bid.get('walk_away_reason', '—')} |")

    lines += ["", "## 7. RAB Ringkas dan Durasi per Pekerjaan"]
    lines += ["| Kelompok | Pekerjaan | Volume | Harga satuan | Subtotal dasar | Waktu cepat/dasar/lambat (hari kerja) |", "|---|---|---:|---:|---:|---:|"]
    for row in rab_rows[:80]:
        sub = rab_row_subtotals(row); duration = estimate_item_duration(row)
        lines.append(f"| {row.get('subcategory') or row.get('category') or '—'} | {row.get('work_item') or '—'} | {row.get('quantity') or '—'} {row.get('unit') or ''} | {idr(row.get('unit_cost')) if to_float(row.get('unit_cost')) > 0 else 'Belum tersedia'} | {idr(sub['subtotal_base']) if sub['subtotal_base'] is not None else 'Belum tersedia'} | {duration['fast']:.1f}/{duration['base']:.1f}/{duration['slow']:.1f} |")
    total = _sum_rab(rab_rows)
    base_total = idr(total['totals']['base']) if total['totals']['base'] is not None else "Belum tersedia"
    if not total["complete_base"]:
        base_total += f" (parsial {total['priced']['base']}/{total['count']} item)"
    lines.append(f"| **TOTAL RAB DASAR** |  |  |  | **{base_total}** | Durasi total dihitung terpisah (critical path) |")
    lines.append(f"Rentang RAB screening: rendah {idr(total['totals']['low']) if total['totals']['low'] is not None else '—'}; dasar {base_total}; atas {idr(total['totals']['high']) if total['totals']['high'] is not None else '—'}. Harga yang belum terisi tidak dianggap nol.")
    schedule = estimate_renovation_duration(rab_rows) if rab_rows else {"available": False}
    if schedule.get("available"):
        lines.append(f"Durasi total critical path: cepat {schedule['calendar_days']['fast']} hari kalender; dasar {schedule['calendar_days']['base']} hari; konservatif {schedule['calendar_days']['slow']} hari.")
    else:
        lines.append("Durasi total belum dapat dihitung karena volume pekerjaan belum tersedia.")

    lines += ["", "## 8. Risk Register: Risiko dan Mitigasi"]
    risks = _as_rows(snapshot.get("risk_register"))
    if risks:
        lines += ["| Risiko | Probabilitas/Dampak | Cadangan | Mitigasi |", "|---|---:|---:|---|"]
        for risk in risks[:40]:
            lines.append(f"| {risk.get('risk_description') or '—'} | {risk.get('probability_1_5', '—')}/{risk.get('impact_1_5', '—')} | {idr(risk.get('cost_reserve'))} | {risk.get('mitigation') or '—'} |")
    else:
        lines.append("Tidak ada risiko yang dicatat pada snapshot.")
    lines += ["", "## 9. Blocker dan Peringatan"]
    lines += [f"- **Blocker:** {x}" for x in decision.get("blockers", [])] or ["- Tidak ada blocker utama yang tercatat."]
    lines += [f"- **Peringatan:** {x}" for x in decision.get("warnings", [])] or ["- Tidak ada peringatan tambahan."]

    _append_portfolio_markdown(lines, snapshot.get("portfolio_context"))
    lines += ["", "## Pengelola Investasi dan Proyek", f"{BRAND} | {BRAND_DESCRIPTOR}.", "", "## Batasan", "Dokumen ini merupakan memorandum investasi dan alat bantu underwriting, bukan appraisal resmi, pendapat hukum, jaminan hasil investasi, atau quotation kontraktor. Harga penawaran bukan harga transaksi kecuali terverifikasi. Kondisi fisik, dokumen, jadwal, dan seluruh asumsi harus diperiksa sebelum keputusan investasi."]
    return "\n".join(lines)


def _append_portfolio_markdown(lines: list[str], portfolio: Any) -> None:
    if not isinstance(portfolio, dict):
        return
    active = _as_rows(portfolio.get("active_projects")); completed = _as_rows(portfolio.get("completed_projects"))
    if not active and not completed:
        return
    lines += ["", "## 9. Portofolio dan Rekam Jejak Kayna Property"]
    if portfolio.get("as_of"):
        lines.append(f"Posisi data per {_fmt_wib(portfolio.get('as_of'))}. Angka mencerminkan data yang telah dicatat di sistem.")
    if active:
        lines += ["### Proyek Aktif", "| Proyek / Lokasi | Tahap | Progres milestone | Aktual dibayar | Komitmen + forecast | Budget proyek | Target jual |", "|---|---|---:|---:|---:|---:|---|"]
        for item in active[:25]:
            progress = f"{item.get('progress_pct'):.0f}%" if item.get("progress_pct") is not None else "Belum dicatat"
            lines.append(f"| {item.get('name')} / {item.get('address')} | {item.get('stage')} | {progress} | {idr(item.get('actual_paid'))} | {idr(to_float(item.get('committed')) + to_float(item.get('forecast')))} | {idr(item.get('budget_total')) if item.get('budget_total') else 'Belum disusun'} | {item.get('target_sale_date') or '—'} |")
    if completed:
        lines += ["", "### Proyek Selesai dan Hasil Aktual", "| Proyek / Lokasi | Closing | ARV dasar → closing | Budget vs modal aktual | Biaya penjualan | Profit / ROI aktual |", "|---|---|---:|---:|---:|---:|"]
        for item in completed[:25]:
            arv_compare = idr(item.get("base_arv"))
            if item.get("closing_vs_base_arv_pct") is not None:
                arv_compare += f" ({item['closing_vs_base_arv_pct']:+.1f}%)"
            budget_compare = f"{idr(item.get('budget_project_total'))} / {idr(item.get('total_actual_cost'))}"
            if item.get("budget_variance_actual") is not None:
                budget_compare += f" (sisa/lebih {idr(item['budget_variance_actual'])})"
            lines.append(f"| {item.get('name')} / {item.get('address')} | {item.get('sold_date') or '—'} · {idr(item.get('closing_price'))} | {arv_compare} | {budget_compare} | {idr(item.get('selling_cost_actual'))} | {idr(item.get('net_profit_actual'))} / {pct(item.get('roi_actual_pct'))} |")


def _portfolio_sections(doc: Any, portfolio: Any, add_table: Any) -> None:
    if not isinstance(portfolio, dict):
        return
    active = _as_rows(portfolio.get("active_projects")); completed = _as_rows(portfolio.get("completed_projects"))
    if not active and not completed:
        return
    doc.add_heading("9. Portofolio dan Rekam Jejak Kayna Property", level=1)
    if portfolio.get("as_of"):
        doc.add_paragraph(f"Posisi data per {_fmt_wib(portfolio.get('as_of'))}. Angka mencerminkan data yang telah dicatat di sistem.")
    if active:
        doc.add_heading("Proyek Aktif", level=2)
        rows = []
        for item in active[:25]:
            progress = f"{item.get('progress_pct'):.0f}%" if item.get("progress_pct") is not None else "Belum dicatat"
            rows.append([
                f"{item.get('name') or 'Properti'}\n{item.get('address') or '—'}",
                f"{item.get('stage') or '—'}\nProgres: {progress}",
                idr(item.get("actual_paid")),
                idr(to_float(item.get("committed")) + to_float(item.get("forecast"))),
                idr(item.get("budget_total")) if item.get("budget_total") else "Belum disusun",
                item.get("target_sale_date") or "—",
            ])
        add_table(["Proyek / Lokasi", "Tahap / Progres", "Aktual", "Komitmen + forecast", "Budget", "Target jual"], rows, widths=[1.8, 1.15, .85, 1.05, .9, .8])
    if completed:
        doc.add_heading("Proyek Selesai dan Hasil Aktual", level=2)
        rows = []
        for item in completed[:25]:
            arv_text = idr(item.get("base_arv"))
            if item.get("closing_vs_base_arv_pct") is not None:
                arv_text += f"\nClosing {item['closing_vs_base_arv_pct']:+.1f}% vs ARV"
            budget_text = f"Budget {idr(item.get('budget_project_total'))}\nAktual {idr(item.get('total_actual_cost'))}"
            if item.get("budget_variance_actual") is not None:
                budget_text += f"\nVarians {idr(item['budget_variance_actual'])}"
            rows.append([
                f"{item.get('name') or 'Properti'}\n{item.get('address') or '—'}",
                f"{item.get('sold_date') or '—'}\n{idr(item.get('closing_price'))}",
                arv_text, budget_text, idr(item.get("selling_cost_actual")),
                f"{idr(item.get('net_profit_actual'))}\nROI {pct(item.get('roi_actual_pct'))}",
            ])
        add_table(["Proyek / Lokasi", "Closing / Harga", "ARV dasar vs closing", "Budget vs aktual", "Biaya jual", "Profit / ROI aktual"], rows, widths=[1.65, .95, 1.05, 1.25, .85, 1.0])


def build_analysis_docx(snapshot: dict[str, Any]) -> bytes:
    """Create a polished Indonesian property investment memorandum; text >=11 pt."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except Exception as exc:
        raise RuntimeError("Library python-docx belum tersedia. Tambahkan python-docx pada requirements.txt.") from exc

    p = _property(snapshot)
    market = snapshot.get("market", {}) if isinstance(snapshot.get("market"), dict) else {}
    bid = snapshot.get("bidding", {}) if isinstance(snapshot.get("bidding"), dict) else {}
    decision = snapshot.get("decision", {}) if isinstance(snapshot.get("decision"), dict) else {}
    costs = snapshot.get("costs", {}) if isinstance(snapshot.get("costs"), dict) else {}
    rab_rows = _as_rows(costs.get("renovation_items"))
    scenarios = _scenario_rows(snapshot)

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(.55); sec.bottom_margin = Inches(.55); sec.left_margin = Inches(.62); sec.right_margin = Inches(.62)
    styles = doc.styles
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        styles[name].font.name = "Aptos"
        styles[name].font.color.rgb = RGBColor.from_string(NAVY)
        styles[name].font.size = Pt(11 if name == "Normal" else (21 if name == "Title" else (14 if name.startswith("Heading") else 11)))
    styles["Normal"].paragraph_format.space_after = Pt(4)

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    h = header.add_run(f"{BRAND}  |  {BRAND_DESCRIPTOR}")
    h.bold = True; h.font.name = "Aptos"; h.font.size = Pt(11); h.font.color.rgb = RGBColor.from_string(NAVY)
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    f = footer.add_run(f"{BRAND}  •  Memorandum Investasi Properti  •  {_fmt_wib(snapshot.get('analyzed_at'))}")
    f.font.name = "Aptos"; f.font.size = Pt(11); f.font.color.rgb = RGBColor.from_string(NAVY)

    def shade(cell: Any, fill: str) -> None:
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = tc_pr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd"); tc_pr.append(shd)
        shd.set(qn("w:fill"), fill)

    def add_table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None, *, total_last: bool = False):
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"; table.alignment = WD_TABLE_ALIGNMENT.CENTER; table.autofit = False
        for idx, label in enumerate(headers):
            cell = table.rows[0].cells[idx]; cell.text = str(label); shade(cell, NAVY)
        for row in rows:
            cells = table.add_row().cells
            for idx, value in enumerate(row):
                if idx < len(cells): cells[idx].text = "—" if value is None or value == "" else str(value)
        header_props = table.rows[0]._tr.get_or_add_trPr()
        repeat = OxmlElement("w:tblHeader"); repeat.set(qn("w:val"), "true"); header_props.append(repeat)
        for ridx, row in enumerate(table.rows):
            tr_props = row._tr.get_or_add_trPr(); cant = OxmlElement("w:cantSplit"); tr_props.append(cant)
            for idx, cell in enumerate(row.cells):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if widths and idx < len(widths): cell.width = Inches(widths[idx])
                if ridx == 0:
                    shade(cell, NAVY)
                elif ridx % 2 == 0:
                    shade(cell, "F3F6FA")
                if total_last and ridx == len(table.rows) - 1:
                    shade(cell, "E8EEF5")
                for para in cell.paragraphs:
                    para.paragraph_format.space_after = Pt(1)
                    para.paragraph_format.keep_together = True
                    for run in para.runs:
                        run.font.name = "Aptos"; run.font.size = Pt(11)
                        run.font.color.rgb = RGBColor.from_string("FFFFFF" if ridx == 0 else NAVY)
                        if ridx == 0 or (total_last and ridx == len(table.rows) - 1): run.bold = True
        doc.add_paragraph().paragraph_format.space_after = Pt(1)
        return table

    title = doc.add_paragraph(style="Title")
    title.paragraph_format.space_after = Pt(1)
    title_run = title.add_run(DOCUMENT_TITLE); title_run.bold = True; title_run.font.color.rgb = RGBColor.from_string(NAVY)
    subtitle = doc.add_paragraph()
    sr = subtitle.add_run(str(p.get("name") or p.get("lot_code") or "Properti Lelang")); sr.bold = True; sr.font.size = Pt(15); sr.font.color.rgb = RGBColor.from_string(TEAL)
    meta = doc.add_paragraph(f"Tanggal analisis: {_fmt_wib(snapshot.get('analyzed_at'))}  |  Property ID: {snapshot.get('property_id', '—')}")
    meta.paragraph_format.space_after = Pt(6)

    doc.add_heading("Ringkasan Eksekutif", level=1)
    doc.add_paragraph(str(decision.get("summary") or "Analisis investasi berdasarkan data dan asumsi yang tersedia."))
    decision_table = doc.add_table(rows=1, cols=2); decision_table.style = "Table Grid"
    decision_table.cell(0, 0).text = "KEPUTUSAN UNDERWRITING"
    decision_table.cell(0, 1).text = str(decision.get("status", "HOLD"))
    for cell in decision_table.rows[0].cells:
        shade(cell, "E8EEF5")
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True; run.font.size = Pt(11); run.font.color.rgb = RGBColor.from_string(NAVY)

    doc.add_heading("1. Identitas dan Jadwal Lelang", level=1)
    add_table(["Parameter", "Data"], [
        ["Nama objek", p.get("name")], ["Kode lot", p.get("lot_code")], ["Alamat lengkap", p.get("address")],
        ["KPKNL", p.get("auction_office")], ["Tanggal lelang", p.get("auction_date")],
        ["Batas setor jaminan", p.get("deposit_deadline")], ["Batas pelunasan", p.get("payment_deadline")],
        ["Nilai limit", idr(p.get("auction_limit"))], ["LT / LB", f"{p.get('land_area', '—')} / {p.get('building_area', '—')} m²"],
        ["Sertifikat", p.get("certificate_type")],
    ], widths=[2.0, 4.8])

    doc.add_heading("2. Penilaian Pasar dan Skenario Exit", level=1)
    add_table(["Indikator", "Nilai"], [
        ["Pembanding valid", market.get("valid_count", 0)], ["Indeks kualitas data", f"{market.get('confidence', '—')}/100"],
        ["ARV konservatif", idr(market.get("conservative_exit"))], ["ARV dasar", idr(market.get("base_exit"))], ["ARV optimistis", idr(market.get("optimistic_exit"))],
    ], widths=[3.4, 3.4])
    comparables = _as_rows(market.get("valid") or snapshot.get("comparables"))
    if comparables:
        doc.add_heading("Daftar Pembanding", level=2)
        comp_rows = []
        for comp in comparables[:20]:
            address = str(comp.get("address") or comp.get("full_address") or comp.get("location") or "Alamat lengkap belum dicantumkan")
            source = str(comp.get("source_platforms") or comp.get("source_url") or "—")
            comp_rows.append([
                str(comp.get("name") or "Pembanding"), idr(comp.get("price")),
                f"{comp.get('land_area') or '—'} / {comp.get('building_area') or '—'}",
                f"{address}\nSumber: {source}",
            ])
        add_table(["Nama listing", "Harga penawaran", "LT / LB (m²)", "Alamat dan sumber"], comp_rows, widths=[1.55, 1.15, 1.0, 3.1])

    doc.add_heading("3. Struktur Modal per Skenario Bidding", level=1)
    capital_rows = []
    for sc in scenarios:
        r = sc["result"]
        reserve = to_float(r.get("possession_risk_reserve")) + to_float(r.get("general_risk_reserve"))
        capital_rows.append([
            sc["name"], idr(sc["bid"]) if sc["bid"] else "Tidak tersedia",
            idr(r.get("capital_before_sale")) if r else "—",
            idr(r.get("possession_risk_reserve")) if r else "—",
            idr(r.get("general_risk_reserve")) if r else "—",
            idr(r.get("cash_requirement_including_reserve")) if r else "—",
        ])
    add_table(["Skenario", "Harga bid / indikatif", "Total modal", "Cadangan penguasaan", "Cadangan risiko lain", "Total kebutuhan kas"], capital_rows, widths=[1.05, 1.05, 1.1, 1.15, 1.1, 1.2])

    doc.add_heading("4. Biaya Penjualan dan Profitabilitas", level=1)
    sale_rows = []
    for sc in scenarios:
        r = sc["result"]
        sale_rows.append([
            sc["name"], idr(r.get("selling_cost")) if r else "—",
            idr(r.get("net_proceeds")) if r else "—", idr(r.get("net_profit")) if r else "—",
            pct(r.get("roi_pct")) if r else "—",
        ])
    add_table(["Skenario", "Biaya penjualan", "Penjualan bersih", "Profit bersih", "ROI"], sale_rows, widths=[1.3, 1.25, 1.35, 1.35, .9])

    doc.add_heading("5. Strategi Penawaran", level=1)
    strategy_rows = []
    for sc in scenarios:
        r = sc["result"]
        target_roi = f"{_scenario_target_roi(snapshot, sc['name']):.1f}%"
        strategy_rows.append([
            sc["name"], idr(sc["bid"]) if sc["bid"] else "—", target_roi,
            pct(r.get("roi_pct")) if r else "—", "Bid legal" if sc["legal_bid"] else sc["note"],
        ])
    strategy_rows.append(["Batas berhenti (walk-away)", idr(bid.get("walk_away_from")) if bid.get("walk_away_from") is not None else "—", "—", "—", bid.get("walk_away_reason") or "—"])
    add_table(["Level", "Harga bid", "Target ROI", "ROI simulasi", "Catatan"], strategy_rows, widths=[1.2, 1.0, .8, .8, 2.4])

    doc.add_heading("6. RAB Ringkas", level=1)
    rab_table_rows = []
    for row in rab_rows[:80]:
        subtotal = rab_row_subtotals(row)
        duration = estimate_item_duration(row)
        time_label = f"{duration['fast']:.1f} / {duration['base']:.1f} / {duration['slow']:.1f}"
        rab_table_rows.append([
            str(row.get("subcategory") or row.get("category") or "—"), str(row.get("work_item") or "—"),
            f"{row.get('quantity') or '—'} {row.get('unit') or ''}".strip(),
            idr(row.get("unit_cost")) if to_float(row.get("unit_cost")) > 0 else "Belum ada harga",
            idr(subtotal.get("subtotal_base")) if subtotal.get("subtotal_base") is not None else "Belum lengkap",
            time_label,
        ])
    total = _sum_rab(rab_rows)
    total_base = idr(total["totals"]["base"]) if total["totals"]["base"] is not None else "Belum tersedia"
    if not total["complete_base"]:
        total_base += f" (parsial {total['priced']['base']}/{total['count']} item)"
    rab_table_rows.append(["TOTAL", "Total RAB dasar", "", "", total_base, "Critical path di bawah"])
    if rab_table_rows:
        add_table(["Kelompok", "Pekerjaan", "Volume", "Harga satuan", "Subtotal dasar", "Waktu cepat/dasar/lambat*"], rab_table_rows, widths=[.85, 2.0, .65, .9, 1.0, 1.1], total_last=True)
        low = idr(total["totals"]["low"]) if total["totals"]["low"] is not None else "Belum tersedia"
        high = idr(total["totals"]["high"]) if total["totals"]["high"] is not None else "Belum tersedia"
        doc.add_paragraph(f"Rentang total RAB screening: rendah {low}; dasar {total_base}; atas {high}. Item tanpa harga tetap terlihat dan tidak dianggap Rp0.")
    else:
        doc.add_paragraph("Rincian item RAB tidak tersedia pada snapshot memo ini.")

    schedule = estimate_renovation_duration(rab_rows) if rab_rows else {"available": False}
    doc.add_heading("7. Estimasi Waktu Renovasi", level=1)
    if schedule.get("available"):
        doc.add_paragraph(f"Estimasi durasi total berdasarkan critical path: cepat {schedule['calendar_days']['fast']} hari kalender; dasar {schedule['calendar_days']['base']} hari; konservatif {schedule['calendar_days']['slow']} hari. Asumsi {schedule['working_days_per_week']} hari kerja per minggu dan buffer {schedule['buffer_pct']:.0f}%.")
        add_table(["Tahap", "Cepat (hari kerja)", "Dasar (hari kerja)", "Konservatif (hari kerja)"], [[x["phase"], round(x["fast_days"], 1), round(x["base_days"], 1), round(x["slow_days"], 1)] for x in schedule.get("phases", [])], widths=[3.0, 1.2, 1.2, 1.4])
        doc.add_paragraph("*Durasi per item pada RAB adalah estimasi effort satu regu kecil. Pekerjaan yang berbeda dalam satu fase dapat berlangsung paralel; karena itu jumlah hari per item tidak dijumlahkan langsung. Durasi total menggunakan estimasi critical path yang sama dengan menu Estimasi Waktu Renovasi.")
    else:
        doc.add_paragraph("Durasi belum dapat dihitung karena volume pekerjaan belum tersedia.")

    doc.add_heading("8. Risiko dan Mitigasi", level=1)
    for label, values in (("Blocker", decision.get("blockers", [])), ("Peringatan", decision.get("warnings", []))):
        doc.add_heading(label, level=2)
        if values:
            for value in values: doc.add_paragraph(str(value), style="List Bullet")
        else: doc.add_paragraph("Tidak ada catatan.")
    risk_items = _as_rows(snapshot.get("risk_register"))
    if risk_items:
        add_table(["Risiko", "Probabilitas / Dampak", "Cadangan", "Mitigasi"], [[str(r.get("risk_description") or "Risiko"), f"{r.get('probability_1_5', '—')} / {r.get('impact_1_5', '—')}", idr(r.get("cost_reserve")), str(r.get("mitigation") or "—")] for r in risk_items[:20]], widths=[2.05, 1.0, 1.15, 2.6])

    _portfolio_sections(doc, snapshot.get("portfolio_context"), add_table)
    doc.add_heading("Pengelola Investasi dan Proyek", level=1)
    doc.add_paragraph(f"{BRAND} menjalankan fungsi property investment dan project management: analisis peluang, perencanaan akuisisi, pengendalian anggaran, koordinasi renovasi, serta persiapan pemasaran aset. Ruang lingkup pelaksanaan mengikuti persetujuan dan perjanjian proyek masing-masing.")
    doc.add_heading("Batasan dan Penafian", level=1)
    doc.add_paragraph("Memorandum ini merupakan ringkasan analisis investasi berdasarkan data yang tersedia. Dokumen ini bukan appraisal resmi, pendapat hukum, jaminan keuntungan, atau penawaran kontraktor. Harga penawaran tidak sama dengan harga transaksi kecuali terverifikasi. Data portofolio hanya mencakup catatan yang tersedia di sistem dan perlu direkonsiliasi sebelum dibagikan kepada investor.")

    # Enforce a minimum 11pt font across all visible document content.
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if run.font.size is None or run.font.size.pt < 11:
                run.font.size = Pt(11)
            if run.font.color.rgb is None:
                run.font.color.rgb = RGBColor.from_string(NAVY)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if run.font.size is None or run.font.size.pt < 11:
                            run.font.size = Pt(11)
                        if run.font.color.rgb is None:
                            run.font.color.rgb = RGBColor.from_string(NAVY)
    out = BytesIO(); doc.save(out); return out.getvalue()


# Backward-compatible API aliases retained for existing integrations.
def investment_memo_filename(snapshot: dict[str, Any], extension: str = "docx") -> str:
    return property_filename(snapshot, extension)


def build_investment_memo_docx(snapshot: dict[str, Any]) -> bytes:
    return build_analysis_docx(snapshot)
