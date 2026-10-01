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
import java.time.format.DateTimeParseException

/**
 * The exact alarm at A + [Stakes.STICK_GRACE_MINUTES] that runs the stick
 * check (trigger `exact`).
 *
 * [AlarmManager.setExactAndAllowWhileIdle], not setAlarmClock: an alarm
 * clock entry would show in the system clock as the "next alarm" between A
 * and A + 15. This check rings nothing, so it needs no alarm-clock status;
 * `USE_EXACT_ALARM` (declared for the daily alarm) grants exact alarms at
 * install. Only if exact alarms are not permitted after all does it fall
 * back to setAlarmClock -- a visible chip beats a check that never runs.
 *
 * Its own receiver and request code ([REQUEST_CODE]), never [AlarmReceiver]:
 * anything that reached that receiver without the re-ring extra would be
 * treated as the daily alarm and *ring*.
 *
 * Armed from [AlarmScheduler.schedule], i.e. by every arm path. The instant
 * is the next occurrence of (A + 15) on its own, and an instant already
 * armed for today is kept against a later one ([StickSchedule.choose]):
 * otherwise a re-arm between A and A + 15 -- the dismiss, the free-day
 * skip, opening the app, boot -- would push today's check to tomorrow,
 * which is exactly the window a phone switched back on lands in.
 */
object StickAlarm {
    private const val REQUEST_CODE = 1004
    private const val SHOW_REQUEST_CODE = 1005
    private const val PREFS = "wake_alarm_stick_alarm"
    private const val KEY_PENDING_AT = "pending_at"
    private const val TAG = "WakeAlarmStickAlarm"

    fun schedule(context: Context, alarm: LocalTime) {
        val now = LocalDateTime.now()
        val at = StickSchedule.choose(
            now,
            StickSchedule.nextOccurrence(now, alarm),
            pendingAt(context),
        )
        // Always re-set, even when the pending instant is kept: a reboot
        // drops every AlarmManager alarm, and boot is one of the callers.
        prefs(context).edit().putString(KEY_PENDING_AT, at.toString()).commit()
        val millis = at.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val how = arm(context, millis)
        Log.i(TAG, "stick check armed for $at via $how")
    }

    /** Arms [millis] exactly; returns which API did it, for the log. */
    private fun arm(context: Context, millis: Long): String {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val exactAllowed = Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            manager.canScheduleExactAlarms()
        if (exactAllowed) {
            try {
                manager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    millis,
                    firePendingIntent(context),
                )
                return "setExactAndAllowWhileIdle"
            } catch (e: SecurityException) {
                Log.w(TAG, "exact alarm refused; falling back to setAlarmClock", e)
            }
        }
        manager.setAlarmClock(
            AlarmManager.AlarmClockInfo(millis, showIntent(context)),
            firePendingIntent(context),
        )
        return "setAlarmClock"
    }

    fun cancel(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(firePendingIntent(context))
        prefs(context).edit().remove(KEY_PENDING_AT).commit()
    }

    private fun pendingAt(context: Context): LocalDateTime? = try {
        prefs(context).getString(KEY_PENDING_AT, null)?.let { LocalDateTime.parse(it) }
    } catch (e: DateTimeParseException) {
        null
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun firePendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        REQUEST_CODE,
        Intent(context, StickCheckReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun showIntent(context: Context): PendingIntent = PendingIntent.getActivity(
        context,
        SHOW_REQUEST_CODE,
        Intent(context, MainActivity::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}

/** Receives [StickAlarm]: runs the check, then arms tomorrow's. */
class StickCheckReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        StickRunner.run(context, "exact")
        // After an undismissed ring nothing else re-arms until the watchdog
        // or the next app launch, so the check re-arms itself. The instant
        // that just fired is now in the past, so choose() drops it.
        AlarmScheduler.storedAlarm(context)?.let { StickAlarm.schedule(context, it) }
    }
}
