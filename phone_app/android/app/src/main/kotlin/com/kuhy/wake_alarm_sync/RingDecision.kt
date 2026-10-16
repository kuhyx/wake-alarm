package com.kuhy.wake_alarm_sync

/** Why the daily alarm stays silent; [wire] is the `alarm_fired` event's `reason`. */
enum class RingSkip(val wire: String, val label: String) {
    FREE_DAY("free_day", "free day"),
    SICK_DAY("sick_day", "sick day"),
}

/**
 * Whether the daily alarm rings, as a pure function of the two native day
 * caches, so the rule is checkable without a device. A date is never in
 * both pools; if a sync race ever put it there, the free day is named.
 */
object RingDecision {
    /** The reason to stay silent, or null to ring. */
    fun skip(isFree: Boolean, isSick: Boolean): RingSkip? = when {
        isFree -> RingSkip.FREE_DAY
        isSick -> RingSkip.SICK_DAY
        else -> null
    }
}
