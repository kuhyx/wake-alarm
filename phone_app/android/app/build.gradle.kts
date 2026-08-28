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
