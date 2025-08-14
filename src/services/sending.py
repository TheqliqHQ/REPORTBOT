
"""
Thin wrapper for sending photos to Telegram with captions.
"""

from aiogram import Bot


async def send_to_boss(bot: Bot, boss_chat_id: int, photo_file_id: str, caption: str) -> None:
    """
    Re-send a previously uploaded Telegram photo by file_id, with caption.
    """
    await bot.send_photo(chat_id=boss_chat_id, photo=photo_file_id, caption=caption)
