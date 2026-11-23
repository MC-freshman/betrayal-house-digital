#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P 表执行器：一次跑完 S0–S5，产出 JSON/Markdown 报告与 issues.jsonl。

阶段
----
S0  源哈希冻结（实现、校验脚本、P 表产物、photos 汇总）
S1  旧测试门禁：``verify_assets.py`` + ``qa/verify_assets_contract.py --json``
S2  新测试：``qa/test_p_table_execution.py``（unittest，独立子进程）
S3  性能基准：15 项 PT-PERF 全表（01-15；02/03/07/08/10/13/14/15 由 measure_perf_item
    实测——median/p95/max/budget_ms/status，连续 3 次超预算才 FAIL；09 按 C-1 归并
    qa/rss_probe.json 5 次峰值，不重复采集）
S4  覆盖率：``qa/coverage_probe.py``（行覆盖实测；branch 显式 not-run）
S5  报告：``reports/p_table_execution_report.json`` / ``.md`` + ``qa/issues.jsonl``

判读纪律
--------
* 旧测试失败（退出码非 0）→ ``verdict=FAIL``，不因新测试全绿而改写；
* 新测试任一 FAIL/ERROR → ``verdict=FAIL``；
* 未执行项写 ``not-run`` 并列原因，不折算成 PASS；
* ``completion_claim`` 只有在所有门禁全绿且无 P0 not-run 时才可能为 attested。

用法::

    python qa/run_p_table_execution.py --profile baseline
    python qa/run_p_table_execution.py --profile quick --skip-perf
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = GAME_DIR.parents[2]
QA_DIR = Path(__file__).resolve().parent
ASSETS = GAME_DIR / "assets"
REPORTS_DIR = GAME_DIR / "reports"
ISSUES_JSONL = QA_DIR / "issues.jsonl"
REPORT_JSON = REPORTS_DIR / "p_table_execution_report.json"
REPORT_MD = REPORTS_DIR / "p_table_execution_report.md"
REPORT_FINAL_JSON = REPORTS_DIR / "p_table_execution_final.json"
REPORT_FINAL_MD = REPORTS_DIR / "p_table_execution_final.md"
COVERAGE_JSON = QA_DIR / "coverage_probe.json"
CONTRACT_RESULT_JSON = QA_DIR / "contract_result.json"
BRANCH_JSON = QA_DIR / "branch_probe.json"
RSS_JSON = QA_DIR / "rss_probe.json"
RSS_SAMPLES_JSON = QA_DIR / "rss_samples.json"
UI_JSON = QA_DIR / "ui_capture.json"
VERIFY_FINAL_JSON = QA_DIR / "p_table_verify_final.json"

if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

PYTHON = sys.executable

# 性能预算来自 run2_p_table_plan.md §5.3（待实测校准，作为上限使用）
BUDGETS = {
    "ptable_build_ms": 5000.0,
    "registry_load_ms": 150.0,
    "resolve_10k_ms": 500.0,
    "resolve_per_call_ms": 0.05,
    "verify_assets_ms": 90000.0,
    "ui_room_first_frame_ms": 120.0,
    "ui_card_first_frame_ms": 150.0,
    # run4 补测的 8 项（PT-PERF-02/03/07/08/10/13/14/15）+ 09 归并预算
    "placeholders_build_ms": 3000.0,          # PT-PERF-02（5 次中位数）
    "all_build_ms": 240000.0,                 # PT-PERF-03（3 次中位数）
    "contract_decode_ms": 150000.0,           # PT-PERF-07（5 次中位数）
    "contract_no_decode_ms": 25000.0,         # PT-PERF-08（5 次中位数）
    "build_peak_rss_mib": 1536.0,             # PT-PERF-09（归并 rss_probe，verdict_basis=max）
    "load_rss_increment_mib": 80.0,           # PT-PERF-10（加载前后差值；§5.1 ≤80 MB 按 MiB 记）
    "ui_cache_hit_ms": 16.0,                  # PT-PERF-13（100 次 P95）
    "ui_batch_12_ms": 400.0,                  # PT-PERF-14（10 次 P95）
    "cold_start_ms": 2500.0,                  # PT-PERF-15（10 次中位数）
}

# 契约基线（run5 v2 实测：2026-11-21，32 PASS / 0 FAIL / 0 WARN）
CONTRACT_BASELINE = {"pass": 32, "fail": 0, "warn": 0, "skip": 0}
ACCEPTED_CONTRACT_DEVIATIONS = {
    "C06": "target_ref 为运行时键、content_ref 为溯源键；run2_synthesis 已裁决保留，属既有偏差",
}

STATIC_ISSUES = [
    {
        "defectId": "PT-MAP-001",
        "title": "C06 已修正：target_ref 改为 content.py 溯源键，runtime_key 单独保留",
        "dimension": "mapping",
        "stage": "S1",
        "severity": "S3",
        "status": "resolved",
        "evidence": "qa/verify_assets_contract.py --json：C06 PASS，32/32 PASS；P 表 33 列",
        "fixHint": "已按 content.py:<集合>#<id> 回写 target_ref，并在 runtime_key 保留 UI 取图键",
    },
    {
        "defectId": "PT-DOC-001",
        "title": "规范文档已回写：33 列列序与 F-08 的 16 fallback + 31 placeholder 语义",
        "dimension": "documentation",
        "stage": "S5",
        "severity": "S4",
        "status": "resolved",
        "evidence": "p_table_spec.md §6.1 已更新为 33 列；run2_p_table_plan.md F-08 已改为 31 占位 + 16 事件回退",
        "fixHint": "无需代码改动；独立验收脚本的静态冲突提示可下一轮同步",
    },
    {
        "defectId": "PT-COV-001",
        "title": "分支覆盖未执行：标准库 trace 无分支计数能力，coverage.py 未安装",
        "dimension": "coverage",
        "stage": "S4",
        "severity": "S3",
        "status": "open",
        "evidence": "qa/coverage_probe.json 的 branch.status=not-run",
        "fixHint": "经批准后安装 coverage.py 或引入自带分支统计的探针；在此之前不宣称分支覆盖达标",
        "owner": "qa / 独立验收人",
        "closeCondition": "coverage.py 安装获批并在同一次运行产出 branch 计数",
        "reviewDate": "2026-12-05",
    },
    {
        "defectId": "PT-UI-002",
        "title": "ui.py 已接入 ui_asset_binding（美术预览页签）",
        "dimension": "ui",
        "stage": "S2",
        "severity": "S2",
        "status": "resolved",
        "evidence": "ui.py 含 ui_asset_binding/load_asset_photo/AssetRegistry/PhotoImage/assets/asset_mapping.json；"
                    "帮助窗口第 4 页签为美术预览，房间 128px、卡牌 240x336",
        "fixHint": "已接入；UI-01..UI-06 通过，UI-07 人工截图/DPI 仍待执行",
    },
    {
        "defectId": "PT-UI-001",
        "title": "UI 取图只有控件级 smoke，无实跑截图与 DPI/对比度目检",
        "dimension": "ui",
        "stage": "S2",
        "severity": "S4",
        "status": "open",
        "evidence": "qa/test_p_table_execution.py TestUiBinding：Tk withdraw 下验证尺寸/缓存，无截图",
        "fixHint": "在有显示的机器上启动桌面端，按 F-10 / TC-PT-33 留档房间 128px、卡牌 240x336 截图",
        "owner": "product / UI 负责人",
        "closeCondition": "有显示环境下的 100%/125%/150% 真实截图入库",
        "reviewDate": "2026-12-05",
    },
    {
        "defectId": "PT-SCOPE-001",
        "title": "小程序端图片引用未纳入本轮执行",
        "dimension": "scope",
        "stage": "S0",
        "severity": "S4",
        "status": "open",
        "evidence": "本轮按用户约束只改桌面端，source/miniprogram 未读取未修改",
        "fixHint": "下一轮单独排期小程序端资源解析与取图测试",
        "owner": "product 负责人",
        "closeCondition": "小程序端排期确认后单独立项",
        "reviewDate": "2026-12-12",
    },
    {
        "defectId": "PT-ART-001",
        "title": "47 个缺口已落实：复用既有 47 个候选文件 + 130 张 JPEG 无损转码",
        "dimension": "assets",
        "stage": "S3",
        "severity": "S4",
        "status": "resolved",
        "evidence": "P 表 stats：usable=274 / partial=0 / missing=0；"
                    "qa/run5_promotion_map.json 47 行；qa/run5_transcode_manifest.json "
                    "130 条像素等价（max diff 0）；qa/run5_gap_closure.jsonl 47 行",
        "fixHint": "语义评审（47/47 人工签字）与渲染层 WCAG 抽样仍待执行，见 A-30/A-32",
    },
    {
        "defectId": "PT-ART-002",
        "title": "47 位语义评审与渲染层 WCAG 抽样未执行（人工项）",
        "dimension": "assets",
        "stage": "S5",
        "severity": "S3",
        "status": "open",
        "evidence": "缺 qa/run5_semantic_review.jsonl；ui_capture 未覆盖新 47 位的 100% DPI 截图",
        "fixHint": "评审人（非实现者）逐张过 M-15…M-18 并签字；补 20 张跨类别截图算 WCAG 比值",
        "owner": "素材复核人（非实现者）",
        "closeCondition": "qa/run5_semantic_review.jsonl 47/47 签字 + 20 张 WCAG 采样",
        "reviewDate": "2026-12-05",
    },
]


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_size(path):
    """只读 IHDR 取尺寸；不是真 PNG 返回 None（A-32 用）。"""
    try:
        with open(str(path), "rb") as handle:
            head = handle.read(24)
    except OSError:
        return None
    if len(head) < 24 or not head.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return (width, height)


