"""
Step 4/8: receive screenshots, OCR, save, and confirm.
"""

import re
import logging
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from .. import db
from ..services.matching import best_match
from ..services.normalize import clean_username, normalize_followers
from ..services.local_ocr import extract as local_extract
from ..services.vision import VisionClient, estimate_wait_seconds
from ..config import (
    OPENAI_API_KEY,
    OCR_MODE,
    QUEUE_NOTIFY_THRESHOLD,
    MAX_START_WAIT_SEC,
)
from .sessions import Intake

router = Router(name="images")
BOT_IMAGE_HANDLER_VERSION = "1.6.1"

log = logging.getLogger(__name__)
log.debug("Images handler version: %s", BOT_IMAGE_HANDLER_VERSION)

# Build Vision client only if an API key exists (created lazily below as well)
vision = (
    VisionClient(api_key=OPENAI_API_KEY)
    if (OPENAI_API_KEY and OCR_MODE in ("hybrid", "openai"))
    else None
)


def _get_open_session(conn, uid):
    return db.q(
        conn,
        "SELECT * FROM sessions WHERE tg_user_id=? AND status='open' "
        "ORDER BY id DESC LIMIT 1",
        [uid],
    ).fetchone()


def _fmt_eta(seconds: float) -> str:
    s = int(max(0, seconds))
    h = s // 3600
    m = (s % 3600) // 60
    s = s % 60
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


@router.message(F.photo | F.document)
async def on_image(m: types.Message, bot, state: FSMContext) -> None:
    """
    Accepts photos (compressed) or image documents (original).
    Saves the item even if you’re not exactly at Step 4, but warns once.
    """

    st = await state.get_state()
    if st != Intake.collecting_images.state:
        await m.reply(
            "I'll save that image, but you're not in Step 4. "
            "Use /start_session → date → order → then send screenshots."
        )

    conn = db.connect()
    try:
        sess = _get_open_session(conn, m.from_user.id)
        if not sess:
            await m.reply("No open session. Use /start_session first.")
            return

        # Choose file id
        file_id = None
        if m.photo:
            file_id = m.photo[-1].file_id
        elif (
            m.document
            and m.document.mime_type
            and m.document.mime_type.startswith("image/")
        ):
            file_id = m.document.file_id
        else:
            await m.reply("Please send an image (photo or image document).")
            return

        # Download bytes
        fobj = await bot.get_file(file_id)
        b = await bot.download_file(fobj.file_path)
        image_bytes = b.read() if hasattr(b, "read") else b.getvalue()

        # --- Pass 1: Local OCR (fast/offline)
        lres = local_extract(image_bytes)
        username = clean_username(lres.username)
        followers_raw = lres.followers
        conf = lres.confidence
        followers_norm = normalize_followers(followers_raw or "")
        local_ok = bool(username and followers_norm)

        # --- Decide on OpenAI fallback
        want_openai_mode = OCR_MODE in ("openai", "hybrid")
        have_api_key = bool(OPENAI_API_KEY)
        # NEW: if OCR_MODE=local but local OCR failed AND we have an API key, escalate automatically.
        need_openai = (
            (want_openai_mode and not local_ok)
            or (OCR_MODE == "local" and have_api_key and not local_ok)
        )

        # Lazily create Vision client if not created yet
        global vision
        if need_openai and not vision and have_api_key:
            vision = VisionClient(api_key=OPENAI_API_KEY)

        # --- Pass 2: OpenAI OCR if needed
        if need_openai and vision:
            wait_s = estimate_wait_seconds()
            if wait_s >= MAX_START_WAIT_SEC:
                # Save stub, ask user to reply with manual correction
                db.q(
                    conn,
                    "INSERT INTO items(session_id,order_index,username,followers_raw,followers_normalized,"
                    "image_file_id,ocr_confidence,corrected,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,datetime('now'))",
                    [sess["id"], None, None, None, None, file_id, 0.0, 0],
                )
                conn.commit()
                await m.reply(
                    "🚦 OpenAI is in long cooldown "
                    f"(~{_fmt_eta(wait_s)}). I saved the image; reply here with:\n"
                    "username=handle followers=1234  (or 1.2k/1.2m)"
                )
                return

            if wait_s >= QUEUE_NOTIFY_THRESHOLD:
                await m.reply(
                    f"⏳ Queued — processing in ~{_fmt_eta(wait_s)}. I’ll update when done."
                )

            ocr = await vision.extract(image_bytes)
            if ocr.username:
                username = clean_username(ocr.username)
            if ocr.followers:
                followers_raw = ocr.followers
            if ocr.confidence is not None:
                conf = ocr.confidence
            followers_norm = normalize_followers(followers_raw or "")
            local_ok = bool(username and followers_norm)

        # If we expected to use OpenAI but **no API key**, be explicit to the user
        if not local_ok and want_openai_mode and not have_api_key:
            await m.reply(
                "⚠️ I couldn't read this with local OCR and OpenAI fallback is disabled "
                "(missing OPENAI_API_KEY). Send a correction reply:\n"
                "username=handle followers=1234 (or 1.2k/1.2m)"
            )

        # Load desired order
        ord_row = db.q(
            conn,
            "SELECT usernames_json FROM username_orders WHERE tg_user_id=?",
            [m.from_user.id],
        ).fetchone()
        order = []
        if ord_row and ord_row["usernames_json"]:
            import json

            order = json.loads(ord_row["usernames_json"])

        # Match to order index
        order_index = None
        match_score = 0
        if username and order:
            idx, match_score = best_match(username, order, threshold=75)
            if idx is not None:
                order_index = idx + 1

        # Persist item
        db.q(
            conn,
            "INSERT INTO items(session_id,order_index,username,followers_raw,followers_normalized,"
            "image_file_id,ocr_confidence,corrected,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,datetime('now'))",
            [
                sess["id"],
                order_index,
                username,
                followers_raw,
                followers_norm,
                file_id,
                (conf or 0.0),
                0,
            ],
        )
        conn.commit()

        # User feedback
        if username and followers_norm:
            if order and order_index is None:
                await m.reply(
                    f"✅ Got it: {username} — {followers_norm}\n"
                    "But I couldn't match this username to your /set_order list.\n"
                    "• Reply to fix: username=correct_name\n"
                    "• Or keep sending screenshots, then /review."
                )
            else:
                oi = order_index if order_index is not None else "?"
                await m.reply(
                    f"✅ Detected {username} — {followers_norm} (order #{oi}, match {match_score})"
                )
        else:
            await m.reply(
                "❗ I couldn't confidently detect username/followers.\n"
                f"(debug) I saw: username={username!r} followers={followers_raw!r}\n"
                "Reply like: username=imsakuraneko followers=1,914  (or 1.2k / 1.2m)"
            )

    finally:
        conn.close()


