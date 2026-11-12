"""Gemini wrapper: explicit opt-in calls, compact prompts, cache-friendly and 429-safe."""
from __future__ import annotations
import json
from typing import Any

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def _client(api_key: str):
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("Paket google-genai belum terpasang. Jalankan pip install -r requirements.txt.") from exc
    return genai.Client(api_key=api_key)


def classify_gemini_error(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    lower = message.lower()
    if "429" in lower or "resource_exhausted" in lower or "too_many_requests" in lower or "quota" in lower:
        if "requests per day" in lower or "rpd" in lower or "per day" in lower or "quota_exceeded" in lower:
            return "QUOTA_DAILY", "Kuota harian Gemini tercapai. Analisis Python tetap tersedia; periksa AI Studio dan coba lagi setelah kuota reset."
        if "tokens per minute" in lower or "tpm" in lower:
            return "QUOTA_TPM", "Batas token per menit tercapai. Kurangi ukuran dokumen/konteks dan jangan kirim ulang berulang kali."
        return "QUOTA_429", "Gemini menolak permintaan (429). Penyebabnya dapat berupa batas request per menit, token per menit, kuota harian, atau batas project/billing. Periksa AI Studio → Rate limits; jangan tekan ulang berkali-kali. Seluruh kalkulasi dan ranking Python tetap tersedia."
    if "403" in lower or "permission_denied" in lower or "api key" in lower:
        return "AUTH", "API key/proyek Gemini tidak memiliki izin untuk model ini atau belum aktif."
    if "404" in lower or "not_found" in lower:
        return "MODEL", "Model ID tidak ditemukan atau tidak tersedia untuk proyek API ini."
    return "ERROR", f"Gemini gagal: {message[:500]}"


def portfolio_adjudication(api_key: str, model: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """One compact call for a selected shortlist; Python percentages cannot be edited by AI."""
    from google.genai import types
    compact = []
    for c in candidates[:8]:
        compact.append({
            "object_id": c.get("object_id"), "name": c.get("name"), "status_python": c.get("status"),
            "eligibility_index_pct": c.get("score_pct"), "base_roi_pct": c.get("base_roi_pct"),
            "base_profit_idr": c.get("base_profit"), "required_cash_idr": c.get("required_cash"),
            "available_cash_idr": c.get("available_cash"),
            "attractive_bid_idr": c.get("attractive_bid"),
            "recommended_bid_idr": c.get("recommended_bid"),
            "mandatory_stop_from_bid_idr": c.get("stop_from_bid"),
            "market_confidence_pct": c.get("market_confidence"), "holding_months": c.get("holding_months"),
            "hard_blockers": (c.get("blockers") or [])[:5],
        })
    prompt = (
        "Anda adalah reviewer portofolio investasi rumah lelang di Indonesia. Pilih maksimal SATU objek untuk "
        "diprioritaskan atau pilih HOLD_ALL. Gunakan HANYA data JSON berikut. Jangan menghitung ulang atau mengubah "
        "eligibility_index_pct, ROI, profit, kas, atau maximum bid yang dihitung Python. "
        "Jika semua kandidat memiliki HARD BLOCKER kritis (legalitas, identitas, okupansi, pajak, pembanding, kas) "
        "atau tidak memenuhi status GO/CONDITIONAL, pilih HOLD_ALL. Jangan pernah menaikkan GO dari status HOLD/NO-GO. "
        "Index % adalah screening score, bukan probabilitas. Utamakan keamanan modal, kas cukup, kualitas bukti pasar, "
        "dan risiko penguasaan; jangan hanya memilih profit terbesar. Balas JSON valid saja dengan skema: "
        '{"recommendation":"HOLD_ALL|SELECT_ONE","selected_object_id":null,"reason":"...",'
        '"top_risks":["..."],"conditions_before_bid":["..."],"ranking_comment":"..."}.\nDATA:\n'
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    )
    response = _client(api_key).models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=650,
            response_mime_type="application/json",
        ),
    )
    raw = str(getattr(response, "text", "") or "{}").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Some model versions may wrap valid JSON in markdown; strip a single fence.
        cleaned = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
    valid_ids = {str(c.get("object_id")) for c in candidates}
    if data.get("recommendation") not in {"HOLD_ALL", "SELECT_ONE"}:
        data["recommendation"] = "HOLD_ALL"
        data["selected_object_id"] = None
        data["reason"] = "Format rekomendasi AI tidak valid; sistem memakai keputusan aman HOLD_ALL."
    if data.get("recommendation") == "SELECT_ONE" and str(data.get("selected_object_id")) not in valid_ids:
        data["recommendation"] = "HOLD_ALL"
        data["selected_object_id"] = None
        data["reason"] = "Model mengembalikan ID yang tidak ada dalam shortlist; sistem mengubah hasil menjadi HOLD_ALL."
    selected = next((c for c in candidates if str(c.get("object_id")) == str(data.get("selected_object_id"))), None)
    if selected and selected.get("status") in {"HOLD", "NO-GO"}:
        data["recommendation"] = "HOLD_ALL"
        data["selected_object_id"] = None
        data["reason"] = "Kandidat pilihan AI memiliki hard-stop status Python; keputusan aman adalah HOLD_ALL. " + str(data.get("reason", ""))
    return data


