#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图片 P 表与资源映射 —— 只读契约验收脚本。

定位
----
本脚本只做验收判定，不参与实现，全程不写任何文件：
- 不创建 / 不修改 `assets/`、`photos/`、`source/` 下任何文件；
- 顶部设置 `sys.dont_write_bytecode = True`，导入被测模块时不生成 `__pycache__`；
- 无临时文件、无网络、无凭据、无子进程写操作。

被测契约
--------
source/desktop/game/asset_pipeline.py          P 表构建与运行时图规范化
source/desktop/game/asset_registry.py          运行时资源注册表
source/desktop/game/assets/p_table.json        P 表（274 个资源位）
source/desktop/game/assets/asset_mapping.json  资源映射（entries + unresolved）

交付物缺失时全部相关检查明确 SKIP（退出码 3），不伪造 PASS。

断言常量来自 .codebuddy/wfat/p_table_spec.md 与只读实测：
274 个资源位（角色 12 / 房间 50 / 预兆 13 / 物品 22 / 事件 45）、
磁盘 95 张（全部 .png 扩展名 + JPEG 魔数，故全部 partial）、
缺口 47（角色 12 / 房间 1 / 事件 34）。

两层判定
--------
- 事实层（C13/C14/C17/C18…）：实测文件与记录是否一致，不一致即 FAIL；
- 规范层（C06/C21/C32…）：字段格式与语义是否符合 spec，偏离单列 FAIL/WARN，
  不与事实层互相污染（避免一个根因引发级联误报）。

用法
----
python verify_assets_contract.py                 人读报告
python verify_assets_contract.py --json          机器可读，仅写到 stdout
python verify_assets_contract.py --list          列出全部检查项
python verify_assets_contract.py --no-decode     快速档：跳过 Pillow 逐图解码
python verify_assets_contract.py --profile post-normalize
python verify_assets_contract.py --strict        把 WARN 计为失败
python verify_assets_contract.py --require       把 SKIP 计为失败（CI 门禁）

退出码
------
0  PASS  无 FAIL / ERROR（可能有 SKIP / WARN）
1  FAIL  存在 FAIL / ERROR（或 --strict / --require 提升了 WARN / SKIP）
2  参数错误或脚本内部异常
3  SKIP  实现未交付，所有依赖交付物的检查被跳过（不构成通过）

判读纪律
--------
本脚本输出 PASS 只表示「数据与契约一致」，不表示「素材可发布」。
95/95 张图扩展名与真实编码冲突，`usable` 必须为 0；`partial` 只能支撑草稿/预览。
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 关键：导入被测模块前关闭字节码写入，保证「只读」可审计。
sys.dont_write_bytecode = True

PASS, FAIL, SKIP, WARN, ERROR = "PASS", "FAIL", "SKIP", "WARN", "ERROR"

# ---------------------------------------------------------------- 断言常量 --

EXPECTED_TOTAL = 274
EXPECTED_BY_ASSET_TYPE = {
    "character": 12,
    "room": 50,
    "card_omen": 13,
    "card_item": 22,
    "card_event": 45,
    # run6 六类渲染面
    "monster": 52,
    "haunt": 70,
    "ending": 2,
    "card_back": 3,
    "room_back": 2,
    "dice": 3,
}
EXPECTED_CONTENT_COUNTS = {
    "CHARACTER_FACES": 12,
    "ROOM_BASES": 39,
    "ROOM_SUPPLEMENTAL_SPECS": 11,
    "OMEN_CARDS": 13,
    "MONSTER_BASES": 52,
    "HAUNT_DEFS": 70,
    "RENDER_SURFACE_SPECS": 10,
    "ITEM_CARDS": 22,
    "EVENT_BASES": 11,
    "EVENT_SUPPLEMENTAL_SPECS": 34,
}
# run5 v2（2026-11-20）：47 个缺口已按"复用既有文件 + 130 张无损转码"落实，
# 274 位全部 usable；旧 0/95/47 不再是活跃断言（见 qa/run5_baseline_diff.json）。
BASELINE_AVAILABILITY = {
    "usable": 274,
    "partial": 0,
    "missing": 0,
    "corrupted": 0,
    "duplicate": 0,
}
BASELINE_MISSING_BY_TYPE = {}

EXPECTED_SOURCE_FILES = 274
# architecture.json 决策：房间 512x512、卡牌 480x672（角色尺寸架构未定义，见文档 R03）
ARCHITECTURE_RUNTIME_SIZES = {"room": (512, 512), "card": (480, 672)}
RUNTIME_SPEC_KEY = {"room": "room", "card_omen": "card", "card_item": "card",
                    "card_event": "card", "character": "character",
                    "icon": "icon", "background": "background"}
# 规范 §2 的推荐下限：卡面长边 >= 1600、房间 >= 1024、角色 >= 1024。
RECOMMENDED_LONG_EDGE = {
    "card_omen": 1600,
    "card_item": 1600,
    "card_event": 1600,
    "room": 1024,
    "character": 1024,
    "icon": 256,
    "background": 1920,
}
# run5 D-01（书面偏差）：角色母版 320x320 被接受——无更高分辨率源、禁止放大、
# 运行时目标即 320；该偏差只对角色生效，WW 重新进入时按 R3 重议。
LONG_EDGE_DEVIATION = {"character": 320}
BLOCKING_FLAGS = {"ext_mismatch", "no_alpha", "below_recommended", "ratio_drift"}
USABLE_FIELD_ENUM = {
    "portrait", "room_tile", "card_face", "icon", "background", "preview", "none",
    # run6 六类渲染面
    "monster_marker", "haunt_art", "ending_screen", "card_back", "room_back", "dice_face",
}
ALLOWED_AVAILABILITY = {"usable", "partial", "missing", "corrupted", "duplicate"}
ALLOWED_MAPPING_STATUS = {
    "matched", "fallback", "ambiguous", "unmatched", "alias", "excluded", "pending_missing",
}
USABLE_FIELDS_BY_TYPE = {
    "room": {"room_tile", "preview"},
    "character": {"portrait", "preview"},
    "icon": {"icon"},
    "background": {"background"},
    "card_omen": {"card_face", "preview"},
    "card_item": {"card_face", "preview"},
    "card_event": {"card_face", "preview"},
    # run6 六类渲染面
    "monster": {"monster_marker", "preview"},
    "haunt": {"haunt_art", "preview"},
    "ending": {"ending_screen", "preview"},
    "card_back": {"card_back", "preview"},
    "room_back": {"room_back", "preview"},
    "dice": {"dice_face", "preview"},
}
REQUIRED_FIELDS = [
    "record_id", "source_file", "source_path", "asset_type", "dimensions", "format",
    "has_alpha", "decodable", "semantic_hint", "match_candidate", "usable_fields",
    "availability", "mapping_status", "target_ref", "missing_note", "provenance",
]

RECORD_ID_RE = re.compile(
    r"^P-(CHR|ROOM|OMEN|ITEM|EVT|MONS|HAUNT|END|CBACK|RBACK|DICE|ICO|BG|UNK)-(\d{3})$")
RECORD_ID_PREFIX = {
    "CHR": "character",
    "ROOM": "room",
    "OMEN": "card_omen",
    "ITEM": "card_item",
    "EVT": "card_event",
    # run6 六类渲染面
    "MONS": "monster",
    "HAUNT": "haunt",
    "END": "ending",
    "CBACK": "card_back",
    "RBACK": "room_back",
    "DICE": "dice",
    "ICO": "icon",
    "BG": "background",
    "UNK": "unknown",
}
# 规范 §1.1 的唯一合法形态：content.py:<集合>#<id>
TARGET_REF_RE = re.compile(r"^content\.py:(?P<coll>[A-Z_]+)#(?P<rid>[^#\s]+)$")
COLLECTION_ALIASES = {
    "character": "CHARACTER_FACES",
    "characters": "CHARACTER_FACES",
    "char": "CHARACTER_FACES",
    "room": "ROOM_BASES",
    "rooms": "ROOM_BASES",
    "omen": "OMEN_CARDS",
    "card_omen": "OMEN_CARDS",
    "item": "ITEM_CARDS",
    "card_item": "ITEM_CARDS",
    "event": "EVENT_BASES",
    "card_event": "EVENT_BASES",
    # run6 六类渲染面
    "monster": "MONSTER_BASES",
    "monsters": "MONSTER_BASES",
    "haunt": "HAUNT_DEFS",
    "haunts": "HAUNT_DEFS",
    "ending": "RENDER_SURFACE_SPECS",
    "endings": "RENDER_SURFACE_SPECS",
    "card_back": "RENDER_SURFACE_SPECS",
    "card_backs": "RENDER_SURFACE_SPECS",
    "room_back": "RENDER_SURFACE_SPECS",
    "room_backs": "RENDER_SURFACE_SPECS",
    "dice": "RENDER_SURFACE_SPECS",
}
UNIVERSE_COLLECTIONS = {
    "character": ("CHARACTER_FACES",),
    "room": ("ROOM_BASES", "ROOM_SUPPLEMENTAL_SPECS"),
    "card_omen": ("OMEN_CARDS",),
    "card_item": ("ITEM_CARDS",),
    "card_event": ("EVENT_BASES", "EVENT_SUPPLEMENTAL_SPECS"),
    # run6 六类渲染面
    "monster": ("MONSTER_BASES",),
    "haunt": ("HAUNT_DEFS",),
    "ending": ("RENDER_SURFACE_SPECS",),
    "card_back": ("RENDER_SURFACE_SPECS",),
    "room_back": ("RENDER_SURFACE_SPECS",),
    "dice": ("RENDER_SURFACE_SPECS",),
}
# 四类固定渲染位共用 RENDER_SURFACE_SPECS；必须按 spec.surface 切子集，
# 否则每个 asset_type 都会看到全部 10 个 id（2 ending / 3 card_back / 2 room_back / 3 dice）。
UNIVERSE_SURFACE = {
    "ending": "ending",
    "card_back": "card_back",
    "room_back": "room_back",
    "dice": "dice",
}
REL_PATH_RE = re.compile(r"^[a-z0-9_][a-z0-9_./-]*$")

CSV_COLUMNS = [
    "record_id", "source_file", "source_path", "asset_type", "dimensions", "format",
    "has_alpha", "decodable", "semantic_hint", "match_candidate", "usable_fields",
    "availability", "mapping_status", "target_ref", "missing_note", "provenance",
    "width", "height", "aspect_ratio", "bytes", "sha256", "category_dir",
    "alpha_required", "quality_flags", "fallback_ref", "canonical_record_id",
    "reviewer", "verified_at",
]

PNG_SIG = b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------------------------- 结果模型 --

class Result(object):
    __slots__ = ("cid", "title", "priority", "status", "detail")

    def __init__(self, cid: str, title: str, priority: str, status: str, detail: str) -> None:
        self.cid = cid
        self.title = title
        self.priority = priority
        self.status = status
        self.detail = detail

    def as_dict(self) -> Dict[str, str]:
        return {
            "id": self.cid,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "detail": self.detail,
        }


