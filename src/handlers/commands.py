"""
Wizard controls:
/start, /help, /start_session, /set_order, /status, /review (Step 6),
/send (Step 7), /end_session (Step 8), /cancel

PLUS admin helpers:
 /my_id, /who_is_boss, /set_boss_here, /set_boss,
 /who_is_topic, /set_topic_here, /set_topic, /debug_send, /where_sending
"""

import json
from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from .. import db
from .sessions import Intake
from ..services.formatting import format_caption
from ..config import BOSS_CHAT_ID, BOSS_THREAD_ID, FORCE_ENV_DESTINATION

router = Router(name="commands")


# ─────────────────────────────── Core flow ─────────────────────────────── #

@router.message(CommandStart())
async def start_cmd(m: types.Message):
    await m.reply(
        "Hi! I’m your IG Report Bot.\n\n"
        "Flow:\n"
        "1) /start_session → send date\n"
        "2) Paste order\n"
        "3) Send all screenshots\n"
        "4) /review → preview\n"
        "5) /send → send to boss\n"
        "6) /end_session → close the day"
    )


@router.message(Command("help"))
async def help_cmd(m: types.Message):
    await m.reply(
        "/start_session - begin a new report\n"
        "/set_order - set/change username order (manual)\n"
        "/status - show progress vs order\n"
        "/review - preview captions in order (Step 6)\n"
        "/send - send images+captions to boss (Step 7)\n"
        "/end_session - close session (Step 8)\n"
        "/cancel - cancel session\n"
        "/undo - remove last item\n\n"
        "Admin helpers:\n"
        "/my_id, /who_is_boss, /set_boss_here, /set_boss\n"
        "/who_is_topic, /set_topic_here, /set_topic, /debug_send, /where_sending"
    )


@router.message(Command("set_order"))
async def set_order_cmd(m: types.Message, state: FSMContext):
    await state.set_state(Intake.waiting_order)
    await m.reply("Paste usernames in order (one per line or comma-separated).")


@router.message(Command("status"))
async def status_cmd(m: types.Message):
    conn = db.connect()
    try:
        sess = db.q(conn,
            "SELECT * FROM sessions WHERE tg_user_id=? AND status='open' ORDER BY id DESC LIMIT 1",
            [m.from_user.id]
        ).fetchone()
        if not sess:
            await m.reply("No open session. Use /start_session.")
            return

        order_row = db.q(conn,
            "SELECT usernames_json FROM username_orders WHERE tg_user_id=?",
            [m.from_user.id]
        ).fetchone()
        order = json.loads(order_row["usernames_json"]) if order_row and order_row["usernames_json"] else []

        items = db.q(conn,
            "SELECT username, followers_normalized, order_index FROM items WHERE session_id=?",
            [sess["id"]]
        ).fetchall()

        captured = {r["order_index"]: (r["username"], r["followers_normalized"]) for r in items if r["order_index"]}
        lines = []
        for i, u in enumerate(order, start=1):
            if i in captured:
                lines.append(f"{i}. {u} — ✅ {captured[i][1]}")
            else:
                lines.append(f"{i}. {u} — ❌ (missing)")
        if not lines:
            lines.append("No order set. Use /set_order.")
        await m.reply("\n".join(lines))
    finally:
        conn.close()


