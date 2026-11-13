# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para generar dist\PizarraVirtual.exe (un solo archivo, sin consola).
#
#   pyinstaller --noconfirm --clean PizarraVirtual.spec

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PizarraVirtual",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/pizarra.ico",
    version="version_info.txt",
)
