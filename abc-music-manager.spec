# -*- mode: python ; coding: utf-8 -*-
# ABC Music Manager — PyInstaller spec for bundling with TinySoundFont and PyAudio.

import os
block_cipher = None
docs_datas = [(os.path.join('docs', f), 'docs') for f in os.listdir('docs')
              if os.path.isfile(os.path.join('docs', f))]

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('NOTICE.txt', '.'),
        ('README.md', '.'),  # For Help > User Guide when frozen
        ('LICENSE.txt', '.'),
        ('PROJECT_BRIEF.md', '.'),
        ('REQUIREMENTS.md', '.'),
        ('DATA_MODEL.md', '.'),
        ('DECISIONS.md', '.'),
        ('SCHEMA.md', '.'),
        ('licenses/LGPL-3.0.txt', 'licenses'),
    ] + docs_datas,
    hiddenimports=['tinysoundfont', 'pyaudio'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ABC Music Manager',
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
)
