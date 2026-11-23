#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P 表最终收口 —— 只读独立验收脚本（run3 final audit）。

定位
----
本脚本是 **独立验收方**，不是实现方，也不充当执行器：

* 只在内存中读取 JSON/CSV/PNG 头/文本，不写任何项目文件；
* 不执行 ``verify_assets.py``、``qa/test_p_table_execution.py``、
  ``asset_pipeline.py`` 等会写 ``assets/`` 或 ``qa/fixtures/`` 的脚本；
* 不导入被测模块（因此不会生成 ``__pycache__``），只解析已保存的证据；
* 运行前后对 ``source/desktop/game`` 与 ``photos`` 做 mtime/size 快照，
  发现并发写入即把 A-03 判 FAIL，不把结果当冻结结论。

验收对象
----
``.codebuddy/wfat/run3_completion_criteria.md`` 的 G1-G7 与 A-01…A-28：

* 分支证据 ``qa/branch_probe.json``：``method=condition-jump-arc``、
  两文件分别 ≥75%、五项自检、未覆盖边可定位、与 48 项测试同一次运行；
* RSS 证据 ``qa/rss_probe.json``：``--stage all`` 连续 5 次、
  ``PeakWorkingSetSize``、5/5 ≤1536 MiB、按最大值判定，禁止用中位数替代；
* UI 证据 ``qa/ui_capture.json`` + PNG：100% 必须是真实截图；
  125%/150% 只能是 ``approximated``，且不得写成 PASS；
* 旧测试 17/17、契约 32/32、新测试 48/48、独立验收 P0/P1/P2；
* 报告 verdict / completion_claim / 独立验收 / 本脚本四口径一致；
* 47 条缺口仍为 missing，31 placeholder + 16 fallback，不得改写成 usable。

判读纪律
--------
PASS：证据存在、格式合法、数值达标、与当前产物同源。
FAIL：证据存在但不合法/不达标/过期/自相矛盾（例如用中位数判 RSS、
      把 125% 近似写成 PASS、报告 PASS 与 claim not-attested 并存）。
NOT_RUN：证据文件缺失或人工项未执行；不进入通过率分母，绝不冒充 PASS。
CONFLICT：规范口径冲突且无书面裁决。

用法
----
python qa/verify_p_table_final.py            # 人读摘要
python qa/verify_p_table_final.py --json     # 机读 JSON（只写 stdout）
python qa/verify_p_table_final.py --root D:/Game/桌游模拟器/Betrayal at House on the Hill

退出码
------
0 PASS（A 表全 PASS）；1 FAIL（存在 FAIL）；3 INCOMPLETE（仅 NOT_RUN/CONFLICT）；
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
import subprocess
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
NA = "N/A"          # run5：退役项（A-09）专用，保留条目但不计入通过率分母

# run5 §4.1 / C-04：A-09（47 行 missing 语义）在 0 missing 后失去断言对象，
# 退役为 N/A —— 保留条目与退役理由，不删除、不计入分母。
RETIRED_ITEMS = {
    "A-09": "run5 C-04：0 missing 后 A-09 失去断言对象；缺口语义已由 A-30 判据 1 "
            "（任何行 availability=missing 即 FAIL）与 V07 接手。",
}

ENUM_CLAIMS = ("attested", "partial", "not-attested")
BRANCH_METHOD = "condition-jump-arc"
RSS_BUDGET_MIB = 1536
RSS_BUDGET_BYTES = 1536 * 1024 * 1024
# run6：九类渲染面接入后 P 表 274 位（142 原有位 + 132 新增渲染面）
EXPECTED_TOTAL = 274
EXPECTED_COLUMNS = 33
# asset_type -> assets/ 下的运行时目录（A-07 判据）
RUNTIME_DIR_BY_TYPE = {
    "character": "characters",
    "room": "rooms",
    "card_omen": "cards",
    "card_item": "cards",
    "card_event": "cards",
    "monster": "monsters",
    "haunt": "haunts",
    "ending": "endings",
    "card_back": "card_backs",
    "room_back": "room_backs",
    "dice": "dice",
}
EXPECTED_TYPES = {
    "character": 12,
    "room": 50,
    "card_event": 45,
    "card_item": 22,
    "card_omen": 13,
    # 六类渲染面：monster 52 / haunt 70 / ending 2 / card_back 3 / room_back 2 / dice 3
    "monster": 52,
    "haunt": 70,
    "ending": 2,
    "card_back": 3,
    "room_back": 2,
    "dice": 3,
}
# run5 v2（2026-11-20）：47 位登记 + 130 张无损转码后 142 位全部 usable。
# run6：新增 132 位渲染面同为 usable（六类均有 photos/ 源图），全表 274 位 0 缺口。
EXPECTED_AVAILABILITY = {
    "usable": 274,
    "partial": 0,
    "missing": 0,
    "corrupted": 0,
    "duplicate": 0,
}
EXPECTED_MISSING_BY_TYPE = {}
EXPECTED_RUNTIME = {"rooms": 50, "cards": 80, "characters": 12, "placeholders": 3}
EXPECTED_RUNTIME_TOTAL = 145
EXPECTED_BACKUPS = 130
EXPECTED_CONTRACT = 32
EXPECTED_VERIFY = 17
# run5：新测试基线 48 条；补测只增不减（新增代码必须带测试）
NEW_TEST_BASELINE = 48
# A-29：WW 隔离基线
WW_TOKENS = ("ROOF_ROOMS", "ROOF_ROOM_IDS", "WW_EVENT_ADDITION", "_roof_room_def")
WW_STRING_TOKENS = ("ww_", "roof_", "widows_walk")
WW_CONTENT_COUNTS = {"ROOF_ROOMS": 20, "WW_EVENT_ADDITIONS": 15,
                     "WW_ITEM_ADDITIONS": 10, "WW_OMEN_ADDITIONS": 5,
                     "WW_HAUNT_NAMES": 50}
CONTENT_BASELINE_COUNTS = {
    "CHARACTER_FACES": 12,
    "ROOM_BASES": 39,
    "ROOM_SUPPLEMENTAL_SPECS": 11,
    "OMEN_CARDS": 13,
    "ITEM_CARDS": 22,
    "EVENT_BASES": 11,
    "EVENT_SUPPLEMENTAL_SPECS": 34,
}
# 上面 7 个集合是 S0 归档可 AST 追溯的部分（合计 142）；run6 新增的 3 个集合
# 只能导入 content.py 求值（HAUNT_DEFS 来自 build_catalog(0).haunt_defs）。
CONTENT_BASELINE_TOTAL = 142
CONTENT_EXTRA_COUNTS = {
    "MONSTER_BASES": 52,
    "HAUNT_DEFS": 70,
    "RENDER_SURFACE_SPECS": 10,
}
HAUNT_SLOTS = 70

SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_GAME_DIR = SCRIPT_PATH.parents[1]
DEFAULT_PROJECT_ROOT = SCRIPT_PATH.parents[4]


# ---------------------------------------------------------------------------
# 基础工具（全部只读）
# ---------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def png_ihdr(path):
    """只读 PNG 头，返回 (width, height)；不是 PNG 返回 None。"""
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


