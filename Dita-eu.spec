# -*- mode: python ; coding: utf-8 -*-
import os

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('icon.png', '.'),
        ('icon_white.png', '.'),
        ('radio-mic.svg', '.'),
        ('venv/Lib/site-packages/faster_whisper/assets', 'faster_whisper/assets')
    ],
    hiddenimports=[
        'config_manager', 'settings_ui', 'audio_recorder', 'transcriber',
        'injector', 'overlay', 'local_transcriber', 'faster_whisper',
        'onnxruntime', 'ctranslate2'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# CORREÇÃO CRÍTICA DO APPCRASH c0000005 (MSVCP140.dll):
# O PyInstaller coletava cópias obsoletas de msvcp140.dll e vcruntime140.dll
# de pastas secundárias no PATH (como Adoptium JDK e PyQt5/Qt5/bin), que entravam
# em conflito com as exigências modernas do onnxruntime/ctranslate2.
# 1. Removemos todas as cópias antigas coletadas.
# 2. Forçamos o uso exclusivo das DLLs do runtime oficial mais moderno de C:\Windows\System32.
system32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
official_msvc_dlls = ['msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll']

filtered_binaries = []
msvc_names = {d.lower() for d in official_msvc_dlls}

for dest, src, kind in a.binaries:
    base = os.path.basename(dest).lower()
    if base in msvc_names:
        continue  # descarta qualquer versão conflitante (ex.: do JDK ou PyQt5)
    filtered_binaries.append((dest, src, kind))

# Injeta as DLLs modernas oficiais diretamente na raiz do executável
for dll in official_msvc_dlls:
    src_path = os.path.join(system32, dll)
    if os.path.exists(src_path):
        filtered_binaries.append((dll, src_path, 'BINARY'))

a.binaries = filtered_binaries

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Dita-eu',
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
