package com.manhwamaniacs.reader

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.os.StatFs
import android.view.Display
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
 *  - Owning the window's preferred display mode, which Flutter does not set
 *    on its own (see [applyPreferredDisplayMode]).
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

    // Whether the window should hold the panel at its fastest mode. Defaults
    // to true to match `PreferencesService.highRefreshRate`, so the very first
    // frames of a cold start are already fast -- Dart pushes the user's real
    // value over the channel a few hundred milliseconds later. A user who
    // turned the setting off therefore pays one brief high-rate window at
    // launch, rather than everyone else paying a 60 Hz startup.
    private var highRefreshRateEnabled = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        applyPreferredDisplayMode()
    }

    override fun onResume() {
        super.onResume()
        // The mode we asked for can be invalidated while we are backgrounded
        // — the user changing screen resolution in system settings renumbers
        // every mode id. Re-asking is a no-op when the preference still holds.
        applyPreferredDisplayMode()
    }

    /**
     * Assert the window's preferred display mode: the panel's fastest mode
     * while [highRefreshRateEnabled], the system default otherwise.
     *
     * Flutter does not set this itself: an Android app inherits the display's
     * default mode, and on nearly every 90/120/144 Hz phone that default is
     * 60 Hz. A reader whose whole interaction is a continuous vertical scroll
     * is exactly the app where that is most visible.
     *
     * Turning the setting off writes [SYSTEM_DEFAULT_MODE_ID] rather than
     * merely skipping the request. A preference once written stays written for
     * the life of the window, so "stop asking" would leave the panel pinned at
     * whatever was last asked for; clearing it is what actually hands the
     * choice back to the system's own variable-refresh policy.
     */
    private fun applyPreferredDisplayMode() {
        val target = if (highRefreshRateEnabled) fastestModeId() else SYSTEM_DEFAULT_MODE_ID

        // Compared against the *preference*, which is what this function
        // establishes — not against `display.mode`, the rate the panel happens
        // to be running this instant. The two disagree whenever something else
        // has cleared the preference while Android's variable-refresh policy
        // still has the fast mode active (touch input in flight, an animation
        // finishing): checking the active mode would return early and leave
        // the preference cleared, free to drop again a moment later.
        // Reassigning window.attributes forces a relayout, so the guard earns
        // its place.
        if (window.attributes.preferredDisplayModeId == target) return

        window.attributes = window.attributes.apply {
            preferredDisplayModeId = target
        }
    }

    /**
     * The id of the fastest mode the panel offers *at its current resolution*,
     * or [SYSTEM_DEFAULT_MODE_ID] when it cannot be determined.
     *
     * Modes are filtered to the current resolution before picking the fastest
     * one. Several phones expose 1080p@120 alongside 1440p@60; choosing purely
     * on refresh rate would silently override the resolution the user chose in
     * system settings, trading their sharpness for smoothness without asking.
     */
    private fun fastestModeId(): Int {
        val display = activeDisplay() ?: return SYSTEM_DEFAULT_MODE_ID
        val current = display.mode ?: return SYSTEM_DEFAULT_MODE_ID
        val fastest = display.supportedModes
            .filter {
                it.physicalWidth == current.physicalWidth &&
                    it.physicalHeight == current.physicalHeight
            }
            .maxByOrNull { it.refreshRate }
            ?: return SYSTEM_DEFAULT_MODE_ID
        return fastest.modeId
    }

    private fun activeDisplay(): Display? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            display
        } else {
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay
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
                "setHighRefreshRateEnabled" -> {
                    // Defaults to true on a malformed argument, matching both
                    // the field's initial value and the Dart-side default.
                    highRefreshRateEnabled = call.arguments as? Boolean ?: true
                    applyPreferredDisplayMode()
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

    private companion object {
        // `WindowManager.LayoutParams.preferredDisplayModeId` documents 0 as
        // "no preference" — the same value `flutter_displaymode` sends for
        // `DisplayMode.auto`.
        const val SYSTEM_DEFAULT_MODE_ID = 0
    }
}
