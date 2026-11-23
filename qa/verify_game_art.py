#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A-33 对局美术渲染 —— 只读独立验收脚本（P 表美术接入对局 UI）。

定位
----
本脚本是 **独立验收方**，不是实现方，也不是探针：

* 只读：只读 ``qa/game_art_probe.json``、``assets/p_table.json``、PNG 头与源码文本；
  不写任何项目文件、不截图、不启动 Tk（``sys.dont_write_bytecode = True``）；
* 不运行 ``qa/game_art_probe.py`` / ``ui_capture.py`` / ``test_*.py`` 等会写
  ``qa/`` 或 ``assets/`` 的脚本；探针必须在验收进程之外先跑完；
* 只把 JSON 打到 stdout，**不落盘**；
* 验收前后对 4 个输入文件做 sha256 快照，运行期被改写即转 NOT_RUN，
  不把结果当冻结结论。

验收对象
--------
``docs/qa_game_art.md``（A-33 验收矩阵）的 12 条判据 + 3 条静态检查：

* J1 棋盘贴图：canvas image 图元数 ≥ 已放置房间数，且每间房都有非占位贴图；
* J2 抽卡卡面：omen/item/event 各弹一次，卡面 240×336×art_dpi/96 ±2、5:7 不拉伸，
  截图必须是真 PNG 且 IHDR 与 shot_size 一致；
* J3 全账本零占位：``placeholder_hits = 0``，路径级复核 + 记录级 usable/ok；
* J4 玩家头像：面板/头像档记录去重后覆盖全部玩家，record_id 落在 12 位角色内，
  面板档 48×48、详情档 96×96（见 §口径下面的 K-07）；
* J5 tooltip/详情缩略图：112×112 / 160×160（×art_dpi/96）图元，关闭后不泄漏引用；
* J6 键可反查：账本每条 key 都能 ``AssetRegistry.resolve`` 命中且 record_id 相等，
  ``unreachable == ["storeroom"]``；
* J7–J12（run6 六类渲染面）：怪物标记 ``monster:*``（canvas 图元数 ≥ 场上怪物数）、
  作祟揭示 ``haunt:*``、结算画面 ``ending:*``、牌堆卡背 ``card_back:*``、
  未翻地块 ``room_back:*``、骰面 ``dice:*``；证据来自
  ``qa/game_art_probe.json`` 的 ``surfaces``，缺证据只落 NOT_RUN；
* S1 ``ui.py`` 的**图片渲染点**覆盖四个渲染面：棋盘（``create_image``）、卡面
  （``Label(..., image=)``）、头像（``Label(..., image=)`` 或 ``.configure(image=)``）、
  tooltip/详情（``Label(..., image=)``）；四类缺任一即 FAIL；
* S2 ``game_art.py`` 存在且三键前缀 ``room:`` / ``card:`` / ``character:`` 齐备；
* S3 ``ui_asset_binding.DEFAULT_CACHE_CAPACITY >= 128``。

尺寸口径（K-07，务必与实现对齐）
--------------------------------
``ui.py`` 的 48 / 112 / 160 / (240, 336) 都是**固定像素常量**，取图链路
（``game_art`` → ``ui_asset_binding``）只做等比缩放，**不做 DPI 缩放**；只有帮助页预览
（``_HelpDialog._art_scaled_size``）才按 ``system_dpi/96`` 缩放。所以对局美术的期望尺寸
按 ``environment.art_dpi``（=96，尺寸常量基准）复算，``environment.system_dpi`` 只作为
宿主环境记录（本机 168 = 175%）。把 system_dpi 的系数套到对局美术上，会在任何非 100%
显示器上把正确实现判死（240×336 的卡面不会因系统 175% 变成 420×588）。

历史口径（未合并）：``docs/qa_game_art.md`` §3.4 写面板 64×64 / 详情 160×160，
但 ``ui.py`` 里没有对应常量（``AVATAR_PANEL_SIZE=48`` / ``AVATAR_DETAIL_SIZE=96``，
160 是房间详情缩略图）。按 K-01 的既有机制，命中旧口径判 **CONFLICT** 要求书面裁决。

判读纪律
--------
PASS：证据存在、格式合法、数值达标、与当前产物同源。
FAIL：证据存在但不合法/不达标/自相矛盾（如卡面拉伸、占位命中、键不可反查、
      自报期望尺寸与独立复算不一致）。
NOT_RUN：证据缺失或实现未交付（探针未跑、缺截图、game_art.py 不存在）。
      不进通过率分母，**绝不折算 PASS**，也不以 skip 冒充。
CONFLICT：同一事项存在两个未合并的口径，且证据只满足其中一个（如 J5 的
      112/160 与旧口径 96/192）。

缺证据只允许落 FAIL 或 NOT_RUN；本脚本没有 skip 分支。

用法
----
python qa/verify_game_art.py                # 机读 JSON（stdout）
python qa/verify_game_art.py --human        # 人读摘要
python qa/verify_game_art.py --probe <path> # 指定探针 JSON
python qa/verify_game_art.py --root <项目根>

退出码
------
0 PASS；1 FAIL；3 INCOMPLETE（仅 NOT_RUN/CONFLICT）；2 参数或内部异常。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

# 只读：任何导入都不得生成字节码。
sys.dont_write_bytecode = True

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT_RUN"
CONFLICT = "CONFLICT"

SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_GAME_DIR = SCRIPT_PATH.parents[1]
DEFAULT_PROJECT_ROOT = SCRIPT_PATH.parents[4]

# ---------------------------------------------------------------------------
# 口径常量（与 docs/qa_game_art.md §4 逐条对应；改这里必须同步改文档）
# ---------------------------------------------------------------------------
CARD_BASE = (240, 336)              # J2 卡面基准（与 A-19/20/21 同源）
PANEL_AVATAR_BASE = (48, 48)        # J4 面板头像 = ui.AVATAR_PANEL_SIZE（_refresh_avatar_strip）
DETAIL_AVATAR_BASE = (96, 96)       # J4 详情头像 = ui.AVATAR_DETAIL_SIZE（_PlayerDetailDialog）
# 历史口径（docs/qa_game_art.md §3.4 J4-5 的 64/160）：ui.py 里没有对应常量，命中即 CONFLICT
PANEL_AVATAR_BASE_SPEC = (64, 64)
DETAIL_AVATAR_BASE_SPEC = (160, 160)
TOOLTIP_BASE = (112, 112)           # J5 tooltip（边界审计 S-08 口径）
TOOLTIP_BASE_LEGACY = (96, 96)      # J5 旧口径（art_acceptance_criteria §J5）
DETAIL_BASE = (160, 160)            # J5 房间详情（边界审计 S-09 口径）
DETAIL_BASE_LEGACY = (192, 192)     # J5 旧口径（art_acceptance_criteria §J5）

SIZE_TOL = 2                        # 像素容差（A-19/20/21 同源）
CARD_RATIO = 5.0 / 7.0              # 卡面 5:7
CARD_RATIO_TOL = 0.02               # 比例偏差上限 2%

MIN_TURNS = 6                       # J1 样本下限
MIN_ROOMS = 8                       # J1 样本下限
MIN_PLAYERS = 3                     # J4 一局最少 3 人
LEDGER_FLOOR = 20                   # J3 账本样本下限
LEDGER_CAP = 512                    # 探针账本上限

# S1：四个渲染面各自至少 1 处图片渲染点（棋盘/卡面/头像/tooltip+详情）
S1_SURFACES = ("board", "card", "avatar", "tooltip_detail")
S1_SURFACE_TITLES = {
    "board": "棋盘（canvas create_image）",
    "card": "卡面（Label image=）",
    "avatar": "头像（Label image= / configure(image=)）",
    "tooltip_detail": "tooltip/详情（Label image=）",
}
# 探针调用的渲染入口 → 渲染面；改名即视为「接线变化」，S1 会明确报出未归属的渲染点。
S1_SCOPE_SURFACE = (
    ("_redraw_board", "board"),
    ("_InfoDialog.__init__", "card"),
    ("_PlayerDetailDialog.__init__", "avatar"),
    ("_refresh_avatar_strip", "avatar"),
    ("_show_room_tooltip", "tooltip_detail"),
)
# 帮助页美术预览（S-14）：不在对局渲染面内，只作信息记录，不计入四类
S1_PREVIEW_SCOPES = ("_HelpDialog.__init__", "_art_page._show_selected")
CACHE_CAPACITY_FLOOR = 128          # S3
CHARACTER_RECORDS = 12              # 12 位角色
CARD_KINDS = ("omen", "item", "event")
CARD_ASSET_TYPES = {"card_omen", "card_item", "card_event"}
UNREACHABLE_EXPECTED = ["storeroom"]
PLACEHOLDER_PATH_TOKENS = ("assets/placeholders/", "assets_ww/")

SURFACES = ("board", "card", "panel", "portrait", "room_tooltip", "room_detail",
            # run6 六类渲染面（J7–J12）；缺一不可，否则 J3 的账本 surface 白名单会报未知面
            "monster", "haunt", "ending", "card_back", "room_back", "dice")
