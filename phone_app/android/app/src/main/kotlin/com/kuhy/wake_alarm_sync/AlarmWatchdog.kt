package com.kuhy.wake_alarm_sync

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Keeps the alarm armed without the user ever opening the app.
 *
 * The ring path already re-arms on boot and on dismiss, but both are *events*:
 * if the app is force-stopped, or an update clears the pending intent, or a
 * re-arm silently fails, nothing notices until the morning it does not ring.
 * This is the periodic check that closes that gap — it runs daily, asks
 * whether an alarm is actually scheduled, and schedules one if not.
 *
 * Deliberately self-rescheduling rather than WorkManager: the ring path takes
 * no third-party dependency (see AlarmChannel), and AlarmManager is already
 * present and understood here.
 */
object AlarmWatchdog {

    private const val TAG = "WakeAlarmWatchdog"

    /** Request code for the watchdog's own repeating wake-up. */
    private const val REQUEST_CODE = 1002

    /** How often to verify the alarm is still armed. */
    private const val INTERVAL_MS = AlarmManager.INTERVAL_DAY

    /** Starts (or refreshes) the periodic check. Safe to call repeatedly. */
    fun schedule(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        // Inexact on purpose: this only has to happen *sometime* each day, and
        // an inexact repeat costs no exact-alarm budget and survives Doze by
        // being deferred rather than dropped.
        manager.setInexactRepeating(
            AlarmManager.RTC_WAKEUP,
            System.currentTimeMillis() + INTERVAL_MS,
            INTERVAL_MS,
            pendingIntent(context),
        )
    }

    /**
     * Re-arms the alarm if nothing is currently scheduled.
     *
     * Re-arming unconditionally would be simpler, but would also reset a
     * legitimately pending alarm every day; `rearmFromStorage` is idempotent
     * for an unchanged time, so this stays cheap either way.
     */
    fun verify(context: Context) {
        val rearmed = AlarmScheduler.rearmFromStorage(context)
        Log.i(TAG, "daily check: rearmed=$rearmed")
        // Third net behind the exact check and boot: within a day, whatever
        // dropped the other two, today's miss is still caught here.
        StickRunner.run(context, "watchdog")
    }

    private fun pendingIntent(context: Context): PendingIntent =
        PendingIntent.getBroadcast(
            context,
            REQUEST_CODE,
            Intent(context, WatchdogReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
}

/** Receives the daily watchdog tick. */
class WatchdogReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        AlarmWatchdog.verify(context)
        // Re-assert the repeat: setInexactRepeating does not survive a reboot,
        // and BootReceiver is the only other thing that would restore it.
        AlarmWatchdog.schedule(context)
    }
}
