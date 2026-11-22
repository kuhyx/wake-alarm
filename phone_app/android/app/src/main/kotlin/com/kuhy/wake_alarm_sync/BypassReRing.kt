package com.kuhy.wake_alarm_sync

import android.content.Context
import java.time.LocalDate

/**
 * The cause of a bypass that restarted the ring during a live morning
 * session, handed to Dart once (`takeBypassReRing`) so the session records
 * that re-ring as `bypass:<cause>` rather than the leg's deadline.
 *
 * Dated, so a session that ends without a dismiss cannot leak it into
 * tomorrow's first re-ring.
 */
object BypassReRing {
    private const val PREFS = "wake_alarm_bypass_rering"
    private const val KEY = "stamp"

    fun stamp(context: Context, cause: String, date: String) {
        prefs(context).edit().putString(KEY, BypassRules.encodeStamp(cause, date)).commit()
    }

    fun take(context: Context): String? {
        val stored = prefs(context).getString(KEY, null) ?: return null
        prefs(context).edit().remove(KEY).commit()
        return BypassRules.takeStamp(stored, LocalDate.now().toString())
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
