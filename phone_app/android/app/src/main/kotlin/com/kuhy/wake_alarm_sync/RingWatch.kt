package com.kuhy.wake_alarm_sync

import android.content.Context
import java.text.SimpleDateFormat
import java.time.LocalDate
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
 * The stick ([StickCheck]) reads only [dismissedOn]. It used to ask "did a
 * ring fire and go undismissed", which needs the *fired* date -- and a phone
 * switched off before the alarm never fires, so that escaped everything.
 * The fired date stays as evidence for whoever debugs a morning.
 */
object RingWatch {
    private const val PREFS = "wake_alarm_ring_watch"
    private const val KEY_FIRED_DATE = "fired_date"
    private const val KEY_DISMISSED_DATE = "dismissed_date"
    private const val KEY_DISMISSED_DATES = "dismissed_dates"
    private const val KEY_SKIPPED_PREFIX = "skipped_dates_"
    private const val KEY_BYPASS_DATES = "bypass_dates"

    // Written only by builds that have [Bypass], next to KEY_FIRED_DATE. A
    // ring fired by an older build (11-22: paused, never dismissed) must not
    // read as a killed ring the first time the new build launches.
    private const val KEY_WATCHED_FIRED_DATE = "watched_fired_date"

    fun markFired(context: Context) {
        prefs(context).edit()
            .putString(KEY_FIRED_DATE, today())
            .putString(KEY_WATCHED_FIRED_DATE, today())
            .apply()
    }

    fun markDismissed(context: Context) {
        prefs(context).edit().putString(KEY_DISMISSED_DATE, today()).apply()
        DateHistory.add(prefs(context), KEY_DISMISSED_DATES, LocalDate.now())
    }

    /**
     * Latches that today's ring stood down for [skip]; called from
     * [AlarmReceiver]. The stick reads it back via [skippedOn], so clearing
     * the mark later that day cannot make the silenced day a miss.
     */
    fun markSkipped(context: Context, skip: RingSkip) {
        DateHistory.add(prefs(context), KEY_SKIPPED_PREFIX + skip.wire, LocalDate.now())
    }

    /** Whether today's fresh ring fired under a build with [Bypass]; [Bypass] asks it. */
    fun firedToday(context: Context): Boolean =
        prefs(context).getString(KEY_WATCHED_FIRED_DATE, null) == today()

    /** Latches a bypass ([Bypass]) on [day]; the stick reads it as a miss. */
    fun markBypass(context: Context, day: LocalDate) {
        DateHistory.add(prefs(context), KEY_BYPASS_DATES, day)
    }

    /** Whether a bypass was recorded on [day]. */
    fun bypassOn(context: Context, day: LocalDate): Boolean =
        DateHistory.contains(prefs(context), KEY_BYPASS_DATES, day)

    /** Why the ring stood down on [day], or null when it was not skipped. */
    fun skippedOn(context: Context, day: LocalDate): RingSkip? =
        RingSkip.entries.firstOrNull {
            DateHistory.contains(prefs(context), KEY_SKIPPED_PREFIX + it.wire, day)
        }

    /**
     * Whether the dismiss gate completed on [day]; read by [StickRunner],
     * which judges past days too. The single [KEY_DISMISSED_DATE] predates
     * the history and still answers for its one day.
     */
    fun dismissedOn(context: Context, day: LocalDate): Boolean =
        DateHistory.contains(prefs(context), KEY_DISMISSED_DATES, day) ||
            prefs(context).getString(KEY_DISMISSED_DATE, null) == day.toString()

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun today(): String =
        SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Calendar.getInstance().time)
}
