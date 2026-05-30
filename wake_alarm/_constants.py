"""Constants for the weekend wake alarm system."""

from __future__ import annotations

from pathlib import Path

# Days the wake alarm is active (Python weekday(): Mon=0 ... Sun=6)
# Monday, Friday, Saturday, Sunday
ALARM_DAYS: frozenset[int] = frozenset({0, 4, 5, 6})

# How many hours after shutdown the PC should wake
WAKE_AFTER_HOURS: int = 8

# Minutes after alarm starts within which you must dismiss to earn skip
DISMISS_WINDOW_MINUTES: int = 30

# Hour at which the second (fallback) alarm fires if the first was missed
FALLBACK_ALARM_HOUR: int = 13

# Alarm escalation phase boundaries (minutes from alarm start)
PHASE_SOFT_END: int = 5
PHASE_MEDIUM_END: int = 15
# After PHASE_MEDIUM_END: continuous sine tone until dismiss window closes

# Beep intervals per phase (seconds)
SOFT_BEEP_INTERVAL: float = 10.0
MEDIUM_BEEP_INTERVAL: float = 5.0
LOUD_TOGGLE_INTERVAL: float = 2.0

# Dismiss challenge: length of the random code
DISMISS_CODE_LENGTH: int = 8
# Number of correct code entries required to dismiss the alarm.
# Requiring more than one round forces the user to stay awake long enough
# to actually read and type multiple independent codes.
DISMISS_ROUNDS_REQUIRED: int = 2
# Seconds the code is visible before being hidden in a flash challenge.
DISMISS_FLASH_SECONDS: int = 4
# How often the dismiss code refreshes (seconds)
DISMISS_CODE_REFRESH_SECONDS: int = 30

# State file for wake alarm (HMAC-signed)
WAKE_STATE_FILE: Path = Path(__file__).resolve().parent / "wake_state.json"

# rtcwake binary path
RTCWAKE_BIN: str = "/usr/sbin/rtcwake"

# Alarm audio output (machine-specific, empirically verified 2026-05-25).
# At wake time the Bluetooth speaker is disconnected and PipeWire only has the
# auto_null sink, so the alarm is silent unless we activate a real output. The
# only audible always-present output on this machine is the G27Q monitor's
# built-in speaker on the NVidia GPU's HDMI audio. WirePlumber leaves the card
# profile "off", so the alarm must force the profile on and wait for the sink.
ALARM_AUDIO_CARD: str = "alsa_card.pci-0000_01_00.1"
ALARM_AUDIO_PROFILE: str = "output:hdmi-stereo"
ALARM_AUDIO_SINK: str = "alsa_output.pci-0000_01_00.1.hdmi-stereo"
# Seconds to wait for the HDMI sink to appear after forcing the profile on.
ALARM_AUDIO_SINK_WAIT_SECONDS: float = 6.0
# Poll interval while waiting for the sink.
ALARM_AUDIO_SINK_POLL_SECONDS: float = 0.5

# TP-Link Tapo P110 smart-plug config file (JSON).
# Create with mode 0600 and these keys: host, email, password.
# Example contents: a JSON object mapping host -> "192.168.x.x", email ->
# "tapo@example.com" and password -> "your-password".
# Missing/invalid file => smart-plug control is skipped silently.
TAPO_CONFIG_FILE: Path = Path.home() / ".config" / "wake_alarm" / "tapo.json"

# Timeout (seconds) for a single Tapo plug operation. Keep short so a
# missing/unreachable plug never delays the alarm by more than this.
TAPO_TIMEOUT_SECONDS: float = 5.0
