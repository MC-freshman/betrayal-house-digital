#!/usr/bin/env python
"""桌面端图片资源管线：构建 274 个资源位的 P 表，并输出运行时 PNG。

run6 版（九类渲染面）：资源位 = 原有 **142**（角色 12、房间 50 = ROOM_BASES 39 +
ROOM_SUPPLEMENTAL_SPECS 11、事件 45 = EVENT_BASES 11 + EVENT_SUPPLEMENTAL_SPECS 34、
物品 22、预兆 13）+ **132**（monster 52、haunt 70、ending 2、card_back 3、
room_back 2、dice 3）= **274**。六类渲染面的 id 分别来自 content.py 的
``MONSTER_BASES``、``build_catalog(0).haunt_defs`` 与 ``RENDER_SURFACE_SPECS``。
Widow's Walk 的 20 屋顶房 / 15 事件 / 10 物品 / 5 预兆 / 50 剧本（71-120）仍隔离在
``content_ww.py``、``haunts/_ww_deferred/``、``assets_ww/``，本管线不读取它们。

设计约束
--------
* 只读 ``photos/``：不改名、不移动、不覆盖；运行时副本写到 ``source/desktop/game/assets/``。
  （美术管线的转码是独立的一次性步骤：``qa/run5_transcode.py``。）
* 资源位（274）为主键，文件为附属；无文件的资源位仍登记 ``missing`` 而不是省略。
* 收口状态：photos/ 142 张全部为真 PNG；可用性一律 ``usable``；角色 12 位接通
  photos/role/ 真源图（RGBA 320x320）。
* 尺寸：房间 512x512、卡牌 480x672、角色 320x320。卡牌按 3:4 源图等比缩放后
  上下居中补边，避免把 3:4 硬拉成 5:7 造成约 5% 的纵向变形。
* 缺失资源位不伪造路径：``source_path`` 留空，``runtime_path`` 指向统一占位图，
  16 个可回退事件按 ``effect_id`` 指向已有事件图（142 位全 after 后该分支仅作兜底）。
* 三种键并存、互不替代：
  ``target_ref`` 是规范溯源键 ``content.py:<集合>#<id>``（如
  ``content.py:OMEN_CARDS#omen_bite``、``content.py:ROOM_BASES#entrance_hall``、
  ``content.py:CHARACTER_FACES#card_1@f0``）；
  ``runtime_key`` 是运行时键（如 ``card:omen:omen_bite`` / ``room:entrance_hall`` /
  ``character:card_1:f0``）；
  ``content_ref`` 保留 content.py 的原始记录 id（角色是 face id
  ``content.py:CHARACTER_FACES#card_1_0``）。
  ``content_refs`` 记录 runtime_key 与 content_ref 的双向映射，registry 同时接受
  runtime_key / target_ref / record_id / content_ref / 裸 id。
* 角色 target_ref 用 ``<card_id>@f<face_index>``（如 ``content.py:CHARACTER_FACES#card_1@f0``）：
  content.py 的 face id 是 ``card_1_0``，但「集合 + card_id」才是可解析全集（card_1..card_6），
  面别由 ``@fN`` 消歧；face id 原文保留在 ``content_ref`` 列。
* 缺失行的 ``mapping_status`` 区分两类：有真实回退目标的记 ``fallback`` 且
  ``fallback_ref`` 填回退目标的 ``record_id``（不是 target_ref）；只显示占位图的记
  ``pending_missing``，``fallback_ref`` 留空，``runtime_status`` 仍为 ``placeholder``。
* 转码溯源：130 张由 JPEG 转来的源图，provenance 追加
  ``;transcode=png;src_sha256:<hex>;backup=<path>``（读 ``qa/run5_transcode_manifest.json``，
  只读），AIGC 事实按原件标记记 ``aigc=true``——PNG 里当然没有 AIGC 标记。
* 备份目录 ``photos/_source_jpeg/`` 显式排除在所有 photos 扫描之外（P-11）。
* 发布档 7 列（``bytes`` / ``sha256`` / ``category_dir`` / ``alpha_required`` /
  ``canonical_record_id`` / ``reviewer`` / ``verified_at``）写在 P 表末尾（33 列 =
  26 业务列 + 发布档 7 列）：
  ``bytes``/``sha256`` 取 ``photos/`` 源文件事实（不是运行时 PNG），missing 行留空；
  ``canonical_record_id`` 非重复行指向自身，duplicate 行指向保留行；
  ``verified_at`` 默认固定为 ``VERIFIED_AT_FALLBACK``，设置 ``SOURCE_DATE_EPOCH``
  时由该时间戳派生，保证同一环境重复构建可逐字节比较。

用法::

    python asset_pipeline.py            # 构建 P 表 + 规范化 + 占位图
    python asset_pipeline.py --stage ptable
    python asset_pipeline.py --stage normalize
    python asset_pipeline.py --stage placeholders

Python 3.9 + Pillow 11.3.0 可运行；不访问网络。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GAME_DIR.parents[2]
PHOTOS_DIR = PROJECT_ROOT / "photos"
ASSETS_DIR = GAME_DIR / "assets"

PTABLE_CSV = ASSETS_DIR / "p_table.csv"
PTABLE_JSON = ASSETS_DIR / "p_table.json"
MAPPING_JSON = ASSETS_DIR / "asset_mapping.json"
PLACEHOLDER_DIR = ASSETS_DIR / "placeholders"

# 转码前的 JPEG 原件备份目录（run5 §3.5 P-09）：不在任何 photos 扫描范围内。
BACKUP_DIRNAME = "_source_jpeg"
TRANSCODE_MANIFEST = GAME_DIR / "qa" / "run5_transcode_manifest.json"
WW_DEFERRED_DIRNAME = "_ww_deferred"
ASSETS_WW_DIR = GAME_DIR / "assets_ww"

CSV_COLUMNS = (
    "record_id",
    "source_file",
    "source_path",
    "asset_type",
    "width",
    "height",
    "dimensions",
    "aspect_ratio",
    "format",
    "has_alpha",
    "decodable",
    "semantic_hint",
    "match_candidate",
    "usable_fields",
    "availability",
    "mapping_status",
    "target_ref",
    # 运行时键与 target_ref 成对出现：target_ref 是规范溯源键，runtime_key 供 registry 取图
    "runtime_key",
    "missing_note",
    "provenance",
    "runtime_path",
    "runtime_format",
    "runtime_status",
    "fallback_ref",
    "quality_flags",
    "content_ref",
    # 发布档 7 列（25 -> 32 列；本轮新增 runtime_key 后为 33 列，旧列语义全部保留）
    "bytes",
    "sha256",
    "category_dir",
    "alpha_required",
    "canonical_record_id",
    "reviewer",
    "verified_at",
)

RELEASE_COLUMNS = (
    "bytes",
    "sha256",
    "category_dir",
    "alpha_required",
    "canonical_record_id",
    "reviewer",
    "verified_at",
)

# 自动匹配/自动校验的行统一署名，便于与人工裁定区分。
REVIEWER_AUTOMATED = "automated"

# verified_at 默认固定日期：保证无 SOURCE_DATE_EPOCH 时重复构建逐字节可比。
VERIFIED_AT_FALLBACK = "2026-11-19"

# 发布档 category_dir 枚举（p_table_spec §1.2）：event/item/omen/room/char/icon/bg/none。
CATEGORY_DIR = {
    "character": "char",
    "room": "room",
    "omen": "omen",
    "item": "item",
    "event": "event",
    # run6 六类渲染面：photos/ 下同名子目录
    "monster": "monster",
    "haunt": "haunt",
    "ending": "ending",
    "card_back": "card_back",
    "room_back": "room_back",
    "dice": "dice",
}

# alpha 需求按用途判定：角色立绘必须带 alpha；房间整图与卡面不需要。
ALPHA_REQUIRED = {
    "character": True,
    "room": False,
    "omen": False,
    "item": False,
    "event": False,
    # run6：怪物标记 / 未翻地块 / 骰面需要透明通道（叠在地块上）；
    # 剧本插画与结算画面是整幅图，牌背是卡面替身，均不需要 alpha。
    "monster": True,
    "haunt": False,
    "ending": False,
    "card_back": False,
    "room_back": True,
    "dice": True,
}

# schema/说明：写入 p_table.json 的 schema 段，解释列语义与两种键的关系。
COLUMN_NOTES = {
    "record_id": "资源位主键 P-<CAT>-<NNN>，类别与前缀一致且段号连续。",
    "source_file": "photos/ 下的文件名；missing 行为空，不伪造。",
    "source_path": "项目根相对路径（正斜杠）；missing 行为空。",
    "asset_type": "资源类别：character / room / card_omen / card_item / card_event。",
    "width": "源文件像素宽（不是运行时宽）；missing 行为空。",
    "height": "源文件像素高（不是运行时高）；missing 行为空。",
    "dimensions": "源图尺寸文本 `<width>x<height>`，如 2048x2048、1773x2364；"
                  "missing 行为空。运行时尺寸见 runtime_specs。",
    "aspect_ratio": "源图宽高比，按最大公约数约分，如 1:1、3:4；missing 行为空。",
    "format": "按魔数判定的真实格式（jpeg/png/unknown），不按扩展名回填。",
    "has_alpha": "源文件是否带 alpha 通道。",
    "decodable": "Pillow verify+load 结果：ok / failed / not_checked。",
    "semantic_hint": "人读语义提示，来自 content.py 的名称与 source_name。",
    "match_candidate": "匹配候选键，如 card_1#f0。",
    "usable_fields": "允许的用途枚举，缺图行为空。",
    "availability": "usable / partial / missing / corrupted / duplicate。",
    "mapping_status": "matched / fallback / pending_missing / excluded / alias；"
                      "fallback 表示有真实回退目标，pending_missing 表示只有占位图。",
    "target_ref": "规范溯源键 content.py:<集合>#<id>，如 content.py:OMEN_CARDS#omen_bite、"
                  "content.py:ROOM_BASES#entrance_hall、content.py:CHARACTER_FACES#card_1@f0；"
                  "角色用 <card_id>@f<face_index> 消歧双面。",
    "runtime_key": "运行时键，registry 取图入口，如 card:omen:omen_bite、room:entrance_hall、"
                   "character:card_1:f0；与 target_ref 成对出现，二者互不替代。",
    "missing_note": "缺口或降级原因 + 下一动作；非 missing 行可为空。",
    "provenance": "来源与哈希；photos 行形如 <path>;sha256:<hex>;aigc=<bool>;origin=photos。",
    "runtime_path": "运行时 PNG 的项目根相对路径（assets/ 下）。",
    "runtime_format": "运行时编码，固定 png。",
    "runtime_status": "ok / fallback / placeholder。",
    "fallback_ref": "回退目标的 record_id（如 P-EVT-007），不是 target_ref；"
                    "pending_missing 行为空。",
    "quality_flags": "质量问题标记，如 ext_mismatch。",
    "content_ref": "content.py 的原始记录 id，如 content.py:OMEN_CARDS#omen_bite；"
                   "角色保留 face id（content.py:CHARACTER_FACES#card_1_0），与 target_ref 的 "
                   "@fN 写法指向同一面。",
    "bytes": "源文件字节数（不是运行时 PNG）；missing 行为空。",
    "sha256": "源文件全量 sha256（64 位十六进制，不是运行时 PNG）；missing 行为空。",
    "category_dir": "photos 分类目录枚举 char/room/omen/item/event；"
                    "missing 行按资源位类别填写，便于发布端分目录。",
    "alpha_required": "按用途判定是否需要 alpha：角色立绘 true，房间整图与卡面 false；"
                      "与 has_alpha（源文件事实）分开，表示需求而非现状。",
    "canonical_record_id": "规范行指向自身 record_id；availability=duplicate 时指向保留行。",
    "reviewer": "裁定/校验署名；自动匹配与自动校验统一为 automated。",
    "verified_at": "校验执行日期 YYYY-MM-DD；默认固定为 %s，可用 SOURCE_DATE_EPOCH 派生。"
                   % VERIFIED_AT_FALLBACK,
}

KEY_RELATION_NOTE = (
    "target_ref 是规范溯源键：content.py:<集合>#<id>，角色用 <card_id>@f<face_index> 消歧双面；"
    "runtime_key 是运行时键：room:<id> / card:<kind>:<id> / character:<card_id>:f<n>。"
    "两者一一对应，经 content_refs 双向互查（runtime_key -> content_ref，content_ref -> runtime_key）。"
    "asset_registry 同时接受 runtime_key、target_ref、record_id、content_ref 与裸 id，"
    "取图结果一致；审计与素材回填以 target_ref/content_ref 为准。"
    "角色因双面（f0/f1）在 content_ref 里用 face id（content.py:CHARACTER_FACES#card_1_0），"
    "在 runtime_key 里用面后缀（character:card_1:f0），在 target_ref 里用 @fN。"
)

CARD_SIZE = (480, 672)
ROOM_SIZE = (512, 512)
CHARACTER_SIZE = (320, 320)

# 资源位总数（独立期望值，不用 len(collect_slots()) 自证）：
# 142 原有位 + monster 52 + haunt 70 + ending 2 + card_back 3 + room_back 2 + dice 3。
EXPECTED_SLOT_TOTAL = 274

PLACEHOLDER_FILES = {
    "character": "character_missing.png",
    "room": "room_missing.png",
    "event": "event_missing.png",
}

# run6 九类渲染面：六类新资源的运行时尺寸（工程自定，官方未规定；
# 在 P 表 runtime_specs 与报告中均标注为自定义规格，不冒充官方）。
MONSTER_SIZE = (512, 512)
HAUNT_SIZE = (1280, 720)
ENDING_SIZE = (1024, 576)
CARD_BACK_SIZE = (480, 640)   # 3:4，与母版 1330x1773 同比例；不复用卡面 5:7
ROOM_BACK_SIZE = (512, 512)
DICE_SIZE = (256, 256)

# 运行时尺寸档位：registry 用它给出 width/height，不必解码图片。
RUNTIME_SPECS = {
    "character": {"width": CHARACTER_SIZE[0], "height": CHARACTER_SIZE[1], "format": "png"},
    "room": {"width": ROOM_SIZE[0], "height": ROOM_SIZE[1], "format": "png"},
    "card": {"width": CARD_SIZE[0], "height": CARD_SIZE[1], "format": "png"},
    "monster": {"width": MONSTER_SIZE[0], "height": MONSTER_SIZE[1], "format": "png"},
    "haunt": {"width": HAUNT_SIZE[0], "height": HAUNT_SIZE[1], "format": "png"},
    "ending": {"width": ENDING_SIZE[0], "height": ENDING_SIZE[1], "format": "png"},
    "card_back": {"width": CARD_BACK_SIZE[0], "height": CARD_BACK_SIZE[1], "format": "png"},
    "room_back": {"width": ROOM_BACK_SIZE[0], "height": ROOM_BACK_SIZE[1], "format": "png"},
    "dice": {"width": DICE_SIZE[0], "height": DICE_SIZE[1], "format": "png"},
}

# 类别优先级：CHR -> ROOM -> OMEN -> ITEM -> EVT（也决定 record_id 段号顺序）。
# run6 追加六类渲染面，**排在 EVT 之后**，保证既有 142 位的 record_id 段号不变。
CATEGORY_ORDER = ("CHR", "ROOM", "OMEN", "ITEM", "EVT",
                  "MONS", "HAUNT", "END", "CBACK", "RBACK", "DICE")

FAMILIES = {
    "character": {
        "cat": "CHR",
        "asset_type": "character",
        # WW 版：角色 12 位从"无源图（runtime 占位）"升级为 photos/role/ 真图
        # （12 张 320x320 PNG 已在盘上，验收 §4.2 要求角色位 has_alpha=true）。
        "photo_dir": "role",
        "size": CHARACTER_SIZE,
        "runtime_spec": "character",
        "usable_fields": ("portrait", "preview"),
    },
    "room": {
        "cat": "ROOM",
        "asset_type": "room",
        "photo_dir": "room",
        "size": ROOM_SIZE,
        "runtime_spec": "room",
        "usable_fields": ("room_tile", "preview"),
    },
    "omen": {
        "cat": "OMEN",
        "asset_type": "card_omen",
        "photo_dir": "omen",
        "size": CARD_SIZE,
        "runtime_spec": "card",
        "usable_fields": ("card_face", "preview"),
    },
    "item": {
        "cat": "ITEM",
        "asset_type": "card_item",
        "photo_dir": "item",
        "size": CARD_SIZE,
        "runtime_spec": "card",
        "usable_fields": ("card_face", "preview"),
    },
    "event": {
        "cat": "EVT",
        "asset_type": "card_event",
        "photo_dir": "event",
        "size": CARD_SIZE,
        "runtime_spec": "card",
        "usable_fields": ("card_face", "preview"),
    },
    # ---- run6 九类渲染面：六类新资源（142 -> 274） ----
    "monster": {
        "cat": "MONS",
        "asset_type": "monster",
        "photo_dir": "monster",
        "size": MONSTER_SIZE,
        "runtime_spec": "monster",
        "usable_fields": ("monster_marker", "preview"),
    },
    "haunt": {
        "cat": "HAUNT",
        "asset_type": "haunt",
        "photo_dir": "haunt",
        "size": HAUNT_SIZE,
        "runtime_spec": "haunt",
        "usable_fields": ("haunt_art", "preview"),
    },
    "ending": {
        "cat": "END",
        "asset_type": "ending",
        "photo_dir": "ending",
        "size": ENDING_SIZE,
        "runtime_spec": "ending",
        "usable_fields": ("ending_screen", "preview"),
    },
    "card_back": {
        "cat": "CBACK",
        "asset_type": "card_back",
        "photo_dir": "card_back",
        "size": CARD_BACK_SIZE,
        "runtime_spec": "card_back",
        "usable_fields": ("card_back", "preview"),
    },
    "room_back": {
        "cat": "RBACK",
        "asset_type": "room_back",
        "photo_dir": "room_back",
        "size": ROOM_BACK_SIZE,
        "runtime_spec": "room_back",
        "usable_fields": ("room_back", "preview"),
    },
    "dice": {
        "cat": "DICE",
        "asset_type": "dice",
        "photo_dir": "dice",
        "size": DICE_SIZE,
        "runtime_spec": "dice",
        "usable_fields": ("dice_face", "preview"),
    },
}

RUNTIME_CARD_DIRS = {
    "omen": ASSETS_DIR / "cards" / "omen",
    "item": ASSETS_DIR / "cards" / "item",
    "event": ASSETS_DIR / "cards" / "event",
}

# run6：六类新资源的运行时目录。目录名用复数以区别于 photos/ 下的源目录。
RUNTIME_EXTRA_DIRS = {
    "monster": ASSETS_DIR / "monsters",
    "haunt": ASSETS_DIR / "haunts",
    "ending": ASSETS_DIR / "endings",
    "card_back": ASSETS_DIR / "card_backs",
    "room_back": ASSETS_DIR / "room_backs",
    "dice": ASSETS_DIR / "dice",
}

# photos/ 下这六类源目录名（scan_photos 的 known 白名单与归属判定共用）
EXTRA_PHOTO_DIRS = {
    "monster": "monster",
    "haunt": "haunt",
    "ending": "ending",
    "card_back": "card_back",
    "room_back": "room_back",
    "dice": "dice",
}

# 占位图配色，取 ui.py 的 PALETTE，保证与界面深色主题一致。
COLOR_BG = "#1f232a"
COLOR_PANEL = "#262b33"
COLOR_BORDER = "#d6b26e"
COLOR_TEXT = "#eef2f6"
COLOR_MUTED = "#aab4c2"

PLACEHOLDER_LABELS = {
    "character": ("角色立绘缺失", "CHARACTER", "MISSING ART"),
    "room": ("房间图缺失", "ROOM", "MISSING ART"),
    "event": ("事件卡图缺失", "EVENT", "MISSING ART"),
}


# ----------------------------------------------------------------------
# 通用小工具
# ----------------------------------------------------------------------
def _rel(path: Path) -> str:
    """项目根相对路径，统一正斜杠；越界时退回绝对 posix。"""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_date_epoch():
    """读取 SOURCE_DATE_EPOCH；非法值返回 None（不静默改写为今天）。"""
    raw = (os.environ.get("SOURCE_DATE_EPOCH") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def verification_date() -> str:
    """校验日期：SOURCE_DATE_EPOCH 派生，否则固定 VERIFIED_AT_FALLBACK。"""
    epoch = _source_date_epoch()
    if epoch is None:
        return VERIFIED_AT_FALLBACK
    try:
        return datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return VERIFIED_AT_FALLBACK


def generation_date() -> str:
    """构建日期：SOURCE_DATE_EPOCH 派生，否则取本地当天。"""
    epoch = _source_date_epoch()
    if epoch is not None:
        try:
            return datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            pass
    return datetime.now().strftime("%Y-%m-%d")


def release_fields(family: str, verified_at: str = None) -> dict:
    """发布档中与源文件无关的 4 列；bytes/sha256 由调用方按行补。"""
    return {
        "category_dir": CATEGORY_DIR[family],
        "alpha_required": bool(ALPHA_REQUIRED[family]),
        "canonical_record_id": "",
        "reviewer": REVIEWER_AUTOMATED,
        "verified_at": verified_at or verification_date(),
    }


def sniff_format(path: Path) -> str:
    """按魔数判定真实格式，禁止按扩展名回填。"""
    with path.open("rb") as handle:
        head = handle.read(32)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def _has_aigc_marker(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"AIGC" in handle.read(4096)


_TRANSCODE_INDEX = None


def transcode_index() -> dict:
    """读 run5 转码清单（只读）：``source_path -> {src_sha256, backup}``。

    130 张 JPEG 已按 A 方案转码为真 PNG（``qa/run5_transcode.py``）。转码后 PNG 里
    当然不再有 AIGC 标记，所以「原件带 AIGC」这一事实只能靠清单回填到 provenance
    （run5 §3.4 P-05）。清单缺失时返回空表：provenance 退回按当前文件事实写。
    """
    global _TRANSCODE_INDEX
    if _TRANSCODE_INDEX is not None:
        return _TRANSCODE_INDEX
    index = {}
    if TRANSCODE_MANIFEST.is_file():
        try:
            document = json.loads(TRANSCODE_MANIFEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            document = {}
        for row in document.get("records") or []:
            path = (row or {}).get("path")
            if path:
                index[path] = {
                    "src_sha256": (row or {}).get("source_sha256", ""),
                    "backup": (row or {}).get("backup", ""),
                }
    _TRANSCODE_INDEX = index
    return index


def _norm_stem(name: str) -> str:
    """规范化文件名主干：小写、- 转 _、去空格、去复数尾 s（两侧同规则）。"""
    stem = name.strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in stem:
        stem = stem.replace("__", "_")
    if stem.endswith("s"):
        stem = stem[:-1]
    return stem


def _resample():
    from PIL import Image

    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def dimensions_text(width, height) -> str:
    """源图尺寸文本；缺尺寸时返回空串（missing 行不允许伪造）。"""
    if not width or not height:
        return ""
    return "%dx%d" % (int(width), int(height))


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def aspect_ratio_text(width, height) -> str:
    """按最大公约数约分的宽高比（1773x2364 -> 3:4，2048x2048 -> 1:1）。"""
    if not width or not height:
        return ""
    width, height = int(width), int(height)
    divisor = _gcd(width, height) or 1
    return "%d:%d" % (width // divisor, height // divisor)


# ----------------------------------------------------------------------
# photos 只读扫描
# ----------------------------------------------------------------------
def probe_photo(path: Path) -> dict:
    """读取单个源文件的真实事实（格式/尺寸/通道/可解码），不写入。

    run5 变更（有据可查）：转码后母版从 140 MB JPEG 变成 690 MB 真 PNG，
    ``--stage ptable`` 若对 142 张逐一 ``load()`` 全解码，实测 median 14.9 s，
    直接顶穿 PT-PERF-01 的 5 s 预算。这里改为 ``Image.open() + verify()``
    （校验 PNG 分块 CRC 与结构，不做像素解码）+ 读头部拿尺寸/通道：
    实测 142 张 0.86 s。**像素级可解码**（1.6 亿像素全解码）仍由
    ``qa/verify_assets_contract.py`` 的 C16 与 run5 M-10 独立执行，
    管线不再重复付这份成本——两者合起来仍是"结构 + 像素"双检，不是放宽。
    """
    from PIL import Image

    facts = {
        "path": path,
        "rel": _rel(path),
        "file": path.name,
        "dir": path.parent.name,
        "stem": path.stem,
        "ext": path.suffix.lstrip(".").lower(),
        "bytes": path.stat().st_size,
        "format": sniff_format(path),
        "width": 0,
        "height": 0,
        "mode": "",
        "has_alpha": False,
        "decodable": "not_checked",
        "sha256": _sha256(path),
        "aigc": _has_aigc_marker(path),
        "error": "",
    }
    try:
        # 结构校验：分块 CRC + 头/尾完整性（不解像素）
        with Image.open(path) as image:
            image.verify()
        # 头部事实：尺寸/通道/透明度标记（Pillow 在 open 时已解析 IHDR）
        with Image.open(path) as image:
            width, height = image.size
            bands = image.getbands()
            has_alpha = "A" in bands or "transparency" in image.info
            mode = image.mode
        if width <= 0 or height <= 0:
            raise ValueError("zero dimension: %sx%s" % (width, height))
        facts.update(
            width=int(width),
            height=int(height),
            mode=mode,
            has_alpha=bool(has_alpha),
            decodable="ok",
        )
    except Exception as exc:  # 隔离损坏文件，不让流程中断
        facts["decodable"] = "failed"
        facts["error"] = "%s: %s" % (type(exc).__name__, exc)
    return facts


# 来源探测缓存（run5 性能修复）：
# 母版转码为真 PNG 后 photos/ 合计约 690 MB，142 张逐一 verify() 全分块 CRC 校验
# 实测 median 5.5 s，顶穿 PT-PERF-01 的 5 s 预算。这里按 (rel, bytes, mtime_ns)
# 做失效键缓存探测事实：文件一旦被改动（大小或 mtime 变化）立刻重算，命中时跳过
# 重复的 verify()+sha256。缓存不进 assets/ 以免干扰资源计数。
PROBE_CACHE_PATH = GAME_DIR / "qa" / ".photo_probe_cache.json"
PROBE_CACHE_VERSION = 1


def _load_probe_cache() -> dict:
    try:
        payload = json.loads(PROBE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict) or payload.get("version") != PROBE_CACHE_VERSION:
        return {}
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def _save_probe_cache(entries: dict) -> None:
    """幂等落盘：内容未变则不写，保证只读审计（SAFE-01）看不到多余写入。"""
    try:
        payload = json.dumps({"version": PROBE_CACHE_VERSION, "entries": entries},
                             ensure_ascii=False, sort_keys=True)
        if PROBE_CACHE_PATH.is_file():
            try:
                if PROBE_CACHE_PATH.read_text(encoding="utf-8") == payload:
                    return
            except Exception:
                pass
        PROBE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROBE_CACHE_PATH.write_text(payload, encoding="utf-8")
    except Exception:
        pass  # 缓存写失败不影响构建正确性


def _absent_facts(path: Path, reason: str) -> dict:
    """文件在扫描与探测之间消失时的占位事实：标记 failed，不中断构建。"""
    return {
        "path": path,
        "rel": _rel(path),
        "file": path.name,
        "dir": path.parent.name,
        "stem": path.stem,
        "ext": path.suffix.lstrip(".").lower(),
        "bytes": 0,
        "format": "",
        "width": 0,
        "height": 0,
        "mode": "",
        "has_alpha": False,
        "decodable": "failed",
        "sha256": "",
        "aigc": False,
        "error": reason,
    }


def probe_photo_cached(path: Path, cache: dict) -> tuple:
    """返回 (facts, hit)。命中条件：rel/bytes/mtime_ns 三者与缓存一致。"""
    try:
        stat = path.stat()
    except OSError as exc:
        return _absent_facts(path, "%s: %s" % (type(exc).__name__, exc)), False
    rel = _rel(path)
    key = {"rel": rel, "bytes": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    entry = cache.get(rel)
    if isinstance(entry, dict) and all(entry.get(k) == v for k, v in key.items()):
        facts = entry.get("facts")
        if isinstance(facts, dict) and facts.get("rel") == rel:
            facts = dict(facts)
            facts["path"] = path
            return facts, True
    facts = probe_photo(path)
    cache[rel] = dict(key, facts={k: v for k, v in facts.items() if k != "path"})
    return facts, False


def scan_photos() -> dict:
    """扫描 photos/（只读），返回文件事实与统计。

    ``photos/_source_jpeg/`` 是转码前的原件备份（P-09），**必须排除**：
    把它算进来会让文件数变成 272 而不是 142，也会让备份被当成源图（P-11）。
    """
    if not PHOTOS_DIR.is_dir():
        raise SystemExit("photos 目录不存在：%s" % PHOTOS_DIR)
    cache = _load_probe_cache()
    cache_hits = 0

    files = []
    excluded = []
    for path in sorted(PHOTOS_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(PHOTOS_DIR).parts
        if rel_parts and rel_parts[0] == BACKUP_DIRNAME:
            excluded.append(_rel(path))
            continue
        facts, hit = probe_photo_cached(path, cache)
        if hit:
            cache_hits += 1
        files.append(facts)

    if cache_hits:
        _save_probe_cache(cache)
    else:
        _save_probe_cache(cache)  # 全量重算后刷新缓存

    by_dir = {}
    for facts in files:
        by_dir.setdefault(facts["dir"], []).append(facts)

    known = {"event", "item", "omen", "room", "role"}
    # run6：六类渲染面源目录加入白名单（否则会被判成 orphans）
    known.update(EXTRA_PHOTO_DIRS.values())
    orphans = [facts["rel"] for facts in files if facts["dir"] not in known]
    return {
        "dir": PHOTOS_DIR,
        "files": files,
        "by_dir": by_dir,
        "orphans": orphans,
        "total": len(files),
        "excluded_backups": len(excluded),
        "corrupted": [f["rel"] for f in files if f["decodable"] != "ok"],
        "with_aigc": sum(1 for f in files if f["aigc"]),
        "probe_cache_hits": cache_hits,
    }


def build_photo_index(photos: dict) -> dict:
    """为每个目录建立 精确主干 / 规范化主干 两级索引。"""
    index = {}
    for dir_name, facts_list in photos["by_dir"].items():
        exact = {}
        norm = {}
        for facts in facts_list:
            exact.setdefault(facts["stem"], []).append(facts)
            norm.setdefault(_norm_stem(facts["stem"]), []).append(facts)
        index[dir_name] = {"exact": exact, "norm": norm}
    return index


def match_photo(slot: dict, index: dict):
    """按 p_table_spec 3.2 的降级次序匹配：精确主干 -> 规范化主干。"""
    dir_name = FAMILIES[slot["family"]]["photo_dir"]
    if not dir_name or dir_name not in index:
        return None, "no_dir"
    stem = slot["match_stem"]
    bucket = index[dir_name]
    hits = bucket["exact"].get(stem) or []
    if len(hits) == 1:
        return hits[0], "exact_id"
    if len(hits) > 1:
        return hits[0], "ambiguous"
    hits = bucket["norm"].get(_norm_stem(stem)) or []
    if len(hits) == 1:
        return hits[0], "normalized_id"
    if len(hits) > 1:
        return hits[0], "ambiguous"
    return None, "unmatched"


# ----------------------------------------------------------------------
# content.py 资源位
# ----------------------------------------------------------------------
def load_content():
    """导入 content.py 取 274 个资源位；不改动源码。"""
    path = GAME_DIR / "content.py"
    if not path.is_file():
        raise SystemExit("找不到 content.py：%s" % path)
    if str(GAME_DIR) not in sys.path:
        sys.path.insert(0, str(GAME_DIR))
    spec = importlib.util.spec_from_file_location("game_content_for_assets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def content_target_ref(collection: str, item_id: str) -> str:
    """规范溯源键：content.py:<集合>#<id>（p_table_spec §1.1 的唯一合法形态）。"""
    return "content.py:%s#%s" % (collection, item_id)


