package com.kuhy.wake_alarm_sync

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

/**
 * The phone's bounded event log: `{"at", "kind", "data"}`, newest first,
 * at most [MAX_ENTRIES] entries and [MAX_AGE_DAYS] days.
 *
 * Native, so the receivers that run with no Flutter engine (the alarm, the
 * stick check, boot) can write it; Dart appends to the same log over the
 * alarm channel and stages it as `phone_events` on every sync. This is the
 * evidence the daily incident report merges with the PC's -- a morning that
 * went wrong is reconstructed from here, not from memory.
 */
object EventLog {
    private const val TAG = "WakeAlarmEvents"
    private const val PREFS = "wake_alarm_events"
    private const val KEY_EVENTS = "events"
    const val MAX_ENTRIES = 400
    const val MAX_AGE_DAYS = 14L

    /** Seconds precision with an explicit offset, which `toString()` drops at :00. */
    private val FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssXXX")

    fun nowIso(): String = OffsetDateTime.now().format(FORMAT)

    /** Appends one event stamped now. Never throws: logging must not break a ring. */
    @Synchronized
    fun append(context: Context, kind: String, data: Map<String, Any?> = emptyMap()) {
        try {
            val entry = JSONObject()
                .put("at", nowIso())
                .put("kind", kind)
                .put("data", JSONObject(data.filterValues { it != null }))
            val kept = JSONArray().put(entry)
            val cutoff = OffsetDateTime.now().minusDays(MAX_AGE_DAYS)
            val old = read(context)
            for (i in 0 until old.length()) {
                if (kept.length() >= MAX_ENTRIES) break
                val event = old.optJSONObject(i) ?: continue
                if (isAfter(event.optString("at"), cutoff)) kept.put(event)
            }
            prefs(context).edit().putString(KEY_EVENTS, kept.toString()).commit()
        } catch (e: JSONException) {
            Log.w(TAG, "event $kind not logged", e)
        }
    }

    /** The whole log as a JSON array string, newest first. */
    @Synchronized
    fun readJson(context: Context): String = read(context).toString()

    private fun read(context: Context): JSONArray = try {
        JSONArray(prefs(context).getString(KEY_EVENTS, "[]") ?: "[]")
    } catch (e: JSONException) {
        // A corrupt log is replaced, not fatal: losing history beats losing
        // every event from here on.
        Log.w(TAG, "event log unreadable; starting over", e)
        JSONArray()
    }

    private fun isAfter(at: String, cutoff: OffsetDateTime): Boolean = try {
        OffsetDateTime.parse(at).isAfter(cutoff)
    } catch (e: DateTimeParseException) {
        false
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
