package com.kuhy.wake_alarm_sync

import android.app.AlarmManager
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import java.time.LocalTime
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

    /**
     * Request code for the morning session's re-ring.
     *
     * Distinct from [REQUEST_CODE] on purpose: a PendingIntent is keyed by
     * request code, so arming the re-ring under 1001 would silently replace
     * tomorrow's wake alarm with a one-shot twenty minutes from now.
     */
    private const val RERING_REQUEST_CODE = 1003

    /** Intent extra naming why the receiver fired; absent on the daily alarm. */
    const val EXTRA_REASON = "reason"

    /** [EXTRA_REASON] value for a session deadline. */
    const val REASON_RERING = "rering"

    /** SharedPreferences file holding the armed time, so boot can re-arm it. */
    private const val PREFS = "wake_alarm_scheduler"
    private const val KEY_HOUR = "hour"
    private const val KEY_MINUTE = "minute"

    /** Epoch millis of the armed re-ring, so a reboot mid-session restores it. */
    private const val KEY_RERING_AT = "rering_at"

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
        // Every arm path (picker, boot, dismiss, free-day skip, watchdog)
        // ends here, so the stick's own check can never be left unarmed.
        StickAlarm.schedule(context, LocalTime.of(hour, minute))
    }

    /** Cancels the armed alarm and forgets the stored time. */
    fun cancel(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(firePendingIntent(context))
        StickAlarm.cancel(context)
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

    /** The stored daily time `A`, or null when none was ever armed. */
    fun storedAlarm(context: Context): LocalTime? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val hour = prefs.getInt(KEY_HOUR, NONE)
        val minute = prefs.getInt(KEY_MINUTE, NONE)
        if (hour == NONE || minute == NONE) return null
        return LocalTime.of(hour, minute)
    }

    /**
     * Arms the morning session's re-ring for the absolute instant [atMillis].
     *
     * Same [AlarmManager.setAlarmClock] path as the daily alarm: it is the
     * one this repo has proved starts the foreground service with the screen
     * off. Replaces any earlier re-ring — the session has exactly one live
     * deadline at a time.
     */
    fun scheduleReRing(context: Context, atMillis: Long) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putLong(KEY_RERING_AT, atMillis).apply()
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.setAlarmClock(
            AlarmManager.AlarmClockInfo(atMillis, showIntent(context)),
            reRingPendingIntent(context),
        )
    }

    /**
     * Drops the pending re-ring. Reached only from the session's own finish
     * path (`finishSession`); there is no Dart-facing cancel for the alarm
     * itself.
     */
    fun clearReRing(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(reRingPendingIntent(context))
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .remove(KEY_RERING_AT).apply()
    }

    /**
     * Re-arms a stored re-ring after a reboot; false when none is still due.
     *
     * A past instant is dropped, never fired: a session whose deadline
     * passed while the phone was off is over, and a stale instant is not
     * confined to reboots -- Android re-delivered BOOT_COMPLETED to a
     * force-stopped app on its next launch (Pixel 6a, 2026-09-16), which
     * fired a nine-minute-old deadline into an evening with no session.
     */
    fun restoreReRing(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val at = prefs.getLong(KEY_RERING_AT, NONE.toLong())
        if (at == NONE.toLong()) return false
        if (at <= System.currentTimeMillis()) {
            prefs.edit().remove(KEY_RERING_AT).apply()
            return false
        }
        scheduleReRing(context, at)
        return true
    }

    /**
     * Whether the system will actually honour a full-screen intent.
     *
     * Requires BOTH the API 34 full-screen-intent grant AND notifications
     * being enabled at all: with notifications blocked the post is dropped
     * before the full-screen intent is ever considered, so the alarm rings
     * with no dismiss screen. Measured on the API 36 AVD, where a freshly
     * installed app sits at importance=NONE and the op logs a rejectTime.
     *
     * The caller must treat a false here as a hard failure rather than
     * logging and continuing — the sleeping user never sees a notification.
     */
    fun canUseFullScreenIntent(context: Context): Boolean {
        val notifications =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (!notifications.areNotificationsEnabled()) return false
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return true
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

    /** The re-ring's own PendingIntent; the extra is how the receiver tells them apart. */
    private fun reRingPendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        RERING_REQUEST_CODE,
        Intent(context, AlarmReceiver::class.java).putExtra(EXTRA_REASON, REASON_RERING),
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
