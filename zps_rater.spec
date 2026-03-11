# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec pro ZPS X Photo Rater
#
# Sestavení:
#   pip install pyinstaller
#   pyinstaller zps_rater.spec
#
# Výsledek je ve složce dist/ZpsXPhotoRater/
# (--onedir je rychlejší než --onefile, protože subprocesy znovu
#  nerozbalují celý archiv; pro distribuci stačí zazipovat celou složku)

from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821  (SPECPATH je injektován PyInstallerem)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Přibal složku prompts/ — rate_with_ai.py ji čte za běhu
        (str(ROOT / "prompts"), "prompts"),
    ],
    hiddenimports=[
        # rawpy linkuje nativní knihovny, PyInstaller je nemusí najít sám
        "rawpy",
        "rawpy._rawpy",
        # Pillow
        "PIL",
        "PIL.Image",
        "PIL.JpegImagePlugin",
        # Anthropic SDK
        "anthropic",
        # tkinter (na Windows bývá součástí Pythonu, ale explicitní import pomůže)
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.scrolledtext",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Vylučujeme věci, které určitě nepotřebujeme
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # --onedir: binárky nejdou přímo do exe
    name="ZpsXPhotoRater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # Žádné konzolové okno — čistě GUI aplikace
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # Sem lze přidat cestu k .ico souboru
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ZpsXPhotoRater",   # výstupní složka: dist/ZpsXPhotoRater/
)
