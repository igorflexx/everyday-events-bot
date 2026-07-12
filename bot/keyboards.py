from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="Мои задачи"),
        KeyboardButton(text="Активная задача"),
    )
    builder.row(
        KeyboardButton(text="Магазин и награды"),
        KeyboardButton(text="Кланы"),
    )
    builder.row(
        KeyboardButton(text="Настройки"),
        KeyboardButton(text="Статистика"),
    )
    return builder.as_markup(resize_keyboard=True)


def tasks_hub_keyboard(has_tasks: bool, has_active_task: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить задачу", callback_data="tasks:add")
    if has_tasks:
        builder.button(text="Запустить задачу", callback_data="tasks:start")
        builder.button(text="Удалить задачу", callback_data="tasks:delete")
    if has_active_task:
        builder.button(text="Завершить активную", callback_data="tasks:complete")
        builder.button(text="Отменить активную", callback_data="tasks:cancel")
    builder.button(text="Обновить", callback_data="tasks:hub")
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def task_selection_keyboard(tasks: list[dict], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        builder.button(
            text=f"{task['title']} ({task['points']} очк.)",
            callback_data=f"{prefix}:{task['id']}",
        )
    builder.button(text="Назад", callback_data="tasks:hub")
    builder.adjust(1)
    return builder.as_markup()


def timer_choice_keyboard(task_id: int, has_default: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Без таймера", callback_data=f"tasks:timer:none:{task_id}")
    if has_default:
        builder.button(text="Стандартный таймер", callback_data=f"tasks:timer:default:{task_id}")
    builder.button(text="Свой таймер", callback_data=f"tasks:timer:custom:{task_id}")
    builder.button(text="Назад", callback_data="tasks:start")
    builder.adjust(1)
    return builder.as_markup()


def active_task_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Завершить", callback_data="tasks:complete")
    builder.button(text="Отменить", callback_data="tasks:cancel")
    builder.button(text="К задачам", callback_data="tasks:hub")
    builder.adjust(2, 1)
    return builder.as_markup()


def rewards_hub_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить награду за достижение", callback_data="rewards:add:milestone")
    builder.button(text="Добавить товар в магазин", callback_data="rewards:add:shop")
    builder.button(text="Показать награды", callback_data="rewards:list:milestone")
    builder.button(text="Показать магазин", callback_data="rewards:list:shop")
    builder.button(text="История наград", callback_data="rewards:history")
    builder.adjust(1)
    return builder.as_markup()


def reward_selection_keyboard(rewards: list[dict], prefix: str, back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reward in rewards:
        builder.button(
            text=f"{reward['title']} ({reward['cost']} очк.)",
            callback_data=f"{prefix}:{reward['id']}",
        )
    builder.button(text="Назад", callback_data=back_target)
    builder.adjust(1)
    return builder.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Изменить очки по умолчанию", callback_data="settings:default_points")
    builder.button(text="Применить ко всем задачам", callback_data="settings:apply_default")
    builder.button(text="Открыть задачи", callback_data="tasks:hub")
    builder.adjust(1)
    return builder.as_markup()


def clan_guest_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Создать клан", callback_data="clan:create")
    builder.button(text="Вступить по коду", callback_data="clan:join")
    builder.adjust(1)
    return builder.as_markup()


def clan_member_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Карточка клана", callback_data="clan:hub")
    builder.button(text="Таблица клана", callback_data="clan:leaderboard")
    builder.button(text="Лента событий", callback_data="clan:feed")
    builder.button(text="Покинуть клан", callback_data="clan:leave")
    builder.adjust(1)
    return builder.as_markup()
