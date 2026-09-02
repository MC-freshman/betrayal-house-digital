"""游戏主机：headless 权威服务器。

- 监听 socket，管理玩家座位（人类 / AI）；
- 房主发 START 后创建 GameEngine 开局（人数不足自动补 AI）；
- 回合驱动：轮到 bot 用 BotController 自动跑；轮到远端人类则等其指令；
- 引擎 prompter = DecisionRouter，把决策请求发给对应客户端并阻塞等回复；
- 每次状态变化广播全量 GameState。
"""
from __future__ import annotations

import queue
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

try:
    from ..bot_ai import BotController
    from ..engine import ActionCommand, GameEngine
    from ..models import Player
    from . import protocol as P
    from .serialize import state_to_view_dict
except ImportError:  # pragma: no cover - direct script execution
    from bot_ai import BotController  # type: ignore
    from engine import ActionCommand, GameEngine  # type: ignore
    from models import Player  # type: ignore
    from net import protocol as P  # type: ignore
    from net.serialize import state_to_view_dict  # type: ignore

from .protocol import BufferedLineReader  # noqa: E402


class DecisionRouter:
    """实现引擎 DecisionProvider：把决策请求路由给正在操作的远端玩家。"""

    def __init__(self, host: "GameHost") -> None:
        self.host = host

    def _active_player(self) -> Player:
        engine = self.host.engine
        pid = engine._active_player_id
        if pid is None or pid >= len(engine.state.players):
            pid = engine.current_player.id
        return engine.state.players[pid]

    def notify(self, title: str, message: str) -> None:
        player = self._active_player()
        self.host.notify_player(player.id, title, message)

    def confirm(self, title: str, message: str) -> bool:
        player = self._active_player()
        value = self.host.request_decision(player, P.REQ_CONFIRM, title, message, None)
        return bool(value)

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        player = self._active_player()
        return self.host.request_decision(player, P.REQ_LIST, title, message, options)

    def choose_rotation(
        self,
        title: str,
        message: str,
        placements: list[dict],
        entry_direction: str,
    ) -> int | None:
        player = self._active_player()
        # 把放置方案（门/链接）发给客户端，客户端用卡片可视化旋转选择
        data = [
            {
                "rotation": p.get("rotation", 0),
                "doors": list(p.get("doors", ())),
                "links": dict(p.get("links", {})),
                "entry_door": p.get("entry_door", ""),
            }
            for p in placements
        ]
        return self.host.request_decision(
            player,
            P.REQ_ROTATION,
            title,
            message,
            None,
            extra={"placements": data, "entry_direction": entry_direction},
        )

    def choose_split_damage(
        self,
        title: str,
        message: str,
        amount: int,
        first_label: str,
        second_label: str,
    ) -> int | None:
        player = self._active_player()
        full = f"{message}（0~{amount}，分配给{first_label}的点数）"
        value = self.host.request_decision(player, P.REQ_SPLIT, title, full, None)
        if value is None:
            return amount
        return max(0, min(amount, int(value)))

    def show_dice_roll(self, dice: list[int], total: int, label: str) -> None:
        player = self._active_player()
        self.host.send_to_game_player(player.id, P.DICE, {
            "dice": list(dice),
            "total": int(total),
            "label": str(label or ""),
        })


