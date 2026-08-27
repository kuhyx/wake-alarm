package com.kuhy.wake_alarm_sync

import android.content.Context
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * The single MethodChannel this feature exposes to Dart.
 *
 * One channel rather than a plugin: the stack is AGP 9 / Gradle 9.1 /
 * Kotlin 2.3.20, and a plugin that fails to compile breaks the build outright
 * instead of degrading. Everything the alarm needs is here.
 */
object AlarmChannel {

    /** Wires [engine]'s Dart side to the scheduler and the ring service. */
    fun register(context: Context, engine: FlutterEngine) {
        val app = context.applicationContext
        MethodChannel(engine.dartExecutor.binaryMessenger, AlarmActivity.CHANNEL)
            .setMethodCallHandler { call, result -> handle(app, call, result) }
    }

    private fun handle(context: Context, call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "schedule" -> schedule(context, call, result)
            "cancel" -> {
                AlarmScheduler.cancel(context)
                result.success(null)
            }
            // Called from the Dart init seam and after a dismiss: with no
            // change-stream in the store, these are the only re-arm hooks
            // besides BOOT_COMPLETED.
            "rearm" -> result.success(AlarmScheduler.rearmFromStorage(context))
            "canUseFullScreenIntent" ->
                result.success(AlarmScheduler.canUseFullScreenIntent(context))
            "dismiss" -> {
                AlarmService.stop(context)
                // Re-arm immediately so the alarm rings again tomorrow.
                AlarmScheduler.rearmFromStorage(context)
                result.success(null)
            }
            // Fires the ring immediately, so the foreground-service and
            // full-screen-intent path can be exercised on an emulator without
            // waiting for a real alarm instant. Reachable only over this app's
            // own channel; it arms nothing and changes no stored time.
            "ringNow" -> {
                AlarmService.start(context)
                result.success(null)
            }
            "hasNfc" -> result.success(NfcReader.isAvailable(context))
            "stepCount" -> result.success(StepCounter.stepsSinceRingStart(context))
            "beginStepCount" -> {
                StepCounter.markRingStart(context)
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    private fun schedule(context: Context, call: MethodCall, result: MethodChannel.Result) {
        val hour = call.argument<Int>("hour")
        val minute = call.argument<Int>("minute")
        if (hour == null || minute == null) {
            result.error("bad_args", "hour and minute are required", null)
            return
        }
        AlarmScheduler.schedule(context, hour, minute)
        result.success(null)
    }
}
