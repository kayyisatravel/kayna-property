"""Deterministic parser for user-supplied markdown Bill of Quantities tables.

The parser preserves quantities supplied by the user; it never measures a
photograph or silently scales a declared BoQ quantity from another property
area. Unit rates remain a separate estimation/quotation step.
"""
from __future__ import annotations

import re
from typing import Any


def _cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [c.strip().replace("**", "").replace("<br>", " ") for c in text.split("|")]


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


def _priority(item_name: str, group_name: str, basis: str = "") -> tuple[str, bool]:
    """Assign a conservative default scope from the BoQ text, not renovation class alone.

    Explicit user quantities are retained. Items that are purely aesthetic or
    depend on hidden conditions stay conditional; work tied to visible damage
    enters the base draft, but remains subject to field verification.
    """
    text = f"{group_name} {item_name} {basis}".lower()
    evidence = str(basis or "").lower()

    # Hidden interior/MEP work is classified before broad terms such as
    # "rembesan". A quantity based on a percentage/assumption is not proof
    # that the concealed element is damaged. It becomes base scope only when
    # the user explicitly says it was inspected/confirmed on site.
    interior_terms = [
        "interior", "ruang utama", "plafon interior", "kamar mandi",
        "sanitair", "instalasi listrik", "titik listrik", "mcb", "pipa",
        "kusen", "daun pintu", "jendela",
    ]
    confirmed_interior = any(token in evidence for token in [
        "hasil inspeksi", "hasil pemeriksaan", "sudah diperiksa",
        "terkonfirmasi di lapangan", "kerusakan aktual", "hasil ukur lapangan",
    ])
    if any(k in text for k in interior_terms):
        if not confirmed_interior:
            return "Bersyarat", True
        if any(k in text for k in ["rusak", "bocor", "lembap", "rembes", "perbaikan", "penggantian", "peremajaan"]):
            return "Wajib", False
        return "Disarankan", False

    # Directly related to visible front facade / roof failure / water ingress.
    if any(k in text for k in [
        "pembongkaran atap", "atap kanopi", "atap teras", "atap depan",
        "flashing", "pengikisan cat mengelupas", "dinding lembap",
        "waterproofing", "jamur", "rembesan", "anti-rembes",
    ]):
        # Whole-area replacement of a canopy may be a preferred scope rather
        # than the only technically necessary repair; retain as recommended.
        if "pemasangan atap kanopi baru" in text or "penggantian atap kanopi" in text:
            return "Disarankan", False
        return "Wajib", False

    if any(k in text for k in [
        "pembersihan tumpukan", "pembersihan area", "perapian taman",
        "penggantian plafon area teras", "tambal sulam plafon teras",
    ]):
        return "Disarankan", False

    # Whole-area finishes and upgrades do not automatically become essential
    # merely because their quantities are present in an assumption-based BoQ.
    if any(k in text for k in [
        "seluruh fasad", "pengecatan ulang fasad", "keramik", "lantai carport",
        "pagar besi", "cat ulang seluruh",
    ]):
        return "Bersyarat", True

    # Any user-supplied scope not strongly supported by the visible evidence is
    # kept for review, not silently charged to the base RAB.
    return "Bersyarat", True


def parse_user_boq_table(description: str) -> list[dict[str, Any]]:
    """Parse a Markdown table with item, quantity, unit and basis columns."""
    lines = [line for line in str(description or "").splitlines() if "|" in line]
    header_index = None
    indexes: dict[str, int] = {}
    for i, line in enumerate(lines):
        cells = _cells(line)
        low = [c.lower() for c in cells]
        item_i = next((j for j, c in enumerate(low) if "item pekerjaan" in c or c in {"pekerjaan", "uraian pekerjaan"}), None)
        qty_i = next((j for j, c in enumerate(low) if "estimasi volume" in c or c in {"volume", "qty", "kuantitas"}), None)
        unit_i = next((j for j, c in enumerate(low) if "satuan" in c or c == "unit"), None)
        basis_i = next((j for j, c in enumerate(low) if "dasar asumsi" in c or "asumsi perhitungan" in c), None)
        group_i = next((j for j, c in enumerate(low) if "kelompok pekerjaan" in c or c in {"kelompok", "group"}), None)
        if item_i is not None and qty_i is not None and unit_i is not None:
            header_index = i
            indexes = {"item": item_i, "qty": qty_i, "unit": unit_i}
            if basis_i is not None:
                indexes["basis"] = basis_i
            if group_i is not None:
                indexes["group"] = group_i
            break
    if header_index is None:
        return []

    output: list[dict[str, Any]] = []
    last_group = ""
    for line in lines[header_index + 1:]:
        cells = _cells(line)
        if not cells or all(not c.strip(" :-") for c in cells):
            continue
        if len(cells) <= max(indexes.values()):
            continue
        group = cells[indexes["group"]].strip() if "group" in indexes and indexes["group"] < len(cells) else ""
        if group:
            last_group = group
        item_name = cells[indexes["item"]].strip()
        qty = _number(cells[indexes["qty"]])
        unit = cells[indexes["unit"]].strip()
        basis = cells[indexes["basis"]].strip() if "basis" in indexes and indexes["basis"] < len(cells) else ""
        if not item_name or qty is None or qty <= 0 or not unit:
            continue
        priority, conditional = _priority(item_name, last_group, basis)
        code = f"USER_BOQ_{len(output) + 1:03d}"
        output.append({
            "item_code": code, "group": last_group, "subcategory": last_group,
            "work_item": item_name,
            "quantity": qty, "quantity_low": qty, "quantity_high": qty,
            "unit": unit, "quantity_basis": basis or "Volume dimasukkan oleh pengguna dalam BoQ; verifikasi ukuran di lapangan.",
            "priority": priority, "conditional": conditional,
            "evidence_basis": "BoQ/dimensi yang diberikan pengguna",
            "confidence": "Sedang" if basis else "Rendah",
            "notes": "Volume dipertahankan persis dari BoQ pengguna. Harga satuan harus ditaksir terpisah atau diverifikasi dengan penawaran lokal.",
            "quantity_source": "USER_SUPPLIED_BOQ",
        })
    return output


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
