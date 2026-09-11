package com.kuhy.wake_alarm_sync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Receives the exact alarm and hands straight off to [AlarmService].
 *
 * Deliberately does no work of its own: a receiver gets ~10s and no wakelock,
 * so anything that must outlive it (sound, the wakelock, the full-screen
 * intent) belongs to the foreground service. Starting that service from here
 * is legal with the screen off only because setAlarmClock grants an
 * alarm-clock exemption to the broadcast.
 */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        // A shared free day means the alarm does not ring -- not later, not
        // quieter, not at all. Re-arm for tomorrow (nextOccurrence rolls over
        // because the armed instant has passed) so the day after is normal.
        if (FreeDays.isToday(context)) {
            Log.i(TAG, "free day: not ringing; re-armed for tomorrow")
            AlarmScheduler.rearmFromStorage(context)
            return
        }
        AlarmService.start(context)
    }

    private companion object {
        const val TAG = "WakeAlarmReceiver"
    }
}
