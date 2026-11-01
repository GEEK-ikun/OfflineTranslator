# -*- coding: utf-8 -*-
"""翻译引擎封装：Argos Translate + CTranslate2，完全离线。

隐私说明：
  * 本模块通过 socket 硬阻断（默认开启）保证运行期无法发起任何网络连接；
  * 模型全部从本软件自带的 models/packages 目录加载，程序内不存在模型下载逻辑；
  * 除了读取自带模型目录和本软件用户数据目录，不读取其它任何文件。
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from app_paths import packages_dir, user_data_dir

# ---------------------------------------------------------------------------
# 1) 先把 Argos 的目录指向本软件自带模型目录（必须在 import argostranslate 之前）
# ---------------------------------------------------------------------------
_PK = packages_dir()
try:
    from argos_env import configure as _configure_argos_env

    _PK = _configure_argos_env()
except Exception:  # pragma: no cover - 环境设置失败时退回最基本的设置
    _PK.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGES_DIR"] = str(_PK)
    os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")


# ---------------------------------------------------------------------------
# 2) 网络硬阻断（隐私红线：运行期不得发起任何网络请求）
# ---------------------------------------------------------------------------
_blocked = False


def block_network() -> None:
    """阻断本进程所有出站 socket 连接。

    这是隐私保证的强制措施：即使某个依赖偷偷尝试联网，也只会得到一个本地异常。
    设置环境变量 OFFLINETRANSLATOR_ALLOW_NETWORK=1 可关闭（仅用于开发调试）。
    """
    global _blocked
    if os.environ.get("OFFLINETRANSLATOR_ALLOW_NETWORK") == "1":
        return
    if _blocked:
        return
    import socket

    def _deny(*_args, **_kwargs):
        raise OSError("[离线保护] 本软件已禁用网络访问")

    try:
        socket.socket.connect = _deny          # type: ignore[assignment]
        socket.socket.connect_ex = _deny       # type: ignore[assignment]
        socket.create_connection = _deny       # type: ignore[assignment]
        try:
            socket.socket.sendto = _deny       # type: ignore[assignment]
        except Exception:
            pass
        _blocked = True
    except Exception:
        pass


def network_blocked() -> bool:
    return _blocked


# ---------------------------------------------------------------------------
# 3) 语言判断与分句
# ---------------------------------------------------------------------------
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN = re.compile(r"[A-Za-z]")
_SENT_END = re.compile(r"(?<=[。！？!?；;])|(?<=[.])(?=\s)|\n+")


def detect_direction(text: str) -> str:
    """返回 'en2zh' 或 'zh2en'。中文（CJK）字符占多数判为中文。"""
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    if cjk == 0:
        return "en2zh"
    if latin == 0:
        return "zh2en"
    return "zh2en" if cjk >= latin else "en2zh"


def has_translatable_content(text: str) -> bool:
    return bool(_CJK.search(text) or _LATIN.search(text))


def split_sentences(text: str, max_chars: int = 400) -> List[str]:
    """按标点/换行分句，并把过长的句子再按长度切开。"""
    pieces: List[str] = []
    for line in _SENT_END.split(text):
        if line is None:
            continue
        pieces.extend(line.split("\n"))
    chunks: List[str] = []
    for p in pieces:
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_chars:
            chunks.append(p)
            continue
        # 过长：优先在空格处断开（英文），否则按长度硬切（中文）
        start = 0
        while start < len(p):
            end = min(start + max_chars, len(p))
            if end < len(p):
                sp = p.rfind(" ", start, end)
                if sp > start + max_chars // 2:
                    end = sp
            chunks.append(p[start:end].strip())
            start = end
    return chunks


@dataclass
class PairStatus:
    """语言对可用性。"""
    en2zh: bool = False
    zh2en: bool = False
    checked: bool = False
    error: str = ""


class TranslationError(RuntimeError):
    """翻译过程中的可预期错误（界面按中文提示展示）。"""


# ---------------------------------------------------------------------------
# 3.5) 离线分句器与 argostranslate 补丁
#
# argostranslate 1.11 自带的分句实现有两条路：
#   a) StanzaSentencizer —— 需要 torch（约 118MB）且随包仅提供 en / zh 分词器；
#   b) MiniSBDSentencizer —— 需要从 GitHub 下载 .onnx 模型（离线不可用）。
# 本程序自己已经实现了分句（见 split_sentences），因此这里把内部分句器替换成
# 「恒等分句器」：不会联网、不需要 torch，行为可预期。
# ---------------------------------------------------------------------------
class OfflineSentencizer:
    """恒等分句器：调用方已经完成分句，这里原样返回整段文本。"""

    def __init__(self, package=None) -> None:  # noqa: D401 - 与 Argos 接口签名保持一致
        self.package = package

    def split_sentences(self, text: str) -> List[str]:
        return [text]

    def __str__(self) -> str:
        return "OfflineSentencizer(本程序自带的离线分句)"


_STANZA_STUBBED = False


def _install_offline_stubs() -> None:
    """在 import argostranslate 之前，放入 stanza / minisbd 的占位模块。

    原因：argostranslate.sbd 会无条件 `import stanza` 和
    `from minisbd import SBDetect, models as minisbd_models`。
      * stanza 需要 torch（约 118MB），而官方模型包自带的分句器本程序用不到；
      * minisbd 需要 onnxruntime，并且它的 .onnx 模型是运行时从 GitHub 下载的，
        在完全离线的软件里不可用。
    本程序自己实现了分句（见 split_sentences），并替换了 Argos 的内部分句器，
    因此这里用最小占位模块保证导入成功；万一有人真的调用它们，会得到明确的中文
    错误提示，而不是静默联网下载。
    """
    global _STANZA_STUBBED
    if _STANZA_STUBBED:
        return
    import types

    def _unavailable(name: str):
        def _raise(*_args, **_kwargs):
            raise RuntimeError(
                f"本软件为完全离线版本，未包含 {name} 组件；分句由本程序自带的离线分句器完成。"
            )

        return _raise

    if "stanza" not in sys.modules:
        stanza = types.ModuleType("stanza")
        stanza.Pipeline = _unavailable("stanza")  # type: ignore[attr-defined]
        stanza.__doc__ = "占位模块（离线版 OfflineTranslator 提供）"
        sys.modules["stanza"] = stanza

    if "minisbd" not in sys.modules:
        minisbd = types.ModuleType("minisbd")
        minisbd.SBDetect = _unavailable("minisbd")  # type: ignore[attr-defined]
        models_mod = types.ModuleType("minisbd.models")
        models_mod.cache_dir = str(user_data_dir() / "argos" / "minisbd")
        models_mod.list_models = lambda: []  # type: ignore[attr-defined]
        models_mod.get_model_file = _unavailable("minisbd")  # type: ignore[attr-defined]
        models_mod.download_models = _unavailable("minisbd")  # type: ignore[attr-defined]
        minisbd.models = models_mod  # type: ignore[attr-defined]
        sys.modules["minisbd"] = minisbd
        sys.modules["minisbd.models"] = models_mod

    _STANZA_STUBBED = True


_PATCHED = False


def patch_argostranslate(argos_translate_module) -> None:
    """把 Argos 的分句器替换为离线实现（不改动第三方源码文件）。"""
    global _PATCHED
    if _PATCHED:
        return
    try:
        argos_translate_module.StanzaSentencizer = OfflineSentencizer
        argos_translate_module.MiniSBDSentencizer = OfflineSentencizer
        argos_translate_module.SpacySentencizerSmall = OfflineSentencizer
        _PATCHED = True
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 4) 实际的翻译封装
# ---------------------------------------------------------------------------
class OfflineTranslator:
    """懒加载的离线翻译器：界面启动时不加载模型，第一次翻译才加载。"""

    def __init__(self, packages: Optional[Path] = None) -> None:
        self.packages = Path(packages) if packages else _PK
        self._lock = threading.Lock()
        self._translations: dict = {}          # "en|zh" -> argostranslate Translation
        self._pair_status = PairStatus()
        self._load_error = ""

    # -- 内部：拿到 argostranslate 模块 -------------------------------------
    @staticmethod
    def _argos():
        try:
            _install_offline_stubs()
            import argostranslate.package as argos_package
            import argostranslate.translate as argos_translate
        except Exception as exc:  # pragma: no cover - 依赖缺失
            raise TranslationError(f"翻译引擎加载失败：{exc}") from exc
        patch_argostranslate(argos_translate)
        return argos_package, argos_translate

    # -- 模型可用性检查 -----------------------------------------------------
    def check_pairs(self, refresh: bool = False) -> PairStatus:
        if self._pair_status.checked and not refresh:
            return self._pair_status
        status = PairStatus(checked=True)
        try:
            argos_package, _ = self._argos()
            self._apply_package_dirs(argos_package)
            installed = argos_package.get_installed_packages()
            pairs = {(p.from_code, p.to_code) for p in installed}
            status.en2zh = ("en", "zh") in pairs
            status.zh2en = ("zh", "en") in pairs
            if not (status.en2zh or status.zh2en):
                status.error = (
                    f"未在模型目录找到中英翻译模型。\n模型目录：{self.packages}"
                )
        except TranslationError as exc:
            status.error = str(exc)
        except Exception as exc:
            status.error = f"读取模型目录失败：{exc}\n模型目录：{self.packages}"
        self._pair_status = status
        return status

    def _apply_package_dirs(self, argos_package) -> None:
        """把 Argos 的搜索路径指向自带模型目录（兼容不同版本）。"""
        targets: List[object] = [argos_package]
        for attr in ("settings", "package"):
            mod = getattr(argos_package, attr, None)
            if mod is not None:
                targets.append(mod)
        try:
            from argostranslate import settings as argos_settings
            targets.append(argos_settings)
        except Exception:
            pass
        try:
            import argostranslate as argos_root
            targets.append(argos_root)
            targets.append(getattr(argos_root, "settings", None))
        except Exception:
            pass
        for obj in targets:
            if obj is None:
                continue
            for attr in ("packages_dir_path", "package_dir_path", "packages_dir"):
                try:
                    if hasattr(obj, attr):
                        setattr(obj, attr, self.packages)
                except Exception:
                    pass

    # -- 取得指定语言对的翻译对象 ------------------------------------------
    def _get_translation(self, from_code: str, to_code: str):
        """按语言对取得翻译对象。

        兼容 Argos Translate 新旧两套 API：
          * 1.11+ ：argostranslate.translate.get_translation_from_codes()
          * 旧版本：Package.get_translation()
        """
        key = f"{from_code}|{to_code}"
        with self._lock:
            cached = self._translations.get(key)
            if cached is not None:
                return cached
            argos_package, argos_translate = self._argos()
            self._apply_package_dirs(argos_package)

            # 先确认模型确实存在，以便给出准确的中文提示
            try:
                installed = argos_package.get_installed_packages()
            except Exception as exc:
                raise TranslationError(f"读取模型目录失败：{exc}") from exc
            match = next(
                (
                    p
                    for p in installed
                    if p.from_code == from_code and p.to_code == to_code
                ),
                None,
            )
            if match is None:
                raise TranslationError(
                    "翻译模型缺失，请重新安装本软件。\n"
                    f"缺少：{from_code}->{to_code}\n模型目录：{self.packages}"
                )

            translation = None
            # 新 API
            getter = getattr(argos_translate, "get_translation_from_codes", None)
            if callable(getter):
                try:
                    translation = getter(from_code, to_code)
                except Exception:
                    translation = None
            # 旧 API 兜底
            if translation is None:
                try:
                    translation = match.get_translation()
                except Exception as exc:
                    raise TranslationError(
                        "翻译模型损坏，请重新安装本软件。\n"
                        f"详情：{exc}\n模型目录：{self.packages}"
                    ) from exc
            if translation is None:
                raise TranslationError(
                    "翻译模型无法加载，请重新安装本软件。\n"
                    f"模型：{from_code}->{to_code}\n模型目录：{self.packages}"
                )
            self._translations[key] = translation
            return translation

    def warm_up(self, direction: Optional[str] = None) -> None:
        """可选：预加载模型（后台线程调用，避免界面卡顿）。"""
        pairs = {"en2zh": ("en", "zh"), "zh2en": ("zh", "en")}
        for key, (f, t) in pairs.items():
            if direction and key != direction:
                continue
            try:
                self._get_translation(f, t)
            except TranslationError:
                pass

    # -- 主翻译入口 ---------------------------------------------------------
    def translate(
        self,
        text: str,
        mode: str = "auto",
        progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Tuple[str, str, float]:
        """翻译文本。

        返回 (译文, 使用的方向, 耗时秒)。
        mode: auto | en2zh | zh2en
        progress: 回调 (已完成句数, 总句数, 当前状态文字)
        """
        text = (text or "").strip()
        if not text:
            raise TranslationError("请输入要翻译的文本")
        if not has_translatable_content(text):
            # 只有符号/数字：原样返回，不报错
            return text, mode if mode != "auto" else "en2zh", 0.0

        direction = detect_direction(text) if mode == "auto" else mode
        from_code, to_code = ("en", "zh") if direction == "en2zh" else ("zh", "en")

        started = time.perf_counter()
        translation = self._get_translation(from_code, to_code)

        chunks = split_sentences(text)
        if not chunks:
            return "", direction, 0.0

        total = len(chunks)
        if progress:
            progress(0, total, "翻译中…")
        parts: List[str] = []
        for index, chunk in enumerate(chunks, start=1):
            try:
                if has_translatable_content(chunk):
                    out = translation.translate(chunk) or ""
                else:
                    out = chunk
            except Exception as exc:
                raise TranslationError(f"翻译失败：{exc}") from exc
            parts.append(out.strip())
            if progress:
                progress(index, total, f"翻译中… 第 {index}/{total} 句")

        # 按原句数合并：单句直接返回，多句用换行连接
        result = "\n".join(p for p in parts if p)
        elapsed = time.perf_counter() - started
        return result, direction, elapsed
