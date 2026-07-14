from dataclasses import dataclass
from pathlib import Path
import os

from aiogram.utils.token import TokenValidationError, validate_token
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_path: Path


def load_config() -> Config:
    bot_token = ""
    token_file = BASE_DIR / "bot_token.txt"
    if token_file.exists():
        bot_token = token_file.read_text(encoding="utf-8").strip()
    if not bot_token:
        bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Fill in .env at the project root "
            "or create bot_token.txt next to it."
        )
    try:
        validate_token(bot_token)
    except TokenValidationError as exc:
        raise RuntimeError(
            "Telegram token is invalid. Check the value in "
            "bot_token.txt or .env. "
            "The token must be copied exactly from @BotFather, without extra spaces or quotes."
        ) from exc

    database_path = Path(
        os.getenv(
            "DATABASE_PATH",
            str(BASE_DIR / "data" / "everyday_events.db"),
        )
    )

    return Config(bot_token=bot_token, database_path=database_path)
