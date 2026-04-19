[app]

title = InventarioApp
package.name = inventarioapp
package.domain = org.test

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.1

requirements = python3==3.10,kivy,pillow,zbarlight

orientation = portrait

fullscreen = 0

android.permissions = CAMERA
android.features = android.hardware.camera

android.api = 33
android.minapi = 21
android.ndk = 25b

android.archs = armeabi-v7a

log_level = 2

warn_on_root = 0
