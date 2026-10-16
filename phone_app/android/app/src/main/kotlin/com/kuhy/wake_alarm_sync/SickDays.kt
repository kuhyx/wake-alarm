package com.kuhy.wake_alarm_sync

import android.content.Context
import android.util.Log
import java.time.LocalDate

/**
 * The native copy of the shared sick-day pool (`~/src/utils/sickdays`): the
 * ISO dates on which the alarm must not ring and the stick stands down.
 *
 * Not every sick day: since sickdays 0.2.0 a sick day may *keep* some
 * lockers active, and Dart writes here only the days on which the `alarm`
 * locker stands down (sick, alarm not kept; `SickDayPool.standDownIsoDates`
 * in `sick_day_pool.dart`). A sick day that keeps the alarm is absent, so
 * it rings, judges the stick and shows its stakes like a normal day. Every
 * reader of this cache ([RingDecision], [StickCheck], the stakes card via
 * [EnforcementChannel]) therefore means "the alarm stands down", and none
 * of them needs to know the keep set exists.
 *
 * A separate cache from [FreeDays], with its own prefs file, because the
 * pools are separate things: a sick day is never called a free day, in a
 * log line or anywhere else. Dart rewrites it after every mark, clear and
 * sync (`sick_day_sync.dart`), including the pre-alarm sync
 * ([PoolSyncReceiver]) that brings a PC mark in with the app closed.
 *
 * Fail closed ([DayCache]): unreadable means "not a sick day", so the
 * alarm rings.
 */
object SickDays {

    private const val TAG = "WakeAlarmSickDays"
    private const val PREFS = "wake_alarm_sickdays"
    private const val KEY_DATES = "sick_dates"

    /** Replaces the cached set with [isoDates] (`yyyy-MM-dd` each). */
    fun store(context: Context, isoDates: List<String>) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putStringSet(KEY_DATES, isoDates.toSet())
            .apply()
        Log.i(TAG, "native cache stored: ${isoDates.sorted()}")
    }

    /**
     * The cached dates, sorted, for the picker's read-back line (the only
     * way to see this cache on a release build); null when unreadable,
     * which the ring path treats as "not a sick day".
     */
    fun dates(context: Context): List<String>? {
        val dates = try {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getStringSet(KEY_DATES, emptySet())?.sorted()
        } catch (e: RuntimeException) {
            Log.w(TAG, "sick-day cache unreadable", e)
            null
        }
        Log.i(TAG, "native cache read: $dates")
        return dates
    }

    /** Whether today (local calendar day) is in the cached set. */
    fun isToday(context: Context): Boolean = isSick(context, LocalDate.now())

    /** Whether [day] is in the cached set; past sick days stay in it. */
    fun isSick(context: Context, day: LocalDate): Boolean = DayCache.contains(
        day,
        onError = { Log.w(TAG, "sick-day cache unreadable; ringing as normal", it) },
    ) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getStringSet(KEY_DATES, emptySet())
    }
}
