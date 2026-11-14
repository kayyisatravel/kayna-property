"""Gemini 3.5 Flash-Lite document parser and optional reviewer."""
from __future__ import annotations
import hashlib, io, json, random, time, re
from typing import Optional, Any
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

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
    """One real-world listing. Fixed fields keep the schema Gemini Developer API compatible."""
    source_index: Optional[int] = None
    name: Optional[str] = None
    address: Optional[str] = None
    complex_name: Optional[str] = None
    price: Optional[int] = None
    land_area: Optional[float] = None
    building_area: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    condition: Optional[str] = None
    condition_detail: Optional[str] = None
    access: Optional[str] = None
    access_detail: Optional[str] = None
    certificate: Optional[str] = None
    orientation: Optional[str] = None
    electricity_watt: Optional[int] = None
    water_source: Optional[str] = None
    source_platforms: list[str] = Field(default_factory=list)
    source_evidence: Optional[str] = None
    source_url: Optional[str] = None
    listing_date: Optional[str] = None
    price_type: Optional[str] = None
    notes: Optional[str] = None


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


def _client_call(api_key: str, model: str, prompt: str, file_bytes: bytes | None = None, mime_type: str | None = None, schema: Any = None, max_output_tokens: int = 1600, extra_files: list[tuple[bytes, str]] | None = None) -> str:
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
    """Split on sequential top-level numbered headings, never on bullet lines."""
    lines = text.splitlines()
    heading = re.compile(r"^\s*(\d{1,2})[.)]\s+(.+?)\s*$")
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
    # A single listing or unnumbered pasted narrative is still sent as one unit.
    return [text.strip()] if text.strip() else []


def parse_comparable_narrative(api_key: str, narrative: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Parse multi-listing prose into exactly one structured row per listing section.

    Missing facts remain null. Source platform names are preserved; URLs and listing
    publication dates are never invented. `date_found` is stamped locally as capture date.
    """
    text = (narrative or "").strip()
    if len(text) < 40:
        raise ValueError("Teks comparable terlalu pendek. Tempel uraian listing yang lebih lengkap.")
    sections = _detect_numbered_listing_sections(text)
    expected_count = len(sections)
    section_manifest = "\n".join(f"BLOK LISTING {i}: {block.splitlines()[0]}" for i, block in enumerate(sections, 1))
    prompt = (
        "Anda adalah data-extraction specialist untuk listing rumah sekunder Indonesia. "
        "Ubah NARASI berikut menjadi JSON terstruktur sesuai schema. Sangat penting: satu listing/rumah "
        "harus menjadi tepat satu item. Jangan membuat satu item untuk setiap bullet atau baris. "
        f"Python telah mendeteksi tepat {expected_count} BLOK LISTING. Anda WAJIB mengembalikan tepat {expected_count} item, "
        "masing-masing satu untuk setiap blok, sesuai urutan. Field source_index diisi nomor blok mulai 1. "
        "Jangan membuat item tambahan dari bullet, subjudul, sumber portal, atau spesifikasi. "
        "Gabungkan seluruh bullet sampai blok bernomor berikutnya sebagai satu properti. "
        "Jangan memecah alamat, harga, spesifikasi, legalitas, fasilitas, dan sumber menjadi record terpisah. "
        "Jangan menggabungkan dua listing berbeda.\n\n"
        "Daftar blok yang diharapkan:\n" + section_manifest + "\n\n"
        "Aturan ekstraksi: harga rupiah sebagai integer tanpa pemisah; LT/LB dalam m2 sebagai angka; "
        "jangan tertukar. Bila LB tidak dicantumkan isi null, bukan 0. Kamar tidur/kamar mandi angka bila jelas. "
        "condition hanya isi 'Siap Huni', 'Butuh Renovasi', atau 'Hitung Tanah' jika benar-benar eksplisit; "
        "bila hanya disebut 'full renovasi', tulis itu dalam condition_detail dan biarkan condition null. "
        "access hanya isi '2 Mobil', '1 Mobil', atau 'Gang' bila ada bukti jelas; selain itu null. "
        "Jangan menyimpulkan akses jalan dari kata hook, carport, atau lokasi perumahan. Sertifikat hanya "
        "isi bila disebut eksplisit. Ambil platform sumber dan nama agen persis dari narasi. Jangan membuat "
        "URL listing jika tidak diberikan. Jangan membuat tanggal publikasi jika tidak disebut. "
        "Harga penawaran/nego yang masih dipasarkan diklasifikasikan 'Asking aktif'. Listing yang disebut "
        "sudah terjual tetapi belum ada bukti transaksi diklasifikasikan 'Marked sold / perlu verifikasi'. "
        "Hanya bukti transaksi final yang eksplisit menjadi 'Transaksi terverifikasi'. Simpan fasilitas, arah "
        "hadap, kode listing, dan detail lain di notes. Data tidak ada = null atau array kosong.\n\n"
        "NARASI LISTING:\n" + text
    )
    raw = _client_call(api_key, model, prompt, schema=ComparableExtraction, max_output_tokens=2400)
    try:
        parsed = ComparableExtraction.model_validate_json(raw)
    except Exception as exc:
        raise RuntimeError(f"JSON comparable dari Gemini tidak sesuai schema: {exc}. Respons: {raw[:500]}") from exc

    if len(parsed.items) != expected_count:
        raise RuntimeError(
            f"Gemini mengembalikan {len(parsed.items)} baris, sedangkan sistem mendeteksi {expected_count} blok listing. "
            "Tabel tidak diisi agar bullet tidak salah dianggap sebagai properti. Coba parse ulang atau pisahkan judul tiap listing dengan nomor 1., 2., 3."
        )
    indexed = {item.source_index: item for item in parsed.items if item.source_index is not None}
    if indexed and (len(indexed) != expected_count or set(indexed) != set(range(1, expected_count + 1))):
        raise RuntimeError("Nomor blok dari Gemini tidak konsisten. Tabel tidak diisi agar data tidak tertukar.")
    ordered_items = [indexed[i] for i in range(1, expected_count + 1)] if indexed else parsed.items

    from datetime import date
    captured = date.today().isoformat()
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(ordered_items, 1):
        platforms = [x.strip() for x in item.source_platforms if x and x.strip()]
        row = item.model_dump()
        row["source_index"] = index
        row["condition"] = _standard_condition(item.condition)
        row["access"] = _standard_access(item.access)
        row["certificate"] = _standard_certificate(item.certificate)
        row["source_platforms"] = "; ".join(dict.fromkeys(platforms))
        row["source_url"] = item.source_url or ""
        row["price_type"] = _standard_price_type(item.price_type)
        row["listing_date"] = _standard_optional_date(item.listing_date)
        row["date_found"] = captured
        row["date_found_basis"] = "Tanggal diproses sistem; bukan tanggal publikasi listing"
        row["adjustment_pct"] = 0.0
        row["parse_source"] = "Gemini narrative parser"
        # Human-readable evidence provenance; never present a source platform as a direct URL.
        row["source_evidence"] = item.source_evidence or ""
        rows.append(row)

    return {"items": rows, "parsing_notes": parsed.parsing_notes, "captured_at": captured, "count": len(rows), "detected_sections": expected_count}
