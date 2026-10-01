package com.kuhy.wake_alarm_sync

import java.time.LocalDate

/**
 * The native copies of the wake-enforcement numbers (`DOCS-wake-enforcement.md`).
 *
 * The stick decides with no Flutter engine running, so it cannot read
 * `lib/services/stakes.dart`. `wake_alarm/tests/test_stakes_mirrors.py`
 * fails when these drift from the Dart and Python copies -- keep each
 * literal on one line so that test can parse it.
 */
object Stakes {
    /** A ring not dismissed this long after the alarm is a miss (`SESSION_NONE_GRACE`). */
    const val STICK_GRACE_MINUTES = 15L

    /** A lockdown never spans more calendar days than this, today included. */
    const val STICK_LOCKDOWN_MAX_DAYS = 5

    /** The escape hatch's last usable day, inclusive. */
    const val ESCAPE_HATCH_LAST_DAY = "2026-10-15"

    /** [ESCAPE_HATCH_LAST_DAY] as a date. */
    val escapeHatchLastDay: LocalDate = LocalDate.parse(ESCAPE_HATCH_LAST_DAY)
}