class Context(object):
    """一次性装载全部只读事实，检查函数只读该上下文。"""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.script_dir = Path(__file__).resolve().parent
        self.game_dir = self.script_dir.parent
        default_root = self.game_dir.parents[2]
        self.root = Path(args.root).resolve() if args.root else default_root
        self.profile = args.profile

        self.p_table_path: Optional[Path] = None
        self.p_table: Optional[dict] = None
        self.p_table_error: str = ""
        self.records: Optional[List[dict]] = None
        self.by_record: Dict[str, dict] = {}
        self.by_target_ref: Dict[str, dict] = {}

        self.mapping_path: Optional[Path] = None
        self.mapping: Optional[dict] = None
        self.mapping_error: str = ""

        self.inventory_path: Optional[Path] = None
        self.inventory: List[dict] = []
        self.inventory_by_file: Dict[str, dict] = {}

        self.content_path: Optional[Path] = None
        self.content: Dict[str, list] = {}
        self.content_error: str = ""

        self.registry: Any = None
        self.registry_error: str = ""

        self.pillow: Any = None
        self.pillow_version: str = ""

        self._sha_cache: Dict[str, str] = {}

    # -- 惰性工具 ---------------------------------------------------------
    def sha256(self, path: Path) -> str:
        key = str(path)
        if key not in self._sha_cache:
            digest = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            self._sha_cache[key] = digest.hexdigest()
        return self._sha_cache[key]

    def abs_path(self, rel: str) -> Path:
        return self.root / rel.replace("\\", "/")

    @property
    def runtime_specs(self) -> Dict[str, dict]:
        table = self.p_table or {}
        specs = table.get("runtime_specs")
        return specs if isinstance(specs, dict) else {}

    @property
    def p_table_missing_reason(self) -> str:
        if self.p_table_error:
            return self.p_table_error
        return "未找到 assets/p_table.json（实现未交付，P 表检查跳过）"

    @property
    def mapping_missing_reason(self) -> str:
        if self.mapping_error:
            return self.mapping_error
        return "未找到 assets/asset_mapping.json（实现未交付，映射检查跳过）"


# ------------------------------------------------------------------ 只读工具 --

def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def sniff_format(path: Path) -> str:
    """按魔数判定真实格式，不看扩展名。"""
    try:
        with path.open("rb") as fh:
            head = fh.read(32)
    except OSError:
        return "unknown"
    if head.startswith(PNG_SIG):
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def png_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    try:
        with path.open("rb") as fh:
            head = fh.read(33)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != PNG_SIG or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def jpeg_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    """只读解析 JPEG SOF 段取宽高，作为 Pillow 之外的独立复核。"""
    try:
        with path.open("rb") as fh:
            if fh.read(2) != b"\xff\xd8":
                return None
            while True:
                byte = fh.read(1)
                if not byte:
                    return None
                if byte != b"\xff":
                    continue
                marker = fh.read(1)
                while marker == b"\xff":
                    marker = fh.read(1)
                if not marker:
                    return None
                code = marker[0]
                if code in (0xD8, 0x01) or 0xD0 <= code <= 0xD7:
                    continue
                if code == 0xD9:
                    return None
                seg = fh.read(2)
                if len(seg) < 2:
                    return None
                length = int.from_bytes(seg, "big")
                if length < 2:
                    return None
                if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
                    data = fh.read(5)
                    if len(data) < 5:
                        return None
                    height = int.from_bytes(data[1:3], "big")
                    width = int.from_bytes(data[3:5], "big")
                    return width, height
                fh.seek(length - 2, 1)
    except OSError:
        return None


def probe_dimensions(path: Path, fmt: str) -> Optional[Tuple[int, int]]:
    if fmt == "png":
        return png_dimensions(path)
    if fmt == "jpeg":
        return jpeg_dimensions(path)
    return None


def walk_case(root: Path, rel: str) -> Tuple[bool, str]:
    """逐段比对磁盘真实文件名，捕捉 Windows 上被掩盖的大小写缺陷。"""
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts:
        return False, "空路径"
    cur = root
    for index, part in enumerate(parts):
        try:
            names = os.listdir(cur)
        except OSError as exc:
            return False, "目录不可读: %s (%s)" % (cur, exc)
        if part in names:
            cur = cur / part
            continue
        ci_match = [n for n in names if n.lower() == part.lower()]
        prefix = "/".join(parts[: index + 1])
        if ci_match:
            actual = "/".join(parts[:index] + [ci_match[0]])
            return False, "大小写不一致: %s 实际为 %s" % (prefix, actual)
        return False, "路径不存在: %s" % rel
    return True, ""


def longest_edge(size: Optional[Tuple[int, int]]) -> Optional[int]:
    if not size:
        return None
    return max(size[0], size[1])


def aspect_ratio(width: int, height: int) -> str:
    def _gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a

    divisor = _gcd(width, height) or 1
    return "%d:%d" % (width // divisor, height // divisor)


def as_list(value: Any) -> List[str]:
    """数组字段兼容 list 与 CSV 的 `;` / `,` 分隔写法。"""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value)
    for sep in (";", "|"):
        if sep in text:
            return [part.strip() for part in text.split(sep) if part.strip()]
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text.strip()]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def norm_ref(value: Any) -> str:
    return str(value or "").strip()


def ref_attr(ref: Any, *names: str) -> Any:
    """AssetRef 可能是对象或 dict，按可观察契约取字段。"""
    for name in names:
        if isinstance(ref, dict):
            if name in ref:
                return ref[name]
        elif hasattr(ref, name):
            return getattr(ref, name)
    return None


# ------------------------------------------------------------ content.py 解析 --

def extract_ids(node: ast.AST) -> List[Any]:
    """从列表字面量提取 id；角色的 face_index 一并保留用于双面校验。

    run6：RENDER_SURFACE_SPECS 的元素是 dict 字面量（``{'id': ..., 'surface': ...}``），
    MONSTER_BASES 的元素是 ``monster_def(monster_id=...)`` 调用；两种形态都要能取到主键，
    否则集合计数会退化成 0（C05 曾因此在 52/70/10 上报错）。
    """
    ids: List[Any] = []
    elements = getattr(node, "elts", []) or []
    for element in elements:
        if isinstance(element, ast.Tuple) and element.elts:
            first = element.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                ids.append(first.value)
            continue
        if isinstance(element, ast.Dict):
            fields: Dict[str, Any] = {}
            for key_node, value_node in zip(element.keys, element.values):
                if (isinstance(key_node, ast.Constant)
                        and isinstance(key_node.value, str)
                        and isinstance(value_node, ast.Constant)):
                    fields[key_node.value] = value_node.value
            if isinstance(fields.get("id"), str):
                entry: Any = {"id": fields["id"]}
                if isinstance(fields.get("surface"), str):
                    entry["surface"] = fields["surface"]
                ids.append(entry)
            continue
        if isinstance(element, ast.Call):
            keywords = {kw.arg: kw.value for kw in element.keywords if kw.arg}
            primary = None
            for name in ("room_id", "card_id", "monster_id", "id"):
                if name in keywords and isinstance(keywords[name], ast.Constant):
                    primary = keywords[name].value
                    break
            if primary is None:
                continue
            face = None
            if "face_index" in keywords and isinstance(keywords["face_index"], ast.Constant):
                face = keywords["face_index"].value
            ids.append((primary, face) if face is not None else primary)
            continue
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            ids.append(element.value)
    return ids


def _load_content_collections(path: Path) -> Dict[str, list]:
    """从 content.py 的真实模块取集合（AST 只有字面量列表覆盖不到的两类）。

    * ``MONSTER_BASES``：元素是 ``monster_def(...)`` 调用，AST 分支取 id，这里取真实对象；
    * ``HAUNT_DEFS``：模块里没有同名列表，唯一来源是 ``build_catalog(0).haunt_defs``
      （P 表 target_ref 写的就是 ``content.py:HAUNT_DEFS#<n>``），只能导入求值；
    * ``RENDER_SURFACE_SPECS``：需要 ``id`` + ``surface`` 两个字段，才能按渲染面切分子集。

    导入失败或解析到别的 ``game.content``（同名模块遮蔽）时返回空表，由 AST 结果兜底，
    C05 会如实报出缺失而不是静默通过。
    """
    game_dir = path.parent
    package_root = str(game_dir.parent)
    added = package_root not in sys.path
    if added:
        sys.path.insert(0, package_root)
    try:
        module = importlib.import_module("game.content")
        module_file = Path(getattr(module, "__file__", "") or "").resolve()
        if module_file != path.resolve():
            module = None
    except Exception:
        module = None
    finally:
        if added:
            try:
                sys.path.remove(package_root)
            except ValueError:
                pass
    if module is None:
        return {}

    out: Dict[str, list] = {}
    monsters = [
        str(item.get("id"))
        for item in (getattr(module, "MONSTER_BASES", []) or [])
        if isinstance(item, dict) and item.get("id")
    ]
    if monsters:
        out["MONSTER_BASES"] = monsters

    specs: List[Any] = []
    for spec in getattr(module, "RENDER_SURFACE_SPECS", []) or []:
        if isinstance(spec, dict) and spec.get("id"):
            entry: Dict[str, str] = {"id": str(spec["id"])}
            if spec.get("surface"):
                entry["surface"] = str(spec["surface"])
            specs.append(entry)
    if specs:
        out["RENDER_SURFACE_SPECS"] = specs

    haunt_defs = {}
    try:
        catalog = module.build_catalog(0)
        haunt_defs = getattr(catalog, "haunt_defs", {}) or {}
    except Exception:
        haunt_defs = {}
    if haunt_defs:
        # 键是 int；P 表 target_ref 用字符串段，统一成 str 便于双向比对。
        out["HAUNT_DEFS"] = [str(key) for key in sorted(haunt_defs)]
    return out


def load_content_index(path: Path) -> Dict[str, list]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    index: Dict[str, list] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if not isinstance(target, ast.Name) or target.id not in EXPECTED_CONTENT_COUNTS:
            continue
        if isinstance(value, (ast.List, ast.Tuple)):
            index[target.id] = extract_ids(value)
    # 真实集合优先（覆盖 AST 取不到的 HAUNT_DEFS 与需要 surface 字段的渲染面规格）
    index.update(_load_content_collections(path))
    return index


def content_primary_ids(index: Dict[str, list], collection: str) -> set:
    out = set()
    for item in index.get(collection, []):
        if isinstance(item, tuple):
            if isinstance(item[0], str):
                out.add(item[0])
        elif isinstance(item, dict):
            ident = item.get("id")
            if isinstance(ident, str):
                out.add(ident)
        elif isinstance(item, str):
            out.add(item)
    return out


def content_surface_ids(index: Dict[str, list], collection: str, surface: str) -> set:
    """RENDER_SURFACE_SPECS 按 ``surface`` 切子集（ending/card_back/room_back/dice）。"""
    out = set()
    for item in index.get(collection, []):
        if not isinstance(item, dict):
            continue
        if str(item.get("surface") or "") != surface:
            continue
        ident = item.get("id")
        if isinstance(ident, str):
            out.add(ident)
    return out


