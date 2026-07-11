package com.manhwamaniacs.reader

import android.app.ActivityManager
import android.content.Context
import android.view.KeyEvent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Native bridge for two things the Flutter side can't do on its own:
 *  - Volume-key page turning in the reader (hardware key events must be
 *    intercepted here, before the OS shows its volume UI).
 *  - Real device memory stats, to size the reader's image cache relative to
 *    the device instead of a single fixed budget for every phone.
 */
class MainActivity : FlutterActivity() {
    private val channelName = "com.manhwamaniacs.reader/native"
    private var methodChannel: MethodChannel? = null

    // Only intercept volume keys while the reader is open and the user has
    // the setting enabled -- toggled from Dart via setVolumeKeyNavEnabled.
    // Every other screen (and a disabled setting) sees normal volume keys.
    private var volumeKeyNavEnabled = false

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
                else -> result.notImplemented()
            }
        }
        methodChannel = channel
    }

    override fun onDestroy() {
        methodChannel?.setMethodCallHandler(null)
        methodChannel = null
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
