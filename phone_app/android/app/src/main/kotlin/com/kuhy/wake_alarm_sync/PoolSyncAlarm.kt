package com.kuhy.wake_alarm_sync

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * The background sync of both day pools before the alarm ([PoolSyncSchedule]).
 *
 * The ring decision itself stays a cache read: [AlarmReceiver] spends its
 * short alarm-clock exemption starting [AlarmService], and a network call
 * there could cost the ring. So the network happens *earlier*, here, and
 * the receiver keeps reading whatever the last sync left -- including a
 * failed one's (fail closed: no cache entry means ring).
 *
 * [AlarmManager.setExactAndAllowWhileIdle], not setAlarmClock: a sync must
 * never show as the "next alarm". Falls back to the inexact
 * setAndAllowWhileIdle when exact alarms are refused -- a sync a few
 * minutes late is fine. Own receiver and request code ([REQUEST_CODE]),
 * never [AlarmReceiver], which would ring.
 *
 * Armed from [AlarmScheduler.schedule] (every arm path, boot included) and
 * re-armed by its own receiver.
 */
object PoolSyncAlarm {
    private const val REQUEST_CODE = 1006
    private const val TAG = "WakeAlarmPoolSync"

    fun schedule(context: Context, alarm: LocalTime?) {
        val at = PoolSyncSchedule.next(LocalDateTime.now(), alarm)
        val millis = at.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        Log.i(TAG, "pool sync armed for $at via ${arm(context, millis)}")
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

    fun cancel(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(pendingIntent(context))
    }

    private fun pendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        REQUEST_CODE,
        Intent(context, PoolSyncReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}

/**
 * Receives [PoolSyncAlarm]: re-arms the next slot first (so a crash below
 * cannot end the chain), then holds the broadcast open with goAsync while
 * [PoolSyncEngine] syncs. Holding it keeps the process out of the cached
 * state, where Android would freeze the Dart isolate mid-request.
 */
class PoolSyncReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        PoolSyncAlarm.schedule(context, AlarmScheduler.storedAlarm(context))
        val pending = goAsync()
        PoolSyncEngine.run(context) { pending.finish() }
    }
}