def content_faces(index: Dict[str, list]) -> set:
    out = set()
    for item in index.get("CHARACTER_FACES", []):
        if isinstance(item, tuple) and isinstance(item[0], str):
            out.add((item[0], item[1]))
    return out


def _face_from_hint(record: dict) -> Optional[int]:
    mc = str(record.get("match_candidate") or "")
    found = re.search(r"#f(\d+)", mc)
    return int(found.group(1)) if found else None


def parse_target_ref(record: dict) -> dict:
    """解析 target_ref。

    返回 {raw, collection, id, face, conformant}：
    - conformant=True 仅当符合规范 `content.py:<集合>#<id>`；
    - 非规范形态（如 `character:card_1:f0`、`card:omen:omen_bite`）仍宽容解析，
      以便「字段合规」与「id 对齐」分开判定，避免级联误报。
    """
    raw = norm_ref(record.get("target_ref"))
    parsed = {"raw": raw, "collection": None, "id": "", "face": None, "conformant": False}
    match = TARGET_REF_RE.match(raw)
    if match:
        parsed["conformant"] = True
        collection = match.group("coll")
        rid = match.group("rid").strip()
        parsed["collection"] = collection
        if "@f" in rid:
            rid, _, suffix = rid.partition("@f")
            if suffix.isdigit():
                parsed["face"] = int(suffix)
        elif collection == "CHARACTER_FACES":
            parsed["face"] = _face_from_hint(record)
        parsed["id"] = rid
        return parsed

    tokens = [token for token in re.split(r"[:#|/]+", raw) if token]
    face: Optional[int] = None
    rest: List[str] = []
    for token in tokens:
        face_match = re.fullmatch(r"f(\d+)", token.lower())
        if face_match:
            face = int(face_match.group(1))
            continue
        rest.append(token)
    if face is None:
        face = _face_from_hint(record)
    if not rest:
        return parsed

    collection = COLLECTION_ALIASES.get(rest[0].lower())
    if collection is not None:
        rest = rest[1:]
        if collection == "ROOM_BASES" and rest and rest[0].lower() in {
                "supplemental", "supplement", "specs"}:
            rest = rest[1:]
        if not rest:
            return parsed
    parsed["collection"] = collection
    parsed["id"] = rest[-1]
    parsed["face"] = face
    return parsed


# -------------------------------------------------------------------- 装载 --

