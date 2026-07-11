allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
// Some plugins (e.g. flutter_displaymode 0.6.0) hard-pin an old compileSdk,
// but their transitive AndroidX deps require a newer one -- currently 36,
// via file_picker's dependency on flutter_plugin_android_lifecycle. Force
// every Android module that compiles below the floor up to it so the release
// build links. Registered before the evaluationDependsOn(":app") block below
// so the afterEvaluate hook is attached while each project is still
// un-evaluated. Bump MIN_COMPILE_SDK whenever a new plugin demands more.
val MIN_COMPILE_SDK = 36
subprojects {
    afterEvaluate {
        val androidExtension = extensions.findByName("android")
        if (androidExtension is com.android.build.gradle.BaseExtension) {
            val currentApi = (androidExtension.compileSdkVersion ?: "")
                .removePrefix("android-")
                .toIntOrNull() ?: 0
            if (currentApi < MIN_COMPILE_SDK) {
                androidExtension.compileSdkVersion(MIN_COMPILE_SDK)
            }
        }
    }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
