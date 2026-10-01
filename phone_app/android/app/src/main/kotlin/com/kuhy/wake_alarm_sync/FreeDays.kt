package com.kuhy.wake_alarm_sync

import android.content.Context
import android.util.Log
import java.time.LocalDate

/**
 * The native copy of the shared free-day pool: the ISO dates on which the
 * alarm must not ring.
 *
 * The alarm fires with no Flutter engine running, so the Dart-side pool
 * (`free_day_pool.dart`) is unreadable at 08:00. Dart rewrites this cache
 * after every local change and every sync; [AlarmReceiver] reads it before
 * making any noise.
 *
 * Fail closed: anything unreadable means "not a free day", so a corrupt or
 * missing cache restores the normal rules rather than silencing the alarm.
 * That matches `freedays.is_free_day()` on the PC.
 */
object FreeDays {

    private const val TAG = "WakeAlarmFreeDays"
    private const val PREFS = "wake_alarm_freedays"
    private const val KEY_DATES = "free_dates"

    /** Replaces the cached set with [isoDates] (`yyyy-MM-dd` each). */
    fun store(context: Context, isoDates: List<String>) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putStringSet(KEY_DATES, isoDates.toSet())
            .apply()
    }

    /** Whether today (local calendar day) is in the cached set. */
    fun isToday(context: Context): Boolean = isFree(context, LocalDate.now())

    /**
     * Whether [day] is in the cached set. Past free days stay in it (Dart
     * hands over every free record), which is what lets the stick's streak
     * skip them.
     */
    fun isFree(context: Context, day: LocalDate): Boolean = try {
        val dates = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getStringSet(KEY_DATES, emptySet()) ?: emptySet()
        dates.contains(day.toString())
    } catch (e: RuntimeException) {
        Log.w(TAG, "free-day cache unreadable; ringing as normal", e)
        false
    }
}
