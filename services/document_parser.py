"""Local document text extraction: no Gemini token usage."""
from __future__ import annotations
from io import BytesIO


def extract_text(file_bytes: bytes, filename: str) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(file_bytes))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            return f"Ekstraksi PDF lokal gagal: {exc}"
    if suffix in {"txt", "md", "csv"}:
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            return f"File teks gagal dibaca: {exc}"
    return "Format belum didukung ekstraksi lokal. Gunakan file PDF atau TXT, atau ekstraksi AI secara manual jika kuota tersedia."
