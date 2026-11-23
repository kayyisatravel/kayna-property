"""Deterministic parser for user-supplied Bill of Quantities (BoQ) text.

Accepted input formats:
- Markdown pipe tables;
- tab-separated tables copied from Excel/Google Sheets;
- plain rows after a recognisable BoQ header, e.g. ``Work item 18 m2``.

User-supplied quantities are preserved exactly. The parser never measures a
photograph or silently scales a declared BoQ quantity from property area.
Unit rates remain a separate AI-estimation/quotation step.
"""
from __future__ import annotations

import re
from typing import Any


def _clean_cell(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .replace("**", "")
        .replace("<br>", " ")
        .replace("<br/>", " ")
        .replace("\u00a0", " ")
    ).strip()


def _cells(line: str) -> list[str]:
    """Split a markdown-pipe or tab-separated row."""
    text = line.strip()
    if "|" in text:
        if text.startswith("|"):
            text = text[1:]
        if text.endswith("|"):
            text = text[:-1]
        return [_clean_cell(c) for c in text.split("|")]
    if "\t" in text:
        return [_clean_cell(c) for c in text.split("\t")]
    return []


def _number(value: str) -> float | None:
    raw = str(value or "").strip().replace(" ", "")
    if not raw:
        return None
    raw = re.sub(r"[^0-9,.-]", "", raw)
    if not raw:
        return None
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    elif "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _unit_is_plausible(value: str) -> bool:
    unit = str(value or "").strip().lower().replace(" ", "")
    return bool(re.fullmatch(
        r"(?:m2|m²|m3|m³|m'|m’|m|ls|l\.s\.|unit|titik|set|paket|buah|bh|kg|ton|liter|ltr|jam|hari|rit|zak|lembar|batang|roll|mtr|meter|m\^2|m\^3)",
        unit,
    ))


def _header_indexes(cells: list[str]) -> dict[str, int] | None:
    low = [re.sub(r"\s+", " ", c.lower()).strip(" .:-") for c in cells]
    item_i = next((j for j, c in enumerate(low) if "item pekerjaan" in c or c in {"pekerjaan", "uraian pekerjaan", "nama pekerjaan"}), None)
    qty_i = next((j for j, c in enumerate(low) if "estimasi volume" in c or c in {"volume", "qty", "kuantitas"}), None)
    unit_i = next((j for j, c in enumerate(low) if c in {"satuan", "unit"} or c.startswith("satuan ")), None)
    if item_i is None or qty_i is None or unit_i is None:
        return None
    indexes = {"item": item_i, "qty": qty_i, "unit": unit_i}
    basis_i = next((j for j, c in enumerate(low) if "dasar asumsi" in c or "asumsi perhitungan" in c or c in {"dasar volume", "basis volume"}), None)
    group_i = next((j for j, c in enumerate(low) if "kelompok pekerjaan" in c or c in {"kelompok", "group", "kategori pekerjaan"}), None)
    if basis_i is not None:
        indexes["basis"] = basis_i
    if group_i is not None:
        indexes["group"] = group_i
    return indexes


def _priority(item_name: str, group_name: str, basis: str = "") -> tuple[str, bool]:
    """Keep explicit user BoQ scopes in the underwriting budget by default.

    Auction properties often cannot be inspected fully. A user-entered BoQ row
    is therefore treated as a planned allowance (Disarankan), even where the
    underlying damage is not yet confirmed. Confidence/notes retain uncertainty;
    the user may explicitly remove a row after inspection.
    """
    text = f"{group_name} {item_name} {basis}".lower()
    # Only scopes that are materially unobservable without interior access or
    # a functional test are flagged as hidden. Missing quantity-basis prose is
    # NOT, by itself, evidence that the work is conditional: users often enter
    # a complete quantity/unit BoQ in a compact table.
    hidden_patterns = [
        r"interior", r"ruang utama", r"kamar mandi",
        r"sanitair", r"instalasi listrik", r"titik listrik", r"mcb",
        r"stop ?kontak", r"saklar", r"kabel", r"pipa", r"plumbing",
        r"plafon.*(interior|dalam|ruang utama)",
        r"(interior|dalam|ruang utama).*plafon",
        r"rangka atap.*(utama|induk|dalam)",
    ]
    hidden_scope = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in hidden_patterns)
    return "Disarankan", hidden_scope


def _build_row(
    item_name: str, qty_value: str, unit: str, group: str = "",
    basis: str = "", row_index: int = 1,
) -> dict[str, Any] | None:
    item_name = _clean_cell(item_name)
    qty = _number(qty_value)
    unit = _clean_cell(unit)
    basis = _clean_cell(basis)
    group = _clean_cell(group) or "BoQ Pengguna"
    if not item_name or qty is None or qty <= 0 or not _unit_is_plausible(unit):
        return None
    priority, conditional = _priority(item_name, group, basis)
    return {
        "item_code": f"USER_BOQ_{row_index:03d}",
        "group": group,
        "subcategory": group,
        "work_item": item_name,
        "quantity": qty,
        "quantity_low": qty,
        "quantity_high": qty,
        "unit": unit,
        "quantity_basis": basis or "Volume dimasukkan oleh pengguna dalam BoQ; verifikasi ukuran di lapangan.",
        "priority": priority,
        "conditional": conditional,
        "evidence_basis": "BoQ/dimensi yang diberikan pengguna",
        "confidence": "Rendah" if conditional else "Sedang",
        "notes": "Volume dipertahankan persis dari BoQ pengguna. Baris masuk sebagai allowance modal walau belum terkonfirmasi; keyakinan diturunkan untuk scope tersembunyi. Keluarkan hanya setelah inspeksi menyimpulkan tidak diperlukan. Harga satuan adalah estimasi screening/quotation lokal.",
        "quantity_source": "USER_SUPPLIED_BOQ",
    }


