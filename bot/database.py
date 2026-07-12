from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sqlite3
import string
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Database:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    total_points INTEGER NOT NULL DEFAULT 0,
                    points_spent INTEGER NOT NULL DEFAULT 0,
                    default_task_points INTEGER NOT NULL DEFAULT 10,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    points INTEGER NOT NULL,
                    default_duration_minutes INTEGER,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS active_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    task_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    duration_minutes INTEGER,
                    ends_at TEXT,
                    reminder_sent INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    task_title TEXT NOT NULL,
                    points_awarded INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    duration_minutes INTEGER,
                    planned_duration_minutes INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    cost INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('milestone', 'shop')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reward_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    reward_id INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL,
                    spent_points INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (reward_id) REFERENCES rewards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS clans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    code TEXT NOT NULL UNIQUE,
                    owner_user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS clan_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clan_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL UNIQUE,
                    joined_at TEXT NOT NULL,
                    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS clan_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clan_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    points_delta INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )

    def close(self) -> None:
        self.connection.close()

    def _dicts(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _get_user_id(self, telegram_id: int) -> int:
        row = self.connection.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if not row:
            raise ValueError("Пользователь не найден. Нажмите /start.")
        return int(row["id"])

    def _get_clan_id_for_user(self, user_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT clan_id FROM clan_members WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["clan_id"]) if row else None

    def register_user(self, telegram_id: int, username: str | None, full_name: str) -> None:
        now = utc_now().isoformat()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO users (telegram_id, username, full_name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id)
                DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name
                """,
                (telegram_id, username, full_name, now),
            )

    def get_profile(self, telegram_id: int) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT
                u.*,
                (
                    SELECT COUNT(*)
                    FROM tasks t
                    WHERE t.user_id = u.id AND t.is_archived = 0
                ) AS task_count,
                (
                    SELECT COUNT(*)
                    FROM task_sessions s
                    WHERE s.user_id = u.id
                ) AS completed_tasks,
                (
                    SELECT COUNT(*)
                    FROM rewards r
                    WHERE r.user_id = u.id AND r.kind = 'shop' AND r.is_active = 1
                ) AS shop_items,
                (
                    SELECT COUNT(*)
                    FROM rewards r
                    WHERE r.user_id = u.id AND r.kind = 'milestone' AND r.is_active = 1
                ) AS milestone_items
            FROM users u
            WHERE u.telegram_id = ?
            """,
            (telegram_id,),
        ).fetchone()
        if not row:
            raise ValueError("Пользователь не найден. Нажмите /start.")
        profile = dict(row)
        profile["available_points"] = profile["total_points"] - profile["points_spent"]
        return profile

    def set_default_task_points(self, telegram_id: int, points: int) -> None:
        user_id = self._get_user_id(telegram_id)
        with self.connection:
            self.connection.execute(
                "UPDATE users SET default_task_points = ? WHERE id = ?",
                (points, user_id),
            )

    def apply_default_points_to_all_tasks(self, telegram_id: int) -> int:
        profile = self.get_profile(telegram_id)
        user_id = self._get_user_id(telegram_id)
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE tasks
                SET points = ?
                WHERE user_id = ? AND is_archived = 0
                """,
                (profile["default_task_points"], user_id),
            )
        return cursor.rowcount

    def create_task(
        self,
        telegram_id: int,
        title: str,
        points: int,
        default_duration_minutes: int | None,
    ) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        now = utc_now().isoformat()
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO tasks (user_id, title, points, default_duration_minutes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, title, points, default_duration_minutes, now),
            )
        task_id = cursor.lastrowid
        return self.get_task(telegram_id, int(task_id))

    def list_tasks(self, telegram_id: int) -> list[dict[str, Any]]:
        user_id = self._get_user_id(telegram_id)
        rows = self.connection.execute(
            """
            SELECT *
            FROM tasks
            WHERE user_id = ? AND is_archived = 0
            ORDER BY created_at ASC, id ASC
            """,
            (user_id,),
        ).fetchall()
        return self._dicts(rows)

    def get_task(self, telegram_id: int, task_id: int) -> dict[str, Any] | None:
        user_id = self._get_user_id(telegram_id)
        row = self.connection.execute(
            """
            SELECT *
            FROM tasks
            WHERE id = ? AND user_id = ? AND is_archived = 0
            """,
            (task_id, user_id),
        ).fetchone()
        return self._dict(row)

    def archive_task(self, telegram_id: int, task_id: int) -> bool:
        user_id = self._get_user_id(telegram_id)
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE tasks
                SET is_archived = 1
                WHERE id = ? AND user_id = ? AND is_archived = 0
                """,
                (task_id, user_id),
            )
        return cursor.rowcount > 0

    def get_active_task(self, telegram_id: int) -> dict[str, Any] | None:
        user_id = self._get_user_id(telegram_id)
        row = self.connection.execute(
            """
            SELECT
                a.*,
                t.title,
                t.points,
                t.default_duration_minutes
            FROM active_tasks a
            JOIN tasks t ON t.id = a.task_id
            WHERE a.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return self._dict(row)

    def start_task(self, telegram_id: int, task_id: int, duration_minutes: int | None) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        task = self.get_task(telegram_id, task_id)
        if not task:
            raise ValueError("Задача не найдена.")
        if self.get_active_task(telegram_id):
            raise ValueError("Сначала завершите или отмените текущую активную задачу.")

        now = utc_now()
        ends_at = None
        if duration_minutes:
            ends_at = (now + timedelta(minutes=duration_minutes)).isoformat()

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO active_tasks (user_id, task_id, started_at, duration_minutes, ends_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, task_id, now.isoformat(), duration_minutes, ends_at),
            )
        return self.get_active_task(telegram_id) or {}

    def cancel_active_task(self, telegram_id: int) -> dict[str, Any] | None:
        active_task = self.get_active_task(telegram_id)
        if not active_task:
            return None
        user_id = self._get_user_id(telegram_id)
        with self.connection:
            self.connection.execute("DELETE FROM active_tasks WHERE user_id = ?", (user_id,))
        return active_task

    def complete_active_task(self, telegram_id: int) -> dict[str, Any]:
        active_task = self.get_active_task(telegram_id)
        if not active_task:
            raise ValueError("Сейчас нет активной задачи.")

        user_id = self._get_user_id(telegram_id)
        completed_at = utc_now().isoformat()
        started_at = datetime.fromisoformat(active_task["started_at"])
        duration_minutes = int((utc_now() - started_at).total_seconds() // 60)

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO task_sessions (
                    user_id,
                    task_id,
                    task_title,
                    points_awarded,
                    started_at,
                    completed_at,
                    duration_minutes,
                    planned_duration_minutes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    active_task["task_id"],
                    active_task["title"],
                    active_task["points"],
                    active_task["started_at"],
                    completed_at,
                    duration_minutes,
                    active_task["duration_minutes"],
                ),
            )
            self.connection.execute(
                "UPDATE users SET total_points = total_points + ? WHERE id = ?",
                (active_task["points"], user_id),
            )
            self.connection.execute("DELETE FROM active_tasks WHERE user_id = ?", (user_id,))

        profile = self.get_profile(telegram_id)
        active_task["actual_duration_minutes"] = duration_minutes
        active_task["available_points"] = profile["available_points"]
        active_task["total_points"] = profile["total_points"]
        return active_task

    def mark_reminder_sent(self, telegram_id: int) -> None:
        user_id = self._get_user_id(telegram_id)
        with self.connection:
            self.connection.execute(
                "UPDATE active_tasks SET reminder_sent = 1 WHERE user_id = ?",
                (user_id,),
            )

    def list_pending_reminders(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
                a.*,
                u.telegram_id,
                t.title,
                t.points
            FROM active_tasks a
            JOIN users u ON u.id = a.user_id
            JOIN tasks t ON t.id = a.task_id
            WHERE a.ends_at IS NOT NULL AND a.reminder_sent = 0
            ORDER BY a.ends_at ASC
            """
        ).fetchall()
        return self._dicts(rows)

    def create_reward(
        self,
        telegram_id: int,
        title: str,
        cost: int,
        description: str,
        kind: str,
    ) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        now = utc_now().isoformat()
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO rewards (user_id, title, description, cost, kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, title, description, cost, kind, now),
            )
        return self.get_reward(telegram_id, int(cursor.lastrowid))

    def get_reward(self, telegram_id: int, reward_id: int) -> dict[str, Any] | None:
        user_id = self._get_user_id(telegram_id)
        row = self.connection.execute(
            """
            SELECT *
            FROM rewards
            WHERE id = ? AND user_id = ? AND is_active = 1
            """,
            (reward_id, user_id),
        ).fetchone()
        return self._dict(row)

    def list_rewards(self, telegram_id: int, kind: str) -> list[dict[str, Any]]:
        user_id = self._get_user_id(telegram_id)
        profile = self.get_profile(telegram_id)
        rows = self.connection.execute(
            """
            SELECT
                r.*,
                EXISTS(
                    SELECT 1
                    FROM reward_claims rc
                    WHERE rc.reward_id = r.id AND rc.user_id = ?
                ) AS claimed
            FROM rewards r
            WHERE r.user_id = ? AND r.kind = ? AND r.is_active = 1
            ORDER BY r.cost ASC, r.created_at ASC
            """,
            (user_id, user_id, kind),
        ).fetchall()
        rewards = self._dicts(rows)
        for reward in rewards:
            reward["can_claim"] = profile["total_points"] >= reward["cost"] and not reward["claimed"]
            reward["can_buy"] = profile["available_points"] >= reward["cost"]
        return rewards

    def claim_milestone(self, telegram_id: int, reward_id: int) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        reward = self.get_reward(telegram_id, reward_id)
        if not reward or reward["kind"] != "milestone":
            raise ValueError("Награда не найдена.")

        already_claimed = self.connection.execute(
            """
            SELECT 1
            FROM reward_claims
            WHERE reward_id = ? AND user_id = ?
            """,
            (reward_id, user_id),
        ).fetchone()
        if already_claimed:
            raise ValueError("Эта награда уже получена.")

        profile = self.get_profile(telegram_id)
        if profile["total_points"] < reward["cost"]:
            raise ValueError("Пока не хватает суммарных очков для этой награды.")

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO reward_claims (user_id, reward_id, claimed_at, spent_points)
                VALUES (?, ?, ?, 0)
                """,
                (user_id, reward_id, utc_now().isoformat()),
            )
        return reward

    def purchase_shop_reward(self, telegram_id: int, reward_id: int) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        reward = self.get_reward(telegram_id, reward_id)
        if not reward or reward["kind"] != "shop":
            raise ValueError("Товар не найден.")

        profile = self.get_profile(telegram_id)
        if profile["available_points"] < reward["cost"]:
            raise ValueError("Недостаточно доступных очков.")

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO reward_claims (user_id, reward_id, claimed_at, spent_points)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, reward_id, utc_now().isoformat(), reward["cost"]),
            )
            self.connection.execute(
                "UPDATE users SET points_spent = points_spent + ? WHERE id = ?",
                (reward["cost"], user_id),
            )
        return reward

    def list_reward_history(self, telegram_id: int, limit: int = 10) -> list[dict[str, Any]]:
        user_id = self._get_user_id(telegram_id)
        rows = self.connection.execute(
            """
            SELECT
                rc.claimed_at,
                rc.spent_points,
                r.title,
                r.kind,
                r.cost
            FROM reward_claims rc
            JOIN rewards r ON r.id = rc.reward_id
            WHERE rc.user_id = ?
            ORDER BY rc.claimed_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return self._dicts(rows)

    def _generate_unique_clan_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            exists = self.connection.execute(
                "SELECT 1 FROM clans WHERE code = ?",
                (code,),
            ).fetchone()
            if not exists:
                return code
        raise RuntimeError("Не удалось создать уникальный код клана.")

    def create_clan(self, telegram_id: int, name: str) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        if self._get_clan_id_for_user(user_id):
            raise ValueError("Сначала выйдите из текущего клана.")

        now = utc_now().isoformat()
        code = self._generate_unique_clan_code()
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO clans (name, code, owner_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, code, user_id, now),
            )
            clan_id = int(cursor.lastrowid)
            self.connection.execute(
                """
                INSERT INTO clan_members (clan_id, user_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (clan_id, user_id, now),
            )
        self.add_clan_event(
            clan_id,
            user_id,
            "create",
            f"Создан клан «{name}».",
            0,
        )
        return self.get_user_clan(telegram_id) or {}

    def join_clan(self, telegram_id: int, code: str) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        if self._get_clan_id_for_user(user_id):
            raise ValueError("Сначала выйдите из текущего клана.")

        clan = self.connection.execute(
            "SELECT * FROM clans WHERE code = ?",
            (code.upper(),),
        ).fetchone()
        if not clan:
            raise ValueError("Клан с таким кодом не найден.")

        now = utc_now().isoformat()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO clan_members (clan_id, user_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (clan["id"], user_id, now),
            )
        self.add_clan_event(
            int(clan["id"]),
            user_id,
            "join",
            "Новый участник вступил в клан.",
            0,
        )
        return self.get_user_clan(telegram_id) or {}

    def leave_clan(self, telegram_id: int) -> dict[str, Any]:
        user_id = self._get_user_id(telegram_id)
        clan = self.get_user_clan(telegram_id)
        if not clan:
            raise ValueError("Вы сейчас не в клане.")

        clan_row = self.connection.execute(
            "SELECT owner_user_id FROM clans WHERE id = ?",
            (clan["id"],),
        ).fetchone()
        owner_user_id = int(clan_row["owner_user_id"])

        with self.connection:
            if owner_user_id == user_id:
                self.connection.execute("DELETE FROM clans WHERE id = ?", (clan["id"],))
                action = "disbanded"
            else:
                self.connection.execute(
                    "DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?",
                    (clan["id"], user_id),
                )
                action = "left"

        return {"action": action, "clan_name": clan["name"], "clan_code": clan["code"]}

    def get_user_clan(self, telegram_id: int) -> dict[str, Any] | None:
        user_id = self._get_user_id(telegram_id)
        row = self.connection.execute(
            """
            SELECT
                c.*,
                (
                    SELECT COUNT(*)
                    FROM clan_members cm
                    WHERE cm.clan_id = c.id
                ) AS members_count
            FROM clans c
            JOIN clan_members cm ON cm.clan_id = c.id
            WHERE cm.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return self._dict(row)

    def get_clan_leaderboard(self, telegram_id: int) -> list[dict[str, Any]]:
        clan = self.get_user_clan(telegram_id)
        if not clan:
            return []
        rows = self.connection.execute(
            """
            SELECT
                u.full_name,
                u.username,
                u.telegram_id,
                u.total_points,
                u.points_spent,
                (u.total_points - u.points_spent) AS available_points,
                (
                    SELECT COUNT(*)
                    FROM task_sessions s
                    WHERE s.user_id = u.id
                ) AS completed_tasks
            FROM clan_members cm
            JOIN users u ON u.id = cm.user_id
            WHERE cm.clan_id = ?
            ORDER BY u.total_points DESC, completed_tasks DESC, u.full_name ASC
            """,
            (clan["id"],),
        ).fetchall()
        return self._dicts(rows)

    def list_clan_events(self, telegram_id: int, limit: int = 10) -> list[dict[str, Any]]:
        clan = self.get_user_clan(telegram_id)
        if not clan:
            return []
        rows = self.connection.execute(
            """
            SELECT
                e.*,
                u.full_name
            FROM clan_events e
            JOIN users u ON u.id = e.user_id
            WHERE e.clan_id = ?
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (clan["id"], limit),
        ).fetchall()
        return self._dicts(rows)

    def add_clan_event(
        self,
        clan_id: int,
        user_id: int,
        event_type: str,
        description: str,
        points_delta: int,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO clan_events (clan_id, user_id, event_type, description, points_delta, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clan_id, user_id, event_type, description, points_delta, utc_now().isoformat()),
            )

    def record_clan_event_for_telegram_user(
        self,
        telegram_id: int,
        event_type: str,
        description: str,
        points_delta: int,
    ) -> dict[str, Any] | None:
        user_id = self._get_user_id(telegram_id)
        clan_id = self._get_clan_id_for_user(user_id)
        if not clan_id:
            return None
        self.add_clan_event(clan_id, user_id, event_type, description, points_delta)
        clan = self.connection.execute(
            "SELECT * FROM clans WHERE id = ?",
            (clan_id,),
        ).fetchone()
        return self._dict(clan)

    def get_clan_member_telegram_ids(self, clan_id: int, exclude_telegram_id: int | None = None) -> list[int]:
        rows = self.connection.execute(
            """
            SELECT u.telegram_id
            FROM clan_members cm
            JOIN users u ON u.id = cm.user_id
            WHERE cm.clan_id = ?
            """,
            (clan_id,),
        ).fetchall()
        member_ids = [int(row["telegram_id"]) for row in rows]
        if exclude_telegram_id is not None:
            member_ids = [member_id for member_id in member_ids if member_id != exclude_telegram_id]
        return member_ids

