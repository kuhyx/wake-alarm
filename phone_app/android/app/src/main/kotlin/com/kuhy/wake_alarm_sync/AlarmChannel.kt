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
            .setMethodCallHandler { call, result -> handleCall(app, call, result) }
    }

    fun handleCall(context: Context, call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "schedule" -> schedule(context, call, result)
            // No "cancel": the alarm cannot be switched off. Removing the
            // handler (rather than just the Dart wrapper) is what makes that
            // real — otherwise the capability is one invokeMethod away.
            // Called from the Dart init seam and after a dismiss: with no
            // change-stream in the store, these are the only re-arm hooks
            // besides BOOT_COMPLETED.
            "rearm" -> result.success(AlarmScheduler.rearmFromStorage(context))
            // Arms the fixed schedule and (re)starts the daily check. Called
            // from the Dart init seam on every launch, so the alarm is armed
            // by opening the app at all rather than by tapping anything.
            "armSchedule" -> {
                val hour = call.argument<Int>("hour")
                val minute = call.argument<Int>("minute")
                if (hour == null || minute == null) {
                    result.error("bad_args", "hour and minute are required", null)
                } else {
                    AlarmScheduler.schedule(context, hour, minute)
                    AlarmWatchdog.schedule(context)
                    result.success(null)
                }
            }
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
            // The Dart pool's free dates, cached where AlarmReceiver can
            // read them with no engine running. Dart calls this after every
            // mark, release and sync; see FreeDays.kt.
            "setFreeDays" -> {
                val dates = call.argument<List<String>>("dates")
                if (dates == null) {
                    result.error("bad_args", "dates is required", null)
                } else {
                    FreeDays.store(context, dates)
                    result.success(null)
                }
            }
            "hasNfc" -> result.success(NfcReader.isAvailable(context))
            // Raw observations only; home_presence.dart decides what they mean.
            // Lives here rather than in MainActivity's override (as NfcReader
            // does) because WifiManager/LocationManager need no Activity, and
            // the ring screen must be able to reach it through AlarmActivity.
            "readPresence" -> HomePresence.read(
                context,
                call.argument<Double>("homeLat"),
                call.argument<Double>("homeLon"),
                call.argument<Boolean>("withFix") ?: false,
            ) { observations -> result.success(observations) }
            // Handled by AlarmActivity, which owns the window; reaching here
            // means the picker asked, where there is no ring screen to close.
            "closeRingScreen" -> result.success(null)
            "stepCount" -> result.success(StepCounter.stepsSinceRingStart(context))
            // The morning session's one live deadline, as an absolute epoch
            // instant; null drops it (a leg with its re-ring spent must not
            // inherit the previous leg's alarm). Dart ints cross the channel
            // as Int when they fit and Long when they do not; an epoch in
            // millis never fits.
            "armReRing" -> {
                val at = call.argument<Number>("atMillis")?.toLong()
                if (at == null) {
                    AlarmScheduler.clearReRing(context)
                } else {
                    AlarmScheduler.scheduleReRing(context, at)
                }
                result.success(null)
            }
            // The session's finish path, and the only thing that drops a
            // pending re-ring. Not named "cancel" and not reachable from any
            // screen but the session's own: the wake alarm itself still has
            // no off switch.
            "finishSession" -> {
                AlarmScheduler.clearReRing(context)
                SessionNotice.clear(context)
                result.success(null)
            }
            // The live leg, for the launcher redirect and the ongoing
            // notification; see SessionNotice.kt. Called on every leg
            // change, never per tick.
            "updateSessionNotice" -> {
                val date = call.argument<String>("date")
                val label = call.argument<String>("label")
                if (date == null || label == null) {
                    result.error("bad_args", "date and label are required", null)
                } else {
                    val at = call.argument<Number>("deadlineMillis")?.toLong()
                    SessionNotice.update(context, date, label, at)
                    result.success(null)
                }
            }
            // Whether a launch right now would be redirected into the
            // morning; the probes ask before starting a test ring.
            "morningLive" ->
                result.success(AlarmService.running || SessionNotice.isLiveToday(context))
            // Whether the ring is sounding; the session screen polls this so
            // a deadline that rang while it sat in the background puts the
            // dismiss sequence in front the moment it is looked at.
            "isRinging" -> result.success(AlarmService.running)
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
