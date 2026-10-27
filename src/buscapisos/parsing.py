"""Pure helpers that clean raw scraped text into numeric types.

These run *before* Pydantic so that strings like "320.000 €" and "115 m²"
become Decimal / int values with no locale-dependent ambiguity.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMERIC_CHARS_RE = re.compile(r"[^\d.,]")
_AREA_UNITS_RE = re.compile(r"(m\s*2|m²|metros?\s*cuadrados?|mt2)")


def _normalize_number(s: str) -> str:
    """Normalize a digit/separator string into a Decimal-parseable string.

    Handles Spanish formatting: "." as thousands separator ("1.250.000") and
    "," as decimal separator ("320,50").
    """
    if "," in s and "." in s:
        # The rightmost separator is the decimal separator; drop the other.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "," in s:
        fraction = s.rsplit(",", 1)[1]
        s = s.replace(",", ".") if len(fraction) <= 2 else s.replace(",", "")
    elif "." in s:
        fraction = s.rsplit(".", 1)[1]
        s = s if len(fraction) <= 2 else s.replace(".", "")
    return s


def parse_price(raw: str | None) -> Decimal:
    """Parse a Spanish-formatted price such as "320.000 €" -> Decimal('320000')."""
    if raw is None or not raw.strip():
        raise ValueError("price is empty")

    cleaned = _NUMERIC_CHARS_RE.sub("", raw.strip())
    if not cleaned:
        raise ValueError(f"cannot parse price from {raw!r}")

    try:
        return Decimal(_normalize_number(cleaned))
    except InvalidOperation as exc:
        raise ValueError(f"cannot parse price from {raw!r}") from exc


def parse_area(raw: str | None) -> Decimal:
    """Parse a surface such as "115 m²" -> Decimal('115')."""
    if raw is None or not raw.strip():
        raise ValueError("area is empty")

    cleaned = _AREA_UNITS_RE.sub("", raw.strip().lower())
    cleaned = _NUMERIC_CHARS_RE.sub("", cleaned)
    if not cleaned:
        raise ValueError(f"cannot parse area from {raw!r}")

    try:
        return Decimal(_normalize_number(cleaned))
    except InvalidOperation as exc:
        raise ValueError(f"cannot parse area from {raw!r}") from exc


def parse_int(raw: str | None) -> int:
    """Extract the first integer from a label such as "3 habitaciones" -> 3."""
    if raw is None:
        raise ValueError("value is empty")

    match = re.search(r"\d+", str(raw))
    if match is None:
        raise ValueError(f"cannot parse integer from {raw!r}")

    return int(match.group())
