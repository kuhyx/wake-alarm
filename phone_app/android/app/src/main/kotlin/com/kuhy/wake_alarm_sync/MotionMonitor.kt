package com.kuhy.wake_alarm_sync

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.SystemClock
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * How long the phone has lain still, for the morning session.
 *
 * A phone that does not move for minutes after the alarm is a phone on the
 * nightstand next to someone who went back to bed. The accelerometer rather
 * than the step sensors: sitting down is not going back to sleep, and a
 * phone in a pocket keeps moving without a single step being taken.
 *
 * Hand-written on the existing channel, like [StepCounter]: nothing on the
 * ring path may depend on a pub plugin compiling. Only meaningful while the
 * session screen keeps the screen on -- an unregistered or suspended sensor
 * reports nothing, which the Dart side reads as "unknown", never as "still".
 */
object MotionMonitor {

    /** Change in acceleration magnitude (m/s²) between samples that counts as motion. */
    private const val THRESHOLD = 0.6f

    /** Sentinel for "not watching". */
    private const val NONE = -1L

    @Volatile
    private var lastMotionAt: Long = NONE

    private var lastMagnitude: Float = Float.NaN
    private var listener: SensorEventListener? = null

    /** Starts watching; the idle clock begins now, so a resume never inherits an old gap. */
    fun start(context: Context) {
        stop(context)
        val manager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor = manager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) ?: return
        lastMotionAt = SystemClock.elapsedRealtime()
        lastMagnitude = Float.NaN
        val l = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                val (x, y, z) = event.values
                val magnitude = sqrt(x * x + y * y + z * z)
                if (!lastMagnitude.isNaN() && abs(magnitude - lastMagnitude) > THRESHOLD) {
                    lastMotionAt = SystemClock.elapsedRealtime()
                }
                lastMagnitude = magnitude
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        manager.registerListener(l, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        listener = l
    }

    /** Milliseconds since the phone last moved, or -1 when not watching. */
    fun idleMillis(): Long {
        val since = lastMotionAt
        if (since == NONE || listener == null) return NONE
        return SystemClock.elapsedRealtime() - since
    }

    /** Stops watching and forgets the clock. */
    fun stop(context: Context) {
        val l = listener ?: return
        val manager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        manager.unregisterListener(l)
        listener = null
        lastMotionAt = NONE
    }
}
