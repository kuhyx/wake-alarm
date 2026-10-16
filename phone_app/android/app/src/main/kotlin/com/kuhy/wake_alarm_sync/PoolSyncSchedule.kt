package com.kuhy.wake_alarm_sync

import java.time.LocalDateTime
import java.time.LocalTime

/**
 * When [PoolSyncAlarm] fires, as a pure function of the clock and the
 * stored alarm -- no Context, so every case is checkable in isolation.
 *
 * Two slots a day, so a free or sick day marked on the PC reaches the
 * native caches before the morning ring without the app being opened:
 * - [EVENING] (21:00): the phone is usually awake and online, which makes
 *   it the dependable slot for anything marked during the day.
 * - A - [LEAD_MINUTES]: catches a mark made late at night. The phone is
 *   usually in Doze by then; an allow-while-idle alarm gets a short network
 *   window, enough for two small RTDB reads, but not a guarantee.
 */
object PoolSyncSchedule {

    /** The evening slot. */
    val EVENING: LocalTime = LocalTime.of(21, 0)

    /** How long before the alarm the morning slot runs. */
    const val LEAD_MINUTES = 30L

    /** The earliest slot strictly after [now]; only [EVENING] when no alarm is stored. */
    fun next(now: LocalDateTime, alarm: LocalTime?): LocalDateTime {
        val times = listOfNotNull(EVENING, alarm?.minusMinutes(LEAD_MINUTES))
        val today = now.toLocalDate()
        return listOf(today, today.plusDays(1))
            .flatMap { day -> times.map { day.atTime(it) } }
            .filter { it.isAfter(now) }
            .min()
    }
}
