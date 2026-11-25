from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import re
from typing import Any
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from core.utils import idr, pct, to_float
from core.renovation_engine import rab_item_is_in_scope, rab_row_subtotals, summarize_rab_scope_totals
from core.renovation_schedule import estimate_item_duration, estimate_renovation_duration

BRAND = "KAYNA PROPERTY"
BRAND_DESCRIPTOR = "PROPERTY INVESTMENT & PROJECT MANAGEMENT"
DOCUMENT_TITLE = "PROPOSAL INVESTASI PROPERTI"
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


def _fmt_short_date(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        dt = datetime.fromisoformat(raw[:10])
        months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    except (ValueError, TypeError):
        return raw or "—"


def _as_rows(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def property_filename(snapshot: dict[str, Any], extension: str = "docx") -> str:
    p = _property(snapshot)
    raw = " ".join(str(x or "") for x in (p.get("name"), p.get("lot_code"), snapshot.get("property_id")))
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "properti"
    slug = slug[:90].strip("-")
    return f"proposal-investasi-properti-{slug}.{extension.lstrip('.')}"




def _rp_juta(value: Any) -> str:
    """Compact Rupiah value in millions; table heading declares the unit."""
    if value in (None, ""):
        return "—"
    amount = to_float(value) / 1_000_000.0
    return f"{amount:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _idr_plain(value: Any) -> str:
    """Exact integer Rupiah without a prefix; table headings carry the currency."""
    if value in (None, ""):
        return "—"
    return f"{to_float(value):,.0f}".replace(",", ".")


def _source_label(comp: dict[str, Any]) -> str:
    """Keep comparable source cells compact while retaining a useful source identifier."""
    url = str(comp.get("source_url") or "").strip()
    if url:
        parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
        host = parsed.netloc.removeprefix("www.")
        if host:
            return host
    platforms = comp.get("source_platforms") or comp.get("source") or "Sumber tidak dicantumkan"
    if isinstance(platforms, list):
        platforms = ", ".join(str(x) for x in platforms if x)
    return str(platforms)[:60]

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


CAPITAL_COMPONENTS = [
    ("Harga bid / nilai limit", "bid_price"),
    ("Bea lelang pembeli", "buyer_auction_fee"),
    ("BPHTB", "bphtb"),
    ("PNBP BPN", "bpn_pnbp_cost"),
    ("Roya", "roya_cost"),
    ("Administrasi akuisisi", "other_acquisition_admin"),
    ("Biaya legal lain", "other_legal_cost"),
    ("PPAT / notaris akuisisi", "acquisition_notary_ppat_fee"),
    ("Biaya penguasaan / kerohiman", "possession_cost"),
    ("RAB renovasi", "renovation_cost"),
    ("Contingency renovasi", "renovation_contingency"),
    ("Cadangan kondisi tersembunyi", "hidden_condition_reserve"),
    ("Biaya holding", "holding_cost"),
    ("Marketing / persiapan penjualan", "marketing_cost"),
    ("Biaya lain pra-penjualan", "other_presale_cost_only"),
    ("TOTAL MODAL PRA-PENJUALAN", "capital_before_sale"),
]


def _scenario_header(scenario: dict[str, Any]) -> str:
    label = {"Bid pada Limit": "Limit", "Skenario Tengah": "Tengah", "Skenario Atas": "Atas"}.get(scenario.get("name"), str(scenario.get("name") or "Bid"))
    amount = _rp_juta(scenario.get("bid")) if scenario.get("bid") else "—"
    return f"{label} · {amount}"


def _scenario_money(result: dict[str, Any], key: str) -> str:
    value = result.get(key) if isinstance(result, dict) else None
    return _rp_juta(value) if value not in (None, "") else "—"


def _capital_matrix(scenarios: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for label, key in CAPITAL_COMPONENTS:
        rows.append([label] + [_scenario_money(sc.get("result") or {}, key) for sc in scenarios])
    return rows


def _cash_matrix(snapshot: dict[str, Any], scenarios: list[dict[str, Any]]) -> list[list[str]]:
    liquidity = snapshot.get("liquidity") if isinstance(snapshot.get("liquidity"), dict) else {}
    available = to_float(liquidity.get("cash_available_for_new_project"))
    rows: list[list[str]] = []
    components = [
        ("Modal pra-penjualan", "capital_before_sale"),
        ("Cadangan penguasaan", "possession_risk_reserve"),
        ("Cadangan risiko umum", "general_risk_reserve"),
        ("TOTAL KEBUTUHAN KAS", "cash_requirement_including_reserve"),
    ]
    for label, key in components:
        rows.append([label] + [_scenario_money(sc.get("result") or {}, key) for sc in scenarios])
    if liquidity.get("cash_available_for_new_project") not in (None, ""):
        rows.append(["Kas tersedia"] + [_rp_juta(available)] * len(scenarios))
        balances = []
        for sc in scenarios:
            result = sc.get("result") or {}
            need = result.get("cash_requirement_including_reserve")
            balances.append(_rp_juta(available - to_float(need)) if need not in (None, "") else "—")
        rows.append(["SURPLUS / (KURANG) KAS"] + balances)
    deposit = _property(snapshot).get("deposit_amount")
    if deposit not in (None, ""):
        rows.append(["Uang jaminan (kebutuhan awal)"] + [_rp_juta(deposit)] * len(scenarios))
    return rows


def _sales_matrix(scenarios: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    components = [
        ("Estimasi harga penjualan / exit price", "exit_price"),
        ("PPh final penjual", "seller_final_tax"),
        ("Komisi agen", "seller_agent"),
        ("AJB / PPAT penjual", "seller_ajb_ppat"),
        ("Biaya penjualan lain", "seller_misc"),
        ("TOTAL BIAYA PENJUALAN", "selling_cost"),
        ("PENJUALAN BERSIH setelah biaya penjualan", "net_proceeds"),
        ("Total modal sebelum biaya penjualan", "capital_before_sale"),
        ("PROFIT BERSIH PROYEK", "net_profit"),
    ]
    for label, key in components:
        rows.append([label] + [_scenario_money(sc.get("result") or {}, key) for sc in scenarios])
    rows.append(["ROI PROYEK"] + [pct((sc.get("result") or {}).get("roi_pct")) for sc in scenarios])
    return rows


def _matrix_markdown(title: str, scenarios: list[dict[str, Any]], rows: list[list[str]]) -> list[str]:
    headers = ["Komponen"] + [_scenario_header(sc) for sc in scenarios]
    separator = ["---"] + ["---:"] * len(scenarios)
    output = [f"## {title}", "| " + " | ".join(headers) + " |", "|" + "|".join(separator) + "|"]
    output.extend("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
    return output


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
        lines += ["### Daftar Pembanding", "| Alamat lengkap | Harga penawaran | LT/LB (m²) | URL / sumber |", "|---|---:|---:|---|"]
        for comp in comparables[:20]:
            address = comp.get("address") or comp.get("full_address") or comp.get("location") or comp.get("name") or "Alamat tidak dicantumkan"
            source = _source_label(comp)
            lines.append(f"| {address} | {idr(comp.get('price'))} | {comp.get('land_area', '—')}/{comp.get('building_area', '—')} | {source} |")
        lines.append("")

    lines += [""]
    lines += _matrix_markdown("4. Rincian Total Modal per Level Bidding", scenarios, _capital_matrix(scenarios))
    lines += ["", "Nilai modal merinci biaya dari harga bid hingga tahap pra-penjualan. Biaya penjualan belum dimasukkan ke total modal pra-penjualan.", ""]
    lines += _matrix_markdown("5. Kebutuhan Kas dan Cadangan Risiko", scenarios, _cash_matrix(snapshot, scenarios))
    lines += ["", "Cadangan risiko merupakan kebutuhan likuiditas dan tidak otomatis menjadi biaya aktual. Uang jaminan adalah kebutuhan kas di muka dan tidak ditambahkan lagi ke total modal karena diperhitungkan dalam pelunasan harga lelang.", ""]
    lines += _matrix_markdown("6. Biaya Penjualan dan Hasil Bersih", scenarios, _sales_matrix(scenarios))
    lines += ["", "Nilai Penjualan bersih adalah estimasi harga penjualan setelah dikurangi biaya penjualan; profit bersih masih mengurangi total modal pra-penjualan.", ""]
    lines += ["## 7. Strategi Penawaran", "| Bid / ceiling (Rp juta) | Target ROI | ROI hasil simulasi | Catatan |", "|---:|---:|---:|---|"]
    for sc in scenarios:
        r = sc["result"]
        target = f"{_scenario_target_roi(snapshot, sc['name']):.1f}%"
        lines.append(f"| {_rp_juta(sc['bid']) if sc['bid'] else '—'} | {target} | {pct(r.get('roi_pct')) if r else '—'} | {sc['name']}: {sc['note']} |")
    walk = bid.get("walk_away_from")
    lines.append(f"| {_rp_juta(walk) if walk is not None else '—'} | — | — | Batas berhenti: {bid.get('walk_away_reason', '—')} |")

    lines += ["", "## 8. RAB Ringkas dan Durasi per Pekerjaan"]
    lines += ["| Kelompok | Pekerjaan | Volume | Harga satuan | Subtotal dasar | Durasi C/D/K (hari kerja) |", "|---|---|---:|---:|---:|---:|"]
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

    lines += ["", "## 9. Risk Register: Risiko dan Mitigasi"]
    risks = _as_rows(snapshot.get("risk_register"))
    if risks:
        lines += ["| Risiko | Probabilitas/Dampak | Cadangan | Mitigasi |", "|---|---:|---:|---|"]
        for risk in risks[:40]:
            lines.append(f"| {risk.get('risk_description') or '—'} | {risk.get('probability_1_5', '—')}/{risk.get('impact_1_5', '—')} | {idr(risk.get('cost_reserve'))} | {risk.get('mitigation') or '—'} |")
    else:
        lines.append("Tidak ada risiko yang dicatat pada snapshot.")
    lines += ["", "## 10. Blocker dan Peringatan"]
    lines += [f"- **Blocker:** {x}" for x in decision.get("blockers", [])] or ["- Tidak ada blocker utama yang tercatat."]
    lines += [f"- **Peringatan:** {x}" for x in decision.get("warnings", [])] or ["- Tidak ada peringatan tambahan."]

    _append_portfolio_markdown(lines, snapshot.get("portfolio_context"))
    lines += ["", "## Pengelola Investasi dan Proyek", f"{BRAND} | {BRAND_DESCRIPTOR}.", "", "## Batasan", "Dokumen ini merupakan proposal investasi dan alat bantu underwriting, bukan appraisal resmi, pendapat hukum, jaminan hasil investasi, atau quotation kontraktor. Harga penawaran bukan harga transaksi kecuali terverifikasi. Kondisi fisik, dokumen, jadwal, dan seluruh asumsi harus diperiksa sebelum keputusan investasi."]
    return "\n".join(lines)


def _append_portfolio_markdown(lines: list[str], portfolio: Any) -> None:
    if not isinstance(portfolio, dict):
        return
    active = _as_rows(portfolio.get("active_projects")); completed = _as_rows(portfolio.get("completed_projects"))
    if not active and not completed:
        return
    lines += ["", "## 11. Portofolio dan Rekam Jejak Kayna Property"]
    if portfolio.get("as_of"):
        lines.append(f"Posisi data per {_fmt_wib(portfolio.get('as_of'))}. Angka mencerminkan data yang telah dicatat di sistem.")
    if active:
        lines += ["### Proyek Aktif", "| Proyek / Lokasi | Tahap | Progres milestone | Aktual dibayar | Komitmen + forecast | Budget proyek | Target jual |", "|---|---|---:|---:|---:|---:|---|"]
        for item in active[:25]:
            progress = f"{item.get('progress_pct'):.0f}%" if item.get("progress_pct") is not None else "Belum diperbarui"
            if item.get("total_work_items"):
                progress += f" (data {item.get('tracked_work_items', 0)}/{item.get('total_work_items')} item)"
            lines.append(f"| {item.get('name')} / {item.get('address')} | {item.get('stage')} | {progress} | {idr(item.get('actual_paid'))} | {idr(to_float(item.get('committed')) + to_float(item.get('forecast')))} | {idr(item.get('budget_total')) if item.get('budget_total') else 'Belum disusun'} | {item.get('target_sale_date') or '—'} |")
    if completed:
        lines += ["", "### Proyek Selesai dan Hasil Aktual", "| Proyek / Lokasi | Closing | ARV dasar → closing | Budget vs modal aktual | Biaya penjualan | Profit / ROI aktual |", "|---|---|---:|---:|---:|---:|"]
        for item in completed[:25]:
            arv_compare = idr(item.get("base_arv"))
            if item.get("closing_vs_base_arv_pct") is not None:
                arv_compare += f" ({item['closing_vs_base_arv_pct']:+.1f}%)"
            if item.get("budget_project_total"):
                budget_compare = f"Budget {idr(item.get('budget_project_total'))} / modal aktual {idr(item.get('total_actual_cost'))}"
                if item.get("budget_variance_actual") is not None:
                    variance = to_float(item.get("budget_variance_actual"))
                    label = "sisa budget" if variance >= 0 else "over budget"
                    budget_compare += f" ({label} {idr(abs(variance))})"
            else:
                budget_compare = f"Budget belum disusun / modal aktual {idr(item.get('total_actual_cost'))}"
            lines.append(f"| {item.get('name')} / {item.get('address')} | {item.get('sold_date') or '—'} · {idr(item.get('closing_price'))} | {arv_compare} | {budget_compare} | {idr(item.get('selling_cost_actual'))} | {idr(item.get('net_profit_actual'))} / {pct(item.get('roi_actual_pct'))} |")


def _portfolio_sections(doc: Any, portfolio: Any, add_table: Any) -> None:
    if not isinstance(portfolio, dict):
        return
    active = _as_rows(portfolio.get("active_projects")); completed = _as_rows(portfolio.get("completed_projects"))
    if not active and not completed:
        return
    doc.add_heading("10. Portofolio dan Rekam Jejak Kayna Property", level=1)
    if portfolio.get("as_of"):
        doc.add_paragraph(f"Posisi data per {_fmt_wib(portfolio.get('as_of'))}. Angka mencerminkan data yang telah dicatat di sistem.")
    if active:
        doc.add_heading("Proyek Aktif", level=2)
        rows = []
        for item in active[:25]:
            progress = f"{item.get('progress_pct'):.0f}%" if item.get("progress_pct") is not None else "Belum diperbarui"
            if item.get("total_work_items"):
                progress += f"\nData {item.get('tracked_work_items', 0)}/{item.get('total_work_items')} item"
            rows.append([
                f"{item.get('name') or 'Properti'}\n{item.get('address') or '—'}",
                f"{item.get('stage') or '—'}\nProgres: {progress}",
                _rp_juta(item.get("actual_paid")),
                _rp_juta(to_float(item.get("committed")) + to_float(item.get("forecast"))),
                _rp_juta(item.get("budget_total")) if item.get("budget_total") else "Belum disusun",
                _fmt_short_date(item.get("target_sale_date")),
            ])
        add_table(["Proyek / Lokasi", "Tahap / Progres", "Aktual (Rp jt)", "Komitmen + forecast (Rp jt)", "Budget (Rp jt)", "Target jual"], rows, widths=[1.5, 1.0, .8, 1.0, .8, 1.15])
    if completed:
        # Keep active and completed portfolio tables together where possible;
        # Word will naturally continue onto the next page only when required.
        doc.add_heading("Proyek Selesai dan Hasil Aktual", level=2)
        rows = []
        for item in completed[:25]:
            arv_text = f"ARV {_rp_juta(item.get('base_arv'))}" if item.get("base_arv") else "ARV belum tersedia"
            if item.get("closing_vs_base_arv_pct") is not None:
                arv_text += f"\nVs ARV {item['closing_vs_base_arv_pct']:+.1f}%"
            if item.get("budget_project_total"):
                budget_text = f"Budget {_rp_juta(item.get('budget_project_total'))}\nModal aktual {_rp_juta(item.get('total_actual_cost'))}"
                if item.get("budget_variance_actual") is not None:
                    variance = to_float(item.get("budget_variance_actual"))
                    variance_label = "Sisa budget" if variance >= 0 else "Over budget"
                    budget_text += f"\n{variance_label} {abs(variance) / 1_000_000:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
            else:
                budget_text = f"Budget belum disusun\nModal aktual {_rp_juta(item.get('total_actual_cost'))}"
            rows.append([
                f"{item.get('name') or 'Properti'}\n{item.get('address') or '—'}",
                f"{_fmt_short_date(item.get('sold_date'))}\n{_rp_juta(item.get('closing_price'))}",
                arv_text, budget_text, _rp_juta(item.get('selling_cost_actual')),
                f"{_rp_juta(item.get('net_profit_actual'))}\nROI {pct(item.get('roi_actual_pct'))}",
            ])
        add_table(["Proyek / Lokasi", "Tanggal / harga jual (Rp juta)", "ARV / vs closing (Rp juta)", "Budget / modal aktual (Rp juta)", "Biaya jual (Rp juta)", "Profit / ROI aktual (Rp juta)"], rows, widths=[1.45, 1.05, 1.0, 1.3, .8, 1.1])


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
    sec.top_margin = Inches(.92); sec.bottom_margin = Inches(.50); sec.left_margin = Inches(.72); sec.right_margin = Inches(.72)
    sec.header_distance = Inches(.24); sec.footer_distance = Inches(.30)
    styles = doc.styles
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        styles[name].font.name = "Aptos"
        styles[name].font.color.rgb = RGBColor.from_string(NAVY)
        styles[name].font.size = Pt(11 if name == "Normal" else (21 if name == "Title" else (14 if name.startswith("Heading") else 11)))
    styles["Normal"].paragraph_format.space_after = Pt(2)

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    h = header.add_run(f"{BRAND}  |  {BRAND_DESCRIPTOR}")
    h.bold = True; h.font.name = "Aptos"; h.font.size = Pt(11); h.font.color.rgb = RGBColor.from_string(NAVY)
    header.paragraph_format.space_after = Pt(18)
    header.paragraph_format.keep_with_next = True
    header.paragraph_format.line_spacing = 1.15
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    f = footer.add_run(f"{BRAND}  •  Proposal Investasi Properti  •  {_fmt_wib(snapshot.get('analyzed_at'))}")
    f.font.name = "Aptos"; f.font.size = Pt(11); f.font.color.rgb = RGBColor.from_string(NAVY)

    def shade(cell: Any, fill: str) -> None:
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = tc_pr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd"); tc_pr.append(shd)
        shd.set(qn("w:fill"), fill)

    def add_table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None, *, total_last: bool = False):
        """V1.0.18 table layout: clean built-in banding, restrained padding, readable widths."""
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Light Shading Accent 1"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        if widths:
            for idx, width in enumerate(widths):
                if idx < len(table.columns):
                    table.columns[idx].width = Inches(width)
        for idx, label in enumerate(headers):
            table.rows[0].cells[idx].text = str(label)
        for row in rows:
            cells = table.add_row().cells
            for idx, value in enumerate(row):
                if idx < len(cells):
                    cells[idx].text = "—" if value is None or value == "" else str(value)
        header_props = table.rows[0]._tr.get_or_add_trPr()
        repeat = OxmlElement("w:tblHeader")
        repeat.set(qn("w:val"), "true")
        header_props.append(repeat)
        for ridx, row in enumerate(table.rows):
            tr_props = row._tr.get_or_add_trPr()
            tr_props.append(OxmlElement("w:cantSplit"))
            for idx, cell in enumerate(row.cells):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if widths and idx < len(widths):
                    cell.width = Inches(widths[idx])
                if total_last and ridx == len(table.rows) - 1:
                    shade(cell, "E8EEF5")
                for para in cell.paragraphs:
                    para.paragraph_format.space_after = Pt(1)
                    para.paragraph_format.keep_together = True
                    for run in para.runs:
                        run.font.name = "Aptos"
                        run.font.size = Pt(11)
                        run.font.color.rgb = RGBColor.from_string(NAVY)
                        if ridx == 0 or (total_last and ridx == len(table.rows) - 1):
                            run.bold = True
        return table

    title = doc.add_paragraph(style="Title")
    title.paragraph_format.space_after = Pt(5)
    title.paragraph_format.keep_with_next = True
    title_run = title.add_run(DOCUMENT_TITLE); title_run.bold = True; title_run.font.color.rgb = RGBColor.from_string(NAVY)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(6)
    sr = subtitle.add_run(str(p.get("name") or p.get("lot_code") or "Properti Lelang")); sr.bold = True; sr.font.size = Pt(15); sr.font.color.rgb = RGBColor.from_string(TEAL)
    meta = doc.add_paragraph(f"Tanggal analisis: {_fmt_wib(snapshot.get('analyzed_at'))}  |  Property ID: {snapshot.get('property_id', '—')}")
    meta.paragraph_format.space_after = Pt(6)

    doc.add_heading("Ringkasan Eksekutif", level=1)
    doc.add_paragraph(str(decision.get("summary") or "Analisis investasi berdasarkan data dan asumsi yang tersedia."))
    decision_table = doc.add_table(rows=1, cols=2); decision_table.style = "Light Shading Accent 1"; decision_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    decision_table.cell(0, 0).text = "KEPUTUSAN UNDERWRITING"
    decision_table.cell(0, 1).text = str(decision.get("status", "HOLD"))
    for cell in decision_table.rows[0].cells:
        shade(cell, "E8EEF5")
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        tc_pr = cell._tc.get_or_add_tcPr()
        margins = OxmlElement("w:tcMar")
        for side, twips in (("top", 120), ("bottom", 120), ("start", 140), ("end", 140)):
            node = OxmlElement(f"w:{side}"); node.set(qn("w:w"), str(twips)); node.set(qn("w:type"), "dxa"); margins.append(node)
        tc_pr.append(margins)
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
            source = _source_label(comp)
            comp_rows.append([
                address, idr(comp.get("price")),
                f"{comp.get('land_area') or '—'} / {comp.get('building_area') or '—'}",
                source,
            ])
        add_table(["Alamat lengkap", "Harga penawaran", "LT / LB (m²)", "URL / sumber"], comp_rows, widths=[3.05, 1.35, .85, 1.35])

    scenario_headers = ["Komponen"] + [_scenario_header(sc) for sc in scenarios]
    matrix_widths = [2.65] + [1.35] * len(scenarios)

    heading = doc.add_heading("3. Rincian Total Modal per Level Bidding", level=1)
    heading.paragraph_format.page_break_before = True
    capital_rows = _capital_matrix(scenarios)
    add_table(scenario_headers, capital_rows, widths=matrix_widths, total_last=True)
    doc.add_paragraph("Nilai modal merinci biaya dari harga bid sampai tahap pra-penjualan. Biaya penjualan belum dimasukkan ke total modal pra-penjualan. Seluruh angka dinyatakan dalam Rp juta.")

    doc.add_heading("4. Kebutuhan Kas dan Cadangan Risiko", level=1)
    cash_rows = _cash_matrix(snapshot, scenarios)
    add_table(scenario_headers, cash_rows, widths=matrix_widths)
    doc.add_paragraph("Cadangan risiko adalah kebutuhan likuiditas dan tidak otomatis menjadi biaya aktual. Uang jaminan merupakan kebutuhan kas di muka dan tidak ditambahkan lagi ke total modal karena diperhitungkan dalam pelunasan harga lelang.")

    doc.add_heading("5. Biaya Penjualan dan Hasil Bersih", level=1)
    sale_rows = _sales_matrix(scenarios)
    add_table(scenario_headers, sale_rows, widths=matrix_widths, total_last=True)
    doc.add_paragraph("Penjualan bersih adalah estimasi harga penjualan setelah dikurangi biaya penjualan. Profit bersih masih mengurangi total modal pra-penjualan.")

    doc.add_heading("6. Strategi Penawaran", level=1)
    strategy_rows = []
    for sc in scenarios:
        r = sc["result"]
        target_roi = f"{_scenario_target_roi(snapshot, sc['name']):.1f}%"
        strategy_rows.append([
            _rp_juta(sc["bid"]) if sc["bid"] else "—", target_roi,
            pct(r.get("roi_pct")) if r else "—", f"{sc['name']}: {'Bid legal' if sc['legal_bid'] else sc['note']}",
        ])
    strategy_rows.append([_rp_juta(bid.get("walk_away_from")) if bid.get("walk_away_from") is not None else "—", "—", "—", f"Batas berhenti: {bid.get('walk_away_reason') or '—'}"])
    add_table(["Bid / ceiling (Rp juta)", "Target ROI", "ROI simulasi", "Catatan"], strategy_rows, widths=[1.3, .9, .9, 3.6])

    # Start the detailed RAB on a fresh page so its heading and first work rows
    # are not stranded at the foot of the bidding-strategy page.
    heading = doc.add_heading("7. RAB Ringkas", level=1)
    heading.paragraph_format.page_break_before = True
    rab_table_rows = []
    for row in rab_rows[:80]:
        subtotal = rab_row_subtotals(row)
        duration = estimate_item_duration(row)
        time_label = f"{duration['fast']:.1f} / {duration['base']:.1f} / {duration['slow']:.1f}"
        rab_table_rows.append([
            str(row.get("subcategory") or row.get("category") or "—"), str(row.get("work_item") or "—"),
            f"{row.get('quantity') or '—'} {row.get('unit') or ''}".strip(),
            _idr_plain(row.get("unit_cost")) if to_float(row.get("unit_cost")) > 0 else "Belum ada harga",
            _idr_plain(subtotal.get("subtotal_base")) if subtotal.get("subtotal_base") is not None else "Belum lengkap",
            time_label,
        ])
    total = _sum_rab(rab_rows)
    total_base = idr(total["totals"]["base"]) if total["totals"]["base"] is not None else "Belum tersedia"
    if not total["complete_base"]:
        total_base += f" (parsial {total['priced']['base']}/{total['count']} item)"
    rab_table_rows.append(["TOTAL", "Total RAB dasar", "", "", _idr_plain(total["totals"]["base"]) if total["totals"]["base"] is not None else "Belum tersedia", "Critical path"] )
    if rab_table_rows:
        add_table(["Kelompok", "Pekerjaan", "Vol.", "Harga satuan (Rp)", "Subtotal dasar (Rp)", "Durasi C/D/K*"], rab_table_rows, widths=[1.1, 1.75, .65, .95, 1.15, 1.05], total_last=True)
        low = idr(total["totals"]["low"]) if total["totals"]["low"] is not None else "Belum tersedia"
        high = idr(total["totals"]["high"]) if total["totals"]["high"] is not None else "Belum tersedia"
        doc.add_paragraph(f"Harga satuan dan subtotal ditampilkan dalam Rupiah penuh. Rentang total RAB screening: rendah {low}; dasar {total_base}; atas {high}. Item tanpa harga tetap terlihat dan tidak dianggap Rp0.")
    else:
        doc.add_paragraph("Rincian item RAB tidak tersedia pada snapshot memo ini.")

    schedule = estimate_renovation_duration(rab_rows) if rab_rows else {"available": False}
    doc.add_heading("8. Estimasi Waktu Renovasi", level=1)
    if schedule.get("available"):
        doc.add_paragraph(f"Estimasi durasi total berdasarkan critical path: cepat {schedule['calendar_days']['fast']} hari kalender; dasar {schedule['calendar_days']['base']} hari; konservatif {schedule['calendar_days']['slow']} hari. Asumsi {schedule['working_days_per_week']} hari kerja per minggu dan buffer {schedule['buffer_pct']:.0f}%.")
        add_table(["Tahap", "Cepat (hari kerja)", "Dasar (hari kerja)", "Konservatif (hari kerja)"], [[x["phase"], round(x["fast_days"], 1), round(x["base_days"], 1), round(x["slow_days"], 1)] for x in schedule.get("phases", [])], widths=[3.0, 1.2, 1.2, 1.4])
        doc.add_paragraph("*Durasi per item pada RAB adalah estimasi effort satu regu kecil. Pekerjaan yang berbeda dalam satu fase dapat berlangsung paralel; karena itu jumlah hari per item tidak dijumlahkan langsung. Durasi total menggunakan estimasi critical path yang sama dengan menu Estimasi Waktu Renovasi.")
    else:
        doc.add_paragraph("Durasi belum dapat dihitung karena volume pekerjaan belum tersedia.")

    heading = doc.add_heading("9. Risiko dan Mitigasi", level=1)
    heading.paragraph_format.page_break_before = True
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
    doc.add_paragraph("Proposal ini bersifat indikatif, bukan appraisal resmi, pendapat hukum, jaminan keuntungan, atau quotation kontraktor. Verifikasi harga transaksi, legalitas, kondisi aset, biaya, dan jadwal sebelum investasi.")

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
