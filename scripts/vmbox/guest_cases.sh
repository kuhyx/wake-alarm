#!/bin/bash

# ============================================================================
# wake_alarm vmbox harness — the cases that run INSIDE the guest.
#
# Kept as its own file rather than inlined into `vm run` for two reasons: the
# vmbox runner wraps its argument in `sh -c` and chokes on a multi-line
# command, and a real file gets shellcheck like every other script here.
#
# Each case prints "PASS <name>" or "FAIL <name>: <why>" and the script exits
# non-zero if any failed, so the host adjudicates on an exit code rather than
# by reading prose.
# ============================================================================

set -uo pipefail

readonly PY=/usr/bin/python3
# The helper .py files ship beside this script, so each gets real linting
# and type checking instead of hiding inside a heredoc.
CASE_DIR="$(dirname "$(readlink -f "$0")")"
readonly CASE_DIR
FAILURES=0

pass() {
    echo "PASS $1"
}

fail() {
    echo "FAIL $1: $2"
    FAILURES=$((FAILURES + 1))
}

# --- Case: the package installs and imports from SYSTEM python ---------------
# The units run /usr/bin/python directly, never a venv, so this is the check
# that actually matters (CLAUDE.md).
case_imports() {
    local name="imports-from-system-python"
    if "$PY" -c "import wake_alarm, gatelock" 2>/dev/null; then
        pass "$name"
    else
        fail "$name" "wake_alarm or gatelock missing from /usr/bin/python3"
    fi
}

# --- Case: units land in the right enablement state --------------------------
# wake-alarm.service must stay `static`. An [Install] section there fires the
# alarm at *login* time, because _should_run_alarm() has no time gate.
case_units() {
    local name state
    name="trigger-timer-enabled"
    state="$(systemctl --user is-enabled wake-alarm-trigger.timer 2>&1)"
    if [[ "$state" == "enabled" ]]; then
        pass "$name"
    else
        fail "$name" "expected enabled, got '$state'"
    fi

    name="alarm-service-never-auto-starts"
    state="$(systemctl --user is-enabled wake-alarm.service 2>&1)"
    if [[ "$state" == "static" || "$state" == "disabled" ]]; then
        pass "$name"
    else
        fail "$name" "wake-alarm.service is '$state'; it must never auto-start"
    fi
}

# --- Case: the shutdown wrapper shadows /usr/bin/shutdown --------------------
case_shutdown_wrapper() {
    local name="shutdown-wrapper-shadows-real-shutdown"
    local resolved
    resolved="$(command -v shutdown)"
    if [[ "$resolved" == "/usr/local/bin/shutdown" ]]; then
        pass "$name"
    else
        fail "$name" "shutdown resolves to '$resolved', not the wrapper"
    fi
}

# --- Case: the wrapper reads the alarm cache, not the network ----------------
# It parses ~/.config/wake_alarm/alarm_cache.json with jq. The shape is the
# only coupling left between the wrapper and _sync.py's _write_cache().
case_wrapper_reads_cache() {
    local name="wrapper-parses-the-alarm-cache"
    local cache="$HOME/.config/wake_alarm/alarm_cache.json"
    mkdir -p "$(dirname "$cache")"
    printf '{"hour": 6, "minute": 45, "fetched_at": %d}\n' "$(date +%s)" > "$cache"
    if jq -e '.hour == 6 and .minute == 45' "$cache" >/dev/null 2>&1; then
        pass "$name"
    else
        fail "$name" "jq could not read the cache shape the wrapper expects"
    fi
    rm -f "$cache"
}

# --- Case: the trigger decides without crashing ------------------------------
case_trigger_dry_run() {
    local name="trigger-dry-run"
    if "$PY" -m wake_alarm._trigger --dry-run 2>/dev/null | grep -q "firing"; then
        pass "$name"
    else
        fail "$name" "--dry-run produced no decision line"
    fi
}

# --- Case: the inhibitor reports honestly ------------------------------------
# The guest's polkit denies an inhibit from a non-interactive ssh session
# ("Failed to inhibit: Access denied", exit 1), so what is asserted here is
# NOT that the power key gets blocked -- it is that the code never *claims*
# a block it did not get. That distinction is the bug this case found: Popen
# succeeded, the alarm logged "power key inhibited", and nothing was.
#
# The two accepted outcomes are therefore "took it and released it" and
# "logind refused and we said so". A silent third state is the failure.
# See DOCS-vmbox.md for why the block itself cannot be proven in a guest.
case_inhibitor() {
    local name="inhibitor-never-claims-a-block-it-lacks"
    "$PY" "$CASE_DIR/check_inhibitor.py" > /tmp/inhibit_result 2>/dev/null
    local result
    result="$(cat /tmp/inhibit_result 2>/dev/null)"
    case "$result" in
        "HELD FREED"|"REFUSED")
            pass "$name ($result)"
            ;;
        *)
            fail "$name" "expected 'HELD FREED' or 'REFUSED', got '$result'"
            ;;
    esac
}

# --- Case: an unfinished session re-fires --------------------------------
# The one case a VM tests better than the host: a real poweroff mid-alarm.
# Here we assert the decision the next boot's trigger tick would make.
case_refire() {
    local name="cut-short-alarm-refires"
    "$PY" "$CASE_DIR/check_refire.py" > /tmp/refire_result 2>/dev/null
    local result
    result="$(cat /tmp/refire_result 2>/dev/null)"
    if [[ "$result" == "False-True-False" ]]; then
        pass "$name"
    else
        fail "$name" "expected False-True-False, got '$result'"
    fi
    rm -f "$HOME/.config/wake_alarm/alarm_session.json"
}

# --- Case: the alarm window really opens on a real X server ------------------
# Verified by the HOST via `vm screenshot`; this half only launches it.
case_alarm_window() {
    local name="alarm-window-opens"
    "$PY" -m wake_alarm._alarm --demo --trigger-now >/tmp/alarm.log 2>&1 &
    local pid=$!
    sleep 12
    if kill -0 "$pid" 2>/dev/null; then
        pass "$name"
        echo "$pid" > /tmp/alarm.pid
    else
        fail "$name" "the alarm exited early: $(tail -3 /tmp/alarm.log)"
    fi
}

main() {
    case "${1:-all}" in
        window)
            # Run alone: it leaves a fullscreen window up for the host to
            # screenshot, which would hide every later case's output.
            case_alarm_window
            ;;
        all)
            case_imports
            case_units
            case_shutdown_wrapper
            case_wrapper_reads_cache
            case_trigger_dry_run
            case_inhibitor
            case_refire
            ;;
        *)
            echo "usage: $0 [all|window]" >&2
            exit 2
            ;;
    esac

    echo "---"
    if [[ $FAILURES -gt 0 ]]; then
        echo "$FAILURES case(s) failed"
        exit 1
    fi
    # The host greps for this exact string. `vm run` reports the VM's verdict
    # rather than this script's exit code, so an exit status alone would let
    # the gate fail open.
    echo "ALL-CASES-PASSED"
}

main "$@"