class GameHost:
    def __init__(self, port: int = 8765, password: str = "", save_path: str | Path | None = None) -> None:
        self.port = port
        self.password = password
        self.save_path = Path(save_path) if save_path is not None else None
        self.engine: GameEngine | None = None
        self.server_sock: socket.socket | None = None
        self.running = True

        self._next_player_id = 0
        self.seats: dict[int, dict] = {}      # player_id -> {name, character_id, control, conn, is_host}
        self.host_id: int | None = None
        self.lock = threading.Lock()

        self.command_queue: queue.Queue = queue.Queue()          # (pid|"admin", msg)
        self.decision_queues: dict[int, queue.Queue] = {}        # player_id -> Queue(value)
        self._pending_req: dict[int, int] = {}                   # player_id -> 当前等待的 req_id
        self._req_seq = 0
        # 决策超时（秒）：客户端长时间不回复时自动取消，避免服务器卡死
        self.decision_timeout = 45.0
        self._send_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 启动 / 网络
    # ------------------------------------------------------------------
    def start(self) -> None:
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("0.0.0.0", self.port))
        self.server_sock.listen(8)
        self.server_sock.settimeout(1.0)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while self.running:
            try:
                conn, addr = self.server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        reader = BufferedLineReader(conn)
        try:
            line = reader.readline()
            if not line:
                conn.close()
                return
            msg = P.decode(line)
            if msg.get("kind") != P.JOIN:
                conn.close()
                return
            joined = self._register_or_reconnect(conn, msg)
            if joined is None:
                return
            pid, welcome = joined
            # 发送大厅状态
            self._send(conn, P.WELCOME, welcome)
            self._broadcast_lobby()
            # 读取循环
            while self.running:
                line = reader.readline()
                if line is None:
                    break
                msg = P.decode(line)
                kind = msg.get("kind")
                if kind == P.ACTION:
                    self.command_queue.put((pid, msg))
                elif kind == P.LOBBY_UPDATE:
                    self._update_lobby_seat(pid, msg)
                elif kind == P.DECISION:
                    # 只接受当前正在等待的 req_id 的回复（避免超时后的迟到回复被误用）
                    game_player_id = self._game_player_id_for_seat(pid)
                    if game_player_id is not None and msg.get("req_id") == self._pending_req.get(game_player_id):
                        q = self.decision_queues.get(game_player_id)
                        if q is not None:
                            q.put(msg.get("value"))
                elif kind == P.START:
                    self.command_queue.put((pid, msg))
                elif kind in {P.SAVE_GAME, P.LOAD_GAME}:
                    self.command_queue.put((pid, msg))
                elif kind == P.PING:
                    self._send(conn, P.PONG, {})
        finally:
            self._drop_client(conn)

    def _register_or_reconnect(self, conn: socket.socket, msg: dict) -> tuple[int, dict] | None:
        if self.password and str(msg.get("password", "")) != self.password:
            self._send(conn, P.ERROR, {"message": "房间口令错误。"})
            try:
                conn.close()
            except OSError:
                pass
            return None

        old_conn: socket.socket | None = None
        result: tuple[int, dict] | None = None
        with self.lock:
            reconnect_id = self._coerce_int(msg.get("reconnect_player_id"))
            token = str(msg.get("session_token") or "")
            if reconnect_id is not None and token:
                seat = self.seats.get(reconnect_id)
                if seat and seat.get("session_token") == token and seat.get("control") == "human":
                    old_conn = seat.get("conn")
                    seat["conn"] = conn
                    seat["connected"] = True
                    seat.pop("disconnect_grace_until", None)
                    if self.engine is None:
                        self._apply_lobby_values_locked(reconnect_id, seat, msg)
                    game_player_id = seat.get("game_player_id")
                    state = state_to_view_dict(self.engine.state, game_player_id) if self.engine else None
                    welcome = {
                        "player_id": reconnect_id,
                        "session_token": seat["session_token"],
                        "is_host": bool(seat.get("is_host")),
                        "state": state,
                        "reconnected": True,
                    }
                    self._log_network_locked(f"{seat['name']} 已重连。")
                    pid = reconnect_id
                    result = (pid, welcome)
                else:
                    self._send(conn, P.ERROR, {"message": "重连身份已失效，请重新加入房间。"})
                    try:
                        conn.close()
                    except OSError:
                        pass
                    return None
            else:
                if self.engine is not None:
                    self._send(conn, P.ERROR, {"message": "游戏已经开始，暂不支持中途加入；原玩家请用重连回到座位。"})
                    try:
                        conn.close()
                    except OSError:
                        pass
                    return None
                pid = self._next_player_id
                self._next_player_id += 1
                wants_host = bool(msg.get("is_host")) or self.host_id is None
                self.seats[pid] = {
                    "name": self._clean_name(msg.get("name"), pid),
                    "character_id": str(msg.get("character_id", "")),
                    "control": "human",
                    "conn": conn,
                    "connected": True,
                    "ready": bool(msg.get("ready", False)),
                    "is_host": wants_host,
                    "game_player_id": None,
                    "session_token": secrets.token_urlsafe(18),
                }
                if wants_host:
                    self._set_host_locked(pid)
                self._log_network_locked(f"{self.seats[pid]['name']} 加入大厅。")
                welcome = {
                    "player_id": pid,
                    "session_token": self.seats[pid]["session_token"],
                    "is_host": bool(self.seats[pid]["is_host"]),
                    "state": None,
                    "reconnected": False,
                }
                result = (pid, welcome)

        if old_conn and old_conn is not conn:
            try:
                old_conn.close()
            except OSError:
                pass
        return result

    def _coerce_int(self, value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _clean_name(self, value, fallback_id: int) -> str:
        name = str(value or "").strip()
        return (name or f"玩家{fallback_id + 1}")[:12]

    def _set_host_locked(self, pid: int | None) -> None:
        self.host_id = pid
        for other_pid, seat in self.seats.items():
            seat["is_host"] = other_pid == pid

    def _apply_lobby_values_locked(self, pid: int, seat: dict, msg: dict) -> None:
        name = str(msg.get("name", seat["name"])).strip()
        if name:
            seat["name"] = name[:12]
        character_id = str(msg.get("character_id", seat.get("character_id", "")))
        if character_id:
            seat["character_id"] = character_id
        if "ready" in msg:
            seat["ready"] = bool(msg.get("ready"))
        wants_host = bool(msg.get("is_host"))
        if wants_host:
            self._set_host_locked(pid)
        elif self.host_id == pid and not wants_host:
            seat["is_host"] = False
            self.host_id = self._first_connected_human_locked()
            if self.host_id is not None:
                self._set_host_locked(self.host_id)

    def _first_connected_human_locked(self) -> int | None:
        for pid, seat in sorted(self.seats.items()):
            if seat.get("control") == "human" and seat.get("connected"):
                return pid
        return None

    def _log_network_locked(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        print(f"[主机][{stamp}] {message}")

    def _update_lobby_seat(self, pid: int, msg: dict) -> None:
        with self.lock:
            if self.engine is not None or pid not in self.seats:
                return
            seat = self.seats[pid]
            self._apply_lobby_values_locked(pid, seat, msg)
        self._broadcast_lobby()

    def _drop_client(self, conn: socket.socket) -> None:
        should_broadcast_state = False
        with self.lock:
            dropped = [pid for pid, s in self.seats.items() if s.get("conn") is conn]
            for pid in dropped:
                seat = self.seats.get(pid)
                if not seat:
                    continue
                game_player_id = seat.get("game_player_id") if seat else None
                q = self.decision_queues.get(game_player_id)
                if q is not None:
                    q.put(None)
                if self.engine:
                    seat["conn"] = None
                    seat["connected"] = False
                    seat["disconnect_grace_until"] = time.time() + 60
                    should_broadcast_state = True
                    if game_player_id is not None and 0 <= game_player_id < len(self.engine.state.players):
                        player = self.engine.state.players[game_player_id]
                        self.engine._log(f"{player.name} 掉线，60 秒内可重连；超时将自动跳过当前回合。")
                else:
                    self.seats.pop(pid, None)
                if self.host_id == pid:
                    new_host = self._first_connected_human_locked()
                    self._set_host_locked(new_host)
        if self.engine and should_broadcast_state:
            self.broadcast_state()
        self._broadcast_lobby()

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    def _send(self, conn: socket.socket, kind: str, payload: dict) -> None:
        try:
            with self._send_lock:
                conn.sendall(P.encode({"kind": kind, **payload}))
        except OSError:
            pass

    def broadcast(self, kind: str, payload: dict) -> None:
        with self.lock:
            conns = [s["conn"] for s in self.seats.values() if s.get("conn") is not None]
        for conn in conns:
            self._send(conn, kind, payload)

    def broadcast_state(self) -> None:
        if not self.engine:
            return
        with self.lock:
            targets = [(pid, s["conn"]) for pid, s in self.seats.items() if s.get("conn") is not None]
        for pid, conn in targets:
            data = state_to_view_dict(self.engine.state, self._game_player_id_for_seat(pid))
            self._send(conn, P.STATE, {"state": data})

    def broadcast_notify(self, title: str, message: str) -> None:
        self.broadcast(P.NOTIFY, {"title": title, "message": message})

    def notify_player(self, player_id: int, title: str, message: str) -> None:
        conn = self._conn_for_game_player(player_id)
        if conn:
            self._send(conn, P.NOTIFY, {"title": title, "message": message})

    def send_to_game_player(self, player_id: int, kind: str, payload: dict) -> None:
        conn = self._conn_for_game_player(player_id)
        if conn:
            self._send(conn, kind, payload)

    def _broadcast_lobby(self) -> None:
        with self.lock:
            seats = [
                {
                    "player_id": pid,
                    "name": s["name"],
                    "character_id": s["character_id"],
                    "is_host": s["is_host"],
                    "ready": bool(s.get("ready")),
                    "connected": bool(s.get("connected")),
                    "game_player_id": s.get("game_player_id"),
                }
                for pid, s in self.seats.items()
            ]
            game_started = self.engine is not None
        self.broadcast(P.LOBBY, {"seats": seats, "game_started": game_started})

    def _game_player_id_for_seat(self, seat_id: int) -> int | None:
        with self.lock:
            seat = self.seats.get(seat_id)
            if not seat:
                return None
            value = seat.get("game_player_id")
        return int(value) if value is not None else None

    def _seat_for_game_player(self, player_id: int) -> dict | None:
        with self.lock:
            for seat in self.seats.values():
                if seat.get("game_player_id") == player_id:
                    return seat
        return None

    def _conn_for_game_player(self, player_id: int) -> socket.socket | None:
        seat = self._seat_for_game_player(player_id)
        if not seat or not seat.get("connected"):
            return None
        return seat.get("conn")

    # ------------------------------------------------------------------
    # 决策请求（阻塞主线程，等待客户端回复）
    # ------------------------------------------------------------------
    def request_decision(self, player: Player, req_kind: str, title: str, message: str, options, extra: dict | None = None) -> int | bool | None:
        if player.control != "human":
            return None
        conn = self._conn_for_game_player(player.id)
        if conn is None:
            return None
        self._req_seq += 1
        req_id = self._req_seq
        self._pending_req[player.id] = req_id
        q = self.decision_queues.setdefault(player.id, queue.Queue())
        self._send(conn, P.REQUEST, {
            "req_id": req_id,
            "title": title,
            "message": message,
            "req_kind": req_kind,
            "options": list(options) if options else [],
            **(extra or {}),
        })
        # 阻塞等该玩家回复（reader 线程放入）；超时自动取消
        try:
            value = q.get(timeout=self.decision_timeout)
        except queue.Empty:
            value = None
            self.engine._log(f"{player.name} 长时间未作出选择，本次操作已自动取消。")
        finally:
            if self._pending_req.get(player.id) == req_id:
                self._pending_req.pop(player.id, None)
        return value

    # ------------------------------------------------------------------
    # 开房
    # ------------------------------------------------------------------
    def _start_game(self, fill_to: int, bot_difficulty: str = "normal") -> str | None:
        with self.lock:
            human_entries = [
                (pid, s)
                for pid, s in sorted(self.seats.items())
                if s["control"] == "human" and s.get("connected")
            ]
            human_seats = [s for _, s in human_entries]
        if not human_seats:
            return "还没有玩家加入"
        not_ready = [s["name"] for s in human_seats if not s.get("ready")]
        if not_ready:
            return f"还有玩家未准备：{', '.join(not_ready)}"
        used = {s["character_id"] for s in human_seats if s["character_id"]}
        # 明确提示是重复还是没选
        names_by_char: dict[str, list[str]] = {}
        for s in human_seats:
            cid = s.get("character_id")
            if cid:
                names_by_char.setdefault(cid, []).append(s["name"])
        dup = next((v for v in names_by_char.values() if len(v) > 1), None)
        if dup:
            return f"角色重复：{' 和 '.join(dup)} 选择了同一角色，请更换"
        missing = [s["name"] for s in human_seats if not s.get("character_id")]
        if missing:
            return f"玩家 {', '.join(missing)} 还没有选择角色"
        engine = GameEngine()  # 用默认 seed；可后续传
        catalog = engine.catalog
        configs = [
            {"name": s["name"], "character_id": s["character_id"], "control": "human"}
            for s in human_seats
        ]
        bot_difficulty = bot_difficulty if bot_difficulty in {"easy", "normal", "hard"} else "normal"
        style_by_difficulty = {
            "easy": "cautious",
            "normal": "balanced",
            "hard": "aggressive",
        }
        # 补 AI 到 fill_to 人
        available = [
            face.id for face in catalog.characters.values() if face.id not in used
        ]
        fill_to = max(4, min(6, int(fill_to or 4)))
        if len(configs) > fill_to:
            return f"当前已有 {len(configs)} 名玩家，总人数不能小于玩家数"
        while len(configs) < fill_to and available:
            cid = available.pop(0)
            used.add(cid)
            configs.append({
                "name": f"机器人{len(configs) + 1}",
                "character_id": cid,
                "control": "bot",
                "bot_difficulty": bot_difficulty,
                "bot_style": style_by_difficulty[bot_difficulty],
            })
        try:
            engine.start_new_game(configs)
        except ValueError as exc:
            return str(exc)
        engine.prompter = DecisionRouter(self)
        self.engine = engine
        with self.lock:
            for game_player_id, (seat_id, _seat) in enumerate(human_entries):
                if seat_id in self.seats:
                    self.seats[seat_id]["game_player_id"] = game_player_id
        self._log_join_info(human_seats)
        return None

    def _log_join_info(self, human_seats: list[dict]) -> None:
        self.engine._log(
            "联机开局："
            + "、".join(
                f"{s['name']}({'房主' if s['is_host'] else '玩家'})" for s in human_seats
            )
        )

    # ------------------------------------------------------------------
    # 主循环：开房等待 → 回合驱动
    # ------------------------------------------------------------------
    def run_loop(self) -> None:
        print(f"[主机] 服务器已启动，端口 {self.port}，等待玩家加入…")
        # 阶段1：等待房主开始
        while self.running and self.engine is None:
            try:
                pid, msg = self.command_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if self._handle_save_load_command(pid, msg):
                continue
            if msg.get("kind") == P.START:
                if pid != self.host_id:
                    self._send_to_seat(pid, P.ERROR, {"message": "只有房主可以开始游戏。"})
                    continue
                fill_to = int(msg.get("fill_to") or 0)
                bot_difficulty = str(msg.get("bot_difficulty") or "normal")
                err = self._start_game(fill_to, bot_difficulty)
                if err:
                    self._send_to_seat(pid, P.ERROR, {"message": err})
                    continue
                self.broadcast_state()
        if not self.running:
            return
        print("[主机] 游戏开始。")

        # 阶段2：回合驱动
        while self.running:
            if self.engine.state.phase == "GAME_OVER":
                self.broadcast(P.GAME_OVER, {
                    "winner": self.engine.state.winner,
                    "reason": self.engine.state.winner_reason,
                })
                self.broadcast_state()
                break
            player = self.engine.current_player
            if player.control == "bot":
                try:
                    BotController().take_turn(self.engine)
                except Exception as exc:  # AI 出错的兜底
                    print("[主机] AI 异常：", exc)
                    self.engine._log(f"机器人 {player.name} 行动异常，跳过。")
                    self.engine.end_turn()
                self.broadcast_state()
                continue
            seat = self._seat_for_game_player(player.id)
            if not seat or not seat.get("connected"):
                grace_until = float(seat.get("disconnect_grace_until", 0)) if seat else 0
                if time.time() >= grace_until:
                    self.engine._log(f"{player.name} 未重连，自动结束本回合。")
                    self.engine.end_turn()
                    self.broadcast_state()
                continue
            # 人类玩家回合：等待该玩家指令
            try:
                pid, msg = self.command_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if self._handle_save_load_command(pid, msg):
                continue
            if msg.get("kind") != P.ACTION:
                continue
            mapped_player_id = self._game_player_id_for_seat(pid)
            if mapped_player_id is None:
                self._send_to_seat(pid, P.ERROR, {"message": "你还没有绑定到本局玩家，请重新连接客户端。"})
                continue
            if mapped_player_id != player.id:
                mapped_name = self.engine.state.players[mapped_player_id].name if 0 <= mapped_player_id < len(self.engine.state.players) else "未知玩家"
                self._send_to_seat(pid, P.ERROR, {
                    "message": f"还没轮到你的回合。当前轮到：{player.name}；你是：{mapped_name}。"
                })
                continue
            self._execute_client_action(player, msg)
            self.broadcast_state()

    def _execute_client_action(self, player: Player, msg: dict) -> None:
        action = msg.get("action")
        data = msg.get("data") or {}
        try:
            if action == "move":
                # 移动目标由服务器算好再请求客户端选择
                options = self.engine.available_move_options(player)
                if not options:
                    self.engine._log(f"{player.name} 没有可走的路线。")
                    return
                labels = [o.label for o in options]
                idx = self.request_decision(player, P.REQ_LIST, "移动", "选择一个移动目标", labels)
                if idx is None or not (0 <= idx < len(options)):
                    return
                self.engine.execute_command(
                    ActionCommand("move", player.id, {"option": options[idx]})
                )
            elif action == "use_item":
                self.engine.execute_command(
                    ActionCommand("use_item", player.id, {"card_id": data.get("card_id")})
                )
            elif action == "pickup":
                self.engine.execute_command(
                    ActionCommand("pickup", player.id, {"card_id": data.get("card_id")})
                )
            elif action == "drop":
                self.engine.execute_command(
                    ActionCommand("drop", player.id, {"card_id": data.get("card_id")})
                )
            elif action == "trade":
                self.engine.execute_command(
                    ActionCommand("trade", player.id, {
                        "target_id": int(data.get("target_id", 0)),
                        "card_id": data.get("card_id"),
                        "target_card_id": data.get("target_card_id"),
                    })
                )
            elif action == "attack":
                # 攻击目标由服务器算好再请求客户端选择
                weapon_id = data.get("weapon_card_id")
                weapon = self.engine.catalog.cards.get(weapon_id) if weapon_id in player.items else None
                ranged = bool(weapon and "ranged" in weapon.tags)
                targets = self.engine.available_attack_targets(player, ranged=ranged)
                if not targets:
                    self.engine._log(f"{player.name} 没有可攻击的目标。")
                    return
                labels = [self._target_label(t) for t in targets]
                idx = self.request_decision(player, P.REQ_LIST, "攻击", "选择攻击目标", labels)
                if idx is None or not (0 <= idx < len(targets)):
                    return
                self.engine.execute_command(
                    ActionCommand("attack", player.id, {
                        "target": targets[idx],
                        "weapon_card_id": weapon_id,
                        "ranged": ranged,
                    })
                )
            elif action == "haunt_action":
                actions = self.engine.available_haunt_actions(player)
                if not actions:
                    self.engine._log(f"{player.name} 没有可执行的剧本行动。")
                    return
                labels = [f"{a.label}：{a.detail}" if a.detail else a.label for a in actions]
                idx = self.request_decision(player, P.REQ_LIST, "剧本行动", "选择要执行的剧本行动", labels)
                if idx is None or not (0 <= idx < len(actions)):
                    return
                action_choice = actions[idx]
                self.engine.execute_command(
                    ActionCommand("haunt_action", player.id, {
                        "action_id": action_choice.id,
                        "data": action_choice.data,
                    })
                )
            elif action == "end_turn":
                self.engine.execute_command(ActionCommand("end_turn", player.id))
        except Exception as exc:  # 客户端指令异常兜底，不拖垮服务器
            print("[主机] 指令异常：", exc)
            self.engine._log(f"{player.name} 的指令执行失败。")

    def _target_label(self, target) -> str:
        if isinstance(target, Player):
            return f"{target.name} / {target.character_name}"
        if getattr(target, "stunned_turns", 0) > 0:
            return f"{getattr(target, 'name', target)}（昏迷{target.stunned_turns}）"
        return getattr(target, "name", str(target))

    def _resolve_target(self, player: Player, data: dict):
        """把远程 target（player_id / monster_id）解析为对象。"""
        if "player_id" in data and data.get("player_id") is not None:
            tid = int(data["player_id"])
            if 0 <= tid < len(self.engine.state.players):
                return self.engine.state.players[tid]
        if "monster_id" in data and data.get("monster_id") is not None:
            mid = str(data["monster_id"])
            for m in self.engine.state.monsters:
                if m.id == mid:
                    return m
        return None

    def _send_to_host(self, kind: str, payload: dict) -> None:
        with self.lock:
            conn = self.seats.get(self.host_id, {}).get("conn") if self.host_id is not None else None
        if conn:
            self._send(conn, kind, payload)

    def _send_to_seat(self, seat_id: int, kind: str, payload: dict) -> None:
        with self.lock:
            seat = self.seats.get(seat_id)
            conn = seat.get("conn") if seat else None
        if conn:
            self._send(conn, kind, payload)

    # ------------------------------------------------------------------
    # 存档 / 读档
    # ------------------------------------------------------------------
    def _default_save_path(self) -> Path:
        if self.save_path is not None:
            return self.save_path
        if getattr(sys, "frozen", False):
            base = Path(sys.argv[0]).resolve().parent
        else:
            base = Path(__file__).resolve().parents[1]
        return base / "saves" / "network_save.json"

    def _handle_save_load_command(self, pid: int, msg: dict) -> bool:
        kind = msg.get("kind")
        if kind not in {P.SAVE_GAME, P.LOAD_GAME}:
            return False
        if pid != self.host_id:
            self._send_to_seat(pid, P.ERROR, {"message": "只有房主可以保存或读取联机局。"})
            return True
        if kind == P.SAVE_GAME:
            error = self._save_network_game()
            if error:
                self._send_to_seat(pid, P.ERROR, {"message": error})
            return True
        error = self._load_network_game()
        if error:
            self._send_to_seat(pid, P.ERROR, {"message": error})
        return True

    def _save_network_game(self) -> str | None:
        if self.engine is None or not self.engine.state.players:
            return "游戏尚未开始，暂时没有可保存的联机局。"
        try:
            path = self.engine.save_to_file(self._default_save_path())
        except Exception as exc:
            return f"保存失败：{exc}"
        self._log_network_locked(f"房主保存存档：{path}")
        self.broadcast_notify("保存成功", f"联机局已保存到主机电脑：\n{path}")
        return None

    def _load_network_game(self) -> str | None:
        path = self._default_save_path()
        if not path.exists():
            return f"未找到联机存档：{path}"
        engine = GameEngine()
        try:
            engine.load_from_file(path)
        except Exception as exc:
            return f"读取失败：{exc}"
        engine.prompter = DecisionRouter(self)
        bind_error = self._bind_loaded_game_to_seats(engine)
        if bind_error:
            return bind_error
        self.engine = engine
        self._pending_req.clear()
        self._log_network_locked(f"房主读取存档：{path}")
        self._broadcast_lobby()
        self.broadcast_state()
        self.broadcast_notify("读取成功", "房主已读取联机存档，棋盘状态已同步。")
        return None

    def _bind_loaded_game_to_seats(self, engine: GameEngine) -> str | None:
        saved_humans = [p for p in engine.state.players if p.control == "human"]
        if not saved_humans:
            return "这个存档里没有人类玩家，不能作为联机局读取。"
        with self.lock:
            human_entries = [
                (pid, seat)
                for pid, seat in sorted(self.seats.items())
                if seat.get("control") == "human" and seat.get("connected")
            ]
            if len(human_entries) != len(saved_humans):
                return (
                    f"存档需要 {len(saved_humans)} 名人类玩家，"
                    f"当前已连接 {len(human_entries)} 名。请让原玩家都连接后再读取。"
                )

            unmatched: dict[int, Player] = {p.id: p for p in saved_humans}
            assignments: dict[int, int] = {}

            def assign(seat_id: int, player: Player) -> None:
                assignments[seat_id] = player.id
                unmatched.pop(player.id, None)

            for seat_id, seat in human_entries:
                value = seat.get("game_player_id")
                if isinstance(value, int) and value in unmatched:
                    assign(seat_id, unmatched[value])

            for seat_id, seat in human_entries:
                if seat_id in assignments:
                    continue
                character_id = seat.get("character_id")
                matches = [p for p in unmatched.values() if p.character_id == character_id]
                if len(matches) == 1:
                    assign(seat_id, matches[0])

            for seat_id, seat in human_entries:
                if seat_id in assignments:
                    continue
                name = seat.get("name")
                matches = [p for p in unmatched.values() if p.name == name]
                if len(matches) == 1:
                    assign(seat_id, matches[0])

            remaining_seats = [(pid, seat) for pid, seat in human_entries if pid not in assignments]
            remaining_players = list(unmatched.values())
            if len(remaining_seats) != len(remaining_players):
                return "无法把当前连接的玩家和存档里的玩家对应起来，请检查名字和角色是否一致。"

            for (seat_id, _seat), player in zip(remaining_seats, remaining_players):
                assign(seat_id, player)

            for seat_id, player_id in assignments.items():
                player = engine.state.players[player_id]
                seat = self.seats[seat_id]
                seat["game_player_id"] = player_id
                seat["name"] = player.name
                seat["character_id"] = player.character_id
                seat["ready"] = True

        self.decision_queues = {
            player.id: self.decision_queues.get(player.id, queue.Queue())
            for player in saved_humans
        }
        return None

    def stop(self) -> None:
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
