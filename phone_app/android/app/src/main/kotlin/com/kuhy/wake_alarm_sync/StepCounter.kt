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

    /** How long to wait for the sensor's first reading before giving up. */
    private const val READ_TIMEOUT_MS = 3000L

    /** Records the current step total as the baseline for this ring. */
    fun markRingStart(context: Context) {
        val current = readTotal(context) ?: return
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putLong(KEY_BASELINE, current).apply()
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
        val current = readTotal(context) ?: return NONE
        return (current - baseline).coerceAtLeast(0)
    }

    /** Blocks briefly for one TYPE_STEP_COUNTER sample; null when there is no sensor. */
    private fun readTotal(context: Context): Long? {
        val manager =
            context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager ?: return null
        val sensor = manager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER) ?: return null
        val lock = Object()
        var value: Long? = null
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                synchronized(lock) {
                    value = event.values.firstOrNull()?.toLong()
                    lock.notifyAll()
                }
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        manager.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_FASTEST)
        synchronized(lock) {
            if (value == null) lock.wait(READ_TIMEOUT_MS)
        }
        manager.unregisterListener(listener)
        return value
    }
}
