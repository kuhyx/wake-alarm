package com.kuhy.wake_alarm_sync

import java.time.LocalDate
import java.time.ZonedDateTime
import java.time.temporal.ChronoUnit

/**
 * The baseline wake time, lowered one minute per calendar day to 07:00.
 *
 * Native copy of `lib/services/alarm_ramp.dart`: the daily re-arm after a
 * dismiss, a free day, a boot or the watchdog runs here with no Dart at all,
 * so without this copy it would re-arm the stored time and the ramp would
 * stall until the app was next opened. `wake_alarm/tests/test_ramp.py` parses
 * these constants and fails when they drift from the Dart and Python copies.
 */
object AlarmRamp {

    /** The last day at the old 08:00 baseline; each day after is a minute earlier. */
    val ANCHOR: LocalDate = LocalDate.of(2026, 9, 25)

    /** Minutes of day on the anchor date (08:00). */
    const val START_MINUTES = 8 * 60

    /** The floor the ramp stops at, for good (07:00). */
    const val FLOOR_MINUTES = 7 * 60

    /** Baseline on [day], in minutes of day. Calendar days, so DST cannot skew it. */
    fun minutesOn(day: LocalDate): Int {
        val elapsed = maxOf(0L, ChronoUnit.DAYS.between(ANCHOR, day))
        return maxOf(FLOOR_MINUTES.toLong(), START_MINUTES - elapsed).toInt()
    }

    /**
     * Next fire instant after [now] for a requested time of [requested] minutes.
     *
     * The ramp is evaluated for the day the alarm fires on, and wins whenever
     * it is earlier than the request; tomorrow always qualifies because the
     * ramp never moves later.
     */
    fun nextFire(requested: Int, now: ZonedDateTime): ZonedDateTime {
        val today = now.toLocalDate()
        val first = at(today, requested, now)
        return if (first.isAfter(now)) first else at(today.plusDays(1), requested, now)
    }

    private fun at(day: LocalDate, requested: Int, now: ZonedDateTime): ZonedDateTime {
        val minutes = minOf(requested, minutesOn(day))
        return day.atTime(minutes / 60, minutes % 60).atZone(now.zone)
    }
}
