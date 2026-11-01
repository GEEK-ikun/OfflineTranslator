# -*- coding: utf-8 -*-
"""本地配置读写（config.json，只存本机，绝不上传）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

from app_paths import config_path

FONT_SIZES = {"小": 11, "中": 13, "大": 16}
MODE_AUTO = "auto"
MODE_EN2ZH = "en2zh"
MODE_ZH2EN = "zh2en"


@dataclass
class Config:
    default_mode: str = MODE_AUTO
    font_size_label: str = "中"
    auto_read_clipboard: bool = False
    history_limit: int = 200
    ui_language: str = "zh"
    show_history_panel: bool = True
    # 自动翻译：停止输入 delay 毫秒后自动翻译，无需点击「翻译」
    auto_translate: bool = True
    auto_translate_delay: int = 800

    @property
    def font_size(self) -> int:
        return FONT_SIZES.get(self.font_size_label, 13)


def load_config() -> Config:
    path = config_path()
    if not path.is_file():
        return Config()
    try:
        raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Config()
    cfg = Config()
    for key, value in raw.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    if cfg.default_mode not in (MODE_AUTO, MODE_EN2ZH, MODE_ZH2EN):
        cfg.default_mode = MODE_AUTO
    if cfg.font_size_label not in FONT_SIZES:
        cfg.font_size_label = "中"
    try:
        cfg.history_limit = max(20, min(2000, int(cfg.history_limit)))
    except Exception:
        cfg.history_limit = 200
    try:
        cfg.auto_translate_delay = max(200, min(3000, int(cfg.auto_translate_delay)))
    except Exception:
        cfg.auto_translate_delay = 800
    cfg.auto_translate = bool(cfg.auto_translate)
    return cfg


def save_config(cfg: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8"
    )