def _plain_row(line: str, row_index: int, current_group: str) -> dict[str, Any] | None:
    """Parse plain text rows whose last two fields are quantity and unit."""
    text = re.sub(r"^\s*(?:[-•*]+|\d+[.)])\s*", "", str(line or "").strip())
    text = text.strip(" |")
    # Deliberately require a recognised unit at line end so prose/assumptions
    # are not accidentally interpreted as construction work items.
    match = re.match(
        r"^(?P<item>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<unit>m2|m²|m3|m³|m['’]|m|ls|l\.s\.|unit|titik|set|paket|buah|bh|kg|ton|liter|ltr|jam|hari|rit|zak|lembar|batang|roll|meter)\s*$",
        text, flags=re.IGNORECASE,
    )
    if not match:
        return None
    item = match.group("item").strip()
    # Some pasted text prefixes rows with a Roman/Arabic sequence token.
    item = re.sub(r"^(?:[IVXLC]+|\d+)[.)]?\s+", "", item, flags=re.IGNORECASE)
    return _build_row(item, match.group("qty"), match.group("unit"), current_group, "", row_index)


def parse_user_boq_table(description: str) -> list[dict[str, Any]]:
    """Parse BoQ rows from Markdown, TSV clipboard paste, or plain rows.

    A recognisable header containing Item Pekerjaan, Estimasi Volume and
    Satuan is required. Markdown and TSV formats preserve optional group and
    quantity-basis columns. A plain-row fallback supports clipboard exports
    where the tab characters were flattened by a text editor.
    """
    raw_lines = [line.rstrip("\r\n") for line in str(description or "").splitlines()]
    header_index: int | None = None
    indexes: dict[str, int] | None = None
    header_kind = ""

    for i, line in enumerate(raw_lines):
        cells = _cells(line)
        candidate = _header_indexes(cells) if cells else None
        if candidate:
            header_index, indexes = i, candidate
            header_kind = "markdown" if "|" in line else "tsv"
            break
        lower = re.sub(r"\s+", " ", line.lower())
        if "item pekerjaan" in lower and "estimasi volume" in lower and "satuan" in lower:
            # Clipboard/editor may flatten tabs. Subsequent rows are parsed by
            # the conservative trailing quantity + unit recogniser.
            header_index = i
            header_kind = "plain"
            break

    if header_index is None:
        return []

    output: list[dict[str, Any]] = []
    last_group = "BoQ Pengguna"
    for line in raw_lines[header_index + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?", stripped):
            continue
        cells = _cells(line)
        if indexes and cells and max(indexes.values()) < len(cells):
            group = cells[indexes["group"]] if "group" in indexes and indexes["group"] < len(cells) else ""
            if group:
                last_group = group
            item = cells[indexes["item"]]
            qty = cells[indexes["qty"]]
            unit = cells[indexes["unit"]]
            basis = cells[indexes["basis"]] if "basis" in indexes and indexes["basis"] < len(cells) else ""
            row = _build_row(item, qty, unit, last_group, basis, len(output) + 1)
            if row:
                output.append(row)
            continue
        # If a row uses a simple 3-column text layout without visible tabs,
        # parse it by its final quantity and unit. Avoid treating narrative
        # bullets following the table as BoQ data.
        row = _plain_row(line, len(output) + 1, last_group)
        if row:
            output.append(row)

    # De-duplicate accidental repeated clipboard rows by the full source row,
    # not by name alone: repeated item scopes may be legitimate when different
    # locations/areas or bases are explicitly provided.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float, str, str]] = set()
    for row in output:
        key = (
            re.sub(r"\s+", " ", row["work_item"].lower()).strip(),
            float(row["quantity"]),
            row["unit"].lower(),
            row["quantity_basis"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        row["item_code"] = f"USER_BOQ_{len(deduped) + 1:03d}"
        deduped.append(row)
    return deduped


def check_geometry_assumptions(description: str, property_context: dict[str, Any] | None = None) -> list[str]:
    """Flag, but never overwrite, property area facts that conflict with BoQ assumptions."""
    context = property_context or {}
    text = str(description or "")
    warnings: list[str] = []
    patterns = [
        ("land_area", r"luas\s+tanah(?:\s+total)?\s*(?:±|~|:)?\s*([0-9]+(?:[.,][0-9]+)?)\s*m(?:2|²)", "LT"),
        ("building_area", r"luas\s+bangunan(?:\s+total)?\s*(?:±|~|:)?\s*([0-9]+(?:[.,][0-9]+)?)\s*m(?:2|²)", "LB"),
    ]
    for key, pattern, label in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        assumed = _number(match.group(1)) if match else None
        actual = _number(str(context.get(key) or ""))
        if assumed and actual and abs(assumed - actual) / max(actual, 1) > 0.03:
            warnings.append(
                f"BoQ menggunakan asumsi {label} {assumed:g} m², sedangkan data properti tersimpan {actual:g} m². "
                "Data properti tidak diubah; volume BoQ tetap dipertahankan sebagai input khusus dan perlu konfirmasi apakah dimensi tersebut memang untuk area pekerjaan ini."
            )
    return warnings
