"""网络消息协议：全部为一行 JSON 文本（UTF-8，以换行分隔）。"""
from __future__ import annotations

import socket

# 客户端 → 服务器
JOIN = "join"            # {"name","character_id","is_host","password","session_token","reconnect_player_id"} 加入/重连
LOBBY_UPDATE = "lobby_update"  # {"name","character_id","is_host","ready"} 开局前更新大厅选择
START = "start"          # {"fill_to","bot_difficulty"} 房主开始游戏（不足补AI）
ACTION = "action"        # {"action","data"} 玩家操作（转成 ActionCommand）
DECISION = "decision"    # {"req_id","value"} 决策回复
SAVE_GAME = "save_game"  # 房主保存当前联机局到主机电脑
LOAD_GAME = "load_game"  # 房主从主机电脑读取联机存档

# 服务器 → 客户端
WELCOME = "welcome"      # {"player_id","session_token","is_host","state"} 分配身份+当前状态
LOBBY = "lobby"          # {"seats":[...],"game_started":bool} 大厅玩家列表
STATE = "state"          # {"state":{...}} 全量状态广播
REQUEST = "request"      # {"req_id","title","message","req_kind","options"} 请求决策
NOTIFY = "notify"        # {"title","message"} 信息弹窗（广播）
DICE = "dice"            # {"dice":[int...],"total":int,"label":str} 骰子投掷动画展示
GAME_OVER = "gameover"   # {"winner","reason"}
ERROR = "error"          # {"message"}
PING = "ping"
PONG = "pong"

# request 类型（decision.value 格式）
REQ_LIST = "list"        # 单选列表 → int 下标
REQ_CONFIRM = "confirm"  # 是/否 → bool
REQ_ROTATION = "rotation"  # 房间朝向（选项字符串）→ int 下标
REQ_SPLIT = "split"      # 伤害分配 → int


def encode(obj: dict) -> bytes:
    """把消息字典编码为一行 JSON（UTF-8 + 换行）。"""
    import json

    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def decode(data: bytes | str) -> dict:
    import json

    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    return json.loads(data)


def recv_line(sock) -> str | None:
    """从 socket 读一行（直到换行），连接关闭返回 None。

    注意：这只是无缓冲的单行读取，多次消息粘包时会丢弃后续内容。
    正式使用请用 BufferedLineReader。
    """
    buf = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            if not buf:
                return None
            break
        buf.extend(chunk)
        newline = buf.find(b"\n")
        if newline >= 0:
            return bytes(buf[:newline]).decode("utf-8", "replace")
        if len(buf) > 1024 * 1024:
            break
    return bytes(buf).decode("utf-8", "replace") if buf else None


class BufferedLineReader:
    """带缓冲区的行读取器：正确处理多条 JSON 消息粘包在一个 TCP 段的情况。"""

    def __init__(self, sock) -> None:
        self.sock = sock
        self.buf = bytearray()

    def readline(self) -> str | None:
        while True:
            nl = self.buf.find(b"\n")
            if nl >= 0:
                line = bytes(self.buf[:nl]).decode("utf-8", "replace")
                del self.buf[:nl + 1]
                return line
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                raise
            except OSError:
                chunk = b""
            if not chunk:
                if not self.buf:
                    return None
                line = bytes(self.buf).decode("utf-8", "replace")
                self.buf.clear()
                return line
            self.buf.extend(chunk)
