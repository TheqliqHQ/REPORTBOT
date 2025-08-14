"""
Application entrypoint: wires together dispatcher, routers, middleware,
and registers Telegram slash commands so typing "/" shows the menu.
"""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
# NOTE: We intentionally do NOT import ParseMode; we disable parse mode globally.

from .config import TELEGRAM_BOT_TOKEN
from .db import init_db
from .handlers import commands, corrections, images, sessions
from .middleware.errors import ErrorMiddleware
from .middleware.logging import setup_logging


async def setup_bot_commands(bot: Bot) -> None:
    """Register the bot's slash commands so they appear when you type "/"."""
    cmds = [
        BotCommand(command="start",          description="Start & see commands"),
        BotCommand(command="help",           description="How to use the bot"),
        BotCommand(command="start_session",  description="Begin a new report (set date)"),
        BotCommand(command="set_order",      description="Set usernames order"),
        BotCommand(command="status",         description="Show today’s progress"),
        BotCommand(command="end_session",    description="Send images+captions to boss"),
        BotCommand(command="undo",           description="Remove last item"),
        BotCommand(command="retry_last",     description="Re-run last OCR (placeholder)"),
        BotCommand(command="cancel",         description="Cancel current session"),
        BotCommand(command="set_boss",       description="Set boss chat id"),
    ]
    await bot.set_my_commands(cmds)


async def main() -> None:
    # Fail fast if there is no bot token configured
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set")

    # Init logging and DB
    setup_logging()
    init_db()

    # Create bot and dispatcher (disable parse mode so "<...>" text won't break)
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None)
    )
    dp = Dispatcher()

    # Register global error middleware for messages
    dp.message.middleware(ErrorMiddleware())

    # Attach feature routers
    dp.include_router(commands.router)
    dp.include_router(sessions.router)
    dp.include_router(images.router)
    dp.include_router(corrections.router)

    # Register slash commands so Telegram shows them on "/"
    await setup_bot_commands(bot)

    # Start long-polling
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
