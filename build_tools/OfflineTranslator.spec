# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（one-folder）。

产物：dist/OfflineTranslator/OfflineTranslator.exe
随附：models/packages（离线中英模型）、assets（图标 + 第三方许可证）

隐私说明：本配置不打包任何联网上报组件；程序运行期由代码中的 socket 硬阻断保证离线。
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("OFFLINETRANSLATOR_ROOT", os.getcwd())).resolve()
SRC = ROOT / "src"
MODELS = ROOT / "models"
ASSETS = ROOT / "assets"
VERSION = "1.0.0"

datas = []
if MODELS.is_dir():
    datas.append((str(MODELS), "models"))
if ASSETS.is_dir():
    datas.append((str(ASSETS), "assets"))

hiddenimports = [
    "argostranslate",
    "argostranslate.package",
    "argostranslate.translate",
    "argostranslate.settings",
    "argostranslate.utils",
    "argostranslate.sbd",
    "argostranslate.networking",
    "ctranslate2",
    "sentencepiece",
    "sacremoses",
    "filelock",
    "packaging",
]

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 联网相关（本软件完全离线，不打包任何 HTTP 客户端）
        "requests",
        "urllib3",
        "httpx",
        "httpcore",
        "h11",
        "anyio",
        "certifi",
        "idna",
        # 体积大且本程序不需要的组件：
        #   onnxruntime / minisbd 是 Argos 的 MiniSBD 分句方案（模型需联网下载），
        #   torch / spacy / stanza 是 Argos 的另外两种分句方案；
        #   本程序使用自带的离线分句器（src/translator.py 的 OfflineSentencizer），
        #   并在导入 Argos 前为上述可选组件放入占位模块。
        "onnxruntime",
        "minisbd",
        "torch",
        "spacy",
        "thinc",
        "stanza",
        "transformers",
        # 其它无关的大件
        "matplotlib",
        "IPython",
        "notebook",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OfflineTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 图形界面程序，不弹黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "icon.ico"),
    version=str(ROOT / "build_tools" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OfflineTranslator",
)
