"""Language detection and validation utilities."""
from __future__ import annotations

from typing import Optional


def detect_script_language(text: Optional[str]) -> str:
    """
    Deterministically detects whether text is written in Tamil ('ta'), Hindi ('hi'),
    or English ('en') using non-overlapping Unicode character ranges.

    Tamil script: Unicode block \\u0B80 - \\u0BFF
    Hindi (Devanagari): Unicode block \\u0900 - \\u097F
    English / Latin: Default fallback
    """
    if not text:
        return "en"

    ta_count = sum(1 for c in text if "\u0B80" <= c <= "\u0BFF")
    hi_count = sum(1 for c in text if "\u0900" <= c <= "\u097F")

    if ta_count > 0 and ta_count >= hi_count:
        return "ta"
    elif hi_count > 0:
        return "hi"
    return "en"
