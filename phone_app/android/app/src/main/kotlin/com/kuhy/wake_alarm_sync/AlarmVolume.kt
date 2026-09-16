package com.kuhy.wake_alarm_sync

import android.content.Context
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Handler
import android.util.Log

/**
 * How loud the alarm is, and how it gets there.
 *
 * Split out of [AlarmService] for the repo's 250-line cap, along a real seam:
 * the service owns the ring's lifecycle, this owns its loudness.
 *
 * **Two knobs, deliberately not merged.** [raiseStream] fixes the *system
 * stream*, which must be at max or a stream someone left at zero silences the
 * alarm outright. [startRamp] shapes the *player's own gain* within it.
 * Collapsing them into one would trade a gentle start for a silent alarm.
 */
object AlarmVolume {

    private const val TAG = "AlarmVolume"

    /** Player gain the ring starts at: audible in a quiet room, not a jolt. */
    const val RAMP_START_GAIN = 0.04f

    /**
     * How long the climb from [RAMP_START_GAIN] to full takes.
     *
     * Ten minutes, up from one on 2026-09-16: a minute to full blast is a
     * jolt, not a wake-up, and with the dismiss walk taking a few minutes
     * the whole sequence was done at maximum volume.
     */
    private const val RAMP_DURATION_MS = 600_000L

    /** Gap between ramp steps; 300 steps over the full duration. */
    private const val RAMP_STEP_MS = 2_000L

    /**
     * An alarm stream turned down to zero must not silence the alarm.
     *
     * Guarded: setStreamVolume can throw under an active zen rule, and by the
     * time this runs startForeground() has already posted — an exception here
     * would take the whole ring down over a volume bump that is only an
     * improvement, not the mechanism.
     */
    fun raiseStream(context: Context) {
        try {
            val audio = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
            val max = audio.getStreamMaxVolume(AudioManager.STREAM_ALARM)
            audio.setStreamVolume(AudioManager.STREAM_ALARM, max, 0)
        } catch (e: SecurityException) {
            Log.w(TAG, "could not raise the alarm volume; ringing anyway", e)
        }
    }

    /**
     * Climbs the player gain from [RAMP_START_GAIN] to full over
     * [RAMP_DURATION_MS].
     *
     * Waking someone at full blast is not more effective, only harsher. The
     * climb is quadratic because perceived loudness is not linear in
     * amplitude: a linear ramp lurches at the start and crawls at the end.
     * Measured on the Pixel 6a at the old one-minute duration: -28 dB at
     * 3s, -21 dB at 15s, -12 dB at 30s, 0 dB at 62s; the shape is the same,
     * stretched tenfold.
     *
     * [player] is re-read every step and a null one ends that step, so a
     * dismissal mid-ramp cannot touch a released MediaPlayer — provided the
     * caller also clears [handler] before releasing it, which
     * `AlarmService.stopSound` does.
     */
    fun startRamp(handler: Handler, player: () -> MediaPlayer?) {
        val steps = (RAMP_DURATION_MS / RAMP_STEP_MS).toInt()
        for (step in 1..steps) {
            handler.postDelayed({
                val live = player() ?: return@postDelayed
                val progress = step.toFloat() / steps
                val gain =
                    RAMP_START_GAIN + (1f - RAMP_START_GAIN) * progress * progress
                runCatching { live.setVolume(gain, gain) }
                    .onFailure { Log.w(TAG, "volume ramp step failed", it) }
            }, RAMP_STEP_MS * step)
        }
    }
}
