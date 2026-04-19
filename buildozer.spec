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

[buildozer]
log_level = 2
warn_on_root = 1
