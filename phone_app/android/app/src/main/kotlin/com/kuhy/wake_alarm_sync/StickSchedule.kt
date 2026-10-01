package com.kuhy.wake_alarm_sync

import java.time.LocalDateTime
import java.time.LocalTime

/**
 * When [StickAlarm] fires, as pure functions of the clock, the alarm time
 * and the check already armed -- no Context, so every case is checkable in
 * isolation.
 */
object StickSchedule {

    /** A few seconds past the boundary, so "passed by >= 15 min" is never a rounding call. */
    private const val SLACK_SECONDS = 5L

    /** The next (A + grace + slack) strictly after [now]. */
    fun nextOccurrence(now: LocalDateTime, alarm: LocalTime): LocalDateTime {
        val time = alarm.plusMinutes(Stakes.STICK_GRACE_MINUTES).plusSeconds(SLACK_SECONDS)
        val candidate = now.toLocalDate().atTime(time)
        return if (candidate.isAfter(now)) candidate else candidate.plusDays(1)
    }

    /**
     * The instant to arm: the earlier of [next] and a still-future [pending].
     *
     * One PendingIntent holds one instant, so arming tomorrow's check would
     * silently drop today's. Between A and A + 15 every re-arm passes the
     * *next* alarm's time -- opening the app re-arms with tomorrow's policy,
     * and "wake me earlier" sets an earlier one -- whose check is tomorrow.
     * Keeping the pending instant is what stops "phone off, back on at A + 5,
     * open the app" from cancelling today's check. A pending instant at or
     * before [now] has fired (or was missed while off) and is dropped.
     */
    fun choose(now: LocalDateTime, next: LocalDateTime, pending: LocalDateTime?): LocalDateTime =
        if (pending != null && pending.isAfter(now) && pending.isBefore(next)) pending else next
}
