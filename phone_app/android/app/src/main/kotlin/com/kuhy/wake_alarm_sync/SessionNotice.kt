package com.kuhy.wake_alarm_sync

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.util.Log
import java.time.LocalDate

/**
 * The native copy of the live morning session: which leg is waiting and when
 * it re-rings, plus the ongoing notification that shows the same.
 *
 * Two jobs, one record. The launcher starts [MainActivity], and it has to
 * know *before any Dart runs* whether to step aside into the session screen;
 * the notification needs the leg glyph with no engine running behind it.
 * Dart rewrites this cache on every leg change (`updateSessionNotice`) and
 * `finishSession` clears it, so it is only ever as stale as the last change.
 *
 * The record carries the session's date and [isLiveToday] refuses any other:
 * a cache left behind by a session that never finished (the phone died
 * mid-morning) must not open a dead checklist the next evening -- the same
 * class of bug as the re-ring instant `restoreReRing` drops.
 *
 * Fail closed: unreadable means "no session", so a corrupt cache costs the
 * shortcut, never the home screen.
 */
object SessionNotice {

    private const val TAG = "WakeAlarmSession"
    private const val PREFS = "wake_alarm_session"
    private const val KEY_DATE = "date"
    private const val KEY_LABEL = "label"
    private const val CHANNEL_ID = "wake_alarm_session"
    private const val NOTIFICATION_ID = 43

    /** Intent extra naming the Dart route [AlarmActivity] should open with. */
    const val EXTRA_ROUTE = "route"

    /** The session screen's route in main.dart. */
    const val SESSION_ROUTE = "/session"

    /** Records [label] for [date] and posts (or updates) the notification. */
    fun update(context: Context, date: String, label: String, deadlineMillis: Long?) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_DATE, date)
            .putString(KEY_LABEL, label)
            .apply()
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, APP_NAME, NotificationManager.IMPORTANCE_LOW),
        )
        manager.notify(NOTIFICATION_ID, build(context, label, deadlineMillis))
    }

    /** Drops the record and the notification; the session's finish path only. */
    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .cancel(NOTIFICATION_ID)
    }

    /** Whether a session dated today (local calendar day) is still live. */
    fun isLiveToday(context: Context): Boolean = try {
        val date = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_DATE, null)
        date == LocalDate.now().toString()
    } catch (e: RuntimeException) {
        Log.w(TAG, "session cache unreadable; treating as no session", e)
        false
    }

    /** Opens [AlarmActivity] on the session screen, or brings the live one forward. */
    fun resumeIntent(context: Context): Intent =
        Intent(context, AlarmActivity::class.java)
            .putExtra(EXTRA_ROUTE, SESSION_ROUTE)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    private fun build(context: Context, label: String, deadlineMillis: Long?): Notification {
        val tap = PendingIntent.getActivity(
            context,
            NOTIFICATION_ID,
            resumeIntent(context),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = Notification.Builder(context, CHANNEL_ID)
            .setContentText(label)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setCategory(Notification.CATEGORY_REMINDER)
            .setContentIntent(tap)
            .setOngoing(true)
            // Re-posted on every leg change; a buzz each time would be noise.
            .setOnlyAlertOnce(true)
        if (deadlineMillis != null) {
            // The system renders the countdown itself, so Dart never has to
            // tick this notification: one post per leg is enough.
            builder.setWhen(deadlineMillis)
                .setUsesChronometer(true)
                .setChronometerCountDown(true)
                .setShowWhen(true)
        }
        return builder.build()
    }
}
