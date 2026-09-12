from __future__ import annotations

import math
import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from . import help_text as HT
    from .bot_ai import BotController
    from .engine import ActionCommand, DecisionProvider, GameEngine, ExitOption
    from .models import DIRECTION_DELTAS, GameState, OPPOSITE, Player, PlacedRoom
except ImportError:  # pragma: no cover - direct script execution
    import help_text as HT  # type: ignore
    from bot_ai import BotController  # type: ignore
    from engine import ActionCommand, DecisionProvider, GameEngine, ExitOption  # type: ignore
    from models import DIRECTION_DELTAS, GameState, OPPOSITE, Player, PlacedRoom  # type: ignore


PALETTE = {
    "bg": "#1f232a",
    "panel": "#262b33",
    "panel2": "#313743",
    "panel3": "#20252d",
    "outline": "#111820",
    "accent": "#d6b26e",
    "text": "#eef2f6",
    "muted": "#aab4c2",
    "danger": "#d46a6a",
    "success": "#79c37c",
    "room": "#38414d",
    "room_revealed": "#4e5a68",
    "start": "#5d6f87",
    "hero": "#4f8cff",
    "traitor": "#d85a5a",
    "monster": "#b274d8",
    "item": "#5fb39b",
    "omen": "#ce8c55",
    "event": "#8b8bd6",
}

# 每位玩家的固定颜色（按 id 取色，便于在地图上区分玩家）
PLAYER_COLORS = ["#5f9bff", "#79c37c", "#f0b25a", "#ce8c55", "#b274d8", "#e06060"]

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_UI_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_PANEL = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 26, "bold")
FONT_SUBTITLE = ("Microsoft YaHei UI", 11)


def _configure_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
    except Exception:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ----------------------------------------------------------------------
# 属性卡尺（轨道）渲染：把每条属性的完整轨道显示出来，
# 骷髅格 ☠、濒危区（最左 N 格）、当前格用颜色标注。
# ----------------------------------------------------------------------
TRACK_STAT_ZH = {"speed": "速度", "might": "力量", "sanity": "理智", "knowledge": "知识"}
TRACK_DANGER_GRID = 2  # 轨道最左几格视为濒危区（红色）
ROLE_LABELS = {
    "explorer": "探索者",
    "hero": "英雄",
    "traitor": "叛徒",
    "unknown": "未知",
}


def _role_text(role: str) -> str:
    return ROLE_LABELS.get(role, role or "未知")


def _config_track_tags(widget: tk.Text) -> None:
    """在 Text 组件上配置轨道渲染用的颜色标签。"""
    widget.tag_configure("tr_normal", foreground=PALETTE["text"])
    widget.tag_configure("tr_danger", foreground=PALETTE["danger"], font=FONT_UI_BOLD)
    widget.tag_configure(
        "tr_current",
        background=PALETTE["accent"],
        foreground="#1f232a",
        font=FONT_UI_BOLD,
    )
    widget.tag_configure("tr_skull", foreground=PALETTE["danger"], font=FONT_UI_BOLD)
    widget.tag_configure("tr_overflow", foreground=PALETTE["success"])
    widget.tag_configure("tr_label", foreground=PALETTE["text"], font=FONT_UI_BOLD)


def _track_cells(value: int, target: int) -> str:
    """把剧本轨道数值渲染成进度格：已完成 ●、未完成 ○；无目标时不画格。"""
    if target <= 0:
        return ""
    filled = max(0, min(int(value), int(target)))
    return "●" * filled + "○" * (int(target) - filled)


def _append_stat_track(widget: tk.Text, player: Player, stat: str) -> None:
    """向 Text 组件追加一行属性卡尺显示；无轨道数据的角色退化为「当前值/上限」。

    显示规则（避免多色混杂）：
      - 只有「当前格」有金色背景填充，其余格子一律白字无背景；
      - 骷髅 ☠ 用红色表示死亡格；
      - 当前格落在濒危区（轨道最左几格）时，行尾追加红色「⚠濒危」警示。
    """
    track = player.stats_tracks.get(stat) if player.stats_tracks else None
    pos = player.stat_positions.get(stat, 0)
    cur = player.stats.get(stat, 0)
    zh = TRACK_STAT_ZH.get(stat, stat)
    widget.insert("end", f"  {zh}：", "tr_label")
    if not track:
        widget.insert("end", f"{cur} / {player.stats_max.get(stat, cur)}", "tr_normal")
        if player.overflow.get(stat, 0):
            widget.insert("end", f" (+{player.overflow[stat]})", "tr_overflow")
        widget.insert("end", "\n")
        return
    widget.insert("end", "☠", "tr_skull")
    widget.insert("end", " ")
    for i, val in enumerate(track):
        tag = "tr_current" if i == pos else "tr_normal"
        widget.insert("end", f" {val} ", (tag,))
    if pos < 0:
        widget.insert("end", " 已跌出轨道", "tr_danger")
    elif pos < TRACK_DANGER_GRID:
        widget.insert("end", " ⚠濒危", "tr_danger")
    if player.overflow.get(stat, 0):
        widget.insert("end", f" (+{player.overflow[stat]})", "tr_overflow")
    widget.insert("end", "\n")


class TkDecisionProvider(DecisionProvider):
    def __init__(self, root: tk.Tk):
        self.root = root

    def notify(self, title: str, message: str) -> None:
        # 自定义静音弹窗，替代系统 messagebox（去掉 Windows 提示音/系统样式）
        dialog = _InfoDialog(self.root, title, message)
        self.root.wait_window(dialog.top)

    def confirm(self, title: str, message: str) -> bool:
        dialog = _ConfirmDialog(self.root, title, message)
        self.root.wait_window(dialog.top)
        return dialog.result

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        if not options:
            return None
        dialog = _ChoiceDialog(self.root, title, message, options)
        self.root.wait_window(dialog.top)
        return dialog.result

    def choose_rotation(self, title, message, placements, entry_direction):
        if not placements:
            return None
        dialog = _RotationDialog(self.root, title, message, placements, entry_direction)
        self.root.wait_window(dialog.top)
        return dialog.result

    def choose_split_damage(
        self,
        title: str,
        message: str,
        amount: int,
        first_label: str,
        second_label: str,
    ) -> int | None:
        prompt = f"{message}\n输入分配给{first_label}的点数（0~{amount}）。"
        value = simpledialog.askinteger(title, prompt, parent=self.root, minvalue=0, maxvalue=amount)
        return value

    def show_dice_roll(self, dice: list[int], total: int, label: str) -> None:
        dialog = _DiceDialog(self.root, dice, total, label)
        self.root.wait_window(dialog.top)


class _DiceDialog:
    """特制骰子投掷动画面板（伪三维翻面滚动）。

    每颗骰子六个面：0/0/1/1/2/2。流程：
    玩家点「投掷」→ 骰子快速翻滚 → 从右往左逐颗翻面定格到真实结果 →
    显示「当前点数依次为：A、B、C（共 X 点）」→ 玩家点「确认」关闭。
    """

    DIE_SIZE = 64
    DIE_GAP = 20
    PAD = 26
    FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
    FONT_NOTE = ("Microsoft YaHei UI", 12)
    FONT_RESULT = ("Microsoft YaHei UI", 17, "bold")
    FONT_BUTTON = ("Microsoft YaHei UI", 14, "bold")

    def __init__(self, root: tk.Tk, dice: list[int], total: int, label: str = "", modal: bool = True) -> None:
        self.dice = list(dice)
        self.total = int(total)
        self.label = label
        self._showing = [0] * len(self.dice)
        self._shrink = [1.0] * len(self.dice)
        self._phase = "idle"
        self._frame = 0
        self._roll_after = None

        n = len(self.dice)
        width = self.PAD * 2 + n * self.DIE_SIZE + (n - 1) * self.DIE_GAP
        height = self.PAD * 2 + self.DIE_SIZE

        self.top = tk.Toplevel(root)
        self.top.title(label or "投掷骰子")
        self.top.configure(bg=PALETTE["panel"])
        self.top.attributes("-topmost", True)
        if modal:
            self.top.transient(root)
            self.top.grab_set()
        self.top.resizable(False, False)

        tk.Label(
            self.top,
            text=label or "投掷骰子",
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=self.FONT_TITLE,
            anchor="w",
            padx=22,
            pady=4,
        ).pack(fill="x", pady=(16, 0))

        self.canvas = tk.Canvas(
            self.top,
            width=width,
            height=height,
            bg=PALETTE["panel"],
            highlightthickness=0,
        )
        self.canvas.pack(padx=10, pady=(8, 4))

        tk.Label(
            self.top,
            text="特制骰：每个六面骰为 0 0 1 1 2 2",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=self.FONT_NOTE,
            anchor="w",
            padx=22,
        ).pack(fill="x", pady=(0, 6))

        self.result_var = tk.StringVar(value="")
        tk.Label(
            self.top,
            textvariable=self.result_var,
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=self.FONT_RESULT,
            anchor="center",
            pady=4,
        ).pack(fill="x")

        self.btn_roll = tk.Button(
            self.top,
            text="🎲 投掷",
            command=self._start_roll,
            bg=PALETTE["accent"],
            fg="#111",
            relief="flat",
            font=self.FONT_BUTTON,
            padx=36,
            pady=8,
            activebackground=PALETTE["panel3"],
            activeforeground=PALETTE["text"],
            cursor="hand2",
        )
        self.btn_roll.pack(pady=(8, 18))

        self._draw_dice()
        self.top.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self) -> None:
        if self._roll_after is not None:
            try:
                self.top.after_cancel(self._roll_after)
            except Exception:
                pass
        try:
            self.top.destroy()
        except Exception:
            pass

    def _draw_dice(self) -> None:
        self.canvas.delete("all")
        for i, value in enumerate(self._showing):
            x = self.PAD + i * (self.DIE_SIZE + self.DIE_GAP)
            y = self.PAD
            self._draw_one_die(x, y, self.DIE_SIZE, value, self._shrink[i])

    def _draw_one_die(self, x: int, y: int, size: int, value: int, shrink: float) -> None:
        """画一颗骰子；shrink 压缩宽度（0~1）模拟翻面滚动。"""
        half = size / 2
        cx = x + half
        cy = y + half
        w = max(3, size * shrink)
        left = cx - w / 2
        right = cx + w / 2
        self.canvas.create_rectangle(
            left, y, right, y + size,
            fill=PALETTE["panel2"],
            outline=PALETTE["outline"],
            width=2,
        )
        if shrink < 0.35:
            return  # 翻到侧边时不画点
        r = max(4, size * 0.09)
        ox = w / size  # 横向压缩时点也跟着收拢
        if value == 1:
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=PALETTE["text"], outline="")
        elif value == 2:
            dx = half * 0.28 * ox
            dy = half * 0.28
            self.canvas.create_oval(
                cx - dx - r, cy - dy - r, cx - dx + r, cy - dy + r,
                fill=PALETTE["text"], outline="",
            )
            self.canvas.create_oval(
                cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r,
                fill=PALETTE["text"], outline="",
            )

    # ------------------------------------------------------------------
    # 动画：翻滚 → 逐颗翻面定格 → 结果确认
    # ------------------------------------------------------------------
    def _start_roll(self) -> None:
        if self._phase != "idle":
            return
        self._phase = "scramble"
        self._frame = 0
        self.btn_roll.config(state="disabled", text="投掷中…")
        self._scramble()

    def _scramble(self) -> None:
        if self._phase != "scramble":
            return
        self._frame += 1
        t = self._frame * 1.0
        for idx in range(len(self.dice)):
            self._showing[idx] = random.choice((0, 1, 2))
            # 不同骰子错峰起伏，模拟翻面滚动
            self._shrink[idx] = 0.3 + 0.7 * abs(math.sin(t * 0.9 + idx * 1.3))
        self._draw_dice()
        if self._frame >= 18:  # 约 1.5s 翻滚
            self._phase = "reveal"
            self._reveal_index = len(self.dice) - 1  # 从右往左定格
            self._reveal_frame = 0
            self._reveal()
        else:
            self._roll_after = self.top.after(82, self._scramble)

    def _reveal(self) -> None:
        if self._phase != "reveal":
            return
        i = self._reveal_index
        # 第 i 颗骰子做一次「翻面落定」：1 → 0.12 → 1，中途切到真实值
        self._reveal_frame += 1
        if self._reveal_frame == 1:
            self._shrink[i] = 0.45
            self._showing[i] = random.choice((0, 1, 2))
        elif self._reveal_frame == 2:
            self._shrink[i] = 0.12
            self._showing[i] = self.dice[i]
        else:
            self._shrink[i] = 1.0
            self._showing[i] = self.dice[i]
            if self._reveal_index <= 0:
                self._phase = "done"
                self._show_result()
                return
            self._reveal_index -= 1
            self._reveal_frame = 0
        self._draw_dice()
        self._roll_after = self.top.after(120, self._reveal)

    def _show_result(self) -> None:
        self._draw_dice()
        detail = "、".join(map(str, self.dice))
        self.result_var.set(f"当前点数依次为：{detail}　（共 {self.total} 点）")
        self.btn_roll.config(state="normal", text="确认", command=self._close)


