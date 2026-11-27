"""Gemini 3.5 Flash-Lite document parser and optional reviewer."""
from __future__ import annotations
import hashlib, io, json, random, time, re
from typing import Optional, Any
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field
from core.utils import to_float
from core.user_boq import parse_user_boq_table, check_geometry_assumptions
from core.renovation_pricing import apply_regional_screening_rates, PRICE_CATALOG_BASIS, PRICE_CATALOG_VERSION

DEFAULT_MODEL = "gemini-3.5-flash-lite"

class FieldEvidence(BaseModel):
    """Explicit evidence fields; avoid dynamic dict/additionalProperties in Gemini schema."""
    lot_code: Optional[str] = None
    name: Optional[str] = None
    auction_office: Optional[str] = None
    seller: Optional[str] = None
    auction_date: Optional[str] = None
    deposit_deadline: Optional[str] = None
    payment_deadline: Optional[str] = None
    auction_limit: Optional[str] = None
    deposit_amount: Optional[str] = None
    bid_increment: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    land_area: Optional[str] = None
    building_area: Optional[str] = None
    certificate_type: Optional[str] = None
    certificate_no: Optional[str] = None
    njop: Optional[str] = None


class AuctionExtraction(BaseModel):
    lot_code: Optional[str] = None
    name: Optional[str] = None
    auction_office: Optional[str] = None
    seller: Optional[str] = None
    auction_type: Optional[str] = None
    auction_date: Optional[str] = None
    auction_time: Optional[str] = None
    auction_url: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    auction_limit: Optional[int] = None
    deposit_amount: Optional[int] = None
    bid_increment: Optional[int] = None
    deposit_deadline: Optional[str] = None
    payment_deadline: Optional[str] = None
    certificate_type: Optional[str] = None
    certificate_no: Optional[str] = None
    rights_expiry: Optional[str] = None
    land_area: Optional[float] = None
    building_area: Optional[float] = None
    njop: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    property_type: Optional[str] = None
    auction_object_description: Optional[str] = None
    facade_assessment: Optional[str] = None
    facade_visible_findings: list[str] = Field(default_factory=list)
    facade_unknowns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    field_evidence: FieldEvidence = Field(default_factory=FieldEvidence)
    verification_notes: Optional[str] = None


class ComparableItem(BaseModel):
    """Compact, aliased schema to reduce Gemini output tokens for multi-listing parsing.

    Short JSON keys are expanded to application field names after validation. URLs
    are extracted deterministically from the user's original text, never generated.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    source_index: Optional[int] = Field(default=None, alias="i")
    name: Optional[str] = Field(default=None, alias="n")
    address: Optional[str] = Field(default=None, alias="a")
    complex_name: Optional[str] = Field(default=None, alias="cx")
    price: Optional[int] = Field(default=None, alias="p")
    njop: Optional[int] = Field(default=None, alias="nj")
    land_area: Optional[float] = Field(default=None, alias="lt")
    building_area: Optional[float] = Field(default=None, alias="lb")
    bedrooms: Optional[int] = Field(default=None, alias="kt")
    bathrooms: Optional[int] = Field(default=None, alias="km")
    condition: Optional[str] = Field(default=None, alias="c")
    condition_detail: Optional[str] = Field(default=None, alias="cd")
    access: Optional[str] = Field(default=None, alias="ac")
    access_detail: Optional[str] = Field(default=None, alias="ad")
    certificate: Optional[str] = Field(default=None, alias="cert")
    orientation: Optional[str] = Field(default=None, alias="ori")
    electricity_watt: Optional[int] = Field(default=None, alias="w")
    water_source: Optional[str] = Field(default=None, alias="water")
    source_platforms: list[str] = Field(default_factory=list, alias="src")
    listing_date: Optional[str] = Field(default=None, alias="dt")
    price_type: Optional[str] = Field(default=None, alias="pt")
    notes: Optional[str] = Field(default=None, alias="nt")


class ComparableExtraction(BaseModel):
    items: list[ComparableItem] = Field(default_factory=list)
    parsing_notes: list[str] = Field(default_factory=list)




class MarketComparableJudgement(BaseModel):
    source_index: int = Field(ge=1, le=20)
    relevance_score: int = Field(default=50, ge=0, le=100)
    suggested_adjustment_pct: float = Field(default=0.0, ge=-20.0, le=20.0)
    exclude_from_primary: bool = False
    reason: str = ""
    data_gaps: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class MarketIntelligenceReview(BaseModel):
    overall_assessment: str = ""
    market_segment: Optional[str] = None
    key_value_drivers: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    items: list[MarketComparableJudgement] = Field(default_factory=list)


class RenovationRabItem(BaseModel):
    """One AI-selected RAB item; deterministic Python quantity hints take priority."""
    item_code: Optional[str] = None
    work_item: str
    scope_description: Optional[str] = None
    quantity: Optional[float] = None
    quantity_basis: Optional[str] = None
    unit: Optional[str] = None
    unit_cost_low: Optional[int] = None
    unit_cost_conservative: Optional[int] = None
    unit_cost_high: Optional[int] = None
    priority: Optional[str] = None
    evidence_basis: Optional[str] = None
    confidence: Optional[str] = None
    rate_basis: Optional[str] = None
    materials_and_labor_included: Optional[bool] = None
    notes: Optional[str] = None


class RenovationBoqRateItem(BaseModel):
    """One unit-rate suggestion for a specific user-supplied BoQ row."""
    item_code: str
    unit_cost_low: Optional[int] = None
    unit_cost_conservative: Optional[int] = None
    unit_cost_high: Optional[int] = None
    rate_basis: Optional[str] = None
    materials_and_labor_included: Optional[bool] = None
    confidence: str = "Rendah"
    notes: Optional[str] = None


class RenovationBoqRateResult(BaseModel):
    items: list[RenovationBoqRateItem] = Field(default_factory=list)


class RenovationInteriorScenario(BaseModel):
    """Unverified interior scenario kept separate from the measured base RAB."""
    scenario_name: str
    assumptions: list[str] = Field(default_factory=list)
    potential_work_items: list[str] = Field(default_factory=list)
    cost_low: Optional[int] = None
    cost_high: Optional[int] = None
    confidence: str = "Rendah"
    inspection_required: bool = True


class RenovationRabExtraction(BaseModel):
    items: list[RenovationRabItem] = Field(default_factory=list)
    visual_findings: list[str] = Field(default_factory=list)
    likely_causes_to_verify: list[str] = Field(default_factory=list)
    interior_unknowns: list[str] = Field(default_factory=list)
    occupancy_unknowns: list[str] = Field(default_factory=list)
    interior_scenarios: list[RenovationInteriorScenario] = Field(default_factory=list)
    inspection_plan: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    items_to_inspect: list[str] = Field(default_factory=list)
    overall_note: Optional[str] = None



def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_upload(file_bytes: bytes, mime_type: str, max_width: int = 1280, jpeg_quality: int = 80) -> tuple[bytes, str]:
    if mime_type == "application/pdf": return file_bytes, mime_type
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.width > max_width:
            new_height = round(image.height * max_width / image.width)
            image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
        out = io.BytesIO(); image.save(out, format="JPEG", quality=jpeg_quality, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception as exc:
        raise ValueError(f"Gambar tidak dapat diproses: {exc}") from exc


def _client_call(api_key: str, model: str, prompt: str, file_bytes: bytes | None = None, mime_type: str | None = None, schema: Any = None, max_output_tokens: int = 1600, extra_files: list[tuple[bytes, str]] | None = None, return_metadata: bool = False) -> str | dict[str, Any]: 
    if not api_key: raise RuntimeError("GEMINI_API_KEY belum dikonfigurasi di Streamlit Secrets.")
    from google import genai
    from google.genai import types
    contents: Any = prompt
    parts = []
    if file_bytes is not None:
        parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type or "application/octet-stream"))
    for extra_bytes, extra_mime in extra_files or []:
        parts.append(types.Part.from_bytes(data=extra_bytes, mime_type=extra_mime or "application/octet-stream"))
    if parts:
        contents = [prompt, *parts]
    last_exc = None
    for attempt in range(3):
        try:
            with genai.Client(api_key=api_key) as client:
                response = client.models.generate_content(
                    model=model or DEFAULT_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        max_output_tokens=max_output_tokens,
                        response_mime_type="application/json" if schema else "text/plain",
                        response_schema=schema,
                    ) if schema else types.GenerateContentConfig(temperature=0.2, max_output_tokens=max_output_tokens),
                )
                candidate = (getattr(response, "candidates", None) or [None])[0]
                finish_obj = getattr(candidate, "finish_reason", None) if candidate is not None else None
                finish_reason = getattr(finish_obj, "name", None) or (str(finish_obj).split(".")[-1] if finish_obj is not None else "UNKNOWN")
                try:
                    text = getattr(response, "text", None)
                except Exception:
                    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
                    text = "".join(str(getattr(part, "text", "") or "") for part in parts)
                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = getattr(usage, "prompt_token_count", None)
                output_tokens = getattr(usage, "candidates_token_count", None)
            if not text:
                if "MAX_TOKENS" in str(finish_reason).upper():
                    raise RuntimeError("Gemini menghentikan output karena MAX_TOKENS. Kurangi jumlah listing per proses atau ringkas narasi.")
                raise RuntimeError("Gemini mengembalikan respons kosong.")
            text = str(text)
            if return_metadata:
                return {"text": text, "finish_reason": str(finish_reason), "prompt_tokens": prompt_tokens, "output_tokens": output_tokens}
            if "MAX_TOKENS" in str(finish_reason).upper():
                raise RuntimeError(f"Gemini menghentikan respons pada MAX_TOKENS ({output_tokens or 'jumlah token tidak tersedia'} token output). JSON mungkin terpotong; bagi narasi menjadi kelompok lebih kecil.")
            return text
        except Exception as exc:
            last_exc = exc
            message = str(exc).lower()
            if "429" in message or "resource_exhausted" in message or "quota" in message:
                raise RuntimeError("Kuota/rate limit Gemini tercapai (429). Tidak dilakukan retry otomatis. Coba setelah kuota reset atau periksa AI Studio Rate Limits.") from exc
            transient = any(x in message for x in ["503", "unavailable", "500", "502", "504", "deadline"])
            if not transient or attempt >= 2: break
            time.sleep((0.8 * (2 ** attempt)) + random.uniform(0, 0.3))
    raise RuntimeError(f"Gemini gagal setelah retry terbatas: {last_exc}") from last_exc


def extract_auction_document(api_key: str, file_bytes: bytes, mime_type: str, filename: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    prepared, prepared_mime = prepare_upload(file_bytes, mime_type)
    prompt = f"""Anda adalah petugas ekstraksi dokumen lelang properti Indonesia. Baca seluruh file {filename}. Ekstrak data lelang dan nilai kondisi fasad YANG TERLIHAT dalam satu respons JSON sesuai skema.
