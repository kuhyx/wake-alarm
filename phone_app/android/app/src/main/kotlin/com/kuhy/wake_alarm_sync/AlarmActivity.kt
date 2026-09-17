package com.kuhy.wake_alarm_sync

import android.app.KeyguardManager
import android.content.Context
import android.os.Bundle
import android.view.WindowManager
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

    /**
     * The ring by default; the session checklist only when asked for by
     * [SessionNotice.resumeIntent] (the launcher redirect or the ongoing
     * notification) AND nothing is sounding. A ring always wins: an intent
     * that opened the checklist over a live alarm would leave the sound
     * running with no dismiss sequence in front of it. Read once, at
     * creation -- a live `singleInstance` instance just comes forward on
     * whatever screen Dart is showing, which is the right thing.
     */
    override fun getInitialRoute(): String {
        if (AlarmService.running) return ringRoute
        return intent?.getStringExtra(SessionNotice.EXTRA_ROUTE) ?: ringRoute
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // showWhenLocked/turnScreenOn are also set as manifest attributes; the
        // programmatic calls cover the case where the activity is re-created
        // while the device is already locked.
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        super.onCreate(savedInstanceState)
        // The morning session lives in this activity for half an hour after
        // the ring stops. With the screen allowed to sleep the activity
        // pauses and NFC stops polling, so a tag tap would need a wake and
        // an unlock first, every leg.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        dismissKeyguard()
    }

    /**
     * Asks the system to take the keyguard down for the ring screen.
     *
     * Load-bearing for the NFC room proof, not cosmetic. Showing *over* the
     * keyguard leaves the device locked, and NFC reports `mScreenState=
     * ON_LOCKED` in that state: the controller stops polling for tags even
     * though `enableReaderMode` was accepted (measured on the Pixel 6a — the
     * same tag that registered fine while unlocked was never discovered while
     * the ring screen was up). Without this the only satisfiable proof at
     * 06:00 is steps, which is exactly the single-mechanism dependency the
     * room-proof redundancy exists to avoid.
     *
     * On a secured device this surfaces the PIN/biometric prompt, which is an
     * acceptable trade for an alarm the user must get up for.
     */
    private fun dismissKeyguard() {
        val keyguard = getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        if (!keyguard.isKeyguardLocked) return
        keyguard.requestDismissKeyguard(
            this,
            object : KeyguardManager.KeyguardDismissCallback() {
                override fun onDismissSucceeded() {
                    // NFC only starts polling once the screen state leaves
                    // ON_LOCKED, so reader mode has to be re-asserted after
                    // the unlock rather than only in onResume.
                    alarmChannel?.let { NfcReader.start(this@AlarmActivity, it) }
                }
            },
        )
    }

    /** Kept so NFC reader mode can push tag ids back to the ring screen. */
    private var alarmChannel: MethodChannel? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        AlarmChannel.register(this, flutterEngine)
        val channel = channel(flutterEngine)
        alarmChannel = channel
        // AlarmChannel deliberately holds applicationContext, so it cannot
        // finish an activity. Without this the dismiss screen stays up over
        // the lockscreen forever after a correct answer — back is disabled,
        // and the live instance would carry _inRoom=true and the solved
        // answer into the next ring.
        channel.setMethodCallHandler { call, result ->
            if (call.method == "closeRingScreen") {
                finishAndRemoveTask()
                result.success(null)
            } else {
                AlarmChannel.handleCall(applicationContext, call, result)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Reader mode only works while this activity is in the foreground, so
        // it is started here rather than at engine-configure time.
        //
        // Re-asserted on every resume, not just the first: anything that comes
        // up over the ring screen (the launcher activity, a system dialog)
        // pauses this one and takes reader mode down with it, and the tag tap
        // must keep working once the ring screen is back in front.
        alarmChannel?.let { NfcReader.start(this, it) }
        // The user can still lock the phone mid-session with the power
        // button. Coming back, the keyguard is up again and NFC is back in
        // ON_LOCKED -- the same dead state onCreate handles.
        dismissKeyguard()
    }

    override fun onPause() {
        // Deliberately does NOT disable reader mode. enableReaderMode is
        // per-activity but disableReaderMode is effectively global, so
        // stopping here killed polling for the ring screen whenever another
        // activity briefly came in front — measured on the Pixel, where the
        // NfcService log showed `flags: 271` immediately followed by
        // `flags: 0`. onDestroy is the right place: by then the ring really
        // is over.
        super.onPause()
    }

    override fun onDestroy() {
        NfcReader.stop(this)
        super.onDestroy()
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
