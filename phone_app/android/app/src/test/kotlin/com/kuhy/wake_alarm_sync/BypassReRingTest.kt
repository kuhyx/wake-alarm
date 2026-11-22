package com.kuhy.wake_alarm_sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A bypass during a live morning session re-rings it, and that re-ring is
 * recorded as `bypass:<cause>`, not as the leg's deadline (2026-11-22).
 */
class BypassReRingTest {
    @Test
    fun `a bypass with the session live and nothing ringing stamps its re-ring`() {
        assertTrue(BypassRules.stampReRing(sessionLive = true, ringing = false))
    }

    @Test
    fun `a bypass while a deadline re-ring sounds keeps that one`() {
        assertFalse(BypassRules.stampReRing(sessionLive = true, ringing = true))
    }

    @Test
    fun `a bypass of the first ring is not a session re-ring`() {
        assertFalse(BypassRules.stampReRing(sessionLive = false, ringing = false))
    }

    @Test
    fun `a stamp is taken only on its own day`() {
        val stamp = BypassRules.encodeStamp("fsi_revoked", "2026-11-22")
        assertEquals("fsi_revoked", BypassRules.takeStamp(stamp, "2026-11-22"))
        assertNull(BypassRules.takeStamp(stamp, "2026-11-23"))
        assertNull(BypassRules.takeStamp(null, "2026-11-22"))
        assertNull(BypassRules.takeStamp("garbage", "2026-11-22"))
    }
}
