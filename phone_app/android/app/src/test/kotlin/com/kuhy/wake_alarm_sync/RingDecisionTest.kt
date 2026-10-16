package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RingDecisionTest {
    @Test
    fun aNormalDayRings() {
        assertNull(RingDecision.skip(isFree = false, isSick = false))
    }

    @Test
    fun aSickDayIsSilentAndNamedSick() {
        val skip = RingDecision.skip(isFree = false, isSick = true)
        assertEquals(RingSkip.SICK_DAY, skip)
        assertEquals("sick_day", skip?.wire)
        assertEquals("sick day", skip?.label)
    }

    @Test
    fun aFreeDayIsSilentAndNamedFree() {
        assertEquals("free_day", RingDecision.skip(isFree = true, isSick = false)?.wire)
    }

    @Test
    fun aDateInBothPoolsIsNamedFree() {
        assertEquals(RingSkip.FREE_DAY, RingDecision.skip(isFree = true, isSick = true))
    }
}
