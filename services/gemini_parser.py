"""Gemini 3.5 Flash-Lite document parser and optional reviewer."""
from __future__ import annotations
import hashlib, io, json, random, time
from typing import Optional, Any
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

DEFAULT_MODEL = "gemini-3.5-flash-lite"

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
    field_evidence: dict[str, Optional[str]] = Field(default_factory=dict)
    verification_notes: Optional[str] = None


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


def _client_call(api_key: str, model: str, prompt: str, file_bytes: bytes | None = None, mime_type: str | None = None, schema: Any = None, max_output_tokens: int = 1600) -> str:
    if not api_key: raise RuntimeError("GEMINI_API_KEY belum dikonfigurasi di Streamlit Secrets.")
    from google import genai
    from google.genai import types
    contents: Any = prompt
    if file_bytes is not None:
        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type or "application/octet-stream")
        contents = [prompt, part]
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
                text = getattr(response, "text", None)
            if not text: raise RuntimeError("Gemini mengembalikan respons kosong.")
            return str(text)
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
    prompt = f"""Anda adalah petugas ekstraksi dokumen lelang properti Indonesia. Baca file {filename}. Ekstrak data lelang dan nilai kondisi fasad YANG TERLIHAT dalam satu respons JSON sesuai skema. DILARANG menebak. Field yang tidak terbaca/tidak tercantum wajib null. Nominal rupiah integer. LT dan LB jangan tertukar. Jangan simpulkan status penghuni, interior, struktur tersembunyi, legalitas terverifikasi, atau status sengketa dari foto. Bedakan fakta terlihat, indikasi, dan hal yang tidak dapat dipastikan. Sertakan kutipan sumber singkat untuk field utama pada field_evidence. Jika informasi bertentangan, masukkan dalam conflicts. Kelipatan bid hanya diisi bila tertulis eksplisit."""
    raw = _client_call(api_key, model, prompt, prepared, prepared_mime, AuctionExtraction, 1700)
    try:
        data = AuctionExtraction.model_validate_json(raw).model_dump()
    except Exception as exc:
        raise RuntimeError(f"JSON hasil ekstraksi tidak sesuai skema: {exc}. Respons awal: {raw[:300]}") from exc
    data["document_sha256"] = file_sha256(file_bytes)
    return data


def review_investment(api_key: str, model: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "property": snapshot.get("property", {}), "market": snapshot.get("market", {}),
        "bidding": snapshot.get("bidding", {}), "at_limit": snapshot.get("at_limit", {}),
        "decision": snapshot.get("decision", {}), "funding": snapshot.get("funding", {}),
        "risks": snapshot.get("risk_register", []),
    }
    prompt = """Bertindak sebagai reviewer underwriting properti lelang Indonesia. Audit analisis Python berikut. Jangan hitung ulang atau mengubah angka. Jangan mengarang data. Pisahkan fakta, asumsi, risiko dan verifikasi yang masih diperlukan. Jika decision status HOLD/DO NOT BID, jangan menyarankan bidding. Jawab bahasa Indonesia secara ringkas dalam JSON dengan keys: overall_review, strengths (array), critical_risks (array), before_bid_checklist (array), challenge_to_assumptions (array), recommendation (BUY_ONLY_IF|HOLD|DO_NOT_BID). JSON input berikut: """ + json.dumps(compact, ensure_ascii=False, default=str)
    from pydantic import BaseModel, Field
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


def review_portfolio(api_key: str, model: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = "Anda reviewer portofolio. Pilih maksimal satu property_id atau HOLD_ALL. Dilarang mengubah status hard-stop Python. Utamakan perlindungan modal, kecukupan kas, kualitas bukti pasar dan risiko aktif. eligibility_index bukan probabilitas. JSON kandidat: " + json.dumps(candidates[:8], ensure_ascii=False, default=str)
    from pydantic import BaseModel, Field
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