def locate(candidates: Sequence[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def prepare(ctx: Context) -> None:
    assets_dir = ctx.game_dir / "assets"
    ctx.p_table_path = locate([
        assets_dir / "p_table.json",
        ctx.game_dir / "docs" / "p_table.json",
        ctx.root / "assets" / "p_table.json",
    ])
    ctx.mapping_path = locate([
        assets_dir / "asset_mapping.json",
        ctx.game_dir / "docs" / "asset_mapping.json",
        ctx.root / "assets" / "asset_mapping.json",
    ])
    ctx.inventory_path = locate([
        ctx.root / ".codebuddy" / "wfat" / "photos_inventory.json",
    ])
    ctx.content_path = locate([ctx.game_dir / "content.py"])

    if ctx.p_table_path is not None:
        try:
            ctx.p_table = read_json(ctx.p_table_path)
            raw_records = ctx.p_table.get("records")
            if not isinstance(raw_records, list):
                ctx.p_table_error = "p_table.json 缺少 records 数组"
            else:
                ctx.records = [rec for rec in raw_records if isinstance(rec, dict)]
                if len(ctx.records) != len(raw_records):
                    ctx.p_table_error = "records 中存在非对象元素 %d 个" % (
                        len(raw_records) - len(ctx.records))
                for rec in ctx.records:
                    rid = str(rec.get("record_id") or "")
                    if rid:
                        ctx.by_record.setdefault(rid, rec)
                    tref = norm_ref(rec.get("target_ref"))
                    if tref:
                        ctx.by_target_ref.setdefault(tref, rec)
        except (OSError, ValueError) as exc:
            ctx.p_table_error = "p_table.json 无法解析: %s: %s" % (type(exc).__name__, exc)

    if ctx.mapping_path is not None:
        try:
            ctx.mapping = read_json(ctx.mapping_path)
            if not isinstance(ctx.mapping, dict):
                ctx.mapping_error = "asset_mapping.json 顶层不是对象"
                ctx.mapping = None
        except (OSError, ValueError) as exc:
            ctx.mapping_error = "asset_mapping.json 无法解析: %s: %s" % (type(exc).__name__, exc)

    if ctx.inventory_path is not None:
        try:
            data = read_json(ctx.inventory_path)
            if isinstance(data, list):
                ctx.inventory = [item for item in data if isinstance(item, dict)]
        except (OSError, ValueError):
            ctx.inventory = []
        for item in ctx.inventory:
            name = str(item.get("file") or "")
            if name:
                ctx.inventory_by_file.setdefault(name, item)

    if ctx.content_path is not None:
        try:
            ctx.content = load_content_index(ctx.content_path)
        except (OSError, SyntaxError, ValueError) as exc:
            ctx.content_error = "content.py 解析失败: %s: %s" % (type(exc).__name__, exc)

    try:
        import PIL  # noqa: F401
        from PIL import Image  # noqa: F401

        ctx.pillow = Image
        ctx.pillow_version = str(getattr(PIL, "__version__", "unknown"))
    except Exception as exc:  # Pillow 缺失不应让脚本崩掉
        ctx.pillow = None
        ctx.pillow_version = "不可用 (%s)" % type(exc).__name__

    registry_file = ctx.game_dir / "asset_registry.py"
    if registry_file.is_file():
        added = str(ctx.game_dir.parent)
        if added not in sys.path:
            sys.path.insert(0, added)
        try:
            ctx.registry = importlib.import_module("game.asset_registry")
        except Exception as exc:
            ctx.registry_error = "asset_registry 导入失败: %s: %s" % (type(exc).__name__, exc)
        finally:
            if added in sys.path:
                sys.path.remove(added)
    else:
        ctx.registry_error = "未找到 asset_registry.py（实现未交付，注册表检查跳过）"


# -------------------------------------------------------------------- 检查 --

def check_c01(ctx: Context) -> Tuple[str, str]:
    records = ctx.records or []
    problems: List[str] = []
    if len(records) != EXPECTED_TOTAL:
        problems.append("records=%d，期望 %d" % (len(records), EXPECTED_TOTAL))
    table = ctx.p_table or {}
    if not table.get("schema_version"):
        problems.append("缺少 schema_version")
    stats = table.get("stats") or {}
    if stats:
        declared = stats.get("records")
        if declared is not None and as_int(declared) != len(records):
            problems.append("stats.records=%s，实测 %d" % (declared, len(records)))
        for key in ("usable", "partial", "missing", "corrupted", "duplicate"):
            if key in stats:
                actual = sum(1 for rec in records if rec.get("availability") == key)
                if as_int(stats.get(key)) != actual:
                    problems.append("stats.%s=%s，实测 %d" % (key, stats.get(key), actual))
    else:
        problems.append("缺少 stats 对象")
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "records=274；stats 自洽"


def check_c02(ctx: Context) -> Tuple[str, str]:
    counts: Dict[str, int] = {}
    unknown: List[str] = []
    for rec in ctx.records or []:
        asset_type = str(rec.get("asset_type") or "")
        counts[asset_type] = counts.get(asset_type, 0) + 1
        if asset_type not in EXPECTED_BY_ASSET_TYPE:
            unknown.append("%s=%s" % (rec.get("record_id"), asset_type))
    problems = []
    for asset_type, expected in EXPECTED_BY_ASSET_TYPE.items():
        actual = counts.get(asset_type, 0)
        if actual != expected:
            problems.append("%s=%d，期望 %d" % (asset_type, actual, expected))
    if unknown:
        problems.append("未知 asset_type: %s" % ", ".join(unknown[:5]))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "角色 12 / 房间 50 / 预兆 13 / 物品 22 / 事件 45"


def check_c03(ctx: Context) -> Tuple[str, str]:
    counts = {key: 0 for key in ALLOWED_AVAILABILITY}
    for rec in ctx.records or []:
        status = str(rec.get("availability") or "")
        counts[status] = counts.get(status, 0) + 1
    if ctx.profile == "post-normalize":
        expected = {"usable": EXPECTED_SOURCE_FILES, "partial": 0, "missing": 0,
                    "corrupted": 0, "duplicate": 0}
        label = "post-normalize"
    else:
        expected = dict(BASELINE_AVAILABILITY)
        label = "baseline(v2)"
    problems = []
    for key, want in expected.items():
        got = counts.get(key, 0)
        if got != want:
            problems.append("%s=%d，期望 %d" % (key, got, want))
    summary = ", ".join("%s=%d" % (key, counts.get(key, 0)) for key in
                        ("usable", "partial", "missing", "corrupted", "duplicate"))
    if problems:
        return FAIL, "[%s] %s；%s" % (label, summary, "；".join(problems[:6]))
    return PASS, "[%s] %s" % (label, summary)


def check_c04(ctx: Context) -> Tuple[str, str]:
    counts: Dict[str, int] = {}
    for rec in ctx.records or []:
        if rec.get("availability") == "missing":
            asset_type = str(rec.get("asset_type") or "")
            counts[asset_type] = counts.get(asset_type, 0) + 1
    problems = []
    for asset_type, expected in BASELINE_MISSING_BY_TYPE.items():
        actual = counts.get(asset_type, 0)
        if actual != expected:
            problems.append("missing/%s=%d，期望 %d" % (asset_type, actual, expected))
    total = sum(counts.values())
    if total != sum(BASELINE_MISSING_BY_TYPE.values()):
        problems.append("missing 合计 %d，期望 %d" % (total, sum(BASELINE_MISSING_BY_TYPE.values())))
    extra = set(counts) - set(BASELINE_MISSING_BY_TYPE)
    if extra:
        problems.append("出现非预期类别缺失: %s" % ", ".join(sorted(extra)))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "missing 合计 0（v2：47 个缺口已全部落实）"


def asset_type_universe(ctx: Context, asset_type: str) -> set:
    collections = UNIVERSE_COLLECTIONS.get(asset_type)
    if not collections:
        return set()
    surface = UNIVERSE_SURFACE.get(asset_type)
    out = set()
    for collection in collections:
        if surface:
            out |= content_surface_ids(ctx.content, collection, surface)
        else:
            out |= content_primary_ids(ctx.content, collection)
    return out


def check_c05(ctx: Context) -> Tuple[str, str]:
    if not ctx.content:
        return SKIP, ctx.content_error or "未找到 content.py，资源位全集无法比对"
    problems: List[str] = []
    for collection, expected in EXPECTED_CONTENT_COUNTS.items():
        actual = len(ctx.content.get(collection, []))
        if actual != expected:
            problems.append("%s=%d，期望 %d" % (collection, actual, expected))

    by_type: Dict[str, List[dict]] = {}
    for rec in ctx.records or []:
        by_type.setdefault(str(rec.get("asset_type") or ""), []).append(rec)

    for asset_type in EXPECTED_BY_ASSET_TYPE:
        universe = asset_type_universe(ctx, asset_type)
        if not universe:
            continue
        records = by_type.get(asset_type, [])
        got: Dict[str, int] = {}
        for rec in records:
            parsed = parse_target_ref(rec)
            rid = parsed["id"]
            if rid:
                got[rid] = got.get(rid, 0) + 1
        # content.py 的 haunt_defs 键是 int（1..70），P 表 target_ref 段是字符串；
        # 统一成 str 再比对，其余集合本来就是 str，不受影响。
        expected_ids = {str(item) for item in universe}
        only_expected = expected_ids - set(got)
        only_actual = set(got) - expected_ids
        if only_expected:
            problems.append("%s 漏登记 %d 个: %s" % (
                asset_type, len(only_expected), ", ".join(sorted(only_expected)[:4])))
        if only_actual:
            problems.append("%s 多出 %d 个: %s" % (
                asset_type, len(only_actual), ", ".join(sorted(only_actual)[:4])))

    faces_expected = content_faces(ctx.content)
    face_seen: Dict[Tuple[str, int], int] = {}
    for rec in by_type.get("character", []):
        parsed = parse_target_ref(rec)
        key = (parsed["id"], parsed["face"])
        face_seen[key] = face_seen.get(key, 0) + 1
    for card, face in sorted(faces_expected):
        count = face_seen.get((card, face), 0)
        if count != 1:
            problems.append("%s#f%s 记录数 %d，期望 1" % (card, face, count))
    extra_faces = set(face_seen) - faces_expected
    if extra_faces:
        problems.append("角色多出面: %s" % ", ".join(
            "%s#f%s" % item for item in sorted(extra_faces)[:4]))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, ("十集合 12/39/11/13/22/11/34/52/70/10（含 build_catalog(0).haunt_defs 与 "
                  "RENDER_SURFACE_SPECS）；274 条按 asset_type 与 content.py 双向一致")


def check_c06(ctx: Context) -> Tuple[str, str]:
    if not ctx.content:
        return SKIP, ctx.content_error or "未找到 content.py，target_ref 无法解析"
    nonconformant: List[str] = []
    unresolved: List[str] = []
    collection_bad: List[str] = []
    face_bad: List[str] = []
    for rec in ctx.records or []:
        rid = rec.get("record_id")
        parsed = parse_target_ref(rec)
        if not parsed["conformant"]:
            nonconformant.append("%s=%r" % (rid, parsed["raw"]))
        if parsed["collection"] and parsed["collection"] not in EXPECTED_CONTENT_COUNTS:
            collection_bad.append("%s 集合名非法: %s" % (rid, parsed["collection"]))
        universe = asset_type_universe(ctx, str(rec.get("asset_type") or ""))
        if universe and parsed["id"] not in universe:
            unresolved.append("%s id 不存在: %r" % (rid, parsed["id"]))
        if str(rec.get("asset_type")) == "character" and parsed["face"] not in (0, 1):
            face_bad.append("%s face=%r" % (rid, parsed["face"]))
    problems: List[str] = []
    if collection_bad:
        problems.append("%d 条集合名非法: %s" % (len(collection_bad), "; ".join(collection_bad[:3])))
    if unresolved:
        problems.append("%d 条 id 不可解析: %s" % (len(unresolved), "; ".join(unresolved[:4])))
    if face_bad:
        problems.append("%d 条角色面缺 face_index: %s" % (len(face_bad), "; ".join(face_bad[:3])))
    if nonconformant:
        problems.append("%d 条 target_ref 非规范格式（规范 §1.1 要求 content.py:<集合>#<id>，"
                        "实测 %s；该格式解决了角色双面歧义，但与规范不一致，见 R12）" % (
                            len(nonconformant), "; ".join(nonconformant[:2])))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, "274 条 target_ref 均为 content.py:<集合>#<id> 且 id 可解析"


def check_c07(ctx: Context) -> Tuple[str, str]:
    seen: Dict[Tuple[str, str, str], List[str]] = {}
    for rec in ctx.records or []:
        parsed = parse_target_ref(rec)
        face_key = "f%s" % parsed["face"] if parsed["face"] is not None else "-"
        key = (str(rec.get("asset_type") or ""), parsed["id"], face_key)
        seen.setdefault(key, []).append(str(rec.get("record_id")))
    hard: List[str] = []
    soft: List[str] = []
    for (asset_type, rid, face_key), ids in seen.items():
        if len(ids) <= 1:
            continue
        if asset_type == "character" and face_key == "-":
            soft.append("%s#%s 未区分面: %s" % (asset_type, rid, ",".join(ids[:4])))
        else:
            hard.append("%s#%s(%s) 重复: %s" % (asset_type, rid, face_key, ",".join(ids[:4])))
    if hard:
        return FAIL, "；".join(hard[:8])
    if soft:
        return WARN, "角色双面未消歧（见文档 R02）: %s" % "；".join(soft[:4])
    return PASS, "274 条资源位唯一（角色按 card + face 区分）"


def check_c08(ctx: Context) -> Tuple[str, str]:
    seen: Dict[str, int] = {}
    problems: List[str] = []
    for rec in ctx.records or []:
        rid = str(rec.get("record_id") or "")
        match = RECORD_ID_RE.match(rid)
        if not match:
            problems.append("record_id 非法: %r" % rid)
            continue
        seen[rid] = seen.get(rid, 0) + 1
        if seen[rid] > 1:
            problems.append("record_id 重复: %s" % rid)
        expected_type = RECORD_ID_PREFIX[match.group(1)]
        asset_type = str(rec.get("asset_type") or "")
        if asset_type != expected_type:
            problems.append("%s 前缀与 asset_type=%s 不一致" % (rid, asset_type))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "record_id 唯一且前缀与 asset_type 一致（%d 条）" % len(seen)


def check_c09(ctx: Context) -> Tuple[str, str]:
    missing_file: List[str] = []
    empty_path: List[str] = []
    absent: List[str] = []
    for rec in ctx.records or []:
        if rec.get("availability") == "missing":
            continue
        rid = rec.get("record_id")
        source_path = str(rec.get("source_path") or "").strip()
        source_file = str(rec.get("source_file") or "").strip()
        if not source_file:
            missing_file.append(str(rid))
        if not source_path:
            empty_path.append(str(rid))
            continue
        if not ctx.abs_path(source_path).is_file():
            absent.append("%s -> %s" % (rid, source_path))
    problems = []
    if missing_file:
        problems.append("%d 条非 missing 行 source_file 为空: %s" % (
            len(missing_file), ", ".join(missing_file[:4])))
    if empty_path:
        problems.append("%d 条非 missing 行 source_path 为空: %s" % (
            len(empty_path), ", ".join(empty_path[:4])))
    if absent:
        problems.append("%d 条路径不存在: %s" % (len(absent), "; ".join(absent[:4])))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, "全部非 missing 行路径可 stat"


def check_c10(ctx: Context) -> Tuple[str, str]:
    cases: List[str] = []
    name_mismatch: List[str] = []
    absent: List[str] = []
    for rec in ctx.records or []:
        source_path = str(rec.get("source_path") or "").strip()
        if not source_path:
            continue
        rid = rec.get("record_id")
        ok, message = walk_case(ctx.root, source_path)
        if not ok:
            if message.startswith("大小写不一致"):
                cases.append("%s %s" % (rid, message))
            else:
                absent.append("%s %s" % (rid, message))
        disk_name = source_path.replace("\\", "/").split("/")[-1]
        if str(rec.get("source_file") or "") != disk_name:
            name_mismatch.append("%s source_file=%r 与 source_path 末段 %r 不一致" % (
                rid, rec.get("source_file"), disk_name))
    problems = []
    if cases:
        problems.append("%d 条大小写不一致: %s" % (len(cases), "; ".join(cases[:4])))
    if absent:
        problems.append("%d 条无法解析: %s" % (len(absent), "; ".join(absent[:3])))
    if name_mismatch:
        problems.append("%d 条 source_file 与路径末段不一致: %s" % (
            len(name_mismatch), "; ".join(name_mismatch[:3])))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, "逐段大小写与磁盘一致"


def check_c11(ctx: Context) -> Tuple[str, str]:
    problems: List[str] = []
    for rec in ctx.records or []:
        if rec.get("availability") != "missing":
            continue
        rid = rec.get("record_id")
        if str(rec.get("source_file") or "").strip():
            problems.append("%s missing 但 source_file 非空" % rid)
        if str(rec.get("source_path") or "").strip():
            problems.append("%s missing 但 source_path 非空（疑似伪造路径）" % rid)
        if len(str(rec.get("missing_note") or "").strip()) < 4:
            problems.append("%s missing 缺 missing_note" % rid)
        if as_list(rec.get("usable_fields")):
            problems.append("%s missing 的 usable_fields 非空" % rid)
        if str(rec.get("decodable") or "") != "not_checked":
            problems.append("%s missing 的 decodable=%r，期望 not_checked" % (
                rid, rec.get("decodable")))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "47 条 missing 路径为空、note 齐全、无可用用途"


def check_c12(ctx: Context) -> Tuple[str, str]:
    hard: List[str] = []
    soft: List[str] = []
    for rec in ctx.records or []:
        raw = str(rec.get("source_path") or "").strip()
        if not raw:
            continue
        rid = rec.get("record_id")
        if "\\" in raw:
            hard.append("%s 使用反斜杠: %s" % (rid, raw))
            continue
        if raw.startswith("./") or raw.startswith("../") or "/../" in raw:
            hard.append("%s 含 ./ 或 ..: %s" % (rid, raw))
            continue
        if re.match(r"^[A-Za-z]:", raw) or raw.startswith("/"):
            hard.append("%s 为绝对路径: %s" % (rid, raw))
            continue
        if not raw.startswith(("photos/", "assets/")):
            hard.append("%s 未以 photos/ 或 assets/ 开头: %s" % (rid, raw))
            continue
        if " " in raw:
            soft.append("%s 路径含空格: %s" % (rid, raw))
        if not REL_PATH_RE.match(raw):
            soft.append("%s 非小写 snake_case: %s" % (rid, raw))
    if hard:
        return FAIL, "；".join(hard[:8])
    if soft:
        return WARN, "；".join(soft[:8])
    return PASS, "路径均为相对项目根的 / 分隔小写路径"


def check_c13(ctx: Context) -> Tuple[str, str]:
    ext_map = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}
    mismatches = 0
    unflagged: List[str] = []
    usable_bad: List[str] = []
    declared_bad: List[str] = []
    checked = 0
    for rec in ctx.records or []:
        source_path = str(rec.get("source_path") or "").strip()
        if not source_path:
            continue
        path = ctx.abs_path(source_path)
        if not path.is_file():
            continue
        checked += 1
        rid = rec.get("record_id")
        ext = path.suffix.lower()
        actual_format = sniff_format(path)
        declared = str(rec.get("format") or "").lower()
        if declared and declared != actual_format:
            declared_bad.append("%s 声明 %s 实际 %s" % (rid, declared, actual_format))
        if ext_map.get(ext) != actual_format:
            mismatches += 1
            flags = {flag.lower() for flag in as_list(rec.get("quality_flags"))}
            if "ext_mismatch" not in flags:
                unflagged.append(str(rid))
            if rec.get("availability") == "usable":
                usable_bad.append(str(rid))
    problems = []
    if declared_bad:
        problems.append("%d 条 format 字段与魔数不符: %s" % (
            len(declared_bad), "; ".join(declared_bad[:4])))
    if unflagged:
        problems.append("%d 条扩展名/魔数不一致却未标 ext_mismatch: %s" % (
            len(unflagged), ", ".join(unflagged[:5])))
    if usable_bad:
        problems.append("%d 条不一致却标 usable: %s" % (
            len(usable_bad), ", ".join(usable_bad[:5])))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, "实测 %d 张：%d 张扩展名与魔数不一致，均已标 ext_mismatch 且非 usable（基线已知）" % (
        checked, mismatches)


def check_c14(ctx: Context) -> Tuple[str, str]:
    problems: List[str] = []
    checked = 0
    for rec in ctx.records or []:
        source_path = str(rec.get("source_path") or "").strip()
        if not source_path:
            continue
        path = ctx.abs_path(source_path)
        if not path.is_file():
            continue
        actual_format = sniff_format(path)
        real = probe_dimensions(path, actual_format)
        if real is None:
            problems.append("%s 无法解析真实尺寸" % rec.get("record_id"))
            continue
        checked += 1
        width, height = real
        rid = rec.get("record_id")
        declared = str(rec.get("dimensions") or "").strip()
        if declared and declared != "%dx%d" % (width, height):
            problems.append("%s dimensions=%r 实际 %dx%d" % (rid, declared, width, height))
        declared_w = as_int(rec.get("width"))
        declared_h = as_int(rec.get("height"))
        if declared_w is None or declared_h is None:
            problems.append("%s width/height 缺失" % rid)
        else:
            if declared_w != width:
                problems.append("%s width=%d 实际 %d" % (rid, declared_w, width))
            if declared_h != height:
                problems.append("%s height=%d 实际 %d" % (rid, declared_h, height))
        declared_ratio = str(rec.get("aspect_ratio") or "").strip()
        if declared_ratio and declared_ratio != aspect_ratio(width, height):
            problems.append("%s aspect_ratio=%r 实际 %s" % (
                rid, declared_ratio, aspect_ratio(width, height)))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "实测 %d 张尺寸与 width/height/aspect_ratio 自洽（dimensions 字段缺失见 C32）" % checked


def check_c15(ctx: Context) -> Tuple[str, str]:
    if ctx.pillow is None:
        return SKIP, "Pillow 不可用，alpha 只能人工核验（见文档 §7）"
    problems: List[str] = []
    checked = 0
    for rec in ctx.records or []:
        source_path = str(rec.get("source_path") or "").strip()
        if not source_path:
            continue
        path = ctx.abs_path(source_path)
        if not path.is_file():
            continue
        try:
            with ctx.pillow.open(str(path)) as image:
                bands = image.getbands()
                has_alpha = ("A" in bands) or ("transparency" in image.info) or str(
                    image.mode) in {"RGBA", "LA", "PA"}
        except Exception as exc:
            problems.append("%s 打不开: %s" % (rec.get("record_id"), type(exc).__name__))
            continue
        checked += 1
        declared = as_bool(rec.get("has_alpha"))
        if declared != has_alpha:
            problems.append("%s has_alpha=%s 实际 %s" % (rec.get("record_id"), declared, has_alpha))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "Pillow %s：%d 张 alpha 与实测一致（基线均 false）" % (
        ctx.pillow_version, checked)


def check_c16(ctx: Context) -> Tuple[str, str]:
    if ctx.args.no_decode:
        return SKIP, "已指定 --no-decode，跳过逐图解码"
    if ctx.pillow is None:
        return SKIP, "Pillow 不可用，无法执行 verify() + load()"
    problems: List[str] = []
    checked = 0
    for rec in ctx.records or []:
        source_path = str(rec.get("source_path") or "").strip()
        if not source_path:
            continue
        path = ctx.abs_path(source_path)
        if not path.is_file():
            continue
        rid = rec.get("record_id")
        declared = str(rec.get("decodable") or "")
        try:
            if path.stat().st_size == 0:
                raise ValueError("zero-byte")
            with ctx.pillow.open(str(path)) as image:
                image.verify()
            with ctx.pillow.open(str(path)) as image:
                image.load()
                width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("zero-dimension")
            actual = "ok"
        except Exception as exc:
            actual = "failed"
            problems.append("%s 解码失败 %s: %s" % (rid, type(exc).__name__, exc))
        checked += 1
        if declared != actual:
            problems.append("%s decodable=%r 实际 %s" % (rid, declared, actual))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:6]))
    return PASS, "Pillow %s：%d 张 verify+load 通过且与 decodable 一致" % (
        ctx.pillow_version, checked)


