package com.kuhy.wake_alarm_sync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Re-arms the stored alarm after a reboot.
 *
 * AlarmManager drops every alarm across a reboot, so without this the phone
 * silently stops being an alarm clock until the user next edits the time.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val rearmed = AlarmScheduler.rearmFromStorage(context)
        // A reboot mid-session must not end the session silently: the live
        // leg's deadline is stored alongside the daily time. Not only after
        // a reboot, either -- see restoreReRing for the launch-time replay.
        val rering = AlarmScheduler.restoreReRing(context)
        Log.i(TAG, "boot: rearmed=$rearmed rering=$rering")
        // setInexactRepeating does not survive a reboot, so the daily check
        // has to be re-established here or it silently stops after the first
        // restart — exactly when a watchdog is most needed.
        AlarmWatchdog.schedule(context)
        // The moment a phone powered off mid-ring comes back is exactly when
        // an abandoned ring should be caught -- see WorkdayStick.
        WorkdayStick.checkAndSignal(context)
    }

    private companion object {
        const val TAG = "WakeAlarmBoot"
    }
}
