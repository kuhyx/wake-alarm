package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class DayCacheTest {
    private val day = LocalDate.of(2026, 10, 20)

    @Test
    fun aCachedDateIsInTheSet() {
        assertTrue(DayCache.contains(day) { setOf("2026-10-19", "2026-10-20") })
    }

    @Test
    fun anotherDateIsNot() {
        assertFalse(DayCache.contains(day) { setOf("2026-10-21") })
    }

    @Test
    fun aMissingCacheMeansNotInTheSet() {
        assertFalse(DayCache.contains(day) { null })
    }

    @Test
    fun anUnreadableCacheFailsClosedAndReportsTheError() {
        val seen = mutableListOf<RuntimeException>()
        val boom = ClassCastException("not a string set")
        assertFalse(DayCache.contains(day, onError = { seen += it }) { throw boom })
        assertEquals(listOf<RuntimeException>(boom), seen)
    }
}
