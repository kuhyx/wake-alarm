package com.kuhy.wake_alarm_sync

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import io.flutter.FlutterInjector
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.dart.DartExecutor
import io.flutter.plugin.common.MethodChannel

/**
 * Publishes `ring_started` the moment the daily alarm fires, with no screen.
 *
 * The ring screen used to be the only source, and it does not always open:
 * on an unlocked phone in use the full-screen intent is downgraded to a
 * heads-up notification. Then no `ring_started` reached the PC, which rang
 * `phone_silent` at a user who was awake and holding the phone. So the
 * alarm itself starts a headless Flutter engine running `ringStartedMain`
 * (`lib/main.dart` → `headless_ring_start.dart`), which records and pushes
 * through the same `RingStartRecorder` as the screen. The first ring of the
 * day wins; the screen's later publish is skipped once this one landed.
 *
 * The engine lives while [AlarmService] holds the process in the
 * foreground. Dart says `done` on [CHANNEL]; [TIMEOUT_MS] destroys it
 * regardless, so a hung network call cannot keep a second engine forever.
 * Never throws: a failure here must never touch the ring.
 */
object HeadlessRingStart {
    private const val TAG = "WakeAlarmHeadless"
    const val CHANNEL = "com.kuhy.wake_alarm_sync/headless"
    private const val ENTRYPOINT = "ringStartedMain"
    private const val TIMEOUT_MS = 90_000L

    private val handler = Handler(Looper.getMainLooper())
    private var engine: FlutterEngine? = null

    /** Starts the engine unless one is already running. Main thread only. */
    fun start(context: Context) {
        if (engine != null) return
        try {
            val app = context.applicationContext
            val created = FlutterEngine(app)
            engine = created
            AlarmChannel.register(app, created)
            MethodChannel(created.dartExecutor.binaryMessenger, CHANNEL)
                .setMethodCallHandler { call, result ->
                    result.success(null)
                    // Posted: destroying an engine inside its own callback
                    // would tear the messenger down under the reply.
                    if (call.method == "done") handler.post { stop("done") }
                }
            val bundle = FlutterInjector.instance().flutterLoader().findAppBundlePath()
            created.dartExecutor.executeDartEntrypoint(
                DartExecutor.DartEntrypoint(bundle, ENTRYPOINT),
            )
            handler.postDelayed({ stop("timeout") }, TIMEOUT_MS)
            Log.i(TAG, "headless ring_started engine started")
        } catch (e: RuntimeException) {
            Log.w(TAG, "headless engine failed; the ring screen still publishes", e)
            stop("failed")
        }
    }

    private fun stop(reason: String) {
        handler.removeCallbacksAndMessages(null)
        engine?.destroy()
        engine = null
        Log.i(TAG, "headless engine stopped: $reason")
    }
}
