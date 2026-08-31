package com.kuhy.wake_alarm_sync

import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import java.util.concurrent.atomic.AtomicBoolean

/**
 * A single location fix, hand-written on LocationManager.
 *
 * Split out of [HomePresence] to hold both files under the repo's 250-line
 * cap, and because the two halves fail differently: the Wi-Fi read is
 * instant and synchronous, a fix is neither.
 *
 * Everything here is best-effort — every path can hand back null, which
 * [HomePresence] reports as unreadable.
 */
object LocationFix {

    /** How long a single fix may take before the read gives up. */
    private const val FIX_TIMEOUT_MS = 5_000L

    /** How stale a cached fix may be and still count as "where we are". */
    private const val LAST_KNOWN_MAX_AGE_MS = 10 * 60 * 1000L

    /** The newest cached fix across every provider, if recent enough. */
    fun freshestLastKnown(manager: LocationManager): Location? {
        val cutoff = System.currentTimeMillis() - LAST_KNOWN_MAX_AGE_MS
        return providers(manager)
            .mapNotNull { runCatching { manager.getLastKnownLocation(it) }.getOrNull() }
            .filter { it.time >= cutoff }
            .maxByOrNull { it.time }
    }

    /**
     * Asks for one fix, giving up after [FIX_TIMEOUT_MS].
     *
     * The timeout is the point: without it a ring screen indoors waits on a
     * GPS fix that is never coming, and the user waits with it.
     */
    fun requestSingle(
        manager: LocationManager,
        main: Handler,
        onResult: (Location?) -> Unit,
    ) {
        val provider = providers(manager).firstOrNull { manager.isProviderEnabled(it) }
        if (provider == null) {
            onResult(null)
            return
        }
        val settled = AtomicBoolean(false)
        fun settle(fix: Location?) {
            if (settled.compareAndSet(false, true)) onResult(fix)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val cancel = CancellationSignal()
            main.postDelayed({
                if (!settled.get()) cancel.cancel()
                settle(null)
            }, FIX_TIMEOUT_MS)
            runCatching {
                manager.getCurrentLocation(
                    provider,
                    cancel,
                    mainExecutor(main),
                ) { fix -> settle(fix) }
            }.onFailure { settle(null) }
            return
        }
        val listener = LocationListener { fix -> settle(fix) }
        main.postDelayed({
            manager.removeUpdates(listener)
            settle(null)
        }, FIX_TIMEOUT_MS)
        runCatching {
            @Suppress("DEPRECATION")
            manager.requestSingleUpdate(provider, listener, Looper.getMainLooper())
        }.onFailure { settle(null) }
    }

    /** Runs the fix callback on the main looper: one thread, no locking. */
    private fun mainExecutor(main: Handler) = java.util.concurrent.Executor { main.post(it) }

    /** Fused first (API 31+): it answers indoors where bare GPS does not. */
    private fun providers(manager: LocationManager): List<String> = buildList {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) add(LocationManager.FUSED_PROVIDER)
        add(LocationManager.NETWORK_PROVIDER)
        add(LocationManager.GPS_PROVIDER)
    }.filter { it in manager.allProviders }
}
