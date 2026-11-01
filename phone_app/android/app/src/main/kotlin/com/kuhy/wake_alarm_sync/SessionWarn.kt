package com.kuhy.wake_alarm_sync

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.os.Build
import android.os.VibrationAttributes
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log

/**
 * A silent buzz [LEAD_MS] before each morning-session deadline.
 *
 * Armed and cleared only alongside the re-ring in [AlarmScheduler], so it
 * cannot outlive or drift from the deadline it warns about.
 */
object SessionWarn {
    private const val TAG = "WakeAlarmSession"

    /** Distinct from 1001 (daily) and 1003 (re-ring): PendingIntents key on it. */
    private const val REQUEST_CODE = 1004

    const val LEAD_MS = 3 * 60_000L

    private val PATTERN = longArrayOf(0, 400, 200, 400, 200, 400)

    /** The buzz instant, or null once it has passed (BOOT_COMPLETED replays). */
    fun warnAt(deadlineMs: Long, nowMs: Long): Long? =
        (deadlineMs - LEAD_MS).takeIf { it > nowMs }

    fun arm(context: Context, deadlineMs: Long) {
        val at = warnAt(deadlineMs, System.currentTimeMillis())
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        if (at == null) {
            manager.cancel(pendingIntent(context))
            return
        }
        manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent(context))
    }

    fun clear(context: Context) {
        val manager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(pendingIntent(context))
    }

    internal fun buzz(context: Context) {
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager)
                ?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        } ?: return
        val effect = VibrationEffect.createWaveform(PATTERN, -1)
        // Alarm usage, so Do Not Disturb and a backgrounded app still buzz.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            vibrator.vibrate(effect, VibrationAttributes.createForUsage(VibrationAttributes.USAGE_ALARM))
        } else {
            val audio = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
            @Suppress("DEPRECATION")
            vibrator.vibrate(effect, audio)
        }
        Log.i(TAG, "deadline warning buzzed")
    }

    private fun pendingIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context,
        REQUEST_CODE,
        Intent(context, SessionWarnReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
}

/** Buzzes only while today's session is live; a stale alarm stays silent. */
class SessionWarnReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!SessionNotice.isLiveToday(context) || AlarmService.running) return
        SessionWarn.buzz(context)
    }
}