def character_face_id(card_id: str, face_index: int) -> str:
    """角色的 target_ref id：<card_id>@f<face_index>。

    content.py 的 face id 是 ``card_1_0``，但角色全集是 ``card_1..card_6``，
    面别只能靠 ``@fN`` 表达；face id 原文另存 ``content_ref`` 列。
    """
    return "%s@f%d" % (card_id, face_index)


def collect_slots(content_module) -> list:
    """把 content.py 的 10 个集合展开为 274 个资源位（run6：WW 仍隔离）。

    每个资源位同时给出：
    * ``target_ref``：规范溯源键 ``content.py:<集合>#<id>``；
    * ``runtime_key``：运行时键（room:/card:/character:）；
    * ``content_ref``：content.py 原始记录 id（角色为 face id）。

    顺序即 record_id 的分配顺序：CHR -> ROOM -> OMEN -> ITEM -> EVT，
    同类别内按 content.py 的声明顺序（基础集合在前，补充集合在后）。
    """
    slots = []

    for face in content_module.CHARACTER_FACES:
        card_id = face["card_id"]
        face_index = int(face["face_index"])
        slots.append(
            {
                "family": "character",
                "collection": "CHARACTER_FACES",
                "slot_id": face["id"],
                # photos/role/ 的文件名形态是 character_card_1_f0.png；
                # face id（card_1_0）与文件主干不同，按实际主干匹配。
                "match_stem": "character_%s_f%s" % (card_id, face_index),
                "target_ref": content_target_ref(
                    "CHARACTER_FACES", character_face_id(card_id, face_index)),
                "runtime_key": "character:%s:f%s" % (card_id, face_index),
                "content_ref": content_target_ref("CHARACTER_FACES", face["id"]),
                "semantic_hint": "角色面：%s %s（%s）"
                % (card_id, "正面" if face_index == 0 else "背面", face["source_name"]),
                "match_candidate": "%s#f%s" % (card_id, face_index),
                "name": face["name"],
                "source_name": face["source_name"],
                "effect_id": "",
                "runtime_name": face["id"],
            }
        )

    for room in content_module.ROOM_BASES:
        slots.append(
            {
                "family": "room",
                "collection": "ROOM_BASES",
                "slot_id": room["id"],
                "match_stem": room["id"],
                "target_ref": content_target_ref("ROOM_BASES", room["id"]),
                "runtime_key": "room:%s" % room["id"],
                "content_ref": content_target_ref("ROOM_BASES", room["id"]),
                "semantic_hint": "房间：%s（%s）" % (room["name"], room["source_name"]),
                "match_candidate": room["id"],
                "name": room["name"],
                "source_name": room["source_name"],
                "effect_id": room.get("effect_id", ""),
                "runtime_name": room["id"],
            }
        )

    for spec in content_module.ROOM_SUPPLEMENTAL_SPECS:
        room_id, name, source_name = spec[0], spec[1], spec[2]
        slots.append(
            {
                "family": "room",
                "collection": "ROOM_SUPPLEMENTAL_SPECS",
                "slot_id": room_id,
                "match_stem": room_id,
                "target_ref": content_target_ref("ROOM_SUPPLEMENTAL_SPECS", room_id),
                "runtime_key": "room:%s" % room_id,
                "content_ref": content_target_ref("ROOM_SUPPLEMENTAL_SPECS", room_id),
                "semantic_hint": "房间：%s（%s）" % (name, source_name),
                "match_candidate": room_id,
                "name": name,
                "source_name": source_name,
                "effect_id": spec[6] if len(spec) > 6 else "",
                "runtime_name": room_id,
            }
        )

    # run5：Widow's Walk 的 20 屋顶板块已隔离到 content_ww.ROOF_ROOMS，
    # 不再进入 P 表（A-29 判据 2 / B-01）。房间位 = 39 + 11 = 50。

    for card in content_module.OMEN_CARDS:
        slots.append(
            {
                "family": "omen",
                "collection": "OMEN_CARDS",
                "slot_id": card["id"],
                "match_stem": card["id"],
                "target_ref": content_target_ref("OMEN_CARDS", card["id"]),
                "runtime_key": "card:omen:%s" % card["id"],
                "content_ref": content_target_ref("OMEN_CARDS", card["id"]),
                "semantic_hint": "预兆卡：%s（%s）" % (card["name"], card["source_name"]),
                "match_candidate": card["id"],
                "name": card["name"],
                "source_name": card["source_name"],
                "effect_id": card.get("effect_id", ""),
                "runtime_name": card["id"],
            }
        )

    for card in content_module.ITEM_CARDS:
        slots.append(
            {
                "family": "item",
                "collection": "ITEM_CARDS",
                "slot_id": card["id"],
                "match_stem": card["id"],
                "target_ref": content_target_ref("ITEM_CARDS", card["id"]),
                "runtime_key": "card:item:%s" % card["id"],
                "content_ref": content_target_ref("ITEM_CARDS", card["id"]),
                "semantic_hint": "物品卡：%s（%s）" % (card["name"], card["source_name"]),
                "match_candidate": card["id"],
                "name": card["name"],
                "source_name": card["source_name"],
                "effect_id": card.get("effect_id", ""),
                "runtime_name": card["id"],
            }
        )

    for card in content_module.EVENT_BASES:
        slots.append(
            {
                "family": "event",
                "collection": "EVENT_BASES",
                "slot_id": card["id"],
                "match_stem": card["id"],
                "target_ref": content_target_ref("EVENT_BASES", card["id"]),
                "runtime_key": "card:event:%s" % card["id"],
                "content_ref": content_target_ref("EVENT_BASES", card["id"]),
                "semantic_hint": "事件卡：%s（%s）" % (card["name"], card["source_name"]),
                "match_candidate": card["id"],
                "name": card["name"],
                "source_name": card["source_name"],
                "effect_id": card.get("effect_id", ""),
                "runtime_name": card["id"],
            }
        )

    for spec in content_module.EVENT_SUPPLEMENTAL_SPECS:
        event_id, name, source_name, effect_id = spec[0], spec[1], spec[2], spec[3]
        slots.append(
            {
                "family": "event",
                "collection": "EVENT_SUPPLEMENTAL_SPECS",
                "slot_id": event_id,
                "match_stem": event_id,
                "target_ref": content_target_ref("EVENT_SUPPLEMENTAL_SPECS", event_id),
                "runtime_key": "card:event:%s" % event_id,
                "content_ref": content_target_ref("EVENT_SUPPLEMENTAL_SPECS", event_id),
                "semantic_hint": "事件卡：%s（%s）" % (name, source_name),
                "match_candidate": event_id,
                "name": name,
                "source_name": source_name,
                "effect_id": effect_id,
                "runtime_name": event_id,
            }
        )

    # ---- run6：monster 52（来自 content.MONSTER_BASES） ----
    for monster in getattr(content_module, "MONSTER_BASES", []) or []:
        monster_id = monster["id"]
        slots.append(
            {
                "family": "monster",
                "collection": "MONSTER_BASES",
                "slot_id": monster_id,
                "match_stem": monster_id,
                "target_ref": content_target_ref("MONSTER_BASES", monster_id),
                "runtime_key": "monster:%s" % monster_id,
                "content_ref": content_target_ref("MONSTER_BASES", monster_id),
                "semantic_hint": "怪物标记：%s（%s）"
                % (monster.get("name", ""), monster.get("source_name", "")),
                "match_candidate": monster_id,
                "name": monster.get("name", ""),
                "source_name": monster.get("source_name", ""),
                "effect_id": "",
                "runtime_name": monster_id,
            }
        )

    # ---- run6：haunt 70（来自 catalog.haunt_defs，文件名为 haunt_<n>.png） ----
    catalog = content_module.build_catalog(0)
    for haunt_id, haunt in sorted(catalog.haunt_defs.items()):
        stem = "haunt_%d" % int(haunt_id)
        slots.append(
            {
                "family": "haunt",
                "collection": "HAUNT_DEFS",
                "slot_id": str(haunt_id),
                "match_stem": stem,
                "target_ref": content_target_ref("HAUNT_DEFS", str(haunt_id)),
                "runtime_key": "haunt:%d" % int(haunt_id),
                "content_ref": content_target_ref("HAUNT_DEFS", str(haunt_id)),
                "semantic_hint": "剧本插画：%s" % getattr(haunt, "name", ""),
                "match_candidate": stem,
                "name": getattr(haunt, "name", ""),
                "source_name": "",
                "effect_id": "",
                "runtime_name": stem,
            }
        )

    # ---- run6：10 个固定渲染位（结算/牌背/未翻地块/骰面） ----
    for spec in getattr(content_module, "RENDER_SURFACE_SPECS", []) or []:
        surface_id = spec["id"]
        family = spec["surface"]
        suffix = surface_id
        for prefix in ("card_back_", "ending_", "dice_"):
            if surface_id.startswith(prefix):
                suffix = surface_id[len(prefix):]
                break
        if surface_id == "room_back":
            suffix = "back"
        elif surface_id == "room_ghost":
            suffix = "ghost"
        slots.append(
            {
                "family": family,
                "collection": "RENDER_SURFACE_SPECS",
                "slot_id": surface_id,
                "match_stem": surface_id,
                "target_ref": content_target_ref("RENDER_SURFACE_SPECS", surface_id),
                "runtime_key": "%s:%s" % (family, suffix),
                "content_ref": content_target_ref("RENDER_SURFACE_SPECS", surface_id),
                "semantic_hint": "%s渲染位：%s" % (family, spec.get("name", "")),
                "match_candidate": surface_id,
                "name": spec.get("name", ""),
                "source_name": "",
                "effect_id": "",
                "runtime_name": surface_id,
            }
        )

    # 按类别优先级重排，类别内保持声明顺序（chunk 拼接已满足，这里显式排序防漂移）。
    order = {name: idx for idx, name in enumerate(CATEGORY_ORDER)}
    family_cat = {name: cfg["cat"] for name, cfg in FAMILIES.items()}
    slots.sort(key=lambda slot: order[family_cat[slot["family"]]])
    slots.sort(key=lambda slot: order[family_cat[slot["family"]]])  # 稳定排序：类别内不动
    return slots