ATURAN TANGGAL WAJIB: ekstrak auction_date (tanggal pelaksanaan lelang) dan deposit_deadline (batas akhir penyetoran uang jaminan) hanya dari tanggal kalender yang tertulis eksplisit. Isi YYYY-MM-DD bila jelas. Salin bukti kutipan persis ke field_evidence.auction_date dan field_evidence.deposit_deadline. Jangan menukar tanggal pengumuman, tanggal batas setor, tanggal lelang, atau batas pelunasan. Jika hanya tertulis relatif seperti H-1 / 1 hari sebelum lelang, jangan hitung sendiri; isi null dan jelaskan di verification_notes. payment_deadline adalah batas pelunasan setelah menang jika tercantum, bukan batas setor jaminan.
DILARANG menebak. Field yang tidak terbaca/tidak tercantum wajib null. Nominal rupiah integer. LT dan LB jangan tertukar. Jangan simpulkan status penghuni, interior, struktur tersembunyi, legalitas terverifikasi, atau status sengketa dari foto. Bedakan fakta terlihat, indikasi, dan hal yang tidak dapat dipastikan. Sertakan kutipan sumber singkat untuk field utama pada field_evidence dengan nama field yang sudah ditentukan skema. Jika informasi bertentangan, masukkan dalam conflicts. Kelipatan bid hanya diisi bila tertulis eksplisit."""
    raw = _client_call(api_key, model, prompt, prepared, prepared_mime, AuctionExtraction, 1700)
    try:
        data = AuctionExtraction.model_validate_json(raw).model_dump()
    except Exception as exc:
        raise RuntimeError(f"JSON hasil ekstraksi tidak sesuai skema: {exc}. Respons awal: {raw[:300]}") from exc
    from core.auction_dates import normalize_auction_date
    data["document_sha256"] = file_sha256(file_bytes)
    data["source_file_name"] = filename
    data["extraction_schema_version"] = "AUCTION_EXTRACT_V2"
    for date_field in ("auction_date", "deposit_deadline", "payment_deadline", "rights_expiry"):
        data[date_field] = normalize_auction_date(data.get(date_field)) if data.get(date_field) else None
    return data


def _normalise_boq_item_name(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _conservative_confidence(*values: Any) -> str:
    """Keep the lowest supplied confidence; AI cannot upgrade hidden evidence."""
    ranks = {"rendah": 0, "sedang": 1, "tinggi": 2}
    clean = [str(v).strip() for v in values if str(v or "").strip().lower() in ranks]
    if not clean:
        return "Rendah"
    return min(clean, key=lambda v: ranks[v.lower()])


def _match_user_boq_row(
    item: dict[str, Any], user_rows: list[dict[str, Any]], matched_codes: set[str]
) -> dict[str, Any] | None:
    """Match Gemini rows to the exact user BoQ row even if the model omits IDs.

    Matching precedence is exact USER_BOQ code, then exact normalized item
    name. We intentionally do not use broad fuzzy matching: a wrong match can
    move a unit/quantity to a different work scope and corrupt the RAB.
    """
    code = str(item.get("item_code") or "").strip()
    if code:
        exact = next((r for r in user_rows if str(r.get("item_code") or "") == code), None)
        if exact and code not in matched_codes:
            return exact
    name = _normalise_boq_item_name(item.get("work_item"))
    if not name:
        return None
    candidates = [
        r for r in user_rows
        if str(r.get("item_code") or "") not in matched_codes
        and _normalise_boq_item_name(r.get("work_item")) == name
    ]
    return candidates[0] if len(candidates) == 1 else None


def renovation_estimate_to_rows(
    data: dict[str, Any],
    quantity_guidance: dict[str, Any] | None = None,
    user_boq_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Map AI price suggestions to a deterministic, user-auditable RAB.

    Priority of quantity evidence: explicit user BoQ > deterministic Python
    catalogue > blank for custom AI scope. Gemini may propose unit rates but
    never overwrite user-entered quantities or invent measurements from photos.
    """
    output: list[dict[str, Any]] = []
    guidance = quantity_guidance or {}
    user_rows = user_boq_rows or []
    user_hints = {str(x.get("item_code")): x for x in user_rows}
    hints = {str(x.get("item_code")): x for x in guidance.get("items", [])}
    ai_items = data.get("items", [])
    matched_user_codes: set[str] = set()

    suppressed_codes: set[str] = set()
    if "VIS_FRONT_ROOF" in hints:
        suppressed_codes.update({"MED_DEM_ROOF", "MED_NEW_ROOF", "LGT_ROOF", "VIS_ROOF_WATERPROOF"})
    if "VIS_DAMP_WALL" in hints:
        suppressed_codes.add("MED_WALL")
    if "VIS_CARPORT_FLOOR" in hints:
        suppressed_codes.update({"MED_FLOOR", "LGT_TILE"})
    if str(guidance.get("category") or "") != "Renovasi Berat":
        suppressed_codes.update({code for code in hints if str(code).startswith("HVY_")})
        suppressed_codes.add("HVY_STRUCT")

    seen_codes: set[str] = set()
    for item in ai_items:
        code = str(item.get("item_code") or "")
        if code in suppressed_codes or (code and code in seen_codes):
            continue
        if code:
            seen_codes.add(code)
        user_hint = user_hints.get(code)
        if user_hint is None:
            user_hint = _match_user_boq_row(item, user_rows, matched_user_codes)
        if user_hint is not None:
            user_code = str(user_hint.get("item_code") or "")
            if user_code in matched_user_codes:
                continue
            matched_user_codes.add(user_code)
            # Normalize the identifier to the stable Python-generated user BoQ ID.
            code = user_code
        hint = user_hint or hints.get(code)
        raw_conservative = item.get("unit_cost_conservative")
        raw_low = item.get("unit_cost_low")
        raw_high = item.get("unit_cost_high")
        conservative = max(0, int(raw_conservative)) if raw_conservative is not None else None
        low = max(0, int(raw_low)) if raw_low is not None else None
        high = max(0, int(raw_high)) if raw_high is not None else None
        if conservative == 0: conservative = None
        if low == 0: low = None
        if high == 0: high = None
        if conservative is not None and low is not None and conservative < low:
            conservative = low
        if high is not None and conservative is not None and high < conservative:
            high = conservative

        if user_hint is not None:
            quantity = user_hint.get("quantity")
            quantity_low = user_hint.get("quantity_low", quantity)
            quantity_high = user_hint.get("quantity_high", quantity)
            unit = user_hint.get("unit")
            quantity_basis = user_hint.get("quantity_basis")
            hint_notes = user_hint.get("notes", "")
            confidence = _conservative_confidence(user_hint.get("confidence"), item.get("confidence"))
            priority = user_hint.get("priority", "Bersyarat")
            evidence_basis = user_hint.get("evidence_basis", "BoQ/dimensi yang diberikan pengguna")
        elif hint is not None:
            quantity = hint.get("quantity_high")
            quantity_low = hint.get("quantity_low")
            quantity_high = hint.get("quantity_high")
            unit = hint.get("unit") or item.get("unit")
            quantity_basis = hint.get("quantity_basis") or item.get("quantity_basis")
            hint_notes = hint.get("notes", "")
            confidence = hint.get("confidence") or item.get("confidence")
            priority = hint.get("priority") or item.get("priority")
            evidence_basis = item.get("evidence_basis")
        else:
            quantity = None
            quantity_low = quantity_high = None
            unit = item.get("unit")
            quantity_basis = "Volume wajib diukur pengguna/kontraktor; AI tidak boleh mengukur skala dari foto."
            hint_notes = "Item tambahan AI di luar katalog kuantitas Python; volume sengaja dikosongkan sampai diukur."
            confidence = item.get("confidence") or "Rendah"
            priority = "Bersyarat"
            evidence_basis = item.get("evidence_basis")

        if quantity is not None and float(quantity) <= 0:
            quantity = None
        notes = [x for x in [item.get("scope_description"), evidence_basis, hint_notes, item.get("rate_basis"), item.get("notes")] if x]
        if item.get("materials_and_labor_included") is not None:
            notes.append("Harga mencakup bahan + upah" if item.get("materials_and_labor_included") else "Harga belum mencakup bahan dan upah secara lengkap; perlu rincian")
        if quantity_low is not None or quantity_high is not None:
            notes.append(f"Rentang volume indikatif: {quantity_low if quantity_low is not None else '—'}–{quantity_high if quantity_high is not None else '—'} {unit or ''}")
        if quantity_basis:
            notes.append(f"Dasar volume: {quantity_basis}")
        if low is not None or conservative is not None or high is not None:
            notes.append(
                f"Harga satuan AI indikatif: rendah {low if low is not None else '—'}; "
                f"konservatif {conservative if conservative is not None else '—'}; "
                f"atas {high if high is not None else '—'} / {unit or 'unit'}; bukan penawaran vendor"
            )
        if confidence:
            notes.append(f"Keyakinan: {confidence}")
        output.append({
            "item_code": code or None,
            "subcategory": (hint.get("subcategory") if hint else None) or (hint.get("group") if hint else None) or item.get("subcategory", ""),
            "work_item": (hint.get("work_item") if hint else None) or item.get("work_item", ""),
            "quantity": quantity, "quantity_low": quantity_low, "quantity_high": quantity_high,
            "quantity_basis": quantity_basis, "unit": unit,
            "unit_cost_low": low, "unit_cost": conservative, "unit_cost_high": high,
            "priority": priority, "conditional": bool(hint.get("conditional", False)) if hint else bool(item.get("conditional", False)),
            "evidence_basis": evidence_basis, "confidence": confidence,
            "rate_basis": item.get("rate_basis"),
            "price_source": "Gemini (estimasi screening; belum diverifikasi lokal)" if conservative is not None else None,
            "materials_and_labor_included": item.get("materials_and_labor_included"),
            "notes": " | ".join(str(x) for x in notes),
        })

    # A model response is not allowed to silently omit a user-supplied BoQ row.
    # Inject every missing line with its exact user quantity and an empty rate.
    # This is preferable to inventing a price or shrinking the user's scope.
    for user_hint in user_rows:
        code = str(user_hint.get("item_code") or "")
        if code in matched_user_codes:
            continue
        output.append({
            "item_code": code, "subcategory": user_hint.get("subcategory") or user_hint.get("group", ""),
            "work_item": user_hint.get("work_item", ""),
            "quantity": user_hint.get("quantity"), "quantity_low": user_hint.get("quantity_low"),
            "quantity_high": user_hint.get("quantity_high"), "quantity_basis": user_hint.get("quantity_basis"),
            "unit": user_hint.get("unit"), "unit_cost_low": None, "unit_cost": None,
            "unit_cost_high": None, "priority": user_hint.get("priority", "Bersyarat"),
            "conditional": bool(user_hint.get("conditional", True)),
            "evidence_basis": "BoQ/dimensi yang diberikan pengguna",
            "confidence": user_hint.get("confidence", "Rendah"), "rate_basis": None, "price_source": None, "materials_and_labor_included": None,
            "notes": str(user_hint.get("notes", "")) + " Harga akan diisi katalog screening Python bila scope dan satuannya cocok; bila tidak cocok, tetap perlu verifikasi manual/quotation.",
        })
    return apply_regional_screening_rates(output)

