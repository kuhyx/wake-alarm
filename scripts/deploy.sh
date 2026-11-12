#!/bin/bash
# ============================================================================
# deploy.sh -- deploy wake-alarm everywhere it runs: the PC half (an editable
# install of ~/src/wake-alarm under the system python, driven by the user
# timers) and the phone app on the Pixel (release build via phone_deploy.sh).
#
# CLAUDE.md's deploy line pulls ~/src/wake-alarm first and then runs THIS copy
# from there, so the freshly pulled script is what executes.
#
# Deliberately does NOT run install.sh: it needs interactive sudo (ring unit,
# sudoers, logind drop-in). A unit or root-file change still means a manual
# `bash install.sh`; this script fails if the timers it relies on are not
# enabled and active, so a missing install is a red deploy, not a silent one.
#
# Idempotent: pip is skipped while the live import already resolves to the
# live checkout; the phone is skipped when the installed base.apk already
# equals the APK built from the live checkout.
#
# Usage: scripts/deploy.sh [--desktop-only | --build-only | --check]
#   --desktop-only  PC half only, no phone step
#   --build-only    PC half, then build the release APK without installing it
#                   (board sessions, which phone_deploy refuses to install from)
#   --check         health checks only: no pull, no install, no build
# Exit: 0 every health check passed, 1 a step failed (named on stderr), or
#       phone_deploy.sh's own exit code is reported in the failure message.
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_DIR
readonly LIVE_REPO="${WAKE_ALARM_LIVE_REPO:-$HOME/src/wake-alarm}"
# The trigger service runs /usr/bin/python, never a venv (CLAUDE.md).
readonly SYSTEM_PYTHON="${DEPLOY_PYTHON:-/usr/bin/python3}"
readonly PHONE_DEPLOY="${PHONE_DEPLOY:-$HOME/.claude/scripts/phone_deploy.sh}"
readonly SERIAL="${ADB_SERIAL:-23181JEGR08034}"
readonly PACKAGE="com.kuhy.wake_alarm_sync"
readonly TIMERS=("wake-alarm-trigger.timer" "wake-alarm-session.timer")
readonly APK_REL="phone_app/build/app/outputs/flutter-apk/app-release.apk"

log() { printf 'deploy: %s\n' "$1" >&2; }
fail() { printf 'deploy: FAILED [%s] -- %s\n' "$1" "$2" >&2; exit 1; }

# Run from / so a checkout in the cwd can never shadow the live install.
live_python() { (cd / && "$SYSTEM_PYTHON" "$@"); }

update_checkout() {
    log "pulling $LIVE_REPO"
    git -C "$LIVE_REPO" pull --ff-only --quiet || fail pull "git pull --ff-only in $LIVE_REPO"
}

install_package() {
    local file
    file=$(live_python -c 'import wake_alarm; print(wake_alarm.__file__)' 2>/dev/null || true)
    if [[ $file == "$LIVE_REPO/wake_alarm/"* ]] \
        && live_python -c 'import gatelock, crdt_sync, sickdays, freedays' 2>/dev/null; then
        log "editable install already points at $LIVE_REPO"
        return
    fi
    log "installing $LIVE_REPO into the system python (editable)"
    live_python -m pip install --quiet --user --break-system-packages -e "$LIVE_REPO" \
        || fail pip "pip install -e $LIVE_REPO"
}

check_desktop() {
    local file out timer
    live_python -c 'import wake_alarm, gatelock, crdt_sync, sickdays, freedays' \
        || fail imports "a runtime dependency is missing from $SYSTEM_PYTHON"
    file=$(live_python -c 'import wake_alarm; print(wake_alarm.__file__)')
    [[ $file == "$LIVE_REPO/wake_alarm/"* ]] || fail imports "wake_alarm resolves to $file"
    for timer in "${TIMERS[@]}"; do
        systemctl --user is-enabled --quiet "$timer" || fail timers "$timer not enabled (run install.sh)"
        systemctl --user is-active --quiet "$timer" || fail timers "$timer not active (run install.sh)"
    done
    out=$(live_python -m wake_alarm._trigger --dry-run 2>&1) || fail trigger "_trigger --dry-run: $out"
    log "desktop OK: $out"
}

build_apk() {
    local app="$1/phone_app"
    log "phone: release build of $app"
    (cd "$app" && flutter build apk --release) || fail phone-build "flutter build apk --release"
    [[ -s "$1/$APK_REL" ]] || fail phone-build "no APK at $1/$APK_REL"
}

# sha256 of the installed base.apk; empty when the phone or app is absent.
installed_apk_sha() {
    local path
    path=$(adb -s "$SERIAL" shell pm path "$PACKAGE" 2>/dev/null | tr -d '\r' | sed -n 's/^package://p' | head -1 || true)
    [[ -n $path ]] || return 0
    adb -s "$SERIAL" shell sha256sum "$path" 2>/dev/null | awk '{print $1}' || true
}

deploy_phone() {
    local want have
    build_apk "$LIVE_REPO"
    want=$(sha256sum "$LIVE_REPO/$APK_REL" | awk '{print $1}')
    have=$(installed_apk_sha)
    if [[ $have == "$want" ]]; then
        log "phone already runs this APK ($PACKAGE)"
        return
    fi
    log "phone: installing $PACKAGE"
    # phone_deploy never uninstalls or clears data; its exit code names the
    # failure (30 unreachable, 32 signature change, 35 install, ...).
    "$PHONE_DEPLOY" "$LIVE_REPO/phone_app" --release || fail phone "phone_deploy.sh exited $?"
    # phone_deploy rebuilt the APK in place: compare against what it installed.
    want=$(sha256sum "$LIVE_REPO/$APK_REL" | awk '{print $1}')
    have=$(installed_apk_sha)
    [[ $have == "$want" ]] || fail phone "installed APK ${have:-absent} != built $want"
    log "phone OK: $PACKAGE matches the built APK"
}

main() {
    local mode="${1:-all}"
    case "$mode" in
        all | --desktop-only | --build-only) ;;
        --check)
            check_desktop
            log "done (check only)"
            return
            ;;
        *) fail usage "unknown option $mode (use --desktop-only, --build-only or --check)" ;;
    esac
    update_checkout
    install_package
    check_desktop
    case "$mode" in
        --desktop-only) ;;
        --build-only) build_apk "$REPO_DIR" ;;
        *) deploy_phone ;;
    esac
    log "done"
}

main "$@"
