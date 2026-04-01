from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses

from app.core.config import Settings
from app.services.monitor import (
    CoinGeckoRateLimited,
    _parse_prices_from_payload,
    _percent_change,
    _retry_after_seconds,
    fetch_coin_prices_usd,
)

# Query string order may vary (ids=...&vs_currencies=... or the reverse).
COINGECKO_PRICE_URL = re.compile(
    r"https://api\.coingecko\.com/api/v3/simple/price\?.*"
)


def test_percent_change_basic() -> None:
    assert _percent_change(100.0, 101.0) == pytest.approx(1.0)
    assert _percent_change(100.0, 99.0) == pytest.approx(1.0)
    assert _percent_change(100.0, 100.0) == 0.0


def test_percent_change_zero_prev() -> None:
    assert _percent_change(0.0, 50.0) == 0.0


def test_parse_prices_ok(settings: Settings) -> None:
    data = {"bitcoin": {"usd": 67500.5}}
    got = _parse_prices_from_payload(data, settings.coin_ids, "usd")
    assert got == {"bitcoin": 67500.5}


def test_parse_prices_multi() -> None:
    data = {"bitcoin": {"usd": 1.0}, "ethereum": {"usd": 2.5}}
    got = _parse_prices_from_payload(data, ("bitcoin", "ethereum"), "usd")
    assert got == {"bitcoin": 1.0, "ethereum": 2.5}


def test_parse_prices_bad_coin(settings: Settings) -> None:
    with pytest.raises(ValueError, match="Unexpected response shape"):
        _parse_prices_from_payload({"bitcoin": "oops"}, settings.coin_ids, "usd")


def test_parse_prices_missing_key(settings: Settings) -> None:
    with pytest.raises(ValueError, match="Missing vs_currency"):
        _parse_prices_from_payload({"bitcoin": {}}, settings.coin_ids, "usd")


def test_retry_after_seconds_from_header() -> None:
    class Resp:
        headers = {"Retry-After": "42"}

    assert _retry_after_seconds(Resp(), 0) == 42.0


def test_retry_after_seconds_fallback_exponential() -> None:
    class Resp:
        headers: dict[str, str] = {}

    assert _retry_after_seconds(Resp(), 0) == 20.0
    assert _retry_after_seconds(Resp(), 1) == 40.0


@pytest.mark.asyncio
async def test_fetch_coin_prices_success(settings: Settings) -> None:
    with aioresponses() as m:
        m.get(
            COINGECKO_PRICE_URL,
            payload={"bitcoin": {"usd": 67000.0}},
        )
        async with aiohttp.ClientSession() as session:
            prices = await fetch_coin_prices_usd(session, settings, max_attempts=3)
    assert prices == {"bitcoin": 67000.0}


@pytest.mark.asyncio
async def test_fetch_429_then_success(settings: Settings) -> None:
    with patch("app.services.monitor.asyncio.sleep", new_callable=AsyncMock):
        with aioresponses() as m:
            m.get(COINGECKO_PRICE_URL, status=429, headers={"Retry-After": "0"})
            m.get(
                COINGECKO_PRICE_URL,
                payload={"bitcoin": {"usd": 67100.0}},
            )
            async with aiohttp.ClientSession() as session:
                prices = await fetch_coin_prices_usd(session, settings, max_attempts=3)
    assert prices == {"bitcoin": 67100.0}


@pytest.mark.asyncio
async def test_fetch_all_429_raises(settings: Settings) -> None:
    with patch("app.services.monitor.asyncio.sleep", new_callable=AsyncMock):
        with aioresponses() as m:
            for _ in range(3):
                m.get(COINGECKO_PRICE_URL, status=429, headers={"Retry-After": "0"})
            async with aiohttp.ClientSession() as session:
                with pytest.raises(CoinGeckoRateLimited):
                    await fetch_coin_prices_usd(session, settings, max_attempts=3)


@pytest.mark.asyncio
async def test_fetch_two_coins_one_request(tmp_path) -> None:
    settings = Settings(
        coin_ids=("bitcoin", "ethereum"),
        vs_currency="usd",
        poll_interval_sec=30,
        price_alert_threshold_percent=1.0,
        database_path=tmp_path / "x.db",
    )
    with aioresponses() as m:
        m.get(
            COINGECKO_PRICE_URL,
            payload={
                "bitcoin": {"usd": 100.0},
                "ethereum": {"usd": 200.0},
            },
        )
        async with aiohttp.ClientSession() as session:
            prices = await fetch_coin_prices_usd(session, settings, max_attempts=3)
    assert prices == {"bitcoin": 100.0, "ethereum": 200.0}
