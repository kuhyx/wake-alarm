package com.kuhy.wake_alarm_sync

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

/**
 * The normal app entry point (the time picker).
 *
 * Registers the same alarm channel as [AlarmActivity] so the picker can arm,
 * cancel and re-arm without going through the ring screen.
 */
class MainActivity : FlutterActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermission()
    }

    /**
     * Asks for POST_NOTIFICATIONS, which is a runtime permission from API 33.
     *
     * Without the grant the app sits at importance=NONE, the full-screen
     * intent is rejected before it is considered, and the alarm rings with no
     * dismiss screen. Measured on the API 36 AVD, where a freshly installed
     * app is blocked by default.
     */
    private fun requestNotificationPermission() {
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) return
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            NOTIFICATION_REQUEST_CODE,
        )
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        AlarmChannel.register(this, flutterEngine)
    }

    private companion object {
        /** Request code for the notification permission prompt. */
        const val NOTIFICATION_REQUEST_CODE = 2001
    }
}
