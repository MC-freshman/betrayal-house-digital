#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""机器人胜率基线 + 作祟查表框架 —— 只读独立验收（run6 第 2/3 项）。

定位
----
本脚本只做验收判定，不参与实现，不写任何项目文件：
- 不创建 / 不修改 `source/`、`assets/`、`reports/` 下任何文件；
- 顶部设置 `sys.dont_write_bytecode = True`，内省 content / profiles 时不生成 `__pycache__`；
- 无临时文件、无网络、无凭据、无子进程。

被测产物
--------
source/desktop/game/qa/winrate_baseline.json     第 2 项胜率基线（seeds / runtime / games / by_haunt / by_profile）
source/desktop/game/qa/haunt_table_stats.json    第 3 项查表统计（entries / selections / fallback / table_hits）
可选：source/desktop/game/qa/run6_guardrails.json  三项回归护栏的合并复跑证据

判定纪律
--------
1. 产物文件缺失 → NOT_RUN（不折算 PASS）。
2. 产物存在但字段缺失 / 自相矛盾 / 数值不达标 → FAIL。
3. 规范口径冲突且无书面裁决 → CONFLICT。
4. 只有全部 27 条 PASS 才输出 verdict=PASS；任一 NOT_RUN/CONFLICT → INCOMPLETE。

判据分组（共 27 条）
--------------------
W-01…W-11  胜率基线（11 条）：产物、seeds、runtime、局数恒等式、胜负未完成恒等式、
            胜率区间、by_haunt 70 项、分剧本计数、by_profile 分组、51/19 分摊、耗时。
H-01…H-08  查表框架（8 条）：产物、entries 为空、selections 有样本、fallback 100%、
            table 命中为 0、计数恒等与异常、source 枚举、表状态与 entries 自洽。
G-01…G-06  回归护栏（6 条）：63 测试 / verify_assets 17 / 契约 32 的清单只增不减，
            以及最近一次执行的 0 fail 与新鲜度。
X-01…X-02  证据归属与只读自证（2 条）：产物时间戳可归属、实现文件哈希未变。

明确排除
--------
官方 91 格表值的正确性、AI 强度目标是否达标、2310 局与 186 条黄金回放逐局等价、
表值来源（页码/版本/誊录）的真实性、bot 对局与人类对局的平衡性 —— 均不在本脚本判定范围。

用法
----
python qa/verify_winrate_haunt.py                输出 JSON（默认）
python qa/verify_winrate_haunt.py --text         人读报告
python qa/verify_winrate_haunt.py --list         列出 27 条判据
python qa/verify_winrate_haunt.py --winrate <path> --haunt-stats <path>
python qa/verify_winrate_haunt.py --guardrails <path>

退出码
------
0  PASS        27 条全部 PASS
1  FAIL        存在 FAIL
3  INCOMPLETE  仅 NOT_RUN / CONFLICT（不构成通过）
2  参数错误或脚本内部异常
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# 关键：内省被测模块前关闭字节码写入，保证「只读」可审计。
sys.dont_write_bytecode = True

PASS, FAIL, NOT_RUN, CONFLICT = "PASS", "FAIL", "NOT_RUN", "CONFLICT"

BASELINE_TESTS = 63
BASELINE_VERIFY_ASSETS = 17
BASELINE_CONTRACT = 32

DEFAULT_HAUNTS = 70
DEFAULT_OMEN_CARDS = 13
DEFAULT_OMEN_ROOMS = 7

CANONICAL_SEEDS = (3, 7, 11, 23, 31, 101, 109, 113, 137, 151, 251)

# 顶层字段可能被实现方放进这些容器；只下钻一层，避免递归歧义。
CONTAINERS = (
    "summary", "totals", "overall", "meta", "result", "report",
    "baseline", "config", "params", "grid", "stats",
    "counts", "selection_counts", "selector_counts", "haunt_counts", "table",
)

COUNTER_SCOPES = ("counts", "selection_counts", "selector_counts", "haunt_counts")

ALIAS = {
    "seeds": ("seeds", "seed_list", "seed_values", "random_seeds"),
    "players": ("players", "player_counts", "player_count", "player_numbers"),
    "games": ("games", "total_games", "games_count", "n_games", "total"),
    "heroes": ("heroes_win", "hero_wins", "heroes_wins", "hero_win", "hero_win_count"),
    "traitor": ("traitor_win", "traitor_wins", "traitors_win", "traitor_win_count"),
    "unfinished": (
        "unfinished", "unfinished_count", "unfinished_games",
        "incomplete", "incomplete_count",
    ),
    "by_haunt": ("by_haunt", "per_haunt", "by_haunts", "haunt_breakdown", "haunt_stats"),
    "by_profile": ("by_profile", "per_profile", "profile_breakdown", "profile_stats"),
    "duration": (
        "duration_s", "duration_seconds", "elapsed_seconds",
        "elapsed_s", "wall_seconds", "runtime_seconds",
    ),
    "entries": (
        "entries", "table_entries", "entry_count", "entry_total",
        "filled_cells", "filled",
    ),
    "selections": (
        "selections", "lookups", "total_selections", "calls",
        "queries", "samples", "lookup_count",
    ),
    "fallback": ("fallback", "fallback_hits", "fallback_count", "used_fallback", "fallbacks"),
    "table_hits": (
        "table_hits", "table_hit_count", "hits",
        "table_matches", "matched", "table_matches_count",
    ),
    "fallback_rate": ("fallback_rate", "fallback_ratio"),
    "errors": (
        "errors", "error_count", "exceptions", "exception_count",
        "failures", "failed", "load_error", "load_errors",
    ),
    "keyspace": ("keyspace", "key_space", "keys_total", "table_keyspace", "key_count"),
    "source_counts": ("source_counts", "by_source", "source_breakdown", "source_distribution"),
    "generated_at": ("generated_at", "finished_at", "completed_at", "created_at", "timestamp", "date"),
}

RUNTIME_KEYS = (
    "runtime", "runtime_version", "engine_version", "engine_info",
    "build_info", "version_info",
)
RUNTIME_VALUE_KEYS = (
    "version", "app_version", "engine_version", "build",
    "git_rev", "git_commit", "commit", "sha", "revision",
)

ELIGIBLE_RUNTIME = {"", "-", "unknown", "n/a", "na", "none", "null", "tbd", "待定"}

ABSENT_TOKENS = {
    "", "-", "absent", "none", "null", "missing", "not_present",
    "not-present", "empty", "no_data", "no-data", "无", "缺失", "未提供", "空",
}

DEFAULT_PROFILE_HINTS = ("default", "默认", "generic", "通用", "base", "fallback")
DEDICATED_PROFILE_HINTS = (
    "dedicated", "专属", "override", "定制", "custom",
    "special", "tuned", "specific", "per_haunt", "per-haunt",
)


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #

def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if text and (text.isdigit() or (text[0] in "+-" and text[1:].isdigit())):
            return int(text)
    return None


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _count_of(value: Any) -> Optional[int]:
    """计数口径：整数原样，列表/集合取长度，映射取显式 count 或键数。"""
    number = _as_int(value)
    if number is not None:
        return number
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value)
    if isinstance(value, dict):
        for key in ("count", "total", "size", "length", "n", "entries", "games"):
            if key in value:
                inner = _count_of(value[key])
                if inner is not None:
                    return inner
        return len(value)
    return None


