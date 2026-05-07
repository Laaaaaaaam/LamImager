import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hidden_imports = collect_submodules('uvicorn') + collect_submodules('aiosqlite') + [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'aiosqlite',
    'desktop',
    'desktop.main',
    'desktop.server',
    'desktop.tray',
    'desktop.updater',
    'pystray',
    'pystray._win32',
    'webview',
    'webview.platforms',
    'webview.platforms.winforms',
    'filelock',
]

datas = [
    ('frontend/dist', 'frontend/dist'),
    ('desktop/assets', 'desktop/assets'),
]

excludes = [
    'tkinter',
    'test',
    'unittest',
    'pytest',
    'setuptools',
    'pip',
    'wheel',
]

a = Analysis(
    ['desktop/main.py'],
    pathex=['backend'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name='LamImager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='desktop/assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LamImager',
)
