package com.kuhy.wake_alarm_sync

import android.content.Context
import android.content.Intent
import android.util.Log
import java.time.DayOfWeek
import java.time.LocalDate

/**
 * Signals `focus-owner` (`~/src/phone-focus-mode`): lock distracting apps
 * through a date, or lift a lockdown now. Signalling only -- whether to lock
 * is [StickCheck]'s decision, run by [StickRunner].
 *
 * Tue/Wed/Thu is the same set `wake_alarm._constants.STICK_DAYS` uses on the
 * PC side for the debt-stacking half of this same stick: both go easy on
 * exactly these three days otherwise, which is why skipping one used to cost
 * nothing.
 */
object WorkdayStick {
    /** Tuesday/Wednesday/Thursday; mirrored by `test_workday_mirrors.py`. */
    val STICK_DAYS =
        setOf(DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY)

    private const val ACTION_LOCKDOWN = "com.kuhy.focus_owner.action.LOCKDOWN_UNTIL_EOD"
    private const val ACTION_LIFT = "com.kuhy.focus_owner.action.LIFT_LOCKDOWN"
    private const val EXTRA_UNTIL = "until"
    private const val PERMISSION_SIGNAL = "com.kuhy.focus_owner.permission.SIGNAL_LOCKDOWN"
    private const val FOCUS_OWNER_PACKAGE = "com.kuhy.focus_owner"

    private const val TAG = "WakeAlarmWorkdayStick"

    /** Locks down through [until], inclusive (`yyyy-MM-dd` on the wire). */
    fun sendLockdown(context: Context, until: LocalDate) {
        Log.i(TAG, "signalling focus-owner lockdown through $until")
        context.sendBroadcast(
            Intent(ACTION_LOCKDOWN)
                .setPackage(FOCUS_OWNER_PACKAGE)
                .putExtra(EXTRA_UNTIL, until.toString()),
            PERMISSION_SIGNAL,
        )
    }

    /** Clears any lockdown now (the escape hatch). */
    fun sendLift(context: Context) {
        Log.i(TAG, "signalling focus-owner lift")
        context.sendBroadcast(
            Intent(ACTION_LIFT).setPackage(FOCUS_OWNER_PACKAGE),
            PERMISSION_SIGNAL,
        )
    }
}
