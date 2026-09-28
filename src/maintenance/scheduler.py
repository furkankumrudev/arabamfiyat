"""Run the maintenance pipeline on a daily schedule inside a long-lived process.

This is intentionally a plain loop rather than a scheduling framework: the
project runs exactly one recurring job, and a dependency-free loop is easier to
reason about, to test, and to replace with system cron if the deployment moves.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from datetime import UTC, datetime, timedelta

from src.maintenance.pipeline import run_pipeline

logger = logging.getLogger(__name__)

DEFAULT_HOUR = 3
DEFAULT_MINUTE = 0


def seconds_until_next_run(now: datetime, hour: int, minute: int) -> float:
    """Seconds from ``now`` until the next occurrence of ``hour:minute``.

    A run scheduled for exactly ``now`` is pushed to the following day so a
    restart during the scheduled minute cannot trigger the job twice.
    """
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Gecersiz zamanlama saati.")

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s degeri sayiya cevrilemedi (%r); %s kullaniliyor.", name, raw, default)
        return default


def _bool_from_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def run_forever(stop: threading.Event | None = None) -> None:
    """Sleep until the scheduled time, run the pipeline, repeat."""
    stop = stop or threading.Event()
    hour = _int_from_env("PIPELINE_HOUR", DEFAULT_HOUR)
    minute = _int_from_env("PIPELINE_MINUTE", DEFAULT_MINUTE)

    if _bool_from_env("PIPELINE_RUN_ON_START"):
        logger.info("Baslangic calistirmasi yapiliyor.")
        _run_once()

    while not stop.is_set():
        delay = seconds_until_next_run(datetime.now(UTC), hour, minute)
        logger.info("Sonraki hat calistirmasi %.0f saniye sonra (%02d:%02d UTC).", delay, hour, minute)
        if stop.wait(delay):
            break
        _run_once()

    logger.info("Zamanlayici durduruldu.")


def _run_once() -> None:
    results = run_pipeline()
    failed = [result.step for result in results if not result.succeeded]
    if failed:
        logger.error("Hat adimlari basarisiz: %s", ", ".join(failed))
    else:
        logger.info("Hat basariyla tamamlandi.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()

    def handle_signal(signum: int, _frame: object) -> None:
        logger.info("Sinyal alindi (%s); kapaniyor.", signum)
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    run_forever(stop)


if __name__ == "__main__":
    main()
