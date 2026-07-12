from __future__ import annotations

from datetime import datetime
from html import escape
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User

from bot.database import Database
from bot.keyboards import (
    active_task_keyboard,
    clan_guest_keyboard,
    clan_member_keyboard,
    main_menu_keyboard,
    reward_selection_keyboard,
    rewards_hub_keyboard,
    settings_keyboard,
    task_selection_keyboard,
    tasks_hub_keyboard,
    timer_choice_keyboard,
)
from bot.scheduler import ReminderScheduler
from bot.states import (
    ClanCreationState,
    ClanJoinState,
    CustomTimerState,
    DefaultPointsState,
    RewardCreationState,
    TaskCreationState,
)


logger = logging.getLogger(__name__)


def build_router(db: Database, scheduler: ReminderScheduler) -> Router:
    router = Router()

    async def ensure_user(user: User) -> None:
        full_name = " ".join(filter(None, [user.first_name, user.last_name])).strip() or user.username or str(user.id)
        db.register_user(user.id, user.username, full_name)

    def format_minutes(value: int | None) -> str:
        if not value:
            return "без таймера"
        hours, minutes = divmod(value, 60)
        if hours and minutes:
            return f"{hours} ч {minutes} мин"
        if hours:
            return f"{hours} ч"
        return f"{minutes} мин"

    def format_datetime(value: str) -> str:
        dt = datetime.fromisoformat(value)
        return dt.astimezone().strftime("%d.%m %H:%M")

    def format_tasks_text(tasks: list[dict], active_task: dict | None) -> str:
        if tasks:
            task_lines = [
                (
                    f"{index}. <b>{escape(task['title'])}</b> "
                    f"- {task['points']} очк., таймер по умолчанию: {format_minutes(task['default_duration_minutes'])}"
                )
                for index, task in enumerate(tasks, start=1)
            ]
            task_block = "\n".join(task_lines)
        else:
            task_block = "Список задач пока пуст. Добавьте первую привычку или повседневное дело."

        if active_task:
            active_block = (
                f"\n\n<b>Сейчас в работе:</b>\n"
                f"{escape(active_task['title'])} - {active_task['points']} очк.\n"
                f"Старт: {format_datetime(active_task['started_at'])}\n"
                f"Таймер: {format_minutes(active_task['duration_minutes'])}"
            )
            if active_task.get("ends_at"):
                active_block += f"\nДедлайн: {format_datetime(active_task['ends_at'])}"
        else:
            active_block = "\n\nАктивной задачи сейчас нет."

        return f"<b>Ваши задачи</b>\n\n{task_block}{active_block}"

    def format_rewards_hub(profile: dict) -> str:
        return (
            "<b>Награды и магазин отдыха</b>\n\n"
            f"Всего заработано: <b>{profile['total_points']}</b>\n"
            f"Доступно для трат: <b>{profile['available_points']}</b>\n"
            f"Наград за достижения: <b>{profile['milestone_items']}</b>\n"
            f"Товаров в магазине: <b>{profile['shop_items']}</b>\n\n"
            "Награда за достижение не списывает очки, а магазин отдыха тратит очки из вашего баланса."
        )

    def format_reward_list(kind: str, rewards: list[dict]) -> str:
        title = "Награды за достижения" if kind == "milestone" else "Магазин отдыха"
        if not rewards:
            return f"<b>{title}</b>\n\nСписок пока пуст."

        lines = [f"<b>{title}</b>\n"]
        for reward in rewards:
            status = ""
            if kind == "milestone":
                if reward["claimed"]:
                    status = "Получено"
                elif reward["can_claim"]:
                    status = "Можно забрать"
                else:
                    status = "Еще не открыто"
            else:
                status = "Можно купить" if reward["can_buy"] else "Не хватает очков"

            description = reward["description"] or "без описания"
            lines.append(
                f"• <b>{escape(reward['title'])}</b> - {reward['cost']} очк.\n"
                f"  {escape(description)}\n"
                f"  Статус: {status}"
            )
        return "\n\n".join(lines)

    def format_history(history: list[dict]) -> str:
        if not history:
            return "<b>История наград</b>\n\nПока тут пусто."
        lines = ["<b>История наград</b>\n"]
        for item in history:
            action = "Покупка" if item["kind"] == "shop" else "Получение"
            spent = f", списано {item['spent_points']} очк." if item["spent_points"] else ""
            lines.append(
                f"• {format_datetime(item['claimed_at'])}: {action} <b>{escape(item['title'])}</b>{spent}"
            )
        return "\n".join(lines)

    def format_clan_summary(clan: dict, leaderboard: list[dict]) -> str:
        leader_text = ""
        if leaderboard:
            top = leaderboard[0]
            leader_name = escape(top["full_name"])
            leader_text = (
                f"\nЛидер сейчас: <b>{leader_name}</b> "
                f"с {top['total_points']} очками."
            )
        return (
            f"<b>Клан: {escape(clan['name'])}</b>\n"
            f"Код для вступления: <code>{clan['code']}</code>\n"
            f"Участников: <b>{clan['members_count']}</b>{leader_text}\n\n"
            "Код можно отправить друзьям, и они вступят через этого же бота."
        )

    def format_leaderboard(rows: list[dict]) -> str:
        if not rows:
            return "<b>Таблица клана</b>\n\nПока нет данных."
        lines = ["<b>Таблица клана</b>\n"]
        for index, member in enumerate(rows, start=1):
            lines.append(
                f"{index}. <b>{escape(member['full_name'])}</b> - "
                f"{member['total_points']} всего / {member['available_points']} доступно / "
                f"{member['completed_tasks']} завершено"
            )
        return "\n".join(lines)

    def format_clan_events(events: list[dict]) -> str:
        if not events:
            return "<b>Лента клана</b>\n\nСобытий пока нет."
        lines = ["<b>Лента клана</b>\n"]
        for event in events:
            points_suffix = f" (+{event['points_delta']} очк.)" if event["points_delta"] else ""
            lines.append(
                f"• {format_datetime(event['created_at'])} - "
                f"<b>{escape(event['full_name'])}</b>: {escape(event['description'])}{points_suffix}"
            )
        return "\n".join(lines)

    async def notify_clan(bot: Bot, telegram_id: int, text: str) -> None:
        clan = db.get_user_clan(telegram_id)
        if not clan:
            return
        member_ids = db.get_clan_member_telegram_ids(int(clan["id"]), exclude_telegram_id=telegram_id)
        for member_id in member_ids:
            try:
                await bot.send_message(member_id, text)
            except Exception as exc:  # pragma: no cover - network side effect
                logger.warning("Failed to notify clan member %s: %s", member_id, exc)

    async def show_tasks(target: Message | CallbackQuery) -> None:
        telegram_id = target.from_user.id
        tasks = db.list_tasks(telegram_id)
        active_task = db.get_active_task(telegram_id)
        text = format_tasks_text(tasks, active_task)
        keyboard = tasks_hub_keyboard(bool(tasks), bool(active_task))
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=keyboard)
            await target.answer()
        else:
            await target.answer(text, reply_markup=keyboard)

    async def show_active_task(target: Message | CallbackQuery) -> None:
        active_task = db.get_active_task(target.from_user.id)
        if not active_task:
            text = "Сейчас нет активной задачи. Откройте раздел задач и запустите любую из списка."
            if isinstance(target, CallbackQuery):
                await target.answer(text, show_alert=True)
            else:
                await target.answer(text)
            return

        text = (
            f"<b>Активная задача</b>\n\n"
            f"{escape(active_task['title'])}\n"
            f"Очки: <b>{active_task['points']}</b>\n"
            f"Старт: {format_datetime(active_task['started_at'])}\n"
            f"Таймер: {format_minutes(active_task['duration_minutes'])}"
        )
        if active_task.get("ends_at"):
            text += f"\nОкончание: {format_datetime(active_task['ends_at'])}"

        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=active_task_keyboard())
            await target.answer()
        else:
            await target.answer(text, reply_markup=active_task_keyboard())

    async def show_rewards(target: Message | CallbackQuery) -> None:
        profile = db.get_profile(target.from_user.id)
        text = format_rewards_hub(profile)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=rewards_hub_keyboard())
            await target.answer()
        else:
            await target.answer(text, reply_markup=rewards_hub_keyboard())

    async def show_reward_list(callback: CallbackQuery, kind: str, notice: str | None = None) -> None:
        rewards = db.list_rewards(callback.from_user.id, kind)
        prefix = "rewards:claim" if kind == "milestone" else "rewards:buy"
        await callback.message.edit_text(
            format_reward_list(kind, rewards),
            reply_markup=reward_selection_keyboard(rewards, prefix, "rewards:hub"),
        )
        await callback.answer(notice)

    async def show_settings(target: Message | CallbackQuery) -> None:
        profile = db.get_profile(target.from_user.id)
        text = (
            "<b>Настройки</b>\n\n"
            f"Очки за новую задачу по умолчанию: <b>{profile['default_task_points']}</b>\n"
            "Если хотите, можно одним нажатием выровнять ценность всех текущих задач."
        )
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=settings_keyboard())
            await target.answer()
        else:
            await target.answer(text, reply_markup=settings_keyboard())

    async def show_clan(target: Message | CallbackQuery) -> None:
        clan = db.get_user_clan(target.from_user.id)
        if not clan:
            text = (
                "<b>Кланы</b>\n\n"
                "У вас пока нет клана. Создайте свой или вступите по коду друга."
            )
            if isinstance(target, CallbackQuery):
                await target.message.edit_text(text, reply_markup=clan_guest_keyboard())
                await target.answer()
            else:
                await target.answer(text, reply_markup=clan_guest_keyboard())
            return

        leaderboard = db.get_clan_leaderboard(target.from_user.id)
        text = format_clan_summary(clan, leaderboard)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=clan_member_keyboard())
            await target.answer()
        else:
            await target.answer(text, reply_markup=clan_member_keyboard())

    async def show_stats(message: Message) -> None:
        profile = db.get_profile(message.from_user.id)
        history = db.list_reward_history(message.from_user.id, limit=5)
        history_lines = [f"• {item['title']} ({'магазин' if item['kind'] == 'shop' else 'достижение'})" for item in history]
        history_block = "\n".join(history_lines) if history_lines else "История наград пока пустая."
        text = (
            "<b>Статистика</b>\n\n"
            f"Всего очков заработано: <b>{profile['total_points']}</b>\n"
            f"Очков потрачено: <b>{profile['points_spent']}</b>\n"
            f"Очков доступно: <b>{profile['available_points']}</b>\n"
            f"Создано задач: <b>{profile['task_count']}</b>\n"
            f"Завершено задач: <b>{profile['completed_tasks']}</b>\n\n"
            "<b>Последние награды</b>\n"
            f"{history_block}"
        )
        await message.answer(text)

    @router.message(CommandStart())
    async def command_start(message: Message) -> None:
        await ensure_user(message.from_user)
        text = (
            "<b>Everyday Events</b>\n\n"
            "Этот бот превращает ваши повседневные задачи в игру: вы создаете свои дела, "
            "назначаете им ценность в очках, запускаете их с таймером или без, "
            "получаете награды и соревнуетесь в кланах.\n\n"
            "Нажмите нужный раздел на клавиатуре внизу."
        )
        await message.answer(text, reply_markup=main_menu_keyboard())

    @router.message(Command("menu"))
    async def command_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await message.answer("Главное меню снова под рукой.", reply_markup=main_menu_keyboard())

    @router.message(Command("help"))
    async def command_help(message: Message) -> None:
        await ensure_user(message.from_user)
        await message.answer(
            "Основные команды: /start, /menu, /cancel.\n"
            "Основные разделы доступны на клавиатуре: задачи, награды, кланы, настройки и статистика."
        )

    @router.message(Command("cancel"))
    async def command_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Текущее действие отменено.", reply_markup=main_menu_keyboard())

    @router.message(F.text == "Мои задачи")
    async def tasks_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await show_tasks(message)

    @router.message(F.text == "Активная задача")
    async def active_task_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await show_active_task(message)

    @router.message(F.text == "Магазин и награды")
    async def rewards_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await show_rewards(message)

    @router.message(F.text == "Настройки")
    async def settings_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await show_settings(message)

    @router.message(F.text == "Кланы")
    async def clans_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await show_clan(message)

    @router.message(F.text == "Статистика")
    async def stats_menu(message: Message) -> None:
        await ensure_user(message.from_user)
        await show_stats(message)

    @router.callback_query(F.data == "tasks:hub")
    async def tasks_hub_callback(callback: CallbackQuery) -> None:
        await ensure_user(callback.from_user)
        await show_tasks(callback)

    @router.callback_query(F.data == "tasks:add")
    async def tasks_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await ensure_user(callback.from_user)
        await state.set_state(TaskCreationState.waiting_title)
        await callback.message.answer("Введите название новой задачи.")
        await callback.answer()

    @router.message(TaskCreationState.waiting_title)
    async def task_title_received(message: Message, state: FSMContext) -> None:
        title = (message.text or "").strip()
        if not title:
            await message.answer("Название не должно быть пустым. Попробуйте еще раз.")
            return
        await state.update_data(title=title)
        await state.set_state(TaskCreationState.waiting_points)
        await message.answer(
            "Сколько очков давать за задачу?\n"
            "Введите число или слово <code>default</code>, чтобы взять значение по умолчанию."
        )

    @router.message(TaskCreationState.waiting_points)
    async def task_points_received(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").strip().lower()
        if raw_value == "default":
            profile = db.get_profile(message.from_user.id)
            points = int(profile["default_task_points"])
        else:
            if not raw_value.isdigit() or int(raw_value) <= 0:
                await message.answer("Введите положительное число или слово <code>default</code>.")
                return
            points = int(raw_value)

        await state.update_data(points=points)
        await state.set_state(TaskCreationState.waiting_duration)
        await message.answer(
            "Введите таймер по умолчанию в минутах.\n"
            "Если таймер не нужен, отправьте <code>0</code>."
        )

    @router.message(TaskCreationState.waiting_duration)
    async def task_duration_received(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").strip()
        if not raw_value.isdigit() or int(raw_value) < 0:
            await message.answer("Введите число минут от 0 и выше.")
            return
        duration = int(raw_value) or None
        data = await state.get_data()
        task = db.create_task(
            message.from_user.id,
            data["title"],
            int(data["points"]),
            duration,
        )
        await state.clear()
        await message.answer(
            f"Задача <b>{escape(task['title'])}</b> создана.\n"
            f"Очки: {task['points']}\n"
            f"Таймер по умолчанию: {format_minutes(task['default_duration_minutes'])}",
            reply_markup=main_menu_keyboard(),
        )
        await show_tasks(message)

    @router.callback_query(F.data == "tasks:start")
    async def tasks_start_list(callback: CallbackQuery) -> None:
        await ensure_user(callback.from_user)
        tasks = db.list_tasks(callback.from_user.id)
        if not tasks:
            await callback.answer("Сначала добавьте хотя бы одну задачу.", show_alert=True)
            return
        await callback.message.edit_text(
            "<b>Выберите задачу для запуска</b>",
            reply_markup=task_selection_keyboard(tasks, "tasks:start_pick"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("tasks:start_pick:"))
    async def tasks_start_pick(callback: CallbackQuery) -> None:
        await ensure_user(callback.from_user)
        task_id = int(callback.data.rsplit(":", 1)[-1])
        task = db.get_task(callback.from_user.id, task_id)
        if not task:
            await callback.answer("Задача не найдена.", show_alert=True)
            return
        await callback.message.edit_text(
            (
                f"Запускаем <b>{escape(task['title'])}</b>.\n"
                f"Очки: {task['points']}\n"
                f"Таймер по умолчанию: {format_minutes(task['default_duration_minutes'])}\n\n"
                "Какой режим выбрать?"
            ),
            reply_markup=timer_choice_keyboard(task_id, bool(task["default_duration_minutes"])),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("tasks:timer:none:"))
    async def tasks_timer_none(callback: CallbackQuery) -> None:
        task_id = int(callback.data.rsplit(":", 1)[-1])
        try:
            active_task = db.start_task(callback.from_user.id, task_id, None)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await callback.message.edit_text(
            f"Задача <b>{escape(active_task['title'])}</b> запущена без таймера.",
            reply_markup=active_task_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("tasks:timer:default:"))
    async def tasks_timer_default(callback: CallbackQuery) -> None:
        task_id = int(callback.data.rsplit(":", 1)[-1])
        task = db.get_task(callback.from_user.id, task_id)
        if not task or not task["default_duration_minutes"]:
            await callback.answer("У задачи нет таймера по умолчанию.", show_alert=True)
            return
        try:
            active_task = db.start_task(callback.from_user.id, task_id, int(task["default_duration_minutes"]))
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        scheduler.schedule_active_task(callback.from_user.id, active_task.get("ends_at"))
        await callback.message.edit_text(
            (
                f"Задача <b>{escape(active_task['title'])}</b> запущена.\n"
                f"Таймер: {format_minutes(active_task['duration_minutes'])}\n"
                f"Окончание: {format_datetime(active_task['ends_at'])}"
            ),
            reply_markup=active_task_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("tasks:timer:custom:"))
    async def tasks_timer_custom(callback: CallbackQuery, state: FSMContext) -> None:
        task_id = int(callback.data.rsplit(":", 1)[-1])
        await state.update_data(start_task_id=task_id)
        await state.set_state(CustomTimerState.waiting_minutes)
        await callback.message.answer("Введите свой таймер в минутах.")
        await callback.answer()

    @router.message(CustomTimerState.waiting_minutes)
    async def custom_timer_received(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").strip()
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await message.answer("Введите положительное число минут.")
            return
        duration = int(raw_value)
        data = await state.get_data()
        try:
            active_task = db.start_task(message.from_user.id, int(data["start_task_id"]), duration)
        except ValueError as exc:
            await message.answer(str(exc))
            await state.clear()
            return
        scheduler.schedule_active_task(message.from_user.id, active_task.get("ends_at"))
        await state.clear()
        await message.answer(
            (
                f"Задача <b>{escape(active_task['title'])}</b> запущена.\n"
                f"Таймер: {format_minutes(active_task['duration_minutes'])}\n"
                f"Окончание: {format_datetime(active_task['ends_at'])}"
            ),
            reply_markup=active_task_keyboard(),
        )

    @router.callback_query(F.data == "tasks:complete")
    async def tasks_complete(callback: CallbackQuery) -> None:
        try:
            completed = db.complete_active_task(callback.from_user.id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        scheduler.remove_job(callback.from_user.id)
        clan = db.record_clan_event_for_telegram_user(
            callback.from_user.id,
            "task_complete",
            f"Завершил задачу «{completed['title']}».",
            int(completed["points"]),
        )
        if clan:
            await notify_clan(
                callback.bot,
                callback.from_user.id,
                (
                    f"Соклановец завершил задачу <b>{escape(completed['title'])}</b> "
                    f"и получил {completed['points']} очков."
                ),
            )

        await callback.message.edit_text(
            (
                f"Задача <b>{escape(completed['title'])}</b> завершена.\n"
                f"Начислено: <b>{completed['points']}</b> очков\n"
                f"Всего заработано: <b>{completed['total_points']}</b>\n"
                f"Доступно сейчас: <b>{completed['available_points']}</b>"
            ),
            reply_markup=tasks_hub_keyboard(bool(db.list_tasks(callback.from_user.id)), False),
        )
        await callback.answer("Очки начислены.")

    @router.callback_query(F.data == "tasks:cancel")
    async def tasks_cancel(callback: CallbackQuery) -> None:
        active_task = db.cancel_active_task(callback.from_user.id)
        if not active_task:
            await callback.answer("Активной задачи нет.", show_alert=True)
            return
        scheduler.remove_job(callback.from_user.id)
        await callback.message.edit_text(
            f"Задача <b>{escape(active_task['title'])}</b> снята с активного выполнения.",
            reply_markup=tasks_hub_keyboard(bool(db.list_tasks(callback.from_user.id)), False),
        )
        await callback.answer()

    @router.callback_query(F.data == "tasks:delete")
    async def tasks_delete_list(callback: CallbackQuery) -> None:
        tasks = db.list_tasks(callback.from_user.id)
        if not tasks:
            await callback.answer("Удалять пока нечего.", show_alert=True)
            return
        await callback.message.edit_text(
            "<b>Выберите задачу для удаления</b>",
            reply_markup=task_selection_keyboard(tasks, "tasks:delete_pick"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("tasks:delete_pick:"))
    async def tasks_delete_pick(callback: CallbackQuery) -> None:
        task_id = int(callback.data.rsplit(":", 1)[-1])
        deleted = db.archive_task(callback.from_user.id, task_id)
        if not deleted:
            await callback.answer("Задача уже удалена или не найдена.", show_alert=True)
            return
        await callback.answer("Задача удалена.")
        await show_tasks(callback)

    @router.callback_query(F.data == "rewards:history")
    async def rewards_history(callback: CallbackQuery) -> None:
        history = db.list_reward_history(callback.from_user.id)
        await callback.message.edit_text(format_history(history), reply_markup=rewards_hub_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("rewards:add:"))
    async def rewards_add_start(callback: CallbackQuery, state: FSMContext) -> None:
        kind = callback.data.rsplit(":", 1)[-1]
        await state.update_data(reward_kind=kind)
        await state.set_state(RewardCreationState.waiting_title)
        reward_type = "награды за достижение" if kind == "milestone" else "товара в магазине"
        await callback.message.answer(f"Введите название для {reward_type}.")
        await callback.answer()

    @router.message(RewardCreationState.waiting_title)
    async def reward_title_received(message: Message, state: FSMContext) -> None:
        title = (message.text or "").strip()
        if not title:
            await message.answer("Название не должно быть пустым.")
            return
        await state.update_data(title=title)
        await state.set_state(RewardCreationState.waiting_cost)
        await message.answer("Введите стоимость или порог в очках.")

    @router.message(RewardCreationState.waiting_cost)
    async def reward_cost_received(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").strip()
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await message.answer("Введите положительное число.")
            return
        await state.update_data(cost=int(raw_value))
        await state.set_state(RewardCreationState.waiting_description)
        await message.answer("Введите описание или отправьте <code>-</code>.")

    @router.message(RewardCreationState.waiting_description)
    async def reward_description_received(message: Message, state: FSMContext) -> None:
        description = (message.text or "").strip()
        data = await state.get_data()
        reward = db.create_reward(
            message.from_user.id,
            data["title"],
            int(data["cost"]),
            "" if description == "-" else description,
            data["reward_kind"],
        )
        await state.clear()
        reward_type = "Награда за достижение" if reward["kind"] == "milestone" else "Товар в магазине"
        await message.answer(
            f"{reward_type} <b>{escape(reward['title'])}</b> создан(а) со стоимостью {reward['cost']} очков.",
            reply_markup=main_menu_keyboard(),
        )
        await show_rewards(message)

    @router.callback_query(F.data.startswith("rewards:list:"))
    async def rewards_list(callback: CallbackQuery) -> None:
        kind = callback.data.rsplit(":", 1)[-1]
        await show_reward_list(callback, kind)

    @router.callback_query(F.data == "rewards:hub")
    async def rewards_hub_callback(callback: CallbackQuery) -> None:
        await show_rewards(callback)

    @router.callback_query(F.data.startswith("rewards:claim:"))
    async def rewards_claim(callback: CallbackQuery) -> None:
        reward_id = int(callback.data.rsplit(":", 1)[-1])
        try:
            reward = db.claim_milestone(callback.from_user.id, reward_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        db.record_clan_event_for_telegram_user(
            callback.from_user.id,
            "milestone_claim",
            f"Получил награду «{reward['title']}».",
            0,
        )
        await notify_clan(
            callback.bot,
            callback.from_user.id,
            f"Соклановец получил награду <b>{escape(reward['title'])}</b>."
        )
        await show_reward_list(callback, "milestone", "Награда получена.")

    @router.callback_query(F.data.startswith("rewards:buy:"))
    async def rewards_buy(callback: CallbackQuery) -> None:
        reward_id = int(callback.data.rsplit(":", 1)[-1])
        try:
            reward = db.purchase_shop_reward(callback.from_user.id, reward_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        db.record_clan_event_for_telegram_user(
            callback.from_user.id,
            "shop_buy",
            f"Купил «{reward['title']}» в магазине.",
            0,
        )
        await notify_clan(
            callback.bot,
            callback.from_user.id,
            f"Соклановец купил в магазине <b>{escape(reward['title'])}</b>."
        )
        await show_reward_list(callback, "shop", "Покупка оформлена.")

    @router.callback_query(F.data == "settings:default_points")
    async def settings_default_points(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(DefaultPointsState.waiting_points)
        await callback.message.answer("Введите новое значение очков по умолчанию для новых задач.")
        await callback.answer()

    @router.message(DefaultPointsState.waiting_points)
    async def settings_default_points_received(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").strip()
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await message.answer("Введите положительное число.")
            return
        db.set_default_task_points(message.from_user.id, int(raw_value))
        await state.clear()
        await message.answer("Значение по умолчанию обновлено.", reply_markup=main_menu_keyboard())
        await show_settings(message)

    @router.callback_query(F.data == "settings:apply_default")
    async def settings_apply_default(callback: CallbackQuery) -> None:
        updated = db.apply_default_points_to_all_tasks(callback.from_user.id)
        await callback.answer(f"Обновлено задач: {updated}.", show_alert=True)
        await show_settings(callback)

    @router.callback_query(F.data == "clan:create")
    async def clan_create_start(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(ClanCreationState.waiting_name)
        await callback.message.answer("Введите название нового клана.")
        await callback.answer()

    @router.message(ClanCreationState.waiting_name)
    async def clan_create_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if len(name) < 2:
            await message.answer("Название должно быть длиннее.")
            return
        try:
            clan = db.create_clan(message.from_user.id, name)
        except ValueError as exc:
            await message.answer(str(exc))
            await state.clear()
            return
        await state.clear()
        await message.answer(
            (
                f"Клан <b>{escape(clan['name'])}</b> создан.\n"
                f"Код для друзей: <code>{clan['code']}</code>"
            ),
            reply_markup=main_menu_keyboard(),
        )
        await show_clan(message)

    @router.callback_query(F.data == "clan:join")
    async def clan_join_start(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(ClanJoinState.waiting_code)
        await callback.message.answer("Введите код клана.")
        await callback.answer()

    @router.message(ClanJoinState.waiting_code)
    async def clan_join_code(message: Message, state: FSMContext) -> None:
        code = (message.text or "").strip().upper()
        if len(code) < 4:
            await message.answer("Похоже на слишком короткий код. Проверьте и отправьте еще раз.")
            return
        try:
            clan = db.join_clan(message.from_user.id, code)
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await state.clear()
        await message.answer(
            (
                f"Вы вступили в клан <b>{escape(clan['name'])}</b>.\n"
                f"Код клана: <code>{clan['code']}</code>"
            ),
            reply_markup=main_menu_keyboard(),
        )
        await notify_clan(
            message.bot,
            message.from_user.id,
            f"В клан вступил новый участник."
        )
        await show_clan(message)

    @router.callback_query(F.data == "clan:leaderboard")
    async def clan_leaderboard(callback: CallbackQuery) -> None:
        rows = db.get_clan_leaderboard(callback.from_user.id)
        await callback.message.edit_text(format_leaderboard(rows), reply_markup=clan_member_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "clan:feed")
    async def clan_feed(callback: CallbackQuery) -> None:
        events = db.list_clan_events(callback.from_user.id)
        await callback.message.edit_text(format_clan_events(events), reply_markup=clan_member_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "clan:leave")
    async def clan_leave(callback: CallbackQuery) -> None:
        try:
            result = db.leave_clan(callback.from_user.id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if result["action"] == "disbanded":
            text = f"Клан <b>{escape(result['clan_name'])}</b> был распущен, потому что вышел владелец."
        else:
            text = f"Вы покинули клан <b>{escape(result['clan_name'])}</b>."
        await callback.message.edit_text(text, reply_markup=clan_guest_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "clan:hub")
    async def clan_hub_callback(callback: CallbackQuery) -> None:
        await show_clan(callback)

    @router.message()
    async def fallback_message(message: Message) -> None:
        await ensure_user(message.from_user)
        await message.answer(
            "Я не понял это сообщение. Используйте кнопки меню внизу или команды /start, /menu, /cancel."
        )

    return router
