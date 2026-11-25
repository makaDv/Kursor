# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# If your project uses WebView with JS, uncomment the following
# and specify the fully qualified class name to the JavaScript interface
# class:
#-keepclassmembers class fqcn.of.javascript.interface.for.webview {
#   public *;
#}

# Uncomment this to preserve the line number information for
# debugging stack traces.
#-keepattributes SourceFile,LineNumberTable

# If you keep the line number information, uncomment this to
# hide the original source file name.
#-renamesourcefileattribute SourceFile

# ---- PadLink release rules (R8) -------------------------------------------------
# Capacitor finds plugins and their @PluginMethod methods by reflection.
-keep class com.getcapacitor.** { *; }
-keep @com.getcapacitor.annotation.CapacitorPlugin class * { *; }
-keepclassmembers class * {
    @com.getcapacitor.PluginMethod public *;
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod

# PadLink native bridge (pinned TLS, secure storage, QR scanner).
-keep class io.github.makadv.padlink.nativebridge.** { *; }

# ZXing scanner activity (started by class name from the plugin).
-keep class com.journeyapps.barcodescanner.** { *; }
-keep class com.google.zxing.** { *; }

# OkHttp / Okio: optional platform integrations not present on Android.
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# Keep line numbers for readable crash reports in Play Console (file names hidden).
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
