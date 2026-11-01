# -*- coding: utf-8 -*-
"""必须在 import argostranslate 之前完成的离线环境设置。

argostranslate 1.11 在 import 阶段就会按 Python 官网默认约定创建
  ~/.local/share/argos-translate、~/.config/argos-translate、~/.local/cache/argos-translate
为了避免程序去动用户主目录以外的任何位置（也避免任何"自动下载"），
这里先把 XDG_* 与 ARGOS_* 环境变量指向本软件自己的目录。
"""
from __future__ import annotations

import os
from pathlib import Path

from app_paths import packages_dir, user_data_dir


def configure() -> Path:
    """设置离线运行所需的环境变量，返回模型包目录。"""
    pk = packages_dir()
    pk.mkdir(parents=True, exist_ok=True)
    data_root = user_data_dir() / "argos"

    # Argos 自身的数据/配置/缓存目录：全部收敛到本软件用户数据目录
    os.environ.setdefault("XDG_DATA_HOME", str(data_root / "share"))
    os.environ.setdefault("XDG_CONFIG_HOME", str(data_root / "config"))
    os.environ.setdefault("XDG_CACHE_HOME", str(data_root / "cache"))
    for sub in ("share", "config", "cache"):
        (data_root / sub).mkdir(parents=True, exist_ok=True)

    # 模型目录：只认本软件自带的 models/packages
    os.environ["ARGOS_PACKAGES_DIR"] = str(pk)
    os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(pk)   # 旧版本兼容

    # 只使用 CPU，避免任何 GPU 相关的探测
    os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")

    # 分句交给本程序自己处理（ARGOSTRANSLATE 是纯 Python 实现，不需要 stanza/torch）
    os.environ["ARGOS_CHUNK_TYPE"] = "ARGOSTRANSLATE"

    # 包索引指向本机不存在的地址：本软件不允许联网更新模型
    os.environ["ARGOS_PACKAGE_INDEX"] = "http://127.0.0.1/offline-no-package-index/"

    # 线程数：桌面场景下保持响应，避免吃满 CPU
    os.environ.setdefault("ARGOS_INTER_THREADS", "1")
    os.environ.setdefault("ARGOS_INTRA_THREADS", "0")

    return pk
