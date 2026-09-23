package com.kuhy.wake_alarm_sync

import android.content.Context
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * Tracks, natively, whether today's ring was ever dismissed.
 *
 * The dismiss gate (tag1 -> steps -> tag2 -> challenges) lives in Dart, but a
 * phone powered off before touching any of it never runs Dart at all that
 * morning -- there is no session, no store, nothing to ask. Two dates, set
 * from opposite ends of the ring, are enough to answer "was this abandoned"
 * with no engine required:
 *
 * - [markFired] -- called from [AlarmReceiver], the instant a *fresh*
 *   (non-re-ring) alarm fires. This runs well before a poweroff mid-ring
 *   could ever prevent it -- setAlarmClock has already woken the CPU.
 * - [markDismissed] -- called from Dart over the alarm channel, the instant
 *   the initial dismiss gate actually completes (`session_handoff.dart`'s
 *   `afterDismiss`).
 *
 * [abandonedRingDate] is non-null exactly when a ring fired and nothing
 * since has dismissed it -- checked from [BootReceiver] and the daily
 * [WatchdogReceiver] tick, both of which run without a Flutter engine.
 */
object RingWatch {
    private const val PREFS = "wake_alarm_ring_watch"
    private const val KEY_FIRED_DATE = "fired_date"
    private const val KEY_DISMISSED_DATE = "dismissed_date"

    fun markFired(context: Context) {
        prefs(context).edit().putString(KEY_FIRED_DATE, today()).apply()
    }

    fun markDismissed(context: Context) {
        prefs(context).edit().putString(KEY_DISMISSED_DATE, today()).apply()
    }

    /** The date a ring fired but was never dismissed, or null. */
    fun abandonedRingDate(context: Context): String? {
        val fired = prefs(context).getString(KEY_FIRED_DATE, null) ?: return null
        val dismissed = prefs(context).getString(KEY_DISMISSED_DATE, null)
        return if (fired == dismissed) null else fired
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun today(): String =
        SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Calendar.getInstance().time)
}
