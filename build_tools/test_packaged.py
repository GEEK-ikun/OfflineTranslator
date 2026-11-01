# -*- coding: utf-8 -*-
"""对打包后的 exe 做「脱离 venv」的验收测试。

用法： python build_tools\test_packaged.py <安装目录或dist目录>
它会用 <目录>\OfflineTranslator.exe 以 --selftest 模式运行离线翻译自检。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python build_tools/test_packaged.py <目录>")
        return 2
    target = Path(sys.argv[1])
    exe = target / "OfflineTranslator.exe"
    if not exe.is_file():
        print(f"FAIL: 找不到 {exe}")
        return 2
    print(f"运行: {exe} --selftest")
    proc = subprocess.run(
        [str(exe), "--selftest"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    print("--- stdout ---")
    print(proc.stdout)
    if proc.stderr.strip():
        print("--- stderr ---")
        print(proc.stderr)
    print(f"--- exit code: {proc.returncode} ---")
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