def estimate_renovation_rab(
    api_key: str,
    files: list[tuple[bytes, str, str]],
    condition_description: str,
    property_context: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Draft a category-driven RAB using property facts, geometry hints and evidence.

    Gemini identifies applicable scopes and evidence. Python provides
    deterministic quantity guidance and versioned unit prices; AI rates are ignored.
    """
    from core.renovation_engine import build_renovation_quantity_guidance, rab_item_is_in_scope, infer_renovation_category, summarize_rab_totals

    description = (condition_description or "").strip()
    selected_files = (files or [])[:6]
    if not description and not selected_files:
        raise ValueError("Unggah minimal satu foto/dokumen survei atau isi deskripsi kondisi rumah.")
    prepared_files: list[tuple[bytes, str]] = []
    file_labels: list[str] = []
    for raw, mime, filename in selected_files:
        prepared, prepared_mime = prepare_upload(raw, mime)
        prepared_files.append((prepared, prepared_mime))
        file_labels.append(filename)
    context = dict(property_context or {})
    user_boq_rows = parse_user_boq_table(description)
    geometry_warnings = check_geometry_assumptions(description, context)
    # The function argument is the authoritative RAB condition narrative. Merge
    # it into the Python guidance context so category/scope inference behaves
    # consistently for every caller, not only when the UI duplicates the field.
    if description and not str(context.get("condition_description") or "").strip():
        context["condition_description"] = description
    guidance = build_renovation_quantity_guidance(context)
    category_warnings: list[str] = []
    selected_category = str(context.get("renovation_category") or "Auto sesuai kondisi umum").strip()
    narrative_category = infer_renovation_category("", "Auto sesuai kondisi umum", description)
    if selected_category and selected_category != "Auto sesuai kondisi umum" and narrative_category not in {"Auto sesuai kondisi umum", selected_category}:
        category_warnings.append(
            f"Pilihan kategori manual adalah {selected_category}, tetapi deskripsi utama menyebut {narrative_category}. Pilihan manual dipakai sebagai override. Pilih 'Auto sesuai kondisi umum' bila ingin kategori mengikuti narasi."
        )
    context_payload = {
        "lokasi": context.get("address") or context.get("district") or "Tidak diketahui",
        "luas_tanah_m2": context.get("land_area"),
        "luas_bangunan_total_m2": context.get("building_area"),
        "jumlah_lantai": context.get("floor_count") or 1,
        "luas_tapak_lantai_dasar_m2": context.get("building_footprint_m2"),
        "dasar_luas_tapak": "Input user bila tersedia; jika tidak Python memperkirakan LB agregat dibagi jumlah lantai",
        "tipe_properti": context.get("property_type"),
        "jumlah_kamar_tidur": context.get("bedrooms"),
        "jumlah_kamar_mandi": context.get("bathrooms"),
        "kondisi_fisik_umum": context.get("physical_condition"),
        "status_hunian_dari_survei_pengguna": context.get("occupancy_status") or "Belum Survei",
        "kategori_lingkup_renovasi": guidance.get("category"),
        "lebar_jalan_m": context.get("road_width_m"),
        "akses_jalan": context.get("access"),
        "konteks_mobilisasi": "Gunakan lebar dan tipe akses untuk memberi catatan biaya mobilisasi/harga satuan, tetapi jangan mengubah volume secara otomatis tanpa dasar.",
        "deskripsi_fasad_dari_survei": context.get("facade_description"),
        "deskripsi_kondisi_dan_scope_dari_pengguna": description,
        "catatan_survei": context.get("survey_notes"),
        "foto_dokumen_yang_dikirim": file_labels,
        "jumlah_baris_boq_pengguna": len(user_boq_rows),
    }
    prompt_parts = [
        "Anda adalah analis scope renovasi rumah tapak di Indonesia. Susun DRAFT lingkup RAB berdasarkan kategori renovasi, data rumah, foto dan deskripsi pengguna. Keluaran JSON mengikuti schema; tanpa markdown. Jangan memberi angka harga satuan: semua rate ditetapkan Python dari pricebook regional berversi atau override manual pengguna.",
        "ATURAN ESTIMASI BERBASIS BUKTI: pahami keseluruhan deskripsi pengguna dan setiap foto sebagai satu rangkaian kondisi, bukan sekadar memilih paket berdasarkan label kosmetik/ringan/sedang/berat. Kategori menunjukkan tingkat kompleksitas, bukan perintah mengganti seluruh elemen bangunan. Buat satu baris untuk setiap pekerjaan yang benar-benar didukung bukti. Anda boleh memakai item_code katalog atau item custom dengan item_code=null jika lingkup spesifik tidak ada di katalog; jangan menghapus pekerjaan spesifik yang disebut pengguna. Hindari dua baris untuk lingkup/permukaan yang sama. Item custom atau item tanpa quantity hint Python harus berstatus Bersyarat sampai volume dan scope disetujui pengguna. Bedakan temuan yang terlihat, dugaan penyebab yang harus diverifikasi, serta kondisi interior/struktur/MEP yang belum terlihat. Untuk foto fasad saja, jangan menyatakan interior/struktur/MEP rusak. Jangan menyimpulkan rumah dihuni, kosong, dijaga atau ditinggalkan dari barang, tanaman, ember, kain, pintu tertutup, atau bagian dalam yang gelap; masukkan status hunian sebagai tidak dapat ditentukan dari foto dan perlu survei/konfirmasi pihak setempat. Jika rembesan/atap bocor tampak, jelaskan kemungkinan area terdampak sebagai skenario inspeksi, bukan fakta. Jumlah kamar tidur bukan jumlah pintu; jumlah kamar mandi bukan bukti seluruh kamar mandi perlu direnovasi. Jika volume tidak punya petunjuk pengukuran dari input user atau katalog Python, quantity=null dan tuliskan cara mengukurnya. Jangan mengubah quantity hint Python berdasarkan perkiraan skala foto. Model tidak boleh menggunakan ukuran gambar/foto sebagai alat ukur.",
        "HARGA SATUAN: Jangan menaksir atau mengisi unit_cost_low, unit_cost_conservative, atau unit_cost_high. Harga akan ditetapkan sepenuhnya oleh Python dari pricebook regional PFMS yang berversi, atau dibiarkan kosong jika item/satuan belum tercakup. Fokus pada pemilihan scope, deskripsi, bukti, volume, satuan, prioritas dan asumsi. Jangan menulis harga yang berubah-ubah. Python menghitung contingency secara terpisah.",
        "KATEGORI DAN SCOPE:",
        "Renovasi Kosmetik: persiapan/proteksi, dinding dan plafon merupakan scope utama saat kategori ini dipilih eksplisit; lantai pilih poles ATAU vinyl/SPC (jangan keduanya); kusen/pintu/aksesori hanya bila dibutuhkan. Jika kondisi hanya disebut siap huni dan kategori Auto, jangan memaksakan pengecatan penuh; cukup rekomendasikan persiapan/inspeksi dan item kosmetik opsional.",
        "Renovasi Ringan: perbaikan lokal atap/nok/talang/lisplang; plafon lokal; keramik lokal; sanitair minor sesuai jumlah kamar mandi bila ada bukti; saklar/stopkontak/lampu lokal; daun pintu/jendela lokal. Python memberi allowance area lokal low-confidence (atap 5–15%, plafon 3–10%, keramik 2–6%); pakai hanya bila kondisi/deskripsi/foto mendukung. Jangan menganggap seluruh atap/MEP diganti.",
        "Renovasi Sedang: perlakukan sebagai beberapa pekerjaan menengah yang bisa lokal maupun menyeluruh. Jangan otomatis membongkar seluruh atap, plafon, lantai, semua kamar mandi, atau seluruh instalasi hanya karena kategori ini dipilih. Jika deskripsi menyebut atap teras/kanopi yang jebol dan katalog menyediakan VIS_FRONT_ROOF, gunakan satu paket itu untuk penutup atap lokal dan flashing; jangan sekaligus menulis MED_DEM_ROOF, MED_NEW_ROOF, LGT_ROOF, atau VIS_ROOF_WATERPROOF untuk area yang sama. Rangka atap dibuat item terpisah VIS_FRONT_ROOF_FRAME berstatus Bersyarat hanya bila inspeksi membuktikan kerangka rusak. Jika dinding carport lembap dan tersedia VIS_DAMP_WALL, gunakan satu item khusus tersebut; jangan juga menambahkan MED_WALL untuk bidang yang sama. Jika deskripsi menyebut warna fasad terlalu mencolok dan tersedia VIS_FACADE_REPAINT, tempatkan pengecatan seluruh fasad sebagai Bersyarat/opsional, dengan pengukuran bidang terpisah dan mengecualikan bidang lembap yang sudah dihitung pada VIS_DAMP_WALL. Jika rabat beton carport retak dan tersedia VIS_CARPORT_FLOOR, jangan tambahkan MED_FLOOR atau pemasangan keramik untuk retakan yang sama. Plafon yang mungkin terdampak dibuat Bersyarat sampai dibuka/diinspeksi. Seluruh baris USER_BOQ yang ditulis eksplisit oleh pengguna wajib masuk sebagai allowance modal dengan prioritas default Disarankan, sekalipun akses inspeksi terbatas. Turunkan confidence menjadi Rendah untuk interior/MEP/struktur tersembunyi, jangan mengklaim kerusakan terbukti, dan biarkan pengguna mengeluarkan baris hanya setelah pemeriksaan menunjukkan tidak diperlukan. Baris visual tambahan di luar BoQ boleh tetap Bersyarat. Struktur dan denah dipertahankan kecuali ada temuan tenaga ahli. Jangan mengklasifikasikan renovasi menjadi berat hanya karena bagian catatan risiko menyebut kemungkinan bergeser ke berat jika temuan tersembunyi kelak terkonfirmasi; gunakan kategori utama yang disebut pengguna dan pisahkan skenario risiko.",
        "LANTAI CARPORT: bila yang terlihat/dideskripsikan adalah rabat beton retak, jangan otomatis memasukkan pemasangan keramik. Susun opsi pemeriksaan retak, tambal lokal, recast/bongkar-pasang atau finishing hanya setelah pengguna mengonfirmasi. Keramik hanya dimasukkan bila kerusakan keramik atau keinginan upgrade disebut eksplisit.",
        "Renovasi Berat: pembongkaran/perubahan ruang, dinding/fasad, atap/lantai/plafon/MEP. Item struktur harus ditandai perlu engineer dan volume/harga null sampai ada desain/perhitungan. Jangan menebak pondasi/kolom/balok/dak dari LT/LB.",
        "Hitung Tanah: pemutusan utilitas, demolisi bangunan, pemuatan/pembuangan puing, land clearing; bukan RAB renovasi. Volume puing sangat kasar dan harus dicek kontraktor.",
        "BOQ TERSTRUKTUR DARI PENGGUNA (jika tersedia):",
        json.dumps(user_boq_rows, ensure_ascii=False, default=str, separators=(",", ":")),
        "ATURAN KHUSUS BOQ PENGGUNA: Jika tabel BoQ di atas berisi baris, keluarkan SATU RenovationRabItem untuk SETIAP item_code USER_BOQ yang diberikan, jangan menghilangkan baris dan jangan mengganti kuantitasnya. Gunakan item_code yang sama persis. Quantity yang ditulis pengguna adalah data sumber dan Python akan mempertahankannya. JANGAN MENAKSIR ATAU MENGISI HARGA SATUAN. Isi unit_cost_low, unit_cost_conservative, unit_cost_high dengan null karena harga ditetapkan deterministik oleh pricebook Python atau override manual yang dikunci pengguna. Isi item_code USER_BOQ persis sama seperti pada input; jangan menghilangkannya. Jangan hanya mengembalikan satu atau dua baris. Jelaskan lingkup kerja dan apakah secara teknis bahan+upah biasanya termasuk dalam pekerjaan tersebut; jangan mengarang tarif atau menyebut angka sebagai HSPK/SSH/quotation. Hanya beri catatan jika pekerjaan benar-benar membutuhkan gambar/inspeksi teknis (misalnya struktur tersembunyi). Jangan mengubah volume pengguna berdasarkan foto atau luas properti lain. Jika ada dua lingkup yang mungkin tumpang tindih, jelaskan dalam notes agar pengguna meninjau agar tidak double-count.",
        "KONTEKS PROPERTI:", json.dumps(context_payload, ensure_ascii=False, default=str),
        "KATALOG KUANTITAS PYTHON (gunakan item_code persis, jangan menghitung ulang quantity):",
        json.dumps(guidance, ensure_ascii=False, default=str, separators=(",", ":")),
        "DESKRIPSI KONDISI TERKINI:", description or "Tidak ada deskripsi; gunakan hanya hal yang terlihat dari foto.",
        "KELUARAN TAMBAHAN WAJIB: visual_findings memuat elemen dan kerusakan yang benar-benar tampak; likely_causes_to_verify berisi kemungkinan penyebab dengan bahasa dugaan; interior_unknowns memuat hal yang tidak terlihat; occupancy_unknowns menyatakan status hunian tidak dapat disimpulkan dari foto tampak depan; inspection_plan berupa urutan pemeriksaan praktis. interior_scenarios maksimal 2 skenario biaya (misalnya interior relatif normal dan ditemukan kerusakan sedang/air merembes), biaya skenario harus dipisahkan dari total RAB dasar dan tidak otomatis dianggap biaya aktual/pekerjaan wajib. Untuk foto fasad saja confidence skenario interior maksimal Rendah. Sertakan assumptions dan overall_note.",
    ]
    prompt = "\n\n".join(prompt_parts)
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=RenovationRabExtraction, max_output_tokens=8192, extra_files=prepared_files)
    try:
        parsed = RenovationRabExtraction.model_validate_json(raw)
    except Exception as exc:
        raise RuntimeError(f"JSON RAB Gemini tidak sesuai schema: {exc}. Respons: {raw[:500]}") from exc
    data = parsed.model_dump()
    # Occupancy must never be inferred from facade imagery or belongings.
    # Preserve the survey status as user-supplied evidence; if no survey exists,
    # make the uncertainty explicit even when the model omits the field.
    occupancy_status = str(context.get("occupancy_status") or "Belum Survei").strip()
    occupancy_notes = list(data.get("occupancy_unknowns") or [])
    if occupancy_status.lower() in {"", "belum survei", "belum diketahui", "belum disurvei"}:
        occupancy_notes.append(
            "Status hunian tidak dapat dipastikan dari foto tampak depan. Verifikasi melalui survei lapangan dan konfirmasi RT/pengelola/penghuni sebelum keputusan investasi."
        )
    else:
        occupancy_notes.append(
            f"Status hunian dicatat dari pilihan survei pengguna: {occupancy_status}. Ini bukan kesimpulan AI dari foto."
        )
    data["occupancy_unknowns"] = list(dict.fromkeys(str(x) for x in occupancy_notes if str(x).strip()))
    data["quantity_guidance"] = guidance
    data["category"] = guidance.get("category")
    data["category_basis"] = guidance.get("category_basis")
    editor_rows = renovation_estimate_to_rows(data, guidance, user_boq_rows)
    returned_codes = {str(r.get("item_code")) for r in data.get("items", []) if r.get("item_code")}
    missing_required = []
    guidance_codes = {str(x.get("item_code") or "") for x in guidance.get("items", [])}
    suppressed_guidance_codes: set[str] = set()
    if "VIS_FRONT_ROOF" in guidance_codes:
        suppressed_guidance_codes.update({"MED_DEM_ROOF", "MED_NEW_ROOF", "LGT_ROOF"})
    if "VIS_DAMP_WALL" in guidance_codes:
        suppressed_guidance_codes.add("MED_WALL")
    if "VIS_CARPORT_FLOOR" in guidance_codes:
        suppressed_guidance_codes.update({"MED_FLOOR", "LGT_TILE"})
    if guidance.get("category") != "Renovasi Berat":
        suppressed_guidance_codes.update(code for code in guidance_codes if code.startswith("HVY_"))
    # Do not append generic visual rows when the user's explicit BoQ already
    # budgets the same surface/scope. This is a scope-deduplication rule, not
    # a locality/condition inference.
    boq_text = " ".join(str(r.get("work_item") or "") for r in user_boq_rows).lower()
    boq_scope_rules = {
        "VIS_FRONT_ROOF": (r"kanopi|atap teras|atap depan", r"bongkar|pasang|penggantian|galvalum|spandek|flashing"),
        # A new canopy installation explicitly includes its frame; do not append
        # a second speculative frame-replacement line from the photo guidance.
        "VIS_FRONT_ROOF_FRAME": (r"kanopi|atap teras|atap depan", r"rangka", r"pasang|pemasangan|ganti|penggantian|baru"),
        "VIS_DAMP_WALL": (r"dinding|rembes|lembap|jamur", r"waterproof|anti.?rembes|rembes|jamur|pengikisan|kupas"),
        "VIS_FRONT_CLEAN": (r"pembersihan|peti kayu|sampah|barang bekas",),
        "VIS_CARPORT_FLOOR": (r"keramik|ubin|lantai carport|rabat beton",),
        "VIS_FACADE_REPAINT": (r"cat ulang fasad|pengecatan.*fasad|weatherproof",),
        # Explicit gate/railing paint in the user's BoQ replaces the optional
        # visual recommendation for the same surface.
        "VIS_FENCE_PAINT": (r"pagar|teralis", r"cat|pengecatan|amplas"),
    }
    for code, patterns in boq_scope_rules.items():
        if code in guidance_codes and all(re.search(pattern, boq_text, re.I) for pattern in patterns):
            suppressed_guidance_codes.add(code)
    # Apply the same rule to AI-returned guidance codes, not just Python-added
    # rows. This prevents a model response from reintroducing a duplicate.
    editor_rows = [
        row for row in editor_rows
        if not (
            str(row.get("item_code") or "") in suppressed_guidance_codes
            and not str(row.get("item_code") or "").startswith("USER_BOQ_")
        )
    ]
    returned_codes = {str(r.get("item_code")) for r in editor_rows if r.get("item_code")}
    # Never let a missing AI row silently erase a required or visually-triggered
    # work scope. Inject it as a visible unpriced row; the user can measure it,
    # price it, or explicitly mark it conditional/not required after inspection.
    for hint in guidance.get("items", []):
        code = str(hint.get("item_code") or "")
        if not code or code in returned_codes or code in suppressed_guidance_codes:
            continue
        is_required = hint.get("priority") == "Wajib" and not hint.get("conditional")
        is_evidence_specific = code.startswith("VIS_") or code.startswith("INSPECT_")
        if not (is_required or is_evidence_specific):
            continue
        if is_required:
            missing_required.append(hint.get("work_item", code))
        editor_rows.append({
            "item_code": code, "work_item": hint.get("work_item"),
            "quantity_low": hint.get("quantity_low"),
            "quantity": hint.get("quantity_base") if hint.get("quantity_base") is not None else hint.get("quantity_high"),
            "quantity_high": hint.get("quantity_high"), "quantity_basis": hint.get("quantity_basis"),
            "unit": hint.get("unit"), "unit_cost_low": None, "unit_cost": None,
            "unit_cost_high": None, "priority": hint.get("priority", "Bersyarat"),
            "conditional": bool(hint.get("conditional", False)),
            "evidence_basis": "Temuan visual/deskripsi dan katalog Python",
            "confidence": hint.get("confidence", "Rendah"),
            "notes": (
                "Scope wajib dari katalog belum diberi harga oleh AI. Ukur dan isi harga satuan, "
                "atau tandai tidak diperlukan setelah verifikasi. " if is_required else
                "Baris visual/inspeksi dari katalog Python ditampilkan agar tidak hilang bila AI tidak mengembalikannya. "
            ) + str(hint.get("notes", "")),
        })
    from core.renovation_engine import deduplicate_generated_rab_rows
    editor_rows, rab_deduplication = deduplicate_generated_rab_rows(editor_rows, user_boq_rows)
    editor_rows = apply_regional_screening_rates(editor_rows)
    data["rab_deduplication"] = rab_deduplication
    data["editor_rows"] = editor_rows
    data["user_boq_rows"] = user_boq_rows
    data["user_boq_count"] = len(user_boq_rows)
    data["user_boq_model_priced_count"] = sum(1 for r in editor_rows if str(r.get("item_code") or "").startswith("USER_BOQ_") and r.get("unit_cost") not in (None, "") and to_float(r.get("unit_cost")) > 0)
    data["user_boq_unpriced_items"] = [r.get("work_item") for r in editor_rows if str(r.get("item_code") or "").startswith("USER_BOQ_") and (r.get("unit_cost") in (None, "") or to_float(r.get("unit_cost")) <= 0)]
    data["ai_rab_rows_received"] = len(data.get("items", []))
    data["user_boq_rows_mapped"] = sum(1 for r in editor_rows if str(r.get("item_code") or "").startswith("USER_BOQ_"))
    data["geometry_warnings"] = geometry_warnings
    data["category_warnings"] = category_warnings
    # The Python screening catalogue can complete a missing Gemini rate. Only
    # retain this warning when quantity or the final base rate is still absent.
    unresolved_required = [
        str(r.get("work_item") or r.get("item_code") or "Scope wajib")
        for r in editor_rows
        if str(r.get("priority") or "").lower() == "wajib"
        and not bool(r.get("conditional", False))
        and (to_float(r.get("quantity")) <= 0 or to_float(r.get("unit_cost")) <= 0)
    ]
    data["items_to_inspect"] = [
        x for x in (data.get("items_to_inspect") or [])
        if not str(x).lower().startswith("scope wajib belum diberi harga oleh ai:")
    ]
    if unresolved_required:
        data["items_to_inspect"].append("Scope wajib masih belum memiliki volume/harga dasar: " + "; ".join(unresolved_required))
    # One shared Python summary function is reused after manual and AI rate edits.
    # This keeps subtotals and completeness flags in sync with the editable rows.
    data.update(summarize_rab_totals(data["editor_rows"]))
    data["files_used"] = file_labels
    data["interior_scenario_cost_is_separate"] = True
    data["pricing_basis_disclosure"] = (
        f"Harga proyek hanya memakai katalog screening deterministik PFMS versi {PRICE_CATALOG_VERSION}; Gemini tidak menjadi sumber angka unit rate. "
        "Katalog ini adalah allowance bahan+upah spesifikasi ekonomis-menengah, bukan HSPK resmi, SSH all-in, atau quotation kontraktor. "
        "Perbup Sidoarjo No. 27 Tahun 2025 (SSH TA 2026), Perbup No. 75 Tahun 2025 dan Permen PUPR No. 8 Tahun 2023 dipakai sebagai referensi kerangka/komponen, bukan klaim bahwa tarif paket rumah pribadi identik. Verifikasi minimal dua quotation lokal."
    )
    data["estimation_basis"] = (
        "RAB underwriting rumah lelang: baris BoQ eksplisit pengguna masuk sebagai allowance modal meski interior/komponen tersembunyi belum dapat diinspeksi; "
        "volume pengguna dipertahankan; harga hanya disediakan pricebook regional deterministik dengan rentang rendah/dasar/atas; item yang belum tercakup pricebook harus diisi dari quotation/override manual, bukan harga AI; pekerjaan struktural/volume yang sungguh tak dapat ditaksir tetap memerlukan inspeksi/quotation. "
        "Baris dapat dikeluarkan hanya setelah pengguna menilai scope tidak diperlukan. Cadangan kondisi tersembunyi dihitung terpisah pada modal proyek jika interior belum diinspeksi."
    )
    data["interior_scenario_note"] = (
        "Skenario interior adalah sensitivitas tambahan di luar item yang sudah tercantum dalam BoQ. Jangan menjumlahkannya lagi untuk pekerjaan yang sama; "
        "item plafon, cat, listrik atau sanitair yang sudah ada di BoQ telah masuk sebagai allowance dasar. Sisa risiko tak terduga tercakup oleh cadangan kondisi tersembunyi."
    )
    data["assumptions"] = list(data.get("assumptions", [])) + guidance.get("warnings", []) + geometry_warnings + category_warnings + [guidance.get("method_note", "")]
    return data

def estimate_missing_boq_unit_rates(
    api_key: str,
    rows: list[dict[str, Any]],
    property_context: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Run a focused, user-triggered second pass for BoQ rows lacking rates.

    It estimates unit rates only; user quantities and scope are never changed.
    This optional call is separate from the initial multimodal RAB request so a
    long visual analysis cannot crowd out pricing every supplied BoQ line.
    """
    candidates = [
        r for r in (rows or [])
        if str(r.get("item_code") or "").startswith("USER_BOQ_")
        and (r.get("unit_cost") in (None, "") or to_float(r.get("unit_cost")) <= 0)
    ]
    if not candidates:
        return {"items": [], "requested_count": 0, "priced_count": 0}
    context = property_context or {}
    payload = [{
        "item_code": r.get("item_code"),
        "group": r.get("subcategory") or r.get("group"),
        "work_item": r.get("work_item"),
        "quantity_for_context_only": r.get("quantity"),
        "unit": r.get("unit"),
        "scope_basis": r.get("quantity_basis"),
        "priority": r.get("priority"),
        "existing_notes": r.get("notes"),
    } for r in candidates]
    prompt = (
        "Anda estimator awal renovasi rumah tinggal di Indonesia. Taksir HARGA SATUAN (bukan total) "
        "untuk setiap baris BoQ berikut. Kembalikan tepat satu baris per item_code dengan item_code sama persis. "
        "Konteks wilayah: " + str(context.get("location") or context.get("district") or "Indonesia") + ". "
        "Properti: " + json.dumps({k: context.get(k) for k in ["land_area", "building_area", "property_type", "floor_count", "road_width_m", "access"]}, ensure_ascii=False, default=str) + ". "
        "Berikan unit_cost_low, unit_cost_conservative, dan unit_cost_high yang konsisten low <= conservative <= high. "
        "unit_cost_conservative adalah angka utama yang akan dipakai Python. Satuan harus mengikuti input (m2, m', titik, unit, ls). "
        "Estimasi harus mempertimbangkan lingkup yang tertulis, bahan, upah, alat, pembuangan, sambungan, akses/mobilisasi bila relevan. "
        "Jelaskan komponen dan asumsi di rate_basis/notes; jelaskan apakah bahan dan upah termasuk. "
        "Jangan mengklaim harga sebagai HSPK/SSH resmi, harga vendor aktual, atau harga terkini terverifikasi karena tidak ada price book/quotation yang dilampirkan. "
        "Gunakan confidence Rendah bila hanya berdasarkan pengetahuan umum. Untuk pekerjaan struktur tersembunyi atau scope yang tidak dapat dinilai, kembalikan null dan jelaskan alasannya. "
        "Jangan mengubah kuantitas atau mengarang lingkup baru. JSON saja sesuai schema.\n\nBOQ:\n" +
        json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    )
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=RenovationBoqRateResult, max_output_tokens=3500)
    parsed = RenovationBoqRateResult.model_validate_json(raw)
    by_code = {str(x.item_code): x.model_dump() for x in parsed.items}
    output = []
    for row in candidates:
        item = by_code.get(str(row.get("item_code")))
        if not item:
            continue
        low = item.get("unit_cost_low")
        mid = item.get("unit_cost_conservative")
        high = item.get("unit_cost_high")
        low = max(0, int(low)) if low is not None else None
        mid = max(0, int(mid)) if mid is not None else None
        high = max(0, int(high)) if high is not None else None
        if low == 0: low = None
        if mid == 0: mid = None
        if high == 0: high = None
        if mid is not None and low is not None and mid < low: mid = low
        if high is not None and mid is not None and high < mid: high = mid
        output.append({
            "item_code": str(row.get("item_code")),
            "unit_cost_low": low,
            "unit_cost": mid,
            "unit_cost_high": high,
            "rate_basis": item.get("rate_basis"),
            "materials_and_labor_included": item.get("materials_and_labor_included"),
            "confidence": item.get("confidence") or "Rendah",
            "notes": item.get("notes") or "Estimasi harga satuan screening dari Gemini; verifikasi dengan price book/quotation lokal.",
        })
    return {"items": output, "requested_count": len(candidates), "priced_count": sum(1 for x in output if x.get("unit_cost") is not None)}


