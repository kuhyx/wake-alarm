#!/bin/bash
# Install the wake-alarm trigger timer.
#
# Usage: bash install.sh
#
# The phone is the alarm. The PC starts the morning routine at the time the
# phone last synced, and -- wake enforcement v2, DOCS-wake-enforcement.md --
# rings itself only when the phone stays silent, and wakes itself (RTC)
# before a Tue/Wed/Thu alarm.
#
# What it does:
#   1. Installs wake_alarm + dependencies for /usr/bin/python
#   2. Installs the systemd user units and enables their timers (trigger,
#      session, fallback, rtc, audit)
#   3. Installs the root pieces of the fallback alarm: the ring WAVs, the
#      ALSA ring script + system unit, the sudoers lines that let the user
#      start/stop that unit, and (pc_wake.json "hibernate" mode only) the
#      logind drop-in that makes the power key hibernate
#   4. Removes the retired waking machinery from earlier installs
#
# Deliberately NOT done, and why:
#   - no shutdown wrapper and no sleep hook: the RTC alarm lives in CMOS and
#     survives however the PC goes down, so neither is needed
#   - systemd-logind is never restarted (that kills the graphical session);
#     the drop-in is applied with a HUP reload

set -euo pipefail

# Refuse to run under sudo. This script must run as the logged-in user: it
# installs *user* systemd units and calls `sudo` itself for the few root-owned
# pieces. Under sudo, XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS are stripped,
# so `systemctl --user` fails and later steps are silently skipped while the
# earlier pip output still looks like success. It also runs pip as root, which
# leaves root-owned files in ~/.cache/pip. Failing loudly beats half-finishing.
if [[ -n "${SUDO_USER:-}" || $EUID -eq 0 ]]; then
    echo "Error: do not run this script with sudo." >&2
    echo "Run it as your normal user:  bash $0" >&2
    echo "It will prompt for sudo itself where root is actually needed." >&2
    exit 1
fi

# Split declare/assign so the command-substitution exit code is not masked (SC2155).
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
readonly SCRIPT_DIR
readonly REPO_DIR="$SCRIPT_DIR"
readonly TRIGGER_SERVICE_SRC="$SCRIPT_DIR/wake-alarm-trigger.service"
readonly TRIGGER_TIMER_SRC="$SCRIPT_DIR/wake-alarm-trigger.timer"
readonly SESSION_SERVICE_SRC="$SCRIPT_DIR/wake-alarm-session.service"
readonly SESSION_TIMER_SRC="$SCRIPT_DIR/wake-alarm-session.timer"
readonly SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
# Enforcement v2 user units (service + timer each).
readonly V2_UNITS=(wake-alarm-fallback wake-alarm-rtc wake-alarm-audit)
# Root pieces of the fallback alarm.
readonly PC_DIR="$SCRIPT_DIR/scripts/pc"
readonly WAV_DIR="/usr/local/share/wake-alarm"
readonly RING_SCRIPT_DST="/usr/local/lib/wake-alarm/ring_alsa.sh"
readonly ALSA_UNIT="wake-alarm-ring-alsa.service"
readonly SUDOERS_FILE="/etc/sudoers.d/wake-alarm"
readonly POWERKEY_DST="/etc/systemd/logind.conf.d/wake-alarm-powerkey.conf"
INSTALL_USER="$(id -un)"
readonly INSTALL_USER
readonly SUDOERS_LINES=(
    "$INSTALL_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start $ALSA_UNIT"
    "$INSTALL_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop $ALSA_UNIT"
)

TEMP_DIR=""
cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

install_ring_audio() {
    # Generated, never committed: the binary hook forbids WAVs in the repo.
    /usr/bin/python3 -m wake_alarm._ring_wav --write "$TEMP_DIR/wav" >/dev/null
    sudo install -D -m 0644 "$TEMP_DIR/wav/ring.wav" "$WAV_DIR/ring.wav"
    sudo install -D -m 0644 "$TEMP_DIR/wav/ring_loop.wav" "$WAV_DIR/ring_loop.wav"
    sudo install -D -m 0755 "$PC_DIR/ring_alsa.sh" "$RING_SCRIPT_DST"
    sudo install -m 0644 "$PC_DIR/$ALSA_UNIT" "/etc/systemd/system/$ALSA_UNIT"
    sudo systemctl daemon-reload
    echo "  Ring WAVs, $RING_SCRIPT_DST and $ALSA_UNIT installed."
}

