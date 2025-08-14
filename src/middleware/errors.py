
"""
Global error middleware to avoid silent crashes and to notify the user.
"""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:  # pragma: no cover - log + best-effort notify
            print("ERROR:", e)
            try:
                if event.message:
                    await event.message.reply("An error occurred. Please try again.")
            except Exception:
                pass
            raise
