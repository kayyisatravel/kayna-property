"""Restore saved property data into Streamlit form widget keys.

Supports current V1 payloads and older/flattened payload layouts. Always
returns every known key so switching to another property cannot leak stale
values from the previous form session.
"""
from __future__ import annotations
from typing import Any
import json


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _pick(*sources: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value is not None and not (isinstance(value, str) and value.strip() == ""):
                return value
    return default


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None


def form_state_from_input_data(data: dict[str, Any] | None, latest_analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    data = _as_dict(data)
    latest = _as_dict(latest_analysis)
    data_inputs = _as_dict(data.get("inputs"))
    latest_inputs = _as_dict(latest.get("inputs"))

    # Deep-merge by section: current persisted input wins; latest snapshot is
    # used as a fallback for fields that older saves omitted.
    def section(name: str, *aliases: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for source in (latest_inputs, latest, data_inputs, data):
            for alias in (name, *aliases):
                candidate = _as_dict(source.get(alias))
                if candidate:
                    result.update(candidate)
        return result

    prop = section("property", "property_data")
    survey = section("survey", "survey_data")
    legal = section("legal", "legal_data")
    costs = section("costs", "cost", "cost_data")
    rules = section("rules", "rules_config")

    bedrooms = _int_or_none(_pick(prop, survey, keys=("bedrooms", "bedroom_count", "jumlah_kamar_tidur", "kamar_tidur", "kt")))
    bathrooms = _int_or_none(_pick(prop, survey, keys=("bathrooms", "bathroom_count", "jumlah_kamar_mandi", "kamar_mandi", "km")))
    property_type = _pick(prop, survey, keys=("property_type", "property_kind", "jenis_properti", "tipe_properti", "type"), default="")
    road_width = _float_or_none(_pick(survey, prop, keys=("road_width_m", "road_width", "road_width_meter", "lebar_jalan", "lebar_jalan_m")))
    access = _pick(survey, prop, keys=("access", "road_access", "access_type", "akses_jalan", "jenis_akses"), default="")
    physical_condition = _pick(survey, prop, costs, keys=("physical_condition", "general_physical_condition", "condition_general", "kondisi_fisik_umum", "kondisi_fisik", "condition"), default="Belum diketahui")
    floor_count = _int_or_none(_pick(prop, keys=("floor_count", "number_of_floors", "jumlah_lantai", "lantai")))
    if floor_count is None:
        floor_count = 2 if "2 lantai" in str(property_type).lower() else 1

    return {
        # Auction / KPKNL
        "na_lot_code": _pick(prop, keys=("lot_code", "kode_lot"), default=""),
        "na_name": _pick(prop, keys=("name", "nama_objek"), default=""),
        "na_complex": _pick(prop, keys=("complex_name", "nama_perumahan", "kompleks"), default=""),
        "na_address": _pick(prop, keys=("address", "lokasi_alamat", "alamat"), default=""),
        "na_district": _pick(prop, keys=("district", "desa_kecamatan_kabupaten", "wilayah"), default=""),
        "na_province": _pick(prop, keys=("province", "provinsi"), default=""),
        "na_office": _pick(prop, keys=("auction_office", "auction_kpknl", "kpknl"), default=""),
        "na_seller": _pick(prop, keys=("seller", "penjual", "kreditur"), default=""),
        "na_auction_type": _pick(prop, keys=("auction_type", "jenis_lelang"), default=""),
        "na_auction_date": _pick(prop, keys=("auction_date", "tanggal_lelang"), default=""),
        "na_auction_time": _pick(prop, keys=("auction_time", "jam_lelang"), default=""),
        "na_auction_url": _pick(prop, keys=("auction_url", "url_lelang"), default=""),
        "na_deposit_deadline": _pick(prop, keys=("deposit_deadline", "batas_setor_jaminan"), default=""),
        "na_payment_deadline": _pick(prop, keys=("payment_deadline", "batas_pelunasan"), default=""),
        "na_limit": _pick(prop, keys=("auction_limit", "nilai_limit", "limit")),
        "na_deposit": _pick(prop, keys=("deposit_amount", "uang_jaminan", "deposit")),
        "na_increment": _pick(prop, keys=("bid_increment", "kelipatan_bid", "increment")),
        "na_certificate": _pick(prop, keys=("certificate_type", "jenis_sertifikat", "certificate"), default=""),
        "na_certificate_no": _pick(prop, keys=("certificate_no", "nomor_sertifikat", "nomor_hak"), default=""),
        "na_rights_expiry": _pick(prop, keys=("rights_expiry", "masa_berlaku_hak"), default=""),
        "na_land": _pick(prop, keys=("land_area", "luas_tanah", "lt")),
        "na_building": _pick(prop, keys=("building_area", "luas_bangunan", "lb")),
        "na_building_footprint": _pick(prop, keys=("building_footprint_m2", "building_footprint", "luas_tapak")),
        "na_njop": _pick(prop, keys=("njop", "nilai_njop")),
        "na_bedrooms": bedrooms,
        "na_bathrooms": bathrooms,
        "na_property_type": str(property_type or ""),
        "na_floor_count": floor_count,
        "na_risk_ceiling": _pick(prop, keys=("risk_adjusted_ceiling", "hard_bid_ceiling")),
        "na_npoptkp_eligible": bool(_pick(prop, legal, keys=("npoptkp_eligible", "eligible_for_npoptkp"), default=False)),
        # Legal / tax
        "na_legal_verified": bool(_pick(legal, keys=("identity_verified", "legal_verified"), default=False)),
        "na_dispute": bool(_pick(legal, keys=("dispute_detected", "dispute"), default=False)),
        "na_tax_verified": bool(_pick(legal, keys=("tax_rules_verified", "tax_verified"), default=False)),
        "na_tax_region": _pick(legal, prop, keys=("tax_region", "tax_region_name"), default=""),
        "na_tax_rule_source": _pick(legal, keys=("tax_rule_source_url", "tax_source_url"), default=""),
        "na_bphtb_rate": _pick(rules, keys=("bphtb_rate_pct",), default=5.0),
        "na_npoptkp": _pick(rules, keys=("npoptkp",), default=80_000_000),
        "na_buyer_fee": _pick(rules, keys=("buyer_auction_fee_pct",), default=2.0),
        # Survey / physical condition
        "na_survey_status": _pick(survey, keys=("survey_status", "occupancy_status", "status_survei"), default="Belum Survei"),
        "na_possession_cost": _pick(survey, keys=("possession_cost", "biaya_pengosongan"), default=25_000_000),
        "na_possession_months": _pick(survey, keys=("possession_months", "waktu_pengosongan_bulan"), default=6),
        "na_possession_risk_reserve": _pick(survey, keys=("possession_risk_reserve", "risk_reserve"), default=100_000_000),
        "na_survey_date": _pick(survey, keys=("survey_date", "tanggal_survei"), default=""),
        "na_road_width": road_width,
        "na_access": str(access or ""),
        "na_physical_condition": str(physical_condition or "Belum diketahui"),
        "na_interior_inspected": bool(_pick(survey, keys=("interior_inspected", "interior_checked"), default=False)),
        "na_facade_ai": _pick(survey, keys=("facade_ai_description", "facade_ai", "facade_description"), default=""),
        "na_facade_manual": _pick(survey, keys=("facade_description", "facade_manual", "facade_ai_description"), default=""),
        "na_survey_notes": _pick(survey, keys=("survey_notes", "catatan_survei"), default=""),
        # Renovation / time / holding
        "na_rab_condition_description": _pick(costs, keys=("rab_condition_description", "condition_description", "renovation_description"), default=""),
        "na_renovation_category": _pick(costs, keys=("renovation_category", "rab_category"), default=_category_from_condition(physical_condition)),
        "na_renovation_extra": _pick(costs, keys=("renovation_extra_cost", "renovation_extra"), default=0),
        "na_renovation_months": _pick(costs, keys=("renovation_months",), default=1),
        "na_selling_months": _pick(costs, keys=("selling_months",), default=3),
        "na_monthly_holding": _pick(costs, rules, keys=("monthly_holding_cost",), default=1_000_000),
        "na_legal_delay_months": _pick(costs, keys=("legal_delay_months",), default=1),
        "na_marketing_cost": _pick(costs, keys=("marketing_cost",), default=1_000_000),
        "na_other_presale": _pick(costs, keys=("other_presale_cost",), default=0),
        "na_negotiation_discount": _pick(rules, keys=("negotiation_discount_pct",), default=10),
        "na_quick_sale_discount": _pick(rules, keys=("quick_sale_discount_pct",), default=5),
        "na_costs_reviewed": bool(_pick(costs, keys=("cost_estimates_reviewed",), default=False)),
    }


def _category_from_condition(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "hitung tanah" in text:
        return "Hitung Tanah"
    if "berat" in text:
        return "Renovasi Berat"
    if "sedang" in text:
        return "Renovasi Sedang"
    if "ringan" in text:
        return "Renovasi Ringan"
    if "kosmetik" in text:
        return "Renovasi Kosmetik"
    return "Auto sesuai kondisi umum"
