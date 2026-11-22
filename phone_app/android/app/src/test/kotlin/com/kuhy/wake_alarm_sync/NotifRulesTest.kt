package com.kuhy.wake_alarm_sync

import android.app.NotificationManager
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime

/** The 21:00 notifications check (2026-11-22): when it runs and what it says. */
class NotifRulesTest {
    private fun at(day: Int, hour: Int, minute: Int = 0, second: Int = 0) =
        LocalDateTime.of(2026, 11, day, hour, minute, second)

    @Test
    fun beforeNineTheCheckIsTonight() {
        assertEquals(at(22, 21), NotifRules.nextEvening(at(22, 3)))
        assertEquals(at(22, 21), NotifRules.nextEvening(at(22, 20, 59, 59)))
    }

    @Test
    fun theInstantThatJustFiredIsNeverReturned() {
        assertEquals(at(23, 21), NotifRules.nextEvening(at(22, 21)))
        assertEquals(at(23, 21), NotifRules.nextEvening(at(22, 23, 59)))
    }

    @Test
    fun offWhenTheAppIsBlockedOrTheRingChannelIsNone() {
        assertTrue(NotifRules.off(appEnabled = false, ringImportance = null))
        assertTrue(
            NotifRules.off(appEnabled = true, ringImportance = NotificationManager.IMPORTANCE_NONE),
        )
        assertFalse(
            NotifRules.off(appEnabled = true, ringImportance = NotificationManager.IMPORTANCE_HIGH),
        )
        // The channel is created at the first ring; none yet is not a block.
        assertFalse(NotifRules.off(appEnabled = true, ringImportance = null))
    }

    @Test
    fun theEventCarriesEnabledAndTheTrigger() {
        assertEquals(
            mapOf("enabled" to false, "trigger" to "evening"),
            NotifRules.eventData(enabled = false, trigger = "evening"),
        )
    }

    @Test
    fun onlyTheAppOrTheRingChannelCounts() {
        val app = NotificationManager.ACTION_APP_BLOCK_STATE_CHANGED
        val channel = NotificationManager.ACTION_NOTIFICATION_CHANNEL_BLOCK_STATE_CHANGED
        assertEquals("app_block", NotifRules.trigger(app, null))
        assertEquals("channel_block", NotifRules.trigger(channel, NotifState.RING_CHANNEL_ID))
        assertEquals(null, NotifRules.trigger(channel, "wake_alarm_session"))
        assertEquals(null, NotifRules.trigger("android.intent.action.BOOT_COMPLETED", null))
    }
}