def write_investment_memo(api_key: str, model: str, snapshot: dict[str, Any]) -> str:
    from google.genai import types
    # Send a compact, controlled payload rather than all raw records/documents.
    compact = {
        "property": snapshot.get("inputs", {}).get("property", {}),
        "survey": snapshot.get("inputs", {}).get("survey", {}),
        "market": {k: snapshot.get("market", {}).get(k) for k in ["count", "confidence", "conservative_exit", "base_exit", "optimistic_exit"]},
        "decision": snapshot.get("decision", {}),
        "suitability": snapshot.get("suitability", {}),
        "results": snapshot.get("results", {}),
    }
    prompt = (
        "Buat memo investasi ringkas berbahasa Indonesia. Gunakan angka hasil Python sebagai sumber kebenaran; "
        "jangan hitung ulang/mengubah angka. Pisahkan fakta, asumsi, dan data belum terverifikasi. "
        "Jelaskan alasan status, harga exit, risiko, biaya utama, cash requirement, maximum bid, holding, "
        "dan checklist sebelum bidding. Jangan mengarang fakta. Jika HOLD/NO-GO, jangan merekomendasikan bidding.\n"
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    )
    response = _client(api_key).models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=900),
    )
    return str(getattr(response, "text", "") or "Gemini tidak mengembalikan teks.")


def extract_document_with_gemini(api_key: str, model: str, file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Extract the fields needed by the KPKNL form; absent/unclear values must be null."""
    from google.genai import types
    prompt = f"""
    Anda bertugas mengekstrak data dari pengumuman resmi lelang KPKNL pada file {filename}.
    Kembalikan SATU object JSON valid, tanpa markdown dan tanpa penjelasan di luar JSON.
    Jangan mengisi dengan tebakan. Jika tidak tercantum, tidak terbaca, atau ambigu, isi null.
    Nominal rupiah wajib berupa angka integer tanpa pemisah ribuan. Luas adalah angka dalam m2.
    Tanggal gunakan YYYY-MM-DD jika dapat dipastikan.
    Jika dua bagian dokumen saling bertentangan, jangan memilih sendiri: catat keduanya di conflicts.
    
    Gunakan skema berikut:
    {{
      "lot_code": null,
      "auction_office": null,
      "seller": null,
      "auction_type": null,
      "name": null,
      "complex_name": null,
      "auction_date": null,
      "auction_time": null,
      "auction_url": null,
      "auction_limit": null,
      "deposit_amount": null,
      "bid_increment": null,
      "deposit_deadline": null,
      "payment_deadline": null,
      "address": null,
      "district": null,
      "province": null,
      "certificate_type": null,
      "certificate_no": null,
      "rights_expiry": null,
      "land_area": null,
      "building_area": null,
      "njop": null,
      "bedrooms": null,
      "bathrooms": null,
      "property_type": null,
      "auction_object_description": null,
      "property_notes": null,
      "conflicts": [],
      "field_evidence": {{
        "auction_limit": "kutipan singkat persis dari dokumen atau null",
        "deposit_amount": "kutipan singkat persis dari dokumen atau null",
        "address": "kutipan singkat persis dari dokumen atau null",
        "land_area": "kutipan singkat persis dari dokumen atau null",
        "building_area": "kutipan singkat persis dari dokumen atau null",
        "certificate_no": "kutipan singkat persis dari dokumen atau null"
      }},
      "catatan_verifikasi": "peringatan pembacaan atau null"
    }}
    
    Aturan tambahan:
    - auction_type hanya dikategorikan bila jelas sebagai Eksekusi Hak Tanggungan, Eksekusi Pengadilan, AYDA, atau Lelang sukarela; selain itu null.
    - certificate_type hanya SHM, SHGB/HGB, atau hak lain bila jelas; selain itu null.
    - LT dan LB jangan tertukar. Bila hanya LT yang tercantum, building_area harus null.
    - Jangan menyimpulkan NJOP dari nilai limit.
    - Jangan mengekstrak status legalitas terverifikasi, status penghuni, kondisi bangunan, atau checklist survei dari dokumen lelang.
    - Kelipatan/increment bid hanya diisi bila tertulis eksplisit di pengumuman; jangan menebak berdasarkan nilai limit.
    - Jangan mengisi nilai form dengan nol sebagai pengganti data yang tidak ada.
    """
        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
        response = _client(api_key).models.generate_content(
            model=model or DEFAULT_MODEL,
            contents=[prompt, part],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=1500,
                response_mime_type="application/json",
            ),
        )
        return str(getattr(response, "text", "") or "{}")
