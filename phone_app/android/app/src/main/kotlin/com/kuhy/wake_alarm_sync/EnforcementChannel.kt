package com.kuhy.wake_alarm_sync

import android.content.Context
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.time.LocalDate

/**
 * The wake-enforcement methods on the one alarm channel ([AlarmChannel]
 * delegates its unknown methods here, so that file stays under the cap).
 *
 * Dart reads the stick and the event log through this, appends its own
 * events to the same log, and uses the escape hatch. Nothing here can lock
 * or arm anything: the stick is decided natively by [StickRunner].
 */
object EnforcementChannel {

    /** Handles [call] if it is one of ours; false leaves it unanswered. */
    fun handleCall(context: Context, call: MethodCall, result: MethodChannel.Result): Boolean {
        when (call.method) {
            "appendEvent" -> {
                val kind = call.argument<String>("kind")
                if (kind == null) {
                    result.error("bad_args", "kind is required", null)
                } else {
                    val data = call.argument<Map<String, Any?>>("data") ?: emptyMap()
                    EventLog.append(context, kind, data)
                    result.success(null)
                }
            }
            "readEvents" -> result.success(EventLog.readJson(context))
            "enforcementState" -> result.success(state(context))
            // False once the hatch has closed; see EscapeHatch.
            "escapeToday" -> result.success(EscapeHatch.use(context))
            else -> return false
        }
        return true
    }

    /**
     * Everything the stakes card and the ring line show, as plain values.
     *
     * `lockIfMiss*` comes from [StickCheck.afterMiss] -- the same function
     * the enforcement runs -- so the date the screen promises is the date a
     * miss would actually send.
     */
    private fun state(context: Context): Map<String, Any?> {
        val today = LocalDate.now()
        val tomorrow = today.plusDays(1)
        val stick = StickStore.load(context)
        val alarm = AlarmScheduler.storedAlarm(context)
        val isFree = { day: LocalDate -> FreeDays.isFree(context, day) }
        return mapOf(
            "today" to today.toString(),
            "alarmHour" to alarm?.hour,
            "alarmMinute" to alarm?.minute,
            "dismissedToday" to RingWatch.dismissedOn(context, today),
            "escapedToday" to StickStore.escapedOn(context, today),
            "freeToday" to isFree(today),
            "freeTomorrow" to isFree(tomorrow),
            "streak" to stick.streak,
            "lockedThrough" to stick.lockedThrough?.toString(),
            "lastMiss" to stick.lastMiss?.toString(),
            "updatedAt" to StickStore.updatedAt(context),
            "lockIfMissToday" to
                StickCheck.afterMiss(today, stick, isFree).lockedThrough?.toString(),
            "lockIfMissTomorrow" to
                StickCheck.afterMiss(tomorrow, stick, isFree).lockedThrough?.toString(),
        )
    }
}