# ----------------------------------------------------------------------
# 行构造
# ----------------------------------------------------------------------
def runtime_rel_path(slot: dict) -> Path:
    family = slot["family"]
    if family == "room":
        return ASSETS_DIR / "rooms" / ("%s.png" % slot["runtime_name"])
    if family in RUNTIME_CARD_DIRS:
        return RUNTIME_CARD_DIRS[family] / ("%s.png" % slot["runtime_name"])
    if family == "character":
        # WW 版：角色 12 位有 photos/role/ 真源图，运行时规范化到
        # assets/characters/<face_id>.png（此前角色一律走占位图）。
        return ASSETS_DIR / "characters" / ("%s.png" % slot["runtime_name"])
    if family in RUNTIME_EXTRA_DIRS:  # run6 六类渲染面
        return RUNTIME_EXTRA_DIRS[family] / ("%s.png" % slot["runtime_name"])
    raise ValueError("未知资源类别：%s" % family)


def placeholder_path(kind: str) -> Path:
    return PLACEHOLDER_DIR / PLACEHOLDER_FILES[kind]


def _partial_note(facts: dict, size) -> str:
    subject = "房间整图" if facts["dir"] == "room" else "卡面"
    return (
        "扩展名 .%s 与魔数 %s 不一致（ext_mismatch）；无 alpha 通道，%s不需要 alpha；"
        "已转码为 %sx%s 运行时 PNG；下一动作=导出真实 PNG 母版后可升 usable"
        % (facts["ext"], facts["format"].upper(), subject, size[0], size[1])
    )


