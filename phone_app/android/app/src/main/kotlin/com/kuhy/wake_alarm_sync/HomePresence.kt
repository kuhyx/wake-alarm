package com.kuhy.wake_alarm_sync

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Where the phone is right now, as raw observations only.
 *
 * Hand-written on the existing MethodChannel for the same reason the ring path
 * is: the stack is AGP 9 / Gradle 9.1 / Kotlin 2.3.20 and a pub plugin that
 * fails to compile breaks the build outright instead of degrading.
 *
 * **This decides nothing.** It reports a BSSID, a fix, and a distance; whether
 * that means "home" is `home_presence.dart`'s job, so the policy stays unit
 * testable without a device. The one exception is [distanceMeters], computed
 * here because [Location.distanceBetween] is already on hand and putting the
 * trig in Dart would mean hand-rolling Haversine in the file under test.
 *
 * Wi-Fi is tried first and, when it answers, GPS is never touched: at home the
 * BSSID is instant and indoors a fix may take 30s or never arrive at all.
 */
object HomePresence {

    private const val TAG = "WakeAlarmPresence"

    /** What Android hands back instead of a real BSSID when it redacts one. */
    private const val REDACTED_BSSID = "02:00:00:00:00:00"

    /** A second redaction sentinel seen on some OEM builds. */
    private const val ZERO_BSSID = "00:00:00:00:00:00"

    /** What WifiManager reports for an SSID it will not disclose. */
    private const val UNKNOWN_SSID = "<unknown ssid>"

    /**
     * Reads presence and hands the observations to [callback] on the main
     * thread.
     *
     * Asynchronous because a fix can take seconds and this is called from the
     * ring screen: blocking the platform thread there is an ANR while the
     * alarm is sounding.
     */
    fun read(
        context: Context,
        homeLat: Double?,
        homeLon: Double?,
        withFix: Boolean,
        callback: (Map<String, Any?>) -> Unit,
    ) {
        val main = Handler(Looper.getMainLooper())
        val answered = AtomicBoolean(false)
        fun done(payload: Map<String, Any?>) {
            if (!answered.compareAndSet(false, true)) return
            Log.i(TAG, "presence $payload")
            main.post { callback(payload) }
        }

        if (!hasLocationPermission(context)) {
            done(unreadable("no-permission"))
            return
        }
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
        // Location services off redacts the BSSID *and* kills every provider,
        // so this single toggle is enough to make presence unreadable.
        if (manager == null || !manager.isLocationEnabled) {
            done(unreadable("location-disabled"))
            return
        }

        val wifi = readWifi(context)
        // At ring time a Wi-Fi answer ends it: GPS is skipped entirely, which
        // is the whole reason the verdict is instant at home. Registration
        // passes withFix so it captures a coordinate too — otherwise the GPS
        // fallback could only ever be configured with Wi-Fi turned off, which
        // means in practice never.
        if (wifi != null && !withFix) {
            done(observation(wifi = wifi, fix = null, homeLat, homeLon, "ok"))
            return
        }

        val cached = LocationFix.freshestLastKnown(manager)
        if (cached != null) {
            done(observation(wifi = wifi, fix = cached, homeLat, homeLon, "ok"))
            return
        }
        LocationFix.requestSingle(manager, main) { fix ->
            if (fix == null && wifi == null) {
                done(unreadable("no-fix"))
            } else {
                done(observation(wifi = wifi, fix = fix, homeLat, homeLon, "ok"))
            }
        }
    }

    private fun hasLocationPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * SSID and BSSID of the connected Wi-Fi, or null when neither can be
     * trusted.
     *
     * Android redacts these to [REDACTED_BSSID] and [UNKNOWN_SSID] rather
     * than failing when the fine-location grant or location services is
     * missing — a redacted value looks exactly like a successful read, so it
     * must be filtered here or every morning silently reads "away".
     *
     * Both are returned because a router hands out a *different* BSSID per
     * band and a mesh node one per box, and the phone roams between them
     * overnight. Matching on the BSSID alone would call a band switch
     * "travelling".
     */
    private fun readWifi(context: Context): Pair<String?, String?>? {
        // getConnectionInfo() is deprecated at API 31 in favour of
        // NetworkCapabilities.getTransportInfo(). Do NOT "modernise" this:
        // the *synchronous* ConnectivityManager.getNetworkCapabilities()
        // redacts every location-sensitive field, so transportInfo comes back
        // null and the BSSID silently vanishes. Measured on the Pixel 6a
        // (API 36, 2026-08-31): connected to a known AP, fine location
        // granted, location services on, and the capabilities route still
        // returned ssid=null bssid=null while the GPS fallback masked it.
        // Un-redacted transportInfo needs a registerNetworkCallback, which is
        // asynchronous and buys nothing here.
        @Suppress("DEPRECATION")
        val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE)
            as? WifiManager
        @Suppress("DEPRECATION")
        val info = wm?.connectionInfo
        val bssid = info?.bssid?.lowercase()?.takeUnless {
            it.isBlank() || it == REDACTED_BSSID || it == ZERO_BSSID
        }
        val ssid = info?.ssid?.trim('"')?.takeUnless {
            it.isBlank() || it == UNKNOWN_SSID
        }
        return if (bssid == null && ssid == null) null else Pair(ssid, bssid)
    }

    private fun observation(
        wifi: Pair<String?, String?>?,
        fix: Location?,
        homeLat: Double?,
        homeLon: Double?,
        reason: String,
    ): Map<String, Any?> = mapOf(
        "ssid" to wifi?.first,
        "bssid" to wifi?.second,
        "lat" to fix?.latitude,
        "lon" to fix?.longitude,
        "accuracy" to fix?.accuracy?.toDouble(),
        "distanceMeters" to distanceMeters(fix, homeLat, homeLon),
        "reason" to reason,
    )

    private fun distanceMeters(fix: Location?, homeLat: Double?, homeLon: Double?): Double? {
        if (fix == null || homeLat == null || homeLon == null) return null
        val out = FloatArray(1)
        Location.distanceBetween(fix.latitude, fix.longitude, homeLat, homeLon, out)
        return out[0].toDouble()
    }

    private fun unreadable(reason: String): Map<String, Any?> = mapOf(
        "ssid" to null,
        "bssid" to null,
        "lat" to null,
        "lon" to null,
        "accuracy" to null,
        "distanceMeters" to null,
        "reason" to reason,
    )
}
