package com.kuhy.wake_alarm_sync

import android.app.NotificationManager
import android.content.Context
import android.util.Log
import java.time.LocalDateTime
import java.time.LocalTime

/** The notifications check's rules as pure functions; [NotifState] gathers the inputs. */
object NotifRules {
    /** When the evening check runs: early enough to fix it before sleeping. */
    val EVENING: LocalTime = LocalTime.of(21, 0)

    /**
     * Off when the app's notifications are blocked or the ring channel is set
     * to none. A channel not created yet ([ringImportance] null) is not a block.
     */
    fun off(appEnabled: Boolean, ringImportance: Int?): Boolean =
        !appEnabled || ringImportance == NotificationManager.IMPORTANCE_NONE

    /** The next [EVENING] strictly after [now]: never one that has passed. */
    fun nextEvening(now: LocalDateTime): LocalDateTime {
        val tonight = now.toLocalDate().atTime(EVENING)
        return if (tonight.isAfter(now)) tonight else tonight.plusDays(1)
    }

    /** The `notifications` event's data. */
    fun eventData(enabled: Boolean, trigger: String): Map<String, Any?> =
        mapOf("enabled" to enabled, "trigger" to trigger)

    /** The event trigger for a block-state broadcast, or null when it is not about the ring. */
    fun trigger(action: String?, channelId: String?): String? = when (action) {
        NotificationManager.ACTION_APP_BLOCK_STATE_CHANGED -> "app_block"
        NotificationManager.ACTION_NOTIFICATION_CHANNEL_BLOCK_STATE_CHANGED ->
            if (channelId == NotifState.RING_CHANNEL_ID) "channel_block" else null
        else -> null
    }
}

/**
 * Whether the ring can show at all: "All WakeAlarm notifications" switched
 * off, or the ring channel blocked, silences it, and no device policy can
 * lock that switch (2026-11-22).
 *
 * Two readers: [Bypass.checkPermissions] at ring time (a bypass), and
 * [report] at 21:00 ([NotifAlarm]) and whenever the switch moves
 * ([NotifBlockReceiver]), which logs a `notifications` event and pushes it
 * at once so the PC rings in the evening while it is still off.
 */
object NotifState {
    const val RING_CHANNEL_ID = "wake_alarm_ring"
    private const val TAG = "WakeAlarmNotif"

    /** Whether notifications that the ring needs are switched off now. */
    fun off(context: Context): Boolean {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = manager.getNotificationChannel(RING_CHANNEL_ID)
        return NotifRules.off(manager.areNotificationsEnabled(), channel?.importance)
    }

    /** Logs the state as a `notifications` event and publishes it now. Main thread. */
    fun report(context: Context, trigger: String) {
        val enabled = !off(context)
        Log.i(TAG, "notifications enabled=$enabled ($trigger)")
        EventLog.append(context, "notifications", NotifRules.eventData(enabled, trigger))
        HeadlessRingStart.start(context, HeadlessRingStart.PUBLISH_ENTRYPOINT)
    }
}
