"""Gemini 3.5 Flash-Lite document parser and optional reviewer."""
from __future__ import annotations
import hashlib, io, json, random, time, re
from typing import Optional, Any
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL = "gemini-3.5-flash-lite"

class FieldEvidence(BaseModel):
    """Explicit evidence fields; avoid dynamic dict/additionalProperties in Gemini schema."""
    lot_code: Optional[str] = None
    name: Optional[str] = None
    auction_office: Optional[str] = None
    seller: Optional[str] = None
    auction_date: Optional[str] = None
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


class RenovationRabItem(BaseModel):
    """One draft renovation work item; conservative unit cost is used by Python."""
    work_item: str
    scope_description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_cost_low: Optional[int] = None
    unit_cost_conservative: Optional[int] = None
    priority: Optional[str] = None
    evidence_basis: Optional[str] = None
    confidence: Optional[str] = None
    notes: Optional[str] = None


class RenovationRabExtraction(BaseModel):
    items: list[RenovationRabItem] = Field(default_factory=list)
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
    prompt = f"""Anda adalah petugas ekstraksi dokumen lelang properti Indonesia. Baca file {filename}. Ekstrak data lelang dan nilai kondisi fasad YANG TERLIHAT dalam satu respons JSON sesuai skema. DILARANG menebak. Field yang tidak terbaca/tidak tercantum wajib null. Nominal rupiah integer. LT dan LB jangan tertukar. Jangan simpulkan status penghuni, interior, struktur tersembunyi, legalitas terverifikasi, atau status sengketa dari foto. Bedakan fakta terlihat, indikasi, dan hal yang tidak dapat dipastikan. Sertakan kutipan sumber singkat untuk field utama pada field_evidence dengan nama field yang sudah ditentukan skema. Jika informasi bertentangan, masukkan dalam conflicts. Kelipatan bid hanya diisi bila tertulis eksplisit."""
    raw = _client_call(api_key, model, prompt, prepared, prepared_mime, AuctionExtraction, 1700)
    try:
        data = AuctionExtraction.model_validate_json(raw).model_dump()
    except Exception as exc:
        raise RuntimeError(f"JSON hasil ekstraksi tidak sesuai skema: {exc}. Respons awal: {raw[:300]}") from exc
    data["document_sha256"] = file_sha256(file_bytes)
    return data


