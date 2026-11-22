package com.kuhy.wake_alarm_sync

import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.time.LocalDateTime
import java.time.ZoneId

/**
 * The exact daily alarm at [NotifRules.EVENING] (21:00) that runs
 * [NotifState.report] (trigger `evening`), so the PC can ring while the
 * notifications are still off and there is time to fix them before sleeping.
 *
 * Same shape as [PoolSyncAlarm]: setExactAndAllowWhileIdle (never an
 * alarm-clock entry, which would show as the "next alarm"), inexact when
 * exact alarms are refused, its own receiver and request code
 * ([REQUEST_CODE]), never [AlarmReceiver], which would ring.
 *
 * Armed from [AlarmScheduler.schedule] (every arm path: launch, dismiss,
 * skip), from [BootReceiver] and from the watchdog, and re-armed by its own
 * receiver. Always the next future 21:00 ([NotifRules.nextEvening]), so a
 * re-arm never restores an instant that has passed.
 */
object NotifAlarm {
    private const val REQUEST_CODE = 1007
    private const val TAG = "WakeAlarmNotifAlarm"

    /**
     * How long a receiver holds its broadcast open after starting the
     * publish: a receiver that returns lets Android freeze the headless Dart
     * engine mid-request (see [PoolSyncReceiver]). Well inside the 60 s a
     * background broadcast may stay open.
     */
    const val HOLD_MS = 25_000L

    fun schedule(context: Context) {
        val at = NotifRules.nextEvening(LocalDateTime.now())
        val millis = at.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        Log.i(TAG, "notifications check armed for $at via ${arm(context, millis)}")
    }

    /** Arms [millis], exactly when permitted; returns which API did it. */
    private fun arm(context: Context, millis: Long): String {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val exactAllowed = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            manager.canScheduleExactAlarms()
        if (exactAllowed) {
            try {
                manager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    millis,
                    pendingIntent(context),
                )
                return "setExactAndAllowWhileIdle"
            } catch (e: SecurityException) {
                Log.w(TAG, "exact alarm refused; arming inexact", e)
            }
        }
        manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, millis, pendingIntent(context))
        return "setAndAllowWhileIdle"
    }

    /** Holds [receiver]'s broadcast open for [HOLD_MS], then lets it go. */
    fun hold(receiver: BroadcastReceiver) {
        val pending = receiver.goAsync()
        Handler(Looper.getMainLooper()).postDelayed({ pending.finish() }, HOLD_MS)
    }

    private fun pendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        REQUEST_CODE,
        Intent(context, NotifCheckReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}

/** Receives [NotifAlarm]: re-arms tomorrow's first, so a crash below cannot end the chain. */
class NotifCheckReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        NotifAlarm.schedule(context)
        NotifAlarm.hold(this)
        NotifState.report(context, "evening")
    }
}

/**
 * The app's notifications, or the ring channel, blocked or unblocked in
 * Settings. The system sends both to this app alone; switching them back on
 * publishes `enabled=true` at once, which stops the PC's evening ring.
 */
class NotifBlockReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val channel = intent.getStringExtra(NotificationManager.EXTRA_NOTIFICATION_CHANNEL_ID)
        val trigger = NotifRules.trigger(intent.action, channel) ?: return
        NotifAlarm.hold(this)
        NotifState.report(context, trigger)
    }
}