def review_investment(api_key: str, model: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "property": snapshot.get("property", {}), "market": snapshot.get("market", {}),
        "bidding": snapshot.get("bidding", {}), "at_limit": snapshot.get("at_limit", {}),
        "decision": snapshot.get("decision", {}), "funding": snapshot.get("funding", {}),
        "risks": snapshot.get("risk_register", []),
    }
    prompt = """Bertindak sebagai reviewer underwriting properti lelang Indonesia. Audit analisis Python berikut. Jangan hitung ulang atau mengubah angka. Jangan mengarang data. Pisahkan fakta, asumsi, risiko dan verifikasi yang masih diperlukan. Jika decision status HOLD/DO NOT BID, jangan menyarankan bidding. Jawab bahasa Indonesia secara ringkas dalam JSON dengan keys: overall_review, strengths (array), critical_risks (array), before_bid_checklist (array), challenge_to_assumptions (array), recommendation (BUY_ONLY_IF|HOLD|DO_NOT_BID). JSON input berikut: """ + json.dumps(compact, ensure_ascii=False, default=str)
    from pydantic import BaseModel, ConfigDict, Field
    class Review(BaseModel):
        overall_review: str
        strengths: list[str] = Field(default_factory=list)
        critical_risks: list[str] = Field(default_factory=list)
        before_bid_checklist: list[str] = Field(default_factory=list)
        challenge_to_assumptions: list[str] = Field(default_factory=list)
        recommendation: str
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=Review, max_output_tokens=1200)
    try: return Review.model_validate_json(raw).model_dump()
    except Exception as exc: raise RuntimeError(f"Review AI tidak valid: {exc}") from exc