@router.message(Command("review"))
async def review_cmd(m: types.Message):
    conn = db.connect()
    try:
        sess = db.q(conn,
            "SELECT * FROM sessions WHERE tg_user_id=? AND status='open' ORDER BY id DESC LIMIT 1",
            [m.from_user.id]
        ).fetchone()
        if not sess:
            await m.reply("No open session. Use /start_session.")
            return

        order_row = db.q(conn,
            "SELECT usernames_json FROM username_orders WHERE tg_user_id=?",
            [m.from_user.id]
        ).fetchone()
        order = json.loads(order_row["usernames_json"]) if order_row and order_row["usernames_json"] else []

        items = db.q(conn, "SELECT * FROM items WHERE session_id=?", [sess["id"]]).fetchall()

        by_idx = {r["order_index"]: r for r in items if r["order_index"]}
        missing = [u for i, u in enumerate(order, start=1) if i not in by_idx]

        lines = []
        for i, u in enumerate(order, start=1):
            r = by_idx.get(i)
            if not r:
                lines.append(f"{i}. {u} — ❌ missing")
                continue
            cap = format_caption(
                sess["date_str"], r["username"] or u, i, r["followers_normalized"] or r["followers_raw"] or ""
            )
            first_line = cap.splitlines()[0] if cap else ""
            lines.append(f"{i}. {first_line}")

        summary = ["Step 6/8 — Review preview:", *lines]
        if missing:
            summary.append("\nMissing: " + ", ".join(missing))
        summary.append("\nIf this looks good, type /send to deliver to your boss.")
        await m.reply("\n".join(summary))
    finally:
        conn.close()


@router.message(Command("send"))
async def send_cmd(m: types.Message, bot):
    conn = db.connect()
    try:
        sess = db.q(conn,
            "SELECT * FROM sessions WHERE tg_user_id=? AND status='open' ORDER BY id DESC LIMIT 1",
            [m.from_user.id]
        ).fetchone()
        if not sess:
            await m.reply("No open session. Use /start_session.")
            return

        order_row = db.q(conn,
            "SELECT usernames_json FROM username_orders WHERE tg_user_id=?",
            [m.from_user.id]
        ).fetchone()
        order = json.loads(order_row["usernames_json"]) if order_row and order_row["usernames_json"] else []
        if not order:
            await m.reply("No order set. Use /set_order first.")
            return

        items = db.q(conn, "SELECT * FROM items WHERE session_id=?", [sess["id"]]).fetchall()
        by_idx = {r["order_index"]: r for r in items if r["order_index"]}

        # Destination resolution: if FORCE_ENV_DESTINATION is true, always use .env
        row = db.q(conn,
            "SELECT boss_chat_id, boss_thread_id FROM users WHERE tg_user_id=?",
            [m.from_user.id]
        ).fetchone()

        if FORCE_ENV_DESTINATION:
            boss_chat_id = int(BOSS_CHAT_ID)
            topic_id = int(BOSS_THREAD_ID) if BOSS_THREAD_ID else None
        else:
            boss_chat_id = int(row["boss_chat_id"]) if row and row["boss_chat_id"] else int(BOSS_CHAT_ID)
            topic_id = (int(row["boss_thread_id"]) if row and row["boss_thread_id"]
                        else (int(BOSS_THREAD_ID) if BOSS_THREAD_ID else None))

        sent = 0
        for i, u in enumerate(order, start=1):
            r = by_idx.get(i)
            if not r:
                continue
            caption = format_caption(
                sess["date_str"], r["username"] or u, i, r["followers_normalized"] or r["followers_raw"] or ""
            )
            try:
                await bot.send_photo(
                    chat_id=boss_chat_id,
                    photo=r["image_file_id"],
                    caption=caption,
                    message_thread_id=topic_id,  # routes to a forum topic (e.g., “Work Proof”)
                )
                sent += 1
            except TelegramBadRequest as e:
                msg = (e.message or "").lower()
                if "chat not found" in msg or "forbidden" in msg:
                    await m.reply(
                        "🚫 I can't send to the configured destination.\n\n"
                        "Fix one:\n"
                        "• If it's a **user**, they must open the bot and tap *Start* once.\n"
                        "• If it's a **group**, add me there; use its negative chat id.\n"
                        "• If it's a **channel**, add me as admin and use its id.\n"
                        "• If it's a **forum group** (topics), set the topic with /set_topic_here.\n\n"
                        "Check with /who_is_boss and /who_is_topic.\n"
                        "Set with /set_boss_here (in the target chat) and /set_topic_here (inside the topic)."
                    )
                    return
                else:
                    raise

        await m.reply(
            f"Step 7/8 — Sent {sent} item(s) to your boss.\n"
            "Step 8/8 — Do you want to end this session? Type /end_session to close, or keep sending images then /review."
        )
    finally:
        conn.close()


