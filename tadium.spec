# -*- mode: python ; coding: utf-8 -*-
# Tadium PyInstaller spec
# Bundles: main.py, index.html, assets, llama_cpp shared libs

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

block_cipher = None

# Collect llama_cpp native binaries
llama_binaries = collect_dynamic_libs('llama_cpp')
llama_datas    = collect_data_files('llama_cpp')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=llama_binaries,
    datas=[
        ('index.html',  '.'),
        ('icon.png',    '.'),
        ('tadium.png',  '.'),
        ('light.ttf',   '.'),
        ('bold.ttf',    '.'),
        *llama_datas,
    ],
    hiddenimports=[
        'llama_cpp',
        'llama_cpp.llama',
        'llama_cpp.llama_cpp',
        'webview',
        'webview.platforms.winforms',
        'pyautogui',
        'pyperclip',
        'PIL',
        'PIL.ImageGrab',
        'playwright',
        'playwright.sync_api',
        'clr',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Tadium',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.png',  # Uncomment after converting to .ico for Windows builds
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Tadium',
)
