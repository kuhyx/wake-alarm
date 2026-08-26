"""Build the gatelock configuration and claim the screen-lock arbiter.

Split out of ``_alarm.py`` for the 250-line cap.

Production hard-locks; demo stays grab-free so a manual test cannot trap the
developer. Demo still takes ``overrideredirect``, because per-output placement
is impossible without it -- a window manager rewrites a managed window's
geometry.
"""

from __future__ import annotations

from gatelock import RANK_WAKE_ALARM, Arbiter, LockConfig

APP_NAME = "wake_alarm"


def build_config(*, demo_mode: bool) -> LockConfig:
    """Build the lock configuration for this run.

    Args:
        demo_mode: True for the closeable manual-test window.

    Returns:
        The configuration to hand to :class:`LockWindow`.
    """
    return LockConfig(
        mode="soft" if demo_mode else "hard",
        overrideredirect=True,
        app_name=APP_NAME,
        rank=RANK_WAKE_ALARM,
    )


def claim_arbiter(config: LockConfig) -> Arbiter:
    """Publish and acquire the arbiter for *config*.

    The caller must hand the result to :class:`LockWindow`, which takes
    ownership and releases it on close.

    Args:
        config: The lock configuration being used.

    Returns:
        The acquired arbiter.
    """
    arbiter = Arbiter(
        APP_NAME,
        RANK_WAKE_ALARM,
        grab=config.resolved_grab(),
        disable_vt=config.resolved_disable_vt(),
    )
    arbiter.publish()
    arbiter.acquire_holder()
    return arbiter
