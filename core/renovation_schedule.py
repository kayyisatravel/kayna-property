"""Deterministic screening schedule for renovation scopes.

Rates represent a small standard work crew and are planning allowances, not
contractor commitments. Independent scopes within a phase can run in parallel.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from typing import Any

# (fast, base, slow) productivity per working day for one small crew.
PRODUCTIVITY: dict[str, dict[str, tuple[float, float, float]]] = {
    "painting": {"m2": (90.0, 60.0, 40.0), "unit": (12.0, 8.0, 5.0)},
    "roof": {"m2": (18.0, 12.0, 8.0), "m": (24.0, 16.0, 10.0)},
    "waterproofing": {"m2": (25.0, 16.0, 10.0), "m": (25.0, 16.0, 10.0)},
    "masonry": {"m2": (18.0, 12.0, 8.0), "m": (20.0, 14.0, 9.0)},
    "ceiling": {"m2": (30.0, 20.0, 12.0)},
    "flooring": {"m2": (22.0, 15.0, 10.0)},
    "electrical": {"point": (10.0, 7.0, 4.0), "unit": (10.0, 7.0, 4.0)},
    "plumbing": {"point": (8.0, 5.0, 3.0), "unit": (8.0, 5.0, 3.0)},
    "joinery": {"unit": (8.0, 5.0, 3.0)},
    "cleaning": {"m2": (150.0, 100.0, 65.0), "ls": (1.0, 1.5, 2.0)},
    "demolition": {"m2": (25.0, 16.0, 10.0), "ls": (1.0, 1.5, 2.0)},
    "other": {"m2": (15.0, 10.0, 6.0), "m": (15.0, 10.0, 6.0), "unit": (5.0, 3.0, 2.0), "point": (5.0, 3.0, 2.0), "ls": (1.0, 2.0, 3.0)},
}

KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("demolition", ("bongkar", "pembongkaran", "kupas", "buang material")),
    ("roof", ("atap", "kanopi", "spandek", "galvalum", "genteng", "talang", "rangka atap", "flashing")),
    ("waterproofing", ("waterproof", "anti rembes", "rembes", "sealant", "kedap air")),
    ("electrical", ("listrik", "kabel", "saklar", "stopkontak", "fitting", "lampu")),
    ("plumbing", ("plumbing", "pipa", "saluran air", "sanitair", "keran", "kran", "closet", "wc")),
    ("ceiling", ("plafon", "gypsum", "pvc ceiling")),
    ("flooring", ("keramik", "ubin", "lantai", "nat lantai")),
    ("painting", ("cat", "pengecatan", "paint", "finishing dinding", "fasad")),
    ("joinery", ("kusen", "engsel", "kunci", "pintu", "jendela", "teralis", "pagar")),
    ("cleaning", ("pembersihan", "bersihkan", "cleaning", "angkat sampah", "proteksi area")),
    ("masonry", ("plester", "aci", "retak", "tambal", "pasangan bata", "perbaikan dinding")),
)

PHASES = [
    ("Persiapan & pembongkaran", {"cleaning", "demolition"}),
    ("Atap, rembesan & perbaikan dasar", {"roof", "waterproofing", "masonry"}),
    ("Instalasi MEP", {"electrical", "plumbing"}),
    ("Plafon & lantai", {"ceiling", "flooring"}),
    ("Pengecatan & finishing", {"painting", "joinery"}),
    ("Pembersihan akhir & pemeriksaan", {"other"}),
]


def classify_work_item(item: dict[str, Any]) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("work_item", "description", "subcategory", "category")).lower()
    for category, words in KEYWORDS:
        if any(word in text for word in words):
            return category
    return "other"


def _unit_key(unit: Any) -> str:
    u = str(unit or "").strip().lower().replace("²", "2").replace(" ", "")
    if u in {"m2", "m^2", "meter2", "meterpersegi"}: return "m2"
    if u in {"m", "m'", "meter", "m1"}: return "m"
    if u in {"titik", "point"}: return "point"
    if u in {"unit", "buah", "bh", "set"}: return "unit"
    if u in {"ls", "lot", "lumpsum", "paket"}: return "ls"
    return u


def _duration_for(item: dict[str, Any]) -> dict[str, float]:
    category = classify_work_item(item)
    unit = _unit_key(item.get("unit"))
    rates = PRODUCTIVITY.get(category, PRODUCTIVITY["other"]).get(unit)
    qty = max(0.0, float(item.get("quantity") or item.get("volume_dipakai") or item.get("volume") or 0))
    if qty <= 0:
        return {"fast": 0.5, "base": 1.0, "slow": 2.0, "category": category, "measured": False}
    if rates is None:
        # Unmapped unit gets a deliberately visible generic allowance.
        rates = (5.0, 3.0, 2.0)
    fast_rate, base_rate, slow_rate = rates
    return {
        "fast": max(0.25, qty / fast_rate),
        "base": max(0.5, qty / base_rate),
        "slow": max(1.0, qty / slow_rate),
        "category": category,
        "measured": True,
    }


def estimate_renovation_duration(items: list[dict[str, Any]] | None, *, start_date: date | None = None, working_days_per_week: int = 6, buffer_pct: float = 20.0) -> dict[str, Any]:
    """Estimate critical-path duration; parallel work in same phase uses max duration.

    The phase totals are rounded to working days and then receive a configurable
    schedule buffer. Calendar conversion assumes the configured work week.
    """
    rows = [x for x in (items or []) if isinstance(x, dict)]
    if not rows:
        return {"available": False, "reason": "Belum ada daftar item renovasi dengan volume untuk dihitung."}
    categorized: list[tuple[dict[str, Any], dict[str, float]]] = [(row, _duration_for(row)) for row in rows]
    phase_rows: list[dict[str, Any]] = []
    totals = {"fast": 0.0, "base": 0.0, "slow": 0.0}
    assigned_codes: set[int] = set()
    for phase_name, categories in PHASES:
        matching = [(row, duration) for row, duration in categorized if duration["category"] in categories]
        if not matching:
            continue
        # Items within a phase can partially overlap. Sum within the same work
        # family only if they are distinct tasks; use phase critical path max
        # across families to avoid blindly adding all parallel trades.
        family_totals: dict[str, dict[str, float]] = {}
        for row, duration in matching:
            family = duration["category"]
            bucket = family_totals.setdefault(family, {"fast": 0.0, "base": 0.0, "slow": 0.0})
            for level in ("fast", "base", "slow"):
                bucket[level] += duration[level]
        phase = {level: max((v[level] for v in family_totals.values()), default=0.0) for level in ("fast", "base", "slow")}
        for level in phase:
            totals[level] += phase[level]
        phase_rows.append({"phase": phase_name, "fast_days": phase["fast"], "base_days": phase["base"], "slow_days": phase["slow"], "items": len(matching)})
        assigned_codes.update(id(row) for row, _duration in matching)
    unassigned = [(row, duration) for row, duration in categorized if id(row) not in assigned_codes]
    if unassigned:
        for level in ("fast", "base", "slow"):
            # Unmapped items are held as sequential work, not silently omitted.
            totals[level] += sum(d[level] for _r, d in unassigned)
        phase_rows.append({"phase": "Pekerjaan lain / perlu klarifikasi", "fast_days": sum(d["fast"] for _r,d in unassigned), "base_days": sum(d["base"] for _r,d in unassigned), "slow_days": sum(d["slow"] for _r,d in unassigned), "items": len(unassigned)})
    buffer = max(0.0, float(buffer_pct)) / 100.0
    workdays = {level: ceil(totals[level] * (1.0 + buffer)) for level in totals}
    days_per_week = max(1, min(7, int(working_days_per_week)))
    calendar = {level: ceil(days * 7 / days_per_week) for level, days in workdays.items()}
    finish_dates = {}
    if start_date:
        # Convert working days to a conservative calendar-day finish; exact local
        # holidays and site-specific closures are not represented.
        for level, duration in calendar.items():
            finish_dates[level] = (start_date + timedelta(days=duration)).isoformat()
    return {
        "available": True,
        "method": "critical_path_screening_by_phase",
        "crew_assumption": "Satu regu kecil per bidang kerja; pekerjaan berbeda dalam fase yang sama dapat berjalan paralel.",
        "working_days_per_week": days_per_week,
        "buffer_pct": float(buffer_pct),
        "working_days": workdays,
        "calendar_days": calendar,
        "finish_dates": finish_dates,
        "phases": phase_rows,
        "unmapped_items": len(unassigned),
    }
