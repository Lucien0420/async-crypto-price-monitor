from __future__ import annotations

import asyncio
import logging
import sys

import aiohttp
from aiohttp import ClientResponseError

from app.core.config import Settings
from app.database.store import fetch_last_price, init_db, insert_snapshot

logger = logging.getLogger(__name__)


class CoinGeckoRateLimited(RuntimeError):
    """CoinGecko kept returning HTTP 429 after retries."""


def _retry_after_seconds(resp: aiohttp.ClientResponse, attempt: int) -> float:
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return min(float(ra), 300.0)
        except ValueError:
            pass
    return min(20.0 * (2**attempt), 120.0)

# Red + bold, reset (works on Windows 10+ conhost / modern terminals)
ANSI_RED_BOLD = "\033[1;91m"
ANSI_RESET = "\033[0m"


def _enable_windows_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _percent_change(prev: float, current: float) -> float:
    if prev == 0:
        return 0.0
    return abs(current - prev) / prev * 100.0


def _parse_prices_from_payload(
    data: object,
    coin_ids: tuple[str, ...],
    vs_currency: str,
) -> dict[str, float]:
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected JSON root: {data!r}")
    out: dict[str, float] = {}
    for cid in coin_ids:
        coin = data.get(cid)
        if not isinstance(coin, dict):
            raise ValueError(f"Unexpected response shape for {cid!r}: {data!r}")
        raw = coin.get(vs_currency)
        if raw is None:
            raise ValueError(f"Missing vs_currency {vs_currency!r} in {coin!r}")
        out[cid] = float(raw)
    return out


async def fetch_coin_prices_usd(
    session: aiohttp.ClientSession,
    settings: Settings,
    *,
    max_attempts: int = 8,
) -> dict[str, float]:
    url = f"{settings.coingecko_base_url}/simple/price"
    params = {
        "ids": ",".join(settings.coin_ids),
        "vs_currencies": settings.vs_currency,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    data: dict | None = None
    for attempt in range(max_attempts):
        async with session.get(url, params=params, timeout=timeout) as resp:
            if resp.status == 429:
                wait = _retry_after_seconds(resp, attempt)
                logger.warning(
                    "CoinGecko 429 (rate limited); retry in ~%.0fs (attempt %s/%s)",
                    wait,
                    attempt + 1,
                    max_attempts,
                )
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            payload = await resp.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Unexpected JSON root: {payload!r}")
            data = payload
            break
    if data is None:
        raise CoinGeckoRateLimited(
            "CoinGecko still returning 429: increase POLL_INTERVAL_SEC and/or set COINGECKO_API_KEY (Demo) in .env"
        )
    return _parse_prices_from_payload(data, settings.coin_ids, settings.vs_currency)


async def run_monitor_loop(settings: Settings) -> None:
    _enable_windows_ansi()
    await init_db(settings.database_path)
    headers = {
        "Accept": "application/json",
        "User-Agent": "AsyncPriceMonitor/1.0",
    }
    if settings.coingecko_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_api_key
    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            try:
                prices = await fetch_coin_prices_usd(session, settings)
                for coin_id in settings.coin_ids:
                    price = prices[coin_id]
                    previous = await fetch_last_price(
                        settings.database_path, coin_id
                    )
                    await insert_snapshot(
                        settings.database_path, coin_id, price
                    )

                    if previous is not None:
                        pct = _percent_change(previous, price)
                        if pct > settings.price_alert_threshold_percent:
                            msg = (
                                f"[ALERT] {coin_id} moved {pct:.4f}% "
                                f"(prev: {previous:.6f} -> now: {price:.6f}); "
                                f"threshold {settings.price_alert_threshold_percent}%"
                            )
                            print(f"{ANSI_RED_BOLD}{msg}{ANSI_RESET}", flush=True)
                            logger.warning(msg)
                        else:
                            logger.info(
                                "tick ok %s price=%s (prev=%s, change=%.4f%%)",
                                coin_id,
                                price,
                                previous,
                                pct,
                            )
                    else:
                        logger.info(
                            "first snapshot %s price=%s (no prior row for alert)",
                            coin_id,
                            price,
                        )
            except asyncio.CancelledError:
                raise
            except CoinGeckoRateLimited as exc:
                logger.warning("%s", exc)
            except ClientResponseError as exc:
                if exc.status == 429:
                    logger.warning(
                        "poll failed: 429 Too Many Requests (no DB write this round)"
                    )
                else:
                    logger.exception("poll failed: %s", exc)
            except Exception as exc:
                logger.exception("poll failed: %s", exc)

            await asyncio.sleep(settings.poll_interval_sec)
