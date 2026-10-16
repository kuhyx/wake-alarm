package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalDateTime
import java.time.LocalTime

class PoolSyncScheduleTest {
    private val alarm = LocalTime.of(7, 30)

    private fun at(day: Int, hour: Int, minute: Int = 0) =
        LocalDateTime.of(2026, 10, day, hour, minute)

    @Test
    fun afternoonNextSlotIsTheEvening() {
        assertEquals(at(16, 21), PoolSyncSchedule.next(at(16, 14), alarm))
    }

    @Test
    fun afterTheEveningNextSlotIsHalfAnHourBeforeTomorrowsAlarm() {
        assertEquals(at(17, 7), PoolSyncSchedule.next(at(16, 21, 0), alarm))
        assertEquals(at(17, 7), PoolSyncSchedule.next(at(16, 23, 59), alarm))
    }

    @Test
    fun earlyMorningNextSlotIsTodaysPreAlarm() {
        assertEquals(at(17, 7), PoolSyncSchedule.next(at(17, 3), alarm))
    }

    @Test
    fun theSlotThatJustFiredIsNeverReturned() {
        assertEquals(at(17, 21), PoolSyncSchedule.next(at(17, 7), alarm))
    }

    @Test
    fun withNoAlarmStoredOnlyTheEveningRuns() {
        assertEquals(at(16, 21), PoolSyncSchedule.next(at(16, 3), null))
        assertEquals(at(17, 21), PoolSyncSchedule.next(at(16, 22), null))
    }

    @Test
    fun theLeadIsThirtyMinutes() {
        assertEquals(30L, PoolSyncSchedule.LEAD_MINUTES)
        assertEquals(
            at(17, 7, 30).minusMinutes(30),
            PoolSyncSchedule.next(at(16, 22), alarm),
        )
    }
}