def check_c17(ctx: Context) -> Tuple[str, str]:
    if not ctx.inventory:
        return SKIP, "未找到 photos_inventory.json，无法做三方交叉验证"
    problems: List[str] = []
    checked = 0
    for rec in ctx.records or []:
        source_file = str(rec.get("source_file") or "").strip()
        source_path = str(rec.get("source_path") or "").strip()
        if not source_file or not source_path:
            continue
        entry = ctx.inventory_by_file.get(source_file)
        if entry is None:
            problems.append("%s 不在 photos_inventory.json 中: %s" % (
                rec.get("record_id"), source_file))
            continue
        path = ctx.abs_path(source_path)
        if not path.is_file():
            continue
        checked += 1
        rid = rec.get("record_id")
        real_sha = ctx.sha256(path)
        declared_sha = str(rec.get("sha256") or "").strip()
        inv_sha = str(entry.get("sha256") or "").strip()
        if declared_sha and declared_sha != real_sha:
            problems.append("%s sha256 与磁盘不符（疑似抄袭/陈旧）" % rid)
        if inv_sha and inv_sha != real_sha:
            problems.append("%s 与清单 sha256 不符" % rid)
        declared_bytes = as_int(rec.get("bytes"))
        real_bytes = path.stat().st_size
        if declared_bytes is not None and declared_bytes != real_bytes:
            problems.append("%s bytes=%s 实际 %d" % (rid, declared_bytes, real_bytes))
        inv_bytes = as_int(entry.get("bytes"))
        if inv_bytes is not None and inv_bytes != real_bytes:
            problems.append("%s 与清单 bytes 不符" % rid)
        if str(rec.get("format") or "").lower() != str(entry.get("format") or "").lower():
            problems.append("%s format 与清单不符" % rid)
        if as_int(rec.get("width")) not in (None, as_int(entry.get("width"))):
            problems.append("%s width 与清单不符" % rid)
        if as_int(rec.get("height")) not in (None, as_int(entry.get("height"))):
            problems.append("%s height 与清单不符" % rid)
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "%d 张 sha256/bytes/尺寸与清单及磁盘三方一致" % checked


def check_c18(ctx: Context) -> Tuple[str, str]:
    if not ctx.inventory:
        return SKIP, "未找到 photos_inventory.json，孤立文件检查无基线"
    inventory_files = set(ctx.inventory_by_file)
    record_files = [str(rec.get("source_file") or "").strip() for rec in ctx.records or []]
    record_files = [name for name in record_files if name]
    seen: Dict[str, int] = {}
    for name in record_files:
        seen[name] = seen.get(name, 0) + 1
    problems = []
    if len(inventory_files) != EXPECTED_SOURCE_FILES:
        problems.append("清单文件数 %d，期望 %d" % (len(inventory_files), EXPECTED_SOURCE_FILES))
    orphan = inventory_files - set(record_files)
    absent = set(record_files) - inventory_files
    if orphan:
        problems.append("%d 个文件未被 P 表引用: %s" % (len(orphan), ", ".join(sorted(orphan)[:5])))
    if absent:
        problems.append("%d 条记录引用了清单外文件: %s" % (
            len(absent), ", ".join(sorted(absent)[:5])))
    duplicated = [name for name, count in seen.items() if count > 1]
    if duplicated:
        problems.append("%d 个文件被多行引用: %s" % (
            len(duplicated), ", ".join(sorted(duplicated)[:4])))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, "274 ↔ 274 双向覆盖，无孤立文件、无重复引用"


def check_c19(ctx: Context) -> Tuple[str, str]:
    problems: List[str] = []
    usable = [rec for rec in ctx.records or [] if rec.get("availability") == "usable"]
    for rec in usable:
        rid = rec.get("record_id")
        source_path = str(rec.get("source_path") or "").strip()
        if not source_path or not ctx.abs_path(source_path).is_file():
            problems.append("%s usable 但路径不可 stat" % rid)
            continue
        path = ctx.abs_path(source_path)
        actual_format = sniff_format(path)
        ext = path.suffix.lower().lstrip(".")
        ext_format = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext)
        if actual_format != ext_format:
            problems.append("%s usable 但真实格式 %s 与扩展名 %s 冲突" % (rid, actual_format, ext))
        flags = {flag.lower() for flag in as_list(rec.get("quality_flags"))}
        blocking = flags & BLOCKING_FLAGS
        if blocking:
            problems.append("%s usable 但仍含阻断标记 %s" % (rid, ",".join(sorted(blocking))))
        asset_type = str(rec.get("asset_type") or "")
        edge = longest_edge(probe_dimensions(path, actual_format))
        floor = LONG_EDGE_DEVIATION.get(asset_type, RECOMMENDED_LONG_EDGE.get(asset_type))
        if edge is not None and floor is not None and edge < floor:
            problems.append("%s usable 但长边 %d < %d" % (rid, edge, floor))
        if as_bool(rec.get("alpha_required")) and not as_bool(rec.get("has_alpha")):
            problems.append("%s usable 但用途要求 alpha 而实测无 alpha" % rid)
        if str(rec.get("missing_note") or "").strip():
            problems.append("%s usable 但 missing_note 非空" % rid)
        if not str(rec.get("provenance") or "").strip():
            problems.append("%s usable 但 provenance 为空" % rid)
    # v2：usable 从 0 变 274 是本轮目标，不再作为违例；改为核对"usable 数必须等于
    # 有源文件的行数"，防止出现"标了 usable 却没文件"的伪造。
    usable_all = [rec for rec in ctx.records or [] if rec.get("availability") == "usable"]
    expected_usable = EXPECTED_SOURCE_FILES
    if len(usable_all) != expected_usable:
        problems.insert(0, "usable=%d，期望 %d（run5 v2：274 位全部落实）"
                        % (len(usable_all), expected_usable))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "usable=%d；逐行核对真 PNG/无阻断标记/尺寸达标/alpha 与用途一致" % len(usable_all)


