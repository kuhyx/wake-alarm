package com.kuhy.wake_alarm_sync

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager

/**
 * Steps taken since the alarm started ringing.
 *
 * Hand-written on the existing MethodChannel rather than a pub plugin, for the
 * same reason the ring path is: no plugin can break the build.
 *
 * TYPE_STEP_COUNTER reports steps since boot, so "since ring start" is the
 * difference against a baseline captured when the alarm fires. Steps are the
 * *fallback* room proof only — the phone is stationary while you walk to it, so
 * steps alone can be faked by shaking it in bed. NFC or QR is the real proof.
 */
object StepCounter {

    private const val PREFS = "wake_alarm_steps"
    private const val KEY_BASELINE = "baseline"

    /** Sentinel for "no baseline captured yet". */
    private const val NONE = -1L

    /** Most recent step total seen, kept so reads never block the caller. */
    @Volatile
    private var latest: Long? = null

    /** The single registered listener; kept so rings do not accumulate them. */
    private var listener: SensorEventListener? = null

    /**
     * Starts listening and records the first reading as this ring's baseline.
     *
     * Registration is fire-and-forget: the sensor callback arrives on its own
     * thread, so nothing here blocks the MethodChannel — this runs on the
     * platform main thread, where a multi-second wait is an ANR.
     */
    fun markRingStart(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.edit().remove(KEY_BASELINE).apply()
        listen(context) { total ->
            // Only the first sample after a ring starts becomes the baseline.
            if (!prefs.contains(KEY_BASELINE)) {
                prefs.edit().putLong(KEY_BASELINE, total).apply()
            }
        }
    }

    /**
     * Steps since [markRingStart], or -1 when unavailable.
     *
     * -1 (rather than 0) so the Dart side can tell "no step sensor / no
     * baseline" apart from "hasn't moved yet" and fall back to another proof.
     */
    fun stepsSinceRingStart(context: Context): Long {
        val baseline = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getLong(KEY_BASELINE, NONE)
        if (baseline == NONE) return NONE
        // Non-blocking: whatever the listener last delivered. Returns -1 until
        // the first sample arrives rather than stalling the ring screen.
        val current = latest ?: return NONE
        return (current - baseline).coerceAtLeast(0)
    }

    /**
     * Registers a step listener, keeping [latest] fresh for later reads.
     *
     * The listener is deliberately never unregistered while the alarm rings:
     * the ring screen polls repeatedly, and re-registering per read would cost
     * a fresh sensor warm-up each time.
     */
    @Synchronized
    private fun listen(context: Context, onFirst: (Long) -> Unit) {
        val manager =
            context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager ?: return
        val sensor = manager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER) ?: return
        // One registration per process: markRingStart runs on every ring, and
        // an unregistered listener per ring would accumulate for the lifetime
        // of the app.
        listener?.let { manager.unregisterListener(it) }
        val fresh = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                val total = event.values.firstOrNull()?.toLong() ?: return
                latest = total
                onFirst(total)
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        listener = fresh
        manager.registerListener(fresh, sensor, SensorManager.SENSOR_DELAY_NORMAL)
    }
}
