from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _parse_coin_ids() -> tuple[str, ...]:
    """COIN_IDS=bitcoin,ethereum,... or fallback to COIN_ID (single coin)."""
    raw = os.getenv("COIN_IDS")
    if raw is not None and raw.strip():
        ids = tuple(x.strip().lower() for x in raw.split(",") if x.strip())
        if ids:
            return ids
    single = _env_str("COIN_ID", "bitcoin").strip().lower()
    return (single,) if single else ("bitcoin",)


@dataclass(frozen=True)
class Settings:
    coin_ids: tuple[str, ...]
    vs_currency: str
    poll_interval_sec: int
    price_alert_threshold_percent: float
    database_path: Path
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    # Optional CoinGecko Demo API key (higher rate limits than anonymous calls).
    coingecko_api_key: str = ""


def load_settings() -> Settings:
    db_rel = _env_str("DATABASE_PATH", "data/monitor.db")
    db_path = Path(db_rel)
    if not db_path.is_absolute():
        db_path = _PROJECT_ROOT / db_path
    return Settings(
        coin_ids=_parse_coin_ids(),
        vs_currency=_env_str("VS_CURRENCY", "usd").lower(),
        # Default 30s — the free public API often returns HTTP 429 if polled too often.
        poll_interval_sec=max(1, _env_int("POLL_INTERVAL_SEC", 30)),
        price_alert_threshold_percent=_env_float("PRICE_ALERT_THRESHOLD_PERCENT", 1.0),
        database_path=db_path,
        coingecko_api_key=_env_str("COINGECKO_API_KEY", ""),
    )
