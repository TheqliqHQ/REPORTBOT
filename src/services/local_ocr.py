"""
Local OCR using Tesseract (no network, no waiting).
Extract username + followers from IG screenshots.
"""

import io
import re
from typing import Optional
from PIL import Image, ImageOps, ImageEnhance
import pytesseract

from ..models import OCRResult
from ..config import TESSERACT_CMD

# Allow explicit tesseract path (Windows)
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def _preprocess(img: Image.Image) -> Image.Image:
    """Upscale + contrast/sharpen for better OCR."""
    gray = ImageOps.grayscale(img)
    gray = ImageEnhance.Contrast(gray).enhance(1.6)
    gray = ImageEnhance.Sharpness(gray).enhance(1.2)
    w, h = gray.size
    if max(w, h) < 1200:
        gray = gray.resize((w * 2, h * 2))
    return gray


def _pick_username(text: str) -> Optional[str]:
    """
    Heuristic: choose most likely handle pattern @?letters/digits/._ length 3..30.
    Prefer longer strings that contain letters.
    """
    t = text.lower()
    cands = re.findall(r'@?([a-z0-9._]{3,30})', t)
    if not cands:
        return None
    for cand in sorted(set(cands), key=lambda s: (-len(s), s)):
        if any(ch.isalpha() for ch in cand):
            return cand.strip(".")
    return None


def _pick_followers(text: str) -> Optional[str]:
    """
    Look for a number (with , . spaces) optionally followed by k/m,
    preferably near 'followers'.
    """
    t = text.lower()
    m = re.search(r'([\d][\d,.\s]*[kKmM]?)\s*(followers|follower|folowers|folowrs)', t)
    if m:
        return m.group(1).strip()

    m2 = re.search(r'([\d][\d,.\s]*[kKmM])', t)  # any k/m number
    if m2:
        return m2.group(1).strip()

    m3 = re.search(r'([\d][\d,.\s]{2,})', t)     # last resort: big number
    if m3:
        return m3.group(1).strip()
    return None


def extract(image_bytes: bytes) -> OCRResult:
    """Return OCRResult(username, followers, confidence) from local OCR."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return OCRResult()

    img = _preprocess(img)

    try:
        text = pytesseract.image_to_string(img, config="--psm 6")
    except Exception:
        return OCRResult()

    username = _pick_username(text)
    followers = _pick_followers(text)

    # Simple confidence heuristic
    if username and followers:
        conf = 0.85
    elif username or followers:
        conf = 0.6
    else:
        conf = 0.0

    return OCRResult(username=username, followers=followers, confidence=conf)
