"""TP-Link Tapo P110 smart-plug control for the wake alarm.

Config file ``~/.config/wake_alarm/tapo.json`` (mode 0600) must contain::

    {
        "host": "192.168.x.x",
        "email": "tapo-account@example.com",
        "password": "tapo-account-password",
    }

If the file is missing, malformed, the ``kasa`` package is unavailable, or
the plug cannot be reached within :data:`TAPO_TIMEOUT_SECONDS`, the
operation is skipped with a WARNING log entry — the alarm must never
block on the plug.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING

from python_pkg.wake_alarm._constants import (
    TAPO_CONFIG_FILE,
    TAPO_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from kasa import Device

_logger = logging.getLogger(__name__)

# ``kasa`` is an optional runtime dependency. Import at module load time so
# we fail fast if it is missing rather than re-importing on every call.
try:
    from kasa import Credentials, Discover
    from kasa.exceptions import KasaException

    _KASA_AVAILABLE = True
except ImportError:
    _KASA_AVAILABLE = False
    _logger.warning(
        "python-kasa is not installed; Tapo smart-plug control disabled",
    )


def _load_config() -> dict[str, str] | None:
    """Return validated Tapo config from :data:`TAPO_CONFIG_FILE`, or ``None``.

    Returns:
        ``None`` if the file is missing, unreadable, malformed, or missing
        any of the required keys. Otherwise a dict with ``host``, ``email``,
        ``password``.
    """
    try:
        with TAPO_CONFIG_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        _logger.warning(
            "Tapo config %s does not exist; smart-plug control disabled",
            TAPO_CONFIG_FILE,
        )
        return None
    except (OSError, json.JSONDecodeError):
        _logger.warning(
            "Tapo config %s is unreadable or malformed; skipping plug control",
            TAPO_CONFIG_FILE,
            exc_info=True,
        )
        return None
    if not isinstance(data, dict):
        _logger.warning(
            "Tapo config %s is not a JSON object; skipping plug control",
            TAPO_CONFIG_FILE,
        )
        return None
    required = ("host", "email", "password")
    if not all(isinstance(data.get(k), str) and data[k] for k in required):
        _logger.warning(
            "Tapo config %s missing required keys %s; skipping plug control",
            TAPO_CONFIG_FILE,
            required,
        )
        return None
    return {k: data[k] for k in required}


async def _connect(config: dict[str, str]) -> Device | None:
    """Open a connection to the configured plug, or ``None`` on failure."""
    try:
        dev = await Discover.discover_single(
            config["host"],
            credentials=Credentials(config["email"], config["password"]),
        )
    except (KasaException, OSError, asyncio.TimeoutError):
        _logger.warning("Tapo plug discovery failed", exc_info=True)
        return None
    try:
        await dev.update()
    except (KasaException, OSError, asyncio.TimeoutError):
        _logger.warning("Tapo plug update failed", exc_info=True)
        with contextlib.suppress(KasaException, OSError):
            await dev.disconnect()
        return None
    return dev


async def _set_state(*, on: bool) -> None:
    """Connect to the plug and set its on/off state."""
    config = _load_config()
    if config is None:
        return
    dev = await _connect(config)
    if dev is None:
        return
    try:
        if on:
            await dev.turn_on()
        else:
            await dev.turn_off()
    except (KasaException, OSError, asyncio.TimeoutError):
        _logger.warning("Tapo plug toggle failed", exc_info=True)
    finally:
        with contextlib.suppress(KasaException, OSError):
            await dev.disconnect()


def _run(*, on: bool) -> None:
    """Run :func:`_set_state` with a hard timeout. Never raises."""
    if not _KASA_AVAILABLE:
        _logger.warning(
            "python-kasa unavailable; skipping Tapo plug %s",
            "ON" if on else "OFF",
        )
        return

    async def _runner() -> None:
        await asyncio.wait_for(_set_state(on=on), timeout=TAPO_TIMEOUT_SECONDS)

    try:
        asyncio.run(_runner())
    except (asyncio.TimeoutError, OSError, RuntimeError):
        _logger.warning("Tapo plug control timed out or failed", exc_info=True)


def turn_on_plug() -> None:
    """Turn the configured Tapo plug on. Logs a WARNING if not configured."""
    _run(on=True)


def turn_off_plug() -> None:
    """Turn the configured Tapo plug off. Logs a WARNING if not configured."""
    _run(on=False)
