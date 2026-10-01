package com.kuhy.wake_alarm_sync

import android.content.SharedPreferences
import java.time.LocalDate

/**
 * A bounded set of ISO dates in one SharedPreferences key: "on which days
 * did X happen". The stick's backlog judges days up to
 * [StickCheck.BACKLOG_DAYS] back, so a single "last date" is not enough --
 * a dismiss on Tuesday would be forgotten by Wednesday's.
 */
object DateHistory {
    /** Kept comfortably longer than the backlog. */
    private const val KEEP_DAYS = 14L

    /** Adds [day] and drops entries older than [KEEP_DAYS]; `commit()`s. */
    fun add(prefs: SharedPreferences, key: String, day: LocalDate) {
        val floor = day.minusDays(KEEP_DAYS)
        val kept = read(prefs, key).filter { iso ->
            runCatching { !LocalDate.parse(iso).isBefore(floor) }.getOrDefault(false)
        }.toSet() + day.toString()
        prefs.edit().putStringSet(key, kept).commit()
    }

    fun contains(prefs: SharedPreferences, key: String, day: LocalDate): Boolean =
        day.toString() in read(prefs, key)

    // A copy: the set SharedPreferences returns must not be modified.
    private fun read(prefs: SharedPreferences, key: String): Set<String> =
        prefs.getStringSet(key, emptySet())?.toSet() ?: emptySet()
}
