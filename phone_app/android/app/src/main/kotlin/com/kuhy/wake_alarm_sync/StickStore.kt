package com.kuhy.wake_alarm_sync

import android.content.Context
import java.time.LocalDate

/**
 * Persists the stick ([StickState]) and the day an escape was used.
 *
 * Every write is `commit()`, not `apply()`: these run inside broadcast
 * receivers (the exact check, BOOT_COMPLETED) whose process may be gone a
 * moment later, and a miss recorded only in memory would be penalised again
 * by the next trigger. [updatedAt] stamps the last change so the synced
 * `stick_state` field is re-pushed only when something actually moved.
 */
object StickStore {
    private const val PREFS = "wake_alarm_stick"
    private const val KEY_STREAK = "streak"
    private const val KEY_LOCKED_THROUGH = "locked_through"
    private const val KEY_LAST_MISS = "last_miss"
    private const val KEY_ESCAPED_DATES = "escaped_dates"
    private const val KEY_CHECKED_THROUGH = "checked_through"
    private const val KEY_UPDATED_AT = "updated_at"

    fun load(context: Context): StickState {
        val prefs = prefs(context)
        return StickState(
            streak = prefs.getInt(KEY_STREAK, 0),
            lockedThrough = parse(prefs.getString(KEY_LOCKED_THROUGH, null)),
            lastMiss = parse(prefs.getString(KEY_LAST_MISS, null)),
        )
    }

    fun save(context: Context, state: StickState) {
        prefs(context).edit()
            .putInt(KEY_STREAK, state.streak)
            .putString(KEY_LOCKED_THROUGH, state.lockedThrough?.toString())
            .putString(KEY_LAST_MISS, state.lastMiss?.toString())
            .putString(KEY_UPDATED_AT, EventLog.nowIso())
            .commit()
    }

    /** Records an escape for [day]: the streak and any lockdown are gone. */
    fun markEscaped(context: Context, day: LocalDate) {
        save(context, load(context).copy(streak = 0, lockedThrough = null))
        DateHistory.add(prefs(context), KEY_ESCAPED_DATES, day)
    }

    fun escapedOn(context: Context, day: LocalDate): Boolean =
        DateHistory.contains(prefs(context), KEY_ESCAPED_DATES, day)

    /** The last day whose verdict was final; null before the first run. */
    fun checkedThrough(context: Context): LocalDate? =
        parse(prefs(context).getString(KEY_CHECKED_THROUGH, null))

    fun setCheckedThrough(context: Context, day: LocalDate) {
        prefs(context).edit().putString(KEY_CHECKED_THROUGH, day.toString()).commit()
    }

    /** ISO instant of the last change, or null before the first one. */
    fun updatedAt(context: Context): String? = prefs(context).getString(KEY_UPDATED_AT, null)

    private fun parse(iso: String?): LocalDate? =
        iso?.let { runCatching { LocalDate.parse(it) }.getOrNull() }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
