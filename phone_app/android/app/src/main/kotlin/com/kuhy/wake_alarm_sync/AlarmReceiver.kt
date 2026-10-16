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
        // No free/sick-day check (neither ever starts a session) and no daily
        // re-arm -- that is the wake alarm's business, not this one's.
        if (intent.getStringExtra(AlarmScheduler.EXTRA_REASON) == AlarmScheduler.REASON_RERING) {
            Log.i(TAG, "session deadline missed: re-ringing")
            EventLog.append(context, "alarm_fired", mapOf("reason" to "rering"))
            AlarmService.start(context)
            return
        }
        // A shared free or sick day means the alarm does not ring -- not
        // later, not quieter, not at all -- and nothing ring-related is
        // recorded: no markFired (the stick's own check skips the day too)
        // and no ring_started for the PC. Re-arm for tomorrow (the armed
        // instant has passed, so it rolls over) so the day after is normal.
        // Both caches fail closed: unreadable means ring.
        val skip = RingDecision.skip(FreeDays.isToday(context), SickDays.isToday(context))
        if (skip != null) {
            Log.i(TAG, "${skip.label}: not ringing; re-armed for tomorrow")
            EventLog.append(context, "alarm_fired", mapOf("reason" to skip.wire))
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
