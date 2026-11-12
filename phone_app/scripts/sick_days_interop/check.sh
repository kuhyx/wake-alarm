#!/bin/bash

# ============================================================================
# Cross-language check for the sick-day pool (sickdays 0.2.0, with keep).
#
# phone_app/lib/services/sick_day_pool.dart writes the wire format that
# ~/src/utils/sickdays (Python) owns. Both directions, Python as the oracle:
#   1. Dart writes a pool; Python reads it and replays the same edits.
#   2. Python writes a pool (incl. a 0.1.0 record with no keep, a stale keep
#      and a malformed one); Dart reads it; Python compares the verdicts.
# Fails on any disagreement about which days are sick or which lockers
# stand down.
#
# Requires a Python with sickdays 0.2.0 importable: SICKDAYS_PYTHON, else
# the venv sickdays/install.sh creates. Python runs with HOME pointed at a
# scratch directory, so no default path can ever reach the real pool.
#
# Usage: phone_app/scripts/sick_days_interop/check.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly SCRIPT_DIR APP_DIR
# shellcheck source=../../../scripts/pinned_flutter.sh
source "$APP_DIR/../scripts/pinned_flutter.sh"
readonly SICKDAYS_PYTHON="${SICKDAYS_PYTHON:-$HOME/.local/share/sickdays/venv/bin/python}"

TEMP_DIR=""
cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

validate_requirements() {
    use_pinned_flutter "$APP_DIR/.."
    if [[ ! -x "$SICKDAYS_PYTHON" ]]; then
        echo "Error: no sickdays python at $SICKDAYS_PYTHON (set SICKDAYS_PYTHON)" >&2
        exit 1
    fi
    command -v flutter >/dev/null || { echo "Error: flutter not on PATH" >&2; exit 1; }
}

# The oracle, isolated from the real pool under ~/.local/share/sickdays.
oracle() {
    HOME="$TEMP_DIR/home" "$SICKDAYS_PYTHON" -I "$SCRIPT_DIR/verify.py" "$@"
}

# Runs one Dart interop test with the given VAR=value environment.
dart_test() {
    local test_file="$1"
    shift
    (cd "$APP_DIR" && env "$@" flutter test "$test_file" | tail -1)
}

main() {
    validate_requirements
    TEMP_DIR="$(mktemp -d)"
    mkdir -p "$TEMP_DIR/home"
    local dart_pool="$TEMP_DIR/dart_sick_days.json"
    local python_pool="$TEMP_DIR/python_sick_days.json"
    local dart_reading="$TEMP_DIR/dart_reading.json"

    echo "== sick-day interop: Dart writes, Python reads =="
    dart_test test/sick_day_interop_writer_test.dart \
        "SICK_DAYS_INTEROP_OUT=$dart_pool"
    [[ -s "$dart_pool" ]] || { echo "Error: Dart wrote no fixture" >&2; exit 1; }
    oracle dart "$dart_pool"

    echo "== sick-day interop: Python writes, Dart reads =="
    oracle write "$python_pool"
    dart_test test/sick_day_interop_reader_test.dart \
        "SICK_DAYS_INTEROP_IN=$python_pool" "SICK_DAYS_INTEROP_READING=$dart_reading"
    [[ -s "$dart_reading" ]] || { echo "Error: Dart wrote no reading" >&2; exit 1; }
    oracle read "$python_pool" "$dart_reading"
}

main "$@"