# 六类渲染面的键前缀与允许段值（与 game_art.*_key / content.py 一致）
SURFACE_KEY_PREFIX = {
    "monster": "monster:",
    "haunt": "haunt:",
    "ending": "ending:",
    "card_back": "card_back:",
    "room_back": "room_back:",
    "dice": "dice:",
}
SURFACE_KEY_VALUES = {
    "ending": {"heroes", "traitor"},
    "card_back": {"omen", "item", "event"},
    "room_back": {"back", "ghost"},
    "dice": {"0", "1", "2"},
}
CARD_BACK_KINDS = ("omen", "item", "event")
# cache/reason 只用于观测，不作必填（避免对没有断言消费的字段制造 FAIL）。
LEDGER_REQUIRED = ("seq", "surface", "key", "asset_type", "record_id",
                   "rel_path", "placeholder")

# 尚未纳入机读断言的渲染面：显式排除（详见文档 §6）。
# run6 已把 U-01/U-02/U-03/U-04/U-05/U-07 六类渲染面接成 J7–J12，故不再排除；
# U-06 仍收窄为 S-11 多选弹窗；S-10 抽卡弹窗由 J2 承担（裁决 K-02）。
EXCLUDED_UNMAPPED = (
    {"id": "U-06", "surface": "S-11 多选舍弹窗（原含 S-10 抽卡弹窗）",
     "reason": "choose_from_list 只收 list[str]，无 card_id；S-11 不可达",
     "proof": "ui.py choose_from_list(options) 无 card 参数",
     "asserted_by": "S-10 抽卡弹窗不排除，由 J2 断言（裁决 K-02）"},
    {"id": "U-08", "surface": "反向孤儿 room:storeroom",
     "reason": "P 表 50 房间 vs catalog 49 模板；storeroom 有图无模板，永不被画",
     "proof": "差集实测 ['room:storeroom']（P-ROOM-048）",
     "asserted_by": "J6-5 只断言「显式登记为 unreachable」，不断言可见"},
    {"id": "U-09", "surface": "合成临时房 template_id='temp'",
     "reason": "仅用于落点可行性模拟，不进 state.board，不会渲染",
     "proof": "engine.py:1086 temp_board 局部变量",
     "asserted_by": "无（无渲染位）"},
)

# 显式不做机读断言（不进 A-33，不阻断）
MANUAL_ITEMS = (
    "美术是否美观、风格是否统一：人工目检，不做机读断言",
    "卡名/房名与画面语义是否对应：由 A-30 的 M-15 语义评审签字覆盖，不重复计数",
    "对局区叠加文字后的实测对比度：A-22 按设计值/预览页口径，A-33 不采棋盘像素",
    "动画/转场（卡牌上滑、房间揭示）：本轮无动画，不做断言",
    "高 DPI 下对局卡面观感：只断言尺寸公式，观感不可判定",
)

TITLES = {
    "J0": "证据归属（probe.mode/输入哈希/可解析）",
    "J1": "棋盘房间贴图：canvas image ≥ 已放置房间数",
    "J2": "抽卡弹窗卡面：三类各一次，240×336×dpi/96 且 5:7",
    "J3": "全账本零占位：placeholder_hits = 0",
    "J4": "玩家头像：面板/头像档覆盖全部玩家（48/96×art_dpi/96）",
    "J5": "tooltip/详情缩略图：112×112 / 160×160 图元",
    "J6": "取图键可反查：每条 key 都能 resolve 且 record_id 相等",
    "J7": "怪物标记：canvas 上 monster:* 图元数 ≥ 场上怪物数",
    "J8": "剧本插画：作祟揭示后存在 haunt:* 图元",
    "J9": "结算画面：GAME_OVER 后存在 ending:* 图元",
    "J10": "牌堆卡背：抽卡弹窗未翻开时存在 card_back:* 图元",
    "J11": "未翻地块：探索预览存在 room_back:* 图元",
    "J12": "骰面：骰子结果区存在 dice:* 图元",
    "S1": "ui.py 四类图片渲染面齐备（canvas create_image / Label image= / configure(image=)）",
    "S2": "game_art.py 存在且三键前缀 room:/card:/character: 齐备",
    "S3": "ui_asset_binding.DEFAULT_CACHE_CAPACITY ≥ 128",
}

# 断言条数（文档 §4/§5 的细分断言计数；用于自检文档与脚本是否同步）
ASSERTION_COUNT = {
    "J0": 4, "J1": 5, "J2": 6, "J3": 7, "J4": 6, "J5": 6, "J6": 5,
    "J7": 4, "J8": 4, "J9": 4, "J10": 4, "J11": 3, "J12": 3,
    "S1": 2, "S2": 3, "S3": 2,
}


