
"""
Utilities for cleaning usernames and normalizing follower counts.
"""

import re
from typing import Optional

# Regex to match k/m-style abbreviations like "1.9k", "2.03m"
_K = re.compile(r"(?i)\b([0-9]*\.?[0-9]+)\s*k\b")
_M = re.compile(r"(?i)\b([0-9]*\.?[0-9]+)\s*m\b")

# Remove every non-digit character
_NON_DIGITS = re.compile(r"[^0-9]")


def normalize_followers(text: str) -> Optional[str]:
    """
    Convert a variety of follower formats into comma-separated integers.
    Examples:
      - "1.9k"  -> "1,900"
      - "2.03m" -> "2,030,000"
      - "1914"  -> "1,914"
    Returns None if it cannot parse a number.
    """
    if not text:
        return None

    t = text.strip()

    # Abbreviated thousands (k)
    m = _K.search(t)
    if m:
        val = float(m.group(1)) * 1000
        return f"{int(round(val)):,}"

    # Abbreviated millions (m)
    m = _M.search(t)
    if m:
        val = float(m.group(1)) * 1_000_000
        return f"{int(round(val)):,}"

    # Plain digits with commas or spaces
    digits = _NON_DIGITS.sub("", t)
    if not digits:
        return None

    try:
        return f"{int(digits):,}"
    except ValueError:
        return None


def clean_username(u: str | None) -> str | None:
    """
    Normalize an Instagram username:
      - lowercase
      - strip leading '@'
      - allow only letters, digits, dot, underscore
    """
    if not u:
        return None
    u = u.strip().lower()
    if u.startswith("@"):
        u = u[1:]
    return re.sub(r"[^a-z0-9._]", "", u)
