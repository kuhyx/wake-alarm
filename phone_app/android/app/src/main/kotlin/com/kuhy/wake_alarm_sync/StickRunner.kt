package com.kuhy.wake_alarm_sync

import android.content.Context
import android.util.Log
import java.time.LocalDate
import java.time.LocalDateTime

/**
 * Runs the stick: gathers [StickInputs] from the native stores, asks
 * [StickCheck], and on a miss persists the new state, signals focus-owner and
 * logs it. The only place those three are wired together.
 *
 * Three triggers share this one decision, so they can never disagree:
 * `exact` (the [StickAlarm] at A + 15), `boot` (closes "phone off before the
 * alarm") and `watchdog` (the daily net). Every run also catches up on the
 * unchecked days before today ([StickCheck.run]), so a phone off for days
 * is judged day by day when it comes back. Running twice is harmless --
 * [StickVerdict.ALREADY_PENALISED] makes a second miss on one day a no-op,
 * which matters because Android replays BOOT_COMPLETED to a force-stopped
 * app on its next launch.
 */
object StickRunner {
    private const val TAG = "WakeAlarmStick"

    @Synchronized
    fun run(context: Context, trigger: String): StickVerdict {
        val before = StickStore.load(context)
        val run = StickCheck.run(
            StickInputs(
                now = LocalDateTime.now(),
                alarm = AlarmScheduler.storedAlarm(context),
                dismissedOn = { RingWatch.dismissedOn(context, it) },
                escapedOn = { StickStore.escapedOn(context, it) },
                isFree = { FreeDays.isFree(context, it) },
                isSick = { SickDays.isSick(context, it) },
                state = before,
                checkedThrough = StickStore.checkedThrough(context),
            ),
        )
        for ((day, verdict) in run.verdicts) {
            Log.i(TAG, "check ($trigger) $day: ${verdict.wire}")
            EventLog.append(
                context,
                "stick_check",
                mapOf("trigger" to trigger, "verdict" to verdict.wire, "date" to day.toString()),
            )
        }
        if (run.state != before) StickStore.save(context, run.state)
        StickStore.setCheckedThrough(context, run.checkedThrough)
        // A missed day whose lockdown already ended (caught up days later)
        // still counts toward the streak, but nothing is sent for it.
        run.signalUntil?.let { until ->
            WorkdayStick.sendLockdown(context, until)
            EventLog.append(
                context,
                "lockdown_sent",
                mapOf("until" to until.toString(), "streak" to run.state.streak),
            )
        }
        return run.verdicts.last().verdict
    }

    /**
     * A dismissed stick day breaks the chain: the streak shown and synced
     * drops to 0 at once. A lockdown already running is left alone, and a
     * dismiss *after* today's miss changes nothing -- the miss stands.
     */
    @Synchronized
    fun onDismissed(context: Context) {
        val today = LocalDate.now()
        if (!StickCheck.isStickDay(today) || FreeDays.isFree(context, today) ||
            SickDays.isSick(context, today)
        ) {
            return
        }
        val state = StickStore.load(context)
        if (state.lastMiss == today || state.streak == 0) return
        StickStore.save(context, state.copy(streak = 0))
    }
}