@router.message(F.reply_to_message, F.text.regexp(r"(?i)username\s*=|followers\s*="))
async def on_correction(m: types.Message):
    """
    Allows manual fix by replying:
      username=<name> followers=<number|k|m>
    """
    txt = m.text or ""
    u = re.search(r"(?i)username\s*=\s*([a-z0-9._@-]+)", txt)
    f = re.search(r"(?i)followers\s*=\s*([0-9.,\s]*[kKmM]?)", txt)
    username = clean_username(u.group(1)) if u else None
    followers_raw = f.group(1).strip() if f else None

    conn = db.connect()
    try:
        sess = _get_open_session(conn, m.from_user.id)
        if not sess:
            await m.reply("No open session.")
            return

        item = db.q(
            conn,
            "SELECT * FROM items WHERE session_id=? ORDER BY id DESC LIMIT 1",
            [sess["id"]],
        ).fetchone()
        if not item:
            await m.reply("Nothing to correct.")
            return

        followers_norm = normalize_followers(followers_raw or "") if followers_raw else None
        new_username = username or item["username"]
        new_followers_raw = followers_raw or item["followers_raw"]
        new_followers_norm = followers_norm or item["followers_normalized"]

        # Recompute order index from your /set_order list
        order_index = item["order_index"]
        ord_row = db.q(
            conn,
            "SELECT usernames_json FROM username_orders WHERE tg_user_id=?",
            [m.from_user.id],
        ).fetchone()
        if ord_row and ord_row["usernames_json"]:
            import json

            order = json.loads(ord_row["usernames_json"])
            if new_username:
                idx, _ = best_match(new_username, order, threshold=75)
                order_index = idx + 1 if idx is not None else None

        db.q(
            conn,
            "UPDATE items SET username=?, followers_raw=?, followers_normalized=?, "
            "order_index=?, corrected=1 WHERE id=?",
            [new_username, new_followers_raw, new_followers_norm, order_index, item["id"]],
        )
        conn.commit()

        await m.reply(f"✅ Updated {new_username or '—'} — {new_followers_norm or '—'}")
    finally:
        conn.close()