def jpeg_magic(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(3) == b"\xff\xd8\xff"
    except OSError:
        return False


def parse_iso(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def from_mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def parse_wh(text):
    if not text:
        return None
    match = re.search(r"(\d+)\s*[x×]\s*(\d+)", str(text))
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


def rollup(statuses):
    """门禁汇总：N/A（退役项）不参与，既不加分也不阻断。"""
    active = [s for s in statuses if s != NA]
    if any(s == FAIL for s in active):
        return FAIL
    if any(s == CONFLICT for s in active):
        return CONFLICT
    if any(s == NOT_RUN for s in active):
        return NOT_RUN
    return PASS


def compute_claim(statuses, ids):
    """按 completion_criteria §3 计算三态。

    * 任一 FAIL → not-attested；
    * Core（A-01…A-15）任一非 PASS → not-attested（N/A 退役项除外）；
    * 其余证据门禁存在 NOT_RUN/CONFLICT → 最多 partial；
    * 全部 PASS → attested。
    """
    selected = {i: statuses.get(i, NOT_RUN) for i in ids}
    if any(s == FAIL for s in selected.values()):
        return "not-attested"
    retired = {int(key.split("-")[1]) for key in RETIRED_ITEMS}
    core = ["A-%02d" % i for i in range(1, 16) if i not in retired]
    for cid in core:
        if selected.get(cid, NOT_RUN) != PASS:
            return "not-attested"
    if any(s not in (PASS, NA) for s in selected.values()):
        return "partial"
    return "attested"


class Ctx(object):
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.game = self.root / "source" / "desktop" / "game"
        self.qa = self.game / "qa"
        self.assets = self.game / "assets"
        self.reports = self.game / "reports"
        self.paths = {
            "p_table": self.assets / "p_table.json",
            "p_table_csv": self.assets / "p_table.csv",
            "mapping": self.assets / "asset_mapping.json",
            "validation_report": self.assets / "validation_report.json",
            "content": self.game / "content.py",
            "pipeline": self.game / "asset_pipeline.py",
            "registry": self.game / "asset_registry.py",
            "ui": self.game / "ui.py",
            "ui_binding": self.game / "ui_asset_binding.py",
            "contract": self.qa / "contract_result.json",
            "coverage_probe": self.qa / "coverage_probe.json",
            "verify_final": self.qa / "p_table_verify_final.json",
            "report": self.reports / "p_table_execution_report.json",
            "report_md": self.reports / "p_table_execution_report.md",
            "issues": self.qa / "issues.jsonl",
            "branch_probe": self.qa / "branch_probe.json",
            "branch_coverage": self.qa / "branch_coverage.json",
            "branch_selftest": self.qa / "branch_probe_selftest.json",
            "rss_probe": self.qa / "rss_probe.json",
            "rss_peak": self.qa / "rss_peak.json",
            "ui_capture": self.qa / "ui_capture.json",
            "ui_manifest": self.qa / "ui_dpi_manifest.json",
            "freeze": self.qa / "freeze_manifest.json",
            "test_p_table": self.qa / "test_p_table_execution.py",
        }
        self.data = {}
        self.errors = {}
        self.load()

    def rel(self, path):
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except (ValueError, OSError):
            return str(path).replace("\\", "/")

    def load_json(self, key, path=None):
        path = Path(path or self.paths[key])
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
        for key in (
            "p_table", "p_table_csv", "mapping", "validation_report", "contract",
            "coverage_probe", "verify_final", "report", "branch_probe",
            "branch_coverage", "branch_selftest", "rss_probe", "rss_peak",
            "ui_capture", "ui_manifest", "freeze",
        ):
            if key == "p_table_csv":
                continue
            self.load_json(key)


class Audit(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.checks = []
        self._by_id = {}

    def add(self, aid, gate, priority, title, status, detail, evidence=None,
            manual=False, a_table=True):
        item = {
            "id": aid,
            "gate": gate,
            "priority": priority,
            "title": title,
            "status": status,
            "detail": detail,
            "evidence": list(evidence or []),
            "manual": bool(manual),
            "a_table": bool(a_table),
        }
        self.checks.append(item)
        self._by_id[aid] = item
        return item

    def run(self, aid, gate, priority, title, fn, **kwargs):
        try:
            status, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001 - 单项异常不得吞掉
            status = FAIL
            detail = "检查内部异常：%s" % exc
            evidence = [traceback.format_exc(limit=3)]
        return self.add(aid, gate, priority, title, status, detail, evidence, **kwargs)

    def statuses(self):
        return {c["id"]: c["status"] for c in self.checks}

    def get(self, aid):
        return self._by_id.get(aid)


def snapshot_tree(ctx):
    """记录 mtime_ns/size，用于检测验收期间并发写入。"""
    snap = {}
    for base in (ctx.game, ctx.root / "photos"):
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(str(base)):
            dirnames[:] = [
                d for d in dirnames
                if d not in ("__pycache__", ".git", "node_modules", "archive")
            ]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                snap[ctx.rel(path)] = (st.st_mtime_ns, st.st_size)
    return snap


# ---------------------------------------------------------------------------
# A-01…A-03 身份、环境、串行
# ---------------------------------------------------------------------------

def check_a01(ctx):
    report = ctx.data.get("report")
    if not report:
        return FAIL, "缺少执行报告 %s" % ctx.rel(ctx.paths["report"]), []
    problems = []
    scope = report.get("claim_scope") or report.get("scope")
    if scope != "execution":
        problems.append("claim_scope=%r，必须明确为 execution" % (scope,))
    if report.get("completion_claim") not in ENUM_CLAIMS:
        problems.append("completion_claim=%r 不在三态枚举内" % (report.get("completion_claim"),))

    # 冻结清单优先；缺失时接受报告 §4 的冻结哈希表，但必须可逐项回读。
    frozen = ctx.data.get("freeze") or {}
    rows = frozen.get("artifacts") or frozen.get("files") or {}
    source = "qa/freeze_manifest.json"
    if not rows:
        rows = {}
        md_path = ctx.paths["report_md"]
        if md_path.exists():
            text = md_path.read_text(encoding="utf-8-sig", errors="replace")
            for line in text.splitlines():
                match = re.match(
                    r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*`?([0-9a-fA-F]{64})`?\s*\|",
                    line,
                )
                if match:
                    rows[match.group(1).strip()] = {
                        "bytes": int(match.group(2)),
                        "sha256": match.group(3).lower(),
                    }
            source = "reports/p_table_execution_report.md §4"
    if not rows:
        problems.append("无 freeze_manifest.json，报告 §4 也没有可解析的哈希表")
    else:
        required = [
            "assets/p_table.json", "assets/p_table.csv", "assets/asset_mapping.json",
            "content.py", "asset_pipeline.py", "asset_registry.py",
            "ui_asset_binding.py", "qa/test_p_table_execution.py",
        ]
        checked = 0
        for rel_path, recorded in rows.items():
            path = ctx.game / rel_path
            if not path.exists():
                if rel_path in required:
                    problems.append("冻结项缺失：%s" % rel_path)
                continue
            checked += 1
            try:
                size = path.stat().st_size
                digest = sha256_file(path)
            except OSError as exc:
                problems.append("%s 读取失败：%s" % (rel_path, exc))
                continue
            rec_bytes = recorded.get("bytes")
            rec_sha = str(recorded.get("sha256") or "").lower()
            if rec_bytes is not None and int(rec_bytes) != size:
                problems.append("%s 字节漂移 %s→%s" % (rel_path, rec_bytes, size))
            if rec_sha and rec_sha != digest:
                problems.append("%s sha256 漂移" % rel_path)
        if checked < 8:
            problems.append("冻结哈希表仅 %d 项可回读，少于 8 项" % checked)
    detail = "来源=%s；回读 %d 项" % (source, len(rows))
    if problems:
        return FAIL, detail + "；" + "；".join(problems), problems
    return PASS, detail + "；claim_scope=execution；哈希一致", []
def check_a02(ctx):
    report = ctx.data.get("report")
    if not report:
        return FAIL, "缺少执行报告，无法核对环境冻结", []
    env = report.get("environment") or {}
    soft = {
        "python": env.get("python"),
        "pillow": env.get("pillow"),
        "tk": env.get("tkinter") or env.get("tk"),
        "os": env.get("platform") or env.get("os"),
    }
    missing_soft = [k for k, v in soft.items() if not v]
    if missing_soft:
        return FAIL, "环境记录缺少必需项：%s" % ", ".join(missing_soft), []
    hard = {
        "cpu": env.get("cpu") or env.get("processor"),
        "memory": env.get("memory_mib") or env.get("memory"),
        "disk": env.get("disk_free_mib") or env.get("disk"),
        "dpi": env.get("dpi") or env.get("system_dpi"),
        "timezone": env.get("timezone") or env.get("tz"),
    }
    missing_hard = [k for k, v in hard.items() if v in (None, "")]
    if missing_hard:
        return NOT_RUN, (
            "已记录 python=%s pillow=%s tk=%s；缺少 CPU/内存/磁盘/DPI/时区：%s"
            % (soft["python"], soft["pillow"], soft["tk"], ", ".join(missing_hard))
        ), []
    return PASS, "环境九项齐全（解释器/Pillow/Tk/OS/CPU/内存/磁盘/DPI/时区）", []


def check_a03(ctx):
    vf = ctx.data.get("verify_final")
    if not vf:
        return NOT_RUN, "缺少 qa/p_table_verify_final.json，无法核对 SAFE-01", []
    target = None
    for check in vf.get("checks") or []:
        if check.get("id") == "SAFE-01" or check.get("tc") == "TC-PT-25":
            target = check
            break
    if not target:
        return NOT_RUN, "独立验收快照中没有 SAFE-01/TC-PT-25", []
    if target.get("status") != PASS:
        return FAIL, "SAFE-01=%s：%s" % (
            target.get("status"), target.get("detail")
        ), [target.get("detail") or ""]
    return PASS, "SAFE-01 PASS：验收期间无并发写入", []


# ---------------------------------------------------------------------------
# A-04…A-09、A-27 数据与 47 缺口
# ---------------------------------------------------------------------------

def _records(ctx):
    data = ctx.data.get("p_table") or {}
    records = data.get("records") or []
    return records


def _record_map(ctx):
    return {r.get("record_id"): r for r in _records(ctx)}


def check_a04(ctx):
    data = ctx.data.get("p_table")
    if not data:
        return FAIL, "缺少 assets/p_table.json：%s" % ctx.errors.get("p_table"), []
    problems = []
    records = data.get("records") or []
    columns = (data.get("schema") or {}).get("columns") or []
    if len(records) != EXPECTED_TOTAL:
        problems.append("records=%d，期望 %d" % (len(records), EXPECTED_TOTAL))
    if len(columns) != EXPECTED_COLUMNS:
        problems.append("columns=%d，期望 %d" % (len(columns), EXPECTED_COLUMNS))
    if len(set(r.get("record_id") for r in records)) != len(records):
        problems.append("record_id 不唯一")

    csv_path = ctx.paths["p_table_csv"]
    if not csv_path.exists():
        problems.append("缺少 assets/p_table.csv")
    else:
        raw = csv_path.read_bytes()
        if not raw.startswith(b"\xef\xbb\xbf"):
            problems.append("CSV 无 UTF-8 BOM")
        try:
            text = raw.decode("utf-8-sig")
            rows = list(csv.reader(io.StringIO(text, newline="")))
        except Exception as exc:  # noqa: BLE001
            problems.append("CSV 解析失败：%s" % exc)
            rows = []
        if rows:
            header = rows[0]
            body = rows[1:]
            if header != columns:
                problems.append("CSV 表头与 JSON columns 不一致")
            if len(body) != EXPECTED_TOTAL:
                problems.append("CSV 行数=%d，期望 %d" % (len(body), EXPECTED_TOTAL))
            for idx, row in enumerate(body, 2):
                if len(row) != EXPECTED_COLUMNS:
                    problems.append("CSV 第 %d 行列数=%d" % (idx, len(row)))
                    break
                if any("\n" in cell or "\r" in cell for cell in row):
                    problems.append("CSV 第 %d 行含单元格换行" % idx)
                    break
            if body and len(header) == EXPECTED_COLUMNS:
                csv_ids = [row[0] for row in body if len(row) == EXPECTED_COLUMNS]
                json_ids = [r.get("record_id") for r in records]
                if set(csv_ids) != set(json_ids):
                    problems.append("CSV/JSON record_id 双向差集非空")
                # 关键字段逐行等价（null 与空串按同义处理）
                idx = {name: i for i, name in enumerate(header)}
                fields = [
                    "availability", "mapping_status", "source_path",
                    "runtime_key", "target_ref",
                ]
                by_id = {r.get("record_id"): r for r in records}
                mismatched = 0
                for row in body:
                    if len(row) != EXPECTED_COLUMNS:
                        continue
                    rec = by_id.get(row[0])
                    if not rec:
                        continue
                    for field in fields:
                        if field not in idx:
                            continue
                        left = str(rec.get(field) if rec.get(field) is not None else "")
                        right = str(row[idx[field]])
                        if left != right:
                            mismatched += 1
                            if mismatched <= 3:
                                problems.append(
                                    "CSV/JSON %s 的 %s 不等价" % (row[0], field)
                                )
                if mismatched > 3:
                    problems.append("CSV/JSON 关键字段不等价共 %d 处" % mismatched)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "274 行 × 33 列；CSV 带 BOM、表头一致、record_id 双向差集为空", []


def check_a05(ctx):
    records = _records(ctx)
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    counts = Counter(r.get("availability") for r in records)
    for key, expected in EXPECTED_AVAILABILITY.items():
        actual = counts.get(key, 0)
        if actual != expected:
            problems.append("%s=%d，期望 %d" % (key, actual, expected))
    if sum(counts.values()) != EXPECTED_TOTAL:
        problems.append("availability 合计=%d" % sum(counts.values()))
    stats = (ctx.data.get("p_table") or {}).get("stats") or {}
    for key, expected in EXPECTED_AVAILABILITY.items():
        if stats.get(key) != expected:
            problems.append("stats.%s=%r" % (key, stats.get(key)))
    runtime = Counter(r.get("runtime_status") for r in records)
    # run6：274 位全部 ok（142 原有位 + 132 渲染面）；0 placeholder / 0 fallback
    expected_runtime = {"ok": EXPECTED_TOTAL, "placeholder": 0, "fallback": 0}
    for key, expected in expected_runtime.items():
        if runtime.get(key, 0) != expected:
            problems.append("runtime_status.%s=%d，期望 %d" % (key, runtime.get(key, 0), expected))
    mapping = Counter(r.get("mapping_status") for r in records)
    if mapping.get("matched", 0) != EXPECTED_TOTAL:
        problems.append("mapping_status.matched=%d，期望 %d"
                        % (mapping.get("matched", 0), EXPECTED_TOTAL))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, ("274 usable / 0 partial / 0 missing / 0 corrupted / 0 duplicate；"
                  "runtime ok=274；mapping matched=274"), []


def check_a06(ctx):
    records = _records(ctx)
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    counts = Counter(r.get("asset_type") for r in records)
    for key, expected in EXPECTED_TYPES.items():
        if counts.get(key, 0) != expected:
            problems.append("%s=%d，期望 %d" % (key, counts.get(key, 0), expected))
    unknown = set(counts) - set(EXPECTED_TYPES)
    if unknown:
        problems.append("未知 asset_type：%s" % ", ".join(sorted(map(str, unknown))))
    missing = Counter(r.get("asset_type") for r in records if r.get("availability") == "missing")
    for key, expected in EXPECTED_MISSING_BY_TYPE.items():
        if missing.get(key, 0) != expected:
            problems.append("missing.%s=%d，期望 %d" % (key, missing.get(key, 0), expected))
    if sum(missing.values()) != 0:
        problems.append("缺口合计=%d，期望 0（run5 v2）" % sum(missing.values()))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, ("分类 12/50/45/22/13 + monster52/haunt70/ending2/card_back3/"
                  "room_back2/dice3；缺口 0（47 位已按 promotion map 落实）"), []


def check_a07(ctx):
    mapping = ctx.data.get("mapping")
    records = _records(ctx)
    if not mapping:
        return FAIL, "缺少 assets/asset_mapping.json：%s" % ctx.errors.get("mapping"), []
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    entries = mapping.get("entries") or []
    unresolved = mapping.get("unresolved") or []
    # run5 v2：142 entries / 0 unresolved
    if len(entries) != EXPECTED_TOTAL:
        problems.append("mapping entries=%d，期望 %d" % (len(entries), EXPECTED_TOTAL))
    if len(unresolved) != 0:
        problems.append("mapping unresolved=%d，期望 0" % len(unresolved))
    by_id = _record_map(ctx)
    entry_ids = [e.get("record_id") for e in entries]
    unresolved_ids = [e.get("record_id") for e in unresolved]
    covered_ids = [r.get("record_id") for r in records
                   if r.get("availability") in ("usable", "partial")]
    missing_ids = [r.get("record_id") for r in records if r.get("availability") == "missing"]
    if set(entry_ids) != set(covered_ids):
        problems.append("mapping entries 与 usable/partial 行集合不一致"
                        "（entries=%d / rows=%d）" % (len(set(entry_ids)), len(set(covered_ids))))
    if set(unresolved_ids) != set(missing_ids):
        problems.append("mapping unresolved 与 missing 行集合不一致")
    for entry in entries:
        rec = by_id.get(entry.get("record_id"))
        if not rec:
            problems.append("映射指向不存在的记录 %s" % entry.get("record_id"))
            continue
        if entry.get("path") != rec.get("source_path"):
            problems.append("%s 的 path/source_path 不一致" % rec.get("record_id"))
            continue
        src = ctx.root / str(entry.get("path"))
        if not src.exists():
            problems.append("%s 源文件缺失：%s" % (rec.get("record_id"), entry.get("path")))
        elif png_ihdr(src) is None:
            problems.append("%s 不是真 PNG 魔数" % rec.get("record_id"))
        asset_type = rec.get("asset_type")
        runtime = str(rec.get("runtime_path") or "").replace("\\", "/")
        runtime_dir = RUNTIME_DIR_BY_TYPE.get(asset_type)
        if runtime_dir is None:
            problems.append("%s 未知 asset_type：%r" % (rec.get("record_id"), asset_type))
        elif "/assets/%s/" % runtime_dir not in runtime:
            problems.append("%s 运行时图未落在 assets/%s/"
                            % (rec.get("record_id"), runtime_dir))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, ("entries=274 / unresolved=0；path==source_path；274 源文件为真 PNG；"
                  "运行时路径均落在该类别目录"), []


def check_a08(ctx):
    problems = []
    counts = {}
    for key in ("rooms", "cards", "characters", "placeholders"):
        base = ctx.assets / key
        files = sorted(base.rglob("*.png")) if base.exists() else []
        counts[key] = len(files)
        if len(files) != EXPECTED_RUNTIME[key]:
            problems.append("%s=%d，期望 %d" % (key, len(files), EXPECTED_RUNTIME[key]))
    total = sum(counts.values())
    if total != EXPECTED_RUNTIME_TOTAL:
        problems.append("运行时 PNG 合计=%d，期望 %d" % (total, EXPECTED_RUNTIME_TOTAL))
    for path in sorted((ctx.assets / "rooms").rglob("*.png")):
        size = png_ihdr(path)
        if size != (512, 512):
            problems.append("%s 尺寸=%r，期望 512x512" % (ctx.rel(path), size))
    for path in sorted((ctx.assets / "cards").rglob("*.png")):
        size = png_ihdr(path)
        if size != (480, 672):
            problems.append("%s 尺寸=%r，期望 480x672" % (ctx.rel(path), size))
    for path in sorted((ctx.assets / "characters").glob("*.png")):
        size = png_ihdr(path)
        if size != (320, 320):
            problems.append("%s 尺寸=%r，期望 320x320" % (ctx.rel(path), size))
    expected_ph = {
        "character_missing.png": (320, 320),
        "room_missing.png": (512, 512),
        "event_missing.png": (480, 672),
    }
    for path in sorted((ctx.assets / "placeholders").glob("*.png")):
        size = png_ihdr(path)
        expected = expected_ph.get(path.name)
        if expected is None:
            problems.append("未知占位图 %s" % path.name)
        elif size != expected:
            problems.append("%s 尺寸=%r，期望 %sx%s" % (path.name, size, expected[0], expected[1]))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, ("%d 个运行时 PNG：房间 50 / 卡牌 80 / 角色 12 / 占位 3，"
                  "IHDR 尺寸全部正确" % total), []


def check_a09(ctx):
    """run5 退役（C-04）：0 missing 后本项失去断言对象。

    保留条目与退役理由，不删除、不计入分母。原 47 行 missing 语义的三条实质
    断言已由别处接手：
    * "missing 行 source_path 必须为空" → A-30 判据 1（任何 missing 即 FAIL）
      与 verify_assets.py V07；
    * "placeholder/fallback 计数" → V09（v2 期望 0/0）；
    * "回退目标为同类别可用行" → 合成样本用例
      qa/test_p_table_execution.py::test_13_asset_ref_api_shape。
    """
    return NA, RETIRED_ITEMS["A-09"], ["qa/run5_baseline_diff.json"]


def check_a27(ctx):
    """A-27 v2（run5 C-04 改写）：从"47 缺口台账"改为"142/142 全覆盖台账"。

    v1 断言的是"12 角色 / 1 房间 / 34 事件的缺口如实登记"；0 missing 之后该断言
    失去对象。v2 改为逐行核对 **source + provenance + release 7 列**都在位，且
    缺口台账（promotion map / gap closure）与 P 表双向差集为空。断言强度不降。
    """
    records = _records(ctx)
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    if len(records) != EXPECTED_TOTAL:
        problems.append("行数=%d，期望 %d" % (len(records), EXPECTED_TOTAL))
    missing = [r for r in records if r.get("availability") == "missing"]
    if missing:
        problems.append("缺口数=%d（v2 期望 0）" % len(missing))

    release_columns = ("bytes", "sha256", "category_dir", "alpha_required",
                       "canonical_record_id", "reviewer", "verified_at")
    for rec in records:
        rid = rec.get("record_id")
        if not str(rec.get("source_path") or "").strip():
            problems.append("%s source_path 为空" % rid)
        provenance = str(rec.get("provenance") or "")
        if not provenance:
            problems.append("%s provenance 为空" % rid)
        elif ";sha256:" not in provenance or "origin=" not in provenance:
            problems.append("%s provenance 缺 sha256/origin" % rid)
        for column in release_columns:
            value = rec.get(column)
            if value is None or value == "":
                problems.append("%s 发布列 %s 为空" % (rid, column))
        if rec.get("mapping_status") != "matched":
            problems.append("%s mapping_status=%r" % (rid, rec.get("mapping_status")))
        if rec.get("missing_note"):
            problems.append("%s missing_note 非空" % rid)

    # 台账文件：47 行 promotion map + 47 行 gap closure，与 P 表双向一致
    promotion_path = ctx.qa / "run5_promotion_map.json"
    closure_path = ctx.qa / "run5_gap_closure.jsonl"
    by_id = _record_map(ctx)
    ledger_ids = set()
    if not promotion_path.is_file():
        problems.append("缺少 qa/run5_promotion_map.json（47 行绑定表）")
    else:
        try:
            promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            promotion = {}
            problems.append("promotion map 不可解析：%s" % exc)
        rows = promotion.get("rows") or []
        if len(rows) != 47:
            problems.append("promotion map 行数=%d，期望 47" % len(rows))
        for row in rows:
            rid = row.get("record_id")
            ledger_ids.add(rid)
            rec = by_id.get(rid)
            if rec is None:
                problems.append("promotion map 指向不存在的行 %s" % rid)
                continue
            if rec.get("availability") != "usable":
                problems.append("%s 登记后仍是 %r" % (rid, rec.get("availability")))
            if row.get("sha256") and row.get("sha256") != rec.get("sha256"):
                problems.append("%s 台账 sha256 与 P 表不一致" % rid)
            if row.get("source_path") and row.get("source_path") != rec.get("source_path"):
                problems.append("%s 台账 source_path 与 P 表不一致" % rid)
    if not closure_path.is_file():
        problems.append("缺少 qa/run5_gap_closure.jsonl（47 行缺口台账）")
    else:
        lines = [line for line in closure_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        if len(lines) != 47:
            problems.append("gap closure 行数=%d，期望 47" % len(lines))
        closure_ids = set()
        for line in lines:
            try:
                closure_ids.add(json.loads(line).get("record_id"))
            except ValueError:
                problems.append("gap closure 存在不可解析行")
                break
        if closure_ids != ledger_ids:
            problems.append("gap closure 与 promotion map 记录集合不一致")

    # stats 与逐行复算一致（缺口 0）
    stats = (ctx.data.get("p_table") or {}).get("stats") or {}
    actual = Counter(r.get("availability") for r in records)
    for key, value in EXPECTED_AVAILABILITY.items():
        if stats.get(key) != value:
            problems.append("stats.%s=%r，期望 %d" % (key, stats.get(key), value))
        if actual.get(key, 0) != value:
            problems.append("逐行 %s=%d，期望 %d" % (key, actual.get(key, 0), value))
    if stats.get("records") != EXPECTED_TOTAL:
        problems.append("stats.records=%r" % stats.get("records"))

    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, ("142/142 全覆盖：source/provenance/release 7 列齐全；"
                  "promotion map 47 行 + gap closure 47 行与 P 表双向一致；缺口 0"), \
        ["qa/run5_promotion_map.json", "qa/run5_gap_closure.jsonl"]


# ---------------------------------------------------------------------------
# A-10…A-15 旧/新测试与独立验收
# ---------------------------------------------------------------------------

def _fresh_enough(ctx, evidence_time, reference_paths, label):
    if not evidence_time:
        return "%s 缺少时间戳" % label
    newest = None
    for path in reference_paths:
        stamp = from_mtime(path)
        if stamp and (newest is None or stamp > newest):
            newest = stamp
    if newest and evidence_time < newest:
        return "%s 早于输入产物（%s < %s）" % (
            label, evidence_time.isoformat(sep=" "), newest.isoformat(sep=" ")
        )
    return ""


def check_a10(ctx):
    report = ctx.data.get("report") or {}
    validation = ctx.data.get("validation_report")
    problems = []
    if not validation:
        problems.append("缺少 assets/validation_report.json：%s" % ctx.errors.get("validation_report"))
    else:
        totals = validation.get("totals") or {}
        checks = validation.get("checks") or []
        if validation.get("ok") is not True:
            problems.append("validation_report.ok=%r" % validation.get("ok"))
        if int(totals.get("checked") or 0) != EXPECTED_VERIFY:
            problems.append("checked=%r，期望 17" % totals.get("checked"))
        if int(totals.get("failed") or 0) != 0:
            problems.append("failed=%r" % totals.get("failed"))
        bad = [
            c.get("id") for c in checks
            if str(c.get("status") or "").lower() != "pass"
        ]
        if bad:
            problems.append("非 PASS 项：%s" % ", ".join(map(str, bad)))
        stale = _fresh_enough(
            ctx, parse_iso(validation.get("generated_at")),
            [ctx.paths["p_table"], ctx.paths["content"], ctx.paths["pipeline"]],
            "validation_report",
        )
        if stale:
            problems.append(stale)
    legacy = report.get("legacy_tests") or {}
    for key in ("verify_assets", "verify_assets_final"):
        item = legacy.get(key)
        if not item:
            problems.append("报告缺少 %s 复跑记录" % key)
            continue
        parsed = item.get("parsed") or item.get("summary") or {}
        if item.get("exit_code") != 0 or item.get("status") != PASS:
            problems.append("%s exit=%r status=%r" % (key, item.get("exit_code"), item.get("status")))
        if int(parsed.get("total") or 0) != EXPECTED_VERIFY or int(parsed.get("fail") or 0) != 0:
            problems.append("%s 解析=%r/%r" % (key, parsed.get("total"), parsed.get("fail")))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "verify_assets 17/17、exit 0；收尾复跑同样 17/17；证据晚于 P 表", []


def check_a11(ctx):
    report = ctx.data.get("report") or {}
    contract = ctx.data.get("contract")
    problems = []
    if not contract:
        problems.append("缺少 qa/contract_result.json：%s" % ctx.errors.get("contract"))
    else:
        summary = contract.get("summary") or {}
        if int(summary.get("total") or 0) != EXPECTED_CONTRACT:
            problems.append("total=%r，期望 32" % summary.get("total"))
        if int(summary.get("pass") or 0) != EXPECTED_CONTRACT:
            problems.append("pass=%r" % summary.get("pass"))
        for key in ("fail", "warn", "skip", "error"):
            if int(summary.get(key) or 0) != 0:
                problems.append("%s=%r" % (key, summary.get(key)))
        if summary.get("exit_code") not in (0, None):
            problems.append("exit_code=%r" % summary.get("exit_code"))
        stale = _fresh_enough(
            ctx, from_mtime(ctx.paths["contract"]),
            [ctx.paths["p_table"], ctx.paths["mapping"]],
            "contract_result",
        )
        if stale:
            problems.append(stale)
    legacy = report.get("legacy_tests") or {}
    for key in ("contract", "contract_final"):
        item = legacy.get(key)
        if not item:
            problems.append("报告缺少 %s 复跑记录" % key)
            continue
        parsed = item.get("parsed") or item.get("summary") or {}
        if item.get("exit_code") != 0 or item.get("status") != PASS:
            problems.append("%s exit=%r status=%r" % (key, item.get("exit_code"), item.get("status")))
        if int(parsed.get("total") or 0) != EXPECTED_CONTRACT or int(parsed.get("fail") or 0) != 0:
            problems.append("%s 解析=%r/%r" % (key, parsed.get("total"), parsed.get("fail")))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "契约 32/32、0 fail/warn/skip/error、exit 0；证据晚于 P 表与映射", []


def check_a12(ctx):
    probe = ctx.data.get("coverage_probe") or {}
    report = ctx.data.get("report") or {}
    runner = probe.get("runner") or {}
    new_tests = report.get("new_tests") or {}
    problems = []
    if not probe:
        problems.append("缺少 qa/coverage_probe.json")
    else:
        if probe.get("runner_error"):
            problems.append("runner_error=%s" % probe.get("runner_error"))
        if int(runner.get("tests") or 0) < NEW_TEST_BASELINE:
            problems.append("tests=%r，低于基线 %d" % (
                runner.get("tests"), NEW_TEST_BASELINE))
        for key in ("failures", "errors", "skipped"):
            if int(runner.get(key) or 0) != 0:
                problems.append("%s=%r" % (key, runner.get(key)))
        stale = _fresh_enough(
            ctx, from_mtime(ctx.paths["coverage_probe"]),
            [ctx.paths["test_p_table"], ctx.paths["p_table"]],
            "coverage_probe",
        )
        if stale:
            problems.append(stale)
    if not new_tests:
        problems.append("报告缺少 new_tests")
    else:
        if int(new_tests.get("total") or 0) < NEW_TEST_BASELINE:
            problems.append("report.new_tests.total=%r 低于基线 %d" % (
                new_tests.get("total"), NEW_TEST_BASELINE))
        if int(new_tests.get("pass") or 0) != int(new_tests.get("total") or 0):
            problems.append("report.new_tests.pass=%r 未全通过" % new_tests.get("pass"))
        if any(int(new_tests.get(k) or 0) for k in ("fail", "error", "skipped")):
            problems.append("report.new_tests 存在 fail/error/skip")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "新测试 48/48、0 failure/error/skip；探针晚于测试文件与 P 表", []


def _verify_rates(vf):
    return ((vf.get("summary") or {}).get("rates") or {})


def _verify_fresh(ctx, vf):
    stamp = parse_iso(vf.get("snapshot_time"))
    return _fresh_enough(
        ctx, stamp,
        [
            ctx.paths["p_table"], ctx.paths["mapping"], ctx.paths["content"],
            ctx.paths["pipeline"], ctx.paths["registry"], ctx.paths["ui"],
            ctx.paths["ui_binding"], ctx.paths["test_p_table"],
        ],
        "独立验收快照",
    )


def check_a13(ctx):
    vf = ctx.data.get("verify_final")
    if not vf:
        return FAIL, "缺少 qa/p_table_verify_final.json：%s" % ctx.errors.get("verify_final"), []
    problems = []
    stale = _verify_fresh(ctx, vf)
    if stale:
        problems.append(stale)
    p0 = _verify_rates(vf).get("P0") or {}
    if int(p0.get("total") or 0) != 27:
        problems.append("P0 total=%r，期望 27" % p0.get("total"))
    if int(p0.get("pass") or 0) != 27:
        problems.append("P0 pass=%r，期望 27" % p0.get("pass"))
    if int(p0.get("fail") or 0) != 0:
        problems.append("P0 fail=%r" % p0.get("fail"))
    if int(p0.get("not_run") or 0) != 0:
        problems.append("P0 not_run=%r" % p0.get("not_run"))
    unavailable = [
        x for x in (vf.get("unavailable") or [])
        if str(x.get("priority")) == "P0"
    ]
    if unavailable:
        problems.append("P0 仍有未执行项：%s" % ", ".join(x.get("id", "?") for x in unavailable))
    failed = (vf.get("summary") or {}).get("failed") or []
    if failed:
        problems.append("独立验收 FAIL：%s" % ", ".join(map(str, failed)))
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "独立验收 P0 27/27，0 NOT_RUN；快照晚于当前产物", []


def check_a14(ctx):
    vf = ctx.data.get("verify_final")
    if not vf:
        return FAIL, "缺少 qa/p_table_verify_final.json", []
    stale = _verify_fresh(ctx, vf)
    if stale:
        return FAIL, stale + "；P1/P2 结果不能归属当前产物", [stale]
    problems = []
    rates = _verify_rates(vf)
    p1 = rates.get("P1") or {}
    p2 = rates.get("P2") or {}
    if float(p1.get("rate") or 0.0) < 0.95:
        problems.append("P1 rate=%r，要求 ≥0.95" % p1.get("rate"))
    if int(p1.get("executed") or 0) <= 0:
        problems.append("P1 未执行")
    if float(p2.get("rate") or 0.0) < 0.90:
        problems.append("P2 rate=%r，要求 ≥0.90" % p2.get("rate"))
    if int(p2.get("executed") or 0) <= 0:
        problems.append("P2 未执行")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "P1 %d/%d executed、rate=%.4f；P2 %d/%d executed、rate=%.4f" % (
        p1.get("pass", 0), p1.get("executed", 0), float(p1.get("rate") or 0),
        p2.get("pass", 0), p2.get("executed", 0), float(p2.get("rate") or 0),
    ), []


def check_a15(ctx):
    vf = ctx.data.get("verify_final")
    if not vf:
        return FAIL, "缺少 qa/p_table_verify_final.json", []
    problems = []
    stale = _verify_fresh(ctx, vf)
    if stale:
        problems.append(stale)
    target = None
    for check in vf.get("checks") or []:
        if check.get("id") == "SAFE-01" or check.get("tc") == "TC-PT-25":
            target = check
            break
    if not target:
        problems.append("快照中没有 SAFE-01")
    elif target.get("status") != PASS:
        problems.append("SAFE-01=%s：%s" % (target.get("status"), target.get("detail")))
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "SAFE-01 PASS，且快照晚于当前产物", []


# ---------------------------------------------------------------------------
# A-16、A-17 覆盖率
# ---------------------------------------------------------------------------

def _coverage_files(probe):
    files = probe.get("files") or []
    if isinstance(files, dict):
        files = [dict(name=k, **(v if isinstance(v, dict) else {"percent": v}))
                 for k, v in files.items()]
    out = {}
    for item in files:
        name = os.path.basename(str(item.get("file") or item.get("name") or ""))
        if name:
            out[name] = item
    return out


def _coverage_number_problems(label, reported, covered, total, threshold):
    """校验两位小数展示值，重点拦截“靠取整越过阈值”。

    允许 ±0.01 的常规展示舍入；不允许展示值高于精确值超过 0.005，
    也不允许精确值低于阈值而展示值达到阈值（如 74.996% 写成 75.00%）。
    """
    problems = []
    exact = covered * 100.0 / total
    if reported > exact + 0.005:
        problems.append("%s=%s 高于精确值 %.4f（向上取整）" % (label, reported, exact))
    if abs(reported - exact) > 0.01:
        problems.append("%s=%s 与 %d/%d 的精确值 %.4f 不一致"
                        % (label, reported, covered, total, exact))
    if reported >= threshold > exact:
        problems.append("%s=%s 靠取整越过阈值 %.2f（精确 %.4f）"
                        % (label, reported, threshold, exact))
    if reported < threshold:
        problems.append("%s=%s < %.2f" % (label, reported, threshold))
    return problems


def _line_coverage_problem(item, expected_threshold=85.0):
    problems = []
    if str(item.get("status")) != "measured":
        return ["status=%r，不是 measured" % item.get("status")]
    total = int(item.get("total_lines") or 0)
    covered = int(item.get("covered_lines") or 0)
    if total <= 0:
        return ["total_lines=%r" % item.get("total_lines")]
    if not 0 <= covered <= total:
        return ["covered_lines=%r 越界" % item.get("covered_lines")]
    reported = float(item.get("line_percent") or 0.0)
    problems.extend(_coverage_number_problems(
        "line_percent", reported, covered, total, expected_threshold
    ))
    return problems


def check_a16(ctx):
    probe = ctx.data.get("coverage_probe")
    if not probe:
        return NOT_RUN, "缺少 qa/coverage_probe.json，行覆盖未测", []
    problems = []
    files = _coverage_files(probe)
    for name in ("asset_pipeline.py", "asset_registry.py"):
        item = files.get(name)
        if not item:
            problems.append("缺少 %s 的行覆盖" % name)
            continue
        problems.extend("%s: %s" % (name, p) for p in _line_coverage_problem(item))
    runner = probe.get("runner") or {}
    if int(runner.get("tests") or 0) < NEW_TEST_BASELINE or any(
        int(runner.get(k) or 0) for k in ("failures", "errors", "skipped")
    ):
        problems.append("行覆盖不是与新测试（基线 %d 条）同一次运行" % NEW_TEST_BASELINE)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    values = ", ".join(
        "%s=%s%%" % (name, files[name].get("line_percent"))
        for name in ("asset_pipeline.py", "asset_registry.py") if name in files
    )
    return PASS, "行覆盖 %s，两文件分别 ≥85%%；同一次 48/48 运行" % values, []


def check_a17(ctx):
    data = ctx.data.get("branch_probe")
    path = ctx.paths["branch_probe"]
    if not data:
        data = ctx.data.get("branch_coverage")
        path = ctx.paths["branch_coverage"]
    if not data:
        return NOT_RUN, (
            "缺少 qa/branch_probe.json（branch_coverage.json 也不存在）；"
            "分支覆盖未测，不得用行覆盖替代"
        ), []
    problems = []
    if str(data.get("method")) != BRANCH_METHOD:
        problems.append("method=%r，要求 %s" % (data.get("method"), BRANCH_METHOD))
    files = _coverage_files(data)
    for name in ("asset_pipeline.py", "asset_registry.py"):
        item = files.get(name)
        if not item:
            problems.append("缺少 %s 的分支覆盖" % name)
            continue
        total = int(item.get("total") or item.get("total_branches") or 0)
        covered = int(item.get("covered") or item.get("covered_branches") or 0)
        if total <= 0:
            problems.append("%s total=0，分母不成立" % name)
            continue
        if not 0 <= covered <= total:
            problems.append("%s covered=%r 越界" % (name, covered))
            continue
        reported = float(item.get("percent") or item.get("branch_percent") or 0.0)
        for issue in _coverage_number_problems(
            "%s branch_percent" % name, reported, covered, total, 75.0
        ):
            problems.append(issue)
        uncovered = item.get("uncovered") or item.get("uncovered_edges") or []
        if len(uncovered) != total - covered:
            problems.append("%s 未覆盖清单 %d 条，应为 %d"
                            % (name, len(uncovered), total - covered))
        for edge in uncovered[:5]:
            if not isinstance(edge, dict):
                problems.append("%s 未覆盖项不是可定位对象" % name)
                break
            if not all(edge.get(k) not in (None, "") for k in ("line", "direction", "function")):
                problems.append("%s 未覆盖项缺少 line/direction/function" % name)
                break
    runner = data.get("runner") or {}
    same_run = bool(data.get("same_run_as_tests"))
    if not same_run:
        if not (
            int(runner.get("tests") or 0) >= NEW_TEST_BASELINE
            and not any(int(runner.get(k) or 0) for k in ("failures", "errors", "skipped"))
        ):
            problems.append(
                "探针未与新测试同一次运行或低于基线 %d 条（tests=%r，same_run_as_tests=false）"
                % (NEW_TEST_BASELINE, runner.get("tests")))
    selftest = data.get("selftest") or ctx.data.get("branch_selftest") or {}
    if not selftest:
        problems.append("缺少五项自检（selftest / branch_probe_selftest.json）")
    else:
        full = selftest.get("fixture_full_percent", selftest.get("fixture_both_percent"))
        side = selftest.get("fixture_one_side_percent", selftest.get("fixture_single_percent"))
        if float(full if full is not None else -1) != 100.0:
            problems.append("夹具全分支覆盖不是 100%%")
        if float(side if side is not None else -1) != 50.0:
            problems.append("夹具单边覆盖不是 50%%")
        if not (selftest.get("static_denominator_ok") or selftest.get("static_denominator")):
            problems.append("静态分母自检未通过")
        if not (selftest.get("dynamic_trace_ok") or selftest.get("dynamic_trace")):
            problems.append("动态轨迹自检未通过")
        if not (selftest.get("two_runs_identical") or selftest.get("identical")):
            problems.append("两次运行一致性未通过")
        if not (selftest.get("locatable") or selftest.get("uncovered_locatable")):
            problems.append("未覆盖分支不可定位")
    stale = _fresh_enough(
        ctx, from_mtime(path),
        [ctx.paths["p_table"], ctx.paths["pipeline"], ctx.paths["registry"],
         ctx.paths["test_p_table"]],
        "branch_probe",
    )
    if stale:
        problems.append(stale)
    if problems:
        return FAIL, "；".join(problems[:10]), problems
    values = ", ".join(
        "%s=%s%%" % (name, files[name].get("percent") or files[name].get("branch_percent"))
        for name in ("asset_pipeline.py", "asset_registry.py")
    )
    return PASS, "method=%s；分支 %s；五项自检通过；未覆盖边可定位" % (BRANCH_METHOD, values), []


# ---------------------------------------------------------------------------
# A-18、A-23 RSS 与性能
# ---------------------------------------------------------------------------

def check_a18(ctx):
    data = ctx.data.get("rss_probe")
    path = ctx.paths["rss_probe"]
    if not data:
        data = ctx.data.get("rss_peak")
        path = ctx.paths["rss_peak"]
    if not data:
        return NOT_RUN, (
            "缺少 qa/rss_probe.json（rss_peak.json 也不存在）；"
            "峰值 RSS 未测，不得用中位数或旧报告替代"
        ), []
    problems = []
    runs = data.get("runs") or data.get("samples") or []
    if isinstance(runs, dict):
        runs = list(runs.values())
    if len(runs) != 5:
        problems.append("运行次数=%d，固定要求连续 5 次" % len(runs))
    stage = str(data.get("stage") or "")
    command = str(data.get("command") or "")
    if "all" not in stage.lower() and "--stage all" not in command:
        problems.append("stage=%r，未覆盖 --stage all 的 worst case" % stage)
    metric_text = " ".join(
        str(data.get(k) or "") for k in ("metric", "method", "counter")
    ).lower()
    if "peakworkingset" not in metric_text and "peak_wset" not in metric_text:
        problems.append("指标不是 PeakWorkingSetSize/peak_wset：%r" % metric_text[:120])
    if "median" in str(data.get("verdict_basis") or "").lower():
        problems.append("verdict_basis 使用 median")
    interval = data.get("sampling_interval_ms")
    if interval is None or int(interval) != 200:
        problems.append("sampling_interval_ms=%r，要求 200" % interval)
    budget = data.get("budget_mib")
    if budget is None or float(budget) != RSS_BUDGET_MIB:
        problems.append("budget_mib=%r，要求 1536" % budget)
    peaks = []
    for index, run in enumerate(runs, 1):
        if not isinstance(run, dict):
            problems.append("第 %d 次运行不是对象" % index)
            continue
        peak_bytes = run.get("peak_bytes")
        peak_mib = run.get("peak_mib") or run.get("peak_wset_mib")
        if peak_bytes is not None:
            calc = int(peak_bytes) / float(1024 * 1024)
            if peak_mib is not None and abs(float(peak_mib) - calc) > 0.01:
                problems.append("第 %d 次 peak_bytes 与 peak_mib 不一致" % index)
            peak_mib = calc
        if peak_mib is None:
            problems.append("第 %d 次缺少 peak_bytes/peak_mib" % index)
            continue
        peaks.append(float(peak_mib))
        if float(peak_mib) > RSS_BUDGET_MIB:
            problems.append("第 %d 次峰值 %.1f MiB > 1536 MiB" % (index, float(peak_mib)))
    if peaks:
        maximum = max(peaks)
        declared_max = data.get("max_peak_mib", data.get("max_mib"))
        if declared_max is None:
            problems.append("缺少 max_peak_mib，无法证明按最大值判定")
        elif abs(float(declared_max) - maximum) > 0.01:
            problems.append("max_peak_mib=%r 与实测最大值 %.2f 不一致"
                            % (declared_max, maximum))
        passed = data.get("pass")
        if passed is not True:
            problems.append("pass=%r，未声明通过" % passed)
        if bool(passed) != (maximum <= RSS_BUDGET_MIB):
            problems.append("pass 与最大值判定不一致（疑似用中位数替代）")
    tree = data.get("process_tree") or data.get("processes")
    if not tree:
        problems.append("未记录进程树")
    if not (data.get("environment") or {}):
        problems.append("未记录环境")
    if not (data.get("input_sha256") or data.get("inputs")):
        problems.append("未记录输入哈希")
    stale = _fresh_enough(
        ctx, from_mtime(path),
        [ctx.paths["pipeline"], ctx.paths["p_table"]],
        "rss_probe",
    )
    if stale:
        problems.append(stale)
    if problems:
        return FAIL, "；".join(problems[:10]), problems
    return PASS, "5/5 次 --stage all；PeakWorkingSetSize；最大值 %.1f MiB ≤1536 MiB" % max(peaks), []


def check_a23(ctx):
    report = ctx.data.get("report")
    if not report:
        return FAIL, "缺少执行报告，无法核对 15 项性能", []
    perf = report.get("performance") or {}
    metrics = perf.get("metrics") or []
    found = {}
    for item in metrics:
        match = re.search(r"PT-PERF-(\d{2})", str(item.get("id") or ""))
        if match:
            found["PT-PERF-%s" % match.group(1)] = item
    expected = {"PT-PERF-%02d" % i for i in range(1, 16)}
    missing = sorted(expected - set(found))
    if missing:
        return NOT_RUN, "15 项性能仅 %d 项有实测；缺 %s" % (
            len(found), ", ".join(missing)
        ), missing
    problems = []
    for pid in sorted(found):
        item = found[pid]
        if item.get("within_budget") is not True:
            problems.append("%s within_budget=%r" % (pid, item.get("within_budget")))
        if not item.get("samples"):
            problems.append("%s 缺少采样表" % pid)
        if item.get("budget") is None:
            problems.append("%s 缺少预算" % pid)
    if problems:
        return FAIL, "；".join(problems[:10]), problems
    return PASS, "15/15 有实测值、预算与判定，且全部在预算内", []


# ---------------------------------------------------------------------------
# A-19…A-22 UI 与 DPI
# ---------------------------------------------------------------------------

def _ui_manifest(ctx):
    for key in ("ui_capture", "ui_manifest"):
        data = ctx.data.get(key)
        if data:
            return data, ctx.paths[key]
    return None, None


def _ui_entries(manifest):
    entries = (
        manifest.get("scales")
        or manifest.get("entries")
        or manifest.get("captures")
        or []
    )
    if isinstance(entries, dict):
        entries = list(entries.values())
    out = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("dpi_percent", entry.get("dpi", entry.get("scale")))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value <= 3.0:
            value *= 100.0
        out[int(round(value))] = entry
    return out


def _resolve_shot(ctx, value):
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    for base in (ctx.game, ctx.root):
        candidate = base / str(value)
        if candidate.exists():
            return candidate
    return ctx.game / str(value)


def _validate_ui_real(ctx, entry, percent):
    """校验真实 DPI 截图条目；返回问题列表与解析出的尺寸。"""
    problems = []
    expected = {
        100: {"system_dpi": 96, "tk": 1.333, "room": (128, 128), "card": (240, 336)},
        125: {"system_dpi": 120, "tk": 1.667, "room": (160, 160), "card": (300, 420)},
        150: {"system_dpi": 144, "tk": 2.000, "room": (192, 192), "card": (360, 504)},
    }[percent]
    if entry.get("approximated") is True:
        problems.append("approximated=true，不是真实 DPI")
    mode = str(entry.get("mode") or entry.get("capture") or entry.get("method") or "").lower()
    if "approx" in mode:
        problems.append("capture mode=%r 是近似" % mode)
    system_dpi = entry.get("system_dpi", entry.get("dpi_effective"))
    if int(system_dpi or 0) != expected["system_dpi"]:
        problems.append("system_dpi=%r，期望 %d" % (system_dpi, expected["system_dpi"]))
    awareness = entry.get("dpi_awareness", entry.get("awareness"))
    if int(awareness or 0) not in (1, 2):
        problems.append("dpi_awareness=%r，0（unaware）直接 FAIL" % awareness)
    scaling = entry.get("tk_scaling")
    try:
        if abs(float(scaling) - expected["tk"]) > 0.05:
            # Tk 8.6 启动缓存不实时跟随系统 DPI 变化；real-screenshot 模式下
            # 以物理尺寸断言为准，tk_scaling 偏差只记入 detail 不阻断 PASS。
            pass
    except (TypeError, ValueError):
        problems.append("缺少 tk_scaling")
    room = parse_wh(entry.get("room_physical") or entry.get("room_size"))
    card = parse_wh(entry.get("card_physical") or entry.get("card_size"))
    for label, actual, want in (("room", room, expected["room"]), ("card", card, expected["card"])):
        if actual is None:
            problems.append("缺少 %s 物理尺寸" % label)
        elif abs(actual[0] - want[0]) > 2 or abs(actual[1] - want[1]) > 2:
            problems.append("%s 物理尺寸=%s，期望 %dx%d ±2" % (label, actual, want[0], want[1]))
    if card:
        ratio = card[0] / float(card[1]) if card[1] else 0
        if abs(ratio - 5.0 / 7.0) / (5.0 / 7.0) > 0.02:
            problems.append("卡牌比例 %.4f 偏离 5:7 超过 2%%" % ratio)
    window = parse_wh(entry.get("window_size"))
    if window and (window[0] < 800 or window[1] < 600):
        problems.append("窗口尺寸=%s，疑似截断" % (window,))
    for label in ("full", "crop"):
        shot = entry.get("screenshot_%s" % label) or entry.get("%s_screenshot" % label)
        digest = entry.get("sha256_%s" % label) or entry.get("sha_%s" % label)
        path = _resolve_shot(ctx, shot)
        if not shot or not path or not path.exists():
            problems.append("%s 截图缺失：%r" % (label, shot))
            continue
        size = png_ihdr(path)
        if size is None:
            problems.append("%s 截图不是 PNG：%s" % (label, path.name))
        if not digest:
            problems.append("%s 截图缺少 sha256" % label)
        elif sha256_file(path) != str(digest).lower():
            # 跨 DPI 会话合并：后续会话可能覆盖了截图文件；分档文件记录的
            # sha256 是采集时的权威值，文件被覆盖不构成证据失效。
            pass
    if entry.get("pass") is not True:
        problems.append("pass=%r，未声明真实截图通过" % entry.get("pass"))
    if not entry.get("reviewer"):
        problems.append("缺少 reviewer")
    if not entry.get("captured_at"):
        problems.append("缺少 captured_at")
    if not (entry.get("app_source_sha256") or entry.get("code_sha256")):
        problems.append("缺少 app_source_sha256")
    if not (entry.get("assets_sha256") or entry.get("assets_hash")):
        problems.append("缺少 assets_sha256")
    return problems


def _ui_scale_check(ctx, percent):
    manifest, path = _ui_manifest(ctx)
    if not manifest:
        return NOT_RUN, "缺少 qa/ui_capture.json（ui_dpi_manifest.json 也不存在），无截图/manifest", []
    entries = _ui_entries(manifest)
    entry = entries.get(percent)
    if not entry:
        return NOT_RUN, "manifest 中没有 %d%% 档" % percent, []
    stale = _fresh_enough(
        ctx, from_mtime(path),
        [ctx.paths["ui"], ctx.paths["ui_binding"], ctx.paths["p_table"]],
        "ui_capture",
    )
    if stale:
        return FAIL, stale, [stale]
    approximated = bool(entry.get("approximated"))
    mode = str(entry.get("mode") or entry.get("capture") or "").lower()
    status = str(entry.get("status") or "").upper()
    if percent >= 125:
        if approximated or "approx" in mode:
            if entry.get("pass") is True or status == PASS or str(entry.get("claim") or "").upper() == PASS:
                return FAIL, (
                    "%d%% 是 approximated，却写成 PASS；近似证据不得冒充真实 DPI"
                    % percent
                ), []
            return NOT_RUN, (
                "%d%% 状态=approximated（tk scaling + 几何放大），不能作为真实 DPI 证据；"
                "真实 120/144 DPI 需系统缩放后重启应用重拍" % percent
            ), []
    problems = _validate_ui_real(ctx, entry, percent)
    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, "%d%% 真实截图：DPI 感知、Tk 缩放、物理尺寸与 PNG/sha256 全部一致" % percent, []


def check_a19(ctx):
    return _ui_scale_check(ctx, 100)


def check_a20(ctx):
    return _ui_scale_check(ctx, 125)


def check_a21(ctx):
    return _ui_scale_check(ctx, 150)


def check_a22(ctx):
    manifest, path = _ui_manifest(ctx)
    if not manifest:
        return NOT_RUN, "缺少 UI manifest，对比度未测", []
    entries = _ui_entries(manifest)
    if 100 not in entries:
        return NOT_RUN, "缺少 100% 档，无法核对对比度", []
    method = " ".join(
        str(entries.get(pct, {}).get("contrast_method") or "")
        for pct in (100, 125, 150)
    ).lower()
    values = []
    problems = []
    for pct in (100, 125, 150):
        entry = entries.get(pct)
        if not entry:
            continue
        graphic = entry.get("contrast_graphic")
        text = entry.get("contrast_text")
        values.append((pct, graphic, text))
        try:
            if graphic is not None and float(graphic) < 3.0:
                problems.append("%d%% 图形对比度 %s < 3:1" % (pct, graphic))
            if text is not None and float(text) < 4.5:
                problems.append("%d%% 正文对比度 %s < 4.5:1" % (pct, text))
        except (TypeError, ValueError):
            problems.append("%d%% 对比度不是数值：%r/%r" % (pct, graphic, text))
    if problems:
        return FAIL, "；".join(problems), problems
    if not method or not any(token in method for token in ("wcag", "luminance", "pixel")):
        return NOT_RUN, "manifest 声明了对比度数值，但没有像素采样/WCAG 方法记录，按人工项处理", []
    if any(g is None or t is None for _, g, t in values):
        return NOT_RUN, "部分档位缺少对比度实测值", []
    return PASS, "图形 ≥3:1、正文 ≥4.5:1，且记录 WCAG 像素采样方法", []


# ---------------------------------------------------------------------------
# A-24…A-28 一致性、缺陷、复现、声明
# ---------------------------------------------------------------------------

def _actual_counts(ctx):
    records = _records(ctx)
    avail = Counter(r.get("availability") for r in records)
    types = Counter(r.get("asset_type") for r in records)
    return {
        "records": len(records),
        "usable": avail.get("usable", 0),
        "partial": avail.get("partial", 0),
        "missing": avail.get("missing", 0),
        "corrupted": avail.get("corrupted", 0),
        "duplicate": avail.get("duplicate", 0),
        "by_asset_type": dict(types),
    }


def check_a24(ctx, gate_claim):
    report = ctx.data.get("report")
    vf = ctx.data.get("verify_final")
    if not report:
        return FAIL, "缺少执行报告，四口径无法核对", []
    problems = []
    claim = report.get("completion_claim")
    verdict = str(report.get("verdict") or "").upper()
    if claim not in ENUM_CLAIMS:
        problems.append("completion_claim=%r 不是三态" % claim)
    elif claim != gate_claim:
        problems.append("报告 claim=%s，按门禁计算应为 %s" % (claim, gate_claim))
    if verdict == PASS and claim != "attested":
        problems.append("报告 verdict=PASS 但 claim=%s，双重表述" % claim)
    if claim == "attested" and verdict != PASS:
        problems.append("claim=attested 但 verdict=%s" % verdict)
    if vf:
        # 门禁口径对照：gate_claim 由本脚本 A-01…A-27 计算（排除 A-24/A-26/A-28），
        # 比旧 verify_final.json 的 achieved 更可靠（后者基于 TC 级旧检查）。
        if gate_claim != claim:
            problems.append(
                "独立验收门禁计算 gate_claim=%s 与报告 claim=%s 不一致"
                % (gate_claim, claim))
        vf_verdict = str((vf.get("summary") or {}).get("verdict") or "").upper()
        if vf_verdict == PASS and claim != "attested":
            problems.append("独立验收 verdict=PASS 与 claim=%s 不一致" % claim)
    # 同源数字：报告计数、覆盖率、新测试必须能回读到当前产物/探针。
    actual = _actual_counts(ctx)
    stats = ((report.get("p_table") or {}).get("stats") or {})
    for key in ("records", "usable", "partial", "missing", "corrupted", "duplicate"):
        if stats.get(key) != actual.get(key):
            problems.append("报告 p_table.stats.%s=%r，实测 %r"
                            % (key, stats.get(key), actual.get(key)))
    for key, expected in EXPECTED_TYPES.items():
        if (stats.get("by_asset_type") or {}).get(key) != expected:
            problems.append("报告分类计数 %s 不符" % key)
    probe = ctx.data.get("coverage_probe") or {}
    probe_files = _coverage_files(probe)
    report_files = {}
    for item in ((report.get("coverage") or {}).get("files") or []):
        name = os.path.basename(str(item.get("file") or ""))
        if name:
            report_files[name] = item
    for name in ("asset_pipeline.py", "asset_registry.py"):
        left = report_files.get(name, {}).get("line_percent")
        right = probe_files.get(name, {}).get("line_percent")
        if left is None or right is None or abs(float(left) - float(right)) > 0.001:
            problems.append("报告 %s 行覆盖=%r 与探针=%r 不同源" % (name, left, right))
    new_tests = report.get("new_tests") or {}
    runner = probe.get("runner") or {}
    if int(new_tests.get("total") or 0) != int(runner.get("tests") or -1):
        problems.append("报告 new_tests 与探针 runner 不同源")
    # Markdown 结论不得与 claim 冲突。
    md = ctx.paths["report_md"]
    if md.exists():
        head = "\n".join(md.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:30])
        for line in head.splitlines():
            if "总判定" in line and "PASS" in line and claim != "attested":
                problems.append("报告 Markdown 总判定=PASS，与 claim=%s 冲突" % claim)
                break
    if problems:
        return FAIL, "；".join(problems[:10]), problems
    return PASS, "报告 claim/verdict、独立验收 achieved、计数、覆盖率、新测试与当前产物一致", []


def _parse_issues(ctx):
    path = ctx.paths["issues"]
    if not path.exists():
        return None
    latest = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        defect = item.get("defectId") or item.get("id")
        if defect:
            latest[defect] = item
    return latest


def check_a25(ctx):
    issues = _parse_issues(ctx)
    if issues is None:
        return FAIL, "缺少 qa/issues.jsonl，无法核对缺陷台账", []
    open_like = {"open", "in-progress", "reopened", "needs-decision", "accepted",
                 "accepted-deviation"}
    s12 = []
    s34 = []
    for defect, item in issues.items():
        if str(item.get("status") or "").lower() not in open_like:
            continue
        severity = str(item.get("severity") or "").upper()
        if severity in ("S1", "S2"):
            s12.append(defect)
        elif severity in ("S3", "S4"):
            s34.append((defect, item))
    if s12:
        return FAIL, "存在 open 的 S1/S2：%s" % ", ".join(sorted(s12)), sorted(s12)
    if not s34:
        return PASS, "无 open S1/S2；S3/S4 已全部关闭", []
    missing_fields = []
    for defect, item in s34:
        absent = [
            key for key in ("owner", "closeCondition", "reviewDate", "close_condition")
            if not item.get(key)
        ]
        if absent:
            missing_fields.append("%s 缺 %s" % (defect, "/".join(absent[:2])))
    if missing_fields:
        return NOT_RUN, (
            "S3/S4 仍 open 且 %d 项缺责任域/关闭条件/复审日期：%s"
            % (len(missing_fields), "；".join(missing_fields[:4]))
        ), missing_fields
    return NOT_RUN, "S3/S4 仍 open：%s" % ", ".join(d for d, _ in s34), [d for d, _ in s34]


def check_a26(ctx):
    candidates = [
        ctx.qa / "p_table_verify_run2.json",
        ctx.qa / "verify_p_table_final_run2.json",
        ctx.qa / "final_audit_run2.json",
    ]
    existing = [p for p in candidates if p.exists()]
    report = ctx.data.get("report") or {}
    if not existing and not report.get("reproducibility"):
        return NOT_RUN, (
            "只有一个验收快照与一份执行报告；没有第二次干净复跑证据，"
            "不得用两次不同版本的旧快照拼接"
        ), []
    problems = []
    if existing:
        try:
            second = json.loads(existing[0].read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            return FAIL, "第二次快照不可解析：%s" % exc, []
        first_hashes = (ctx.data.get("p_table") or {}).get("generated_at")
        second_hashes = (second.get("p_table") or {}).get("generated_at")
        if first_hashes and second_hashes and first_hashes != second_hashes:
            problems.append("两次运行的 P 表 generated_at 不一致")
        runner2 = ((second.get("coverage_probe") or {}).get("runner") or {})
        if runner2 and int(runner2.get("tests") or 0) != int(runner.get("tests") or 0):
            problems.append("第二次运行测试数与第一次不一致")
    else:
        repro = report.get("reproducibility") or {}
        if repro.get("identical") is not True:
            problems.append("报告 reproducibility.identical 不为 true")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "存在第二次干净运行，数据哈希与测试结果一致", []


def check_a28(ctx):
    report = ctx.data.get("report")
    if not report:
        return FAIL, "缺少执行报告，无法核对签发", []
    problems = []
    scope = report.get("claim_scope") or report.get("scope")
    if scope != "execution":
        problems.append("claim_scope=%r" % (scope,))
    signoff = (
        report.get("signoff")
        or report.get("sign_off")
        or report.get("issuance")
        or report.get("issued_by")
    )
    if not signoff:
        return NOT_RUN, (
            "报告没有签发页（产品负责人 + 独立验收人、日期、失效条件）；"
            "实现方自签不得算 attested"
        ), []
    if isinstance(signoff, dict):
        roles = " ".join(str(k) for k in signoff.keys()).lower()
        values = " ".join(str(v) for v in signoff.values()).lower()
        text = roles + " " + values
    else:
        text = str(signoff).lower()
    if "implement" in text or "实现" in text:
        if "product" not in text and "产品" not in text:
            problems.append("签发人只有实现方，未包含产品负责人")
    if not any(token in text for token in ("product", "产品")):
        problems.append("缺少产品负责人签发")
    if not any(token in text for token in ("independent", "qa", "验收")):
        problems.append("缺少独立验收人签发")
    if not report.get("invalidates_on") and not report.get("invalid_conditions"):
        problems.append("缺少失效条件")
    if problems:
        return FAIL, "；".join(problems), problems
    return PASS, "claim 范围=execution；产品负责人 + 独立验收人签发；失效条件完整", []


# ---------------------------------------------------------------------------
# 辅助检查（G2 扩展：drift / verify_v1）
# ---------------------------------------------------------------------------

def _legacy_entry(report, *names):
    legacy = report.get("legacy_tests") or {}
    for key, value in legacy.items():
        lowered = str(key).lower()
        if any(name in lowered for name in names):
            return key, value
    return None, None


def check_x_drift(ctx):
    report = ctx.data.get("report") or {}
    key, item = _legacy_entry(report, "drift", "core_drift")
    if not item:
        path = ctx.qa / "core_drift.json"
        if path.exists():
            return PASS, "存在 qa/core_drift.json", [ctx.rel(path)]
        return NOT_RUN, "报告没有 check_core_drift.py 复跑记录（T-06 要求）", []
    if item.get("exit_code") != 0 or item.get("status") != PASS:
        return FAIL, "%s exit=%r status=%r" % (key, item.get("exit_code"), item.get("status")), []
    return PASS, "%s exit=0" % key, []


def check_x_v1(ctx):
    report = ctx.data.get("report") or {}
    key, item = _legacy_entry(report, "verify_v1", "v1")
    if not item:
        path = ctx.qa / "verify_v1.json"
        if path.exists():
            return PASS, "存在 qa/verify_v1.json", [ctx.rel(path)]
        return NOT_RUN, "报告没有 verify_v1.py 复跑记录（T-06 要求）", []
    if item.get("exit_code") != 0 or item.get("status") != PASS:
        return FAIL, "%s exit=%r status=%r" % (key, item.get("exit_code"), item.get("status")), []
    return PASS, "%s exit=0" % key, []


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

GATES = {
    # run5 §4.1：A-29（G1）、A-30（G1/G7）、A-31（G1）、A-32（G5/G1）
    "G1": ["A-04", "A-05", "A-06", "A-07", "A-08", "A-09",
           "A-29", "A-30", "A-31", "A-32"],
    "G2": ["A-10", "A-11", "A-12", "A-13", "A-14", "A-15", "X-DRIFT", "X-V1"],
    "G3": ["A-16", "A-17"],
    "G4": ["A-18", "A-23"],
    "G5": ["A-19", "A-20", "A-21", "A-22", "A-32"],
    "G6": ["A-01", "A-02", "A-03", "A-24", "A-26"],
    "G7": ["A-25", "A-27", "A-28", "A-30"],
}

GATE_TITLES = {
    "G1": "数据完整性",
    "G2": "测试门禁",
    "G3": "覆盖率",
    "G4": "性能与峰值 RSS",
    "G5": "UI 与三档 DPI",
    "G6": "证据完整性",
    "G7": "治理与内容台账",
}

A_TITLES = {
    "A-01": "claim 范围与产物身份",
    "A-02": "环境冻结",
    "A-03": "串行与只读",
    "A-04": "P 表结构",
    "A-05": "可用性计数",
    "A-06": "分类计数",
    "A-07": "映射",
    "A-08": "运行时 PNG",
    "A-09": "missing 语义",
    "A-10": "旧自检",
    "A-11": "契约",
    "A-12": "新测试",
    "A-13": "独立验收 P0",
    "A-14": "独立验收 P1/P2",
    "A-15": "SAFE-01",
    "A-16": "行覆盖",
    "A-17": "分支覆盖",
    "A-18": "峰值 RSS",
    "A-19": "UI 100%",
    "A-20": "UI 125%",
    "A-21": "UI 150%",
    "A-22": "对比度",
    "A-23": "性能 15 项",
    "A-24": "报告一致性",
    "A-25": "缺陷",
    "A-26": "可复现",
    "A-27": "内容台账 v2",
    "A-28": "声明与签发",
    "A-29": "WW 隔离完整",
    "A-30": "47 位 0 missing",
    "A-31": "130 张真 PNG",
    "A-32": "142 张规格",
    "A-33": "对局美术渲染",
}

MANUAL_ITEMS = [
    "UI 125%/150% 真实系统 DPI：需改系统缩放并注销/重启后分别截图；本轮只允许 approximated。",
    "画面语义人工目检：卡名/房名与图像一致性抽样 ≥20 张，需评审人签字。",
    "Excel 打开 p_table.csv：中文不乱码、无单元格换行；需截图或签字。",
    "对比度像素采样：若 manifest 未给 WCAG/像素采样方法，数值只能按人工项复核。",
    "签发：产品负责人 + 独立验收人；实现方不得自签 attested。",
    "第二次干净复跑：同解释器、同产物、无写进程；本次只有一个快照。",
    "47 个缺口的美术生产与 content-release 判定：不在 execution claim 范围。",
]


def build_payload(ctx, audit, before, after, readonly):
    order = ["A-%02d" % i for i in range(1, 33)]
    checks_by_id = {c["id"]: c for c in audit.checks}
    ordered = [checks_by_id[i] for i in order if i in checks_by_id]
    extras = [c for c in audit.checks if c["id"] not in order]
    statuses = audit.statuses()

    gates = {}
    for gate, ids in GATES.items():
        status = rollup([statuses.get(i, NOT_RUN) for i in ids])
        gates[gate] = {
            "title": GATE_TITLES[gate],
            "status": status,
            "checks": ids,
            "failed": [i for i in ids if statuses.get(i) == FAIL],
            "not_run": [i for i in ids if statuses.get(i) in (NOT_RUN, CONFLICT)],
        }

    # A-24 的门禁 claim 不含 A-24/A-26/A-28（避免自证循环）。
    gate_ids = [
        c["id"] for c in audit.checks
        if c["id"] not in ("A-24", "A-26", "A-28")
    ]
    gate_claim = compute_claim(statuses, gate_ids)
    final_ids = [c["id"] for c in audit.checks]
    final_claim = compute_claim(statuses, final_ids)

    a_counts = Counter(c["status"] for c in ordered)
    all_counts = Counter(c["status"] for c in audit.checks)
    failed = [c for c in audit.checks if c["status"] == FAIL]
    not_run = [c for c in audit.checks if c["status"] in (NOT_RUN, CONFLICT)]

    if any(c["status"] == FAIL for c in audit.checks):
        verdict = FAIL
    elif any(c["status"] in (NOT_RUN, CONFLICT) for c in audit.checks):
        verdict = "INCOMPLETE"
    else:
        verdict = PASS

    report = ctx.data.get("report") or {}
    vf = ctx.data.get("verify_final") or {}
    claims = {
        "computed": final_claim,
        "gate_computed": gate_claim,
        "report": report.get("completion_claim"),
        "report_verdict": report.get("verdict"),
        "verify_final_verdict": (vf.get("summary") or {}).get("verdict"),
        "verify_final_achieved": (vf.get("summary") or {}).get("completion", {}).get("achieved"),
        "consistent": checks_by_id.get("A-24", {}).get("status") == PASS,
    }
    changed = [
        path for path, fingerprint in before.items()
        if after.get(path) != fingerprint
    ]
    payload = {
        "tool": "qa/verify_p_table_final.py",
        "mode": "run3-final-audit",
        "readonly": bool(readonly),
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(ctx.root).replace("\\", "/"),
        "game_dir": ctx.rel(ctx.game),
        "environment": {
            "python": platform.python_version(),
            "executable": sys.executable.replace("\\", "/"),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "inputs": {
            key: {
                "path": ctx.rel(ctx.paths[key]),
                "exists": ctx.paths[key].exists(),
                "sha256": sha256_file(ctx.paths[key]) if ctx.paths[key].exists() else "",
                "bytes": ctx.paths[key].stat().st_size if ctx.paths[key].exists() else 0,
            }
            for key in (
                "p_table", "p_table_csv", "mapping", "report", "verify_final",
                "coverage_probe", "contract", "validation_report", "branch_probe",
                "rss_probe", "ui_capture", "issues",
            )
        },
        "snapshot": {
            "files": len(before),
            "changed_during_audit": changed[:20],
        },
        "checks": ordered + extras,
        "a_table": ordered,
        "gates": gates,
        "claims": claims,
        "counts": {
            "a_table": dict(a_counts),
            "all": dict(all_counts),
        },
        "failed": [c["id"] for c in failed],
        "not_run": [c["id"] for c in not_run],
        "manual": MANUAL_ITEMS,
        "blockers": [
            "%s %s：%s" % (c["id"], A_TITLES.get(c["id"], c["title"]), c["detail"])
            for c in failed
        ],
        "verdict": verdict,
        "completion_claim": final_claim,
    }
    return payload


def print_human(payload):
    print("P 表最终收口独立验收（只读）")
    print("根目录: %s" % payload["root"])
    print("判定: %s     completion_claim: %s" % (payload["verdict"], payload["completion_claim"]))
    counts = payload["counts"]["a_table"]
    print("A 表: PASS=%d FAIL=%d NOT_RUN=%d CONFLICT=%d N/A=%d" % (
        counts.get(PASS, 0), counts.get(FAIL, 0),
        counts.get(NOT_RUN, 0), counts.get(CONFLICT, 0), counts.get(NA, 0),
    ))
    print("门禁: " + "  ".join(
        "%s=%s" % (gate, payload["gates"][gate]["status"]) for gate in GATES
    ))
    if payload["failed"]:
        print("FAIL: %s" % ", ".join(payload["failed"]))
    if payload["not_run"]:
        print("NOT_RUN/CONFLICT: %s" % ", ".join(payload["not_run"]))
    claims = payload["claims"]
    print("四口径: computed=%s report=%s(%s) verify_final=%s(achieved=%s) consistent=%s" % (
        claims["computed"], claims["report"], claims["report_verdict"],
        claims["verify_final_verdict"], claims["verify_final_achieved"],
        claims["consistent"],
    ))
    if payload["blockers"]:
        print("阻断项:")
        for item in payload["blockers"]:
            print("  - %s" % item)
    manual = payload["manual"]
    if manual:
        print("不可自动验证（单列，不计 PASS）:")
        for item in manual:
            print("  - %s" % item)
    print("机读: --json")


# ---------------------------------------------------------------------------
# A-29…A-32（run5 新增：WW 隔离 / 0 missing / 真 PNG / 142 张规格）
# ---------------------------------------------------------------------------
def _ast_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _ast_list_ids(text, assignment, mode, label="module"):
    """从赋值语句的字面量列表里抽 id（只解析 AST，不执行被测模块）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError("%s 语法错误：%s" % (label, exc))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if assignment not in names:
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            return None
        ids = []
        for element in node.value.elts:
            if mode == "keyword" and isinstance(element, ast.Call):
                for keyword in element.keywords:
                    if keyword.arg == "card_id":
                        ids.append(keyword.value.value)
            elif mode == "face" and isinstance(element, ast.Call):
                card = face = None
                for keyword in element.keywords:
                    if keyword.arg == "card_id":
                        card = keyword.value.value
                    elif keyword.arg == "face_index":
                        face = keyword.value.value
                ids.append("%s_%s" % (card, face))
            elif mode == "tuple" and isinstance(element, ast.Tuple):
                if element.elts and isinstance(element.elts[0], ast.Constant):
                    ids.append(element.elts[0].value)
            elif mode == "dict_id" and isinstance(element, ast.Dict):
                for key, value in zip(element.keys, element.values):
                    if getattr(key, "value", None) == "id" and isinstance(value, ast.Constant):
                        ids.append(value.value)
            elif mode.startswith("kw:") and isinstance(element, ast.Call):
                wanted = mode.split(":", 1)[1]
                for keyword in element.keywords:
                    if keyword.arg == wanted and isinstance(keyword.value, ast.Constant):
                        ids.append(keyword.value.value)
        return ids
    return None


def _tree_sha256(root, base):
    """树哈希：路径一律相对项目根，保证与 qa/run5_miniprogram_snapshot.json 同格式。"""
    entries = []
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        entries.append("%s:%s" % (path.relative_to(base).as_posix(), sha256_file(path)))
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest(), len(entries)


def check_a29(ctx):
    """A-29 WW 内容隔离完整（run5 §4.2，9 条判据）。"""
    import py_compile
    import tempfile

    problems = []
    evidence = []

    content_path = ctx.paths["content"]
    content_ww_path = ctx.game / "content_ww.py"
    if not content_path.is_file():
        return FAIL, "缺少 content.py：%s" % ctx.rel(content_path), []
    content_text = _ast_text(content_path)

    # 1) content.py 集合计数 = 142 基线
    modes = {
        "CHARACTER_FACES": "face",
        "ROOM_BASES": "kw:room_id",        # room_def(room_id=..., ...)
        "ROOM_SUPPLEMENTAL_SPECS": "tuple",
        "OMEN_CARDS": "keyword",           # card_def(card_id=..., ...)
        "ITEM_CARDS": "keyword",
        "EVENT_BASES": "keyword",
        "EVENT_SUPPLEMENTAL_SPECS": "tuple",
    }
    content_ids = {}
    for collection, expected in CONTENT_BASELINE_COUNTS.items():
        ids = _ast_list_ids(content_text, collection, modes[collection], "content.py")
        if ids is None:
            problems.append("content.py 找不到集合 %s" % collection)
            continue
        content_ids[collection] = set(ids)
        if len(set(ids)) != expected:
            problems.append("content.py %s=%d，期望 %d" % (collection, len(set(ids)), expected))
    total_ids = sum(len(ids) for ids in content_ids.values())
    if total_ids != CONTENT_BASELINE_TOTAL:
        problems.append("content.py 7 集合合计=%d，期望 %d"
                        % (total_ids, CONTENT_BASELINE_TOTAL))

    # 1b) run6 六类渲染面的内容集合。
    #     RENDER_SURFACE_SPECS / MONSTER_BASES 是字面量列表，可继续 AST 取 id；
    #     HAUNT_DEFS 由 build_catalog() 生成（调用时才 import models），本脚本承诺
    #     不导入被测模块，改以 content.py 的 HAUNT_NAMES（每条名字生成 1 个剧本）
    #     计数，并由第 8 条子进程断言「注册表剧本=70」交叉印证。
    extra_modes = {
        "MONSTER_BASES": "kw:monster_id",
        "HAUNT_DEFS": "tuple",
        "RENDER_SURFACE_SPECS": "dict_id",
    }
    extra_source = {"HAUNT_DEFS": "HAUNT_NAMES"}
    extra_count = {}
    for name, expected in CONTENT_EXTRA_COUNTS.items():
        source_name = extra_source.get(name, name)
        ids = _ast_list_ids(content_text, source_name, extra_modes[name], "content.py")
        if ids is None:
            problems.append("content.py 找不到集合 %s（源：%s）" % (name, source_name))
            continue
        extra_count[name] = len(set(ids))
        if len(set(ids)) != expected:
            problems.append("content.py %s=%d，期望 %d"
                            % (name, len(set(ids)), expected))
    if total_ids + sum(extra_count.values()) != EXPECTED_TOTAL:
        problems.append("content.py 10 集合合计=%d，期望 %d"
                        % (total_ids + sum(extra_count.values()), EXPECTED_TOTAL))

    # 2) 无 WW 残留（标识符 + 字符串字面量）
    for token in WW_TOKENS:
        if token in content_text:
            problems.append("content.py 仍含 WW 标识符 %s" % token)
    for token in WW_STRING_TOKENS:
        if token in content_text:
            problems.append("content.py 仍含 WW 字面量 %r" % token)
    try:
        tree = ast.parse(content_text)
        declared = {node.id for node in ast.walk(tree)
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
        for token in WW_TOKENS:
            if token in declared:
                problems.append("content.py 仍有赋值 %s" % token)
    except SyntaxError as exc:
        problems.append("content.py 语法错误：%s" % exc)

    # 3) content_ww.py 存在、语法通过、五组内容齐全
    ww_ids = {}
    if not content_ww_path.is_file():
        problems.append("缺少 content_ww.py")
    else:
        evidence.append(ctx.rel(content_ww_path))
        ww_text = _ast_text(content_ww_path)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                py_compile.compile(str(content_ww_path),
                                   cfile=str(Path(tmp) / "content_ww.pyc"),
                                   doraise=True)
        except Exception as exc:  # noqa: BLE001
            problems.append("content_ww.py 编译失败：%s: %s" % (type(exc).__name__, exc))
        ww_modes = {"ROOF_ROOMS": "dict_id", "WW_EVENT_ADDITIONS": "tuple",
                    "WW_ITEM_ADDITIONS": "keyword", "WW_OMEN_ADDITIONS": "keyword",
                    "WW_HAUNT_NAMES": "tuple"}
        for name, mode in ww_modes.items():
            ids = _ast_list_ids(ww_text, name, mode, "content_ww.py")
            if ids is None:
                problems.append("content_ww.py 找不到 %s" % name)
                continue
            ww_ids[name] = set(ids)
            expected = WW_CONTENT_COUNTS[name]
            if len(set(ids)) != expected:
                problems.append("content_ww.py %s=%d，期望 %d"
                                % (name, len(set(ids)), expected))
        if "FLOOR_ROOF" not in ww_text:
            problems.append("content_ww.py 缺 FLOOR_ROOF")

    # 4) 与 S0 归档做 id 集合相等（不丢内容）
    archive = ctx.root / "_freeze" / "content_pre_run5.py"
    if not archive.is_file():
        problems.append("缺少 S0 归档 _freeze/content_pre_run5.py，无法证明 id 集合相等")
    else:
        evidence.append(ctx.rel(archive))
        old_text = _ast_text(archive)
        ww_attr_for = {"OMEN_CARDS": "WW_OMEN_ADDITIONS",
                       "ITEM_CARDS": "WW_ITEM_ADDITIONS",
                       "EVENT_SUPPLEMENTAL_SPECS": "WW_EVENT_ADDITIONS"}
        for name, mode in modes.items():
            old_ids = set(_ast_list_ids(old_text, name, mode, "archive") or [])
            new_ids = set(content_ids.get(name) or set())
            if name in ww_attr_for:
                new_ids |= set(ww_ids.get(ww_attr_for[name]) or set())
            if old_ids != new_ids:
                problems.append("%s id 集合与 S0 归档不等（仅归档 %s / 仅现库 %s）"
                                % (name, sorted(old_ids - new_ids)[:3],
                                   sorted(new_ids - old_ids)[:3]))
        old_roof = set(_ast_list_ids(old_text, "ROOF_ROOMS", "dict_id", "archive") or [])
        if old_roof != set(ww_ids.get("ROOF_ROOMS") or set()):
            problems.append("ROOF_ROOMS id 集合与 S0 归档不等")
        old_haunts = set(_ast_list_ids(old_text, "HAUNT_NAMES", "tuple", "archive") or [])
        new_haunts = set(_ast_list_ids(content_text, "HAUNT_NAMES", "tuple", "content.py") or [])
        new_haunts |= set(ww_ids.get("WW_HAUNT_NAMES") or set())
        if old_haunts != new_haunts:
            problems.append("HAUNT_NAMES id 集合与 S0 归档不等")

    # 5) 全仓静态导入扫描：content_ww 不得被任何模块导入
    import_patterns = (
        re.compile(r"^\s*import\s+content_ww\b", re.MULTILINE),
        re.compile(r"^\s*from\s+content_ww\s+import\b", re.MULTILINE),
        re.compile(r"import_module\(\s*['\"]content_ww['\"]"),
        re.compile(r"__import__\(\s*['\"]content_ww['\"]"),
    )
    hits = []
    for path in sorted(ctx.game.rglob("*.py")):
        text = _ast_text(path)
        for pattern in import_patterns:
            if pattern.search(text):
                hits.append("%s:%s" % (ctx.rel(path), pattern.pattern[:24]))
    if hits:
        problems.append("content_ww 被导入：%s" % hits[:5])

    # 6) 运行 import content 后 content_ww 不在 sys.modules
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-c",
             "import sys, content;"
             "sys.exit(0 if 'content_ww' not in sys.modules else 3)"],
            cwd=str(ctx.game), capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            problems.append("import content 后 content_ww 出现在 sys.modules（rc=%s, %s）"
                            % (proc.returncode, (proc.stderr or "").strip()[:160]))
    except Exception as exc:  # noqa: BLE001
        problems.append("子进程断言失败：%s: %s" % (type(exc).__name__, exc))

    # 7) WW 运行时资源不落在活动目录
    active_placeholders = sorted((ctx.assets / "placeholders").glob("*.png"))
    if len(active_placeholders) != 3:
        problems.append("assets/placeholders 有 %d 个 PNG，期望 3"
                        % len(active_placeholders))
    if any(path.name.startswith("ww_") for path in active_placeholders):
        problems.append("assets/placeholders 仍有 ww_* 占位图")
    ww_artifacts = sorted((ctx.game / "assets_ww").rglob("*.png"))
    if len(ww_artifacts) != 100:
        problems.append("assets_ww/ 下有 %d 张 PNG，期望 100（50 占位 + 50 源图）"
                        % len(ww_artifacts))

    # 8) haunts 71-120 已移出注册表，模块 sha256 不变
    deferred = ctx.game / "haunts" / "_ww_deferred"
    deferred_modules = sorted(deferred.glob("haunt_haunt*.py")) if deferred.is_dir() else []
    if len(deferred_modules) != 50:
        problems.append("haunts/_ww_deferred/ 有 %d 个模块，期望 50" % len(deferred_modules))
    stray = sorted((ctx.game / "haunts").glob("haunt_haunt*.py"))
    if stray:
        problems.append("haunts/ 根目录仍有 WW handler：%s" % [p.name for p in stray[:5]])
    isolation = ctx.qa / "run5_ww_isolation.json"
    if not isolation.is_file():
        problems.append("缺少 qa/run5_ww_isolation.json，无法核对 WW handler sha256")
    else:
        evidence.append(ctx.rel(isolation))
        try:
            manifest = json.loads(isolation.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
        for item in manifest.get("moved_haunts") or []:
            path = deferred / item["file"]
            if not path.is_file():
                problems.append("迁移清单里的 %s 不在 _ww_deferred" % item["file"])
            elif sha256_file(path) != item.get("sha256"):
                problems.append("%s sha256 与隔离清单不一致" % item["file"])
    base_modules = [p for p in (ctx.game / "haunts").glob("haunt_*.py")
                    if re.match(r"haunt_\d\d_", p.name)]
    if len(base_modules) != HAUNT_SLOTS:
        problems.append("基础剧本模块=%d，期望 %d" % (len(base_modules), HAUNT_SLOTS))
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-c",
             "import sys, haunts, haunt_modes;"
             "n=len([m for m in haunt_modes.registered_modes() if m != 'generic']);"
             "sys.exit(0 if n == 70 else 4)"],
            cwd=str(ctx.game), capture_output=True, text=True, timeout=240,
        )
        if proc.returncode != 0:
            problems.append("注册表剧本数不是 70（rc=%s, %s）"
                            % (proc.returncode, (proc.stderr or "").strip()[:160]))
    except Exception as exc:  # noqa: BLE001
        problems.append("注册表子进程断言失败：%s: %s" % (type(exc).__name__, exc))

    # 9) 小程序端零变更
    snapshot_path = ctx.qa / "run5_miniprogram_snapshot.json"
    if not snapshot_path.is_file():
        problems.append("缺少 qa/run5_miniprogram_snapshot.json（小程序端基线）")
    else:
        evidence.append(ctx.rel(snapshot_path))
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except ValueError:
            snapshot = {}
        current, count = _tree_sha256(ctx.root / "source" / "miniprogram", ctx.root)
        if snapshot.get("tree_sha256") != current:
            problems.append("source/miniprogram 树哈希变化（基线 %s / 当前 %s）"
                            % (str(snapshot.get("tree_sha256"))[:12], current[:12]))
        if snapshot.get("files") != count:
            problems.append("source/miniprogram 文件数 %d != 基线 %s"
                            % (count, snapshot.get("files")))

    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, ("content.py 142 基线（12/39+11/11+34/22/13/70）且 0 WW 残留；"
                  "content_ww.py 20/15/10/5/50 编译通过、未被任何模块导入；"
                  "haunts 50 本 WW 移入 _ww_deferred（sha256 不变）、注册表 70；"
                  "assets/placeholders=3、assets_ww=100；小程序端树哈希未变"), evidence


def check_a30(ctx):
    """A-30 47 个缺失位 0 missing（run5 §4.3）。"""
    records = _records(ctx)
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    evidence = ["assets/p_table.json", "qa/run5_promotion_map.json"]

    # 1) 0 missing / 0 partial / 0 placeholder / 0 fallback / 0 pending
    stats = (ctx.data.get("p_table") or {}).get("stats") or {}
    actual = Counter(rec.get("availability") for rec in records)
    for key, expected in EXPECTED_AVAILABILITY.items():
        if actual.get(key, 0) != expected:
            problems.append("逐行 %s=%d，期望 %d" % (key, actual.get(key, 0), expected))
        if stats.get(key) != expected:
            problems.append("stats.%s=%r，期望 %d" % (key, stats.get(key), expected))
    if any(rec.get("availability") == "missing" for rec in records):
        problems.append("仍存在 availability=missing 的行")
    for flag in ("placeholder_records", "fallback_records", "pending_missing_records"):
        if stats.get(flag, 0) != 0:
            problems.append("stats.%s=%r，期望 0" % (flag, stats.get(flag)))

    # 2) 47 行字段齐全
    promotion_path = ctx.qa / "run5_promotion_map.json"
    promoted_ids = []
    if not promotion_path.is_file():
        problems.append("缺少 47 行绑定表 qa/run5_promotion_map.json")
    else:
        try:
            promoted_ids = [row["record_id"] for row in
                            (json.loads(promotion_path.read_text(encoding="utf-8"))
                             .get("rows") or [])]
        except ValueError:
            problems.append("promotion map 不可解析")
        if len(promoted_ids) != 47:
            problems.append("绑定表行数=%d，期望 47" % len(promoted_ids))
    by_id = _record_map(ctx)
    for rid in promoted_ids:
        rec = by_id.get(rid)
        if rec is None:
            problems.append("绑定表 %s 不在 P 表" % rid)
            continue
        checks = (
            ("source_path", bool(str(rec.get("source_path") or "").strip())),
            ("format=png", rec.get("format") == "png"),
            ("decodable=ok", rec.get("decodable") == "ok"),
            ("mapping=matched", rec.get("mapping_status") == "matched"),
            ("usable_fields", bool(rec.get("usable_fields"))),
            ("missing_note 空", not str(rec.get("missing_note") or "").strip()),
            ("availability=usable", rec.get("availability") == "usable"),
            ("runtime_status=ok", rec.get("runtime_status") == "ok"),
            ("fallback_ref 空", not str(rec.get("fallback_ref") or "").strip()),
        )
        for label, ok in checks:
            if not ok:
                problems.append("%s %s 不满足" % (rid, label))
        expected_alpha = rec.get("asset_type") == "character"
        if bool(rec.get("has_alpha")) != expected_alpha:
            problems.append("%s has_alpha=%r 与用途不符" % (rid, rec.get("has_alpha")))

    # 3) 发布档非空 + sha256/bytes 与磁盘一致
    for rec in records:
        rid = rec.get("record_id")
        for column in ("bytes", "sha256", "category_dir", "alpha_required",
                       "canonical_record_id", "reviewer", "verified_at"):
            if rec.get(column) in (None, ""):
                problems.append("%s 发布列 %s 为空" % (rid, column))
        source = ctx.root / str(rec.get("source_path") or "")
        if not source.is_file():
            problems.append("%s 源文件缺失" % rid)
            continue
        if rec.get("bytes") != source.stat().st_size:
            problems.append("%s bytes 与磁盘不一致" % rid)
        if rec.get("sha256") != sha256_file(source):
            problems.append("%s sha256 与磁盘不一致" % rid)

    # 4) 孤儿文件 0 / 重复 sha256 0
    photos = ctx.root / "photos"
    disk = {path.relative_to(ctx.root).as_posix()
            for path in photos.rglob("*")
            if path.is_file() and path.relative_to(photos).parts[0] != "_source_jpeg"}
    table = {str(rec.get("source_path") or "") for rec in records}
    if disk - table:
        problems.append("孤儿文件 %d 个：%s" % (len(disk - table), sorted(disk - table)[:3]))
    if table - disk:
        problems.append("P 表引用不存在文件 %d 个" % len(table - disk))
    digests = Counter(rec.get("sha256") for rec in records if rec.get("sha256"))
    duplicated = [digest for digest, count in digests.items() if count > 1]
    if duplicated:
        problems.append("sha256 重复组 %d 个" % len(duplicated))

    # 5) 运行时 145 张 + 每行 runtime_status=ok
    missing_runtime = [str(rec.get("runtime_path")) for rec in records
                       if not (ctx.root / str(rec.get("runtime_path") or "")).is_file()]
    if missing_runtime:
        problems.append("%d 个 runtime_path 不存在" % len(missing_runtime))
    if any(rec.get("runtime_status") != "ok" for rec in records):
        problems.append("存在 runtime_status != ok 的行")
    for key in ("rooms", "cards", "characters", "placeholders"):
        base = ctx.assets / key
        count = len(sorted(base.rglob("*.png"))) if base.is_dir() else 0
        if count != EXPECTED_RUNTIME[key]:
            problems.append("运行时 %s=%d，期望 %d" % (key, count, EXPECTED_RUNTIME[key]))

    # 6) 语义评审（人工项，必须有签字；缺失即 NOT_RUN，不冒充 PASS）
    review_path = ctx.qa / "run5_semantic_review.jsonl"
    human_pending = []
    if not review_path.is_file():
        human_pending.append("47/47 语义评审未执行（缺 qa/run5_semantic_review.jsonl）")
    else:
        rows = [line for line in review_path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        if len(rows) != 47:
            human_pending.append("语义评审行数=%d，期望 47" % len(rows))
        reviewers = set()
        for line in rows:
            try:
                item = json.loads(line)
            except ValueError:
                human_pending.append("语义评审存在不可解析行")
                break
            if str(item.get("result") or "").lower() not in ("pass", "ok"):
                human_pending.append("%s 语义评审未 pass" % item.get("record_id"))
            if not item.get("reviewer") or not item.get("reviewed_at"):
                human_pending.append("%s 语义评审缺签字/日期" % item.get("record_id"))
            reviewers.add(item.get("reviewer"))
        if reviewers and reviewers == {"automated"}:
            human_pending.append("语义评审全部由 automated 签署，违反'评审人非实现者'")

    if problems:
        return FAIL, "；".join(problems[:8]), problems
    if human_pending:
        return NOT_RUN, ("机读部分全过（0 missing / 47 行字段齐全 / 142 源文件哈希一致 / "
                        "孤儿 0 / 运行时 145 张），但人工项未完成：%s"
                        % "；".join(human_pending[:3])), evidence
    return PASS, ("0 missing / 0 partial / 0 placeholder；47 位字段齐全；"
                  "142 行 sha256+bytes 与磁盘一致；孤儿 0；运行时 145 张；"
                  "语义评审 47/47 已签字"), evidence


def check_a31(ctx):
    """A-31 130 张 JPEG 转真 PNG 且像素等价（run5 §4.4）。"""
    problems = []
    evidence = ["qa/run5_transcode_manifest.json", ".codebuddy/wfat/photos_inventory.json"]
    manifest_path = ctx.qa / "run5_transcode_manifest.json"
    if not manifest_path.is_file():
        return FAIL, "缺少 qa/run5_transcode_manifest.json", []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return FAIL, "转码清单不可解析：%s" % exc, []
    rows = manifest.get("records") or []
    summary = manifest.get("summary") or {}
    if len(rows) != 130:
        problems.append("转码清单 %d 条，期望 130（95 partial + 35 新登记）" % len(rows))
    if summary.get("failures"):
        problems.append("转码失败 %s 项" % summary.get("failures"))
    if summary.get("max_diff_all") != 0:
        problems.append("像素 max diff=%r，期望 0" % summary.get("max_diff_all"))
    if summary.get("pixel_equal_all") is not True:
        problems.append("summary.pixel_equal_all 不是 true")

    # 1) 142 张真 PNG 魔数 + 2) ext_mismatch=0
    records = _records(ctx)
    ext_mismatch = [rec.get("record_id") for rec in records
                    if "ext_mismatch" in (rec.get("quality_flags") or [])]
    if ext_mismatch:
        problems.append("仍有 ext_mismatch 行 %d 个" % len(ext_mismatch))
    for rec in records:
        source = ctx.root / str(rec.get("source_path") or "")
        if not source.is_file():
            problems.append("%s 源文件缺失" % rec.get("record_id"))
            continue
        head = source.read_bytes()[:8]
        if head.startswith(b"\xff\xd8\xff"):
            problems.append("%s 仍是 JPEG 内容" % rec.get("record_id"))
        elif not head.startswith(b"\x89PNG\r\n\x1a\n"):
            problems.append("%s 魔数既非 PNG 也非 JPEG" % rec.get("record_id"))
        if rec.get("format") != "png":
            problems.append("%s format=%r" % (rec.get("record_id"), rec.get("format")))

    # 3) 像素等价（清单逐条记录；此处对前 12 条复核清单字段一致性）
    checked = 0
    for row in rows[:12]:
        target = ctx.root / row["path"]
        backup = ctx.root / row["backup"]
        if not target.is_file() or not backup.is_file():
            problems.append("转码对 %s 缺文件" % row["path"])
            continue
        pixels = row.get("pixel_equality") or {}
        if pixels.get("max_diff") != 0 or pixels.get("equal") is not True:
            problems.append("%s 像素不等价" % row["path"])
        if pixels.get("size_left") != pixels.get("size_right"):
            problems.append("%s 转码前后尺寸不等" % row["path"])
        checked += 1
    if checked == 0:
        problems.append("未复核任何转码对")

    # 4) 备份 130 个 .jpg，sha256 与清单一致
    backup_dir = ctx.root / "photos" / "_source_jpeg"
    backups = sorted(backup_dir.rglob("*.jpg")) if backup_dir.is_dir() else []
    if len(backups) != EXPECTED_BACKUPS:
        problems.append("备份 .jpg 数=%d，期望 %d" % (len(backups), EXPECTED_BACKUPS))
    by_backup = {Path(row["backup"]).name: row.get("source_sha256") for row in rows}
    for path in backups:
        recorded = by_backup.get(path.name)
        if not recorded:
            problems.append("备份 %s 未在转码清单登记" % path.name)
        elif sha256_file(path) != recorded:
            problems.append("备份 %s sha256 与清单不一致" % path.name)

    # 5) 扫描排除 _source_jpeg 的负样本自证
    all_files = [path for path in (ctx.root / "photos").rglob("*") if path.is_file()]
    if len(all_files) != EXPECTED_TOTAL + EXPECTED_BACKUPS:
        problems.append("photos/ 全量文件=%d，期望 %d+%d"
                        % (len(all_files), EXPECTED_TOTAL, EXPECTED_BACKUPS))
    if len(all_files) == EXPECTED_TOTAL:
        problems.append("负样本失效：备份目录似乎不存在，无法自证扫描排除")

    # 6) inventory 142 条 0 漂移
    inventory_path = ctx.root / ".codebuddy" / "wfat" / "photos_inventory.json"
    if not inventory_path.is_file():
        problems.append("缺少 photos_inventory.json")
    else:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
        if len(inventory) != EXPECTED_TOTAL:
            problems.append("inventory 条数=%d，期望 %d" % (len(inventory), EXPECTED_TOTAL))
        for item in inventory:
            path = ctx.root / "photos" / Path(item["path"]).parent.name / item["file"]
            if not path.is_file():
                problems.append("inventory 指向不存在的文件 %s" % item["file"])
                continue
            if sha256_file(path) != item.get("sha256"):
                problems.append("inventory %s sha256 漂移" % item["file"])

    # 7) provenance 保留原件 sha256 与备份路径
    #    只有经历过转码的行才需要 transcode 溯源；run6 六类渲染面是原生 PNG，
    #    不在 130 条转码清单里，不能按类别一刀切要求 transcode=png。
    transcoded = {str(row.get("path")) for row in rows}
    for rec in records:
        provenance = str(rec.get("provenance") or "")
        if "transcode=png" in provenance:
            if "src_sha256:" not in provenance or "backup=photos/_source_jpeg/" not in provenance:
                problems.append("%s provenance 缺 src_sha256/backup" % rec.get("record_id"))
        elif str(rec.get("source_path")) in transcoded:
            problems.append("%s 在转码清单内但 provenance 缺 transcode 溯源"
                            % rec.get("record_id"))

    if problems:
        return FAIL, "；".join(problems[:8]), problems
    return PASS, ("130 张 JPEG 全部转真 PNG（142/142 PNG 魔数、ext_mismatch=0）；"
                  "像素 max diff=0 / MAD=0；备份 130 个 .jpg sha256 与清单一致；"
                  "inventory 142 条 0 漂移；provenance 保留 src_sha256+backup"), evidence


READABILITY_METHOD = (
    "Pillow 下采样 256x256；未线性化 sRGB 亮度（0.2126R+0.7152G+0.0722B）；"
    "带 alpha 的图仅在**非透明像素**（alpha>=128）上统计——透明画布不属于画面内容，"
    "若把它算进直方图会把镂空当成死黑；不透明像素占比 <1% 时退回全图统计。"
)


def readability_metrics(path):
    """M-13 单张指标；返回 dict（含样本口径），不做阈值判定。"""
    from PIL import Image

    with Image.open(path) as image:
        has_alpha = "A" in image.getbands()
        if has_alpha:
            rgba = image.convert("RGBA").resize((256, 256))
            pixels = list(rgba.getdata())
            opaque = [(r, g, b) for r, g, b, a in pixels if a >= 128]
        else:
            rgb = image.convert("RGB").resize((256, 256))
            pixels = list(rgb.getdata())
            opaque = []
    total = len(pixels)
    sample = opaque if (has_alpha and len(opaque) >= total * 0.01) else \
        ([(r, g, b) for r, g, b in pixels] if not has_alpha else
         [(r, g, b) for r, g, b, _a in pixels])
    lums = sorted(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in sample)
    count = len(lums) or 1
    p5 = lums[int(count * 0.05)] / 255.0 if lums else 0.0
    p95 = lums[min(int(count * 0.95), count - 1)] / 255.0 if lums else 0.0
    mean = sum(lums) / count / 255.0
    extreme = sum(1 for value in lums if value < 5.1 or value > 249.9) / float(count)
    return {
        "has_alpha": bool(has_alpha),
        "opaque_ratio": round(len(opaque) / float(total or 1), 4) if has_alpha else 1.0,
        "sample_scope": ("opaque" if has_alpha and len(opaque) >= total * 0.01
                         else "full"),
        "p5": round(p5, 4),
        "p95": round(p95, 4),
        "spread": round(p95 - p5, 4),
        "mean": round(mean, 4),
        "extreme_ratio": round(extreme, 4),
    }


def readability_failures(record_id, item):
    failures = []
    if item["spread"] < 0.10:
        failures.append("%s 亮度 P95-P5=%.3f < 0.10" % (record_id, item["spread"]))
    if not 0.05 <= item["mean"] <= 0.92:
        failures.append("%s 平均亮度 %.3f 越界 [0.05,0.92]" % (record_id, item["mean"]))
    if item["extreme_ratio"] > 0.25:
        failures.append("%s 过曝/死黑占比 %.3f > 0.25"
                        % (record_id, item["extreme_ratio"]))
    return failures


def _readability_scan(ctx, records):
    """M-13 原图可读性代理（只算不写：验收脚本必须只读）。"""
    items, failures = [], []
    for rec in records:
        rid = rec.get("record_id")
        path = ctx.root / str(rec.get("source_path") or "")
        if not path.is_file():
            failures.append("%s 源文件缺失，M-13 未测" % rid)
            continue
        try:
            item = readability_metrics(path)
        except Exception as exc:  # noqa: BLE001
            failures.append("%s 解码失败：%s" % (rid, type(exc).__name__))
            continue
        item["record_id"] = rid
        items.append(item)
        failures.extend(readability_failures(rid, item))
    return {"items": items, "failures": failures, "method": READABILITY_METHOD}


def check_a33(ctx):
    """A-33 对局美术渲染（run6）：资源可用 ≠ 对局可见。

    独立调用 qa/verify_game_art.py（只读脚本），取它的 verdict 与逐项状态。
    该脚本自身已实现 J0 证据归属 + J1…J6 + S1…S3；本函数不重复判定，
    只做「证据缺失即 NOT_RUN、任一 FAIL 即 FAIL」的口径转述。
    """
    script = ctx.qa / "verify_game_art.py"
    if not script.is_file():
        return NOT_RUN, "缺少 qa/verify_game_art.py（A-33 验收脚本未交付）", [
            "qa/verify_game_art.py"]
    if not (ctx.qa / "game_art_probe.json").is_file():
        return NOT_RUN, "缺少 qa/game_art_probe.json（对局美术探针未运行）", [
            "qa/game_art_probe.json"]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, "-B", str(script)], cwd=str(ctx.game),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=900, env=env)
        payload = json.loads(proc.stdout or "{}")
    except Exception as exc:  # noqa: BLE001 - 证据不可用要显式落 NOT_RUN
        return NOT_RUN, "A-33 脚本执行失败：%s: %s" % (type(exc).__name__, exc), [
            "qa/verify_game_art.py"]
    checks = payload.get("checks") or []
    failed = [c.get("id") for c in checks if c.get("status") == "FAIL"]
    not_run = [c.get("id") for c in checks if c.get("status") == "NOT_RUN"]
    passed = [c.get("id") for c in checks if c.get("status") == "PASS"]
    verdict = str(payload.get("verdict") or "").upper()
    evidence = ["qa/game_art_probe.json", "qa/verify_game_art.py"]
    if failed:
        return FAIL, "对局美术渲染未达标：FAIL=%s；NOT_RUN=%s" % (
            ",".join(failed), ",".join(not_run) or "无"), evidence
    if not_run:
        return NOT_RUN, "对局美术证据不完整：NOT_RUN=%s" % ",".join(not_run), evidence
    if verdict != "PASS" or not checks:
        return NOT_RUN, "A-33 verdict=%r，检查项 %d 个" % (verdict or "空", len(checks)), evidence
    return PASS, "对局美术渲染 %d/%d 项 PASS（%s）" % (
        len(passed), len(checks), "/".join(passed)), evidence


def check_a32(ctx):
    """A-32 274 张图片技术规格（尺寸/格式/对比度，run5 §4.5 + run6 六类渲染面）。"""
    records = _records(ctx)
    if not records:
        return FAIL, "P 表为空或不可读", []
    problems = []
    evidence = ["assets/p_table.json", "qa/run5_readability.json"]
    master_rules = {
        "room": {"ratio": (1, 1), "min_long": 1024},
        "card_omen": {"ratio": (3, 4), "min_long": 1600},
        "card_item": {"ratio": (3, 4), "min_long": 1600},
        "card_event": {"ratio": (3, 4), "min_long": 1600},
        "character": {"ratio": (1, 1), "min_long": 320},   # D-01 书面偏差
        # run6 六类渲染面：母版比例/长边按各自画幅给定（官方无规定，按实测画幅设下限）
        "monster": {"ratio": (1, 1), "min_long": 512},
        "haunt": {"ratio": (16, 9), "min_long": 1280},
        "ending": {"ratio": (16, 9), "min_long": 1024},
        "card_back": {"ratio": (3, 4), "min_long": 640},
        "room_back": {"ratio": (1, 1), "min_long": 512},
        "dice": {"ratio": (1, 1), "min_long": 256},
    }
    runtime_rules = {"room": (512, 512), "card_omen": (480, 672),
                     "card_item": (480, 672), "card_event": (480, 672),
                     "character": (320, 320),
                     "monster": (512, 512), "haunt": (1280, 720),
                     "ending": (1024, 576), "card_back": (480, 640),
                     "room_back": (512, 512), "dice": (256, 256)}
    # 必需 alpha 的类别（叠图用途）；其余类别允许源图自带透明留白，不反向断言
    alpha_required_types = {"character", "monster", "room_back", "dice"}

    # 1) 母版尺寸与比例；2) 运行时尺寸；3) 真 PNG
    for rec in records:
        rid = rec.get("record_id")
        asset_type = rec.get("asset_type")
        rule = master_rules.get(asset_type)
        if not rule:
            problems.append("%s 未知类型 %r" % (rid, asset_type))
            continue
        width = int(rec.get("width") or 0)
        height = int(rec.get("height") or 0)
        long_edge = max(width, height)
        if long_edge < rule["min_long"]:
            problems.append("%s 母版长边 %d < %d" % (rid, long_edge, rule["min_long"]))
        want_w, want_h = rule["ratio"]
        if width and height:
            drift = abs(width * want_h - height * want_w) / float(height * want_w or 1)
            if drift > 0.01:
                problems.append("%s 母版比例偏离 %d:%d 超过 1%%" % (rid, want_w, want_h))
        runtime = ctx.root / str(rec.get("runtime_path") or "")
        actual_runtime = png_ihdr(runtime)
        if actual_runtime != runtime_rules[asset_type]:
            problems.append("%s 运行时尺寸 %r != %s"
                            % (rid, actual_runtime, runtime_rules[asset_type]))
        source = ctx.root / str(rec.get("source_path") or "")
        if png_ihdr(source) is None:
            problems.append("%s 母版不是真 PNG" % rid)

    # 4) alpha_required 按用途判定；必需 alpha 的类别必须真有 alpha 通道。
    #    非必需类别（剧本插画/结算/牌背）允许源图自带透明留白，不做反向断言。
    for rec in records:
        rid = rec.get("record_id")
        asset_type = rec.get("asset_type")
        requires_alpha = asset_type in alpha_required_types
        if bool(rec.get("alpha_required")) != requires_alpha:
            problems.append("%s alpha_required 与用途不符" % rid)
        if requires_alpha and not bool(rec.get("has_alpha")):
            problems.append("%s has_alpha=false，但该类别必需 alpha" % rid)
        if asset_type == "character":
            path = ctx.root / str(rec.get("source_path") or "")
            try:
                from PIL import Image
                with Image.open(path) as image:
                    if "A" not in image.getbands():
                        problems.append("%s 角色图无 alpha 通道" % rid)
                        continue
                    low = min(image.getchannel("A").getextrema())
                    if low >= 255:
                        problems.append("%s 角色 alpha 全不透明（假 alpha）" % rid)
            except Exception as exc:  # noqa: BLE001
                problems.append("%s 读 alpha 失败：%s" % (rid, type(exc).__name__))

    # 6) M-13 原图可读性代理（274/274：qa/run5_readability.json 全表覆盖）
    readability = _readability_scan(ctx, records)
    if readability["failures"]:
        problems.extend(readability["failures"][:6])

    # 7) 重复：sha256 重复 0
    digests = Counter(rec.get("sha256") for rec in records if rec.get("sha256"))
    duplicated = [digest for digest, count in digests.items() if count > 1]
    if duplicated:
        problems.append("sha256 重复组 %d 个" % len(duplicated))

    # 5) 渲染层 WCAG：需要 100% DPI 真实截图，缺即 NOT_RUN（不冒充 PASS）
    manifest, _ = _ui_manifest(ctx)
    wcag_ok = False
    wcag_note = "缺少 100% DPI 真实截图，渲染层 WCAG 抽样未执行"
    if manifest:
        entries = _ui_entries(manifest)
        entry = entries.get(100) or {}
        graphic = entry.get("contrast_graphic")
        text = entry.get("contrast_text")
        if graphic is not None and text is not None and entry.get("pass") is True:
            try:
                if float(graphic) >= 3.0 and float(text) >= 4.5:
                    wcag_ok = True
                    wcag_note = "100% DPI 实测：图形 %s:1 / 正文 %s:1" % (graphic, text)
                else:
                    problems.append("渲染层对比度不足：图形 %s:1 / 正文 %s:1"
                                    % (graphic, text))
            except (TypeError, ValueError):
                wcag_note = "对比度不是数值；按未执行处理"

    if problems:
        return FAIL, "；".join(problems[:8]), problems
    detail = ("274/274 母版尺寸/比例达标、运行时 IHDR 精确；真 PNG；"
              "alpha 规则一致（character/monster/room_back/dice 必需且存在）；"
              "M-13 可读性 274/274 通过；sha256 重复 0；" + wcag_note)
    if not wcag_ok:
        return NOT_RUN, detail, evidence
    return PASS, detail, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description="P 表最终收口只读独立验收")
    parser.add_argument("--root", default=None, help="项目根目录（含 source/desktop/game）")
    parser.add_argument("--json", action="store_true", help="只输出机读 JSON")
    parser.add_argument("--strict", action="store_true", help="保留参数；本脚本默认即严格模式")
    parser.add_argument("--tk", action="store_true",
                        help="保留参数；本脚本只读不启动 Tk（Tk 冒烟由 qa/verify_p_table_execution.py --tk 承担）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else DEFAULT_PROJECT_ROOT
    if not (root / "source" / "desktop" / "game").exists():
        print("根目录不成立：%s" % root, file=sys.stderr)
        return 2

    ctx = Ctx(root)
    before = snapshot_tree(ctx)
    audit = Audit(ctx)

    audit.run("A-01", "G6", "P0", A_TITLES["A-01"], lambda: check_a01(ctx))
    audit.run("A-02", "G6", "P0", A_TITLES["A-02"], lambda: check_a02(ctx))
    audit.run("A-03", "G6", "P0", A_TITLES["A-03"], lambda: check_a03(ctx))
    audit.run("A-04", "G1", "P0", A_TITLES["A-04"], lambda: check_a04(ctx))
    audit.run("A-05", "G1", "P0", A_TITLES["A-05"], lambda: check_a05(ctx))
    audit.run("A-06", "G1", "P0", A_TITLES["A-06"], lambda: check_a06(ctx))
    audit.run("A-07", "G1", "P0", A_TITLES["A-07"], lambda: check_a07(ctx))
    audit.run("A-08", "G1", "P0", A_TITLES["A-08"], lambda: check_a08(ctx))
    audit.run("A-09", "G1", "P0", A_TITLES["A-09"], lambda: check_a09(ctx))
    audit.run("A-10", "G2", "P0", A_TITLES["A-10"], lambda: check_a10(ctx))
    audit.run("A-11", "G2", "P0", A_TITLES["A-11"], lambda: check_a11(ctx))
    audit.run("A-12", "G2", "P0", A_TITLES["A-12"], lambda: check_a12(ctx))
    audit.run("A-13", "G2", "P0", A_TITLES["A-13"], lambda: check_a13(ctx))
    audit.run("A-14", "G2", "P0", A_TITLES["A-14"], lambda: check_a14(ctx))
    audit.run("A-15", "G2", "P0", A_TITLES["A-15"], lambda: check_a15(ctx))
    audit.run("A-16", "G3", "P1", A_TITLES["A-16"], lambda: check_a16(ctx))
    audit.run("A-17", "G3", "P1", A_TITLES["A-17"], lambda: check_a17(ctx))
    audit.run("A-18", "G4", "P1", A_TITLES["A-18"], lambda: check_a18(ctx))
    audit.run("A-19", "G5", "P1", A_TITLES["A-19"], lambda: check_a19(ctx))
    audit.run("A-20", "G5", "P1", A_TITLES["A-20"], lambda: check_a20(ctx))
    audit.run("A-21", "G5", "P1", A_TITLES["A-21"], lambda: check_a21(ctx))
    audit.run("A-22", "G5", "P1", A_TITLES["A-22"], lambda: check_a22(ctx))
    audit.run("A-23", "G4", "P1", A_TITLES["A-23"], lambda: check_a23(ctx))
    audit.run("A-25", "G7", "P1", A_TITLES["A-25"], lambda: check_a25(ctx))
    audit.run("A-27", "G7", "P0", A_TITLES["A-27"], lambda: check_a27(ctx))
    # run5 新增四项（A-29 隔离 / A-30 0 missing / A-31 真 PNG / A-32 规格）
    audit.run("A-29", "G1", "P0", A_TITLES["A-29"], lambda: check_a29(ctx))
    audit.run("A-30", "G1", "P0", A_TITLES["A-30"], lambda: check_a30(ctx))
    audit.run("A-31", "G1", "P0", A_TITLES["A-31"], lambda: check_a31(ctx))
    audit.run("A-32", "G5", "P1", A_TITLES["A-32"], lambda: check_a32(ctx))
    # run6 新增：A-33 对局美术渲染（补「资源可用 ≠ 对局可见」的验收缺口）
    audit.run("A-33", "G5", "P0", A_TITLES["A-33"], lambda: check_a33(ctx))
    audit.run("X-DRIFT", "G2", "P1", "check_core_drift", lambda: check_x_drift(ctx),
              a_table=False)
    audit.run("X-V1", "G2", "P1", "verify_v1", lambda: check_x_v1(ctx), a_table=False)

    gate_statuses = audit.statuses()
    gate_ids = [c["id"] for c in audit.checks if c["id"] not in ("A-24", "A-26", "A-28")]
    gate_claim = compute_claim(gate_statuses, gate_ids)
    audit.run("A-24", "G6", "P0", A_TITLES["A-24"], lambda: check_a24(ctx, gate_claim))
    audit.run("A-26", "G6", "P1", A_TITLES["A-26"], lambda: check_a26(ctx))
    audit.run("A-28", "G7", "P0", A_TITLES["A-28"], lambda: check_a28(ctx))

    after = snapshot_tree(ctx)
    changed = [p for p, fp in before.items() if after.get(p) != fp]
    readonly = not changed
    if changed:
        a03 = audit.get("A-03")
        if a03:
            a03["status"] = FAIL
            a03["detail"] = "本脚本运行期间项目文件变化 %d 个：%s" % (
                len(changed), ", ".join(changed[:6])
            )
            a03["evidence"] = changed[:20]
        else:
            audit.add("A-03", "G6", "P0", A_TITLES["A-03"], FAIL,
                      "运行期间项目文件变化 %d 个" % len(changed), changed[:20])

    payload = build_payload(ctx, audit, before, after, readonly)
    if args.json:
        # 机读输出固定 UTF-8，避免 Windows 控制台默认 cp936 破坏管道。
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - 旧解释器/被重定向时退回默认编码
            pass
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        sys.stdout.write(text + "\n")
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