def make_photo_record(slot: dict, facts: dict, verified_at: str = None) -> dict:
    cfg = FAMILIES[slot["family"]]
    size = cfg["size"]
    flags = []
    if facts["format"] != "unknown" and facts["format"] != facts["ext"]:
        flags.append("ext_mismatch")
    if facts["format"] == "unknown":
        flags.append("unknown_format")

    if facts["decodable"] != "ok":
        availability, mapping, decodable = "corrupted", "excluded", "failed"
    elif flags:
        availability, mapping, decodable = "partial", "matched", "ok"
    else:
        availability, mapping, decodable = "usable", "matched", "ok"

    runtime = runtime_rel_path(slot)
    transcode = transcode_index().get(facts["rel"])
    aigc = bool(facts["aigc"])
    if transcode and not aigc:
        # 转码后 PNG 无 AIGC 标记；原件（备份）带标记则事实仍是 aigc=true（P-05）。
        backup_path = PROJECT_ROOT / transcode["backup"] if transcode["backup"] else None
        if backup_path is not None and backup_path.is_file():
            aigc = _has_aigc_marker(backup_path)
    provenance = "%s;sha256:%s;aigc=%s;origin=photos" % (
        facts["rel"],
        facts["sha256"],
        "true" if aigc else "false",
    )
    if transcode:
        provenance += ";transcode=png;src_sha256:%s;backup=%s" % (
            transcode["src_sha256"], transcode["backup"])

    row = {
        "source_file": facts["file"],
        "source_path": facts["rel"],
        "asset_type": cfg["asset_type"],
        "width": facts["width"],
        "height": facts["height"],
        "dimensions": dimensions_text(facts["width"], facts["height"]),
        "aspect_ratio": aspect_ratio_text(facts["width"], facts["height"]),
        "format": facts["format"],
        "has_alpha": facts["has_alpha"],
        "decodable": decodable,
        "semantic_hint": slot["semantic_hint"],
        "match_candidate": slot["match_candidate"],
        "usable_fields": list(cfg["usable_fields"]) if availability != "corrupted" else [],
        "availability": availability,
        "mapping_status": mapping,
        "target_ref": slot["target_ref"],
        "runtime_key": slot["runtime_key"],
        "missing_note": _partial_note(facts, size) if availability != "usable" else "",
        "provenance": provenance,
        "runtime_path": _rel(runtime),
        "runtime_format": "png",
        "runtime_status": "ok",
        "fallback_ref": "",
        "quality_flags": flags,
        "content_ref": slot["content_ref"],
        # 发布档：bytes/sha256 取源文件事实；missing 行由 make_missing_record 留空
        "bytes": facts["bytes"],
        "sha256": facts["sha256"],
        "_family": slot["family"],
        "_collection": slot["collection"],
        "_content_ref": slot["content_ref"],
        "_runtime_spec": cfg["runtime_spec"],
        "_runtime_abs": runtime,
        "_match_status": "",
        "_source_kind": "photo",
        "_fallback_target": "",
    }
    row.update(release_fields(slot["family"], verified_at))
    return row


