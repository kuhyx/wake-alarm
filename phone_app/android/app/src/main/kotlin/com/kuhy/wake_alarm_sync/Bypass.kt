package com.kuhy.wake_alarm_sync

import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.util.Log
import java.time.LocalDate

/** How the alarm was got around; [wire] is the `bypass` event's `cause`. */
enum class BypassCause(val wire: String) {
    SUSPENDED("suspended"),
    ADMIN_REMOVED("admin_removed"),
    FSI_REVOKED("fsi_revoked"),
    NOTIFICATIONS_OFF("notifications_off"),
    RING_KILLED("ring_killed"),
}

/** The bypass rules as pure functions; [Bypass] gathers the inputs. */
object BypassRules {
    /** A bypass counts on a ringing day while the ring or the morning session is live. */
    fun counts(ringingDay: Boolean, ringLive: Boolean, sessionLive: Boolean): Boolean =
        ringingDay && (ringLive || sessionLive)

    /** The same cause recorded less than [windowMs] ago. */
    fun isRepeat(last: Pair<String, Long>?, cause: String, now: Long, windowMs: Long): Boolean =
        last != null && last.first == cause && now - last.second in 0 until windowMs

    /** Today's ring fired, was never dismissed, and nothing is ringing now. */
    fun ringKilled(firedToday: Boolean, dismissedToday: Boolean, ringing: Boolean): Boolean =
        firedToday && !dismissedToday && !ringing
}

/**
 * Records a bypass of the alarm: the app paused from the launcher
 * ("Wstrzymaj aplikację", 2026-11-20 and 11-22), its device admin removed,
 * notifications or the full-screen intent switched off, or the ring killed.
 *
 * A bypass is a miss on any ringing day ([StickCheck]), so it locks the phone
 * down through the next day and stacks the streak. It is published at once
 * (the `bypass` phone event), so the PC rings until a fresh dismiss, and the
 * phone rings again: the morning goes on as if the bypass never happened,
 * one re-ring richer when a session was live.
 */
object Bypass {
    private const val TAG = "WakeAlarmBypass"

    // One launch runs the checks from MainActivity and then AlarmActivity
    // (emulator, 2026-11-22: two events, two publishes for one revoke).
    private const val REPEAT_WINDOW_MS = 60_000L
    private var lastRecorded: Pair<String, Long>? = null

    /** Records [cause] if it counts today; returns whether it did. */
    @Synchronized
    fun record(context: Context, cause: BypassCause): Boolean {
        val today = LocalDate.now()
        val ringLive = RingWatch.firedToday(context) && !RingWatch.dismissedOn(context, today)
        val sessionLive = SessionNotice.isLiveToday(context)
        if (!BypassRules.counts(ringingDay(context, today), ringLive, sessionLive)) {
            Log.i(TAG, "${cause.wire}: no ring or session live; not a bypass")
            EventLog.append(context, "bypass_ignored", mapOf("cause" to cause.wire))
            return false
        }
        val now = System.currentTimeMillis()
        if (BypassRules.isRepeat(lastRecorded, cause.wire, now, REPEAT_WINDOW_MS)) {
            Log.i(TAG, "bypass: ${cause.wire} again within a minute; already recorded")
            return true
        }
        lastRecorded = cause.wire to now
        Log.w(TAG, "bypass: ${cause.wire}")
        RingWatch.markBypass(context, today)
        EventLog.append(
            context,
            "bypass",
            mapOf("cause" to cause.wire, "date" to today.toString(), "session" to sessionLive),
        )
        if (cause == BypassCause.SUSPENDED) WorkdayStick.sendUnsuspend(context)
        StickRunner.run(context, "bypass")
        ringAgain(context)
        HeadlessRingStart.start(context, HeadlessRingStart.PUBLISH_ENTRYPOINT)
        return true
    }

    /**
     * Every launch, from either activity: the launcher restores whichever
     * one was on top (the ring or the session screen), so checking only in
     * MainActivity missed a revoke made mid-morning (emulator, 2026-11-22).
     */
    fun checkOnLaunch(context: Context) {
        checkRingKilled(context)
        checkPermissions(context)
    }

    /** Checks the permissions the ring needs; a revoked one on a live morning is a bypass. */
    fun checkPermissions(context: Context) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (NotifState.off(context)) {
            record(context, BypassCause.NOTIFICATIONS_OFF)
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE &&
            !manager.canUseFullScreenIntent()
        ) {
            record(context, BypassCause.FSI_REVOKED)
        }
    }

    /** On a launch or boot: today's ring fired, undismissed, and is not ringing. */
    fun checkRingKilled(context: Context) {
        val killed = BypassRules.ringKilled(
            firedToday = RingWatch.firedToday(context),
            dismissedToday = RingWatch.dismissedOn(context, LocalDate.now()),
            ringing = AlarmService.running,
        )
        if (killed) record(context, BypassCause.RING_KILLED)
    }

    /** Starts the ring again; a refused start (still suspended) waits for the unsuspend. */
    fun ringAgain(context: Context) {
        try {
            AlarmService.start(context)
        } catch (e: RuntimeException) {
            Log.w(TAG, "ring not restarted yet: $e")
        }
    }

    private fun ringingDay(context: Context, day: LocalDate): Boolean =
        AlarmScheduler.storedAlarm(context) != null &&
            !FreeDays.isFree(context, day) &&
            !SickDays.isSick(context, day) &&
            RingWatch.skippedOn(context, day) == null
}
