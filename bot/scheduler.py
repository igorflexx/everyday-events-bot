from __future__ import annotations

from datetime import datetime, timezone
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database import Database
from bot.keyboards import active_task_keyboard


logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule_active_task(self, telegram_id: int, ends_at: str | None) -> None:
        self.remove_job(telegram_id)
        if not ends_at:
            return
        run_at = datetime.fromisoformat(ends_at)
        self.scheduler.add_job(
            self.send_reminder,
            "date",
            id=self._job_id(telegram_id),
            run_date=run_at,
            args=[telegram_id],
            replace_existing=True,
        )

    def remove_job(self, telegram_id: int) -> None:
        job_id = self._job_id(telegram_id)
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    async def restore_pending_reminders(self) -> None:
        for reminder in self.db.list_pending_reminders():
            ends_at = reminder["ends_at"]
            if not ends_at:
                continue
            end_time = datetime.fromisoformat(ends_at)
            if end_time <= datetime.now(timezone.utc):
                await self.send_reminder(int(reminder["telegram_id"]))
            else:
                self.schedule_active_task(int(reminder["telegram_id"]), ends_at)

    async def send_reminder(self, telegram_id: int) -> None:
        active_task = self.db.get_active_task(telegram_id)
        if not active_task or active_task.get("reminder_sent"):
            self.remove_job(telegram_id)
            return

        try:
            await self.bot.send_message(
                telegram_id,
                (
                    f"Таймер по задаче <b>{active_task['title']}</b> закончился.\n"
                    "Можете завершить задачу и забрать очки или продолжить позже."
                ),
                reply_markup=active_task_keyboard(),
            )
            self.db.mark_reminder_sent(telegram_id)
        except Exception as exc:  # pragma: no cover - network side effect
            logger.warning("Failed to send reminder to %s: %s", telegram_id, exc)
        finally:
            self.remove_job(telegram_id)

    @staticmethod
    def _job_id(telegram_id: int) -> str:
        return f"task-reminder-{telegram_id}"

