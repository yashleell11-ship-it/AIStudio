package com.manhwamaniacs.reader

import android.app.ActivityManager
import android.content.Context
import android.os.Bundle
import android.os.StatFs
import android.view.KeyEvent
import androidx.core.view.WindowCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Native bridge for things the Flutter side can't do on its own:
 *  - Volume-key page turning in the reader (hardware key events must be
 *    intercepted here, before the OS shows its volume UI).
 *  - Real device memory stats, to size the reader's image cache relative to
 *    the device instead of a single fixed budget for every phone.
 *  - Free disk space, so the on-device chapter store (1c-M3) can enforce its
 *    ~1.5 GB free-space floor. `dart:io` has no cross-platform "bytes free"
 *    API and this project adds no new plugins for it — `StatFs` is a
 *    framework class, zero new Gradle dependencies.
 *
 * 1c-M4's OCR lives on its own channel in [OcrChannel] rather than here: it
 * is the one piece with a real dependency behind it (ML Kit), and keeping it
 * separate means this class stays the "framework classes only" bridge it has
 * always been.
 */
class MainActivity : FlutterActivity() {
    private val channelName = "com.manhwamaniacs.reader/native"
    private var methodChannel: MethodChannel? = null
    private var ocrChannel: OcrChannel? = null

    // Only intercept volume keys while the reader is open and the user has
    // the setting enabled -- toggled from Dart via setVolumeKeyNavEnabled.
    // Every other screen (and a disabled setting) sees normal volume keys.
    private var volumeKeyNavEnabled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "setVolumeKeyNavEnabled" -> {
                    volumeKeyNavEnabled = call.arguments as? Boolean ?: false
                    result.success(null)
                }
                "getDeviceMemoryInfo" -> result.success(readDeviceMemoryInfo())
                "getFreeDiskSpace" -> result.success(readFreeDiskSpaceBytes())
                else -> result.notImplemented()
            }
        }
        methodChannel = channel
        ocrChannel = OcrChannel(flutterEngine.dartExecutor.binaryMessenger)
    }

    override fun onDestroy() {
        methodChannel?.setMethodCallHandler(null)
        methodChannel = null
        ocrChannel?.dispose()
        ocrChannel = null
        super.onDestroy()
    }

    private fun readDeviceMemoryInfo(): Map<String, Any> {
        val activityManager = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val info = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(info)
        return mapOf(
            "totalMem" to info.totalMem,
            "availMem" to info.availMem,
            "lowMemory" to info.lowMemory,
        )
    }

    // Bytes free on the same volume the blob store writes to
    // (`getApplicationDocumentsDirectory()` resolves to `filesDir` here) —
    // matching the partition the free-space floor actually protects, not
    // necessarily the whole disk on a device with multiple volumes.
    private fun readFreeDiskSpaceBytes(): Long {
        val stat = StatFs(filesDir.path)
        return stat.availableBytes
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val isVolumeKey = event.keyCode == KeyEvent.KEYCODE_VOLUME_UP ||
            event.keyCode == KeyEvent.KEYCODE_VOLUME_DOWN
        if (volumeKeyNavEnabled && isVolumeKey) {
            // Consume both DOWN and UP so the system never shows its volume
            // overlay, but only invoke Dart once per physical press.
            if (event.action == KeyEvent.ACTION_DOWN) {
                val method = if (event.keyCode == KeyEvent.KEYCODE_VOLUME_UP) {
                    "onVolumeUp"
                } else {
                    "onVolumeDown"
                }
                methodChannel?.invokeMethod(method, null)
            }
            return true
        }
        return super.dispatchKeyEvent(event)
    }
}
