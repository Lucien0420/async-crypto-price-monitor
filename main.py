from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from app.core.config import load_settings
from app.services.monitor import run_monitor_loop


def _setup_logging(project_root: Path) -> None:
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )


async def _run_with_shutdown_signals(settings) -> None:
    """Register SIGTERM/SIGINT on Linux and in containers so `docker stop` cancels the monitor loop."""
    log = logging.getLogger(__name__)
    task = asyncio.create_task(run_monitor_loop(settings))
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        task.cancel()

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _request_stop)
            except (NotImplementedError, RuntimeError):
                pass
    try:
        await task
    except asyncio.CancelledError:
        log.info("shutdown requested")


def main() -> None:
    _setup_logging(_ROOT)
    settings = load_settings()
    try:
        asyncio.run(_run_with_shutdown_signals(settings))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("stopped by user (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