# ---------------------------------------------------------------------------
# 基础工具（全部只读）
# ---------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def png_size(path):
    """只读 PNG 头返回 (width, height)；非 PNG 或损坏返回 None。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(33)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if head[12:16] != b"IHDR":
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def as_int(value, default=0):
    try:
        if value is None or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def as_size(value):
    """把 [w,h] / {"width":..} / "240x336" 归一成 (w,h)；不可解析返回 None。"""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    if isinstance(value, dict):
        width, height = value.get("width"), value.get("height")
        if width is not None and height is not None:
            try:
                return (int(width), int(height))
            except (TypeError, ValueError):
                return None
    if isinstance(value, str):
        parts = value.replace("×", "x").lower().split("x")
        if len(parts) == 2:
            try:
                return (int(parts[0].strip()), int(parts[1].strip()))
            except ValueError:
                return None
    return None


def near(value, expected, tol=SIZE_TOL):
    return value is not None and abs(int(value) - int(expected)) <= tol


def fmt(size):
    if not size:
        return "?"
    return "%dx%d" % (int(size[0]), int(size[1]))


def scaled(base, dpi):
    """按 dpi/96 换算物理尺寸；dpi 缺失返回 None。"""
    if not dpi:
        return None
    factor = float(dpi) / 96.0
    return (int(round(base[0] * factor)), int(round(base[1] * factor)))


def decide(problems, shortfalls, conflicts=None):
    """三态裁决：FAIL > CONFLICT > NOT_RUN > PASS。缺证据绝不 PASS。"""
    if problems:
        return FAIL
    if conflicts:
        return CONFLICT
    if shortfalls:
        return NOT_RUN
    return PASS


def join_unique(items, limit=6):
    """去重后拼接（同一个问题在多条记录上重复时只报一次）。"""
    return "；".join(list(dict.fromkeys(str(item) for item in items))[:limit])


def rollup(statuses):
    if any(s == FAIL for s in statuses):
        return FAIL
    if any(s == CONFLICT for s in statuses):
        return CONFLICT
    if any(s == NOT_RUN for s in statuses):
        return NOT_RUN
    return PASS


def read_json(path):
    """返回 (data, error)；error 为 '' 表示成功，"missing" 表示文件不存在。"""
    if not path or not Path(path).is_file():
        return None, "missing"
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), ""
    except Exception as exc:  # noqa: BLE001 - 证据损坏必须显式暴露
        return None, "unreadable: %s" % exc


# ---------------------------------------------------------------------------
# 上下文与探针装载
# ---------------------------------------------------------------------------

class Ctx(object):
    def __init__(self, root, probe_path=None):
        self.root = Path(root).resolve()
        self.game = self.root / "source" / "desktop" / "game"
        self.qa = self.game / "qa"
        self.paths = {
            "ui": self.game / "ui.py",
            "game_art": self.game / "game_art.py",
            "ui_binding": self.game / "ui_asset_binding.py",
            "asset_registry": self.game / "asset_registry.py",
            "p_table": self.game / "assets" / "p_table.json",
            "asset_mapping": self.game / "assets" / "asset_mapping.json",
            "probe": Path(probe_path).resolve() if probe_path else (self.qa / "game_art_probe.json"),
        }
        self.snapshots = {key: self._fingerprint(value) for key, value in self.paths.items()}

    @staticmethod
    def _fingerprint(path):
        path = Path(path)
        if not path.is_file():
            return None
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns, sha256_file(path))

    def rel(self, path):
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except (ValueError, OSError):
            return str(path).replace("\\", "/")

    def changed_inputs(self):
        changed = []
        for key, before in self.snapshots.items():
            if self._fingerprint(self.paths[key]) != before:
                changed.append(self.rel(self.paths[key]))
        return changed


class Probe(object):
    """game_art_probe.json 的只读视图 + J0 证据归属判定。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.path = Path(ctx.paths["probe"])
        self.data = {}
        self.error = ""
        self.mode = ""
        self.dpi = 0.0               # 对局美术布局 DPI（期望尺寸按它复算）
        self.dpi_source = ""
        self.system_dpi = 0.0        # 宿主显示器 DPI（环境记录）
        self.system_dpi_source = ""
        self.attribution_problems = []
        self.attribution_shortfalls = []
        self.load()

    # -- 装载 ---------------------------------------------------------
    def load(self):
        data, error = read_json(self.path)
        if error == "missing":
            self.error = "missing: %s" % self.ctx.rel(self.path)
        elif error:
            self.error = "%s: %s" % (self.ctx.rel(self.path), error)
        else:
            self.error = ""
        if data is None:
            return
        if not isinstance(data, dict):
            self.error = "顶层不是对象：%r" % type(data).__name__
            return
        self.data = data
        self.mode = str(data.get("mode") or "")
        env = data.get("environment") or {}
        self.system_dpi, self.system_dpi_source = self._resolve_system_dpi(env)
        self.dpi, self.dpi_source = self._resolve_art_dpi(env, self.system_dpi)
        self._attribute()

    @staticmethod
    def _resolve_system_dpi(env):
        """宿主显示器 DPI：优先 system_dpi，其次 dpi/tk_dpi，最后 scale×96。"""
        if not isinstance(env, dict):
            return 0.0, ""
        for key in ("system_dpi", "dpi", "tk_dpi"):
            value = env.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value), "environment.%s" % key
        scale = env.get("scale")
        if isinstance(scale, (int, float)) and scale > 0:
            return float(scale) * 96.0, "environment.scale"
        return 0.0, ""

    @staticmethod
    def _resolve_art_dpi(env, system_dpi):
        """对局美术布局 DPI（K-07）：期望尺寸按它复算，而不是宿主显示器 DPI。

        ``ui.py`` 的 48/112/160/(240, 336) 是固定像素常量，取图链路不做 DPI 缩放，
        所以 96 是唯一的正确基准；探针显式声明 ``art_dpi`` 时以它为准，
        未声明才回落到 system_dpi（等同旧口径，非 100% 显示器上会判死）。
        """
        if isinstance(env, dict):
            for key in ("art_dpi", "render_dpi", "layout_dpi"):
                value = env.get(key)
                if isinstance(value, (int, float)) and value > 0:
                    return float(value), "environment.%s" % key
            scale = env.get("art_scale")
            if isinstance(scale, (int, float)) and scale > 0:
                return float(scale) * 96.0, "environment.art_scale"
        if system_dpi:
            return float(system_dpi), "fallback: environment.system_dpi"
        return 0.0, ""

    def _attribute(self):
        """证据归属：mode + 4 个输入哈希必须与当前产物一致（文档 §4 J0）。"""
        if self.mode != "real-tk":
            self.attribution_shortfalls.append(
                "probe.mode=%r，非真实 Tk 渲染（要求 real-tk）" % self.mode)
        if self.dpi <= 0:
            self.attribution_shortfalls.append(
                "environment.art_dpi/system_dpi/scale 全缺失，无法独立复算期望尺寸")
        if self.system_dpi <= 0:
            self.attribution_shortfalls.append(
                "environment.system_dpi 缺失（宿主 DPI 必须可复算，不能只报美术布局 DPI）")
        inputs = self.data.get("inputs") or {}
        if not isinstance(inputs, dict) or not inputs:
            self.attribution_shortfalls.append("probe.inputs 缺失，证据不可归属")
            return
        pairs = (
            ("ui_py_sha256", "ui"),
            ("ui_asset_binding_sha256", "ui_binding"),
            ("p_table_sha256", "p_table"),
            ("asset_mapping_sha256", "asset_mapping"),
        )
        for key, target in pairs:
            path = self.ctx.paths[target]
            declared = str(inputs.get(key) or "")
            if not declared:
                self.attribution_shortfalls.append("%s 缺失，无法证明证据与当前产物同源" % key)
                continue
            if not path.is_file():
                self.attribution_shortfalls.append(
                    "%s 不存在，无法比对 %s" % (self.ctx.rel(path), key))
                continue
            actual = sha256_file(path)
            if declared != actual:
                self.attribution_shortfalls.append(
                    "%s 不一致（%s… vs %s…），证据早于当前产物" % (
                        key, declared[:12], actual[:12]))

    # -- 便捷访问 -----------------------------------------------------
    @property
    def usable(self):
        return bool(self.data) and not self.error and not self.attribution_problems \
            and not self.attribution_shortfalls

    def ledger(self):
        rows = self.data.get("ledger")
        return rows if isinstance(rows, list) else []

    def board(self):
        value = self.data.get("board")
        return value if isinstance(value, dict) else {}

    def counters(self):
        value = self.data.get("counters")
        return value if isinstance(value, dict) else {}

    def cards(self):
        value = self.data.get("cards")
        return value if isinstance(value, list) else []

    def players(self):
        value = self.data.get("players")
        return value if isinstance(value, dict) else {}

    def section(self, name):
        value = self.data.get(name)
        return value if isinstance(value, dict) else {}

    def screenshots(self):
        value = self.data.get("screenshots")
        return [str(item) for item in value] if isinstance(value, list) else []


class Records(object):
    """P 表索引（只读 JSON，不 import 被测模块）。"""

    def __init__(self, ctx):
        self.path = ctx.paths["p_table"]
        payload, error = read_json(self.path)
        self.error = error
        self.rows = []
        self.by_id = {}
        if isinstance(payload, dict):
            rows = payload.get("records")
            if isinstance(rows, list):
                self.rows = [r for r in rows if isinstance(r, dict)]
                self.by_id = {r.get("record_id"): r for r in self.rows}

    @property
    def ok(self):
        return bool(self.rows)

    def of_type(self, *types):
        wanted = set(types)
        return [r for r in self.rows if r.get("asset_type") in wanted]


def load_registry(ctx):
    """返回 (registry, error)。只 import 纯标准库模块，不产生字节码。"""
    if not ctx.paths["p_table"].is_file():
        return None, "缺少 assets/p_table.json"
    sys.path.insert(0, str(ctx.game))
    try:
        import asset_registry  # noqa: WPS433 - 运行期按路径导入，只读
        return asset_registry.AssetRegistry.load(str(ctx.paths["p_table"])), ""
    except Exception as exc:  # noqa: BLE001 - 导入失败要显式暴露
        return None, "asset_registry 不可用：%s" % exc
    finally:
        try:
            sys.path.remove(str(ctx.game))
        except ValueError:
            pass


def resolve_shot(ctx, value):
    """截图路径可能相对 game/、相对项目根，或只给文件名（默认 qa/screenshots/）。"""
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    tries = [candidate] if candidate.is_absolute() else [
        ctx.game / text,
        ctx.root / text,
        ctx.qa / "screenshots" / candidate.name,
    ]
    for path in tries:
        if Path(path).is_file():
            return Path(path)
    return None


# ---------------------------------------------------------------------------
# J0 证据归属
# ---------------------------------------------------------------------------

def check_j0(ctx, probe):
    if probe.error.startswith("missing:"):
        return NOT_RUN, "缺少 qa/game_art_probe.json（探针未运行）", [ctx.rel(probe.path)]
    if probe.error:
        return FAIL, "game_art_probe.json 不可解析：%s" % probe.error, [ctx.rel(probe.path)]
    if probe.attribution_problems:
        return FAIL, "；".join(probe.attribution_problems[:6]), [ctx.rel(probe.path)]
    if probe.attribution_shortfalls:
        return NOT_RUN, "；".join(probe.attribution_shortfalls[:6]), [ctx.rel(probe.path)]
    return PASS, ("mode=real-tk；4 个输入哈希与当前产物一致；art_dpi=%s（%s）；"
                  "system_dpi=%s（%s）") % (
        int(probe.dpi) if probe.dpi else "?", probe.dpi_source or "未声明",
        int(probe.system_dpi) if probe.system_dpi else "?",
        probe.system_dpi_source or "未声明"), []


def _gate(probe):
    """J1..J6 的公共前置：J0 未通过时不冒充 PASS，统一记 NOT_RUN。"""
    if probe.error:
        return "探针证据不可用：%s" % probe.error
    if probe.attribution_shortfalls:
        return "J0 证据归属未通过：%s" % probe.attribution_shortfalls[0]
    return ""


# ---------------------------------------------------------------------------
# J1 棋盘房间贴图
# ---------------------------------------------------------------------------

