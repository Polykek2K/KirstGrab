# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['KirstGrab.py'],
    pathex=[],
    binaries=[
        ('yt-dlp.exe', 'bin'),
        ('ffmpeg.exe', 'bin'),
        ('ffprobe.exe', 'bin'),
        ('ffplay.exe', 'bin'),
        ('avcodec-62.dll', 'bin'),
        ('avdevice-62.dll', 'bin'),
        ('avfilter-11.dll', 'bin'),
        ('avformat-62.dll', 'bin'),
        ('avutil-60.dll', 'bin'),
        ('swresample-6.dll', 'bin'),
        ('swscale-9.dll', 'bin'),
    ],
    datas=[
        ('images/background.png', 'images'),
        ('fonts/m6x11plus.ttf', 'fonts'),
        ('icon.ico', '.'),
        ('cookies.txt', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KirstGrab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