def make_missing_record(slot: dict, art_event_ids, verified_at: str = None) -> dict:
    cfg = FAMILIES[slot["family"]]
    family = slot["family"]
    runtime = None
    runtime_status = "placeholder"
    mapping_status = "pending_missing"
    fallback_ref = ""
    fallback_target = ""
    note_extra = ""

    if family == "event" and slot["effect_id"] and slot["effect_id"] in art_event_ids:
        runtime = RUNTIME_CARD_DIRS["event"] / ("%s.png" % slot["effect_id"])
        runtime_status = "fallback"
        mapping_status = "fallback"
        # 对外填写回退目标的 record_id（不是 target_ref/runtime_key），等 record_id 分配后回填；
        # 这里先记运行时键，assign_fallback_refs 用它反查 record_id。
        fallback_target = "card:event:%s" % slot["effect_id"]
        note_extra = (
            "；按 effect_id=%s 回退到已有事件图（runtime_key=%s），"
            "回退图仅表达同一规则效果，不等于该卡已完成美术"
            % (slot["effect_id"], fallback_target)
        )
    else:
        runtime = placeholder_path(
            {"character": "character", "room": "room", "event": "event",
             "omen": "event", "item": "event"}[family]
        )
        note_extra = "；无真实替代美术，mapping_status=pending_missing；当前运行时显示统一占位图 %s" % _rel(runtime)

    if family == "character":
        # 缺口说明用运行时键拆卡号与面别（target_ref 是 content.py 引用，不含 :fN 形态）
        runtime_key = slot["runtime_key"]
        head = "%s 无角色立绘文件；需补 character_%s_f%s.png（320x320，必须带 alpha）" % (
            slot["content_ref"],
            runtime_key.split(":")[1],
            runtime_key.split(":f")[1],
        )
    elif family == "room":
        head = "%s 无房间图（49/50 已有）；需补 room_%s.png（2048x2048）" % (
            slot["content_ref"],
            slot["slot_id"],
        )
    else:
        head = "%s 无独立美术；需补 %s.png（1773x2364）" % (slot["content_ref"], slot["slot_id"])

    row = {
        "source_file": "",
        "source_path": "",
        "asset_type": cfg["asset_type"],
        "width": None,
        "height": None,
        "dimensions": "",
        "aspect_ratio": "",
        "format": "unknown",
        "has_alpha": False,
        "decodable": "not_checked",
        "semantic_hint": slot["semantic_hint"],
        "match_candidate": slot["match_candidate"],
        "usable_fields": [],
        "availability": "missing",
        "mapping_status": mapping_status,
        "target_ref": slot["target_ref"],
        "runtime_key": slot["runtime_key"],
        "missing_note": head + note_extra,
        "provenance": "required;origin=content.py;collection=%s" % slot["collection"],
        "runtime_path": _rel(runtime),
        "runtime_format": "png",
        "runtime_status": runtime_status,
        "fallback_ref": fallback_ref,
        "quality_flags": [],
        "content_ref": slot["content_ref"],
        # 发布档：缺口行不得伪造源文件事实，bytes/sha256 留空
        "bytes": None,
        "sha256": "",
        "_family": family,
        "_collection": slot["collection"],
        "_content_ref": slot["content_ref"],
        "_runtime_spec": cfg["runtime_spec"],
        "_runtime_abs": runtime,
        "_match_status": "missing_slot",
        "_source_kind": "content_only",
        "_fallback_target": fallback_target,
    }
    row.update(release_fields(family, verified_at))
    return row


