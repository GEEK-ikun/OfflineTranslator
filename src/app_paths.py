# -*- coding: utf-8 -*-
"""本地路径与运行环境解析。

设计约束（隐私相关）：本模块只解析本软件自己的目录，
不遍历、不扫描用户的其它文件夹。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "OfflineTranslator"
APP_CN_NAME = "离线英汉互译"
APP_VERSION = "1.0.0"


def is_frozen() -> bool:
    """是否为 PyInstaller 打包后运行。"""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """随程序分发的只读资源目录（模型、图标、许可证）。"""
    if is_frozen():
        # one-folder: exe 在 dist/OfflineTranslator/，随附文件在 _internal/
        exe_dir = Path(sys.executable).resolve().parent
        internal = exe_dir / "_internal"
        if internal.is_dir():
            return internal
        return Path(getattr(sys, "_MEIPASS", exe_dir))
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """程序本体所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    """离线翻译模型目录。"""
    override = os.environ.get("OFFLINETRANSLATOR_MODELS")
    if override:
        return Path(override)
    candidates = [
        resource_dir() / "models",
        app_dir() / "models",
    ]
    for c in candidates:
        if (c / "packages").is_dir() or c.is_dir():
            return c
    return candidates[0]


def packages_dir() -> Path:
    return models_dir() / "packages"


def user_data_dir() -> Path:
    """本机用户数据目录（配置、历史、日志）。只写这里。

    可用环境变量 OFFLINETRANSLATOR_DATA_DIR 覆盖（便于便携使用或自动化测试）。
    默认为 %APPDATA%\\OfflineTranslator，不会写到其它地方。
    """
    override = os.environ.get("OFFLINETRANSLATOR_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / APP_NAME


def logs_dir() -> Path:
    return user_data_dir() / "logs"


def config_path() -> Path:
    return user_data_dir() / "config.json"


def history_path() -> Path:
    return user_data_dir() / "history.json"


def log_path() -> Path:
    return logs_dir() / "app.log"


def ensure_user_dirs() -> None:
    logs_dir().mkdir(parents=True, exist_ok=True)