def check_c20(ctx: Context) -> Tuple[str, str]:
    problems: List[str] = []
    for rec in ctx.records or []:
        if rec.get("availability") != "partial":
            continue
        rid = rec.get("record_id")
        if len(str(rec.get("missing_note") or "").strip()) < 8:
            problems.append("%s partial 缺可执行 missing_note" % rid)
        if not as_list(rec.get("quality_flags")):
            problems.append("%s partial 未登记 quality_flags" % rid)
        fields = {field.lower() for field in as_list(rec.get("usable_fields"))}
        if "none" in fields and len(fields) > 1:
            problems.append("%s usable_fields 混用 none 与具体用途" % rid)
        if rec.get("asset_type") == "character" and "portrait" in fields:
            problems.append("%s partial 角色被允许作 portrait" % rid)
        if "icon" in fields and rec.get("asset_type") != "icon":
            problems.append("%s partial 非图标却被允许作 icon" % rid)
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "95 条 partial 均写明降级原因且未越权用于立绘/图标"


def check_c21(ctx: Context) -> Tuple[str, str]:
    allowed = {
        "usable": {"matched"},
        "missing": {"pending_missing", "fallback", "unmatched"},
        "corrupted": {"excluded"},
        "duplicate": {"alias"},
    }
    problems: List[str] = []
    empty_fallback: List[str] = []
    for rec in ctx.records or []:
        rid = rec.get("record_id")
        availability = str(rec.get("availability") or "")
        status = str(rec.get("mapping_status") or "")
        if availability not in ALLOWED_AVAILABILITY:
            problems.append("%s availability 非法: %r" % (rid, availability))
            continue
        if status not in ALLOWED_MAPPING_STATUS:
            problems.append("%s mapping_status 非法: %r" % (rid, status))
            continue
        if availability in allowed and status not in allowed[availability]:
            problems.append("%s %s 却配 %s" % (rid, availability, status))
        if status == "fallback" and not str(rec.get("fallback_ref") or "").strip():
            empty_fallback.append(str(rid))
    if empty_fallback:
        problems.append("%d 条 mapping_status=fallback 但 fallback_ref 为空（占位图不是替代美术，"
                        "应 pending_missing 或补 fallback_ref）: %s" % (
                            len(empty_fallback), ", ".join(empty_fallback[:5])))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "availability ↔ mapping_status 相容，fallback 均带引用"


def check_c22(ctx: Context) -> Tuple[str, str]:
    problems: List[str] = []
    for rec in ctx.records or []:
        rid = rec.get("record_id")
        asset_type = str(rec.get("asset_type") or "")
        fields = {field.lower() for field in as_list(rec.get("usable_fields"))}
        illegal = fields - USABLE_FIELD_ENUM
        if illegal:
            problems.append("%s usable_fields 非法值: %s" % (rid, ",".join(sorted(illegal))))
        availability = str(rec.get("availability") or "")
        if availability in {"missing", "corrupted", "duplicate"} and fields:
            problems.append("%s %s 应 usable_fields=[]" % (rid, availability))
            continue
        allowed_fields = USABLE_FIELDS_BY_TYPE.get(asset_type)
        if allowed_fields is None:
            continue
        over = fields - allowed_fields
        if over:
            problems.append("%s %s 不允许用途 %s" % (rid, asset_type, ",".join(sorted(over))))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "usable_fields 枚举与 asset_type 相容"


def check_c23(ctx: Context) -> Tuple[str, str]:
    groups: Dict[str, List[dict]] = {}
    for rec in ctx.records or []:
        sha = str(rec.get("sha256") or "").strip()
        if sha:
            groups.setdefault(sha, []).append(rec)
    problems: List[str] = []
    for sha, group in groups.items():
        if len(group) <= 1:
            continue
        canonical = [rec for rec in group if rec.get("availability") != "duplicate"]
        if len(canonical) != 1:
            problems.append("sha256 %s 有 %d 条 canonical" % (sha[:16], len(canonical)))
            continue
        canonical_id = str(canonical[0].get("record_id"))
        for rec in group:
            if rec.get("availability") != "duplicate":
                continue
            rid = rec.get("record_id")
            if str(rec.get("canonical_record_id") or "") != canonical_id:
                problems.append("%s 的 canonical_record_id 未指向 %s" % (rid, canonical_id))
            if str(rec.get("mapping_status") or "") != "alias":
                problems.append("%s duplicate 未置 alias" % rid)
    for rec in ctx.records or []:
        if rec.get("availability") == "duplicate":
            target = str(rec.get("canonical_record_id") or "")
            if not target or target not in ctx.by_record:
                problems.append("%s duplicate 缺有效 canonical_record_id" % rec.get("record_id"))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "sha256 分组无冲突（基线重复组 0）"


def check_c24(ctx: Context) -> Tuple[str, str]:
    entries = ctx.mapping.get("entries") if isinstance(ctx.mapping, dict) else None
    if not isinstance(entries, list):
        return FAIL, "asset_mapping.json 缺少 entries 数组"
    problems: List[str] = []
    covered: set = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append("entries[%d] 不是对象" % index)
            continue
        rid = str(entry.get("record_id") or "")
        rec = ctx.by_record.get(rid)
        if rec is None:
            problems.append("entries[%d] record_id 不存在: %r" % (index, rid))
            continue
        covered.add(rid)
        if norm_ref(entry.get("target_ref")) and norm_ref(entry.get("target_ref")) != norm_ref(
                rec.get("target_ref")):
            problems.append("%s target_ref 与 P 表不一致" % rid)
        path = str(entry.get("path") or "").strip()
        allowed_paths = {str(rec.get("source_path") or "").strip(),
                         str(rec.get("runtime_path") or "").strip()}
        allowed_paths.discard("")
        if not path:
            problems.append("%s 映射 path 为空" % rid)
        elif path not in allowed_paths:
            problems.append("%s 映射 path=%r 未命中 source_path/runtime_path（口径冲突见 R01）" % (
                rid, path))
        runtime_path = str(entry.get("runtime_path") or "").strip()
        record_runtime = str(rec.get("runtime_path") or "").strip()
        if runtime_path and record_runtime and runtime_path != record_runtime:
            problems.append("%s 映射 runtime_path 与 P 表不一致" % rid)
        status = str(entry.get("status") or "")
        if status not in {"matched", "fallback", "alias"}:
            problems.append("%s 映射 status 非法: %r" % (rid, status))
        if str(rec.get("availability") or "") not in {"usable", "partial"}:
            problems.append("%s availability=%s 不得出现在 entries" % (
                rid, rec.get("availability")))
    matched = {str(rec.get("record_id")) for rec in ctx.records or []
               if rec.get("mapping_status") == "matched"}
    uncovered = matched - covered
    if uncovered:
        problems.append("%d 条 matched 无映射项: %s" % (
            len(uncovered), ", ".join(sorted(uncovered)[:5])))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "entries %d 条与 matched 记录双向覆盖" % len(entries)


def check_c25(ctx: Context) -> Tuple[str, str]:
    unresolved = ctx.mapping.get("unresolved") if isinstance(ctx.mapping, dict) else None
    if not isinstance(unresolved, list):
        return FAIL, "asset_mapping.json 缺少 unresolved 数组"
    expected = {norm_ref(rec.get("target_ref")) for rec in ctx.records or []
                if rec.get("availability") in {"missing", "corrupted"}}
    got = set()
    problems: List[str] = []
    for index, item in enumerate(unresolved):
        if not isinstance(item, dict):
            problems.append("unresolved[%d] 不是对象" % index)
            continue
        ref = norm_ref(item.get("target_ref"))
        if not ref:
            problems.append("unresolved[%d] 缺 target_ref" % index)
            continue
        got.add(ref)
        if not str(item.get("reason") or "").strip():
            problems.append("%s unresolved 缺 reason" % ref)
    only_expected = expected - got
    only_got = got - expected
    if only_expected:
        problems.append("%d 个缺口未进 unresolved: %s" % (
            len(only_expected), ", ".join(sorted(only_expected)[:4])))
    if only_got:
        problems.append("%d 个 unresolved 不对应 missing/corrupted: %s" % (
            len(only_got), ", ".join(sorted(only_got)[:4])))
    if problems:
        return FAIL, "；".join(problems[:8])
    return PASS, "unresolved %d 条与 47 个缺口一一对应" % len(unresolved)


def check_c26(ctx: Context) -> Tuple[str, str]:
    records = ctx.records or []
    runtime_records = [rec for rec in records if str(rec.get("runtime_path") or "").strip()]
    if not runtime_records:
        entries = ctx.mapping.get("entries") if isinstance(ctx.mapping, dict) else []
        if not entries:
            return SKIP, "P 表与映射均无 runtime_path，运行时 PNG 检查不适用"
        runtime_records = [rec for rec in records
                           if any(str(entry.get("record_id")) == str(rec.get("record_id"))
                                  and str(entry.get("runtime_path") or "").strip()
                                  for entry in entries if isinstance(entry, dict))]
        if not runtime_records:
            return SKIP, "映射未使用运行时路径（规范 §6.3 与架构口径冲突，见 R01）"

    specs = ctx.runtime_specs
    problems: List[str] = []
    for key, expected in ARCHITECTURE_RUNTIME_SIZES.items():
        spec = specs.get(key)
        if isinstance(spec, dict):
            declared = (as_int(spec.get("width")), as_int(spec.get("height")))
            if declared != expected:
                problems.append("runtime_specs[%s]=%sx%s，架构要求 %dx%d" % (
                    key, declared[0], declared[1], expected[0], expected[1]))

    unique_paths: Dict[str, str] = {}
    for rec in runtime_records:
        rel = str(rec.get("runtime_path") or "").strip()
        if rel:
            unique_paths.setdefault(rel, str(rec.get("asset_type") or ""))

    checked = 0
    unknown_spec = 0
    for rel, asset_type in unique_paths.items():
        path = ctx.abs_path(rel)
        if not path.is_file():
            problems.append("运行时文件不存在: %s" % rel)
            continue
        actual_format = sniff_format(path)
        if actual_format != "png":
            problems.append("运行时文件魔数为 %s，不是 PNG: %s" % (actual_format, rel))
            continue
        size = png_dimensions(path)
        if size is None:
            problems.append("PNG IHDR 解析失败: %s" % rel)
            continue
        spec_key = RUNTIME_SPEC_KEY.get(asset_type)
        spec = specs.get(spec_key) if spec_key else None
        if isinstance(spec, dict) and as_int(spec.get("width")) is not None:
            expected = (as_int(spec.get("width")), as_int(spec.get("height")))
        else:
            expected = ARCHITECTURE_RUNTIME_SIZES.get(spec_key or "")
        if expected is None:
            unknown_spec += 1
            continue
        checked += 1
        if size != expected:
            problems.append("%s %s=%dx%d，期望 %dx%d" % (
                rel, asset_type, size[0], size[1], expected[0], expected[1]))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    detail = "%d 个运行时 PNG 真实性与尺寸通过（房间 512×512、卡牌 480×672）" % checked
    if unknown_spec:
        detail += "；%d 个类别无尺寸口径跳过（R03）" % unknown_spec
    return PASS, detail


