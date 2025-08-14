"""
Utility actions:
/undo (remove last item), /retry_last (placeholder)
"""

from aiogram import Router, types
from aiogram.filters import Command
from .. import db

router = Router(name="corrections")

@router.message(Command("undo"))
async def undo_cmd(m: types.Message) -> None:
    conn = db.connect()
    sess = db.q(conn, "SELECT * FROM sessions WHERE tg_user_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                [m.from_user.id]).fetchone()
    if not sess:
        await m.reply("No open session."); conn.close(); return

    last = db.q(conn, "SELECT * FROM items WHERE session_id=? ORDER BY id DESC LIMIT 1", [sess["id"]]).fetchone()
    if not last:
        await m.reply("Nothing to undo."); conn.close(); return

    db.q(conn, "DELETE FROM items WHERE id=?", [last["id"]])
    conn.commit(); conn.close()
    await m.reply("Removed last item.")

@router.message(Command("retry_last"))
async def retry_last_cmd(m: types.Message) -> None:
    await m.reply("Feature not implemented in this build. Re-send the image instead.")
