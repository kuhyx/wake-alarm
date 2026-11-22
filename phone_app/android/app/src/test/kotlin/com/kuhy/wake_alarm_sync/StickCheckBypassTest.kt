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
 * A bypass (the app paused, its admin removed, a permission revoked, the
 * ring killed) is a miss on any ringing day, 2026-11-22.
 */
class StickCheckBypassTest {
    // 2026-11-20 is a Friday, 22 a Sunday, 24 a Tuesday.
    private val fri = LocalDate.of(2026, 11, 20)
    private val sun = LocalDate.of(2026, 11, 22)
    private val mon = sun.plusDays(1)
    private val tue = sun.plusDays(2)

    private fun inputs(
        now: LocalDateTime,
        bypass: Set<LocalDate> = emptySet(),
        dismissed: Set<LocalDate> = emptySet(),
        free: Set<LocalDate> = emptySet(),
        sick: Set<LocalDate> = emptySet(),
        state: StickState = StickState(),
        checkedThrough: LocalDate? = null,
    ) = StickInputs(
        now = now,
        alarm = LocalTime.of(7, 30),
        dismissedOn = { it in dismissed },
        escapedOn = { false },
        isFree = { it in free },
        isSick = { it in sick },
        state = state,
        checkedThrough = checkedThrough,
        bypassOn = { it in bypass },
    )

    @Test
    fun aSundayBypassIsAMissLockingThroughMonday() {
        val run = StickCheck.run(inputs(sun.atTime(7, 40), bypass = setOf(sun)))
        assertEquals(StickVerdict.MISS, run.verdicts.single().verdict)
        assertEquals(StickState(streak = 1, lockedThrough = mon, lastMiss = sun), run.state)
        assertEquals(mon, run.signalUntil)
    }

    @Test
    fun aBypassCountsEvenBeforeTheGraceAndAfterADismiss() {
        val run = StickCheck.run(
            inputs(tue.atTime(7, 35), bypass = setOf(tue), dismissed = setOf(tue)),
        )
        assertEquals(StickVerdict.MISS, run.verdicts.single().verdict)
    }

    @Test
    fun aTuesdayMissAfterASundayBypassStacks() {
        val afterSunday = StickState(streak = 1, lockedThrough = mon, lastMiss = sun)
        val run = StickCheck.run(
            inputs(
                tue.atTime(9, 0),
                bypass = setOf(sun),
                state = afterSunday,
                checkedThrough = mon,
            ),
        )
        assertEquals(StickVerdict.MISS, run.verdicts.last().verdict)
        assertEquals(2, run.state.streak)
        assertEquals(tue.plusDays(2), run.state.lockedThrough)
    }

    @Test
    fun aLateFridayWithNoBypassChangesNothing() {
        val run = StickCheck.run(inputs(fri.atTime(11, 0)))
        assertEquals(StickVerdict.NOT_STICK_DAY, run.verdicts.single().verdict)
        assertEquals(StickState(), run.state)
        assertNull(run.signalUntil)
    }

    @Test
    fun freeAndSickDaysStayNeutralEvenWithABypass() {
        val free = StickCheck.run(inputs(sun.atTime(8, 0), bypass = setOf(sun), free = setOf(sun)))
        assertEquals(StickVerdict.FREE_DAY, free.verdicts.single().verdict)
        val sick = StickCheck.run(inputs(tue.atTime(8, 0), bypass = setOf(tue), sick = setOf(tue)))
        assertEquals(StickVerdict.SICK_DAY, sick.verdicts.single().verdict)
        assertEquals(StickState(), sick.state)
    }

    @Test
    fun aSecondBypassTheSameDayIsAlreadyPenalised() {
        val afterSunday = StickState(streak = 1, lockedThrough = mon, lastMiss = sun)
        val run = StickCheck.run(
            inputs(sun.atTime(8, 0), bypass = setOf(sun), state = afterSunday, checkedThrough = sun),
        )
        assertEquals(StickVerdict.ALREADY_PENALISED, run.verdicts.single().verdict)
        assertNull(run.signalUntil)
    }

    @Test
    fun aBypassCountsOnlyOnARingingDayWithARingOrSessionLive() {
        assertTrue(BypassRules.counts(ringingDay = true, ringLive = true, sessionLive = false))
        assertTrue(BypassRules.counts(ringingDay = true, ringLive = false, sessionLive = true))
        assertFalse(BypassRules.counts(ringingDay = true, ringLive = false, sessionLive = false))
        assertFalse(BypassRules.counts(ringingDay = false, ringLive = true, sessionLive = true))
    }

    @Test
    fun aRingIsKilledWhenItFiredUndismissedAndNothingRings() {
        assertTrue(BypassRules.ringKilled(firedToday = true, dismissedToday = false, ringing = false))
        assertFalse(BypassRules.ringKilled(firedToday = true, dismissedToday = false, ringing = true))
        assertFalse(BypassRules.ringKilled(firedToday = true, dismissedToday = true, ringing = false))
        assertFalse(BypassRules.ringKilled(firedToday = false, dismissedToday = false, ringing = false))
    }

    @Test
    fun theSameCauseWithinAMinuteIsARepeat() {
        val last = "fsi_revoked" to 1_000L
        assertFalse(BypassRules.isRepeat(null, "fsi_revoked", 1_000L, 60_000L))
        assertTrue(BypassRules.isRepeat(last, "fsi_revoked", 60_999L, 60_000L))
        assertFalse(BypassRules.isRepeat(last, "fsi_revoked", 61_000L, 60_000L))
        assertFalse(BypassRules.isRepeat(last, "suspended", 2_000L, 60_000L))
        assertFalse(BypassRules.isRepeat(last, "fsi_revoked", 999L, 60_000L))
    }
}