class _InfoDialog:
    """静音的自定义信息弹窗（替代系统 messagebox，去掉 Windows 提示音）。"""

    def __init__(self, root: tk.Tk, title: str, message: str, error: bool = False) -> None:
        self.top = tk.Toplevel(root)
        self.top.title(title)
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.attributes("-topmost", True)
        self.top.resizable(False, False)
        tk.Label(
            self.top,
            text=title,
            bg=PALETTE["panel"],
            fg=PALETTE["danger"] if error else PALETTE["accent"],
            font=("Microsoft YaHei UI", 13, "bold"),
            anchor="w",
            padx=20,
            pady=4,
        ).pack(fill="x", pady=(16, 0))
        tk.Label(
            self.top,
            text=message,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_PANEL,
            justify="left",
            wraplength=420,
            padx=20,
            pady=4,
            anchor="w",
        ).pack(fill="x", pady=(4, 12))
        tk.Button(
            self.top,
            text="确定",
            command=self.top.destroy,
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            font=FONT_UI_BOLD,
            padx=24,
            pady=5,
            activebackground=PALETTE["accent"],
            activeforeground="#111",
            cursor="hand2",
        ).pack(anchor="e", padx=20, pady=(0, 16))
        self.top.protocol("WM_DELETE_WINDOW", self.top.destroy)


class _TextDialog:
    """可滚动长文本窗口，用于剧本和较长说明。"""

    def __init__(self, root: tk.Tk, title: str, message: str) -> None:
        self.top = tk.Toplevel(root)
        self.top.title(title)
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.geometry("760x620")
        self.top.minsize(620, 420)

        tk.Label(
            self.top,
            text=title,
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=("Microsoft YaHei UI", 14, "bold"),
            anchor="w",
            padx=18,
            pady=8,
        ).pack(fill="x", pady=(10, 0))

        frame = tk.Frame(self.top, bg=PALETTE["panel"])
        frame.pack(fill="both", expand=True, padx=18, pady=(6, 12))
        scroll = tk.Scrollbar(frame, orient="vertical")
        text = tk.Text(
            frame,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            wrap="word",
            borderwidth=0,
            padx=14,
            pady=12,
            font=FONT_PANEL,
            yscrollcommand=scroll.set,
        )
        scroll.config(command=text.yview)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", message or "暂无内容。")
        text.config(state="disabled")

        tk.Button(
            self.top,
            text="关闭",
            command=self.top.destroy,
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            font=FONT_UI_BOLD,
            padx=24,
            pady=7,
            activebackground=PALETTE["accent"],
            activeforeground="#111",
            cursor="hand2",
        ).pack(anchor="e", padx=18, pady=(0, 16))
        self.top.protocol("WM_DELETE_WINDOW", self.top.destroy)


class _ConfirmDialog:
    """静音的自定义确认弹窗（替代 messagebox.askyesno）。"""

    def __init__(self, root: tk.Tk, title: str, message: str) -> None:
        self.result = False
        self.top = tk.Toplevel(root)
        self.top.title(title)
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.attributes("-topmost", True)
        self.top.resizable(False, False)
        tk.Label(
            self.top,
            text=title,
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=("Microsoft YaHei UI", 13, "bold"),
            anchor="w",
            padx=20,
            pady=4,
        ).pack(fill="x", pady=(16, 0))
        tk.Label(
            self.top,
            text=message,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_PANEL,
            justify="left",
            wraplength=420,
            padx=20,
            pady=4,
            anchor="w",
        ).pack(fill="x", pady=(4, 12))
        row = tk.Frame(self.top, bg=PALETTE["panel"])
        row.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(
            row,
            text="否",
            command=self._no,
            bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD,
            padx=20, pady=5, activebackground=PALETTE["danger"], activeforeground="#111", cursor="hand2",
        ).pack(side="right")
        tk.Button(
            row,
            text="是",
            command=self._yes,
            bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD,
            padx=20, pady=5, activebackground=PALETTE["accent"], activeforeground="#111", cursor="hand2",
        ).pack(side="right", padx=(0, 8))
        self.top.protocol("WM_DELETE_WINDOW", self.top.destroy)

    def _yes(self) -> None:
        self.result = True
        self.top.destroy()

    def _no(self) -> None:
        self.top.destroy()


class _ChoiceDialog:
    def __init__(self, root: tk.Tk, title: str, message: str, options: list[str]) -> None:
        self.result: int | None = None
        self.top = tk.Toplevel(root)
        self.top.title(title)
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.attributes("-topmost", True)
        self.top.geometry("420x320")

        label = tk.Label(
            self.top,
            text=message,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            justify="left",
            wraplength=380,
        )
        label.pack(fill="x", padx=16, pady=(16, 8))

        frame = tk.Frame(self.top, bg=PALETTE["panel"])
        frame.pack(fill="both", expand=True, padx=16, pady=8)

        listbox = tk.Listbox(
            frame,
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            selectbackground=PALETTE["accent"],
            activestyle="none",
            height=min(max(len(options), 6), 12),
        )
        for option in options:
            listbox.insert("end", option)
        listbox.pack(fill="both", expand=True)

        button_row = tk.Frame(self.top, bg=PALETTE["panel"])
        button_row.pack(fill="x", padx=16, pady=(0, 16))

        def choose() -> None:
            selection = listbox.curselection()
            if selection:
                self.result = int(selection[0])
            self.top.destroy()

        tk.Button(button_row, text="确定", command=choose, width=10, padx=8, pady=5).pack(side="right")
        tk.Button(button_row, text="取消", command=self.top.destroy, width=10, padx=8, pady=5).pack(side="right", padx=(0, 8))
        listbox.bind("<Double-Button-1>", lambda _event: choose())
        if options:
            listbox.selection_set(0)
            listbox.focus_set()
        self.top.protocol("WM_DELETE_WINDOW", self.top.destroy)


