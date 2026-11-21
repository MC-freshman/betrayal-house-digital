#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""现有 142 位 P 表落实 —— 只读独立验收脚本（run5 / 素材层）。

定位
----
本脚本是 **独立验收方**，不是实现方，也不是执行器：

* 只读：只读 JSON/CSV/PNG 头/源码文本，不写任何项目文件、不生成图片、
  不创建 ``__pycache__``（不 import 被测模块，全部用 ``ast.parse`` 静态解析）；
* 不运行 ``verify_assets.py`` / ``asset_pipeline.py`` / ``qa/test_*.py``
  等会写 ``assets/`` 或 ``qa/fixtures/`` 的脚本，因此不会刷新
  ``assets/validation_report.json``；
* 运行前后对 ``source/desktop/game`` 与 ``photos`` 做 mtime/size 快照，
  发现并发写入即把 Q-01 判 FAIL，不把结果当冻结结论。

验收对象
--------
``.codebuddy/wfat/run5_acceptance_criteria.md`` 的 A-29…A-32 与 V05/V11 回归：

* A-29 WW 隔离完整：content.py 回到 142 基线、WW 内容进 content_ww.py 且
  不被导入、placeholders 仅 3 张、haunts 71–120 不进注册表、P 表无 WW 行；
* A-30 47 个缺失位 0 missing：字段齐全、与磁盘事实一致、47 行来源集合与基线
  候选文件集合相等、映射 142/0、孤儿 0、运行时 145 张；
* A-31 130 张 JPEG 转真 PNG：魔数、备份 130 个 .jpg、sha256 链、像素等价、
  inventory v2；
* A-32 142 张成品规格：母版尺寸（分层口径）、运行时尺寸、位深/色彩类型、
  角色真 alpha、M-13 可读性代理、重复 0；
* V05 / V11 回归：以 ``assets/validation_report.json`` 为运行时证据，另做
  独立复算与静态重基线检查（V11 必须以 142 为文件数基线并排除
  ``_source_jpeg``）。

判读纪律
--------
PASS：证据存在、格式合法、数值达标、与当前产物同源。
FAIL：证据存在但不合法/不达标/自相矛盾（例如 content.py 仍有 ROOF_ROOMS、
      photos 里 130 张是 JPEG 却写 .png、V11 仍以 95 为基线）。
NOT_RUN：工作尚未执行或证据文件缺失（例如 content_ww.py 不存在、转码清单
      未落、语义评审未签字）。NOT_RUN 不进通过率分母，绝不折算 PASS。

口径提醒（详见 docs/qa_existing_142.md §1）
-------------------------------------------
* 320²/512²/480×672 是 **运行时** 尺寸；``photos/`` 母版是 2048²/1773×2364，
  母版按 R3 判（房间 ≥1024 且 1:1、卡面长边 ≥1600 且 3:4、角色 320²=D-01）。
  用运行时阈值判母版会制造假 FAIL，本脚本分两层各自断言。
* 本脚本的 scope_claim 只覆盖"WW 隔离 + 142 位素材落实"，不等于
  ``completion_claim@execution`` 或 ``@content-release``。

用法
----
python qa/verify_existing_142.py                 # 人读摘要
python qa/verify_existing_142.py --json          # 机读 JSON（只写 stdout）
python qa/verify_existing_142.py --pixels        # 额外实测 130 张像素等价（慢）
python qa/verify_existing_142.py --no-contrast   # 跳过 M-13 对比度代理
python qa/verify_existing_142.py --root <项目根>

退出码
------
0 PASS；1 FAIL（存在阻断 FAIL）；3 INCOMPLETE（仅 NOT_RUN/CONFLICT）；
2 参数或内部异常。
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import os
import platform
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# 只读：任何导入都不得生成字节码。
sys.dont_write_bytecode = True

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT_RUN"
CONFLICT = "CONFLICT"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_COLOR_RGB = 2
PNG_COLOR_RGBA = 6

SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_GAME_DIR = SCRIPT_PATH.parents[1]
DEFAULT_PROJECT_ROOT = SCRIPT_PATH.parents[4]

EXPECTED_TOTAL = 142
EXPECTED_COLUMNS = 33
EXPECTED_TYPES = {
    "character": 12,
    "room": 50,
    "card_event": 45,
    "card_item": 22,
    "card_omen": 13,
}
# content.py 隔离后应只剩这 7 个集合（ROOF_ROOMS 及 WW 增量全部外迁）。
BASELINE_COLLECTIONS = (
    "CHARACTER_FACES",
    "ROOM_BASES",
    "ROOM_SUPPLEMENTAL_SPECS",
    "OMEN_CARDS",
    "ITEM_CARDS",
    "EVENT_BASES",
    "EVENT_SUPPLEMENTAL_SPECS",
)
# A-29 判据 2：content.py 不得出现的标识符与字符串。
FORBIDDEN_TOKENS = (
    "ROOF_ROOMS",
    "ROOF_ROOM_IDS",
    "FLOOR_ROOF",
    "WW_EVENT_ADDITION",
    "WW_ITEM_ADDITION",
    "WW_OMEN_ADDITION",
    "_roof_room_def",
    "ww_",
    "roof_",
    "widows_walk",
    "content_ww",
)
# A-29-11：除 content_ww.py / 生成脚本 / qa/ 外，生产模块不得再引用这些符号。
FORBIDDEN_SYMBOLS = {
    "ROOF_ROOMS",
    "ROOF_ROOM_IDS",
    "WW_EVENT_ADDITION",
    "WW_EVENT_ADDITIONS",
    "WW_ITEM_ADDITION",
    "WW_ITEM_ADDITIONS",
    "WW_OMEN_ADDITION",
    "WW_OMEN_ADDITIONS",
}
WW_SLOT_TARGETS = {"rooms": 20, "events": 15, "items": 10, "omens": 5}
WW_SLOT_TOTAL = 50

RUNTIME_SIZE = {
    "character": (320, 320),
    "room": (512, 512),
    "card_event": (480, 672),
    "card_item": (480, 672),
    "card_omen": (480, 672),
}
# photos/ 子目录名（角色母版放在 role/，与 P 表 category_dir=char 不同名）。
PHOTOS_SUBDIR = {
    "character": "role",
    "room": "room",
    "card_event": "event",
    "card_item": "item",
    "card_omen": "omen",
}
CATEGORY_DIR = {
    "character": "char",
    "room": "room",
    "card_event": "event",
    "card_item": "item",
    "card_omen": "omen",
}
BACKUP_DIRNAME = "_source_jpeg"
BACKUP_EXPECTED = {"room": 50, "event": 45, "item": 22, "omen": 13}
PLACEHOLDER_FILES = {"character_missing.png", "room_missing.png", "event_missing.png"}

# M-13 原图层可读性代理阈值（run5 §2.5）。
M13_SPREAD_MIN = 0.10
M13_MEAN_MIN = 0.05
M13_MEAN_MAX = 0.92
M13_EXTREME_MAX = 0.25


# ---------------------------------------------------------------------------
# 基础工具（全部只读）
# ---------------------------------------------------------------------------

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_info(path):
    """只读 PNG 头，返回 (width, height, bit_depth, color_type)；非 PNG 返回 None。"""
    try:
        with open(path, "rb") as handle:
            head = handle.read(33)
    except OSError:
        return None
    if len(head) < 33 or head[:8] != PNG_MAGIC or head[12:16] != b"IHDR":
        return None
    return (
        int.from_bytes(head[16:20], "big"),
        int.from_bytes(head[20:24], "big"),
        head[24],
        head[25],
    )


def png_size(path):
    info = png_info(path)
    return (info[0], info[1]) if info else None


