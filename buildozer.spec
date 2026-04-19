[app]
title = Inventario
package.name = inventarioapp
package.domain = org.inventario.local
source.dir = .
source.include_exts = py
version = 0.1.0
requirements = python3,kivy,Pillow,android,pyzbar
orientation = portrait
fullscreen = 0
# Permisos: camara (escaneo), red (sync WiFi)
android.permissions = INTERNET,CAMERA

# --- Android / SDK (evita "Aidl not found" y licencias en CI) ---
android.accept_sdk_license = True
android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
# Una sola arquitectura acelera GitHub Actions (quita arm64-v8a y deja solo armeabi-v7a si prefieres 32 bits)
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
