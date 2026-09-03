package com.manhwamaniacs.reader

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * The Android half of the `mm/ocr` channel (spec §4): ML Kit's on-device
 * Latin text recognizer, wired by hand rather than through a Flutter plugin
 * package.
 *
 * The dependency is declared directly in `app/build.gradle.kts` and lives
 * only in this file, so nothing about it touches the Flutter plugin registry
 * — which matters because the iOS half of this channel must add no pod at
 * all, and a plugin package would have forced one.
 *
 * **The model is Play-Services-hosted, not bundled.** The bundled artifact
 * (`com.google.mlkit:text-recognition`) carries an ~11 MB native OCR pipeline
 * per ABI; against this project's three-ABI release APK that is ~31 MB, or
 * half again the APK's current size, for a feature whose primary platform is
 * iOS (spec O-2). The hosted variant costs about 1 MB and downloads its model
 * through Play Services instead. The price is that OCR is genuinely
 * *unavailable* until that download lands — which is why [isAvailable] below
 * is a real probe rather than a hardcoded `true`, and why
 * `AndroidManifest.xml` asks Play Services to fetch the model at install time
 * rather than waiting for the first run.
 */
class OcrChannel(messenger: BinaryMessenger) {

    private val channel = MethodChannel(messenger, CHANNEL_NAME)
    private val mainHandler = Handler(Looper.getMainLooper())

    /**
     * A single worker thread, not a pool: the Dart side sends one page per
     * call and waits for it, so concurrency would buy nothing, while a serial
     * executor keeps at most one decoded page bitmap alive at a time.
     */
    private val worker = Executors.newSingleThreadExecutor()

    /**
     * Created lazily and reused for the whole app session. Constructing a
     * recognizer per page would reload the model 60 times in a chapter run.
     */
    private var recognizer: TextRecognizer? = null

    init {
        channel.setMethodCallHandler { call, result -> handle(call, result) }
    }

    fun dispose() {
        channel.setMethodCallHandler(null)
        recognizer?.close()
        recognizer = null
        worker.shutdown()
    }

    private fun handle(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "isAvailable" -> worker.execute {
                val available = probeAvailability()
                mainHandler.post { result.success(available) }
            }
            "engineId" -> result.success("mlkit")
            "recognize" -> {
                val paths = call.argument<List<String>>("paths")
                if (paths == null) {
                    result.error("bad_arguments", "recognize expects { paths: [String] }", null)
                    return
                }
                // Off the platform thread: a full-resolution page is hundreds
                // of milliseconds of decode + inference, and blocking here
                // would freeze the UI for the length of a chapter run.
                worker.execute {
                    val pages = paths.map { recognizePage(it) }
                    mainHandler.post { result.success(pages) }
                }
            }
            else -> result.notImplemented()
        }
    }

    /**
     * Answers "can this device recognize text *right now*" by actually
     * recognizing — running the pipeline over a blank scratch bitmap and
     * reporting whether it completed.
     *
     * A behavioural probe rather than a Play-Services module query on
     * purpose: it needs no API beyond the one page recognition already uses,
     * and it is true by construction. Finding no text in a blank image is a
     * success; the failure this is looking for is ML Kit reporting the
     * optional module is still downloading, which is exactly the state where
     * spec §4 says the feature must stay hidden rather than offer a button
     * that produces nothing. A later launch, once the download has landed,
     * probes true and the feature appears.
     */
    private fun probeAvailability(): Boolean {
        return try {
            // ML Kit rejects inputs under 32x32; this is comfortably over.
            val scratch = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
            try {
                var succeeded = false
                val latch = CountDownLatch(1)
                client().process(InputImage.fromBitmap(scratch, 0))
                    .addOnSuccessListener { succeeded = true; latch.countDown() }
                    .addOnFailureListener { latch.countDown() }
                latch.await(PROBE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                succeeded
            } finally {
                scratch.recycle()
            }
        } catch (_: Throwable) {
            false
        }
    }

    /**
     * Recognizes one page, returning the `{text, boxes}` map Dart's
     * `PageText.fromChannel` expects. Never throws: an unreadable blob or an
     * ML Kit failure becomes an empty page so one bad file costs its own page
     * and not the rest of the chapter.
     */
    private fun recognizePage(path: String): Map<String, Any> {
        val empty = mapOf<String, Any>("text" to "", "boxes" to emptyList<Map<String, Any>>())

        val bitmap = try {
            BitmapFactory.decodeFile(path)
        } catch (_: Throwable) {
            null
        } ?: return empty

        val width = bitmap.width.toDouble()
        val height = bitmap.height.toDouble()
        if (width <= 0 || height <= 0) {
            bitmap.recycle()
            return empty
        }

        return try {
            // ML Kit delivers its result to a listener, not a return value.
            // This is already the worker thread and ML Kit's default listener
            // executor is the main thread, so blocking here on a latch cannot
            // deadlock — and it keeps `recognize` a plain synchronous
            // page-in/page-out call, which is what makes the Dart-side
            // one-page-at-a-time progress loop straightforward.
            val latch = CountDownLatch(1)
            var recognized: Text? = null
            client().process(InputImage.fromBitmap(bitmap, 0))
                .addOnSuccessListener { recognized = it; latch.countDown() }
                .addOnFailureListener { latch.countDown() }
            // A bound rather than an indefinite wait: a wedged recognizer must
            // cost one page, not hang the whole chapter run forever.
            latch.await(RECOGNIZE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            val visionText = recognized ?: return empty

            val lines = StringBuilder()
            val boxes = ArrayList<Map<String, Any>>()
            for (block in visionText.textBlocks) {
                for (line in block.lines) {
                    val text = line.text
                    if (text.isEmpty()) continue
                    if (lines.isNotEmpty()) lines.append('\n')
                    lines.append(text)

                    val box = line.boundingBox ?: continue
                    if (boxes.size >= MAX_BOXES_PER_PAGE) continue
                    // ML Kit reports pixel rects with a top-left origin;
                    // normalizing them to 0..1 here is what makes an Android
                    // box mean the same thing as the iOS one (see
                    // `OcrTextBox` on the Dart side). ML Kit exposes no
                    // per-line confidence, so none is sent — a fabricated
                    // 1.0 would be worse than an absent field.
                    boxes.add(
                        mapOf(
                            "text" to text,
                            "x" to box.left / width,
                            "y" to box.top / height,
                            "width" to (box.right - box.left) / width,
                            "height" to (box.bottom - box.top) / height,
                        ),
                    )
                }
            }
            mapOf("text" to lines.toString(), "boxes" to boxes)
        } catch (_: Throwable) {
            empty
        } finally {
            bitmap.recycle()
        }
    }

    private fun client(): TextRecognizer =
        recognizer ?: TextRecognition
            .getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            .also { recognizer = it }

    private companion object {
        const val CHANNEL_NAME = "mm/ocr"

        /** Mirrors `OCR_MAX_BOXES_PER_PAGE` in `backend/routes/ocr.py`. */
        const val MAX_BOXES_PER_PAGE = 300

        const val RECOGNIZE_TIMEOUT_SECONDS = 30L
        const val PROBE_TIMEOUT_SECONDS = 10L
    }
}
