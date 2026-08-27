package com.kuhy.wake_alarm_sync

import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * The dismiss screen, launched by the full-screen intent over the lockscreen.
 *
 * A separate FlutterActivity from [MainActivity] so the ring UI can never be
 * confused with the normal app task: it is launched with CLEAR_TASK and routes
 * straight to the Dart ring screen.
 */
class AlarmActivity : FlutterActivity() {

    /** Dart route the ring screen is registered under in main.dart. */
    private val ringRoute = "/ring"

    override fun getInitialRoute(): String = ringRoute

    override fun onCreate(savedInstanceState: Bundle?) {
        // showWhenLocked/turnScreenOn are also set as manifest attributes; the
        // programmatic calls cover the case where the activity is re-created
        // while the device is already locked.
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        super.onCreate(savedInstanceState)
    }

    /** Kept so NFC reader mode can push tag ids back to the ring screen. */
    private var alarmChannel: MethodChannel? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        AlarmChannel.register(this, flutterEngine)
        alarmChannel = channel(flutterEngine)
    }

    override fun onResume() {
        super.onResume()
        // Reader mode only works while this activity is in the foreground, so
        // it is started here rather than at engine-configure time.
        alarmChannel?.let { NfcReader.start(this, it) }
    }

    override fun onPause() {
        NfcReader.stop(this)
        super.onPause()
    }

    /**
     * Dismissing is the only way out: the ring screen owns the challenge, so
     * back must not silently drop the user onto the lockscreen with the alarm
     * still sounding.
     */
    @Suppress("MissingSuperCall")
    override fun onBackPressed() = Unit

    companion object {
        /** Channel name shared with [MainActivity]; one channel for the whole feature. */
        const val CHANNEL: String = "com.kuhy.wake_alarm_sync/alarm"

        /** Convenience for tests and callers that need the MethodChannel type. */
        fun channel(engine: FlutterEngine): MethodChannel =
            MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
    }
}
