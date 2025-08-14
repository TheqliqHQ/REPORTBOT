
"""
Typed models used across services.
"""

from pydantic import BaseModel


class OCRResult(BaseModel):
    """
    The structured response from the vision model.
    """
    username: str | None = None
    followers: str | None = None
    confidence: float | None = None
