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

    /** Most recent cumulative total seen, kept so reads never block. */
    @Volatile
    private var latest: Long? = null

    /**
     * Steps counted by TYPE_STEP_DETECTOR since [markRingStart].
     *
     * The detector fires once per step, so it needs no baseline and reports
     * the very first stride. The counter (TYPE_STEP_COUNTER) is on-change and
     * cumulative, so on its own it delivers nothing until the user has
     * already walked — which is why a phone sitting still reported a step
     * sensor that "does not work". The detector is now primary and the
     * counter is the cross-check.
     */
    @Volatile
    private var detected: Long = 0

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
        detected = 0
        listen(context) { total ->
            // Only the first sample after a ring starts becomes the baseline.
            if (!prefs.contains(KEY_BASELINE)) {
                prefs.edit().putLong(KEY_BASELINE, total).apply()
            }
        }
        // TYPE_STEP_COUNTER is an on-change sensor: it reports only when the
        // user actually steps, so registering alone can leave us with no
        // sample for minutes. requestTriggerSensor is not available for it,
        // but SENSOR_DELAY_FASTEST plus an immediate flush() asks the
        // hardware FIFO to deliver the current cumulative total now, which is
        // what makes the baseline correct from the first tap rather than
        // silently swallowing the user's first strides.
        flush(context)
    }

    /** Asks the sensor FIFO to deliver any batched sample immediately. */
    private fun flush(context: Context) {
        val manager =
            context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager ?: return
        listener?.let { manager.flush(it) }
    }

    /**
     * Steps since [markRingStart], or -1 when unavailable.
     *
     * -1 (rather than 0) so the Dart side can tell "no step sensor / no
     * baseline" apart from "hasn't moved yet" and fall back to another proof.
     */
    fun stepsSinceRingStart(context: Context): Long {
        // The detector is authoritative: it counts every stride since the ring
        // started, with no baseline to miss. Only fall back to the cumulative
        // counter when there is no detector on the device.
        if (hasDetector) return detected
        val baseline = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getLong(KEY_BASELINE, NONE)
        if (baseline == NONE) return NONE
        val current = latest ?: return NONE
        return (current - baseline).coerceAtLeast(0)
    }

    /** Whether this device exposes TYPE_STEP_DETECTOR, set when listening starts. */
    @Volatile
    private var hasDetector: Boolean = false

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
        val counter = manager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)
        val detector = manager.getDefaultSensor(Sensor.TYPE_STEP_DETECTOR)
        if (counter == null && detector == null) return
        // One registration per process: markRingStart runs on every ring, and
        // an unregistered listener per ring would accumulate for the lifetime
        // of the app.
        listener?.let { manager.unregisterListener(it) }
        val fresh = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                when (event.sensor.type) {
                    // Fires once per stride; each event is exactly one step.
                    Sensor.TYPE_STEP_DETECTOR -> detected++
                    Sensor.TYPE_STEP_COUNTER -> {
                        val total = event.values.firstOrNull()?.toLong() ?: return
                        latest = total
                        onFirst(total)
                    }
                    else -> Unit
                }
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        listener = fresh
        hasDetector = detector != null
        // FASTEST so the first stride registers immediately; these sensors are
        // low-rate by nature, so this costs nothing meaningful.
        detector?.let { manager.registerListener(fresh, it, SensorManager.SENSOR_DELAY_FASTEST) }
        counter?.let { manager.registerListener(fresh, it, SensorManager.SENSOR_DELAY_FASTEST) }
    }
}