install_sudoers() {
    # Merge, never clobber: the file also holds the rtcwake entry the RTC
    # arming relies on. Validated with visudo before it replaces anything.
    local merged="$TEMP_DIR/sudoers" line
    # The file is root-only (0440); a missing one starts the merge empty.
    sudo cat "$SUDOERS_FILE" 2>/dev/null | tee "$merged" >/dev/null || : >"$merged"
    if ! grep -q '/usr/sbin/rtcwake' "$merged"; then
        echo "$INSTALL_USER ALL=(root) NOPASSWD: /usr/sbin/rtcwake" >>"$merged"
    fi
    for line in "${SUDOERS_LINES[@]}"; do
        grep -qxF "$line" "$merged" || echo "$line" >>"$merged"
    done
    sudo visudo -cf "$merged" >/dev/null
    sudo install -m 0440 -o root -g root "$merged" "$SUDOERS_FILE"
    echo "  $SUDOERS_FILE: rtcwake + start/stop $ALSA_UNIT (validated)."
}

install_powerkey_dropin() {
    local mode
    mode="$(/usr/bin/python3 -m wake_alarm._pc_wake_mode)"
    if [[ "$mode" == "hibernate" ]]; then
        if sudo cmp -s "$PC_DIR/wake-alarm-powerkey.conf" "$POWERKEY_DST"; then
            echo "  Power key already hibernates (mode: $mode)."
            return 0
        fi
        sudo install -D -m 0644 "$PC_DIR/wake-alarm-powerkey.conf" "$POWERKEY_DST"
    elif sudo test -f "$POWERKEY_DST"; then
        sudo rm -f "$POWERKEY_DST"
    else
        echo "  Power key untouched (mode: $mode)."
        return 0
    fi
    # Reload, NEVER restart: restarting logind kills the graphical session.
    sudo systemctl kill -s HUP systemd-logind
    echo "  logind drop-in updated for mode $mode and reloaded."
}

echo "=== Wake Alarm Trigger Installer ==="

echo "[1/4] Installing wake_alarm for /usr/bin/python..."
# Editable, and from this clone: a later `git pull` here then updates the
# running production code with no reinstall. A non-editable snapshot taken
# from a scratch directory silently stops tracking this repo.
/usr/bin/python3 -m pip install --user --break-system-packages -e "$REPO_DIR"
echo "  Installed. Verifying import..."
/usr/bin/python3 -c "import wake_alarm; import gatelock"
echo "  wake_alarm and gatelock import under /usr/bin/python."

echo "[2/4] Installing systemd user units..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$TRIGGER_SERVICE_SRC" "$TRIGGER_TIMER_SRC" \
   "$SESSION_SERVICE_SRC" "$SESSION_TIMER_SRC" "$SYSTEMD_USER_DIR/"
for unit in "${V2_UNITS[@]}"; do
    cp "$SCRIPT_DIR/$unit.service" "$SCRIPT_DIR/$unit.timer" "$SYSTEMD_USER_DIR/"
done
systemctl --user daemon-reload
systemctl --user enable --now wake-alarm-trigger.timer
echo "  Trigger timer enabled and started (ticks once a minute)."
systemctl --user enable --now wake-alarm-session.timer
echo "  Session timer enabled (07:00-11:00, every 2 min)."
for unit in "${V2_UNITS[@]}"; do
    systemctl --user enable --now "$unit.timer"
done
echo "  Fallback (04-09, every min), RTC (every 15 min + boot) and audit"
echo "  (11:05) timers enabled."

echo "[3/4] Installing the fallback alarm's root pieces (sudo)..."
TEMP_DIR="$(mktemp -d)"
install_ring_audio
install_sudoers
install_powerkey_dropin

echo "[4/4] Removing retired waking machinery from earlier installs..."
# Opportunistic, and deliberately NOT fatal. This script runs under `set -e`
# and the cleanup needs root, so on a machine without cached/passwordless sudo
# a hard call would abort the install *after* the package and timer are
# already in place -- reporting failure for an install that actually worked.
# `sudo -n` rather than plain sudo so it cannot hang on a password prompt in a
# non-TTY context either.
if sudo -n true 2>/dev/null; then
    bash "$SCRIPT_DIR/uninstall.sh" --retired-only ||
        echo "  Cleanup incomplete — run: bash uninstall.sh --retired-only"
else
    echo "  Needs root and sudo would prompt; skipping."
    echo "  Run it yourself:  bash uninstall.sh --retired-only"
    echo "  This matters: /usr/local/bin/shutdown otherwise keeps turning"
    echo "  'shutdown now' into a hibernate."
fi
echo

echo "=== Installation complete ==="
echo "The timer ticks once a minute and starts morning-routine.service at the"
echo "time the phone last synced."
echo "Check what it resolves right now:  python -m wake_alarm._sync --show"
echo "Check what the next tick would do:  python -m wake_alarm._trigger --dry-run"
echo "Watch it live:  journalctl --user -fu wake-alarm-trigger.service"
echo "Fallback alarm:  python -m wake_alarm._fallback --dry-run"
echo "RTC plan:        python -m wake_alarm._rtc --show"
echo "Audit a morning: python -m wake_alarm._audit --dry-run [YYYY-MM-DD]"
