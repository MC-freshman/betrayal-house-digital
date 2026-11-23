#!/usr/bin/env python
"""A-33 采集器：驱动一局本地对局，产出「对局美术真的画了图」的机读证据链。

做法
----
1. 先 ``SetProcessDpiAwareness(1)`` 再读系统 DPI（``GetDC(0)`` + ``GetDeviceCaps(dc, 88)``），
   保证读数是非虚拟化值；同时记录「对局美术布局 DPI」=96（见下）；
2. 起一个 ``ui.GameApp`` 并 ``deiconify()``：探针要抓真实窗口截图，窗口必须真的映射到桌面，
   但停掉 300ms 空闲轮询（``_idle_poll``），由探针自己驱动回合，避免统计被机器人回合打断；
3. 4 名机器人（``bot_controller.take_turn``）推进对局到 ≥``turns`` / ≥``rooms``；
4. **清账本后按面逐个取证**（一帧一账）：棋盘 ``_redraw_board`` / 头像条 ``_refresh_avatar_strip`` /
   房间 tooltip ``_show_room_tooltip`` / 房间详情 ``_show_room_info`` / 抽卡弹窗
   ``_draw_omen``/``_draw_item``/``_draw_event`` → ``prompter.notify``；
   run6 追加六类渲染面：未翻地块（探索预览 ``room_back:*``）/ 作祟揭示
   （``engine._trigger_haunt`` → 手册弹窗 ``haunt:*``）/ 怪物标记（棋盘 ``monster:*``）/
   骰面（``ui._DiceDialog`` → ``dice:*``）/ 结算画面（``_set_winner`` → ``_EndingDialog``
   的 ``ending:*``）/ 抽卡弹窗顶部卡背（``card_back:*``，随每次抽卡取证）；
5. 每个渲染面都把 ``game_art`` 账本的新增行映射成验收 schema（``seq/surface/key/asset_type/
   record_id/rel_path/placeholder`` + 实测 ``actual``），并抓一张真 PNG 截图。

口径（与 ``docs/qa_game_art.md`` §8 的映射表一致）
-----------------------------------------------
* ``game_art`` 账本只记 ``kind``（room/card/character）+ 请求尺寸，**不记渲染面**，
  所以 ``surface`` 由探针按「调用点 + 请求尺寸」判定：棋盘=``ts×ts``（≤102）、
  tooltip=112、详情=160、面板头像=48、玩家详情头像=96、卡面=``(240, 336)``；
* ``actual`` 取 ``PhotoImage.width()/height()``（不是请求尺寸），因为绑定层会等比缩到包围盒；
* ``rel_path`` 去掉项目根前缀，保留 ``source/desktop/game/...``。

对局美术的尺寸口径
------------------
``ui.py`` 的 48 / 112 / 160 / (240, 336) 都是**固定像素常量**，取图链路（``game_art`` →
``ui_asset_binding``）不做 DPI 缩放（只有帮助页预览 ``_HelpDialog`` 才按 ``system_dpi/96`` 缩放）。
因此本探针同时记录两个 DPI：

* ``environment.system_dpi``：宿主显示器 DPI（本机 168 = 175%），仅作环境记录；
* ``environment.art_dpi``：对局美术的布局 DPI，恒为 96（尺寸常量的基准）。

验收脚本按 ``art_dpi/96`` 复算期望尺寸；若把 ``system_dpi`` 的缩放系数套到对局美术上，
在任何非 100% 显示器上都会把正确实现判死（240×336 的卡面不会因为系统 175% 变成 420×588）。

只写 ``qa/game_art_probe.json`` 与 ``qa/screenshots/art_*.png``；
不写 ``assets/``、``photos/``、``saves/``，不改 ``ui.py`` / ``game_art.py``。

用法::

    python qa/game_art_probe.py
    python qa/game_art_probe.py --min-rooms 10 --seed 7 --out qa/game_art_probe.json
"""

from __future__ import annotations

import argparse
import ctypes
import json
import platform
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent.parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
SHOT_DIR = QA_DIR / "screenshots"
DEFAULT_OUT = QA_DIR / "game_art_probe.json"

PROBE_SEED = 20261122
MIN_ROOMS = 8               # 验收下限（verify MIN_ROOMS）
TARGET_ROOMS = 12           # 探针目标：多放几间，保证账本 ≥ 20 条有余量
MIN_TURNS = 6               # 验收下限（verify MIN_TURNS）
MAX_TURNS = 80
PLAYER_COUNT = 4
ART_DPI = 96                # 对局美术布局 DPI（ui.py 常量基准），不是显示器 DPI
CARD_BASE = (240, 336)      # ui.CARD_FACE_SIZE
CARD_RATIO = 5.0 / 7.0
CARD_RATIO_TOL = 0.02
TOOLTIP_SIZE = 112          # ui.ROOM_TOOLTIP_SIZE
DETAIL_SIZE = 160           # ui.ROOM_DETAIL_SIZE
PANEL_AVATAR_SIZE = 48      # ui.AVATAR_PANEL_SIZE
PORTRAIT_AVATAR_SIZE = 96   # ui.AVATAR_DETAIL_SIZE

INPUT_FILES = {
    "ui_py_sha256": "ui.py",
    "ui_asset_binding_sha256": "ui_asset_binding.py",
    "p_table_sha256": "assets/p_table.json",
    "asset_mapping_sha256": "assets/asset_mapping.json",
}

CARD_DRAWERS = (
    ("omen", "抽到预兆：", "_draw_omen"),
    ("item", "获得物品：", "_draw_item"),
    ("event", "触发事件：", "_draw_event"),
)


# ---------------------------------------------------------------------------
# 环境 / 输入哈希
# ---------------------------------------------------------------------------

def _enable_dpi_awareness() -> dict:
    """建窗口、读 DPI 之前必须调用；返回 awareness 读数（0=unaware,1=system,2=per-monitor）。"""
    info = {"dpi_awareness": -1, "error": ""}
    if sys.platform != "win32":
        info["error"] = "非 win32：跳过 SetProcessDpiAwareness"
        return info
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)      # PROCESS_SYSTEM_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as exc:                            # pragma: no cover - 老系统
            info["error"] = "SetProcessDpiAwareness 失败：%r" % exc
            return info
    try:
        value = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(value))
        info["dpi_awareness"] = int(value.value)
    except Exception:
        pass
    return info


