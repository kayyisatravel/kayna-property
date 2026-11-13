from __future__ import annotations
import json, math, re
from datetime import date, datetime
from typing import Any


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        value = value.replace("Rp", "").replace("rp", "").replace(" ", "")
        if "," in value and "." in value:
            value = value.replace(".", "").replace(",", ".")
        elif "," in value:
            value = value.replace(",", ".")
        elif value.count(".") > 1:
            value = value.replace(".", "")
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy values and non-finite numbers to strict JSON values."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    # Handle pandas/numpy scalar values without requiring either package here.
    if hasattr(value, "item") and callable(value.item):
        try:
            scalar = value.item()
            if scalar is not value:
                return _json_safe(scalar)
        except Exception:
            pass
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def safe_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def parse_json(value: Any, default: Any = None) -> Any:
    if default is None: default = {}
    if isinstance(value, (dict, list)): return value
    try: return json.loads(value) if value else default
    except (TypeError, ValueError): return default


def idr(value: Any, decimals: int = 0) -> str:
    if value is None or value == "": return "—"
    n = to_float(value)
    sign = "-" if n < 0 else ""
    return f"{sign}Rp{abs(n):,.{decimals}f}".replace(",", ".")


def pct(value: Any, decimals: int = 1) -> str:
    if value is None: return "—"
    return f"{to_float(value):.{decimals}f}%"


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == ""


def new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def iso_now() -> str: return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()
