"""Import user-copied comparable listings from tab-separated or CSV text."""
from __future__ import annotations
import csv, io, re
from typing import Any
from core.utils import to_float

ALIASES = {
    "name": ["alamat / nama listing", "alamat", "nama listing", "listing", "nama", "komparasi"],
    "address": ["alamat", "alamat listing", "lokasi"],
    "price": ["harga listing (idr)", "harga listing", "harga", "price", "nilai"],
    "land_area": ["luas tanah (m2)", "luas tanah", "lt", "land area"],
    "building_area": ["luas bangunan (m2)", "luas bangunan", "lb", "building area"],
    "condition": ["kondisi", "condition"],
    "access": ["akses jalan", "akses", "access"],
    "price_type": ["status harga", "jenis harga", "price type"],
    "certificate": ["sertifikat", "jenis sertifikat", "certificate"],
    "source_url": ["url sumber", "url", "link", "sumber", "source url"],
    "date_found": ["tanggal ditemukan", "tanggal", "date found"],
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _money(s: Any) -> int | None:
    if s is None or str(s).strip() == "": return None
    text = str(s).lower().replace("rp", "").replace("idr", "").strip()
    mult = 1
    if any(x in text for x in ["miliar", "milyar", "m"]): mult = 1_000_000_000
    elif any(x in text for x in ["juta", "jt"]): mult = 1_000_000
    elif any(x in text for x in ["ribu", "rb"]): mult = 1_000
    text = re.sub(r"[^0-9,\.\-]", "", text)
    if not text: return None
    try:
        if mult > 1:
            if "," in text and "." in text: text = text.replace(".", "").replace(",", ".")
            elif "," in text: text = text.replace(",", ".")
            elif "." in text and len(text.split(".")[-1]) == 3: text = text.replace(".", "")
            return int(float(text) * mult)
        if "," in text and "." in text: text = text.replace(".", "").replace(",", ".")
        elif "." in text and len(text.split(".")[-1]) == 3: text = text.replace(".", "")
        elif "," in text and len(text.split(",")[-1]) == 3: text = text.replace(",", "")
        return int(float(text))
    except ValueError: return None


def parse_comparable_paste(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text: return []
    delimiter = "\t" if "\t" in text else (";" if text.count(";") > text.count(",") else ",")
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows: return []
    first = [_norm(x) for x in rows[0]]
    has_header = any(any(alias in col for aliases in ALIASES.values() for alias in aliases) for col in first)
    if has_header:
        headers = first; data_rows = rows[1:]
        mapping = {}
        for target, aliases in ALIASES.items():
            for i, h in enumerate(headers):
                if h in aliases or any(a in h for a in aliases if len(a) > 3): mapping[target] = i; break
    else:
        # Column order: name, price, LT, LB, condition, access, URL, date.
        mapping = {"name": 0, "price": 1, "land_area": 2, "building_area": 3, "condition": 4, "access": 5, "source_url": 6, "date_found": 7}
        data_rows = rows
    output = []
    for row in data_rows:
        def get(k: str, default: Any = "") -> Any:
            i = mapping.get(k)
            return row[i].strip() if i is not None and i < len(row) else default
        name = get("name")
        if not name: continue
        condition = get("condition", "")
        condition_map = {"siap huni": "Siap Huni", "butuh renovasi": "Butuh Renovasi", "hitung tanah": "Hitung Tanah"}
        access = get("access", "")
        access_map = {"2 mobil": "2 Mobil", "2 mobil": "2 Mobil", "1 mobil": "1 Mobil", "gang": "Gang"}
        pt = get("price_type", "Asking aktif") or "Asking aktif"
        pt_map = {"aktif": "Asking aktif", "asking": "Asking aktif", "asking aktif": "Asking aktif", "marked sold": "Marked sold / perlu verifikasi", "terjual": "Marked sold / perlu verifikasi", "transaksi": "Transaksi terverifikasi", "transaksi terverifikasi": "Transaksi terverifikasi"}
        output.append({
            "name": name, "address": get("address", name), "price": _money(get("price")),
            "land_area": to_float(get("land_area"), 0) or None,
            "building_area": to_float(get("building_area"), 0) or None,
            "condition": condition_map.get(_norm(condition), condition), "access": access_map.get(_norm(access), access),
            "price_type": pt_map.get(_norm(pt), pt), "certificate": get("certificate"),
            "source_url": get("source_url"), "date_found": get("date_found"), "adjustment_pct": 0.0,
        })
    return output
