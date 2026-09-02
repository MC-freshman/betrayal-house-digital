"""联机客户端：登录（IP/端口/名字/选角色）→ 连接 → 渲染游戏 + 决策弹窗。

复用 ui.GameApp 的渲染/交互，但操作通过 net 发给主机，本端只读。
"""
from __future__ import annotations

import queue
import socket
import threading
import tkinter as tk
from tkinter import simpledialog

try:
    from game.content import build_catalog
    from game.engine import GameEngine
    from game.models import GameState
    from game.ui import (
        PALETTE,
        FONT_UI_BOLD,
        FONT_PANEL,
        _ChoiceDialog,
        _ConfirmDialog,
        _DiceDialog,
        _InfoDialog,
        _RotationDialog,
        _configure_windows_dpi_awareness,
        GameApp,
    )
    from game.net import protocol as P
    from game.net.serialize import state_from_dict
    from game.net.protocol import BufferedLineReader
except ImportError:  # pragma: no cover - direct script execution
    from content import build_catalog  # type: ignore
    from engine import GameEngine  # type: ignore
    from models import GameState  # type: ignore
    from ui import (  # type: ignore
        PALETTE,
        FONT_UI_BOLD,
        FONT_PANEL,
        _ChoiceDialog,
        _ConfirmDialog,
        _DiceDialog,
        _InfoDialog,
        _RotationDialog,
        _configure_windows_dpi_awareness,
        GameApp,
    )
    from net import protocol as P  # type: ignore
    from net.serialize import state_from_dict  # type: ignore
    from net.protocol import BufferedLineReader  # type: ignore

NET_DISCONNECTED = "__net_disconnected__"


class NetClient:
    """与主机的 socket 连接：发送指令，接收消息放入队列。"""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.inbox: queue.Queue = queue.Queue()
        self.running = False
        self.player_id = -1
        self.is_host = False
        self.session_token = ""

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.sock.settimeout(None)
        self.running = True
        threading.Thread(target=self._recv, daemon=True).start()

    def _recv(self) -> None:
        reader = BufferedLineReader(self.sock)
        while self.running:
            try:
                line = reader.readline()
            except socket.timeout:
                continue
            except OSError:
                break
            if line is None:
                break
            try:
                msg = P.decode(line)
            except Exception:
                continue
            self.inbox.put(msg)
        self.running = False
        self.inbox.put({"kind": NET_DISCONNECTED})

    def send(self, msg: dict) -> None:
        if self.sock:
            try:
                self.sock.sendall(P.encode(msg))
            except OSError:
                pass

    def join(
        self,
        name: str,
        character_id: str,
        is_host: bool,
        password: str = "",
        ready: bool = False,
        reconnect_player_id: int | None = None,
        session_token: str = "",
    ) -> None:
        self.send({
            "kind": P.JOIN,
            "name": name,
            "character_id": character_id,
            "is_host": is_host,
            "password": password,
            "ready": ready,
            "reconnect_player_id": reconnect_player_id,
            "session_token": session_token,
        })

    def send_start(self, fill_to: int, bot_difficulty: str = "normal") -> None:
        self.send({"kind": P.START, "fill_to": fill_to, "bot_difficulty": bot_difficulty})

    def send_save_game(self) -> None:
        self.send({"kind": P.SAVE_GAME})

    def send_load_game(self) -> None:
        self.send({"kind": P.LOAD_GAME})

    def send_lobby_update(self, name: str, character_id: str, is_host: bool, ready: bool) -> None:
        self.send({
            "kind": P.LOBBY_UPDATE,
            "name": name,
            "character_id": character_id,
            "is_host": is_host,
            "ready": ready,
        })

    def send_action(self, action: str, data: dict | None = None) -> None:
        self.send({"kind": P.ACTION, "action": action, "data": data or {}})

    def send_decision(self, req_id: int, value) -> None:
        self.send({"kind": P.DECISION, "req_id": req_id, "value": value})


class RemoteEngine:
    """客户端侧的只读引擎壳：提供渲染所需接口，不执行规则。"""

    def __init__(self) -> None:
        self.catalog = build_catalog()
        self.state = GameState()
        self.prompter = None  # 由 ClientApp 注入 LocalPrompter（本地弹窗选择）

    @property
    def current_player(self):
        if not self.state.players or not self.state.turn_order:
            raise RuntimeError("游戏尚未开始")
        idx = self.state.turn_order[self.state.turn_index % len(self.state.turn_order)]
        return self.state.players[idx]

    def current_room(self, player=None):
        player = player or self.current_player
        return self.state.board.get(player.room_key)

    def room_items(self, room_key: str) -> list:
        return list(self.state.room_items.get(room_key, []))

    def _link_target_key(self, value: str) -> str | None:
        if value in self.state.board:
            return value
        for key, room in self.state.board.items():
            if room.template_id == value:
                return key
        return None

    def _room_effect_desc(self, effect: str) -> str:
        # 复用引擎的纯逻辑（只用参数，不依赖实例状态）
        return GameEngine._room_effect_desc(self, effect)

    def _player_label(self, player) -> str:
        return f"{player.name}（{player.character_name}）"


