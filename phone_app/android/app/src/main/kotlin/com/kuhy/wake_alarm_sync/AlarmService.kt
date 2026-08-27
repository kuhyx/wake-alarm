package com.kuhy.wake_alarm_sync

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

/**
 * Foreground service that actually makes noise until the alarm is dismissed.
 *
 * Holds a PARTIAL_WAKE_LOCK so the CPU keeps running with the screen off (it
 * does **not** wake the screen — [AlarmActivity]'s turnScreenOn does that), and
 * posts a full-screen-intent notification that launches the dismiss screen over
 * the lockscreen.
 */
class AlarmService : Service() {

    private var player: MediaPlayer? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var vibrator: Vibrator? = null

    companion object {
        private const val TAG = "AlarmService"
        private const val CHANNEL_ID = "wake_alarm_ring"
        private const val NOTIFICATION_ID = 42

        /** Vibration: 1s buzz, 1s gap, repeating from index 0. */
        private val VIBRATION_PATTERN = longArrayOf(0, 1000, 1000)

        /** Starts the ring. Safe to call when already ringing — start is idempotent. */
        fun start(context: Context) {
            val intent = Intent(context, AlarmService::class.java)
            context.startForegroundService(intent)
        }

        /** Stops the ring and releases every resource it holds. */
        fun stop(context: Context) {
            context.stopService(Intent(context, AlarmService::class.java))
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createChannel()
        // The type must be passed here AND declared on the <service> in the
        // manifest; omitting either is a hard crash at ring time on API 34+.
        startForeground(
            NOTIFICATION_ID,
            buildNotification(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
        )
        acquireWakeLock()
        startSound()
        startVibration()
        // START_STICKY: if the system kills us under memory pressure while the
        // user is still asleep, the alarm comes back rather than going silent.
        return START_STICKY
    }

    override fun onDestroy() {
        stopSound()
        stopVibration()
        releaseWakeLock()
        super.onDestroy()
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        // IMPORTANCE_HIGH is required for a full-screen intent to be honoured.
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Wake alarm",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "The ringing wake alarm"
            // The service owns sound and vibration, so the channel must not add
            // its own — a channel sound would play on the notification stream
            // and be silenced by DND, unlike STREAM_ALARM.
            setSound(null, null)
            enableVibration(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val fullScreen = PendingIntent.getActivity(
            this,
            0,
            Intent(this, AlarmActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Wake alarm")
            .setContentText("Tap to dismiss")
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setCategory(Notification.CATEGORY_ALARM)
            .setOngoing(true)
            .setFullScreenIntent(fullScreen, true)
            .build()
    }

    private fun acquireWakeLock() {
        val power = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = power.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "wake_alarm_sync:ring",
        ).apply { acquire() }
    }

    private fun releaseWakeLock() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
    }

    private fun startSound() {
        if (player != null) return
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            ?: return
        // USAGE_ALARM maps to STREAM_ALARM, which is what ignores DND and
        // silent mode. Never USAGE_MEDIA here — it would be muted exactly when
        // the alarm matters most.
        player = MediaPlayer().apply {
            setDataSource(this@AlarmService, uri)
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            isLooping = true
            prepare()
            start()
        }
        raiseAlarmVolume()
    }

    /**
     * Alarm stream turned down to zero must not silence the alarm.
     *
     * Guarded: setStreamVolume can throw under an active zen rule, and by this
     * point startForeground() has already posted — an exception here would
     * take the whole ring down over a volume bump that is only an
     * improvement, not the mechanism.
     */
    private fun raiseAlarmVolume() {
        try {
            val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            val max = audio.getStreamMaxVolume(AudioManager.STREAM_ALARM)
            audio.setStreamVolume(AudioManager.STREAM_ALARM, max, 0)
        } catch (e: SecurityException) {
            Log.w(TAG, "could not raise the alarm volume; ringing anyway", e)
        }
    }

    private fun stopSound() {
        player?.run {
            if (isPlaying) stop()
            release()
        }
        player = null
    }

    private fun startVibration() {
        val service = resolveVibrator() ?: return
        vibrator = service
        service.vibrate(
            VibrationEffect.createWaveform(VIBRATION_PATTERN, 0),
        )
    }

    private fun stopVibration() {
        vibrator?.cancel()
        vibrator = null
    }

    private fun resolveVibrator(): Vibrator? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager)
                ?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
}
