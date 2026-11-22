package com.kuhy.wake_alarm_sync

import android.app.admin.DeviceAdminReceiver
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import java.time.LocalDate

/**
 * The app's own device admin. An active admin cannot be paused
 * ("Wstrzymaj aplikację"): Android refuses to suspend it. Deactivating it is
 * possible in Settings and no one can stop that, so it is a bypass instead.
 * Activated over adb (`dpm set-active-admin`), never by a tap.
 */
class WakeAdminReceiver : DeviceAdminReceiver() {
    override fun onDisabled(context: Context, intent: Intent) {
        Bypass.record(context, BypassCause.ADMIN_REMOVED)
    }
}

/**
 * `MY_PACKAGE_SUSPENDED` / `UNSUSPENDED`, sent by the system to this app
 * itself. Suspended: record the bypass and ask focus-owner to lift it.
 * Unsuspended: when today's bypass is live, ring again (the start may have
 * been refused while suspended).
 */
class SuspendReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_MY_PACKAGE_SUSPENDED -> {
                Log.w(TAG, "suspended")
                Bypass.record(context, BypassCause.SUSPENDED)
            }
            Intent.ACTION_MY_PACKAGE_UNSUSPENDED -> {
                Log.i(TAG, "unsuspended")
                EventLog.append(context, "unsuspended")
                if (RingWatch.bypassOn(context, LocalDate.now())) {
                    if (!AlarmService.running) Bypass.ringAgain(context)
                    // Again now the app runs normally: the push made while
                    // suspended may not have gone out.
                    HeadlessRingStart.start(context, HeadlessRingStart.PUBLISH_ENTRYPOINT)
                }
            }
        }
    }

    private companion object {
        const val TAG = "WakeAlarmSuspend"
    }
}