class LocalPrompter:
    """客户端本地决策器：供渲染层的本地选择使用（如『查看玩家』）。

    注意：联机时的游戏内决策（移动/攻击/抽卡等）由服务器通过 REQUEST 下发，
    不经这里；这里只负责 UI 自带的本地选择框。
    """

    def __init__(self, app: "ClientApp") -> None:
        self.app = app

    def notify(self, title: str, message: str) -> None:
        self.app._show_info(title, message)

    def confirm(self, title: str, message: str) -> bool:
        dlg = _ConfirmDialog(self.app, title, message)
        self.app.wait_window(dlg.top)
        return dlg.result

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        dlg = _ChoiceDialog(self.app, title, message, list(options))
        self.app.wait_window(dlg.top)
        return dlg.result

    def choose_rotation(self, title, message, placements, entry_direction) -> int | None:
        labels = [f"方向 {i + 1}" for i in range(len(placements))]
        dlg = _ChoiceDialog(self.app, title, message, labels)
        self.app.wait_window(dlg.top)
        return dlg.result

    def choose_split_damage(self, title, message, amount, first_label, second_label) -> int | None:
        return simpledialog.askinteger(title, message, parent=self.app, minvalue=0, maxvalue=amount)


class ClientApp(GameApp):
    def __init__(self) -> None:
        _configure_windows_dpi_awareness()
        tk.Tk.__init__(self)
        self.title("山中小屋 - 联机客户端")
        self.geometry("1240x780")
        self.minsize(1024, 680)
        self.configure(bg=PALETTE["bg"])

        self.net: NetClient | None = None
        self.engine = RemoteEngine()
        self.engine.prompter = LocalPrompter(self)  # 本地选择器（查看玩家等）
        self.my_seat_id = -1
        self.my_player_id = -1
        self.my_is_host = False
        self.selected_player_index = 0
        self.current_move_options = []
        self.current_attack_targets = []
        self._last_fp = None
        self.zoom = 1.0
        self._tooltip = None
        self._room_tooltip = None
        self._game_built = False
        self._lobby_started = False
        self._lobby_update_after = None
        self._lobby_sync_after = None
        self._last_lobby_payload: tuple[str, str, bool, bool] | None = None
        self._suppress_lobby_update = False
        self._reconnect_after = None
        self._server_host = "127.0.0.1"
        self._server_port = 8765
        self._server_password = ""
        self._session_token = ""
        self._network_log: list[str] = []
        self._reconnect_attempts = 0
        self._closing = False
        self._net_poll_after = None

        self._show_login()
        self._net_poll_after = self.after(100, self._poll_net)
        self.after(1000, self._periodic_lobby_sync)

    # ------------------------------------------------------------------
    # 登录界面
    # ------------------------------------------------------------------
    def _show_login(self) -> None:
        self.login_page = tk.Frame(self, bg=PALETTE["bg"])
        self.login_page.pack(fill="both", expand=True)
        self.login_frame = tk.Frame(
            self.login_page,
            bg=PALETTE["panel"],
            padx=24,
            pady=16,
            highlightthickness=1,
            highlightbackground=PALETTE["outline"],
        )
        self.login_frame.place(relx=0.5, rely=0.5, anchor="center", width=880)

        tk.Label(self.login_frame, text="山中小屋 · 联机", bg=PALETTE["panel"],
                 fg=PALETTE["accent"], font=("Microsoft YaHei UI", 18, "bold")).pack(pady=(0, 10))

        content = tk.Frame(self.login_frame, bg=PALETTE["panel"])
        content.pack(fill="x")
        content.grid_columnconfigure(0, weight=1, uniform="login")
        content.grid_columnconfigure(1, weight=1, uniform="login")
        left = tk.Frame(content, bg=PALETTE["panel"])
        right = tk.Frame(content, bg=PALETTE["panel"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right.grid(row=0, column=1, sticky="nsew", padx=(14, 0))

        def row(parent, label, make_widget):
            line = tk.Frame(parent, bg=PALETTE["panel"])
            line.pack(fill="x", pady=3)
            line.grid_columnconfigure(1, weight=1)
            tk.Label(line, text=label, width=8, anchor="w", bg=PALETTE["panel"],
                     fg=PALETTE["text"], font=FONT_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10))
            widget = make_widget(line)
            widget.grid(row=0, column=1, sticky="ew")
            return widget

        host_line = tk.Frame(left, bg=PALETTE["panel"])
        host_line.pack(fill="x", pady=3)
        host_line.grid_columnconfigure(1, weight=1)
        tk.Label(host_line, text="主机地址", width=8, anchor="w", bg=PALETTE["panel"],
                 fg=PALETTE["text"], font=FONT_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.entry_ip = tk.Entry(
            host_line,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            width=24,
        )
        self.entry_ip.grid(row=0, column=1, sticky="ew")
        self.entry_ip.insert(0, "127.0.0.1")
        tk.Label(host_line, text="端口", bg=PALETTE["panel"], fg=PALETTE["text"],
                 font=FONT_PANEL).grid(row=0, column=2, sticky="e", padx=(12, 6))
        self.entry_port = tk.Entry(
            host_line,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            width=7,
        )
        self.entry_port.grid(row=0, column=3, sticky="e")
        self.entry_port.insert(0, "8765")

        self.entry_password = row(left, "口令", lambda parent: tk.Entry(
            parent,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            width=24,
            show="*",
        ))

        self.entry_name = row(left, "你的名字", lambda parent: tk.Entry(
            parent,
            bg="#181c22",
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            width=24,
        ))
        self.entry_name.insert(0, "玩家")

        faces = list(self.engine.catalog.characters.values())
        self.char_names = [face.name for face in faces]
        self.char_ids = [face.id for face in faces]
        self.combo_char = tk.StringVar(value=self.char_names[0])
        self.char_menu = row(left, "选择角色", lambda parent: tk.OptionMenu(parent, self.combo_char, *self.char_names))
        self.char_menu.config(bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat",
                              highlightthickness=0, font=FONT_PANEL, cursor="hand2",
                              activebackground=PALETTE["accent"])
        self.char_menu["menu"].config(bg=PALETTE["panel2"], fg=PALETTE["text"],
                                       activebackground=PALETTE["accent"], activeforeground="#111")

        self.var_host = tk.BooleanVar(value=False)
        self.var_ready = tk.BooleanVar(value=False)
        check_line = tk.Frame(left, bg=PALETTE["panel"])
        check_line.pack(fill="x", pady=(6, 2))
        tk.Checkbutton(check_line, text="我是房主（负责开局）", variable=self.var_host,
                       bg=PALETTE["panel"], fg=PALETTE["text"], selectcolor=PALETTE["panel2"],
                       font=FONT_PANEL, activebackground=PALETTE["panel"]).pack(side="left")
        tk.Checkbutton(check_line, text="我已准备", variable=self.var_ready,
                       bg=PALETTE["panel"], fg=PALETTE["text"], selectcolor=PALETTE["panel2"],
                       font=FONT_PANEL, activebackground=PALETTE["panel"]).pack(side="left", padx=(18, 0))

        fill_line = tk.Frame(left, bg=PALETTE["panel"])
        fill_line.pack(fill="x", pady=(2, 2))
        fill_line.grid_columnconfigure(3, weight=1)
        tk.Label(fill_line, text="总人数", width=8, anchor="w", bg=PALETTE["panel"],
                 fg=PALETTE["muted"], font=FONT_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.spin_fill = tk.Spinbox(fill_line, from_=4, to=6, width=4, bg="#181c22", fg=PALETTE["text"],
                                    buttonbackground=PALETTE["panel2"], relief="flat")
        self.spin_fill.delete(0, "end")
        self.spin_fill.insert(0, "4")
        self.spin_fill.grid(row=0, column=1, sticky="w")
        tk.Label(fill_line, text="机器人", width=7, anchor="e", bg=PALETTE["panel"],
                 fg=PALETTE["muted"], font=FONT_PANEL).grid(row=0, column=2, sticky="e", padx=(18, 8))
        self.bot_difficulty_names = {"简单": "easy", "普通": "normal", "困难": "hard"}
        self.combo_bot_difficulty = tk.StringVar(value="普通")
        self.bot_difficulty_menu = tk.OptionMenu(fill_line, self.combo_bot_difficulty, *self.bot_difficulty_names.keys())
        self.bot_difficulty_menu.config(bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat",
                                        highlightthickness=0, font=FONT_PANEL, cursor="hand2",
                                        activebackground=PALETTE["accent"])
        self.bot_difficulty_menu["menu"].config(bg=PALETTE["panel2"], fg=PALETTE["text"],
                                                activebackground=PALETTE["accent"], activeforeground="#111")
        self.bot_difficulty_menu.grid(row=0, column=3, sticky="w")

        self.btn_connect = tk.Button(right, text="连接", command=self._connect,
                                     bg=PALETTE["accent"], fg="#111", relief="flat",
                                     font=FONT_UI_BOLD, padx=30, pady=4, height=1, cursor="hand2")
        self.btn_connect.pack(fill="x", pady=(0, 5))

        self.btn_start = tk.Button(right, text="开始游戏", command=self._start_game,
                                   bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat",
                                   font=FONT_UI_BOLD, padx=30, pady=4, height=1, cursor="hand2",
                                   state="disabled")
        self.btn_start.pack(fill="x", pady=(0, 5))

        self.btn_load_lobby = tk.Button(right, text="读取联机存档", command=self._load_network_save_from_lobby,
                                        bg=PALETTE["panel2"], fg=PALETTE["text"], relief="flat",
                                        font=FONT_UI_BOLD, padx=30, pady=4, height=1, cursor="hand2",
                                        state="disabled")
        self.btn_load_lobby.pack(fill="x", pady=(0, 7))

        self.lobby_label = tk.Label(right, text="未连接", bg=PALETTE["panel"],
                                    fg=PALETTE["muted"], font=FONT_PANEL, justify="left",
                                    anchor="w", wraplength=360)
        self.lobby_label.pack(fill="x", pady=(4, 0))
        self.net_log_text = tk.Text(
            right,
            width=1,
            height=5,
            bg="#11151a",
            fg=PALETTE["muted"],
            insertbackground=PALETTE["text"],
            relief="flat",
            font=FONT_PANEL,
            wrap="word",
        )
        self.net_log_text.pack(fill="x", pady=(8, 0))
        self.net_log_text.config(state="disabled")
        self.entry_name.bind("<KeyRelease>", lambda _e: self._queue_lobby_update())
        self.entry_name.bind("<FocusOut>", lambda _e: self._queue_lobby_update())
        self.combo_char.trace_add("write", lambda *_args: self._queue_lobby_update())
        self.var_host.trace_add("write", lambda *_args: self._queue_lobby_update())
        self.var_ready.trace_add("write", lambda *_args: self._queue_lobby_update())

    def _selected_character_id(self) -> str:
        current = self.combo_char.get()
        if current in self.char_names:
            return self.char_ids[self.char_names.index(current)]
        return self.char_ids[0]

    def _add_network_log(self, message: str) -> None:
        self._network_log.append(message)
        self._network_log = self._network_log[-80:]
        if hasattr(self, "net_log_text") and self.net_log_text.winfo_exists():
            self.net_log_text.config(state="normal")
            self.net_log_text.delete("1.0", "end")
            self.net_log_text.insert("end", "\n".join(self._network_log[-20:]))
            self.net_log_text.config(state="disabled")
            self.net_log_text.see("end")

    def _queue_lobby_update(self) -> None:
        if self._suppress_lobby_update or not self.net or self._lobby_started:
            return
        if self._lobby_update_after is not None:
            try:
                self.after_cancel(self._lobby_update_after)
            except Exception:
                pass
        self._lobby_update_after = self.after_idle(lambda: self._send_lobby_update(force=True))

    def _lobby_payload(self) -> tuple[str, str, bool, bool]:
        return (
            self.entry_name.get().strip() or "玩家",
            self._selected_character_id(),
            bool(self.var_host.get()),
            bool(self.var_ready.get()),
        )

    def _send_lobby_update(self, force: bool = False) -> None:
        self._lobby_update_after = None
        if not self.net or self._lobby_started:
            return
        payload = self._lobby_payload()
        if not force and payload == self._last_lobby_payload:
            return
        self._last_lobby_payload = payload
        self.net.send_lobby_update(*payload)

    def _periodic_lobby_sync(self) -> None:
        if self._closing:
            return
        if self.net and not self._lobby_started and not self._suppress_lobby_update:
            self._send_lobby_update(force=False)
        self._lobby_sync_after = self.after(1000, self._periodic_lobby_sync)

    def _connect(self) -> None:
        host = self.entry_ip.get().strip() or "127.0.0.1"
        try:
            port = int(self.entry_port.get().strip() or 8765)
        except ValueError:
            self._show_error("端口", "端口必须是数字。")
            return
        name = self.entry_name.get().strip() or f"玩家{self.my_player_id + 1}"
        char_id = self._selected_character_id()
        is_host = self.var_host.get()
        password = self.entry_password.get()
        net = NetClient(host, port)
        try:
            net.connect()
        except OSError as exc:
            self._show_error("连接失败", f"无法连接 {host}:{port}\n{exc}")
            return
        self.net = net
        self._server_host = host
        self._server_port = port
        self._server_password = password
        self.btn_connect.config(state="disabled", text="已连接")
        self.lobby_label.config(text="连接中…")
        self._add_network_log(f"正在连接 {host}:{port} ...")
        net.join(name, char_id, is_host, password, bool(self.var_ready.get()))
        self._last_lobby_payload = None

    def _show_toast(self, title: str, message: str) -> None:
        """非阻塞、自动消失的提示（不卡 UI，适合广播类通知）。"""
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg="#1c2027")
        tk.Label(
            tip,
            text=f"{title}：{message}",
            bg="#1c2027",
            fg=PALETTE["text"],
            font=FONT_PANEL,
            justify="left",
            padx=12,
            pady=8,
            bd=1,
            relief="solid",
            highlightbackground=PALETTE["panel2"],
            wraplength=340,
        ).pack()
        self.update_idletasks()
        w = tip.winfo_reqwidth()
        h = tip.winfo_reqheight()
        toasts = getattr(self, "_toasts", [])
        x = self.winfo_rootx() + self.winfo_width() - w - 16
        y = self.winfo_rooty() + 60 + len(toasts) * (h + 8)
        tip.geometry(f"+{x}+{y}")
        toasts.append(tip)
        self._toasts = toasts
        tip.after(4500, lambda: self._dismiss_toast(tip))

    def _dismiss_toast(self, tip) -> None:
        toasts = getattr(self, "_toasts", [])
        if tip in toasts:
            toasts.remove(tip)
            self._toasts = toasts
        try:
            tip.destroy()
        except Exception:
            pass

    def _start_game(self) -> None:
        if not self.net:
            self._show_info("提示", "请先连接主机。")
            return
        if not self.my_is_host:
            self._show_info("提示", "只有房主可以开始游戏。")
            return
        if self._game_built or self.engine.state.phase != "SETUP":
            self._show_info("提示", "游戏已经开始。")
            return
        # 开局前强制把本机最新选择发给主机，避免刚改角色/准备状态就开局时仍用旧值。
        self._send_lobby_update(force=True)
        # 本地先检查角色是否重复，避免“点了没反应”
        seen: dict = {}
        connected = [seat for seat in (getattr(self, "_lobby_seats", []) or []) if seat.get("connected")]
        not_ready = [seat.get("name", "玩家") for seat in connected if not seat.get("ready")]
        if not_ready:
            self._show_error("无法开局", "还有玩家未准备：" + "、".join(not_ready))
            return
        for seat in connected:
            cid = seat.get("character_id")
            if cid:
                if cid in seen:
                    self._show_error("无法开局", f"角色重复：{seen[cid]} 和 {seat.get('name')} 选择了同一角色，请更换。")
                    return
                seen[cid] = seat.get("name")
            else:
                self._show_error("无法开局", f"{seat.get('name', '玩家')} 还没有选择角色。")
                return
        try:
            fill_to = int(self.spin_fill.get())
        except ValueError:
            fill_to = 4
        fill_to = max(4, min(6, fill_to))
        difficulty = self.bot_difficulty_names.get(self.combo_bot_difficulty.get(), "normal")
        self.net.send_start(fill_to, difficulty)

    # ------------------------------------------------------------------
    # 网络消息处理（UI 线程轮询）
    # ------------------------------------------------------------------
    def _poll_net(self) -> None:
        if self._closing:
            return
        net = self.net
        if net:
            while True:
                try:
                    msg = net.inbox.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_msg(msg)
                except Exception as exc:
                    print(f"[客户端] 处理消息异常 ({msg.get('kind')}): {exc!r}")
                    import traceback
                    traceback.print_exc()
        self._net_poll_after = self.after(100, self._poll_net)

    def _handle_msg(self, msg: dict) -> None:
        kind = msg.get("kind")
        if kind == P.WELCOME:
            self.net.player_id = msg.get("player_id", -1)
            self.net.session_token = msg.get("session_token", "")
            self.my_seat_id = self.net.player_id
            self._session_token = self.net.session_token
            self.my_is_host = bool(msg.get("is_host"))
            self._reconnect_attempts = 0
            self._add_network_log("重连成功。" if msg.get("reconnected") else "连接成功。")
            # 已开始的房间：直接进入游戏界面（作为当前局的一员/观战）
            st = msg.get("state")
            if st and st.get("phase") != "SETUP" and not self._game_built:
                viewer_id = (st.get("meta") or {}).get("viewer_id")
                if viewer_id is not None:
                    self.my_player_id = int(viewer_id)
                self.engine.state = state_from_dict(st)
                self._enter_game()
                return
            if not self._game_built:
                self.lobby_label.config(text=f"已连接，你的编号：{self.my_seat_id + 1}")
                if self.my_is_host:
                    self.btn_start.config(state="normal", text="开始游戏")
                    self.btn_load_lobby.config(state="normal")
        elif kind == P.LOBBY:
            self._update_lobby(msg)
        elif kind == P.STATE:
            raw_state = msg.get("state") or {}
            viewer_id = (raw_state.get("meta") or {}).get("viewer_id")
            if viewer_id is not None:
                self.my_player_id = int(viewer_id)
            state = state_from_dict(raw_state)
            self.engine.state = state
            if state.phase != "SETUP" and not self._game_built:
                self._enter_game()
            elif self._game_built:
                self._refresh_ui()
        elif kind == P.REQUEST:
            self._show_request(msg)
        elif kind == P.DICE:
            self._show_dice(msg)
        elif kind == P.NOTIFY:
            self._show_info(msg.get("title", "提示"), msg.get("message", ""))
        elif kind == P.GAME_OVER:
            winner = msg.get("winner")
            reason = msg.get("reason", "")
            self._show_info("游戏结束", f"胜方：{winner}\n{reason}")
        elif kind == P.ERROR:
            self._add_network_log("服务器提示：" + msg.get("message", ""))
            self._show_error("提示", msg.get("message", ""))
        elif kind == P.PONG:
            pass
        elif kind == NET_DISCONNECTED:
            self._handle_disconnect()

    def _handle_disconnect(self) -> None:
        self._add_network_log("连接已断开。")
        if hasattr(self, "btn_connect") and self.btn_connect.winfo_exists() and not self._game_built:
            self.btn_connect.config(state="normal", text="重新连接")
            self.lobby_label.config(text="连接已断开，可重新连接。")
        if self._game_built and self._session_token and self.my_seat_id >= 0:
            self._show_toast("联机", "连接断开，正在尝试重连…")
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._reconnect_after is not None:
            return
        self._reconnect_after = self.after(1200, self._try_reconnect)

    def _try_reconnect(self) -> None:
        self._reconnect_after = None
        if not self._session_token or self.my_seat_id < 0:
            return
        if self.net and self.net.running:
            return
        if self._reconnect_attempts >= 20:
            self._add_network_log("自动重连已暂停，可手动重新连接。")
            return
        self._reconnect_attempts += 1
        net = NetClient(self._server_host, self._server_port)
        try:
            net.connect()
        except OSError as exc:
            self._add_network_log(f"第 {self._reconnect_attempts} 次重连失败：{exc}")
            self._schedule_reconnect()
            return
        old = self.net
        if old is not None and old is not net:
            old.running = False
            try:
                if old.sock is not None:
                    old.sock.close()
            except OSError:
                pass
        self.net = net
        name = self._current_lobby_name()
        char_id = self._current_lobby_character_id()
        ready = bool(self.var_ready.get()) if hasattr(self, "var_ready") else True
        self._add_network_log(f"第 {self._reconnect_attempts} 次重连中…")
        net.join(
            name,
            char_id,
            self.my_is_host,
            self._server_password,
            ready,
            reconnect_player_id=self.my_seat_id,
            session_token=self._session_token,
        )

    def _current_lobby_name(self) -> str:
        if hasattr(self, "entry_name") and self.entry_name.winfo_exists():
            return self.entry_name.get().strip() or "玩家"
        if 0 <= self.my_player_id < len(self.engine.state.players):
            return self.engine.state.players[self.my_player_id].name
        return "玩家"

    def _current_lobby_character_id(self) -> str:
        if hasattr(self, "combo_char") and self.login_frame.winfo_exists():
            return self._selected_character_id()
        if 0 <= self.my_player_id < len(self.engine.state.players):
            return self.engine.state.players[self.my_player_id].character_id
        return self.char_ids[0]

    def _update_lobby(self, msg: dict) -> None:
        seats = msg.get("seats", [])
        started = msg.get("game_started", False)
        self._lobby_started = started
        self._lobby_seats = seats
        my_seat = next((seat for seat in seats if seat.get("player_id") == self.my_seat_id), None)
        if my_seat is not None:
            self.my_is_host = bool(my_seat.get("is_host"))
            self._suppress_lobby_update = True
            try:
                if self.var_host.get() != self.my_is_host:
                    self.var_host.set(self.my_is_host)
                if "ready" in my_seat and self.var_ready.get() != bool(my_seat.get("ready")):
                    self.var_ready.set(bool(my_seat.get("ready")))
            finally:
                self._suppress_lobby_update = False
        # 已被其它玩家占用的角色在选角色下拉里置灰（避免选重复）
        if hasattr(self, "char_menu") and not started:
            occupied = {
                s.get("character_id")
                for s in seats
                if s.get("connected") and s.get("character_id") and s.get("player_id") != self.my_seat_id
            }
            menu = self.char_menu["menu"]
            for i, cid in enumerate(self.char_ids):
                menu.entryconfig(i, state="disabled" if cid in occupied else "normal")
        lines = ["大厅玩家："]
        for seat in seats:
            char_name = ""
            cid = seat.get("character_id")
            if cid in self.engine.catalog.characters:
                char_name = self.engine.catalog.characters[cid].name
            tag = "（房主）" if seat.get("is_host") else ""
            ready = "已准备" if seat.get("ready") else "未准备"
            if not seat.get("connected"):
                ready = "掉线"
            lines.append(f"  {seat.get('name')}{tag} / {char_name} / {ready}")
        connected = [seat for seat in seats if seat.get("connected")]
        all_ready = bool(connected) and all(seat.get("ready") for seat in connected)
        has_missing = any(not seat.get("character_id") for seat in connected)
        seen: dict[str, str] = {}
        duplicate = False
        for seat in connected:
            cid = seat.get("character_id")
            if cid and cid in seen:
                duplicate = True
                break
            if cid:
                seen[cid] = seat.get("name", "")
        if started:
            lines.append("游戏已开始，正在同步…")
            self.btn_start.config(state="disabled", text="游戏已开始")
            self.btn_load_lobby.config(state="disabled")
        else:
            lines.append("（4-6 人，人数不足会自动补机器人）")
            self.btn_load_lobby.config(state="normal" if self.my_is_host and self.net else "disabled")
            if self.my_is_host and all_ready and not has_missing and not duplicate:
                self.btn_start.config(state="normal", text="开始游戏")
            elif self.my_is_host:
                self.btn_start.config(state="disabled", text="等待准备完成")
            else:
                self.btn_start.config(state="disabled", text="等待房主开始")
        self.lobby_label.config(text="\n".join(lines))

    def _enter_game(self) -> None:
        if self._game_built:
            return
        self._game_built = True
        try:
            if hasattr(self, "login_page") and self.login_page.winfo_exists():
                self.login_page.destroy()
            elif self.login_frame.winfo_exists():
                self.login_frame.destroy()
        except Exception:
            pass
        self._build_ui()
        self._build_game_board()
        self._build_legend()
        self._refresh_ui()

    def _current_viewer_id(self) -> int | None:
        return self._effective_player_id()

    def _effective_player_id(self) -> int | None:
        if self.my_player_id >= 0:
            return self.my_player_id
        for seat in getattr(self, "_lobby_seats", []) or []:
            if seat.get("player_id") == self.my_seat_id and seat.get("game_player_id") is not None:
                try:
                    return int(seat["game_player_id"])
                except (TypeError, ValueError):
                    return None
        return None

    def _should_confirm_private_view(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # 决策请求（弹窗 → 发回）
    # ------------------------------------------------------------------
    def _show_request(self, msg: dict) -> None:
        req_id = msg.get("req_id")
        title = msg.get("title", "选择")
        message = msg.get("message", "")
        req_kind = msg.get("req_kind")
        options = msg.get("options", [])
        print(f"[客户端] 收到决策请求: {title} ({req_kind})")
        if req_kind == P.REQ_CONFIRM:
            dlg = _ConfirmDialog(self, title, message)
            self.wait_window(dlg.top)
            self.net.send_decision(req_id, dlg.result)
        elif req_kind == P.REQ_SPLIT:
            value = simpledialog.askinteger(title, message, parent=self, minvalue=0, maxvalue=999)
            self.net.send_decision(req_id, value)
        elif req_kind == P.REQ_ROTATION:
            placements = msg.get("placements") or []
            entry = msg.get("entry_direction")
            if placements:
                # 卡片式旋转选择（画四边门 + 顺时针/逆时针）
                dlg = _RotationDialog(self, title, message, placements, entry)
                self.wait_window(dlg.top)
                self.net.send_decision(req_id, dlg.result)
            else:
                dlg = _ChoiceDialog(self, title, message, list(options))
                self.wait_window(dlg.top)
                self.net.send_decision(req_id, dlg.result)
        else:  # list
            dlg = _ChoiceDialog(self, title, message, list(options))
            self.wait_window(dlg.top)
            self.net.send_decision(req_id, dlg.result)

    def _show_dice(self, msg: dict) -> None:
        """服务器发来的骰子投掷动画（非模态，自动关闭，不阻塞决策弹窗）。"""
        try:
            _DiceDialog(
                self,
                list(msg.get("dice") or []),
                int(msg.get("total") or 0),
                msg.get("label") or "",
                modal=False,
            )
        except Exception as exc:
            print(f"[客户端] 骰子面板异常: {exc!r}")

    # ------------------------------------------------------------------
    # 操作按钮（网络版，覆盖 GameApp）
    # ------------------------------------------------------------------
    def _can_act(self) -> bool:
        state = self.engine.state
        if not self.net or not state.players or state.phase == "GAME_OVER":
            return False
        current = self.engine.current_player
        viewer_id = self._effective_player_id()
        if current.id != viewer_id:
            self._show_info("提示", "还没轮到你的回合。")
            return False
        if current.dead:
            self._show_info("提示", "你已经倒下。")
            return False
        return True

    def _action_move(self) -> None:
        if not self._can_act():
            return
        self.net.send_action("move", {})

    def _action_use_item(self) -> None:
        if not self._can_act():
            return
        player = self.engine.current_player
        if not player.items:
            self._show_info("物品", "你现在没有物品。")
            return
        labels = [self.engine.catalog.cards[c].name for c in player.items]
        dlg = _ChoiceDialog(self, "使用物品", "选择要使用的物品", labels)
        self.wait_window(dlg.top)
        if dlg.result is not None:
            self.net.send_action("use_item", {"card_id": player.items[dlg.result]})

    def _action_pickup(self) -> None:
        if not self._can_act():
            return
        player = self.engine.current_player
        room_items = self.engine.room_items(player.room_key)
        if not room_items:
            self._show_info("拾取", "这个房间里没有可拾取的物品。")
            return
        labels = [self.engine.catalog.cards[c].name for c in room_items]
        dlg = _ChoiceDialog(self, "拾取", "选择要拿起的物品", labels)
        self.wait_window(dlg.top)
        if dlg.result is not None:
            self.net.send_action("pickup", {"card_id": room_items[dlg.result]})

    def _action_drop(self) -> None:
        if not self._can_act():
            return
        player = self.engine.current_player
        if not player.items:
            self._show_info("丢弃", "你现在没有可以丢弃的物品。")
            return
        labels = [self.engine.catalog.cards[c].name for c in player.items]
        dlg = _ChoiceDialog(self, "丢弃", "选择要丢下的物品", labels)
        self.wait_window(dlg.top)
        if dlg.result is not None:
            self.net.send_action("drop", {"card_id": player.items[dlg.result]})

    def _action_trade(self) -> None:
        if not self._can_act():
            return
        player = self.engine.current_player
        others = [
            o for o in self.engine.state.players
            if o.id != player.id and not o.dead and o.room_key == player.room_key
        ]
        if not others or not player.items:
            self._show_info("交易", "同房间没有可交易的对象或你没有物品。")
            return
        labels = [f"{o.name} / {o.character_name}" for o in others]
        dlg = _ChoiceDialog(self, "交易", "选择交易对象", labels)
        self.wait_window(dlg.top)
        if dlg.result is None:
            return
        target = others[dlg.result]
        offer = [c for c in player.items if self.engine.catalog.cards[c].tradeable]
        if not offer:
            self._show_info("交易", "你没有可交易的物品。")
            return
        labels2 = [self.engine.catalog.cards[c].name for c in offer]
        dlg2 = _ChoiceDialog(self, "交易", "选择给出的物品", labels2)
        self.wait_window(dlg2.top)
        if dlg2.result is not None:
            self.net.send_action("trade", {
                "target_id": target.id,
                "card_id": offer[dlg2.result],
            })

    def _action_attack(self) -> None:
        if not self._can_act():
            return
        player = self.engine.current_player
        if self.engine.state.phase != "HAUNT_PHASE":
            self._show_info("攻击", "作祟开始后才能攻击。")
            return
        weapons = [c for c in player.items if "weapon" in self.engine.catalog.cards[c].tags]
        weapon_card_id = None
        ranged_attack = False
        if weapons:
            labels = ["徒手攻击"] + [self.engine.catalog.cards[c].name for c in weapons]
            dlg = _ChoiceDialog(self, "攻击", "选择攻击方式", labels)
            self.wait_window(dlg.top)
            if dlg.result is None:
                return
            if dlg.result > 0:
                weapon_card_id = weapons[dlg.result - 1]
                ranged_attack = "ranged" in self.engine.catalog.cards[weapon_card_id].tags
        self.net.send_action("attack", {"weapon_card_id": weapon_card_id, "ranged": ranged_attack})

    def _action_haunt_action(self) -> None:
        if not self._can_act():
            return
        self.net.send_action("haunt_action", {})

    def _action_save_game(self) -> None:
        if not self.net:
            self._show_info("保存", "请先连接主机。")
            return
        if not self.my_is_host:
            self._show_info("保存", "只有房主可以保存联机局。")
            return
        self.net.send_save_game()

    def _action_load_game(self) -> None:
        self._send_load_game_request()

    def _load_network_save_from_lobby(self) -> None:
        self._send_load_game_request()

    def _send_load_game_request(self) -> None:
        if not self.net:
            self._show_info("读取", "请先连接主机。")
            return
        if not self.my_is_host:
            self._show_info("读取", "只有房主可以读取联机局。")
            return
        if not self._lobby_started:
            self._send_lobby_update(force=True)
        dlg = _ConfirmDialog(self, "读取联机存档", "读取主机电脑上的联机存档会覆盖当前局，确定继续吗？")
        self.wait_window(dlg.top)
        if dlg.result:
            self.net.send_load_game()

    def _action_end_turn(self) -> None:
        if not self._can_act():
            return
        self.net.send_action("end_turn", {})

    # ------------------------------------------------------------------
    # 按钮状态（网络版，覆盖 GameApp：只有轮到自己且未死才可操作）
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
        for name, fn in steps:
            try:
                fn()
            except Exception as exc:
                print(f"[客户端] 刷新[{name}] 异常: {exc!r}")
                import traceback
                traceback.print_exc()

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
        who = current.name
        viewer_id = self._effective_player_id()
        if current.id == viewer_id:
            who = f"{current.name}（你）"
        elif current.control == "bot":
            who = f"{current.name}（机器人）"
        self.status_label.config(
            text=f"阶段：{phase_label}   回合：{state.turn_count}   轮到：{who}   预兆：{state.omens_drawn}   剧本：{state.haunt.name if state.haunt else '未揭示'}"
        )

    def _refresh_buttons(self) -> None:
        state = self.engine.state
        if not hasattr(self, "btn_move"):
            return
        if not state.players:
            for button in (self.btn_move, self.btn_use, self.btn_pickup, self.btn_drop,
                           self.btn_trade, self.btn_attack, self.btn_haunt_action,
                           self.btn_script, self.btn_end):
                self._set_action_button(button, False, "等待房主开始游戏或读取联机存档。")
            self.btn_save.config(state="disabled")
            self.btn_load.config(state="normal" if self.net and self.my_is_host else "disabled")
            self._refresh_action_hint()
            return
        current = self.engine.current_player
        viewer_id = self._effective_player_id()
        is_me = current.id == viewer_id and not current.dead
        is_over = state.phase == "GAME_OVER"
        room_items = self.engine.room_items(current.room_key)
        same_room_players = [
            other for other in state.players
            if other.id != current.id and not other.dead and other.room_key == current.room_key
        ]
        base_reason = (
            "游戏已经结束。"
            if is_over
            else "还没轮到你。"
            if current.id != viewer_id
            else "你已经倒下。"
            if current.dead
            else ""
        )
        self._set_action_button(
            self.btn_move,
            is_me and current.steps_remaining > 0 and not current.movement_stopped and not is_over,
            base_reason or ("移动点数已用完。" if current.steps_remaining <= 0 else "当前移动被房间或效果终止。"),
        )
        self._set_action_button(
            self.btn_use,
            is_me and bool(current.items) and not is_over,
            base_reason or "你现在没有物品。",
        )
        self._set_action_button(
            self.btn_pickup,
            is_me and bool(room_items) and not is_over,
            base_reason or "当前房间没有可拾取物品。",
        )
        self._set_action_button(
            self.btn_drop,
            is_me and bool(current.items) and not is_over,
            base_reason or "你现在没有可丢弃物品。",
        )
        self._set_action_button(
            self.btn_trade,
            is_me and bool(current.items) and bool(same_room_players) and not is_over,
            base_reason or ("你没有可交易物品。" if not current.items else "同房间没有其他玩家。"),
        )
        self._set_action_button(
            self.btn_attack,
            is_me and state.phase == "HAUNT_PHASE" and not current.attack_used and not is_over,
            base_reason or (
                "作祟开始后才能攻击。"
                if state.phase != "HAUNT_PHASE"
                else "本回合已经攻击过。"
                if current.attack_used
                else "点击后由主机确认可攻击目标。"
            ),
        )
        # 规则数据不会通过公共状态下发给客户端，因此不能按剧本编号硬编码。
        # 作祟阶段统一显示入口，由主机根据当前玩家和隐藏规则返回可用行动。
        has_haunt_action = bool(state.phase == "HAUNT_PHASE" and state.haunt)
        self._set_action_button(
            self.btn_haunt_action,
            is_me and has_haunt_action and not is_over,
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
            is_me and not is_over,
            base_reason or "当前不能结束回合。",
        )
        can_admin = bool(self.net and self.my_is_host)
        self.btn_save.config(state="normal" if can_admin and not is_over else "disabled")
        self.btn_load.config(state="normal" if can_admin else "disabled")
        self._refresh_action_hint()
        # 诊断：轮到自己却禁用时打印原因（帮助定位“点了没反应”）
        if current.id == viewer_id and self.btn_move["state"] == "disabled":
            print(f"[客户端][诊断] 轮到我({current.name})但移动禁用: "
                  f"dead={current.dead} steps={current.steps_remaining} "
                  f"stopped={current.movement_stopped} over={is_over}")

    def destroy(self) -> None:
        self._closing = True
        for attr in ("_net_poll_after", "_lobby_sync_after", "_lobby_update_after", "_reconnect_after"):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
                setattr(self, attr, None)
        if self.net:
            self.net.running = False
            sock = getattr(self.net, "sock", None)
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        super().destroy()


def run_client() -> None:
    app = ClientApp()
    app.mainloop()


if __name__ == "__main__":
    run_client()
