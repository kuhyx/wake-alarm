package com.kuhy.wake_alarm_sync

import java.time.LocalDate

/**
 * The one rule both native day caches ([FreeDays], [SickDays]) answer by,
 * as a pure function so it is checkable without a device.
 *
 * Fail closed: a read that throws or finds nothing means "not in the set",
 * so a corrupt or missing cache restores the normal rules (the alarm rings,
 * the stick applies) rather than standing everything down. That matches
 * `freedays.is_free_day()` and `sickdays.is_sick_day()` on the PC.
 */
object DayCache {

    /** Whether [day] (as `yyyy-MM-dd`) is in the set [read] returns. */
    fun contains(
        day: LocalDate,
        onError: (RuntimeException) -> Unit = {},
        read: () -> Set<String>?,
    ): Boolean = try {
        read()?.contains(day.toString()) ?: false
    } catch (e: RuntimeException) {
        onError(e)
        false
    }
}
