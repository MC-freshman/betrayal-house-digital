from __future__ import annotations

import socket
import sys
import threading
import time
import queue
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    import game.net.client_app as client_module
    from game.content import build_catalog
    from game.launcher import LauncherApp
    from game.net import protocol as P
    from game.net.client_app import ClientApp, NetClient
    from game.net.protocol import BufferedLineReader
    from game.net.server import GameHost
else:
    from .net import client_app as client_module
    from .content import build_catalog
    from .launcher import LauncherApp
    from .net import protocol as P
    from .net.client_app import ClientApp, NetClient
    from .net.protocol import BufferedLineReader
    from .net.server import GameHost


class _SocketClient:
    def __init__(
        self,
        port: int,
        name: str,
        character_id: str,
        is_host: bool = False,
        *,
        password: str = "",
        ready: bool = False,
        reconnect_player_id: int | None = None,
        session_token: str = "",
    ) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.reader = BufferedLineReader(self.sock)
        self.name = name
        self.seat_id = -1
        self.viewer_id = -1
        self.session_token = ""
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

    def send(self, msg: dict) -> None:
        self.sock.sendall(P.encode(msg))

    def read_until(self, kind: str, timeout: float = 5.0) -> dict:
        end = time.time() + timeout
        last = None
        while time.time() < end:
            self.sock.settimeout(max(0.1, end - time.time()))
            line = self.reader.readline()
            if line is None:
                raise AssertionError(f"{self.name} disconnected while waiting for {kind}")
            msg = P.decode(line)
            last = msg
            if msg.get("kind") == kind:
                return msg
        raise AssertionError(f"timeout waiting for {kind}, last={last}")

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class _TimeoutThenDataSock:
    def __init__(self) -> None:
        self.calls = 0

    def recv(self, _size: int) -> bytes:
        self.calls += 1
        if self.calls == 1:
            raise socket.timeout()
        return P.encode({"kind": P.PONG})


def verify_socket_timeout_not_treated_as_disconnect() -> None:
    reader = BufferedLineReader(_TimeoutThenDataSock())
    try:
        reader.readline()
    except socket.timeout:
        pass
    else:
        raise AssertionError("socket.timeout should not be converted to EOF")
    assert P.decode(reader.readline())["kind"] == P.PONG


def verify_netclient_uses_blocking_socket_after_connect() -> None:
    catalog = build_catalog(3)
    character_id = next(iter(catalog.characters))
    host = GameHost(port=0)
    host.start()
    assert host.server_sock is not None
    port = host.server_sock.getsockname()[1]
    net = NetClient("127.0.0.1", port)
    try:
        net.connect()
        assert net.sock is not None
        assert net.sock.gettimeout() is None
        net.join("超时测试", character_id, is_host=True, ready=True)
        end = time.time() + 3
        seen_welcome = False
        while time.time() < end:
            try:
                msg = net.inbox.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg.get("kind") == P.WELCOME:
                seen_welcome = True
                break
        assert seen_welcome
    finally:
        net.running = False
        if net.sock:
            try:
                net.sock.close()
            except OSError:
                pass
        host.stop()


def _wait_for_human_turn(host: GameHost, timeout: float = 5.0) -> int:
    end = time.time() + timeout
    while time.time() < end:
        engine = host.engine
        if engine and engine.current_player.control == "human":
            return engine.current_player.id
        time.sleep(0.05)
    raise AssertionError("no human turn reached")


def _read_lobby_until(client: _SocketClient, predicate, timeout: float = 5.0) -> dict:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        lobby = client.read_until(P.LOBBY, timeout=max(0.1, end - time.time()))
        last = lobby
        if predicate(lobby):
            return lobby
    raise AssertionError(f"timeout waiting for lobby predicate, last={last}")