def _system_dpi() -> int:
    """user32.GetDC(0) + gdi32.GetDeviceCaps(dc, 88=LOGPIXELSX)；失败返回 0。"""
    if sys.platform != "win32":
        return 0
    try:
        dc = ctypes.windll.user32.GetDC(0)
        try:
            return int(ctypes.windll.gdi32.GetDeviceCaps(dc, 88))
        finally:
            ctypes.windll.user32.ReleaseDC(0, dc)
    except Exception:
        return 0


def _sha256_file(path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_hashes() -> dict:
    out = {}
    for key, relative in INPUT_FILES.items():
        path = GAME_DIR / relative
        out[key] = _sha256_file(path) if path.is_file() else ""
    return out


def _environment(awareness: dict) -> dict:
    import tkinter

    info = {
        "python": sys.version.split()[0],
        "tk": str(tkinter.TkVersion),
        "platform": sys.platform,
        "system": platform.platform(),
    }
    try:
        import PIL

        info["pillow"] = getattr(PIL, "__version__", "unknown")
    except Exception:
        info["pillow"] = None
    system_dpi = _system_dpi()
    info["system_dpi"] = system_dpi
    info["scale"] = round(system_dpi / 96.0, 4) if system_dpi else 0.0
    # 对局美术布局 DPI：ui.py 的尺寸常量是固定像素（@96 基准），取图链路不做 DPI 缩放。
    info["art_dpi"] = ART_DPI
    info["art_scale"] = round(ART_DPI / 96.0, 4)
    info["dpi_awareness"] = awareness.get("dpi_awareness", -1)
    if awareness.get("error"):
        info["dpi_awareness_error"] = awareness["error"]
    info["dpi_note"] = (
        "system_dpi 为宿主显示器 DPI，仅作环境记录；对局美术按 art_dpi=96 的固定像素布局渲染，"
        "期望尺寸按 art_dpi/96 复算（ui.py:61-66）。"
    )
    return info


def _rel_root(path) -> str:
    """项目根相对路径（assets/ 溯源用），保留 source/desktop/game/... 前缀。"""
    text = str(path or "").replace("\\", "/")
    if not text:
        return ""
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception:
        return text


def _rel_game(path) -> str:
    """game/ 相对路径（截图用），形如 qa/screenshots/art_card_omen.png。"""
    text = str(path or "").replace("\\", "/")
    if not text:
        return ""
    try:
        return str(Path(path).resolve().relative_to(GAME_DIR)).replace("\\", "/")
    except Exception:
        return text


# ---------------------------------------------------------------------------
# 渲染面判定（game_art 账本 → 验收 schema）
# ---------------------------------------------------------------------------

# run6 六类渲染面：kind 与 P 表 asset_type 同名，无需按尺寸二次推断。
SURFACE_KINDS = ("monster", "haunt", "ending", "card_back", "room_back", "dice")


def surface_for(kind: str, size) -> str:
    """按调用点的请求尺寸判定渲染面。

    尺寸来自 ui.py 的常量，互不重叠：棋盘 ts≤102（``tile_size - 8``，tile_size≤110）、
    tooltip 112、房间详情 160、面板头像 48、玩家详情头像 96、卡面 (240, 336)。
    run6 六类渲染面的 kind 自带语义（monster/haunt/...），直接作为 surface。
    """
    if kind in SURFACE_KINDS:
        return kind
    try:
        width = int(size[0])
    except (TypeError, ValueError, IndexError):
        return ""
    if kind == "card":
        return "card"
    if kind == "character":
        middle = (PANEL_AVATAR_SIZE + PORTRAIT_AVATAR_SIZE) // 2
        return "portrait" if width >= middle else "panel"
    if kind == "room":
        if width >= DETAIL_SIZE - 2:
            return "room_detail"
        if width >= TOOLTIP_SIZE - 2:
            return "room_tooltip"
        return "board"
    return ""


def asset_type_for(kind: str, key: str) -> str:
    """room/card/character → P 表 asset_type（card 还要拼 kind 段）。"""
    if kind != "card":
        return kind
    parts = str(key or "").split(":")
    if len(parts) >= 3 and parts[1] in ("omen", "item", "event"):
        return "card_%s" % parts[1]
    return "card"


def _alive(widget) -> bool:
    try:
        return bool(widget.winfo_exists())
    except Exception:
        return False


def _photo_size(photo):
    if photo is None:
        return None
    try:
        return [int(photo.width()), int(photo.height())]
    except Exception:
        return None


def _count_image_items(canvas) -> int:
    total = 0
    for item in canvas.find_all():
        if canvas.type(item) == "image":
            total += 1
    return total


def _canvas_art_keys(canvas) -> dict:
    """按 ``art:<runtime_key>`` 标签数画布上**真实存在**的图元。

    返回 ``{surface: [key, ...]}``；同一 surface 内保留重复（同房间两只同种怪物
    就是两个图元），调用方需去重时自己 set。
    """
    out: dict = {}
    try:
        items = canvas.find_all()
    except Exception:
        return out
    for item in items:
        try:
            tags = canvas.gettags(item)
        except Exception:
            continue
        for tag in tags:
            if not tag.startswith("art:"):
                continue
            key = tag[len("art:"):]
            surface = key.split(":", 1)[0]
            out.setdefault(surface, []).append(key)
    return out


def _surface_evidence(canvas, surface) -> dict:
    keys = _canvas_art_keys(canvas).get(surface, [])
    return {"image_items": len(keys), "keys": sorted(set(keys))}


# ---------------------------------------------------------------------------
# 取证器：截图 + 账本映射
# ---------------------------------------------------------------------------

_DIALOGS = []   # 探针持有的 _InfoDialog 实例（保住 PhotoImage 引用，见 _install_dialog_tracker）


def _install_dialog_tracker(ui_module):
    """让探针持有弹窗实例（``_InfoDialog`` / ``_TextDialog`` / ``_EndingDialog``）。

    两个原因，都不改 ``ui.py``：

    1. ``ui._show_room_info`` / ``_open_script_dialog`` 不保留弹窗返回值，
       ``PhotoImage`` 随局部变量出栈即被回收（``PhotoImage.__del__`` 会向 Tcl 发
       ``image delete``），图片区当场变空白；探针持引用才能截到真图；
    2. 卡面/详情/作祟插画要读 ``dialog.photo.width()/height()`` 才能给出**实测** ``actual``。
    """
    for name in ("_InfoDialog", "_TextDialog", "_EndingDialog"):
        original = getattr(ui_module, name, None)
        if original is None or getattr(original, "_probe_tracked", False):
            continue

        def _make(original_cls):
            class _TrackedDialog(original_cls):  # type: ignore[misc,valid-type]
                _probe_tracked = True

                def __init__(self, *args, **kwargs):
                    original_cls.__init__(self, *args, **kwargs)
                    _DIALOGS.append(self)

            return _TrackedDialog

        setattr(ui_module, name, _make(original))


class Capture(object):
    """一帧一账：把 ``game_art`` 账本增量映射成验收 schema，并抓真 PNG 截图。"""

    def __init__(self, app, tk_module, shot_dir):
        self.app = app
        self.tk = tk_module
        self.shot_dir = Path(shot_dir)
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        self.rows = []
        self.screenshots = []
        self.errors = []
        self.warnings = []
        self.seq = 0
        self._sweep_gen = 0

    # -- 截图 ---------------------------------------------------------
    def shoot(self, widget, name) -> dict:
        try:
            widget.update_idletasks()
            width = int(widget.winfo_width())
            height = int(widget.winfo_height())
            left = int(widget.winfo_rootx())
            top = int(widget.winfo_rooty())
        except Exception as exc:
            self.errors.append("截图失败 %s：%r" % (name, exc))
            return {}
        if width <= 1 or height <= 1:
            self.errors.append("截图失败 %s：窗口未映射（%dx%d）" % (name, width, height))
            return {}
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab(bbox=(left, top, left + width, top + height))
            path = self.shot_dir / name
            image.save(str(path))
        except Exception as exc:
            self.errors.append("截图失败 %s：%r" % (name, exc))
            return {}
        rel = _rel_game(path)
        self.screenshots.append(rel)
        return {"screenshot": rel, "shot_size": [int(image.width), int(image.height)]}

    # -- 账本映射 -----------------------------------------------------
    def _row(self, entry, actual) -> dict:
        self.seq += 1
        size = entry.get("size") or [0, 0]
        key = str(entry.get("key") or "")
        kind = str(entry.get("kind") or "")
        return {
            "seq": self.seq,
            "surface": surface_for(kind, size),
            "key": key,
            "asset_type": asset_type_for(kind, key),
            "record_id": str(entry.get("record_id") or ""),
            "rel_path": _rel_root(entry.get("path")),
            "placeholder": bool(entry.get("placeholder")),
            "requested": [int(size[0]), int(size[1])],
            "actual": actual,
            "resolved": bool(entry.get("resolved")),
        }

    def capture(self, expected_surface, action, photos=None) -> list:
        """执行一次渲染动作，把账本新增行收进 ledger。

        ``photos`` 返回该动作产出的 PhotoImage 序列（与账本新增行同序），用于实测 ``actual``；
        给不出来时 ``actual=None``（验收侧会落 NOT_RUN，而不是拿请求尺寸冒充实测值）。
        """
        before = len(self.app.art.ledger())
        action()
        entries = self.app.art.ledger()[before:]
        images = list(photos() or []) if photos is not None else []
        for index, entry in enumerate(entries):
            photo = images[index] if index < len(images) else None
            row = self._row(entry, _photo_size(photo))
            if expected_surface and row["surface"] != expected_surface:
                self.warnings.append(
                    "surface 推导不符：期望 %s，实得 %s（key=%s size=%s）"
                    % (expected_surface, row["surface"], row["key"], row["requested"]))
            self.rows.append(row)
        if len(entries) != len(images):
            self.warnings.append(
                "surface=%s 账本新增 %d 条 / 产出图片 %d 张（actual 缺失者按 null 记）"
                % (expected_surface, len(entries), len(images)))
        return entries

    # -- 模态弹窗抢拍 -------------------------------------------------
    def run_popup(self, action, shot_name, timeout=6.0, grace=1.5) -> dict:
        """执行会弹出模态框的动作，在 ``wait_window`` 里抢拍一张并把弹窗关掉。

        ``ui`` 里两条模态链路都要覆盖：

        * 抽卡：``engine._draw_omen/_draw_item/_draw_event`` → ``prompter.notify``；
        * 房间详情：``_show_room_info`` → ``_show_info`` → ``_InfoDialog`` + ``wait_window``。

        窗口映射要几帧，所以「未映射的弹窗」先等 ``grace`` 秒再关；一次抽卡可能连带弹出
        别的事件说明，扫尾阶段把剩余 Toplevel 一并关掉，避免探针被第二个模态框永久阻塞。
        """
        info = {"title": "", "photo": None, "back_photo": None, "handled": False,
                "screenshot": "", "shot_size": None}
        started = time.time()
        deadline = started + timeout
        settle = 0.30                      # 等窗口淡入/排完版再抢拍，避免截到半透明中间帧
        first_seen = [0.0]
        self._sweep_gen += 1
        generation = self._sweep_gen

        def sweep():
            if generation != self._sweep_gen:
                return
            now = time.time()
            handles = []
            for dialog in list(_DIALOGS):
                handles.append((
                    getattr(dialog, "top", None),
                    getattr(dialog, "photo", None),
                    getattr(dialog, "back_photo", None),
                ))
            try:
                for widget in self.app.winfo_children():
                    if isinstance(widget, self.tk.Toplevel):
                        handles.append((widget, None, None))
            except Exception:
                pass
            for top, photo, back_photo in handles:
                if top is None or not _alive(top):
                    continue
                try:
                    mapped = bool(top.winfo_ismapped())
                except Exception:
                    mapped = False
                if mapped:
                    if first_seen[0] <= 0:
                        first_seen[0] = now
                    if info["handled"]:
                        try:
                            top.destroy()
                        except Exception:
                            pass
                    elif now - first_seen[0] >= settle:
                        info["handled"] = True
                        try:
                            info["title"] = top.title()
                        except Exception:
                            info["title"] = ""
                        info["photo"] = photo
                        info["back_photo"] = back_photo
                        info.update(self.shoot(top, shot_name))
                        try:
                            top.destroy()
                        except Exception:
                            pass
                elif now - started > grace:
                    try:
                        top.destroy()
                    except Exception:
                        pass
            if now < deadline:
                self.app.after(60, sweep)

        self.app.after(60, sweep)
        try:
            action()
        finally:
            self._sweep_gen += 1        # 让残留的 sweep 立刻失效
            try:
                self.app.update_idletasks()
            except Exception:
                pass
        return info


# ---------------------------------------------------------------------------
# 对局驱动
# ---------------------------------------------------------------------------

def _player_configs(catalog, count: int = PLAYER_COUNT) -> list:
    """全机器人配置：take_turn 会用 BotDecisionProvider 顶掉 prompter，不会弹窗阻塞。"""
    faces = list(catalog.characters.values())[:count]
    configs = []
    for index, face in enumerate(faces):
        configs.append(
            {
                "name": "探针机器人%d" % (index + 1),
                "character_id": face.id,
                "control": "bot",
                "bot_difficulty": "normal",
                "bot_style": "balanced",
            }
        )
    return configs


class _ProbePrompter(object):
    """只把 ``notify`` 交给真实 Tk 弹窗；其余决策给默认值，避免第二个模态框把探针卡死。

    抽卡卡面由 ``notify`` 渲染（J2 的取证对象），confirm/choose_from_list 之类的规则问答
    不是本次验收对象，交给探针自动作答，保证 ``_draw_omen`` 这类真实抽卡调用能跑完。
    """

    def __init__(self, tk_prompter):
        self.tk = tk_prompter

    def notify(self, title, message):
        return self.tk.notify(title, message)

    def confirm(self, title, message):
        return True

    def choose_from_list(self, title, message, options):
        return 0 if options else None

    def choose_rotation(self, title, message, placements, entry_direction):
        return 0 if placements else None

    def choose_split_damage(self, title, message, amount, first_label, second_label):
        return 0

    def show_dice_roll(self, dice, total, label):
        return None


class _SilentPrompter(_ProbePrompter):
    """强制推进到作祟阶段时用：不弹任何窗口，避免模态框把探针卡死。

    ``_trigger_haunt`` 会走 ``notify``（私密手册）与 ``choose_traitor``（叛徒选择），
    两者都改成无界面返回；叛徒按引擎属性规则默认值决定（返回 None）。
    """

    def notify(self, title, message):
        return None

    def choose_traitor(self, candidates, state):
        return None


class _Event(object):
    """伪造悬停事件：``_show_room_tooltip`` 只读 x_root / y_root。"""

    def __init__(self, x_root, y_root):
        self.x_root = int(x_root)
        self.y_root = int(y_root)


def _draw_cards(app, capture, catalog, art_scale) -> list:
    """omen/item/event 各抽一张，抓弹窗卡面截图。"""
    engine = app.engine
    state = engine.state
    player = engine.current_player
    original = engine.prompter
    cards = []
    for kind, prefix, method_name in CARD_DRAWERS:
        drawer = getattr(engine, method_name, None)
        record = {
            "kind": kind,
            "card_id": "",
            "title": "",
            "record_id": "",
            "photo_size": None,
            "expected_size": [int(round(CARD_BASE[0] * art_scale)),
                              int(round(CARD_BASE[1] * art_scale))],
            # run6 card_back:<kind>：抽卡弹窗顶部卡背（未翻开时显示）
            "back_key": "",
            "back_photo_size": None,
            "ratio_ok": False,
            "placeholder": True,
            "popup_opened": False,
            "screenshot": "",
            "shot_size": None,
            "trigger": "engine.%s → prompter.notify（真实抽卡调用）" % method_name,
        }
        if drawer is None:
            capture.errors.append("engine 缺少 %s，无法抽 %s 卡" % (method_name, kind))
            cards.append(record)
            continue

        before = len(app.art.ledger())
        engine.prompter = _ProbePrompter(original)
        try:
            info = capture.run_popup(
                lambda _fn=drawer: _fn(player), "art_card_%s.png" % kind)
        except Exception as exc:
            capture.errors.append("抽 %s 卡失败：%r" % (kind, exc))
            info = {"title": "", "photo": None, "handled": False}
        finally:
            engine.prompter = original

        entries = app.art.ledger()[before:]
        for entry in entries:
            row = capture._row(entry, _photo_size(info.get("photo")) if info["handled"] else None)
            if row["surface"] not in ("card", "card_back"):
                capture.warnings.append(
                    "抽 %s 卡时出现非卡面/非卡背账本行：%s / %s"
                    % (kind, row["surface"], row["key"]))
            capture.rows.append(row)
        card_row = next((r for r in entries if str(r.get("kind")) == "card"), None)
        back_row = next((r for r in entries if str(r.get("kind")) == "card_back"), None)
        # 只认实测：拿不到 PhotoImage 就留 None，由验收侧落 NOT_RUN，不拿请求尺寸冒充实测值。
        record["photo_size"] = _photo_size(info.get("photo"))
        record["title"] = info.get("title") or ""
        record["popup_opened"] = bool(info.get("handled"))
        record["screenshot"] = info.get("screenshot") or ""
        record["shot_size"] = info.get("shot_size")
        if info.get("handled"):
            record["placeholder"] = False
        if card_row is not None:
            key = str(card_row.get("key") or "")
            parts = key.split(":")
            record["card_id"] = parts[2] if len(parts) >= 3 else ""
            record["record_id"] = str(card_row.get("record_id") or "")
            record["placeholder"] = bool(card_row.get("placeholder"))
        if back_row is not None:
            record["back_key"] = str(back_row.get("key") or "")
        # 卡背是弹窗里的独立 Label 图元（不是卡面），单独记实测尺寸。
        record["back_photo_size"] = _photo_size(info.get("back_photo"))
        size = record.get("photo_size")
        if size and size[1]:
            deviation = abs(size[0] / float(size[1]) - CARD_RATIO) / CARD_RATIO
            record["ratio_ok"] = bool(deviation <= CARD_RATIO_TOL)
        if not record["card_id"]:
            card = None
            try:
                import ui

                card = ui._card_from_notice(catalog, record["title"])
            except Exception:
                card = None
            if card is not None:
                record["card_id"] = card.id
        if not record["record_id"] and record["card_id"]:
            registry = getattr(app.art, "registry", None)
            ref = registry.resolve("card:%s:%s" % (kind, record["card_id"])) if registry else None
            record["record_id"] = getattr(ref, "record_id", "") or ""
        cards.append(record)
    return cards


def _collect_unreachable(app) -> list:
    """P 表 room 键 - catalog 房间模板 = 不可达房间（当前应为 ['storeroom']）。"""
    registry = getattr(app.art, "registry", None)
    if registry is None:
        return []
    try:
        catalog = app.engine.catalog
        templates = set(getattr(catalog, "room_templates", {}) or {})
        keys = {ref.runtime_key for ref in registry.by_type("room") if ref.runtime_key}
    except Exception:
        return []
    orphan = keys - {"room:%s" % template for template in templates}
    return sorted(key.split(":", 1)[1] for key in orphan if key.startswith("room:"))


def _count_ambiguous_cards(app) -> int:
    """有多少张卡在 P 表里取不到图（>0 表示抽到它只能退化成纯文字）。"""
    registry = getattr(app.art, "registry", None)
    if registry is None:
        return -1
    missing = 0
    for card in getattr(app.engine.catalog, "cards", {}).values():
        if registry.resolve("card:%s:%s" % (card.kind, card.id)) is None:
            missing += 1
    return missing


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(seed: int = PROBE_SEED, min_rooms: int = MIN_ROOMS, max_turns: int = MAX_TURNS,
        shot_dir=SHOT_DIR, target_rooms: int = TARGET_ROOMS) -> dict:
    awareness = _enable_dpi_awareness()
    result = {
        "tool": "qa/game_art_probe.py",
        "mode": "real-tk",
        "seed": seed,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "environment": _environment(awareness),
        "inputs": _input_hashes(),
        "board": {},
        "players": {},
        "room_tooltip": {},
        "room_detail": {},
        "ledger": [],
        "counters": {},
        "cards": [],
        "screenshots": [],
        "unreachable": [],
        "instrumentation": [
            "app._idle_poll 置空（停掉 300ms 轮询，回合由探针驱动）",
            "ui._InfoDialog / _TextDialog / _EndingDialog 换成跟踪子类（持图 + 读实测尺寸）",
            "engine.prompter 在抽卡期间包一层（notify 走真弹窗，规则问答自动作答）",
            "未翻地块取证时临时把当前玩家 control 置 human（只为画探索预览格，规则不变）",
            "作祟取证走 engine._trigger_haunt 真实揭示路径，prompter 换成 _SilentPrompter",
            "若作祟未生成怪物，按 engine._spawn_single_haunt_monster 真实生成路径补一只",
            "结算取证最后执行：engine._set_winner('heroes') + _refresh_ui 打开 _EndingDialog",
        ],
        "errors": [],
        "warnings": [],
        "pass": False,
    }

    import tkinter as tk

    import ui  # 推到有 Tk 的进程里 import；import 时 ui 会再设一次 DPI awareness

    result["environment"] = _environment(awareness)
    _install_dialog_tracker(ui)

    app = ui.GameApp()
    try:
        app.geometry("1440x900+40+40")
        app.deiconify()                     # 真截图需要真映射
        app.attributes("-topmost", True)
        idle = getattr(app, "_idle_after", None)
        if idle is not None:
            try:
                app.after_cancel(idle)
            except Exception:
                pass
            app._idle_after = None
        app._idle_poll = lambda: None       # 防止 update() 里被重新排上
        app.update()

        engine = app.engine
        rng = getattr(engine, "rng", None)
        if rng is not None:
            rng.seed(seed)                  # 固定房间/牌堆抽取顺序，样本可复现

        capture = Capture(app, tk, shot_dir)
        result["environment"]["screen"] = [int(app.winfo_screenwidth()),
                                           int(app.winfo_screenheight())]

        engine.start_new_game(_player_configs(engine.catalog))
        app._build_game_board()
        app._build_legend()
        app._refresh_ui()
        engine.start_turn()
        app._refresh_ui()

        state = engine.state
        turns = 0
        while turns < max_turns:
            if len(state.board) >= max(min_rooms, target_rooms) and turns >= MIN_TURNS:
                break
            if state.phase == "GAME_OVER":
                break
            if not app.bot_controller.take_turn(engine):
                break
            turns += 1
            app._refresh_ui()

        # ---- 取证阶段：清账本，逐面取一次真证据（单面失败不影响其它面） ----
        app.art.reset_ledger()

        def phase(name, func, default=None):
            try:
                return func()
            except Exception:
                capture.errors.append(
                    "取证阶段 %s 失败：\n%s" % (name, traceback.format_exc(limit=6)))
                return default

        # 1) 棋盘：整帧贴图 + 画布图元数（本帧也可能包含 monster/room_back 图元）
        def _board_phase():
            capture.capture("", app._redraw_board,
                            lambda: list(getattr(app, "_board_photos", [])))
            app.update_idletasks()
            keys = _canvas_art_keys(app.board_canvas)
            return {
                "items": _count_image_items(app.board_canvas),
                "shot": capture.shoot(app.board_canvas, "art_board_100.png"),
                "monster": _surface_evidence(app.board_canvas, "monster"),
                "room_back": _surface_evidence(app.board_canvas, "room_back"),
            }

        board_phase = phase("棋盘", _board_phase, {}) or {}
        board_items = int(board_phase.get("items") or 0)
        board_shot = board_phase.get("shot") or {}

        # 2) 玩家头像条（面板档）
        def _panel_phase():
            capture.capture(
                "panel",
                lambda: app._refresh_avatar_strip(state),
                lambda: list(getattr(app, "_avatar_photos", {}).values()),
            )
            app.update_idletasks()
            strip = getattr(app, "avatar_strip", None)
            return capture.shoot(strip, "art_player_panel.png") if strip is not None else {}

        panel_shot = phase("玩家面板", _panel_phase, {})

        # 3) 房间 tooltip：覆盖 ≥3 间不同房间，第一张抢拍
        rooms = list(state.board.values())
        hovered = []
        tooltip_shot = {}

        def _tooltip_phase():
            shot = {}
            for index, room in enumerate(rooms[:4]):
                if not getattr(room, "template_id", ""):
                    continue
                event = _Event(app.winfo_rootx() + 120, app.winfo_rooty() + 120)
                capture.capture(
                    "room_tooltip",
                    lambda _room=room, _event=event: app._show_room_tooltip(_room, _event),
                    lambda: [getattr(app, "_room_tooltip_photo", None)],
                )
                app.update_idletasks()
                tip = getattr(app, "_room_tooltip", None)
                if index == 0 and tip is not None:
                    shot = capture.shoot(tip, "art_room_tooltip.png")
                if room.key not in hovered:
                    hovered.append(room.key)
                app._hide_room_tooltip()
            return shot

        tooltip_shot = phase("房间 tooltip", _tooltip_phase, {}) or {}
        refs_after_close = 1 if getattr(app, "_room_tooltip_photo", None) is not None else 0

        # 4) 房间详情：一张 160 缩略图 + 截图（_show_room_info 也是模态，走同一套抢拍）
        detail_shot = {}
        detail_opened = 0
        detail_room = rooms[0] if rooms else None

        def _detail_phase():
            nonlocal detail_opened
            before = len(app.art.ledger())
            info = capture.run_popup(
                lambda: app._show_room_info(detail_room), "art_room_detail.png")
            entries = app.art.ledger()[before:]
            for entry in entries:
                row = capture._row(entry, _photo_size(info.get("photo")) if info["handled"] else None)
                if row["surface"] != "room_detail":
                    capture.warnings.append(
                        "开房间详情时出现非详情账本行：%s / %s" % (row["surface"], row["key"]))
                capture.rows.append(row)
            if info["handled"]:
                detail_opened = 1
                return {"screenshot": info.get("screenshot", ""),
                        "shot_size": info.get("shot_size")}
            return {}

        if detail_room is not None:
            detail_shot = phase("房间详情", _detail_phase, {}) or {}

        # 5) 未翻地块（room_back:<back|ghost>）：探索预览格 + 悬停虚影
        #    必须放在抽卡之前：抽预兆会 stop_movement（steps_remaining=0），
        #    之后 explore_options 为空，预览格就画不出来了。
        room_back_evidence = {"image_items": 0, "keys": [], "screenshot": ""}

        def _room_back_phase():
            nonlocal room_back_evidence
            player = engine.current_player
            original_control = player.control
            # 探索预览本身只在"人类回合"绘制；这里临时放开 control，
            # 只影响是否画预览格，不改规则/不改引擎判定（探针 instrumentation 已登记）。
            player.control = "human"
            try:
                capture.capture("", app._redraw_board,
                                lambda: list(getattr(app, "_board_photos", [])))
                app.update_idletasks()
                evidence = _surface_evidence(app.board_canvas, "room_back")
                shot = capture.shoot(app.board_canvas, "art_room_back.png")
                tags = list(getattr(app, "_exploration_slots", {}))
                if tags:
                    tag = tags[0]
                    before = len(app.art.ledger())
                    app._on_exploration_slot_enter(tag)
                    entries = app.art.ledger()[before:]
                    for entry in entries:
                        photo = (app._board_photos[-1]
                                 if getattr(app, "_board_photos", None) else None)
                        capture.rows.append(capture._row(entry, _photo_size(photo)))
                    app.update_idletasks()
                    hover = _surface_evidence(app.board_canvas, "room_back")
                    evidence["image_items"] = max(
                        evidence.get("image_items", 0), hover.get("image_items", 0))
                    evidence["keys"] = sorted(set(evidence.get("keys", [])) | set(hover.get("keys", [])))
                    app._on_exploration_slot_leave(tag)
                evidence["exploration_slots"] = len(tags)
                evidence["screenshot"] = shot.get("screenshot", "")
                room_back_evidence = evidence
            finally:
                player.control = original_control

        phase("未翻地块", _room_back_phase, {})

        # 6) 抽卡弹窗：omen/item/event 各一次（同时取 card_back:<kind>）
        cards = phase("抽卡弹窗", lambda: _draw_cards(
            app, capture, engine.catalog,
            float(result["environment"].get("art_scale") or 1.0)), []) or []

        # 7) 作祟揭示（haunt:<n>）+ 怪物标记（monster:<template_id>）
        surface_monster = dict(board_phase.get("monster") or {"image_items": 0, "keys": []})
        haunt_evidence = {"image_items": 0, "keys": [], "dialog_opened": False,
                          "photo_size": None, "screenshot": ""}

        def _haunt_phase():
            nonlocal surface_monster, haunt_evidence
            real_prompter = engine.prompter
            viewer = engine.current_player
            original_control = viewer.control
            engine.prompter = _SilentPrompter(real_prompter)
            try:
                if not state.last_omen_id:
                    # 真实抽牌路径（SilentPrompter.notify 不弹窗）
                    engine._draw_omen(viewer)
                engine._trigger_haunt(viewer)
                # 单人热座语义：当前屏幕上就是这位玩家的手册
                viewer.control = "human"
                app._haunt_briefed_id = None
                app._refresh_ui()
                before = len(app.art.ledger())
                info = capture.run_popup(
                    lambda: app._maybe_show_haunt_briefing(), "art_haunt_reveal.png")
                entries = app.art.ledger()[before:]
                # 只收 haunt 行：_refresh_ui 同时会重画棋盘/头像，那些行另有取证帧，
                # 混进来会让 J4 看到"无 actual 的面板行"而误判 NOT_RUN。
                for entry in entries:
                    if str(entry.get("kind")) != "haunt":
                        continue
                    capture.rows.append(capture._row(entry, _photo_size(info.get("photo"))))
                keys = [str(entry.get("key") or "") for entry in entries
                        if str(entry.get("kind")) == "haunt"]
                if not keys:
                    keys = [str(row.get("key") or "") for row in capture.rows
                            if row.get("surface") == "haunt"]
                haunt_evidence = {
                    "image_items": 1 if info.get("photo") is not None else 0,
                    "keys": sorted({key for key in keys if key}),
                    "dialog_opened": bool(info.get("handled")),
                    "photo_size": _photo_size(info.get("photo")),
                    "screenshot": info.get("screenshot", ""),
                }

                def _redraw_and_count():
                    capture.capture("", app._redraw_board,
                                    lambda: list(getattr(app, "_board_photos", [])))
                    app.update_idletasks()
                    return _surface_evidence(app.board_canvas, "monster")

                evidence = _redraw_and_count()
                if not evidence.get("keys"):
                    # 少数剧本不生成怪物：走引擎真实生成路径补一只，保证 J7 有样本
                    templates = list(getattr(engine.catalog, "monsters", {}) or {})
                    if templates:
                        engine._spawn_single_haunt_monster(
                            {"template_id": templates[0]}, viewer.room_key)
                        evidence = _redraw_and_count()
                        evidence["spawned_by_probe"] = True
                surface_monster = evidence
            finally:
                viewer.control = original_control
                engine.prompter = real_prompter

        phase("作祟揭示", _haunt_phase, {})

        # 8) 骰面结果区（dice:<0|1|2>）
        dice_evidence = {"image_items": 0, "keys": [], "photo_size": None, "screenshot": ""}

        def _dice_phase():
            nonlocal dice_evidence
            before = len(app.art.ledger())
            dialog = ui._DiceDialog(app, [1, 2, 0], 3, "探针骰面", modal=False)
            try:
                # 真实流程由 _reveal 逐颗写入 _showing；探针直接落到"结果已出"的状态，
                # 让结果区同时出现 1/2/0 三个面（否则只有投掷前的 0 面）。
                dialog._showing = list(dialog.dice)
                dialog._show_result()          # 结果区：定格 1/2/0 三面
                app.update()                   # 让 Toplevel 真正映射后再截图
                entries = app.art.ledger()[before:]
                for entry in entries:
                    # 同一次 _draw_dice 会重绘多轮，逐条对齐图片不可靠；
                    # actual 留 null（J12 只断言图元存在且键合法），不拿请求尺寸冒充。
                    capture.rows.append(capture._row(entry, None))
                shot = capture.shoot(dialog.top, "art_dice.png")
                evidence = _surface_evidence(dialog.canvas, "dice")
                photos = list(getattr(dialog, "_dice_photos", []))
                evidence["photo_size"] = _photo_size(photos[0]) if photos else None
                evidence["screenshot"] = shot.get("screenshot", "")
                dice_evidence = evidence
            finally:
                dialog._close()

        phase("骰面", _dice_phase, {})

        # 8b) 棋盘终检：作祟 setup 可能新增剧本房，J1 必须按**最终**棋盘数图元
        def _final_board_phase():
            capture.capture("", app._redraw_board,
                            lambda: list(getattr(app, "_board_photos", [])))
            app.update_idletasks()
            return {
                "items": _count_image_items(app.board_canvas),
                "shot": capture.shoot(app.board_canvas, "art_board_100.png"),
            }

        final_board = phase("棋盘终检", _final_board_phase, {}) or {}
        board_items = int(final_board.get("items") or board_items)
        board_shot = final_board.get("shot") or board_shot

        # 9) 结算画面（ending:<heroes|traitor>）：放在最后，避免 GAME_OVER 影响前面取证
        ending_evidence = {"image_items": 0, "keys": [], "dialog_opened": False,
                           "winner": "", "photo_size": None, "screenshot": ""}

        def _ending_phase():
            nonlocal ending_evidence
            before = len(app.art.ledger())
            engine._set_winner("heroes", "探针：结算画面取证")
            app._refresh_ui()
            app.update()                       # 让全屏 Toplevel 真正映射后再截图
            dialog = getattr(app, "_ending_dialog", None)
            if dialog is None:
                return
            entries = app.art.ledger()[before:]
            # 同上：只收 ending 行，避免把 _refresh_ui 重画的面板/棋盘行带进账本。
            for entry in entries:
                if str(entry.get("kind")) != "ending":
                    continue
                capture.rows.append(capture._row(entry, _photo_size(dialog.photo)))
            evidence = _surface_evidence(dialog.canvas, "ending")
            evidence["dialog_opened"] = True
            evidence["winner"] = "heroes"
            evidence["photo_size"] = _photo_size(dialog.photo)
            evidence["screenshot"] = capture.shoot(
                dialog.top, "art_ending.png").get("screenshot", "")
            ending_evidence = evidence

        phase("结算画面", _ending_phase, {})

        # ---- 汇总 ----
        ledger = capture.rows
        counters_raw = app.art.counters()
        board_rows = [row for row in ledger if row["surface"] == "board"]
        board_keys = {row["key"] for row in board_rows if row["key"]}
        rooms_with_image = len({row["key"] for row in board_rows
                                if row["key"] and not row["placeholder"]})
        panel_rows = [row for row in ledger if row["surface"] in ("panel", "portrait")]
        room_count = len(state.board)

        players = []
        for index, player in enumerate(state.players):
            face = getattr(engine.catalog, "characters", {}).get(player.character_id)
            key = ""
            try:
                key = app.art.character_key(face)
            except Exception:
                key = ""
            row = next((item for item in panel_rows if item["key"] == key), None)
            players.append(
                {
                    "player_id": int(getattr(player, "id", index)),
                    "name": str(getattr(player, "name", "")),
                    "character_id": str(getattr(player, "character_id", "")),
                    "key": key,
                    "record_id": row["record_id"] if row else "",
                    "photo_size": row["actual"] if row else None,
                    "placeholder": row["placeholder"] if row else True,
                }
            )

        result["board"] = {
            "turns_played": turns,
            "rooms_placed": room_count,
            "canvas_image_items": board_items,
            "rooms_with_image": rooms_with_image,
            "rounds": int(getattr(state, "turn_count", 0) or 0),
            "board_keys": len(board_keys),
            "screenshot": board_shot.get("screenshot", ""),
            "shot_size": board_shot.get("shot_size"),
        }
        result["players"] = {
            "count": len(state.players),
            "avatar_records": [item["record_id"] for item in players],
            "panel_images": len([row for row in panel_rows
                                 if row["surface"] == "panel" and not row["placeholder"]]),
            "portrait_images": len([row for row in panel_rows
                                    if row["surface"] == "portrait" and not row["placeholder"]]),
            "records": players,
            "screenshot": panel_shot.get("screenshot", ""),
            "shot_size": panel_shot.get("shot_size"),
        }
        result["room_tooltip"] = {
            "hovered": hovered,
            "photo_refs_after_close": refs_after_close,
            "tooltip_size": [TOOLTIP_SIZE, TOOLTIP_SIZE],
            "screenshot": tooltip_shot.get("screenshot", ""),
            "shot_size": tooltip_shot.get("shot_size"),
        }
        result["room_detail"] = {
            "opened": detail_opened,
            "room": getattr(detail_room, "name", "") if detail_room is not None else "",
            "detail_size": [DETAIL_SIZE, DETAIL_SIZE],
            "screenshot": detail_shot.get("screenshot", ""),
            "shot_size": detail_shot.get("shot_size"),
        }
        # ---- run6 六类渲染面证据（J7–J12 的唯一输入；缺证据只能落 NOT_RUN） ----
        back_records = [c for c in cards
                        if isinstance(c, dict) and c.get("back_key")]
        card_back_evidence = {
            "image_items": len([c for c in back_records if c.get("back_photo_size")]),
            "keys": sorted({str(c.get("back_key")) for c in back_records}),
            "kinds": sorted({str(c.get("kind")) for c in back_records}),
            "photo_sizes": {str(c.get("kind")): c.get("back_photo_size")
                            for c in back_records},
        }
        monster_evidence = dict(surface_monster)
        # 「场上」= 所在房间已在棋盘上的怪物（ui 只画这些）；总数另记，便于对照。
        monster_evidence["monsters_on_board"] = len([
            monster for monster in state.monsters if monster.room_key in state.board])
        monster_evidence["monsters_total"] = len(state.monsters)
        surfaces = {
            "monster": monster_evidence,
            "haunt": dict(haunt_evidence),
            "ending": dict(ending_evidence),
            "card_back": card_back_evidence,
            "room_back": dict(room_back_evidence),
            "dice": dict(dice_evidence),
        }
        for name, evidence in surfaces.items():
            evidence["placeholder"] = len([
                row for row in ledger
                if row.get("surface") == name and row.get("placeholder")])
        result["surfaces"] = surfaces
        result["surfaces_complete"] = {
            name: bool(surfaces[name].get("keys")) for name in SURFACE_KINDS
        }

        result["ledger"] = ledger
        result["counters"] = {
            "rooms_placed": room_count,
            "image_items": board_items,
            "ledger_entries": len(ledger),
            "placeholder_hits": int(counters_raw.get("placeholder_hits", 0)),
            "resolve_failures": int(counters_raw.get("resolve_failures", 0)),
            "loader_errors": int(counters_raw.get("loader_errors", 0)),
            "requests": int(counters_raw.get("requests", 0)),
            "misses": int(counters_raw.get("misses", 0)),
            "name_ambiguous": _count_ambiguous_cards(app),
        }
        result["cards"] = cards
        result["screenshots"] = list(capture.screenshots)
        result["unreachable"] = _collect_unreachable(app)
        result["errors"].extend(capture.errors)
        result["warnings"].extend(capture.warnings)

        card_kinds = {card["kind"] for card in cards if card["popup_opened"]}
        result["pass"] = bool(
            room_count >= min_rooms
            and turns >= MIN_TURNS
            and board_items >= room_count
            and rooms_with_image == room_count
            and result["counters"]["placeholder_hits"] == 0
            and card_kinds == {"omen", "item", "event"}
            and bool(tooltip_shot)
            and bool(detail_shot)
            and len(ledger) >= 20
        )
    except Exception:
        result["errors"].append(traceback.format_exc(limit=8))
    finally:
        try:
            app.destroy()
        except Exception:
            pass

    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="A-33 对局美术渲染探针")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="探针产物路径")
    parser.add_argument("--min-rooms", type=int, default=MIN_ROOMS, help="要求的最少已放置房间数")
    parser.add_argument("--target-rooms", type=int, default=TARGET_ROOMS,
                        help="推进目标房间数（账本样本余量）")
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS, help="推进回合上限")
    parser.add_argument("--seed", type=int, default=PROBE_SEED, help="对局随机种子")
    parser.add_argument("--shot-dir", default=str(SHOT_DIR), help="截图输出目录")
    args = parser.parse_args(argv)

    result = run(seed=args.seed, min_rooms=args.min_rooms, max_turns=args.max_turns,
                 shot_dir=args.shot_dir, target_rooms=args.target_rooms)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out_path), "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    board = result.get("board") or {}
    counters = result.get("counters") or {}
    print(
        "turns={turns} rooms={rooms} canvas_image={items} rooms_with_image={with_image} "
        "ledger={ledger} placeholder_hits={hits} cards={cards} shots={shots} pass={passed}".format(
            turns=board.get("turns_played", 0),
            rooms=board.get("rooms_placed", 0),
            items=board.get("canvas_image_items", 0),
            with_image=board.get("rooms_with_image", 0),
            ledger=counters.get("ledger_entries", 0),
            hits=counters.get("placeholder_hits", -1),
            cards=len(result.get("cards") or []),
            shots=len(result.get("screenshots") or []),
            passed=result.get("pass"),
        )
    )
    if result.get("errors"):
        for line in result["errors"][:4]:
            print(line, file=sys.stderr)
        return 1
    print("产物：%s" % out_path)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