def check_j1(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    problems, shortfalls = [], []
    board = probe.board()
    ledger = probe.ledger()
    turns = as_int(board.get("turns_played"))
    rooms = as_int(board.get("rooms_placed"))
    items = as_int(board.get("canvas_image_items"))
    with_image = as_int(board.get("rooms_with_image"))
    board_rows = [r for r in ledger if r.get("surface") == "board"]
    board_keys = {str(r.get("key") or "") for r in board_rows}

    if turns < MIN_TURNS or rooms < MIN_ROOMS:
        shortfalls.append("样本不足：turns=%s rooms=%s（要求 ≥%d / ≥%d）"
                          % (turns, rooms, MIN_TURNS, MIN_ROOMS))
    if not board:
        shortfalls.append("probe.board 缺失（未采集棋盘）")
    if items < rooms:
        problems.append("canvas image=%d < rooms=%d" % (items, rooms))
    if with_image != rooms:
        problems.append("rooms_with_image=%d != rooms_placed=%d" % (with_image, rooms))
    bad_keys = sorted(k for k in board_keys
                      if k and (not k.startswith("room:") or len(k) <= len("room:")))
    if bad_keys:
        problems.append("board 键口径错误 %d 条：%s" % (len(bad_keys), ", ".join(bad_keys[:3])))
    bad_type = [r for r in board_rows if r.get("asset_type") != "room"]
    if bad_type:
        problems.append("board 记录 asset_type != room 共 %d 条" % len(bad_type))
    if board_keys and with_image and len(board_keys) != with_image:
        problems.append("board 账本去重 key=%d != rooms_with_image=%d（疑似自报虚高）"
                        % (len(board_keys), with_image))
    placeholder_rows = [r for r in board_rows if r.get("placeholder")]
    if placeholder_rows:
        problems.append("board 贴图落在占位 %d 条" % len(placeholder_rows))

    status = decide(problems, shortfalls)
    evidence = [ctx.rel(probe.path), "canvas_image_items=%d rooms=%d" % (items, rooms)]
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "turns=%d rooms=%d；canvas image=%d ≥ %d；%d/%d 房间有非占位贴图" % (
        turns, rooms, items, rooms, with_image, rooms), evidence


# ---------------------------------------------------------------------------
# J2 抽卡弹窗卡面
# ---------------------------------------------------------------------------

def check_j2(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    problems, shortfalls = [], []
    cards = [c for c in probe.cards() if isinstance(c, dict)]
    if not cards:
        return NOT_RUN, "probe.cards 缺失（抽卡弹窗未采集）", [ctx.rel(probe.path)]

    kinds = [str(c.get("kind") or "") for c in cards]
    missing = [k for k in CARD_KINDS if k not in kinds]
    if missing:
        shortfalls.append("三类卡缺 %s" % ", ".join(missing))
    if len(cards) < 3:
        shortfalls.append("cards 仅 %d 条（要求三类各至少一次）" % len(cards))
    not_opened = [c.get("card_id") for c in cards if c.get("popup_opened") is not True]
    if not_opened:
        shortfalls.append("popup_opened != true：%s" % ", ".join(map(str, not_opened[:3])))

    want = scaled(CARD_BASE, probe.dpi)
    if want is None:
        shortfalls.append("environment.system_dpi 缺失，无法独立复算卡面期望尺寸")
    character_ids = {r.get("record_id") for r in
                     Records(ctx).of_type(*CARD_ASSET_TYPES)}
    for card in cards:
        cid = str(card.get("card_id") or "?")
        size = as_size(card.get("photo_size"))
        declared = as_size(card.get("expected_size"))
        if size is None:
            shortfalls.append("%s 缺 photo_size" % cid)
            continue
        if card.get("placeholder") is True:
            problems.append("%s 卡面落在占位图" % cid)
        if want is not None:
            if not (near(size[0], want[0]) and near(size[1], want[1])):
                problems.append("%s 卡面 %s != %s（±%d）"
                                % (cid, fmt(size), fmt(want), SIZE_TOL))
            if declared is not None and not (
                    near(declared[0], want[0], 1) and near(declared[1], want[1], 1)):
                problems.append("%s 自报期望 %s 与独立复算 %s 不一致"
                                % (cid, fmt(declared), fmt(want)))
        if size[1]:
            deviation = abs(size[0] / float(size[1]) - CARD_RATIO) / CARD_RATIO
            if deviation > CARD_RATIO_TOL:
                problems.append("%s 比例偏离 5:7 %.1f%% (>%.0f%%)"
                                % (cid, deviation * 100, CARD_RATIO_TOL * 100))
        record_id = str(card.get("record_id") or "")
        if not record_id:
            shortfalls.append("%s 缺 record_id" % cid)
        elif character_ids and record_id not in character_ids:
            problems.append("%s record_id=%s 不在 P 表卡牌记录内" % (cid, record_id))
        shot = resolve_shot(ctx, card.get("screenshot"))
        if shot is None:
            shortfalls.append("%s 缺截图（J2 需真窗口截图，不得以数值替代）" % cid)
        else:
            actual = png_size(shot)
            if actual is None:
                problems.append("%s 截图不是有效 PNG：%s" % (cid, ctx.rel(shot)))
            else:
                shot_size = as_size(card.get("shot_size"))
                if shot_size is not None and tuple(shot_size) != tuple(actual):
                    problems.append("%s shot_size=%s 与 PNG IHDR=%s 不一致（疑似合成）"
                                    % (cid, fmt(shot_size), fmt(actual)))
                if as_int(actual[0]) < as_int(size[0]):
                    problems.append("%s 截图宽 %d < 弹窗卡面宽 %d"
                                    % (cid, actual[0], size[0]))

    status = decide(problems, shortfalls)
    evidence = [ctx.rel(probe.path)]
    for card in cards:
        shot = resolve_shot(ctx, card.get("screenshot"))
        if shot is not None:
            evidence.append(ctx.rel(shot))
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "omen/item/event 各弹一次；卡面 %s（dpi=%s）；5:7 偏差 ≤2%%；截图 IHDR 与 shot_size 一致" % (
        fmt(want), int(probe.dpi) if probe.dpi else "?"), evidence


# ---------------------------------------------------------------------------
# J3 全账本零占位
# ---------------------------------------------------------------------------

def check_j3(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    problems, shortfalls = [], []
    ledger = probe.ledger()
    counters = probe.counters()
    records = Records(ctx)

    if len(ledger) < LEDGER_FLOOR:
        shortfalls.append("账本样本 %d < %d" % (len(ledger), LEDGER_FLOOR))
    if len(ledger) > LEDGER_CAP:
        problems.append("账本 %d 条 > 上限 %d" % (len(ledger), LEDGER_CAP))

    hits = [r for r in ledger if r.get("placeholder") is True]
    declared_hits = as_int(counters.get("placeholder_hits"), -1)
    if hits:
        problems.append("占位命中 %d 条" % len(hits))
    if declared_hits < 0:
        shortfalls.append("counters.placeholder_hits 缺失（无法与账本交叉核对）")
    elif declared_hits != 0:
        problems.append("counters.placeholder_hits=%d != 0" % declared_hits)
    elif len(hits) != 0:
        problems.append("counters.placeholder_hits=0 与账本 %d 条占位矛盾" % len(hits))

    bad_paths = [str(r.get("rel_path") or "") for r in ledger
                 if any(token in str(r.get("rel_path") or "")
                        for token in PLACEHOLDER_PATH_TOKENS)]
    if bad_paths:
        problems.append("占位路径 %d 条：%s" % (len(bad_paths), bad_paths[0]))

    incomplete = [r for r in ledger
                  if any(key not in r for key in LEDGER_REQUIRED)]
    if incomplete:
        problems.append("账本缺必填字段 %d 条（如 %s）"
                        % (len(incomplete), ", ".join(
                            key for key in LEDGER_REQUIRED if key not in incomplete[0])[:60]))
    bad_surface = sorted({str(r.get("surface") or "") for r in ledger
                          if str(r.get("surface") or "") not in SURFACES})
    if bad_surface:
        problems.append("未知 surface：%s" % ", ".join(bad_surface[:4]))

    if not records.ok:
        shortfalls.append("P 表不可读，无法做记录级核对")
    else:
        unknown = [r for r in ledger if str(r.get("record_id") or "") not in records.by_id]
        if unknown:
            problems.append("账本出现未知 record_id %d 条：%r"
                            % (len(unknown), unknown[0].get("record_id")))
        not_usable = []
        for row in ledger:
            record = records.by_id.get(str(row.get("record_id") or ""))
            if record is None:
                continue
            if record.get("availability") != "usable" or record.get("runtime_status") != "ok":
                not_usable.append("%s(%s/%s)" % (
                    row.get("record_id"), record.get("availability"),
                    record.get("runtime_status")))
        if not_usable:
            problems.append("记录状态非 usable/ok %d 条：%s"
                            % (len(not_usable), ", ".join(not_usable[:3])))

    loader_errors = as_int(counters.get("loader_errors"), -1)
    resolve_failures = as_int(counters.get("resolve_failures"), -1)
    if loader_errors < 0 or resolve_failures < 0:
        shortfalls.append("counters 缺 loader_errors/resolve_failures")
    else:
        if loader_errors:
            problems.append("counters.loader_errors=%d" % loader_errors)
        if resolve_failures:
            problems.append("counters.resolve_failures=%d" % resolve_failures)

    status = decide(problems, shortfalls)
    evidence = [ctx.rel(probe.path)]
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "账本 %d 条；placeholder_hits=%d；占位路径 0；记录级 usable/ok；loader_errors=0" % (
        len(ledger), declared_hits if declared_hits >= 0 else 0), evidence


# ---------------------------------------------------------------------------
# J4 玩家头像
# ---------------------------------------------------------------------------

def check_j4(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    problems, shortfalls = [], []
    players = probe.players()
    ledger = probe.ledger()
    records = Records(ctx)
    count = as_int(players.get("count"))
    entries = players.get("records")
    entries = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []

    if not players:
        shortfalls.append("probe.players 缺失（玩家面板未采集）")
    if count < MIN_PLAYERS:
        shortfalls.append("玩家数 %d < %d" % (count, MIN_PLAYERS))

    panel_rows = [r for r in ledger if r.get("surface") in ("panel", "portrait")]
    panel_keys = {str(r.get("key") or "") for r in panel_rows if r.get("key")}
    if not panel_rows:
        shortfalls.append("账本无 panel/portrait 记录")
    elif count and len(panel_keys) != count:
        problems.append("面板/头像 key 去重 %d != 玩家数 %d" % (len(panel_keys), count))

    if entries:
        if len({str(e.get("character_id") or "") for e in entries}) < count:
            problems.append("players.records 角色覆盖 %d < %d" % (
                len({str(e.get("character_id") or "") for e in entries}), count))
    elif players:
        shortfalls.append("players.records 缺失，无法逐人核对")

    # 账本会跨多帧累积（面板/作祟/结算各刷一次），同一玩家同一 key 的重复行不算冲突；
    # 断言的是「不同头像 key 不得共用同一条角色记录」——与旧口径同义，只是按帧去重。
    record_by_key = {}
    for row in panel_rows:
        key = str(row.get("key") or "")
        record_id = str(row.get("record_id") or "")
        if key and record_id:
            record_by_key[key] = record_id
    portrait_ids = list(record_by_key.values())
    if len(set(portrait_ids)) != len(portrait_ids):
        problems.append("同一角色记录被绑到多个玩家头像（record_id 重复）")

    character_ids = {r.get("record_id") for r in records.of_type("character")}
    if not records.ok:
        shortfalls.append("P 表不可读，无法核对 12 位角色")
    elif character_ids:
        if len(character_ids) != CHARACTER_RECORDS:
            shortfalls.append("P 表 character 记录 %d != %d（基线漂移）"
                              % (len(character_ids), CHARACTER_RECORDS))
        stray = sorted({rid for rid in portrait_ids if rid and rid not in character_ids})
        if stray:
            problems.append("头像 record_id 不在 12 位角色内：%s" % ", ".join(stray[:3]))

    placeholder_rows = [r for r in panel_rows if r.get("placeholder")]
    if placeholder_rows:
        problems.append("头像落在占位 %d 条" % len(placeholder_rows))

    conflicts = []
    panel_want = scaled(PANEL_AVATAR_BASE, probe.dpi)
    detail_want = scaled(DETAIL_AVATAR_BASE, probe.dpi)
    spec_panel = scaled(PANEL_AVATAR_BASE_SPEC, probe.dpi)
    spec_detail = scaled(DETAIL_AVATAR_BASE_SPEC, probe.dpi)
    if panel_want is None:
        shortfalls.append("environment.art_dpi/system_dpi 缺失，无法核对头像尺寸档位")

    def _avatar_size(label, size):
        """头像尺寸三态：命中实现档 → 通过；命中旧文档档 → CONFLICT；其余 → FAIL。"""
        allowed = [w for w in (panel_want, detail_want) if w]
        if allowed and any(near(size[0], w[0]) and near(size[1], w[1]) for w in allowed):
            return
        legacy = [w for w in (spec_panel, spec_detail) if w]
        if legacy and any(near(size[0], w[0]) and near(size[1], w[1]) for w in legacy):
            conflicts.append("%s 命中旧口径 %s（ui.py 实际 48/96），需书面裁决" % (label, fmt(size)))
            return
        problems.append("%s 图元 %s 不属 48/96 档（×art_dpi/96，ui.py:61-62）" % (label, fmt(size)))

    for row in panel_rows:
        size = as_size(row.get("actual"))
        if size is None:
            shortfalls.append("%s 缺 actual 尺寸" % row.get("key"))
            continue
        _avatar_size(str(row.get("key")), size)
    for entry in entries:
        size = as_size(entry.get("photo_size"))
        if size is None:
            shortfalls.append("%s 缺 photo_size" % entry.get("player_id"))
            continue
        _avatar_size("玩家 %s 面板头像" % entry.get("player_id"), size)
        if entry.get("placeholder") is True:
            problems.append("%s 头像落在占位图" % entry.get("player_id"))

    status = decide(problems, shortfalls, conflicts)
    evidence = [ctx.rel(probe.path)]
    if problems:
        return FAIL, join_unique(problems), evidence
    if conflicts:
        return CONFLICT, join_unique(conflicts, 3), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "玩家 %d 人；面板/头像 key 去重 %d；record_id 全在 12 位角色内且不重复；尺寸 48/96×art_dpi/96 ±%d" % (
        count, len(panel_keys), SIZE_TOL), evidence


# ---------------------------------------------------------------------------
# J5 房间 tooltip / 详情缩略图
# ---------------------------------------------------------------------------

def _size_check(rows, primary, legacy, label, probe, problems, conflicts, shortfalls):
    want = scaled(primary, probe.dpi)
    want_legacy = scaled(legacy, probe.dpi)
    if want is None:
        shortfalls.append("environment.system_dpi 缺失，无法核对 %s 尺寸" % label)
        return
    for row in rows:
        size = as_size(row.get("actual"))
        if size is None:
            shortfalls.append("%s 记录缺 actual 尺寸" % label)
            continue
        if near(size[0], want[0]) and near(size[1], want[1]):
            continue
        if want_legacy and near(size[0], want_legacy[0]) and near(size[1], want_legacy[1]):
            conflicts.append("%s 命中旧口径 %s（本轮口径 %s），需书面裁决"
                             % (label, fmt(want_legacy), fmt(want)))
            continue
        problems.append("%s 图元 %s 不属 %s / %s" % (
            label, fmt(size), fmt(want), fmt(want_legacy) if want_legacy else "-"))


def check_j5(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    problems, shortfalls, conflicts = [], [], []
    tooltip = probe.section("room_tooltip")
    detail = probe.section("room_detail")
    ledger = probe.ledger()

    hovered = tooltip.get("hovered")
    hovered = [str(x) for x in hovered] if isinstance(hovered, list) else []
    opened = as_int(detail.get("opened"))
    tip_rows = [r for r in ledger if r.get("surface") == "room_tooltip"]
    detail_rows = [r for r in ledger if r.get("surface") == "room_detail"]

    if len(set(hovered)) < 3:
        shortfalls.append("tooltip 覆盖 %d 个房间 < 3" % len(set(hovered)))
    if opened < 1:
        shortfalls.append("详情弹窗打开 %d 次 < 1" % opened)
    if not tip_rows or not detail_rows:
        shortfalls.append("账本缺 room_tooltip/room_detail 记录")

    ok_rows = [r for r in tip_rows + detail_rows if r.get("placeholder") is False]
    if len(ok_rows) < 4:
        problems.append("缩略图非占位记录 %d 条 < 4" % len(ok_rows))
    placeholder_rows = [r for r in tip_rows + detail_rows if r.get("placeholder")]
    if placeholder_rows:
        problems.append("缩略图落在占位 %d 条" % len(placeholder_rows))

    refs = as_int(tooltip.get("photo_refs_after_close"), -1)
    if refs < 0:
        shortfalls.append("room_tooltip.photo_refs_after_close 缺失")
    elif refs != 0:
        problems.append("tooltip 关闭后仍持有 %d 个 PhotoImage 引用" % refs)

    _size_check(tip_rows, TOOLTIP_BASE, TOOLTIP_BASE_LEGACY, "tooltip", probe,
                problems, conflicts, shortfalls)
    _size_check(detail_rows, DETAIL_BASE, DETAIL_BASE_LEGACY, "room_detail", probe,
                problems, conflicts, shortfalls)

    shots = []
    for section, name in ((tooltip, "art_room_tooltip"), (detail, "art_room_detail")):
        value = section.get("screenshot")
        shot = resolve_shot(ctx, value)
        if shot is None:
            # 退一步按 probe.screenshots 的 basename 匹配（art_room_tooltip / art_room_detail）
            for item in probe.screenshots():
                if Path(str(item)).stem == name:
                    shot = resolve_shot(ctx, item)
                    break
        if shot is None:
            shortfalls.append("%s 缺截图（J5 需截图证据，不得以账本单独折算 PASS）" % name)
            continue
        actual = png_size(shot)
        if actual is None:
            problems.append("%s 不是有效 PNG：%s" % (name, ctx.rel(shot)))
        else:
            shots.append(ctx.rel(shot))
            declared = as_size(section.get("shot_size"))
            if declared is not None and tuple(declared) != tuple(actual):
                problems.append("%s shot_size=%s 与 IHDR=%s 不一致"
                                % (name, fmt(declared), fmt(actual)))

    status = decide(problems, shortfalls, conflicts)
    evidence = [ctx.rel(probe.path)] + shots
    if problems:
        return FAIL, join_unique(problems), evidence
    if conflicts:
        return CONFLICT, join_unique(conflicts, 3), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "tooltip %s / 详情 %s（dpi=%s）；非占位 %d 条；关闭后引用 0；2 张截图 IHDR 一致" % (
        fmt(scaled(TOOLTIP_BASE, probe.dpi)), fmt(scaled(DETAIL_BASE, probe.dpi)),
        int(probe.dpi) if probe.dpi else "?", len(ok_rows)), evidence


# ---------------------------------------------------------------------------
# J6 取图键可反查
# ---------------------------------------------------------------------------

def check_j6(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    problems, shortfalls = [], []
    ledger = probe.ledger()
    counters = probe.counters()
    registry, error = load_registry(ctx)
    if registry is None:
        shortfalls.append(error)
        return NOT_RUN, error, [ctx.rel(ctx.paths["asset_registry"])]
    if not ledger:
        shortfalls.append("账本为空，无可反查的键")

    unresolved, mismatched = [], []
    for row in ledger:
        key = row.get("key")
        record_id = str(row.get("record_id") or "")
        if not key:
            shortfalls.append("账本记录缺 key（seq=%r）" % row.get("seq"))
            continue
        ref = registry.resolve(key)
        if ref is None:
            unresolved.append(str(key))
            continue
        if record_id and str(ref.record_id) != record_id:
            mismatched.append("%s→%s（账本 %s）" % (key, ref.record_id, record_id))
    if unresolved:
        problems.append("键不可反查 %d 条：%s（共 %d 条账本）"
                        % (len(unresolved), ", ".join(unresolved[:3]), len(ledger)))
    if mismatched:
        problems.append("键↔记录不一致 %d 条：%s" % (len(mismatched), mismatched[0]))

    resolve_failures = as_int(counters.get("resolve_failures"), -1)
    name_ambiguous = as_int(counters.get("name_ambiguous"), -1)
    if resolve_failures < 0:
        shortfalls.append("counters.resolve_failures 缺失")
    elif resolve_failures:
        problems.append("counters.resolve_failures=%d" % resolve_failures)
    if name_ambiguous < 0:
        shortfalls.append("counters.name_ambiguous 缺失")
    elif name_ambiguous:
        problems.append("counters.name_ambiguous=%d（有卡退化成纯文字）" % name_ambiguous)

    unreachable = probe.data.get("unreachable")
    if not isinstance(unreachable, list):
        shortfalls.append("probe.unreachable 缺失（不可达位必须显式登记）")
    else:
        normalized = sorted({str(x).strip() for x in unreachable if str(x).strip()})
        if normalized != UNREACHABLE_EXPECTED:
            problems.append("unreachable=%r，期望 %r" % (unreachable, UNREACHABLE_EXPECTED))

    status = decide(problems, shortfalls)
    evidence = [ctx.rel(probe.path), ctx.rel(ctx.paths["asset_registry"])]
    if problems:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "账本 %d 条 key 全部 resolve 命中且 record_id 相等；resolve_failures=0；name_ambiguous=0；unreachable=['storeroom']" % len(ledger), evidence


# ---------------------------------------------------------------------------
# J7–J12 六类渲染面（run6）
# ---------------------------------------------------------------------------

def _surface(probe, name):
    """取 ``probe.surfaces.<name>``；缺失/类型不对统一返回空 dict（落 NOT_RUN）。"""
    surfaces = probe.data.get("surfaces")
    if not isinstance(surfaces, dict):
        return {}
    value = surfaces.get(name)
    return value if isinstance(value, dict) else {}


def _surface_keys(section):
    values = section.get("keys")
    return [str(item) for item in values] if isinstance(values, list) else []


def _surface_evidence_list(ctx, probe, section):
    evidence = [ctx.rel(probe.path)]
    shot = resolve_shot(ctx, section.get("screenshot"))
    if shot is not None:
        evidence.append(ctx.rel(shot))
    return evidence


def _key_shape_problems(name, keys, problems):
    """键前缀 + 段值合法性（不依赖 P 表；record 级一致性由 J6/账本保证）。"""
    prefix = SURFACE_KEY_PREFIX[name]
    allowed = SURFACE_KEY_VALUES.get(name)
    bad_prefix = [key for key in keys
                  if not key.startswith(prefix) or len(key) <= len(prefix)]
    if bad_prefix:
        problems.append("%s 键口径错误 %d 条：%s"
                        % (name, len(bad_prefix), ", ".join(bad_prefix[:3])))
    if allowed is not None:
        bad_value = [key for key in keys if key[len(prefix):] not in allowed]
        if bad_value:
            problems.append("%s 键段值非法 %d 条：%s"
                            % (name, len(bad_value), ", ".join(bad_value[:3])))


def check_j7(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    section = _surface(probe, "monster")
    if not section:
        return NOT_RUN, "probe.surfaces.monster 缺失（未采集怪物标记）", [ctx.rel(probe.path)]
    evidence = _surface_evidence_list(ctx, probe, section)
    monsters = as_int(section.get("monsters_on_board"), -1)
    items = as_int(section.get("image_items"), -1)
    keys = _surface_keys(section)
    if monsters <= 0:
        return NOT_RUN, "场上无怪物（monsters_on_board=%s），怪物标记无从取证" % monsters, evidence
    problems, shortfalls = [], []
    if items < 0:
        shortfalls.append("monster.image_items 缺失")
    elif items < monsters:
        problems.append("monster 图元 %d < 场上怪物 %d" % (items, monsters))
    if not keys:
        problems.append("monster 图元缺少 art:monster:* 键标签（无法证明画的是真图）")
    _key_shape_problems("monster", keys, problems)
    if as_int(section.get("placeholder"), 0):
        problems.append("怪物标记落在占位 %d 条" % as_int(section.get("placeholder")))
    status = decide(problems, shortfalls)
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "场上怪物 %d；monster 图元 %d ≥ %d；键 %d 个；占位 0" % (
        monsters, items, monsters, len(set(keys))), evidence


def check_j8(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    section = _surface(probe, "haunt")
    if not section:
        return NOT_RUN, "probe.surfaces.haunt 缺失（未采集作祟揭示）", [ctx.rel(probe.path)]
    evidence = _surface_evidence_list(ctx, probe, section)
    keys = _surface_keys(section)
    problems, shortfalls = [], []
    if not keys:
        shortfalls.append("作祟揭示未采集到 haunt:* 图元")
    if as_int(section.get("image_items"), 0) < 1:
        shortfalls.append("haunt.image_items<1")
    if section.get("dialog_opened") is not True:
        shortfalls.append("作祟手册弹窗未打开（dialog_opened != true）")
    _key_shape_problems("haunt", keys, problems)
    if as_int(section.get("placeholder"), 0):
        problems.append("作祟插画落在占位 %d 条" % as_int(section.get("placeholder")))
    status = decide(problems, shortfalls)
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "作祟揭示：haunt 图元 %d；键 %s；弹窗已打开" % (
        as_int(section.get("image_items")), ", ".join(keys[:3])), evidence


def check_j9(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    section = _surface(probe, "ending")
    if not section:
        return NOT_RUN, "probe.surfaces.ending 缺失（未采集结算画面）", [ctx.rel(probe.path)]
    evidence = _surface_evidence_list(ctx, probe, section)
    keys = _surface_keys(section)
    problems, shortfalls = [], []
    if not keys:
        shortfalls.append("GAME_OVER 后未采集到 ending:* 图元")
    if section.get("dialog_opened") is not True:
        shortfalls.append("结算画面未打开（dialog_opened != true）")
    winner = str(section.get("winner") or "")
    if not winner:
        shortfalls.append("ending.winner 缺失")
    elif winner not in SURFACE_KEY_VALUES["ending"]:
        problems.append("ending.winner=%r 不是 heroes/traitor" % winner)
    _key_shape_problems("ending", keys, problems)
    if as_int(section.get("placeholder"), 0):
        problems.append("结算插画落在占位 %d 条" % as_int(section.get("placeholder")))
    status = decide(problems, shortfalls)
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "结算画面：ending 图元 %d；键 %s" % (
        as_int(section.get("image_items")), ", ".join(keys[:3])), evidence


def check_j10(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    section = _surface(probe, "card_back")
    if not section:
        return NOT_RUN, "probe.surfaces.card_back 缺失（未采集牌堆卡背）", [ctx.rel(probe.path)]
    evidence = _surface_evidence_list(ctx, probe, section)
    keys = _surface_keys(section)
    problems, shortfalls = [], []
    if not keys:
        shortfalls.append("抽卡弹窗未采集到 card_back:* 图元")
    if as_int(section.get("image_items"), 0) < 1:
        shortfalls.append("card_back.image_items<1")
    missing = [kind for kind in CARD_BACK_KINDS
               if "card_back:%s" % kind not in keys]
    if missing:
        shortfalls.append("三类牌堆卡背缺 %s" % ", ".join(missing))
    _key_shape_problems("card_back", keys, problems)
    if as_int(section.get("placeholder"), 0):
        problems.append("卡背落在占位 %d 条" % as_int(section.get("placeholder")))
    status = decide(problems, shortfalls)
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "抽卡弹窗卡背：%d 个图元；键 %s" % (
        as_int(section.get("image_items")), ", ".join(keys[:3])), evidence


def check_j11(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    section = _surface(probe, "room_back")
    if not section:
        return NOT_RUN, "probe.surfaces.room_back 缺失（未采集未翻地块）", [ctx.rel(probe.path)]
    evidence = _surface_evidence_list(ctx, probe, section)
    keys = _surface_keys(section)
    problems, shortfalls = [], []
    if as_int(section.get("exploration_slots"), 0) <= 0:
        shortfalls.append("探索预览没有落点格（exploration_slots=0）")
    if not keys:
        shortfalls.append("探索预览未采集到 room_back:* 图元")
    if keys and "room_back:back" not in keys:
        problems.append("未翻地块缺 room_back:back（只有 ghost 不足以说明牌背已画）")
    _key_shape_problems("room_back", keys, problems)
    if as_int(section.get("placeholder"), 0):
        problems.append("未翻地块落在占位 %d 条" % as_int(section.get("placeholder")))
    status = decide(problems, shortfalls)
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    ghost = "room_back:ghost" in keys
    return PASS, "未翻地块：图元 %d；键 %s%s" % (
        as_int(section.get("image_items")), ", ".join(keys[:3]),
        "（含悬停虚影）" if ghost else ""), evidence


def check_j12(ctx, probe):
    blocked = _gate(probe)
    if blocked:
        return NOT_RUN, blocked, [ctx.rel(probe.path)]
    section = _surface(probe, "dice")
    if not section:
        return NOT_RUN, "probe.surfaces.dice 缺失（未采集骰面）", [ctx.rel(probe.path)]
    evidence = _surface_evidence_list(ctx, probe, section)
    keys = _surface_keys(section)
    problems, shortfalls = [], []
    if not keys:
        shortfalls.append("骰子结果区未采集到 dice:* 图元")
    if as_int(section.get("image_items"), 0) < 1:
        shortfalls.append("dice.image_items<1")
    _key_shape_problems("dice", keys, problems)
    if as_int(section.get("placeholder"), 0):
        problems.append("骰面落在占位 %d 条" % as_int(section.get("placeholder")))
    status = decide(problems, shortfalls)
    if status == FAIL:
        return FAIL, join_unique(problems), evidence
    if status == NOT_RUN:
        return NOT_RUN, join_unique(shortfalls, 4), evidence
    return PASS, "骰子结果区：图元 %d；键 %s" % (
        as_int(section.get("image_items")), ", ".join(keys[:3])), evidence


# ---------------------------------------------------------------------------
# 静态检查 S1/S2/S3（ast 解析，不 import 被测模块）
# ---------------------------------------------------------------------------

def parse_module(path):
    if not Path(path).is_file():
        return None, "文件不存在：%s" % str(path).replace("\\", "/")
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, "不可读：%s" % exc
    try:
        return ast.parse(text), ""
    except SyntaxError as exc:
        return None, "语法不可解析：%s" % exc


def _str_constants(node):
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _walk_scoped(tree):
    """遍历 AST 并带上最近的「类/函数」限定名（渲染面按所在入口判定）。"""
    stack = [(tree, "")]
    while stack:
        node, scope = stack.pop()
        if isinstance(node, ast.ClassDef):
            scope = "%s.%s" % (scope, node.name) if scope else node.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = "%s.%s" % (scope, node.name) if scope else node.name
        yield node, scope
        for child in ast.iter_child_nodes(node):
            stack.append((child, scope))


def _has_nonempty_image(node):
    """``image=`` 实参是否非空：``image=""`` / ``image=None`` 不算渲染点。"""
    for keyword in node.keywords:
        if keyword.arg != "image":
            continue
        value = keyword.value
        if isinstance(value, ast.Constant):
            return value.value not in (None, "")
        return True
    return False


def _call_kind(node):
    """Call 形态：canvas(create_image) / label(Label) / configure(.configure)。"""
    func = node.func
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    else:
        return ""
    if name == "create_image":
        return "canvas"
    if name == "Label":
        return "label"
    if name == "configure":
        return "configure"
    return ""


def _surface_for_scope(scope):
    for suffix, surface in S1_SCOPE_SURFACE:
        if scope == suffix or scope.endswith("." + suffix):
            return surface
    for suffix in S1_PREVIEW_SCOPES:
        if scope == suffix or scope.endswith("." + suffix):
            return "preview"
    return ""


def collect_render_points(tree):
    """AST 层的「图片渲染点」= create_image 调用 + Label(image=非空) + configure(image=非空)。

    实现里棋盘走 canvas、卡面/头像/tooltip/详情走 Label，只数 ``create_image`` 会得到
    1 处，必然把正确接线判死（旧口径 1 < 4 恒 FAIL）。这里按调用形态 + 所在入口
    判定渲染面，四个面各自要有 ≥1 处。
    """
    points = []
    for node, scope in _walk_scoped(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _call_kind(node)
        if not kind:
            continue
        if kind in ("label", "configure") and not _has_nonempty_image(node):
            continue
        points.append(
            {
                "kind": kind,
                "surface": _surface_for_scope(scope),
                "scope": scope,
                "line": int(getattr(node, "lineno", 0) or 0),
            }
        )
    points.sort(key=lambda item: (item["line"], item["kind"]))
    return points


def key_prefix_map(tree):
    """找每个键前缀落在哪个函数里（f-string 的首段常量也算）。"""
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for text in _str_constants(node):
            for prefix in ("room:", "card:", "character:"):
                if text.startswith(prefix):
                    found.setdefault(prefix, set()).add(node.name)
    return found


def class_methods(tree):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out[node.name] = sorted(
                item.name for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return out


def module_constant(tree, name):
    """取模块级 `NAME = <int>` 的字面值；找不到返回 (None, False)。"""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        else:
            continue
        if name not in targets:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            return int(value.value), True
    return None, False


def check_s1(ctx):
    """四类图片渲染面齐备（棋盘 / 卡面 / 头像 / tooltip+详情），缺任一即 FAIL。"""
    rel_ui = ctx.rel(ctx.paths["ui"])
    tree, error = parse_module(ctx.paths["ui"])
    if tree is None:
        return FAIL, "ui.py 不可用：%s" % error, [rel_ui]
    points = collect_render_points(tree)
    evidence = ["%s:%d %s/%s" % (rel_ui, item["line"], item["kind"],
                                 item["surface"] or "未归属") for item in points[:10]]
    if not points:
        return NOT_RUN, ("ui.py 尚无图片渲染点（canvas/Label 都没接对局取图），"
                         "记 NOT_RUN 而非 PASS"), evidence
    bad_line = [item for item in points if item["line"] <= 0]
    if bad_line:
        return FAIL, "有 %d 处渲染点行号不可定位（AST lineno=0）" % len(bad_line), evidence

    by_surface = {}
    for item in points:
        by_surface.setdefault(item["surface"], []).append(item)
    missing = [surface for surface in S1_SURFACES if not by_surface.get(surface)]
    summary = "、".join(
        "%s %d 处" % (S1_SURFACE_TITLES[surface], len(by_surface.get(surface, [])))
        for surface in S1_SURFACES)
    preview = len(by_surface.get("preview", []))
    tail = "；另 %d 处在帮助页预览（不计入四类）" % preview if preview else ""
    if missing:
        return FAIL, "渲染面缺 %s（共 %d 处渲染点：%s%s）" % (
            "、".join(S1_SURFACE_TITLES[surface] for surface in missing),
            len(points), summary, tail), evidence

    unowned = [item for item in points if not item["surface"]]
    detail = "图片渲染点 %d 处：%s；四类齐备%s" % (len(points), summary, tail)
    if unowned:
        detail += "；%d 处未归属（%s）" % (
            len(unowned), ", ".join("%s:%d" % (item["scope"] or "?", item["line"])
                                    for item in unowned[:3]))
    return PASS, detail, evidence


def check_s2(ctx):
    path = ctx.paths["game_art"]
    if not path.is_file():
        return NOT_RUN, "game_art.py 不存在（统一取图组件未交付，记 NOT_RUN 而非 PASS）", [
            ctx.rel(path)]
    tree, error = parse_module(path)
    if tree is None:
        return FAIL, "game_art.py 不可解析：%s" % error, [ctx.rel(path)]
    prefixes = key_prefix_map(tree)
    missing = [p for p in ("room:", "card:", "character:") if p not in prefixes]
    detail_map = ", ".join("%s→%s" % (p, "/".join(sorted(prefixes[p])[:2]))
                           for p in ("room:", "card:", "character:") if p in prefixes)
    methods = class_methods(tree)
    key_methods = sorted({name for names in methods.values() for name in names
                          if name.endswith("_key")})
    notes = "GameArt 方法：%s" % (", ".join(key_methods) if key_methods else "未发现 *_key")
    evidence = [ctx.rel(path)]
    if missing:
        return FAIL, "game_art.py 缺键前缀 %s（已找到：%s）；%s" % (
            ", ".join(missing), detail_map or "无", notes), evidence
    if key_methods and "ledger" in {n for names in methods.values() for n in names}:
        return PASS, "三键前缀齐备（%s）；%s；ledger() 存在" % (detail_map, notes), evidence
    return PASS, "三键前缀齐备（%s）；%s" % (detail_map, notes), evidence


def check_s3(ctx):
    tree, error = parse_module(ctx.paths["ui_binding"])
    if tree is None:
        return FAIL, "ui_asset_binding.py 不可用：%s" % error, [ctx.rel(ctx.paths["ui_binding"])]
    value, found = module_constant(tree, "DEFAULT_CACHE_CAPACITY")
    evidence = [ctx.rel(ctx.paths["ui_binding"])]
    if not found:
        return FAIL, "未找到模块级 DEFAULT_CACHE_CAPACITY 字面量", evidence
    if value >= CACHE_CAPACITY_FLOOR:
        return PASS, "DEFAULT_CACHE_CAPACITY=%d ≥ %d" % (value, CACHE_CAPACITY_FLOOR), evidence
    return FAIL, "DEFAULT_CACHE_CAPACITY=%d < %d（多尺寸档并发会互相淘汰，RK-05）" % (
        value, CACHE_CAPACITY_FLOOR), evidence


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def add_check(checks, cid, gate, priority, status, detail, evidence=None, blocking=True):
    item = {
        "id": cid,
        "gate": gate,
        "priority": priority,
        "title": TITLES.get(cid, cid),
        "status": status,
        "detail": detail,
        "evidence": [str(e).replace("\\", "/") for e in (evidence or [])],
        "assertions": ASSERTION_COUNT.get(cid, 0),
        "blocking": bool(blocking),
    }
    checks.append(item)
    return item


def build_payload(ctx, probe, checks, changed):
    counts = Counter(item["status"] for item in checks)
    statuses = [item["status"] for item in checks]
    verdict = rollup(statuses)
    claim = {"PASS": "attested", "FAIL": "not-attested",
             "CONFLICT": "partial", "NOT_RUN": "partial"}[verdict]
    inputs = {}
    for key, path in ctx.paths.items():
        path = Path(path)
        inputs[key] = {
            "path": ctx.rel(path),
            "exists": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else "",
            "bytes": path.stat().st_size if path.is_file() else 0,
        }
    return {
        "tool": "qa/verify_game_art.py",
        "mode": "a33-game-art-acceptance",
        "scope": ("A-33 对局美术渲染（G5/P0）：J1-J12 判据 + S1-S3 静态检查"
                  "（J7-J12 覆盖 run6 六类渲染面）"),
        "scope_claim_note": ("本结论只覆盖「已渲染且非占位」；不替代 A-19/A-20/A-21/A-22/A-32，"
                             "也不抵消任何 NOT_RUN"),
        "readonly": not changed,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(ctx.root).replace("\\", "/"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "probe": {
            "path": ctx.rel(probe.path),
            "exists": probe.path.is_file(),
            "sha256": sha256_file(probe.path) if probe.path.is_file() else "",
            "mode": probe.mode,
            "art_dpi": probe.dpi,
            "art_dpi_source": probe.dpi_source,
            "system_dpi": probe.system_dpi,
            "system_dpi_source": probe.system_dpi_source,
            "error": probe.error,
        },
        "inputs": inputs,
        "thresholds": {
            "card_base": list(CARD_BASE),
            "panel_avatar_base": list(PANEL_AVATAR_BASE),
            "detail_avatar_base": list(DETAIL_AVATAR_BASE),
            "panel_avatar_base_spec": list(PANEL_AVATAR_BASE_SPEC),
            "detail_avatar_base_spec": list(DETAIL_AVATAR_BASE_SPEC),
            "tooltip_base": list(TOOLTIP_BASE),
            "tooltip_base_legacy": list(TOOLTIP_BASE_LEGACY),
            "detail_base": list(DETAIL_BASE),
            "detail_base_legacy": list(DETAIL_BASE_LEGACY),
            "size_tolerance_px": SIZE_TOL,
            "card_ratio_tolerance": CARD_RATIO_TOL,
            "min_turns": MIN_TURNS,
            "min_rooms": MIN_ROOMS,
            "min_players": MIN_PLAYERS,
            "ledger_floor": LEDGER_FLOOR,
            "cache_capacity_floor": CACHE_CAPACITY_FLOOR,
            "s1_required_surfaces": list(S1_SURFACES),
        },
        "checks": checks,
        "counts": {
            "total": len(checks),
            "assertions": sum(item["assertions"] for item in checks),
            "status": dict(counts),
        },
        "failed": [item["id"] for item in checks if item["status"] == FAIL],
        "conflict": [item["id"] for item in checks if item["status"] == CONFLICT],
        "not_run": [item["id"] for item in checks if item["status"] == NOT_RUN],
        "excluded_unmapped": [dict(item) for item in EXCLUDED_UNMAPPED],
        "excluded_count": len(EXCLUDED_UNMAPPED),
        "manual": list(MANUAL_ITEMS),
        "readonly_evidence": {
            "snapshot_files": len(ctx.paths),
            "changed_during_audit": changed[:20],
        },
        "verdict": verdict,
        "completion_claim": claim,
    }


def print_human(payload):
    print("A-33 对局美术渲染 —— 只读独立验收")
    print("根目录: %s" % payload["root"])
    print("判定: %s    completion_claim: %s" % (payload["verdict"], payload["completion_claim"]))
    counts = payload["counts"]
    print("检查项: %d 条 / 细分断言 %d 条" % (counts["total"], counts["assertions"]))
    status = counts["status"]
    print("三态: PASS=%d FAIL=%d NOT_RUN=%d CONFLICT=%d" % (
        status.get(PASS, 0), status.get(FAIL, 0),
        status.get(NOT_RUN, 0), status.get(CONFLICT, 0)))
    for item in payload["checks"]:
        print("  [%s] %s %s | %s" % (item["status"], item["id"], item["title"], item["detail"]))
    print("排除项: %d 条（U-06/U-08/U-09，不做断言）" % payload["excluded_count"])
    if payload["readonly_evidence"]["changed_during_audit"]:
        print("只读: 运行期变化 %s" % ", ".join(payload["readonly_evidence"]["changed_during_audit"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="A-33 对局美术渲染只读独立验收")
    parser.add_argument("--root", default=None, help="项目根目录（含 source/desktop/game）")
    parser.add_argument("--probe", default=None, help="探针 JSON 路径（默认为 qa/game_art_probe.json）")
    parser.add_argument("--human", action="store_true", help="人读摘要（默认输出机读 JSON）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else DEFAULT_PROJECT_ROOT
    if not (root / "source" / "desktop" / "game").exists():
        print("根目录不成立：%s" % root, file=sys.stderr)
        return 2

    ctx = Ctx(root, args.probe)
    probe = Probe(ctx)
    checks = []

    add_check(checks, "J0", "G5", "P0", *check_j0(ctx, probe))
    add_check(checks, "J1", "G5", "P0", *check_j1(ctx, probe))
    add_check(checks, "J2", "G5", "P0", *check_j2(ctx, probe))
    add_check(checks, "J3", "G5", "P0", *check_j3(ctx, probe))
    add_check(checks, "J4", "G5", "P0", *check_j4(ctx, probe))
    add_check(checks, "J5", "G5", "P0", *check_j5(ctx, probe))
    add_check(checks, "J6", "G5", "P0", *check_j6(ctx, probe))
    add_check(checks, "J7", "G5", "P1", *check_j7(ctx, probe))
    add_check(checks, "J8", "G5", "P1", *check_j8(ctx, probe))
    add_check(checks, "J9", "G5", "P1", *check_j9(ctx, probe))
    add_check(checks, "J10", "G5", "P1", *check_j10(ctx, probe))
    add_check(checks, "J11", "G5", "P1", *check_j11(ctx, probe))
    add_check(checks, "J12", "G5", "P1", *check_j12(ctx, probe))
    add_check(checks, "S1", "G5", "P1", *check_s1(ctx))
    add_check(checks, "S2", "G5", "P1", *check_s2(ctx))
    add_check(checks, "S3", "G5", "P1", *check_s3(ctx))

    changed = ctx.changed_inputs()
    if changed:
        # 验收期间输入被改写：任何 PASS 都不成立，统一降级为 NOT_RUN。
        for item in checks:
            if item["status"] == PASS:
                item["status"] = NOT_RUN
                item["detail"] = "验收期间输入变化（%s），原 PASS 不成立：%s" % (
                    ", ".join(changed[:3]), item["detail"])

    payload = build_payload(ctx, probe, checks, changed)
    if args.human:
        print_human(payload)
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - 旧解释器/被重定向时退回默认编码
            pass
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    if payload["verdict"] == PASS:
        return 0
    if payload["verdict"] == FAIL:
        return 1
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
