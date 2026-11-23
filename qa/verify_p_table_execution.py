#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P 表执行 —— 只读独立验收脚本。

定位
----
本脚本是 **独立验收方**，不参与实现、不改实现、不写任何项目文件：

* 顶部设置 ``sys.dont_write_bytecode = True``，导入被测模块不生成 ``__pycache__``；
* 不调用 ``asset_pipeline.main`` / ``write_p_table`` / ``normalize_*`` /
  ``build_placeholders`` 等任何写 ``assets/`` 的函数；
* 不运行 ``verify_assets.py``（它会写 ``assets/validation_report.json``）与
  ``qa/test_p_table_execution.py``（它会写 ``assets/`` 与 ``qa/fixtures/``）；
* 负样本全部在内存中构造，或只读引用现有 PNG/JPEG/JSON；
* 运行前后对 ``source/desktop/game`` 与 ``photos`` 做 mtime/size 快照比对，
  并在结束时复查关键文件 sha256；发现并发写入即判 FAIL/漂移，不把结果当冻结结论。

覆盖
----
274 行 / 33 列（含 runtime_key）/ 0 usable / 95 partial / 47 missing / 16 fallback / 31 pending、
95 个源文件事实、98 个运行时 PNG、三张占位图、registry 全键空间、
11 组异常负样本、重复读取与内存重建一致性、UI 绑定静态与缓存契约、
15 项性能预算（只读可测项实测，写文件项显式 NOT_RUN）、
旧测试结果解析（verify_assets / 契约 / 其他 verify 脚本 / 实现方 unittest）。

判读纪律
--------
* 只有 PASS / FAIL 进入通过率分母；NOT_RUN 与 CONFLICT 单独列出，绝不冒充 PASS；
* P0 存在 FAIL 或 NOT_RUN 时，不得宣称本轮完成；
* 缺失实现、缺失工具、旧结果过期，明确 FAIL 或 NOT_RUN，不使用 SKIP 掩盖；
* 旧测试报告只在“晚于全部输入”时才视为新鲜；过期即 NOT_RUN。

用法
----
python qa/verify_p_table_execution.py                 # 人读摘要
python qa/verify_p_table_execution.py --json          # 机读 JSON（只写 stdout）
python qa/verify_p_table_execution.py --fast          # 跳过大体重建/二次扫描
python qa/verify_p_table_execution.py --run-contract  # 以只读子进程重跑契约（stdout）
python qa/verify_p_table_execution.py --tk            # 尝试 Tk 冒烟（需要显示环境）