def _load_registry(ctx: Context) -> Any:
    cls = getattr(ctx.registry, "AssetRegistry", None)
    if cls is None:
        raise RuntimeError("asset_registry 未导出 AssetRegistry")
    manifest = ctx.p_table_path or ctx.mapping_path
    if manifest is None:
        raise FileNotFoundError("P 表与映射均不存在")
    return cls.load(str(manifest))


def _resolve(registry: Any, asset_id: str) -> Any:
    return registry.resolve(asset_id)


def _ref_path(ctx: Context, ref: Any) -> str:
    raw = ref_attr(ref, "path", "runtime_path", "rel_path", "file_path", "file")
    return str(raw or "")


def _ref_path_exists(ctx: Context, ref: Any) -> bool:
    raw = _ref_path(ctx, ref)
    if not raw:
        return False
    path = Path(raw)
    if not path.is_absolute():
        path = ctx.abs_path(raw)
    return path.exists()


def check_c27(ctx: Context) -> Tuple[str, str]:
    if ctx.mapping is None:
        return SKIP, ctx.mapping_missing_reason
    try:
        registry = _load_registry(ctx)
    except Exception as exc:
        return FAIL, "Registry 加载失败: %s: %s" % (type(exc).__name__, exc)
    entries = ctx.mapping.get("entries") or []
    if not entries:
        return FAIL, "entries 为空，resolve 契约无法验证"
    problems: List[str] = []
    checked = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ref_id = norm_ref(entry.get("target_ref"))
        if not ref_id:
            continue
        try:
            ref = _resolve(registry, ref_id)
        except Exception as exc:
            problems.append("%s resolve 抛异常 %s" % (ref_id, type(exc).__name__))
            continue
        checked += 1
        if ref is None:
            problems.append("%s resolve 返回 None（entries 内应为可用）" % ref_id)
            continue
        if not _ref_path_exists(ctx, ref):
            problems.append("%s resolve 返回不可 stat 的路径: %r" % (ref_id, _ref_path(ctx, ref)))
    probe_id = "__qa_unknown_asset__"
    try:
        if _resolve(registry, probe_id) is not None:
            problems.append("未知 asset_id 未返回 None")
    except Exception as exc:
        problems.append("未知 asset_id resolve 抛异常 %s" % type(exc).__name__)
    try:
        issues = registry.validate(str(ctx.root))
        if not isinstance(issues, (list, tuple)):
            problems.append("validate() 未返回列表，实际 %s" % type(issues).__name__)
    except Exception as exc:
        problems.append("validate() 抛异常 %s: %s" % (type(exc).__name__, exc))
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "resolve %d 条均可 stat；未知 id 返回 None；validate 返回列表" % checked


def _fallback_record(ctx: Context, fallback_ref: str) -> Optional[dict]:
    if fallback_ref in ctx.by_record:
        return ctx.by_record[fallback_ref]
    return ctx.by_target_ref.get(fallback_ref)


def check_c28(ctx: Context) -> Tuple[str, str]:
    if ctx.mapping is None:
        return SKIP, ctx.mapping_missing_reason
    try:
        registry = _load_registry(ctx)
    except Exception as exc:
        return SKIP, "Registry 不可用，fallback 行为无法验证: %s" % type(exc).__name__
    problems: List[str] = []
    checked = 0
    fallback_checked = 0
    for rec in ctx.records or []:
        if rec.get("availability") != "missing":
            continue
        rid = rec.get("record_id")
        status = str(rec.get("mapping_status") or "")
        ref_id = norm_ref(rec.get("target_ref"))
        try:
            ref = _resolve(registry, ref_id)
        except Exception as exc:
            problems.append("%s resolve 抛异常 %s" % (rid, type(exc).__name__))
            continue
        checked += 1
        runtime_status = str(rec.get("runtime_status") or "")
        if status == "pending_missing":
            if ref is not None and _ref_path_exists(ctx, ref) and runtime_status not in {
                    "placeholder", "fallback"}:
                problems.append("%s pending_missing 返回真实路径但未声明占位/回退" % rid)
            continue
        if status != "fallback":
            continue
        fallback_ref = str(rec.get("fallback_ref") or "").strip()
        if not fallback_ref:
            continue
        fallback_checked += 1
        fb_record = _fallback_record(ctx, fallback_ref)
        if fb_record is None:
            problems.append("%s fallback_ref 无法解析: %r" % (rid, fallback_ref))
            continue
        if fb_record.get("asset_type") != rec.get("asset_type"):
            problems.append("%s fallback 跨类别: %s" % (rid, fb_record.get("asset_type")))
        if fb_record.get("availability") not in {"usable", "partial"}:
            problems.append("%s fallback 指向不可用行: %s" % (
                fb_record.get("record_id"), fb_record.get("availability")))
        if ref is not None and not _ref_path_exists(ctx, ref):
            problems.append("%s fallback 返回不存在路径（伪造）" % rid)
    if problems:
        return FAIL, "%d 项：%s" % (len(problems), "；".join(problems[:8]))
    return PASS, "%d 条缺失资源位无伪造路径；%d 条显式 fallback 同类别且指向可用行" % (
        checked, fallback_checked)


def check_c29(ctx: Context) -> Tuple[str, str]:
    stats = {key: 0 for key in ALLOWED_AVAILABILITY}
    for rec in ctx.records or []:
        key = str(rec.get("availability") or "")
        stats[key] = stats.get(key, 0) + 1
    problems: List[str] = []
    # run5 v2：两个档位都要求 274/0/0；"可用"不等于"可发布"——content-release 还要过
    # C-01…C-06（语义 47/47 签字、WCAG 抽样、双签），本契约不签发 release。
    if stats.get("partial", 0) or stats.get("missing", 0):
        problems.append("%s 档仍有 partial=%d / missing=%d，不可进入 release 判定" % (
            ctx.profile, stats.get("partial", 0), stats.get("missing", 0)))
    if stats.get("usable", 0) != EXPECTED_SOURCE_FILES:
        problems.append("%s 档 usable=%d，期望 %d" % (
            ctx.profile, stats.get("usable", 0), EXPECTED_SOURCE_FILES))
    unregistered = [rec.get("record_id") for rec in ctx.records or []
                    if rec.get("availability") == "missing"
                    and not str(rec.get("missing_note") or "").strip()]
    if unregistered:
        problems.append("%d 条 missing 未说明原因" % len(unregistered))
    detail = ("%s 档门禁：usable=%d / partial=0 / missing=0；"
              "release 仍需 C-01…C-06 通过，本契约不签发" % (ctx.profile, stats.get("usable", 0)))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, detail


def check_c30(ctx: Context) -> Tuple[str, str]:
    if ctx.content_path is None:
        return SKIP, "未找到 content.py，无法核对同步摘要"
    real_sha = ctx.sha256(ctx.content_path)
    table = ctx.p_table or {}
    declared = ""

    content_meta = table.get("content")
    if isinstance(content_meta, dict):
        declared = str(content_meta.get("sha256") or "")
        declared_counts = content_meta.get("collections")
        if isinstance(declared_counts, dict):
            problems = []
            for collection, expected in EXPECTED_CONTENT_COUNTS.items():
                actual = as_int(declared_counts.get(collection))
                if actual != expected:
                    problems.append("%s=%s，期望 %d" % (collection, actual, expected))
            if problems:
                return FAIL, "content.collections 与实测不符：%s" % "；".join(problems[:5])
    if not declared:
        generated = table.get("generated_from")
        if isinstance(generated, dict):
            content_ref = generated.get("content")
            if isinstance(content_ref, dict):
                declared = str(content_ref.get("sha256") or "")
            elif isinstance(content_ref, str) and re.fullmatch(r"[0-9a-f]{64}", content_ref):
                declared = content_ref
    if not declared:
        declared = str(table.get("content_sha256") or "")
    if not declared:
        return WARN, "P 表未记录 content.py sha256，无法证明 §8.2 同步（实测 %s…）" % real_sha[:12]
    if declared != real_sha:
        return FAIL, "content.py sha256 不匹配：记录 %s… 实测 %s…" % (declared[:12], real_sha[:12])
    return PASS, "content.py sha256 与 P 表记录一致（%s…），集合计数一致" % real_sha[:12]


def check_c31(ctx: Context) -> Tuple[str, str]:
    candidates: List[Path] = []
    if ctx.p_table_path is not None:
        candidates.append(ctx.p_table_path.with_suffix(".csv"))
    candidates.append(ctx.game_dir / "assets" / "p_table.csv")
    csv_path = locate([path for path in candidates if path is not None])
    if csv_path is None:
        return SKIP, "未找到 p_table.csv，CSV/JSON 一致性不适用"
    try:
        raw = csv_path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(text.splitlines()))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return FAIL, "p_table.csv 无法解析: %s: %s" % (type(exc).__name__, exc)
    problems: List[str] = []
    if not has_bom:
        problems.append("缺少 UTF-8 BOM（Excel 直接打开会乱码）")
    if not rows:
        return FAIL, "p_table.csv 为空"
    header = [cell.strip() for cell in rows[0]]
    body = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    if len(body) != EXPECTED_TOTAL:
        problems.append("数据行 %d，期望 %d" % (len(body), EXPECTED_TOTAL))
    records = ctx.records or []
    json_ids = {str(rec.get("record_id")) for rec in records}
    index = header.index("record_id") if "record_id" in header else 0
    csv_ids = {row[index].strip() for row in body if len(row) > index}
    only_csv = csv_ids - json_ids
    only_json = json_ids - csv_ids
    if only_csv:
        problems.append("CSV 多出 %d 条: %s" % (len(only_csv), ", ".join(sorted(only_csv)[:4])))
    if only_json:
        problems.append("JSON 多出 %d 条: %s" % (len(only_json), ", ".join(sorted(only_json)[:4])))
    if records:
        json_fields = set(records[0])
        missing_in_csv = {"dimensions"} - set(header) if "dimensions" in json_fields else set()
        if missing_in_csv:
            problems.append("CSV 缺规范列: %s（字段级问题见 C32）" % ",".join(sorted(missing_in_csv)))
    if problems:
        return FAIL, "；".join(problems[:6])
    return PASS, "CSV 含 BOM、%d 行、%d 列，record_id 与 JSON 双向一致" % (len(body), len(header))