def verify_lobby_updates_and_player_mapping() -> None:
    catalog = build_catalog(1)
    character_ids = list(catalog.characters)

    host = GameHost(port=0)
    host.start()
    assert host.server_sock is not None
    port = host.server_sock.getsockname()[1]
    threading.Thread(target=host.run_loop, daemon=True).start()

    clients: list[_SocketClient] = []
    try:
        # Create a seat-id gap. This used to make seat_id and game player id diverge.
        temp = _SocketClient(port, "临时", character_ids[0])
        assert temp.read_until(P.WELCOME)["player_id"] == 0
        temp.close()
        time.sleep(0.2)

        c1 = _SocketClient(port, "甲", character_ids[0])
        clients.append(c1)
        welcome1 = c1.read_until(P.WELCOME)
        c1.seat_id = welcome1["player_id"]
        c1.session_token = welcome1["session_token"]
        assert c1.seat_id >= 1
        c1.read_until(P.LOBBY)

        c1.send(
            {
                "kind": P.LOBBY_UPDATE,
                "name": "甲新版",
                "character_id": character_ids[1],
                "is_host": True,
                "ready": False,
            }
        )
        lobby = _read_lobby_until(
            c1,
            lambda data: any(
                seat["player_id"] == c1.seat_id
                and seat["name"] == "甲新版"
                and seat["character_id"] == character_ids[1]
                for seat in data["seats"]
            ),
        )
        seat1 = next(seat for seat in lobby["seats"] if seat["player_id"] == c1.seat_id)
        assert seat1["is_host"] is True
        assert seat1["name"] == "甲新版"
        assert seat1["character_id"] == character_ids[1]
        assert seat1["ready"] is False

        c1.send({"kind": P.START, "fill_to": 4, "bot_difficulty": "normal"})
        assert "未准备" in c1.read_until(P.ERROR)["message"]

        c2 = _SocketClient(port, "乙", character_ids[0])
        clients.append(c2)
        welcome2 = c2.read_until(P.WELCOME)
        c2.seat_id = welcome2["player_id"]
        c2.session_token = welcome2["session_token"]
        c2.read_until(P.LOBBY)
        c2.send(
            {
                "kind": P.LOBBY_UPDATE,
                "name": "乙新版",
                "character_id": character_ids[2],
                "is_host": False,
                "ready": True,
            }
        )
        c1.read_until(P.LOBBY)
        lobby = _read_lobby_until(
            c2,
            lambda data: any(
                seat["player_id"] == c2.seat_id
                and seat["name"] == "乙新版"
                and seat["character_id"] == character_ids[2]
                and seat.get("ready") is True
                for seat in data["seats"]
            ),
        )
        seat2 = next(seat for seat in lobby["seats"] if seat["player_id"] == c2.seat_id)
        assert seat2["character_id"] == character_ids[2]
        assert seat2["ready"] is True

        c1.send(
            {
                "kind": P.LOBBY_UPDATE,
                "name": "甲新版",
                "character_id": character_ids[1],
                "is_host": True,
                "ready": True,
            }
        )
        lobby = _read_lobby_until(
            c1,
            lambda data: any(
                seat["player_id"] == c1.seat_id
                and seat.get("ready") is True
                for seat in data["seats"]
            ),
        )
        seat1 = next(seat for seat in lobby["seats"] if seat["player_id"] == c1.seat_id)
        assert seat1["ready"] is True

        c2.send({"kind": P.START, "fill_to": 4, "bot_difficulty": "normal"})
        assert "只有房主" in c2.read_until(P.ERROR)["message"]

        c1.send({"kind": P.START, "fill_to": 4, "bot_difficulty": "normal"})
        state1 = c1.read_until(P.STATE)["state"]
        state2 = c2.read_until(P.STATE)["state"]
        c1.viewer_id = state1["meta"]["viewer_id"]
        c2.viewer_id = state2["meta"]["viewer_id"]
        assert c1.viewer_id == 0
        assert c2.viewer_id == 1
        assert state1["players"][0]["character_id"] == character_ids[1]
        assert state1["players"][1]["character_id"] == character_ids[2]
        assert len(state1["players"]) == 4

        decision_result: list[bool | None] = []
        asker = threading.Thread(
            target=lambda: decision_result.append(
                host.request_decision(host.engine.state.players[0], P.REQ_CONFIRM, "测试", "确认路由", None)
            ),
            daemon=True,
        )
        asker.start()
        req = c1.read_until(P.REQUEST)
        assert req["req_kind"] == P.REQ_CONFIRM
        c1.send({"kind": P.DECISION, "req_id": req["req_id"], "value": True})
        asker.join(timeout=3)
        assert decision_result == [True]

        c1.close()
        time.sleep(0.4)
        assert host.engine.state.players[0].dead is False
        c1r = _SocketClient(
            port,
            "甲重连",
            character_ids[1],
            is_host=True,
            reconnect_player_id=c1.seat_id,
            session_token=c1.session_token,
        )
        clients.append(c1r)
        welcome_reconnect = c1r.read_until(P.WELCOME)
        assert welcome_reconnect["player_id"] == c1.seat_id
        assert welcome_reconnect["reconnected"] is True
        assert welcome_reconnect["state"]["meta"]["viewer_id"] == 0

        current_player_id = _wait_for_human_turn(host)
        acting_client = c1r if current_player_id == c1.viewer_id else c2
        before_turn = host.engine.state.turn_count
        acting_client.send({"kind": P.ACTION, "action": "end_turn", "data": {}})
        end = time.time() + 5
        while time.time() < end and host.engine.state.turn_count <= before_turn:
            time.sleep(0.05)
        assert host.engine.state.turn_count > before_turn
    finally:
        for client in clients:
            client.close()
        host.stop()