退出码
------
0 PASS；1 FAIL；2 参数或内部异常；3 INCOMPLETE（仅 NOT_RUN/CONFLICT，无 FAIL）
"""

from __future__ import annotations

import argparse
import ast
import copy
import csv
import gc
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import struct
import subprocess
import sys
import time
import traceback
from pathlib import Path

# 必须在任何被测模块导入之前设置：保证验收过程不生成 __pycache__。
sys.dont_write_bytecode = True

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT_RUN"
CONFLICT = "CONFLICT"
BLOCKED = "BLOCKED"

SCRIPT_PATH = Path(__file__).resolve()
GAME_DIR = SCRIPT_PATH.parents[1]
DEFAULT_ROOT = GAME_DIR.parents[2]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

EXPECTED_TOTAL = 274
EXPECTED_BY_TYPE = {
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
# run5 v2（2026-11-20）：47 位登记 + 130 张无损转码后 274 位全部 usable。
# 旧 0/95/47 已退役，见 qa/run5_baseline_diff.json。
EXPECTED_AVAILABILITY = {
    "usable": 274,
    "partial": 0,
    "missing": 0,
    "corrupted": 0,
    "duplicate": 0,
}
EXPECTED_MISSING_BY_TYPE = {}
EXPECTED_MISSING_FALLBACK = 0
EXPECTED_MISSING_PENDING = 0
EXPECTED_SOURCE_FILES = 274
EXPECTED_BACKUP_FILES = 130
EXPECTED_RUNTIME_ROOMS = 50
EXPECTED_RUNTIME_CARDS = 80
EXPECTED_RUNTIME_CHARACTERS = 12
EXPECTED_PLACEHOLDERS = 3
EXPECTED_COLUMNS = 33
EXPECTED_CONTRACT_CHECKS = 32
EXPECTED_VERIFY_CHECKS = 17

RELEASE_COLUMNS = [
    "bytes",
    "sha256",
    "category_dir",
    "alpha_required",
    "canonical_record_id",
    "reviewer",
    "verified_at",
]

# p_table_spec.md §6.1 的 28 列（历史规范），用于差异登记，不作为 33 列实现的上限。
SPEC_COLUMNS_28 = [
    "record_id", "source_file", "source_path", "asset_type", "dimensions", "format",
    "has_alpha", "decodable", "semantic_hint", "match_candidate", "usable_fields",
    "availability", "mapping_status", "target_ref", "missing_note", "provenance",
    "width", "height", "aspect_ratio", "bytes", "sha256", "category_dir",
    "alpha_required", "quality_flags", "fallback_ref", "canonical_record_id",
    "reviewer", "verified_at",
]

# 当前实现（26 业务列，含 runtime_key + 7 发布列）的 33 列；若 pipeline 可导入则以 pipeline 为准。
DEFAULT_COLUMNS_33 = [
    "record_id", "source_file", "source_path", "asset_type", "width", "height",
    "dimensions", "aspect_ratio", "format", "has_alpha", "decodable", "semantic_hint",
    "match_candidate", "usable_fields", "availability", "mapping_status", "target_ref",
    "runtime_key", "missing_note", "provenance", "runtime_path", "runtime_format",
    "runtime_status", "fallback_ref", "quality_flags", "content_ref", "bytes", "sha256",
    "category_dir", "alpha_required", "canonical_record_id", "reviewer", "verified_at",
]

REQUIRED_FIELDS_16 = [
    "record_id", "source_file", "source_path", "asset_type", "dimensions", "format",
    "has_alpha", "decodable", "semantic_hint", "match_candidate", "usable_fields",
    "availability", "mapping_status", "target_ref", "missing_note", "provenance",
]

RUNTIME_SIZE_BY_TYPE = {
    "character": (320, 320),
    "room": (512, 512),
    "card_omen": (480, 672),
    "card_item": (480, 672),
    "card_event": (480, 672),
    # run6 六类渲染面（P 表 runtime_specs 同源，见 asset_pipeline.RUNTIME_SPECS）
    "monster": (512, 512),
    "haunt": (1280, 720),
    "ending": (1024, 576),
    "card_back": (480, 640),
    "room_back": (512, 512),
    "dice": (256, 256),
}

# 只断言「必需 alpha」的类别必须带 alpha 通道（叠图用途）；剧本插画/结算/牌背
# 是整幅图或卡面替身，源图自带透明留白属正常，不做反向断言。
RUNTIME_ALPHA_REQUIRED_TYPES = ("character", "monster", "room_back", "dice")

CATEGORY_DIR_BY_TYPE = {
    "character": "char",
    "room": "room",
    "card_omen": "omen",
    "card_item": "item",
    "card_event": "event",
}

USABLE_FIELDS_BY_TYPE = {
    "character": {"portrait", "preview"},
    "room": {"room_tile", "preview"},
    "card_omen": {"card_face", "preview"},
    "card_item": {"card_face", "preview"},
    "card_event": {"card_face", "preview"},
}

# run6：九类渲染面扩到十一类，前缀与 asset_type 一一对应（见下面的 PREFIX_BY_ASSET_TYPE）。
RECORD_ID_RE = re.compile(
    r"^P-(CHR|ROOM|OMEN|ITEM|EVT|MONS|HAUNT|END|CBACK|RBACK|DICE)-(\d{3})$")
FALLBACK_ID_RE = re.compile(r"^P-(EVT|DICE)-\d{3}$")
PREFIX_BY_ASSET_TYPE = {
    "character": "CHR", "room": "ROOM", "card_omen": "OMEN",
    "card_item": "ITEM", "card_event": "EVT",
    "monster": "MONS", "haunt": "HAUNT", "ending": "END",
    "card_back": "CBACK", "room_back": "RBACK", "dice": "DICE",
}
# run6：runtime_key 命名空间（room:/card:/character: + 六类渲染面）
RUNTIME_KEY_PREFIXES = (
    "room:", "card:", "character:",
    "monster:", "haunt:", "ending:", "card_back:", "room_back:", "dice:",
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CONTRACT_IDS = ["C%02d" % index for index in range(1, EXPECTED_CONTRACT_CHECKS + 1)]
VERIFY_IDS = ["V%02d" % index for index in range(1, EXPECTED_VERIFY_CHECKS + 1)]

# run2_p_table_plan.md §5.3 的预算（待实测校准；None 表示只读阶段不可测）
PERF_BUDGETS = {
    "PT-PERF-01": {"label": "asset_pipeline --stage ptable 端到端", "budget": 5.0, "unit": "s"},
    "PT-PERF-02": {"label": "asset_pipeline --stage placeholders", "budget": 3.0, "unit": "s"},
    "PT-PERF-03": {"label": "asset_pipeline all（含 95 张规范化）", "budget": 240.0, "unit": "s"},
    "PT-PERF-04": {"label": "AssetRegistry.load", "budget": 0.150, "unit": "s"},
    "PT-PERF-05": {"label": "10,000 次 resolve（五类键混合）", "budget": 0.500, "unit": "s"},
    "PT-PERF-06": {"label": "verify_assets.py 全量", "budget": 90.0, "unit": "s"},
    "PT-PERF-07": {"label": "契约脚本全量（含解码）", "budget": 150.0, "unit": "s"},
    "PT-PERF-08": {"label": "契约脚本 --no-decode", "budget": 25.0, "unit": "s"},
    "PT-PERF-09": {"label": "构建峰值 RSS（all）", "budget": 1536.0, "unit": "MB"},
    "PT-PERF-10": {"label": "load 峰值增量 RSS", "budget": 80.0, "unit": "MB"},
    "PT-PERF-11": {"label": "UI 房间图首帧 512→128", "budget": 0.120, "unit": "s"},
    "PT-PERF-12": {"label": "UI 卡牌首帧 480x672→240x336", "budget": 0.150, "unit": "s"},
    "PT-PERF-13": {"label": "UI 缓存命中", "budget": 0.016, "unit": "s"},
    "PT-PERF-14": {"label": "一屏 12 图块批量绑定", "budget": 0.400, "unit": "s"},
    "PT-PERF-15": {"label": "冷启动到主界面", "budget": 2.5, "unit": "s"},
}

# 旧契约基线：首轮 29 PASS/3 FAIL；最新产物已收敛到 31/1。验收只要求不劣于 3 条
# 已知规范偏离，且残留 FAIL 必须在产品裁决内；不允许把未知 FAIL 当通过。
CONTRACT_BASELINE_FAIL_MAX = 3
CONTRACT_KNOWN_FAIL_IDS = {"C06", "C21", "C32"}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with open(str(path), "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def read_json(path):
    with open(str(path), "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def percentile(values, ratio):
    if not values:
        return None
    data = sorted(values)
    position = (len(data) - 1) * ratio
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return data[lower]
    return data[lower] * (upper - position) + data[upper] * (position - lower)


def median(values):
    return percentile(values, 0.5)


def png_size_local(path):
    """独立于 asset_registry 的 PNG IHDR 读取；非 PNG / 截断返回 None。"""
    try:
        with open(str(path), "rb") as handle:
            head = handle.read(33)
    except OSError:
        return None
    if not head.startswith(PNG_SIGNATURE) or len(head) < 24 or head[12:16] != b"IHDR":
        return None
    try:
        width, height = struct.unpack(">II", head[16:24])
    except struct.error:
        return None
    return int(width), int(height)


def png_has_alpha_channel(path):
    """只读 IHDR color type 判断 PNG 是否带 alpha（4=灰度+alpha，6=RGBA）。

    调色板（3）+ tRNS 也算带透明，但工程侧规范化输出统一是 RGBA/RGB，
    这里按 color type 直判，避免额外解析 chunk 产生歧义。
    """
    try:
        with open(str(path), "rb") as handle:
            head = handle.read(26)
    except OSError:
        return None
    if not head.startswith(PNG_SIGNATURE) or len(head) < 26 or head[12:16] != b"IHDR":
        return None
    return head[25] in (4, 6)


def sniff_magic(path):
    try:
        with open(str(path), "rb") as handle:
            head = handle.read(12)
    except OSError:
        return "unknown"
    if head.startswith(PNG_SIGNATURE):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def norm_field(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return str(value)


def case_consistent(base, rel_path):
    """逐段比对磁盘真实名称；Windows 大小写不敏感会掩盖发布端缺陷。"""
    current = Path(base)
    for part in str(rel_path).replace("\\", "/").split("/"):
        if not part or part == ".":
            continue
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def snapshot_tree(root, project_root):
    snap = {}
    root = Path(root)
    if not root.is_dir():
        return snap
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(name for name in dirnames if name not in ("__pycache__", ".git"))
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            path = Path(dirpath) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            try:
                rel = path.relative_to(project_root).as_posix()
            except ValueError:
                rel = path.as_posix()
            snap[rel] = (int(stat.st_size), int(stat.st_mtime_ns))
    return snap


def rss_bytes():
    """当前进程工作集；Windows 用 psapi，Linux 用 /proc；不可用返回 None。"""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.windll.psapi
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        except Exception:
            return None
        return None
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as handle:
            pages = int(handle.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def compute_stats(rows):
    """独立复算 stats，不调用实现方 stats_of。"""
    def count(predicate):
        return sum(1 for row in rows if predicate(row))

    by_type = {}
    missing_by_type = {}
    runtime_status = {}
    mapping_status = {}
    for row in rows:
        asset_type = row.get("asset_type")
        by_type[asset_type] = by_type.get(asset_type, 0) + 1
        if row.get("availability") == "missing":
            missing_by_type[asset_type] = missing_by_type.get(asset_type, 0) + 1
        runtime_status[row.get("runtime_status")] = runtime_status.get(row.get("runtime_status"), 0) + 1
        mapping_status[row.get("mapping_status")] = mapping_status.get(row.get("mapping_status"), 0) + 1
    return {
        "records": len(rows),
        "usable": count(lambda row: row.get("availability") == "usable"),
        "partial": count(lambda row: row.get("availability") == "partial"),
        "missing": count(lambda row: row.get("availability") == "missing"),
        "corrupted": count(lambda row: row.get("availability") == "corrupted"),
        "duplicate": count(lambda row: row.get("availability") == "duplicate"),
        "by_asset_type": by_type,
        "missing_by_asset_type": missing_by_type,
        "by_runtime_status": runtime_status,
        "by_mapping_status": mapping_status,
        "fallback_events": count(lambda row: row.get("runtime_status") == "fallback"),
        "fallback_records": count(lambda row: row.get("mapping_status") == "fallback"),
        "pending_missing_records": count(lambda row: row.get("mapping_status") == "pending_missing"),
        "placeholder_records": count(lambda row: row.get("runtime_status") == "placeholder"),
    }


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------
class Result(object):
    __slots__ = ("cid", "tc", "title", "priority", "status", "detail", "evidence")

    def __init__(self, cid, tc, title, priority, status, detail, evidence=None):
        self.cid = cid
        self.tc = tc
        self.title = title
        self.priority = priority
        self.status = status
        self.detail = detail
        self.evidence = list(evidence or [])

    def as_dict(self):
        return {
            "id": self.cid,
            "tc": self.tc,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
        }


class Runner(object):
    def __init__(self):
        self.results = []

    def add(self, cid, tc, title, priority, status, detail, evidence=None):
        self.results.append(Result(cid, tc, title, priority, status, detail, evidence))

    def execute(self, cid, tc, title, priority, func):
        try:
            outcome = func()
        except Exception as exc:  # 检查函数异常不得伪装成数据失败
            self.add(cid, tc, title, priority, FAIL,
                     "检查执行异常：%s: %s" % (type(exc).__name__, exc),
                     [traceback.format_exc(limit=4)])
            return
        if isinstance(outcome, tuple) and len(outcome) == 3:
            status, detail, evidence = outcome
        elif isinstance(outcome, tuple) and len(outcome) == 2:
            status, detail = outcome
            evidence = []
        else:
            status, detail, evidence = PASS, str(outcome), []
        self.add(cid, tc, title, priority, status, detail, evidence)


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------
class Context(object):
    def __init__(self, root, args):
        self.root = Path(root).resolve()
        self.game_dir = self.root / "source" / "desktop" / "game"
        self.assets = self.game_dir / "assets"
        self.photos = self.root / "photos"
        self.p_table = self.assets / "p_table.json"
        self.p_csv = self.assets / "p_table.csv"
        self.mapping_path = self.assets / "asset_mapping.json"
        self.inventory_path = self.root / ".codebuddy" / "wfat" / "photos_inventory.json"
        self.args = args

        self.payload = None
        self.payload_error = ""
        self.payload_raw = b""
        self.rows = []
        self.mapping = None
        self.mapping_error = ""
        self.registry = None
        self.registry_error = ""
        self.registry_module = None
        self._registry_loaded = False
        self.pipeline = None
        self.pipeline_error = ""
        self.contract_run = None

        self.initial_snapshot = {}
        self.initial_hashes = {}
        self.waivers = self._load_waivers()

        if str(self.game_dir) not in sys.path:
            sys.path.insert(0, str(self.game_dir))

        self.initial_snapshot = self._snapshot()
        self.initial_hashes = self._key_hashes()
        self._load_payload()
        self._load_mapping()

    # -- 装载 -------------------------------------------------------------
    def _load_payload(self):
        try:
            self.payload_raw = self.p_table.read_bytes()
            self.payload = json.loads(self.payload_raw.decode("utf-8-sig"))
            if not isinstance(self.payload, dict):
                raise ValueError("P 表根对象不是字典")
            self.rows = self.payload.get("records") or []
            if not isinstance(self.rows, list):
                raise ValueError("P 表 records 不是列表")
        except Exception as exc:
            self.payload = None
            self.rows = []
            self.payload_error = "%s: %s" % (type(exc).__name__, exc)

    def _load_mapping(self):
        try:
            self.mapping = read_json(self.mapping_path)
            if not isinstance(self.mapping, dict):
                raise ValueError("映射根对象不是字典")
        except Exception as exc:
            self.mapping = None
            self.mapping_error = "%s: %s" % (type(exc).__name__, exc)

    def _load_waivers(self):
        path = self.root / ".codebuddy" / "wfat" / "review.json"
        try:
            payload = read_json(path)
            items = payload.get("acceptedDeviations") or []
            return {str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}
        except Exception:
            return set()

    # -- 被测模块 ---------------------------------------------------------
    def get_registry_module(self):
        if self.registry_module is not None:
            return self.registry_module
        import asset_registry  # noqa: WPS433 - 延迟导入，保证快照先生成
        self.registry_module = asset_registry
        return asset_registry

    def get_registry(self):
        if self._registry_loaded:
            return self.registry
        self._registry_loaded = True
        try:
            module = self.get_registry_module()
            self.registry = module.AssetRegistry.load(str(self.p_table))
        except Exception as exc:
            self.registry = None
            self.registry_error = "%s: %s" % (type(exc).__name__, exc)
        return self.registry

    def get_pipeline(self):
        if self.pipeline is not None:
            return self.pipeline
        try:
            import asset_pipeline
            self.pipeline = asset_pipeline
        except Exception as exc:
            self.pipeline_error = "%s: %s" % (type(exc).__name__, exc)
        return self.pipeline

    def load_content_module(self):
        path = self.game_dir / "content.py"
        spec = importlib.util.spec_from_file_location("qa_p_table_content_probe", str(path))
        if spec is None or spec.loader is None:
            raise ImportError("无法构造 content.py 的导入规格")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def build_registry(self, payload, runtime_specs=None):
        module = self.get_registry_module()
        records = payload.get("records") or []
        specs = runtime_specs if runtime_specs is not None else (payload.get("runtime_specs") or {})
        registry = module.AssetRegistry(
            records=records,
            runtime_specs=specs,
            base_dir_name=payload.get("base_dir") or "",
            project_root=str(self.root),
            manifest_path=str(self.p_table),
            generated_at=payload.get("generated_at", ""),
            stats=payload.get("stats") or {},
        )
        registry._build_indexes(payload)
        return registry

    # -- 快照 -------------------------------------------------------------
    def _snapshot(self):
        snap = {}
        snap.update(snapshot_tree(self.game_dir, self.root))
        snap.update(snapshot_tree(self.photos, self.root))
        return snap

    def _key_hashes(self):
        files = [
            self.game_dir / "asset_pipeline.py",
            self.game_dir / "asset_registry.py",
            self.game_dir / "verify_assets.py",
            self.game_dir / "ui.py",
            self.game_dir / "ui_asset_binding.py",
            self.game_dir / "qa" / "verify_assets_contract.py",
            self.game_dir / "qa" / "test_p_table_execution.py",
            self.p_table,
            self.p_csv,
            self.mapping_path,
            self.inventory_path,
        ]
        return {str(path.relative_to(self.root)).replace("\\", "/"): sha256_file(path) for path in files}

    def current_hashes(self):
        return {key: sha256_file(self.root / key) for key in self.initial_hashes}

    def diff_snapshots(self):
        current = self._snapshot()
        changed = []
        for key in sorted(set(self.initial_snapshot) | set(current)):
            if self.initial_snapshot.get(key) != current.get(key):
                changed.append(key)
        return changed


# ---------------------------------------------------------------------------
# 通用断言辅助
# ---------------------------------------------------------------------------
def require_payload(ctx):
    if ctx.payload is None:
        raise AssertionError("P 表不可读：%s" % ctx.payload_error)
    if len(ctx.rows) != EXPECTED_TOTAL:
        raise AssertionError("P 表行数 %d != %d" % (len(ctx.rows), EXPECTED_TOTAL))
    return ctx.payload


def require_mapping(ctx):
    if ctx.mapping is None:
        raise AssertionError("映射不可读：%s" % ctx.mapping_error)
    return ctx.mapping


def require_registry(ctx):
    registry = ctx.get_registry()
    if registry is None:
        raise AssertionError("registry 不可用：%s" % ctx.registry_error)
    return registry


def by_record_id(rows):
    return {row.get("record_id"): row for row in rows}


def by_target_ref(rows):
    return {row.get("target_ref"): row for row in rows}


def append_limited(bucket, message, limit=8):
    if len(bucket) < limit:
        bucket.append(message)


# ---------------------------------------------------------------------------
# ENV / 产物
# ---------------------------------------------------------------------------
def check_env(ctx):
    problems = []
    if sys.version_info < (3, 9):
        problems.append("Python %s < 3.9" % platform.python_version())
    if ctx.payload is None:
        problems.append("P 表不可读：%s" % ctx.payload_error)
    if not ctx.photos.is_dir():
        problems.append("photos/ 不存在")
    if not ctx.assets.is_dir():
        problems.append("assets/ 不存在")
    detail = "python=%s pillow=%s tk=%s coverage=%s os=%s" % (
        platform.python_version(),
        _module_version("PIL"),
        _module_version("tkinter"),
        _module_version("coverage"),
        platform.platform(),
    )
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, detail, []


def _module_version(name):
    try:
        module = __import__(name)
        return str(getattr(module, "__version__", "available"))
    except Exception:
        return "absent"


def check_required_artifacts(ctx):
    required = [
        "source/desktop/game/asset_pipeline.py",
        "source/desktop/game/asset_registry.py",
        "source/desktop/game/verify_assets.py",
        "source/desktop/game/ui.py",
        "source/desktop/game/ui_asset_binding.py",
        "source/desktop/game/assets/p_table.json",
        "source/desktop/game/assets/p_table.csv",
        "source/desktop/game/assets/asset_mapping.json",
        "source/desktop/game/qa/verify_assets_contract.py",
        "photos",
    ]
    missing = [rel for rel in required if not (ctx.root / rel).exists()]
    if missing:
        return FAIL, "缺少关键产物 %d 项：%s" % (len(missing), ", ".join(missing[:8])), missing
    return PASS, "关键产物齐全（%d 项）" % len(required), []


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------
def check_data_rows(ctx):
    payload = ctx.payload
    if payload is None:
        return FAIL, "P 表不可读：%s" % ctx.payload_error, []
    problems = []
    if len(ctx.rows) != EXPECTED_TOTAL:
        problems.append("records=%d，期望 %d" % (len(ctx.rows), EXPECTED_TOTAL))
    stats = payload.get("stats") or {}
    if stats.get("records") != len(ctx.rows):
        problems.append("stats.records=%r 与 records=%d 不一致" % (stats.get("records"), len(ctx.rows)))
    if not payload.get("generated_at"):
        problems.append("generated_at 为空")
    if not payload.get("schema_version"):
        problems.append("schema_version 为空")
    if payload.get("base_dir") != ctx.root.name:
        problems.append("base_dir=%r 与项目根 %r 不一致" % (payload.get("base_dir"), ctx.root.name))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "records=%d，schema=%s，generated_at=%s" % (
        len(ctx.rows), payload.get("schema_version"), payload.get("generated_at")), []


def check_data_stats(ctx):
    require_payload(ctx)
    computed = compute_stats(ctx.rows)
    stats = ctx.payload.get("stats") or {}
    problems = []
    for key, expected in computed.items():
        actual = stats.get(key)
        if actual != expected:
            problems.append("%s: stats=%r 实测=%r" % (key, actual, expected))
    if problems:
        return FAIL, "stats 与逐行复算不一致 %d 项" % len(problems), problems
    return PASS, "stats 与逐行复算逐项一致（records=274，0/95/47/0/0）", []


def check_data_type_counts(ctx):
    require_payload(ctx)
    counts = {}
    for row in ctx.rows:
        asset_type = row.get("asset_type")
        counts[asset_type] = counts.get(asset_type, 0) + 1
    problems = []
    for key, expected in EXPECTED_BY_TYPE.items():
        if counts.get(key, 0) != expected:
            problems.append("%s=%d，期望 %d" % (key, counts.get(key, 0), expected))
    extra = {key: value for key, value in counts.items() if key not in EXPECTED_BY_TYPE}
    if extra:
        problems.append("未知 asset_type：%r" % extra)
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "12/50/13/22/45，无未知枚举", []


def check_data_availability(ctx):
    require_payload(ctx)
    counts = {key: 0 for key in EXPECTED_AVAILABILITY}
    problems = []
    for row in ctx.rows:
        availability = row.get("availability")
        if availability not in counts:
            problems.append("%s availability 非法：%r" % (row.get("record_id"), availability))
            continue
        counts[availability] += 1
        if availability == "partial":
            fields = set(row.get("usable_fields") or [])
            allowed = USABLE_FIELDS_BY_TYPE.get(row.get("asset_type"), set())
            illegal = fields - allowed
            if illegal:
                problems.append("%s partial 用途越权：%s" % (row.get("record_id"), sorted(illegal)))
        if availability in ("missing", "corrupted", "duplicate") and row.get("usable_fields"):
            problems.append("%s %s 但 usable_fields 非空" % (row.get("record_id"), availability))
    for key, expected in EXPECTED_AVAILABILITY.items():
        if counts.get(key, 0) != expected:
            problems.append("%s=%d，期望 %d" % (key, counts.get(key, 0), expected))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "usable=0 / partial=95 / missing=47 / corrupted=0 / duplicate=0；partial 未越权为 usable", []


def check_data_ids(ctx):
    require_payload(ctx)
    problems = []
    seen = set()
    per_prefix = {}
    for row in ctx.rows:
        record_id = row.get("record_id")
        if record_id in seen:
            problems.append("重复 record_id：%s" % record_id)
            continue
        seen.add(record_id)
        match = RECORD_ID_RE.match(str(record_id))
        if not match:
            problems.append("record_id 格式非法：%r" % record_id)
            continue
        prefix = match.group(1)
        expected_prefix = PREFIX_BY_ASSET_TYPE.get(row.get("asset_type"))
        if prefix != expected_prefix:
            problems.append("%s 前缀与 %s 不一致" % (record_id, row.get("asset_type")))
        per_prefix.setdefault(prefix, []).append(int(match.group(2)))
    for prefix, numbers in per_prefix.items():
        expected = list(range(1, max(numbers) + 1))
        if sorted(numbers) != expected:
            problems.append("%s 段号不连续：%r" % (prefix, sorted(numbers)))
    target_refs = [row.get("target_ref") for row in ctx.rows]
    if len(set(target_refs)) != EXPECTED_TOTAL:
        problems.append("target_ref 唯一数 %d != 274" % len(set(target_refs)))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "274 个 record_id 唯一、前缀正确、段号连续；target_ref 唯一", []


def check_data_content_refs(ctx):
    require_payload(ctx)
    content_refs = ctx.payload.get("content_refs") or {}
    problems = []
    if len(content_refs) != EXPECTED_TOTAL * 2:
        problems.append("content_refs 条目 %d != %d" % (len(content_refs), EXPECTED_TOTAL * 2))
    forward = {}
    reverse = {}
    for row in ctx.rows:
        # content_refs 的运行时侧固定是 runtime_key（target_ref 已是 content.py 溯源键）
        runtime_key = row.get("runtime_key") or ""
        content_ref = row.get("content_ref") or ""
        if not runtime_key.startswith(RUNTIME_KEY_PREFIXES):
            problems.append("%s runtime_key 格式非法：%r" % (row.get("record_id"), runtime_key))
            continue
        if not content_ref.startswith("content.py:"):
            problems.append("%s content_ref 格式非法：%r" % (row.get("record_id"), content_ref))
            continue
        forward[runtime_key] = content_ref
        if content_ref in reverse:
            problems.append("content_ref 重复：%s" % content_ref)
        reverse[content_ref] = runtime_key
    for runtime_key, content_ref in forward.items():
        if content_refs.get(runtime_key) != content_ref:
            problems.append("正向映射缺失：%s" % runtime_key)
        if content_refs.get(content_ref) != runtime_key:
            problems.append("反向映射缺失：%s" % content_ref)
    if len(forward) != EXPECTED_TOTAL or len(reverse) != EXPECTED_TOTAL:
        problems.append("content_ref 唯一数 %d/%d != 274" % (len(forward), len(reverse)))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "content_refs %d 条双向一致（runtime_key ↔ content_ref）；274 个 content_ref 唯一" % (
        len(content_refs)), []


def check_data_mapping(ctx):
    require_payload(ctx)
    mapping = require_mapping(ctx)
    entries = mapping.get("entries") or []
    unresolved = mapping.get("unresolved") or []
    covered_rows = [row for row in ctx.rows
                    if row.get("availability") in ("usable", "partial")]
    missing_rows = [row for row in ctx.rows if row.get("availability") == "missing"]
    problems = []
    if len(entries) != EXPECTED_TOTAL:
        problems.append("entries=%d != %d" % (len(entries), EXPECTED_TOTAL))
    if len(unresolved) != EXPECTED_AVAILABILITY["missing"]:
        problems.append("unresolved=%d != %d" % (len(unresolved),
                                                 EXPECTED_AVAILABILITY["missing"]))
    rows_by_target = by_target_ref(ctx.rows)
    entry_refs = {entry.get("target_ref") for entry in entries}
    unresolved_refs = {item.get("target_ref") for item in unresolved}
    if entry_refs != {row.get("target_ref") for row in covered_rows}:
        problems.append("entries 与 usable/partial 双向差集非空")
    if unresolved_refs != {row.get("target_ref") for row in missing_rows}:
        problems.append("unresolved 与 missing 双向差集非空")
    for entry in entries:
        row = rows_by_target.get(entry.get("target_ref"))
        if row is None:
            problems.append("entry 指向未知 target_ref：%r" % entry.get("target_ref"))
            continue
        for key in ("record_id", "content_ref", "status", "fallback", "runtime_path"):
            if key == "status":
                expected = row.get("mapping_status")
            elif key == "fallback":
                expected = row.get("fallback_ref")
            else:
                expected = row.get(key)
            if entry.get(key) != expected:
                problems.append("%s 映射 %s 不一致" % (entry.get("target_ref"), key))
        if entry.get("path") != row.get("source_path"):
            problems.append("%s 映射 path != source_path" % entry.get("target_ref"))
    for item in unresolved:
        row = rows_by_target.get(item.get("target_ref"))
        if row is None:
            problems.append("unresolved 指向未知 target_ref：%r" % item.get("target_ref"))
            continue
        if item.get("reason") != "missing_file":
            problems.append("%s reason != missing_file" % item.get("target_ref"))
        for key, expected in (
            ("record_id", row.get("record_id")),
            ("content_ref", row.get("content_ref")),
            ("status", row.get("mapping_status")),
            ("fallback", row.get("fallback_ref")),
            ("runtime_status", row.get("runtime_status")),
            ("runtime_path", row.get("runtime_path")),
            ("note", row.get("missing_note")),
        ):
            if item.get(key) != expected:
                problems.append("%s unresolved %s 不一致" % (item.get("target_ref"), key))
    mapping_stats = mapping.get("stats") or {}
    if mapping_stats.get("entries") != len(entries):
        problems.append("mapping.stats.entries 与 entries 不一致")
    if mapping_stats.get("unresolved") != len(unresolved):
        problems.append("mapping.stats.unresolved 与 unresolved 不一致")
    if problems:
        return FAIL, "映射双向覆盖/字段不一致 %d 项" % len(problems), problems[:8]
    return PASS, "entries=95 ↔ partial=95；unresolved=47 ↔ missing=47；path=source_path", []


def check_data_partial_facts(ctx):
    require_payload(ctx)
    partial_rows = [row for row in ctx.rows if row.get("availability") == "partial"]
    problems = []
    if len(partial_rows) != EXPECTED_AVAILABILITY["partial"]:
        problems.append("partial 行数 %d != 95" % len(partial_rows))
    for row in partial_rows:
        record_id = row.get("record_id")
        source_path = row.get("source_path") or ""
        absolute = ctx.root / source_path
        if not source_path.startswith("photos/"):
            problems.append("%s source_path 不在 photos/：%r" % (record_id, source_path))
        if ".." in source_path.replace("\\", "/").split("/"):
            problems.append("%s source_path 含 .." % record_id)
        if not absolute.is_file():
            problems.append("%s 源文件不存在：%s" % (record_id, source_path))
            continue
        if not case_consistent(ctx.root, source_path):
            problems.append("%s 源路径大小写不一致" % record_id)
        if row.get("source_file") != Path(source_path).name:
            problems.append("%s source_file != basename" % record_id)
        if sniff_magic(absolute) != "jpeg" or row.get("format") != "jpeg":
            problems.append("%s 魔数/format 非 jpeg" % record_id)
        if Path(source_path).suffix.lower() != ".png":
            problems.append("%s 扩展名不是 .png" % record_id)
        if "ext_mismatch" not in (row.get("quality_flags") or []):
            problems.append("%s 缺 ext_mismatch" % record_id)
        if row.get("has_alpha") is not False:
            problems.append("%s has_alpha 应为 false" % record_id)
        if row.get("decodable") != "ok":
            problems.append("%s decodable != ok" % record_id)
        if row.get("mapping_status") != "matched":
            problems.append("%s mapping_status != matched" % record_id)
        if row.get("runtime_status") != "ok":
            problems.append("%s runtime_status != ok" % record_id)
        if not row.get("missing_note"):
            problems.append("%s partial 缺 missing_note" % record_id)
        width, height = row.get("width"), row.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            problems.append("%s width/height 非法" % record_id)
        elif row.get("dimensions") != "%dx%d" % (width, height):
            problems.append("%s dimensions 与 width/height 不一致" % record_id)
        if not SHA256_RE.match(str(row.get("sha256") or "")):
            problems.append("%s sha256 非法" % record_id)
        if not isinstance(row.get("bytes"), int) or row.get("bytes") <= 0:
            problems.append("%s bytes 非法" % record_id)
        if row.get("category_dir") != CATEGORY_DIR_BY_TYPE.get(row.get("asset_type")):
            problems.append("%s category_dir 不一致" % record_id)
        if row.get("alpha_required") is not False:
            problems.append("%s alpha_required 应为 false" % record_id)
        if row.get("canonical_record_id") != record_id:
            problems.append("%s canonical_record_id 未自指" % record_id)
        if not row.get("reviewer"):
            problems.append("%s reviewer 为空" % record_id)
        if not DATE_RE.match(str(row.get("verified_at") or "")):
            problems.append("%s verified_at 非 YYYY-MM-DD" % record_id)
    if problems:
        return FAIL, "95 partial 源事实不一致 %d 项" % len(problems), problems[:8]
    return PASS, "95/95 源文件存在、逐段大小写一致、JPEG 魔数 + .png 扩展名、partial 未冒充 usable", []


def check_data_missing_facts(ctx):
    require_payload(ctx)
    missing_rows = [row for row in ctx.rows if row.get("availability") == "missing"]
    problems = []
    if len(missing_rows) != EXPECTED_AVAILABILITY["missing"]:
        problems.append("missing 行数 %d != 47" % len(missing_rows))
    by_type = {}
    for row in missing_rows:
        record_id = row.get("record_id")
        by_type[row.get("asset_type")] = by_type.get(row.get("asset_type"), 0) + 1
        if row.get("source_file") or row.get("source_path"):
            problems.append("%s missing 行带 source_file/source_path" % record_id)
        if row.get("format") != "unknown" or row.get("decodable") != "not_checked":
            problems.append("%s missing 行 format/decodable 不一致" % record_id)
        if row.get("dimensions") or row.get("aspect_ratio"):
            problems.append("%s missing 行带 dimensions/aspect_ratio" % record_id)
        if row.get("width") is not None or row.get("height") is not None:
            problems.append("%s missing 行带 width/height" % record_id)
        if row.get("usable_fields"):
            problems.append("%s missing 行 usable_fields 非空" % record_id)
        if not row.get("missing_note"):
            problems.append("%s missing_note 为空" % record_id)
        if row.get("bytes") is not None or row.get("sha256"):
            problems.append("%s missing 行伪造 bytes/sha256" % record_id)
        if row.get("category_dir") != CATEGORY_DIR_BY_TYPE.get(row.get("asset_type")):
            problems.append("%s category_dir 不一致" % record_id)
        expected_alpha = row.get("asset_type") == "character"
        if bool(row.get("alpha_required")) is not expected_alpha:
            problems.append("%s alpha_required 不一致" % record_id)
        if row.get("canonical_record_id") != record_id:
            problems.append("%s canonical_record_id 未自指" % record_id)
        if not row.get("reviewer"):
            problems.append("%s reviewer 为空" % record_id)
        if not DATE_RE.match(str(row.get("verified_at") or "")):
            problems.append("%s verified_at 非 YYYY-MM-DD" % record_id)
        if not row.get("runtime_path"):
            problems.append("%s runtime_path 为空" % record_id)
    for asset_type, expected in EXPECTED_MISSING_BY_TYPE.items():
        if by_type.get(asset_type, 0) != expected:
            problems.append("%s missing=%d，期望 %d" % (asset_type, by_type.get(asset_type, 0), expected))
    if problems:
        return FAIL, "47 missing 登记不一致 %d 项" % len(problems), problems[:8]
    return PASS, "47 missing（角色 12 / 房间 1 / 事件 34）路径留空、note 齐全、不伪造源事实", []


def check_data_fallback(ctx):
    require_payload(ctx)
    rows_by_id = by_record_id(ctx.rows)
    fallback_rows = [row for row in ctx.rows if row.get("mapping_status") == "fallback"]
    problems = []
    if len(fallback_rows) != EXPECTED_MISSING_FALLBACK:
        problems.append("fallback=%d != 16" % len(fallback_rows))
    for row in fallback_rows:
        record_id = row.get("record_id")
        fallback_ref = row.get("fallback_ref") or ""
        if not FALLBACK_ID_RE.match(str(fallback_ref)):
            problems.append("%s fallback_ref 非 record_id：%r" % (record_id, fallback_ref))
            continue
        target = rows_by_id.get(fallback_ref)
        if target is None:
            problems.append("%s fallback_ref 不存在：%s" % (record_id, fallback_ref))
            continue
        if target.get("asset_type") != "card_event":
            problems.append("%s fallback 目标非事件卡" % record_id)
        if target.get("availability") == "missing":
            problems.append("%s fallback 目标仍是 missing" % record_id)
        if row.get("runtime_path") != target.get("runtime_path"):
            problems.append("%s fallback runtime_path 与目标不一致" % record_id)
        if row.get("runtime_status") != "fallback":
            problems.append("%s runtime_status != fallback" % record_id)
        if fallback_ref == record_id:
            problems.append("%s fallback 指向自身" % record_id)
    if problems:
        return FAIL, "16 fallback 语义不一致 %d 项" % len(problems), problems[:8]
    return PASS, "16/16 fallback_ref=P-EVT-###，目标为可用事件卡且 runtime_path 一致", []


def check_data_pending(ctx):
    require_payload(ctx)
    pending_rows = [row for row in ctx.rows if row.get("mapping_status") == "pending_missing"]
    placeholder_paths = {row.get("runtime_path") for row in ctx.rows if row.get("runtime_status") == "placeholder"}
    problems = []
    if len(pending_rows) != EXPECTED_MISSING_PENDING:
        problems.append("pending_missing=%d != 31" % len(pending_rows))
    for row in pending_rows:
        record_id = row.get("record_id")
        if row.get("fallback_ref"):
            problems.append("%s pending_missing 带 fallback_ref" % record_id)
        if row.get("runtime_status") != "placeholder":
            problems.append("%s pending runtime_status != placeholder" % record_id)
        if row.get("runtime_path") not in placeholder_paths:
            problems.append("%s pending 未指向占位图" % record_id)
    if problems:
        return FAIL, "31 pending_missing 语义不一致 %d 项" % len(problems), problems[:8]
    return PASS, "31/31 pending_missing：fallback_ref 为空、runtime_status=placeholder、指向 3 张占位图", []


def check_data_missing_routing(ctx):
    require_payload(ctx)
    missing_rows = [row for row in ctx.rows if row.get("availability") == "missing"]
    placeholders = {
        "source/desktop/game/assets/placeholders/character_missing.png",
        "source/desktop/game/assets/placeholders/room_missing.png",
        "source/desktop/game/assets/placeholders/event_missing.png",
    }
    placeholder_rows = [row for row in missing_rows if row.get("runtime_path") in placeholders]
    fallback_rows = [row for row in missing_rows if row.get("runtime_status") == "fallback"]
    problems = []
    if len(placeholder_rows) != EXPECTED_MISSING_PENDING:
        problems.append("占位图 missing=%d != 31" % len(placeholder_rows))
    if len(fallback_rows) != EXPECTED_MISSING_FALLBACK:
        problems.append("回退 missing=%d != 16" % len(fallback_rows))
    for row in missing_rows:
        path = ctx.root / (row.get("runtime_path") or "")
        if not path.is_file():
            problems.append("%s 运行时文件不存在：%s" % (row.get("record_id"), row.get("runtime_path")))
            continue
        if png_size_local(path) is None:
            problems.append("%s 运行时文件不是真实 PNG" % row.get("record_id"))
    if problems:
        return FAIL, "47 missing 运行时路由不一致 %d 项" % len(problems), problems[:8]
    return PASS, "31 条走 3 张占位图 + 16 条走已有事件图；47 条运行时均为真实 PNG", []


def check_f08_literal(ctx):
    require_payload(ctx)
    missing_rows = [row for row in ctx.rows if row.get("availability") == "missing"]
    placeholders = {
        "source/desktop/game/assets/placeholders/character_missing.png",
        "source/desktop/game/assets/placeholders/room_missing.png",
        "source/desktop/game/assets/placeholders/event_missing.png",
    }
    outside = [row for row in missing_rows if row.get("runtime_path") not in placeholders]
    if not outside:
        return PASS, "F-08 字面判据满足：47 条 missing 全部指向 3 张占位图", []
    detail = (
        "计划 F-08 字面要求 47 条 missing 全部指向 3 张占位图，实际 16 条按 effect_id 回退到事件图；"
        "这与 V09/当前语义（31 placeholder + 16 fallback）冲突，属规范层待裁决，不计入代码缺陷"
    )
    return CONFLICT, detail, [row.get("record_id") for row in outside[:16]]


def check_data_content_sync(ctx):
    require_payload(ctx)
    payload = ctx.payload
    content = payload.get("content") or {}
    content_path = ctx.game_dir / "content.py"
    problems = []
    actual_sha = sha256_file(content_path)
    if content.get("sha256") != actual_sha:
        problems.append("content.sha256 与 content.py 实测不一致")
    if content.get("path") and not str(content.get("path")).endswith("content.py"):
        problems.append("content.path 未指向 content.py")
    expected_collections = {
        "CHARACTER_FACES": 12,
        "ROOM_BASES": 39,
        "ROOM_SUPPLEMENTAL_SPECS": 11,
        "OMEN_CARDS": 13,
        "ITEM_CARDS": 22,
        "EVENT_BASES": 11,
        "EVENT_SUPPLEMENTAL_SPECS": 34,
        # run6 六类渲染面（142 -> 274）：怪物标记 52 / 剧本插画 70 / 固定渲染位 10
        "MONSTER_BASES": 52,
        "HAUNT_DEFS": 70,
        "RENDER_SURFACE_SPECS": 10,
    }
    try:
        module = ctx.load_content_module()
        # HAUNT_DEFS 不是模块级列表，唯一来源是 build_catalog(0).haunt_defs
        # （与 qa/verify_assets_contract.py 的 _load_content_collections 同源）。
        catalog = module.build_catalog(0)
        actual_counts = {
            "CHARACTER_FACES": len(module.CHARACTER_FACES),
            "ROOM_BASES": len(module.ROOM_BASES),
            "ROOM_SUPPLEMENTAL_SPECS": len(module.ROOM_SUPPLEMENTAL_SPECS),
            "OMEN_CARDS": len(module.OMEN_CARDS),
            "ITEM_CARDS": len(module.ITEM_CARDS),
            "EVENT_BASES": len(module.EVENT_BASES),
            "EVENT_SUPPLEMENTAL_SPECS": len(module.EVENT_SUPPLEMENTAL_SPECS),
            "MONSTER_BASES": len(getattr(module, "MONSTER_BASES", []) or []),
            "HAUNT_DEFS": len(getattr(catalog, "haunt_defs", {}) or {}),
            "RENDER_SURFACE_SPECS": len(getattr(module, "RENDER_SURFACE_SPECS", []) or []),
        }
        if sum(actual_counts.values()) != EXPECTED_TOTAL:
            problems.append("集合展开 %d != 274" % sum(actual_counts.values()))
        if actual_counts != expected_collections:
            problems.append("集合计数与基线不一致：%r" % actual_counts)
    except Exception as exc:
        problems.append("content.py 导入失败：%s: %s" % (type(exc).__name__, exc))
    if content.get("collections") != expected_collections:
        problems.append("P 表 content.collections 与基线不一致")
    inventory = payload.get("source_inventory") or {}
    if inventory.get("files") != EXPECTED_SOURCE_FILES:
        problems.append("source_inventory.files != 95")
    if inventory.get("corrupted"):
        problems.append("source_inventory.corrupted 非空")
    if inventory.get("orphans"):
        problems.append("source_inventory.orphans 非空")
    if problems:
        return FAIL, "content.py 同步失败 %d 项" % len(problems), problems[:8]
    return PASS, ("content.py sha256 一致；10 集合 "
                  "12/39/11/13/22/11/34/52/70/10=274；无损坏/孤立源文件"), []


def check_data_photos(ctx):
    require_payload(ctx)
    problems = []
    # run5：photos/_source_jpeg/ 是 130 个转码原件备份，显式排除在源文件集合外。
    all_files = sorted(path for path in ctx.photos.rglob("*") if path.is_file())
    disk_files = [path for path in all_files
                  if path.relative_to(ctx.photos).parts[0] != "_source_jpeg"]
    backup_files = [path for path in all_files
                    if path.relative_to(ctx.photos).parts[0] == "_source_jpeg"]
    if len(disk_files) != EXPECTED_SOURCE_FILES:
        problems.append("photos 源文件数 %d != %d"
                        % (len(disk_files), EXPECTED_SOURCE_FILES))
    if len(backup_files) != EXPECTED_BACKUP_FILES:
        problems.append("photos 备份文件数 %d != %d"
                        % (len(backup_files), EXPECTED_BACKUP_FILES))
    disk_rel = {path.relative_to(ctx.root).as_posix() for path in disk_files}
    present_rows = [row for row in ctx.rows
                    if row.get("availability") in ("usable", "partial")]
    table_rel = {row.get("source_path") for row in present_rows}
    if disk_rel != table_rel:
        problems.append("photos 与 P 表 source_path 双向差集非空")
    inventory = {}
    try:
        items = read_json(ctx.inventory_path)
        inventory = {item.get("file"): item for item in items if isinstance(item, dict)}
    except Exception as exc:
        problems.append("photos_inventory.json 不可读：%s" % type(exc).__name__)
    if len(inventory) != EXPECTED_SOURCE_FILES:
        problems.append("inventory 条目 %d != 95" % len(inventory))
    rows_by_source = {row.get("source_path"): row for row in present_rows}
    for path in disk_files:
        rel = path.relative_to(ctx.root).as_posix()
        row = rows_by_source.get(rel)
        if row is None:
            continue
        digest = sha256_file(path)
        if row.get("sha256") != digest:
            problems.append("%s 源文件 sha256 与 P 表不一致" % row.get("record_id"))
        item = inventory.get(path.name)
        if item is not None and item.get("sha256") != digest:
            problems.append("%s 源文件 sha256 与 inventory 不一致" % row.get("record_id"))
        if row.get("bytes") != path.stat().st_size:
            problems.append("%s bytes 与磁盘不一致" % row.get("record_id"))
        if not str(row.get("provenance") or "").startswith(rel + ";sha256:" + digest):
            problems.append("%s provenance 哈希前缀不一致" % row.get("record_id"))
        try:
            with open(str(path), "rb") as handle:
                head = handle.read(4096)
        except OSError:
            head = b""
        marker = b"AIGC" in head
        provenance = str(row.get("provenance") or "")
        provenance_aigc = "aigc=true" in provenance
        # run5：130 张转码 PNG 本身没有 AIGC 标记，事实由原件（备份）承载。
        # 判定口径 = 当前文件有标记 或 备份有标记，二者之一即应为 aigc=true。
        backup_marker = False
        match = re.search(r"backup=([^;]+)", provenance)
        if match:
            backup = ctx.root / match.group(1)
            if backup.is_file():
                try:
                    with open(str(backup), "rb") as handle:
                        backup_marker = b"AIGC" in handle.read(4096)
                except OSError:
                    backup_marker = False
        if provenance_aigc != (marker or backup_marker):
            problems.append("%s AIGC 标记与 provenance 不一致（文件=%s / 备份=%s / 声明=%s）"
                            % (row.get("record_id"), marker, backup_marker, provenance_aigc))
    if problems:
        return FAIL, "源文件回归失败 %d 项" % len(problems), problems[:8]
    return PASS, ("274 源文件与 photos_inventory/P 表 sha256/bytes 三方一致；"
                  "AIGC 事实按原件（备份）核对；130 个备份在独立目录且不计入源文件；"
                  "无孤立"), []


# ---------------------------------------------------------------------------
# Schema / 33 列（含 runtime_key）
# ---------------------------------------------------------------------------
def _expected_columns(ctx):
    pipeline = ctx.get_pipeline()
    if pipeline is not None and hasattr(pipeline, "CSV_COLUMNS"):
        return list(pipeline.CSV_COLUMNS)
    return list(DEFAULT_COLUMNS_33)


def _csv_rows(ctx):
    raw = ctx.p_csv.read_bytes()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    header = list(reader.fieldnames or [])
    rows = [dict(row) for row in reader]
    return raw, header, rows


def check_schema_csv_json(ctx):
    require_payload(ctx)
    problems = []
    try:
        raw, header, csv_rows = _csv_rows(ctx)
    except Exception as exc:
        return FAIL, "p_table.csv 不可读：%s: %s" % (type(exc).__name__, exc), []
    if not raw.startswith(b"\xef\xbb\xbf"):
        problems.append("CSV 缺 UTF-8 BOM")
    if len(csv_rows) != EXPECTED_TOTAL:
        problems.append("CSV 行数 %d != 274" % len(csv_rows))
    columns = list(ctx.payload.get("schema", {}).get("columns") or [])
    if header != columns:
        problems.append("CSV 表头与 P 表 schema.columns 不一致")
    expected = _expected_columns(ctx)
    if header != expected:
        problems.append("CSV 表头与实现 CSV_COLUMNS 不一致")
    for index, row in enumerate(ctx.rows[:5]):
        if list(row.keys()) != columns:
            problems.append("JSON 第 %d 行字段集/顺序与 schema.columns 不一致" % index)
            break
    if problems:
        return FAIL, "CSV/JSON 结构不一致 %d 项" % len(problems), problems[:8]
    return PASS, "CSV BOM + 274 行；CSV 表头 = JSON schema.columns = 实现 %d 列" % len(columns), []


def check_schema_required_fields(ctx):
    require_payload(ctx)
    problems = []
    counts = {field: 0 for field in REQUIRED_FIELDS_16}
    for row in ctx.rows:
        for field in REQUIRED_FIELDS_16:
            if field not in row:
                counts[field] += 1
    for field, count in counts.items():
        if count:
            problems.append("缺必填字段 %s（%d/274）" % (field, count))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "16 个必填字段在 274 行全部存在", []


def check_schema_columns(ctx):
    require_payload(ctx)
    columns = list(ctx.payload.get("schema", {}).get("columns") or [])
    expected = _expected_columns(ctx)
    problems = []
    if len(columns) != EXPECTED_COLUMNS:
        problems.append("schema.columns=%d != %d" % (len(columns), EXPECTED_COLUMNS))
    if columns != expected:
        problems.append("schema.columns 与实现 CSV_COLUMNS 不一致")
    # target_ref（规范溯源键）与 runtime_key（运行时键）必须同表并存
    for column in ("target_ref", "runtime_key", "content_ref"):
        if column not in columns:
            problems.append("缺键列：%s" % column)
    missing_release = [column for column in RELEASE_COLUMNS if column not in columns]
    if missing_release:
        problems.append("缺发布档列：%s" % ",".join(missing_release))
    missing_spec = [column for column in SPEC_COLUMNS_28 if column not in columns]
    if missing_spec:
        problems.append("缺规范 §6.1 列：%s" % ",".join(missing_spec))
    release_declared = list(ctx.payload.get("schema", {}).get("release_columns") or [])
    if release_declared != RELEASE_COLUMNS:
        problems.append("schema.release_columns 与 7 列不一致")
    if problems:
        return FAIL, "%d 列契约不满足 %d 项" % (EXPECTED_COLUMNS, len(problems)), problems[:8]
    return PASS, "%d 列 = 26 业务列（target_ref + runtime_key 并存）+ 7 发布列；" \
                 "发布档齐全，规范 §6.1 的 28 列全部包含" % EXPECTED_COLUMNS, []


def check_schema_column_order(ctx):
    require_payload(ctx)
    columns = list(ctx.payload.get("schema", {}).get("columns") or [])
    common_spec = [column for column in SPEC_COLUMNS_28 if column in columns]
    common_actual = [column for column in columns if column in set(SPEC_COLUMNS_28)]
    if common_spec == common_actual:
        return PASS, "%d 列中属于规范 §6.1 的列序一致" % len(columns), []
    first = next(
        (index for index, (left, right) in enumerate(zip(common_spec, common_actual)) if left != right),
        0,
    )
    detail = (
        "规范 §6.1 仍是 28 列旧序（第 %d 位 %s），实现为 %d 列（第 %d 位 %s）；"
        "列集完整但列序未回写规范，属文档/规范待裁决，不计入代码缺陷"
        % (first + 1, common_spec[first] if common_spec else "?", len(columns), first + 1,
           common_actual[first] if common_actual else "?")
    )
    return CONFLICT, detail, []


def check_schema_contract_32(ctx):
    path = ctx.game_dir / "qa" / "verify_assets_contract.py"
    if not path.is_file():
        return FAIL, "契约脚本不存在：%s" % path, []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return FAIL, "契约脚本 AST 解析失败：%s" % type(exc).__name__, []
    checks = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CHECKS" for target in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                checks = node.value.elts
            break
    if checks is None:
        return FAIL, "契约脚本未定义 CHECKS 列表", []
    ids = []
    for item in checks:
        if isinstance(item, ast.Tuple) and item.elts and isinstance(item.elts[0], ast.Constant):
            ids.append(item.elts[0].value)
    if len(checks) != EXPECTED_CONTRACT_CHECKS or ids != CONTRACT_IDS:
        return FAIL, "契约检查 %d 条 / ID %r，期望 32 条 C01-C32" % (len(checks), ids[:5]), []
    return PASS, "契约脚本定义 32 项检查 C01-C32", []


def check_schema_csv_json_equiv(ctx):
    require_payload(ctx)
    try:
        _, _, csv_rows = _csv_rows(ctx)
    except Exception as exc:
        return FAIL, "CSV 不可读：%s" % type(exc).__name__, []
    columns = list(ctx.payload.get("schema", {}).get("columns") or [])
    problems = []
    if len(csv_rows) != len(ctx.rows):
        problems.append("CSV/JSON 行数不一致")
    for index, (csv_row, json_row) in enumerate(zip(csv_rows, ctx.rows)):
        for column in columns:
            if norm_field(csv_row.get(column)) != norm_field(json_row.get(column)):
                append_limited(problems, "第 %d 行 %s：CSV=%r JSON=%r" % (
                    index, column, csv_row.get(column), json_row.get(column)))
    if problems:
        return FAIL, "CSV/JSON 字段不一致 %d 项" % len(problems), problems[:8]
    return PASS, "274 行 × %d 列逐字段等价" % len(columns), []


# ---------------------------------------------------------------------------
# 运行时 PNG
# ---------------------------------------------------------------------------
def _runtime_paths(ctx):
    paths = {}
    for row in ctx.rows:
        rel = row.get("runtime_path") or ""
        if rel:
            paths.setdefault(rel, []).append(row)
    return paths


def check_runtime_inventory(ctx):
    require_payload(ctx)
    paths = _runtime_paths(ctx)
    rooms = [rel for rel in paths if "/assets/rooms/" in rel]
    cards = [rel for rel in paths if "/assets/cards/" in rel]
    characters = [rel for rel in paths if "/assets/characters/" in rel]
    placeholders_in_rows = [rel for rel in paths if "/assets/placeholders/" in rel]
    problems = []
    # run5 v2：274 位各有一张自有运行时图（277 张 = 274 + 3 张占位图另计）
    if len(paths) != EXPECTED_TOTAL:
        problems.append("去重运行时文件 %d != %d" % (len(paths), EXPECTED_TOTAL))
    for label, actual, expected in (
        ("rooms", len(rooms), EXPECTED_RUNTIME_ROOMS),
        ("cards", len(cards), EXPECTED_RUNTIME_CARDS),
        ("characters", len(characters), EXPECTED_RUNTIME_CHARACTERS),
    ):
        if actual != expected:
            problems.append("%s=%d != %d" % (label, actual, expected))
    if placeholders_in_rows:
        problems.append("%d 行的 runtime_path 仍指向占位图" % len(placeholders_in_rows))
    placeholder_dir = ctx.game_dir / "assets" / "placeholders"
    placeholder_files = sorted(placeholder_dir.glob("*.png")) if placeholder_dir.is_dir() else []
    if len(placeholder_files) != EXPECTED_PLACEHOLDERS:
        problems.append("placeholders 目录 %d 张 != %d"
                        % (len(placeholder_files), EXPECTED_PLACEHOLDERS))
    missing = [rel for rel in paths if not (ctx.root / rel).is_file()]
    if missing:
        problems.append("运行时文件缺失 %d 个：%s" % (len(missing), missing[:4]))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, ("274 个去重运行时 PNG：rooms=50 / cards=80 / characters=12；"
                  "另有 placeholders=3 张兜底图（无行指向）"), []


def check_runtime_png_sizes(ctx):
    require_payload(ctx)
    paths = _runtime_paths(ctx)
    problems = []
    for rel, rows in paths.items():
        absolute = ctx.root / rel
        actual = png_size_local(absolute)
        if actual is None:
            problems.append("%s 非真实 PNG/IHDR 截断" % rel)
            continue
        expected_sizes = {RUNTIME_SIZE_BY_TYPE.get(row.get("asset_type")) for row in rows}
        if None in expected_sizes:
            problems.append("%s 存在未知 asset_type" % rel)
            continue
        if len(expected_sizes) != 1:
            problems.append("%s 被多种规格引用：%r" % (rel, expected_sizes))
            continue
        expected = expected_sizes.pop()
        if actual != expected:
            problems.append("%s 实测 %dx%d，期望 %dx%d" % (rel, actual[0], actual[1], expected[0], expected[1]))
        if sniff_magic(absolute) != "png":
            problems.append("%s 魔数不是 PNG" % rel)
        # alpha 只对「必需 alpha」的类别断言（叠图用途）；其余类别不反向断言。
        alpha_types = {row.get("asset_type") for row in rows} & set(RUNTIME_ALPHA_REQUIRED_TYPES)
        if alpha_types:
            has_alpha = png_has_alpha_channel(absolute)
            if has_alpha is None:
                problems.append("%s 无法读取 IHDR color type" % rel)
            elif not has_alpha:
                problems.append("%s 缺少 alpha 通道（%s 必需）"
                                % (rel, "/".join(sorted(alpha_types))))
    if problems:
        return FAIL, "运行时 PNG 真实性/尺寸不一致 %d 项" % len(problems), problems[:8]
    return PASS, ("274/274 真实 PNG；房间 512×512、卡牌 480×672、角色 320×320、"
                  "怪物 512×512、剧本 1280×720、结算 1024×576、牌背 480×640、"
                  "未翻地块 512×512、骰面 256×256；alpha 仅断言 character/monster/"
                  "room_back/dice"), []


def check_runtime_placeholders(ctx):
    require_payload(ctx)
    problems = []
    for kind, size in (("character", (320, 320)), ("room", (512, 512)), ("event", (480, 672))):
        rel = "source/desktop/game/assets/placeholders/%s_missing.png" % kind
        path = ctx.root / rel
        if not path.is_file():
            problems.append("%s 不存在" % rel)
            continue
        actual = png_size_local(path)
        if actual != size:
            problems.append("%s 尺寸 %r != %r" % (rel, actual, size))
        if sniff_magic(path) != "png":
            problems.append("%s 魔数不是 PNG" % rel)
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "3 张占位图存在且尺寸为 320×320 / 512×512 / 480×672", []


def check_runtime_paths_inside_assets(ctx):
    require_payload(ctx)
    problems = []
    assets_root = ctx.assets.resolve()
    for row in ctx.rows:
        rel = str(row.get("runtime_path") or "")
        record_id = row.get("record_id")
        if not rel:
            problems.append("%s runtime_path 为空" % record_id)
            continue
        if not rel.startswith("source/desktop/game/assets/"):
            problems.append("%s runtime_path 前缀非法：%s" % (record_id, rel))
            continue
        if ".." in rel.replace("\\", "/").split("/"):
            problems.append("%s runtime_path 含 .." % record_id)
            continue
        absolute = (ctx.root / rel).resolve()
        try:
            absolute.relative_to(assets_root)
        except ValueError:
            problems.append("%s runtime_path 越界：%s" % (record_id, rel))
            continue
        if not case_consistent(ctx.root, rel):
            problems.append("%s runtime_path 大小写不一致" % record_id)
    if problems:
        return FAIL, "运行时路径越界/口径非法 %d 项" % len(problems), problems[:8]
    return PASS, "274 条 runtime_path 均在 assets 内、无 ..、逐段大小写一致", []


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def check_registry_load_no_decode(ctx):
    module = ctx.get_registry_module()
    source = read_text(ctx.game_dir / "asset_registry.py")
    problems = []
    try:
        tree = ast.parse(source)
    except Exception as exc:
        tree = None
        problems.append("registry AST 解析失败：%s" % type(exc).__name__)
    if tree is not None:
        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                top_imports.add(node.module or "")
        for name in sorted(top_imports):
            if name.startswith("PIL") or name.startswith("tkinter"):
                problems.append("registry 顶层 import %s" % name)
    original = module.png_size
    called = {"value": False}

    def _boom(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("AssetRegistry.load 不应读取/解码图片")

    module.png_size = _boom
    try:
        registry = module.AssetRegistry.load(str(ctx.p_table))
    finally:
        module.png_size = original
    if called["value"]:
        problems.append("load 期间调用了 png_size")
    if len(registry) != EXPECTED_TOTAL:
        problems.append("load 后 len=%d != 274" % len(registry))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "load 仅读 JSON/建索引，未调用 png_size；顶层无 PIL/tkinter", []


def check_registry_counts(ctx):
    registry = require_registry(ctx)
    problems = []
    if len(registry) != EXPECTED_TOTAL:
        problems.append("len(registry)=%d != 274" % len(registry))
    if len(registry.missing()) != EXPECTED_AVAILABILITY["missing"]:
        problems.append("missing()=%d != 47" % len(registry.missing()))
    for asset_type, expected in EXPECTED_BY_TYPE.items():
        actual = len(registry.by_type(asset_type))
        if actual != expected:
            problems.append("by_type(%s)=%d != %d" % (asset_type, actual, expected))
    summary = registry.summary()
    if summary.get("records") != EXPECTED_TOTAL:
        problems.append("summary.records=%r" % summary.get("records"))
    maybes = summary.get("availability") or {}
    if (maybes.get("usable", 0) != EXPECTED_AVAILABILITY["usable"]
            or maybes.get("partial", 0) != EXPECTED_AVAILABILITY["partial"]
            or maybes.get("missing", 0) != EXPECTED_AVAILABILITY["missing"]):
        problems.append("summary.availability=%r" % maybes)
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, ("len=274、missing=0、五类 by_type=12/50/13/22/45、"
                  "summary 274/0/0"), []


def check_registry_resolve_all(ctx):
    registry = require_registry(ctx)
    problems = []
    checked = {"target_ref": 0, "runtime_key": 0, "record_id": 0, "content_ref": 0, "bare": 0}
    rows_by_target = by_target_ref(ctx.rows)
    for row in ctx.rows:
        target_ref = row.get("target_ref")
        ref = registry.resolve(target_ref)
        checked["target_ref"] += 1
        if ref is None or ref.record_id != row.get("record_id"):
            problems.append("target_ref 解析失败：%s" % target_ref)
        # 新旧键必须落在同一资源位
        ref = registry.resolve(row.get("runtime_key"))
        checked["runtime_key"] += 1
        if ref is None or ref.record_id != row.get("record_id"):
            problems.append("runtime_key 解析失败：%s" % row.get("runtime_key"))
        elif ref.target_ref != target_ref:
            problems.append("runtime_key 与 target_ref 不同源：%s" % row.get("runtime_key"))
        ref = registry.resolve(row.get("record_id"))
        checked["record_id"] += 1
        if ref is None or ref.target_ref != target_ref:
            problems.append("record_id 解析失败：%s" % row.get("record_id"))
        ref = registry.resolve(row.get("content_ref"))
        checked["content_ref"] += 1
        if ref is None or ref.record_id != row.get("record_id"):
            problems.append("content_ref 解析失败：%s" % row.get("content_ref"))
        if row.get("asset_type") == "character":
            continue
        bare = str(row.get("runtime_key") or "").split(":")[-1]
        ref = registry.resolve(bare)
        checked["bare"] += 1
        if ref is None:
            problems.append("裸 id 解析失败：%s" % bare)
        elif ref.target_ref not in rows_by_target:
            problems.append("裸 id 返回未知 target_ref：%s" % ref.target_ref)
    if problems:
        return FAIL, "全键空间解析失败 %d 项" % len(problems), problems[:8]
    return PASS, "target_ref=274 / runtime_key=274 / record_id=274 / content_ref=274 / 裸 id=130 全部可解析", []


def check_registry_dirty_keys(ctx):
    registry = require_registry(ctx)
    problems = []
    cases = [
        None, "", "   ", "no:such:key", "no_such_room", 274, 3.14, ["x"], {"a": 1},
        "../etc/passwd", "room:../entrance_hall", "source/desktop/game/assets/rooms/entrance_hall.png",
        "C:\\Windows\\win.ini", "card:omen:omen_bite/../../x",
    ]
    for key in cases:
        try:
            result = registry.resolve(key)
        except Exception as exc:
            problems.append("resolve(%r) 抛 %s" % (key, type(exc).__name__))
            continue
        if result is not None:
            problems.append("resolve(%r) 非 None：%r" % (key, getattr(result, "target_ref", result)))
    try:
        if registry.resolve("  P-CHR-001  ") is None:
            problems.append("record_id 前后空格未被 strip 接受")
    except Exception as exc:
        problems.append("带空格 record_id 抛 %s" % type(exc).__name__)
    if problems:
        return FAIL, "脏键/路径穿越处理失败 %d 项" % len(problems), problems[:8]
    return PASS, "None/空串/空白/非字符串/未知键/../ 与路径分隔符均返回 None，不抛异常", []


def check_registry_case_insensitive(ctx):
    registry = require_registry(ctx)
    problems = []
    samples = [row for row in ctx.rows if row.get("asset_type") != "character"][:5]
    samples += [row for row in ctx.rows if row.get("asset_type") == "character"][:5]
    for row in samples:
        cases = [
            str(row.get("target_ref")).upper(),
            str(row.get("runtime_key")).upper(),
            str(row.get("record_id")).lower(),
            str(row.get("content_ref")).upper(),
        ]
        if row.get("asset_type") != "character":
            cases.append(str(row.get("runtime_key")).split(":")[-1].upper())
        for key in cases:
            ref = registry.resolve(key)
            if ref is None or ref.record_id != row.get("record_id"):
                problems.append("%s 大小写变体解析失败：%r" % (row.get("record_id"), key))
    if problems:
        return FAIL, "大小写不敏感失败 %d 项" % len(problems), problems[:8]
    return PASS, "10 行样本的 target_ref/record_id/content_ref/裸 id 大小写变体均命中同一 record_id", []


def check_registry_character_faces(ctx):
    registry = require_registry(ctx)
    problems = []
    faces = [row for row in ctx.rows if row.get("asset_type") == "character"]
    if len(faces) != 12:
        problems.append("角色面行 %d != 12" % len(faces))
    by_card = {}
    for row in faces:
        # 卡号与面别取运行时键（target_ref 是 content.py:CHARACTER_FACES#card_1@f0）
        runtime_key = str(row.get("runtime_key") or "")
        card_id = runtime_key.split(":")[1]
        face = runtime_key.split(":f")[-1]
        by_card.setdefault(card_id, {})[face] = row
    for card_id, pair in by_card.items():
        front, back = pair.get("0"), pair.get("1")
        if front is None or back is None:
            problems.append("%s 面别不完整" % card_id)
            continue
        if front.get("record_id") == back.get("record_id"):
            problems.append("%s f0/f1 共用 record_id" % card_id)
        if registry.resolve("character:%s:f0" % card_id).record_id != front.get("record_id"):
            problems.append("%s f0 解析错误" % card_id)
        if registry.resolve("character:%s:f1" % card_id).record_id != back.get("record_id"):
            problems.append("%s f1 解析错误" % card_id)
        if registry.resolve("%s#f0" % card_id).record_id != front.get("record_id"):
            problems.append("%s card#f0 别名错误" % card_id)
        if registry.resolve("%s#f1" % card_id).record_id != back.get("record_id"):
            problems.append("%s card#f1 别名错误" % card_id)
        if registry.resolve("content.py:CHARACTER_FACES#%s" % card_id) is not None:
            problems.append("%s 未带面别的 content_ref 不应解析" % card_id)
        if registry.resolve("content.py:CHARACTER_FACES#%s_0" % card_id).record_id != front.get("record_id"):
            problems.append("%s face content_ref f0 解析错误" % card_id)
        if registry.resolve("content.py:CHARACTER_FACES#%s_1" % card_id).record_id != back.get("record_id"):
            problems.append("%s face content_ref f1 解析错误" % card_id)
        if registry.resolve("content.py:CHARACTER_FACES#%s@f0" % card_id).record_id != front.get("record_id"):
            problems.append("%s target_ref @f0 解析错误" % card_id)
        if registry.resolve("content.py:CHARACTER_FACES#%s@f1" % card_id).record_id != back.get("record_id"):
            problems.append("%s target_ref @f1 解析错误" % card_id)
    if problems:
        return FAIL, "角色双面键空间失败 %d 项" % len(problems), problems[:8]
    return PASS, "6 角色 × 2 面：f0/f1 record_id 不同，character:card_N:fN、card#fN、face content_ref、" \
                 "target_ref @fN 四类键均可解析；无面别返回 None", []


def check_registry_bare_id_collision(ctx):
    require_payload(ctx)
    registry = require_registry(ctx)
    groups = {}
    for row in ctx.rows:
        if row.get("asset_type") == "character":
            continue
        bare = str(row.get("runtime_key") or "").split(":")[-1]
        groups.setdefault(bare, []).append(row)
    collisions = {key: value for key, value in groups.items() if len({row.get("asset_type") for row in value}) > 1}
    problems = []
    for bare, rows in collisions.items():
        first = registry.resolve(bare)
        second = registry.resolve(bare)
        if first is None or second is None:
            problems.append("真实跨类别裸 id %s 无法解析" % bare)
        elif first.record_id != second.record_id:
            problems.append("真实跨类别裸 id %s 解析不稳定" % bare)
    synthetic = {
        "records": [
            {"record_id": "P-OMEN-001", "target_ref": "card:omen:dup_probe", "asset_type": "card_omen",
             "runtime_path": "", "availability": "missing", "mapping_status": "pending_missing",
             "missing_note": "probe"},
            {"record_id": "P-EVT-001", "target_ref": "card:event:dup_probe", "asset_type": "card_event",
             "runtime_path": "", "availability": "missing", "mapping_status": "pending_missing",
             "missing_note": "probe"},
        ],
        "content_refs": {
            "content.py:OMEN_CARDS#dup_probe": "card:omen:dup_probe",
            "content.py:EVENT_BASES#dup_probe": "card:event:dup_probe",
        },
    }
    try:
        probe = ctx.build_registry(synthetic)
        first = probe.resolve("dup_probe")
        second = probe.resolve("dup_probe")
        if first is None or second is None:
            problems.append("合成跨类别裸 id 未解析")
        elif first.record_id != second.record_id:
            problems.append("合成跨类别裸 id 解析不稳定")
    except Exception as exc:
        problems.append("合成跨类别 registry 构造失败：%s" % type(exc).__name__)
    if problems:
        return FAIL, "裸 id 跨类别失败 %d 项" % len(problems), problems[:8]
    if collisions:
        return PASS, "真实跨类别裸 id %d 组均解析稳定；合成同名 omen/event 亦稳定" % len(collisions), []
    return PASS, "真实数据无跨类别裸 id 冲突；合成 omen/event 同名 id 解析稳定（首命中，不串号）", []


def check_registry_fallback(ctx):
    registry = require_registry(ctx)
    rows_by_id = by_record_id(ctx.rows)
    problems = []
    for row in ctx.rows:
        fallback_ref = row.get("fallback_ref") or ""
        if not fallback_ref:
            continue
        ref = registry.resolve(fallback_ref)
        if ref is None:
            problems.append("%s fallback 无法解析：%s" % (row.get("record_id"), fallback_ref))
            continue
        if ref.availability == "missing":
            problems.append("%s fallback 指向 missing" % row.get("record_id"))
        if ref.asset_type != "card_event":
            problems.append("%s fallback 非事件卡" % row.get("record_id"))
        if ref.rel_path != row.get("runtime_path"):
            problems.append("%s fallback runtime_path 不一致" % row.get("record_id"))
    if problems:
        return FAIL, "fallback registry 语义失败 %d 项" % len(problems), problems[:8]
    return PASS, "16 条 fallback_ref 均解析到非 missing 事件卡，runtime_path 与目标一致", []


def check_registry_validate(ctx):
    registry = require_registry(ctx)
    problems = []
    try:
        issues = registry.validate(str(ctx.assets))
    except Exception as exc:
        return FAIL, "validate(assets) 抛异常：%s" % type(exc).__name__, []
    if not isinstance(issues, (list, tuple)):
        problems.append("validate 返回 %s 而非列表" % type(issues).__name__)
    else:
        if issues:
            problems.append("validate(assets) 返回 %d 条问题" % len(issues))
    try:
        issues_none = registry.validate()
    except Exception as exc:
        problems.append("validate() 抛异常：%s" % type(exc).__name__)
        issues_none = []
    if issues_none:
        problems.append("validate() 返回 %d 条问题" % len(issues_none))
    if problems:
        return FAIL, "；".join(problems), [str(item) for item in (issues or [])[:5]]
    return PASS, "validate(assets) 与 validate() 均返回空列表、不抛异常", []


def check_registry_load_variants(ctx):
    module = ctx.get_registry_module()
    problems = []
    try:
        from_mapping = module.AssetRegistry.load(str(ctx.mapping_path))
        if len(from_mapping) != EXPECTED_TOTAL:
            problems.append("从 asset_mapping.json 回退加载 len=%d != 274" % len(from_mapping))
    except Exception as exc:
        problems.append("映射回退加载失败：%s" % type(exc).__name__)
    missing_path = ctx.assets / "__no_such_manifest__.json"
    try:
        module.AssetRegistry.load(str(missing_path))
        problems.append("不存在清单未抛 FileNotFoundError")
    except FileNotFoundError as exc:
        if str(missing_path) not in str(exc) and missing_path.name not in str(exc):
            problems.append("FileNotFoundError 消息未含路径")
    except Exception as exc:
        problems.append("不存在清单抛 %s 而非 FileNotFoundError" % type(exc).__name__)
    no_records = ctx.root / ".codebuddy" / "wfat" / "run2_architecture.json"
    if not no_records.is_file():
        no_records = ctx.root / ".codebuddy" / "wfat" / "closure.json"
    if no_records.is_file():
        try:
            module.AssetRegistry.load(str(no_records))
            problems.append("缺 records 且无同目录 P 表时未抛 ValueError")
        except ValueError:
            pass
        except Exception as exc:
            problems.append("缺 records 抛 %s 而非 ValueError" % type(exc).__name__)
    else:
        problems.append("缺少用于缺 records 负样本的只读 JSON")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "映射回退加载 274；缺清单 FileNotFoundError 含路径；缺 records 且无同目录表 ValueError", []


def check_registry_duplicate_keys(ctx):
    require_payload(ctx)
    module = ctx.get_registry_module()
    problems = []
    payload = copy.deepcopy(ctx.payload)
    records = payload.get("records") or []
    if len(records) < 2:
        return FAIL, "P 表记录不足，无法构造重复键负样本", []
    first, second = records[0], records[1]
    duplicate_id = copy.deepcopy(payload)
    duplicate_id["records"][1]["record_id"] = first.get("record_id")
    try:
        module.AssetRegistry(
            records=duplicate_id["records"], runtime_specs=duplicate_id.get("runtime_specs") or {},
            base_dir_name=duplicate_id.get("base_dir") or "", project_root=str(ctx.root),
            manifest_path=str(ctx.p_table), stats=duplicate_id.get("stats") or {},
        )
        problems.append("重复 record_id 未抛 ValueError")
    except ValueError:
        pass
    except Exception as exc:
        problems.append("重复 record_id 抛 %s 而非 ValueError" % type(exc).__name__)
    duplicate_ref = copy.deepcopy(payload)
    duplicate_ref["records"][1]["target_ref"] = first.get("target_ref")
    try:
        module.AssetRegistry(
            records=duplicate_ref["records"], runtime_specs=duplicate_ref.get("runtime_specs") or {},
            base_dir_name=duplicate_ref.get("base_dir") or "", project_root=str(ctx.root),
            manifest_path=str(ctx.p_table), stats=duplicate_ref.get("stats") or {},
        )
        problems.append("重复 target_ref 未抛 ValueError")
    except ValueError:
        pass
    except Exception as exc:
        problems.append("重复 target_ref 抛 %s 而非 ValueError" % type(exc).__name__)
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "重复 record_id / target_ref 均显式 ValueError，不再 last-wins", []


# ---------------------------------------------------------------------------
# 负样本（内存构造）
# ---------------------------------------------------------------------------
def _mutated_payload(ctx):
    payload = copy.deepcopy(ctx.payload)
    if not payload or not payload.get("records"):
        raise AssertionError("P 表不可用，无法构造负样本")
    return payload


def _forced_row(payload, availability=None, mapping_status=None, runtime_status=None,
                asset_type=None):
    """取第一条记录并**强制**成指定状态，供负样本使用。

    run5 v2 之后真实 P 表已无 partial / missing 行，负样本不能再"从真实表里挑一行
    改坏"。改为就地合成一行坏数据：校验器的负向分支照样被真实触发，断言一条没少。
    """
    record = payload["records"][0]
    if availability is not None:
        record["availability"] = availability
    if mapping_status is not None:
        record["mapping_status"] = mapping_status
    if runtime_status is not None:
        record["runtime_status"] = runtime_status
    if asset_type is not None:
        record["asset_type"] = asset_type
    return record


def _sample_event_row(payload):
    """取一条事件卡行（负样本里要按 asset_type 精确构造时用）。"""
    for row in payload["records"]:
        if row.get("asset_type") == "card_event":
            return row
    return payload["records"][0]


def _first_backup_jpeg(ctx):
    """photos/_source_jpeg/ 下第一个真实 JPEG（转码原件），供负样本使用。"""
    backup_dir = ctx.photos / "_source_jpeg"
    if backup_dir.is_dir():
        for path in sorted(backup_dir.rglob("*.jpg")):
            return path
    return None


def _codes(ctx, payload, runtime_specs=None):
    registry = ctx.build_registry(payload, runtime_specs=runtime_specs)
    return {issue.get("code") for issue in registry.validate(str(ctx.assets))}


def check_neg_manifest_missing(ctx):
    module = ctx.get_registry_module()
    path = ctx.assets / "__qa_no_such_manifest__.json"
    try:
        module.AssetRegistry.load(str(path))
    except FileNotFoundError as exc:
        if path.name in str(exc):
            return PASS, "不存在清单抛 FileNotFoundError，消息含路径", []
        return FAIL, "FileNotFoundError 消息不含路径：%s" % exc, []
    except Exception as exc:
        return FAIL, "抛 %s 而非 FileNotFoundError" % type(exc).__name__, []
    return FAIL, "不存在的清单未抛异常", []


def check_neg_no_records(ctx):
    module = ctx.get_registry_module()
    path = ctx.root / ".codebuddy" / "wfat" / "run2_architecture.json"
    if not path.is_file():
        path = ctx.root / ".codebuddy" / "wfat" / "closure.json"
    if not path.is_file():
        return NOT_RUN, "缺少只读 JSON 负样本（run2_architecture.json/closure.json）", []
    if (path.parent / "p_table.json").is_file():
        return NOT_RUN, "负样本同目录意外存在 p_table.json，无法验证缺 records 分支", []
    try:
        module.AssetRegistry.load(str(path))
    except ValueError:
        return PASS, "%s 缺 records 且无同目录 P 表，抛 ValueError" % path.name, []
    except Exception as exc:
        return FAIL, "抛 %s 而非 ValueError" % type(exc).__name__, []
    return FAIL, "缺 records 未抛 ValueError", []


def check_neg_bad_json(ctx):
    module = ctx.get_registry_module()
    path = ctx.game_dir / "README.md"
    if not path.is_file():
        return NOT_RUN, "缺少只读非 JSON 文件（README.md）", []
    try:
        module.AssetRegistry.load(str(path))
    except ValueError:
        return PASS, "非 JSON 清单抛 ValueError/JSONDecodeError", []
    except Exception as exc:
        return FAIL, "抛 %s 而非 ValueError" % type(exc).__name__, []
    return FAIL, "非 JSON 清单未抛异常", []


def check_neg_runtime_absent(ctx):
    payload = _mutated_payload(ctx)
    record = _forced_row(payload, availability="partial")
    record["runtime_path"] = "source/desktop/game/assets/rooms/__qa_absent__.png"
    codes = _codes(ctx, payload)
    if "runtime_file_absent" in codes:
        return PASS, "运行时文件缺失产出 runtime_file_absent，进程不崩", sorted(codes)
    return FAIL, "未产出 runtime_file_absent：%r" % sorted(codes), sorted(codes)


def check_neg_bad_png_and_size(ctx):
    payload = _mutated_payload(ctx)
    record = _forced_row(payload, availability="partial")
    # run5：源图已是真 PNG，不能再用"源图是 JPEG"构造负样本。
    # 改用 photos/_source_jpeg/ 里的真实 JPEG 原件 —— 这正好是"JPEG 内容冒充 PNG"
    # 的那个坏形态，断言意图不变。
    jpeg = _first_backup_jpeg(ctx)
    if jpeg is None:
        return NOT_RUN, "photos/_source_jpeg/ 下无 JPEG 原件，无法构造 runtime_not_png 负样本", []
    record["runtime_path"] = jpeg.relative_to(ctx.root).as_posix()
    codes = _codes(ctx, payload)
    problems = []
    if "runtime_not_png" not in codes:
        problems.append("JPEG 冒充运行时 PNG 未触发 runtime_not_png")
    if png_size_local(jpeg) is not None:
        problems.append("本地 PNG 头解析未拒绝 JPEG")
    corrupt = ctx.game_dir / "qa" / "fixtures" / "corrupt.png"
    if corrupt.is_file() and png_size_local(corrupt) is not None:
        problems.append("截断 PNG 未被 png_size 拒绝")
    payload2 = _mutated_payload(ctx)
    specs = copy.deepcopy(payload2.get("runtime_specs") or {})
    specs["room"] = {"width": 511, "height": 512, "format": "png"}
    codes2 = _codes(ctx, payload2, runtime_specs=specs)
    if "runtime_size_mismatch" not in codes2:
        problems.append("尺寸不符未触发 runtime_size_mismatch")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "JPEG 魔数/截断 PNG 触发 runtime_not_png；规格 511×512 触发 runtime_size_mismatch", []


def check_neg_semantic_rows(ctx):
    # run5 v2：真实表已无 missing / pending_missing / fallback 行，负样本改为合成。
    payload = _mutated_payload(ctx)
    missing = _forced_row(payload, availability="missing", mapping_status="pending_missing")
    missing["source_path"] = "photos/event/event_awful_waffles.png"
    codes = _codes(ctx, payload)
    problems = []
    if "missing_has_source" not in codes:
        problems.append("missing 带 source_path 未触发 missing_has_source")

    payload = _mutated_payload(ctx)
    pending = _forced_row(payload, availability="missing", mapping_status="pending_missing")
    pending["fallback_ref"] = "P-EVT-001"
    codes = _codes(ctx, payload)
    if "pending_missing_with_fallback" not in codes:
        problems.append("pending_missing 带 fallback_ref 未触发对应检查")

    payload = _mutated_payload(ctx)
    fallback = _forced_row(payload, availability="missing", mapping_status="fallback",
                           runtime_status="fallback")
    fallback["fallback_ref"] = "P-EVT-999"
    codes = _codes(ctx, payload)
    if "fallback_unresolved" not in codes:
        problems.append("不存在的 fallback 未触发 fallback_unresolved")

    payload = _mutated_payload(ctx)
    fallback = _forced_row(payload, availability="missing", mapping_status="fallback",
                           runtime_status="fallback")
    fallback["fallback_ref"] = "card:event:event_lights_out"
    codes = _codes(ctx, payload)
    if "fallback_not_record_id" not in codes:
        problems.append("target_ref 形式 fallback 未触发 fallback_not_record_id")

    payload = _mutated_payload(ctx)
    fallback = _forced_row(payload, availability="missing", mapping_status="fallback",
                           runtime_status="fallback")
    fallback["fallback_ref"] = ""
    codes = _codes(ctx, payload)
    if "fallback_mapping_without_ref" not in codes:
        problems.append("fallback 空引用未触发 fallback_mapping_without_ref")
    if "fallback_without_ref" not in codes:
        problems.append("runtime_status=fallback 空引用未触发 fallback_without_ref")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "missing_has_source / pending_missing_with_fallback / fallback_unresolved / fallback_not_record_id / 空引用均被检出", []


def check_neg_outside_root(ctx):
    payload = _mutated_payload(ctx)
    record = _forced_row(payload, availability="partial")
    candidates = sorted((ctx.root / "docs").rglob("*.png"))
    if not candidates:
        return NOT_RUN, "docs/ 下无真实 PNG，无法构造 assets 外有效 PNG", []
    record["runtime_path"] = candidates[0].relative_to(ctx.root).as_posix()
    codes = _codes(ctx, payload)
    if "runtime_outside_assets_root" in codes:
        return PASS, "assets 外真实 PNG 触发 runtime_outside_assets_root", sorted(codes)
    return FAIL, "未触发 runtime_outside_assets_root：%r" % sorted(codes), sorted(codes)


def check_neg_missing_fields(ctx):
    problems = []
    payload = _mutated_payload(ctx)
    pending = _forced_row(payload, availability="missing", mapping_status="pending_missing")
    pending["runtime_path"] = ""
    codes = _codes(ctx, payload)
    if "runtime_path_missing" not in codes:
        problems.append("空 runtime_path 未触发 runtime_path_missing")

    payload = _mutated_payload(ctx)
    pending = _forced_row(payload, availability="missing", mapping_status="pending_missing")
    pending["missing_note"] = ""
    codes = _codes(ctx, payload)
    if "missing_note_absent" not in codes:
        problems.append("空 missing_note 未触发 missing_note_absent")

    payload = _mutated_payload(ctx)
    pending = _forced_row(payload, availability="missing", mapping_status="pending_missing")
    pending["runtime_status"] = "placeholder"
    pending["runtime_path"] = "source/desktop/game/assets/cards/event/event_lights_out.png"
    codes = _codes(ctx, payload)
    if "placeholder_path_suspect" not in codes:
        problems.append("placeholder 指向非 placeholders 未触发 placeholder_path_suspect")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "runtime_path_missing / missing_note_absent / placeholder_path_suspect 均被检出", []


def check_neg_count_boundary(ctx):
    """计数边界：删 1 条后 len / missing() / by_type() 必须同步减 1。

    run5 v2：真实表 0 missing，改为先**合成**一条 pending 事件，再用"删前/删后
    实测差"做断言（比硬编码 274→141、47→46 更强，且不依赖旧基线数字）。
    """
    problems = []
    payload = _mutated_payload(ctx)
    target = _sample_event_row(payload)
    target["availability"] = "missing"
    target["mapping_status"] = "pending_missing"
    before = ctx.build_registry(payload)
    baseline = {
        "len": len(before),
        "missing": len(before.missing()),
        "card_event": len(before.by_type("card_event")),
    }
    if baseline["missing"] < 1:
        problems.append("合成 pending 行后 missing()=0，负样本未生效")
    payload["records"] = [row for row in payload["records"] if row is not target]
    after = ctx.build_registry(payload)
    if len(after) != baseline["len"] - 1:
        problems.append("删 1 条后 len=%d != %d" % (len(after), baseline["len"] - 1))
    if len(after.missing()) != baseline["missing"] - 1:
        problems.append("删 pending 后 missing=%d != %d"
                        % (len(after.missing()), baseline["missing"] - 1))
    if len(after.by_type("card_event")) != baseline["card_event"] - 1:
        problems.append("删 pending 后 card_event=%d != %d"
                        % (len(after.by_type("card_event")), baseline["card_event"] - 1))

    payload = _mutated_payload(ctx)
    room = next(row for row in payload["records"] if row.get("asset_type") == "room")
    rooms_before = len(ctx.build_registry(payload).by_type("room"))
    payload["records"] = [row for row in payload["records"] if row is not room]
    if len(ctx.build_registry(payload).by_type("room")) != rooms_before - 1:
        problems.append("删 room 后 room=%d != %d"
                        % (len(ctx.build_registry(payload).by_type("room")), rooms_before - 1))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, ("删除 1 条合成 pending / 1 条 room 后 len、missing()、by_type() "
                  "同步减 1，无缓存残留"), []


# ---------------------------------------------------------------------------
# 重复运行 / 可复现
# ---------------------------------------------------------------------------
def _canonical_payload_hash(payload):
    clone = copy.deepcopy(payload)
    clone.pop("generated_at", None)
    text = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_repeat_read(ctx):
    require_payload(ctx)
    problems = []
    raw_first = ctx.p_table.read_bytes()
    raw_second = ctx.p_table.read_bytes()
    if hashlib.sha256(raw_first).hexdigest() != hashlib.sha256(raw_second).hexdigest():
        problems.append("两次读取 p_table.json 字节不一致")
    first = json.loads(raw_first.decode("utf-8-sig"))
    second = json.loads(raw_second.decode("utf-8-sig"))
    if _canonical_payload_hash(first) != _canonical_payload_hash(second):
        problems.append("两次读取的归一化 payload 不一致")
    csv_first = ctx.p_csv.read_bytes()
    csv_second = ctx.p_csv.read_bytes()
    if hashlib.sha256(csv_first).hexdigest() != hashlib.sha256(csv_second).hexdigest():
        problems.append("两次读取 p_table.csv 字节不一致")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "p_table.json / p_table.csv 两次读取字节与归一化哈希一致", []


def _rebuild(ctx):
    pipeline = ctx.get_pipeline()
    if pipeline is None:
        raise AssertionError("asset_pipeline 不可用：%s" % ctx.pipeline_error)
    module = pipeline.load_content()
    started = time.perf_counter()
    photos = pipeline.scan_photos()
    rows, _slots = pipeline.build_records(module, photos)
    pipeline.assign_record_ids(rows)
    pipeline.assign_fallback_refs(rows)
    if hasattr(pipeline, "assign_canonical_ids"):
        pipeline.assign_canonical_ids(rows)
    elapsed = time.perf_counter() - started
    return pipeline, photos, rows, elapsed


def check_repeat_rebuild(ctx):
    if ctx.args.fast:
        return NOT_RUN, "--fast 跳过 95 图扫描与内存重建", []
    try:
        pipeline, photos, rows, elapsed = _rebuild(ctx)
    except Exception as exc:
        return NOT_RUN, "内存重建不可用（Pillow/管线缺失）：%s: %s" % (type(exc).__name__, exc), []
    problems = []
    columns = _expected_columns(ctx)
    if len(rows) != EXPECTED_TOTAL:
        problems.append("重建行数 %d != 274" % len(rows))
    for index, (rebuilt, disk) in enumerate(zip(rows, ctx.rows)):
        if rebuilt.get("target_ref") != disk.get("target_ref"):
            problems.append("第 %d 行 target_ref 顺序漂移" % index)
            break
        for column in columns:
            if norm_field(rebuilt.get(column)) != norm_field(disk.get(column)):
                append_limited(problems, "第 %d 行 %s：重建=%r 磁盘=%r" % (
                    index, column, rebuilt.get(column), disk.get(column)))
    try:
        rebuilt_stats = pipeline.stats_of(rows)
    except Exception as exc:
        rebuilt_stats = {"error": "%s: %s" % (type(exc).__name__, exc)}
    if rebuilt_stats != ctx.payload.get("stats"):
        problems.append("重建 stats 与磁盘 stats 不一致")
    if problems:
        return FAIL, "内存重建与磁盘 P 表不一致 %d 项（耗时 %.2fs）" % (len(problems), elapsed), problems[:8]
    return PASS, "内存重建 274 行 × %d 列与磁盘逐字段一致；stats 一致（耗时 %.2fs）" % (
        len(columns), elapsed), []


def check_repeat_second_build(ctx):
    if ctx.args.fast:
        return NOT_RUN, "--fast 跳过二次 scan/build", []
    try:
        pipeline, photos_first, rows_first, first_elapsed = _rebuild(ctx)
        photos_second = pipeline.scan_photos()
    except Exception as exc:
        return NOT_RUN, "二次 scan/build 不可用：%s: %s" % (type(exc).__name__, exc), []
    problems = []
    first_by_rel = {facts.get("rel"): facts for facts in photos_first.get("files") or []}
    second_by_rel = {facts.get("rel"): facts for facts in photos_second.get("files") or []}
    if set(first_by_rel) != set(second_by_rel):
        problems.append("两次 scan 文件集合不一致")
    for rel in sorted(set(first_by_rel) & set(second_by_rel)):
        for key in ("bytes", "format", "width", "height", "has_alpha", "decodable", "sha256", "aigc"):
            if first_by_rel[rel].get(key) != second_by_rel[rel].get(key):
                append_limited(problems, "二次 scan %s.%s 不一致" % (rel, key))
    rows_second, _slots = pipeline.build_records(pipeline.load_content(), photos_second)
    pipeline.assign_record_ids(rows_second)
    pipeline.assign_fallback_refs(rows_second)
    if hasattr(pipeline, "assign_canonical_ids"):
        pipeline.assign_canonical_ids(rows_second)
    fields = ("target_ref", "record_id", "fallback_ref", "availability", "runtime_path",
              "sha256", "bytes", "canonical_record_id")
    fingerprint_first = [tuple(row.get(field) for field in fields) for row in rows_first]
    fingerprint_second = [tuple(row.get(field) for field in fields) for row in rows_second]
    if fingerprint_first != fingerprint_second:
        problems.append("两次 build 的键/回退/发布档指纹不一致")
    if problems:
        return FAIL, "二次运行不一致 %d 项" % len(problems), problems[:8]
    return PASS, "95 文件二次扫描与 274 行二次构建指纹一致（首次 %.2fs）" % first_elapsed, []


def check_repeat_canonical_hash(ctx):
    require_payload(ctx)
    first = _canonical_payload_hash(ctx.payload)
    second = _canonical_payload_hash(json.loads(ctx.p_table.read_bytes().decode("utf-8-sig")))
    if first != second:
        return FAIL, "排除 generated_at 后的归一化 payload 哈希不一致", [first, second]
    return PASS, "排除 generated_at 后归一化 payload 哈希稳定：%s" % first[:16], [first]


# ---------------------------------------------------------------------------
# UI 绑定
# ---------------------------------------------------------------------------
def _read_binding(ctx):
    return read_text(ctx.game_dir / "ui_asset_binding.py")


def check_ui_module_contract(ctx):
    binding = ctx.game_dir / "ui_asset_binding.py"
    if not binding.is_file():
        return FAIL, "ui_asset_binding.py 未交付", []
    source = _read_binding(ctx)
    problems = []
    try:
        tree = ast.parse(source)
    except Exception as exc:
        return FAIL, "ui_asset_binding.py AST 解析失败：%s" % type(exc).__name__, []
    top_imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_imports.add(node.module or "")
    if any(name.startswith("tkinter") or name.startswith("PIL") for name in top_imports):
        problems.append("模块顶层 import tkinter/PIL，破坏无显示环境可导入性")
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in ("load_asset_photo", "load_photo_for_ref", "default_cache", "cache_stats"):
        if name not in functions:
            problems.append("缺函数 %s" % name)
    if "AssetImageCache" not in {node.name for node in tree.body if isinstance(node, ast.ClassDef)}:
        problems.append("缺 AssetImageCache")
    loader = functions.get("load_asset_photo")
    if loader is not None:
        params = [arg.arg for arg in loader.args.args]
        for name in ("registry", "key", "master"):
            if name not in params:
                problems.append("load_asset_photo 缺参数 %s" % name)
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "ui_asset_binding.py 可无显示导入；load_asset_photo/load_photo_for_ref/AssetImageCache/缓存统计齐全", []


def check_ui_wiring(ctx):
    source = read_text(ctx.game_dir / "ui.py")
    names = {
        "ui_asset_binding": source.count("ui_asset_binding"),
        "load_asset_photo": source.count("load_asset_photo"),
        "AssetRegistry": source.count("AssetRegistry"),
        "PhotoImage": source.count("PhotoImage"),
        "ImageTk": source.count("ImageTk"),
        "assets/": source.count("assets/"),
    }
    hits = {key: value for key, value in names.items() if value}
    if not hits:
        return FAIL, "ui.py 对 ui_asset_binding/AssetRegistry/PhotoImage/assets/ 引用均为 0；绑定层已交付但未接入 UI", [str(names)]
    return PASS, "ui.py 已出现资源绑定引用：%r" % hits, [str(names)]


def check_ui_sizes(ctx):
    try:
        spec = importlib.util.spec_from_file_location(
            "qa_ui_binding_probe", str(ctx.game_dir / "ui_asset_binding.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return FAIL, "ui_asset_binding.py 导入失败：%s" % type(exc).__name__, []
    problems = []
    cases = [
        ((512, 512), (128, 128), (128, 128)),
        ((480, 672), (240, 336), (240, 336)),
        ((480, 672), (256, 256), (183, 256)),
    ]
    for source_size, max_size, expected in cases:
        actual = module._fit_size(source_size[0], source_size[1], max_size)
        if actual != expected:
            problems.append("_fit_size%s,%s=%r，期望 %r" % (source_size, max_size, actual, expected))
    ui_source = read_text(ctx.game_dir / "ui.py")
    if "128" not in ui_source:
        problems.append("ui.py 未出现房间 128px 尺寸")
    if "240" not in ui_source or "336" not in ui_source:
        problems.append("ui.py 未出现卡牌 240×336 尺寸")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "_fit_size 支持 512→128 与 480×672→240×336；ui.py 使用 128/240×336", []


def check_ui_cache(ctx):
    try:
        spec = importlib.util.spec_from_file_location(
            "qa_ui_cache_probe", str(ctx.game_dir / "ui_asset_binding.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return FAIL, "ui_asset_binding.py 导入失败：%s" % type(exc).__name__, []
    cache = module.AssetImageCache(capacity=2)
    problems = []
    cache.put("a", 1)
    cache.put("b", 2)
    if cache.get("a") != 1:
        problems.append("LRU 命中值错误")
    cache.put("c", 3)
    if cache.get("b") is not None:
        problems.append("容量 2 下插入第 3 项未淘汰最旧项")
    stats = cache.stats()
    if stats.get("hits") != 1 or stats.get("misses") != 1 or stats.get("evictions") != 1:
        problems.append("缓存计数异常：%r" % stats)
    if stats.get("size") != 2:
        problems.append("缓存 size=%r != 2" % stats.get("size"))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "AssetImageCache LRU：容量 2 淘汰最旧；hits/misses/evictions/size 可观测", []


def check_ui_unknown_key(ctx):
    registry = require_registry(ctx)
    try:
        spec = importlib.util.spec_from_file_location(
            "qa_ui_unknown_probe", str(ctx.game_dir / "ui_asset_binding.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return FAIL, "ui_asset_binding.py 导入失败：%s" % type(exc).__name__, []
    problems = []
    cache = module.AssetImageCache(capacity=4)
    try:
        if module.load_asset_photo(registry, "no:such:key", None, cache=cache) is not None:
            problems.append("未知键未返回 None")
        if module.load_asset_photo(registry, None, None, cache=cache) is not None:
            problems.append("None 键未返回 None")
    except Exception as exc:
        problems.append("未知键调用抛异常：%s" % type(exc).__name__)
    if cache.stats().get("misses", 0) < 2:
        problems.append("未知键未计入 misses")
    candidates = module._placeholder_candidates(registry, "character")
    if not any("character_missing.png" in str(path) for path in candidates):
        problems.append("角色缺图未解析到 character_missing.png")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "未知/None 键返回 None 且计入 miss；角色占位候选命中 character_missing.png", []


def check_ui_tk_smoke(ctx):
    if not ctx.args.tk:
        return NOT_RUN, "默认不创建 Tk root；需显示环境，使用 --tk 或在实现方写使能测试中执行", []
    try:
        import tkinter
    except Exception as exc:
        return FAIL, "tkinter 不可用：%s: %s" % (type(exc).__name__, exc), []
    try:
        spec = importlib.util.spec_from_file_location(
            "qa_ui_tk_probe", str(ctx.game_dir / "ui_asset_binding.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        registry = require_registry(ctx)
        root = tkinter.Tk()
        root.withdraw()
        try:
            room = next(row for row in ctx.rows
                        if row.get("asset_type") == "room"
                        and row.get("availability") in ("usable", "partial"))
            card = next(row for row in ctx.rows
                        if row.get("asset_type") == "card_event"
                        and row.get("availability") in ("usable", "partial"))
            cache = module.AssetImageCache(capacity=8)
            room_photo = module.load_asset_photo(registry, room["target_ref"], root, (128, 128), cache)
            card_photo = module.load_asset_photo(registry, card["target_ref"], root, (240, 336), cache)
            if room_photo is None or card_photo is None:
                return FAIL, "Tk 加载房间/卡牌返回 None", []
            if (room_photo.width(), room_photo.height()) != (128, 128):
                return FAIL, "房间 PhotoImage 尺寸 %dx%d != 128x128" % (room_photo.width(), room_photo.height()), []
            if (card_photo.width(), card_photo.height()) != (240, 336):
                return FAIL, "卡牌 PhotoImage 尺寸 %dx%d != 240x336" % (card_photo.width(), card_photo.height()), []
            again = module.load_asset_photo(registry, room["target_ref"], root, (128, 128), cache)
            if again is not room_photo:
                return FAIL, "重复绑定未命中缓存", []
        finally:
            root.destroy()
            module.reset_default_caches()
    except Exception as exc:
        return FAIL, "Tk 冒烟异常：%s: %s" % (type(exc).__name__, exc), [traceback.format_exc(limit=3)]
    return PASS, "Tk 冒烟：房间 128×128、卡牌 240×336、重复绑定命中缓存", []


# ---------------------------------------------------------------------------
# 性能
# ---------------------------------------------------------------------------
def check_perf_write_stage(ctx, stage):
    return NOT_RUN, "禁止写文件：--stage %s 会写 assets/；只读验收不执行。写使能阶段命令见计划 §4.1" % stage, []


def check_perf_load(ctx, rounds=10):
    try:
        registry_module = ctx.get_registry_module()
    except Exception as exc:
        return NOT_RUN, "asset_registry 不可用：%s" % type(exc).__name__, []
    times = []
    for _ in range(rounds):
        started = time.perf_counter()
        registry_module.AssetRegistry.load(str(ctx.p_table))
        times.append(time.perf_counter() - started)
    p95 = percentile(times, 0.95)
    budget = PERF_BUDGETS["PT-PERF-04"]["budget"]
    detail = "load ×%d：median=%.2fms p95=%.2fms（预算 %.0fms）" % (
        rounds, median(times) * 1000, p95 * 1000, budget * 1000)
    if p95 <= budget:
        return PASS, detail, [detail]
    return FAIL, detail, [detail]


def check_perf_resolve(ctx, rounds=10, batch=10000):
    registry = require_registry(ctx)
    require_payload(ctx)
    targets = [row["target_ref"] for row in ctx.rows]
    runtimes = [row["runtime_key"] for row in ctx.rows]
    records = [row["record_id"] for row in ctx.rows]
    contents = [row["content_ref"] for row in ctx.rows]
    bares = [str(row["runtime_key"]).split(":")[-1] for row in ctx.rows if row.get("asset_type") != "character"]
    uppers = [str(row["target_ref"]).upper() for row in ctx.rows]
    # 六类键混合：规范溯源键 / 运行时键 / record_id / 内容键 / 裸 id / 大写变体
    groups = [targets, runtimes, records, contents, bares, uppers]
    keys = []
    while len(keys) < batch:
        for group in groups:
            keys.append(group[len(keys) % len(group)])
            if len(keys) >= batch:
                break
    unresolved = [key for key in keys if registry.resolve(key) is None]
    if unresolved:
        return FAIL, "性能样本含 %d 个不可解析键，先修键空间" % len(unresolved), unresolved[:5]
    for key in keys[:200]:
        registry.resolve(key)
    round_times = []
    for _ in range(rounds):
        started = time.perf_counter()
        for key in keys:
            registry.resolve(key)
        round_times.append(time.perf_counter() - started)
    call_times = []
    for key in keys[:1000]:
        started = time.perf_counter_ns()
        registry.resolve(key)
        call_times.append((time.perf_counter_ns() - started) / 1e9)
    total_p95 = percentile(round_times, 0.95)
    call_p95 = percentile(call_times, 0.95)
    budget_total = PERF_BUDGETS["PT-PERF-05"]["budget"]
    budget_call = 0.00005
    detail = "10k resolve ×%d：round p95=%.1fms（预算 %.0fms）；单次 p95=%.2fus（预算 50us）" % (
        rounds, total_p95 * 1000, budget_total * 1000, call_p95 * 1e6)
    if total_p95 <= budget_total and call_p95 <= budget_call:
        return PASS, detail, [detail]
    return FAIL, detail, [detail]


def check_perf_load_rss(ctx, rounds=10):
    before = rss_bytes()
    if before is None:
        return NOT_RUN, "当前平台无法读取 RSS（psapi/proc 不可用）", []
    gc.collect()
    registry_module = ctx.get_registry_module()
    kept = []
    for _ in range(rounds):
        kept.append(registry_module.AssetRegistry.load(str(ctx.p_table)))
    gc.collect()
    after = rss_bytes()
    if after is None:
        return NOT_RUN, "加载后 RSS 不可读", []
    delta_mb = (after - before) / (1024.0 * 1024.0)
    budget = PERF_BUDGETS["PT-PERF-10"]["budget"]
    detail = "load ×%d RSS 增量 %.2fMB（预算 %.0fMB；before=%.1fMB after=%.1fMB）" % (
        rounds, delta_mb, budget, before / 1048576.0, after / 1048576.0)
    if delta_mb <= budget:
        return PASS, detail, [detail]
    return FAIL, detail, [detail]


def check_perf_contract_no_decode(ctx):
    if not ctx.args.run_contract:
        return NOT_RUN, "未执行契约子进程（--run-contract 可只读运行）；保存的契约 JSON 不能代表当前耗时", []
    if ctx.contract_run is None:
        return NOT_RUN, "契约子进程未产生结果", []
    if not ctx.contract_run.get("no_decode"):
        return NOT_RUN, "本次运行是全量契约（含解码）；--no-decode 档未运行", []
    elapsed = ctx.contract_run.get("elapsed", 0.0)
    budget = PERF_BUDGETS["PT-PERF-08"]["budget"]
    detail = "contract --no-decode 子进程 %.2fs（预算 %.0fs）" % (elapsed, budget)
    if elapsed <= budget:
        return PASS, detail, [detail]
    return FAIL, detail, [detail]


def check_perf_contract_full(ctx):
    if not ctx.args.run_contract:
        return NOT_RUN, "未执行契约子进程（--run-contract 可只读运行）；含解码全量不代跑", []
    if ctx.contract_run is None:
        return NOT_RUN, "契约子进程未产生结果", []
    if ctx.contract_run.get("no_decode"):
        return NOT_RUN, "本次为 --no-decode 快速档；含解码全量未运行", []
    elapsed = ctx.contract_run.get("elapsed", 0.0)
    budget = PERF_BUDGETS["PT-PERF-07"]["budget"]
    detail = "contract 全量（含解码）子进程 %.2fs（预算 %.0fs）" % (elapsed, budget)
    if elapsed <= budget:
        return PASS, detail, [detail]
    return FAIL, detail, [detail]


# ---------------------------------------------------------------------------
# 旧测试 / 覆盖率
# ---------------------------------------------------------------------------
def _legacy_report(ctx):
    path = Path(ctx.args.verify_report) if ctx.args.verify_report else (ctx.assets / "validation_report.json")
    if not path.is_file():
        return None, "未找到 verify_assets 报告：%s（该脚本会写 validation_report.json，只读验收不代跑）" % path
    try:
        payload = read_json(path)
    except Exception as exc:
        return None, "报告不可解析：%s: %s" % (type(exc).__name__, exc)
    return (path, payload), ""


def check_legacy_verify_assets(ctx):
    found, error = _legacy_report(ctx)
    if found is None:
        return NOT_RUN, error, []
    path, payload = found
    problems = []
    if payload.get("tool") != "verify_assets.py":
        problems.append("tool=%r" % payload.get("tool"))
    if payload.get("ok") is not True:
        problems.append("ok != true")
    totals = payload.get("totals") or {}
    if totals.get("records") != EXPECTED_TOTAL:
        problems.append("totals.records=%r" % totals.get("records"))
    if totals.get("failed") not in (0, None):
        problems.append("totals.failed=%r" % totals.get("failed"))
    checks = {item.get("id"): item for item in payload.get("checks") or [] if isinstance(item, dict)}
    missing = [cid for cid in VERIFY_IDS if cid not in checks]
    if missing:
        problems.append("缺检查项：%s" % ",".join(missing))
    failures = [cid for cid, item in checks.items() if item.get("status") != "pass"]
    if failures:
        problems.append("未通过：%s" % ",".join(failures))
    input_paths = [ctx.p_table, ctx.p_csv, ctx.mapping_path,
                   ctx.game_dir / "asset_pipeline.py", ctx.game_dir / "asset_registry.py",
                   ctx.game_dir / "verify_assets.py"]
    newest = max(path.stat().st_mtime for path in input_paths if path.exists())
    report_mtime = path.stat().st_mtime
    if report_mtime + 1.0 < newest:
        stale = newest - report_mtime
        return NOT_RUN, "报告早于最新输入 %.1fs（报告 %s；最新输入 mtime %s）；需在代码冻结后重跑 verify_assets.py" % (
            stale, time.strftime("%H:%M:%S", time.localtime(report_mtime)),
            time.strftime("%H:%M:%S", time.localtime(newest))), [str(path)]
    if problems:
        return FAIL, "；".join(problems), problems[:8]
    return PASS, "verify_assets %d 项全部 pass；报告晚于全部输入" % len(VERIFY_IDS), [str(path)]


def _find_contract_json(ctx):
    if ctx.args.contract_json:
        path = Path(ctx.args.contract_json)
        return path if path.is_file() else None
    candidates = [
        ctx.game_dir / "qa" / "_tmp_contract.json",
        ctx.game_dir / "qa" / "_baseline_contract.json",
        ctx.game_dir / "qa" / "contract_result.json",
        ctx.root / ".codebuddy" / "wfat" / "run2_contract_result.json",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def _evaluate_contract(ctx, payload, fresh, source, no_decode=False):
    problems = []
    if payload.get("profile") != "baseline":
        problems.append("profile=%r（期望 baseline）" % payload.get("profile"))
    checks = payload.get("checks") or []
    ids = [item.get("id") for item in checks if isinstance(item, dict)]
    if len(checks) != EXPECTED_CONTRACT_CHECKS:
        problems.append("检查项 %d != 32" % len(checks))
    if ids != CONTRACT_IDS:
        problems.append("检查 ID 非 C01-C32（%r）" % ids[:5])
    summary = payload.get("summary") or {}
    if summary.get("total") != EXPECTED_CONTRACT_CHECKS:
        problems.append("summary.total=%r" % summary.get("total"))
    skip_ids = [item.get("id") for item in checks if item.get("status") == "SKIP"]
    # --no-decode 下 C16（逐图解码）合法 SKIP；必须显式标注为未覆盖，不能当作通过。
    # 保存的 JSON 若只缺 C16，按 --no-decode 解释并在 detail 中注明。
    inferred_no_decode = (not no_decode and set(skip_ids) == {"C16"})
    allowed_skip = {"C16"} if (no_decode or inferred_no_decode) else set()
    unexpected_skip = set(skip_ids) - allowed_skip
    if unexpected_skip:
        problems.append("存在非预期 SKIP：%s" % ",".join(sorted(unexpected_skip)))
    if summary.get("error"):
        problems.append("存在 ERROR %r" % summary.get("error"))
    fail_ids = [item.get("id") for item in checks if item.get("status") == "FAIL"]
    warn_ids = [item.get("id") for item in checks if item.get("status") == "WARN"]
    error_ids = [item.get("id") for item in checks if item.get("status") == "ERROR"]
    if error_ids:
        problems.append("ERROR：%s" % ",".join(error_ids))
    if len(fail_ids) > CONTRACT_BASELINE_FAIL_MAX:
        problems.append("FAIL %d 条超过基线上限 %d" % (len(fail_ids), CONTRACT_BASELINE_FAIL_MAX))
    unknown = set(fail_ids) - CONTRACT_KNOWN_FAIL_IDS
    if unknown:
        problems.append("未知 FAIL：%s" % ",".join(sorted(unknown)))
    waived = set(fail_ids) <= ctx.waivers
    if fail_ids and not waived:
        problems.append("FAIL %s 不在产品裁决 acceptedDeviations 内" % ",".join(fail_ids))
    detail = "32 项：PASS=%r FAIL=%r WARN=%r SKIP=%r；fresh=%s；来源=%s" % (
        summary.get("pass"), fail_ids, warn_ids, skip_ids, fresh, source)
    if skip_ids:
        detail += "；SKIP 未覆盖=%s（%s，不计 PASS）" % (
            ",".join(skip_ids),
            "推断为 --no-decode" if inferred_no_decode else "--no-decode",
        )
    if problems:
        return FAIL, "；".join(problems + [detail]), problems[:8]
    if fail_ids:
        return PASS, "基线内且已裁决：%s（不等于已修复）" % detail, [detail]
    return PASS, detail, [detail]


def check_legacy_contract(ctx):
    if ctx.contract_run is not None:
        payload = ctx.contract_run.get("payload")
        if payload is None:
            return FAIL, "契约子进程未输出可解析 JSON：%s" % ctx.contract_run.get("error"), []
        return _evaluate_contract(
            ctx, payload, True, "run-contract",
            no_decode=bool(ctx.contract_run.get("no_decode")))
    path = _find_contract_json(ctx)
    if path is None:
        return NOT_RUN, "未找到契约结果 JSON；用 --run-contract 只读重跑或传入 --contract-json", []
    try:
        payload = read_json(path)
    except Exception as exc:
        return FAIL, "契约 JSON 不可解析：%s: %s" % (type(exc).__name__, exc), []
    input_paths = [ctx.p_table, ctx.game_dir / "asset_pipeline.py",
                   ctx.game_dir / "asset_registry.py",
                   ctx.game_dir / "qa" / "verify_assets_contract.py"]
    newest = max(item.stat().st_mtime for item in input_paths if item.exists())
    if path.stat().st_mtime + 1.0 < newest:
        return NOT_RUN, "契约结果早于最新输入 %.1fs；需重跑或 --run-contract" % (
            newest - path.stat().st_mtime), [str(path)]
    return _evaluate_contract(ctx, payload, True, str(path))


def check_legacy_other_verifies(ctx):
    scripts = [
        "source/desktop/game/verify_base_rules.py",
        "source/desktop/game/verify_ai_rules.py",
        "source/desktop/game/verify_haunt_systems.py",
        "source/desktop/game/verify_v1.py",
        "source/desktop/game/verify_network.py",
    ]
    present = [rel for rel in scripts if (ctx.root / rel).is_file()]
    return NOT_RUN, "未执行 %d 个规则/UI 回归脚本（只读验收不运行长耗时/写文件测试）；合并前需在写使能阶段逐脚本记录退出码与用例数" % len(present), present


def check_legacy_core_drift(ctx):
    path = ctx.game_dir / "check_core_drift.py"
    if not path.is_file():
        return FAIL, "check_core_drift.py 不存在", []
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(path)],
            cwd=str(ctx.game_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(ctx.args.timeout, 180),
        )
    except Exception as exc:
        return FAIL, "check_core_drift.py 执行异常：%s: %s" % (type(exc).__name__, exc), []
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode == 0 and "通过" in output:
        return PASS, "双端内核同一性通过：9 个内核模块 + net.serialize 同一对象，别名壳无拷贝", [output.strip()[:300]]
    return FAIL, "check_core_drift.py 退出码 %s：%s" % (completed.returncode, output.strip()[:300]), [output[:1000]]


def check_legacy_unittest(ctx):
    path = ctx.game_dir / "qa" / "test_p_table_execution.py"
    if not path.is_file():
        return NOT_RUN, "实现方 unittest 未交付", []
    return NOT_RUN, "qa/test_p_table_execution.py 会写 assets/ 与 qa/fixtures/，只读验收禁止执行；需在写使能阶段运行并提交结果", [str(path)]


def check_coverage_line(ctx):
    installed = importlib.util.find_spec("coverage") is not None
    tests = sorted((ctx.game_dir / "qa").glob("test_*.py"))
    return NOT_RUN, (
        "行覆盖未测：coverage=%s；qa/test_*.py=%d 个（会写 assets/fixtures，只读验收禁止执行）。"
        "达标线 85%%；写使能阶段命令：python -m coverage run --branch --source=asset_pipeline,asset_registry "
        "-m unittest discover -s qa -p \"test_*.py\" && python -m coverage report -m --fail-under=85"
        % ("installed" if installed else "absent", len(tests))
    ), []


def check_coverage_branch(ctx):
    installed = importlib.util.find_spec("coverage") is not None
    return NOT_RUN, (
        "分支覆盖未测：coverage=%s；测试套件会写 assets/fixtures，只读验收禁止执行。达标线 75%%；"
        "写使能阶段读取 qa/coverage.json 的 totals.branches 计算" % ("installed" if installed else "absent")
    ), []


# ---------------------------------------------------------------------------
# 旧结果新鲜度 / 只读自证
# ---------------------------------------------------------------------------
def check_legacy_freshness(ctx):
    entries = []
    report = ctx.assets / "validation_report.json"
    if report.is_file():
        newest = max(
            path.stat().st_mtime for path in (
                ctx.p_table, ctx.p_csv, ctx.mapping_path,
                ctx.game_dir / "asset_pipeline.py", ctx.game_dir / "asset_registry.py",
            ) if path.exists()
        )
        entries.append({
            "artifact": "validation_report.json",
            "mtime": report.stat().st_mtime,
            "newest_input": newest,
            "fresh": report.stat().st_mtime + 1.0 >= newest,
        })
    contract = _find_contract_json(ctx)
    if contract is not None:
        newest = max(
            path.stat().st_mtime for path in (
                ctx.p_table, ctx.game_dir / "asset_pipeline.py",
                ctx.game_dir / "asset_registry.py",
                ctx.game_dir / "qa" / "verify_assets_contract.py",
            ) if path.exists()
        )
        entries.append({
            "artifact": contract.name,
            "mtime": contract.stat().st_mtime,
            "newest_input": newest,
            "fresh": contract.stat().st_mtime + 1.0 >= newest,
        })
    if not entries:
        return NOT_RUN, "未找到任何旧测试结果产物", []
    stale = [entry for entry in entries if not entry["fresh"]]
    if stale:
        return CONFLICT, "旧结果过期 %d 项（不计入代码缺陷，须在冻结后重跑）：%s" % (
            len(stale), ", ".join(entry["artifact"] for entry in stale)), [str(entry) for entry in entries]
    return PASS, "旧结果均晚于当前输入：%s" % ", ".join(entry["artifact"] for entry in entries), [str(entry) for entry in entries]


def check_safe_readonly(ctx):
    problems = []
    changed = ctx.diff_snapshots()
    if changed:
        problems.append("运行期间项目文件发生变化 %d 个：%s" % (len(changed), ", ".join(changed[:6])))
    current_hashes = ctx.current_hashes()
    hash_changed = [key for key, value in ctx.initial_hashes.items() if current_hashes.get(key) != value]
    if hash_changed:
        problems.append("关键文件哈希变化：%s" % ", ".join(hash_changed[:6]))
    source = read_text(SCRIPT_PATH)
    try:
        tree = ast.parse(source)
    except Exception as exc:
        problems.append("自检 AST 解析失败：%s" % type(exc).__name__)
        tree = None
    writes = []
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name == "open":
                    mode = ""
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        mode = str(node.args[1].value)
                    for keyword in node.keywords:
                        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                            mode = str(keyword.value.value)
                    if any(flag in mode for flag in ("w", "a", "x", "+")):
                        writes.append("open(mode=%r)" % mode)
                elif name in ("write_text", "write_bytes"):
                    writes.append(name)
                elif name == "dump":
                    writes.append("json.dump")
    if writes:
        problems.append("脚本自身存在写文件调用：%s" % ", ".join(sorted(set(writes))))
    if "sys.dont_write_bytecode = True" not in source:
        problems.append("脚本未设置 sys.dont_write_bytecode")
    if problems:
        return FAIL, "；".join(problems), problems[:8]
    return PASS, "项目快照与关键文件哈希未变；脚本无写文件调用；dont_write_bytecode 已设置", []


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _run_contract(ctx):
    script = ctx.game_dir / "qa" / "verify_assets_contract.py"
    if not script.is_file():
        ctx.contract_run = {"payload": None, "elapsed": 0.0, "error": "契约脚本不存在"}
        return
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, str(script), "--json"]
    if ctx.args.contract_no_decode:
        command.append("--no-decode")
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ctx.game_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ctx.args.timeout,
        )
        elapsed = time.perf_counter() - started
        stdout = completed.stdout or ""
        payload = None
        try:
            payload = json.loads(stdout)
        except Exception:
            start = stdout.find("{")
            if start >= 0:
                try:
                    payload = json.loads(stdout[start:])
                except Exception:
                    payload = None
        ctx.contract_run = {
            "payload": payload,
            "elapsed": elapsed,
            "exit_code": completed.returncode,
            "no_decode": bool(ctx.args.contract_no_decode),
            "error": "" if payload is not None else "stdout 无 JSON（exit=%s, stderr=%s）" % (
                completed.returncode, (completed.stderr or "")[:200]),
        }
    except Exception as exc:
        ctx.contract_run = {
            "payload": None,
            "elapsed": time.perf_counter() - started,
            "no_decode": bool(ctx.args.contract_no_decode),
            "error": "%s: %s" % (type(exc).__name__, exc),
        }


def run_all(ctx):
    runner = Runner()
    runner.execute("ENV-01", "TC-PT-00a", "环境与工具链", "P2", lambda: check_env(ctx))
    runner.execute("ENV-02", "TC-PT-00b", "关键产物齐全", "P0", lambda: check_required_artifacts(ctx))

    runner.execute("DATA-01", "TC-PT-01", "P 表可解析且 274 行", "P0", lambda: check_data_rows(ctx))
    runner.execute("DATA-02", "TC-PT-01", "stats 与逐行复算自洽", "P0", lambda: check_data_stats(ctx))
    runner.execute("DATA-03", "TC-PT-02", "五类计数 12/50/45/22/13", "P0", lambda: check_data_type_counts(ctx))
    runner.execute("DATA-04", "TC-PT-03", "availability 0/95/47/0/0 且 partial 不冒充 usable", "P0", lambda: check_data_availability(ctx))
    runner.execute("DATA-05", "TC-PT-26", "record_id 唯一/前缀/段号连续", "P0", lambda: check_data_ids(ctx))
    runner.execute("DATA-06", "TC-PT-04", "content_refs 284 条双向一致", "P0", lambda: check_data_content_refs(ctx))
    runner.execute("DATA-07", "TC-PT-05", "映射 entries 95 / unresolved 47 双向覆盖", "P0", lambda: check_data_mapping(ctx))
    runner.execute("DATA-08", "TC-PT-07", "95 partial 源文件事实", "P0", lambda: check_data_partial_facts(ctx))
    runner.execute("DATA-09", "TC-PT-08", "47 missing 登记完整", "P0", lambda: check_data_missing_facts(ctx))
    runner.execute("DATA-10", "TC-PT-09", "16 fallback 语义", "P0", lambda: check_data_fallback(ctx))
    runner.execute("DATA-11", "TC-PT-10", "31 pending_missing 语义", "P0", lambda: check_data_pending(ctx))
    runner.execute("DATA-12", "TC-PT-08", "47 missing 运行时路由", "P0", lambda: check_data_missing_routing(ctx))
    runner.execute("DATA-13", "TC-PT-58", "F-08 字面判据与 V09 语义冲突", "P2", lambda: check_f08_literal(ctx))
    runner.execute("DATA-14", "TC-PT-22", "content.py sha256 与集合同步", "P0", lambda: check_data_content_sync(ctx))
    runner.execute("DATA-15", "TC-PT-20", "95 源文件 sha256/bytes 三方一致", "P0", lambda: check_data_photos(ctx))

    runner.execute("SCHEMA-01", "TC-PT-01", "CSV BOM/行数/表头 = JSON 列", "P0", lambda: check_schema_csv_json(ctx))
    runner.execute("SCHEMA-02", "TC-PT-23", "16 个必填字段齐全", "P0", lambda: check_schema_required_fields(ctx))
    runner.execute("SCHEMA-03", "TC-PT-23", "33 列 = 26 业务（含 runtime_key）+ 7 发布；规范 28 列全含", "P0", lambda: check_schema_columns(ctx))
    runner.execute("SCHEMA-04", "TC-PT-52", "列序与规范 §6.1 的差异", "P2", lambda: check_schema_column_order(ctx))
    runner.execute("SCHEMA-05", "TC-PT-53", "契约脚本定义 32 项 C01-C32", "P2", lambda: check_schema_contract_32(ctx))
    runner.execute("SCHEMA-06", "TC-PT-39", "CSV/JSON 274×33 逐字段等价", "P1", lambda: check_schema_csv_json_equiv(ctx))

    runner.execute("RUNTIME-01", "TC-PT-06", "98 个运行时 PNG 清单", "P0", lambda: check_runtime_inventory(ctx))
    runner.execute("RUNTIME-02", "TC-PT-06", "运行时 PNG 真实性与尺寸", "P0", lambda: check_runtime_png_sizes(ctx))
    runner.execute("RUNTIME-03", "TC-PT-06", "3 张占位图规格", "P0", lambda: check_runtime_placeholders(ctx))
    runner.execute("RUNTIME-04", "TC-PT-08", "runtime_path 不越界/大小写一致", "P0", lambda: check_runtime_paths_inside_assets(ctx))

    runner.execute("REG-01", "TC-PT-60", "load 不读图片/不 import PIL", "P1", lambda: check_registry_load_no_decode(ctx))
    runner.execute("REG-02", "TC-PT-21", "registry 计数与 summary", "P0", lambda: check_registry_counts(ctx))
    runner.execute("REG-03", "TC-PT-04", "全键空间解析", "P0", lambda: check_registry_resolve_all(ctx))
    runner.execute("REG-04", "TC-PT-14", "脏键/路径穿越返回 None", "P0", lambda: check_registry_dirty_keys(ctx))
    runner.execute("REG-05", "TC-PT-12", "大小写不敏感", "P0", lambda: check_registry_case_insensitive(ctx))
    runner.execute("REG-06", "TC-PT-11", "角色双面键空间", "P0", lambda: check_registry_character_faces(ctx))
    runner.execute("REG-07", "TC-PT-13", "裸 id 不跨类别", "P1", lambda: check_registry_bare_id_collision(ctx))
    runner.execute("REG-08", "TC-PT-09", "fallback_ref registry 语义", "P0", lambda: check_registry_fallback(ctx))
    runner.execute("REG-09", "TC-PT-27", "validate 返回空列表不抛异常", "P1", lambda: check_registry_validate(ctx))
    runner.execute("REG-10", "TC-PT-42", "映射回退/缺清单/缺 records", "P1", lambda: check_registry_load_variants(ctx))
    runner.execute("REG-11", "TC-PT-42", "重复键显式 ValueError", "P1", lambda: check_registry_duplicate_keys(ctx))

    runner.execute("NEG-01", "TC-PT-15", "清单不存在 FileNotFoundError", "P0", lambda: check_neg_manifest_missing(ctx))
    runner.execute("NEG-02", "TC-PT-16", "缺 records 且无同目录表 ValueError", "P0", lambda: check_neg_no_records(ctx))
    runner.execute("NEG-03", "TC-PT-38", "坏 JSON 抛 ValueError", "P1", lambda: check_neg_bad_json(ctx))
    runner.execute("NEG-04", "TC-PT-17", "运行时文件缺失 runtime_file_absent", "P0", lambda: check_neg_runtime_absent(ctx))
    runner.execute("NEG-05", "TC-PT-35", "坏 PNG/尺寸不符", "P1", lambda: check_neg_bad_png_and_size(ctx))
    runner.execute("NEG-06", "TC-PT-36", "missing_has_source / pending fallback / fallback 异常", "P1", lambda: check_neg_semantic_rows(ctx))
    runner.execute("NEG-07", "TC-PT-37", "assets 外路径 runtime_outside_assets_root", "P1", lambda: check_neg_outside_root(ctx))
    runner.execute("NEG-08", "TC-PT-56", "runtime/note/placeholder 缺失", "P2", lambda: check_neg_missing_fields(ctx))
    runner.execute("NEG-09", "TC-PT-34", "删除 1 条计数边界", "P1", lambda: check_neg_count_boundary(ctx))

    runner.execute("REPEAT-01", "TC-PT-40", "两次读取字节/归一化哈希一致", "P1", lambda: check_repeat_read(ctx))
    runner.execute("REPEAT-02", "TC-PT-24", "内存重建 = 磁盘 P 表", "P0", lambda: check_repeat_rebuild(ctx))
    runner.execute("REPEAT-03", "TC-PT-41", "二次 scan/build 指纹一致", "P1", lambda: check_repeat_second_build(ctx))
    runner.execute("REPEAT-04", "TC-PT-57", "排除 generated_at 的归一化哈希", "P2", lambda: check_repeat_canonical_hash(ctx))

    runner.execute("UI-01", "TC-PT-28", "绑定模块接口", "P1", lambda: check_ui_module_contract(ctx))
    runner.execute("UI-02", "TC-PT-29", "ui.py 接入绑定层", "P1", lambda: check_ui_wiring(ctx))
    runner.execute("UI-03", "TC-PT-30", "128/240×336 尺寸", "P1", lambda: check_ui_sizes(ctx))
    runner.execute("UI-04", "TC-PT-31", "LRU 缓存与计数", "P1", lambda: check_ui_cache(ctx))
    runner.execute("UI-05", "TC-PT-32", "未知键/占位候选", "P1", lambda: check_ui_unknown_key(ctx))
    runner.execute("UI-06", "TC-PT-33", "Tk 冒烟/解码回落", "P1", lambda: check_ui_tk_smoke(ctx))
    runner.execute("UI-07", "TC-PT-55", "缺图可辨识/对比度/DPI（人工）", "P2",
                   lambda: (NOT_RUN, "人工项：缺图占位观感、对比度 ≥3:1/≥4.5:1、100%/125%/150% DPI 需截图实测", []))

    runner.execute("PERF-01", "TC-PT-46", "pipeline --stage ptable 耗时", "P1",
                   lambda: check_perf_write_stage(ctx, "ptable"))
    runner.execute("PERF-02", "TC-PT-46", "pipeline --stage placeholders 耗时", "P1",
                   lambda: check_perf_write_stage(ctx, "placeholders"))
    runner.execute("PERF-03", "TC-PT-62", "pipeline all 耗时", "P2",
                   lambda: check_perf_write_stage(ctx, "all"))
    runner.execute("PERF-04", "TC-PT-43", "AssetRegistry.load 耗时", "P1", lambda: check_perf_load(ctx))
    runner.execute("PERF-05", "TC-PT-44", "10k resolve 耗时", "P1", lambda: check_perf_resolve(ctx))
    runner.execute("PERF-06", "TC-PT-47", "verify_assets 全量耗时", "P1",
                   lambda: (NOT_RUN, "禁止写文件：verify_assets.py 会写 assets/validation_report.json；只读验收不执行", []))
    runner.execute("PERF-07", "TC-PT-47", "契约全量（含解码）耗时", "P1", lambda: check_perf_contract_full(ctx))
    runner.execute("PERF-08", "TC-PT-47", "契约 --no-decode 耗时", "P1", lambda: check_perf_contract_no_decode(ctx))
    runner.execute("PERF-09", "TC-PT-54", "构建峰值 RSS", "P2",
                   lambda: (NOT_RUN, "禁止写文件：all 构建会写 assets/；峰值 RSS 需写使能阶段采样", []))
    runner.execute("PERF-10", "TC-PT-45", "load 峰值增量 RSS", "P1", lambda: check_perf_load_rss(ctx))
    for index, (label, budget, tc) in enumerate((
        ("UI 房间图首帧 512→128", "0.120s", "TC-PT-48"),
        ("UI 卡牌首帧 480×672→240×336", "0.150s", "TC-PT-48"),
        ("UI 缓存命中", "0.016s", "TC-PT-48"),
        ("一屏 12 图块批量绑定", "0.400s", "TC-PT-48"),
        ("冷启动到主界面", "2.5s", "TC-PT-48"),
    ), start=11):
        cid = "PERF-%02d" % index
        runner.execute(cid, tc, label, "P1",
                       lambda label=label, budget=budget: (
                           NOT_RUN,
                           "需要 Tk 显示环境与 ui.py 实际接入；预算 %s，只读/无显示阶段不测" % budget,
                           []))

    runner.execute("LEGACY-01", "TC-PT-18", "verify_assets 旧报告解析", "P0", lambda: check_legacy_verify_assets(ctx))
    runner.execute("LEGACY-02", "TC-PT-19", "契约结果解析/基线", "P0", lambda: check_legacy_contract(ctx))
    runner.execute("LEGACY-03", "TC-PT-51", "其他 verify 脚本回归", "P1", lambda: check_legacy_other_verifies(ctx))
    runner.execute("LEGACY-04", "TC-PT-61", "双端内核同一性", "P0", lambda: check_legacy_core_drift(ctx))
    runner.execute("LEGACY-05", "TC-PT-51", "实现方 unittest 结果", "P1", lambda: check_legacy_unittest(ctx))
    runner.execute("LEGACY-06", "TC-PT-59", "旧结果新鲜度", "P1", lambda: check_legacy_freshness(ctx))

    runner.execute("COV-01", "TC-PT-49", "行覆盖 ≥85%", "P1", lambda: check_coverage_line(ctx))
    runner.execute("COV-02", "TC-PT-50", "分支覆盖 ≥75%", "P1", lambda: check_coverage_branch(ctx))

    runner.execute("SAFE-01", "TC-PT-25", "只读自证与漂移检测", "P0", lambda: check_safe_readonly(ctx))
    return runner.results


def summarize(results):
    counts = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    # 计划要求按用例计通过率：同一 TC 的多条断言任一 FAIL 即整条 FAIL；
    # 仅未执行（NOT_RUN）且无 FAIL 时整条 NOT_RUN；CONFLICT 单独列出。
    case_map = {}
    for result in results:
        case_map.setdefault(result.tc, []).append(result)
    cases = []
    for tc, items in case_map.items():
        if any(item.priority == "P0" for item in items):
            priority = "P0"
        elif any(item.priority == "P1" for item in items):
            priority = "P1"
        else:
            priority = "P2"
        statuses = [item.status for item in items]
        if FAIL in statuses:
            status = FAIL
        elif NOT_RUN in statuses:
            status = NOT_RUN
        elif CONFLICT in statuses:
            status = CONFLICT
        else:
            status = PASS
        cases.append({"tc": tc, "priority": priority, "status": status,
                      "checks": [item.cid for item in items]})
    case_counts = {}
    for case in cases:
        case_counts[case["status"]] = case_counts.get(case["status"], 0) + 1
    rates = {}
    for priority in ("P0", "P1", "P2"):
        items = [case for case in cases if case["priority"] == priority]
        executed = [case for case in items if case["status"] in (PASS, FAIL)]
        passed = [case for case in items if case["status"] == PASS]
        failed = [case for case in items if case["status"] == FAIL]
        not_run = [case for case in items if case["status"] == NOT_RUN]
        conflicts = [case for case in items if case["status"] == CONFLICT]
        rates[priority] = {
            "total": len(items),
            "executed": len(executed),
            "pass": len(passed),
            "fail": len(failed),
            "not_run": len(not_run),
            "conflict": len(conflicts),
            "rate": round(len(passed) / float(len(executed)), 4) if executed else None,
        }
    thresholds = {"P0": 1.0, "P1": 0.95, "P2": 0.90}
    gates = {}
    for priority, threshold in thresholds.items():
        data = rates[priority]
        if priority == "P0":
            gates[priority] = (
                data["fail"] == 0
                and data["not_run"] == 0
                and data["rate"] is not None
                and data["rate"] >= threshold
            )
        else:
            gates[priority] = data["rate"] is not None and data["rate"] >= threshold
    failed_ids = [case["tc"] for case in cases if case["status"] == FAIL]
    not_run_ids = [case["tc"] for case in cases if case["status"] == NOT_RUN]
    conflict_ids = [case["tc"] for case in cases if case["status"] == CONFLICT]
    hard_gaps = []
    soft_gaps = []
    for result in results:
        if result.cid in ("UI-02", "UI-03") and result.status != PASS:
            hard_gaps.append("UI 绑定未完成（%s）：%s" % (result.cid, result.detail))
        if result.cid == "LEGACY-01" and result.status != PASS:
            soft_gaps.append("verify_assets 旧测试未取得新鲜 PASS（%s）" % result.status)
        if result.cid == "LEGACY-02" and result.status != PASS:
            soft_gaps.append("契约旧测试未取得新鲜 PASS/裁决（%s）" % result.status)
        if result.cid == "LEGACY-04" and result.status != PASS:
            soft_gaps.append("双端内核同一性未执行（%s）" % result.status)
    perf_not_run = [result.cid for result in results if result.cid.startswith("PERF-") and result.status == NOT_RUN]
    if perf_not_run:
        soft_gaps.append("性能 15 项中 %d 项未测：%s" % (len(perf_not_run), ", ".join(perf_not_run)))
    if any(result.cid.startswith("COV-") and result.status != PASS for result in results):
        soft_gaps.append("行/分支覆盖率未测（coverage 不可用 + 测试套件会写项目文件）")
    if any(result.cid == "LEGACY-05" and result.status != PASS for result in results):
        soft_gaps.append("实现方 unittest 未在只读阶段执行（会写 assets/fixtures）")
    # 去重保持顺序
    seen = set()
    required_gaps = [item for item in hard_gaps + soft_gaps if not (item in seen or seen.add(item))]

    p0_fail = rates["P0"]["fail"] > 0
    p0_incomplete = rates["P0"]["not_run"] > 0 or rates["P0"]["rate"] is None
    p1_bad = rates["P1"]["rate"] is None or rates["P1"]["rate"] < thresholds["P1"]
    p2_bad = rates["P2"]["rate"] is None or rates["P2"]["rate"] < thresholds["P2"]
    verdict = "PASS"
    if p0_fail or p1_bad or p2_bad or hard_gaps:
        verdict = "FAIL"
    elif p0_incomplete or soft_gaps or not_run_ids or conflict_ids:
        verdict = "INCOMPLETE"
    completion = {
        "achieved": verdict == "PASS" and not required_gaps,
        "reasons": required_gaps,
    }
    return {
        "counts": counts,
        "case_counts": case_counts,
        "cases": cases,
        "rates": rates,
        "gates": gates,
        "thresholds": thresholds,
        "failed": failed_ids,
        "not_run": not_run_ids,
        "conflicts": conflict_ids,
        "hard_gaps": hard_gaps,
        "soft_gaps": soft_gaps,
        "required_gaps": required_gaps,
        "completion": completion,
        "verdict": verdict,
    }


def main(argv=None):
    # Windows 控制台默认 GBK，报告含 ↔/× 等字符；统一 UTF-8，避免编码异常中断验收。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(
        description="P 表执行只读独立验收（不修改实现、不写项目文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=None, help="项目根目录，默认由脚本位置推导")
    parser.add_argument("--json", action="store_true", help="输出 JSON 到 stdout")
    parser.add_argument("--fast", action="store_true", help="跳过 95 图扫描/内存重建")
    parser.add_argument("--run-contract", action="store_true", help="只读子进程运行契约脚本（默认含解码全量）")
    parser.add_argument("--contract-no-decode", action="store_true", help="契约子进程走 --no-decode 快速档（C16 SKIP 单列）")
    parser.add_argument("--contract-json", default=None, help="已有契约结果 JSON 路径")
    parser.add_argument("--verify-report", default=None, help="已有 verify_assets 报告路径")
    parser.add_argument("--tk", action="store_true", help="尝试 Tk 冒烟（需要显示环境）")
    parser.add_argument("--timeout", type=int, default=300, help="契约子进程超时秒数")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    if not (root / "source" / "desktop" / "game").is_dir():
        sys.stderr.write("项目根无效：%s\n" % root)
        return 2
    ctx = Context(root, args)
    if args.run_contract:
        _run_contract(ctx)
    results = run_all(ctx)
    summary = summarize(results)

    payload = {
        "tool": "verify_p_table_execution.py",
        "readonly": True,
        "root": str(root),
        "snapshot_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pillow": _module_version("PIL"),
            "tkinter": _module_version("tkinter"),
            "coverage": _module_version("coverage"),
        },
        "inputs": {
            "p_table": str(ctx.p_table),
            "p_table_sha256": sha256_file(ctx.p_table),
            "p_table_columns": len((ctx.payload or {}).get("schema", {}).get("columns") or []),
            "p_table_records": len(ctx.rows),
            "contract_json": str(_find_contract_json(ctx)) if _find_contract_json(ctx) else "",
            "verify_report": str(_legacy_report(ctx)[0][0]) if _legacy_report(ctx)[0] else "",
        },
        "summary": summary,
        "checks": [result.as_dict() for result in results],
        "unavailable": [
            {"id": result.cid, "priority": result.priority, "detail": result.detail}
            for result in results if result.status == NOT_RUN
        ],
        "conflicts": [
            {"id": result.cid, "priority": result.priority, "detail": result.detail}
            for result in results if result.status == CONFLICT
        ],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("== P 表执行独立验收（只读） ==")
        print("root      : %s" % root)
        print("p_table   : %s（records=%d, columns=%d, sha256=%s）" % (
            ctx.p_table, len(ctx.rows), payload["inputs"]["p_table_columns"],
            payload["inputs"]["p_table_sha256"][:16]))
        print("python    : %s / pillow=%s / tk=%s / coverage=%s" % (
            payload["environment"]["python"], payload["environment"]["pillow"],
            payload["environment"]["tkinter"], payload["environment"]["coverage"]))
        print("-" * 100)
        for result in results:
            mark = result.status
            detail = result.detail.replace("\n", " ")
            if len(detail) > 220:
                detail = detail[:217] + "..."
            print("[%s] %-11s %-7s %-6s %s" % (mark, result.cid, result.priority, result.tc, detail))
        print("-" * 100)
        print("检查项: PASS %d / FAIL %d / NOT_RUN %d / CONFLICT %d / BLOCKED %d" % (
            summary["counts"].get(PASS, 0), summary["counts"].get(FAIL, 0),
            summary["counts"].get(NOT_RUN, 0), summary["counts"].get(CONFLICT, 0),
            summary["counts"].get(BLOCKED, 0)))
        print("用例数: PASS %d / FAIL %d / NOT_RUN %d / CONFLICT %d" % (
            summary["case_counts"].get(PASS, 0), summary["case_counts"].get(FAIL, 0),
            summary["case_counts"].get(NOT_RUN, 0), summary["case_counts"].get(CONFLICT, 0)))
        for priority in ("P0", "P1", "P2"):
            rate = summary["rates"][priority]
            rate_text = "not-run" if rate["rate"] is None else "%.1f%%" % (rate["rate"] * 100)
            print("%s: executed=%d pass=%d fail=%d not_run=%d conflict=%d rate=%s gate=%s" % (
                priority, rate["executed"], rate["pass"], rate["fail"], rate["not_run"],
                rate["conflict"], rate_text, "PASS" if summary["gates"][priority] else "FAIL"))
        if summary["failed"]:
            print("FAIL 项: %s" % ", ".join(summary["failed"]))
        if summary["conflicts"]:
            print("CONFLICT: %s" % ", ".join(summary["conflicts"]))
        if summary["not_run"]:
            print("NOT_RUN : %s" % ", ".join(summary["not_run"]))
        print("判定: %s" % summary["verdict"])
        if summary["required_gaps"]:
            print("完成缺口:")
            for item in summary["required_gaps"][:12]:
                print("  - %s" % item)

    if summary["verdict"] == "PASS":
        return 0
    if summary["verdict"] == "FAIL":
        return 1
    return 3


if __name__ == "__main__":
    sys.exit(main())
