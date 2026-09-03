plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
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
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.manhwamaniacs.reader"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
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
