# -*- coding: utf-8 -*-
"""离线英汉互译 —— Tkinter 图形界面主程序。

隐私声明：
  * 全程离线运行，运行期通过 socket 硬阻断任何网络连接；
  * 只在 %APPDATA%\\OfflineTranslator 下写配置/历史/日志，不上传任何内容；
  * 不读取与翻译无关的文件，不采集设备信息，不含任何遥测或广告。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import queue
import sys
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_paths import (
    APP_CN_NAME,
    APP_NAME,
    APP_VERSION,
    app_dir,
    ensure_user_dirs,
    is_frozen,
    log_path,
    models_dir,
)
from config import (
    FONT_SIZES,
    MODE_AUTO,
    MODE_EN2ZH,
    MODE_ZH2EN,
    Config,
    load_config,
    save_config,
)
from history import History
from translator import (
    OfflineTranslator,
    TranslationError,
    block_network,
    network_blocked,
)

# ---------------------------------------------------------------------------
# 单实例控制（重复启动时激活已有窗口，不重复开进程）
# ---------------------------------------------------------------------------
MUTEX_NAME = "Local\\OfflineTranslator_SingleInstance_v1"
_mutex_handle = None


def acquire_single_instance() -> bool:
    global _mutex_handle
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        last_error = ctypes.get_last_error()
        if not handle:
            return True
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            return False
        _mutex_handle = handle
        return True
    except Exception:
        return True


def activate_existing_window() -> None:
    """把已在运行的窗口拉到前台。"""
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = user32.FindWindowW(None, f"{APP_CN_NAME} OfflineTranslator {APP_VERSION}")
        if not hwnd:
            hwnd = user32.FindWindowW(None, APP_CN_NAME)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 日志（只写本机）
# ---------------------------------------------------------------------------
def setup_logging() -> logging.Logger:
    ensure_user_dirs()
    logger = logging.getLogger("offline-translator")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            log_path(), maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)
    return logger


LOG = setup_logging()

PAD = 8


class TranslatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg: Config = load_config()
        self.history = History(limit=self.cfg.history_limit)
        self.engine = OfflineTranslator()
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False
        self.last_direction = ""
        self._history_rows: list = []
        # 自动翻译相关状态
        self._auto_job = None            # after() 句柄，用于输入防抖
        self._last_translated = ""       # 上次已翻译的原文，避免重复翻译
        self._req_id = 0                 # 请求序号，用于丢弃过期结果

        self.title(f"{APP_CN_NAME} OfflineTranslator {APP_VERSION}")
        self.geometry("980x660")
        self.minsize(820, 500)
        self._set_icon()

        self._build_menu()
        self._build_ui()
        self._apply_font()
        self._bind_keys()
        self._refresh_history_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.cfg.auto_translate:
            self.status_var.set("就绪｜输入后会自动翻译")
        else:
            self.status_var.set("就绪（首次翻译需加载模型，请稍候）")
        self.after(120, self._drain_events)
        if self.cfg.auto_read_clipboard:
            self.after(300, self.read_clipboard)

    # ------------------------------------------------------------------ 图标
    def _set_icon(self) -> None:
        try:
            icon = app_dir() / "assets" / "icon.ico"
            if not icon.is_file():
                icon = app_dir() / "_internal" / "assets" / "icon.ico"
            if icon.is_file():
                self.iconbitmap(default=str(icon))
        except Exception:
            pass

    # ------------------------------------------------------------------ 菜单
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="导出译文为 TXT…", command=self.export_target)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.on_close)
        menubar.add_cascade(label="文件", menu=m_file)

        m_set = tk.Menu(menubar, tearoff=0)
        m_set.add_command(label="设置…", command=self.open_settings)
        m_set.add_command(label="显示 / 隐藏历史记录栏", command=self.toggle_history_panel)
        menubar.add_cascade(label="设置", menu=m_set)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="关于 / 隐私说明", command=self.open_about)
        m_help.add_command(label="打开日志目录", command=self.open_log_dir)
        menubar.add_cascade(label="帮助", menu=m_help)

        self.config(menu=menubar)

    # -------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            pass

        # ---- 顶部：模式选择 + 操作按钮 ----
        top = ttk.Frame(self, padding=(PAD, PAD, PAD, 0))
        top.pack(fill="x")
        ttk.Label(top, text="翻译方向：").pack(side="left")
        self.mode_var = tk.StringVar(value=self.cfg.default_mode)
        for text, value in (
            ("自动识别", MODE_AUTO),
            ("英 → 中", MODE_EN2ZH),
            ("中 → 英", MODE_ZH2EN),
        ):
            ttk.Radiobutton(
                top, text=text, value=value, variable=self.mode_var,
                command=self.on_mode_changed,
            ).pack(side="left", padx=(2, 6))
        ttk.Button(top, text="互换方向", width=10, command=self.swap_direction).pack(
            side="left", padx=(10, 0)
        )
        self.auto_var = tk.BooleanVar(value=bool(self.cfg.auto_translate))
        ttk.Checkbutton(
            top,
            text="自动翻译",
            variable=self.auto_var,
            command=self.on_auto_toggle,
        ).pack(side="left", padx=(12, 0))
        self.offline_badge = ttk.Label(
            top,
            text="离线模式" + ("（已阻断网络）" if network_blocked() else ""),
            foreground="#0a7d28",
        )
        self.offline_badge.pack(side="right")

        # ---- 中部：翻译区 + 历史面板 ----
        splitter = ttk.PanedWindow(self, orient="horizontal")
        splitter.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        center = ttk.Frame(splitter)
        splitter.add(center, weight=4)

        panes = ttk.PanedWindow(center, orient="horizontal")
        panes.pack(fill="both", expand=True)

        # 左：原文
        left = ttk.LabelFrame(panes, text="原文", padding=6)
        panes.add(left, weight=1)
        self.src_text = tk.Text(left, wrap="word", undo=True, height=14)
        src_sb = ttk.Scrollbar(left, orient="vertical", command=self.src_text.yview)
        self.src_text.configure(yscrollcommand=src_sb.set)
        self.src_text.pack(side="left", fill="both", expand=True)
        src_sb.pack(side="right", fill="y")

        # 右：译文
        right = ttk.LabelFrame(panes, text="译文", padding=6)
        panes.add(right, weight=1)
        self.dst_text = tk.Text(right, wrap="word", height=14, background="#fbfbfb")
        dst_sb = ttk.Scrollbar(right, orient="vertical", command=self.dst_text.yview)
        self.dst_text.configure(yscrollcommand=dst_sb.set)
        self.dst_text.pack(side="left", fill="both", expand=True)
        dst_sb.pack(side="right", fill="y")
        self.dst_text.configure(state="disabled")

        # ---- 操作按钮行 ----
        actions = ttk.Frame(center)
        actions.pack(fill="x", pady=(PAD, 0))
        self.translate_btn = ttk.Button(
            actions, text="翻译 (Ctrl+Enter)", command=self.start_translate
        )
        self.translate_btn.pack(side="left")
        ttk.Button(actions, text="复制译文", command=self.copy_target).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="清空", command=self.clear_all).pack(side="left")
        ttk.Button(actions, text="从剪贴板读取", command=self.read_clipboard).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="导出译文 TXT", command=self.export_target).pack(
            side="left"
        )
        self.progress = ttk.Progressbar(actions, mode="determinate", length=160)
        self.progress.pack(side="right")

        # 历史面板
        self.history_frame = ttk.LabelFrame(splitter, text="历史记录（本机保存）", padding=6)
        splitter.add(self.history_frame, weight=0)
        self.history_list = tk.Listbox(
            self.history_frame, activestyle="none", exportselection=False, width=26
        )
        h_sb = ttk.Scrollbar(
            self.history_frame, orient="vertical", command=self.history_list.yview
        )
        self.history_list.configure(yscrollcommand=h_sb.set)
        self.history_list.pack(side="left", fill="both", expand=True)
        h_sb.pack(side="right", fill="y")
        self.history_list.bind("<<ListboxSelect>>", self.on_history_select)

        h_btns = ttk.Frame(self.history_frame)
        h_btns.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(h_btns, text="删除选中", command=self.delete_history_selected).pack(
            side="left"
        )
        ttk.Button(h_btns, text="清空历史", command=self.clear_history).pack(
            side="left", padx=6
        )

        if not self.cfg.show_history_panel:
            try:
                splitter.forget(self.history_frame)
            except Exception:
                pass

        # ---- 底部状态栏 ----
        status = ttk.Frame(self, padding=(PAD, 4, PAD, 6))
        status.pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        self.count_var = tk.StringVar(value="字符数：0")
        ttk.Label(status, textvariable=self.count_var, anchor="e").pack(side="right")
        self.src_text.bind("<KeyRelease>", self.on_source_changed)
        self.src_text.bind("<<Paste>>", lambda e: self.after(10, self.on_source_changed))
        self.src_text.bind("<<Cut>>", lambda e: self.after(10, self.on_source_changed))

    def _apply_font(self) -> None:
        size = self.cfg.font_size
        for widget in (self.src_text, self.dst_text):
            widget.configure(font=("Microsoft YaHei UI", size))

    def _bind_keys(self) -> None:
        self.bind_all("<Control-Return>", lambda e: (self.start_translate(), "break")[1])
        self.bind_all("<Control-Shift-T>", lambda e: self.toggle_topmost())
        self.bind_all("<Control-Shift-S>", lambda e: self.swap_direction())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------------------------------------------------- 小工具
    def _update_count(self, _event=None) -> None:
        self.count_var.set(f"字符数：{len(self.src_text.get('1.0', 'end-1c'))}")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def set_target(self, text: str) -> None:
        self.dst_text.configure(state="normal")
        self.dst_text.delete("1.0", "end")
        self.dst_text.insert("1.0", text)
        self.dst_text.configure(state="disabled")

    def get_target(self) -> str:
        return self.dst_text.get("1.0", "end-1c")

    def toggle_topmost(self) -> None:
        self.attributes("-topmost", not bool(self.attributes("-topmost")))
        self.set_status("窗口置顶：" + ("开" if self.attributes("-topmost") else "关"))

    def on_mode_changed(self) -> None:
        """切换翻译方向后，重新按新方向翻译当前内容。"""
        self._last_translated = ""
        if self.cfg.auto_translate:
            self.schedule_auto_translate()
        else:
            self.set_status("已切换翻译方向，点击「翻译」或按 Ctrl+Enter 重新翻译")

    def toggle_history_panel(self) -> None:
        """显示 / 隐藏历史记录栏（状态会保存到配置）。"""
        splitter = self.history_frame.master
        shown = bool(self.history_frame.winfo_ismapped())
        try:
            if shown:
                splitter.forget(self.history_frame)
                self.set_status("已隐藏历史记录栏")
            else:
                splitter.add(self.history_frame, weight=0)
                self.set_status("已显示历史记录栏")
        except Exception as exc:
            self.set_status(f"切换历史记录栏失败：{exc}")
            return
        self.cfg.show_history_panel = not shown

    def read_clipboard(self) -> None:
        """只在用户点击按钮或开启该设置时读取剪贴板。"""
        try:
            data = self.clipboard_get()
        except Exception:
            data = ""
        if data:
            self.src_text.delete("1.0", "end")
            self.src_text.insert("1.0", data)
            self._last_translated = ""
            self.on_source_changed()
            self.set_status("已从剪贴板读取文本，正在自动翻译…")
        else:
            self.set_status("剪贴板没有文本内容")

    def copy_target(self) -> None:
        text = self.get_target().strip()
        if not text:
            self.set_status("还没有译文可复制")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status("译文已复制到剪贴板")

    def clear_all(self) -> None:
        self.cancel_auto_job()
        self.src_text.delete("1.0", "end")
        self.set_target("")
        self._last_translated = ""
        self.progress["value"] = 0
        self._update_count()
        self.set_status("已清空")

    def swap_direction(self) -> None:
        current = self.mode_var.get()
        if current == MODE_EN2ZH:
            self.mode_var.set(MODE_ZH2EN)
        elif current == MODE_ZH2EN:
            self.mode_var.set(MODE_EN2ZH)
        # 顺手把原文/译文对调，方便双向修改
        src = self.src_text.get("1.0", "end-1c")
        dst = self.get_target()
        if dst.strip():
            self.src_text.delete("1.0", "end")
            self.src_text.insert("1.0", dst)
            self.set_target(src)
        self._last_translated = ""
        self._update_count()
        self.set_status("已互换方向")
        if self.cfg.auto_translate:
            self.schedule_auto_translate()

    def export_target(self) -> None:
        text = self.get_target()
        if not text.strip():
            self.set_status("还没有译文可导出")
            return
        path = filedialog.asksaveasfilename(
            title="导出译文",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="译文.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.set_status(f"已导出：{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", f"无法写入文件：\n{exc}")

    # -------------------------------------------------------------- 翻译流程
    def start_translate(self, auto: bool = False) -> None:
        """开始翻译。auto=True 表示由自动翻译触发（不做二次确认弹窗）。"""
        text = self.src_text.get("1.0", "end-1c").strip()

        if not text:
            if auto:
                return
            self.set_status("请输入要翻译的文本")
            return
        # 已经翻译过同样内容就不再重复（除非用户手动点按钮）
        if auto and text == self._last_translated:
            return
        if len(text) > 20000:
            if auto:
                self.set_status(
                    f"文本 {len(text)} 字符，已超过自动翻译上限（20000），请点击「翻译」按钮手动翻译"
                )
                return
            if not messagebox.askyesno(
                "文本较长",
                f"当前文本 {len(text)} 字符，超过 20000 字符。\n"
                "程序会自动分句逐句翻译，可能需要较长时间，是否继续？",
            ):
                return

        self._req_id += 1
        req_id = self._req_id
        self.busy = True
        self.translate_btn.configure(state="disabled")
        self.progress.configure(
            mode=("determinate" if auto else "indeterminate"), value=0
        )
        if not auto:
            self.progress.start(60)
        self.set_status("正在翻译…（首次翻译需加载模型，请稍候）")
        mode = self.mode_var.get()
        threading.Thread(
            target=self._translate_worker, args=(text, mode, req_id), daemon=True
        ).start()

    def _translate_worker(self, text: str, mode: str, req_id: int) -> None:
        try:
            result, direction, elapsed = self.engine.translate(
                text,
                mode=mode,
                progress=lambda done, total, msg: self.events.put(
                    ("progress", req_id, done, total, msg)
                ),
            )
            self.events.put(("done", req_id, text, result, direction, elapsed))
        except TranslationError as exc:
            self.events.put(("error", req_id, str(exc), False))
        except Exception as exc:  # 未预期错误
            LOG.error("翻译异常: %s\n%s", exc, traceback.format_exc())
            self.events.put(
                ("error", req_id, f"发生未预期错误：{exc}\n详情已写入日志。", True)
            )

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _, req_id, done, total, msg = event
                    if req_id != self._req_id:      # 过期请求：直接丢弃
                        continue
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=max(total, 1))
                    self.progress["value"] = done
                    self.set_status(msg)
                elif kind == "done":
                    _, req_id, source, result, direction, elapsed = event
                    if req_id != self._req_id:
                        continue
                    self._finish_success(source, result, direction, elapsed)
                elif kind == "error":
                    _, req_id, message, unexpected = event
                    if req_id != self._req_id:
                        continue
                    self._finish_error(message, unexpected)
        except queue.Empty:
            pass
        self.after(120, self._drain_events)

    def _finish_success(self, source: str, result: str, direction: str, elapsed: float) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=self.progress["maximum"])
        self.set_target(result)
        self.last_direction = direction
        self._last_translated = source
        arrow = "英→中" if direction == "en2zh" else "中→英"
        self.set_status(f"完成｜模型：{direction}（{arrow}）｜耗时 {elapsed:.2f} 秒")
        self.history.limit = self.cfg.history_limit
        self.history.add(source, result, direction)
        self._refresh_history_list()
        self.busy = False
        self.translate_btn.configure(state="normal")

    def _finish_error(self, message: str, unexpected: bool = False) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.set_status("翻译失败")
        self.busy = False
        self.translate_btn.configure(state="normal")
        if unexpected:
            messagebox.showerror("翻译失败", message)
        else:
            # 可预期错误（如模型缺失）：状态栏提示为主，避免自动翻译时反复弹窗
            self.set_status(f"翻译失败：{message.splitlines()[0]}")
            messagebox.showerror("翻译失败", message)

    # ---------------------------------------------------------- 自动翻译
    def on_auto_toggle(self) -> None:
        self.cfg.auto_translate = bool(self.auto_var.get())
        save_config(self.cfg)
        if self.cfg.auto_translate:
            self.set_status(
                f"已开启自动翻译：停止输入 {self.cfg.auto_translate_delay} 毫秒后自动翻译"
            )
            self.schedule_auto_translate()
        else:
            self.cancel_auto_job()
            self.set_status("已关闭自动翻译，请点击「翻译」按钮或按 Ctrl+Enter")

    def cancel_auto_job(self) -> None:
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
            self._auto_job = None

    def on_source_changed(self, _event=None) -> None:
        """输入变化：更新字数统计，并按设置安排自动翻译。"""
        self._update_count()
        self.schedule_auto_translate()

    def schedule_auto_translate(self) -> None:
        self.cancel_auto_job()
        if not self.cfg.auto_translate:
            return
        text = self.src_text.get("1.0", "end-1c").strip()
        if not text:
            self.set_target("")
            self._last_translated = ""
            self.progress["value"] = 0
            return
        if text == self._last_translated:
            return
        delay = max(200, int(self.cfg.auto_translate_delay))
        self._auto_job = self.after(delay, self._auto_translate_now)

    def _auto_translate_now(self) -> None:
        self._auto_job = None
        if self.busy:
            # 上一次翻译还没结束：稍后再试，避免堆积
            self._auto_job = self.after(300, self._auto_translate_now)
            return
        self.start_translate(auto=True)

    # -------------------------------------------------------------- 历史记录
    def _refresh_history_list(self) -> None:
        self.history_list.delete(0, "end")
        self._history_rows = []
        for item in self.history.items:
            arrow = "英→中" if item.direction == "en2zh" else "中→英"
            self.history_list.insert("end", f"[{item.time_text}] {arrow} {item.preview}")
            self._history_rows.append(item)

    def on_history_select(self, _event=None) -> None:
        selection = self.history_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self._history_rows):
            return
        item = self._history_rows[index]
        self.src_text.delete("1.0", "end")
        self.src_text.insert("1.0", item.source)
        self.set_target(item.target)
        self._last_translated = item.source   # 已是历史里的译文，不必重新翻译
        self._update_count()
        self.set_status(f"已载入历史记录（{item.time_text}）")

    def delete_history_selected(self) -> None:
        selection = self.history_list.curselection()
        if not selection:
            self.set_status("请先选中一条历史记录")
            return
        self.history.remove_at(selection[0])
        self._refresh_history_list()
        self.set_status("已删除该条历史记录")

    def clear_history(self) -> None:
        if not self.history.items:
            self.set_status("历史记录已是空的")
            return
        if messagebox.askyesno("清空历史", "确定要删除全部历史记录吗？此操作不可撤销。"):
            self.history.clear()
            self._refresh_history_list()
            self.set_status("历史记录已清空")

    # ------------------------------------------------------------------ 设置
    def open_settings(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("设置")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.grab_set()

        body = ttk.Frame(dlg, padding=14)
        body.pack(fill="both", expand=True)

        mode_var = tk.StringVar(value=self.cfg.default_mode)
        font_var = tk.StringVar(value=self.cfg.font_size_label)
        clip_var = tk.BooleanVar(value=self.cfg.auto_read_clipboard)
        limit_var = tk.IntVar(value=self.cfg.history_limit)
        auto_var = tk.BooleanVar(value=bool(self.cfg.auto_translate))
        delay_var = tk.IntVar(value=int(self.cfg.auto_translate_delay))

        ttk.Label(body, text="默认翻译方向：").grid(row=0, column=0, sticky="w", pady=6)
        mode_box = ttk.Combobox(
            body,
            state="readonly",
            width=16,
            values=["auto", MODE_EN2ZH, MODE_ZH2EN],
        )
        mode_box.set(mode_var.get())
        mode_box.grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(body, text="（auto=自动识别）", foreground="#666").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(body, text="界面字体大小：").grid(row=1, column=0, sticky="w", pady=6)
        font_box = ttk.Combobox(
            body, state="readonly", width=16, values=list(FONT_SIZES.keys())
        )
        font_box.set(font_var.get())
        font_box.grid(row=1, column=1, sticky="w", pady=6)

        clip_check = ttk.Checkbutton(body, text="启动时自动读取剪贴板", variable=clip_var)
        clip_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=6)

        ttk.Label(body, text="历史记录条数上限：").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Spinbox(body, from_=20, to=2000, increment=10, width=8, textvariable=limit_var).grid(
            row=3, column=1, sticky="w", pady=6
        )

        auto_check = ttk.Checkbutton(
            body, text="输入后自动翻译（无需点击「翻译」）", variable=auto_var
        )
        auto_check.grid(row=4, column=0, columnspan=3, sticky="w", pady=6)

        ttk.Label(body, text="停止输入多久后翻译（毫秒）：").grid(
            row=5, column=0, sticky="w", pady=6
        )
        ttk.Spinbox(
            body, from_=200, to=3000, increment=100, width=8, textvariable=delay_var
        ).grid(row=5, column=1, sticky="w", pady=6)

        info = (
            "本软件完全离线运行，不联网、不上传任何内容。\n"
            f"配置与历史只保存在：{os.environ.get('APPDATA')}\\{APP_NAME}"
        )
        ttk.Label(body, text=info, foreground="#0a7d28", justify="left").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(10, 6)
        )

        def on_ok() -> None:
            self.cfg.default_mode = mode_box.get()
            self.cfg.font_size_label = font_box.get()
            self.cfg.auto_read_clipboard = bool(clip_var.get())
            try:
                self.cfg.history_limit = max(20, min(2000, int(limit_var.get())))
            except Exception:
                self.cfg.history_limit = 200
            self.cfg.auto_translate = bool(auto_var.get())
            try:
                self.cfg.auto_translate_delay = max(200, min(3000, int(delay_var.get())))
            except Exception:
                self.cfg.auto_translate_delay = 800
            self.history.limit = self.cfg.history_limit
            self.mode_var.set(self.cfg.default_mode)
            self.auto_var.set(self.cfg.auto_translate)
            self._apply_font()
            save_config(self.cfg)
            dlg.destroy()
            self.set_status("设置已保存")
            if self.cfg.auto_translate:
                self._last_translated = ""
                self.schedule_auto_translate()

        btns = ttk.Frame(body)
        btns.grid(row=7, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="确定", command=on_ok).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side="left")

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def open_about(self) -> None:
        lic_path = models_dir().parent / "assets" / "LICENSE-THIRD-PARTY.md"
        if not lic_path.is_file():
            lic_path = app_dir() / "assets" / "LICENSE-THIRD-PARTY.md"
        text = (
            f"{APP_CN_NAME}（OfflineTranslator） {APP_VERSION}\n\n"
            "完全离线运行的英汉 / 汉英双向翻译软件。\n"
            "翻译由本机神经机器翻译模型完成，不需要联网。\n\n"
            "【隐私承诺】\n"
            "· 运行期不发起任何网络请求（已用 socket 硬阻断强制保证）\n"
            "· 不采集、不上传原文/译文/历史记录，不含遥测与广告\n"
            "· 配置、历史、日志只写入本机用户数据目录\n"
            "· 不读取与翻译无关的文件\n\n"
            f"【本机数据目录】\n{os.environ.get('APPDATA')}\\{APP_NAME}\n\n"
            f"【模型目录】\n{models_dir() / 'packages'}\n\n"
            "【第三方组件与模型许可】\n"
            "· Argos Translate / CTranslate2 / SentencePiece：MIT / Apache-2.0\n"
            "· 翻译模型由 Argos Open Tech 提供（OPUS 数据训练），CC-BY-4.0\n"
            "  详见随软件附带的 assets/LICENSE-THIRD-PARTY.md\n"
        )
        if not lic_path.is_file():
            text += "\n（未找到许可证文件，请检查安装是否完整）"
        messagebox.showinfo("关于 / 隐私说明", text, parent=self)

    def open_log_dir(self) -> None:
        try:
            os.startfile(str(log_path().parent))  # noqa: S606 - 打开本软件自己的日志目录
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    # ------------------------------------------------------------------ 关闭
    def on_close(self) -> None:
        try:
            self.cfg.show_history_panel = bool(self.history_frame.winfo_ismapped())
            save_config(self.cfg)
        except Exception:
            pass
        self.destroy()


def run_selftest() -> int:
    """无界面自检（供打包后验证使用）：检查模型与双向翻译是否可用。"""
    block_network()
    print(f"{APP_CN_NAME} OfflineTranslator {APP_VERSION} 自检开始")
    print(f"模型目录: {models_dir()}")
    print(f"packages : {models_dir() / 'packages'}")
    engine = OfflineTranslator()
    status = engine.check_pairs(refresh=True)
    print(f"模型: en->zh={status.en2zh}  zh->en={status.zh2en}")
    if status.error:
        print("模型错误:", status.error)
    if not (status.en2zh and status.zh2en):
        print("SELFTEST FAIL: 模型不完整")
        return 2
    failures = 0
    for text, mode in (
        ("This software works completely offline.", "auto"),
        ("这个软件完全离线运行。", "auto"),
        ("Hello world", "zh2en"),
    ):
        try:
            result, direction, elapsed = engine.translate(text, mode=mode)
        except Exception as exc:
            print(f"FAIL 翻译出错: {exc}")
            failures += 1
            continue
        print(f"[{direction}] {text}  ->  {result}   ({elapsed:.2f}s)")
        if not result.strip():
            failures += 1
    print("SELFTEST " + ("PASS" if failures == 0 else f"FAIL({failures})"))
    return 0 if failures == 0 else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return run_selftest()
    if not acquire_single_instance():
        activate_existing_window()
        return 0
    block_network()  # 隐私红线：运行期硬阻断网络
    LOG.info("启动 %s %s (frozen=%s)", APP_NAME, APP_VERSION, is_frozen())
    app = TranslatorApp()

    def report_callback_exception(exc, val, tb) -> None:
        LOG.error("界面异常: %s\n%s", val, "".join(traceback.format_exception(exc, val, tb)))
        try:
            messagebox.showerror("发生错误", f"程序遇到未预期的错误：\n{val}\n\n详情已写入日志。")
        except Exception:
            pass

    app.report_callback_exception = report_callback_exception
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
