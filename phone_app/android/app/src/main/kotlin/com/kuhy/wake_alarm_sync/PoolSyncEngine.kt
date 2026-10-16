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
 * A headless Flutter engine running `poolSyncMain` (`lib/main.dart` ->
 * `day_pool_refresh.dart`): pulls the free- and sick-day pools and rewrites
 * [FreeDays] and [SickDays] through [AlarmChannel] -- the same Dart sync the
 * screens use, so the RTDB wire format has one implementation on the phone.
 *
 * Same shape as [HeadlessRingStart]. Dart says `done` on [CHANNEL];
 * [TIMEOUT_MS] destroys the engine regardless. That bound sits well inside
 * the 60 s a background broadcast may stay open, since [PoolSyncReceiver]
 * holds one for exactly this long. Never throws.
 */
object PoolSyncEngine {
    private const val TAG = "WakeAlarmPoolSync"
    const val CHANNEL = "com.kuhy.wake_alarm_sync/poolsync"
    private const val ENTRYPOINT = "poolSyncMain"
    private const val TIMEOUT_MS = 25_000L

    private val handler = Handler(Looper.getMainLooper())
    private var engine: FlutterEngine? = null
    private var onFinished: (() -> Unit)? = null
    private val timeout = Runnable { stop("timeout") }

    /** Runs one sync, then calls [finished]. Main thread only. */
    fun run(context: Context, finished: () -> Unit) {
        if (engine != null) {
            // One sync at a time; the running one covers this slot too.
            finished()
            return
        }
        onFinished = finished
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
            handler.postDelayed(timeout, TIMEOUT_MS)
            Log.i(TAG, "pool sync engine started")
        } catch (e: RuntimeException) {
            Log.w(TAG, "pool sync engine failed; the caches keep their last sync", e)
            stop("failed")
        }
    }

    private fun stop(reason: String) {
        handler.removeCallbacks(timeout)
        engine?.destroy()
        engine = null
        Log.i(TAG, "pool sync engine stopped: $reason")
        onFinished?.invoke()
        onFinished = null
    }
}
