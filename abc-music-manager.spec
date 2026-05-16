# -*- mode: python ; coding: utf-8 -*-
# ABC Music Manager — PyInstaller spec for bundling with TinySoundFont and PyAudio.

import os
import sys
block_cipher = None


def _exit_if_windows_dist_exe_locked():
    """PyInstaller replaces the output .exe via os.remove; that fails if the app is still running."""
    if sys.platform != "win32":
        return
    try:
        distpath = DISTPATH
    except NameError:
        return
    target = os.path.join(distpath, "ABC Music Manager.exe")
    if not os.path.isfile(target):
        return
    try:
        os.remove(target)
    except PermissionError:
        print(
            "\nCannot rebuild: the previous build is still locked:\n"
            f"  {os.path.abspath(target)}\n\n"
            "Close any running ABC Music Manager (Task Manager if needed), then rebuild.\n"
            "Or delete/rename that .exe manually and run PyInstaller again.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)


docs_datas = [(os.path.join('docs', f), 'docs') for f in os.listdir('docs')
              if os.path.isfile(os.path.join('docs', f))]


def _set_play_relay_worker_datas():
    """Bundle Cloudflare worker template (no node_modules) for deploy wizard."""
    out = []
    root = os.path.join('workers', 'set-play-relay')
    if not os.path.isdir(root):
        return out
    skip_dirnames = {'node_modules', '.wrangler'}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirnames]
        low = dirpath.replace('\\', '/').lower()
        if '/.cache/' in low or low.endswith('/.cache'):
            continue
        for fn in filenames:
            if 'wrangler-account' in fn:
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, root)
            dest_dir = os.path.join('workers', 'set-play-relay', os.path.dirname(rel))
            if os.sep != '/':
                dest_dir = dest_dir.replace(os.sep, '/')
            out.append((src, dest_dir))
    return out


set_play_worker_datas = _set_play_relay_worker_datas()

_exit_if_windows_dist_exe_locked()

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
        ('resources/icons', 'resources/icons'),
    ] + docs_datas + set_play_worker_datas,
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

_app_icon = os.path.join(
    'resources',
    'icons',
    'app.icns' if sys.platform == 'darwin' else 'app.ico',
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
    icon=_app_icon,
)
