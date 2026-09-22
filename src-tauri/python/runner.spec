# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import playwright

block_cipher = None

playwright_pkg_dir = os.path.dirname(playwright.__file__)
playwright_driver_dir = os.path.join(playwright_pkg_dir, 'driver')

a = Analysis(
    ['runner.py'],
    pathex=[],
    binaries=[],
    datas=[
        (playwright_driver_dir, 'playwright/driver'),
        ('src', 'src'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'src.browser',
        'src.approver',
        'src.tencent_form',
        'src.webhook',
        'src.registration',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'PIL', 'scipy', 'pandas', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ApprovalRunner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='ApprovalRunner'
)
