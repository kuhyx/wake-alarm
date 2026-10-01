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
        // A session deadline: the user dismissed the alarm and then stalled.
        // No free-day check (a free day never starts a session) and no daily
        // re-arm -- that is the wake alarm's business, not this one's.
        if (intent.getStringExtra(AlarmScheduler.EXTRA_REASON) == AlarmScheduler.REASON_RERING) {
            Log.i(TAG, "session deadline missed: re-ringing")
            EventLog.append(context, "alarm_fired", mapOf("reason" to "rering"))
            AlarmService.start(context)
            return
        }
        // A shared free day means the alarm does not ring -- not later, not
        // quieter, not at all. Re-arm for tomorrow (nextOccurrence rolls over
        // because the armed instant has passed) so the day after is normal.
        if (FreeDays.isToday(context)) {
            Log.i(TAG, "free day: not ringing; re-armed for tomorrow")
            EventLog.append(context, "alarm_fired", mapOf("reason" to "free_day"))
            AlarmScheduler.rearmFromStorage(context)
            return
        }
        // The one fresh (non-re-ring) daily alarm. Recorded here, not in
        // Dart, so a poweroff mid-ring can never race it: setAlarmClock has
        // already woken the CPU by the time this line runs.
        RingWatch.markFired(context)
        AlarmService.start(context)
        EventLog.append(context, "alarm_fired", mapOf("reason" to "daily"))
        // After the sound is started, never before: tells the PC the phone
        // is ringing even when the ring screen never opens.
        HeadlessRingStart.start(context)
    }

    private companion object {
        const val TAG = "WakeAlarmReceiver"
    }
}