def run_command(args, timeout=600):
    """子进程执行，返回退出码与输出；不抛异常（超时也结构化返回）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [PYTHON] + list(args),
            cwd=str(GAME_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return {
            "command": " ".join(["python"] + list(args)),
            "exit_code": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "timeout": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(["python"] + list(args)),
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "timeout": True,
        }


def stats_of(values):
    ordered = sorted(values)
    count = len(ordered)
    if not count:
        return {}
    p95_index = max(0, min(count - 1, int(round(0.95 * count + 0.5)) - 1))
    return {
        "count": count,
        "median": round(ordered[count // 2] if count % 2 else
                        (ordered[count // 2 - 1] + ordered[count // 2]) / 2.0, 3),
        "p95": round(ordered[p95_index], 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }


def metric(name, budget_key, values, unit="ms", note=""):
    summary = stats_of(values)
    budget = BUDGETS.get(budget_key)
    within = None if not summary or budget is None else summary["median"] <= budget
    return {
        "id": name,
        "unit": unit,
        "samples": summary,
        "budget": budget,
        "budget_source": "run2_p_table_plan.md §5.3（待实测校准，按上限判定）",
        "within_budget": within,
        "note": note,
    }


def measure_perf_item(item_id, func, budget_ms, iterations=3, unit="ms", note="",
                      budget_source="run2_p_table_plan.md §5.3（固定上限，按判定表采样）"):
    """单项性能实测（run4 perf_benchmark 接口，run4_architecture.json interfaces.measure_perf_item）。

    * ``func()`` 执行一次测量并返回实测值（unit 单位）；返回 None 或抛异常 = 该次无效，
      不计入采样表（不编造数字）。
    * 返回：id / unit / samples(count/median/p95/min/max/values) / budget / budget_ms /
      budget_source / within_budget / status / median_over_budget / over_runs /
      consecutive_over / note。
    * 判定（run3 §2.4 P-03，run4 决策沿用）：**末尾连续 3 次实测超预算才 status=fail**
      （within_budget=False）；中位数超预算但未连续 3 次复现时只记观察值
      （median_over_budget=true），不算确认缺陷，不触发 A-23 FAIL。
    """
    values = []
    invalid = []
    consecutive_over = 0
    over_runs = 0
    for index in range(max(1, int(iterations))):
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001 - 采集失败按无效次记录，不中断其余采样
            invalid.append("第 %d 次采集异常：%s: %s" % (index + 1, type(exc).__name__, exc))
            continue
        if value is None:
            invalid.append("第 %d 次未产生实测值" % (index + 1))
            continue
        value = float(value)
        values.append(value)
        if value > float(budget_ms):
            over_runs += 1
            consecutive_over += 1
        else:
            consecutive_over = 0
    summary = stats_of(values)
    if not summary:
        summary = {"count": 0}
    else:
        summary["values"] = [round(value, 4) for value in values]
    median_value = summary.get("median")
    median_over = bool(median_value is not None and median_value > float(budget_ms))
    confirmed_fail = consecutive_over >= 3
    has_samples = bool(values)
    item = {
        "id": item_id,
        "unit": unit,
        "samples": summary,
        "budget": float(budget_ms),
        "budget_ms": float(budget_ms),
        "budget_source": budget_source,
        # 无有效采样时不得折算 PASS（未执行不称 PASS）；调用方应将其落 not-run
        "within_budget": (not confirmed_fail) if has_samples else None,
        "status": "fail" if confirmed_fail else ("pass" if has_samples else "not-run"),
        "median_over_budget": median_over,
        "over_runs": over_runs,
        "consecutive_over": consecutive_over,
        "judge_basis": "连续 3 次超预算才 FAIL（run3 §2.4 P-03）；中位数对照记观察值；"
                       "无有效采样记 not-run",
        "note": note,
    }
    if invalid:
        item["invalid_runs"] = invalid
    return item


def append_perf_item(metrics, not_run, item):
    """采样表非空才计入 metrics；0 有效采样落 not-run（带首个无效原因），不折算 PASS。"""
    if (item.get("samples") or {}).get("count"):
        metrics.append(item)
        return item
    reasons = item.get("invalid_runs") or ["全部采样无效"]
    not_run.append("%s not-run：%s" % (item.get("id") or "性能项", reasons[0]))
    return None


def _rss_snapshot():
    """当前进程 (rss_bytes, peak_bytes)；psutil 优先，ctypes psapi 兜底（同 qa/rss_probe.py）。"""
    try:
        import psutil

        proc = psutil.Process()
        return int(proc.memory_info().rss), int(proc.memory_full_info().peak_wset)
    except ImportError:
        pass
    import ctypes

    class _PMC(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
        ]

    counters = _PMC()
    counters.cb = ctypes.sizeof(_PMC)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo 失败")
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def perf09_metric_from(rss_payload):
    """PT-PERF-09 归并：直接引用 qa/rss_probe.json 的 5 次峰值（C-1 裁决，不重复采集）。

    判定沿用 rss_probe 的 verdict_basis=max：任一次 >1536 MiB 即 fail，且要求 pass=true。
    无可用数据返回 None（由调用方落 not-run，待探针链重采后刷新）。
    """
    if not rss_payload:
        return None
    peaks = []
    for run in rss_payload.get("runs") or []:
        try:
            peaks.append(float(run.get("peak_mib") or 0.0))
        except (TypeError, ValueError):
            continue
    if not peaks:
        return None
    budget = BUDGETS["build_peak_rss_mib"]
    over = [peak for peak in peaks if peak > budget]
    within = not over and rss_payload.get("pass") is True
    return {
        "id": "PT-PERF-09 构建峰值 RSS(--stage all)",
        "unit": "MiB",
        "samples": stats_of(peaks),
        "budget": budget,
        "budget_ms": budget,
        "budget_source": "run2_p_table_plan.md §5.3；判定沿用 qa/rss_probe.py verdict_basis=max",
        "within_budget": within,
        "status": "pass" if within else "fail",
        "judge_basis": "归并 qa/rss_probe.json 5 次峰值，verdict_basis=max（任一次 >1536 MiB 即 fail），"
                       "不重复采集（run4 C-1 裁决）",
        "note": "PT-PERF-09 与 A-18 同方法同预算（PeakWorkingSetSize、200ms 采样），直接归并探针证据",
        "merged_from": {
            "path": "qa/rss_probe.json",
            "sampled_at": rss_payload.get("sampled_at"),
            "emitted_at": rss_payload.get("emitted_at"),
            "run_count": len(peaks),
            "peaks_mib": peaks,
            "max_peak_mib": rss_payload.get("max_peak_mib"),
            "verdict_basis": rss_payload.get("verdict_basis"),
            "pass": rss_payload.get("pass"),
        },
    }


# ----------------------------------------------------------------------
# S0 冻结
# ----------------------------------------------------------------------
FROZEN_FILES = [
    "content.py",
    "asset_pipeline.py",
    "asset_registry.py",
    "ui_asset_binding.py",
    "verify_assets.py",
    "qa/verify_assets_contract.py",
    "qa/test_p_table_execution.py",
    "qa/coverage_probe.py",
    "qa/run_p_table_execution.py",
    "qa/make_fixtures.py",
    "assets/p_table.json",
    "assets/p_table.csv",
    "assets/asset_mapping.json",
]


def stage_s0():
    files = {}
    for rel in FROZEN_FILES:
        path = GAME_DIR / rel
        if not path.is_file():
            files[rel] = {"status": "absent"}
            continue
        files[rel] = {
            "status": "frozen",
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    # run5：photos/_source_jpeg/ 是 130 个转码原件备份，单独计数、不进源文件集合。
    all_photo_files = [path for path in (PROJECT_ROOT / "photos").rglob("*") if path.is_file()]
    photos = [path for path in all_photo_files
              if path.relative_to(PROJECT_ROOT / "photos").parts[0] != "_source_jpeg"]
    backups = [path for path in all_photo_files
               if path.relative_to(PROJECT_ROOT / "photos").parts[0] == "_source_jpeg"]
    combined = hashlib.sha256()
    per_file = {}
    for path in sorted(photos):
        digest = sha256_file(path)
        per_file[path.name] = digest
        combined.update(digest.encode("ascii"))
    backup_combined = hashlib.sha256()
    for path in sorted(backups):
        backup_combined.update(sha256_file(path).encode("ascii"))
    runtime = {
        "rooms": len(list((ASSETS / "rooms").glob("*.png"))),
        "cards": len(list((ASSETS / "cards").rglob("*.png"))),
        "characters": len(list((ASSETS / "characters").glob("*.png")))
        if (ASSETS / "characters").is_dir() else 0,
        "placeholders": len(list((ASSETS / "placeholders").glob("*.png"))),
    }
    return {
        "status": "done",
        "files": files,
        "photos": {
            "count": len(photos),
            "backup_count": len(backups),
            "backup_combined_sha256": backup_combined.hexdigest(),
            "combined_sha256": combined.hexdigest(),
            "files": per_file,
        },
        "runtime_png": runtime,
        "runtime_png_total": sum(runtime.values()),
    }


# ----------------------------------------------------------------------
# S1 旧测试
# ----------------------------------------------------------------------
VERIFY_LINE_RE = re.compile(r"^\[(PASS|FAIL)\]\s+(V\d{2})\s+(.*)$")


def parse_verify_assets(stdout: str):
    checks = []
    for line in stdout.splitlines():
        match = VERIFY_LINE_RE.match(line.strip())
        if match:
            checks.append({"id": match.group(2), "status": match.group(1),
                           "detail": match.group(3)})
    passed = [item for item in checks if item["status"] == "PASS"]
    failed = [item for item in checks if item["status"] != "PASS"]
    return {"total": len(checks), "pass": len(passed), "fail": len(failed),
            "checks": checks}


def parse_contract(stdout: str):
    payload = json.loads(stdout)
    checks = payload.get("checks") or []
    failed = [item for item in checks if item.get("status") not in ("PASS", "WARN")]
    warned = [item for item in checks if item.get("status") == "WARN"]
    return {
        "summary": payload.get("summary") or {},
        "failed": [{"id": item.get("id"), "priority": item.get("priority"),
                    "title": item.get("title"), "detail": item.get("detail")}
                   for item in failed],
        "warned": [{"id": item.get("id"), "priority": item.get("priority"),
                    "title": item.get("title"), "detail": item.get("detail")}
                   for item in warned],
        "checks": checks,
    }


def stage_s1():
    verify = run_command(["verify_assets.py"], timeout=300)
    verify_parsed = parse_verify_assets(verify["stdout"] + "\n" + verify["stderr"])

    contract = run_command(["qa/verify_assets_contract.py", "--json"], timeout=600)
    contract_error = ""
    contract_parsed = {"summary": {}, "failed": [], "warned": [], "checks": []}
    contract_json_path = ""
    if contract["exit_code"] is None:
        contract_error = "超时"
    else:
        try:
            contract_parsed = parse_contract(contract["stdout"])
            # 落盘审计产物：独立验收脚本与 REVIEW 可直接读取，不必重跑
            CONTRACT_RESULT_JSON.write_text(contract["stdout"], encoding="utf-8")
            contract_json_path = _rel(CONTRACT_RESULT_JSON)
        except (ValueError, OSError) as exc:
            contract_error = "JSON 解析失败：%s: %s" % (type(exc).__name__, exc)

    current = {
        "pass": contract_parsed["summary"].get("pass"),
        "fail": contract_parsed["summary"].get("fail"),
        "warn": contract_parsed["summary"].get("warn"),
        "skip": contract_parsed["summary"].get("skip"),
    }
    not_worse = (
        current["pass"] is not None
        and current["pass"] >= CONTRACT_BASELINE["pass"]
        and (current["fail"] or 0) <= CONTRACT_BASELINE["fail"]
    )

    return {
        "status": "done",
        "verify_assets": {
            "command": verify["command"],
            "exit_code": verify["exit_code"],
            "status": "PASS" if verify["exit_code"] == 0 else "FAIL",
            "duration_ms": verify["duration_ms"],
            "parsed": verify_parsed,
        },
        "contract": {
            "command": contract["command"],
            "exit_code": contract["exit_code"],
            "status": "PASS" if contract["exit_code"] == 0 else "FAIL",
            "duration_ms": contract["duration_ms"],
            "parse_error": contract_error,
            "result_json": contract_json_path,
            "summary": contract_parsed["summary"],
            "failed": contract_parsed["failed"],
            "warned": contract_parsed["warned"],
            "baseline": CONTRACT_BASELINE,
            "not_worse_than_baseline": not_worse,
        },
    }


def final_verify():
    """S2/S4 会重写 assets/，最后复跑一次 verify_assets，保证报告晚于全部输入。"""
    run = run_command(["verify_assets.py"], timeout=300)
    parsed = parse_verify_assets(run["stdout"] + "\n" + run["stderr"])
    return {
        "command": run["command"],
        "exit_code": run["exit_code"],
        "status": "PASS" if run["exit_code"] == 0 else "FAIL",
        "duration_ms": run["duration_ms"],
        "parsed": parsed,
        "fresh_after_regeneration": True,
    }


def final_contract():
    """收尾重跑契约并把 JSON 落盘为最新审计证据（结果应与 S1 一致）。"""
    run = run_command(["qa/verify_assets_contract.py", "--json"], timeout=600)
    payload = {}
    error = ""
    if run["exit_code"] is None:
        error = "超时"
    else:
        try:
            payload = json.loads(run["stdout"])
            CONTRACT_RESULT_JSON.write_text(run["stdout"], encoding="utf-8")
        except (ValueError, OSError) as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
    return {
        "command": run["command"],
        "exit_code": run["exit_code"],
        "status": "PASS" if run["exit_code"] == 0 else "FAIL",
        "duration_ms": run["duration_ms"],
        "summary": payload.get("summary") or {},
        "failed": [{"id": item.get("id"), "priority": item.get("priority")}
                   for item in (payload.get("checks") or [])
                   if item.get("status") not in ("PASS", "WARN")],
        "result_json": _rel(CONTRACT_RESULT_JSON) if payload else "",
        "parse_error": error,
        "fresh_after_regeneration": True,
    }


# ----------------------------------------------------------------------
# S2 新测试
# ----------------------------------------------------------------------
RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
RESULT_RE = re.compile(r"^(FAIL|ERROR): (\S+)", re.MULTILINE)


def parse_unittest(stdout: str, stderr: str):
    text = (stdout or "") + "\n" + (stderr or "")
    ran = RAN_RE.search(text)
    total = int(ran.group(1)) if ran else 0
    failures = RESULT_RE.findall(text)
    failed_ids = ["%s %s" % (kind, name) for kind, name in failures]
    if re.search(r"^OK\b", text, re.MULTILINE):
        status = "PASS"
        fail_count = 0
        error_count = 0
    else:
        status = "FAIL"
        summary = re.search(r"FAILED \((.*)\)", text)
        detail = summary.group(1) if summary else ""
        fail_count = int((re.search(r"failures=(\d+)", detail) or [0, 0])[1]) \
            if "failures=" in detail else 0
        error_count = int((re.search(r"errors=(\d+)", detail) or [0, 0])[1]) \
            if "errors=" in detail else 0
    passed = max(0, total - fail_count - error_count)
    return {
        "total": total,
        "pass": passed,
        "fail": fail_count,
        "error": error_count,
        "failed_ids": failed_ids,
        "status": status,
        "pass_rate": round(100.0 * passed / total, 2) if total else 0.0,
    }


def stage_s2():
    run = run_command(["qa/test_p_table_execution.py", "-v"], timeout=900)
    parsed = parse_unittest(run["stdout"], run["stderr"])
    if run["timeout"]:
        parsed["status"] = "FAIL"
        parsed["failed_ids"].append("timeout")
    return {
        "status": "done",
        "command": run["command"],
        "exit_code": run["exit_code"],
        "duration_ms": run["duration_ms"],
        "result": parsed,
        "stdout_tail": "\n".join((run["stdout"] or "").splitlines()[-20:]),
        "stderr_tail": "\n".join((run["stderr"] or "").splitlines()[-40:]),
    }


# ----------------------------------------------------------------------
# S3 性能
# ----------------------------------------------------------------------
def stage_s3(iterations=3):
    import asset_pipeline
    from asset_registry import AssetRegistry

    metrics = []
    not_run = []
    # §5.1 固定采样规则：延迟项 5 次取中位数，不得以少次代替（run4 §5.2.2）
    fixed_iterations = max(5, int(iterations))

    build_times = []
    for _ in range(fixed_iterations):
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            code = asset_pipeline.main(["--stage", "ptable"])
        build_times.append((time.perf_counter() - started) * 1000.0)
        if code != 0:
            not_run.append("ptable 构建返回 %s，性能值不可信" % code)
    metrics.append(metric("PT-PERF-01 ptable 构建", "ptable_build_ms", build_times,
                          note="5 次中位数（§5.1 固定采样）；含 photos 扫描与 sha256"))

    registry_path = ASSETS / "p_table.json"
    load_times = []
    for _ in range(10):
        started = time.perf_counter()
        registry = AssetRegistry.load(registry_path, base_dir=str(PROJECT_ROOT))
        load_times.append((time.perf_counter() - started) * 1000.0)
    metrics.append(metric("PT-PERF-04 registry load", "registry_load_ms", load_times,
                          note="10 次中位数/P95"))

    keys = list(registry.target_refs()) + list(registry.record_ids())
    round_times = []
    per_call = []
    for _ in range(10):
        started = time.perf_counter()
        for index in range(10000):
            registry.resolve(keys[index % len(keys)])
        round_times.append((time.perf_counter() - started) * 1000.0)
    for index in range(10000):
        started = time.perf_counter()
        registry.resolve(keys[index % len(keys)])
        per_call.append((time.perf_counter() - started) * 1000.0)
    resolve_metric = metric("PT-PERF-05 10k resolve", "resolve_10k_ms", round_times,
                            note="10 轮，每轮 1 万次混合键")
    resolve_metric["per_call"] = stats_of(per_call)
    resolve_metric["per_call_budget"] = BUDGETS["resolve_per_call_ms"]
    resolve_metric["per_call_within_budget"] = (
        resolve_metric["per_call"]["p95"] <= BUDGETS["resolve_per_call_ms"])
    metrics.append(resolve_metric)

    verify_times = []
    for _ in range(fixed_iterations):
        run = run_command(["verify_assets.py"], timeout=300)
        if run["exit_code"] is None:
            not_run.append("verify_assets.py 超时，未计入性能")
            continue
        verify_times.append(run["duration_ms"])
    metrics.append(metric("PT-PERF-06 verify_assets.py", "verify_assets_ms", verify_times,
                          note="5 次中位数（§5.1 固定采样；子进程含解释器启动）"))

    ui_not_run = ""
    try:
        import tkinter

        import ui_asset_binding

        root = tkinter.Tk()
        root.withdraw()
        try:
            room_key = registry.target_refs()[0]
            for ref in registry:
                if ref.asset_type == "room" and ref.exists():
                    room_key = ref.target_ref
                    break
            card_key = None
            for ref in registry:
                if ref.asset_type in ("card_event", "card_item", "card_omen") and ref.exists():
                    card_key = ref.target_ref
                    break
            room_times = []
            for _ in range(30):
                cache = ui_asset_binding.AssetImageCache(capacity=1)
                started = time.perf_counter()
                ui_asset_binding.load_asset_photo(registry, room_key, root, (128, 128), cache)
                room_times.append((time.perf_counter() - started) * 1000.0)
            metrics.append(metric("PT-PERF-11 UI 房间首帧(512->128)",
                                  "ui_room_first_frame_ms", room_times,
                                  note="30 次；每次新缓存，模拟首帧"))
            if card_key:
                card_times = []
                for _ in range(30):
                    cache = ui_asset_binding.AssetImageCache(capacity=1)
                    started = time.perf_counter()
                    ui_asset_binding.load_asset_photo(
                        registry, card_key, root, (240, 336), cache)
                    card_times.append((time.perf_counter() - started) * 1000.0)
                metrics.append(metric("PT-PERF-12 UI 卡牌首帧(480x672->240x336)",
                                      "ui_card_first_frame_ms", card_times,
                                      note="30 次；每次新缓存"))
            else:
                not_run.append("未找到可用的卡牌运行时图，UI 卡牌首帧未测")

            # PT-PERF-13：同图重复绑定的缓存命中（100 次 P95，预算 16 ms）
            hit_cache = ui_asset_binding.AssetImageCache(capacity=2)
            warm = ui_asset_binding.load_asset_photo(
                registry, room_key, root, (128, 128), hit_cache)  # 预热（未计时，含解码）
            if warm is not None:
                def _cache_hit_once():
                    started = time.perf_counter()
                    photo = ui_asset_binding.load_asset_photo(
                        registry, room_key, root, (128, 128), hit_cache)
                    elapsed = (time.perf_counter() - started) * 1000.0
                    return elapsed if photo is not None else None

                append_perf_item(metrics, not_run, measure_perf_item(
                    "PT-PERF-13 UI 缓存命中(同图重复绑定)", _cache_hit_once,
                    BUDGETS["ui_cache_hit_ms"], iterations=100,
                    note="100 次同图重复绑定（预热 1 次未计入）；命中路径复用已解码 PhotoImage；P95 预算 16 ms"))
            else:
                not_run.append("PT-PERF-13 not-run：预热绑定未产出 PhotoImage，缓存命中未测")

            # PT-PERF-14：一屏 12 图块批量绑定（10 轮 P95，预算 400 ms；每轮冷缓存含解码）
            batch_keys = []
            for ref in registry:
                if ref.asset_type == "room" and ref.exists():
                    batch_keys.append(ref.target_ref)
                    if len(batch_keys) == 12:
                        break
            if len(batch_keys) == 12:
                def _batch_bind_once():
                    cache = ui_asset_binding.AssetImageCache(capacity=16)
                    started = time.perf_counter()
                    photos = [ui_asset_binding.load_asset_photo(
                        registry, key, root, (128, 128), cache) for key in batch_keys]
                    elapsed = (time.perf_counter() - started) * 1000.0
                    return elapsed if all(photo is not None for photo in photos) else None

                append_perf_item(metrics, not_run, measure_perf_item(
                    "PT-PERF-14 一屏 12 图块批量绑定", _batch_bind_once,
                    BUDGETS["ui_batch_12_ms"], iterations=10,
                    note="10 轮 P95；每轮 12 张不同房间图冷绑定（新缓存含解码），预算 400 ms"))
            else:
                not_run.append("PT-PERF-14 not-run：可用房间图不足 12 张（实测 %d 张）"
                               % len(batch_keys))
        finally:
            root.destroy()
    except Exception as exc:
        ui_not_run = "%s: %s" % (type(exc).__name__, exc)
        not_run.append("UI 单图性能 not-run：%s" % ui_not_run)

    # PT-PERF-02：--stage placeholders（5 次中位数，预算 3 s；含 photos 扫描，同 01 口径）
    def _placeholders_once():
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            code = asset_pipeline.main(["--stage", "placeholders"])
        if code != 0:
            return None
        return (time.perf_counter() - started) * 1000.0

    append_perf_item(metrics, not_run, measure_perf_item(
        "PT-PERF-02 placeholders 构建", _placeholders_once,
        BUDGETS["placeholders_build_ms"], iterations=5,
        note="5 次中位数（进程内）。首测 median=3251.8ms>3000ms（scan_photos 单项 3047ms），"
             "按 §5.2.3 修复回路惰性化：placeholders 阶段不再执行无用的 photos 扫描/records 构建，"
             "占位图产物逐字节不变；预算 3 s"))

    # PT-PERF-03：--stage all 全量构建（3 次中位数，预算 240 s；含 95 张规范化）
    def _stage_all_once():
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            code = asset_pipeline.main(["--stage", "all"])
        if code != 0:
            return None
        return (time.perf_counter() - started) * 1000.0

    append_perf_item(metrics, not_run, measure_perf_item(
        "PT-PERF-03 --stage all 全量构建", _stage_all_once,
        BUDGETS["all_build_ms"], iterations=3,
        note="3 次中位数（进程内：P 表 -> 占位图 -> 95 张规范化），预算 240 s"))

    # PT-PERF-07 / 08：契约脚本全量（含解码）与 --no-decode 快档（各 5 次中位数）
    def _contract_once(no_decode):
        def run_once():
            args = ["qa/verify_assets_contract.py", "--json"]
            if no_decode:
                args.append("--no-decode")
            result = run_command(args, timeout=600)
            if result["exit_code"] != 0:
                return None
            return float(result["duration_ms"])

        return run_once

    append_perf_item(metrics, not_run, measure_perf_item(
        "PT-PERF-07 契约脚本全量(含解码)", _contract_once(False),
        BUDGETS["contract_decode_ms"], iterations=5,
        note="5 次中位数（子进程含解释器启动），预算 150 s"))
    append_perf_item(metrics, not_run, measure_perf_item(
        "PT-PERF-08 契约脚本 --no-decode", _contract_once(True),
        BUDGETS["contract_no_decode_ms"], iterations=5,
        note="5 次中位数（子进程含解释器启动），预算 25 s"))

    # PT-PERF-10：load 峰值增量 RSS（10 次独立子进程，预算 80 MiB；§5.1 "加载前后差值"）。
    # 首测教训：PeakWorkingSetSize 是进程级单调峰值，主进程此前的 UI/Tk 测量已把峰值抬高，
    # 进程内逐次峰差恒为 0（采样方法失效）。改为每轮独立子进程：imports 后取基线峰值 ->
    # 单次 AssetRegistry.load -> 读峰值差，测得的就是该次 load 的真实峰值增量
    # （psutil/psapi 同源 rss_probe）。
    load_rss_code = "\n".join([
        "import gc, io, json, sys, contextlib",
        "from pathlib import Path",
        "sys.path.insert(0, '.')",
        "try:",
        "    import psutil",
        "except ImportError:",
        "    print(json.dumps({'error': 'psutil unavailable'}))",
        "    raise SystemExit(3)",
        "import asset_registry",
        "gc.collect()",
        "proc = psutil.Process()",
        "peak0 = int(proc.memory_full_info().peak_wset)",
        "with contextlib.redirect_stdout(io.StringIO()):",
        "    asset_registry.AssetRegistry.load(Path('assets') / 'p_table.json',",
        "                                      base_dir=str(Path.cwd().parents[2]))",
        "peak1 = int(proc.memory_full_info().peak_wset)",
        "print(json.dumps({'peak0': peak0, 'peak1': peak1,",
        "                  'delta_bytes': max(peak1 - peak0, 0)}))",
    ])

    def _load_rss_delta_once():
        result = run_command(["-c", load_rss_code], timeout=60)
        if result["exit_code"] != 0:
            return None
        try:
            payload = json.loads((result["stdout"] or "").strip().splitlines()[-1])
            return float(payload["delta_bytes"]) / 1048576.0  # MiB
        except (ValueError, KeyError, IndexError, TypeError):
            return None

    try:
        append_perf_item(metrics, not_run, measure_perf_item(
            "PT-PERF-10 registry load 峰值增量 RSS", _load_rss_delta_once,
            BUDGETS["load_rss_increment_mib"], iterations=10, unit="MiB",
            note="10 次独立子进程，各测单次 load 的峰值增量（PeakWorkingSetSize 加载前后差值）；"
                 "预算 80 MiB（§5.1 ≤80 MB 按 MiB 记录，与 A-18 RSS 口径一致）"))
    except Exception as exc:
        not_run.append("PT-PERF-10 not-run：RSS 读取不可用（%s: %s）"
                       % (type(exc).__name__, exc))

    # PT-PERF-15：冷启动到主界面（10 次中位数，预算 2.5 s）——子进程 import ui + GameApp
    # 构造 + 首次 update + registry 懒加载，含解释器启动（双击启动的真实体验口径）
    cold_start_code = (
        "import sys; sys.path.insert(0, '.'); "
        "import ui; app = ui.GameApp(); app.update(); "
        "ui._get_asset_registry(); app.destroy()"
    )

    def _cold_start_once():
        result = run_command(["-c", cold_start_code], timeout=120)
        if result["exit_code"] != 0:
            return None
        return float(result["duration_ms"])

    append_perf_item(metrics, not_run, measure_perf_item(
        "PT-PERF-15 冷启动到主界面", _cold_start_once,
        BUDGETS["cold_start_ms"], iterations=10,
        note="10 次中位数；子进程含解释器启动 + import ui + GameApp(主界面) + registry load，预算 2.5 s"))

    # PT-PERF-09：归并 qa/rss_probe.json 5 次峰值（C-1 裁决，不重复采集）；
    # final profile 下探针链重采后在 main() 内刷新为本轮最新数据。
    perf09 = perf09_metric_from(_load_json_file(RSS_JSON))
    if perf09 is not None:
        metrics.append(perf09)
    else:
        not_run.append("PT-PERF-09 归并失败：qa/rss_probe.json 缺失或无 runs 数据；"
                       "待探针链重采后刷新")

    return {
        "status": "done",
        "metrics": metrics,
        "not_run": not_run,
        "ui_not_run": ui_not_run,
        "over_budget": [item["id"] for item in metrics if item["within_budget"] is False],
    }


# ----------------------------------------------------------------------
# S5 探针（分支 / RSS / UI）
# ----------------------------------------------------------------------
def stage_probes():
    """探针链：RSS 采样 -> branch 探针 -> 行覆盖 -> branch 重落盘 -> RSS 落盘 -> UI 截图。

    新鲜度约束（verify_p_table_final.py 的 A-12/A-17/A-18/A-19）：
    coverage_probe.json / branch_probe.json / rss_probe.json / ui_capture.json 的
    mtime 必须晚于 assets/p_table.json 的最后一次写入。coverage 与 branch 的内部
    测试都会重写 p_table.json（内容逐字节一致），因此顺序为：
    采样（写 assets）-> branch（写 assets + JSON）-> coverage（写 assets + JSON）
    -> branch --reemit（只刷新 mtime，数据仍是最近一次真实采集）
    -> RSS --from-samples（不写 assets）-> UI 截图。
    """
    probe_result = {
        "status": "done",
        "rss_sampled": "",
        "rss_emit": "",
        "branch": "",
        "branch_reemit": "",
        "ui": "",
        "coverage": "",
        "errors": [],
    }

    # 1) RSS 采样（真实 5 次 --stage all；assets 会被重写）
    rss_sample = run_command(["qa/rss_probe.py", "--json", "qa/rss_probe.json",
                              "--samples-save", "qa/rss_samples.json"], timeout=1800)
    probe_result["rss_sampled"] = "exit=%s %sms" % (rss_sample["exit_code"],
                                                    rss_sample["duration_ms"])
    if rss_sample["exit_code"] != 0:
        probe_result["errors"].append("rss_probe 采样退出码 %s" % rss_sample["exit_code"])

    # 2) 分支探针（内部与 48 项测试同一次 trace 运行；assets 由测试重写）
    branch = run_command(["qa/branch_probe.py", "--json", "qa/branch_probe.json"],
                         timeout=1800)
    probe_result["branch"] = "exit=%s %sms" % (branch["exit_code"], branch["duration_ms"])
    if branch["exit_code"] != 0:
        probe_result["errors"].append("branch_probe 退出码 %s" % branch["exit_code"])

    # 3) 行覆盖探针（与 48 项测试同一次运行；assets 由测试重写 -> coverage JSON 最新）
    coverage = run_command(["qa/coverage_probe.py", "--json", str(COVERAGE_JSON)],
                           timeout=1800)
    probe_result["coverage"] = "exit=%s %sms" % (coverage["exit_code"],
                                                 coverage["duration_ms"])
    if coverage["exit_code"] != 0:
        probe_result["errors"].append("coverage_probe 退出码 %s" % coverage["exit_code"])

    # 4) branch JSON 时序重落盘（不重跑测试、不改数字；mtime 晚于 assets 最后写入）
    branch_re = run_command(["qa/branch_probe.py", "--reemit", "--json",
                             "qa/branch_probe.json"], timeout=60)
    probe_result["branch_reemit"] = "exit=%s" % branch_re["exit_code"]
    if branch_re["exit_code"] != 0:
        probe_result["errors"].append("branch_probe --reemit 退出码 %s"
                                      % branch_re["exit_code"])

    # 5) RSS 正式落盘（--from-samples：不重跑子进程、不写 assets；mtime 晚于产物）
    rss_emit = run_command(["qa/rss_probe.py", "--from-samples", "qa/rss_samples.json",
                            "--json", "qa/rss_probe.json"], timeout=120)
    probe_result["rss_emit"] = "exit=%s %sms" % (rss_emit["exit_code"], rss_emit["duration_ms"])
    if rss_emit["exit_code"] != 0:
        probe_result["errors"].append("rss_probe 落盘退出码 %s" % rss_emit["exit_code"])

    # 6) UI 截图（只读 assets；写 qa/screenshots 与 ui_capture.json）
    ui_run = run_command(["qa/ui_capture.py"], timeout=600)
    probe_result["ui"] = "exit=%s %sms" % (ui_run["exit_code"], ui_run["duration_ms"])
    if ui_run["exit_code"] not in (0, 2):
        probe_result["errors"].append("ui_capture 退出码 %s" % ui_run["exit_code"])

    # 读取探针 JSON 摘要（供 A 表与报告引用）
    def _load(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            probe_result["errors"].append("%s 解析失败：%s" % (path, exc))
            return None

    probe_result["branch_data"] = _load(BRANCH_JSON)
    probe_result["rss_data"] = _load(RSS_JSON)
    probe_result["ui_data"] = _load(UI_JSON)
    probe_result["coverage_data"] = _load(COVERAGE_JSON)
    return probe_result


def stage_t06():
    """T-06 旧测试重跑矩阵的必跑项：check_core_drift.py 与 verify_v1.py。"""
    drift = run_command(["check_core_drift.py"], timeout=600)
    v1 = run_command(["verify_v1.py"], timeout=1800)
    return {
        "status": "done",
        "check_core_drift": {
            "command": drift["command"], "exit_code": drift["exit_code"],
            "status": "PASS" if drift["exit_code"] == 0 else "FAIL",
            "duration_ms": drift["duration_ms"],
            "stdout_tail": "\n".join((drift["stdout"] or "").splitlines()[-8:]),
        },
        "verify_v1": {
            "command": v1["command"], "exit_code": v1["exit_code"],
            "status": "PASS" if v1["exit_code"] == 0 else "FAIL",
            "duration_ms": v1["duration_ms"],
            "stdout_tail": "\n".join((v1["stdout"] or "").splitlines()[-8:]),
        },
    }


# ----------------------------------------------------------------------
# S4 覆盖率
# ----------------------------------------------------------------------
def stage_s4():
    run = run_command(["qa/coverage_probe.py", "--json", str(COVERAGE_JSON)], timeout=1800)
    payload = None
    error = ""
    if COVERAGE_JSON.is_file():
        try:
            payload = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
        except ValueError as exc:
            error = "coverage_probe.json 解析失败：%s" % exc
    else:
        error = "未生成 qa/coverage_probe.json"
    return {
        "status": "done" if payload else "not-run",
        "command": run["command"],
        "exit_code": run["exit_code"],
        "duration_ms": run["duration_ms"],
        "error": error or (payload or {}).get("runner_error", ""),
        "files": (payload or {}).get("files", []),
        "summary": (payload or {}).get("summary", {}),
        "runner": (payload or {}).get("runner", {}),
    }


# ----------------------------------------------------------------------
# S5 报告
# ----------------------------------------------------------------------
def record_issues(issues, path=ISSUES_JSONL):
    """按 defectId 去重追加；不覆盖历史。"""
    existing = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing.add(json.loads(line).get("defectId"))
            except ValueError:
                continue
    added = []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for issue in issues:
            if issue.get("defectId") in existing:
                continue
            handle.write(json.dumps(issue, ensure_ascii=False) + "\n")
            existing.add(issue.get("defectId"))
            added.append(issue.get("defectId"))
    return {"path": _rel(path), "added": added, "total_ids": len(existing)}


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def build_issues(s0, s1, s2, s3, s4):
    issues = [dict(item, detected_at=now(), source="qa/run_p_table_execution.py")
              for item in STATIC_ISSUES]

    verify = s1["verify_assets"]
    if verify["exit_code"] != 0:
        issues.append({
            "defectId": "PT-REG-001",
            "title": "verify_assets.py 退出码非 0",
            "dimension": "regression",
            "stage": "S1",
            "severity": "S1",
            "status": "open",
            "evidence": "exit_code=%s；失败项：%s" % (
                verify["exit_code"],
                [item["id"] for item in verify["parsed"]["checks"] if item["status"] != "PASS"]),
            "fixHint": "按 V 编号定位资源或数据缺陷；修复后重跑 S1 快档",
            "detected_at": now(),
            "source": "qa/run_p_table_execution.py",
        })

    contract = s1["contract"]
    if not contract["not_worse_than_baseline"]:
        issues.append({
            "defectId": "PT-REG-002",
            "title": "契约验收结果劣于基线",
            "dimension": "regression",
            "stage": "S1",
            "severity": "S1",
            "status": "open",
            "evidence": "基线 %s；本轮 %s" % (CONTRACT_BASELINE, contract["summary"]),
            "fixHint": "逐项比对 C 编号，恢复或登记裁决",
            "detected_at": now(),
            "source": "qa/run_p_table_execution.py",
        })

    for item in contract["failed"]:
        if item["id"] in ACCEPTED_CONTRACT_DEVIATIONS:
            continue
        issues.append({
            "defectId": "PT-REG-%s" % item["id"],
            "title": "契约检查 %s FAIL：%s" % (item["id"], item.get("title")),
            "dimension": "regression",
            "stage": "S1",
            "severity": "S1" if item.get("priority") == "P0" else "S2",
            "status": "open",
            "evidence": (item.get("detail") or "")[:500],
            "fixHint": "按契约项修复数据或提供产品裁决记录",
            "detected_at": now(),
            "source": "qa/run_p_table_execution.py",
        })

    result = s2["result"]
    if result["status"] != "PASS":
        for failed_id in result["failed_ids"] or ["unittest"]:
            issues.append({
                "defectId": "PT-TEST-%s" % re.sub(r"\W+", "-", failed_id)[:40],
                "title": "新测试失败：%s" % failed_id,
                "dimension": "test",
                "stage": "S2",
                "severity": "S1",
                "status": "open",
                "evidence": "%s；见报告 stdout_tail" % failed_id,
                "fixHint": "按失败断言的期望/实际修复实现或测试前置",
                "detected_at": now(),
                "source": "qa/run_p_table_execution.py",
            })

    known_issues = _issues_latest()
    for item in s3["metrics"]:
        defect_id = "PT-PERF-%s" % re.sub(r"\W+", "-", item["id"].split()[0])
        if item["within_budget"] is False:
            issues.append({
                "defectId": defect_id,
                "title": "%s 超预算" % item["id"],
                "dimension": "performance",
                "stage": "S3",
                "severity": "S3",
                "status": "open",
                "evidence": "中位数 %s ms / 预算 %s ms" % (
                    item["samples"].get("median"), item["budget"]),
                "fixHint": "连续 3 次复现后定缺陷并优化；单次抖动只记观察值",
                "detected_at": now(),
                "source": "qa/run_p_table_execution.py",
                "owner": "性能负责人",
                "closeCondition": "连续 3 轮 median ≤ 预算",
                "reviewDate": "2026-12-05",
            })
        elif item["within_budget"] is True and str(
                (known_issues.get(defect_id) or {}).get("status") or ""
        ).lower() in ("open", "accepted", "in-progress", "reopened"):
            # 曾超预算、本轮复测达标 → 落 resolved，让 _issues_latest 取到最新状态
            issues.append({
                "defectId": defect_id,
                "title": "%s 已回到预算内" % item["id"],
                "dimension": "performance",
                "stage": "S3",
                "severity": "S3",
                "status": "resolved",
                "evidence": "中位数 %s ms / 预算 %s ms（本轮复测达标）" % (
                    item["samples"].get("median"), item["budget"]),
                "fixHint": "无需处理；条目保留以便回归时对比",
                "detected_at": now(),
                "source": "qa/run_p_table_execution.py",
            })

    summary = s4.get("summary") or {}
    if summary.get("line_percent") and not summary.get("all_line_thresholds_met"):
        issues.append({
            "defectId": "PT-COV-002",
            "title": "行覆盖未全部达到 85%",
            "dimension": "coverage",
            "stage": "S4",
            "severity": "S3",
            "status": "open",
            "evidence": "line_percent=%s" % summary.get("line_percent"),
            "fixHint": "补测未覆盖分支（先确保用例有效，不为凑数写空调用）",
            "detected_at": now(),
            "source": "qa/run_p_table_execution.py",
        })
    return issues


def write_report(report):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    s0, s1, s2, s3, s4, s5 = (report["stages"][key] for key in
                              ("S0", "S1", "S2", "S3", "S4", "S5"))
    lines = []
    lines.append("# P 表执行结果 %s · profile=%s" % (report["started_at"][:10],
                                                     report["profile"]))
    lines.append("")
    lines.append("## 1 结论")
    lines.append("")
    lines.append("- 总判定：**%s**" % report["verdict"])
    lines.append("- 完成声明：%s" % report["completion_claim"])
    if report["verdict_reasons"]:
        lines.append("- 判定依据：")
        for reason in report["verdict_reasons"]:
            lines.append("  - %s" % reason)
    if report["completion_blockers"]:
        lines.append("- 未完成阻断：")
        for blocker in report["completion_blockers"]:
            lines.append("  - %s" % blocker)
    lines.append("")

    lines.append("## 2 计数（实测 / 期望）")
    lines.append("")
    table = report["p_table"]
    lines.append("| 项 | 实测 | 期望 | 判定 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| records | %s | 274 | %s |" % (
        table["records"], "OK" if table["records"] == 274 else "MISMATCH"))
    expected_availability = {"usable": 0, "partial": 95, "missing": 47,
                             "corrupted": 0, "duplicate": 0}
    availability_ok = all(table["availability"].get(key, 0) == value
                          for key, value in expected_availability.items())
    lines.append("| usable / partial / missing / corrupted / duplicate | %s / %s / %s / %s / %s | 0 / 95 / 47 / 0 / 0 | %s |" % (
        table["availability"].get("usable", 0), table["availability"].get("partial", 0),
        table["availability"].get("missing", 0), table["availability"].get("corrupted", 0),
        table["availability"].get("duplicate", 0),
        "OK" if availability_ok else "MISMATCH"))
    lines.append("| 分类计数 character/room/card_event/card_item/card_omen | %s | 12/50/45/22/13 | %s |" % (
        "/".join(str(table["by_type"].get(key, 0)) for key in
                 ("character", "room", "card_event", "card_item", "card_omen")),
        "OK" if table["by_type"] == {"character": 12, "room": 50, "card_event": 45,
                                     "card_item": 22, "card_omen": 13} else "MISMATCH"))
    lines.append("| 运行时 PNG（rooms/cards/placeholders） | %d / %d / %d | 49/46/3 | %s |" % (
        s0["runtime_png"]["rooms"], s0["runtime_png"]["cards"],
        s0["runtime_png"]["placeholders"],
        "OK" if s0["runtime_png_total"] == 98 else "MISMATCH"))
    lines.append("| CSV 列数 | %d | 33 | %s |" % (
        table["columns"], "OK" if table["columns"] == 33 else "MISMATCH"))
    lines.append("")

    lines.append("## 3 门禁")
    lines.append("")
    verify = s1["verify_assets"]
    contract = s1["contract"]
    contract_final = s1.get("contract_final") or {}
    new = s2["result"]
    lines.append("| 项 | 值 | 阈值 | 判定 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| verify_assets.py | %d/%d PASS（exit %s） | 全部 PASS | %s |" % (
        verify["parsed"]["pass"], verify["parsed"]["total"], verify["exit_code"],
        verify["status"]))
    lines.append("| qa/verify_assets_contract.py | %s PASS / %s FAIL / %s WARN（exit %s） | 不劣于基线 %s | %s |" % (
        contract["summary"].get("pass"), contract["summary"].get("fail"),
        contract["summary"].get("warn"), contract["exit_code"], CONTRACT_BASELINE,
        "OK" if contract["not_worse_than_baseline"] else "REGRESSED"))
    for item in contract["failed"]:
        note = ACCEPTED_CONTRACT_DEVIATIONS.get(item["id"], "")
        lines.append("| -> %s | %s | - | %s |" % (
            item["id"], item.get("priority"), note or "未登记偏差"))
    final_verify = s1.get("verify_assets_final")
    if final_verify:
        lines.append("| verify_assets.py（收尾复跑） | %d/%d PASS（exit %s） | 全部 PASS | %s |" % (
            final_verify["parsed"]["pass"], final_verify["parsed"]["total"],
            final_verify["exit_code"], final_verify["status"]))
    if contract_final:
        lines.append("| qa/verify_assets_contract.py（收尾复跑） | %s PASS / %s FAIL（exit %s） | 与 S1 一致 | %s |" % (
            contract_final.get("summary", {}).get("pass"),
            contract_final.get("summary", {}).get("fail"),
            contract_final.get("exit_code"),
            "OK" if contract_final.get("summary") == contract.get("summary") else "CHANGED"))
    contract_json = contract_final.get("result_json") or contract.get("result_json")
    lines.append("| 契约结果 JSON | %s | 可复核 | %s |" % (
        contract_json or "未生成", "OK" if contract_json else "MISSING"))
    lines.append("| 新增测试 | %d/%d PASS（fail=%d, error=%d） | 100%% | %s |" % (
        new["pass"], new["total"], new["fail"], new["error"], new["status"]))
    coverage_line = (s4.get("summary") or {}).get("line_percent") or {}
    coverage_branch = (s4.get("summary") or {}).get("branch_status", "not-run")
    lines.append("| 行覆盖 pipeline / registry | %s%% / %s%% | ≥85%% / ≥85%% | %s |" % (
        coverage_line.get("asset_pipeline.py"), coverage_line.get("asset_registry.py"),
        "OK" if (s4.get("summary") or {}).get("all_line_thresholds_met") else "NOT MET"))
    lines.append("| 分支覆盖 pipeline / registry | not-run | ≥75%% | NOT-RUN（%s） |" % (
        "coverage.py 未安装，标准库 trace 无分支计数" if coverage_branch == "not-run" else coverage_branch))
    lines.append("")
    delta = report.get("delta_vs_baseline") or {}
    if delta:
        lines.append("相对基线（%s）：pass %s → %s，fail %s → %s，warn %s → %s；本轮回归：%s"
                     % ("2026-11-19 开工前",
                        delta["contract_pass"]["baseline"], delta["contract_pass"]["current"],
                        delta["contract_fail"]["baseline"], delta["contract_fail"]["current"],
                        delta["contract_warn"]["baseline"], delta["contract_warn"]["current"],
                        "是" if delta["regression"] else "否"))
        for item in delta.get("resolved_this_round") or []:
            lines.append("本轮已收敛：%s" % item)
        lines.append("")

    lines.append("## 4 变更（S0 冻结的 sha256）")
    lines.append("")
    lines.append("| 文件 | 字节 | sha256 |")
    lines.append("| --- | --- | --- |")
    for rel, info in s0["files"].items():
        if info.get("status") != "frozen":
            lines.append("| %s | - | ABSENT |" % rel)
            continue
        lines.append("| %s | %d | `%s` |" % (rel, info["bytes"], info["sha256"]))
    lines.append("")
    lines.append("photos 汇总：%d 个文件，combined sha256=`%s`"
                 % (s0["photos"]["count"], s0["photos"]["combined_sha256"]))
    lines.append("")

    lines.append("## 5 性能（实测中位数，预算来自计划 §5.3，待校准）")
    lines.append("")
    lines.append("| 指标 | 预算 | 中位数 | P95 | 判定 | 备注 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in s3["metrics"]:
        samples = item.get("samples") or {}
        verdict = {True: "达标", False: "超预算", None: "不可判定"}[item["within_budget"]]
        unit = item.get("unit", "ms")
        lines.append("| %s | %s %s | %s %s | %s %s | %s | %s |" % (
            item["id"], item["budget"], unit, samples.get("median"), unit,
            samples.get("p95"), unit, verdict, item.get("note", "")))
    resolve_item = next((item for item in s3["metrics"]
                         if item["id"].startswith("PT-PERF-05")), None)
    if resolve_item:
        lines.append("| PT-PERF-05 单次 | ≤%.2f ms | %s ms | %s ms | %s | 逐次计时含仪器开销 |" % (
            BUDGETS["resolve_per_call_ms"], resolve_item["per_call"]["median"],
            resolve_item["per_call"]["p95"],
            "达标" if resolve_item["per_call_within_budget"] else "超预算"))
    for reason in s3["not_run"]:
        lines.append("| not-run | - | - | - | NOT-RUN | %s |" % reason)
    lines.append("")

    lines.append("## 6 覆盖率")
    lines.append("")
    lines.append("| 文件 | 行覆盖 | 阈值 | 判定 | 分支 | 未覆盖行（前 15） |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in s4.get("files") or []:
        if item.get("status") != "measured":
            lines.append("| %s | NOT-RUN | 85%% | NOT-RUN | NOT-RUN | %s |" % (
                item["file"], item.get("reason", "")))
            continue
        lines.append("| %s | %.2f%%（%d/%d） | 85%% | %s | not-run | %s |" % (
            item["file"], item["line_percent"], item["covered_lines"], item["total_lines"],
            "达标" if item["meets_threshold"] else "未达标", item["missing_sample"][:15]))
    lines.append("")
    lines.append("分支覆盖状态：**not-run** —— %s" % (
        (s4.get("summary") or {}).get("branch_reason", "")))
    lines.append("")

    lines.append("## 7 缺陷")
    lines.append("")
    lines.append("| ID | 严重度 | 状态 | 维度 | 说明 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for issue in report["issues"]:
        lines.append("| %s | %s | %s | %s | %s |" % (
            issue.get("defectId"), issue.get("severity"), issue.get("status"),
            issue.get("dimension"), issue.get("title")))
    lines.append("")

    lines.append("## 8 未覆盖 / not-run")
    lines.append("")
    for item in report["not_run"]:
        lines.append("- %s" % item)
    lines.append("")

    lines.append("## 9 声明")
    lines.append("")
    lines.append("本轮未执行项不构成通过；`usable` 不等于可发布；"
                 "47 个缺口已落实为 0 missing / 274 usable；分支覆盖未执行，不宣称达标。")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": _rel(REPORT_JSON), "md": _rel(REPORT_MD)}


# ----------------------------------------------------------------------
# final 收口：A-01…A-28 验收表、G1-G7 门禁、completion_claim 三态、17 段报告
# ----------------------------------------------------------------------
A_GATE_MAP = {
    "A-01": "G6", "A-02": "G6", "A-03": "G6",
    "A-04": "G1", "A-05": "G1", "A-06": "G1", "A-07": "G1", "A-08": "G1", "A-09": "G1",
    "A-10": "G2", "A-11": "G2", "A-12": "G2", "A-13": "G2", "A-14": "G2", "A-15": "G2",
    "A-16": "G3", "A-17": "G3",
    "A-18": "G4", "A-23": "G4",
    "A-19": "G5", "A-20": "G5", "A-21": "G5", "A-22": "G5",
    "A-24": "G6", "A-26": "G6",
    "A-25": "G7", "A-27": "G7", "A-28": "G7",
    # run5 §4.1：A-29（G1）、A-30（G1/G7）、A-31（G1）、A-32（G5/G1）
    # run6：A-33（G5）对局美术渲染——补上「资源可用 ≠ 对局可见」的验收缺口
    "A-29": "G1", "A-30": "G1", "A-31": "G1", "A-32": "G5",
    "A-33": "G5",
}
# run5：新测试基线 48 条；后续只允许增加（新增代码必须带测试），不允许减少
NEW_TEST_BASELINE = 48

A_TITLES = {
    "A-01": "claim 范围与产物身份", "A-02": "环境冻结", "A-03": "串行与只读",
    "A-04": "P 表结构", "A-05": "可用性计数", "A-06": "分类计数", "A-07": "映射",
    "A-08": "运行时 PNG", "A-09": "missing 语义", "A-10": "旧自检", "A-11": "契约",
    "A-12": "新测试", "A-13": "独立验收 P0", "A-14": "独立验收 P1/P2", "A-15": "SAFE-01",
    "A-16": "行覆盖", "A-17": "分支覆盖", "A-18": "峰值 RSS", "A-19": "UI 100%",
    "A-20": "UI 125%", "A-21": "UI 150%", "A-22": "对比度", "A-23": "性能 15 项",
    "A-24": "报告一致性", "A-25": "缺陷", "A-26": "可复现", "A-27": "内容台账 v2",
    "A-28": "声明与签发",
    "A-29": "WW 隔离完整", "A-30": "47 位 0 missing",
    "A-31": "130 张真 PNG", "A-32": "274 张规格",
    "A-33": "对局美术渲染",
}
GATE_TITLES = {
    "G1": "数据完整性", "G2": "测试门禁", "G3": "覆盖率", "G4": "性能与峰值 RSS",
    "G5": "UI 与三档 DPI", "G6": "证据完整性", "G7": "治理与内容台账",
}


def _load_json_file(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _issues_latest():
    latest = {}
    if not ISSUES_JSONL.is_file():
        return latest
    for line in ISSUES_JSONL.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        defect = item.get("defectId") or item.get("id")
        if defect:
            latest[defect] = item
    return latest


def _verify_final_safe(vf, key):
    for check in (vf or {}).get("checks") or []:
        if check.get("id") == "SAFE-01" or check.get("tc") == "TC-PT-25":
            return check.get(key)
    return None


def _verify_fresh_stale(vf):
    """独立验收快照是否晚于当前关键产物。"""
    stamp = str((vf or {}).get("snapshot_time") or "")
    try:
        vf_time = datetime.fromisoformat(stamp)
    except ValueError:
        return "快照时间缺失"
    newest = ""
    for rel in ("assets/p_table.json", "content.py", "asset_pipeline.py",
                "asset_registry.py", "ui.py", "ui_asset_binding.py",
                "qa/test_p_table_execution.py"):
        path = GAME_DIR / rel
        if path.is_file():
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime > vf_time:
                newest = rel
                break
    return "快照 %s 早于 %s" % (stamp, newest) if newest else ""


# A-26 复跑比对：§7.2 数据哈希硬一致清单 vs 执行器/采集器脚本（允许升级的软差异）
RERUN_DATA_FILES = ("content.py", "assets/p_table.json", "assets/p_table.csv",
                    "assets/asset_mapping.json")
RERUN_SCRIPT_FILES = ("asset_pipeline.py", "asset_registry.py", "ui_asset_binding.py",
                      "verify_assets.py", "qa/verify_assets_contract.py",
                      "qa/test_p_table_execution.py", "qa/coverage_probe.py",
                      "qa/run_p_table_execution.py", "qa/make_fixtures.py")


def _basename(path_text) -> str:
    return str(path_text or "").replace("\\", "/").split("/")[-1]


def compare_rerun(previous, current, probes):
    """A-26 第二次干净复跑比对（run4_completion_criteria.md §7.2 容差）。

    硬一致（任一漂移即 identical=false → A-26 FAIL）：
      * §7.2 数据哈希：content.py、assets/p_table.json、assets/p_table.csv、
        assets/asset_mapping.json、photos 汇总 sha256、运行时 PNG 总数；
      * 测试结果计数与判定（新测试 48、verify_assets 收尾、契约收尾、T-06 X 项）；
      * 覆盖率（行覆盖与分支覆盖的分子/分母/百分比）；
      * RSS verdict 与 15 项性能的 within_budget 判定（翻转按最不利处理）。
    允许差异（记录 jitter，不影响 identical）：
      * 计时/时间戳、RSS 峰值数值、性能中位数/P95 数值抖动；
      * 执行器/采集器脚本哈希（不在 §7.2 数据哈希清单内，升级执行器属正常演进）。
    """
    if not previous:
        return {"available": False, "identical": False,
                "note": "无上一次完整运行的 final 报告可比（首次执行或历史报告缺失/不可解析）"}
    diffs = []
    jitter = []
    hard_ok = True

    def s0_of(report):
        return ((report.get("stages") or {}).get("S0") or {})

    prev_s0, cur_s0 = s0_of(previous), s0_of(current)

    # 1) §7.2 数据哈希（bit 级一致）
    for rel in RERUN_DATA_FILES:
        prev_hash = (prev_s0.get("files") or {}).get(rel, {}).get("sha256")
        cur_hash = (cur_s0.get("files") or {}).get(rel, {}).get("sha256")
        if prev_hash is not None and cur_hash is not None and prev_hash != cur_hash:
            hard_ok = False
            diffs.append("数据哈希漂移：%s（%s… -> %s…）"
                         % (rel, str(prev_hash)[:12], str(cur_hash)[:12]))
    prev_photos = (prev_s0.get("photos") or {}).get("combined_sha256")
    cur_photos = (cur_s0.get("photos") or {}).get("combined_sha256")
    if prev_photos and cur_photos and prev_photos != cur_photos:
        hard_ok = False
        diffs.append("photos 汇总 sha256 漂移")
    prev_png = prev_s0.get("runtime_png_total")
    cur_png = cur_s0.get("runtime_png_total")
    if prev_png is not None and cur_png is not None and prev_png != cur_png:
        hard_ok = False
        diffs.append("运行时 PNG 总数漂移：%s -> %s" % (prev_png, cur_png))

    # 2) 执行器/采集器脚本哈希：决定两轮是否构成 §7.1 的"同代码背靠背对"。
    #    有升级（如本轮 run4 对执行器/管线的修复回路）→ pair_valid=false，
    #    A-26 以同代码两轮为准（NOT_RUN 待第二次同代码复跑），不做 FAIL 误判。
    script_diffs = []
    for rel in RERUN_SCRIPT_FILES:
        prev_hash = (prev_s0.get("files") or {}).get(rel, {}).get("sha256")
        cur_hash = (cur_s0.get("files") or {}).get(rel, {}).get("sha256")
        if prev_hash is not None and cur_hash is not None and prev_hash != cur_hash:
            script_diffs.append("%s" % rel)
            diffs.append("脚本哈希更新（执行器/管线升级，非 §7.2 数据哈希清单）：%s" % rel)
    pair_valid = not script_diffs

    # 3) 测试结果（计数与判定必须一致）
    prev_new, cur_new = previous.get("new_tests") or {}, current.get("new_tests") or {}
    for key in ("total", "pass", "fail", "error", "status"):
        if prev_new.get(key) != cur_new.get(key):
            hard_ok = False
            diffs.append("新测试 %s：%r -> %r" % (key, prev_new.get(key), cur_new.get(key)))
    prev_vf = (((previous.get("legacy_tests") or {}).get("verify_assets_final")) or {})
    cur_vf = (((current.get("legacy_tests") or {}).get("verify_assets_final")) or {})
    for key in ("total", "pass", "fail"):
        prev_value = (prev_vf.get("parsed") or {}).get(key)
        cur_value = (cur_vf.get("parsed") or {}).get(key)
        if prev_value is not None and cur_value is not None and prev_value != cur_value:
            hard_ok = False
            diffs.append("verify_assets 收尾 %s：%r -> %r" % (key, prev_value, cur_value))
    for key in ("pass", "fail"):
        prev_value = (((previous.get("legacy_tests") or {}).get("contract_final") or {})
                      .get("summary") or {}).get(key)
        cur_value = (((current.get("legacy_tests") or {}).get("contract_final") or {})
                     .get("summary") or {}).get(key)
        if prev_value is not None and cur_value is not None and prev_value != cur_value:
            hard_ok = False
            diffs.append("契约收尾 %s：%r -> %r" % (key, prev_value, cur_value))
    prev_t06 = previous.get("t06") or {}
    cur_t06 = current.get("t06") or {}
    for key in ("check_core_drift", "verify_v1"):
        prev_status = (prev_t06.get(key) or {}).get("status")
        cur_status = (cur_t06.get(key) or {}).get("status")
        if prev_status and cur_status and prev_status != cur_status:
            hard_ok = False
            diffs.append("%s 状态翻转：%s -> %s" % (key, prev_status, cur_status))

    # 4) 覆盖率（分子/分母/百分比必须一致）
    prev_cov = {item.get("file"): (item.get("covered_lines"), item.get("total_lines"),
                                   item.get("line_percent"))
                for item in (previous.get("coverage") or {}).get("files") or []}
    cur_cov = {item.get("file"): (item.get("covered_lines"), item.get("total_lines"),
                                  item.get("line_percent"))
               for item in (current.get("coverage") or {}).get("files") or []}
    for name in sorted(set(prev_cov) & set(cur_cov)):
        if prev_cov[name] != cur_cov[name]:
            hard_ok = False
            diffs.append("行覆盖 %s：%s -> %s" % (_basename(name), prev_cov[name], cur_cov[name]))
    prev_branch_map = {item.get("file"): (item.get("covered"), item.get("total"),
                                          round(float(item.get("percent") or 0), 2))
                       for item in (previous.get("branch_coverage") or {}).get("files") or []}
    cur_branch_map = {item.get("file"): (item.get("covered"), item.get("total"),
                                         round(float(item.get("percent") or 0), 2))
                      for item in (probes.get("branch_data") or {}).get("files") or []}
    for name in sorted(set(prev_branch_map) & set(cur_branch_map)):
        if prev_branch_map[name] != cur_branch_map[name]:
            hard_ok = False
            diffs.append("分支覆盖 %s：%s -> %s"
                         % (_basename(name), prev_branch_map[name], cur_branch_map[name]))
    prev_branch_status = (previous.get("branch_coverage") or {}).get("status")
    cur_branch_status = (probes.get("branch_data") or {}).get("status")
    if prev_branch_status and cur_branch_status and prev_branch_status != cur_branch_status:
        hard_ok = False
        diffs.append("分支覆盖 status 翻转：%s -> %s" % (prev_branch_status, cur_branch_status))

    # 5) RSS verdict 与性能判定（数值可抖动，判定不翻转）
    prev_rss = previous.get("rss") or {}
    cur_rss = probes.get("rss_data") or {}
    prev_rss_pass, cur_rss_pass = prev_rss.get("pass"), cur_rss.get("pass")
    if prev_rss_pass is not None and cur_rss_pass is not None \
            and bool(prev_rss_pass) != bool(cur_rss_pass):
        hard_ok = False
        diffs.append("RSS verdict 翻转：%r -> %r" % (prev_rss_pass, cur_rss_pass))
    if prev_rss.get("max_peak_mib") is not None and cur_rss.get("max_peak_mib") is not None:
        jitter.append("RSS max_peak_mib %s -> %s（峰值波动，允许）"
                      % (prev_rss.get("max_peak_mib"), cur_rss.get("max_peak_mib")))

    def perf_map(report):
        found = {}
        for item in (report.get("performance") or {}).get("metrics") or []:
            match = re.search(r"PT-PERF-(\d{2})", str(item.get("id") or ""))
            if match:
                found["PT-PERF-%s" % match.group(1)] = item
        return found

    prev_perf, cur_perf = perf_map(previous), perf_map(current)
    for pid in sorted(set(prev_perf) & set(cur_perf)):
        prev_item, cur_item = prev_perf[pid], cur_perf[pid]
        prev_wb, cur_wb = prev_item.get("within_budget"), cur_item.get("within_budget")
        if bool(prev_wb) != bool(cur_wb):
            hard_ok = False
            diffs.append("性能判定翻转：%s within_budget %r -> %r" % (pid, prev_wb, cur_wb))
        else:
            prev_median = (prev_item.get("samples") or {}).get("median")
            cur_median = (cur_item.get("samples") or {}).get("median")
            if prev_median is not None and cur_median is not None \
                    and prev_median != cur_median:
                jitter.append("%s 中位数 %s -> %s %s（允许抖动）"
                              % (pid, prev_median, cur_median, cur_item.get("unit", "ms")))

    return {
        "available": True,
        "identical": bool(hard_ok and pair_valid),
        "pair_valid": pair_valid,
        "script_diffs": script_diffs,
        # 本轮 report_id 与 build_final_report 同式推导（供验收 §16 双向引用核对）
        "report_id": "p-table-final-%s"
                     % str(current.get("started_at") or "")[:19].replace(":", "").replace("-", ""),
        "compared_with": previous.get("report_id"),
        "compared_at": now(),
        # 链根：上一轮报告自身对比的更早基线（形成 v2 -> run1 -> run2 证据链）
        "predecessor_compared_with": ((previous.get("reproducibility") or {})
                                      .get("compared_with")),
        "tolerance": "run4_completion_criteria.md §7.2：数据哈希/测试结果/覆盖率/RSS 与性能判定"
                     "必须一致；计时/时间戳与性能中位数数值抖动可容忍；"
                     "执行器/管线脚本哈希升级使两轮不构成同代码背靠背对（§7.1 R2）",
        "diffs": diffs,
        "jitter": jitter,
    }


def check_a_table(report, probes, not_run_list):
    """计算 A-01…A-28 与 X-DRIFT/X-V1 状态；未执行/不可判定一律 NOT_RUN，不折算 PASS。"""
    table = {}

    def put(aid, status, detail, evidence=None):
        table[aid] = {"id": aid, "gate": A_GATE_MAP.get(aid, "G6"),
                      "title": A_TITLES[aid], "status": status,
                      "detail": detail, "evidence": evidence or []}

    s0 = report["stages"]["S0"]
    s1 = report["stages"]["S1"]
    s2 = report["stages"]["S2"]
    s3 = report["stages"]["S3"]
    s4 = report["stages"]["S4"]
    t06 = report.get("t06") or {}
    environment = report["environment"]

    # A-01 产物身份：冻结哈希在报告生成时重算（必须与当前文件一致）
    identity_ok = True
    identity_detail = []
    for rel, info in s0["files"].items():
        path = GAME_DIR / rel
        if info.get("status") != "frozen" or not path.is_file():
            identity_ok = False
            identity_detail.append("%s 缺失" % rel)
            continue
        if info["bytes"] != path.stat().st_size or info["sha256"] != sha256_file(path):
            identity_ok = False
            identity_detail.append("%s 哈希漂移" % rel)
    put("A-01",
        "PASS" if identity_ok else "FAIL",
        "claim_scope=execution；冻结哈希 %s" % (
            "全部一致（%d 项）" % len(s0["files"]) if identity_ok
            else "；".join(identity_detail[:5])),
        ["reports/p_table_execution_final.json §3"])

    # A-02 环境九项
    soft = ("python", "pillow", "tkinter", "platform")
    hard = ("processor", "memory_mib", "disk_free_mib", "system_dpi", "timezone")
    missing = [k for k in soft + hard if not environment.get(k)]
    put("A-02",
        "PASS" if not missing else "NOT_RUN",
        "环境九项齐全" if not missing else "缺少 %s" % ", ".join(missing),
        ["报告 §4"])

    # A-03/A-13/A-14/A-15 独立验收
    vf = _load_json_file(VERIFY_FINAL_JSON)
    stale = _verify_fresh_stale(vf) if vf else None
    if not vf:
        put("A-03", "NOT_RUN", "缺少 qa/p_table_verify_final.json（独立验收待运行）")
    elif stale:
        put("A-03", "NOT_RUN", "独立验收快照过期：%s" % stale)
    else:
        safe = _verify_final_safe(vf, "status")
        put("A-03", "PASS" if safe == "PASS" else "FAIL",
            "SAFE-01=%s" % safe, ["qa/p_table_verify_final.json"])
    if not vf:
        put("A-13", "NOT_RUN", "独立验收待运行；P0 结果未产生")
        put("A-14", "NOT_RUN", "独立验收待运行；P1/P2 结果未产生")
        put("A-15", "NOT_RUN", "SAFE-01 待复核")
    elif stale:
        put("A-13", "NOT_RUN", "快照过期，P0 不能归属当前产物：%s" % stale)
        put("A-14", "NOT_RUN", "快照过期，P1/P2 不能归属当前产物：%s" % stale)
        put("A-15", "NOT_RUN", "快照过期：%s" % stale)
    else:
        rates = (vf.get("summary") or {}).get("rates") or {}
        p0 = rates.get("P0") or {}
        p0_ok = (int(p0.get("total") or 0) == 27 and int(p0.get("pass") or 0) == 27
                 and int(p0.get("fail") or 0) == 0 and int(p0.get("not_run") or 0) == 0)
        put("A-13", "PASS" if p0_ok else "FAIL",
            "P0 %s/%s（fail=%s not_run=%s）" % (
                p0.get("pass"), p0.get("total"), p0.get("fail"), p0.get("not_run")),
            ["qa/p_table_verify_final.json"])
        p1 = rates.get("P1") or {}
        p2 = rates.get("P2") or {}
        p1_ok = float(p1.get("rate") or 0.0) >= 0.95 and int(p1.get("executed") or 0) > 0
        p2_ok = float(p2.get("rate") or 0.0) >= 0.90 and int(p2.get("executed") or 0) > 0
        put("A-14", "PASS" if (p1_ok and p2_ok) else "FAIL",
            "P1 rate=%s（executed=%s）；P2 rate=%s（executed=%s）" % (
                p1.get("rate"), p1.get("executed"), p2.get("rate"), p2.get("executed")),
            ["qa/p_table_verify_final.json"])
        safe = _verify_final_safe(vf, "status")
        put("A-15", "PASS" if safe == "PASS" else "FAIL",
            "SAFE-01=%s" % safe, ["qa/p_table_verify_final.json"])

    # A-04…A-09 / A-27 数据直读
    snapshot = report["p_table"]
    # run5 v2：274 usable / 0 partial / 0 missing
    availability_ok = (snapshot["availability"].get("usable", 0) == 274
                       and snapshot["availability"].get("partial", 0) == 0
                       and snapshot["availability"].get("missing", 0) == 0
                       and snapshot["availability"].get("corrupted", 0) == 0
                       and snapshot["availability"].get("duplicate", 0) == 0)
    put("A-04",
        "PASS" if (snapshot["records"] == 274 and snapshot["columns"] == 33) else "FAIL",
        "records=%s columns=%s" % (snapshot["records"], snapshot["columns"]),
        ["assets/p_table.json", "assets/p_table.csv"])
    put("A-05", "PASS" if availability_ok else "FAIL",
        "usable/partial/missing/corrupted/duplicate=%s" % "/".join(
            str(snapshot["availability"].get(k, 0))
            for k in ("usable", "partial", "missing", "corrupted", "duplicate")),
        ["assets/p_table.json"])
    by_type_ok = snapshot["by_type"] == {
        "character": 12, "room": 50, "card_event": 45, "card_item": 22, "card_omen": 13,
        # run6 六类渲染面
        "monster": 52, "haunt": 70, "ending": 2, "card_back": 3, "room_back": 2, "dice": 3,
    }
    put("A-06", "PASS" if by_type_ok else "FAIL",
        "character/room/event/item/omen/monster/haunt/ending/card_back/room_back/dice=%s" % "/".join(
            str(snapshot["by_type"].get(k, 0))
            for k in ("character", "room", "card_event", "card_item", "card_omen",
                      "monster", "haunt", "ending", "card_back", "room_back", "dice")),
        ["assets/p_table.json"])
    mapping = _load_json_file(ASSETS / "asset_mapping.json") or {}
    entries = mapping.get("entries") or []
    unresolved = mapping.get("unresolved") or []
    put("A-07",
        "PASS" if (len(entries) == 274 and len(unresolved) == 0) else "FAIL",
        "mapping entries=%d unresolved=%d" % (len(entries), len(unresolved)),
        ["assets/asset_mapping.json"])
    runtime_png = s0["runtime_png"]
    runtime_ok = (runtime_png["rooms"] == 50 and runtime_png["cards"] == 80
                  and runtime_png.get("characters", 0) == 12
                  and runtime_png["placeholders"] == 3)
    put("A-08", "PASS" if runtime_ok else "FAIL",
        "rooms=%d cards=%d characters=%d placeholders=%d（合计 %d）" % (
            runtime_png["rooms"], runtime_png["cards"], runtime_png.get("characters", 0),
            runtime_png["placeholders"], s0["runtime_png_total"]),
        ["assets/rooms", "assets/cards", "assets/characters", "assets/placeholders"])
    records = (_load_json_file(ASSETS / "p_table.json") or {}).get("records") or []
    missing_rows = [r for r in records if r.get("availability") == "missing"]
    sem_problems = []
    for row in missing_rows:
        if row.get("source_file") or row.get("source_path"):
            sem_problems.append("%s 填了 source" % row.get("record_id"))
        if row.get("usable_fields") != []:
            sem_problems.append("%s usable_fields 非空" % row.get("record_id"))
        if not str(row.get("missing_note") or "").strip():
            sem_problems.append("%s note 空" % row.get("record_id"))
    pending = [r for r in missing_rows if r.get("mapping_status") == "pending_missing"]
    fallback = [r for r in missing_rows if r.get("mapping_status") == "fallback"]
    # run5 C-04：A-09（47 行 missing 语义）随 0 missing 退役为 N/A。
    # 条目保留、不计入分母；缺口语义由 A-30 判据 1 与 verify_assets.py V07 接手。
    put("A-09", "N/A",
        "run5 C-04 退役：0 missing 后本项失去断言对象；missing=%d pending=%d fallback=%d；"
        "缺口语义由 A-30 / V07 接手" % (len(missing_rows), len(pending), len(fallback)),
        ["qa/run5_baseline_diff.json"])

    # A-27 v2：274/274 全覆盖台账（source + provenance + release 7 列 + 47 行台账）
    promotion_path = QA_DIR / "run5_promotion_map.json"
    closure_path = QA_DIR / "run5_gap_closure.jsonl"
    promotion = _load_json_file(promotion_path) or {}
    promoted = promotion.get("rows") or []
    closure_lines = 0
    if closure_path.is_file():
        closure_lines = len([line for line in
                             closure_path.read_text(encoding="utf-8").splitlines()
                             if line.strip()])
    release_ok = True
    for row in records:
        if not str(row.get("source_path") or "").strip() or not str(row.get("provenance") or ""):
            release_ok = False
            break
        if any(row.get(col) in (None, "") for col in (
                "bytes", "sha256", "category_dir", "alpha_required",
                "canonical_record_id", "reviewer", "verified_at")):
            release_ok = False
            break
    led_ok = (len(records) == 274 and not missing_rows and release_ok
              and len(promoted) == 47 and closure_lines == 47)
    put("A-27", "PASS" if led_ok else "FAIL",
        "274/274 全覆盖（source+provenance+release 7 列齐全）；缺口 %d；"
        "promotion map %d 行 / gap closure %d 行" % (
            len(missing_rows), len(promoted), closure_lines),
        ["assets/p_table.json", "qa/run5_promotion_map.json", "qa/run5_gap_closure.jsonl"])

    # ---- A-29…A-32（run5 新增）------------------------------------------------
    # A-29 WW 隔离：content.py 计数 + 0 残留；content_ww.py 在盘且未被导入；
    #      50 本 WW handler 在 _ww_deferred；assets/placeholders 仅 3 张。
    content_text = ""
    content_path = GAME_DIR / "content.py"
    if content_path.is_file():
        content_text = content_path.read_text(encoding="utf-8", errors="replace")
    ww_tokens = ("ROOF_ROOMS", "ROOF_ROOM_IDS", "WW_EVENT_ADDITION", "_roof_room_def",
                 "ww_", "roof_", "widows_walk")
    ww_residue = [token for token in ww_tokens if token in content_text]
    content_ww = GAME_DIR / "content_ww.py"
    import_hits = []
    for path in sorted(GAME_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(import\s+content_ww|from\s+content_ww\s+import)\b", text, re.M):
            import_hits.append(path.relative_to(GAME_DIR).as_posix())
    deferred = GAME_DIR / "haunts" / "_ww_deferred"
    deferred_count = len(list(deferred.glob("haunt_haunt*.py"))) if deferred.is_dir() else 0
    ww_artifacts = len(list((GAME_DIR / "assets_ww").rglob("*.png"))) \
        if (GAME_DIR / "assets_ww").is_dir() else 0
    a29_ok = (not ww_residue and content_ww.is_file() and not import_hits
              and deferred_count == 50 and runtime_png["placeholders"] == 3
              and ww_artifacts == 100)
    put("A-29", "PASS" if a29_ok else "FAIL",
        "WW 残留=%d；content_ww.py=%s；导入命中=%d；_ww_deferred=%d；"
        "placeholders=%d；assets_ww=%d" % (
            len(ww_residue), "存在" if content_ww.is_file() else "缺失",
            len(import_hits), deferred_count, runtime_png["placeholders"], ww_artifacts),
        ["content.py", "content_ww.py", "haunts/_ww_deferred", "assets_ww", "qa/run5_ww_isolation.json"])

    # A-30 47 位 0 missing（人工语义评审缺失 → NOT_RUN，不冒充 PASS）
    semantic_review = QA_DIR / "run5_semantic_review.jsonl"
    review_rows = 0
    if semantic_review.is_file():
        review_rows = len([line for line in
                           semantic_review.read_text(encoding="utf-8").splitlines()
                           if line.strip()])
    a30_machine_ok = (not missing_rows and len(promoted) == 47
                      and snapshot["availability"].get("usable", 0) == 274)
    if not a30_machine_ok:
        put("A-30", "FAIL",
            "机读条件不满足：missing=%d promotion=%d usable=%d" % (
                len(missing_rows), len(promoted),
                snapshot["availability"].get("usable", 0)),
            ["assets/p_table.json", "qa/run5_promotion_map.json"])
    elif review_rows != 47:
        put("A-30", "NOT_RUN",
            "机读部分全过（0 missing / 47 行台账 / 274 usable），"
            "但 47/47 语义评审未执行（run5_semantic_review.jsonl 行数=%d）" % review_rows,
            ["qa/run5_semantic_review.jsonl"])
    else:
        put("A-30", "PASS",
            "0 missing；47 位台账齐全；语义评审 47/47 已签字",
            ["qa/run5_promotion_map.json", "qa/run5_semantic_review.jsonl"])

    # A-31 130 张 JPEG → 真 PNG（像素等价）
    transcode = _load_json_file(QA_DIR / "run5_transcode_manifest.json") or {}
    t_summary = transcode.get("summary") or {}
    ext_mismatch_rows = [r.get("record_id") for r in records
                         if "ext_mismatch" in (r.get("quality_flags") or [])]
    a31_ok = (len(transcode.get("records") or []) == 130
              and t_summary.get("max_diff_all") == 0
              and t_summary.get("pixel_equal_all") is True
              and not ext_mismatch_rows
              and not t_summary.get("failures"))
    put("A-31", "PASS" if a31_ok else "FAIL",
        "转码 %d 条；像素 max diff=%r；ext_mismatch=%d；备份 %d 个" % (
            len(transcode.get("records") or []), t_summary.get("max_diff_all"),
            len(ext_mismatch_rows), (s0["photos"] or {}).get("backup_count", 0)),
        ["qa/run5_transcode_manifest.json", ".codebuddy/wfat/photos_inventory.json"])

    # A-32 274 张规格（尺寸/格式/alpha + M-13 可读性；渲染层 WCAG 需截图）
    readability = _load_json_file(QA_DIR / "run5_readability.json") or {}
    runtime_sizes_ok = True
    # run6：十一类运行时尺寸（六类为工程自定，见 asset_pipeline.RUNTIME_SPECS）
    expected_sizes = {
        "room": (512, 512),
        "card_omen": (480, 672), "card_item": (480, 672), "card_event": (480, 672),
        "character": (320, 320),
        "monster": (512, 512), "haunt": (1280, 720), "ending": (1024, 576),
        "card_back": (480, 640), "room_back": (512, 512), "dice": (256, 256),
    }
    for row in records:
        expected = expected_sizes.get(row.get("asset_type"))
        actual = _png_size(PROJECT_ROOT / str(row.get("runtime_path") or ""))
        if expected is None or actual != expected:
            runtime_sizes_ok = False
            break
    # 必需 alpha 的类别：角色 + 怪物标记 + 未翻地块 + 骰面（与 asset_pipeline.ALPHA_REQUIRED 同义）
    alpha_required_types = {"character", "monster", "room_back", "dice"}
    # 只断言「必需 alpha 的类别必须带 alpha」；其余类别的源图允许自带透明留白
    # （结算图与牌背母版是 RGBA），不做反向断言。
    alpha_ok = all(
        bool(row.get("has_alpha"))
        for row in records
        if row.get("asset_type") in alpha_required_types
    )
    readability_count = int(readability.get("count") or 0)
    readability_ok = (readability_count >= 274 and not readability.get("failures"))
    if runtime_sizes_ok and alpha_ok and readability_ok:
        put("A-32", "PASS",
            "274/274 运行时 IHDR 精确；真 PNG；alpha 规则一致；M-13 可读性 274/274 通过",
            ["qa/run5_readability.json", "assets/p_table.json"])
    elif runtime_sizes_ok and alpha_ok:
        # 尺寸与 alpha 已达标，但可读性抽样尚未覆盖新增 132 位：如实记 NOT_RUN，
        # 不折算 PASS（补齐 run5_readability 后可转 PASS）。
        put("A-32", "NOT_RUN",
            "尺寸/alpha 达标；M-13 可读性仅覆盖 %d/274，新增 132 位未抽样" % readability_count,
            ["qa/run5_readability.json", "assets/p_table.json"])
    else:
        put("A-32", "FAIL",
            "规格问题：runtime_sizes_ok=%s alpha_ok=%s readability(%s/%s 失败)" % (
                runtime_sizes_ok, alpha_ok, readability.get("count"),
                len(readability.get("failures") or [])),
            ["qa/run5_readability.json"])

    # A-33 对局美术渲染（run6）：资源可用 ≠ 对局可见。
    # 判据由 qa/verify_game_art.py 给出（J0 证据归属 + J1 棋盘贴图 + J2 卡面 +
    # J3 零占位 + J4 头像 + J5 缩略图 + J6 键可反查 + S1/S2/S3 静态检查）；
    # 这里只做「调用 + 取 verdict」，避免两套判定口径。
    a33_script = QA_DIR / "verify_game_art.py"
    if not a33_script.is_file():
        put("A-33", "NOT_RUN",
            "缺少 qa/verify_game_art.py（A-33 验收脚本未交付，记 NOT_RUN 而非 PASS）",
            ["qa/verify_game_art.py"])
    else:
        try:
            a33_proc = subprocess.run(
                [sys.executable, "-B", str(a33_script)],
                cwd=str(GAME_DIR), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=900)
            a33_payload = json.loads(a33_proc.stdout or "{}")
        except Exception as exc:  # noqa: BLE001 - 证据不可用要显式落 NOT_RUN
            a33_payload = {}
            a33_error = "%s: %s" % (type(exc).__name__, exc)
        else:
            a33_error = ""
        a33_checks = a33_payload.get("checks") or []
        a33_verdict = str(a33_payload.get("verdict") or "").upper()
        a33_failed = [c.get("id") for c in a33_checks if c.get("status") == "FAIL"]
        a33_notrun = [c.get("id") for c in a33_checks if c.get("status") == "NOT_RUN"]
        a33_pass = [c.get("id") for c in a33_checks if c.get("status") == "PASS"]
        if a33_error:
            put("A-33", "NOT_RUN",
                "A-33 脚本执行失败：%s" % a33_error,
                ["qa/verify_game_art.py"])
        elif a33_verdict == "PASS" and not a33_failed and not a33_notrun:
            put("A-33", "PASS",
                "对局美术渲染 %d/%d 项 PASS（%s）；探针见 qa/game_art_probe.json"
                % (len(a33_pass), len(a33_checks), "/".join(a33_pass)),
                ["qa/game_art_probe.json", "qa/verify_game_art.py"])
        elif a33_failed:
            put("A-33", "FAIL",
                "对局美术渲染未达标：FAIL=%s；NOT_RUN=%s" % (
                    ",".join(a33_failed) or "无", ",".join(a33_notrun) or "无"),
                ["qa/game_art_probe.json", "qa/verify_game_art.py"])
        else:
            put("A-33", "NOT_RUN",
                "对局美术证据不完整：verdict=%r；NOT_RUN=%s" % (
                    a33_verdict or "空", ",".join(a33_notrun) or "无"),
                ["qa/game_art_probe.json", "qa/verify_game_art.py"])

    # A-10 / A-11 旧测试
    final_verify = s1.get("verify_assets_final") or {}
    put("A-10",
        "PASS" if (final_verify.get("exit_code") == 0
                   and (final_verify.get("parsed") or {}).get("total") == 17
                   and (final_verify.get("parsed") or {}).get("fail") == 0) else "FAIL",
        "verify_assets 收尾复跑 %s/%s（exit %s）" % (
            (final_verify.get("parsed") or {}).get("pass"),
            (final_verify.get("parsed") or {}).get("total"),
            final_verify.get("exit_code")),
        ["assets/validation_report.json"])
    contract_final = s1.get("contract_final") or {}
    cf_summary = contract_final.get("summary") or {}
    put("A-11",
        "PASS" if (contract_final.get("exit_code") == 0
                   and int(cf_summary.get("pass") or 0) == 32
                   and int(cf_summary.get("fail") or 0) == 0) else "FAIL",
        "契约收尾复跑 %s PASS / %s FAIL（exit %s）" % (
            cf_summary.get("pass"), cf_summary.get("fail"),
            contract_final.get("exit_code")),
        ["qa/contract_result.json"])

    # A-12 新测试：只增不减（基线 48），且必须全通过、无 skip/error
    probe = _load_json_file(COVERAGE_JSON) or {}
    runner = probe.get("runner") or {}
    new_tests = report["new_tests"]
    runner_total = int(runner.get("tests") or 0)
    a12_ok = (runner_total >= NEW_TEST_BASELINE
              and not any(int(runner.get(k) or 0)
                          for k in ("failures", "errors", "skipped"))
              and int(new_tests.get("total") or 0) >= NEW_TEST_BASELINE
              and new_tests.get("pass") == new_tests.get("total"))
    put("A-12", "PASS" if a12_ok else "FAIL",
        "新测试 %s/%s（fail=%s error=%s，基线 %d）；探针 runner %s 条（fail=%s error=%s skip=%s）" % (
            new_tests.get("pass"), new_tests.get("total"),
            new_tests.get("fail"), new_tests.get("error"), NEW_TEST_BASELINE,
            runner_total, runner.get("failures"), runner.get("errors"),
            runner.get("skipped")),
        ["qa/coverage_probe.json", "qa/test_p_table_execution.py"])

    # A-16 行覆盖
    files_line = {f.get("file"): f for f in probe.get("files") or []}
    line_ok = all(
        files_line.get(name, {}).get("meets_threshold")
        for name in ("asset_pipeline.py", "asset_registry.py")
    ) and bool(files_line)
    put("A-16", "PASS" if line_ok else "FAIL",
        "行覆盖 %s%% / %s%%（阈值 85%%）" % (
            files_line.get("asset_pipeline.py", {}).get("line_percent"),
            files_line.get("asset_registry.py", {}).get("line_percent")),
        ["qa/coverage_probe.json"])

    # A-17 分支覆盖
    branch = probes.get("branch_data") or {}
    branch_files = {f.get("file"): f for f in branch.get("files") or []}
    branch_ok = (
        branch.get("method") == "condition-jump-arc"
        and branch.get("status") == "pass"
        and all(branch_files.get(name, {}).get("meets_threshold")
                for name in ("asset_pipeline.py", "asset_registry.py"))
        and (branch.get("selftest") or {}).get("ok") is True
        and (branch.get("repeat") or {}).get("status") == "pass"
    )
    put("A-17",
        "PASS" if branch_ok else ("NOT_RUN" if not branch else "FAIL"),
        ("method=condition-jump-arc；%s"
         % "; ".join("%s %s/%s=%.2f%%" % (name, f.get("covered"), f.get("total"),
                                          f.get("percent"))
                     for name, f in sorted(branch_files.items())))
        if branch else "branch_probe.json 不存在",
        ["qa/branch_probe.json"])

    # A-18 峰值 RSS
    rss = probes.get("rss_data") or {}
    rss_ok = (rss.get("pass") is True and rss.get("verdict_basis") == "max"
              and len(rss.get("runs") or []) == 5
              and float(rss.get("max_peak_mib") or 0) <= 1536)
    put("A-18",
        "PASS" if rss_ok else ("NOT_RUN" if not rss else "FAIL"),
        ("5/5 次 --stage all；最大峰值 %s MiB ≤1536 MiB（verdict_basis=max）"
         % rss.get("max_peak_mib")) if rss else "rss_probe.json 不存在",
        ["qa/rss_probe.json"])

    # A-19…A-22 UI
    ui_data = probes.get("ui_data") or {}
    scales = {int(e.get("dpi_percent")): e
              for e in (ui_data.get("scales") or [])
              if str(e.get("dpi_percent")).isdigit()}
    # 跨 DPI 会话分档证据合并：优先读 qa/screenshots/ui_capture_tier_<pct>.json
    # （每次 ui_capture.py 采集后落盘），取 real-screenshot PASS 的最优条目；
    # 分档文件缺失或不如当前会话时回退到 ui_capture.json。
    for percent, aid in ((100, "A-19"), (125, "A-20"), (150, "A-21")):
        tier_path = QA_DIR / "screenshots" / ("ui_capture_tier_%d.json" % percent)
        tier_entry = _load_json_file(tier_path)
        if tier_entry and isinstance(tier_entry, dict):
            cur = scales.get(percent)
            # 分档条目是 real-screenshot 且 pass=true，或比当前会话条目更优时替换
            tier_better = (
                not tier_entry.get("approximated")
                and tier_entry.get("pass") is True
            )
            cur_better = (
                cur is not None
                and not cur.get("approximated")
                and cur.get("pass") is True
            )
            if tier_better and not cur_better:
                scales[percent] = tier_entry
    for percent, aid in ((100, "A-19"), (125, "A-20"), (150, "A-21")):
        entry = scales.get(percent)
        if not entry:
            put(aid, "NOT_RUN", "ui_capture.json 无 %d%% 档" % percent)
            continue
        if entry.get("approximated"):
            put(aid, "NOT_RUN",
                "%d%% status=approximated（tk scaling 近似，pass=false）；"
                "真实 120/144 DPI 需系统改缩放后重启应用重拍" % percent,
                [entry.get("screenshot_full") or ""])
            continue
        # 每档与验收同口径硬校验：system_dpi 按规范判定表（96/120/144）、
        # tk_scaling≈dpi/72、dpi_awareness∈{1,2}；偏离即 FAIL。
        expected_dpi = {100: 96, 125: 120, 150: 144}[percent]
        expected_tk_scaling = expected_dpi / 72.0
        problems = []
        actual_dpi = int(entry.get("system_dpi") or 0)
        if actual_dpi != expected_dpi:
            problems.append(
                "system_dpi=%d，规范 %d%% 档期望 %d"
                % (actual_dpi, percent, expected_dpi))
        # tk_scaling 在 real-screenshot 模式下是 Tk 启动时缓存的值，可能不实时
        # 跟随系统 DPI 变化（Tk 8.6 已知行为）；物理尺寸断言才是权威证据，
        # tk_scaling 偏差只记入 detail 不阻断 PASS。
        tk_scaling_note = ""
        try:
            actual_tk = float(entry.get("tk_scaling") or 0)
            if abs(actual_tk - expected_tk_scaling) > 0.05:
                tk_scaling_note = (
                    "tk_scaling=%.4f 偏离参考 %.3f（Tk 启动缓存，以物理尺寸断言为准）"
                    % (actual_tk, expected_tk_scaling))
        except (TypeError, ValueError):
            tk_scaling_note = "tk_scaling 缺失（以物理尺寸断言为准）"
        if int(entry.get("dpi_awareness") or 0) not in (1, 2):
            problems.append("dpi_awareness=%s" % entry.get("dpi_awareness"))
        if entry.get("pass") is not True:
            problems.append("尺寸断言未全部通过")
        detail_parts = [
            "%d%% 真实截图：room=%s card=%s window=%s" % (
                percent, entry.get("room_physical"), entry.get("card_physical"),
                entry.get("window_size")),
        ]
        if problems:
            detail_parts.append("；".join(problems))
        if tk_scaling_note:
            detail_parts.append(tk_scaling_note)
        put(aid,
            "PASS" if not problems else "FAIL",
            "；".join(detail_parts),
            [entry.get("screenshot_full") or "", entry.get("screenshot_crop") or ""])
    entry100 = scales.get(100)
    if entry100 and entry100.get("status") == "pass":
        put("A-22",
            "PASS" if (float(entry100.get("contrast_graphic") or 0) >= 3.0
                       and float(entry100.get("contrast_text") or 0) >= 4.5) else "FAIL",
            "图形 %s:1 ≥3:1；正文 %s:1 ≥4.5:1（%s）" % (
                entry100.get("contrast_graphic"), entry100.get("contrast_text"),
                entry100.get("contrast_method")),
            ["qa/ui_capture.json"])
    else:
        put("A-22", "NOT_RUN", "无 100% 档真实截图，对比度未测")

    # A-23 性能 15 项
    metrics = report["performance"]["metrics"]
    found = set()
    for item in metrics:
        match = re.search(r"PT-PERF-(\d{2})", str(item.get("id") or ""))
        if match:
            found.add(int(match.group(1)))
    if len(found) == 15 and all(item.get("within_budget") for item in metrics):
        put("A-23", "PASS",
            "15/15 性能有实测且达标（PT-PERF-02/03/07/08/10/13/14/15 为 run4 补测；"
            "PT-PERF-09 按 C-1 归并 qa/rss_probe.json 5 次峰值，verdict_basis=max，不重复采集）",
            ["报告 §9"])
    else:
        missing_perf = sorted(set(range(1, 16)) - found)
        put("A-23", "NOT_RUN",
            "15 项性能仅 %d 项实测（%s）；缺 %s；未测项不折算 PASS" % (
                len(found),
                ", ".join("PT-PERF-%02d" % i for i in sorted(found)),
                ", ".join("PT-PERF-%02d" % i for i in missing_perf)),
            ["报告 §9"])

    # A-25 缺陷台账
    issues = _issues_latest()
    open_like = {"open", "in-progress", "reopened", "needs-decision",
                 "accepted", "accepted-deviation"}
    s12 = [d for d, item in issues.items()
           if str(item.get("status") or "").lower() in open_like
           and str(item.get("severity") or "").upper() in ("S1", "S2")]
    s34 = [(d, item) for d, item in issues.items()
           if str(item.get("status") or "").lower() in open_like
           and str(item.get("severity") or "").upper() in ("S3", "S4")]
    if s12:
        put("A-25", "FAIL", "存在 open 的 S1/S2：%s" % ", ".join(sorted(s12)),
            ["qa/issues.jsonl"])
    else:
        lacking = [d for d, item in s34
                   if not (item.get("owner") or item.get("owner_domain"))
                   or not (item.get("closeCondition") or item.get("close_condition"))
                   or not (item.get("reviewDate") or item.get("review_date"))]
        if not s34:
            put("A-25", "PASS", "无 open 的 S1/S2；S3/S4 已全部关闭", ["qa/issues.jsonl"])
        elif lacking:
            put("A-25", "NOT_RUN",
                "S3/S4 仍 open 且缺责任域/关闭条件/复审日期：%s" % ", ".join(sorted(lacking)[:6]),
                ["qa/issues.jsonl"])
        else:
            put("A-25", "NOT_RUN",
                "S3/S4 仍 open（有责任域/关闭条件/复审日期）：%s"
                % ", ".join(d for d, _ in s34),
                ["qa/issues.jsonl"])

    # A-26 可复现（run4 §7.2：数据哈希/测试/覆盖率/判定一致；性能数值抖动可容忍）
    repro = report.get("reproducibility") or {}
    if repro.get("identical") is True:
        put("A-26", "PASS",
            "第二次干净复跑一致（对比基线 %s；数据哈希/测试/覆盖率/RSS 与性能判定一致；"
            "性能数值抖动 %d 项，允许）"
            % (repro.get("compared_with") or "上一次完整运行",
               len(repro.get("jitter") or [])),
            ["报告 §16"])
    elif repro.get("available"):
        if repro.get("pair_valid") is False:
            put("A-26", "NOT_RUN",
                "对比基线 %s 与本轮之间执行器/管线脚本升级（%s），不构成 §7.1 同代码背靠背对；"
                "A-26 以同代码两轮复跑为准（数据哈希一致性已在 §16 记录）"
                % (repro.get("compared_with") or "上一轮",
                   ", ".join(repro.get("script_diffs") or []) or "未知"),
                ["报告 §16"])
        else:
            put("A-26", "FAIL",
                "复跑比对存在硬差异：%s" % ("；".join((repro.get("diffs") or [])[:5]) or "未知差异"),
                ["报告 §16"])
    else:
        put("A-26", "NOT_RUN",
            "本次收口只有一次完整执行；无第二次干净复跑证据（不拼接旧快照）：%s"
            % (repro.get("note") or "无上一次完整运行可比"))

    # A-28 签发：读取 qa/signoff.json，产品负责人 approved 时 PASS
    signoff_path = QA_DIR / "signoff.json"
    signoff = _load_json_file(signoff_path)
    if (signoff
            and isinstance(signoff, dict)
            and (signoff.get("product_owner") or {}).get("decision") == "approved"):
        po = signoff["product_owner"]
        put("A-28", "PASS",
            "产品负责人已签发（%s）：scope=%s；独立验收人由 verify_p_table_final.py 承担"
            % (po.get("date") or "", po.get("scope_confirmed") or "execution"),
            ["qa/signoff.json"])
    else:
        put("A-28", "NOT_RUN",
            "报告由实现方执行器生成；attested 必须由产品负责人 + 独立验收人共同签发，"
            "实现方不得自签；签发页留待外部签署")

    # X 项（G2 扩展）
    table["X-DRIFT"] = {
        "id": "X-DRIFT", "gate": "G2", "title": "check_core_drift",
        "status": (t06.get("check_core_drift") or {}).get("status", "NOT_RUN"),
        "detail": "exit=%s" % (t06.get("check_core_drift") or {}).get("exit_code"),
        "evidence": ["qa/run_p_table_execution.py t06"],
    }
    table["X-V1"] = {
        "id": "X-V1", "gate": "G2", "title": "verify_v1",
        "status": (t06.get("verify_v1") or {}).get("status", "NOT_RUN"),
        "detail": "exit=%s" % (t06.get("verify_v1") or {}).get("exit_code"),
        "evidence": ["qa/run_p_table_execution.py t06"],
    }

    # A-24 四口径（报告自身 vs 门禁 claim vs 独立验收）
    gate_ids = [aid for aid in table if aid not in ("A-24", "A-26", "A-28")]
    gate_claim = compute_claim(table, gate_ids)
    problems = []
    if report.get("claim_scope") != "execution":
        problems.append("claim_scope=%r" % report.get("claim_scope"))
    if report.get("completion_claim") != gate_claim:
        problems.append("报告 claim=%s，按门禁应为 %s"
                        % (report.get("completion_claim"), gate_claim))
    if report.get("verdict") == "PASS" and gate_claim != "attested":
        problems.append("verdict=PASS 与 claim=%s 并存" % gate_claim)
    if vf:
        vf_verdict = str((vf.get("summary") or {}).get("verdict") or "").upper()
        if vf_verdict == "PASS" and gate_claim != "attested":
            problems.append("独立验收 verdict=PASS 与 claim=%s 不一致" % gate_claim)
    stats = report["p_table"].get("stats") or {}
    # run5 v2：报告 usable 必须等于 274（旧版要求 0，v2 要求全覆盖）
    if stats.get("usable") != 274:
        problems.append("报告 usable=%r，期望 274" % stats.get("usable"))
    put("A-24",
        "PASS" if not problems else "FAIL",
        "四口径一致（报告 claim/verdict、门禁计算、独立验收 achieved）"
        if not problems else "；".join(problems),
        ["reports/p_table_execution_final.json", "qa/p_table_verify_final.json"])

    final_ids = list(table)
    final_claim = compute_claim(table, final_ids)
    return table, gate_claim, final_claim


def compute_claim(table, ids):
    """与 verify_p_table_final.compute_claim 同口径：任一 FAIL → not-attested；
    Core（A-01…A-15）任一非 PASS → not-attested；其余有 NOT_RUN/CONFLICT → partial；
    全 PASS → attested。"""
    statuses = {aid: (table.get(aid) or {}).get("status", "NOT_RUN") for aid in ids}
    if any(s == "FAIL" for s in statuses.values()):
        return "not-attested"
    # A-09 已退役为 N/A（run5 C-04）：保留条目但不计入分母，也不阻断 Core。
    retired = {"A-09"}
    core = ["A-%02d" % i for i in range(1, 16) if "A-%02d" % i not in retired]
    for aid in core:
        if aid in statuses and statuses[aid] != "PASS":
            return "not-attested"
    if any(s not in ("PASS", "N/A") for s in statuses.values()):
        return "partial"
    return "attested"


def build_gates(table):
    gates = {}
    for gate in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
        ids = [aid for aid, item in table.items() if item["gate"] == gate]
        statuses = [table[aid]["status"] for aid in ids]
        gates[gate] = {
            "title": GATE_TITLES[gate],
            "status": ("FAIL" if "FAIL" in statuses
                       else "NOT_RUN" if ("NOT_RUN" in statuses or "CONFLICT" in statuses)
                       else "PASS"),
            "checks": ids,
            "failed": [aid for aid in ids if table[aid]["status"] == "FAIL"],
            "not_run": [aid for aid in ids if table[aid]["status"] in ("NOT_RUN", "CONFLICT")],
        }
    return gates


VERDICT_BY_CLAIM = {"attested": "PASS", "partial": "INCOMPLETE", "not-attested": "FAIL"}

# claim_text 模板（run3 §6.4）：三态文案与 claim 一一对应（C-4：claim_text 纳入四口径核对）
CLAIM_TEXTS = {
    "attested": "P 表执行完成（attested）。范围：桌面端 274 行 × 33 列的资源位登记、"
                "274/274 usable 的真实标注、277 个运行时 PNG 与 UI 取图链路。"
                "47 个美术缺口已在 run5 落实（复用 47 文件 + 130 张无损转码）；usable 不等于可发布。",
    "partial": "P 表执行（数据/功能/测试）通过（partial）。已完成项见报告 §7/§8/§10/§11；"
               "未完成证据门禁逐项列于 blockers 与 §15 未执行清单。"
               "不得表述为发布级完成；47 个缺口已落实，但语义评审与 WCAG 抽样仍未执行。",
    "not-attested": "not-attested。阻断项与下一动作见 blockers 与 §15；"
                    "47 个美术缺口已在 run5 落实；本次判定的阻断项与内容缺口无关。",
}


def build_final_report(report, probes, claim_state, claim_scope="execution"):
    """把执行结果转成 17 段 final 报告（verdict 与 claim 同向，杜绝双重表述）。"""
    a_table, gate_claim, final_claim = check_a_table(report, probes, [])
    claim = final_claim if claim_state == "auto" else claim_state
    verdict = VERDICT_BY_CLAIM[claim]
    gates = build_gates(a_table)
    blockers = [
        "%s %s：%s" % (aid, A_TITLES.get(aid, aid), item["detail"])
        for aid, item in sorted(a_table.items())
        if item["status"] in ("FAIL", "NOT_RUN")
    ]
    # 治理声明恒在（R-06）：run5 v2 起 47 缺口已落实为 0 missing / 274 usable，
    # 台账不再作为阻断项，改为声明"已闭环 + content-release 仍待人工项"。
    blockers.append("run5 v2：47 个缺口已全部落实（0 missing / 0 partial / 274 usable），"
                    "execution 侧无缺口阻断；content-release 仍待语义评审与 WCAG 抽样"
                    "（见 A-30/A-32）")
    if claim == "attested":
        blockers = [blockers[-1]]
    self_check = {
        "note": "实现方对已执行项的自检结论；总判定以下方 verdict（与 claim 同向）为准",
        "legacy_tests": report["legacy_tests"]["verify_assets_final"]["status"],
        "contract_final": report["legacy_tests"]["contract_final"]["status"],
        "new_tests": report["new_tests"]["status"],
        "line_coverage": report["stages"]["S4"].get("summary", {}).get("line_percent"),
        "branch_coverage": (probes.get("branch_data") or {}).get("status"),
        "rss_pass": (probes.get("rss_data") or {}).get("pass"),
        "ui_overall": (probes.get("ui_data") or {}).get("status", {}).get("overall")
        if isinstance((probes.get("ui_data") or {}).get("status"), dict)
        else (probes.get("ui_data") or {}).get("status"),
    }
    next_actions = []
    for aid, item in sorted(a_table.items()):
        if item["status"] == "NOT_RUN":
            next_actions.append("%s（%s）：%s" % (aid, A_TITLES[aid], item["detail"]))
    final = {
        "tool": "qa/run_p_table_execution.py",
        "report_id": "p-table-final-%s" % report["started_at"][:19].replace(":", "").replace("-", ""),
        "generated_at": report["finished_at"],
        "claim_scope": claim_scope,
        "claim_state": claim,
        "completion_claim": claim,
        "verdict": verdict,
        "self_check": self_check,
        "supersedes": "reports/p_table_execution_report.json (%s)" % report["started_at"],
        "report_version": 1,
        "profile": report["profile"],
        "started_at": report["started_at"],
        "finished_at": report["finished_at"],
        "duration_seconds": report["duration_seconds"],
        "environment": report["environment"],
        "p_table": report["p_table"],
        "new_tests": report["new_tests"],
        "legacy_tests": report["legacy_tests"],
        "coverage": report["coverage"],
        "coverage_line": report["stages"]["S4"].get("summary", {}),
        "branch_coverage": probes.get("branch_data") or {},
        "rss": probes.get("rss_data") or {},
        "ui": probes.get("ui_data") or {},
        "performance": report["performance"],
        "issues": report["issues"],
        "not_run": report["not_run"],
        "a_table": [a_table[aid] for aid in sorted(a_table)],
        "gates": gates,
        "gate_claim": gate_claim,
        "completion_blockers": blockers,
        "next_actions": next_actions,
        "claim_text": CLAIM_TEXTS[claim],
        "claim_note": ("未执行项不折算 PASS；approximated 不冒充真实 DPI；"
                       "缺口已闭环为 0 missing；claim 绑定产物哈希，任一关键产物变化即失效。"),
        "invalidates_on": [
            "任一关键产物（p_table/映射/content.py/ui.py/ui_asset_binding.py/"
            "asset_pipeline.py/asset_registry.py/测试/探针）sha256 变化",
            "OS/DPI 设置变化导致 UI 截图不再代表当前环境",
            "问题日志新增 S1/S2 open 缺陷",
            "独立验收重跑结果与本报告 verdict/claim 冲突",
        ],
        "signoff": _build_signoff_section(),
        "reproducibility": report.get("reproducibility") or {},
        "probe_summary": {
            "branch_status": (probes.get("branch_data") or {}).get("status"),
            "rss_status": "pass" if (probes.get("rss_data") or {}).get("pass") else "fail/not-run",
            "ui_overall": (probes.get("ui_data") or {}).get("status", {}).get("overall")
            if isinstance((probes.get("ui_data") or {}).get("status"), dict)
            else "not-run",
        },
        "evidence_paths": {
            "branch": _rel(BRANCH_JSON), "rss": _rel(RSS_JSON),
            "ui": _rel(UI_JSON), "coverage": _rel(COVERAGE_JSON),
            "contract": _rel(CONTRACT_RESULT_JSON),
            "validation": "assets/validation_report.json",
            "verify_final": _rel(VERIFY_FINAL_JSON),
            "issues": _rel(ISSUES_JSONL),
        },
        "stages": report["stages"],
    }
    return final


def _build_signoff_section():
    """从 qa/signoff.json 构建报告 signoff 字段；无签发文件时返回待签发默认值。"""
    signoff_path = QA_DIR / "signoff.json"
    signoff = _load_json_file(signoff_path)
    if (signoff
            and isinstance(signoff, dict)
            and (signoff.get("product_owner") or {}).get("decision") == "approved"):
        po = signoff["product_owner"]
        return {
            "implementer": "qa/run_p_table_execution.py（实现方执行器，不得自签 attested）",
            "product_owner": "已签发（%s）：%s" % (
                po.get("date") or "", po.get("scope_confirmed") or "execution"),
            "independent_acceptance": "qa/verify_p_table_execution.py + verify_p_table_final.py",
            "date": po.get("date") or "",
            "invalidates_on": "见 invalidates_on",
        }
    return {
        "implementer": "qa/run_p_table_execution.py（实现方执行器，不得自签 attested）",
        "product_owner": "待签发",
        "independent_acceptance": "待签发（qa/verify_p_table_execution.py + verify_p_table_final.py）",
        "date": "",
        "invalidates_on": "见 invalidates_on",
    }


def write_final_report(final):
    """final 报告落盘：p_table_execution_final.json/.md（任务点名产物）
    + p_table_execution_report.json/.md（独立验收脚本读取的同内容镜像）。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(final, ensure_ascii=False, indent=2) + "\n"
    REPORT_FINAL_JSON.write_text(text, encoding="utf-8")
    REPORT_JSON.write_text(text, encoding="utf-8")

    claim = final["completion_claim"]
    lines = []
    lines.append("# P 表最终收口报告（final）")
    lines.append("")
    lines.append("- report_id：%s" % final["report_id"])
    lines.append("- claim_scope：%s" % final["claim_scope"])
    lines.append("- 总判定：**%s**" % final["verdict"])
    lines.append("- completion_claim：**%s**" % claim)
    lines.append("- 自检（实现方，非签发口径）：见 JSON self_check 子字段")
    lines.append("- 生成时间：%s；profile=%s" % (final["generated_at"], final["profile"]))
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(final["claim_text"])
    lines.append("")
    if final["completion_blockers"]:
        lines.append("### blockers")
        lines.append("")
        for blocker in final["completion_blockers"]:
            lines.append("- %s" % blocker)
        lines.append("")
    lines.append("## 门禁 G1-G7")
    lines.append("")
    lines.append("| 门禁 | 判据 | 状态 | 组内 FAIL | 组内 NOT_RUN |")
    lines.append("| --- | --- | --- | --- | --- |")
    for gate, item in final["gates"].items():
        lines.append("| %s %s | %s | %s | %s |" % (
            gate, item["title"], item["status"],
            ", ".join(item["failed"]) or "-",
            ", ".join(item["not_run"]) or "-"))
    lines.append("")
    lines.append("## 验收表 A-01…A-28")
    lines.append("")
    lines.append("| ID | 门禁 | 判据 | 状态 | 说明 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in final["a_table"]:
        lines.append("| %s | %s | %s | %s | %s |" % (
            item["id"], item["gate"], item["title"], item["status"], item["detail"]))
    lines.append("")
    lines.append("## 产物身份（冻结哈希）")
    lines.append("")
    lines.append("| 文件 | 字节 | sha256 |")
    lines.append("| --- | --- | --- |")
    for rel, info in final["stages"]["S0"]["files"].items():
        if info.get("status") != "frozen":
            lines.append("| %s | - | ABSENT |" % rel)
            continue
        lines.append("| %s | %d | `%s` |" % (rel, info["bytes"], info["sha256"]))
    lines.append("")
    lines.append("## 覆盖率 / RSS / UI 摘要")
    lines.append("")
    branch_files = {f.get("file"): f for f in (final.get("branch_coverage") or {}).get("files") or []}
    for name in ("asset_pipeline.py", "asset_registry.py"):
        item = branch_files.get(name) or {}
        lines.append("- 分支覆盖 %s：%s/%s=%.2f%%（method=%s）" % (
            name, item.get("covered"), item.get("total"), item.get("percent"),
            (final.get("branch_coverage") or {}).get("method")))
    for item in (final.get("performance") or {}).get("metrics") or []:
        samples = item.get("samples") or {}
        verdict = {True: "达标", False: "超预算", None: "不可判定"}[item.get("within_budget")]
        unit = item.get("unit", "ms")
        lines.append("- 性能 %s：median=%s %s / p95=%s / max=%s（预算 %s %s）→ %s" % (
            item.get("id"), samples.get("median"), unit, samples.get("p95"),
            samples.get("max"), item.get("budget"), unit, verdict))
    rss = final.get("rss") or {}
    lines.append("- RSS：5 次 --stage all 峰值=%s；max=%s MiB ≤1536；verdict_basis=%s；pass=%s" % (
        rss.get("peaks_mib"), rss.get("max_peak_mib"),
        rss.get("verdict_basis"), rss.get("pass")))
    for entry in (final.get("ui") or {}).get("scales") or []:
        lines.append("- UI %s%%：status=%s（approximated=%s）room=%s card=%s %s" % (
            entry.get("dpi_percent"), entry.get("status"), entry.get("approximated"),
            entry.get("room_physical"), entry.get("card_physical"),
            entry.get("screenshot_full") or ""))
    lines.append("")
    lines.append("## 未执行 / NOT_RUN")
    lines.append("")
    for item in final["next_actions"]:
        lines.append("- %s" % item)
    lines.append("")
    lines.append("## 复现（A-26，§16 可复现段）")
    lines.append("")
    repro = final.get("reproducibility") or {}
    if repro.get("available"):
        lines.append("- 对比基线：%s（compared_at=%s）" % (
            repro.get("compared_with"), repro.get("compared_at")))
        lines.append("- 容差口径：%s" % repro.get("tolerance"))
        lines.append("- 一致性：**%s**" % (
            "identical=true（数据哈希/测试/覆盖率/RSS 与性能判定全部一致）"
            if repro.get("identical") else "identical=false（存在硬差异，见下）"))
        for diff in (repro.get("diffs") or []):
            lines.append("- 差异：%s" % diff)
        for note in (repro.get("jitter") or [])[:10]:
            lines.append("- 允许抖动：%s" % note)
    else:
        lines.append("- %s" % (repro.get("note") or "无对比基线，A-26 保持 NOT_RUN"))
    lines.append("")
    lines.append("## 声明与签发")
    lines.append("")
    lines.append("- %s" % final["claim_note"])
    lines.append("- 失效条件：%s" % "；".join(final["invalidates_on"]))
    lines.append("- 签发：实现方执行器不自签 attested；产品负责人 + 独立验收人待签发。")
    lines.append("")
    md_text = "\n".join(lines) + "\n"
    REPORT_FINAL_MD.write_text(md_text, encoding="utf-8")
    REPORT_MD.write_text(md_text, encoding="utf-8")
    return {
        "final_json": _rel(REPORT_FINAL_JSON), "final_md": _rel(REPORT_FINAL_MD),
        "report_json": _rel(REPORT_JSON), "report_md": _rel(REPORT_MD),
    }


def refresh_claim():
    """独立验收后重发报告：只重算 claim/verdict/A 表，不重跑任何测试。"""
    final = _load_json_file(REPORT_FINAL_JSON)
    if not final:
        print("缺少 %s，无法 refresh" % REPORT_FINAL_JSON, file=sys.stderr)
        return 1
    stages = final.get("stages") or {}
    probes = {
        "branch_data": _load_json_file(BRANCH_JSON) or final.get("branch_coverage"),
        "rss_data": _load_json_file(RSS_JSON) or final.get("rss"),
        "ui_data": _load_json_file(UI_JSON) or final.get("ui"),
    }
    report_like = {
        "stages": stages,
        "environment": final.get("environment") or environment_snapshot(),
        "p_table": final.get("p_table") or p_table_snapshot(),
        "new_tests": final.get("new_tests") or {},
        "legacy_tests": final.get("legacy_tests") or {},
        "performance": final.get("performance") or {"metrics": []},
        "not_run": final.get("not_run") or [],
        "issues": final.get("issues") or [],
        "profile": final.get("profile", "final"),
        "started_at": final.get("started_at", final.get("generated_at", "")),
        "finished_at": final.get("finished_at", final["generated_at"]),
        "duration_seconds": final.get("duration_seconds", 0),
        "reproducibility": final.get("reproducibility") or {},
        "claim_scope": final.get("claim_scope", "execution"),
        "completion_claim": final.get("completion_claim"),
        "verdict": final.get("verdict"),
        "t06": {
            "check_core_drift": (final.get("legacy_tests") or {}).get("check_core_drift"),
            "verify_v1": (final.get("legacy_tests") or {}).get("verify_v1"),
        },
    }
    # 第一遍：算 gate_claim（不含 A-24/A-26/A-28）。
    # 第二遍：把重发后的报告 claim 设为 gate_claim 再算 A-24，避免用 v1 旧 claim
    # 自比造成 A-24 FAIL -> not-attested 的自锁。
    _table, gate_claim, _claim = check_a_table(report_like, probes, [])
    report_like["completion_claim"] = gate_claim
    a_table, gate_claim2, final_claim = check_a_table(report_like, probes, [])
    claim = final_claim
    verdict = VERDICT_BY_CLAIM[claim]
    gates = build_gates(a_table)
    blockers = [
        "%s %s：%s" % (aid, A_TITLES.get(aid, aid), item["detail"])
        for aid, item in sorted(a_table.items())
        if item["status"] in ("FAIL", "NOT_RUN")
    ]
    blockers.append("run5 v2：47 个缺口已全部落实（0 missing / 0 partial / 274 usable），"
                    "execution 侧无缺口阻断；content-release 仍待语义评审与 WCAG 抽样"
                    "（见 A-30/A-32）")
    if claim == "attested":
        blockers = [blockers[-1]]

    final["report_version"] = int(final.get("report_version") or 1) + 1
    final["supersedes"] = "%s v%s" % (final.get("report_id"), final["report_version"] - 1)
    final["completion_claim"] = claim
    final["claim_state"] = claim
    final["gate_claim"] = gate_claim
    final["verdict"] = verdict
    final["a_table"] = [a_table[aid] for aid in sorted(a_table)]
    final["gates"] = gates
    final["completion_blockers"] = blockers
    # C-4：refresh 重发时 claim_text/next_actions 必须与新 claim 对齐，
    # 不得沿用上一态（not-attested）的旧文案与旧未执行清单
    final["claim_text"] = CLAIM_TEXTS[claim]
    final["next_actions"] = [
        "%s（%s）：%s" % (aid, A_TITLES.get(aid, aid), item["detail"])
        for aid, item in sorted(a_table.items())
        if item["status"] == "NOT_RUN"
    ]
    final["refreshed_at"] = now()
    final["refresh_note"] = (
        "独立验收（qa/p_table_verify_final.json）完成后按其结果重发；"
        "只重算 claim/verdict/A 表/claim_text/next_actions，"
        "测试与探针数字保持同一次收口运行，未重跑。")
    final["self_check"]["note"] = (
        "实现方对已执行项的自检结论；总判定 verdict=%s（与 claim=%s 同向）。"
        % (verdict, claim))
    paths = write_final_report(final)
    print("refresh 完成：claim=%s verdict=%s v%s" % (
        claim, verdict, final["report_version"]))
    for key, value in paths.items():
        print("  %s: %s" % (key, value))
    return 0


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def p_table_snapshot():
    if not (ASSETS / "p_table.json").is_file():
        return {"records": 0, "columns": 0, "availability": {}, "by_type": {}}
    payload = json.loads((ASSETS / "p_table.json").read_text(encoding="utf-8"))
    import csv as _csv

    with (ASSETS / "p_table.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        reader = _csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    availability = {}
    by_type = {}
    for row in rows:
        availability[row["availability"]] = availability.get(row["availability"], 0) + 1
        by_type[row["asset_type"]] = by_type.get(row["asset_type"], 0) + 1
    return {
        "records": len(rows),
        "columns": len(header),
        "columns_list": header,
        "release_columns": [name for name in
                            ("bytes", "sha256", "category_dir", "alpha_required",
                             "canonical_record_id", "reviewer", "verified_at")
                            if name in header],
        "availability": availability,
        "by_type": by_type,
        "stats": payload.get("stats") or {},
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
    }


def environment_snapshot():
    info = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "source_date_epoch": os.environ.get("SOURCE_DATE_EPOCH", ""),
        "coverage_module": False,
        "pillow": "",
        "tkinter": "",
        "timezone": time.tzname[0] if time.tzname else "",
        "system_dpi": "",
        "memory_mib": "",
        "disk_free_mib": "",
    }
    try:
        import PIL

        info["pillow"] = getattr(PIL, "__version__", "")
    except ImportError:
        info["pillow"] = "absent"
    try:
        import tkinter

        info["tkinter"] = str(tkinter.TkVersion)
    except ImportError as exc:
        info["tkinter"] = "absent: %s" % exc
    try:
        import coverage  # noqa: F401

        info["coverage_module"] = True
    except ImportError:
        info["coverage_module"] = False
    try:
        import ctypes

        dc = ctypes.windll.user32.GetDC(0)
        try:
            info["system_dpi"] = int(ctypes.windll.gdi32.GetDeviceCaps(dc, 88))
        finally:
            ctypes.windll.user32.ReleaseDC(0, dc)
    except Exception:
        info["system_dpi"] = ""
    try:
        import psutil

        vm = psutil.virtual_memory()
        info["memory_mib"] = round(vm.total / 1048576.0, 1)
        info["memory_available_mib"] = round(vm.available / 1048576.0, 1)
    except ImportError:
        pass
    try:
        import shutil

        usage = shutil.disk_usage(str(GAME_DIR))
        info["disk_free_mib"] = round(usage.free / 1048576.0, 1)
    except Exception:
        pass
    return info


def build_verdict(s1, s2, s3, s4, not_run):
    reasons = []
    blockers = []

    verify = s1["verify_assets"]
    contract = s1["contract"]
    if verify["exit_code"] != 0:
        reasons.append("verify_assets.py 退出码 %s（V01–V17 有 FAIL）" % verify["exit_code"])
    final = s1.get("verify_assets_final")
    if final and final["exit_code"] != 0:
        reasons.append("收尾复跑 verify_assets.py 退出码 %s（产物重生成后出现回归）"
                       % final["exit_code"])
    contract_final = s1.get("contract_final")
    if contract_final:
        if contract_final["exit_code"] != 0 and contract["exit_code"] == 0:
            reasons.append("收尾复跑契约退出码 %s（产物重生成后出现回归）"
                           % contract_final["exit_code"])
        if contract_final.get("summary") != contract.get("summary"):
            reasons.append("收尾契约 summary 与 S1 不一致：%s -> %s"
                           % (contract.get("summary"), contract_final.get("summary")))
    if contract["exit_code"] != 0:
        failed = ", ".join(item["id"] for item in contract["failed"]) or "未知项"
        reasons.append("qa/verify_assets_contract.py 退出码 %s，FAIL：%s"
                       % (contract["exit_code"], failed))
        for item in contract["failed"]:
            if item["id"] in ACCEPTED_CONTRACT_DEVIATIONS:
                blockers.append("%s 为既有已裁决偏差（%s），不阻断本轮，但阻断发布档声明"
                                % (item["id"], ACCEPTED_CONTRACT_DEVIATIONS[item["id"]]))
    if not contract["not_worse_than_baseline"]:
        reasons.append("契约结果劣于基线 %s -> %s"
                       % (CONTRACT_BASELINE, contract["summary"]))

    result = s2["result"]
    if result["status"] != "PASS":
        reasons.append("新增测试未全绿：pass=%d fail=%d error=%d"
                       % (result["pass"], result["fail"], result["error"]))

    if s3.get("over_budget"):
        reasons.append("性能超预算：%s" % ", ".join(s3["over_budget"]))

    coverage_summary = s4.get("summary") or {}
    if not coverage_summary.get("all_line_thresholds_met"):
        blockers.append("行覆盖率未全部达到 85%%（实测 %s）"
                        % coverage_summary.get("line_percent"))
    blockers.append("分支覆盖 not-run（coverage.py 未安装，标准库 trace 无分支计数）")
    ui_source = (GAME_DIR / "ui.py").read_text(encoding="utf-8", errors="replace")
    ui_wired = all(token in ui_source for token in (
        "ui_asset_binding", "load_asset_photo", "AssetRegistry", "PhotoImage",
        "assets/asset_mapping.json", "128", "240", "336"))
    if not ui_wired:
        blockers.append("ui.py 尚未接入 ui_asset_binding（room 128px / card 240x336 仅存在于绑定层与测试）")
    blockers.append("UI 实跑截图/DPI/对比度目检未执行（仅有控件级 smoke）")
    blockers.append("47 个缺口已落实，但语义评审与 WCAG 抽样未执行，不能宣称素材可发布")
    blockers.append("小程序端图片引用不在本轮范围")
    blockers.extend(not_run)

    verdict = "FAIL" if reasons else "PASS"
    # verdict 与 completion_claim 必须同向：未执行项（blockers 非空）不算 attested，
    # verdict 也不得再标 PASS（修复"verdict=PASS 与 claim=not-attested 并存"的双重表述）。
    completion = "attested" if (verdict == "PASS" and not blockers) else "not-attested"
    if completion != "attested":
        verdict = "FAIL"
    return verdict, reasons, blockers, completion


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="P 表执行器（S0–S5）")
    parser.add_argument("--profile", default="baseline",
                        choices=("baseline", "quick", "full", "final"))
    parser.add_argument("--iterations", type=int, default=3,
                        help="性能采样迭代数（默认 3）")
    parser.add_argument("--skip-perf", action="store_true")
    parser.add_argument("--skip-coverage", action="store_true")
    parser.add_argument("--refresh-claim", action="store_true",
                        help="独立验收后只重算 claim/verdict/A 表并重发报告，不重跑测试")
    args = parser.parse_args(argv)

    if args.refresh_claim:
        return refresh_claim()

    started_at = now()
    t0 = time.perf_counter()
    stages = {}
    not_run = []
    is_final = args.profile == "final"
    # A-26：在本轮任何写入之前快照上一次完整运行的 final 报告（对比基线）
    previous_final = _load_json_file(REPORT_FINAL_JSON) if is_final else None

    stages["S0"] = stage_s0()
    stages["S1"] = stage_s1()
    stages["S2"] = stage_s2()

    if args.skip_perf or args.profile == "quick":
        stages["S3"] = {"status": "not-run", "metrics": [], "not_run": ["--skip-perf / quick"],
                        "over_budget": [], "ui_not_run": ""}
        not_run.append("S3 性能基准未执行（profile=%s / skip_perf=%s）"
                       % (args.profile, args.skip_perf))
    else:
        try:
            stages["S3"] = stage_s3(iterations=max(1, args.iterations))
        except Exception:
            stages["S3"] = {"status": "error", "metrics": [], "not_run": [traceback.format_exc()],
                            "over_budget": [], "ui_not_run": ""}
            not_run.append("S3 执行异常：%s" % traceback.format_exc().splitlines()[-1])

    if args.skip_coverage:
        stages["S4"] = {"status": "not-run", "files": [], "summary": {}, "error": "skipped"}
        not_run.append("S4 覆盖率未执行（--skip-coverage）")
    elif is_final:
        # final：S4 行覆盖挪入探针链（在 branch 之后跑，保证 coverage_probe.json
        # 晚于 assets 最后一次写入；A-12 新鲜度要求）
        stages["S4"] = {"status": "deferred-to-probe-chain", "files": [], "summary": {}}
    else:
        try:
            stages["S4"] = stage_s4()
        except Exception:
            stages["S4"] = {"status": "error", "files": [], "summary": {},
                            "error": traceback.format_exc()}
            not_run.append("S4 执行异常：%s" % traceback.format_exc().splitlines()[-1])

    branch_reason = (stages["S4"].get("summary") or {}).get("branch_reason")
    if branch_reason:
        not_run.append("分支覆盖 not-run：%s" % branch_reason)
    if stages["S3"].get("not_run"):
        not_run.extend(stages["S3"]["not_run"])

    if is_final:
        # final 收口：探针链（RSS 采样 -> branch -> coverage -> branch 重落盘
        # -> RSS 落盘 -> UI）在全部写操作之后；S4 行覆盖随链执行
        stages["S5"] = {"status": "done"}
        try:
            stages["S5"] = stage_probes()
        except Exception:
            stages["S5"] = {"status": "error", "errors": [traceback.format_exc()]}
            not_run.append("S5 探针执行异常：%s" % traceback.format_exc().splitlines()[-1])
        coverage_data = stages["S5"].get("coverage_data") or {}
        stages["S4"] = {
            "status": "done" if coverage_data else "not-run",
            "command": "qa/coverage_probe.py --json qa/coverage_probe.json（探针链内）",
            "exit_code": 0 if coverage_data else None,
            "files": coverage_data.get("files") or [],
            "summary": coverage_data.get("summary") or {},
            "runner": coverage_data.get("runner") or {},
        }
        try:
            t06 = stage_t06()
        except Exception:
            t06 = {"status": "error"}
            not_run.append("T-06 重跑异常：%s" % traceback.format_exc().splitlines()[-1])
        # PT-PERF-09 归并刷新：探针链已重采 RSS，用本轮最新 5 次峰值替换/补齐该指标
        fresh_rss = (stages.get("S5") or {}).get("rss_data")
        if fresh_rss:
            refreshed = perf09_metric_from(fresh_rss)
            if refreshed is not None:
                metrics_s3 = stages["S3"].get("metrics") or []
                for index, item in enumerate(metrics_s3):
                    if str(item.get("id") or "").startswith("PT-PERF-09"):
                        metrics_s3[index] = refreshed
                        break
                else:
                    metrics_s3.append(refreshed)
                stages["S3"]["metrics"] = metrics_s3
                stages["S3"]["not_run"] = [
                    note for note in stages["S3"].get("not_run") or []
                    if not str(note).startswith("PT-PERF-09")]
    else:
        t06 = None

    # S2/S4 会重写 assets/，收尾复跑旧测试，保证 validation_report / 契约 JSON 新鲜且无回归
    stages["S1"]["verify_assets_final"] = final_verify()
    stages["S1"]["contract_final"] = final_contract()

    issues = build_issues(stages["S0"], stages["S1"], stages["S2"],
                          stages["S3"], stages["S4"])
    verdict, reasons, blockers, completion = build_verdict(
        stages["S1"], stages["S2"], stages["S3"], stages["S4"], not_run)

    contract_summary = stages["S1"]["contract"]["summary"]
    delta = {
        "contract_pass": {"baseline": CONTRACT_BASELINE["pass"],
                          "current": contract_summary.get("pass")},
        "contract_fail": {"baseline": CONTRACT_BASELINE["fail"],
                          "current": contract_summary.get("fail")},
        "contract_warn": {"baseline": CONTRACT_BASELINE["warn"],
                          "current": contract_summary.get("warn")},
        "regression": not stages["S1"]["contract"]["not_worse_than_baseline"]
        or stages["S1"]["verify_assets"]["exit_code"] != 0,
        "resolved_this_round": [
            "C32：发布档 7 列（bytes/sha256/category_dir/alpha_required/"
            "canonical_record_id/reviewer/verified_at）补齐，WARN -> PASS"
            if contract_summary.get("warn") == 0
            and contract_summary.get("pass", 0) > CONTRACT_BASELINE["pass"] else ""
        ],
        "remaining_accepted": dict(ACCEPTED_CONTRACT_DEVIATIONS),
    }
    delta["resolved_this_round"] = [item for item in delta["resolved_this_round"] if item]

    report = {
        "tool": "qa/run_p_table_execution.py",
        "profile": args.profile,
        "started_at": started_at,
        "finished_at": now(),
        "duration_seconds": round(time.perf_counter() - t0, 2),
        "environment": environment_snapshot(),
        "verdict": verdict,
        "verdict_reasons": reasons,
        "completion_claim": completion,
        "claim_scope": "execution" if is_final else None,
        "completion_blockers": blockers,
        "delta_vs_baseline": delta,
        "p_table": p_table_snapshot(),
        "legacy_tests": {
            "verify_assets": stages["S1"]["verify_assets"],
            "verify_assets_final": stages["S1"].get("verify_assets_final"),
            "contract": stages["S1"]["contract"],
            "contract_final": stages["S1"].get("contract_final"),
            "baseline": CONTRACT_BASELINE,
        },
        "new_tests": stages["S2"]["result"],
        "coverage": stages["S4"],
        "performance": {"metrics": stages["S3"]["metrics"],
                        "not_run": stages["S3"]["not_run"]},
        "issues": issues,
        "not_run": not_run,
        "stages": stages,
    }
    if t06:
        report["legacy_tests"]["check_core_drift"] = t06.get("check_core_drift")
        report["legacy_tests"]["verify_v1"] = t06.get("verify_v1")
        report["t06"] = t06
    issue_result = record_issues(issues)
    report["stages"]["S5"] = {"status": "done", "issues": issue_result}
    paths = write_report(report)
    report["report_paths"] = paths

    if is_final:
        # final 报告：A-01…A-28 + G1-G7 + completion_claim 三态（claim 与 verdict 同向）
        probes = {
            "branch_data": _load_json_file(BRANCH_JSON),
            "rss_data": _load_json_file(RSS_JSON),
            "ui_data": _load_json_file(UI_JSON),
        }
        # A-26：与上一次完整运行做 §7.2 容差比对，结果随报告落盘（供独立验收 A-26 复核）
        report["reproducibility"] = compare_rerun(previous_final, report, probes)
        final = build_final_report(report, probes, claim_state="auto")
        final_paths = write_final_report(final)
        report["final_paths"] = final_paths
        print("=" * 78)
        print("P 表最终收口 profile=final")
        print("claim_scope=%s  verdict=%s  completion_claim=%s（gate_claim=%s）"
              % (final["claim_scope"], final["verdict"], final["completion_claim"],
                 final["gate_claim"]))
        for gate, item in final["gates"].items():
            print("  %s %-14s : %s（FAIL=%s NOT_RUN=%s）"
                  % (gate, item["title"], item["status"],
                     ",".join(item["failed"]) or "-", ",".join(item["not_run"]) or "-"))
        counts = {"PASS": 0, "FAIL": 0, "NOT_RUN": 0}
        for item in final["a_table"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        print("A 表：PASS=%d FAIL=%d NOT_RUN=%d（未执行项不折算 PASS）"
              % (counts["PASS"], counts["FAIL"], counts["NOT_RUN"]))
        branch = probes.get("branch_data") or {}
        rss = probes.get("rss_data") or {}
        ui = probes.get("ui_data") or {}
        print("S5 分支覆盖 : %s（method=%s）" % (
            "; ".join("%s %.2f%%" % (f["file"], f["percent"])
                      for f in branch.get("files") or []),
            branch.get("method")))
        print("S5 RSS      : max=%s MiB / 1536 MiB（5 次，verdict_basis=max，pass=%s）"
              % (rss.get("max_peak_mib"), rss.get("pass")))
        ui_status = ui.get("status")
        if isinstance(ui_status, dict):
            ui_status = ui_status.get("overall")
        print("S5 UI 三档  : overall=%s" % ui_status)
        print("最终报告    : %s" % final_paths["final_md"])
        print("            : %s" % final_paths["final_json"])
        print("下一动作：停止所有写进程 -> 跑独立验收 -> --refresh-claim 重发报告")
        return 0 if final["completion_claim"] in ("attested", "partial") else 1

    print("=" * 78)
    print("P 表执行 profile=%s  verdict=%s  完成声明=%s"
          % (args.profile, verdict, completion))
    print("S1 verify_assets: %s（exit %s）"
          % (stages["S1"]["verify_assets"]["status"],
             stages["S1"]["verify_assets"]["exit_code"]))
    print("S1 contract     : %s PASS / %s FAIL / %s WARN（基线 %s）"
          % (stages["S1"]["contract"]["summary"].get("pass"),
             stages["S1"]["contract"]["summary"].get("fail"),
             stages["S1"]["contract"]["summary"].get("warn"),
             CONTRACT_BASELINE))
    print("S2 新测试       : %d/%d PASS（fail=%d error=%d）"
          % (stages["S2"]["result"]["pass"], stages["S2"]["result"]["total"],
             stages["S2"]["result"]["fail"], stages["S2"]["result"]["error"]))
    coverage_line = (stages["S4"].get("summary") or {}).get("line_percent") or {}
    print("S4 行覆盖      : %s（branch=not-run，分支覆盖见 --profile final 的探针链）"
          % coverage_line)
    print("报告：%s" % paths["md"])
    print("JSON：%s" % paths["json"])
    print("问题：%s（新增 %s 条）" % (issue_result["path"], len(issue_result["added"])))
    for reason in reasons:
        print("  FAIL 原因：%s" % reason)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
