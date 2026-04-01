from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        coin_ids=("bitcoin",),
        vs_currency="usd",
        poll_interval_sec=30,
        price_alert_threshold_percent=1.0,
        database_path=tmp_path / "t.db",
    )