def renovation_estimate_to_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Map Gemini RAB output into the editable Streamlit renovation table.

    `unit_cost` is deliberately populated with the conservative upper estimate;
    all rows remain drafts until the user reviews and applies them.
    """
    output: list[dict[str, Any]] = []
    for item in data.get("items", []):
        raw_high = item.get("unit_cost_conservative")
        raw_low = item.get("unit_cost_low")
        high = max(0, int(raw_high)) if raw_high is not None else None
        low = max(0, int(raw_low)) if raw_low is not None else None
        if high == 0: high = None
        if low == 0: low = None
        if high is not None and low is not None and high < low:
            high = low  # enforce that the conservative unit rate is never below the low estimate
        quantity = item.get("quantity")
        if quantity is not None and float(quantity) <= 0:
            quantity = None
        notes = [x for x in [item.get("scope_description"), item.get("evidence_basis"), item.get("notes")] if x]
        if low is not None or high is not None:
            notes.append(f"Kisaran indikatif: {low if low is not None else '—'}–{high if high is not None else '—'} / {item.get('unit') or 'unit'}")
        if item.get("confidence"):
            notes.append(f"Keyakinan estimasi: {item['confidence']}")
        output.append({
            "work_item": item.get("work_item", ""),
            "quantity": quantity,
            "unit": item.get("unit"),
            "unit_cost_low": low,
            "unit_cost": high,
            "unit_cost_high": high,
            "priority": item.get("priority"),
            "evidence_basis": item.get("evidence_basis"),
            "confidence": item.get("confidence"),
            "notes": " | ".join(str(x) for x in notes),
        })
    return output


def estimate_renovation_rab(
    api_key: str,
    files: list[tuple[bytes, str, str]],
    condition_description: str,
    property_context: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Create an AI-assisted draft RAB from survey images/PDF and user descriptions.

    The AI may only price visible/user-described work. Hidden structural/interior
    defects must be flagged for inspection rather than invented as certain repairs.
    """
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
    context = property_context or {}
    context_payload = {
        "lokasi": context.get("address") or context.get("district") or "Tidak diketahui",
        "luas_tanah_m2": context.get("land_area"),
        "luas_bangunan_m2": context.get("building_area"),
        "jenis_bangunan": context.get("property_type"),
        "kondisi_umum_survei": context.get("physical_condition"),
        "foto_dokumen_yang_dikirim": file_labels,
    }
    prompt = (
        "Anda adalah estimator awal pekerjaan renovasi rumah di Indonesia. Buat DRAFT RAB terperinci dalam JSON sesuai schema. "
        "Gunakan hanya bukti yang tampak pada foto/dokumen dan deskripsi kondisi yang diberikan pengguna. "
        "Satu baris untuk satu pekerjaan, bukan satu baris untuk setiap foto. Prioritaskan pekerjaan wajib agar rumah aman, "
        "berfungsi dan layak dipasarkan. Tambahkan pekerjaan kosmetik hanya jika terlihat/dijelaskan atau tandai sebagai opsional. "
        "JANGAN menganggap atap, pondasi, struktur, instalasi listrik, pipa, plafon atau interior rusak jika tidak tampak/disebut. "
        "Untuk bagian tersembunyi yang tidak dapat dinilai, jangan buat biaya seolah-olah kerusakannya pasti; masukkan ke items_to_inspect. "
        "Buat kuantitas sebagai estimasi awal dari data LT/LB/foto hanya bila dapat diperkirakan; bila tidak, quantity=null dan jelaskan pengukuran yang dibutuhkan. "
        "Berikan unit_cost_low dan unit_cost_conservative (batas atas rasional) dalam rupiah per satuan, termasuk material+upah bila relevan. "
        "Harga satuan hanya ESTIMASI INDIKATIF, bukan penawaran kontraktor atau harga pasar real-time; gunakan perkiraan konservatif wajar untuk wilayah Sidoarjo/Jawa Timur bila lokasi cocok, "
        "dan nyatakan ketidakpastiannya. Jangan mengarang sumber/vendor. Python akan memakai unit_cost_conservative sebagai dasar awal dan menambah contingency terpisah. "
        "Jangan memasukkan contingency ke item RAB agar tidak dihitung dua kali. Bedakan priority Wajib/Disarankan/Opsional, confidence Tinggi/Sedang/Rendah, "
        "dan evidence_basis hanya Fakta visual / Deskripsi pengguna / Asumsi kuantitas. Data yang tidak diketahui bukan nol dan bukan kerusakan pasti. "
        "Jika foto hanya fasad, batasi item pada pekerjaan yang terlihat dan pekerjaan yang secara eksplisit dijelaskan pengguna. "
        "Jangan memberi kepastian bahwa struktur aman hanya dari foto. Bahasa Indonesia, ringkas tetapi terukur.\n\n"
        "KONTEKS OBJEK:\n" + json.dumps(context_payload, ensure_ascii=False, default=str) +
        "\n\nDESKRIPSI KONDISI TERKINI DARI PENGGUNA:\n" + (description or "Tidak ada deskripsi tertulis; gunakan foto hanya untuk temuan visual.")
    )
    raw = _client_call(api_key, model or DEFAULT_MODEL, prompt, schema=RenovationRabExtraction, max_output_tokens=2800, extra_files=prepared_files)
    try:
        parsed = RenovationRabExtraction.model_validate_json(raw)
    except Exception as exc:
        raise RuntimeError(f"JSON RAB Gemini tidak sesuai schema: {exc}. Respons: {raw[:500]}") from exc
    data = parsed.model_dump()
    data["editor_rows"] = renovation_estimate_to_rows(data)
    complete_low = [r for r in data["editor_rows"] if r.get("quantity") is not None and r.get("unit_cost_low") is not None]
    complete_high = [r for r in data["editor_rows"] if r.get("quantity") is not None and r.get("unit_cost") is not None]
    data["total_low_indicative"] = round(sum(r["quantity"] * r["unit_cost_low"] for r in complete_low)) if complete_low else None
    data["total_conservative_indicative"] = round(sum(r["quantity"] * r["unit_cost"] for r in complete_high)) if complete_high else None
    data["unpriced_items"] = [r.get("work_item", "Pekerjaan tanpa nama") for r in data["editor_rows"] if r.get("quantity") is None or r.get("unit_cost") is None]
    data["total_conservative_complete"] = len(data["unpriced_items"]) == 0 and bool(data["editor_rows"])
    data["files_used"] = file_labels
    data["estimation_basis"] = "Draft AI berdasarkan foto/deskripsi pengguna; harga satuan indikatif dan wajib diverifikasi." 
    return data


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