def has_png_magic(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(8) == PNG_MAGIC
    except OSError:
        return False


def has_jpeg_magic(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(3) == JPEG_MAGIC
    except OSError:
        return False


def read_text(path):
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def norm(value):
    """CSV 字符串与 JSON 原生值归一到同一比较口径（与 verify_assets._norm 同义）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return str(value)


def case_consistent(root, rel_path):
    """逐段比对磁盘真实名称（Windows 大小写不敏感，发布端敏感）。"""
    current = Path(root)
    for part in str(rel_path).replace("\\", "/").split("/"):
        if not part:
            continue
        try:
            entries = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in entries:
            return False
        current = current / part
    return True


def rollup(statuses):
    if any(status == FAIL for status in statuses):
        return FAIL
    if any(status == CONFLICT for status in statuses):
        return CONFLICT
    if any(status == NOT_RUN for status in statuses):
        return NOT_RUN
    return PASS


# ---------------------------------------------------------------------------
# 静态源码解析（ast，不执行、不导入）
# ---------------------------------------------------------------------------

def parse_module(path):
    """返回 (tree, text)；解析失败返回 (None, text)。"""
    text = read_text(path)
    if not text:
        return None, ""
    try:
        return ast.parse(text, filename=str(path)), text
    except SyntaxError:
        return None, text


def top_level_list(tree, name):
    if tree is None:
        return None
    for node in tree.body:
        targets = []
        value = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        if name in targets and isinstance(value, (ast.List, ast.Tuple)):
            return value
    return None


def top_level_names(tree):
    names = set()
    if tree is None:
        return names
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def kwarg(call, name):
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def element_id(elt, fn_hooks):
    """从一个集合元素里取出资源 id；无法静态判定返回 None。"""
    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
        return elt.value
    if isinstance(elt, ast.Tuple) and elt.elts:
        first = elt.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None
    if isinstance(elt, ast.Call):
        fname = getattr(elt.func, "id", None) or getattr(elt.func, "attr", None)
        if fname in fn_hooks:
            return fn_hooks[fname](elt)
        for key in ("card_id", "room_id", "id", "slot_id"):
            value = kwarg(elt, key)
            if isinstance(value, str):
                return value
    return None


def collection_ids(tree, name):
    """返回 (ids, error)。ids 顺序保持源码顺序；出现不可解析元素时 error 非空。"""
    node = top_level_list(tree, name)
    if node is None:
        return None, "集合 %s 不是顶层字面量列表（无法静态计数）" % name

    def _character_face(call):
        card_id = kwarg(call, "card_id")
        face_index = kwarg(call, "face_index")
        if isinstance(card_id, str) and face_index is not None:
            return "%s_%s" % (card_id, face_index)
        return None

    hooks = {"character_face": _character_face}
    ids = []
    for elt in node.elts:
        ids.append(element_id(elt, hooks))
    if any(item is None for item in ids):
        return None, "集合 %s 存在不可静态解析的元素（%d/%d）" % (
            name, sum(1 for item in ids if item is None), len(ids)
        )
    return ids, ""


def dict_list_ids(tree, name, key="id"):
    node = top_level_list(tree, name)
    if node is None:
        return None, "集合 %s 不存在或不是顶层字面量列表" % name
    ids = []
    for elt in node.elts:
        if isinstance(elt, ast.Dict):
            value = None
            for k, v in zip(elt.keys, elt.values):
                if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Constant):
                    value = v.value
                    break
            ids.append(value)
        else:
            ids.append(None)
    if any(item is None for item in ids):
        return None, "集合 %s 存在缺少 %r 键的元素" % (name, key)
    return ids, ""


def int_tuple_ids(tree, name):
    node = top_level_list(tree, name)
    if node is None:
        return None, "集合 %s 不存在" % name
    ids = []
    for elt in node.elts:
        if isinstance(elt, ast.Tuple) and elt.elts:
            first = elt.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, int):
                ids.append(first.value)
                continue
        ids.append(None)
    if any(item is None for item in ids):
        return None, "集合 %s 存在不可解析元素" % name
    return ids, ""


def string_constants(tree):
    values = set()
    if tree is None:
        return values
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.add(node.value)
    return values


def docstring_node_ids(tree):
    """模块/类/函数 docstring 的 id 集合：它们不是"字符串常量"，不得计入禁用词扫描。"""
    ids = set()
    if tree is None:
        return ids
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def haunt_ids(tree):
    """聚合所有 HAUNT 命名的 (int, str) 列表 id。

    兼容 `HAUNT_NAMES = list(BASE_HAUNT_NAMES) + list(WW_HAUNT_NAMES)` 的拼接写法：
    字面量列表逐个解析，拼接口径按"所有 HAUNT 列表的并集"统计。
    """
    ids = []
    for name in top_level_names(tree):
        if "HAUNT" not in name.upper():
            continue
        node = top_level_list(tree, name)
        if node is None:
            continue
        got, _err = int_tuple_ids(tree, name)
        if got:
            ids.extend(got)
    return sorted(set(ids))


def imported_modules(tree):
    """收集 import 的模块名（含 importlib.import_module 的字符串字面量）。"""
    names = set()
    if tree is None:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
            for alias in node.names:
                names.add("%s.%s" % (module, alias.name) if module else alias.name)
        elif isinstance(node, ast.Call):
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fn in ("import_module", "__import__", "find_spec"):
                if node.args and isinstance(node.args[0], ast.Constant):
                    value = node.args[0].value
                    if isinstance(value, str):
                        names.add(value)
    return names


def referenced_names(tree):
    names = set()
    if tree is None:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def iter_py_files(base, skip_dirs=("__pycache__", ".git", "node_modules", "archive", "fixtures")):
    found = []
    if not base.exists():
        return found
    for dirpath, dirnames, filenames in os.walk(str(base)):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if name.endswith(".py"):
                found.append(Path(dirpath) / name)
    return sorted(found)


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------

class Ctx(object):
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.game = self.root / "source" / "desktop" / "game"
        self.qa = self.game / "qa"
        self.assets = self.game / "assets"
        self.photos = self.root / "photos"
        self.wfat = self.root / ".codebuddy" / "wfat"
        self.paths = {
            "p_table": self.assets / "p_table.json",
            "p_table_csv": self.assets / "p_table.csv",
            "mapping": self.assets / "asset_mapping.json",
            "validation_report": self.assets / "validation_report.json",
            "content": self.game / "content.py",
            "content_ww": self.game / "content_ww.py",
            "pipeline": self.game / "asset_pipeline.py",
            "registry": self.game / "asset_registry.py",
            "haunts_init": self.game / "haunts" / "__init__.py",
            "verify_assets": self.game / "verify_assets.py",
            "inventory": self.wfat / "photos_inventory.json",
            "boundary": self.wfat / "run5_boundary_audit.json",
            "promotion_map": self.qa / "run5_promotion_map.json",
            "semantic_review": self.qa / "run5_semantic_review.jsonl",
            "transcode_manifest": self.qa / "run5_transcode_manifest.json",
            "baseline_diff": self.qa / "run5_baseline_diff.json",
            "size_report": self.qa / "run5_size_report.json",
            "freeze_dir": self.root / "_freeze",
        }
        self.data = {}
        self.errors = {}
        self._hash_cache = {}
        self.load()

    def rel(self, path):
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except (ValueError, OSError):
            return str(path).replace("\\", "/")

    def load_json(self, key):
        path = self.paths[key]
        if not path.exists():
            self.data[key] = None
            self.errors[key] = "missing: %s" % self.rel(path)
            return
        try:
            self.data[key] = json.loads(path.read_text(encoding="utf-8-sig"))
            self.errors[key] = ""
        except Exception as exc:  # noqa: BLE001 - 证据损坏必须显式暴露
            self.data[key] = None
            self.errors[key] = "%s: %s" % (self.rel(path), exc)

    def load(self):
        for key in ("p_table", "mapping", "validation_report", "inventory",
                    "boundary", "promotion_map", "transcode_manifest",
                    "baseline_diff", "size_report"):
            self.load_json(key)
        csv_path = self.paths["p_table_csv"]
        self.data["csv_rows"] = []
        self.data["csv_header"] = []
        self.data["csv_bom"] = False
        if csv_path.exists():
            raw = csv_path.read_bytes()
            self.data["csv_bom"] = raw.startswith(b"\xef\xbb\xbf")
            try:
                reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
                self.data["csv_header"] = list(reader.fieldnames or [])
                self.data["csv_rows"] = [dict(row) for row in reader]
            except Exception as exc:  # noqa: BLE001
                self.errors["p_table_csv"] = "解析失败：%s" % exc

    def records(self):
        return (self.data.get("p_table") or {}).get("records") or []

    def record_map(self):
        return {r.get("record_id"): r for r in self.records()}

    def stats(self):
        return (self.data.get("p_table") or {}).get("stats") or {}

    def hash_of(self, path):
        key = str(path)
        if key not in self._hash_cache:
            try:
                self._hash_cache[key] = sha256_file(path)
            except OSError:
                self._hash_cache[key] = ""
        return self._hash_cache[key]

    def photos_files(self):
        """photos/ 下母版文件（递归），排除 _source_jpeg 备份目录。"""
        out = []
        if not self.photos.exists():
            return out
        for dirpath, dirnames, filenames in os.walk(str(self.photos)):
            dirnames[:] = [d for d in dirnames if d != BACKUP_DIRNAME]
            for name in filenames:
                out.append(Path(dirpath) / name)
        return sorted(out)

    def backup_files(self):
        base = self.photos / BACKUP_DIRNAME
        if not base.exists():
            return []
        return sorted(p for p in base.rglob("*") if p.is_file())

    def baseline_missing_ids(self):
        audit = self.data.get("boundary") or {}
        section = audit.get("2_missing_47") or {}
        items = section.get("items") or []
        return {item.get("record_id") for item in items if item.get("record_id")}

    def baseline_orphan_paths(self):
        audit = self.data.get("boundary") or {}
        section = audit.get("4_orphan_47") or {}
        items = section.get("items") or []
        return {
            str(item.get("path") or "").replace("\\", "/")
            for item in items if item.get("path")
        }

    def baseline_ww_ids(self):
        """WW 基线 id 集合：优先 run5_boundary_audit §1 的 ww_only，其次 S0 归档。"""
        audit = self.data.get("boundary") or {}
        ww_only = ((audit.get("1_ww_boundary") or {}).get("ww_only") or {})
        groups = {
            "rooms": list(ww_only.get("ww_only_rooms") or []),
            "events": list(ww_only.get("ww_only_events") or []),
            "items": list(ww_only.get("ww_only_items") or []),
            "omens": list(ww_only.get("ww_only_omens") or []),
        }
        if all(groups.values()):
            groups["haunts"] = [str(n) for n in range(71, 121)]
            return groups, "run5_boundary_audit.json §1 ww_only"
        archive = self.paths["freeze_dir"] / "content_pre_run5.py"
        if archive.exists():
            tree, _ = parse_module(archive)
            derived = {}
            for name, key in (
                ("ROOF_ROOMS", "rooms"),
                ("EVENT_SUPPLEMENTAL_SPECS", "events"),
                ("ITEM_CARDS", "items"),
                ("OMEN_CARDS", "omens"),
            ):
                ids, _err = collection_ids(tree, name)
                if not ids:
                    ids, _err = dict_list_ids(tree, name)
                derived[key] = list(ids or [])
            if all(derived.values()):
                derived["haunts"] = [str(n) for n in range(71, 121)]
                return derived, "S0 归档 %s" % self.rel(archive)
        return None, "缺少 WW 基线（run5_boundary_audit.json §1 与 _freeze/content_pre_run5.py 均不可用）"

    def scope_rows(self):
        """142 位基线范围内的 P 表行。

        越界（WW 行混入 P 表）由 A-29-10 单点判 FAIL；A-30/A-31/A-32 只判
        142 位本身，避免同一缺陷被重复计数，也避免把 WW 行的缺图误报成
        "母版缺失"噪声。无法取得 WW 基线时退化为全表并置空 scope 说明。
        """
        rows = self.records()
        baseline, _source = self.baseline_ww_ids()
        ww_ids = set()
        if baseline:
            for key in ("rooms", "events", "items", "omens"):
                ww_ids.update(str(item) for item in baseline.get(key) or [])
        out = []
        for row in rows:
            ref = str(row.get("content_ref") or "")
            collection, cid = "", ""
            if ref.startswith("content.py:"):
                collection, _, cid = ref[len("content.py:"):].partition("#")
            if collection == "ROOF_ROOMS":
                continue
            if cid and cid in ww_ids:
                continue
            out.append(row)
        return out

    def scope_note(self):
        total = len(self.records())
        scoped = len(self.scope_rows())
        if total == scoped:
            return ""
        return "（已排除 %d 行 WW 越界行，越界判定见 A-29-10）" % (total - scoped)


class Audit(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.checks = []
        self._by_id = {}

    def add(self, cid, gate, title, status, detail, evidence=None, advisory=False):
        item = {
            "id": cid,
            "gate": gate,
            "title": title,
            "status": status,
            "detail": detail,
            "evidence": list(evidence or []),
            "advisory": bool(advisory),
        }
        self.checks.append(item)
        self._by_id[cid] = item
        return item

    def run(self, cid, gate, title, fn, **kwargs):
        try:
            status, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001 - 单项异常不得吞掉
            status = FAIL
            detail = "检查内部异常：%s" % exc
            evidence = [traceback.format_exc(limit=4)]
        return self.add(cid, gate, title, status, detail, evidence, **kwargs)

    def statuses(self):
        return {c["id"]: c["status"] for c in self.checks}

    def blocking(self):
        return [c for c in self.checks if not c["advisory"]]


GATES = {
    "G1": ("WW 边界与隔离（A-29）", [
        "A-29-01", "A-29-02", "A-29-03", "A-29-04", "A-29-05", "A-29-06",
        "A-29-07", "A-29-08", "A-29-09", "A-29-10", "A-29-11", "A-29-12",
    ]),
    "G2": ("47 位登记与 0 missing（A-30）", [
        "A-30-01", "A-30-02", "A-30-03", "A-30-04", "A-30-05", "A-30-06",
        "A-30-07", "A-30-08", "A-30-09", "A-30-10", "A-30-11",
    ]),
    "G3": ("130 张转码（A-31）", [
        "A-31-01", "A-31-02", "A-31-03", "A-31-04", "A-31-05", "A-31-06", "A-31-07",
    ]),
    "G4": ("142 张成品规格（A-32）", [
        "A-32-01", "A-32-02", "A-32-03", "A-32-04", "A-32-05", "A-32-06", "A-32-07",
    ]),
    "G5": ("V05 / V11 回归", ["V-05", "V-11", "V-17"]),
    "G6": ("只读与证据", ["Q-01", "Q-02"]),
}

TITLES = {
    "A-29-01": "content.py 七集合与 P 表逐项相等（142 基线）",
    "A-29-02": "content.py 无 WW 标识符/字符串残留",
    "A-29-03": "content.py 剧本标题 1–70（HAUNT_NAMES=70）",
    "A-29-04": "content_ww.py 存在、可编译、50 槽齐全",
    "A-29-05": "WW 内容保全（id 集合与基线相等）",
    "A-29-06": "全仓静态导入 content_ww = 0 次",
    "A-29-07": "运行时 content_ww 不在 sys.modules",
    "A-29-08": "placeholders 仅 3 张，assets/ 无 ww_* 运行时图",
    "A-29-09": "haunts 71–120 不进活动目录与注册表（70 本）",
    "A-29-10": "P 表无 WW 行、无 WW 前缀 id",
    "A-29-11": "生产模块无 ROOF_ROOMS / WW_*_ADDITION 符号引用",
    "A-29-12": "source/miniprogram 全树 sha256 不变",
    "A-30-01": "availability missing = 0（表/stats/CSV 三方一致）",
    "A-30-02": "partial/corrupted/duplicate/placeholder/fallback/pending = 0",
    "A-30-03": "47 行字段齐全且与磁盘事实一致",
    "A-30-04": "47 行来源集合 == 基线 47 个候选文件集合",
    "A-30-05": "CSV/JSON 142×33 逐字段等价",
    "A-30-06": "映射 142 entries / 0 unresolved，path==source_path",
    "A-30-07": "孤儿 0、sha256 重复 0、占位图未被占用",
    "A-30-08": "运行时 50/80/12/3 = 145 且 IHDR 正确",
    "A-30-09": "47 行提升台账 run5_promotion_map.json",
    "A-30-10": "语义评审 47/47 签字",
    "A-30-11": "重基线 diff 表 run5_baseline_diff.json",
    "A-31-01": "142/142 真 PNG 魔数 + 扩展名一致 + format=png",
    "A-31-02": "备份 130 个 .jpg 按类别落位",
    "A-31-03": "备份 sha256 与 provenance/manifest 一致",
    "A-31-04": "像素等价 max diff 0 / MAD 0",
    "A-31-05": "photos_inventory v2 = 142 条、0 漂移",
    "A-31-06": "运行时图与转码前视觉一致（≤2）",
    "A-31-07": "体积与打包影响已登记（P-19）",
    "A-32-01": "母版尺寸/比例（房间 ≥1024 1:1、卡面长边 ≥1600 3:4、角色 320²）",
    "A-32-02": "运行时尺寸精确 512²/480×672/320²（142/142）",
    "A-32-03": "PNG 位深 8 且色彩类型正确（2/6）",
    "A-32-04": "角色真 alpha + has_alpha/alpha_required 一致",
    "A-32-05": "M-13 可读性代理 142/142",
    "A-32-06": "sha256 重复 0 + provenance 可追溯",
    "A-32-07": "渲染层 WCAG 抽样 ≥20",
    "V-05": "V05 回归：7 集合双向可解析（运行时 + 静态）",
    "V-11": "V11 回归：142 文件基线 + 排除 _source_jpeg + 0 哈希漂移",
    "V-17": "verify_assets 17/17 同源",
    "Q-01": "验收期间零写入",
    "Q-02": "输入证据清单与哈希",
    "Q-03": "（咨询）旧 95/47 基线常量是否全部升级",
}


# ---------------------------------------------------------------------------
# A-29 WW 边界与隔离
# ---------------------------------------------------------------------------

def check_a29_01(ctx):
    tree, text = parse_module(ctx.paths["content"])
    if tree is None:
        return FAIL, "content.py 缺失或语法不可解析（%s）" % ctx.rel(ctx.paths["content"]), []
    expected = defaultdict(set)
    for row in ctx.records():
        ref = str(row.get("content_ref") or "")
        if not ref.startswith("content.py:"):
            continue
        collection, _, cid = ref[len("content.py:"):].partition("#")
        expected[collection].add(cid)
    if not expected:
        return NOT_RUN, "P 表没有可解析的 content_ref，无法做集合比对", []

    problems = []
    actual_by_collection = {}
    for name in BASELINE_COLLECTIONS:
        ids, err = collection_ids(tree, name)
        if err:
            problems.append(err)
            continue
        actual_by_collection[name] = ids
        if len(ids) != len(set(ids)):
            problems.append("%s 存在重复 id" % name)
        missing = expected.get(name, set()) - set(ids)
        extra = set(ids) - expected.get(name, set())
        if missing:
            problems.append("%s 缺 P 表引用的 id %d 个（如 %s）"
                            % (name, len(missing), sorted(missing)[:3]))
        if extra:
            problems.append("%s 多出 P 表未引用的 id %d 个（如 %s）"
                            % (name, len(extra), sorted(extra)[:3]))
    # 分类计数
    by_type = {}
    if all(name in actual_by_collection for name in BASELINE_COLLECTIONS):
        by_type = {
            "character": len(actual_by_collection["CHARACTER_FACES"]),
            "room": len(actual_by_collection["ROOM_BASES"]) + len(actual_by_collection["ROOM_SUPPLEMENTAL_SPECS"]),
            "card_event": len(actual_by_collection["EVENT_BASES"]) + len(actual_by_collection["EVENT_SUPPLEMENTAL_SPECS"]),
            "card_item": len(actual_by_collection["ITEM_CARDS"]),
            "card_omen": len(actual_by_collection["OMEN_CARDS"]),
        }
        for key, want in EXPECTED_TYPES.items():
            if by_type.get(key) != want:
                problems.append("%s=%r，期望 %d" % (key, by_type.get(key), want))
        total = sum(by_type.values())
        if total != EXPECTED_TOTAL:
            problems.append("集合合计=%d，期望 %d" % (total, EXPECTED_TOTAL))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "content.py = 12/50/45/22/13 = 142，且与 P 表 content_ref 双向相等", []


def check_a29_02(ctx):
    """只扫 AST 标识符与"字符串常量"（排除 docstring）；注释里提到 content_ww.py 不算残留。"""
    tree, text = parse_module(ctx.paths["content"])
    if tree is None:
        return FAIL, "content.py 不可读或不可解析", []
    problems = []
    names = top_level_names(tree) | referenced_names(tree)
    name_hits = sorted(
        (names & FORBIDDEN_SYMBOLS)
        | {n for n in names if n in ("FLOOR_ROOF", "ROOF_ROOM_IDS", "_roof_room_def")}
    )
    if name_hits:
        problems.append("标识符命中 %s" % ",".join(name_hits))
    docs = docstring_node_ids(tree)
    token_hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docs:
            continue
        for token in FORBIDDEN_TOKENS:
            if token in node.value:
                token_hits.append("%s@L%d" % (token, getattr(node, "lineno", 0)))
    if token_hits:
        problems.append("字符串常量命中 %s" % ",".join(sorted(set(token_hits))[:6]))
    if problems:
        return FAIL, "仍有 WW 残留：" + "；".join(problems), problems
    return PASS, ("content.py AST 0 命中：标识符 0、字符串常量 0（docstring/注释中的"
                  "\"已隔离到 content_ww.py\" 说明不计）"), []


def check_a29_03(ctx):
    tree, _text = parse_module(ctx.paths["content"])
    if tree is None:
        return FAIL, "content.py 不可解析", []
    if "HAUNT_NAMES" not in top_level_names(tree):
        return NOT_RUN, ("content.py 无 HAUNT_NAMES；若剧本 1–70 标题已迁至 haunts/ 或 "
                         "registry，请提供回读证据后改判"), []
    ids, err = int_tuple_ids(tree, "HAUNT_NAMES")
    if err:
        return FAIL, err, []
    if len(ids) != 70 or set(ids) != set(range(1, 71)):
        bad = sorted(set(ids) - set(range(1, 71)))[:5]
        return FAIL, "HAUNT_NAMES=%d 条，期望 70 条（1–70）；越界 id 示例 %s" % (len(ids), bad), []
    return PASS, "HAUNT_NAMES 70 条，id 集合 = 1..70，无 71–120", []


def check_a29_04(ctx):
    path = ctx.paths["content_ww"]
    if not path.exists():
        return FAIL, ("content_ww.py 不存在（%s）：WW 内容未隔离也未保全，S1 未执行"
                      % ctx.rel(path)), []
    text = read_text(path)
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        return FAIL, "content_ww.py 语法错误：%s" % exc, []
    tree, _ = parse_module(path)
    names = top_level_names(tree)
    problems = []
    rooms, err = dict_list_ids(tree, "ROOF_ROOMS")
    if err:
        problems.append(err)
    elif len(rooms) != WW_SLOT_TARGETS["rooms"]:
        problems.append("ROOF_ROOMS=%d，期望 20" % len(rooms))
    if "FLOOR_ROOF" not in names:
        problems.append("缺少 FLOOR_ROOF")

    def _size(full_name, ww_name, want_full, want_add):
        if ww_name in names:
            ids, err_ = collection_ids(tree, ww_name) if ww_name != "ROOF_ROOMS" else dict_list_ids(tree, ww_name)
            if err_:
                return None, err_
            return len(ids), ""
        if full_name in names:
            ids, err_ = collection_ids(tree, full_name)
            if err_:
                return None, err_
            return len(ids), ""
        return None, "缺少 %s 或 %s" % (ww_name, full_name)

    events, err = _size("EVENT_SUPPLEMENTAL_SPECS", "WW_EVENT_ADDITIONS", 49, 15)
    if err:
        problems.append("事件：%s" % err)
    elif events not in (15, 49):
        problems.append("事件增量=%d，期望 15（或全量 49）" % events)
    items, err = _size("ITEM_CARDS", "WW_ITEM_ADDITIONS", 32, 10)
    if err:
        problems.append("物品：%s" % err)
    elif items not in (10, 32):
        problems.append("物品增量=%d，期望 10（或全量 32）" % items)
    omens, err = _size("OMEN_CARDS", "WW_OMEN_ADDITIONS", 18, 5)
    if err:
        problems.append("预兆：%s" % err)
    elif omens not in (5, 18):
        problems.append("预兆增量=%d，期望 5（或全量 18）" % omens)
    haunt_list = haunt_ids(tree)
    haunts = len(haunt_list) if haunt_list else None
    if haunts is None:
        problems.append("缺少 HAUNT_NAMES 系列（或不可静态解析）")
    elif haunts not in (50, 120):
        problems.append("HAUNT_NAMES 合计=%r，期望 50（仅 WW）或 120（全量）" % haunts)

    slots = None
    if not problems:
        slot_events = 15 if events == 15 else (events - 34 if events else 0)
        slot_items = 10 if items == 10 else (items - 22 if items else 0)
        slot_omens = 5 if omens == 5 else (omens - 13 if omens else 0)
        slots = len(rooms) + slot_events + slot_items + slot_omens
        if slots != WW_SLOT_TOTAL:
            problems.append("WW 槽位合计=%d，期望 50（20+15+10+5）" % slots)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, ("content_ww.py 可编译：ROOF_ROOMS 20 / 事件 %d / 物品 %d / 预兆 %d / "
                  "剧本 %d；50 槽齐全" % (events, items, omens, haunts)), []


def check_a29_05(ctx):
    path = ctx.paths["content_ww"]
    if not path.exists():
        return FAIL, "content_ww.py 不存在，WW 内容保全无从核对", []
    tree, _text = parse_module(path)
    if tree is None:
        return FAIL, "content_ww.py 不可解析", []
    baseline, source = ctx.baseline_ww_ids()
    if not baseline:
        return NOT_RUN, source, []
    consts = string_constants(tree)
    problems = []
    for key in ("rooms", "events", "items", "omens"):
        ids = [str(item) for item in baseline.get(key) or []]
        if not ids:
            problems.append("基线 %s 为空" % key)
            continue
        missing = [item for item in ids if item not in consts]
        if missing:
            problems.append("%s 丢失 %d 个（如 %s）" % (key, len(missing), missing[:3]))
    haunts = [int(item) for item in (baseline.get("haunts") or []) if str(item).isdigit()]
    if haunts:
        declared = haunt_ids(tree)
        if declared:
            lost = sorted(set(haunts) - set(declared))
            if lost:
                problems.append("剧本号丢失 %d 个（如 %s）" % (len(lost), lost[:3]))
        else:
            problems.append("content_ww 中 HAUNT 系列不可静态解析（期望包含 71–120）")
    if problems:
        return FAIL, "基线=%s；%s" % (source, "；".join(problems[:6])), problems
    total = sum(len(baseline.get(key) or []) for key in ("rooms", "events", "items", "omens"))
    return PASS, "基线=%s；%d 个 WW 资源 id + 50 个剧本号在 content_ww.py 中全部可回读" % (
        source, total), []


def check_a29_06(ctx):
    base = ctx.root / "source"
    hits = []
    qa_hits = []
    for path in iter_py_files(base):
        if path.name == "content_ww.py":
            continue
        tree, _ = parse_module(path)
        if tree is None:
            continue
        # 只看 import 语句与 importlib.import_module/__import__ 的实参，
        # 不看 docstring/注释里的"已隔离到 content_ww.py"说明。
        names = imported_modules(tree)
        matched = sorted(n for n in names if "content_ww" in n)
        if not matched:
            continue
        rel = ctx.rel(path)
        if "/qa/" in rel.replace("\\", "/"):
            qa_hits.append(rel)
        else:
            hits.append("%s(%s)" % (rel, ",".join(matched[:2])))
    if hits:
        return FAIL, "生产模块导入 content_ww：%s" % "；".join(hits[:6]), hits
    detail = "生产模块 0 处导入 content_ww"
    if qa_hits:
        detail += "；qa/ 下 %d 处引用（测试/校验代码，不构成生产导入）：%s" % (
            len(qa_hits), "，".join(qa_hits[:3]))
    return PASS, detail, []


def check_a29_07(ctx):
    return NOT_RUN, (
        "需要独立子进程断言（本脚本不 import 被测模块，以免产生 __pycache__）。"
        "外部执行：python -B -c \"import sys, content; "
        "assert 'content_ww' not in sys.modules, sorted(sys.modules)\" （cwd=source/desktop/game）"
    ), []


def check_a29_08(ctx):
    problems = []
    ph_dir = ctx.assets / "placeholders"
    files = sorted(ph_dir.glob("*.png")) if ph_dir.exists() else []
    names = {p.name for p in files}
    if len(files) != 3:
        problems.append("assets/placeholders 有 %d 张 PNG，期望 3" % len(files))
    extra = names - PLACEHOLDER_FILES
    if extra:
        problems.append("非基础占位图 %d 张（如 %s）" % (len(extra), sorted(extra)[:3]))
    missing = PLACEHOLDER_FILES - names
    if missing:
        problems.append("缺少基础占位图 %s" % sorted(missing))
    ww_runtime = [
        ctx.rel(p) for p in ctx.assets.rglob("ww_*.png")
    ] if ctx.assets.exists() else []
    if ww_runtime:
        problems.append("assets/ 下仍有 %d 张 ww_* 运行时图（如 %s）"
                        % (len(ww_runtime), ww_runtime[:3]))
    ww_assets = ctx.game / "assets_ww"
    note = ""
    if ww_assets.exists():
        count = len(list((ww_assets / "placeholders").glob("*.png"))) \
            if (ww_assets / "placeholders").exists() else 0
        note = "；assets_ww/placeholders=%d 张（隔离保留）" % count
    if problems:
        return FAIL, "；".join(problems[:6]) + note, problems
    return PASS, "placeholders 仅 3 张基础图；assets/ 无 ww_* 运行时图" + note, []


def check_a29_09(ctx):
    haunts = ctx.game / "haunts"
    if not haunts.exists():
        return FAIL, "haunts/ 目录不存在", []
    active = []
    for path in haunts.glob("*.py"):
        match = re.match(r"^haunt_(\d+)_", path.stem) or re.match(r"^haunt_haunt(\d+)$", path.stem)
        if not match:
            continue
        number = int(match.group(1))
        if 71 <= number <= 120:
            active.append(path.name)
    deferred = []
    deferred_dir = haunts / "_ww_deferred"
    if deferred_dir.exists():
        for path in deferred_dir.rglob("*.py"):
            match = re.match(r"^haunt_(\d+)_", path.stem) or re.match(r"^haunt_haunt(\d+)$", path.stem)
            if match and 71 <= int(match.group(1)) <= 120:
                deferred.append(path.name)

    problems = []
    if active:
        problems.append("haunts/ 顶层仍有 %d 个 WW 剧本模块（如 %s），须移入 haunts/_ww_deferred/"
                        % (len(active), sorted(active)[:3]))
    if not active and len(deferred) < 50:
        problems.append("WW 剧本模块仅 %d 个在 _ww_deferred/（期望 50），既未激活也未见归档，违反 B-03 不删除"
                        % len(deferred))

    tree, _ = parse_module(ctx.paths["haunts_init"])
    registry = []
    if tree is not None:
        node = top_level_list(tree, "_MODULES")
        if node is not None:
            registry = [elt.value for elt in node.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    if not registry:
        problems.append("无法静态解析 haunts/__init__.py 的 _MODULES")
    else:
        ww_registered = [name for name in registry if "haunt_haunt" in name]
        if len(registry) != 70:
            problems.append("注册表 _MODULES=%d，期望 70" % len(registry))
        if ww_registered:
            problems.append("注册表仍加载 %d 个 WW 模块（如 %s）"
                            % (len(ww_registered), ww_registered[:3]))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "haunts/ 顶层 0 个 71–120 模块；_ww_deferred/ %d 个；注册表 70 本" % len(deferred), []


def check_a29_10(ctx):
    records = ctx.records()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    if len(records) != EXPECTED_TOTAL:
        problems.append("records=%d，期望 %d（出现第 143 行即越界）" % (len(records), EXPECTED_TOTAL))
    bad_refs = []
    bad_ids = []
    bad_paths = []
    for row in records:
        ref = str(row.get("content_ref") or "")
        collection = ref[len("content.py:"):].partition("#")[0] if ref.startswith("content.py:") else ""
        if collection not in BASELINE_COLLECTIONS:
            bad_refs.append("%s→%r" % (row.get("record_id"), ref))
        for field in ("runtime_key", "target_ref", "content_ref"):
            value = str(row.get(field) or "")
            if value.startswith("roof_") or "ROOF_ROOMS" in value or "#ww_" in value:
                bad_ids.append("%s.%s=%r" % (row.get("record_id"), field, value))
        source = str(row.get("source_path") or "").replace("\\", "/")
        if source and (os.path.basename(source).startswith("ww_") or "/roof_" in source):
            bad_paths.append(source)
    if bad_refs:
        problems.append("content_ref 指向非 7 集合 %d 行（如 %s）" % (len(bad_refs), bad_refs[:3]))
    if bad_ids:
        problems.append("出现 WW 前缀 id %d 处（如 %s）" % (len(bad_ids), bad_ids[:3]))
    if bad_paths:
        problems.append("source_path 指向 WW 文件 %d 处（如 %s）" % (len(bad_paths), bad_paths[:3]))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "142 行全部落在 7 个基线集合；无 roof_/ww_ id 与路径", []


def check_a29_11(ctx):
    skip = {"content_ww.py", "_gen_ww_art.py", "_gen_ww_haunts.py"}
    hits = []
    for path in iter_py_files(ctx.game):
        if path.name in skip:
            continue
        rel = ctx.rel(path).replace("\\", "/")
        if "/qa/" in rel or "/haunts/" in rel:
            continue
        tree, _ = parse_module(path)
        if tree is None:
            continue
        found = sorted(referenced_names(tree) & FORBIDDEN_SYMBOLS)
        if found:
            hits.append("%s:%s" % (rel, ",".join(found)))
    if hits:
        return FAIL, ("仍有生产模块引用 WW 常量（content_ww 之外的符号）：%s"
                      % "；".join(hits[:6])), hits
    return PASS, "生产模块 0 处引用 ROOF_ROOMS/ROOF_ROOM_IDS/WW_*_ADDITION*", []


def check_a29_12(ctx):
    freeze_manifest = ctx.paths["freeze_dir"] / "manifest.json"
    if not freeze_manifest.exists():
        return NOT_RUN, ("缺少 S0 冻结清单（_freeze/manifest.json），miniprogram 树哈希无基线可比；"
                         "本轮不得以\"未改\"自证"), []
    try:
        payload = json.loads(freeze_manifest.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return FAIL, "冻结清单不可解析：%s" % exc, []
    recorded = (payload.get("trees") or {}).get("source/miniprogram")
    if not recorded:
        return NOT_RUN, "冻结清单未记录 source/miniprogram 树哈希", []
    base = ctx.root / "source" / "miniprogram"
    digest = hashlib.sha256()
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        digest.update(ctx.rel(path).encode("utf-8"))
        digest.update(ctx.hash_of(path).encode("ascii"))
    actual = digest.hexdigest()
    if actual != recorded:
        return FAIL, "miniprogram 树哈希漂移：%s→%s" % (str(recorded)[:12], actual[:12]), []
    return PASS, "source/miniprogram 树哈希与 S0 基线一致", []


# ---------------------------------------------------------------------------
# A-30 47 位登记与 0 missing
# ---------------------------------------------------------------------------

def check_a30_01(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读：%s" % ctx.errors.get("p_table"), []
    note = ctx.scope_note()
    problems = []
    counts = Counter(r.get("availability") for r in records)
    missing = counts.get("missing", 0)
    if missing != 0:
        problems.append("142 位内 missing=%d" % missing)
    if len(records) != EXPECTED_TOTAL:
        problems.append("范围内行数=%d，期望 142" % len(records))
    # stats 是全表口径：只有不存在越界行时才要求 stats.missing==0；
    # 否则把 stats 的数字写进 detail，口径归属 A-29-10。
    stats_missing = ctx.stats().get("missing")
    if not note and stats_missing != 0:
        problems.append("stats.missing=%r" % stats_missing)
    scope_ids = {r.get("record_id") for r in records}
    csv_missing = sum(1 for row in ctx.data.get("csv_rows") or []
                      if row.get("record_id") in scope_ids and row.get("availability") == "missing")
    if csv_missing != 0:
        problems.append("CSV 范围内 missing=%d" % csv_missing)
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "142 位 records/CSV 范围内 missing 均为 0%s" % note, []


def check_a30_02(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    note = ctx.scope_note()
    counts = Counter(r.get("availability") for r in records)
    runtime = Counter(r.get("runtime_status") for r in records)
    mapping = Counter(r.get("mapping_status") for r in records)
    problems = []
    for key in ("partial", "corrupted", "duplicate"):
        if counts.get(key, 0) != 0:
            problems.append("availability.%s=%d" % (key, counts.get(key)))
    if counts.get("usable", 0) != EXPECTED_TOTAL:
        problems.append("usable=%d，期望 142" % counts.get("usable", 0))
    for key in ("placeholder", "fallback"):
        if runtime.get(key, 0) != 0:
            problems.append("runtime_status.%s=%d" % (key, runtime.get(key)))
    for key in ("fallback", "pending_missing"):
        if mapping.get(key, 0) != 0:
            problems.append("mapping_status.%s=%d" % (key, mapping.get(key)))
    if not note:
        for key, value in (ctx.stats() or {}).items():
            if key in ("partial", "corrupted", "duplicate") and value != 0:
                problems.append("stats.%s=%r" % (key, value))
    if problems:
        return FAIL, "；".join(problems[:8]) + note, problems
    return PASS, "142 usable；partial/corrupted/duplicate/placeholder/fallback/pending 全 0" + note, []


def check_a30_03(ctx):
    records = ctx.records()
    baseline = ctx.baseline_missing_ids()
    if not records:
        return FAIL, "P 表为空或不可读", []
    if not baseline:
        return NOT_RUN, "缺少基线 47 行清单（run5_boundary_audit.json §2），无法逐行核对", []
    rows = [r for r in records if r.get("record_id") in baseline]
    problems = []
    if len(rows) != len(baseline):
        problems.append("基线 47 行只找到 %d 行" % len(rows))
    expected_field = {
        "character": "portrait",
        "room": "room_tile",
        "card_event": "card_face",
        "card_item": "card_face",
        "card_omen": "card_face",
    }
    for row in rows:
        rid = row.get("record_id")
        asset_type = row.get("asset_type")
        availability = row.get("availability")
        if availability not in ("usable", "partial"):
            problems.append("%s availability=%r（仍为 %s）" % (rid, availability, availability))
            continue
        if availability == "partial" and not row.get("quality_flags"):
            problems.append("%s partial 但 quality_flags 为空（§2.8 禁止）" % rid)
        source = str(row.get("source_path") or "").replace("\\", "/")
        if not source:
            problems.append("%s source_path 为空" % rid)
            continue
        if BACKUP_DIRNAME in source:
            problems.append("%s source_path 指向备份目录" % rid)
            continue
        absolute = ctx.root / source
        if not absolute.is_file():
            problems.append("%s 源文件缺失：%s" % (rid, source))
            continue
        if not case_consistent(ctx.root, source):
            problems.append("%s 路径大小写与磁盘不一致" % rid)
        if row.get("source_file") != os.path.basename(source):
            problems.append("%s source_file 与 source_path 基名不一致" % rid)
        if row.get("format") != "png":
            problems.append("%s format=%r" % (rid, row.get("format")))
        if not has_png_magic(absolute):
            problems.append("%s 文件不是 PNG 魔数" % rid)
        if row.get("decodable") != "ok":
            problems.append("%s decodable=%r" % (rid, row.get("decodable")))
        want_alpha = asset_type == "character"
        if bool(row.get("has_alpha")) != want_alpha:
            problems.append("%s has_alpha=%r，期望 %r" % (rid, row.get("has_alpha"), want_alpha))
        if bool(row.get("alpha_required")) != want_alpha:
            problems.append("%s alpha_required=%r，期望 %r"
                            % (rid, row.get("alpha_required"), want_alpha))
        if row.get("mapping_status") != "matched":
            problems.append("%s mapping_status=%r" % (rid, row.get("mapping_status")))
        if str(row.get("missing_note") or "").strip():
            problems.append("%s missing_note 非空" % rid)
        if str(row.get("fallback_ref") or "").strip():
            problems.append("%s fallback_ref 非空" % rid)
        usable = row.get("usable_fields") or []
        if not usable:
            problems.append("%s usable_fields 为空" % rid)
        elif expected_field.get(asset_type) not in usable and asset_type in expected_field:
            problems.append("%s usable_fields 缺 %s" % (rid, expected_field[asset_type]))
        size = absolute.stat().st_size
        if norm(row.get("bytes")) != str(size):
            problems.append("%s bytes=%r，实测 %d" % (rid, row.get("bytes"), size))
        if str(row.get("sha256") or "").lower() != ctx.hash_of(absolute):
            problems.append("%s sha256 与磁盘不一致" % rid)
        info = png_info(absolute)
        if info:
            if (row.get("width"), row.get("height")) != (info[0], info[1]):
                problems.append("%s width/height=%r/%r，IHDR=%dx%d"
                                % (rid, row.get("width"), row.get("height"), info[0], info[1]))
            if str(row.get("dimensions") or "") != "%dx%d" % (info[0], info[1]):
                problems.append("%s dimensions=%r" % (rid, row.get("dimensions")))
        if row.get("category_dir") != CATEGORY_DIR.get(asset_type):
            problems.append("%s category_dir=%r" % (rid, row.get("category_dir")))
        if row.get("canonical_record_id") != rid:
            problems.append("%s canonical_record_id 未自指" % rid)
        reviewer = str(row.get("reviewer") or "").strip()
        if not reviewer or reviewer.lower() == "automated":
            problems.append("%s reviewer=%r（47 行须人工/复核人具名）" % (rid, reviewer))
        if not str(row.get("verified_at") or "").strip():
            problems.append("%s verified_at 为空" % rid)
    if problems:
        return FAIL, "47 行核对：%d 处问题；%s" % (len(problems), "；".join(problems[:8])), problems
    return PASS, "47/47 行字段齐全、盘上事实一致、reviewer 具名", []


def check_a30_04(ctx):
    records = ctx.records()
    baseline_rows = ctx.baseline_missing_ids()
    baseline_paths = ctx.baseline_orphan_paths()
    if not records:
        return FAIL, "P 表为空或不可读", []
    if not baseline_rows or not baseline_paths:
        return NOT_RUN, "缺少基线 47 行/47 候选文件清单（run5_boundary_audit.json）", []
    by_id = {r.get("record_id"): r for r in records}
    actual = set()
    absent = []
    for rid in sorted(baseline_rows):
        row = by_id.get(rid)
        if not row:
            absent.append(rid)
            continue
        source = str(row.get("source_path") or "").replace("\\", "/")
        if source:
            actual.add(source)
    problems = []
    if absent:
        problems.append("P 表缺 %d 行：%s" % (len(absent), absent[:3]))
    only_table = sorted(actual - baseline_paths)
    only_disk = sorted(baseline_paths - actual)
    if only_table:
        problems.append("47 行引入了基线外文件 %d 个（如 %s）"
                        % (len(only_table), only_table[:3]))
    if only_disk:
        problems.append("基线候选文件未被登记 %d 个（如 %s）"
                        % (len(only_disk), only_disk[:3]))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "47 行 source_path 集合与基线 47 个候选文件集合完全相等（未改名、未移出 photos/）", []


def check_a30_05(ctx):
    data = ctx.data.get("p_table")
    if not data:
        return FAIL, "缺少 p_table.json", []
    records = data.get("records") or []
    columns = (data.get("schema") or {}).get("columns") or []
    header = ctx.data.get("csv_header") or []
    rows = ctx.data.get("csv_rows") or []
    note = ctx.scope_note()
    problems = []
    if len(columns) != EXPECTED_COLUMNS:
        problems.append("JSON columns=%d，期望 33" % len(columns))
    if header != columns:
        problems.append("CSV 表头与 JSON columns 不一致")
    if not ctx.data.get("csv_bom"):
        problems.append("CSV 无 UTF-8 BOM")
    if len(rows) != len(records):
        problems.append("CSV/JSON 行数不一致：CSV=%d / JSON=%d" % (len(rows), len(records)))
    scoped = ctx.scope_rows()
    if len(scoped) != EXPECTED_TOTAL:
        problems.append("142 位范围内行数=%d" % len(scoped))
    if len(rows) == len(records):
        for index, (csv_row, record) in enumerate(zip(rows, records)):
            for column in columns:
                if norm(csv_row.get(column)) != norm(record.get(column)):
                    problems.append("第 %d 行 %s 不等价（csv=%r / json=%r）"
                                    % (index + 2, column, csv_row.get(column), record.get(column)))
                    break
            if len(problems) >= 8:
                break
    csv_ids = {row.get("record_id") for row in rows}
    json_ids = {record.get("record_id") for record in records}
    if csv_ids != json_ids:
        problems.append("record_id 双向差集非空")
    if problems:
        return FAIL, "；".join(problems[:8]) + note, problems
    return PASS, "142 行 × 33 列，BOM、表头、逐字段、record_id 双向一致" + note, []


def check_a30_06(ctx):
    mapping = ctx.data.get("mapping")
    if not mapping:
        return FAIL, "缺少 asset_mapping.json：%s" % ctx.errors.get("mapping"), []
    records = ctx.scope_rows()
    note = ctx.scope_note()
    by_id = {r.get("record_id"): r for r in records}
    entries = mapping.get("entries") or []
    unresolved = mapping.get("unresolved") or []
    problems = []
    if len(by_id) != EXPECTED_TOTAL:
        problems.append("范围内行数=%d，期望 142" % len(by_id))
    entry_ids = {e.get("record_id") for e in entries}
    if not set(by_id) <= entry_ids:
        problems.append("entries 未覆盖范围内 %d 行" % len(set(by_id) - entry_ids))
    bad_unresolved = [u.get("record_id") for u in unresolved if u.get("record_id") in by_id]
    if bad_unresolved:
        problems.append("范围内仍有 unresolved %d 行（如 %s）"
                        % (len(bad_unresolved), bad_unresolved[:3]))
    for entry in entries:
        row = by_id.get(entry.get("record_id"))
        if not row:
            problems.append("映射指向不存在的记录 %s" % entry.get("record_id"))
            continue
        path = str(entry.get("path") or "").replace("\\", "/")
        if path != str(row.get("source_path") or "").replace("\\", "/"):
            problems.append("%s path≠source_path" % row.get("record_id"))
        if path and not (ctx.root / path).is_file():
            problems.append("%s 源文件缺失" % row.get("record_id"))
        runtime = str(row.get("runtime_path") or "").replace("\\", "/")
        asset_type = row.get("asset_type")
        if asset_type == "room" and "/assets/rooms/" not in runtime:
            problems.append("%s 运行时图不在 assets/rooms/" % row.get("record_id"))
        if str(asset_type).startswith("card_") and "/assets/cards/" not in runtime:
            problems.append("%s 运行时图不在 assets/cards/" % row.get("record_id"))
        if problems and len(problems) >= 8:
            break
    if problems:
        return FAIL, "；".join(problems[:8]) + note, problems
    return PASS, "entries=142 / unresolved=0；path==source_path；无跨类别借用" + note, []


def check_a30_07(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    table_paths = {
        str(r.get("source_path") or "").replace("\\", "/")
        for r in records if r.get("availability") != "missing" and r.get("source_path")
    }
    disk_paths = {ctx.rel(p) for p in ctx.photos_files()}
    orphan = sorted(disk_paths - table_paths)
    dangling = sorted(table_paths - disk_paths)
    if orphan:
        problems.append("孤儿文件 %d 个（如 %s）" % (len(orphan), orphan[:3]))
    if dangling:
        problems.append("P 表引用但盘上缺失 %d 个（如 %s）" % (len(dangling), dangling[:3]))
    groups = defaultdict(list)
    for row in records:
        digest = str(row.get("sha256") or "")
        if digest:
            groups[digest].append(row.get("record_id"))
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    if duplicates:
        problems.append("sha256 重复组 %d（如 %s）"
                        % (len(duplicates), list(duplicates.values())[:2]))
    placeholder_hashes = {
        ctx.hash_of(p) for p in (ctx.assets / "placeholders").glob("*.png")
    } if (ctx.assets / "placeholders").exists() else set()
    used = [r.get("record_id") for r in records if str(r.get("sha256") or "") in placeholder_hashes]
    if used:
        problems.append("占位图哈希被登记为可用资源：%s" % used[:5])
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "孤儿 0；dangling 0；sha256 重复组 0；占位图哈希未被占用", []


def check_a30_08(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    per_type = defaultdict(set)
    for row in records:
        runtime = str(row.get("runtime_path") or "").replace("\\", "/")
        if not runtime:
            problems.append("%s runtime_path 为空" % row.get("record_id"))
            continue
        if row.get("runtime_status") != "ok":
            problems.append("%s runtime_status=%r" % (row.get("record_id"), row.get("runtime_status")))
        absolute = ctx.root / runtime
        if not absolute.is_file():
            problems.append("%s 运行时图缺失：%s" % (row.get("record_id"), runtime))
            continue
        info = png_info(absolute)
        if not info:
            problems.append("%s 运行时图非 PNG" % row.get("record_id"))
            continue
        want = RUNTIME_SIZE.get(row.get("asset_type"))
        if want and (info[0], info[1]) != want:
            problems.append("%s 运行时=%dx%d，期望 %dx%d"
                            % (row.get("record_id"), info[0], info[1], want[0], want[1]))
        per_type[row.get("asset_type")].add(runtime)
        if len(problems) >= 10:
            break
    want_counts = {"character": 12, "room": 50, "card_event": 45, "card_item": 22, "card_omen": 13}
    for key, want in want_counts.items():
        if len(per_type.get(key, set())) != want:
            problems.append("%s 运行时图 %d 张，期望 %d" % (key, len(per_type.get(key, set())), want))
    total = sum(len(v) for v in per_type.values())
    if total != EXPECTED_TOTAL:
        problems.append("运行时图合计 %d，期望 142（可复算口径）" % total)
    dirs = {
        "rooms": len(list((ctx.assets / "rooms").glob("*.png"))) if (ctx.assets / "rooms").exists() else 0,
        "cards": len([p for p in (ctx.assets / "cards").rglob("*.png")]) if (ctx.assets / "cards").exists() else 0,
        "characters": len(list((ctx.assets / "characters").glob("*.png"))) if (ctx.assets / "characters").exists() else 0,
        "placeholders": len(list((ctx.assets / "placeholders").glob("*.png"))) if (ctx.assets / "placeholders").exists() else 0,
    }
    want_dirs = {"rooms": 50, "cards": 80, "characters": 12, "placeholders": 3}
    for key, want in want_dirs.items():
        if dirs[key] != want:
            problems.append("assets/%s=%d，期望 %d" % (key, dirs[key], want))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "运行时 50/80/12/3 = 145；142 行 runtime_status=ok 且 IHDR 正确", []


def check_a30_09(ctx):
    data = ctx.data.get("promotion_map")
    baseline = ctx.baseline_missing_ids()
    if not data:
        return NOT_RUN, ("缺少 qa/run5_promotion_map.json（M-04 要求 47 行绑定表并签字）；"
                         "未交付不得以 P 表自证"), []
    rows = list_field(data, "items", "rows", "entries", "records")
    if not baseline:
        return NOT_RUN, "缺少基线 47 行清单，无法做双向差集", []
    problems = []
    if len(rows) != 47:
        problems.append("台账 %d 行，期望 47" % len(rows))
    ids = {str(r.get("record_id") or "") for r in rows}
    if ids != baseline:
        problems.append("与基线 47 行双向差集非空（缺 %d / 多 %d）"
                        % (len(baseline - ids), len(ids - baseline)))
    by_id = ctx.record_map()
    for row in rows:
        rid = row.get("record_id")
        rec = by_id.get(rid)
        if not rec:
            problems.append("台账记录 %s 不在 P 表" % rid)
            continue
        if str(row.get("source_path") or "").replace("\\", "/") != \
                str(rec.get("source_path") or "").replace("\\", "/"):
            problems.append("%s 台账路径与 P 表不一致" % rid)
        if str(row.get("sha256") or "").lower() != str(rec.get("sha256") or "").lower():
            problems.append("%s 台账 sha256 与 P 表不一致" % rid)
        if not str(row.get("decision") or "").strip():
            problems.append("%s 缺 decision" % rid)
        if not str(row.get("reviewer") or "").strip():
            problems.append("%s 缺 reviewer" % rid)
        if problems and len(problems) >= 8:
            break
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "台账 47 行，与 P 表双向差集为空；路径/sha256/decision/reviewer 齐全", []


def check_a30_10(ctx):
    path = ctx.paths["semantic_review"]
    if not path.exists():
        return NOT_RUN, ("缺少 qa/run5_semantic_review.jsonl（M-15 要求 47/47 逐张签字，"
                         "评审人不得为实现者）；本项不可脚本代签"), []
    baseline = ctx.baseline_missing_ids()
    entries = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            return FAIL, "语义评审文件存在无法解析的行", [line[:120]]
    problems = []
    if len(entries) != 47:
        problems.append("评审条目 %d，期望 47" % len(entries))
    ids = {str(e.get("record_id") or "") for e in entries}
    if baseline and ids != baseline:
        problems.append("评审 record_id 与基线 47 行不一致")
    for entry in entries:
        rid = entry.get("record_id")
        if entry.get("pass") is not True and str(entry.get("verdict") or "").upper() != PASS:
            problems.append("%s 未判 pass" % rid)
        if not str(entry.get("reviewer") or "").strip():
            problems.append("%s 缺 reviewer" % rid)
        if not str(entry.get("reviewed_at") or entry.get("date") or "").strip():
            problems.append("%s 缺评审日期" % rid)
        if problems and len(problems) >= 8:
            break
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "语义评审 47/47 pass，评审人与日期齐全", []


def check_a30_11(ctx):
    data = ctx.data.get("baseline_diff")
    if not data:
        return NOT_RUN, ("缺少 qa/run5_baseline_diff.json（A-30 判据 9 要求逐条 old/new/why/evidence/"
                         "reviewer）；本项为 0 missing 的达成条件之一"), []
    rows = list_field(data, "items", "rows", "entries", "records")
    text = json.dumps(data, ensure_ascii=False)
    required = ("A-05", "A-07", "A-08", "A-27", "V05", "V06", "V07", "V11")
    missing = [key for key in required if key not in text]
    problems = []
    if not rows:
        problems.append("diff 表无 items")
    if missing:
        problems.append("缺条目：%s" % ", ".join(missing))
    for row in rows[:200]:
        if not all(row.get(k) not in (None, "") for k in ("id", "old", "expected_v2", "why")):
            problems.append("存在缺 id/old/expected_v2/why 的条目")
            break
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "基线 diff 表覆盖 A-05/A-07/A-08/A-27 与 V05/V06/V07/V11，字段齐全", []


# ---------------------------------------------------------------------------
# A-31 130 张转码
# ---------------------------------------------------------------------------

def check_a31_01(ctx):
    files = ctx.photos_files()
    if not files:
        return FAIL, "photos/ 为空或不存在", []
    problems = []
    not_png = []
    wrong_ext = []
    for path in files:
        if not has_png_magic(path):
            not_png.append(path.name)
        if path.suffix.lower() != ".png":
            wrong_ext.append(path.name)
    if not_png:
        jpeg_like = sum(1 for p in files if has_jpeg_magic(p))
        problems.append("%d/%d 个文件不是 PNG 魔数（其中 JPEG 内容 %d 个）"
                        % (len(not_png), len(files), jpeg_like))
    if wrong_ext:
        problems.append("扩展名不是 .png 的文件 %d 个" % len(wrong_ext))
    if len(files) != EXPECTED_TOTAL:
        problems.append("photos/ 母版文件数=%d，期望 142（备份目录不计）" % len(files))
    records = ctx.scope_rows()
    bad_format = [r.get("record_id") for r in records
                  if r.get("availability") != "missing" and r.get("format") != "png"]
    if bad_format:
        problems.append("P 表 format≠png 的行 %d（如 %s）" % (len(bad_format), bad_format[:3]))
    flags = [r.get("record_id") for r in records
             if "ext_mismatch" in (r.get("quality_flags") or [])]
    if flags:
        problems.append("仍带 ext_mismatch 的行 %d（如 %s）" % (len(flags), flags[:3]))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "142/142 真 PNG 魔数；扩展名一致；format=png；ext_mismatch=0", []


def check_a31_02(ctx):
    backups = ctx.backup_files()
    jpeg_masters = [p for p in ctx.photos_files() if has_jpeg_magic(p)]
    if not backups:
        if jpeg_masters:
            return NOT_RUN, ("photos/_source_jpeg/ 不存在，且仍有 %d 张 JPEG 母版：转码尚未执行"
                             % len(jpeg_masters)), []
        return FAIL, "photos/ 已无 JPEG 内容但缺少 _source_jpeg/ 备份（P-09/P-10 不可逆）", []
    problems = []
    by_dir = Counter()
    for path in backups:
        by_dir[path.parent.name] += 1
        if path.suffix.lower() != ".jpg":
            problems.append("备份扩展名不是 .jpg：%s" % path.name)
    for key, want in BACKUP_EXPECTED.items():
        if by_dir.get(key, 0) != want:
            problems.append("_source_jpeg/%s=%d，期望 %d" % (key, by_dir.get(key, 0), want))
    extra = set(by_dir) - set(BACKUP_EXPECTED)
    if extra:
        problems.append("未知备份子目录：%s" % sorted(extra))
    total = len(backups)
    if total != 130:
        problems.append("备份合计 %d，期望 130" % total)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "备份 130 个 .jpg：room 50 / event 45 / item 22 / omen 13", []


def list_field(data, *names):
    """证据文件的条目数组：兼容 items/entries/records/rows 或裸列表。"""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for name in names:
        value = data.get(name)
        if isinstance(value, list):
            return value
    return []


def transcode_entries(ctx):
    return list_field(ctx.data.get("transcode_manifest"), "records", "items", "entries")


def pixel_result(entry):
    """转码清单的像素等价字段：兼容顶层与 pixel_equality 嵌套两种写法。"""
    nested = entry.get("pixel_equality") or {}
    max_diff = entry.get("max_diff", nested.get("max_diff"))
    mad = entry.get("mad", nested.get("mad"))
    equal = entry.get("equal", nested.get("equal"))
    left = entry.get("src_size") or nested.get("size_left")
    right = entry.get("dst_size") or nested.get("size_right")
    return max_diff, mad, equal, left, right


def check_a31_03(ctx):
    backups = ctx.backup_files()
    if not backups:
        return NOT_RUN, "无 backups 可核对（转码未执行或未备份）", []
    manifest_map = {}
    for entry in transcode_entries(ctx):
        backup = str(entry.get("backup") or "").replace("\\", "/")
        if backup:
            manifest_map[backup] = str(entry.get("source_sha256") or entry.get("src_sha256") or "").lower()
    records = ctx.records()
    provenance_src = {}
    backup_paths = {}
    for row in records:
        text = str(row.get("provenance") or "")
        match = re.search(r"src_sha256:([0-9a-f]{64})", text)
        if match:
            provenance_src[row.get("record_id")] = match.group(1)
        # §3.6 模板写 `backup=...`，实现也可能写 `backup:...`，两种都接受。
        match = re.search(r"backup[:=]([^;]+)", text)
        if match:
            backup_paths[row.get("record_id")] = match.group(1).replace("\\", "/")
    entries = transcode_entries(ctx)
    problems = []
    if len(provenance_src) != 130:
        problems.append("带 src_sha256 的 provenance 行 %d，期望 130" % len(provenance_src))
    if len(entries) != 130:
        problems.append("run5_transcode_manifest 条目 %d，期望 130（P-08 工具记录）" % len(entries))
    unmatched = []
    for path in backups:
        digest = ctx.hash_of(path)
        rel = ctx.rel(path)
        hit = [rid for rid, recorded in provenance_src.items() if recorded == digest]
        if not hit:
            unmatched.append("%s(P 表 provenance 无对应 src_sha256)" % rel)
            continue
        recorded_backup = backup_paths.get(hit[0])
        if recorded_backup != rel:
            unmatched.append("%s(provenance 记录的备份路径=%r)" % (rel, recorded_backup))
            continue
        if manifest_map and manifest_map.get(rel) != digest:
            unmatched.append("%s(清单 source_sha256 不一致)" % rel)
    if unmatched:
        problems.append("备份哈希链断裂 %d 个（如 %s）"
                        % (len(unmatched), unmatched[:3]))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, ("130 个备份 sha256 与 P 表 provenance.src_sha256、清单 source_sha256 "
                  "三方一致，备份路径已登记"), []


def check_a31_04(ctx, pixels=False):
    backups = ctx.backup_files()
    if not backups:
        return NOT_RUN, "无备份可比对像素（转码未执行）", []
    entries = transcode_entries(ctx)
    claimed = []
    for entry in entries:
        max_diff, mad, equal, left, right = pixel_result(entry)
        if equal is True or (max_diff == 0 and (mad in (0, 0.0, None))):
            claimed.append((entry, left, right))
    if not pixels and len(claimed) >= 130:
        bad_size = [e.get("path") for e, left, right in claimed
                    if left and right and list(left) != list(right)]
        if bad_size:
            return FAIL, "manifest 中 %d 条尺寸不等（P-02 禁止缩放）：%s" % (
                len(bad_size), bad_size[:3]), []
        return PASS, "manifest 记录 130/130 max_diff=0、MAD=0、尺寸不变（pixel_equality）", []
    # 实测路径（--pixels）
    try:
        from PIL import Image, ImageChops  # noqa: PLC0415 - 可选依赖，缺失即 NOT_RUN
    except Exception:  # noqa: BLE001
        if entries:
            return FAIL, ("manifest 仅 %d 条 max_diff=0（期望 130），且本机无 Pillow 无法实测"
                          % len(claimed)), []
        return NOT_RUN, "无 manifest 证据且本机无 Pillow：像素等价无法实测", []
    problems = []
    checked = 0
    by_name = {p.name: p for p in ctx.photos_files()}
    for backup in backups:
        stem = backup.stem + ".png"
        target = by_name.get(stem)
        if not target:
            problems.append("找不到对应母版：%s" % stem)
            continue
        try:
            with Image.open(backup) as left, Image.open(target) as right:
                if left.size != right.size:
                    problems.append("%s 尺寸不等 %r≠%r" % (stem, left.size, right.size))
                    continue
                diff = ImageChops.difference(left.convert("RGB"), right.convert("RGB"))
                if diff.getbbox() is not None:
                    problems.append("%s 像素不等（getbbox 非空）" % stem)
                    continue
        except Exception as exc:  # noqa: BLE001
            problems.append("%s 解码失败：%s" % (stem, exc))
            continue
        checked += 1
    if problems:
        return FAIL, "实测 %d/%d 通过；%s" % (checked, len(backups), "；".join(problems[:6])), problems
    return PASS, "实测 %d/%d：尺寸相同且 ImageChops 差集为空（max diff=0，MAD=0）" % (checked, len(backups)), []


def check_a31_05(ctx):
    inventory = ctx.data.get("inventory")
    if inventory is None:
        return NOT_RUN, "缺少 .codebuddy/wfat/photos_inventory.json", []
    if not isinstance(inventory, list):
        return FAIL, "inventory 结构不是列表", []
    problems = []
    if len(inventory) != EXPECTED_TOTAL:
        problems.append("inventory 条数=%d，期望 142" % len(inventory))
    disk = {p.name: p for p in ctx.photos_files()}
    drift = []
    missing = []
    for item in inventory:
        name = item.get("file")
        recorded = str(item.get("sha256") or "").lower()
        path = disk.get(name)
        if not path:
            missing.append(name)
            continue
        if recorded and recorded != ctx.hash_of(path):
            drift.append(name)
        if str(item.get("format") or "").upper() not in ("PNG", ""):
            problems.append("%s inventory.format=%r" % (name, item.get("format")))
    if missing:
        problems.append("inventory 指向不存在的文件 %d 个（如 %s）" % (len(missing), missing[:3]))
    if drift:
        problems.append("哈希漂移 %d 个（如 %s）" % (len(drift), drift[:3]))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "inventory 142 条，逐条 sha256 与磁盘一致，0 漂移", []


def check_a31_06(ctx):
    for name in ("qa/run5_runtime_before", "_freeze/runtime_before"):
        candidate = ctx.root / name
        if candidate.exists():
            return NOT_RUN, ("发现转码前运行时快照 %s，但本脚本未实现逐像素对比（P-18 需 "
                             "max diff ≤2）；请用独立工具比较并落证" % name), []
    return NOT_RUN, ("缺少转码前运行时 PNG 归档，P-18（同尺寸 max diff ≤2）无法自动核对；"
                     "需在 S2 前归档 assets/rooms|cards 旧产物"), []


def check_a31_07(ctx):
    data = ctx.data.get("size_report")
    if not data:
        return NOT_RUN, ("缺少 qa/run5_size_report.json（P-19）：photos/ 总字节、_source_jpeg/ 总字节、"
                         "增量百分比、打包影响均未登记"), []
    required = ("photos_bytes", "backup_bytes", "delta_percent", "package_impact")
    missing = [key for key in required if data.get(key) in (None, "")]
    if missing:
        return FAIL, "体积报告缺字段：%s" % ", ".join(missing), []
    return PASS, "体积与打包影响已登记（photos/backup/增量/打包结论）", []


# ---------------------------------------------------------------------------
# A-32 142 张成品规格
# ---------------------------------------------------------------------------

def check_a32_01(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    checked = 0
    for row in records:
        source = str(row.get("source_path") or "").replace("\\", "/")
        if not source:
            problems.append("%s source_path 为空" % row.get("record_id"))
            continue
        path = ctx.root / source
        info = png_info(path)
        if not info:
            problems.append("%s 母版不是 PNG 或缺失" % row.get("record_id"))
            continue
        width, height = info[0], info[1]
        asset_type = row.get("asset_type")
        if asset_type == "character":
            if (width, height) != (320, 320):
                problems.append("%s 角色母版 %dx%d，期望 320x320（D-01）"
                                % (row.get("record_id"), width, height))
        elif asset_type == "room":
            if width != height:
                problems.append("%s 房间母版 %dx%d 非 1:1" % (row.get("record_id"), width, height))
            elif min(width, height) < 1024:
                problems.append("%s 房间母版短边 %d <1024（R3）" % (row.get("record_id"), min(width, height)))
        else:
            long_edge = max(width, height)
            if long_edge < 1600:
                problems.append("%s 卡面母版长边 %d <1600（R3）" % (row.get("record_id"), long_edge))
            ratio = width / float(height) if height else 0
            if abs(ratio - 0.75) / 0.75 > 0.01:
                problems.append("%s 卡面母版比例 %.4f 偏离 3:4 超过 1%%" % (row.get("record_id"), ratio))
        checked += 1
        if len(problems) >= 10:
            break
    if problems:
        return FAIL, "母版层核对 %d 行：%s" % (checked, "；".join(problems[:8])), problems
    return PASS, "母版 142/142 达标：房间 1:1 ≥1024、卡面长边 ≥1600 且 3:4、角色 320²（D-01）", []


def check_a32_02(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    checked = 0
    for row in records:
        runtime = str(row.get("runtime_path") or "").replace("\\", "/")
        want = RUNTIME_SIZE.get(row.get("asset_type"))
        if not runtime or not want:
            problems.append("%s runtime_path/asset_type 不可判" % row.get("record_id"))
            continue
        info = png_info(ctx.root / runtime)
        if not info:
            problems.append("%s 运行时图缺失/非 PNG" % row.get("record_id"))
            continue
        actual = (info[0], info[1])
        if actual != want:
            problems.append("%s 运行时=%dx%d，期望 %dx%d"
                            % (row.get("record_id"), actual[0], actual[1], want[0], want[1]))
        checked += 1
        if len(problems) >= 10:
            break
    if problems:
        return FAIL, "运行时层核对 %d 行：%s" % (checked, "；".join(problems[:8])), problems
    return PASS, "运行时 142/142 精确：房间 512²、卡牌 480×672、角色 320²", []


def check_a32_03(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    for row in records:
        source = str(row.get("source_path") or "").replace("\\", "/")
        info = png_info(ctx.root / source) if source else None
        if not info:
            problems.append("%s 母版缺失/非 PNG" % row.get("record_id"))
            continue
        _w, _h, depth, color_type = info
        if depth != 8:
            problems.append("%s bit_depth=%d，期望 8" % (row.get("record_id"), depth))
        want = PNG_COLOR_RGBA if row.get("asset_type") == "character" else PNG_COLOR_RGB
        if color_type != want:
            problems.append("%s color_type=%d，期望 %d" % (row.get("record_id"), color_type, want))
        if len(problems) >= 10:
            break
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "142/142 位深 8；角色 color_type=6、其余 color_type=2", []


def check_a32_04(ctx):
    records = [r for r in ctx.scope_rows() if r.get("asset_type") == "character"]
    if not records:
        return FAIL, "P 表无角色行或不可读", []
    problems = []
    for row in records:
        if not row.get("has_alpha") or not row.get("alpha_required"):
            problems.append("%s has_alpha/alpha_required 不为 true" % row.get("record_id"))
        source = str(row.get("source_path") or "").replace("\\", "/")
        path = ctx.root / source if source else None
        info = png_info(path) if path else None
        if not info or info[3] != PNG_COLOR_RGBA:
            problems.append("%s 不是 RGBA PNG" % row.get("record_id"))
            continue
    others = [r for r in ctx.scope_rows() if r.get("asset_type") != "character"]
    for row in others:
        if row.get("has_alpha") or row.get("alpha_required"):
            problems.append("%s 非角色却要求 alpha" % row.get("record_id"))
            break
    # 真实镂空：需要 Pillow 读 alpha 直方图
    try:
        from PIL import Image  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        if problems:
            return FAIL, "；".join(problems[:8]), problems
        return NOT_RUN, ("IHDR 与 P 表已通过（RGBA/alpha_required=true），但\"非全不透明\"需 Pillow "
                         "读取 alpha 直方图；本机无 Pillow"), []
    for row in records:
        path = ctx.root / str(row.get("source_path") or "").replace("\\", "/")
        try:
            with Image.open(path) as image:
                if image.mode != "RGBA":
                    problems.append("%s mode=%s" % (row.get("record_id"), image.mode))
                    continue
                hist = image.getchannel("A").histogram()
        except Exception as exc:  # noqa: BLE001
            problems.append("%s 解码失败：%s" % (row.get("record_id"), exc))
            continue
        total = float(sum(hist)) or 1.0
        non_opaque = sum(hist[:255]) / total
        if non_opaque < 0.01:
            problems.append("%s 透明像素占比 %.4f <1%%（疑似全不透明假 alpha）"
                            % (row.get("record_id"), non_opaque))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "12/12 角色 RGBA 且实测非全不透明；非角色 has_alpha=false", []


def check_a32_05(ctx, enabled=True):
    if not enabled:
        return NOT_RUN, "按 --no-contrast 跳过 M-13 可读性代理", []
    try:
        from PIL import Image  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return NOT_RUN, "本机无 Pillow，M-13 三项指标无法计算", []
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    metrics = []
    for row in records:
        source = str(row.get("source_path") or "").replace("\\", "/")
        path = ctx.root / source if source else None
        if not path or not path.is_file():
            problems.append("%s 母版缺失" % row.get("record_id"))
            continue
        try:
            with Image.open(path) as image:
                # 角色为真实镂空 RGBA：先裁到 alpha 外接框（只统计画作区），
                # 再按 UI 背景 #1f232a 合成，避免把 68%–85% 的透明边距
                # 当成死黑像素（否则 12/12 都会被误判）。
                if image.mode in ("RGBA", "LA", "P"):
                    rgba = image.convert("RGBA")
                    bbox = rgba.getchannel("A").getbbox()
                    if not bbox:
                        problems.append("%s 全透明（alpha bbox 为空）" % row.get("record_id"))
                        continue
                    rgba = rgba.crop(bbox)
                    canvas = Image.new("RGB", rgba.size, (31, 35, 42))
                    canvas.paste(rgba, mask=rgba.getchannel("A"))
                    gray = canvas.convert("L")
                else:
                    gray = image.convert("L")
                gray = gray.resize((256, 256), Image.BILINEAR)
                hist = gray.histogram()
        except Exception as exc:  # noqa: BLE001
            problems.append("%s 解码失败：%s" % (row.get("record_id"), exc))
            continue
        total = float(sum(hist)) or 1.0

        def pct(share):
            target = total * share
            acc = 0
            for index, count in enumerate(hist):
                acc += count
                if acc >= target:
                    return index / 255.0
            return 1.0

        p5, p95 = pct(0.05), pct(0.95)
        spread = p95 - p5
        mean = sum(i * count for i, count in enumerate(hist)) / (255.0 * total)
        extreme = (sum(hist[:6]) + sum(hist[250:])) / total
        metrics.append((row.get("record_id"), spread, mean, extreme))
        if spread < M13_SPREAD_MIN:
            problems.append("%s P95−P5=%.3f <0.10" % (row.get("record_id"), spread))
        if not (M13_MEAN_MIN <= mean <= M13_MEAN_MAX):
            problems.append("%s mean=%.3f 越界" % (row.get("record_id"), mean))
        if extreme > M13_EXTREME_MAX:
            problems.append("%s 过曝/死黑=%.3f >0.25" % (row.get("record_id"), extreme))
        if len(problems) >= 10:
            break
    if problems:
        return FAIL, "M-13 核对 %d 张：%s" % (len(metrics), "；".join(problems[:8])), problems
    spreads = [m[1] for m in metrics]
    return PASS, ("142/142 通过 M-13（角色按 alpha bbox 裁切后按 #1f232a 合成统计）："
                  "spread %.3f–%.3f、mean 全在 [0.05,0.92]、极端像素 ≤25%%"
                  % (min(spreads), max(spreads))), []


def check_a32_06(ctx):
    records = ctx.scope_rows()
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    groups = defaultdict(list)
    for row in records:
        groups[str(row.get("sha256") or "")].append(row.get("record_id"))
    duplicates = {k: v for k, v in groups.items() if k and len(v) > 1}
    if duplicates:
        problems.append("sha256 重复组 %d（如 %s）" % (len(duplicates), list(duplicates.values())[:2]))
    # 47 位（M-A/M-B 路径）必须带 batch；95 张转码行按 §3.6 只需 origin/sha256。
    baseline = ctx.baseline_missing_ids()
    for row in records:
        text = str(row.get("provenance") or "")
        rid = row.get("record_id")
        needs_batch = ("batch=" not in text) and (
            (baseline and rid in baseline) or "origin=generated" in text
        )
        if not text:
            problems.append("%s provenance 为空" % rid)
        elif not re.search(r"sha256:[0-9a-f]{64}", text):
            problems.append("%s provenance 缺 sha256" % rid)
        elif "aigc=" not in text:
            problems.append("%s provenance 缺 aigc 标记" % rid)
        elif "origin=" not in text:
            problems.append("%s provenance 缺 origin" % rid)
        elif needs_batch:
            problems.append("%s provenance 缺 batch（47 位/generated 必填）" % rid)
        if problems and len(problems) >= 8:
            break
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "sha256 重复组 0；provenance 含 sha256/aigc/origin（47 位另含 batch）", []


def check_a32_07(ctx):
    return NOT_RUN, ("渲染层 WCAG（图形 ≥3:1、正文 ≥4.5:1）需 100% DPI 真实截图 ≥20 张"
                     "（五类各 ≥3）；本脚本不启动 Tk、不截屏，不得用图像统计替代"), []


# ---------------------------------------------------------------------------
# V05 / V11 回归
# ---------------------------------------------------------------------------

def _validation_check(ctx):
    data = ctx.data.get("validation_report")
    if not data:
        return None, "缺少 assets/validation_report.json：%s" % ctx.errors.get("validation_report")
    checks = {c.get("id"): c for c in (data.get("checks") or [])}
    return (data, checks), ""


def check_v05(ctx):
    loaded, error = _validation_check(ctx)
    _tree, text = parse_module(ctx.paths["verify_assets"])
    if not loaded:
        return NOT_RUN, error, []
    data, checks = loaded
    problems = []
    item = checks.get("V05")
    if not item:
        problems.append("validation_report 无 V05 结果")
    elif str(item.get("status")) != "pass":
        problems.append("V05 status=%r（%s）" % (item.get("status"), item.get("detail")))
    totals = data.get("totals") or {}
    if int(totals.get("checked") or 0) != 17 or int(totals.get("failed") or 0) != 0:
        problems.append("validation_report totals checked=%r failed=%r"
                        % (totals.get("checked"), totals.get("failed")))
    # 注意：verify_assets.py 里出现 ROOF_ROOMS 可能是"负向断言"（守门：content.py
    # 不得再有该属性），因此不按出现与否判 FAIL，只看 _content_sets 的集合数。
    collections = re.findall(r'"(CHARACTER_FACES|ROOM_BASES|ROOM_SUPPLEMENTAL_SPECS|'
                             r'OMEN_CARDS|ITEM_CARDS|EVENT_BASES|EVENT_SUPPLEMENTAL_SPECS)"',
                             text)
    if len(set(collections)) != 7:
        problems.append("_content_sets 集合数=%d，期望 7" % len(set(collections)))
    if problems:
        return FAIL, "；".join(problems[:6]), problems
    return PASS, "V05 pass：7 集合 142 槽双向可解析；validation_report 17 项 0 fail", []


def check_v11(ctx):
    problems = []
    text = read_text(ctx.paths["verify_assets"])
    present = re.search(r"^EXPECTED_PRESENT\s*=\s*(\d+)", text, re.M)
    if not present:
        problems.append("无法解析 verify_assets.py 的 EXPECTED_PRESENT")
    elif int(present.group(1)) != EXPECTED_TOTAL:
        problems.append("EXPECTED_PRESENT=%s，V11 仍以 %s 为文件数基线（142 状态必然失败）"
                        % (present.group(1), present.group(1)))
    block = re.search(r"#\s*V11.*?(?=#\s*V12)", text, re.S)
    if not block:
        problems.append("无法定位 V11 代码块")
    elif BACKUP_DIRNAME not in block.group(0):
        problems.append("V11 扫描未显式排除 _source_jpeg（备份计入会使计数变成 272）")
    # 独立复算：文件数 + 哈希（拆成两条，避免再次混淆）
    files = ctx.photos_files()
    if len(files) != EXPECTED_TOTAL:
        problems.append("photos/ 母版文件数=%d，期望 142" % len(files))
    loaded, error = _validation_check(ctx)
    if loaded:
        data, checks = loaded
        item = checks.get("V11")
        if not item:
            problems.append("validation_report 无 V11 结果")
        elif str(item.get("status")) != "pass":
            problems.append("V11 status=%r（%s）" % (item.get("status"), item.get("detail")))
    else:
        problems.append(error)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "V11 pass：142 文件基线、备份目录已排除、142 哈希 0 漂移", []


def check_v17(ctx):
    loaded, error = _validation_check(ctx)
    if not loaded:
        return NOT_RUN, error, []
    data, checks = loaded
    problems = []
    totals = data.get("totals") or {}
    if int(totals.get("checked") or 0) != 17:
        problems.append("checked=%r，期望 17" % totals.get("checked"))
    if int(totals.get("failed") or 0) != 0:
        problems.append("failed=%r，期望 0" % totals.get("failed"))
    if data.get("ok") is not True:
        problems.append("ok=%r" % data.get("ok"))
    failed_ids = [cid for cid, item in checks.items() if str(item.get("status")) != "pass"]
    if failed_ids:
        problems.append("非 PASS 项：%s" % ", ".join(sorted(failed_ids)))
    stamp = str(data.get("generated_at") or "")
    if not stamp:
        problems.append("缺少 generated_at")
    else:
        try:
            produced = datetime.fromisoformat(stamp.replace("Z", "+00:00")).replace(tzinfo=None)
            references = [ctx.paths["p_table"], ctx.paths["content"]]
            stamps = [datetime.fromtimestamp(p.stat().st_mtime) for p in references if p.exists()]
            if stamps and produced < max(stamps):
                problems.append("validation_report 早于 P 表/content.py（%s < %s）"
                                % (produced.isoformat(sep=" "),
                                   max(stamps).isoformat(sep=" ")))
        except Exception:  # noqa: BLE001
            problems.append("generated_at 不可解析：%r" % stamp)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "verify_assets 17/17、failed=0、ok=true，且晚于当前 P 表", []


# ---------------------------------------------------------------------------
# 只读与证据
# ---------------------------------------------------------------------------

def snapshot_tree(ctx):
    snap = {}
    for base in (ctx.game, ctx.photos):
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(str(base)):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", "node_modules", "archive")]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                snap[ctx.rel(path)] = (stat.st_mtime_ns, stat.st_size)
    return snap


def evidence_hashes(ctx):
    keys = (
        "p_table", "p_table_csv", "mapping", "validation_report", "content",
        "content_ww", "pipeline", "haunts_init", "verify_assets",
        "inventory", "boundary", "promotion_map", "semantic_review",
        "transcode_manifest", "baseline_diff",
    )
    payload = {}
    for key in keys:
        path = ctx.paths[key]
        exists = path.exists()
        payload[key] = {
            "path": ctx.rel(path),
            "exists": exists,
            "bytes": path.stat().st_size if exists else 0,
            "sha256": ctx.hash_of(path) if exists else "",
        }
    return payload


# ---------------------------------------------------------------------------
# 咨询项：旧 95/47 基线是否全部升级
# ---------------------------------------------------------------------------

def check_q03(ctx):
    text = read_text(ctx.paths["verify_assets"])
    if not text:
        return FAIL, "verify_assets.py 不可读", []
    stale = []
    patterns = {
        "EXPECTED_PRESENT": r"^EXPECTED_PRESENT\s*=\s*(\d+)",
        "EXPECTED_MISSING": r"^EXPECTED_MISSING\s*=\s*(\d+)",
        "EXPECTED_MISSING_PENDING": r"^EXPECTED_MISSING_PENDING\s*=\s*(\d+)",
        "EXPECTED_MISSING_FALLBACK": r"^EXPECTED_MISSING_FALLBACK\s*=\s*(\d+)",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, text, re.M)
        if match and match.group(1) not in ("0", "142"):
            stale.append("%s=%s" % (name, match.group(1)))
    if "ext_mismatch" in text and 'row["format"] != "jpeg"' in text:
        stale.append("V06 仍要求 format=jpeg + ext_mismatch")
    if "stats_split" in text and 'stats.get("usable") != 0' in text:
        stale.append("V12 仍断言 stats.usable==0")
    if stale:
        return FAIL, "旧 95/47 基线仍在：%s（S4 重基线未完成，17/17 无法达成）" % "；".join(stale), stale
    return PASS, "旧基线常量已升级，verify_assets 无 95/47 活跃断言", []


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

MANUAL_ITEMS = [
    "content_ww 运行时探针（sys.modules）：需外部子进程 python -B -c \"import content\" 断言，本脚本不 import 被测模块。",
    "source/miniprogram 全树哈希：需 S0 冻结清单 _freeze/manifest.json 记录树哈希后才有基线。",
    "47 位语义一致性：47/47 逐张评审 + 签字（M-15…M-18），评审人不得为实现者，脚本不代签。",
    "渲染层 WCAG 抽样 ≥20 张（五类各 ≥3）：需 100% DPI 真实截图，脚本不启动 Tk。",
    "P-18 运行时视觉一致（max diff ≤2）：需转码前运行时 PNG 归档后才能对比。",
    "P-19 体积与打包影响：需资产体积总账与 build_exe 打包预算结论。",
    "第二次干净复跑与双签：属 execution/content-release claim，不在本脚本 scope。",
]


def build_payload(ctx, audit, before, after, readonly, pixels, contrast):
    statuses = audit.statuses()
    gates = {}
    for gid, (title, ids) in GATES.items():
        gate_status = rollup([statuses.get(cid, NOT_RUN) for cid in ids])
        gates[gid] = {
            "title": title,
            "status": gate_status,
            "checks": ids,
            "failed": [cid for cid in ids if statuses.get(cid) == FAIL],
            "not_run": [cid for cid in ids if statuses.get(cid) in (NOT_RUN, CONFLICT)],
        }
    blocking = audit.blocking()
    blocking_statuses = [c["status"] for c in blocking]
    blocking_counts = Counter(blocking_statuses)
    advisory = [c for c in audit.checks if c["advisory"]]
    advisory_counts = Counter(c["status"] for c in advisory)

    if any(status == FAIL for status in blocking_statuses):
        verdict = FAIL
        scope_claim = "not-attested"
    elif any(status in (NOT_RUN, CONFLICT) for status in blocking_statuses):
        verdict = "INCOMPLETE"
        scope_claim = "partial"
    else:
        verdict = PASS
        scope_claim = "attested"

    changed = [path for path, fingerprint in before.items() if after.get(path) != fingerprint]
    return {
        "tool": "qa/verify_existing_142.py",
        "mode": "run5-asset-acceptance",
        "scope": "现有 142 位 P 表落实（WW 隔离 + 47 登记 + 130 转码 + 规格 + V05/V11 回归）",
        "scope_claim_note": ("本 scope_claim 只覆盖素材层与隔离门禁，"
                             "不等于 completion_claim@execution / @content-release"),
        "readonly": bool(readonly),
        "options": {"pixels": bool(pixels), "contrast": bool(contrast)},
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(ctx.root).replace("\\", "/"),
        "environment": {
            "python": platform.python_version(),
            "executable": sys.executable.replace("\\", "/"),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "inputs": evidence_hashes(ctx),
        "checks": list(audit.checks),
        "gates": gates,
        "counts": {
            "total": len(audit.checks),
            "blocking": len(blocking),
            "blocking_status": dict(blocking_counts),
            "advisory": len(advisory),
            "advisory_status": dict(advisory_counts),
        },
        "failed": [c["id"] for c in blocking if c["status"] == FAIL],
        "not_run": [c["id"] for c in blocking if c["status"] in (NOT_RUN, CONFLICT)],
        "advisory_failed": [c["id"] for c in advisory if c["status"] == FAIL],
        "manual": MANUAL_ITEMS,
        "readonly_evidence": {
            "snapshot_files": len(before),
            "changed_during_audit": changed[:20],
        },
        "verdict": verdict,
        "scope_claim": scope_claim,
    }


def print_human(payload):
    print("现有 142 位 P 表落实 —— 只读独立验收")
    print("根目录: %s" % payload["root"])
    print("判定: %s    scope_claim: %s（仅素材层/隔离门禁）"
          % (payload["verdict"], payload["scope_claim"]))
    counts = payload["counts"]
    print("检查项: %d（阻断 %d / 咨询 %d）" % (counts["total"], counts["blocking"], counts["advisory"]))
    blocking = counts["blocking_status"]
    print("阻断项: PASS=%d FAIL=%d NOT_RUN=%d CONFLICT=%d" % (
        blocking.get(PASS, 0), blocking.get(FAIL, 0),
        blocking.get(NOT_RUN, 0), blocking.get(CONFLICT, 0),
    ))
    print("门禁: " + "  ".join("%s=%s" % (gid, payload["gates"][gid]["status"]) for gid in GATES))
    if payload["failed"]:
        print("FAIL: %s" % ", ".join(payload["failed"]))
    if payload["not_run"]:
        print("NOT_RUN/CONFLICT: %s" % ", ".join(payload["not_run"]))
    if payload["advisory_failed"]:
        print("咨询项 FAIL: %s" % ", ".join(payload["advisory_failed"]))
    groups = defaultdict(list)
    for check in payload["checks"]:
        if check["status"] != PASS:
            groups[check["status"]].append(check)
    for status in (FAIL, NOT_RUN, CONFLICT):
        for check in groups.get(status, [])[:12]:
            print("  [%s] %s %s | %s" % (status, check["id"], check["title"], check["detail"]))
    changed = payload["readonly_evidence"]["changed_during_audit"]
    print("只读: 快照 %d 文件，运行期变化 %d 个%s"
          % (payload["readonly_evidence"]["snapshot_files"], len(changed),
             ("：" + ", ".join(changed[:6])) if changed else ""))
    print("不可自动验证（单列，不计 PASS）:")
    for item in payload["manual"]:
        print("  - %s" % item)
    print("机读: --json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="现有 142 位 P 表落实只读独立验收")
    parser.add_argument("--root", default=None, help="项目根目录（含 source/desktop/game）")
    parser.add_argument("--json", action="store_true", help="只输出机读 JSON")
    parser.add_argument("--pixels", action="store_true",
                        help="额外实测 130 张转码像素等价（需 Pillow，较慢）")
    parser.add_argument("--no-contrast", action="store_true", help="跳过 M-13 对比度代理")
    parser.add_argument("--strict", action="store_true", help="保留参数；本脚本默认严格")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else DEFAULT_PROJECT_ROOT
    if not (root / "source" / "desktop" / "game").exists():
        print("根目录不成立：%s" % root, file=sys.stderr)
        return 2

    ctx = Ctx(root)
    before = snapshot_tree(ctx)
    audit = Audit(ctx)

    audit.run("A-29-01", "G1", TITLES["A-29-01"], lambda: check_a29_01(ctx))
    audit.run("A-29-02", "G1", TITLES["A-29-02"], lambda: check_a29_02(ctx))
    audit.run("A-29-03", "G1", TITLES["A-29-03"], lambda: check_a29_03(ctx))
    audit.run("A-29-04", "G1", TITLES["A-29-04"], lambda: check_a29_04(ctx))
    audit.run("A-29-05", "G1", TITLES["A-29-05"], lambda: check_a29_05(ctx))
    audit.run("A-29-06", "G1", TITLES["A-29-06"], lambda: check_a29_06(ctx))
    audit.run("A-29-07", "G1", TITLES["A-29-07"], lambda: check_a29_07(ctx))
    audit.run("A-29-08", "G1", TITLES["A-29-08"], lambda: check_a29_08(ctx))
    audit.run("A-29-09", "G1", TITLES["A-29-09"], lambda: check_a29_09(ctx))
    audit.run("A-29-10", "G1", TITLES["A-29-10"], lambda: check_a29_10(ctx))
    audit.run("A-29-11", "G1", TITLES["A-29-11"], lambda: check_a29_11(ctx))
    audit.run("A-29-12", "G1", TITLES["A-29-12"], lambda: check_a29_12(ctx))

    audit.run("A-30-01", "G2", TITLES["A-30-01"], lambda: check_a30_01(ctx))
    audit.run("A-30-02", "G2", TITLES["A-30-02"], lambda: check_a30_02(ctx))
    audit.run("A-30-03", "G2", TITLES["A-30-03"], lambda: check_a30_03(ctx))
    audit.run("A-30-04", "G2", TITLES["A-30-04"], lambda: check_a30_04(ctx))
    audit.run("A-30-05", "G2", TITLES["A-30-05"], lambda: check_a30_05(ctx))
    audit.run("A-30-06", "G2", TITLES["A-30-06"], lambda: check_a30_06(ctx))
    audit.run("A-30-07", "G2", TITLES["A-30-07"], lambda: check_a30_07(ctx))
    audit.run("A-30-08", "G2", TITLES["A-30-08"], lambda: check_a30_08(ctx))
    audit.run("A-30-09", "G2", TITLES["A-30-09"], lambda: check_a30_09(ctx))
    audit.run("A-30-10", "G2", TITLES["A-30-10"], lambda: check_a30_10(ctx))
    audit.run("A-30-11", "G2", TITLES["A-30-11"], lambda: check_a30_11(ctx))

    audit.run("A-31-01", "G3", TITLES["A-31-01"], lambda: check_a31_01(ctx))
    audit.run("A-31-02", "G3", TITLES["A-31-02"], lambda: check_a31_02(ctx))
    audit.run("A-31-03", "G3", TITLES["A-31-03"], lambda: check_a31_03(ctx))
    audit.run("A-31-04", "G3", TITLES["A-31-04"], lambda: check_a31_04(ctx, args.pixels))
    audit.run("A-31-05", "G3", TITLES["A-31-05"], lambda: check_a31_05(ctx))
    audit.run("A-31-06", "G3", TITLES["A-31-06"], lambda: check_a31_06(ctx))
    audit.run("A-31-07", "G3", TITLES["A-31-07"], lambda: check_a31_07(ctx))

    audit.run("A-32-01", "G4", TITLES["A-32-01"], lambda: check_a32_01(ctx))
    audit.run("A-32-02", "G4", TITLES["A-32-02"], lambda: check_a32_02(ctx))
    audit.run("A-32-03", "G4", TITLES["A-32-03"], lambda: check_a32_03(ctx))
    audit.run("A-32-04", "G4", TITLES["A-32-04"], lambda: check_a32_04(ctx))
    audit.run("A-32-05", "G4", TITLES["A-32-05"],
              lambda: check_a32_05(ctx, not args.no_contrast))
    audit.run("A-32-06", "G4", TITLES["A-32-06"], lambda: check_a32_06(ctx))
    audit.run("A-32-07", "G4", TITLES["A-32-07"], lambda: check_a32_07(ctx))

    audit.run("V-05", "G5", TITLES["V-05"], lambda: check_v05(ctx))
    audit.run("V-11", "G5", TITLES["V-11"], lambda: check_v11(ctx))
    audit.run("V-17", "G5", TITLES["V-17"], lambda: check_v17(ctx))

    audit.run("Q-03", "G6", TITLES["Q-03"], lambda: check_q03(ctx), advisory=True)

    after = snapshot_tree(ctx)
    changed = [path for path, fingerprint in before.items() if after.get(path) != fingerprint]
    readonly = not changed
    if changed:
        audit.add("Q-01", "G6", TITLES["Q-01"], FAIL,
                  "本脚本运行期间项目文件变化 %d 个：%s" % (len(changed), ", ".join(changed[:6])),
                  changed[:20])
    else:
        audit.add("Q-01", "G6", TITLES["Q-01"], PASS,
                  "运行期 %d 个文件 mtime/size 未变，结论可归属当前产物" % len(before), [])
    hashes = evidence_hashes(ctx)
    missing_evidence = [key for key, item in hashes.items()
                        if not item["exists"] and key in (
                            "p_table", "p_table_csv", "mapping", "validation_report",
                            "content", "inventory", "verify_assets")]
    audit.add("Q-02", "G6", TITLES["Q-02"],
              PASS if not missing_evidence else FAIL,
              "证据清单 %d 项，其中缺失 %d 项%s" % (
                  len(hashes), len(missing_evidence),
                  ("：" + ", ".join(missing_evidence)) if missing_evidence else ""),
              missing_evidence)

    payload = build_payload(ctx, audit, before, after, readonly, args.pixels, not args.no_contrast)
    if args.json:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - 旧解释器/重定向时退回默认编码
            pass
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        print_human(payload)
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
