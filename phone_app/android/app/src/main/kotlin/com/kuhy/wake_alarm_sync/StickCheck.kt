package com.kuhy.wake_alarm_sync

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/** What one stick check concluded; [wire] is the `stick_check` event's `verdict`. */
enum class StickVerdict(val wire: String, val final: Boolean = true) {
    NO_ALARM("no_alarm"),
    NOT_STICK_DAY("not_stick_day"),
    FREE_DAY("free_day"),
    ESCAPED("escaped"),
    ALREADY_PENALISED("already_penalised"),
    DISMISSED("dismissed"),
    TOO_EARLY("too_early", final = false),
    MISS("miss"),
}

/** The persisted stick: the streak and the lockdown it bought. */
data class StickState(
    val streak: Int = 0,
    val lockedThrough: LocalDate? = null,
    val lastMiss: LocalDate? = null,
)

/** Everything one run reads; gathered by [StickRunner], decided here. */
data class StickInputs(
    val now: LocalDateTime,
    /** The stored daily alarm `A`, or null when none is stored. */
    val alarm: LocalTime?,
    val dismissedOn: (LocalDate) -> Boolean,
    val escapedOn: (LocalDate) -> Boolean,
    /** The native free-day cache; fail-closed, so unreadable is `false`. */
    val isFree: (LocalDate) -> Boolean,
    val state: StickState,
    /** The last day whose verdict was final, or null before the first run. */
    val checkedThrough: LocalDate?,
)

/** One day's verdict within a run. */
data class DayVerdict(val day: LocalDate, val verdict: StickVerdict)

/**
 * A run's result: each day judged, the state to persist, how far days are
 * now settled, and the lockdown to signal (null when no miss in this run
 * locks through today or later).
 */
data class StickRun(
    val verdicts: List<DayVerdict>,
    val state: StickState,
    val checkedThrough: LocalDate,
    val signalUntil: LocalDate?,
)

/**
 * The stick's decision, as pure functions -- no Context, no clock, no I/O,
 * so every rule here is checkable in isolation.
 *
 * A **miss** is a stick day (Tue/Wed/Thu, [WorkdayStick.STICK_DAYS]) that is
 * not a free day, whose alarm passed by at least [Stakes.STICK_GRACE_MINUTES]
 * with no dismiss and no escape, and that has not already been penalised.
 * Nothing here needs the ring to have *fired*: a phone switched off before
 * the alarm misses exactly like one left ringing (hole 1 of the contract).
 */
object StickCheck {

    /** How many past days a run catches up on (a phone off for days). */
    const val BACKLOG_DAYS = 5L

    /** How far back [previousStickDay] looks before giving up. */
    private const val LOOKBACK_DAYS = 60L

    /**
     * Judges every unchecked day, oldest first, then today.
     *
     * Past days run from the day after [StickInputs.checkedThrough], at most
     * [BACKLOG_DAYS] back -- in order, so the streak builds exactly as if
     * each day had been checked on time. A first run (no checkedThrough)
     * judges today only: days from before this stick existed have no
     * dismiss records and must not be punished.
     */
    fun run(inputs: StickInputs): StickRun {
        val today = inputs.now.toLocalDate()
        val verdicts = mutableListOf<DayVerdict>()
        var state = inputs.state
        var signal: LocalDate? = null
        val checked = inputs.checkedThrough
        var day = if (checked == null) {
            today
        } else {
            maxOf(checked.plusDays(1), today.minusDays(BACKLOG_DAYS))
        }
        if (day.isAfter(today)) day = today
        while (!day.isAfter(today)) {
            val at = if (day == today) inputs.now else day.atTime(LocalTime.MAX)
            val (verdict, next) = decideDay(day, at, inputs, state)
            verdicts += DayVerdict(day, verdict)
            if (verdict == StickVerdict.MISS) {
                signal = next.lockedThrough?.takeIf { !it.isBefore(today) }
            }
            state = next
            day = day.plusDays(1)
        }
        val settled = if (verdicts.last().verdict.final) today else today.minusDays(1)
        return StickRun(verdicts, state, maxOf(settled, checked ?: settled), signal)
    }

    /** One day's verdict and the state after it; [now] is when it is judged. */
    fun decideDay(
        day: LocalDate,
        now: LocalDateTime,
        inputs: StickInputs,
        state: StickState,
    ): Pair<StickVerdict, StickState> {
        val alarm = inputs.alarm ?: return StickVerdict.NO_ALARM to state
        if (!isStickDay(day)) return StickVerdict.NOT_STICK_DAY to state
        if (inputs.isFree(day)) return StickVerdict.FREE_DAY to state
        // A dismissed or escaped stick day breaks the chain: the streak
        // shown and synced drops to 0 (a lockdown already sent stays).
        if (inputs.escapedOn(day)) return StickVerdict.ESCAPED to state.copy(streak = 0)
        if (state.lastMiss == day) return StickVerdict.ALREADY_PENALISED to state
        if (inputs.dismissedOn(day)) return StickVerdict.DISMISSED to state.copy(streak = 0)
        val due = day.atTime(alarm).plusMinutes(Stakes.STICK_GRACE_MINUTES)
        if (now.isBefore(due)) return StickVerdict.TOO_EARLY to state
        return StickVerdict.MISS to afterMiss(day, state, inputs.isFree)
    }

    /**
     * The state a miss on [day] would produce. Also what the UI shows as
     * "locked through" before the miss happens, so the screen and the
     * enforcement can never disagree about the date. Never shortens a
     * lockdown already in force: a chain restarting at 1 must not report
     * an earlier end than the one focus-owner was already sent.
     */
    fun afterMiss(day: LocalDate, state: StickState, isFree: (LocalDate) -> Boolean): StickState {
        val streak = streakAfterMiss(day, state, isFree)
        val computed = lockedThrough(day, streak)
        val locked = state.lockedThrough?.let { maxOf(it, computed) } ?: computed
        return StickState(streak = streak, lockedThrough = locked, lastMiss = day)
    }

    /**
     * Consecutive stick-day misses including one on [day]: the chain
     * continues only when the previous stick day (free days skipped) is
     * exactly the last miss.
     */
    fun streakAfterMiss(day: LocalDate, state: StickState, isFree: (LocalDate) -> Boolean): Int {
        val previous = previousStickDay(day, isFree)
        return if (previous != null && previous == state.lastMiss) state.streak + 1 else 1
    }

    /** `day + min(streak, max - 1)`: 1 → the next day, 4+ → five calendar days. */
    fun lockedThrough(day: LocalDate, streak: Int): LocalDate =
        day.plusDays(minOf(streak, Stakes.STICK_LOCKDOWN_MAX_DAYS - 1).toLong())

    /** The nearest earlier stick day that is not a free day, or null. */
    fun previousStickDay(day: LocalDate, isFree: (LocalDate) -> Boolean): LocalDate? {
        var step = day.minusDays(1)
        val floor = day.minusDays(LOOKBACK_DAYS)
        while (step.isAfter(floor)) {
            if (isStickDay(step) && !isFree(step)) return step
            step = step.minusDays(1)
        }
        return null
    }

    fun isStickDay(day: LocalDate): Boolean = day.dayOfWeek in WorkdayStick.STICK_DAYS
}
