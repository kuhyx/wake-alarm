package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SessionWarnTest {
    private val deadline = 1_000_000_000L

    @Test
    fun warnsThreeMinutesBeforeTheDeadline() {
        assertEquals(deadline - 180_000L, SessionWarn.warnAt(deadline, deadline - 600_000L))
    }

    @Test
    fun aWarnInstantAlreadyPastIsDropped() {
        assertNull(SessionWarn.warnAt(deadline, deadline - 60_000L))
    }

    @Test
    fun aDeadlineAlreadyPastIsDropped() {
        assertNull(SessionWarn.warnAt(deadline, deadline + 1L))
    }
}
