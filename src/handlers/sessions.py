"""
Session flow:
1) /start_session -> ask for date
2) after date -> ask for username order
3) after order -> ask for screenshots (collecting)
"""

from datetime import date, datetime
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from .. import db

router = Router(name="sessions")

class Intake(StatesGroup):
    waiting_date = State()
    waiting_order = State()
    collecting_images = State()

@router.message(F.text == "/start_session")
async def start_session_cmd(m: types.Message, state: FSMContext):
    await state.set_state(Intake.waiting_date)
    await m.reply("Step 2/8 — Send report date (DD/MM/YYYY or YYYY-MM-DD or type 'today')")

@router.message(Intake.waiting_date, F.text)
async def handle_date(m: types.Message, state: FSMContext):
    txt = (m.text or "").strip().lower()
    if txt == "today":
        ds = date.today().strftime("%d/%m/%Y")
    else:
        try:
            if "-" in txt:
                ds = datetime.strptime(txt, "%Y-%m-%d").strftime("%d/%m/%Y")
            else:
                ds = datetime.strptime(txt, "%d/%m/%Y").strftime("%d/%m/%Y")
        except Exception:
            await m.reply("Invalid date. Use DD/MM/YYYY or YYYY-MM-DD or 'today'.")
            return

    conn = db.connect()
    db.q(conn, "INSERT INTO sessions(tg_user_id,date_str,status,created_at) VALUES(?,?, 'open', datetime('now'))",
         [m.from_user.id, ds])
    conn.commit()
    conn.close()

    await state.set_state(Intake.waiting_order)
    await m.reply(
        "Step 3/8 — Paste the usernames in the exact order to send to your boss.\n"
        "Format: one per line or comma-separated. (We'll match OCR to this list.)"
    )

@router.message(Intake.waiting_order, F.text)
async def handle_order(m: types.Message, state: FSMContext):
    raw = (m.text or "")
    parts = [p.strip().lower().lstrip("@") for p in raw.replace(",", "\n").splitlines() if p.strip()]
    if not parts:
        await m.reply("I didn't see any usernames. Please paste them (one per line or comma-separated).")
        return

    import json
    conn = db.connect()
    db.q(conn,
         "INSERT INTO username_orders(tg_user_id,usernames_json,updated_at) "
         "VALUES(?,?,datetime('now')) "
         "ON CONFLICT(tg_user_id) DO UPDATE SET usernames_json=excluded.usernames_json, updated_at=datetime('now')",
         [m.from_user.id, json.dumps(parts)])
    conn.commit()
    conn.close()

    await state.set_state(Intake.collecting_images)
    await m.reply("Step 4/8 — Send ALL the screenshots now (you can send many). When you're done, type /review.")
