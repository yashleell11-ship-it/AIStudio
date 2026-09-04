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
