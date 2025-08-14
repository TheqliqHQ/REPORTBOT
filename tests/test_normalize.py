
from services.normalize import normalize_followers


def test_k():
    # 1.9k -> 1,900
    assert normalize_followers("1.9k") == "1,900"


def test_m():
    # 2.03m -> 2,030,000
    assert normalize_followers("2.03m") == "2,030,000"


def test_plain():
    # 1914 -> 1,914
    assert normalize_followers("1914") == "1,914"
