"""Helpers for storing non-winning auction outcomes as comparable market evidence."""
from __future__ import annotations
from datetime import date
from typing import Any
from .utils import to_float, new_id, iso_now

OUTCOME_STATUSES = [
    "Pemenang lain - harga diketahui",
    "Saya menang",
    "Tidak ada penawaran / tidak laku",
    "Lelang dibatalkan",
    "Hasil belum diketahui",
]
PRICE_TYPES = ["Harga menang resmi", "Penawaran tertinggi", "Harga dilaporkan pihak lain", "Estimasi / belum terverifikasi"]
SOURCE_GRADES = ["Dokumen resmi KPKNL", "Halaman hasil resmi / portal lelang", "Informasi pihak terlibat", "Informasi tidak terverifikasi"]


def build_auction_outcome_record(*, property_id: str = "", property_name: str = "", lot_code: str = "", address: str = "", auction_date: str = "", auction_limit: float = 0, outcome_status: str, winning_price: float = 0, price_type: str = "", source_grade: str, source_url: str = "", source_note: str = "", outcome_id: str | None = None) -> dict[str, Any]:
    status = str(outcome_status or "").strip()
    if status not in OUTCOME_STATUSES:
        raise ValueError("Status hasil lelang tidak dikenal.")
    price = max(0.0, to_float(winning_price))
    if status in {OUTCOME_STATUSES[0], OUTCOME_STATUSES[1]} and price <= 0:
        raise ValueError("Harga menang/penawaran tertinggi harus diisi untuk hasil lelang yang memiliki harga.")
    if price > 0 and not price_type:
        raise ValueError("Jenis harga wajib dipilih agar harga menang tidak disamakan dengan estimasi.")
    if not source_grade:
        raise ValueError("Kualitas sumber wajib dipilih.")
    return {
        "outcome_id": outcome_id or new_id("AUC"),
        "property_id": str(property_id or ""),
        "property_name": str(property_name or "").strip(),
        "lot_code": str(lot_code or "").strip(),
        "address": str(address or "").strip(),
        "auction_date": str(auction_date or "")[:10],
        "auction_limit": max(0.0, to_float(auction_limit)),
        "outcome_status": status,
        "winning_price": price,
        "price_type": str(price_type or ""),
        "source_grade": str(source_grade),
        "source_url": str(source_url or "").strip(),
        "source_note": str(source_note or "").strip(),
        "recorded_at": iso_now(),
        "payload": {"is_market_evidence": True, "no_winner_personal_data": True},
    }


def implied_discount_vs_limit(limit: float, winning_price: float) -> float | None:
    limit = to_float(limit); price = to_float(winning_price)
    if limit <= 0 or price <= 0:
        return None
    return (price - limit) / limit * 100.0
