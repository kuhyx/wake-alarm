package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/** The stick on sick days: no miss, no streak change, no lockdown. */
class StickCheckSickTest {
    // 2026-10-20 is a Tuesday; 21 Wed, 22 Thu, 27 the next Tuesday.
    private val tue = LocalDate.of(2026, 10, 20)
    private val wed = tue.plusDays(1)
    private val thu = tue.plusDays(2)

    private fun inputs(
        now: LocalDateTime,
        sick: Set<LocalDate> = emptySet(),
        free: Set<LocalDate> = emptySet(),
        state: StickState = StickState(),
        checkedThrough: LocalDate? = null,
    ) = StickInputs(
        now = now,
        alarm = LocalTime.of(7, 30),
        dismissedOn = { false },
        escapedOn = { false },
        isFree = { it in free },
        isSick = { it in sick },
        state = state,
        checkedThrough = checkedThrough,
    )

    @Test
    fun anUndismissedSickStickDayIsNotAMiss() {
        val run = StickCheck.run(inputs(wed.atTime(9, 0), sick = setOf(wed)))
        assertEquals(StickVerdict.SICK_DAY, run.verdicts.single().verdict)
        assertEquals("sick_day", run.verdicts.single().verdict.wire)
        assertEquals(StickState(), run.state)
        assertNull(run.signalUntil)
    }

    @Test
    fun theSameDayNotSickIsAMiss() {
        val run = StickCheck.run(inputs(wed.atTime(9, 0)))
        assertEquals(StickVerdict.MISS, run.verdicts.single().verdict)
        assertEquals(thu, run.signalUntil)
    }

    @Test
    fun aSickDayKeepsAnExistingStreakAsItWas() {
        val before = StickState(streak = 2, lockedThrough = wed, lastMiss = tue)
        val run = StickCheck.run(inputs(wed.atTime(9, 0), sick = setOf(wed), state = before))
        assertEquals(before, run.state)
    }

    @Test
    fun aSickDayIsSkippedWhenTheStreakLooksBack() {
        // Missed Tuesday, sick Wednesday: Thursday's miss continues the chain.
        val before = StickState(streak = 1, lockedThrough = wed, lastMiss = tue)
        val after = StickCheck.afterMiss(thu, before) { it == wed }
        assertEquals(2, after.streak)
    }

    @Test
    fun aCaughtUpSickDayIsJudgedSick() {
        val run = StickCheck.run(
            inputs(thu.atTime(6, 0), sick = setOf(wed), checkedThrough = tue),
        )
        assertEquals(
            listOf(StickVerdict.SICK_DAY, StickVerdict.TOO_EARLY),
            run.verdicts.map { it.verdict },
        )
    }

    @Test
    fun aFreeDayIsStillNamedFree() {
        val run = StickCheck.run(inputs(wed.atTime(9, 0), free = setOf(wed)))
        assertEquals(StickVerdict.FREE_DAY, run.verdicts.single().verdict)
    }

    @Test
    fun standsDownCoversBothPools() {
        val i = inputs(wed.atTime(9, 0), sick = setOf(wed), free = setOf(thu))
        assertEquals(listOf(false, true, true), listOf(tue, wed, thu).map(i.standsDown))
    }
}
