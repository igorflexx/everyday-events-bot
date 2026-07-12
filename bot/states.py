from aiogram.fsm.state import State, StatesGroup


class TaskCreationState(StatesGroup):
    waiting_title = State()
    waiting_points = State()
    waiting_duration = State()


class CustomTimerState(StatesGroup):
    waiting_minutes = State()


class RewardCreationState(StatesGroup):
    waiting_title = State()
    waiting_cost = State()
    waiting_description = State()


class DefaultPointsState(StatesGroup):
    waiting_points = State()


class ClanCreationState(StatesGroup):
    waiting_name = State()


class ClanJoinState(StatesGroup):
    waiting_code = State()

