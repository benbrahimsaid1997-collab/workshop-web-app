[app]

title = ورشة السيارات
package.name = workshop
package.domain = com.workshop
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,mp4
version = 1.0
requirements = python3,kivy,kivymd,requests,arabic-reshaper,python-bidi
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a
android.accept_sdk_license = True
android.release_artifact = apk
log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1