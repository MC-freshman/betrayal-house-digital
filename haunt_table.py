"""作祟查表选择器（第 3 项）—— 查表优先，哈希兜底。

为什么单独抽出来
----------------
引擎里原来的选择逻辑只有一行哈希取模（``sha1(room|omen) % 70 + 1``），
它和官方触发表没有任何关系。要接官方 13×7 表，就必须有一个"表没数据时
行为逐字节不变"的中间层：否则一次数据缺失就会改写 186 条黄金回放与
2310 局胜率基线，而且失败方式是不可见的（不是崩，是悄悄换了剧本号）。

本模块只做三件事：

1. 读 ``qa/haunt_table.json``（schema ``haunt-table/v1``），键 = 预兆卡 id
   × 预兆房 ``template_id``；
2. 命中且值合法 → ``(haunt_id, "table")``；
3. 文件缺失 / 解析失败 / 键未命中 / 值非法 → 走原 SHA1 公式，
   返回 ``(haunt_id, "fallback")``。

硬约束（与 T-08/T-10 一致）
--------------------------
* **绝不抛异常**：表坏了也只是回退。选择函数夹在对局初始化的关键路径上，
  为了一张表把整局打挂是不可接受的失败方式。
* **回退公式逐字节保留**：``f"{room_id}|{omen_id}"`` 的 UTF-8 字节、sha1、
  roof 分支 ``71 + value % 50``、基础分支 ``(value % 70) + 1``。
* **不编造表值**：``qa/haunt_table.json`` 的 ``entries`` 在拿到官方数据前
  保持为空，全部走回退。覆盖率由 ``selection_counts()`` 记录。

计数口径
--------
``selection_counts()`` 是进程内累加器：``table`` / ``fallback`` / ``invalid``
/ ``table_missing`` / ``load_error``。它不进存档、不进网络同步——只给
``qa/haunt_table_stats.py`` 这类统计脚本读，用来算回退覆盖率。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

GAME_DIR = Path(__file__).resolve().parent
DEFAULT_TABLE_PATH = GAME_DIR / "qa" / "haunt_table.json"
SCHEMA = "haunt-table/v1"

# 基础层 70 本；屋顶分支的 WW 槽位是 71-120（引擎 roof 分支产出 71..120）。
BASE_HAUNT_MAX = 70
ROOF_HAUNT_MIN = 71
ROOF_HAUNT_MAX = 120

_COUNTS: Dict[str, int] = {
    "table": 0,
    "fallback": 0,
    "invalid": 0,
    "table_missing": 0,
    "load_error": 0,
}

_CACHE: Dict[str, Any] = {"key": None, "table": None}


def table_path() -> Path:
    """表文件路径；``BTH_HAUNT_TABLE`` 可指向别处（测试/演练用）。"""
    override = os.environ.get("BTH_HAUNT_TABLE")
    return Path(override) if override else DEFAULT_TABLE_PATH


def _cache_key(path: Path) -> Tuple[str, int, int]:
    try:
        stat = path.stat()
        return (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (str(path), -1, -1)


def _empty_table() -> Dict[str, Any]:
    return {"schema": SCHEMA, "entries": {}, "source": "missing", "note": ""}


def load_table(force: bool = False) -> Dict[str, Any]:
    """读表（按 mtime+size 缓存）。任何异常一律降级为空表，不抛。"""
    path = table_path()
    key = _cache_key(path)
    if not force and _CACHE["table"] is not None and _CACHE["key"] == key:
        return _CACHE["table"]

    if not path.is_file():
        _COUNTS["table_missing"] += 1
        table = _empty_table()
        _CACHE["key"], _CACHE["table"] = key, table
        return table

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # 坏文件 = 没有表，不是崩
        _COUNTS["load_error"] += 1
        table = _empty_table()
        table["source"] = "load-error"
        table["note"] = "%s: %s" % (type(exc).__name__, exc)
        _CACHE["key"], _CACHE["table"] = key, table
        return table

    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        _COUNTS["load_error"] += 1
        table = _empty_table()
        table["source"] = "schema-error"
        table["note"] = "entries 不是对象"
        _CACHE["key"], _CACHE["table"] = key, table
        return table

    table = {
        "schema": raw.get("schema", ""),
        "entries": entries,
        "source": raw.get("source", ""),
        "note": raw.get("note", ""),
    }
    _CACHE["key"], _CACHE["table"] = key, table
    return table


def table_status() -> Dict[str, Any]:
    """表的状态快照，给统计产物留证（不参与选择）。"""
    path = table_path()
    table = load_table()
    entries = table.get("entries") or {}
    filled = 0
    for value in entries.values():
        if isinstance(value, dict):
            filled += len([k for k, v in value.items() if _valid_haunt_id(v)])
    return {
        "path": str(path),
        "exists": path.is_file(),
        "schema": table.get("schema", ""),
        "source": table.get("source", ""),
        "note": table.get("note", ""),
        "omen_keys": len(entries),
        "filled_cells": filled,
        "empty": filled == 0,
    }


def _valid_haunt_id(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return 1 <= value <= ROOF_HAUNT_MAX


def hash_fallback(room_id: str, omen_id: str, catalog: Any = None) -> int:
    """原样保留的 SHA1 取模（roof 分支在内），作为表的兜底。

    屋顶层条件剧本：揭示者站在屋顶层房间触发时，从 50 本 WW 剧本
    （槽位 71-120，官方编号 51-100）中选择；基础层房间保持 ``% 70 + 1``，
    未上屋顶的旧对局剧本选择序列零漂移。
    """
    payload = "%s|%s" % (room_id or "", omen_id or "")
    value = int(hashlib.sha1(payload.encode("utf-8")).hexdigest(), 16)
    template = None
    if catalog is not None:
        try:
            template = catalog.room_templates.get(room_id)
        except AttributeError:  # catalog 形状不符也不该崩
            template = None
    if template is not None and getattr(template, "floor", None) == "roof":
        return ROOF_HAUNT_MIN + (value % 50)
    return (value % BASE_HAUNT_MAX) + 1


def select_haunt(
    state: Any,
    room_id: Optional[str] = None,
    omen_id: Optional[str] = None,
    catalog: Any = None,
) -> Tuple[int, str]:
    """选剧本号，返回 ``(haunt_id, source)``，source ∈ {"table", "fallback"}。

    ``room_id`` / ``omen_id`` 省略时从 ``state`` 取：``state.last_omen_id``
    与 ``state.last_omen_room``（无该字段则为空串 → 必然回退，行为与旧版
    对空 room_id 取模一致）。引擎调用点显式传参，避免依赖 state 形状。
    """
    if omen_id is None:
        omen_id = getattr(state, "last_omen_id", None) or ""
    if room_id is None:
        room_id = getattr(state, "last_omen_room", None) or ""
    if catalog is None:
        catalog = getattr(state, "catalog", None)

    room_key = str(room_id or "")
    omen_key = str(omen_id or "")

    try:
        table = load_table()
        entries = table.get("entries") or {}
        cell = entries.get(omen_key) if omen_key else None
        if isinstance(cell, dict) and room_key in cell:
            value = cell[room_key]
            if _valid_haunt_id(value):
                _COUNTS["table"] += 1
                return int(value), "table"
            # 命中了脏值：记一次 invalid，再走回退（不静默吞掉，也不炸）
            _COUNTS["invalid"] += 1
    except Exception:  # noqa: BLE001 - 选择函数不允许把整局带崩
        _COUNTS["load_error"] += 1

    _COUNTS["fallback"] += 1
    return hash_fallback(room_key, omen_key, catalog), "fallback"


def selection_counts() -> Dict[str, int]:
    """进程内累计的选择计数（含回退覆盖率分子分母）。"""
    counts = dict(_COUNTS)
    total = counts["table"] + counts["fallback"]
    counts["total"] = total
    counts["fallback_rate"] = round(counts["fallback"] / total, 4) if total else 0.0
    counts["table_rate"] = round(counts["table"] / total, 4) if total else 0.0
    return counts


def reset_selection_counts() -> None:
    for key in _COUNTS:
        _COUNTS[key] = 0