def _detect_numbered_listing_sections(text: str) -> list[str]:
    """Split top-level numbered listing headings, including Markdown bold/link headings."""
    lines = text.splitlines()
    heading = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*(\d{1,2})[.)]\s+(.+?)\s*(?:\*\*|__)?\s*$")
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = heading.match(line)
        if match:
            starts.append((index, int(match.group(1))))
    if len(starts) >= 2 and [number for _, number in starts] == list(range(1, len(starts) + 1)):
        sections = []
        for pos, (line_index, _) in enumerate(starts):
            end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
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
    if any(x in path for x in ["/iklan/", "/listing/", "/property/", "/properti/", "/rumah-dijual/"]):
        return "Listing individual"
    if "kgmid=" in query or path in {"", "/"} or any(x in path for x in ["/search", "/q/", "/sidoarjo_g", "/properti"]):
        return "Portal pencarian/kategori"
    if "trovit" in host or ("olx" in host and ("q=" in query or "/q/" in path)):
        return "Portal pencarian/kategori"
    return "Perlu verifikasi"


def _extract_section_urls(section: str) -> list[str]:
    """Extract exact URLs from user text; exclude Google knowledge-panel/search links."""
    from urllib.parse import urlparse
    found = re.findall(r"https?://[^\s<>\]\)]+", section, flags=re.IGNORECASE)
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
        "p=harga rupiah integer; lt/lb=m2; kt/km=jumlah kamar. LT dan LB jangan tertukar. "
        "c hanya Siap Huni, Butuh Renovasi, Hitung Tanah jika eksplisit; frasa 'full renovasi' masuk cd/nt dan bukan otomatis siap huni. "
        "ac hanya 2 Mobil, 1 Mobil, Gang jika eksplisit; lebar jalan tulis di ad. Hook/carport tidak membuktikan akses. "
        "Sumber platform masuk src. Jangan membuat URL/tanggal publikasi; URL dipasangkan Python dari teks asli. "
        "pt: Asking aktif untuk harga penawaran/nego; Marked sold / perlu verifikasi bila disebut terjual tanpa bukti; Transaksi terverifikasi hanya bila harga final eksplisit. "
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


def parse_comparable_narrative(api_key: str, narrative: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Parse numbered multi-listing prose into one row per property.

    Markdown headings and URLs are detected from original text. The response schema
    uses compact keys and a larger output allowance to avoid incomplete JSON.
    """
    text = (narrative or "").strip()
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
            row["orientation"] = item.orientation or ""
            row["electricity_watt"] = item.electricity_watt
            row["water_source"] = item.water_source or ""
            row["price_type"] = _standard_price_type(item.price_type)
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