class _RotationDialog:
    """卡片式房间方向选择：直观展示房间四侧的门，可顺时针/逆时针旋转。"""

    CARD = "#4e5a68"
    DOOR = "#e8c98a"
    DOOR_BACK = "#f0a23a"
    DIR_CN = {"north": "北", "east": "东", "south": "南", "west": "西"}

    def __init__(self, root, title, message, placements, entry_direction):
        self.result = None
        self.placements = placements
        self.entry_direction = entry_direction
        self.index = 0
        self.top = tk.Toplevel(root)
        self.top.title(title)
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.attributes("-topmost", True)
        self.top.resizable(False, False)

        tk.Label(
            self.top,
            text=message,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_PANEL,
            justify="left",
            wraplength=320,
        ).pack(pady=(16, 6), padx=16, fill="x")

        self.canvas = tk.Canvas(self.top, width=300, height=268, bg=PALETTE["panel"], highlightthickness=0)
        self.canvas.pack(pady=4)

        rot_row = tk.Frame(self.top, bg=PALETTE["panel"])
        rot_row.pack(fill="x", padx=16, pady=(2, 4))
        tk.Button(
            rot_row,
            text="⟲ 逆时针",
            command=lambda: self._rotate(-1),
            bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD,
            activebackground=PALETTE["accent"], activeforeground="#111", cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            rot_row,
            text="⟳ 顺时针",
            command=lambda: self._rotate(1),
            bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD,
            activebackground=PALETTE["accent"], activeforeground="#111", cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        tk.Label(
            self.top,
            text="旋转后点「确定」放置；橙色门 = 连回上一个房间",
            bg=PALETTE["panel"], fg=PALETTE["muted"], font=FONT_PANEL,
        ).pack(pady=(0, 4))

        foot = tk.Frame(self.top, bg=PALETTE["panel"])
        foot.pack(fill="x", padx=16, pady=(0, 16))
        tk.Button(
            foot, text="确定", command=self._confirm,
            bg=PALETTE["accent"], fg="#111", relief="flat", font=FONT_UI_BOLD,
            padx=18, pady=5, cursor="hand2",
        ).pack(side="right")
        tk.Button(
            foot, text="取消", command=self.top.destroy,
            bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat", font=FONT_UI_BOLD,
            padx=14, pady=5, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

        self._draw()

    def _rotate(self, delta):
        self.index = (self.index + delta) % len(self.placements)
        self._draw()

    def _confirm(self):
        self.result = self.index
        self.top.destroy()

    def _draw(self):
        c = self.canvas
        c.delete("all")
        pl = self.placements[self.index]
        doors = set(pl["doors"])
        back = OPPOSITE[self.entry_direction]  # 连回上一个房间的门所在侧

        cx, cy, half = 150, 122, 80
        c.create_rectangle(cx - half, cy - half, cx + half, cy + half, fill=self.CARD, outline="")
        gap, w = 22, 11
        for side in ("north", "east", "south", "west"):
            if side not in doors:
                continue
            color = self.DOOR_BACK if side == back else self.DOOR
            if side == "north":
                c.create_rectangle(cx - gap, cy - half, cx + gap, cy - half + w, fill=color, outline="")
            elif side == "south":
                c.create_rectangle(cx - gap, cy + half - w, cx + gap, cy + half, fill=color, outline="")
            elif side == "east":
                c.create_rectangle(cx + half - w, cy - gap, cx + half, cy + gap, fill=color, outline="")
            elif side == "west":
                c.create_rectangle(cx - half, cy - gap, cx - half + w, cy + gap, fill=color, outline="")

        c.create_text(cx, cy - half - 16, text="北", fill=PALETTE["muted"], font=FONT_PANEL)
        c.create_text(cx, cy + half + 16, text="南", fill=PALETTE["muted"], font=FONT_PANEL)
        c.create_text(cx - half - 18, cy, text="西", fill=PALETTE["muted"], font=FONT_PANEL)
        c.create_text(cx + half + 18, cy, text="东", fill=PALETTE["muted"], font=FONT_PANEL)
        c.create_text(cx, cy + half + 40, text=f"方向 {self.index + 1} / {len(self.placements)}", fill=PALETTE["muted"], font=FONT_PANEL)


class _PlayerDetailDialog:
    """点击玩家标志后弹出的玩家详情（属性以卡尺轨道显示）。"""

    def __init__(self, root, player, catalog, room_name, role_label: str = "未知"):
        self.top = tk.Toplevel(root)
        self.top.title(f"{player.name} 详情")
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.geometry("480x620")

        head = [f"{player.name} / {player.character_name}"]
        if player.source_name:
            head.append(f"原版：{player.source_name}")
        head.extend([f"生日：{player.birthday}", f"阵营：{role_label}", f"位置：{room_name}"])
        tk.Label(
            self.top,
            text="\n".join(head),
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_PANEL,
            justify="left",
            padx=16,
            pady=4,
            anchor="w",
        ).pack(fill="x", pady=(12, 0))

        tk.Label(
            self.top,
            text="属性（卡尺）：☠=死亡格  金色=当前  红色⚠=当前已濒危",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=FONT_UI_BOLD,
            anchor="w",
            padx=16,
            pady=2,
        ).pack(fill="x")
        stat_text = tk.Text(
            self.top,
            height=5,
            width=42,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_PANEL,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=16,
            wrap="none",
        )
        stat_text.pack(fill="x")
        _config_track_tags(stat_text)
        for stat in ("speed", "might", "sanity", "knowledge"):
            _append_stat_track(stat_text, player, stat)
        stat_text.configure(state="disabled")

        rest = ["", "物品："]
        detail_text = tk.Text(
            self.top,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_PANEL,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=16,
            pady=4,
            wrap="word",
        )
        detail_text.pack(fill="both", expand=True, padx=4, pady=(0, 2))
        scroll = tk.Scrollbar(self.top, orient="vertical", command=detail_text.yview)
        detail_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        detail_text.insert("end", "物品：\n")
        if player.items:
            for card_id in player.items:
                card = catalog.cards.get(card_id)
                if not card:
                    detail_text.insert("end", f"  - {card_id}\n")
                    continue
                usage = HT.card_usage(card)
                detail_text.insert("end", f"  · {card.name}：{usage if usage else card.text}\n", "item")
        else:
            detail_text.insert("end", "  (无)\n")
        detail_text.insert("end", "\n同伴：\n")
        if player.companions:
            for card_id in player.companions:
                card = catalog.cards.get(card_id)
                detail_text.insert("end", f"  · {card.name if card else card_id}\n")
        else:
            detail_text.insert("end", "  (无)\n")
        detail_text.tag_configure("item", foreground=PALETTE["item"])
        detail_text.configure(state="disabled")
        tk.Button(
            self.top,
            text="关闭",
            command=self.top.destroy,
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            font=FONT_UI_BOLD,
            padx=20,
            pady=4,
            cursor="hand2",
        ).pack(pady=(0, 14))


class _HelpDialog:
    """规则与图鉴帮助窗口：基本规则 / 道具图鉴 / 房间图鉴。"""

    def __init__(self, root: tk.Tk, catalog) -> None:
        self.top = tk.Toplevel(root)
        self.top.title("规则与图鉴")
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
        self.top.geometry("700x600")
        self.top.minsize(600, 480)

        tk.Label(
            self.top,
            text="规则与图鉴",
            bg=PALETTE["panel"],
            fg=PALETTE["accent"],
            font=("Microsoft YaHei UI", 15, "bold"),
            anchor="w",
            padx=16,
            pady=6,
        ).pack(fill="x", pady=(10, 0))

        nb = ttk.Notebook(self.top)
        nb.pack(fill="both", expand=True, padx=12, pady=8)
        nb.add(self._rules_page(), text="  基本规则  ")
        nb.add(self._cards_page(catalog), text="  道具图鉴  ")
        nb.add(self._rooms_page(catalog), text="  房间图鉴  ")

        tk.Button(
            self.top,
            text="关闭",
            command=self.top.destroy,
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            font=FONT_UI_BOLD,
            padx=22,
            pady=5,
            cursor="hand2",
        ).pack(pady=(0, 12))

    def _page_text(self, content: str) -> tk.Frame:
        frame = tk.Frame(self.top, bg=PALETTE["panel"])
        text = tk.Text(
            frame,
            bg="#0d1013",
            fg=PALETTE["text"],
            font=FONT_PANEL,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            wrap="word",
        )
        scroll = tk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("end", content)
        text.configure(state="disabled")
        return frame

    def _rules_page(self) -> tk.Frame:
        return self._page_text(HT.rules_text())

    def _cards_page(self, catalog) -> tk.Frame:
        lines = ["道具 / 预兆 / 事件 说明：\n"]
        order: list[str] = []
        for kind in ("item", "omen", "event"):
            order.extend(sorted(c.id for c in catalog.cards.values() if c.kind == kind))
        kind_cn = {"item": "物品", "omen": "预兆", "event": "事件"}
        for cid in order:
            card = catalog.cards[cid]
            usage = HT.card_usage(card)
            desc = usage if usage else (card.text or "（无说明）")
            lines.append(f"[{kind_cn.get(card.kind, card.kind)}] {card.name}：{desc}")
        return self._page_text("\n".join(lines))

    def _rooms_page(self, catalog) -> tk.Frame:
        lines = ["房间效果一览：\n"]
        floor_cn = {1: "二层", 0: "一层", -1: "地下室"}
        for rid in sorted(catalog.room_templates):
            room = catalog.room_templates[rid]
            floor = floor_cn.get(room.floor, f"{room.floor}F")
            effect = HT.room_effect_detail(room.effect_id)
            if not effect:
                effect = room.text or "无特殊效果。"
            lines.append(f"[{floor}] {room.name}：{effect}")
        return self._page_text("\n".join(lines))


class GameApp(tk.Tk):
    def __init__(self) -> None:
        _configure_windows_dpi_awareness()
        super().__init__()
        self.title("山中小屋 - 本地单机版")
        self.geometry("1240x780")
        self.minsize(1024, 680)
        self.configure(bg=PALETTE["bg"])

        self.engine = GameEngine(prompter=TkDecisionProvider(self))
        self.selected_player_index = 0
        self.current_move_options: list[ExitOption] = []
        self.current_attack_targets: list[object] = []
        self._last_fp = None
        self._bot_busy = False
        self.zoom = 1.0
        self._tooltip = None
        self._closing = False
        self._idle_after = None
        self.bot_controller = BotController()
        self._exploration_slots: dict[str, dict] = {}
        self._exploration_hover_tag: str | None = None

        self._build_ui()
        self._build_start_screen()
        self._idle_after = self.after(100, self._idle_poll)

    # ------------------------------------------------------------------
    # UI structure
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.status_bar = tk.Frame(self, bg=PALETTE["panel"], height=48)
        self.status_bar.pack(fill="x", side="top")
        self.status_bar.pack_propagate(False)

        self.status_actions = tk.Frame(self.status_bar, bg=PALETTE["panel"])
        self.status_actions.pack(side="right", padx=12)
        top_button_style = dict(
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            activebackground=PALETTE["accent"],
            activeforeground="#111",
            font=FONT_UI_BOLD,
            padx=12,
            pady=5,
            cursor="hand2",
            disabledforeground=PALETTE["muted"],
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        self.btn_help = tk.Button(self.status_actions, text="帮助", command=self._action_help, **top_button_style)
        self.btn_save = tk.Button(self.status_actions, text="保存局面", command=self._action_save_game, **top_button_style)
        self.btn_load = tk.Button(self.status_actions, text="读取局面", command=self._action_load_game, **top_button_style)
        self.btn_help.pack(side="left", padx=(0, 6))
        self.btn_save.pack(side="left", padx=(0, 6))
        self.btn_load.pack(side="left")

        self.status_label = tk.Label(
            self.status_bar,
            text="尚未开始",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            anchor="w",
            padx=16,
            font=FONT_UI_BOLD,
        )
        self.status_label.pack(side="left", fill="both", expand=True)

        body = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=PALETTE["outline"],
            sashwidth=8,
            sashpad=1,
            relief="flat",
            opaqueresize=True,
        )
        body.pack(fill="both", expand=True, padx=10, pady=10)

        self.map_frame = tk.Frame(body, bg=PALETTE["bg"])
        right_shell = tk.Frame(body, bg=PALETTE["bg"], width=410)
        body.add(self.map_frame, minsize=580, stretch="always", padx=2, pady=2)
        body.add(right_shell, minsize=380, width=410, stretch="never", padx=2, pady=2)
        self.main_splitter = body

        right_shell.grid_rowconfigure(0, weight=1)
        right_shell.grid_columnconfigure(0, weight=1)

        self.right_canvas = tk.Canvas(right_shell, bg=PALETTE["bg"], highlightthickness=0)
        self.right_scroll = tk.Scrollbar(right_shell, orient="vertical", command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=self.right_scroll.set)
        self.right_canvas.grid(row=0, column=0, sticky="nsew")
        self.right_scroll.grid(row=0, column=1, sticky="ns")

        right = tk.Frame(self.right_canvas, bg=PALETTE["bg"], width=380)
        self.right_panel = right
        self._right_window = self.right_canvas.create_window((0, 0), window=right, anchor="nw", width=380)

        def resize_right(event) -> None:
            # 右侧内容不足一屏时，让最后的日志面板吸收剩余高度；
            # 内容超过可视区时仍保留外层纵向滚动。
            right_height = max(event.height, right.winfo_reqheight())
            self.right_canvas.itemconfigure(
                self._right_window,
                width=max(1, event.width),
                height=max(1, right_height),
            )
            self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))

        self.right_canvas.bind("<Configure>", resize_right)
        right.bind("<Configure>", lambda _event: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")))
        self.right_canvas.bind(
            "<MouseWheel>",
            lambda event: self.right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
        )
        right.bind(
            "<MouseWheel>",
            lambda event: self.right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
        )

        self.legend_frame = tk.Frame(right, bg=PALETTE["bg"])
        self.legend_frame.pack(fill="x", pady=(0, 6))

        self.info_panel = tk.Frame(
            right,
            bg=PALETTE["panel"],
            width=360,
            height=270,
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        self.info_panel.pack(fill="x")
        self.info_panel.pack_propagate(False)

        tk.Label(
            self.info_panel,
            text="玩家状态",
            bg=PALETTE["panel3"],
            fg=PALETTE["accent"],
            anchor="w",
            padx=12,
            pady=5,
            font=FONT_UI_BOLD,
        ).pack(fill="x")
        info_body = tk.Frame(self.info_panel, bg=PALETTE["panel"])
        info_body.pack(fill="both", expand=True)
        self.info_scroll = tk.Scrollbar(info_body, orient="vertical")
        self.player_info = tk.Text(
            info_body,
            wrap="word",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=12,
            font=FONT_PANEL,
            yscrollcommand=self.info_scroll.set,
        )
        self.info_scroll.config(command=self.player_info.yview)
        self.info_scroll.pack(side="right", fill="y")
        self.player_info.pack(side="left", fill="both", expand=True)
        _config_track_tags(self.player_info)
        self.player_info.bind(
            "<MouseWheel>",
            lambda e: self.player_info.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

        self.action_panel = tk.Frame(
            right,
            bg=PALETTE["panel"],
            width=360,
            height=270,
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        self.action_panel.pack(fill="x", pady=(12, 0))
        self.action_panel.pack_propagate(False)

        tk.Label(
            self.action_panel,
            text="行动",
            bg=PALETTE["panel3"],
            fg=PALETTE["accent"],
            anchor="w",
            padx=12,
            pady=5,
            font=FONT_UI_BOLD,
        ).pack(fill="x")
        button_grid = tk.Frame(self.action_panel, bg=PALETTE["panel"])
        button_grid.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        button_style = dict(
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            activebackground=PALETTE["accent"],
            activeforeground="#111",
            font=FONT_UI_BOLD,
            padx=10,
            pady=7,
            height=1,
            cursor="hand2",
            disabledforeground=PALETTE["muted"],
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        self.btn_move = tk.Button(button_grid, text="移动", command=self._action_move, **button_style)
        self.btn_use = tk.Button(button_grid, text="使用", command=self._action_use_item, **button_style)
        self.btn_pickup = tk.Button(button_grid, text="拾取", command=self._action_pickup, **button_style)
        self.btn_drop = tk.Button(button_grid, text="丢弃", command=self._action_drop, **button_style)
        self.btn_trade = tk.Button(button_grid, text="交易", command=self._action_trade, **button_style)
        self.btn_attack = tk.Button(button_grid, text="攻击", command=self._action_attack, **button_style)
        self.btn_haunt_action = tk.Button(button_grid, text="剧本行动", command=self._action_haunt_action, **button_style)
        self.btn_script = tk.Button(button_grid, text="剧本", command=self._action_view_haunt_script, **button_style)
        self.btn_end = tk.Button(button_grid, text="结束", command=self._action_end_turn, **button_style)

        buttons = (
            (self.btn_move, 0, 0),
            (self.btn_use, 0, 1),
            (self.btn_haunt_action, 0, 2),
            (self.btn_pickup, 1, 0),
            (self.btn_drop, 1, 1),
            (self.btn_trade, 1, 2),
            (self.btn_attack, 2, 0),
            (self.btn_script, 2, 1),
            (self.btn_end, 2, 2),
        )
        for button, row, col in buttons:
            button.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            button.config(bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat")
        for row in range(3):
            button_grid.grid_rowconfigure(row, weight=1, minsize=58)
        for col in range(3):
            button_grid.grid_columnconfigure(col, weight=1, uniform="action")

        self.action_hint = tk.Label(
            self.action_panel,
            text="",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            anchor="w",
            justify="left",
            padx=12,
            pady=5,
            font=FONT_PANEL,
        )
        self.action_hint.pack(fill="x")
        self._action_button_labels = {
            self.btn_move: "移动",
            self.btn_use: "使用",
            self.btn_pickup: "拾取",
            self.btn_drop: "丢弃",
            self.btn_trade: "交易",
            self.btn_attack: "攻击",
            self.btn_haunt_action: "剧本行动",
            self.btn_script: "剧本",
            self.btn_end: "结束",
        }
        self._action_button_reasons: dict[tk.Button, str] = {}
        for button, label in self._action_button_labels.items():
            button.bind("<Enter>", lambda _e, b=button: self._show_action_button_hint(b))
            button.bind("<Leave>", lambda _e: self._refresh_action_hint())

        self.deck_panel = tk.Frame(
            right,
            bg=PALETTE["panel"],
            width=360,
            height=190,
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        self.deck_panel.pack(fill="x", pady=(12, 0))
        self.deck_panel.pack_propagate(False)

        tk.Label(
            self.deck_panel,
            text="局势",
            bg=PALETTE["panel3"],
            fg=PALETTE["accent"],
            anchor="w",
            padx=12,
            pady=5,
            font=FONT_UI_BOLD,
        ).pack(fill="x")
        self.deck_info = tk.Label(
            self.deck_panel,
            text="",
            justify="left",
            anchor="nw",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            padx=12,
            pady=10,
            font=FONT_PANEL,
        )
        self.deck_info.pack(fill="both", expand=True)

        self.log_panel = tk.Frame(right, bg=PALETTE["panel"], width=360, height=190, highlightthickness=1, highlightbackground=PALETTE["outline"])
        self.log_panel.pack(fill="both", expand=True, pady=(12, 0))
        self.log_panel.pack_propagate(False)

        tk.Label(
            self.log_panel,
            text="日志",
            bg=PALETTE["panel3"],
            fg=PALETTE["accent"],
            anchor="w",
            padx=12,
            pady=5,
            font=FONT_UI_BOLD,
        ).pack(fill="x")
        log_body = tk.Frame(self.log_panel, bg="#181c22")
        log_body.pack(fill="both", expand=True)
        self.log_scroll = tk.Scrollbar(log_body, orient="vertical")
        self.log_hscroll = tk.Scrollbar(log_body, orient="horizontal")
        self.log_text = tk.Text(
            log_body,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            wrap="none",
            borderwidth=0,
            font=FONT_PANEL,
            width=44,
            height=8,
            yscrollcommand=self.log_scroll.set,
            xscrollcommand=self.log_hscroll.set,
        )
        self.log_scroll.config(command=self.log_text.yview)
        self.log_hscroll.config(command=self.log_text.xview)
        self.log_hscroll.pack(side="bottom", fill="x")
        self.log_scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)
        self.log_text.config(state="disabled")
        self.log_text.bind(
            "<MouseWheel>",
            lambda e: self.log_text.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

    def _build_start_screen(self) -> None:
        self._clear_map()
        self._draw_start_form()
        self._refresh_ui()

    def _draw_start_form(self) -> None:
        for widget in self.map_frame.winfo_children():
            widget.destroy()

        card = tk.Frame(
            self.map_frame,
            bg=PALETTE["panel"],
            highlightthickness=1,
            highlightbackground="#111",
            highlightcolor="#111",
        )
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.9, relheight=0.92)
        card.pack_propagate(False)

        title = tk.Label(
            card,
            text="山中小屋",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_TITLE,
        )
        title.pack(anchor="n", pady=(16, 6))

        subtitle = tk.Label(
            card,
            text="配置 4 到 6 名玩家；空名字会由机器人补位。",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=FONT_SUBTITLE,
        )
        subtitle.pack(anchor="n", pady=(0, 12))

        self.start_entries: list[tk.Entry] = []
        self.character_vars: list[tk.StringVar] = []
        self.local_bot_difficulty_names = {"简单": "easy", "普通": "normal", "困难": "hard"}

        controls = tk.Frame(card, bg=PALETTE["panel"])
        controls.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(controls, text="总人数", bg=PALETTE["panel"], fg=PALETTE["muted"], font=FONT_PANEL).pack(side="left")
        self.local_total_players = tk.Spinbox(
            controls,
            from_=4,
            to=6,
            width=4,
            bg="#181c22",
            fg=PALETTE["text"],
            buttonbackground=PALETTE["panel2"],
            relief="flat",
        )
        self.local_total_players.delete(0, "end")
        self.local_total_players.insert(0, "4")
        self.local_total_players.pack(side="left", padx=(8, 18))
        tk.Label(controls, text="机器人难度", bg=PALETTE["panel"], fg=PALETTE["muted"], font=FONT_PANEL).pack(side="left")
        self.local_bot_difficulty = tk.StringVar(value="普通")
        diff_menu = tk.OptionMenu(controls, self.local_bot_difficulty, *self.local_bot_difficulty_names.keys())
        diff_menu.config(bg=PALETTE["panel2"], fg=PALETTE["text"], highlightthickness=0, font=FONT_PANEL)
        diff_menu["menu"].config(bg=PALETTE["panel2"], fg=PALETTE["text"])
        diff_menu.pack(side="left", padx=(8, 0))

        footer = tk.Frame(card, bg=PALETTE["panel"])
        footer.pack(side="bottom", fill="x", padx=18, pady=(8, 14))
        self.btn_local_start = tk.Button(
            footer,
            text="开始游戏",
            command=self._begin_game_from_form,
            bg=PALETTE["accent"],
            fg="#111",
            relief="flat",
            padx=14,
            pady=8,
            font=FONT_UI_BOLD,
            cursor="hand2",
        )
        self.btn_local_start.pack(side="right")

        note = tk.Label(
            card,
            text="留空的席位会自动交给机器人控制。",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            wraplength=540,
            justify="left",
            font=FONT_UI,
        )
        note.pack(side="bottom", anchor="w", padx=18, pady=(0, 4))

        # 席位数量可以是 4-6 人；把席位列表放入独立滚动区，避免第 5/6 行
        # 被底部说明和开始按钮遮住，同时让底部操作区始终可见。
        roster_shell = tk.Frame(card, bg=PALETTE["panel"])
        roster_shell.pack(fill="both", expand=True, padx=18, pady=(0, 4))
        roster_shell.grid_rowconfigure(0, weight=1)
        roster_shell.grid_columnconfigure(0, weight=1)
        roster_canvas = tk.Canvas(
            roster_shell,
            bg=PALETTE["panel"],
            highlightthickness=0,
            borderwidth=0,
        )
        roster_scroll = tk.Scrollbar(roster_shell, orient="vertical", command=roster_canvas.yview)
        roster_canvas.configure(yscrollcommand=roster_scroll.set)
        roster_canvas.grid(row=0, column=0, sticky="nsew")
        roster_scroll.grid(row=0, column=1, sticky="ns")
        roster = tk.Frame(roster_canvas, bg=PALETTE["panel"])
        roster_window = roster_canvas.create_window((0, 0), window=roster, anchor="nw")

        def resize_roster(event) -> None:
            roster_canvas.itemconfigure(roster_window, width=max(1, event.width))
            roster_canvas.configure(scrollregion=roster_canvas.bbox("all"))

        roster_canvas.bind("<Configure>", resize_roster)
        roster.bind(
            "<Configure>",
            lambda _event: roster_canvas.configure(scrollregion=roster_canvas.bbox("all")),
        )
        roster_canvas.bind(
            "<MouseWheel>",
            lambda event: roster_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
        )
        roster.bind(
            "<MouseWheel>",
            lambda event: roster_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
        )

        character_names = [face.name for face in self.engine.catalog.characters.values()]
        for index in range(6):
            row = tk.Frame(roster, bg=PALETTE["panel"])
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(1, weight=1)
            tk.Label(
                row,
                text=f"玩家 {index + 1}",
                width=8,
                anchor="w",
                bg=PALETTE["panel"],
                fg=PALETTE["text"],
                font=FONT_UI_BOLD,
            ).grid(row=0, column=0, sticky="w", padx=(0, 12))
            entry = tk.Entry(row, bg=PALETTE["panel2"], fg=PALETTE["text"], insertbackground=PALETTE["text"], relief="flat", font=FONT_UI)
            entry.insert(0, "玩家1" if index == 0 else "")
            entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), ipady=4)
            self.start_entries.append(entry)

            default_name = character_names[index % len(character_names)] if character_names else ""
            var = tk.StringVar(value=default_name)
            self.character_vars.append(var)
            option = tk.OptionMenu(row, var, *character_names)
            option.config(bg=PALETTE["panel2"], fg=PALETTE["text"], highlightthickness=0, width=16, font=FONT_UI)
            option["menu"].config(bg=PALETTE["panel2"], fg=PALETTE["text"])
            option.grid(row=0, column=2, sticky="e")


    def _clear_map(self) -> None:
        for widget in self.map_frame.winfo_children():
            widget.destroy()

    def _build_legend(self) -> None:
        for widget in self.legend_frame.winfo_children():
            widget.destroy()
        if not self.engine.state.players:
            return
        for player in self.engine.state.players:
            color = PLAYER_COLORS[player.id % len(PLAYER_COLORS)]
            row = tk.Frame(self.legend_frame, bg=PALETTE["bg"])
            row.pack(side="left", padx=5)
            tk.Label(row, text="●", fg=color, bg=PALETTE["bg"], font=("Arial", 13)).pack(side="left")
            tk.Label(row, text=f"{player.id + 1}:{player.name}", fg=PALETTE["text"], bg=PALETTE["bg"], font=FONT_PANEL).pack(side="left")

    def _current_viewer_id(self) -> int | None:
        state = self.engine.state
        if not state.players or not state.turn_order:
            return None
        return self.engine.current_player.id

    def _viewer_player(self) -> Player | None:
        viewer_id = self._current_viewer_id()
        if viewer_id is None or not (0 <= viewer_id < len(self.engine.state.players)):
            return None
        return self.engine.state.players[viewer_id]

    def _should_confirm_private_view(self) -> bool:
        return True

    def _role_label_for_viewer(self, player: Player) -> str:
        state = self.engine.state
        if state.phase != "HAUNT_PHASE" or state.winner:
            return _role_text(player.role)
        viewer_id = self._current_viewer_id()
        if viewer_id is not None and player.id == viewer_id:
            return _role_text(player.role)
        return "未知"

    def _haunt_text_for_viewer(self) -> tuple[str, str] | None:
        state = self.engine.state
        haunt = state.haunt
        viewer = self._viewer_player()
        if not haunt or viewer is None:
            return None
        if state.winner:
            text = "\n\n".join(part for part in (haunt.hero_script, haunt.traitor_script) if part)
            return f"#{haunt.id} {haunt.name} · 剧本", text
        if viewer.role == "traitor":
            text = haunt.traitor_script or haunt.traitor_goal
            return f"#{haunt.id} {haunt.name} · 叛徒手册", text
        if viewer.role == "hero":
            text = haunt.hero_script or haunt.hero_goal
            return f"#{haunt.id} {haunt.name} · 英雄手册", text
        return None

    def _begin_game_from_form(self) -> None:
        configs = []
        used_characters = set()
        try:
            total_players = int(self.local_total_players.get())
        except ValueError:
            total_players = 4
        total_players = max(4, min(6, total_players))
        bot_difficulty = self.local_bot_difficulty_names.get(self.local_bot_difficulty.get(), "normal")
        style_by_difficulty = {
            "easy": "cautious",
            "normal": "balanced",
            "hard": "aggressive",
        }
        human_count = 0
        for index, (entry, var) in enumerate(zip(self.start_entries, self.character_vars)):
            if index >= total_players:
                break
            name = entry.get().strip()
            character_name = var.get()
            character = next(
                (face for face in self.engine.catalog.characters.values() if face.name == character_name),
                None,
            )
            if not character:
                continue
            if character.id in used_characters:
                self._show_error("角色重复", "同一角色不能给两名玩家使用。")
                return
            used_characters.add(character.id)
            if name:
                human_count += 1
                configs.append({"name": name, "character_id": character.id, "control": "human"})
            else:
                configs.append({
                    "name": f"机器人{index + 1}",
                    "character_id": character.id,
                    "control": "bot",
                    "bot_difficulty": bot_difficulty,
                    "bot_style": style_by_difficulty[bot_difficulty],
                })

        if len(configs) < 4:
            self._show_error("人数不足", "至少需要 4 名玩家。")
            return
        if human_count < 1:
            self._show_error("缺少玩家", "至少需要填写 1 名人类玩家。")
            return
        self.engine.start_new_game(configs)
        self._build_game_board()
        self._build_legend()
        self._refresh_ui()
        self.engine.start_turn()
        self._refresh_ui()

    # ------------------------------------------------------------------
    # Board rendering
    # ------------------------------------------------------------------
    def _build_game_board(self) -> None:
        self._clear_map()

        toolbar = tk.Frame(self.map_frame, bg=PALETTE["bg"])
        toolbar.pack(side="top", fill="x", pady=(0, 6))
        toolbar.grid_columnconfigure(0, weight=1)
        toolbar.grid_columnconfigure(1, weight=0, minsize=118)
        toolbar.grid_rowconfigure(0, minsize=38)

        toolbar_left = tk.Frame(toolbar, bg=PALETTE["bg"])
        toolbar_left.grid(row=0, column=0, sticky="ew")
        toolbar_left.grid_columnconfigure(0, weight=1)
        toolbar_right = tk.Frame(toolbar, bg=PALETTE["bg"])
        toolbar_right.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))

        dice_row = tk.Frame(toolbar_left, bg=PALETTE["bg"])
        dice_row.grid(row=0, column=0, sticky="w")
        self._build_desk_dice(dice_row)
        controls_row = tk.Frame(toolbar_left, bg=PALETTE["bg"])
        controls_row.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.btn_zoom_out = tk.Button(controls_row, text="−", command=lambda: self._zoom(-0.15), bg=PALETTE["panel2"], fg=PALETTE["text"],
                                      relief="flat", font=FONT_UI_BOLD, width=3, cursor="hand2")
        self.btn_zoom_out.pack(side="left")
        self.zoom_label = tk.Label(controls_row, text="100%", bg=PALETTE["bg"], fg=PALETTE["text"], font=FONT_UI_BOLD, width=5)
        self.zoom_label.pack(side="left")
        self.btn_zoom_in = tk.Button(controls_row, text="＋", command=lambda: self._zoom(0.15), bg=PALETTE["panel2"], fg=PALETTE["text"],
                                     relief="flat", font=FONT_UI_BOLD, width=3, cursor="hand2")
        self.btn_zoom_in.pack(side="left")
        tk.Label(controls_row, text="滚轮滚动 · Ctrl+滚轮缩放", bg=PALETTE["bg"], fg=PALETTE["muted"], font=FONT_PANEL).pack(side="left", padx=10)
        self.btn_inspect_players = tk.Button(toolbar_right, text="查看玩家", command=self._action_inspect_players, bg=PALETTE["panel2"], fg=PALETTE["text"],
                                             relief="flat", font=FONT_UI_BOLD, width=10, height=1, padx=10, pady=6, cursor="hand2")
        self.btn_inspect_players.pack(side="right")

        board_body = tk.Frame(self.map_frame, bg=PALETTE["bg"])
        board_body.pack(side="top", fill="both", expand=True)

        scroll = tk.Scrollbar(board_body, orient="vertical")
        hscroll = tk.Scrollbar(board_body, orient="horizontal")
        canvas = tk.Canvas(
            board_body,
            bg="#171b21",
            highlightthickness=0,
            yscrollcommand=scroll.set,
            xscrollcommand=hscroll.set,
        )
        scroll.config(command=canvas.yview)
        hscroll.config(command=canvas.xview)
        hscroll.pack(side="bottom", fill="x")
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        canvas.bind(
            "<Control-MouseWheel>",
            lambda e: self._zoom(0.1 if e.delta > 0 else -0.1),
        )
        self.board_canvas = canvas
        self.board_scroll = scroll
        self.board_hscroll = hscroll
        self.tile_widgets: dict[str, dict] = {}
        self._redraw_board()

    def _build_desk_dice(self, parent) -> None:
        """桌面上常驻的特制骰子展示（每颗六面：0/0/1/1/2/2）。"""
        frame = tk.Frame(parent, bg=PALETTE["bg"])
        frame.pack(side="left", padx=(0, 14))
        canvas = tk.Canvas(frame, width=158, height=26, bg=PALETTE["bg"], highlightthickness=0)
        canvas.pack(side="left")
        tk.Label(
            frame,
            text="特制骰·每颗六面",
            bg=PALETTE["bg"],
            fg=PALETTE["muted"],
            font=FONT_PANEL,
        ).pack(side="left", padx=(6, 0))
        size = 22
        gap = 4
        values = [0, 0, 1, 1, 2, 2]
        for i, v in enumerate(values):
            x = i * (size + gap)
            y = 2
            canvas.create_rectangle(
                x, y, x + size, y + size,
                fill=PALETTE["panel2"],
                outline=PALETTE["outline"],
                width=1,
            )
            cx = x + size / 2
            cy = y + size / 2
            r = 2
            if v == 1:
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=PALETTE["text"], outline="")
            elif v == 2:
                canvas.create_oval(
                    x + size * 0.22 - r, y + size * 0.22 - r,
                    x + size * 0.22 + r, y + size * 0.22 + r,
                    fill=PALETTE["text"], outline="",
                )
                canvas.create_oval(
                    x + size * 0.78 - r, y + size * 0.78 - r,
                    x + size * 0.78 + r, y + size * 0.78 + r,
                    fill=PALETTE["text"], outline="",
                )

    def _redraw_board(self) -> None:
        canvas = self.board_canvas
        canvas.delete("all")
        self._exploration_slots = {}
        self._exploration_hover_tag = None
        canvas.configure(cursor="")
        self._hide_player_tooltip()
        self._hide_room_tooltip()
        state = self.engine.state
        if not state.board:
            return

        # 地图是三维的（地下室/一层/二层），这里按楼层分成三条竖向带分别排版，
        # 避免不同楼层同坐标的房间互相覆盖。
        floor_order = [1, 0, -1]  # 自上而下：二层、一层、地下室
        floor_label = {1: "二层 (2F)", 0: "一层 (1F)", -1: "地下室 (-1F)"}
        floor_rooms: dict[int, list] = {f: [] for f in floor_order}
        for room in state.board.values():
            floor_rooms.setdefault(room.floor, []).append(room)

        current_player = None
        current_options: list[ExitOption] = []
        if state.players and state.turn_order:
            current_player = self.engine.current_player
            try:
                current_options = self.engine.available_move_options(current_player)
            except Exception:
                current_options = []
        self.current_move_options = current_options
        explore_options = [
            option
            for option in current_options
            if option.is_new_room
            and current_player is not None
            and current_player.control != "bot"
            and state.phase == "EXPLORE"
            and not state.winner
            and current_player.steps_remaining >= option.cost
        ]
        explore_positions: list[tuple[ExitOption, tuple[int, int, int]]] = []
        if current_player is not None:
            current_room = state.board.get(current_player.room_key)
            if current_room is not None:
                for option in explore_options:
                    dx, dy = DIRECTION_DELTAS.get(option.direction, (0, 0))
                    target_pos = (current_room.floor, current_room.x + dx, current_room.y + dy)
                    if target_pos not in state.pos_index:
                        explore_positions.append((option, target_pos))

        canvas_w = max(canvas.winfo_width(), 720)
        base_tile = 110
        layout_xs: dict[int, list[int]] = {
            floor: [room.x for room in rooms] for floor, rooms in floor_rooms.items() if rooms
        }
        for f in floor_order:
            rooms = floor_rooms[f]
            if not rooms:
                continue
            xs = layout_xs[f]
            xs.extend(pos[1] for _option, pos in explore_positions if pos[0] == f)
            span = max(xs) - min(xs) + 1
            base_tile = min(base_tile, max(72, int((canvas_w - 90) / span)))
        tile_size = max(64, int(max(72, base_tile) * self.zoom))

        all_xs = [room.x for room in state.board.values()]
        all_xs.extend(pos[1] for _option, pos in explore_positions)
        global_min_x = min(all_xs) if all_xs else 0
        global_max_x = max(all_xs) if all_xs else 0
        content_width = (global_max_x - global_min_x + 1) * tile_size
        margin_x = max(40, int((canvas_w - content_width) / 2))
        label_h = 22
        gap = 30

        # 预计算每个楼层的网格原点与最小坐标。
        # 各楼层共用同一个全局 min_x，保证二层/一层/地下室在水平方向上对齐。
        floor_meta: dict[int, tuple[int, int, int, int]] = {}
        y_cursor = 16
        for f in floor_order:
            rooms = floor_rooms[f]
            if not rooms:
                continue
            xs = layout_xs[f]
            ys = [r.y for r in rooms]
            ys.extend(pos[2] for _option, pos in explore_positions if pos[0] == f)
            min_y = min(ys)
            floor_meta[f] = (margin_x, y_cursor + label_h, global_min_x, min_y)
            y_cursor += label_h + (max(ys) - min(ys) + 1) * tile_size + gap

        def room_px(room):
            ox, oy, min_x, min_y = floor_meta[room.floor]
            return ox + (room.x - min_x) * tile_size, oy + (room.y - min_y) * tile_size

        # 楼层标题
        for f in floor_order:
            if f not in floor_meta:
                continue
            ox, oy, _, _ = floor_meta[f]
            canvas.create_text(
                ox,
                oy - label_h + 6,
                text=floor_label[f],
                fill=PALETTE["muted"],
                font=("Arial", 12, "bold"),
                anchor="w",
            )

        # 新房间的合法落点：只画在当前玩家有门、该楼层还有房间牌且步数足够的位置。
        # 空心虚线格不会遮住地图；悬停/点击由同一个 ExitOption 驱动，最终仍由引擎复核。
        self._exploration_slots = {}
        for index, (option, target_pos) in enumerate(explore_positions):
            if target_pos[0] not in floor_meta:
                continue
            ox, oy, min_x, min_y = floor_meta[target_pos[0]]
            px = ox + (target_pos[1] - min_x) * tile_size
            py = oy + (target_pos[2] - min_y) * tile_size
            tag = f"explore_{target_pos[0]}_{target_pos[1]}_{target_pos[2]}_{index}"
            rect = canvas.create_rectangle(
                px,
                py,
                px + tile_size - 8,
                py + tile_size - 8,
                fill="#252b33",
                outline="#b9c4d1",
                dash=(5, 4),
                width=1,
                tags=(tag, "explore_slot"),
            )
            self._exploration_slots[tag] = {"rect": rect, "option": option, "pos": target_pos}
            canvas.tag_bind(tag, "<Button-1>", lambda _e, slot=tag: self._on_exploration_slot_click(slot))
            canvas.tag_bind(tag, "<Enter>", lambda _e, slot=tag: self._on_exploration_slot_enter(slot))
            canvas.tag_bind(tag, "<Leave>", lambda _e, slot=tag: self._on_exploration_slot_leave(slot))

        # 房间
        self.tile_widgets = {}
        for room in state.board.values():
            px, py = room_px(room)
            color = PALETTE["room_revealed"] if room.revealed else PALETTE["room"]
            if room.template_id in self.engine.catalog.start_room_ids:
                color = PALETTE["start"]
            if room.symbol == "omen":
                color = PALETTE["omen"] if room.revealed else color
            elif room.symbol == "item":
                color = PALETTE["item"] if room.revealed else color
            elif room.symbol == "event":
                color = PALETTE["event"] if room.revealed else color

            troom_tag = "troom_" + room.key.replace(":", "_")
            rect = canvas.create_rectangle(
                px,
                py,
                px + tile_size - 8,
                py + tile_size - 8,
                fill=color,
                outline="#111",
                width=2,
                tags=(troom_tag,),
            )
            ts = tile_size - 8
            name_size = max(8, min(11, int(tile_size / 11)))
            floor_size = max(7, min(9, int(tile_size / 13)))
            # 顶部：楼层标签；下方：房间名（中间留给玩家序号）
            canvas.create_text(
                px + ts / 2,
                py + max(9, ts * 0.18),
                text=floor_label.get(room.floor, f"{room.floor}F"),
                fill=PALETTE["muted"],
                font=("Microsoft YaHei UI", floor_size),
                tags=(troom_tag,),
            )
            canvas.create_text(
                px + ts / 2,
                py + ts * 0.64,
                text=room.name,
                fill=PALETTE["text"],
                width=max(34, ts - 16),
                font=("Microsoft YaHei UI", name_size, "bold"),
                tags=(troom_tag,),
            )
            canvas.tag_bind(troom_tag, "<Button-1>", lambda _e, key=room.key: self._on_room_click(key))
            canvas.tag_bind(troom_tag, "<Enter>", lambda e, r=room: self._show_room_tooltip(r, e))
            canvas.tag_bind(troom_tag, "<Leave>", lambda _e: self._hide_room_tooltip())
            # 门标记：在对应边上画小方块，直观表示该方向有门
            door_mark = PALETTE["accent"]
            for direction in room.doors:
                if direction == "north":
                    canvas.create_rectangle(px + ts / 2 - 7, py - 3, px + ts / 2 + 7, py + 3, fill=door_mark, outline="")
                elif direction == "south":
                    canvas.create_rectangle(px + ts / 2 - 7, py + ts - 3, px + ts / 2 + 7, py + ts + 3, fill=door_mark, outline="")
                elif direction == "east":
                    canvas.create_rectangle(px + ts - 3, py + ts / 2 - 7, px + ts + 3, py + ts / 2 + 7, fill=door_mark, outline="")
                elif direction == "west":
                    canvas.create_rectangle(px - 3, py + ts / 2 - 7, px + 3, py + ts / 2 + 7, fill=door_mark, outline="")
            self.tile_widgets[room.key] = {"rect": rect, "room": room}

        # 特殊连接（楼梯/密道；跨楼层时呈纵向虚线，表示上下连通）
        for room in state.board.values():
            px, py = room_px(room)
            for link_value in room.links.values():
                target_key = self.engine._link_target_key(link_value)
                if not target_key:
                    continue
                target = state.board[target_key]
                tx, ty = room_px(target)
                canvas.create_line(
                    px + tile_size / 2,
                    py + tile_size / 2,
                    tx + tile_size / 2,
                    ty + tile_size / 2,
                    fill="#9ad8ff",
                    dash=(4, 3),
                    width=2,
                )

        # 玩家棋子（当前玩家金色描边；点击查看详情，悬停显示属性/道具）
        current_player_id = state.turn_order[state.turn_index % len(state.turn_order)] if state.turn_order else None
        self._player_token_ids = {}
        for player in state.players:
            if player.room_key not in state.board:
                continue
            room = state.board[player.room_key]
            px, py = room_px(room)
            index = player.id
            # 玩家序号放到房间中央；同房多玩家时轻微错开
            mates = [o.id for o in state.players if o.room_key == player.room_key]
            k = mates.index(index) if index in mates else 0
            ts = tile_size - 8
            circle_x = px + ts / 2 - 11 + (k % 2) * 14
            circle_y = py + ts / 2 - 11 + (k // 2) * 14
            color = PLAYER_COLORS[player.id % len(PLAYER_COLORS)]
            outline = "#101010"
            width = 1
            if player.dead:
                color = PALETTE["muted"]
            elif current_player_id == player.id:
                outline = PALETTE["accent"]
                width = 2
            token = canvas.create_oval(circle_x, circle_y, circle_x + 22, circle_y + 22, fill=color, outline=outline, width=width)
            num = canvas.create_text(circle_x + 11, circle_y + 11, text=str(player.id + 1), fill="#ffffff", font=("Arial", 10, "bold"))
            tag = f"ptok{player.id}"
            canvas.addtag_withtag(tag, token)
            canvas.addtag_withtag(tag, num)
            canvas.tag_bind(tag, "<Button-1>", lambda _e, pid=player.id: self._on_player_token_click(pid))
            canvas.tag_bind(tag, "<Enter>", lambda e, pid=player.id: self._on_player_token_hover(pid, e))
            canvas.tag_bind(tag, "<Leave>", lambda _e: self._hide_player_tooltip())
            self._player_token_ids[player.id] = token

        # 怪物
        for monster in state.monsters:
            if monster.room_key not in state.board:
                continue
            room = state.board[monster.room_key]
            px, py = room_px(room)
            canvas.create_rectangle(
                px + tile_size - 34,
                py + tile_size - 34,
                px + tile_size - 18,
                py + tile_size - 18,
                fill=PALETTE["monster"],
                outline="#101010",
            )

        bbox = canvas.bbox("all")
        if bbox:
            canvas.configure(
                scrollregion=(bbox[0] - 24, bbox[1] - 24, bbox[2] + 24, bbox[3] + 24)
            )

    # ------------------------------------------------------------------
    # 玩家查看 / 地图缩放
    # ------------------------------------------------------------------
    def _zoom(self, delta: float) -> None:
        self.zoom = max(0.4, min(2.5, self.zoom + delta))
        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text=f"{int(round(self.zoom * 100))}%")
        if hasattr(self, "board_canvas"):
            self._redraw_board()

    def _action_inspect_players(self) -> None:
        if not self.engine.state.players:
            return
        names = [f"{p.id + 1}. {p.name} / {p.character_name}" for p in self.engine.state.players]
        idx = self.engine.prompter.choose_from_list("查看玩家", "选择要查看的玩家", names)
        if idx is None:
            return
        self._show_player_detail(idx)

    def _action_help(self) -> None:
        _HelpDialog(self, self.engine.catalog)

    def _on_player_token_click(self, player_id: int) -> None:
        self._show_player_detail(player_id)

    def _on_room_click(self, room_key: str) -> None:
        """点击地图房间：在移动力允许时沿最短已连接路线自动前进。"""
        state = self.engine.state
        target = state.board.get(room_key)
        if target is None:
            return
        if not state.players:
            return
        player = self.engine.current_player
        if player.control == "bot":
            self._show_info("地图移动", "当前是机器人回合，请等待机器人完成行动。")
            return
        if state.phase == "GAME_OVER":
            self._show_info("地图移动", "游戏已经结束。")
            return
        if target.key == player.room_key:
            self._show_room_info(target)
            return
        if player.dead or player.movement_stopped or player.steps_remaining <= 0:
            self._show_info("地图移动", "当前没有足够的移动力，或移动已被本回合效果终止。")
            return

        moved = False
        while player.room_key != target.key and player.steps_remaining > 0 and not player.movement_stopped:
            path = self.engine._shortest_path(player.room_key, target.key)
            if len(path) <= 1:
                break
            next_key = path[1]
            options = [
                option
                for option in self.engine.available_move_options(player)
                if not option.is_new_room and option.target_key == next_key
            ]
            if not options:
                break
            option = options[0]
            if option.cost > player.steps_remaining:
                break
            if not self.engine.execute_command(ActionCommand("move", player.id, {"option": option})):
                break
            moved = True

        if player.room_key != target.key:
            if moved:
                self._show_info("地图移动", f"已移动到「{state.board[player.room_key].name}」，剩余移动力：{player.steps_remaining}。")
            else:
                self._show_info("地图移动", "目标房间当前无法通过已连接的门或楼梯到达，或步数不足。")
        self._refresh_ui()

    def _on_exploration_slot_enter(self, slot_tag: str) -> None:
        slot = self._exploration_slots.get(slot_tag)
        if not slot:
            return
        if self._exploration_hover_tag and self._exploration_hover_tag != slot_tag:
            previous = self._exploration_slots.get(self._exploration_hover_tag)
            if previous:
                self.board_canvas.itemconfigure(
                    previous["rect"], fill="#252b33", outline="#b9c4d1", width=1
                )
        self._exploration_hover_tag = slot_tag
        self.board_canvas.itemconfigure(
            slot["rect"], fill="#566575", outline="#ffffff", width=3
        )
        self.board_canvas.configure(cursor="hand2")

    def _on_exploration_slot_leave(self, slot_tag: str) -> None:
        slot = self._exploration_slots.get(slot_tag)
        if slot:
            self.board_canvas.itemconfigure(
                slot["rect"], fill="#252b33", outline="#b9c4d1", width=1
            )
        if self._exploration_hover_tag == slot_tag:
            self._exploration_hover_tag = None
            self.board_canvas.configure(cursor="")

    def _on_exploration_slot_click(self, slot_tag: str) -> None:
        """点击白色格探索新房间；使用字典命令让引擎再次校验格子是否仍有效。"""
        slot = self._exploration_slots.get(slot_tag)
        if not slot or not self.engine.state.players:
            return
        player = self.engine.current_player
        option: ExitOption = slot["option"]
        if player.control == "bot":
            self._show_info("探索", "当前是机器人回合，请等待机器人完成行动。")
            return
        if player.steps_remaining < option.cost:
            self._show_info("探索", "当前移动力不足，无法探索这个位置。")
            return
        command_option = {"direction": option.direction, "target_key": option.target_key}
        if not self.engine.execute_command(
            ActionCommand("move", player.id, {"option": command_option})
        ):
            self._show_info("探索", "这个探索位置已经失效，请重新查看地图上的白色方格。")
        self._refresh_ui()

    def _show_room_info(self, room: PlacedRoom) -> None:
        lines = [f"房间：{room.name}", f"坐标：{room.x}, {room.y}"]
        floor_label = {1: "二层", 0: "一层", -1: "地下室"}.get(room.floor, f"{room.floor}F")
        lines.append(f"楼层：{floor_label}")
        if room.symbol:
            lines.append(f"符号：{ {'omen': '预兆', 'item': '物品', 'event': '事件'}.get(room.symbol, room.symbol) }")
        desc = HT.room_effect_detail(room.effect_id) or self.engine._room_effect_desc(room.effect_id)
        if desc:
            lines.append(f"效果：{desc}")
        if room.text:
            lines.append(f"描述：{room.text}")
        self._show_info(f"房间：{room.name}", "\n".join(lines))

    def _show_player_detail(self, player_id: int) -> None:
        if not 0 <= player_id < len(self.engine.state.players):
            return
        player = self.engine.state.players[player_id]
        room = self.engine.state.board.get(player.room_key)
        room_name = room.name if room else "未知"
        _PlayerDetailDialog(self, player, self.engine.catalog, room_name, self._role_label_for_viewer(player))

    def _on_player_token_hover(self, player_id: int, event) -> None:
        if not 0 <= player_id < len(self.engine.state.players):
            return
        self._show_player_tooltip(player_id, event)

    def _show_player_tooltip(self, player_id: int, event) -> None:
        self._hide_player_tooltip()
        self._hide_room_tooltip()
        p = self.engine.state.players[player_id]
        room = self.engine.state.board.get(p.room_key)
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg="#0d1013")
        text = tk.Text(
            tip,
            bg="#0d1013",
            fg=PALETTE["text"],
            font=FONT_PANEL,
            relief="solid",
            bd=1,
            padx=10,
            pady=8,
            wrap="word",
            width=42,
            height=16,
            highlightthickness=0,
            state="normal",
        )
        text.pack()
        _config_track_tags(text)
        text.tag_configure("item", foreground=PALETTE["item"])
        text.tag_configure("muted", foreground=PALETTE["muted"])
        text.insert("end", f"{p.name} / {p.character_name}\n", "tr_label")
        text.insert("end", f"阵营：{self._role_label_for_viewer(p)}    位置：{room.name if room else '未知'}\n", "tr_label")
        text.insert("end", "属性：\n", "tr_label")
        for stat in ("speed", "might", "sanity", "knowledge"):
            _append_stat_track(text, p, stat)
        text.insert("end", "\n物品：\n", "tr_label")
        if p.items:
            for cid in p.items:
                card = self.engine.catalog.cards[cid]
                usage = HT.card_usage(card)
                if usage:
                    text.insert("end", f"· {card.name}：{usage}\n", "item")
                else:
                    text.insert("end", f"· {card.name}（{card.text}）\n", "item")
        else:
            text.insert("end", "  (无)\n", "muted")
        text.configure(state="disabled")
        tip.geometry(f"+{event.x_root + 16}+{event.y_root + 16}")
        self._tooltip = tip

    def _hide_player_tooltip(self) -> None:
        tip = getattr(self, "_tooltip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
            self._tooltip = None

    def _show_room_tooltip(self, room, event) -> None:
        """悬停房间时显示该房间的名字/楼层/符号/特殊效果。"""
        self._hide_player_tooltip()
        self._hide_room_tooltip()
        lines = [f"房间：{room.name}"]
        floor_label = {1: "二层", 0: "一层", -1: "地下室"}.get(room.floor, f"{room.floor}F")
        lines.append(f"楼层：{floor_label}")
        if room.symbol:
            sym = {"omen": "预兆", "item": "物品", "event": "事件"}.get(room.symbol, room.symbol)
            lines.append(f"符号：进入触发{sym}卡")
        desc = HT.room_effect_detail(room.effect_id) or self.engine._room_effect_desc(room.effect_id)
        if desc:
            lines.append(f"效果：{desc}")
        if room.text:
            lines.append(f"描述：{room.text}")
        occupants = [p.name for p in self.engine.state.players if not p.dead and p.room_key == room.key]
        if occupants:
            lines.append("玩家：" + "、".join(occupants))
        items = self.engine.room_items(room.key)
        if items:
            lines.append("物品：" + "、".join(self.engine.catalog.cards[c].name for c in items))
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg="#0d1013")
        tk.Label(
            tip,
            text="\n".join(lines),
            bg="#0d1013",
            fg=PALETTE["text"],
            font=FONT_PANEL,
            justify="left",
            padx=10,
            pady=8,
            bd=1,
            relief="solid",
            wraplength=400,
        ).pack()
        tip.geometry(f"+{event.x_root + 16}+{event.y_root + 16}")
        self._room_tooltip = tip

    def _hide_room_tooltip(self) -> None:
        tip = getattr(self, "_room_tooltip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
            self._room_tooltip = None

    def _set_action_button(self, button: tk.Button, enabled: bool, reason: str = "") -> None:
        button.config(
            state="normal" if enabled else "disabled",
            bg=PALETTE["panel2"] if enabled else PALETTE["panel3"],
            cursor="hand2" if enabled else "arrow",
        )
        self._action_button_reasons[button] = "" if enabled else reason

    def _show_action_button_hint(self, button: tk.Button) -> None:
        label = self._action_button_labels.get(button, "操作")
        reason = self._action_button_reasons.get(button, "")
        if reason:
            self.action_hint.config(text=f"{label}不可用：{reason}", fg=PALETTE["muted"])
        else:
            self.action_hint.config(text=f"{label}可用。", fg=PALETTE["success"])

    def _refresh_action_hint(self) -> None:
        if not hasattr(self, "action_hint"):
            return
        enabled = [
            label
            for button, label in self._action_button_labels.items()
            if str(button["state"]) == "normal"
        ]
        if enabled:
            self.action_hint.config(text="当前可用：" + "、".join(enabled), fg=PALETTE["success"])
            return
        reasons = [reason for reason in self._action_button_reasons.values() if reason]
        text = reasons[0] if reasons else "暂无可用行动。"
        self.action_hint.config(text="当前不可行动：" + text, fg=PALETTE["muted"])

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _show_info(self, title: str, message: str) -> None:
        dialog = _InfoDialog(self, title, message)
        self.wait_window(dialog.top)

    def _show_error(self, title: str, message: str) -> None:
        dialog = _InfoDialog(self, title, message, error=True)
        self.wait_window(dialog.top)

    def _default_save_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            base = Path(sys.argv[0]).resolve().parent
        else:
            base = Path(__file__).resolve().parent
        save_dir = base / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _action_save_game(self) -> None:
        if not self.engine.state.players:
            self._show_info("保存", "还没有开始游戏。")
            return
        initial = self._default_save_dir() / "local_save.json"
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="保存游戏",
            initialdir=str(initial.parent),
            initialfile=initial.name,
            defaultextension=".json",
            filetypes=[("山中小屋存档", "*.json"), ("所有文件", "*.*")],
        )
        if not filename:
            return
        try:
            path = self.engine.save_to_file(filename)
        except Exception as exc:
            self._show_error("保存失败", str(exc))
            return
        self._show_info("保存成功", f"已保存到：\n{path}")

    def _action_load_game(self) -> None:
        save_dir = self._default_save_dir()
        filename = filedialog.askopenfilename(
            parent=self,
            title="读取游戏",
            initialdir=str(save_dir),
            filetypes=[("山中小屋存档", "*.json"), ("所有文件", "*.*")],
        )
        if not filename:
            return
        if self.engine.state.players:
            ok = self.engine.prompter.confirm("读取游戏", "读取存档会覆盖当前局，确定继续吗？")
            if not ok:
                return
        try:
            self.engine.load_from_file(filename)
        except Exception as exc:
            self._show_error("读取失败", str(exc))
            return
        self._build_game_board()
        self._build_legend()
        self._refresh_ui()
        self._show_info("读取成功", "存档已载入。")

    def _action_view_haunt_script(self) -> None:
        payload = self._haunt_text_for_viewer()
        viewer = self._viewer_player()
        if payload is None or viewer is None:
            self._show_info("剧本", "作祟开始后才能查看对应剧本。")
            return
        title, text = payload
        if not text.strip():
            self._show_info("剧本", "当前视角没有可查看的剧本文本。")
            return
        if self._should_confirm_private_view():
            ok = self.engine.prompter.confirm("查看剧本", f"请确认现在屏幕前是 {viewer.name}。")
            if not ok:
                return
        dialog = _TextDialog(self, title, text)
        self.wait_window(dialog.top)

    def _action_move(self) -> None:
        player = self.engine.current_player
        options = self.engine.available_move_options(player)
        if not options:
            self._show_info("移动", "当前没有可走的路线。")
            return
        labels = [option.label for option in options]
        idx = self.engine.prompter.choose_from_list("移动", "选择一个移动目标", labels)
        if idx is None:
            return
        if self.engine.move_player(player, options[idx]):
            self._refresh_ui()

    def _action_use_item(self) -> None:
        player = self.engine.current_player
        if not player.items:
            self._show_info("物品", "你现在没有物品。")
            return
        labels = [self.engine.catalog.cards[card_id].name for card_id in player.items]
        idx = self.engine.prompter.choose_from_list("使用物品", "选择一个物品", labels)
        if idx is None:
            return
        self.engine.use_item(player, player.items[idx])
        self._refresh_ui()

    def _action_pickup(self) -> None:
        player = self.engine.current_player
        room_items = self.engine.room_items(player.room_key)
        if not room_items:
            self._show_info("拾取", "这个房间里没有可拾取的物品。")
            return
        labels = [self.engine.catalog.cards[card_id].name for card_id in room_items]
        idx = self.engine.prompter.choose_from_list("拾取", "选择要拿起的物品", labels)
        if idx is None:
            return
        if self.engine.pickup_item(player, room_items[idx]):
            self._refresh_ui()

    def _action_drop(self) -> None:
        player = self.engine.current_player
        if not player.items:
            self._show_info("丢弃", "你现在没有可以丢弃的物品。")
            return
        labels = [self.engine.catalog.cards[card_id].name for card_id in player.items]
        idx = self.engine.prompter.choose_from_list("丢弃", "选择要丢下的物品", labels)
        if idx is None:
            return
        if self.engine.drop_item(player, player.items[idx]):
            self._refresh_ui()

    def _action_trade(self) -> None:
        player = self.engine.current_player
        targets = [
            other
            for other in self.engine.state.players
            if other.id != player.id and not other.dead and other.room_key == player.room_key
        ]
        if not targets:
            self._show_info("交易", "同房间没有其他玩家。")
            return
        target_idx = self.engine.prompter.choose_from_list(
            "交易",
            "选择要交易的对象",
            [self.engine._player_label(other) for other in targets],
        )
        if target_idx is None:
            return
        target = targets[target_idx]
        offer_ids = [card_id for card_id in player.items if self.engine.catalog.cards[card_id].tradeable]
        if not offer_ids:
            self._show_info("交易", "你没有可交易的物品。")
            return
        offer_idx = self.engine.prompter.choose_from_list(
            "交易",
            "选择要给出的物品",
            [self.engine.catalog.cards[card_id].name for card_id in offer_ids],
        )
        if offer_idx is None:
            return
        target_ids = [card_id for card_id in target.items if self.engine.catalog.cards[card_id].tradeable]
        swap_choice = None
        if target_ids:
            swap_labels = ["只给予"] + [self.engine.catalog.cards[card_id].name for card_id in target_ids]
            swap_choice = self.engine.prompter.choose_from_list("交易", "要不要换一件回来？", swap_labels)
            if swap_choice is None:
                return
        target_card_id = None if not target_ids or swap_choice == 0 else target_ids[swap_choice - 1]
        if self.engine.trade_item(player, target, offer_ids[offer_idx], target_card_id):
            self._refresh_ui()

    def _action_attack(self) -> None:
        player = self.engine.current_player
        if self.engine.state.phase != "HAUNT_PHASE":
            self._show_info("攻击", "作祟开始后才能攻击。")
            return
        weapons = self.engine.available_attack_weapons(player)
        weapon_card_id: str | None = None
        ranged_attack = False
        if weapons:
            labels = ["徒手攻击"] + [self.engine.catalog.cards[card_id].name for card_id in weapons]
            idx = self.engine.prompter.choose_from_list("攻击", "选择攻击方式", labels)
            if idx is None:
                return
            if idx > 0:
                weapon_card_id = weapons[idx - 1]
                ranged_attack = "ranged" in self.engine.catalog.cards[weapon_card_id].tags
        targets = self.engine.available_attack_targets(player, ranged=ranged_attack)
        if not targets:
            if ranged_attack:
                self._show_info("攻击", "没有可用的远程目标。")
            else:
                self._show_info("攻击", "同房间没有可攻击目标。")
            return
        labels = [self._target_label(target) for target in targets]
        idx = self.engine.prompter.choose_from_list("攻击", "选择目标", labels)
        if idx is None:
            return
        self.engine.attack(player, targets[idx], weapon_card_id, ranged_attack)
        self._refresh_ui()

    def _action_haunt_action(self) -> None:
        player = self.engine.current_player
        actions = self.engine.available_haunt_actions(player)
        if not actions:
            self._show_info("剧本行动", "当前没有可执行的剧本行动。")
            return
        labels = [
            f"{action.label}：{action.detail}" if action.detail else action.label
            for action in actions
        ]
        idx = self.engine.prompter.choose_from_list("剧本行动", "选择要执行的剧本行动", labels)
        if idx is None:
            return
        action = actions[idx]
        self.engine.perform_haunt_action(player, action.id, action.data)
        self._refresh_ui()

    def _action_end_turn(self) -> None:
        self.engine.end_turn()
        self._refresh_ui()

    def _target_label(self, target: object) -> str:
        if isinstance(target, Player):
            return f"{target.name} / {target.character_name}"
        if getattr(target, "stunned_turns", 0) > 0:
            return f"{target.name}（昏迷{target.stunned_turns}）"
        return target.name

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _refresh_ui(self) -> None:
        # 每步单独容错：任何一步异常都不影响后续（尤其保证按钮一定刷新）
        steps = [
            ("status", self._refresh_status),
            ("player_panel", self._refresh_player_panel),
            ("deck", self._refresh_deck_panel),
            ("log", self._refresh_log),
            ("board", lambda: self._redraw_board() if hasattr(self, "board_canvas") else None),
            ("buttons", self._refresh_buttons),
        ]
        for _name, fn in steps:
            try:
                fn()
            except Exception as exc:
                print(f"[本地] 刷新[{_name}] 异常: {exc!r}")

    def _refresh_status(self) -> None:
        state = self.engine.state
        if not state.players:
            self.status_label.config(text="尚未开始")
            return
        current = self.engine.current_player
        current_name = f"{current.name}（机器人）" if current.control == "bot" else current.name
        phase_label = {
            "SETUP": "设置",
            "EXPLORE": "探索",
            "HAUNT_REVEAL": "作祟揭示",
            "HAUNT_PHASE": "作祟阶段",
            "GAME_OVER": "结束",
        }.get(state.phase, state.phase)
        self.status_label.config(
            text=f"阶段：{phase_label}   回合：{state.turn_count}   当前：{current_name}   预兆：{state.omens_drawn}   剧本：{state.haunt.name if state.haunt else '未揭示'}"
        )

    def _refresh_player_panel(self) -> None:
        state = self.engine.state
        self.player_info.config(state="normal")
        self.player_info.delete("1.0", "end")
        if not state.players:
            self.player_info.config(state="disabled")
            return
        current = self.engine.current_player
        self.player_info.insert("end", f"当前玩家：{current.name} / {current.character_name}\n", "tr_label")
        self.player_info.insert("end", f"身份：{self._role_label_for_viewer(current)}\n", "tr_label")
        self.player_info.insert(
            "end",
            f"位置：{state.board[current.room_key].name if current.room_key in state.board else '未知'}\n",
            "tr_label",
        )
        self.player_info.insert(
            "end",
            f"行动：步数 {current.steps_remaining}，攻击 {'已用' if current.attack_used else '未用'}，物品 {'已用' if current.item_used else '未用'}\n\n",
            "tr_label",
        )
        self.player_info.insert("end", "属性（卡尺）：\n", "tr_label")
        for stat in ("speed", "might", "sanity", "knowledge"):
            _append_stat_track(self.player_info, current, stat)
        lines = ["", "物品："]
        if current.items:
            for card_id in current.items:
                card = self.engine.catalog.cards[card_id]
                lines.append(f"  - {HT.card_short(card)}")
        else:
            lines.append("  (无)")
        carried = self.engine.tokens_held_by(current.id)
        lines.append("")
        lines.append("携带令牌：")
        if carried:
            lines.append("  " + "，".join(t.label or t.kind for t in carried))
        else:
            lines.append("  (无)")
        lines.append("")
        lines.append("同伴：")
        if current.companions:
            for card_id in current.companions:
                card = self.engine.catalog.cards[card_id]
                lines.append(f"  - {card.name}")
        else:
            lines.append("  (无)")
        room = state.board.get(current.room_key)
        lines.append("")
        lines.append("房间：")
        if room:
            room_symbol = room.symbol or "无符号"
            lines.append(f"  {room.name} / {room_symbol}")
            room_items = self.engine.room_items(room.key)
            if room_items:
                lines.append("  物品：" + "，".join(self.engine.catalog.cards[card_id].name for card_id in room_items))
            else:
                lines.append("  物品：(无)")
            room_tokens = self.engine.tokens_in_room(room.key)
            if room_tokens:
                lines.append("  令牌：" + "，".join(t.label or t.kind for t in room_tokens))
            occupants: list[str] = []
            for other in state.players:
                if other.id == current.id or other.dead or other.room_key != room.key:
                    continue
                occupants.append(f"{other.name}/{other.character_name}")
            for monster in state.monsters:
                if monster.room_key != room.key:
                    continue
                label = monster.name
                if monster.stunned_turns > 0:
                    label = f"{label}(昏迷{monster.stunned_turns})"
                occupants.append(label)
            lines.append("  同房间：" + ("，".join(occupants) if occupants else "(无)"))
        self.player_info.insert("end", "\n".join(lines))
        self.player_info.config(state="disabled")
        self.player_info.see("1.0")

    def _haunt_progress_summary(self, viewer) -> list[str]:
        """问当前剧本 handler 要额外的进度摘要行（duck-typed，可选钩子）。"""
        try:
            handler = self.engine._mode_handler()
        except Exception:
            return []
        summary = getattr(handler, "progress_summary", None)
        if not callable(summary):
            return []
        try:
            return list(summary(self.engine, viewer) or [])
        except Exception:
            return []

    def _refresh_deck_panel(self) -> None:
        state = self.engine.state
        lines = [
            f"牌堆余量：",
            f"  预兆 {len(state.card_decks.get('omen', []))} / 弃牌 {len(state.card_discards.get('omen', []))}",
            f"  物品 {len(state.card_decks.get('item', []))} / 弃牌 {len(state.card_discards.get('item', []))}",
            f"  事件 {len(state.card_decks.get('event', []))} / 弃牌 {len(state.card_discards.get('event', []))}",
        ]
        if state.haunt:
            viewer = self._viewer_player()
            viewer_role = self._role_label_for_viewer(viewer) if viewer else "未知"
            lines.extend([
                "",
                f"剧本：#{state.haunt.id} {state.haunt.name}",
                f"你的身份：{viewer_role}",
                "使用“剧本”按钮查看你的手册",
            ])
            haunt_rule = state.meta.get("haunt_rule", {})
            tracks = haunt_rule.get("tracks", {}) if isinstance(haunt_rule, dict) else {}
            if tracks:
                lines.append("")
                lines.append("公开进度：")
                for track in tracks.values():
                    # 叛徒轨道只存于隐藏规则层，不能出现在公共面板。
                    if track.get("side") == "traitor":
                        continue
                    label = track.get("label", "进度")
                    value = track.get("value", 0)
                    target = track.get("target", 0)
                    lines.append(f"  {label} {_track_cells(value, target)}  {value}/{target}")
            summary = self._haunt_progress_summary(viewer)
            if summary:
                lines.append("")
                lines.append("剧本进度：")
                lines.extend(f"  {row}" for row in summary)
        self.deck_info.config(text="\n".join(lines))

    def _refresh_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "\n".join(self.engine.state.log[-80:]))
        self.log_text.config(state="disabled")
        self.log_text.see("end")

    def _refresh_buttons(self) -> None:
        state = self.engine.state
        if not state.players:
            for button in (self.btn_move, self.btn_use, self.btn_pickup, self.btn_drop, self.btn_trade, self.btn_attack, self.btn_haunt_action, self.btn_script, self.btn_end):
                self._set_action_button(button, False, "开始游戏或读取存档后可用。")
            self.btn_save.config(state="disabled")
            self.btn_load.config(state="normal")
            self._refresh_action_hint()
            return
        current = self.engine.current_player
        is_human_turn = current.control != "bot"
        is_over = state.phase == "GAME_OVER"
        room_items = self.engine.room_items(current.room_key)
        same_room_players = [
            other
            for other in state.players
            if other.id != current.id and not other.dead and other.room_key == current.room_key
        ]
        weapons = self.engine.available_attack_weapons(current)
        ranged_weapon = any("ranged" in self.engine.catalog.cards[card_id].tags for card_id in weapons)
        has_attack_target = bool(self.engine.available_attack_targets(current) or (ranged_weapon and self.engine.available_attack_targets(current, ranged=True)))
        has_haunt_action = bool(self.engine.available_haunt_actions(current))

        turn_reason = "当前是机器人回合，稍等自动行动。" if not is_human_turn else ""
        over_reason = "游戏已经结束。" if is_over else ""
        base_reason = over_reason or turn_reason
        self._set_action_button(
            self.btn_move,
            is_human_turn and current.steps_remaining > 0 and not current.movement_stopped and not is_over,
            base_reason or ("移动点数已用完。" if current.steps_remaining <= 0 else "当前移动被房间或效果终止。"),
        )
        self._set_action_button(
            self.btn_use,
            is_human_turn and bool(current.items) and not is_over,
            base_reason or "当前玩家没有物品。",
        )
        self._set_action_button(
            self.btn_pickup,
            is_human_turn and bool(room_items) and not is_over,
            base_reason or "当前房间没有可拾取物品。",
        )
        self._set_action_button(
            self.btn_drop,
            is_human_turn and bool(current.items) and not is_over,
            base_reason or "当前玩家没有可丢弃物品。",
        )
        self._set_action_button(
            self.btn_trade,
            is_human_turn and bool(current.items) and bool(same_room_players) and not is_over,
            base_reason or ("当前玩家没有可交易物品。" if not current.items else "同房间没有其他玩家。"),
        )
        self._set_action_button(
            self.btn_attack,
            is_human_turn and state.phase == "HAUNT_PHASE" and not current.attack_used and has_attack_target and not is_over,
            base_reason or (
                "作祟开始后才能攻击。"
                if state.phase != "HAUNT_PHASE"
                else "本回合已经攻击过。"
                if current.attack_used
                else "没有可攻击目标。"
            ),
        )
        self._set_action_button(
            self.btn_haunt_action,
            is_human_turn and has_haunt_action and not is_over,
            base_reason or "当前没有可执行的剧本行动。",
        )
        viewer = self._viewer_player()
        can_view_script = bool(state.haunt and viewer is not None and viewer.control != "bot")
        self._set_action_button(
            self.btn_script,
            can_view_script,
            "作祟开始后才有剧本可看。" if not state.haunt else "当前视角不能查看剧本。",
        )
        self._set_action_button(
            self.btn_end,
            is_human_turn and not is_over,
            base_reason or "当前不能结束回合。",
        )
        self.btn_save.config(state="normal")
        self.btn_load.config(state="normal")
        self._refresh_action_hint()

    def _state_fingerprint(self):
        state = self.engine.state
        log_tail = tuple(state.log[-6:])
        players = tuple(
            (p.id, p.room_key, p.role, p.dead, p.steps_remaining,
             tuple(p.items), tuple(p.companions), p.attack_used, p.item_used,
             p.extra_check_rerolls, p.next_check_auto_success,
             tuple(sorted(p.stats.items())),
             tuple(sorted(p.stat_positions.items())),
             tuple(sorted(p.overflow.items())))
            for p in state.players
        )
        board = tuple(sorted((k, r.x, r.y, r.floor, r.revealed, tuple(r.doors)) for k, r in state.board.items()))
        monsters = tuple((m.id, m.room_key, m.stunned_turns) for m in state.monsters)
        haunt_rule = state.meta.get("haunt_rule", {})
        haunt_tracks = tuple(
            sorted(
                (key, value.get("value", 0), value.get("target", 0))
                for key, value in haunt_rule.get("tracks", {}).items()
            )
        ) if isinstance(haunt_rule, dict) else ()
        return (
            state.phase, state.turn_count, state.turn_index, state.omens_drawn,
            state.winner, state.haunt.id if state.haunt else None,
            log_tail, players, board, monsters, haunt_tracks,
        )

    def _idle_poll(self) -> None:
        if getattr(self, "_closing", False):
            return
        self._maybe_run_bot_turn()
        if hasattr(self, "board_canvas"):
            fp = self._state_fingerprint()
            if fp != self._last_fp:
                self._last_fp = fp
                self._refresh_ui()
        self._idle_after = self.after(300, self._idle_poll)

    def _maybe_run_bot_turn(self) -> None:
        state = self.engine.state
        if self._bot_busy or not state.players or state.phase == "GAME_OVER":
            return
        current = self.engine.current_player
        if current.control != "bot" or current.dead:
            return
        self._bot_busy = True
        try:
            self.bot_controller.take_turn(self.engine)
        except Exception as exc:
            self.engine._log(f"机器人 {current.name} 行动异常，跳过。")
            self.engine.end_turn()
            print("[本地] AI 异常：", exc)
        finally:
            self._bot_busy = False

    def destroy(self) -> None:
        self._closing = True
        idle_after = getattr(self, "_idle_after", None)
        if idle_after is not None:
            try:
                self.after_cancel(idle_after)
            except Exception:
                pass
            self._idle_after = None
        super().destroy()


def run_app() -> None:
    app = GameApp()
    app.mainloop()
