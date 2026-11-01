# -*- coding: utf-8 -*-
"""历史记录（只存本机 %APPDATA%\\OfflineTranslator\\history.json，绝不上传）。"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import List

from app_paths import history_path


@dataclass
class HistoryItem:
    ts: float
    source: str
    target: str
    direction: str

    @property
    def time_text(self) -> str:
        return time.strftime("%m-%d %H:%M", time.localtime(self.ts))

    @property
    def preview(self) -> str:
        one = " ".join(self.source.split())
        return one if len(one) <= 42 else one[:42] + "…"


class History:
    def __init__(self, limit: int = 200) -> None:
        self.limit = limit
        self.items: List[HistoryItem] = []
        self.load()

    def load(self) -> None:
        path = history_path()
        self.items = []
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for row in raw if isinstance(raw, list) else []:
                try:
                    self.items.append(
                        HistoryItem(
                            ts=float(row["ts"]),
                            source=str(row["source"]),
                            target=str(row["target"]),
                            direction=str(row.get("direction", "")),
                        )
                    )
                except Exception:
                    continue
        except Exception:
            self.items = []

    def save(self) -> None:
        path = history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps([asdict(i) for i in self.items], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        tmp.replace(path)

    def add(self, source: str, target: str, direction: str) -> HistoryItem:
        item = HistoryItem(ts=time.time(), source=source, target=target, direction=direction)
        # 同原文去重：新记录置顶
        self.items = [i for i in self.items if i.source != source]
        self.items.insert(0, item)
        if len(self.items) > self.limit:
            self.items = self.items[: self.limit]
        self.save()
        return item

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]
            self.save()

    def clear(self) -> None:
        self.items = []
        self.save()
