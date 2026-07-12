import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.database import Database
from bot.handlers import build_router
from bot.scheduler import ReminderScheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    config = load_config()
    database = Database(config.database_path)
    database.initialize()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    scheduler = ReminderScheduler(bot, database)
    scheduler.start()
    await scheduler.restore_pending_reminders()

    dispatcher.include_router(build_router(database, scheduler))

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown()
        database.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