def _norm(value: Any) -> str:
    return str(value).strip().lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_time(path: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _parse_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    parsed: Optional[datetime] = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _iso(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S") if value else ""


# --------------------------------------------------------------------------- #
# 上下文
# --------------------------------------------------------------------------- #

class Ctx(object):
    def __init__(
        self,
        root: Optional[str] = None,
        game_dir: Optional[str] = None,
        winrate: Optional[str] = None,
        haunt_stats: Optional[str] = None,
        guardrails: Optional[str] = None,
    ) -> None:
        self.root = Path(root).resolve() if root else _find_root()
        self.game = Path(game_dir).resolve() if game_dir else self.root / "source" / "desktop" / "game"
        self.qa = self.game / "qa"
        self.paths: Dict[str, Path] = {
            "winrate": Path(winrate).resolve() if winrate else self.qa / "winrate_baseline.json",
            "haunt": Path(haunt_stats).resolve() if haunt_stats else self.qa / "haunt_table_stats.json",
            "guardrails": Path(guardrails).resolve() if guardrails else self.qa / "run6_guardrails.json",
            "engine": self.game / "engine.py",
            "content": self.game / "content.py",
            "profiles": self.game / "haunt_ai_profiles.py",
            "haunt_table_module": self.game / "haunt_table.py",
            "winrate_module": self.game / "winrate_baseline.py",
            "tests": self.qa / "test_p_table_execution.py",
            "verify_assets": self.game / "verify_assets.py",
            "contract_tool": self.qa / "verify_assets_contract.py",
            "validation_report": self.game / "assets" / "validation_report.json",
            "contract_result": self.qa / "contract_result.json",
            "execution_report": self.game / "reports" / "p_table_execution_report.json",
        }
        self.data: Dict[str, Any] = {}
        self.errors: Dict[str, str] = {}
        self.impl_before: Dict[str, Any] = {}
        self.constants, self.constants_source = _probe_constants(self.game)
        self.profile_keys, self.profile_source = _probe_profiles(self.game)
        self._load()
        self._snapshot_impl()

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except (ValueError, OSError):
            return str(path).replace("\\", "/")

    def fingerprint(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.is_file():
            return None
        return {
            "bytes": path.stat().st_size,
            "mtime": _iso(_file_time(path)),
            "sha256": _sha256(path),
        }

    def _load_json(self, key: str) -> None:
        path = self.paths[key]
        if not path.is_file():
            self.data[key] = None
            self.errors[key] = "missing: %s" % self.rel(path)
            return
        try:
            self.data[key] = json.loads(path.read_text(encoding="utf-8-sig"))
            self.errors[key] = ""
        except Exception as exc:  # noqa: BLE001 - 证据损坏必须显式暴露
            self.data[key] = None
            self.errors[key] = "invalid: %s: %s" % (self.rel(path), exc)

    def _load(self) -> None:
        for key in (
            "winrate", "haunt", "guardrails", "validation_report",
            "contract_result", "execution_report",
        ):
            self._load_json(key)

    def _snapshot_impl(self) -> None:
        for key in ("engine", "content", "profiles", "haunt_table_module", "winrate_module"):
            self.impl_before[key] = self.fingerprint(self.paths[key])


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "source" / "desktop" / "game").is_dir():
            return candidate
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / "source" / "desktop" / "game").is_dir():
            return candidate
    return here.parents[4]


def _probe_constants(game: Path) -> Tuple[Dict[str, Any], str]:
    """独立来源：content.py 的 13 张预兆 / 7 个预兆房 / 70 本剧本。"""
    defaults = {
        "haunts": DEFAULT_HAUNTS,
        "omen_cards": DEFAULT_OMEN_CARDS,
        "omen_rooms": DEFAULT_OMEN_ROOMS,
        "keys": DEFAULT_OMEN_CARDS * DEFAULT_OMEN_ROOMS,
    }
    try:
        sys.path.insert(0, str(game))
        import content  # type: ignore  # noqa: PLC0415

        haunts = len(content.build_catalog().haunt_defs)
        omens = len(content.OMEN_CARDS)
        rooms = len([room for room in content.ROOM_BASES if room.get("symbol") == "omen"])
        if min(haunts, omens, rooms) <= 0:
            raise ValueError("content 常量非正: haunts=%r omens=%r rooms=%r" % (haunts, omens, rooms))
        return {
            "haunts": haunts,
            "omen_cards": omens,
            "omen_rooms": rooms,
            "keys": omens * rooms,
        }, "content.py"
    except Exception as exc:  # noqa: BLE001 - 内省失败退回常量并记录
        defaults["note"] = "content 内省失败：%s: %s" % (type(exc).__name__, exc)
        return defaults, "defaults"


def _probe_profiles(game: Path) -> Tuple[Optional[List[int]], str]:
    """专属档案覆盖集：by_profile 的 51/19 分摊基准。"""
    try:
        sys.path.insert(0, str(game))
        import haunt_ai_profiles  # type: ignore  # noqa: PLC0415

        keys = sorted(int(key) for key in haunt_ai_profiles.HAUNT_AI_PROFILE_OVERRIDES)
        return keys, "haunt_ai_profiles.py"
    except Exception as exc:  # noqa: BLE001 - 缺失时回退文档常量
        return None, "unavailable: %s: %s" % (type(exc).__name__, exc)


# --------------------------------------------------------------------------- #
# 字段解析
# --------------------------------------------------------------------------- #

def _lookup(obj: Any, aliases: Sequence[str]) -> List[Tuple[str, Any]]:
    hits: List[Tuple[str, Any]] = []
    if not isinstance(obj, dict):
        return hits
    for alias in aliases:
        if alias in obj:
            hits.append((alias, obj[alias]))
    for container in CONTAINERS:
        sub = obj.get(container)
        if isinstance(sub, dict):
            for alias in aliases:
                if alias in sub:
                    hits.append(("%s.%s" % (container, alias), sub[alias]))
    return hits


def _pick(doc: Any, aliases: Sequence[str]) -> Dict[str, Any]:
    hits = _lookup(doc, aliases)
    if not hits:
        return {"status": "missing", "value": None, "path": "", "hits": []}
    tokens: Dict[str, List[Tuple[str, Any]]] = {}
    for path, value in hits:
        token = json.dumps(value, sort_keys=True, ensure_ascii=False, default=repr)
        tokens.setdefault(token, []).append((path, value))
    if len(tokens) > 1:
        return {
            "status": "conflict",
            "value": None,
            "path": "",
            "hits": [path for path, _ in hits],
        }
    path, value = hits[0]
    return {"status": "found", "value": value, "path": path, "hits": [p for p, _ in hits]}


def _count_result(hits: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    if not hits:
        return {"status": "missing", "value": None, "path": "", "hits": []}
    values: List[Tuple[str, int]] = []
    for path, value in hits:
        number = _count_of(value)
        if number is None:
            return {"status": "invalid", "value": None, "path": path, "hits": [p for p, _ in hits]}
        values.append((path, number))
    distinct = {number for _, number in values}
    if len(distinct) > 1:
        return {
            "status": "conflict",
            "value": None,
            "path": "",
            "hits": [p for p, _ in hits],
        }
    return {
        "status": "found",
        "value": values[0][1],
        "path": values[0][0],
        "hits": [p for p, _ in hits],
    }


def _pick_count(doc: Any, aliases: Sequence[str]) -> Dict[str, Any]:
    return _count_result(_lookup(doc, aliases))


def _pick_counter(
    doc: Any,
    aliases: Sequence[str],
    scoped_aliases: Sequence[str] = (),
) -> Dict[str, Any]:
    """优先读 counts / selection_counts 作用域，避免与顶层 table 状态相撞。

    ``scoped_aliases`` 只允许出现在 counts 作用域内（如 ``total`` / ``table``），
    不回落到顶层，防止把 ``games`` 或 table 快照误读成选择计数。
    """
    hits: List[Tuple[str, Any]] = []
    if isinstance(doc, dict):
        for scope in COUNTER_SCOPES:
            sub = doc.get(scope)
            if not isinstance(sub, dict):
                continue
            for alias in tuple(aliases) + tuple(scoped_aliases):
                if alias in sub:
                    hits.append(("%s.%s" % (scope, alias), sub[alias]))
    if hits:
        return _count_result(hits)
    return _pick_count(doc, aliases)


def _int_list(result: Dict[str, Any]) -> Optional[List[int]]:
    if result.get("status") != "found":
        return None
    value = result.get("value")
    if not isinstance(value, (list, tuple)):
        return None
    numbers: List[int] = []
    for item in value:
        number = _as_int(item)
        if number is None:
            return None
        numbers.append(number)
    return numbers


def _runtime_version(doc: Any) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        return {"status": "missing", "value": "", "path": ""}
    for key in RUNTIME_KEYS:
        if key not in doc:
            continue
        value = doc[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"status": "found", "value": str(value), "path": key}
        if isinstance(value, str) and value.strip():
            return {"status": "found", "value": value.strip(), "path": key}
        if isinstance(value, dict):
            for sub in RUNTIME_VALUE_KEYS:
                raw = value.get(sub)
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    return {"status": "found", "value": str(raw), "path": "%s.%s" % (key, sub)}
                if isinstance(raw, str) and raw.strip():
                    return {"status": "found", "value": raw.strip(), "path": "%s.%s" % (key, sub)}
            return {
                "status": "insufficient",
                "value": "",
                "path": key,
                "detail": "%s 仅含环境信息，无版本号" % key,
            }
    return {"status": "missing", "value": "", "path": ""}


def _doc_time(doc: Any) -> Tuple[Optional[datetime], str]:
    if isinstance(doc, dict):
        for key in ALIAS["generated_at"]:
            if key in doc:
                parsed = _parse_time(doc[key])
                if parsed:
                    return parsed, key
    return None, ""


def _evidence_time(doc: Any, path: Path) -> Tuple[Optional[datetime], str]:
    parsed, key = _doc_time(doc)
    if parsed:
        return parsed, key
    return _file_time(path), "mtime"


def _reference_time(ctx: Ctx) -> Optional[datetime]:
    times = []
    for key in ("engine", "content", "profiles", "haunt_table_module", "winrate_module"):
        path = ctx.paths[key]
        if path.is_file():
            stamp = _file_time(path)
            if stamp:
                times.append(stamp)
    return max(times) if times else None


# --------------------------------------------------------------------------- #
# 领域解析
# --------------------------------------------------------------------------- #

def _haunt_id(value: Any) -> Optional[int]:
    number = _as_int(value)
    if number is not None:
        return number if 1 <= number <= DEFAULT_HAUNTS else None
    if isinstance(value, str):
        text = value.strip().lower()
        for prefix in ("haunt_", "haunt-", "haunt #", "haunt#", "#", "h"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        number = _as_int(text)
        if number is not None and 1 <= number <= DEFAULT_HAUNTS:
            return number
    return None


def _haunt_table(doc: Any) -> Optional[Dict[int, Dict[str, Any]]]:
    value = _pick(doc, ALIAS["by_haunt"])
    if value["status"] != "found":
        return None
    raw = value["value"]
    table: Dict[int, Dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, entry in raw.items():
            hid = _haunt_id(key)
            if hid is None:
                return None
            table[hid] = entry if isinstance(entry, dict) else {"value": entry}
        return table
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                return None
            hid = None
            for key in ("haunt", "haunt_id", "haunt_no", "id", "n"):
                if key in entry:
                    hid = _haunt_id(entry[key])
                    break
            if hid is None:
                return None
            table[hid] = entry
        return table
    return None


def _profile_groups(doc: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    value = _pick(doc, ALIAS["by_profile"])
    if value["status"] != "found":
        return None
    raw = value["value"]
    groups: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, entry in raw.items():
            groups[str(key)] = entry if isinstance(entry, dict) else {"value": entry}
        return groups
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                return None
            name = None
            for key in ("profile", "profile_kind", "kind", "group", "name", "type"):
                if key in entry:
                    name = str(entry[key])
                    break
            if name is None:
                return None
            groups[name] = entry
        return groups
    return None


def _classify_profiles(groups: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Dict[str, Any]]]:
    default_entry = None
    dedicated_entry = None
    for name, entry in groups.items():
        text = _norm(name)
        is_default = any(hint in text for hint in DEFAULT_PROFILE_HINTS)
        is_dedicated = any(hint in text for hint in DEDICATED_PROFILE_HINTS)
        if is_default and not is_dedicated:
            default_entry = entry
        elif is_dedicated and not is_default:
            dedicated_entry = entry
    if default_entry is None or dedicated_entry is None:
        return None
    return {"default": default_entry, "dedicated": dedicated_entry}


def _haunt_set(entry: Dict[str, Any]) -> Optional[set]:
    for key in ("haunts", "haunt_ids", "haunt_list", "ids", "members"):
        if key not in entry:
            continue
        raw = entry[key]
        if isinstance(raw, dict):
            ids = {_haunt_id(item) for item in raw}
        elif isinstance(raw, (list, tuple, set)):
            ids = {_haunt_id(item) for item in raw}
        else:
            return None
        if None in ids:
            return None
        return set(ids)
    return None


def _entry_games(entry: Dict[str, Any]) -> Optional[int]:
    number = _pick_count(entry, ALIAS["games"])
    if number["status"] == "found":
        return int(number["value"])
    heroes = _pick_count(entry, ALIAS["heroes"])
    traitor = _pick_count(entry, ALIAS["traitor"])
    unfinished = _pick_count(entry, ALIAS["unfinished"])
    if heroes["status"] == traitor["status"] == unfinished["status"] == "found":
        return int(heroes["value"]) + int(traitor["value"]) + int(unfinished["value"])
    return None


def _group_games(entry: Dict[str, Any]) -> Optional[int]:
    return _entry_games(entry)


def _per_haunt_games(doc: Any) -> Optional[int]:
    seeds = _int_list(_pick(doc, ALIAS["seeds"]))
    players = _int_list(_pick(doc, ALIAS["players"]))
    if not seeds or not players:
        return None
    return len(seeds) * len(players)


def _source_key_legal(key: Any) -> bool:
    return _norm(key) in ("table", "fallback")


# --------------------------------------------------------------------------- #
# W 组：胜率基线
# --------------------------------------------------------------------------- #

def check_w01(ctx: Ctx) -> Tuple[str, str, List[str]]:
    path = ctx.paths["winrate"]
    if not path.is_file():
        return NOT_RUN, "缺少 %s；胜率基线 11 条判据均无法判定" % ctx.rel(path), []
    if ctx.data.get("winrate") is None:
        return FAIL, "产物存在但无法解析：%s" % ctx.errors.get("winrate"), [ctx.rel(path)]
    return PASS, "产物可解析（%d 字节）" % path.stat().st_size, [ctx.rel(path)]


def check_w02(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    if not isinstance(doc, dict):
        return FAIL, "顶层不是对象（%s）" % type(doc).__name__, []
    result = _pick(doc, ALIAS["seeds"])
    if result["status"] == "missing":
        return FAIL, "缺少 seeds 列表：基线无法复现", []
    if result["status"] == "conflict":
        return FAIL, "seeds 在多个位置取值不一致：%s" % ", ".join(result["hits"]), []
    seeds = _int_list(result)
    if seeds is None:
        return FAIL, "seeds 不是整型列表：%r" % (result["value"],), []
    if not seeds:
        return FAIL, "seeds 为空：无种子即无基线证据", []
    duplicates = sorted({seed for seed in seeds if seeds.count(seed) > 1})
    if duplicates:
        return FAIL, "seeds 存在重复值：%s" % duplicates, []
    canonical = set(CANONICAL_SEEDS)
    same = set(seeds) == canonical
    detail = "seeds=%d 个（%s）" % (len(seeds), result["path"])
    detail += "；与 BASE-A 11 种子%s（仅记录，不判定）" % ("一致" if same else "不一致")
    return PASS, detail, [ctx.rel(ctx.paths["winrate"])]


def check_w03(ctx: Ctx) -> Tuple[str, str, List[str]]:
    """runtime 版本，或等价的内容哈希（engine_sha256 必须与磁盘一致）。"""
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    runtime = _runtime_version(doc)
    if runtime["status"] == "found":
        value = _norm(runtime["value"])
        if value in ELIGIBLE_RUNTIME:
            return FAIL, "runtime 版本为占位值：%r" % runtime["value"], []
        return PASS, "runtime=%s（%s）" % (runtime["value"], runtime["path"]), []

    block = doc.get("runtime") if isinstance(doc.get("runtime"), dict) else {}
    engine_hash = ""
    engine_key = ""
    for key in ("engine_sha256", "engine_hash", "engine_digest", "build_sha256"):
        raw = block.get(key)
        if isinstance(raw, str) and raw.strip():
            engine_hash = raw.strip().lower()
            engine_key = key
            break
    if not engine_hash:
        if runtime["status"] == "insufficient":
            return FAIL, "runtime 字段无版本号：%s" % runtime.get("detail", ""), []
        return FAIL, "缺少 runtime 版本字段（runtime/runtime_version/engine_version）", []

    engine_path = ctx.paths["engine"]
    if not engine_path.is_file():
        return FAIL, "engine.py 缺失，无法核对 %s" % engine_key, []
    actual = _sha256(engine_path)
    if actual != engine_hash:
        return FAIL, "%s 与磁盘不一致（记录 %s…，实际 %s…）：证据身份漂移" % (
            engine_key, engine_hash[:12], actual[:12],
        ), [ctx.rel(engine_path)]
    for key in ("haunt_ai_profiles_sha256", "profiles_sha256", "haunt_ai_sha256"):
        raw = block.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        profiles_path = ctx.paths["profiles"]
        if not profiles_path.is_file():
            return FAIL, "%s 已记录但 haunt_ai_profiles.py 缺失" % key, []
        actual_profiles = _sha256(profiles_path)
        if actual_profiles != raw.strip().lower():
            return FAIL, "%s 与磁盘不一致（记录 %s…，实际 %s…）" % (
                key, raw.strip()[:12], actual_profiles[:12],
            ), [ctx.rel(profiles_path)]
    return PASS, "runtime 以 %s 固定（%s…），与磁盘一致" % (engine_key, engine_hash[:12]), [
        ctx.rel(engine_path),
    ]


def check_w04(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    seed_result = _pick(doc, ALIAS["seeds"])
    players_result = _pick(doc, ALIAS["players"])
    games_result = _pick_count(doc, ALIAS["games"])
    seeds = _int_list(seed_result)
    players = _int_list(players_result)
    if seeds is None or players is None:
        return NOT_RUN, "seeds 或 players 缺失/非法，无法复算局数", []
    problems: List[str] = []
    if not seeds:
        problems.append("seeds 为空")
    if not players:
        problems.append("players 为空")
    if len(set(players)) != len(players):
        problems.append("players 有重复：%s" % players)
    illegal = [p for p in players if not 2 <= p <= 6]
    if illegal:
        problems.append("players 超出 2..6：%s" % illegal)
    if games_result["status"] == "missing":
        return NOT_RUN, "缺少 games/total_games，无法核对局数恒等式", []
    if games_result["status"] in ("invalid", "conflict"):
        return FAIL, "games 字段非法（%s）：%r" % (games_result["status"], games_result.get("value")), []
    games = int(games_result["value"])
    expected = len(seeds) * len(players) * int(ctx.constants["haunts"])
    if problems:
        return FAIL, "；".join(problems), []
    if games != expected:
        return FAIL, "games=%d，但 seeds(%d) × players(%d) × haunts(%d) = %d" % (
            games, len(seeds), len(players), ctx.constants["haunts"], expected,
        ), []
    detail = "games=%d == %d seeds × %d players × %d haunts（常量来源 %s）" % (
        games, len(seeds), len(players), ctx.constants["haunts"], ctx.constants_source,
    )
    canonical = set(CANONICAL_SEEDS)
    if set(seeds) != canonical:
        detail += "；注意：非 BASE-A 种子集"
    return PASS, detail, [ctx.rel(ctx.paths["winrate"])]


def check_w05(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    games = _pick_count(doc, ALIAS["games"])
    heroes = _pick_count(doc, ALIAS["heroes"])
    traitor = _pick_count(doc, ALIAS["traitor"])
    unfinished = _pick_count(doc, ALIAS["unfinished"])
    missing = [
        name for name, result in (
            ("games", games), ("heroes_win", heroes),
            ("traitor_win", traitor), ("unfinished", unfinished),
        ) if result["status"] != "found"
    ]
    if missing:
        return NOT_RUN, "缺少计数口径：%s" % ", ".join(missing), []
    total = int(heroes["value"]) + int(traitor["value"]) + int(unfinished["value"])
    if total != int(games["value"]):
        return FAIL, "heroes(%d) + traitor(%d) + unfinished(%d) = %d，但 games=%d" % (
            heroes["value"], traitor["value"], unfinished["value"], total, games["value"],
        ), []
    return PASS, "heroes=%d + traitor=%d + unfinished=%d == games=%d" % (
        heroes["value"], traitor["value"], unfinished["value"], games["value"],
    ), []


def check_w06(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    games = _pick_count(doc, ALIAS["games"])
    heroes = _pick_count(doc, ALIAS["heroes"])
    traitor = _pick_count(doc, ALIAS["traitor"])
    unfinished = _pick_count(doc, ALIAS["unfinished"])
    if any(result["status"] != "found" for result in (games, heroes, traitor, unfinished)):
        return NOT_RUN, "缺少计数，无法复算胜率", []
    total = int(games["value"])
    if total <= 0:
        return FAIL, "games=%d，无法计算胜率" % total, []
    counts = {
        "hero": int(heroes["value"]),
        "traitor": int(traitor["value"]),
        "unfinished": int(unfinished["value"]),
    }
    negative = [name for name, count in counts.items() if count < 0]
    if negative:
        return FAIL, "计数为负：%s" % negative, []
    computed = {name: count / total for name, count in counts.items()}
    stored_aliases = {
        "hero": ("hero_win_rate", "heroes_win_rate", "hero_rate", "hero_winrate"),
        "traitor": ("traitor_win_rate", "traitor_rate", "traitor_winrate"),
        "unfinished": ("unfinished_rate", "incomplete_rate"),
    }
    problems: List[str] = []
    for name, aliases in stored_aliases.items():
        result = _pick(doc, aliases)
        if result["status"] == "missing":
            continue
        if result["status"] != "found":
            problems.append("%s 胜率字段冲突/非法" % name)
            continue
        value = _as_number(result["value"])
        if value is None:
            problems.append("%s 胜率不是数值：%r" % (name, result["value"]))
            continue
        if not 0.0 <= value <= 1.0:
            problems.append("%s 胜率=%r 超出 [0,1]（疑似百分数）" % (name, value))
            continue
        if abs(value - computed[name]) > 0.001:
            problems.append("%s 存储胜率=%.6f，复算=%.6f" % (name, value, computed[name]))
    if problems:
        return FAIL, "；".join(problems), []
    detail = "hero=%.4f traitor=%.4f unfinished=%.4f（均 ∈ [0,1]，可由计数复算）" % (
        computed["hero"], computed["traitor"], computed["unfinished"],
    )
    return PASS, detail, []


def check_w07(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    table = _haunt_table(doc)
    if table is None:
        result = _pick(doc, ALIAS["by_haunt"])
        if result["status"] == "missing":
            return FAIL, "缺少 by_haunt：无法证明 70 本覆盖", []
        return FAIL, "by_haunt 无法规范化为 haunt_id → 计数映射", []
    expected = set(range(1, int(ctx.constants["haunts"]) + 1))
    found = set(table)
    missing = sorted(expected - found)
    extra = sorted(found - expected)
    if missing or extra or len(found) != int(ctx.constants["haunts"]):
        detail = "by_haunt 键数=%d，期望 %d" % (len(found), ctx.constants["haunts"])
        if missing:
            detail += "；缺 %d 本：%s" % (len(missing), missing[:12])
        if extra:
            detail += "；多出：%s" % extra[:12]
        return FAIL, detail, []
    return PASS, "by_haunt 覆盖 1..%d 共 %d 项" % (ctx.constants["haunts"], len(found)), []


def check_w08(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    table = _haunt_table(doc)
    per_haunt = _per_haunt_games(doc)
    games = _pick_count(doc, ALIAS["games"])
    if table is None or per_haunt is None or games["status"] != "found":
        return NOT_RUN, "by_haunt / seeds / players / games 不足以复算分剧本计数", []
    no_counts = [hid for hid, entry in table.items() if _entry_games(entry) is None]
    if no_counts:
        return FAIL, "%d/%d 本缺少分剧本计数（如 %s）" % (
            len(no_counts), len(table), sorted(no_counts)[:12],
        ), []
    counts = {hid: int(_entry_games(entry)) for hid, entry in table.items()}
    wrong = {hid: count for hid, count in counts.items() if count != per_haunt}
    if wrong:
        sample = sorted(wrong.items())[:8]
        return FAIL, "每本局数应为 %d，异常 %d 本：%s" % (per_haunt, len(wrong), sample), []
    total = sum(counts.values())
    if total != int(games["value"]):
        return FAIL, "分剧本合计=%d，但 games=%d" % (total, games["value"]), []
    # 单本三层恒等式（若三项齐全）
    broken = []
    for hid, entry in table.items():
        heroes = _pick_count(entry, ALIAS["heroes"])
        traitor = _pick_count(entry, ALIAS["traitor"])
        unfinished = _pick_count(entry, ALIAS["unfinished"])
        if heroes["status"] == traitor["status"] == unfinished["status"] == "found":
            if int(heroes["value"]) + int(traitor["value"]) + int(unfinished["value"]) != counts[hid]:
                broken.append(hid)
    if broken:
        return FAIL, "%d 本 heroes+traitor+unfinished 与分本局数不一致：%s" % (
            len(broken), sorted(broken)[:12],
        ), []
    return PASS, "70 本每本 %d 局，合计 %d == games" % (per_haunt, total), []


def check_w09(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    groups = _profile_groups(doc)
    if groups is None:
        result = _pick(doc, ALIAS["by_profile"])
        if result["status"] == "missing":
            return FAIL, "缺少 by_profile：默认档案与专属档案无法分层", []
        return FAIL, "by_profile 无法规范化为分组映射", []
    split = _classify_profiles(groups)
    if split is None:
        return FAIL, "by_profile 未区分 default 与 dedicated：%s" % sorted(groups), []
    return PASS, "by_profile 分组：%s" % sorted(groups), []


def check_w10(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    groups = _profile_groups(doc)
    split = _classify_profiles(groups or {})
    if groups is None or split is None:
        return NOT_RUN, "by_profile 未形成可判定的 default/dedicated 两组", []
    per_haunt = _per_haunt_games(doc)
    games = _pick_count(doc, ALIAS["games"])
    if per_haunt is None or games["status"] != "found":
        return NOT_RUN, "seeds/players/games 缺失，无法复算 51/19 分摊", []
    haunts = int(ctx.constants["haunts"])
    overrides = ctx.profile_keys
    if overrides is None:
        dedicated_count = 51
        default_count = haunts - dedicated_count
        source = "文档常量 51/19（%s）" % ctx.profile_source
    else:
        dedicated_count = len(overrides)
        default_count = haunts - dedicated_count
        source = "haunt_ai_profiles（%d/%d）" % (dedicated_count, default_count)
    problems: List[str] = []
    dedicated_set = _haunt_set(split["dedicated"])
    default_set = _haunt_set(split["default"])
    if dedicated_set is not None and overrides is not None:
        if dedicated_set != set(overrides):
            problems.append("dedicated 剧本集与覆盖表不一致（多 %s / 少 %s）" % (
                sorted(dedicated_set - set(overrides))[:8],
                sorted(set(overrides) - dedicated_set)[:8],
            ))
    if default_set is not None and overrides is not None:
        expected_default = set(range(1, haunts + 1)) - set(overrides)
        if default_set != expected_default:
            problems.append("default 剧本集与未覆盖集不一致（多 %s / 少 %s）" % (
                sorted(default_set - expected_default)[:8],
                sorted(expected_default - default_set)[:8],
            ))
    dedicated_games = _group_games(split["dedicated"])
    default_games = _group_games(split["default"])
    if dedicated_games is None or default_games is None:
        problems.append("至少一组缺少 games 计数")
    else:
        if dedicated_games != dedicated_count * per_haunt:
            problems.append("dedicated games=%d，期望 %d×%d=%d" % (
                dedicated_games, dedicated_count, per_haunt, dedicated_count * per_haunt,
            ))
        if default_games != default_count * per_haunt:
            problems.append("default games=%d，期望 %d×%d=%d" % (
                default_games, default_count, per_haunt, default_count * per_haunt,
            ))
        if dedicated_games + default_games != int(games["value"]):
            problems.append("两组之和=%d，但 games=%d" % (
                dedicated_games + default_games, games["value"],
            ))
    if problems:
        return FAIL, "；".join(problems), []
    return PASS, "dedicated %d 本 / default %d 本，两组之和 == games（%s）" % (
        dedicated_count, default_count, source,
    ), []


def check_w11(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("winrate")
    if not doc:
        return NOT_RUN, "缺少可解析的 winrate_baseline.json", []
    result = _pick(doc, ALIAS["duration"])
    if result["status"] == "missing":
        return FAIL, "缺少 duration_s/elapsed_seconds：耗时未入档", []
    if result["status"] != "found":
        return FAIL, "duration 字段冲突/非法", []
    value = _as_number(result["value"])
    if value is None:
        return FAIL, "duration 不是数值：%r" % (result["value"],), []
    if value <= 0:
        return FAIL, "duration=%r 非正" % value, []
    games = _pick_count(doc, ALIAS["games"])
    if games["status"] == "found" and int(games["value"]) >= 100 and value < 1.0:
        return FAIL, "duration=%.6fs 与 games=%d 不相称（疑似伪造）" % (value, games["value"]), []
    per_game = value / int(games["value"]) * 1000.0 if games["status"] == "found" and games["value"] else 0.0
    return PASS, "duration=%.2fs（%.2f ms/局，%s）" % (value, per_game, result["path"]), []


# --------------------------------------------------------------------------- #
# H 组：作祟查表框架
# --------------------------------------------------------------------------- #

def check_h01(ctx: Ctx) -> Tuple[str, str, List[str]]:
    path = ctx.paths["haunt"]
    if not path.is_file():
        return NOT_RUN, "缺少 %s；查表 8 条判据均无法判定" % ctx.rel(path), []
    if ctx.data.get("haunt") is None:
        return FAIL, "产物存在但无法解析：%s" % ctx.errors.get("haunt"), [ctx.rel(path)]
    return PASS, "产物可解析（%d 字节）" % path.stat().st_size, [ctx.rel(path)]


def check_h02(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    result = _pick_count(doc, ALIAS["entries"])
    if result["status"] == "missing":
        return FAIL, "缺少 entries：无法证明表为空", []
    if result["status"] != "found":
        return FAIL, "entries 字段非法（%s）" % result["status"], []
    entries = int(result["value"])
    if entries < 0:
        return FAIL, "entries=%d 为负" % entries, []
    if entries == 0:
        return PASS, "entries=0（%s）：仓库无触发表数据，符合本轮前提" % result["path"], []
    provenance = _pick(doc, ("entries_source", "table_source", "provenance", "data_source"))
    if provenance["status"] == "found":
        text = _norm(provenance["value"])
        if text not in ABSENT_TOKENS:
            return CONFLICT, "entries=%d 且声称来源 %r：表值正确性无法本地核验，超出本轮排除项" % (
                entries, provenance["value"],
            ), []
    return FAIL, "entries=%d 但无来源：无表数据时出现表项视为伪造风险" % entries, []


def check_h03(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    result = _pick_counter(doc, ALIAS["selections"], ("total", "selection_total"))
    if result["status"] == "missing":
        return NOT_RUN, "未记录 selections/total：没有运行样本", []
    if result["status"] != "found":
        return FAIL, "selections 字段非法（%s）" % result["status"], []
    selections = int(result["value"])
    if selections <= 0:
        return NOT_RUN, "selections=%d：无选择样本，未取得运行证据" % selections, []
    return PASS, "selections=%d（%s）" % (selections, result["path"]), []


def check_h04(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    entries = _pick_count(doc, ALIAS["entries"])
    if entries["status"] != "found":
        return NOT_RUN, "entries 缺失，无法判断 fallback 口径", []
    if int(entries["value"]) != 0:
        return NOT_RUN, "entries>0：100% fallback 条件不适用", []
    selections = _pick_counter(doc, ALIAS["selections"], ("total", "selection_total"))
    fallback = _pick_counter(doc, ALIAS["fallback"])
    if selections["status"] != "found" or fallback["status"] != "found":
        return NOT_RUN, "selections 或 fallback 缺失", []
    if int(fallback["value"]) != int(selections["value"]):
        return FAIL, "fallback=%d，selections=%d：entries=0 时必须 100%% 回退" % (
            fallback["value"], selections["value"],
        ), []
    rate = _pick_counter(doc, ALIAS["fallback_rate"])
    if rate["status"] == "found":
        value = _as_number(rate["value"])
        if value is None or not 0.0 <= value <= 1.0:
            return FAIL, "fallback_rate=%r 超出 [0,1]" % rate["value"], []
        if abs(value - 1.0) > 1e-9:
            return FAIL, "fallback_rate=%r，entries=0 时应为 1.0" % value, []
    return PASS, "fallback=%d == selections=%d（100%%）" % (
        fallback["value"], selections["value"],
    ), []


def check_h05(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    entries = _pick_count(doc, ALIAS["entries"])
    if entries["status"] != "found":
        return NOT_RUN, "entries 缺失，无法判断命中口径", []
    if int(entries["value"]) != 0:
        return PASS, "entries>0：命中合法性属人工核验范围（排除项）", []
    hits = _pick_counter(doc, ALIAS["table_hits"], ("table",))
    if hits["status"] == "missing":
        return NOT_RUN, "entries=0 但未记录 table_hits/table", []
    if hits["status"] != "found":
        return FAIL, "table_hits 字段非法（%s）" % hits["status"], []
    if int(hits["value"]) != 0:
        return FAIL, "entries=0 却出现 table 命中 %d 次：无表数据时命中即伪造" % hits["value"], []
    invalid = _pick_counter(doc, ("invalid", "invalid_cells", "invalid_values", "bad_values"))
    if invalid["status"] == "found" and int(invalid["value"]) != 0:
        return FAIL, "entries=0 却出现无效表值 %d 次" % invalid["value"], []
    sources = _pick(doc, ALIAS["source_counts"])
    if sources["status"] == "found" and isinstance(sources["value"], dict):
        table_count = 0
        for key, value in sources["value"].items():
            if _norm(key) == "table":
                number = _count_of(value)
                if number is None:
                    return FAIL, "source_counts.table 不是计数：%r" % (value,), []
                table_count += int(number)
        if table_count != 0:
            return FAIL, "source_counts.table=%d，但 entries=0" % table_count, []
    return PASS, "table_hits=0（entries=0）", []


def check_h06(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    selections = _pick_counter(doc, ALIAS["selections"], ("total", "selection_total"))
    fallback = _pick_counter(doc, ALIAS["fallback"])
    hits = _pick_counter(doc, ALIAS["table_hits"], ("table",))
    if any(result["status"] != "found" for result in (selections, fallback, hits)):
        return NOT_RUN, "selections/fallback/table_hits 不齐，无法核对恒等式", []
    total = int(fallback["value"]) + int(hits["value"])
    if total != int(selections["value"]):
        return FAIL, "fallback(%d) + table(%d) = %d，但 selections=%d" % (
            fallback["value"], hits["value"], total, selections["value"],
        ), []
    errors = _pick_counter(doc, ALIAS["errors"])
    if errors["status"] == "conflict":
        return FAIL, "异常计数在不同字段取值不一致：%s" % ", ".join(errors["hits"]), []
    if errors["status"] == "found" and int(errors["value"]) != 0:
        return FAIL, "errors/exceptions=%d，查表路径不得抛异常" % errors["value"], []
    sources = _pick(doc, ALIAS["source_counts"])
    if sources["status"] == "found":
        if not isinstance(sources["value"], dict):
            return FAIL, "source_counts 不是映射：%r" % (sources["value"],), []
        mapped = 0
        for key, value in sources["value"].items():
            number = _count_of(value)
            if number is None:
                return FAIL, "source_counts[%r] 不是计数：%r" % (key, value), []
            mapped += int(number)
        if mapped != int(selections["value"]):
            return FAIL, "source_counts 合计=%d，但 selections=%d" % (mapped, selections["value"]), []
    return PASS, "fallback(%d) + table(%d) == selections(%d)；errors=0" % (
        fallback["value"], hits["value"], selections["value"],
    ), []


def check_h07(ctx: Ctx) -> Tuple[str, str, List[str]]:
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    sources = _pick(doc, ALIAS["source_counts"])
    if sources["status"] == "missing":
        return PASS, "未提供分源映射；table/fallback 两桶已由 H-04/H-05 覆盖", []
    if sources["status"] != "found" or not isinstance(sources["value"], dict):
        return FAIL, "source_counts 不是映射，无法核对枚举", []
    illegal = [key for key in sources["value"] if not _source_key_legal(key)]
    if illegal:
        return FAIL, "source 取值越界：%s（仅允许 table / fallback）" % illegal, []
    return PASS, "source 取值仅 table / fallback：%s" % sorted(sources["value"]), []


def check_h08(ctx: Ctx) -> Tuple[str, str, List[str]]:
    """表状态快照与 entries 自洽：空表前提必须由加载器自己的状态证实。"""
    doc = ctx.data.get("haunt")
    if not doc:
        return NOT_RUN, "缺少可解析的 haunt_table_stats.json", []
    table = None
    for key in ("table", "table_status", "table_snapshot"):
        candidate = doc.get(key) if isinstance(doc, dict) else None
        if isinstance(candidate, dict):
            table = candidate
            break
    if table is None:
        return NOT_RUN, "未记录 table 状态快照（exists/empty/filled_cells）", []
    entries = _pick_count(doc, ALIAS["entries"])
    if entries["status"] != "found":
        return NOT_RUN, "entries 缺失，无法与表状态互证", []
    declared = int(entries["value"])
    problems: List[str] = []
    exists = table.get("exists")
    empty = table.get("empty")
    filled = _pick_count(table, ("filled_cells", "filled", "entries"))
    if isinstance(exists, bool) and isinstance(empty, bool) and exists is False and empty is False:
        problems.append("exists=false 但 empty=false")
    if isinstance(empty, bool):
        if empty and declared != 0:
            problems.append("table.empty=true 但 entries=%d" % declared)
        if not empty and declared == 0:
            problems.append("table.empty=false 但 entries=0")
    if filled["status"] == "found" and int(filled["value"]) != declared:
        problems.append("filled_cells=%d 与 entries=%d 不一致" % (filled["value"], declared))
    if problems:
        return FAIL, "；".join(problems), []
    return PASS, "表状态 exists=%r empty=%r filled=%r 与 entries=%d 自洽" % (
        exists, empty, filled["value"] if filled["status"] == "found" else None, declared,
    ), []


# --------------------------------------------------------------------------- #
# G 组：回归护栏
# --------------------------------------------------------------------------- #

def _count_test_methods(path: Path) -> Tuple[Optional[int], str]:
    if not path.is_file():
        return None, "缺少 %s" % path.name
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return None, "解析失败：%s: %s" % (type(exc).__name__, exc)
    names = [
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
    ]
    return len(names), "AST 统计 test* 方法"


def _verify_asset_ids(path: Path) -> Tuple[Optional[set], str]:
    if not path.is_file():
        return None, "缺少 %s" % path.name
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return None, "解析失败：%s: %s" % (type(exc).__name__, exc)
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            ids.add(first.value)
    return ids, "AST 统计 checker.add(\"Vxx\")"


def _contract_check_ids(path: Path) -> Tuple[Optional[set], str]:
    if not path.is_file():
        return None, "缺少 %s" % path.name
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return None, "解析失败：%s: %s" % (type(exc).__name__, exc)
    ids = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "CHECKS" for target in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue
        for element in node.value.elts:
            if isinstance(element, ast.Tuple) and element.elts:
                first = element.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    ids.add(first.value)
    return ids, "AST 统计 CHECKS 列表"


def _guardrail_tests(ctx: Ctx) -> Tuple[Optional[Dict[str, Any]], Optional[datetime], str]:
    guardrails = ctx.data.get("guardrails")
    if isinstance(guardrails, dict) and isinstance(guardrails.get("tests"), dict):
        stamp, _ = _evidence_time(guardrails, ctx.paths["guardrails"])
        return guardrails["tests"], stamp, ctx.rel(ctx.paths["guardrails"])
    report = ctx.data.get("execution_report")
    if isinstance(report, dict) and isinstance(report.get("new_tests"), dict):
        stamp, _ = _evidence_time(report, ctx.paths["execution_report"])
        return report["new_tests"], stamp, ctx.rel(ctx.paths["execution_report"]) + "#new_tests"
    return None, None, ""


def _guardrail_verify_assets(ctx: Ctx) -> Tuple[Optional[Dict[str, Any]], Optional[datetime], str]:
    guardrails = ctx.data.get("guardrails")
    if isinstance(guardrails, dict) and isinstance(guardrails.get("verify_assets"), dict):
        stamp, _ = _evidence_time(guardrails, ctx.paths["guardrails"])
        return guardrails["verify_assets"], stamp, ctx.rel(ctx.paths["guardrails"])
    report = ctx.data.get("validation_report")
    if isinstance(report, dict):
        stamp, _ = _evidence_time(report, ctx.paths["validation_report"])
        return report, stamp, ctx.rel(ctx.paths["validation_report"])
    return None, None, ""


def _guardrail_contract(ctx: Ctx) -> Tuple[Optional[Dict[str, Any]], Optional[datetime], str]:
    guardrails = ctx.data.get("guardrails")
    if isinstance(guardrails, dict) and isinstance(guardrails.get("contract"), dict):
        stamp, _ = _evidence_time(guardrails, ctx.paths["guardrails"])
        return guardrails["contract"], stamp, ctx.rel(ctx.paths["guardrails"])
    result = ctx.data.get("contract_result")
    if isinstance(result, dict):
        stamp, _ = _evidence_time(result, ctx.paths["contract_result"])
        return result, stamp, ctx.rel(ctx.paths["contract_result"])
    return None, None, ""


def _staleness(ctx: Ctx, stamp: Optional[datetime]) -> Optional[float]:
    reference = _reference_time(ctx)
    if stamp is None or reference is None:
        return None
    return (reference - stamp).total_seconds()


def check_g01(ctx: Ctx) -> Tuple[str, str, List[str]]:
    total, note = _count_test_methods(ctx.paths["tests"])
    if total is None:
        return FAIL, note, [ctx.rel(ctx.paths["tests"])]
    if total < BASELINE_TESTS:
        return FAIL, "test* 方法 %d 条，低于基线 %d（既有用例被删）" % (total, BASELINE_TESTS), []
    return PASS, "test* 方法 %d 条 ≥ %d（%s）" % (total, BASELINE_TESTS, note), [
        ctx.rel(ctx.paths["tests"]),
    ]


def check_g02(ctx: Ctx) -> Tuple[str, str, List[str]]:
    evidence, stamp, source = _guardrail_tests(ctx)
    if evidence is None:
        return NOT_RUN, "缺少 63 测试的复跑证据（qa/run6_guardrails.json 或执行报告 new_tests）", []
    total = _count_of(evidence.get("total", evidence.get("pass")))
    fail = _count_of(evidence.get("fail"))
    error = _count_of(evidence.get("error"))
    if total is None:
        return FAIL, "测试证据缺少 total：%r" % (evidence,), [source]
    if total < BASELINE_TESTS:
        return FAIL, "测试总数 %d，低于基线 %d" % (total, BASELINE_TESTS), [source]
    if fail is None or error is None:
        return FAIL, "测试证据缺少 fail/error 计数", [source]
    if fail + error != 0:
        return FAIL, "测试 fail=%d / error=%d，不得回退" % (fail, error), [source]
    stale = _staleness(ctx, stamp)
    if stale is None:
        return NOT_RUN, "测试证据时间不可判定", [source]
    if stale > 1.0:
        return FAIL, "测试证据早于实现产物 %.0fs（生成于 %s）" % (stale, _iso(stamp)), [source]
    return PASS, "测试 %d 条，fail=0 error=0，证据新鲜（%s）" % (total, source), [source]


def check_g03(ctx: Ctx) -> Tuple[str, str, List[str]]:
    ids, note = _verify_asset_ids(ctx.paths["verify_assets"])
    if ids is None:
        return FAIL, note, [ctx.rel(ctx.paths["verify_assets"])]
    expected = {"V%02d" % index for index in range(1, BASELINE_VERIFY_ASSETS + 1)}
    missing = sorted(expected - ids)
    if missing:
        return FAIL, "verify_assets 缺少检查项：%s" % missing, []
    return PASS, "verify_assets 检查项 %d 个，V01..V17 齐全（%s）" % (len(ids), note), [
        ctx.rel(ctx.paths["verify_assets"]),
    ]


def check_g04(ctx: Ctx) -> Tuple[str, str, List[str]]:
    evidence, stamp, source = _guardrail_verify_assets(ctx)
    if evidence is None:
        return NOT_RUN, "缺少 verify_assets 复跑证据（qa/run6_guardrails.json 或 assets/validation_report.json）", []
    totals = evidence.get("totals") if isinstance(evidence.get("totals"), dict) else evidence
    checked = _count_of(totals.get("checked", totals.get("total")))
    failed = _count_of(totals.get("failed", totals.get("fail")))
    ok = evidence.get("ok")
    if checked is None or failed is None:
        return FAIL, "verify_assets 证据缺少 checked/failed 计数", [source]
    if checked < BASELINE_VERIFY_ASSETS:
        return FAIL, "checked=%d，低于基线 %d" % (checked, BASELINE_VERIFY_ASSETS), [source]
    if failed != 0:
        return FAIL, "failed=%d，不得回退" % failed, [source]
    if ok is False:
        return FAIL, "ok=false，不得回退", [source]
    stale = _staleness(ctx, stamp)
    if stale is None:
        return NOT_RUN, "verify_assets 证据时间不可判定", [source]
    if stale > 1.0:
        return FAIL, "verify_assets 证据早于实现产物 %.0fs（生成于 %s）" % (stale, _iso(stamp)), [source]
    return PASS, "verify_assets %d/%d，0 fail，证据新鲜（%s）" % (checked, checked, source), [source]


def check_g05(ctx: Ctx) -> Tuple[str, str, List[str]]:
    ids, note = _contract_check_ids(ctx.paths["contract_tool"])
    if ids is None:
        return FAIL, note, [ctx.rel(ctx.paths["contract_tool"])]
    expected = {"C%02d" % index for index in range(1, BASELINE_CONTRACT + 1)}
    missing = sorted(expected - ids)
    if missing:
        return FAIL, "契约缺少检查项：%s" % missing, []
    return PASS, "契约检查项 %d 个，C01..C32 齐全（%s）" % (len(ids), note), [
        ctx.rel(ctx.paths["contract_tool"]),
    ]


def check_g06(ctx: Ctx) -> Tuple[str, str, List[str]]:
    evidence, stamp, source = _guardrail_contract(ctx)
    if evidence is None:
        return NOT_RUN, "缺少契约复跑证据（qa/run6_guardrails.json 或 qa/contract_result.json）", []
    summary = evidence.get("summary") if isinstance(evidence.get("summary"), dict) else evidence
    total = _count_of(summary.get("total"))
    passed = _count_of(summary.get("pass"))
    failed = _count_of(summary.get("fail"))
    exit_code = summary.get("exit_code")
    if total is None or passed is None or failed is None:
        return FAIL, "契约证据缺少 total/pass/fail 计数", [source]
    if total < BASELINE_CONTRACT or passed < BASELINE_CONTRACT:
        return FAIL, "契约 total=%d pass=%d，低于基线 %d" % (
            total, passed, BASELINE_CONTRACT,
        ), [source]
    if failed != 0:
        return FAIL, "契约 fail=%d，不得回退" % failed, [source]
    if exit_code not in (0, None):
        return FAIL, "契约 exit_code=%r，不得回退" % exit_code, [source]
    stale = _staleness(ctx, stamp)
    if stale is None:
        return NOT_RUN, "契约证据时间不可判定", [source]
    if stale > 1.0:
        return FAIL, "契约证据早于实现产物 %.0fs（生成于 %s）" % (stale, _iso(stamp)), [source]
    return PASS, "契约 %d/%d，0 fail，证据新鲜（%s）" % (passed, total, source), [source]


# --------------------------------------------------------------------------- #
# X 组：证据归属与只读自证
# --------------------------------------------------------------------------- #

def check_x01(ctx: Ctx) -> Tuple[str, str, List[str]]:
    winrate = ctx.data.get("winrate")
    haunt = ctx.data.get("haunt")
    if not winrate or not haunt:
        return NOT_RUN, "至少一份产物缺失，时间戳无法成对核对", []
    win_time, win_key = _doc_time(winrate)
    haunt_time, haunt_key = _doc_time(haunt)
    if win_time is None or haunt_time is None:
        missing = []
        if win_time is None:
            missing.append("winrate_baseline.json")
        if haunt_time is None:
            missing.append("haunt_table_stats.json")
        return FAIL, "缺少可解析 generated_at：%s" % ", ".join(missing), []
    return PASS, "winrate@%s（%s）；haunt@%s（%s）" % (
        _iso(win_time), win_key, _iso(haunt_time), haunt_key,
    ), []


def check_x02(ctx: Ctx) -> Tuple[str, str, List[str]]:
    changed = []
    tracked = []
    missing = []
    for key, before in ctx.impl_before.items():
        path = ctx.paths[key]
        after = ctx.fingerprint(path)
        if before != after:
            changed.append(ctx.rel(path))
        elif path.is_file():
            tracked.append(ctx.rel(path))
        else:
            missing.append(ctx.rel(path))
    if changed:
        return FAIL, "验收期间实现文件发生变化：%s" % changed, changed
    detail = "实现文件哈希未变（%d 个存在）" % len(tracked)
    if missing:
        detail += "；未交付：%s" % ", ".join(missing)
    return PASS, detail + "；脚本无写操作", tracked


# --------------------------------------------------------------------------- #
# 判据清单
# --------------------------------------------------------------------------- #

CHECKS: List[Tuple[str, str, str, Any]] = [
    ("W-01", "胜率基线产物存在且可解析", "P0", check_w01),
    ("W-02", "seeds 列表已入档（非空/唯一/整型）", "P0", check_w02),
    ("W-03", "runtime 版本/引擎哈希已入档", "P0", check_w03),
    ("W-04", "games == seeds × players × 70", "P0", check_w04),
    ("W-05", "heroes + traitor + unfinished == games", "P0", check_w05),
    ("W-06", "胜率区间 [0,1] 且可由计数复算", "P0", check_w06),
    ("W-07", "by_haunt 覆盖 1..70 共 70 项", "P0", check_w07),
    ("W-08", "by_haunt 分本计数与总局数自洽", "P1", check_w08),
    ("W-09", "by_profile 区分 default 与 dedicated", "P0", check_w09),
    ("W-10", "by_profile 分组与 51/19 档案覆盖一致", "P1", check_w10),
    ("W-11", "duration_s 已入档且与局数相称", "P2", check_w11),
    ("H-01", "查表统计产物存在且可解析", "P0", check_h01),
    ("H-02", "entries 为空（无表数据）", "P0", check_h02),
    ("H-03", "selections 已记录且有样本", "P0", check_h03),
    ("H-04", "entries 为空时 fallback 率 100%", "P0", check_h04),
    ("H-05", "entries 为空时 table 命中为 0", "P0", check_h05),
    ("H-06", "fallback + table == selections 且无异常", "P0", check_h06),
    ("H-07", "source 取值仅 table/fallback", "P1", check_h07),
    ("H-08", "表状态快照与 entries 自洽", "P1", check_h08),
    ("G-01", "既有 63 测试用例只增不减", "P0", check_g01),
    ("G-02", "63 测试最近一次 0 fail/0 error 且新鲜", "P1", check_g02),
    ("G-03", "verify_assets 17 项检查只增不减", "P0", check_g03),
    ("G-04", "verify_assets 最近一次 17/17 且新鲜", "P1", check_g04),
    ("G-05", "契约 32 项检查只增不减", "P0", check_g05),
    ("G-06", "契约最近一次 32/32 且新鲜", "P1", check_g06),
    ("X-01", "两份产物时间戳可归属", "P2", check_x01),
    ("X-02", "验收过程未修改实现文件", "P1", check_x02),
]

EXCLUDED = [
    "官方 91 格触发表值的正确性：仓库无权威表数据，本地无法核验；本轮只验收「框架 + 回退」行为。",
    "AI 强度目标（英雄胜率是否达标）：只建立基线，不设阈值、不判优劣。",
    "2310 局与 186 条黄金回放的逐局哈希等价：需实现方运行，验收脚本只读不代跑。",
    "表值来源的真实性（页码/版本/誊录）：只核对 provenance 是否存在，不核对其内容。",
    "bot 对局与人类对局的平衡性：基线只作相对指标，不代表人类对局。",
]


# --------------------------------------------------------------------------- #
# 审计与输出
# --------------------------------------------------------------------------- #

class Audit(object):
    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx
        self.checks: List[Dict[str, Any]] = []

    def run(self) -> None:
        for check_id, title, priority, func in CHECKS:
            try:
                status, detail, evidence = func(self.ctx)
            except Exception as exc:  # noqa: BLE001 - 检查异常必须显式暴露
                status, detail, evidence = FAIL, "检查执行异常：%s: %s" % (
                    type(exc).__name__, exc,
                ), []
            if status not in (PASS, FAIL, NOT_RUN, CONFLICT):
                status = FAIL
                detail = "检查返回未知状态；%s" % detail
            self.checks.append({
                "id": check_id,
                "title": title,
                "priority": priority,
                "status": status,
                "detail": detail,
                "evidence": list(evidence),
            })

    def statuses(self) -> Dict[str, str]:
        return {check["id"]: check["status"] for check in self.checks}


def _counts(statuses: Iterable[str]) -> Dict[str, int]:
    counts = {PASS: 0, FAIL: 0, NOT_RUN: 0, CONFLICT: 0}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts


def _observations(ctx: Ctx) -> Dict[str, Any]:
    winrate = ctx.data.get("winrate") if isinstance(ctx.data.get("winrate"), dict) else {}
    haunt = ctx.data.get("haunt") if isinstance(ctx.data.get("haunt"), dict) else {}
    seeds = _int_list(_pick(winrate, ALIAS["seeds"])) or []
    players = _int_list(_pick(winrate, ALIAS["players"])) or []
    games = _pick_count(winrate, ALIAS["games"])
    heroes = _pick_count(winrate, ALIAS["heroes"])
    traitor = _pick_count(winrate, ALIAS["traitor"])
    unfinished = _pick_count(winrate, ALIAS["unfinished"])
    runtime = _runtime_version(winrate)
    runtime_block = winrate.get("runtime") if isinstance(winrate.get("runtime"), dict) else {}
    runtime_identity = runtime.get("value") if runtime["status"] == "found" else ""
    if not runtime_identity:
        for key in ("engine_sha256", "engine_hash", "engine_digest", "build_sha256"):
            raw = runtime_block.get(key)
            if isinstance(raw, str) and raw.strip():
                runtime_identity = raw.strip()
                break
    entries = _pick_count(haunt, ALIAS["entries"])
    selections = _pick_count(haunt, ALIAS["selections"])
    fallback = _pick_count(haunt, ALIAS["fallback"])
    hits = _pick_count(haunt, ALIAS["table_hits"])
    return {
        "winrate": {
            "seeds": seeds,
            "seeds_canonical": set(seeds) == set(CANONICAL_SEEDS) if seeds else None,
            "players": players,
            "games": games.get("value") if games["status"] == "found" else None,
            "heroes_win": heroes.get("value") if heroes["status"] == "found" else None,
            "traitor_win": traitor.get("value") if traitor["status"] == "found" else None,
            "unfinished": unfinished.get("value") if unfinished["status"] == "found" else None,
            "runtime": runtime.get("value") if runtime["status"] == "found" else None,
            "runtime_identity": runtime_identity or None,
        },
        "haunt_table": {
            "entries": entries.get("value") if entries["status"] == "found" else None,
            "selections": selections.get("value") if selections["status"] == "found" else None,
            "fallback": fallback.get("value") if fallback["status"] == "found" else None,
            "table_hits": hits.get("value") if hits["status"] == "found" else None,
        },
        "constants": ctx.constants,
        "constants_source": ctx.constants_source,
        "profile_overrides": len(ctx.profile_keys) if ctx.profile_keys is not None else None,
        "profile_source": ctx.profile_source,
    }


def build_payload(ctx: Ctx, audit: Audit) -> Dict[str, Any]:
    statuses = audit.statuses()
    counts = _counts(statuses.values())
    failed = [check["id"] for check in audit.checks if check["status"] == FAIL]
    not_run = [check["id"] for check in audit.checks if check["status"] == NOT_RUN]
    conflicts = [check["id"] for check in audit.checks if check["status"] == CONFLICT]
    if failed:
        verdict = FAIL
        claim = "not-attested"
    elif not_run or conflicts:
        verdict = "INCOMPLETE"
        claim = "partial"
    else:
        verdict = PASS
        claim = "attested"
    inputs = {}
    for key in (
        "winrate", "haunt", "guardrails", "validation_report",
        "contract_result", "execution_report", "engine", "content",
        "haunt_table_module", "winrate_module", "tests",
        "verify_assets", "contract_tool",
    ):
        path = ctx.paths[key]
        inputs[key] = {
            "path": ctx.rel(path),
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": _sha256(path) if path.is_file() else "",
            "mtime": _iso(_file_time(path)),
        }
    return {
        "tool": "qa/verify_winrate_haunt.py",
        "mode": "run6-item2-item3-acceptance",
        "readonly": True,
        "generated_at": _iso(datetime.now()),
        "root": str(ctx.root).replace("\\", "/"),
        "game_dir": ctx.rel(ctx.game),
        "environment": {
            "python": platform.python_version(),
            "executable": sys.executable.replace("\\", "/"),
            "platform": platform.platform(),
        },
        "criteria_total": len(CHECKS),
        "inputs": inputs,
        "observations": _observations(ctx),
        "checks": audit.checks,
        "counts": counts,
        "failed": failed,
        "not_run": not_run,
        "conflicts": conflicts,
        "excluded": EXCLUDED,
        "verdict": verdict,
        "claim": claim,
    }


def print_text(payload: Dict[str, Any]) -> None:
    print("机器人胜率基线 + 作祟查表框架 独立验收（只读）")
    print("根目录: %s" % payload["root"])
    print("判定: %s    claim: %s    判据: %d 条" % (
        payload["verdict"], payload["claim"], payload["criteria_total"],
    ))
    counts = payload["counts"]
    print("PASS=%d FAIL=%d NOT_RUN=%d CONFLICT=%d" % (
        counts.get(PASS, 0), counts.get(FAIL, 0),
        counts.get(NOT_RUN, 0), counts.get(CONFLICT, 0),
    ))
    for check in payload["checks"]:
        print("[%s] %-4s %s | %s" % (
            check["status"], check["id"], check["title"], check["detail"],
        ))
    if payload["excluded"]:
        print("排除项:")
        for item in payload["excluded"]:
            print("  - %s" % item)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="run6 第 2/3 项只读验收：机器人胜率基线 + 作祟查表框架",
    )
    parser.add_argument("--root", help="项目根目录（默认从脚本位置向上探测）")
    parser.add_argument("--game-dir", help="source/desktop/game 目录")
    parser.add_argument("--winrate", help="胜率基线 JSON 路径")
    parser.add_argument("--haunt-stats", help="查表统计 JSON 路径")
    parser.add_argument("--guardrails", help="回归护栏合并证据 JSON 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认行为）")
    parser.add_argument("--text", action="store_true", help="输出人读报告")
    parser.add_argument("--list", action="store_true", help="列出 27 条判据后退出")
    args = parser.parse_args(argv)

    if args.list:
        for check_id, title, priority, _ in CHECKS:
            print("%-5s %-3s %s" % (check_id, priority, title))
        return 0

    try:
        ctx = Ctx(
            root=args.root,
            game_dir=args.game_dir,
            winrate=args.winrate,
            haunt_stats=args.haunt_stats,
            guardrails=args.guardrails,
        )
        audit = Audit(ctx)
        audit.run()
        payload = build_payload(ctx, audit)
    except Exception as exc:  # noqa: BLE001 - 参数/环境错误必须可机读
        print(json.dumps({
            "tool": "qa/verify_winrate_haunt.py",
            "readonly": True,
            "verdict": "ERROR",
            "error": "%s: %s" % (type(exc).__name__, exc),
        }, ensure_ascii=False, indent=2))
        return 2

    if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    if args.text:
        print_text(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 3}.get(payload["verdict"], 2)


if __name__ == "__main__":
    sys.exit(main())
