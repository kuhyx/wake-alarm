package com.kuhy.wake_alarm_sync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Re-arms the stored alarm after a reboot.
 *
 * AlarmManager drops every alarm across a reboot, so without this the phone
 * silently stops being an alarm clock until the user next edits the time.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        AlarmScheduler.rearmFromStorage(context)
    }
}
