package com.kuhy.wake_alarm_sync

import android.content.Context
import android.content.Intent
import android.util.Log
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * Signals `focus-owner` to lock down distracting apps when a
 * Tuesday/Wednesday/Thursday ring was abandoned -- see [RingWatch].
 *
 * Tue/Wed/Thu is the same set `wake_alarm._constants.STICK_DAYS` uses on the
 * PC side for the debt-stacking half of this same stick: both go easy on
 * exactly these three days otherwise, which is why skipping one used to cost
 * nothing.
 */
object WorkdayStick {
    /** [Calendar.DAY_OF_WEEK] values for Tuesday/Wednesday/Thursday. */
    private val STICK_DAYS =
        setOf(Calendar.TUESDAY, Calendar.WEDNESDAY, Calendar.THURSDAY)

    private const val ACTION_LOCKDOWN = "com.kuhy.focus_owner.action.LOCKDOWN_UNTIL_EOD"
    private const val PERMISSION_SIGNAL = "com.kuhy.focus_owner.permission.SIGNAL_LOCKDOWN"
    private const val FOCUS_OWNER_PACKAGE = "com.kuhy.focus_owner"

    private const val TAG = "WakeAlarmWorkdayStick"

    /** Checks for an abandoned stick-day ring and signals focus-owner. */
    fun checkAndSignal(context: Context) {
        val abandoned = RingWatch.abandonedRingDate(context) ?: return
        if (!isStickDay(abandoned)) return
        Log.i(TAG, "abandoned ring on $abandoned: signalling focus-owner lockdown")
        context.sendBroadcast(
            Intent(ACTION_LOCKDOWN).setPackage(FOCUS_OWNER_PACKAGE),
            PERMISSION_SIGNAL,
        )
    }

    private fun isStickDay(isoDate: String): Boolean {
        val format = SimpleDateFormat("yyyy-MM-dd", Locale.US)
        val parsed = runCatching { format.parse(isoDate) }.getOrNull() ?: return false
        val calendar = Calendar.getInstance()
        calendar.time = parsed
        return calendar.get(Calendar.DAY_OF_WEEK) in STICK_DAYS
    }
}