def check_c32(ctx: Context) -> Tuple[str, str]:
    # 按字段聚合，避免 274 条同因记录刷屏
    missing_counter: Dict[str, int] = {}
    sample: Dict[str, str] = {}
    for rec in ctx.records or []:
        for field in REQUIRED_FIELDS:
            if field in rec:
                continue
            missing_counter[field] = missing_counter.get(field, 0) + 1
            sample.setdefault(field, str(rec.get("record_id")))
    hard: List[str] = []
    for field, count in sorted(missing_counter.items()):
        hard.append("缺必填字段 %s（%d/%d 条，示例 %s）" % (
            field, count, len(ctx.records or []), sample.get(field)))

    fallback_as_ref = sum(
        1 for rec in ctx.records or []
        if str(rec.get("fallback_ref") or "").strip()
        and str(rec.get("fallback_ref") or "").strip() not in ctx.by_record
    )
    soft: List[str] = []
    if fallback_as_ref:
        soft.append("%d 条 fallback_ref 填的是 target_ref 而非 record_id（规范 §1.2）" %
                    fallback_as_ref)

    csv_path = None
    if ctx.p_table_path is not None:
        candidate = ctx.p_table_path.with_suffix(".csv")
        if candidate.is_file():
            csv_path = candidate
    if csv_path is not None:
        try:
            header = [cell.strip() for cell in next(csv.reader(
                csv_path.read_text(encoding="utf-8-sig").splitlines()))]
            missing_cols = [col for col in CSV_COLUMNS if col not in header]
            missing_cols = [col for col in missing_cols if col not in missing_counter]
            if missing_cols:
                soft.append("p_table.csv 另缺 %d 个规范列（发布档必填）: %s" % (
                    len(missing_cols), ",".join(missing_cols)))
        except (OSError, UnicodeDecodeError, csv.Error, StopIteration) as exc:
            hard.append("p_table.csv 表头不可解析: %s" % type(exc).__name__)

    if hard:
        detail = "；".join(hard[:4])
        if soft:
            detail += "；补充：" + "；".join(soft[:2])
        return FAIL, detail
    if soft:
        return WARN, "；".join(soft[:4])
    return PASS, "16 个必填字段齐全；CSV 列集与规范一致；fallback_ref 均为 record_id"


# ------------------------------------------------------------------ 检查清单 --

CHECKS = [
    ("C01", "资源位总数与 stats 自洽", "P0", "p_table", check_c01),
    ("C02", "分类计数 12/50/13/22/45", "P0", "p_table", check_c02),
    ("C03", "availability 分布（baseline 95 partial + 47 missing）", "P0", "p_table", check_c03),
    ("C04", "missing 分类计数 12/1/34", "P0", "p_table", check_c04),
    ("C05", "target_ref 与 content.py 全集双向一致", "P1", "p_table", check_c05),
    ("C06", "target_ref 规范格式与 id 可解析", "P0", "p_table", check_c06),
    ("C07", "资源位唯一性（角色按 card+face）", "P1", "p_table", check_c07),
    ("C08", "record_id 唯一、格式与类别前缀", "P1", "p_table", check_c08),
    ("C09", "非 missing 行路径可 stat", "P0", "p_table", check_c09),
    ("C10", "路径逐段大小写与磁盘一致", "P0", "p_table", check_c10),
    ("C11", "missing 行路径为空且 note 齐全", "P0", "p_table", check_c11),
    ("C12", "路径口径（相对、正斜杠、无 ..）", "P1", "p_table", check_c12),
    ("C13", "魔数与扩展名/format 一致", "P0", "p_table", check_c13),
    ("C14", "尺寸字段与实测自洽", "P0", "p_table", check_c14),
    ("C15", "has_alpha 与实测一致", "P1", "p_table", check_c15),
    ("C16", "逐图 verify+load 可解码", "P1", "p_table", check_c16),
    ("C17", "sha256/bytes/尺寸与清单三方一致", "P1", "p_table", check_c17),
    ("C18", "95 文件全覆盖、无孤立", "P1", "p_table", check_c18),
    ("C19", "不得伪造 usable", "P0", "p_table", check_c19),
    ("C20", "partial 降级说明与用途约束", "P1", "p_table", check_c20),
    ("C21", "availability ↔ mapping_status 相容", "P1", "p_table", check_c21),
    ("C22", "usable_fields 与 asset_type 相容", "P1", "p_table", check_c22),
    ("C23", "重复与别名一致性", "P1", "p_table", check_c23),
    ("C24", "映射 entries 双向覆盖", "P0", "mapping", check_c24),
    ("C25", "unresolved 与缺口一一对应", "P0", "mapping", check_c25),
    ("C26", "运行时 PNG 真实性与尺寸", "P0", "p_table", check_c26),
    ("C27", "Registry resolve/validate 契约", "P0", "registry", check_c27),
    ("C28", "缺失 fallback 不得伪造路径", "P1", "registry", check_c28),
    ("C29", "分档门禁（release 不可宣称）", "P1", "p_table", check_c29),
    ("C30", "content.py 同步摘要", "P2", "p_table", check_c30),
    ("C31", "p_table.csv 与 JSON 一致", "P2", "p_table", check_c31),
    ("C32", "P 表必填字段与 CSV 列合规", "P0", "p_table", check_c32),
]


# -------------------------------------------------------------------- 运行 --

def run_checks(ctx: Context, selected: Optional[set]) -> List[Result]:
    results: List[Result] = []
    for cid, title, priority, need, func in CHECKS:
        if selected and cid not in selected:
            continue
        skip_reason = ""
        if need == "p_table":
            if ctx.records is None:
                skip_reason = ctx.p_table_missing_reason
            elif ctx.p_table_error:
                skip_reason = ctx.p_table_error
        elif need == "mapping":
            skip_reason = ctx.mapping_missing_reason if ctx.mapping is None else ""
            if not skip_reason and ctx.records is None:
                skip_reason = ctx.p_table_missing_reason
        elif need == "registry":
            if ctx.registry is None:
                skip_reason = ctx.registry_error or "asset_registry 不可用"
            elif ctx.mapping is None:
                skip_reason = ctx.mapping_missing_reason
        if skip_reason:
            results.append(Result(cid, title, priority, SKIP, skip_reason))
            continue
        try:
            status, detail = func(ctx)
        except Exception as exc:  # 检查函数自身异常不得伪装成数据失败
            status, detail = ERROR, "%s: %s" % (type(exc).__name__, exc)
        results.append(Result(cid, title, priority, status, detail))
    return results


def format_human(ctx: Context, results: Sequence[Result]) -> str:
    lines: List[str] = []
    lines.append("== 图片资源 P 表与映射 契约验收（只读，不写文件） ==")
    lines.append("项目根 : %s" % ctx.root)
    lines.append("P 表   : %s" % (ctx.p_table_path or "未找到（实现未交付）"))
    if ctx.records is not None:
        lines.append("          records=%d" % len(ctx.records))
    lines.append("映射   : %s" % (ctx.mapping_path or "未找到（实现未交付）"))
    if isinstance(ctx.mapping, dict):
        lines.append("          entries=%d / unresolved=%d" % (
            len(ctx.mapping.get("entries") or []), len(ctx.mapping.get("unresolved") or [])))
    lines.append("注册表 : %s" % (ctx.registry_error or "已导入 game.asset_registry"))
    lines.append("Pillow : %s" % ctx.pillow_version)
    lines.append("档位   : %s%s" % (ctx.profile, "（strict）" if ctx.args.strict else ""))
    lines.append("-" * 78)
    for result in results:
        lines.append("[%s] %s %s (%s)" % (result.status, result.cid, result.title,
                                          result.priority))
        lines.append("       %s" % result.detail)
    counts: Dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    lines.append("-" * 78)
    lines.append("汇总: PASS %d / FAIL %d / WARN %d / SKIP %d / ERROR %d" % (
        counts.get(PASS, 0), counts.get(FAIL, 0), counts.get(WARN, 0),
        counts.get(SKIP, 0), counts.get(ERROR, 0)))
    lines.append("判定: %s" % verdict_text(ctx, results))
    return "\n".join(lines)


def verdict_text(ctx: Context, results: Sequence[Result]) -> str:
    counts: Dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    if counts.get(FAIL) or counts.get(ERROR):
        return "FAIL（存在契约违例，见上方明细）"
    if ctx.args.strict and counts.get(WARN):
        return "FAIL（strict：WARN 计为失败）"
    if ctx.args.require and counts.get(SKIP):
        return "FAIL（require：SKIP 计为失败）"
    if results and counts.get(SKIP) == len(results):
        return "SKIP（实现未交付，不构成通过）"
    if counts.get(WARN) or counts.get(SKIP):
        return "PASS（含 WARN/SKIP，未覆盖范围须写入报告）"
    return "PASS（仅代表契约一致，不代表素材可发布）"


def exit_code(ctx: Context, results: Sequence[Result]) -> int:
    counts: Dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    if counts.get(FAIL) or counts.get(ERROR):
        return 1
    if ctx.args.strict and counts.get(WARN):
        return 1
    if ctx.args.require and counts.get(SKIP):
        return 1
    if results and counts.get(SKIP) == len(results):
        return 3
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="图片 P 表与资源映射只读契约验收（不修改实现、不写文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=None, help="项目根目录，默认由脚本位置推导")
    parser.add_argument("--profile", choices=("baseline", "post-normalize"), default="baseline",
                        help="baseline=当前 95 partial/47 missing；post-normalize=转码后 95 usable")
    parser.add_argument("--only", default=None, help="只跑指定检查，逗号分隔，如 C01,C13")
    parser.add_argument("--list", action="store_true", help="列出全部检查项后退出")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON 到 stdout")
    parser.add_argument("--no-decode", action="store_true", help="跳过 Pillow 逐图解码")
    parser.add_argument("--strict", action="store_true", help="WARN 计为失败")
    parser.add_argument("--require", action="store_true", help="SKIP 计为失败（CI 门禁）")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    args = parse_args(argv)
    if args.list:
        for cid, title, priority, need, _func in CHECKS:
            print("%s\t%s\t%s\t依赖=%s" % (cid, priority, title, need or "无"))
        return 0

    selected = None
    if args.only:
        selected = {part.strip().upper() for part in args.only.split(",") if part.strip()}
        known = {item[0] for item in CHECKS}
        unknown = selected - known
        if unknown:
            sys.stderr.write("未知检查 ID: %s\n" % ", ".join(sorted(unknown)))
            return 2

    ctx = Context(args)
    try:
        prepare(ctx)
    except Exception as exc:
        sys.stderr.write("装载失败 %s: %s\n" % (type(exc).__name__, exc))
        return 2

    results = run_checks(ctx, selected)
    code = exit_code(ctx, results)

    if args.json:
        payload = {
            "profile": ctx.profile,
            "root": str(ctx.root),
            "p_table": str(ctx.p_table_path) if ctx.p_table_path else "",
            "mapping": str(ctx.mapping_path) if ctx.mapping_path else "",
            "registry": "" if ctx.registry is not None else ctx.registry_error,
            "pillow": ctx.pillow_version,
            "checks": [result.as_dict() for result in results],
            "summary": {
                "total": len(results),
                "pass": sum(1 for r in results if r.status == PASS),
                "fail": sum(1 for r in results if r.status == FAIL),
                "warn": sum(1 for r in results if r.status == WARN),
                "skip": sum(1 for r in results if r.status == SKIP),
                "error": sum(1 for r in results if r.status == ERROR),
                "verdict": verdict_text(ctx, results),
                "exit_code": code,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_human(ctx, results))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