@router.message(Command("end_session"))
async def end_session_cmd(m: types.Message):
    conn = db.connect()
    try:
        db.q(conn,
             "UPDATE sessions SET status='closed', closed_at=datetime('now') WHERE tg_user_id=? AND status='open'",
             [m.from_user.id])
        conn.commit()
        await m.reply("Session closed. ✅")
    finally:
        conn.close()


@router.message(Command("cancel"))
async def cancel_cmd(m: types.Message):
    conn = db.connect()
    try:
        db.q(conn,
             "UPDATE sessions SET status='closed', closed_at=datetime('now') WHERE tg_user_id=? AND status='open'",
             [m.from_user.id])
        conn.commit()
        await m.reply("Cancelled current session.")
    finally:
        conn.close()


# ───────────────────────────── Admin / debug helpers ───────────────────────────── #

@router.message(Command("my_id"))
async def my_id_cmd(m: types.Message):
    await m.reply(f"chat.id = {m.chat.id}\nfrom_user.id = {m.from_user.id}")


@router.message(Command("who_is_boss"))
async def who_is_boss_cmd(m: types.Message):
    conn = db.connect()
    try:
        row = db.q(conn, "SELECT boss_chat_id FROM users WHERE tg_user_id=?", [m.from_user.id]).fetchone()
        if row and row["boss_chat_id"]:
            await m.reply(f"Boss chat (DB) = {row['boss_chat_id']}")
        else:
            await m.reply(f"Boss chat (.env) = {BOSS_CHAT_ID}")
    finally:
        conn.close()


@router.message(Command("set_boss_here"))
async def set_boss_here_cmd(m: types.Message):
    conn = db.connect()
    try:
        db.q(conn,
             "INSERT INTO users(tg_user_id,boss_chat_id,updated_at) VALUES(?,?,datetime('now')) "
             "ON CONFLICT(tg_user_id) DO UPDATE SET boss_chat_id=excluded.boss_chat_id, updated_at=datetime('now')",
             [m.from_user.id, m.chat.id])
        conn.commit()
        await m.reply(f"✅ Boss chat set to current chat: {m.chat.id}")
    finally:
        conn.close()


@router.message(Command("set_boss"))
async def set_boss_cmd(m: types.Message, bot):
    args = (m.text or "").split(maxsplit=1)
    if len(args) < 2:
        await m.reply("Usage:\n• /set_boss <numeric_id>\n• /set_boss @username\n• or run /set_boss_here in the target chat")
        return
    target = args[1].strip()
    if target.startswith("@"):
        try:
            ch = await bot.get_chat(target)
            chat_id = ch.id
        except TelegramBadRequest as e:
            await m.reply(f"Could not resolve {target}: {e.message}")
            return
    else:
        try:
            chat_id = int(target)
        except ValueError:
            await m.reply("Invalid id. Use a number or @username.")
            return

    conn = db.connect()
    try:
        db.q(conn,
             "INSERT INTO users(tg_user_id,boss_chat_id,updated_at) VALUES(?,?,datetime('now')) "
             "ON CONFLICT(tg_user_id) DO UPDATE SET boss_chat_id=excluded.boss_chat_id, updated_at=datetime('now')",
             [m.from_user.id, chat_id])
        conn.commit()
        await m.reply(f"✅ Boss chat set to {chat_id}")
    finally:
        conn.close()


