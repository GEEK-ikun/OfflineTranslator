# -*- coding: utf-8 -*-
"""源码态验收测试（不依赖图形界面）。

覆盖需求：双向翻译、自动识别、长文本分句、空输入、纯符号输入、
模型缺失时的友好报错、离线加载（用自带模型目录，不走网络）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from translator import (  # noqa: E402
    OfflineTranslator,
    TranslationError,
    block_network,
    detect_direction,
    split_sentences,
)

SAMPLES = [
    ("en", "Hello, how are you today?"),
    ("en", "This software works completely offline."),
    ("en", "The quick brown fox jumps over the lazy dog."),
    ("en", "Please restart your computer to finish the update."),
    ("en", "Machine translation quality depends on the training data."),
    ("zh", "你好，今天过得怎么样？"),
    ("zh", "这个软件完全离线运行。"),
    ("zh", "请重启电脑以完成更新。"),
    ("zh", "机器翻译的质量取决于训练数据。"),
    ("zh", "我喜欢在早上去公园跑步。"),
]


def main() -> int:
    block_network()
    engine = OfflineTranslator()
    status = engine.check_pairs(refresh=True)
    print(f"模型检查: en->zh={status.en2zh}  zh->en={status.zh2en}")
    if status.error:
        print("模型错误:", status.error)
    if not (status.en2zh and status.zh2en):
        print("FAIL: 双向模型不完整")
        return 2

    failures = 0
    print("\n=== 双向翻译测试 ===")
    for index, (lang, text) in enumerate(SAMPLES, start=1):
        expect = "en2zh" if lang == "en" else "zh2en"
        got_dir = detect_direction(text)
        started = time.perf_counter()
        try:
            result, direction, elapsed = engine.translate(text, mode="auto")
        except TranslationError as exc:
            print(f"[{index}] ERROR {exc}")
            failures += 1
            continue
        wall = time.perf_counter() - started
        ok_dir = "OK" if direction == expect else f"BAD(expect {expect})"
        print(f"[{index}] {lang}->{expect} dir={ok_dir} t={wall:.2f}s")
        print(f"     源: {text}")
        print(f"     译: {result}")
        if direction != expect or not result.strip():
            failures += 1
        if wall > 2.0 and index > 2:  # 首句含模型加载时间
            print(f"     注意: 单句耗时 {wall:.2f}s 超过 2 秒指标")

    print("\n=== 分句测试 ===")
    long_text = (
        "Artificial intelligence is changing the world. "
        "It helps doctors diagnose diseases. "
        "It also helps students learn faster.\n"
        "But we must use it carefully."
    )
    chunks = split_sentences(long_text)
    print(f"长文本 {len(long_text)} 字符 -> {len(chunks)} 段")
    for c in chunks:
        print("   ·", c)
    if len(chunks) < 3:
        print("FAIL: 分句异常")
        failures += 1

    print("\n=== 长文本翻译（进度回调）===")
    seen = []
    result, direction, elapsed = engine.translate(
        long_text, mode="en2zh", progress=lambda d, t, m: seen.append((d, t))
    )
    print(f"方向={direction} 耗时={elapsed:.2f}s 进度事件={len(seen)}")
    print("译文：")
    print(result)
    if not result.strip():
        failures += 1

    print("\n=== 边界情况 ===")
    cases = [
        ("空输入", "", "请输入要翻译的文本"),
        ("纯空格", "   ", "请输入要翻译的文本"),
    ]
    for name, text, expect_msg in cases:
        try:
            engine.translate(text)
            print(f"FAIL: {name} 未报错")
            failures += 1
        except TranslationError as exc:
            ok = expect_msg in str(exc)
            print(f"{'OK  ' if ok else 'FAIL'} {name} -> {exc}")
            if not ok:
                failures += 1
    symbols = "12345 !!! ###"
    out, direction, _ = engine.translate(symbols)
    print(f"{'OK  ' if out == symbols else 'FAIL'} 纯符号/数字原样返回 -> {out!r}")
    if out != symbols:
        failures += 1

    print("\n=== 手动指定方向优先 ===")
    out, direction, _ = engine.translate("Hello world", mode="zh2en")
    print(f"强制 zh2en 时 direction={direction}（应为 zh2en）")
    if direction != "zh2en":
        failures += 1

    print("\n=== 连续 200 句压力测试 ===")
    sentence = "Offline translation keeps your text on your own computer."
    started = time.perf_counter()
    ok_count = 0
    for _ in range(200):
        try:
            engine.translate(sentence)
            ok_count += 1
        except Exception as exc:
            print("中断:", exc)
            break
    total = time.perf_counter() - started
    print(f"成功 {ok_count}/200 句，总耗时 {total:.1f}s，平均 {total / max(ok_count,1):.3f}s/句")
    if ok_count < 200:
        failures += 1

    print(f"\n=== 结果：{'全部通过' if failures == 0 else f'{failures} 项失败'} ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
