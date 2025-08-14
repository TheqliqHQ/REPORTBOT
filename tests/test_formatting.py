
from services.formatting import format_caption


def test_caption():
    c = format_caption("2025-08-08", "sakura9neko", 2, "80,200")
    assert "08/08/2025 - Work finished for sakura9neko" in c
    assert "IG #2-> Total followers 80,200" in c
