"""Verified official economic context snapshots, not property-price forecasts.

Sources are published by BPS Sidoarjo and Bank Indonesia. The app includes
only snapshots within their stated validity windows and labels their geography.
No economic indicator is used as an automatic ARV adjustment.
"""
from __future__ import annotations
from datetime import date
from typing import Any

ECONOMY_SNAPSHOT_VERSION = "ID_EAST_JAVA_2026-11-25_V1"
SOURCES: list[dict[str, Any]] = [
    {
        "geography": "Kabupaten Sidoarjo",
        "indicator": "Pertumbuhan ekonomi (PDRB riil)",
        "value": "5,63%",
        "period": "Tahun 2025",
        "published": "2026-03-06",
        "max_age_days": 450,
        "source": "BPS Kabupaten Sidoarjo",
        "url": "https://sidoarjokab.bps.go.id/id/pressrelease/2026/03/06/60/economic-growth-of-sidoarjo-regency-in-2025.html",
        "interpretation": "Aktivitas ekonomi kabupaten tumbuh. Indikator ini memberi konteks kemampuan ekonomi wilayah, tetapi tidak mengukur harga atau kecepatan penjualan rumah pada satu perumahan.",
    },
    {
        "geography": "Provinsi Jawa Timur",
        "indicator": "Pertumbuhan ekonomi (PDRB riil)",
        "value": "5,72% yoy",
        "period": "Triwulan II 2026",
        "published": "2026-09-15",
        "max_age_days": 180,
        "source": "Bank Indonesia - Laporan Perekonomian Jawa Timur Agustus 2026",
        "url": "https://www.bi.go.id/id/publikasi/laporan/lpp/Pages/Laporan-Perekonomian-Provinsi-Jawa-Timur-Agustus-2026.aspx",
        "interpretation": "Pertumbuhan regional ditopang antara lain investasi, ekspor, industri pengolahan, perdagangan, konstruksi dan akomodasi. Ini konteks provinsi, bukan data mikro di sekitar alamat objek.",
    },
    {
        "geography": "Pasar primer perumahan Indonesia",
        "indicator": "Pertumbuhan Indeks Harga Properti Residensial (RPPI)",
        "value": "+0,58% yoy",
        "period": "Triwulan III 2026",
        "published": "2026-11-06",
        "max_age_days": 120,
        "source": "Bank Indonesia - Survei Harga Properti Residensial Q3 2026",
        "url": "https://www.bi.go.id/en/publikasi/ruang-media/news-release/Pages/sp_2824426.aspx",
        "interpretation": "Harga properti residensial primer tumbuh terbatas. Indeks nasional ini bukan indeks harga rumah secondary di Sidoarjo.",
    },
    {
        "geography": "Pasar primer perumahan Indonesia",
        "indicator": "Pertumbuhan penjualan rumah primer",
        "value": "-8,43% yoy",
        "period": "Triwulan III 2026",
        "published": "2026-11-06",
        "max_age_days": 120,
        "source": "Bank Indonesia - Survei Harga Properti Residensial Q3 2026",
        "url": "https://www.bi.go.id/en/publikasi/ruang-media/news-release/Pages/sp_2824426.aspx",
        "interpretation": "Penjualan rumah primer nasional melemah. Ini menjadi sinyal kehati-hatian untuk asumsi waktu jual, tetapi tidak dapat langsung disamakan dengan pasar rumah secondary setempat.",
    },
]


def build_regional_economy_context(location: str, today: date | None = None) -> dict[str, Any] | None:
    loc = str(location or "").lower()
    if not any(term in loc for term in ("sidoarjo", "jawa timur", "east java")):
        return None
    today = today or date.today()
    selected = []
    for row in SOURCES:
        geo = row["geography"].lower()
        if "sidoarjo" in geo and "sidoarjo" not in loc:
            continue
        try:
            age = (today - date.fromisoformat(row["published"])).days
        except ValueError:
            continue
        if age < 0 or age > int(row["max_age_days"]):
            continue
        selected.append({**row, "age_days": age, "freshness": "Terbaru dalam jendela pemakaian"})
    if not selected:
        return None
    return {
        "version": ECONOMY_SNAPSHOT_VERSION,
        "as_of": today.isoformat(),
        "location_scope": "Sidoarjo dan Jawa Timur; indikator nasional dipisahkan sebagai konteks pasar primer",
        "items": selected,
        "advice": [
            "Pertumbuhan PDRB Sidoarjo dan Jawa Timur memberi konteks aktivitas ekonomi regional, tetapi tidak digunakan sebagai pengali ARV.",
            "Pertumbuhan harga rumah primer yang terbatas dan kontraksi penjualan primer nasional menjadi alasan untuk tidak mengasumsikan penjualan cepat tanpa dukungan listing pembanding secondary setempat.",
            "Harga jual, diskon cepat jual dan estimasi waktu pemasaran tetap ditentukan terutama oleh pembanding rumah secondary terdekat, kondisi fisik, legalitas, akses, dan respons calon pembeli.",
        ],
        "limitations": "Tidak tersedia indikator harga transaksi rumah secondary pada tingkat desa/perumahan dari sumber resmi yang konsisten dalam snapshot ini. Data makro hanya konteks, bukan bukti ARV atau likuiditas mikro.",
    }