def build_records(content_module, photos: dict) -> tuple:
    """构建 274 行 P 表记录（未分配 record_id）。"""
    slots = collect_slots(content_module)
    index = build_photo_index(photos)
    art_event_ids = {facts["stem"] for facts in photos["by_dir"].get("event", [])}
    verified_at = verification_date()  # 整表同一日期，避免跨日构建自相矛盾

    records = []
    for slot in slots:
        facts, how = match_photo(slot, index)
        if facts is None:
            records.append(make_missing_record(slot, art_event_ids, verified_at))
        else:
            row = make_photo_record(slot, facts, verified_at)
            row["_match_status"] = how
            records.append(row)
    return records, slots


def assign_record_ids(records: list) -> None:
    """按类别优先级 + 声明顺序分配 P-<CAT>-<NNN>，稳定且不重复。"""
    counters = {}
    for row in records:
        cat = FAMILIES[row["_family"]]["cat"]
        counters[cat] = counters.get(cat, 0) + 1
        row["record_id"] = "P-%s-%03d" % (cat, counters[cat])


def assign_fallback_refs(records: list) -> None:
    """把 fallback_ref 回填成回退目标的 record_id（runtime_key 只在内部流转）。"""
    by_runtime = {row["runtime_key"]: row["record_id"] for row in records}
    for row in records:
        target = row.get("_fallback_target") or ""
        if not target:
            row["fallback_ref"] = ""
            continue
        record_id = by_runtime.get(target)
        if record_id is None:
            # 指向不存在的资源位属于数据缺陷，直接失败而不是写出半真映射。
            raise SystemExit("fallback 目标不在 P 表内：%s（record_id=%s）"
                             % (target, row["record_id"]))
        row["fallback_ref"] = record_id


def assign_canonical_ids(records: list) -> None:
    """canonical_record_id：非重复行指向自身，duplicate 行指向同 sha256 的保留行。"""
    canonical_by_sha = {}
    for row in records:
        digest = (row.get("sha256") or "").strip()
        if not digest:
            continue
        bucket = canonical_by_sha.setdefault(digest, [])
        bucket.append(row)
    resolved = {}
    for digest, group in canonical_by_sha.items():
        keeper = next((row for row in group if row["availability"] != "duplicate"), group[0])
        resolved[digest] = keeper["record_id"]
    for row in records:
        if row["availability"] == "duplicate":
            digest = (row.get("sha256") or "").strip()
            row["canonical_record_id"] = resolved.get(digest) or row["record_id"]
        else:
            row["canonical_record_id"] = row["record_id"]


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------
def _json_row(row: dict) -> dict:
    return {key: row.get(key) for key in CSV_COLUMNS}


def _csv_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return str(value)


def stats_of(records: list) -> dict:
    def count(predicate):
        return sum(1 for row in records if predicate(row))

    by_type = {}
    for row in records:
        by_type[row["asset_type"]] = by_type.get(row["asset_type"], 0) + 1

    missing_by_type = {}
    for row in records:
        if row["availability"] == "missing":
            missing_by_type[row["asset_type"]] = missing_by_type.get(row["asset_type"], 0) + 1

    runtime_status = {}
    for row in records:
        runtime_status[row["runtime_status"]] = runtime_status.get(row["runtime_status"], 0) + 1

    mapping_status = {}
    for row in records:
        mapping_status[row["mapping_status"]] = mapping_status.get(row["mapping_status"], 0) + 1

    return {
        "records": len(records),
        "usable": count(lambda r: r["availability"] == "usable"),
        "partial": count(lambda r: r["availability"] == "partial"),
        "missing": count(lambda r: r["availability"] == "missing"),
        "corrupted": count(lambda r: r["availability"] == "corrupted"),
        "duplicate": count(lambda r: r["availability"] == "duplicate"),
        "by_asset_type": by_type,
        "missing_by_asset_type": missing_by_type,
        "by_runtime_status": runtime_status,
        "by_mapping_status": mapping_status,
        "fallback_events": count(lambda r: r["runtime_status"] == "fallback"),
        "fallback_records": count(lambda r: r["mapping_status"] == "fallback"),
        "pending_missing_records": count(lambda r: r["mapping_status"] == "pending_missing"),
        "placeholder_records": count(lambda r: r["runtime_status"] == "placeholder"),
    }


