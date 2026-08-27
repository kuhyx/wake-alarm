package com.kuhy.wake_alarm_sync

import android.app.Activity
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.util.Log
import io.flutter.plugin.common.MethodChannel

/**
 * Reads NFC tag ids while the ring screen is up.
 *
 * Hand-written on the existing MethodChannel rather than `nfc_manager`, for
 * the same reason the ring path is: nothing on the dismiss path may depend on
 * a plugin compiling against AGP 9. If NFC and QR were both plugins and both
 * failed, item 3 would have no working proof at all.
 *
 * Reader mode (rather than the foreground-dispatch intent flow) is what lets
 * a tag be read without the activity being restarted, which matters because
 * restarting the ring screen would reset the challenge.
 */
object NfcReader {

    /** Dart method invoked with the scanned tag id. */
    private const val ON_TAG = "onNfcTag"

    /** Tag technologies to poll; covers the common cheap NTAG stickers. */
    private const val FLAGS =
        NfcAdapter.FLAG_READER_NFC_A or
            NfcAdapter.FLAG_READER_NFC_B or
            NfcAdapter.FLAG_READER_NFC_F or
            NfcAdapter.FLAG_READER_NFC_V or
            NfcAdapter.FLAG_READER_NO_PLATFORM_SOUNDS

    /**
     * Starts polling, pushing each tag id to Dart over [channel].
     *
     * Returns false when the device has no NFC or it is switched off, so the
     * ring screen can say so rather than waiting on a tap that cannot come.
     */
    fun start(activity: Activity, channel: MethodChannel): Boolean {
        val adapter = NfcAdapter.getDefaultAdapter(activity) ?: return false
        if (!adapter.isEnabled) return false
        adapter.enableReaderMode(
            activity,
            { tag ->
                val id = idOf(tag)
                Log.i(TAG, "tag discovered: $id")
                activity.runOnUiThread { channel.invokeMethod(ON_TAG, id) }
            },
            FLAGS,
            null,
        )
        Log.i(TAG, "reader mode started on ${activity.javaClass.simpleName}")
        return true
    }

    /** Logcat tag for diagnosing why a tap did or did not arrive. */
    private const val TAG = "WakeAlarmNfc"

    /** Whether this device can read NFC at all and has it switched on. */
    fun isAvailable(context: android.content.Context): Boolean {
        val adapter = NfcAdapter.getDefaultAdapter(context) ?: return false
        return adapter.isEnabled
    }

    /** Stops polling; safe to call when [start] returned false. */
    fun stop(activity: Activity) {
        NfcAdapter.getDefaultAdapter(activity)?.disableReaderMode(activity)
    }

    /** Lower-case hex of the tag's id, which is what Settings registers. */
    private fun idOf(tag: Tag): String =
        tag.id.joinToString("") { "%02x".format(it) }
}
