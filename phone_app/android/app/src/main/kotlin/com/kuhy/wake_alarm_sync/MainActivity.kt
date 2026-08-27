package com.kuhy.wake_alarm_sync

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

/**
 * The normal app entry point (the time picker).
 *
 * Registers the same alarm channel as [AlarmActivity] so the picker can arm,
 * cancel and re-arm without going through the ring screen.
 */
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        AlarmChannel.register(this, flutterEngine)
    }
}
