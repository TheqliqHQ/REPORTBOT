"""
Caption formatting: EXACT line you asked for.

Example:
"08/08/2025 - Work finished for sakura9neko
 IG #2-> Total followers 80,200"
"""

def format_caption(date_str: str, username: str, index: int, followers_text: str) -> str:
    # Make sure username has no leading '@' and is lowercase for consistency
    u = (username or "").lstrip("@").strip()
    # Followers text is whatever you send us (already normalized like "80,200")
    ftxt = followers_text or ""
    # Build exact two-line caption
    line1 = f"{date_str} - Work finished for {u}"
    line2 = f" IG #{index}-> Total followers {ftxt}"
    return line1 + "\n" + line2