def verify_network_save_load() -> None:
    catalog = build_catalog(2)
    character_ids = list(catalog.characters)
    with TemporaryDirectory() as tmp:
        save_path = Path(tmp) / "network_save.json"
        host = GameHost(port=0, save_path=save_path)
        host.start()
        assert host.server_sock is not None
        port = host.server_sock.getsockname()[1]
        threading.Thread(target=host.run_loop, daemon=True).start()

        clients: list[_SocketClient] = []
        try:
            c1 = _SocketClient(port, "房主", character_ids[0], is_host=True, ready=True)
            clients.append(c1)
            welcome1 = c1.read_until(P.WELCOME)
            c1.seat_id = welcome1["player_id"]
            c1.session_token = welcome1["session_token"]
            c1.read_until(P.LOBBY)

            c2 = _SocketClient(port, "玩家二", character_ids[1], ready=True)
            clients.append(c2)
            welcome2 = c2.read_until(P.WELCOME)
            c2.seat_id = welcome2["player_id"]
            c2.session_token = welcome2["session_token"]
            c2.read_until(P.LOBBY)

            c1.send({"kind": P.START, "fill_to": 4, "bot_difficulty": "normal"})
            state1 = c1.read_until(P.STATE)["state"]
            c2.read_until(P.STATE)
            assert state1["meta"]["viewer_id"] == 0
            assert state1["players"][0]["character_id"] == character_ids[0]
            assert state1["players"][1]["character_id"] == character_ids[1]

            c2.send({"kind": P.SAVE_GAME})
            assert "房主" in c2.read_until(P.ERROR)["message"]

            c1.send({"kind": P.SAVE_GAME})
            assert "保存成功" in c1.read_until(P.NOTIFY)["title"]
            assert save_path.exists()

            assert host.engine is not None
            saved_dead = host.engine.state.players[0].dead
            saved_turn = host.engine.state.turn_count
            host.engine.state.players[0].dead = not saved_dead
            host.engine.state.turn_count = saved_turn + 7

            c1.send({"kind": P.LOAD_GAME})
            c1.read_until(P.STATE)
            loaded_state = c2.read_until(P.STATE)["state"]
            assert host.engine.state.players[0].dead is saved_dead
            assert host.engine.state.turn_count == saved_turn
            assert loaded_state["meta"]["viewer_id"] == 1
            assert loaded_state["players"][0]["character_id"] == character_ids[0]
            assert loaded_state["players"][1]["character_id"] == character_ids[1]
        finally:
            for client in clients:
                client.close()
            host.stop()


def verify_password_rejects_wrong_join() -> None:
    catalog = build_catalog(1)
    character_id = next(iter(catalog.characters))
    host = GameHost(port=0, password="secret")
    host.start()
    assert host.server_sock is not None
    port = host.server_sock.getsockname()[1]
    try:
        client = _SocketClient(port, "错口令", character_id, password="bad")
        try:
            error = client.read_until(P.ERROR)
            assert "口令" in error["message"]
        finally:
            client.close()
    finally:
        host.stop()


class _FakeNet:
    def __init__(self) -> None:
        self.inbox = queue.Queue()
        self.calls: list[tuple] = []

    def send_lobby_update(self, name: str, character_id: str, is_host: bool, ready: bool) -> None:
        self.calls.append(("lobby_update", name, character_id, is_host, ready))

    def send_start(self, fill_to: int, bot_difficulty: str = "normal") -> None:
        self.calls.append(("start", fill_to, bot_difficulty))

    def send_load_game(self) -> None:
        self.calls.append(("load",))

    def send_save_game(self) -> None:
        self.calls.append(("save",))


