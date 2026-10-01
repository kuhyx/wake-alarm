package com.kuhy.wake_alarm_sync

import android.content.Context
import android.util.Log
import java.time.LocalDate

/**
 * "That was a bug": excuses today's morning on the phone side.
 *
 * Marks today escaped (so no trigger can penalise it), clears the streak and
 * any lockdown, tells focus-owner to lift, and logs both. The PC side reads
 * the `escapes` field Dart publishes afterwards. Refused natively after
 * [Stakes.escapeHatchLastDay] as well -- hiding the button is not the only
 * guard.
 */
object EscapeHatch {
    private const val TAG = "WakeAlarmEscape"

    fun isOpen(today: LocalDate): Boolean = !today.isAfter(Stakes.escapeHatchLastDay)

    /** False when the hatch has closed; nothing is changed then. */
    @Synchronized
    fun use(context: Context): Boolean {
        val today = LocalDate.now()
        if (!isOpen(today)) {
            Log.w(TAG, "escape refused: the hatch closed after ${Stakes.escapeHatchLastDay}")
            return false
        }
        StickStore.markEscaped(context, today)
        EventLog.append(context, "escape_used", mapOf("date" to today.toString()))
        WorkdayStick.sendLift(context)
        EventLog.append(context, "lift_sent")
        return true
    }
}