def build_ai_feasibility_brief(api_key: str, model: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Create a senior-analyst style feasibility brief from Python-calculated facts.

    Gemini interprets, challenges and explains the supplied evidence. It must not
    invent or recompute financial figures and does not make the Owner's decision.
    """
    market = snapshot.get("market", {}) or {}
    at_limit = snapshot.get("at_limit", {}) or {}
    decision = snapshot.get("decision", {}) or {}
    # Give Gemini the small, auditable evidence set, not just market aggregates.
    # URLs and listing labels are user-provided inputs and are not independently
    # verified by the language model.
    comparable_rows = []
    for row in list(market.get("valid") or [])[:15]:
        comparable_rows.append({key: row.get(key) for key in (
            "name", "address", "price", "negotiated_price", "price_type",
            "land_area", "building_area", "condition", "source_platforms",
            "source_url", "source_url_scope", "date_found", "listing_date",
            "distance_km", "similarity_score", "proximity_score",
            "market_segment", "missing_quality_fields",
        ) if row.get(key) not in (None, "", [])})
    liquidity = snapshot.get("liquidity", {}) or {}
    compact = {
        "property": snapshot.get("property", {}),
        "survey": snapshot.get("survey", {}),
        "legal": snapshot.get("legal", {}),
        "owner_valuation": snapshot.get("owner_valuation", {}),
        "market": {
            "base_exit": market.get("base_exit"),
            "conservative_exit": market.get("conservative_exit"),
            "market_range_low": market.get("market_range_low"),
            "market_range_high": market.get("market_range_high"),
            "fmv_as_is": market.get("fmv_as_is"),
            "arv_after_repair": market.get("arv_after_repair"),
            "matched_comparables": market.get("arv_condition_comparable_count"),
            "comparable_pool_count": market.get("comparable_pool_count"),
            "confidence_index": market.get("confidence"),
            "confidence_is_not_probability": True,
            "valuation_is_provisional": market.get("valuation_is_provisional"),
            "exit_value_source": market.get("exit_value_source"),
            "quality_notes": market.get("quality_notes", []),
            "comparable_observations_for_review": comparable_rows,
        },
        "costs": snapshot.get("costs", {}),
        "at_limit_python_result": at_limit,
        "scenario_results_python": snapshot.get("feasibility_scenarios", []),
        "mao": snapshot.get("mao", {}),
        "risk_register": snapshot.get("risk_register", []),
        "risk_summary_python": snapshot.get("risk_summary", {}),
        "funding": snapshot.get("funding", {}),
        "cash_timing": {
            "cash_available_now": liquidity.get("cash_available_for_new_project"),
            "cash_available_at_auction": liquidity.get("cash_available_for_new_project_at_auction"),
            "expected_cash_amount": liquidity.get("expected_cash_amount"),
            "expected_cash_date": liquidity.get("expected_cash_date"),
            "expected_cash_status": liquidity.get("expected_cash_status"),
            "expected_cash_is_provisional": liquidity.get("expected_cash_is_provisional"),
            "expected_cash_after_auction": liquidity.get("expected_cash_after_auction"),
        },
        "decision_engine_reference": decision,
    }
    prompt = (
        "Anda adalah Analis Senior investasi properti lelang Indonesia yang bekerja sebagai AI Feasibility Co-Pilot. "
        "Pemilik/Owner adalah pengambil keputusan akhir; jangan bertindak sebagai hakim, polisi, atau veto otomatis. "
        "Susun feasibility brief strategis dari data JSON. Telaah listing comparable satu per satu sebelum menerima agregat; "
        "bedakan listing asking price dari transaksi terkonfirmasi dan sebutkan keterbatasan URL/tanggal/similarity. "
        "Bedakan FAKTA INPUT, ASUMSI OWNER, HASIL HITUNG PYTHON, INFERENSI ANALITIS, dan DATA YANG BELUM TERSEDIA. "
        "Jangan mengarang data pasar, transaksi, kondisi legal/fisik, "
        "atau angka. Jangan menghitung ulang angka keuangan; gunakan nilai Python apa adanya. Bila angka tidak ada, tulis "
        "'belum tersedia'. Analisis kelebihan, friksi yang bisa diberi harga, risiko yang tidak dapat dimitigasi, skenario "
        "cepat/moderat/tekanan, sensitivitas, strategi MAO/walk-away, dan pilihan Owner: GO, CONDITIONAL GO, HOLD, SKIP. "
        "Jelaskan bahwa status referensi sistem bukan keputusan Owner dan Bid Readiness berbeda dari daya tarik investasi. "
        "Jika SKPT/KPKNL ditandai sudah diperiksa, perlakukan sebagai verifikasi yang dinyatakan Owner, namun jangan "
        "menyimpulkan jaminan absolut tidak ada gugatan. Jangan mendorong bidding jika hard stop yang telah dikonfirmasi. "
        "Bahasa Indonesia yang jelas, ringkas tetapi bernas, seperti memo analis senior.\n\nDATA JSON:\n"
        + json.dumps(compact, ensure_ascii=False, default=str)
    )
    from pydantic import BaseModel, Field
    class FeasibilityBrief(BaseModel):
        executive_summary: str
        financial_assessment: str
        market_assessment: str
        execution_assessment: str
        scenario_assessment: list[str] = Field(default_factory=list)
        strengths: list[str] = Field(default_factory=list)
        value_drivers: list[str] = Field(default_factory=list)
        key_risks: list[str] = Field(default_factory=list)
        mitigations: list[str] = Field(default_factory=list)
        assumptions_to_validate: list[str] = Field(default_factory=list)
        owner_options: list[str] = Field(default_factory=list)
        reference_recommendation: str
        recommendation_rationale: str
        owner_decision_authority: str = "Keputusan akhir berada pada Owner."
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=FeasibilityBrief, max_output_tokens=2800)
    try:
        result = FeasibilityBrief.model_validate_json(raw).model_dump()
    except Exception as exc:
        raise RuntimeError(f"AI Feasibility Brief tidak valid: {exc}") from exc

    # Keep the narrative model's recommendation coherent with confirmed facts
    # and Python safety signals. This remains a reference recommendation; the
    # Owner's separately recorded decision is not changed here.
    allowed = {"GO", "CONDITIONAL GO", "HOLD", "DO NOT BID", "SKIP", "REVIEW"}
    recommendation = str(result.get("reference_recommendation") or "REVIEW").strip().upper()
    if recommendation not in allowed:
        recommendation = "REVIEW"
        result["recommendation_rationale"] = (
            str(result.get("recommendation_rationale") or "")
            + " Rekomendasi AI dinormalisasi menjadi REVIEW karena label di luar pilihan yang didukung."
        ).strip()
    hard_stops = list(decision.get("hard_stops") or [])
    python_profit = at_limit.get("net_profit")
    python_roi = at_limit.get("roi_pct")
    if hard_stops and recommendation not in {"DO NOT BID", "SKIP"}:
        recommendation = "DO NOT BID"
        result["recommendation_rationale"] = (
            "Python mencatat hard stop terkonfirmasi. AI tidak boleh merekomendasikan bidding selama hard stop tersebut belum diselesaikan. "
            + str(result.get("recommendation_rationale") or "")
        ).strip()
    elif (python_profit is None or python_roi is None) and recommendation in {"GO", "CONDITIONAL GO"}:
        recommendation = "HOLD"
        result["recommendation_rationale"] = (
            "Profit/ROI belum dapat dihitung dari data Python, sehingga rekomendasi investasi belum dapat dinaikkan menjadi GO. "
            + str(result.get("recommendation_rationale") or "")
        ).strip()
    result["reference_recommendation"] = recommendation
    return result

def review_portfolio(api_key: str, model: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = "Anda reviewer portofolio. Pilih maksimal satu property_id atau HOLD_ALL. Dilarang mengubah status hard-stop Python. Utamakan perlindungan modal, kecukupan kas, kualitas bukti pasar dan risiko aktif. eligibility_index bukan probabilitas. JSON kandidat: " + json.dumps(candidates[:8], ensure_ascii=False, default=str)
    from pydantic import BaseModel, ConfigDict, Field
    class PortfolioReview(BaseModel):
        recommendation: str
        selected_property_id: Optional[str] = None
        reason: str
        risks: list[str] = Field(default_factory=list)
        conditions: list[str] = Field(default_factory=list)
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=PortfolioReview, max_output_tokens=800)
    data = PortfolioReview.model_validate_json(raw).model_dump()
    allowed = {str(x.get("property_id")) for x in candidates}
    if data["recommendation"] not in {"HOLD_ALL", "SELECT_ONE"}: data["recommendation"] = "HOLD_ALL"
    if data["recommendation"] == "SELECT_ONE":
        selected = next((x for x in candidates if str(x.get("property_id")) == str(data.get("selected_property_id"))), None)
        if not selected or selected.get("decision_status") not in {"GO", "CONDITIONAL GO"}:
            data.update(recommendation="HOLD_ALL", selected_property_id=None, reason="AI memilih kandidat yang tidak memenuhi hard gate Python; hasil diubah menjadi HOLD_ALL.")
    return data


def _standard_condition(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip().lower()
    if any(x in text for x in ["hitung tanah", "tanah kosong", "land only"]):
        return "Hitung Tanah"
    if any(x in text for x in ["butuh renovasi", "perlu renovasi", "rusak berat", "perlu perbaikan"]):
        return "Butuh Renovasi"
    if any(x in text for x in ["siap huni", "ready to move", "layak huni"]):
        return "Siap Huni"
    # Do not infer "Siap Huni" solely from phrases such as "full renovasi".
    return None


def _standard_price_type(value: Optional[str]) -> str:
    if not value:
        return "Asking aktif"
    text = value.strip().lower()
    if any(x in text for x in ["over kredit", "oper kredit", "take over", "take-over", "lanjut cicilan", "alih debitur"]):
        return "Over kredit / skema kewajiban"
    if any(x in text for x in ["transaksi terverifikasi", "verified transaction", "harga transaksi"]):
        return "Transaksi terverifikasi"
    if any(x in text for x in ["marked sold", "perlu verifikasi", "ditandai terjual", "terjual"]):
        return "Marked sold / perlu verifikasi"
    return "Asking aktif"


def _standard_certificate(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip().lower().replace(" ", "")
    if "shm" in text or "hakmilik" in text:
        return "SHM"
    if "shgb" in text or "hgb" in text or "hakgunabangunan" in text:
        return "SHGB"
    return value.strip()


def _standard_optional_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    from datetime import datetime
    text = value.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _standard_access(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip().lower()
    if "2 mobil" in text or "dua mobil" in text or "double car" in text:
        return "2 Mobil"
    if "1 mobil" in text or "satu mobil" in text or "single car" in text:
        return "1 Mobil"
    if "gang" in text or "motor" in text or "pedestrian" in text:
        return "Gang"
    return None


def _unescape_markdown_punctuation(text: str) -> str:
    """Undo Markdown backslash escaping before heading/URL detection and AI parsing."""
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~:])", r"\1", str(text or ""))


def _detect_numbered_listing_sections(text: str) -> list[str]:
    r"""Split top-level headings including Markdown-escaped ``1\.`` numbering."""
    text = _unescape_markdown_punctuation(text)
    lines = text.splitlines()
    heading = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*(\d{1,2})(?:[.)]|\\\.)\s+(.+?)\s*(?:\*\*|__)?\s*$")
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = heading.match(line)
        if match:
            starts.append((index, int(match.group(1))))
    # A title such as "10 Listing Pembanding Terpercaya" may be detected as
    # a heading numbered 10. Ignore preamble candidates before the first real
    # listing numbered 1, then require a clean 1..N sequence.
    first_listing_pos = next((i for i, (_, number) in enumerate(starts) if number == 1), None)
    candidate_starts = starts[first_listing_pos:] if first_listing_pos is not None else starts
    candidate_numbers = [number for _, number in candidate_starts]
    if len(candidate_starts) >= 2 and candidate_numbers == list(range(1, len(candidate_starts) + 1)):
        sections = []
        for pos, (line_index, _) in enumerate(candidate_starts):
            end = candidate_starts[pos + 1][0] if pos + 1 < len(candidate_starts) else len(lines)
            block = "\n".join(lines[line_index:end]).strip()
            if block:
                sections.append(block)
        return sections
    return [text.strip()] if text.strip() else []


def _classify_source_url_scope(url: str) -> str:
    """Conservative classification; a portal/category page is not a listing detail."""
    from urllib.parse import urlparse
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    if not host:
        return "Tidak diketahui"
    if "/venue/" in path:
        return "Halaman venue/kompleks"
    if "/view/" in path or any(x in path for x in ["/iklan/", "/listing/", "/property/", "/properti/", "/rumah-dijual/"]):
        return "Listing individual"
    if path in {"", "/"}:
        return "Portal/domain only"
    if "kgmid=" in query or any(x in path for x in ["/search", "/q/", "/sidoarjo_g", "/properti"]):
        return "Portal pencarian/kategori"
    if "trovit" in host or ("olx" in host and ("q=" in query or "/q/" in path)):
        return "Portal pencarian/kategori"
    return "Perlu verifikasi"


def _extract_section_urls(section: str) -> list[str]:
    """Extract exact URLs and labelled bare domains without inventing listing paths.

    A bare portal domain is normalized to its HTTPS homepage and classified as
    portal/domain-only, never promoted to an individual listing URL.
    """
    from urllib.parse import urlparse
    section = _unescape_markdown_punctuation(section)
    found = re.findall(r"https?://[^\s<>\]\)]+", section, flags=re.IGNORECASE)
    if not found:
        labelled = re.search(
            r"URL\s*(?:individual)?\s*(?:valid)?\s*[:.]?\s*((?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s<>\])]+)?)",
            section, flags=re.IGNORECASE,
        )
        if labelled:
            candidate = labelled.group(1).rstrip(".,;:!?'\"*_")
            found = [candidate if candidate.lower().startswith(("http://", "https://")) else "https://" + candidate]
    urls: list[str] = []
    for raw in found:
        url = raw.strip().rstrip(".,;:!?\"'")
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower()
        if host in {"google.com", "www.google.com"} and "kgmid=" in url.lower():
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _comparable_prompt(sections: list[str], start_index: int) -> str:
    manifest = "\n".join(
        f"{start_index + offset}: {block.splitlines()[0].strip()[:140]}"
        for offset, block in enumerate(sections)
    )
    numbered_blocks = "\n\n".join(
        f"[LISTING {start_index + offset}]\n{block}"
        for offset, block in enumerate(sections)
    )
    return (
        "Ekstrak listing properti Indonesia menjadi JSON ringkas sesuai schema. "
        "SATU judul bernomor = SATU rumah = SATU item. Semua bullet, alamat, harga, spesifikasi, fasilitas, legalitas, agen dan portal dalam blok sama adalah satu properti. "
        f"Jumlah item wajib {len(sections)} dengan indeks global: {', '.join(str(start_index+i) for i in range(len(sections)))}. "
        "Gunakan indeks i persis sesuai [LISTING]. Jangan memecah bullet atau menggabungkan listing. "
        "Ekstrak hanya fakta tertulis. Tidak ada/ambigu = null; array sumber kosong bila tidak disebut. "
        "p=harga penawaran/transaksi rupiah integer; nj=NJOP total pembanding rupiah integer hanya bila tertulis; lt/lb=m2; kt/km=jumlah kamar. LT dan LB jangan tertukar. "
        "c hanya Siap Huni, Butuh Renovasi, Hitung Tanah jika eksplisit; frasa 'full renovasi' masuk cd/nt dan bukan otomatis siap huni. "
        "ac hanya 2 Mobil, 1 Mobil, Gang jika eksplisit; lebar jalan tulis di ad. Hook/carport tidak membuktikan akses. "
        "Sumber platform masuk src. Jangan membuat URL/tanggal publikasi; URL dipasangkan Python dari teks asli. "
        "pt: Asking aktif untuk harga penawaran/nego; Marked sold / perlu verifikasi bila disebut terjual tanpa bukti; Transaksi terverifikasi hanya bila harga final eksplisit. Jika harga berupa DP + pengambilalihan sisa cicilan/over kredit, tandai 'Over kredit / skema kewajiban' dan jangan setarakan dengan harga jual tunai. "
        "Simpan arah hadap, listrik, air, jumlah lantai, carport, dimensi, agen, kode listing dan fasilitas ringkas di nt (maksimal 180 karakter). "
        "Kembalikan JSON saja, tanpa penjelasan panjang.\n\nURUTAN BLOK:\n" + manifest + "\n\nTEKS ASLI:\n" + numbered_blocks
    )


def _parse_comparable_response(raw_result: Any, expected_count: int, start_index: int) -> ComparableExtraction:
    metadata = raw_result if isinstance(raw_result, dict) and "text" in raw_result else {"text": raw_result, "finish_reason": "UNKNOWN"}
    raw = str(metadata.get("text") or "")
    finish_reason = str(metadata.get("finish_reason") or "UNKNOWN").upper()
    if "MAX_TOKENS" in finish_reason:
        raise RuntimeError(
            f"Output Gemini terpotong karena MAX_TOKENS pada kelompok listing mulai nomor {start_index}. "
            "Tidak ada data parsial dimasukkan ke tabel. Bagi narasi menjadi kelompok lebih kecil."
        )
    try:
        parsed = ComparableExtraction.model_validate_json(raw)
    except Exception as exc:
        error_text = str(exc).lower()
        if any(marker in error_text for marker in ["unexpected end", "eof", "json_invalid", "unterminated string"]):
            raise RuntimeError(
                f"JSON Gemini terpotong/tidak selesai pada kelompok listing mulai nomor {start_index}. "
                "Respons tidak dimasukkan ke tabel agar data tidak bergeser. Coba parse maksimal 3–4 listing per sekali proses."
            ) from exc
        raise RuntimeError(f"JSON comparable Gemini tidak sesuai schema: {exc}. Respons awal: {raw[:350]}") from exc
    if len(parsed.items) != expected_count:
        raise RuntimeError(
            f"Gemini mengembalikan {len(parsed.items)} baris, sedangkan kelompok ini berisi {expected_count} listing. "
            "Tabel tidak diisi agar bullet tidak salah dianggap sebagai properti."
        )
    expected_indices = list(range(start_index, start_index + expected_count))
    indexed = {item.source_index: item for item in parsed.items if item.source_index is not None}
    if len(indexed) == expected_count and set(indexed) == set(expected_indices):
        parsed.items = [indexed[i] for i in expected_indices]
    else:
        supplied = [item.source_index for item in parsed.items if item.source_index is not None]
        if supplied and supplied != expected_indices:
            raise RuntimeError(f"Nomor listing dari Gemini tidak cocok dengan urutan input {expected_indices}; tabel tidak diisi.")
    return parsed


def _extract_area_range_midpoint(section: str, label: str) -> tuple[float, float, float] | None:
    """Return low, high and midpoint for an explicitly stated LT/LB range."""
    text = _unescape_markdown_punctuation(section)
    pattern = (
        rf"\b{re.escape(label)}\s*[:=]?\s*"
        r"(\d+(?:[.,]\d+)?)\s*(?:-|–|—|s\.d\.|hingga)\s*"
        r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²)?"
    )
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    low = float(match.group(1).replace(",", "."))
    high = float(match.group(2).replace(",", "."))
    if low <= 0 or high <= 0 or high < low:
        return None
    return low, high, round((low + high) / 2, 2)


def _detect_market_segment(section: str, price_type: str = "") -> str:
    """Separate new developer supply from resale evidence when the text says so."""
    text = _unescape_markdown_punctuation(section).lower()
    if price_type == "Over kredit / skema kewajiban" or re.search(r"rumah\s+second|secondary|resale|rumah\s+bekas|sudah\s+renovasi|baru\s+direnovasi", text):
        return "Secondary / resale"
    if re.search(r"rumah\s+baru|unit\s+baru|proyek\s+baru|primary|developer|unit\s+resmi\s+klaster|dalam\s+pembangunan", text):
        return "Primary / developer"
    return "Tidak diketahui"


def parse_comparable_narrative(api_key: str, narrative: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Parse numbered multi-listing prose into one row per property.

    Markdown headings and URLs are detected from original text. The response schema
    uses compact keys and a larger output allowance to avoid incomplete JSON.
    """
    text = _unescape_markdown_punctuation((narrative or "").strip())
    if len(text) < 40:
        raise ValueError("Teks comparable terlalu pendek. Tempel uraian listing yang lebih lengkap.")
    sections = _detect_numbered_listing_sections(text)
    expected_count = len(sections)
    if expected_count > 10:
        raise ValueError("Maksimal 10 listing per satu proses pada mode Free Tier. Bagi narasi menjadi dua kelompok.")
    rows: list[dict[str, Any]] = []
    all_notes: list[str] = []
    # Use 4-item chunks only for larger inputs. Typical 5–7 listing input takes
    # one or two requests and stays within the free-tier request cadence.
    batch_size = 4 if expected_count > 5 else 5
    for offset in range(0, expected_count, batch_size):
        section_batch = sections[offset:offset + batch_size]
        start_index = offset + 1
        prompt = _comparable_prompt(section_batch, start_index)
        raw_result = _client_call(
            api_key, model, prompt, schema=ComparableExtraction,
            max_output_tokens=4096, return_metadata=True
        )
        parsed = _parse_comparable_response(raw_result, len(section_batch), start_index)
        all_notes.extend(parsed.parsing_notes or [])
        for local_index, item in enumerate(parsed.items):
            global_index = start_index + local_index
            row = item.model_dump()
            row["source_index"] = global_index
            row["condition"] = _standard_condition(item.condition)
            row["access"] = _standard_access(item.access)
            row["certificate"] = _standard_certificate(item.certificate)
            platforms = [x.strip() for x in item.source_platforms if x and x.strip()]
            row["source_platforms"] = "; ".join(dict.fromkeys(platforms))
            urls = _extract_section_urls(section_batch[local_index])
            row["source_url"] = urls[0] if urls else ""
            row["source_evidence"] = ("Platform disebut: " + "; ".join(dict.fromkeys(platforms))) if platforms else ""
            if urls:
                url_evidence = "URL dari teks: " + " ; ".join(urls)
                row["source_evidence"] = (row["source_evidence"] + " | " + url_evidence).strip(" |")
                if len(urls) > 1:
                    row["notes"] = ((row.get("notes") or "").strip() + " | URL lain: " + " ; ".join(urls[1:])).strip(" |")
            row["source_url_scope"] = _classify_source_url_scope(row.get("source_url")) if row.get("source_url") else "Tidak ada URL langsung"
            row["complex_name"] = item.complex_name or ""
            lb_range = _extract_area_range_midpoint(section_batch[local_index], "LB")
            lt_range = _extract_area_range_midpoint(section_batch[local_index], "LT")
            if lb_range:
                row["building_area"] = lb_range[2]
                range_note = f"LB ditulis rentang {lb_range[0]:g}–{lb_range[1]:g} m²; midpoint {lb_range[2]:g} m² dipakai untuk normalisasi dan tetap perlu diverifikasi."
                row["notes"] = ((row.get("notes") or "").strip() + " | " + range_note).strip(" |")
            if lt_range:
                row["land_area"] = lt_range[2]
                range_note = f"LT ditulis rentang {lt_range[0]:g}–{lt_range[1]:g} m²; midpoint {lt_range[2]:g} m² dipakai untuk normalisasi dan tetap perlu diverifikasi."
                row["notes"] = ((row.get("notes") or "").strip() + " | " + range_note).strip(" |")
            row["orientation"] = item.orientation or ""
            row["electricity_watt"] = item.electricity_watt
            row["water_source"] = item.water_source or ""
            section_text = section_batch[local_index].lower()
            is_overcredit = bool(re.search(
                r"over\s*kredit|oper\s*kredit|ganti\s*dp|lanjut\s*cicilan|ambil\s*alih.{0,30}cicilan|take[- ]over|alih\s*debitur",
                section_text,
            ))
            row["price_type"] = "Over kredit / skema kewajiban" if is_overcredit else _standard_price_type(item.price_type)
            row["market_segment"] = _detect_market_segment(section_batch[local_index], row["price_type"])
            row["njop"] = item.njop
            row["listing_date"] = _standard_optional_date(item.listing_date)
            from datetime import date
            row["date_found"] = date.today().isoformat()
            row["date_found_basis"] = "Tanggal diproses sistem; bukan tanggal publikasi listing"
            row["adjustment_pct"] = 0.0
            row["parse_source"] = "Gemini narrative parser"
            rows.append(row)
    if len(rows) != expected_count:
        raise RuntimeError(f"Hasil parsing tidak lengkap: {len(rows)} dari {expected_count} listing. Tidak ada data yang dimasukkan ke tabel.")
    from datetime import date
    captured = date.today().isoformat()
    return {
        "items": rows,
        "parsing_notes": all_notes,
        "captured_at": captured,
        "count": len(rows),
        "detected_sections": expected_count,
        "api_calls": (expected_count + batch_size - 1) // batch_size,
    }



def assess_market_with_ai(
    api_key: str,
    model: str,
    subject: dict[str, Any],
    comparables: list[dict[str, Any]],
    python_market_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Review comparable quality and propose bounded, evidence-based adjustments.

    Gemini is not asked to invent a final ARV or transaction prices. Python remains
    responsible for the numeric valuation. Suggestions are advisory and require
    explicit user application in the comparable table.
    """
    rows = [dict(x) for x in (comparables or []) if isinstance(x, dict)]
    if not rows:
        raise ValueError("Belum ada data listing untuk dievaluasi.")
    if len(rows) > 20:
        raise ValueError("Evaluasi AI dibatasi 20 listing per permintaan. Pilih/pecah data menjadi kelompok yang lebih kecil.")
    compact_rows = []
    for idx, row in enumerate(rows, start=1):
        compact_rows.append({
            "source_index": idx, "name": row.get("name"), "address": row.get("address"),
            "complex_name": row.get("complex_name"), "price_rp": row.get("price"),
            "price_type": row.get("price_type"), "land_area_m2": row.get("land_area"),
            "building_area_m2": row.get("building_area"), "bedrooms": row.get("bedrooms"),
            "bathrooms": row.get("bathrooms"), "condition": row.get("condition"),
            "condition_detail": row.get("condition_detail"), "access": row.get("access"),
            "access_detail": row.get("access_detail"), "certificate": row.get("certificate"),
            "njop_rp": row.get("njop"), "listing_date": row.get("listing_date"),
            "date_found": row.get("date_found"), "source_platforms": row.get("source_platforms"),
            "source_url_scope": row.get("source_url_scope"), "notes": row.get("notes"),
        })
    prompt = f"""Anda adalah analis pasar properti residensial Indonesia. Lakukan peer review terhadap data pembanding yang diberikan.

OBJEK TARGET (fakta yang diberikan pengguna):
{json.dumps(subject, ensure_ascii=False, default=str)}

HASIL AWAL PYTHON (untuk mengkritisi, bukan untuk ditiru):
{json.dumps(python_market_result or {}, ensure_ascii=False, default=str)}

DATA COMPARABLE (source_index adalah nomor baris; jangan mengubah identitas):
{json.dumps(compact_rows, ensure_ascii=False, default=str)}

ATURAN KETAT:
1. Gunakan hanya fakta yang ada pada input. Jangan membuat transaksi, harga deal, tanggal, ukuran, kondisi, lokasi, atau URL baru.
2. Harga listing bukan harga transaksi. Harga bertanda sold tanpa bukti tetap tidak terverifikasi.
3. Nilai setiap listing terhadap properti target: kemiripan lokasi, LT/LB, tipe, kondisi, legalitas, akses, dan kualitas sumber.
4. Berikan suggested_adjustment_pct terhadap HARGA PEMBANDING agar lebih setara dengan target: positif bila pembanding terlihat inferior sehingga harga pembanding perlu dinaikkan; negatif bila pembanding superior sehingga harga pembanding perlu diturunkan.
5. Hanya sarankan penyesuaian jika perbedaannya eksplisit pada input. Jika datanya tidak cukup, adjustment harus 0 dan jelaskan data gap. Jangan menyamarkan ketidaktahuan sebagai presisi. Batas penyesuaian -20% sampai +20%.
6. Tandai exclude_from_primary hanya untuk listing yang jelas duplikat, beda segmen/lokasi secara material, harga tidak masuk akal dibanding input lain, atau bukan properti pembanding. Jelaskan alasannya. Jangan mengecualikan hanya karena datanya tidak lengkap; turunkan relevance dan catat gap.
7. Jangan menghitung atau mengusulkan ARV akhir, jangan menyebut angka transaksi aktual yang tidak tersedia. Tugas Python menghitung dari data yang telah ditinjau.
8. relevance_score adalah skor kualitas/kecocokan relatif 0-100, bukan probabilitas.
9. Output satu item untuk setiap source_index yang relevan, tanpa mengarang listing baru.

Berikan overall_assessment singkat, market_segment jika bisa disimpulkan, faktor pendorong nilai dan limitations."""
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=MarketIntelligenceReview, max_output_tokens=2400)
    try:
        result = MarketIntelligenceReview.model_validate_json(str(raw)).model_dump()
    except Exception as exc:
        raise RuntimeError(f"Hasil evaluasi pasar AI tidak sesuai skema: {exc}. Respons awal: {str(raw)[:350]}") from exc
    seen = set()
    clean_items = []
    for item in result.get("items", []):
        idx = int(item.get("source_index") or 0)
        if idx < 1 or idx > len(rows) or idx in seen:
            continue
        seen.add(idx)
        item["suggested_adjustment_pct"] = max(-20.0, min(20.0, float(item.get("suggested_adjustment_pct") or 0)))
        clean_items.append(item)
    result["items"] = clean_items
    result["model"] = model or DEFAULT_MODEL
    result["input_count"] = len(rows)
    result["returned_count"] = len(clean_items)
    result["warning"] = "Saran AI bukan data transaksi atau appraisal. Periksa alasan setiap penyesuaian sebelum menerapkannya; Python tetap menghitung ARV."
    return result