def _assert_visible_children_inside(root, parent) -> None:
    root.update_idletasks()
    root_left = root.winfo_rootx()
    root_top = root.winfo_rooty()
    root_right = root_left + root.winfo_width()
    root_bottom = root_top + root.winfo_height()
    for widget in parent.winfo_children():
        if not widget.winfo_ismapped():
            continue
        left = widget.winfo_rootx()
        top = widget.winfo_rooty()
        right = left + widget.winfo_width()
        bottom = top + widget.winfo_height()
        assert root_left <= left <= root_right, (widget, left, root_left, root_right)
        assert root_left <= right <= root_right, (widget, right, root_left, root_right)
        assert root_top <= top <= root_bottom, (widget, top, root_top, root_bottom)
        assert root_top <= bottom <= root_bottom, (widget, bottom, root_top, root_bottom)
        _assert_visible_children_inside(root, widget)


def verify_client_login_layout_stays_inside() -> None:
    app = ClientApp()
    try:
        app.geometry("1024x680")
        app.update()
        assert app.login_frame.winfo_width() <= 900
        _assert_visible_children_inside(app, app.login_page)
        for widget in (
            app.entry_ip,
            app.entry_port,
            app.entry_password,
            app.entry_name,
            app.char_menu,
            app.btn_connect,
            app.btn_start,
            app.btn_load_lobby,
            app.net_log_text,
        ):
            assert widget.winfo_width() >= 40, widget
            assert widget.winfo_rootx() >= app.winfo_rootx(), widget
            assert widget.winfo_rootx() + widget.winfo_width() <= app.winfo_rootx() + app.winfo_width(), widget
    finally:
        app.destroy()


def verify_launcher_layout_and_mode_buttons() -> None:
    app = LauncherApp()
    try:
        app.geometry("640x460")
        app.update_idletasks()
        _assert_visible_children_inside(app, app)
        for button in (app.btn_local_mode, app.btn_client_mode, app.btn_host_mode):
            assert button.winfo_width() >= 320
            assert button.winfo_height() >= 48
            assert button.bind("<Button-1>")
    finally:
        app.destroy()


def verify_client_flushes_lobby_before_start() -> None:
    app = ClientApp()
    try:
        app.withdraw()
        catalog = app.engine.catalog
        character_ids = list(catalog.characters)
        target_id = character_ids[2]
        target_name = catalog.characters[target_id].name
        fake = _FakeNet()
        app.net = fake
        app.my_is_host = True
        app.my_seat_id = 0
        app._lobby_started = False
        app._lobby_seats = [{
            "player_id": 0,
            "name": "测试玩家",
            "character_id": character_ids[0],
            "is_host": True,
            "ready": True,
            "connected": True,
            "game_player_id": None,
        }]
        app.entry_name.delete(0, "end")
        app.entry_name.insert(0, "测试玩家")
        app.combo_char.set(target_name)
        app.var_ready.set(True)
        app.var_host.set(True)
        app.spin_fill.delete(0, "end")
        app.spin_fill.insert(0, "4")

        app._start_game()

        assert fake.calls[0][0] == "lobby_update"
        assert fake.calls[0][2] == target_id
        assert fake.calls[0][4] is True
        assert fake.calls[1][0] == "start"

        class _FakeConfirmDialog:
            def __init__(self, root, title, message) -> None:
                self.result = True
                self.top = None

        app.wait_window = lambda _top: None  # type: ignore[method-assign]
        with patch.object(client_module, "_ConfirmDialog", _FakeConfirmDialog):
            app.btn_load_lobby.config(state="normal")
            app.btn_load_lobby.invoke()
        assert fake.calls[-2][0] == "lobby_update"
        assert fake.calls[-1][0] == "load"
    finally:
        app.destroy()


def main() -> None:
    verify_socket_timeout_not_treated_as_disconnect()
    verify_netclient_uses_blocking_socket_after_connect()
    verify_launcher_layout_and_mode_buttons()
    verify_client_login_layout_stays_inside()
    verify_client_flushes_lobby_before_start()
    verify_password_rejects_wrong_join()
    verify_lobby_updates_and_player_mapping()
    verify_network_save_load()
    print("verify_network: ok")


if __name__ == "__main__":
    main()
