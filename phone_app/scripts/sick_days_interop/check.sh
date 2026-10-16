#!/bin/bash

# ============================================================================
# Cross-language check for the sick-day pool.
#
# phone_app/lib/services/sick_day_pool.dart writes the wire format that
# ~/src/utils/sickdays (Python) owns. This writes a pool through the Dart
# rules and reads it back through the Python ones, and fails on any
# disagreement about which days are sick.
#
# Requires a Python with sickdays importable: SICKDAYS_PYTHON, else the venv
# sickdays/install.sh creates.
#
# Usage: phone_app/scripts/sick_days_interop/check.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly SCRIPT_DIR APP_DIR
readonly SICKDAYS_PYTHON="${SICKDAYS_PYTHON:-$HOME/.local/share/sickdays/venv/bin/python}"

TEMP_DIR=""
cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

validate_requirements() {
    if [[ ! -x "$SICKDAYS_PYTHON" ]]; then
        echo "Error: no sickdays python at $SICKDAYS_PYTHON (set SICKDAYS_PYTHON)" >&2
        exit 1
    fi
    command -v flutter >/dev/null || { echo "Error: flutter not on PATH" >&2; exit 1; }
}

main() {
    validate_requirements
    TEMP_DIR="$(mktemp -d)"
    local pool="$TEMP_DIR/sick_days.json"

    echo "== sick-day interop: Dart writes =="
    (
        cd "$APP_DIR"
        SICK_DAYS_INTEROP_OUT="$pool" flutter test test/sick_day_interop_writer_test.dart \
            | tail -1
    )
    [[ -s "$pool" ]] || { echo "Error: Dart wrote no fixture" >&2; exit 1; }

    echo "== sick-day interop: Python reads =="
    "$SICKDAYS_PYTHON" -I "$SCRIPT_DIR/verify.py" "$pool"
}

main "$@"