@router.message(Command("who_is_topic"))
async def who_is_topic_cmd(m: types.Message):
    conn = db.connect()
    try:
        row = db.q(conn, "SELECT boss_thread_id FROM users WHERE tg_user_id=?", [m.from_user.id]).fetchone()
        if row and row["boss_thread_id"]:
            await m.reply(f"Topic (DB) = {row['boss_thread_id']}")
        else:
            await m.reply("Topic is not set. Run /set_topic_here inside the topic (thread).")
    finally:
        conn.close()


@router.message(Command("set_topic_here"))
async def set_topic_here_cmd(m: types.Message):
    if m.message_thread_id is None:
        await m.reply("This chat has no topic context. Run this inside the topic you want.")
        return
    conn = db.connect()
    try:
        db.q(conn,
             "INSERT INTO users(tg_user_id,boss_thread_id,updated_at) VALUES(?,?,datetime('now')) "
             "ON CONFLICT(tg_user_id) DO UPDATE SET boss_thread_id=excluded.boss_thread_id, updated_at=datetime('now')",
             [m.from_user.id, m.message_thread_id])
        conn.commit()
        await m.reply(f"✅ Topic set to this thread id: {m.message_thread_id}")
    finally:
        conn.close()


@router.message(Command("set_topic"))
async def set_topic_cmd(m: types.Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.reply("Usage: /set_topic <message_thread_id>\nTip: use /set_topic_here inside the topic to auto-detect.")
        return
    try:
        thread_id = int(parts[1])
    except ValueError:
        await m.reply("Topic id must be a number.")
        return
    conn = db.connect()
    try:
        db.q(conn,
             "INSERT INTO users(tg_user_id,boss_thread_id,updated_at) VALUES(?,?,datetime('now')) "
             "ON CONFLICT(tg_user_id) DO UPDATE SET boss_thread_id=excluded.boss_thread_id, updated_at=datetime('now')",
             [m.from_user.id, thread_id])
        conn.commit()
        await m.reply(f"✅ Topic set to {thread_id}")
    finally:
        conn.close()


@router.message(Command("debug_send"))
async def debug_send_cmd(m: types.Message, bot):
    args = (m.text or "").split(maxsplit=2)
    if len(args) < 2:
        await m.reply("Usage: /debug_send <chat_id|@username> [text]")
        return
    target = args[1]
    text = args[2] if len(args) > 2 else "debug"

    # Resolve @username if needed
    if target.startswith("@"):
        try:
            ch = await bot.get_chat(target)
            chat_id = ch.id
        except TelegramBadRequest as e:
            await m.reply(f"Could not resolve {target}: {e.message}")
            return
    else:
        try:
            chat_id = int(target)
        except ValueError:
            await m.reply("Invalid id. Use a number or @username.")
            return

    try:
        await bot.send_message(chat_id=chat_id, text=f"[debug] {text}")
        await m.reply(f"✅ Sent to {chat_id}")
    except TelegramBadRequest as e:
        await m.reply(f"🚫 Telegram error: {e.message}")


@router.message(Command("where_sending"))
async def where_sending(m: types.Message):
    conn = db.connect()
    try:
        row = db.q(conn,
            "SELECT boss_chat_id, boss_thread_id FROM users WHERE tg_user_id=?",
            [m.from_user.id]
        ).fetchone()
        db_chat = row["boss_chat_id"] if row else None
        db_topic = row["boss_thread_id"] if row else None
        effective_chat = BOSS_CHAT_ID if FORCE_ENV_DESTINATION or not db_chat else db_chat
        effective_topic = BOSS_THREAD_ID if FORCE_ENV_DESTINATION or not db_topic else db_topic
        await m.reply(
            "Destination:\n"
            f"• FORCE_ENV_DESTINATION = {FORCE_ENV_DESTINATION}\n"
            f"• .env chat = {BOSS_CHAT_ID}, .env topic = {BOSS_THREAD_ID}\n"
            f"• DB chat = {db_chat}, DB topic = {db_topic}\n"
            f"→ Effective chat = {effective_chat}, topic = {effective_topic}"
        )
    finally:
        conn.close()
