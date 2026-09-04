import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing. `android/key.properties` and the .jks beside it are gitignored:
// the upload key never reaches the repository. A missing file is not fatal — the
// release build falls back to debug signing so `flutter run --release` still works
// on a machine that has no key, which is how CI and fresh clones behave.
val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.inputStream().use { keystoreProperties.load(it) }
}

android {
    namespace = "com.manhwamaniacs.reader"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.manhwamaniacs.reader"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            val alias = keystoreProperties.getProperty("keyAlias")
            if (alias != null) {
                keyAlias = alias
                keyPassword = keystoreProperties.getProperty("keyPassword")
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
            }
        }
    }

    buildTypes {
        release {
            // The upload key when key.properties is present, debug otherwise.
            // An APK signed with a DIFFERENT key cannot upgrade an installed one —
            // Android refuses it — so everyone still running a debug-signed build
            // must uninstall once before taking this and every future release.
            signingConfig = if (keystoreProperties.getProperty("keyAlias") != null) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

// Release packages only the ABIs a physical Android phone can run.
//
// The Flutter Gradle Plugin sets `defaultConfig.ndk.abiFilters` to all three
// architectures it supports — armeabi-v7a, arm64-v8a, x86_64 — when the plugin
// is applied. x86_64 is there for the emulator: no phone has ever run it, and
// it was the single biggest thing in the APK. Measured on this tree it is
// 21.2 MB of a 63.5 MB universal build — a third of the download — for hardware
// that nobody installing from app.manhwamaniacs.xyz/app/download owns.
// Dropping it takes the release APK from 63,543,608 to 41,295,479 bytes (-35%).
//
// Excluded per-variant rather than by overriding `defaultConfig.ndk.abiFilters`
// (build-type `ndk` blocks are merged with defaultConfig, not substituted for
// it, so overriding there would have applied to every variant) — this way debug
// and profile builds keep x86_64 and `flutter run` still works on an emulator.
//
// armeabi-v7a deliberately STAYS. 32-bit-only ARM phones — MT6580/MT6737-class
// budget hardware — were still being sold running Android 7-9, which is inside
// this app's minSdk of 24. Dropping it would save another 17.6 MB, but
// /app/download hands ONE file to every phone, and the failure mode for a user
// on one of those devices is a bare "App not installed" with nothing on screen
// to explain it. ops/vps/push.sh refuses to publish an APK missing either ABI.
//
// Measured and deliberately NOT taken: adding
// `variant.packaging.jniLibs.useLegacyPackaging.set(true)` here compresses the
// native libraries instead of storing them page-aligned, and takes the same APK
// from 41,295,479 to 19,913,127 bytes — another 52% off the download. The cost
// is that Android must extract those libraries at install time, so the app then
// occupies ~57 MB on the device instead of ~41 MB, permanently. The users that
// buys the least are precisely the 32-bit budget phones armeabi-v7a is kept
// for, which are also the ones with 8-16 GB of total storage. If the download
// size ever matters more than the footprint, that one line is the switch, and
// the numbers above are the trade.
androidComponents {
    onVariants(selector().withBuildType("release")) { variant ->
        variant.packaging.jniLibs.excludes.add("**/x86_64/**")
    }
}

dependencies {
    // 1c-M4's `mm/ocr` channel (`OcrChannel.kt`). A plain Gradle dependency,
    // not a Flutter plugin package: the iOS half of the same channel must add
    // no CocoaPod at all (the sideload pipeline's Podfile.lock is generated in
    // CI and is not worth risking), and a plugin package would have forced
    // one on both platforms.
    //
    // The Play-Services-hosted model, deliberately not the bundled one
    // (`com.google.mlkit:text-recognition`). The bundled artifact ships an
    // ~11 MB native OCR pipeline per ABI, and this project's release APK
    // carries three (arm64-v8a, armeabi-v7a, x86_64) with native libs stored
    // uncompressed — about +31 MB on a 61 MB APK, half again its size, for a
    // feature whose primary platform is iOS (spec O-2). This variant is
    // ~1 MB and fetches its model through Play Services; `OcrChannel`'s
    // `isAvailable` probes for real so the feature stays hidden until the
    // model has actually landed, rather than offering a button that finds
    // nothing.
    implementation("com.google.android.gms:play-services-mlkit-text-recognition:19.0.1")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
