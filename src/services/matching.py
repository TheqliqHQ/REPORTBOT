
"""
Fuzzy matching of OCR'd usernames to the fixed order list.
"""

from typing import List, Optional, Tuple

# Prefer rapidfuzz for speed/quality; fallback to difflib if not available.
try:
    from rapidfuzz import fuzz

    def fuzz_ratio(a: str, b: str) -> int:
        return int(fuzz.ratio(a, b))
except Exception:  # pragma: no cover - fallback path
    from difflib import SequenceMatcher as _SM

    def fuzz_ratio(a: str, b: str) -> int:
        return int(_SM(None, a, b).ratio() * 100)


def best_match(candidate: str, order_list: List[str], threshold: int = 80) -> Tuple[Optional[int], int]:
    """
    Return the best match (index, score) for candidate in order_list.
    - index is 0-based; None if the best score is below threshold.
    - score is the fuzz ratio for visibility/debugging.
    """
    if not order_list:
        return None, 0

    best_i, best_s = None, -1
    for i, target in enumerate(order_list):
        s = fuzz_ratio(candidate, target)
        if s > best_s:
            best_i, best_s = i, s

    if best_s >= threshold:
        return best_i, best_s

    return None, best_s
