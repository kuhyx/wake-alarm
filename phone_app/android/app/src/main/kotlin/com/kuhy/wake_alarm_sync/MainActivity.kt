package com.kuhy.wake_alarm_sync

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * The normal app entry point (the time picker).
 *
 * Registers the same alarm channel as [AlarmActivity] so the picker can arm,
 * cancel and re-arm without going through the ring screen.
 */
class MainActivity : FlutterActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestAlarmPermissions()
    }

    /**
     * Asks for the two runtime permissions the alarm cannot work without.
     *
     * POST_NOTIFICATIONS (API 33+): without the grant the app sits at
     * importance=NONE, the full-screen intent is rejected before it is even
     * considered, and the alarm rings with no dismiss screen. Measured on the
     * API 36 AVD, where a freshly installed app is blocked by default.
     *
     * ACTIVITY_RECOGNITION (API 29+): TYPE_STEP_COUNTER delivers nothing
     * without it, so the steps fallback would report "sensor unavailable"
     * forever. That matters because a room proof that can never be satisfied
     * makes the alarm undismissable, not merely degraded.
     */
    private fun requestAlarmPermissions() {
        val wanted = arrayOf(
            Manifest.permission.POST_NOTIFICATIONS,
            Manifest.permission.ACTIVITY_RECOGNITION,
        )
        val missing = wanted.filter {
            ContextCompat.checkSelfPermission(this, it) !=
                PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) return
        ActivityCompat.requestPermissions(
            this,
            missing.toTypedArray(),
            NOTIFICATION_REQUEST_CODE,
        )
    }

    /** Kept so NFC reader mode can push tag ids back to the Settings screen. */
    private var alarmChannel: MethodChannel? = null

    /** True while Settings is waiting for a tag to register. */
    private var registeringTag = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        AlarmChannel.register(this, flutterEngine)
        val channel = AlarmActivity.channel(flutterEngine)
        alarmChannel = channel
        // Registration needs an Activity for reader mode, which the shared
        // channel handler cannot supply — it holds applicationContext.
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "startTagRegistration" -> {
                    registeringTag = NfcReader.start(this, channel)
                    result.success(registeringTag)
                }
                // Finishes the picker after starting a test ring, so it
                // cannot sit on top of AlarmActivity — that pause used to
                // tear NFC reader mode down for the whole ring.
                "ringNow" -> {
                    AlarmChannel.handleCall(applicationContext, call, result)
                    // An unlocked, in-use device downgrades the full-screen
                    // intent to a heads-up notification (appops logs a
                    // rejectTime), so the ring screen would never appear on
                    // its own during a hardware test. Launch it directly and
                    // step out of the way: leaving the picker in front pauses
                    // AlarmActivity, which used to kill NFC reader mode.
                    startActivity(
                        Intent(this, AlarmActivity::class.java).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        },
                    )
                    finishAndRemoveTask()
                }
                "stopTagRegistration" -> {
                    registeringTag = false
                    NfcReader.stop(this)
                    result.success(null)
                }
                else -> AlarmChannel.handleCall(applicationContext, call, result)
            }
        }
    }

    override fun onPause() {
        if (registeringTag) NfcReader.stop(this)
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        if (registeringTag) alarmChannel?.let { NfcReader.start(this, it) }
    }

    private companion object {
        /** Request code for the notification permission prompt. */
        const val NOTIFICATION_REQUEST_CODE = 2001
    }
}
