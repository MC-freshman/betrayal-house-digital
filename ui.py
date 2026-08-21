from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

try:
    from .engine import DecisionProvider, GameEngine, ExitOption
    from .models import GameState, OPPOSITE, Player, PlacedRoom
except ImportError:  # pragma: no cover - direct script execution
    from engine import DecisionProvider, GameEngine, ExitOption  # type: ignore
    from models import GameState, OPPOSITE, Player, PlacedRoom  # type: ignore


PALETTE = {
    "bg": "#1f232a",
    "panel": "#262b33",
    "panel2": "#313743",
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


class TkDecisionProvider(DecisionProvider):
    def __init__(self, root: tk.Tk):
        self.root = root

    def notify(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self.root)

    def confirm(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message, parent=self.root)

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


class _ChoiceDialog:
    def __init__(self, root: tk.Tk, title: str, message: str, options: list[str]) -> None:
        self.result: int | None = None
        self.top = tk.Toplevel(root)
        self.top.title(title)
        self.top.configure(bg=PALETTE["panel"])
        self.top.transient(root)
        self.top.grab_set()
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


class GameApp(tk.Tk):
    def __init__(self) -> None:
        _configure_windows_dpi_awareness()
        super().__init__()
        self.title("山中小屋 - 本地单机版")
        self.geometry("1240x780")
        self.minsize(1180, 720)
        self.configure(bg=PALETTE["bg"])

        self.engine = GameEngine(prompter=TkDecisionProvider(self))
        self.selected_player_index = 0
        self.current_move_options: list[ExitOption] = []
        self.current_attack_targets: list[object] = []

        self._build_ui()
        self._build_start_screen()
        self.after(100, self._idle_poll)

    # ------------------------------------------------------------------
    # UI structure
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.status_bar = tk.Frame(self, bg=PALETTE["panel"], height=48)
        self.status_bar.pack(fill="x", side="top")
        self.status_bar.pack_propagate(False)

        self.status_label = tk.Label(
            self.status_bar,
            text="尚未开始",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            anchor="w",
            padx=16,
            font=FONT_UI_BOLD,
        )
        self.status_label.pack(fill="both", expand=True)

        body = tk.Frame(self, bg=PALETTE["bg"])
        body.pack(fill="both", expand=True)

        body.grid_columnconfigure(0, weight=1, minsize=800)
        body.grid_columnconfigure(1, weight=0, minsize=380)
        body.grid_rowconfigure(0, weight=1)

        self.map_frame = tk.Frame(body, bg=PALETTE["bg"])
        self.map_frame.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)

        right = tk.Frame(body, bg=PALETTE["bg"], width=380)
        right.grid(row=0, column=1, sticky="ns", padx=(6, 12), pady=12)
        right.grid_propagate(False)

        self.info_panel = tk.Frame(
            right,
            bg=PALETTE["panel"],
            width=360,
            height=300,
            highlightthickness=1,
            highlightbackground="#111",
        )
        self.info_panel.pack(fill="x")
        self.info_panel.pack_propagate(False)

        self.info_scroll = tk.Scrollbar(self.info_panel, orient="vertical")
        self.player_info = tk.Text(
            self.info_panel,
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
        self.player_info.bind(
            "<MouseWheel>",
            lambda e: self.player_info.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

        self.action_panel = tk.Frame(
            right,
            bg=PALETTE["panel"],
            width=360,
            height=220,
            highlightthickness=1,
            highlightbackground="#111",
        )
        self.action_panel.pack(fill="x", pady=(12, 0))
        self.action_panel.pack_propagate(False)

        button_grid = tk.Frame(self.action_panel, bg=PALETTE["panel"])
        button_grid.pack(fill="both", expand=True, padx=10, pady=10)

        button_style = dict(
            bg=PALETTE["panel2"],
            fg=PALETTE["text"],
            relief="flat",
            activebackground=PALETTE["accent"],
            activeforeground="#111",
            font=FONT_UI_BOLD,
            padx=10,
            pady=8,
            height=2,
            cursor="hand2",
        )
        self.btn_move = tk.Button(button_grid, text="移动", command=self._action_move, **button_style)
        self.btn_use = tk.Button(button_grid, text="使用", command=self._action_use_item, **button_style)
        self.btn_pickup = tk.Button(button_grid, text="拾取", command=self._action_pickup, **button_style)
        self.btn_drop = tk.Button(button_grid, text="丢弃", command=self._action_drop, **button_style)
        self.btn_trade = tk.Button(button_grid, text="交易", command=self._action_trade, **button_style)
        self.btn_attack = tk.Button(button_grid, text="攻击", command=self._action_attack, **button_style)
        self.btn_end = tk.Button(button_grid, text="结束", command=self._action_end_turn, **button_style)

        buttons = (
            (self.btn_move, 0, 0),
            (self.btn_use, 0, 1),
            (self.btn_pickup, 1, 0),
            (self.btn_drop, 1, 1),
            (self.btn_trade, 2, 0),
            (self.btn_attack, 2, 1),
        )
        for button, row, col in buttons:
            button.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            button.config(bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat")
        self.btn_end.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=3, pady=(8, 3))
        self.btn_end.config(bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat")
        for row in range(4):
            button_grid.grid_rowconfigure(row, weight=1, minsize=42)
        for col in range(2):
            button_grid.grid_columnconfigure(col, weight=1, uniform="action")

        self.deck_panel = tk.Frame(
            right,
            bg=PALETTE["panel"],
            width=360,
            height=110,
            highlightthickness=1,
            highlightbackground="#111",
        )
        self.deck_panel.pack(fill="x", pady=(12, 0))
        self.deck_panel.pack_propagate(False)

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

        self.log_panel = tk.Frame(right, bg=PALETTE["panel"], width=360, highlightthickness=1, highlightbackground="#111")
        self.log_panel.pack(fill="both", expand=True, pady=(12, 0))

        self.log_scroll = tk.Scrollbar(self.log_panel, orient="vertical")
        self.log_text = tk.Text(
            self.log_panel,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            wrap="word",
            borderwidth=0,
            font=FONT_PANEL,
            yscrollcommand=self.log_scroll.set,
        )
        self.log_scroll.config(command=self.log_text.yview)
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
        card.place(relx=0.5, rely=0.5, anchor="center", width=680, height=640)

        title = tk.Label(
            card,
            text="山中小屋",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=FONT_TITLE,
        )
        title.pack(anchor="n", pady=(24, 8))

        subtitle = tk.Label(
            card,
            text="先配置 3 到 6 名玩家，然后开始本地热座对局。",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=FONT_SUBTITLE,
        )
        subtitle.pack(anchor="n", pady=(0, 20))

        self.start_entries: list[tk.Entry] = []
        self.character_vars: list[tk.StringVar] = []

        roster = tk.Frame(card, bg=PALETTE["panel"])
        roster.pack(fill="both", expand=True, padx=18)

        character_names = [face.name for face in self.engine.catalog.characters.values()]
        for index in range(6):
            row = tk.Frame(roster, bg=PALETTE["panel"])
            row.pack(fill="x", pady=6)
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
            entry.insert(0, f"玩家{index + 1}")
            entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), ipady=4)
            self.start_entries.append(entry)

            var = tk.StringVar(value=character_names[index % len(character_names)])
            self.character_vars.append(var)
            option = tk.OptionMenu(row, var, *character_names)
            option.config(bg=PALETTE["panel2"], fg=PALETTE["text"], highlightthickness=0, width=16, font=FONT_UI)
            option["menu"].config(bg=PALETTE["panel2"], fg=PALETTE["text"])
            option.grid(row=0, column=2, sticky="e")

        footer = tk.Frame(card, bg=PALETTE["panel"])
        footer.pack(fill="x", padx=18, pady=(10, 18))
        tk.Button(
            footer,
            text="开始游戏",
            command=self._begin_game_from_form,
            bg=PALETTE["accent"],
            fg="#111",
            relief="flat",
            padx=12,
            pady=8,
            font=FONT_UI_BOLD,
        ).pack(side="right")

        note = tk.Label(
            card,
            text="事件、房间和作祟都已整理成可直接试玩的版本，少量细节按主题摘要处理。",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            wraplength=540,
            justify="left",
            font=FONT_UI,
        )
        note.pack(anchor="w", padx=18, pady=(0, 18))

    def _clear_map(self) -> None:
        for widget in self.map_frame.winfo_children():
            widget.destroy()

    def _begin_game_from_form(self) -> None:
        configs = []
        used_characters = set()
        for entry, var in zip(self.start_entries, self.character_vars):
            name = entry.get().strip()
            if not name:
                continue
            character_name = var.get()
            character = next(
                (face for face in self.engine.catalog.characters.values() if face.name == character_name),
                None,
            )
            if not character:
                continue
            if character.id in used_characters:
                messagebox.showerror("角色重复", "同一角色不能给两名玩家使用。", parent=self)
                return
            used_characters.add(character.id)
            configs.append({"name": name, "character_id": character.id})

        if len(configs) < 3:
            messagebox.showerror("人数不足", "至少需要 3 名玩家。", parent=self)
            return
        self.engine.start_new_game(configs)
        self._build_game_board()
        self._refresh_ui()
        self.engine.start_turn()
        self._refresh_ui()

    # ------------------------------------------------------------------
    # Board rendering
    # ------------------------------------------------------------------
    def _build_game_board(self) -> None:
        self._clear_map()
        scroll = tk.Scrollbar(self.map_frame, orient="vertical")
        canvas = tk.Canvas(self.map_frame, bg="#171b21", highlightthickness=0, yscrollcommand=scroll.set)
        scroll.config(command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        self.board_canvas = canvas
        self.board_scroll = scroll
        self.tile_widgets: dict[str, dict] = {}
        self._redraw_board()

    def _redraw_board(self) -> None:
        canvas = self.board_canvas
        canvas.delete("all")
        state = self.engine.state
        if not state.board:
            return

        # 地图是三维的（地下室/一层/二层），这里按楼层分成三条竖向带分别排版，
        # 避免不同楼层同坐标的房间互相覆盖。
        floor_order = [1, 0, -1]  # 自上而下：二层、一层、地下室
        floor_label = {1: "二层 (2F)", 0: "一层 (1F)", -1: "地下室 (-1F)"}
        floor_rooms: dict[int, list] = {f: [] for f in floor_order}
        for room in state.board.values():
            floor_rooms[room.floor].append(room)

        canvas_w = max(canvas.winfo_width(), 720)
        tile_size = 110
        for f in floor_order:
            rooms = floor_rooms[f]
            if not rooms:
                continue
            xs = [r.x for r in rooms]
            span = max(xs) - min(xs) + 1
            tile_size = min(tile_size, int((canvas_w - 90) / span))
        tile_size = max(56, tile_size)

        margin_x = 40
        label_h = 22
        gap = 30

        # 预计算每个楼层的网格原点与最小坐标。
        # 各楼层共用同一个全局 min_x，保证二层/一层/地下室在水平方向上对齐。
        all_xs = [room.x for room in state.board.values()]
        global_min_x = min(all_xs) if all_xs else 0
        floor_meta: dict[int, tuple[int, int, int, int]] = {}
        y_cursor = 16
        for f in floor_order:
            rooms = floor_rooms[f]
            if not rooms:
                continue
            xs = [r.x for r in rooms]
            ys = [r.y for r in rooms]
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

            rect = canvas.create_rectangle(
                px,
                py,
                px + tile_size - 8,
                py + tile_size - 8,
                fill=color,
                outline="#111",
                width=2,
            )
            canvas.create_text(
                px + (tile_size - 8) / 2,
                py + 22,
                text=room.name,
                fill=PALETTE["text"],
                width=tile_size - 24,
                font=("Arial", 10, "bold"),
            )
            canvas.create_text(
                px + (tile_size - 8) / 2,
                py + 50,
                text=floor_label.get(room.floor, f"{room.floor}F"),
                fill=PALETTE["muted"],
                font=("Arial", 9),
            )
            # 门标记：在对应边上画小方块，直观表示该方向有门
            ts = tile_size - 8
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

        # 玩家棋子（当前玩家用金色描边高亮）
        current_player_id = state.turn_order[state.turn_index % len(state.turn_order)] if state.turn_order else None
        for player in state.players:
            if player.room_key not in state.board:
                continue
            room = state.board[player.room_key]
            px, py = room_px(room)
            index = player.id
            circle_x = px + 24 + (index % 3) * 26
            circle_y = py + tile_size - 34 + (index // 3) * 12
            color = PALETTE["hero"]
            outline = "#101010"
            width = 1
            if player.dead:
                color = PALETTE["muted"]
            elif current_player_id == player.id:
                outline = PALETTE["accent"]
                width = 2
            canvas.create_oval(circle_x, circle_y, circle_x + 14, circle_y + 14, fill=color, outline=outline, width=width)

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

        canvas.configure(scrollregion=canvas.bbox("all"))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _action_move(self) -> None:
        player = self.engine.current_player
        options = self.engine.available_move_options(player)
        if not options:
            messagebox.showinfo("移动", "当前没有可走的路线。", parent=self)
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
            messagebox.showinfo("物品", "你现在没有物品。", parent=self)
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
            messagebox.showinfo("拾取", "这个房间里没有可拾取的物品。", parent=self)
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
            messagebox.showinfo("丢弃", "你现在没有可以丢弃的物品。", parent=self)
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
            messagebox.showinfo("交易", "同房间没有其他玩家。", parent=self)
            return
        target_idx = self.engine.prompter.choose_from_list(
            "交易",
            "选择要交易的对象",
            [self._player_label(other) for other in targets],
        )
        if target_idx is None:
            return
        target = targets[target_idx]
        offer_ids = [card_id for card_id in player.items if self.engine.catalog.cards[card_id].tradeable]
        if not offer_ids:
            messagebox.showinfo("交易", "你没有可交易的物品。", parent=self)
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
            messagebox.showinfo("攻击", "作祟开始后才能攻击。", parent=self)
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
                messagebox.showinfo("攻击", "没有可用的远程目标。", parent=self)
            else:
                messagebox.showinfo("攻击", "同房间没有可攻击目标。", parent=self)
            return
        labels = [self._target_label(target) for target in targets]
        idx = self.engine.prompter.choose_from_list("攻击", "选择目标", labels)
        if idx is None:
            return
        self.engine.attack(player, targets[idx], weapon_card_id, ranged_attack)
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
        self._refresh_status()
        self._refresh_player_panel()
        self._refresh_deck_panel()
        self._refresh_log()
        if hasattr(self, "board_canvas"):
            self._redraw_board()
        self._refresh_buttons()

    def _refresh_status(self) -> None:
        state = self.engine.state
        if not state.players:
            self.status_label.config(text="尚未开始")
            return
        current = self.engine.current_player
        phase_label = {
            "SETUP": "设置",
            "EXPLORE": "探索",
            "HAUNT_REVEAL": "作祟揭示",
            "HAUNT_PHASE": "作祟阶段",
            "GAME_OVER": "结束",
        }.get(state.phase, state.phase)
        self.status_label.config(
            text=f"阶段：{phase_label}   回合：{state.turn_count}   当前：{current.name}   预兆：{state.omens_drawn}   剧本：{state.haunt.name if state.haunt else '未揭示'}"
        )

    def _refresh_player_panel(self) -> None:
        state = self.engine.state
        self.player_info.config(state="normal")
        self.player_info.delete("1.0", "end")
        if not state.players:
            self.player_info.config(state="disabled")
            return
        current = self.engine.current_player
        lines = [
            f"当前玩家：{current.name} / {current.character_name}",
            f"位置：{state.board[current.room_key].name if current.room_key in state.board else '未知'}",
            f"行动：步数 {current.steps_remaining}，攻击 {'已用' if current.attack_used else '未用'}，物品 {'已用' if current.item_used else '未用'}",
            "",
            "属性：",
        ]
        for stat in ("speed", "might", "sanity", "knowledge"):
            lines.append(f"  {stat}: {current.stats[stat]} / {current.stats_max[stat]} (+{current.overflow.get(stat, 0)} overflow)")
        lines.append("")
        lines.append("物品：")
        if current.items:
            for card_id in current.items:
                card = self.engine.catalog.cards[card_id]
                lines.append(f"  - {card.name}")
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

    def _refresh_deck_panel(self) -> None:
        state = self.engine.state
        lines = [
            f"牌堆余量：",
            f"  预兆 {len(state.card_decks.get('omen', []))} / 弃牌 {len(state.card_discards.get('omen', []))}",
            f"  物品 {len(state.card_decks.get('item', []))} / 弃牌 {len(state.card_discards.get('item', []))}",
            f"  事件 {len(state.card_decks.get('event', []))} / 弃牌 {len(state.card_discards.get('event', []))}",
        ]
        if state.haunt:
            lines.extend([
                "",
                f"剧本：#{state.haunt.id} {state.haunt.name}",
                "作祟信息：已发送",
            ])
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
            for button in (self.btn_move, self.btn_use, self.btn_pickup, self.btn_drop, self.btn_trade, self.btn_attack, self.btn_end):
                button.config(state="disabled")
            return
        current = self.engine.current_player
        room_items = self.engine.room_items(current.room_key)
        same_room_players = [
            other
            for other in state.players
            if other.id != current.id and not other.dead and other.room_key == current.room_key
        ]
        weapons = self.engine.available_attack_weapons(current)
        ranged_weapon = any("ranged" in self.engine.catalog.cards[card_id].tags for card_id in weapons)
        has_attack_target = bool(self.engine.available_attack_targets(current) or (ranged_weapon and self.engine.available_attack_targets(current, ranged=True)))
        self.btn_move.config(state="normal" if current.steps_remaining > 0 and not current.movement_stopped and state.phase != "GAME_OVER" else "disabled")
        self.btn_use.config(state="normal" if current.items and state.phase != "GAME_OVER" else "disabled")
        self.btn_pickup.config(state="normal" if room_items and state.phase != "GAME_OVER" else "disabled")
        self.btn_drop.config(state="normal" if current.items and state.phase != "GAME_OVER" else "disabled")
        self.btn_trade.config(state="normal" if current.items and same_room_players and state.phase != "GAME_OVER" else "disabled")
        self.btn_attack.config(state="normal" if state.phase == "HAUNT_PHASE" and not current.attack_used and has_attack_target else "disabled")
        self.btn_end.config(state="normal" if state.phase != "GAME_OVER" else "disabled")

    def _idle_poll(self) -> None:
        if hasattr(self, "board_canvas"):
            self._refresh_ui()
        self.after(300, self._idle_poll)


def run_app() -> None:
    app = GameApp()
    app.mainloop()