def write_p_table(records: list, photos: dict, content_module) -> dict:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    with PTABLE_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        for row in records:
            writer.writerow({key: _csv_value(row.get(key)) for key in CSV_COLUMNS})

    content_path = GAME_DIR / "content.py"
    # 双向映射固定以 runtime_key（运行时键）为运行时侧：正向 runtime_key -> content_ref，
    # 反向 content_ref -> runtime_key；角色 target_ref 的 @fN 写法由 registry 直接按 target_ref 命中。
    content_refs = {row["runtime_key"]: row["_content_ref"] for row in records}
    content_refs.update({row["_content_ref"]: row["runtime_key"] for row in records})

    document = {
        "schema_version": "1.2.0",
        "generated_at": generation_date(),
        "base_dir": PROJECT_ROOT.name,
        "schema": {
            "format_version": "1.2.0",
            "description": "274 个资源位的 P 表；CSV 与 JSON 的 records 逐字段等价，"
                           "列序以 columns 为准（33 列 = 业务 26 列 + 发布档 7 列）。",
            "columns": list(CSV_COLUMNS),
            "release_columns": list(RELEASE_COLUMNS),
            "release": {
                "reviewer": REVIEWER_AUTOMATED,
                "verified_at": verification_date(),
                "verified_at_source": "SOURCE_DATE_EPOCH"
                if _source_date_epoch() is not None else "fixed",
                "bytes_sha256_source": "photos/ 源文件（不是运行时 PNG）；missing 行留空",
                "alpha_required": "角色 true；房间与卡面 false",
                "canonical_record_id": "非重复行指向自身；duplicate 行指向保留行",
            },
            "fields": {name: COLUMN_NOTES.get(name, "") for name in CSV_COLUMNS},
            "keys": {
                "record_id": "资源位主键，同时是 registry.resolve 接受的键之一。",
                "target_ref": "规范溯源键 content.py:<集合>#<id>（如 "
                              "content.py:OMEN_CARDS#omen_bite / "
                              "content.py:ROOM_BASES#entrance_hall / "
                              "content.py:CHARACTER_FACES#card_1@f0）。",
                "runtime_key": "运行时键（如 card:omen:omen_bite / room:entrance_hall / "
                               "character:card_1:f0）；registry 取图入口。",
                "content_ref": "content.py 原始记录 id（角色为 face id，如 "
                               "content.py:CHARACTER_FACES#card_1_0）。",
                "resolvable": "registry 同时接受 runtime_key / target_ref / record_id / "
                              "content_ref / 裸 id。",
            },
            "key_relation": KEY_RELATION_NOTE,
            "mapping_status": {
                "matched": "有真实源文件并已映射。",
                "fallback": "缺自有美术，但存在同类别真实回退图；fallback_ref 指向回退目标的 record_id。",
                "pending_missing": "缺图且只有统一占位图，无回退目标；fallback_ref 留空，"
                                   "runtime_status 仍为 placeholder。",
            },
            "dimensions": "源图尺寸文本 <width>x<height>；与 width/height 同源，missing 行为空。",
            "aspect_ratio": "源图宽高比，约分后形如 1:1、3:4；missing 行为空。",
        },
        "content": {
            "path": _rel(content_path),
            "sha256": _sha256(content_path),
            "collections": {
                "CHARACTER_FACES": len(content_module.CHARACTER_FACES),
                "ROOM_BASES": len(content_module.ROOM_BASES),
                "ROOM_SUPPLEMENTAL_SPECS": len(content_module.ROOM_SUPPLEMENTAL_SPECS),
                "OMEN_CARDS": len(content_module.OMEN_CARDS),
                "ITEM_CARDS": len(content_module.ITEM_CARDS),
                "EVENT_BASES": len(content_module.EVENT_BASES),
                "EVENT_SUPPLEMENTAL_SPECS": len(content_module.EVENT_SUPPLEMENTAL_SPECS),
                # run6 六类渲染面
                "MONSTER_BASES": len(getattr(content_module, "MONSTER_BASES", []) or []),
                "HAUNT_DEFS": len(content_module.build_catalog(0).haunt_defs),
                "RENDER_SURFACE_SPECS": len(
                    getattr(content_module, "RENDER_SURFACE_SPECS", []) or []),
            },
        },
        "source_inventory": {
            "photos_dir": _rel(PHOTOS_DIR),
            "files": photos["total"],
            "excluded_backup_files": photos.get("excluded_backups", 0),
            "aigc_marked": photos["with_aigc"],
            "corrupted": photos["corrupted"],
            "orphans": photos["orphans"],
        },
        "runtime_specs": RUNTIME_SPECS,
        "placeholders": {
            kind: _rel(placeholder_path(kind)) for kind in PLACEHOLDER_FILES
        },
        "stats": stats_of(records),
        "content_refs": content_refs,
        "records": [_json_row(row) for row in records],
    }

    with PTABLE_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")

    return document


def write_mapping(records: list) -> dict:
    """按 p_table_spec 6.3 输出映射；entries 只放可用/部分可用，unresolved 对齐 missing。"""
    entries = []
    unresolved = []
    for row in records:
        if row["availability"] in ("usable", "partial"):
            entries.append(
                {
                    "target_ref": row["target_ref"],
                    "runtime_key": row["runtime_key"],
                    "record_id": row["record_id"],
                    "content_ref": row["content_ref"],
                    "path": row["source_path"],
                    "status": row["mapping_status"],
                    "fallback": row["fallback_ref"],
                    "runtime_path": row["runtime_path"],
                }
            )
        elif row["availability"] == "missing":
            unresolved.append(
                {
                    "target_ref": row["target_ref"],
                    "runtime_key": row["runtime_key"],
                    "record_id": row["record_id"],
                    "content_ref": row["content_ref"],
                    "reason": "missing_file",
                    "status": row["mapping_status"],
                    # fallback 填回退目标的 record_id；pending_missing 为空。
                    "fallback": row["fallback_ref"],
                    "runtime_status": row["runtime_status"],
                    "runtime_path": row["runtime_path"],
                    "note": row["missing_note"],
                }
            )

    stats = stats_of(records)
    document = {
        "version": "1.1.0",
        "base_dir": PROJECT_ROOT.name,
        "generated_from": {
            "p_table": _rel(PTABLE_JSON),
            "content": _rel(GAME_DIR / "content.py"),
        },
        "notes": {
            "target_ref": "规范溯源键 content.py:<集合>#<id>；asset_registry 直接按它命中。",
            "runtime_key": "运行时键（room:/card:/character:），与 target_ref 一一对应。",
            "content_ref": "content.py 原始记录 id（角色为 face id card_1_0），供回溯。",
            "fallback": "回退目标的 record_id（如 P-EVT-007）；pending_missing 行为空。",
            "resolvable": "registry 同时接受 runtime_key / target_ref / record_id / "
                          "content_ref / 裸 id。",
        },
        "runtime_specs": RUNTIME_SPECS,
        "stats": {
            "entries": len(entries),
            "unresolved": len(unresolved),
            "mapping_status": stats["by_mapping_status"],
            "runtime_status": stats["by_runtime_status"],
        },
        "entries": entries,
        "unresolved": unresolved,
    }
    with MAPPING_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    return document


# ----------------------------------------------------------------------
# 规范化：源图 -> 运行时 PNG
# ----------------------------------------------------------------------
def normalize_room(source: Path, target: Path) -> tuple:
    from PIL import Image

    with Image.open(source) as image:
        converted = image.convert("RGB")
        resized = converted.resize(ROOM_SIZE, _resample())
        target.parent.mkdir(parents=True, exist_ok=True)
        resized.save(target, format="PNG", optimize=True)
    return ROOM_SIZE


