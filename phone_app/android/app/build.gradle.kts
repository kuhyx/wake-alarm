import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing key, kept out of the repo. CI writes key.properties from
// repository secrets; locally the file is absent and the build falls back to
// the debug key so `flutter run --release` still works. Every release APK is
// signed with the one shared key, so updates install over each other instead
// of forcing an uninstall.
val keystoreProperties = Properties().apply {
    val f = rootProject.file("key.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "com.kuhy.wake_alarm_sync"
    // Pinned explicitly rather than delegated to the Flutter Gradle plugin:
    // full-screen-intent and foreground-service semantics both changed at
    // API 34/35, and the alarm path cannot be reasoned about without a floor.
    // Pinned above `flutter.compileSdkVersion` (36 on Flutter 3.47.2):
    // flutter_secure_storage 11.0.0, which arrives with crdt_sync_flutter
    // v0.3.1, publishes AAR metadata demanding API 37 or later. That in
    // turn needs AGP > 9.1.0, which needs Gradle >= 9.5.0 -- see
    // settings.gradle.kts and gradle-wrapper.properties.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.kuhy.wake_alarm_sync"
        // 28 is the floor for android:showWhenLocked / android:turnScreenOn as
        // plain manifest attributes, which the ring activity relies on; it also
        // clears flutter_secure_storage's API 23 (Android Keystore) requirement
        // and Flutter's own default of 24.
        minSdk = 28
        // Matches the target phone. Keep in step with compileSdk above.
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystoreProperties.getProperty("storeFile") != null) {
            create("release") {
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Falls back to the debug key only when key.properties is absent
            // (a fresh clone or a local run), so `flutter run --release` works.
            signingConfig = signingConfigs.findByName("release")
                ?: signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // JVM unit tests (src/test) for the pure decision code -- StickCheck,
    // DayCache, RingDecision, PoolSyncSchedule. No Robolectric: anything
    // that needs a Context stays out of them.
    testImplementation("junit:junit:4.13.2")
}

// Start the Dart compile first. Without the configuration cache (Flutter's
// FlutterTask does not support it) Gradle runs one :app task at a time, and
// `compileFlutterBuild<Variant>` sat ~190th in the plan: on a clean tree it
// started ~8 s in, after :app had idled waiting on plugin resources, then
// held :app for ~20 s while Kotlin, dex and manifests queued behind it.
// Running it before pre<Variant>Build overlaps it with the plugin projects.
// mustRunAfter only orders; it pulls the compile into no task graph.
tasks.matching { it.name.matches(Regex("pre\\w+Build")) }.configureEach {
    val variant = name.removePrefix("pre").removeSuffix("Build")
    mustRunAfter(tasks.matching { it.name == "compileFlutterBuild$variant" })
}

// Debug APKs only reach the Pixel 6a (arm64-v8a) and the x86_64 emulator.
// Flutter packs three ABIs into every debug APK (182 MB), and merging,
// stripping and zipping libraries no debug install loads cost the clean
// probe build seconds it does not have: the 32-bit ABIs, and the engine's
// 15 MB Vulkan validation layer, loaded only when the manifest sets
// io.flutter.embedding.android.EnableVulkanValidation (it does not).
// Release keeps every ABI.
androidComponents {
    onVariants(selector().withBuildType("debug")) { variant ->
        variant.packaging.jniLibs.excludes.addAll(
            listOf("lib/armeabi-v7a/**", "lib/x86/**", "**/libVkLayer_khronos_validation.so"),
        )
    }
}
