package com.kuhy.wake_alarm_sync

import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import java.util.Calendar

/**
 * Arms and cancels the one exact alarm this app owns.
 *
 * Uses [AlarmManager.setAlarmClock] rather than setExactAndAllowWhileIdle: it is
 * the only API that is Doze-exempt *and* needs no SCHEDULE_EXACT_ALARM user
 * prompt (USE_EXACT_ALARM covers an alarm-clock app), and it is what grants the
 * receiver its brief foreground-service exemption when it fires with the screen
 * off. Everything else about the ring path depends on that exemption.
 */
object AlarmScheduler {

    /** Request code for the single alarm PendingIntent; reused so re-arming replaces. */
    private const val REQUEST_CODE = 1001

    /** SharedPreferences file holding the armed time, so boot can re-arm it. */
    private const val PREFS = "wake_alarm_scheduler"
    private const val KEY_HOUR = "hour"
    private const val KEY_MINUTE = "minute"

    /** Sentinel for "no alarm stored", distinguishable from a valid 0. */
    private const val NONE = -1

    /**
     * Arms the alarm for the next occurrence of [hour]:[minute] in local time,
     * and persists it so [rearmFromStorage] can restore it after a reboot.
     */
    fun schedule(context: Context, hour: Int, minute: Int) {
        persist(context, hour, minute)
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val at = nextOccurrence(hour, minute)
        // showIntent is what the system Clock surfaces; the fire intent is separate.
        manager.setAlarmClock(
            AlarmManager.AlarmClockInfo(at, showIntent(context)),
            firePendingIntent(context),
        )
    }

    /** Cancels the armed alarm and forgets the stored time. */
    fun cancel(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(firePendingIntent(context))
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .remove(KEY_HOUR).remove(KEY_MINUTE).apply()
    }

    /**
     * Re-arms from the persisted time, returning false when nothing was stored.
     *
     * Called on BOOT_COMPLETED and after a dismiss: an alarm clock that only
     * armed on user edit would ring exactly once.
     */
    fun rearmFromStorage(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val hour = prefs.getInt(KEY_HOUR, NONE)
        val minute = prefs.getInt(KEY_MINUTE, NONE)
        if (hour == NONE || minute == NONE) return false
        schedule(context, hour, minute)
        return true
    }

    /**
     * Whether the system will actually honour a full-screen intent.
     *
     * False from API 34 unless the user granted it. The caller must treat this
     * as a hard failure rather than logging and continuing: without it the
     * alarm posts a notification the sleeping user never sees.
     */
    fun canUseFullScreenIntent(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return true
        val notifications =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        return notifications.canUseFullScreenIntent()
    }

    private fun persist(context: Context, hour: Int, minute: Int) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putInt(KEY_HOUR, hour).putInt(KEY_MINUTE, minute).apply()
    }

    /** Next local-time instant matching [hour]:[minute]; tomorrow if today has passed. */
    private fun nextOccurrence(hour: Int, minute: Int): Long {
        val now = Calendar.getInstance()
        val at = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        if (!at.after(now)) at.add(Calendar.DAY_OF_YEAR, 1)
        return at.timeInMillis
    }

    /** FLAG_IMMUTABLE is mandatory from API 31; without it this throws at arm time. */
    private fun firePendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        REQUEST_CODE,
        Intent(context, AlarmReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    /** Tapping the clock's alarm chip opens the app rather than the ring screen. */
    private fun showIntent(context: Context): PendingIntent = PendingIntent.getActivity(
        context,
        REQUEST_CODE + 1,
        Intent(context, MainActivity::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}