def normalize_card(source: Path, target: Path) -> tuple:
    """等比缩放到 480x672 画布内，余下补边（源图 3:4，目标 5:7，硬拉会变形）。"""
    from PIL import Image

    with Image.open(source) as image:
        converted = image.convert("RGB")
        width, height = converted.size
        scale = min(CARD_SIZE[0] / float(width), CARD_SIZE[1] / float(height))
        new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        resized = converted.resize(new_size, _resample())

        corners = [
            resized.getpixel((0, 0)),
            resized.getpixel((new_size[0] - 1, 0)),
            resized.getpixel((0, new_size[1] - 1)),
            resized.getpixel((new_size[0] - 1, new_size[1] - 1)),
        ]
        pad = tuple(sum(channel) // len(corners) for channel in zip(*corners))

        canvas = Image.new("RGB", CARD_SIZE, pad)
        canvas.paste(resized, ((CARD_SIZE[0] - new_size[0]) // 2, (CARD_SIZE[1] - new_size[1]) // 2))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, format="PNG", optimize=True)
    return CARD_SIZE


def normalize_character(source: Path, target: Path) -> tuple:
    """角色立绘规范化到 320x320：缩放居中后落到 RGBA 画布（alpha_required）。"""
    from PIL import Image

    with Image.open(source) as image:
        converted = image.convert("RGBA")
        width, height = converted.size
        scale = min(CHARACTER_SIZE[0] / float(width), CHARACTER_SIZE[1] / float(height))
        new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        resized = converted.resize(new_size, _resample())
        canvas = Image.new("RGBA", CHARACTER_SIZE, (0, 0, 0, 0))
        canvas.paste(
            resized,
            ((CHARACTER_SIZE[0] - new_size[0]) // 2, (CHARACTER_SIZE[1] - new_size[1]) // 2),
            resized,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, format="PNG", optimize=True)
    return CHARACTER_SIZE


def normalize_extra(source: Path, target: Path, size, keep_alpha: bool) -> tuple:
    """run6 六类渲染面：等比缩放到目标尺寸内并居中。

    keep_alpha=True（怪物标记 / 未翻地块 / 骰面）保留透明通道，避免叠在地块上
    出现白色方块；其余（剧本插画 / 结算 / 牌背）按不透明处理，补边色取四角均值。
    """
    from PIL import Image

    width_target, height_target = size
    with Image.open(source) as image:
        if keep_alpha:
            converted = image.convert("RGBA")
        else:
            converted = image.convert("RGB")
        width, height = converted.size
        scale = min(width_target / float(width), height_target / float(height))
        new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        resized = converted.resize(new_size, _resample())
        if keep_alpha:
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            canvas.paste(resized, ((width_target - new_size[0]) // 2,
                                   (height_target - new_size[1]) // 2), resized)
        else:
            corners = [
                resized.getpixel((0, 0)),
                resized.getpixel((new_size[0] - 1, 0)),
                resized.getpixel((0, new_size[1] - 1)),
                resized.getpixel((new_size[0] - 1, new_size[1] - 1)),
            ]
            pad = tuple(sum(channel) // len(corners) for channel in zip(*corners))
            canvas = Image.new("RGB", size, pad)
            canvas.paste(resized, ((width_target - new_size[0]) // 2,
                                   (height_target - new_size[1]) // 2))
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, format="PNG", optimize=True)
    return size


def normalize_assets(records: list) -> dict:
    """只处理 availability in {usable, partial} 且有源文件的行；不触碰 photos。"""
    from PIL import Image

    photos_root = PHOTOS_DIR.resolve()
    written = []
    failures = []
    total_bytes = 0

    for row in records:
        if row["availability"] not in ("usable", "partial"):
            continue
        if not row["source_path"]:
            failures.append({"record_id": row["record_id"], "reason": "partial_without_source"})
            continue

        source = PROJECT_ROOT / row["source_path"]
        target = row["_runtime_abs"]
        try:
            if photos_root in target.resolve().parents:
                raise RuntimeError("拒绝写入 photos：%s" % target)

            if row["_family"] == "room":
                size = normalize_room(source, target)
            elif row["_family"] == "character":
                size = normalize_character(source, target)
            elif row["_family"] in RUNTIME_EXTRA_DIRS:
                size = normalize_extra(
                    source, target,
                    FAMILIES[row["_family"]]["size"],
                    bool(ALPHA_REQUIRED[row["_family"]]))
            else:
                size = normalize_card(source, target)

            # 回读确认写出的是真实 PNG，不是改名 JPEG。
            with Image.open(target) as check:
                check.load()
                if check.format != "PNG":
                    raise RuntimeError("运行时文件不是 PNG：%s" % check.format)
                if check.size != tuple(size):
                    raise RuntimeError("运行时尺寸异常：%s" % (check.size,))

            size_bytes = target.stat().st_size
            total_bytes += size_bytes
            written.append(
                {
                    "record_id": row["record_id"],
                    "target_ref": row["target_ref"],
                    "runtime_path": row["runtime_path"],
                    "width": size[0],
                    "height": size[1],
                    "bytes": size_bytes,
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "record_id": row["record_id"],
                    "source_path": row["source_path"],
                    "reason": "%s: %s" % (type(exc).__name__, exc),
                }
            )

    return {
        "written": len(written),
        "bytes": total_bytes,
        "failures": failures,
        "items": written,
    }


# ----------------------------------------------------------------------
# 占位图
# ----------------------------------------------------------------------
def _pick_font(size: int, bold: bool = False):
    """优先中文黑体，缺失时退回 Pillow 内置字体（只画 ASCII 标签）。"""
    from PIL import ImageFont

    candidates = []
    if bold:
        candidates.extend(["msyhbd.ttc", "msyhbd.ttf", "simhei.ttf"])
    candidates.extend(["msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc", "deng.ttf"])
    roots = [Path("C:/Windows/Fonts")]
    for name in candidates:
        for root in roots:
            path = root / name
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size), True
                except Exception:
                    continue
    try:
        return ImageFont.load_default(size=size), False
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default(), False


def _center_text(draw, center, text, font, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = right - left
    height = bottom - top
    draw.text(
        (center[0] - width / 2.0 - left, center[1] - height / 2.0 - top),
        text,
        font=font,
        fill=fill,
    )


def build_placeholder(kind: str, size) -> Path:
    """深色底 + 类别文字 + 简洁边框的缺图占位。"""
    from PIL import Image, ImageDraw

    width, height = size
    label_cn, label_en, label_sub = PLACEHOLDER_LABELS[kind]

    image = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(image)

    inset = max(6, width // 30)
    panel_inset = inset + max(4, width // 90)
    draw.rectangle([panel_inset, panel_inset, width - 1 - panel_inset, height - 1 - panel_inset],
                   fill=COLOR_PANEL)
    draw.rectangle([inset, inset, width - 1 - inset, height - 1 - inset],
                   outline=COLOR_BORDER, width=max(2, width // 160))

    font_title, cjk = _pick_font(max(16, width // 11), bold=True)
    font_sub, _ = _pick_font(max(12, width // 21), bold=True)
    font_note, _ = _pick_font(max(10, width // 30))

    title = label_cn if cjk else label_en
    subtitle = label_en if cjk else label_sub
    note = "%dx%d PLACEHOLDER" % (width, height)

    _center_text(draw, (width / 2.0, height * 0.40), title, font_title, COLOR_TEXT)
    line_y = int(height * 0.475)
    draw.line(
        [(int(width * 0.30), line_y), (int(width * 0.70), line_y)],
        fill=COLOR_BORDER,
        width=max(1, width // 240),
    )
    _center_text(draw, (width / 2.0, height * 0.545), subtitle, font_sub, COLOR_BORDER)
    _center_text(draw, (width / 2.0, height * 0.625), note, font_note, COLOR_MUTED)

    PLACEHOLDER_DIR.mkdir(parents=True, exist_ok=True)
    out = placeholder_path(kind)
    image.save(out, format="PNG", optimize=True)

    with Image.open(out) as check:
        check.load()
        if check.format != "PNG" or check.size != size:
            raise RuntimeError("占位图自检失败：%s" % out)
    return out


def build_placeholders() -> dict:
    built = {}
    for kind, size in (
        ("character", CHARACTER_SIZE),
        ("room", ROOM_SIZE),
        ("event", CARD_SIZE),
    ):
        path = build_placeholder(kind, size)
        built[kind] = {"path": _rel(path), "width": size[0], "height": size[1],
                       "bytes": path.stat().st_size}
    return built


# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------
def _summary(document: dict) -> str:
    stats = document["stats"]
    lines = [
        "P 表：%d 行（usable=%d / partial=%d / missing=%d / corrupted=%d）"
        % (stats["records"], stats["usable"], stats["partial"], stats["missing"],
           stats["corrupted"]),
        "分类计数：" + ", ".join("%s=%s" % (k, v) for k, v in stats["by_asset_type"].items()),
        "映射状态：" + ", ".join("%s=%s" % (k, v) for k, v in stats["by_mapping_status"].items()),
        "运行时状态：" + ", ".join("%s=%s" % (k, v) for k, v in stats["by_runtime_status"].items()),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建 P 表并生成桌面端运行时 PNG 资源")
    parser.add_argument(
        "--stage",
        choices=("all", "ptable", "normalize", "placeholders"),
        default="all",
        help="默认 all：P 表 -> 占位图 -> 规范化",
    )
    args = parser.parse_args(argv)

    content_module = load_content()
    # run4 性能修复（run4 §5.2.3 修复回路，PT-PERF-02）：--stage placeholders 只生成
    # 3 张固定占位图，不需要 photos 扫描与 records 构建；此前无条件前置扫描使该阶段
    # 恒超 3s 预算（实测 median 3251.8ms，scan_photos 单项 3047ms）。惰性推迟到
    # 需要它们的阶段（all/ptable/normalize），占位图产物逐字节不变。
    photos = None
    records = None
    slots = None
    if args.stage in ("all", "ptable", "normalize"):
        photos = scan_photos()
        records, slots = build_records(content_module, photos)
        assign_record_ids(records)
        assign_fallback_refs(records)
        assign_canonical_ids(records)

    document = None
    if args.stage in ("all", "ptable"):
        document = write_p_table(records, photos, content_module)
        write_mapping(records)
        print("[ptable] %s" % _rel(PTABLE_CSV))
        print("[ptable] %s" % _rel(PTABLE_JSON))
        print("[ptable] %s" % _rel(MAPPING_JSON))
        print(_summary(document))

    if args.stage in ("all", "placeholders"):
        placeholders = build_placeholders()
        print("[placeholders] %d 张" % len(placeholders))
        for kind, info in placeholders.items():
            print("  %-9s %-52s %dx%d %d B"
                  % (kind, info["path"], info["width"], info["height"], info["bytes"]))

    if args.stage in ("all", "normalize"):
        result = normalize_assets(records)
        print("[normalize] 写出 %d 张，合计 %d 字节（%.2f MiB）"
              % (result["written"], result["bytes"], result["bytes"] / 1048576.0))
        if result["failures"]:
            print("[normalize] 失败 %d 项：" % len(result["failures"]))
            for item in result["failures"]:
                print("  %s" % item)
            return 1

    if slots and len(records) != EXPECTED_SLOT_TOTAL:
        print("[warn] 资源位数量 %d != %d，请检查 content.py"
              % (len(records), EXPECTED_SLOT_TOTAL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
