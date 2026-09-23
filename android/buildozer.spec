[app]
title = SA-US ERP
package.name = sauserp
package.domain = com.saultimatesolutions
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = hostpython3==3.11.9,python3==3.11.9,kivy==2.3.1,openpyxl,pillow,plyer
orientation = portrait
fullscreen = 0
icon.filename = ../client/branding/app_logo.png

android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.skip_update = False

[buildozer]
log_level = 2
warn_on_root = 1
