package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/**
 * A day already penalised re-sends the lockdown it bought (2026-11-22, C6):
 * the one signal went out while focus-owner was neither Device Owner nor
 * running, and every later bypass that day got `already_penalised` and sent
 * nothing, so the lockdown never landed.
 */
class StickResendTest {
    // 2026-11-22 is a Sunday, 24 a Tuesday.
    private val sun = LocalDate.of(2026, 11, 22)
    private val mon = sun.plusDays(1)
    private val tue = sun.plusDays(2)

    private fun inputs(
        now: LocalDateTime,
        state: StickState,
        escaped: Set<LocalDate> = emptySet(),
    ) = StickInputs(
        now = now,
        alarm = LocalTime.of(7, 30),
        dismissedOn = { false },
        escapedOn = { it in escaped },
        isFree = { false },
        isSick = { false },
        state = state,
        checkedThrough = now.toLocalDate(),
        bypassOn = { it == sun },
    )

    @Test
    fun aSecondBypassTheSameDayResendsTheSameLockdown() {
        val afterSunday = StickState(streak = 1, lockedThrough = mon, lastMiss = sun)
        val run = StickCheck.run(inputs(sun.atTime(8, 0), afterSunday))
        assertEquals(StickVerdict.ALREADY_PENALISED, run.verdicts.single().verdict)
        assertEquals(mon, run.signalUntil)
        assertTrue(run.resend)
    }

    @Test
    fun aResendNeverExtendsTheStreakOrTheDate() {
        val stacked = StickState(streak = 3, lockedThrough = sun.plusDays(3), lastMiss = sun)
        val run = StickCheck.run(inputs(sun.atTime(9, 0), stacked))
        assertEquals(stacked, run.state)
        assertEquals(sun.plusDays(3), run.signalUntil)
    }

    @Test
    fun aLockdownThatAlreadyEndedIsNotResent() {
        val ended = StickState(streak = 1, lockedThrough = sun.minusDays(1), lastMiss = sun)
        val run = StickCheck.run(inputs(sun.atTime(8, 0), ended))
        assertEquals(StickVerdict.ALREADY_PENALISED, run.verdicts.single().verdict)
        assertNull(run.signalUntil)
        assertFalse(run.resend)
    }

    @Test
    fun noStoredDateMeansNothingToResend() {
        val undated = StickState(streak = 1, lockedThrough = null, lastMiss = sun)
        assertNull(StickCheck.run(inputs(sun.atTime(8, 0), undated)).signalUntil)
    }

    @Test
    fun anEscapedDayIsNotResent() {
        val afterSunday = StickState(streak = 1, lockedThrough = mon, lastMiss = sun)
        val run = StickCheck.run(inputs(sun.atTime(8, 0), afterSunday, escaped = setOf(sun)))
        assertEquals(StickVerdict.ESCAPED, run.verdicts.single().verdict)
        assertNull(run.signalUntil)
    }

    @Test
    fun aFreshMissIsSentButNotMarkedAResend() {
        val run = StickCheck.run(inputs(tue.atTime(9, 0), StickState()))
        assertEquals(StickVerdict.MISS, run.verdicts.single().verdict)
        assertEquals(tue.plusDays(1), run.signalUntil)
        assertFalse(run.resend)
    }
}
