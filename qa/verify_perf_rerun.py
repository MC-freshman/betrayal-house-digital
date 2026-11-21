#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa/verify_perf_rerun.py —— 第 4 轮收口独立验收：15 项性能 + 第二次复跑一致性（只读）

只读纪律：
- 本脚本不写任何文件、不运行测试/探针、不调用 subprocess、不导入被测实现模块。
- 只读取既有报告与证据 JSON，独立重算判定并打印结论。
- 缺证据标 FAIL/NOT_RUN；未执行不称 PASS；实现方自报字段只作交叉核对，不替代独立验算。

上游判据（只读引用，不在此复述全文）：
- .codebuddy/wfat/run4_completion_criteria.md
  - §4 A-20/A-21：真实 DPI 判定表（100%/125%/150% 物理尺寸 ±2px、awareness ∈ {1,2}）
  - §5 A-23：15 项预算全表（§5.1）与判定方法（§5.2：采样规则固定；超预算连续 3 次才定缺陷）
  - §6 A-25：PT-PERF-002 关闭须回写 issues.jsonl（status=resolved + evidence + resolved_at）
  - §7 A-26：复跑比对范围与容忍度（§7.2：哈希 bit 级一致；测试/覆盖率一致；RSS/性能只比对判定不比对数值）
- .codebuddy/wfat/run2_p_table_plan.md §5.3：15 项性能预算（上限）与采样规则
- qa/run_p_table_execution.py stage_s3 / metric() / stats_of()：实测数据结构来源

用法（PowerShell，在 source/desktop/game 下）：
  python qa/verify_perf_rerun.py
  python qa/verify_perf_rerun.py --report1 <第1轮报告.json> --report2 <第2轮报告.json>
  python qa/verify_perf_rerun.py --ui-capture <ui_capture.json> --issues <issues.jsonl>

退出码：0 = PASS；1 = FAIL（任一门禁判定失败）；2 = NOT_RUN（无 FAIL 但证据不齐）。
建议把输出重定向留档（输出本身只进 stdout，本脚本不落盘）：
  python qa/verify_perf_rerun.py > qa_perf_rerun_verdict.txt
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径与常量（默认指向当前冻结链产物；可用 CLI 覆盖）
# ---------------------------------------------------------------------------
QA_DIR = Path(__file__).resolve().parent          # source/desktop/game/qa
GAME_DIR = QA_DIR.parent                          # source/desktop/game
REPORTS_DIR = GAME_DIR / "reports"
DEFAULT_REPORT2 = REPORTS_DIR / "p_table_execution_final.json"
DEFAULT_UI = QA_DIR / "ui_capture.json"
DEFAULT_ISSUES = QA_DIR / "issues.jsonl"
DEFAULT_RSS = QA_DIR / "rss_probe.json"
FREEZE_MANIFEST = QA_DIR / "freeze_manifest.json"

EXECUTOR_TOOL = "qa/run_p_table_execution.py"

# 15 项性能预算与采样规则（run2 §5.3 / run4 §5.1；判据口径，不得事后放宽）
# stat: 该项的判定统计量；min_samples: 采样规则固定次数（不足即采样不合规）
PERF_RULES = {
    "01": {"budget": 5000.0,   "unit": "ms",  "stat": "median", "min_samples": 5,
           "title": "ptable 构建（asset_pipeline --stage ptable）"},
    "02": {"budget": 3000.0,   "unit": "ms",  "stat": "median", "min_samples": 5,
           "title": "placeholders 阶段"},
    "03": {"budget": 240000.0, "unit": "ms",  "stat": "median", "min_samples": 3,
           "title": "all 阶段（含 95 张规范化）"},
    "04": {"budget": 150.0,    "unit": "ms",  "stat": "p95",    "min_samples": 10,
           "title": "AssetRegistry.load(p_table.json)"},
    "05": {"budget": 500.0,    "unit": "ms",  "stat": "p95",    "min_samples": 10,
           "title": "10,000 次 resolve（五类键混合）", "per_call_p95": 0.05},
    "06": {"budget": 90000.0,  "unit": "ms",  "stat": "median", "min_samples": 5,
           "title": "verify_assets.py 全量"},
    "07": {"budget": 150000.0, "unit": "ms",  "stat": "median", "min_samples": 5,
           "title": "verify_assets_contract.py 全量（含解码）"},
    "08": {"budget": 25000.0,  "unit": "ms",  "stat": "median", "min_samples": 5,
           "title": "verify_assets_contract.py --no-decode"},
    "09": {"budget": 1536.0,   "unit": "MiB", "stat": "max",    "min_samples": 5,
           "title": "构建峰值 RSS（--stage all，0.2s 采样）", "special": "rss"},
    "10": {"budget": 80.0,     "unit": "MiB", "stat": "max",    "min_samples": 1,
           "title": "load 峰值增量 RSS（加载前后差值）"},
    "11": {"budget": 120.0,    "unit": "ms",  "stat": "p95",    "min_samples": 30,
           "title": "UI 房间首帧（512x512→128）"},
    "12": {"budget": 150.0,    "unit": "ms",  "stat": "p95",    "min_samples": 30,
           "title": "UI 卡牌首帧（480x672→240x336）"},
    "13": {"budget": 16.0,     "unit": "ms",  "stat": "p95",    "min_samples": 100,
           "title": "UI 缓存命中（同图重复绑定）"},
    "14": {"budget": 400.0,    "unit": "ms",  "stat": "p95",    "min_samples": 10,
           "title": "一屏 12 图块批量绑定"},
    "15": {"budget": 2500.0,   "unit": "ms",  "stat": "median", "min_samples": 10,
           "title": "冷启动到主界面（含 registry load）"},
}

# run4 §4.2 逐档判定表（物理尺寸，±2px）
UI_TIER_TABLE = {
    "100": {"system_dpi": 96,  "room": (128, 128), "card": (240, 336)},
    "125": {"system_dpi": 120, "room": (160, 160), "card": (300, 420)},
    "150": {"system_dpi": 144, "room": (192, 192), "card": (360, 504)},
}
UI_SIZE_TOLERANCE = 2
MIB = 1024.0 * 1024.0

CHECKS = []          # [{id, name, status, detail, gate}]


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def add_check(cid, name, status, detail, gate=True):
    CHECKS.append({"id": cid, "name": name, "status": status,
                   "detail": detail, "gate": gate})


def load_json(path):
    """读 JSON（容忍 BOM）。返回 (data, err)。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh), ""
    except FileNotFoundError:
        return None, "文件不存在：%s" % path
    except Exception as exc:  # 只读容错，不吞上下文
        return None, "%s: %s" % (type(exc).__name__, exc)


def parse_dt(text):
    if not text or not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text.strip())
    except ValueError:
        try:
            return datetime.strptime(text.strip()[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None


def fmt(v):
    if isinstance(v, float):
        return ("%.3f" % v).rstrip("0").rstrip(".")
    return str(v)


def metric_perf_id(item):
    m = re.search(r"PT-PERF-(\d{2})", str(item.get("id") or ""))
    return m.group(1) if m else None


def collect_perf_metrics(report):
    """返回 {perf_id: metric}（取报告 performance.metrics 与 stages.S3.metrics 的并集，后者不覆盖前者）。"""
    merged = {}
    for block_name in ("performance", "stages"):
        block = report.get(block_name) or {}
        if block_name == "stages":
            block = (report.get("stages") or {}).get("S3") or {}
        for item in (block.get("metrics") or []):
            pid = metric_perf_id(item)
            if pid and pid not in merged:
                merged[pid] = item
    return merged


def value_in_budget_unit(value, unit):
    """把 metric 数值换算成 MiB（PT-PERF-09/10 单位自适应）。"""
    if unit in ("bytes", "B"):
        return value / MIB
    return value  # MiB / MB 近似按 MiB 判（判据口径为 MiB）


def within_report_window(ts_text, report, before_slack=60, after_slack=600):
    started = parse_dt(report.get("started_at"))
    finished = parse_dt(report.get("finished_at"))
    ts = parse_dt(ts_text)
    if not (started and finished and ts):
        return False, "时间戳不可解析（started/finished/ts=%r）" % ts_text
    low = min(started, finished).timestamp() - before_slack
    high = max(started, finished).timestamp() + after_slack
    return (low <= ts.timestamp() <= high), ""


# ---------------------------------------------------------------------------
# 检查组 1：15 项性能（A-23，run4 §5）
# ---------------------------------------------------------------------------
def replace_check(cid, name, status, detail, gate=True):
    """归并路径复写同 ID 检查项，避免重复条目。"""
    CHECKS[:] = [c for c in CHECKS if c["id"] != cid]
    add_check(cid, name, status, detail, gate=gate)


def check_perf_15(report):
    metrics = collect_perf_metrics(report)
    results = {}
    for pid in sorted(PERF_RULES):
        rule = PERF_RULES[pid]
        cid = "VP-P%s" % pid
        item = metrics.get(pid)
        if item is None:
            results[pid] = "NOT_RUN"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "NOT_RUN",
                      "报告无 PT-PERF-%s 实测项；未测不折算 PASS" % pid)
            continue

        samples = item.get("samples") or {}
        count = samples.get("count") or 0
        budget = item.get("budget")
        executor_within = item.get("within_budget")
        unit = str(item.get("unit") or rule["unit"])

        # 空样本
        if count <= 0 or not samples:
            results[pid] = "FAIL"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL",
                      "samples 空或 count=0，证据无效")
            continue

        # 采样规则固定（run4 §5.2.2）
        if count < rule["min_samples"]:
            results[pid] = "FAIL"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL",
                      "采样次数 %d < 采样规则 %d 次（run4 §5.1）；采样规则固定，不得以少次代替" % (
                          count, rule["min_samples"]))
            continue

        # 预算口径（防放宽，run4 §5.2.4）
        if budget is not None:
            expected_budget = rule["budget"]
            got = value_in_budget_unit(float(budget), unit) if rule["unit"] == "MiB" else float(budget)
            if abs(got - expected_budget) > max(1e-6, expected_budget * 1e-6):
                results[pid] = "FAIL"
                add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL",
                          "预算字段 %s%s 与判据 %s%s 不一致（疑似放宽；调整预算须架构书面批准）" % (
                              fmt(budget), unit, fmt(expected_budget), rule["unit"]))
                continue

        # 判定统计量
        stat_name = rule["stat"]
        raw = samples.get(stat_name)
        if raw is None:
            results[pid] = "FAIL"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL",
                      "samples 缺少判定统计量 %s" % stat_name)
            continue
        value = value_in_budget_unit(float(raw), unit)
        over = value > rule["budget"]
        # 超预算需连续 3 次复现才定缺陷（run4 §5.2.3）：单次统计量超限先记 FAIL 候选，
        # 连续性由修复回路核实；本脚本按“任一轮超限即登记 FAIL”保守判定。
        if over:
            results[pid] = "FAIL"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL",
                      "%s=%s%s > 预算 %s%s（超预算；确认缺陷须连续 3 次复现，修复后重跑受影响项）" % (
                          stat_name, fmt(value), rule["unit"], fmt(rule["budget"]), rule["unit"]))
            continue

        # 执行器判定字段须同向（自报只作交叉核对）
        if executor_within is not True:
            results[pid] = "FAIL"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL",
                      "独立重算达标但报告 within_budget=%r，报告判定与实测矛盾" % (executor_within,))
            continue

        # 项内附加判据
        extra_ok, extra_detail = True, ""
        if pid == "05":
            per_call = item.get("per_call") or {}
            pc_p95 = per_call.get("p95")
            if pc_p95 is None:
                extra_ok, extra_detail = False, "缺 per_call.p95（单次 P95 ≤%s ms 判据）" % rule["per_call_p95"]
            elif float(pc_p95) > rule["per_call_p95"]:
                extra_ok, extra_detail = False, "per_call.p95=%s ms > %s ms" % (
                    fmt(float(pc_p95)), fmt(rule["per_call_p95"]))
            elif item.get("per_call_within_budget") is not True:
                extra_ok, extra_detail = False, "报告 per_call_within_budget=%r 与实测矛盾" % (
                    item.get("per_call_within_budget"),)
        if pid == "10":
            mib_value = value_in_budget_unit(float(raw), unit)
            if unit == "ms":
                extra_ok, extra_detail = False, "单位为 %s，与增量 RSS 指标不符" % unit
            elif mib_value > rule["budget"]:
                extra_ok, extra_detail = False, "增量 RSS=%s MiB > 80 MiB" % fmt(mib_value)

        if not extra_ok:
            results[pid] = "FAIL"
            add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "FAIL", extra_detail)
            continue
        results[pid] = "PASS"
        add_check(cid, "PT-PERF-%s %s" % (pid, rule["title"]), "PASS",
                  "%s=%s%s ≤ %s%s；count=%d；within_budget=True" % (
                      stat_name, fmt(value), rule["unit"], fmt(rule["budget"]),
                      rule["unit"], count))

    # PT-PERF-09 归并路径（C-1：与 A-18 rss_probe 同方法同预算，不单列补测）
    if results.get("09") == "NOT_RUN":
        rss = report.get("rss") or {}
        interval = rss.get("sampling_interval_ms")
        max_peak = rss.get("max_peak_mib")
        ok, why = within_report_window(rss.get("emitted_at") or rss.get("sampled_at"), report)
        if rss.get("pass") is True and max_peak is not None \
                and float(max_peak) <= PERF_RULES["09"]["budget"] \
                and interval == 200 and ok:
            results["09"] = "PASS"
            replace_check("VP-P09", "PT-PERF-09 %s" % PERF_RULES["09"]["title"], "PASS",
                          "按 C-1 归并报告内嵌 rss 块：max_peak=%s MiB ≤1536 MiB；采样间隔 %sms；"
                          "时间戳与本轮窗口同源（budget_source=A-18/rss_probe.json）" % (
                              fmt(float(max_peak)), fmt(interval)))
        else:
            detail = []
            if rss.get("pass") is not True:
                detail.append("rss.pass=%r" % (rss.get("pass"),))
            if max_peak is None or float(max_peak or 0) > 1536:
                detail.append("max_peak_mib=%r" % (max_peak,))
            if interval != 200:
                detail.append("sampling_interval_ms=%r≠200" % (interval,))
            if not ok:
                detail.append(why or "rss 时间戳不在本轮报告窗口内")
            replace_check("VP-P09", "PT-PERF-09 %s" % PERF_RULES["09"]["title"], "NOT_RUN",
                          "归并路径证据不足：%s；无实测项，未测不折算 PASS" % "；".join(detail))
    return results


# ---------------------------------------------------------------------------
# 检查组 2：a_table 一致性（A-23/A-26 状态与独立重算同向）
# ---------------------------------------------------------------------------
def a_table_item(report, aid):
    for item in (report.get("a_table") or []):
        if item.get("id") == aid:
            return item
    return None


def check_a_table_consistency(report, perf_results, rerun_status):
    a23 = a_table_item(report, "A-23")
    computed23 = "PASS" if all(v == "PASS" for v in perf_results.values()) else \
        ("FAIL" if "FAIL" in perf_results.values() else "NOT_RUN")
    if a23 is None:
        add_check("VP-A23", "a_table A-23 与独立重算同向", "FAIL", "报告 a_table 缺 A-23 条目")
    else:
        reported = str(a23.get("status") or "").upper()
        if reported == computed23:
            add_check("VP-A23", "a_table A-23 与独立重算同向", "PASS",
                      "A-23=%s；独立重算=%s（实测 %d/15）" % (
                          reported, computed23,
                          sum(1 for v in perf_results.values() if v == "PASS")))
        else:
            add_check("VP-A23", "a_table A-23 与独立重算同向", "FAIL",
                      "A-23 报告状态=%s，独立重算=%s；口径不一致须重出报告（未测项不折算 PASS）" % (
                          reported, computed23))

    a26 = a_table_item(report, "A-26")
    computed26 = rerun_status
    if a26 is None:
        add_check("VP-A26", "a_table A-26 与独立重算同向", "FAIL", "报告 a_table 缺 A-26 条目")
    else:
        reported = str(a26.get("status") or "").upper()
        if reported == computed26:
            add_check("VP-A26", "a_table A-26 与独立重算同向", "PASS",
                      "A-26=%s；独立重算=%s" % (reported, computed26))
        else:
            add_check("VP-A26", "a_table A-26 与独立重算同向", "FAIL",
                      "A-26 报告状态=%s，独立重算=%s（第二次干净复跑证据与报告必须同源，不拼接旧快照）" % (
                          reported, computed26))
    return computed23


# ---------------------------------------------------------------------------
# 检查组 3：第二次复跑一致性（A-26，run4 §7.2）
# ---------------------------------------------------------------------------
def discover_report1(report2_path, report2):
    """在第 1 轮归档中找 report1：同 report_id 的更低版本，或 supersedes 链上的 id。
    禁止拼接旧链快照（p_table_execution_report.json 等非本轮链文件一律不用）。"""
    rid2 = report2.get("report_id")
    supersedes = str(report2.get("supersedes") or "")
    ver2 = int(report2.get("report_version") or 0)
    profile2 = report2.get("profile")
    candidates = []
    for path in sorted(REPORTS_DIR.glob("*.json")):
        try:
            if path.resolve() == report2_path.resolve():
                continue
            data, _err = load_json(path)
        except Exception:
            continue
        if data is None:
            continue
        if data.get("tool") != EXECUTOR_TOOL:
            continue
        if profile2 and data.get("profile") != profile2:
            continue
        same_chain = (data.get("report_id") == rid2 and int(data.get("report_version") or 0) < ver2) \
            or (rid2 and rid2 in supersedes and data.get("report_id") == rid2)
        if not same_chain:
            continue
        gen = parse_dt(data.get("generated_at"))
        gen2 = parse_dt(report2.get("generated_at"))
        if gen and gen2 and gen >= gen2:
            continue  # 只取早于第 2 轮的版本
        candidates.append((data.get("generated_at") or "", path, data))
    if not candidates:
        return None, ("未在第 2 轮 supersede 链上找到第 1 轮报告；复跑前须把第 1 轮 report JSON 归档"
                      "（同目录版本归档），不拼接旧链快照。可用 --report1 显式指定。")
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][2], str(candidates[-1][1])


def subset_equal(a, b, keys):
    for k in keys:
        if (a or {}).get(k) != (b or {}).get(k):
            return False, k
    return True, ""


def check_rerun(report1, report2, report1_src):
    gate_checks = []
    # VP-R30 报告对有效性
    if report1 is None:
        add_check("VP-R30", "复跑报告对（第 1 轮 + 第 2 轮）", "NOT_RUN", report1_src)
        return "NOT_RUN"
    if report1.get("report_id") == report2.get("report_id") \
            and int(report1.get("report_version") or 0) == int(report2.get("report_version") or 0):
        add_check("VP-R30", "复跑报告对（第 1 轮 + 第 2 轮）", "FAIL",
                  "两份报告 report_id/report_version 相同，疑似同一份文件，不构成两次独立运行")
        return "FAIL"
    g1 = parse_dt(report1.get("generated_at"))
    g2 = parse_dt(report2.get("generated_at"))
    if not (g1 and g2 and g1 < g2):
        add_check("VP-R30", "复跑报告对（第 1 轮 + 第 2 轮）", "FAIL",
                  "两轮 generated_at 无先后关系（#1=%r, #2=%r）" % (
                      report1.get("generated_at"), report2.get("generated_at")))
        return "FAIL"
    add_check("VP-R30", "复跑报告对（第 1 轮 + 第 2 轮）", "PASS",
              "#1=%s(%s, v%s)@%s ← %s；#2=%s(v%s)@%s" % (
                  report1.get("report_id"), report1.get("profile"),
                  report1.get("report_version"), report1.get("generated_at"),
                  report1_src,
                  report2.get("report_id"), report2.get("report_version"),
                  report2.get("generated_at")))

    # VP-R31 冻结哈希 bit 级一致（S0.files + S0.photos.combined_sha256）
    f1 = ((report1.get("stages") or {}).get("S0") or {}).get("files") or {}
    f2 = ((report2.get("stages") or {}).get("S0") or {}).get("files") or {}
    diffs = []
    for rel in sorted(set(f1) | set(f2)):
        h1 = (f1.get(rel) or {}).get("sha256")
        h2 = (f2.get(rel) or {}).get("sha256")
        if h1 != h2:
            diffs.append("%s: %s != %s" % (rel, h1, h2))
    p1 = ((report1.get("stages") or {}).get("S0") or {}).get("photos") or {}
    p2 = ((report2.get("stages") or {}).get("S0") or {}).get("photos") or {}
    if (p1.get("combined_sha256") != p2.get("combined_sha256")) or (p1.get("count") != p2.get("count")):
        diffs.append("photos: combined_sha256/count 不一致（#1=%s/%s, #2=%s/%s）" % (
            p1.get("combined_sha256"), p1.get("count"),
            p2.get("combined_sha256"), p2.get("count")))
    if diffs:
        add_check("VP-R31", "冻结哈希 bit 级一致（S0 13 文件 + photos）", "FAIL",
                  "哈希漂移 → A-26 FAIL → not-attested，按哈希漂移作废下游证据回 S0：%s" % "; ".join(diffs[:6]))
        gate_checks.append("FAIL")
    else:
        add_check("VP-R31", "冻结哈希 bit 级一致（S0 13 文件 + photos）", "PASS",
                  "%d 个冻结文件 + photos(combined=%s) 两轮完全一致" % (
                      len(set(f1) & set(f2)), p2.get("combined_sha256")))
        gate_checks.append("PASS")

    # VP-R32 测试结果一致（new_tests / legacy_tests / S2）
    diffs = []
    ok, bad = subset_equal(report1.get("new_tests"), report2.get("new_tests"),
                           ["total", "pass", "fail", "error", "skipped"])
    if not ok:
        diffs.append("new_tests.%s" % bad)
    lt1, lt2 = report1.get("legacy_tests") or {}, report2.get("legacy_tests") or {}
    if set(lt1) != set(lt2):
        diffs.append("legacy_tests 键集不一致")
    else:
        for key in sorted(lt1):
            b1, b2 = lt1[key], lt2[key]
            if b1.get("status") != b2.get("status"):
                diffs.append("legacy_tests.%s.status" % key)
            s1, s2 = b1.get("summary"), b2.get("summary")
            if (s1 is None) != (s2 is None):
                diffs.append("legacy_tests.%s.summary 存在性" % key)
            elif s1 is not None and dict(s1) != dict(s2):
                diffs.append("legacy_tests.%s.summary 计数" % key)
    e1 = ((report1.get("stages") or {}).get("S2") or {}).get("exit_code")
    e2 = ((report2.get("stages") or {}).get("S2") or {}).get("exit_code")
    if e1 != e2:
        diffs.append("S2.exit_code")
    r1 = ((report1.get("stages") or {}).get("S2") or {}).get("result") or {}
    r2 = ((report2.get("stages") or {}).get("S2") or {}).get("result") or {}
    ok2, bad2 = subset_equal(r1, r2, ["total", "pass", "fail", "error"])
    if not ok2:
        diffs.append("S2.result.%s" % bad2)
    if diffs:
        add_check("VP-R32", "测试结果一致（48 项 / legacy / 契约 / S2）", "FAIL",
                  "任一翻转即 FAIL：%s" % "; ".join(sorted(set(diffs))))
        gate_checks.append("FAIL")
    else:
        add_check("VP-R32", "测试结果一致（48 项 / legacy / 契约 / S2）", "PASS",
                  "new_tests %s/%s；legacy %s；S2 %s/%s 两轮一致" % (
                      (report2.get("new_tests") or {}).get("pass"),
                      (report2.get("new_tests") or {}).get("total"),
                      sorted(lt2.keys()), r2.get("pass"), r2.get("total")))
        gate_checks.append("PASS")

    # VP-R33 覆盖率一致（分子/分母/百分比两位小数 + 分支判定）
    def coverage_fingerprint(rep):
        out = []
        for f in (rep.get("coverage") or {}).get("files") or []:
            out.append((f.get("file"), f.get("total_lines"), f.get("covered_lines"),
                        round(float(f.get("line_percent") or 0.0), 2),
                        f.get("meets_threshold")))
        br = rep.get("branch_coverage") or {}
        for f in br.get("files") or []:
            out.append((f.get("file"), "branch", f.get("total"), f.get("covered"),
                        round(float(f.get("percent") or 0.0), 2), f.get("meets_threshold")))
        out.append(("probe_summary.branch_status", (rep.get("probe_summary") or {}).get("branch_status")))
        return out
    fp1, fp2 = coverage_fingerprint(report1), coverage_fingerprint(report2)
    if fp1 != fp2:
        delta = [x for x in fp2 if x not in fp1] + [x for x in fp1 if x not in fp2]
        add_check("VP-R33", "覆盖率一致（行/分支 分子分母百分比）", "FAIL",
                  "覆盖率漂移须重新对账，不得只解释不重测；差异（前 6）：%s" % "; ".join(map(str, delta[:6])))
        gate_checks.append("FAIL")
    else:
        add_check("VP-R33", "覆盖率一致（行/分支 分子分母百分比）", "PASS",
                  "%d 项指纹两轮一致（含 branch 状态）" % len(fp2))
        gate_checks.append("PASS")

    # VP-R34 RSS 判定一致（数值允许波动，verdict 必须一致）
    v1 = (report1.get("rss") or {}).get("pass")
    v2 = (report2.get("rss") or {}).get("pass")
    if v1 is not v2:
        add_check("VP-R34", "RSS 判定（5/5 ≤1536 MiB）两轮一致", "FAIL",
                  "rss.pass #1=%r #2=%r；任一轮单次越界按 P-03 处理" % (v1, v2))
        gate_checks.append("FAIL")
    else:
        add_check("VP-R34", "RSS 判定（5/5 ≤1536 MiB）两轮一致", "PASS",
                  "两轮 rss.pass=%r；峰值数值不比对（允许波动：#1 max=%s, #2 max=%s MiB）" % (
                      v2, fmt((report1.get("rss") or {}).get("max_peak_mib") or -1),
                      fmt((report2.get("rss") or {}).get("max_peak_mib") or -1)))
        gate_checks.append("PASS")

    # VP-R35 性能判定不翻转（中位数/P95 数值允许波动）
    m1, m2 = collect_perf_metrics(report1), collect_perf_metrics(report2)
    flips = []
    for pid in sorted(set(m1) | set(m2)):
        w1 = (m1.get(pid) or {}).get("within_budget")
        w2 = (m2.get(pid) or {}).get("within_budget")
        if w1 is not w2:
            flips.append("PT-PERF-%s: %r -> %r" % (pid, w1, w2))
        pc1 = (m1.get(pid) or {}).get("per_call_within_budget")
        pc2 = (m2.get(pid) or {}).get("per_call_within_budget")
        if (pc1 is None) != (pc2 is None) or (pc1 is not None and pc1 is not pc2):
            flips.append("PT-PERF-%s per_call: %r -> %r" % (pid, pc1, pc2))
    if flips:
        add_check("VP-R35", "性能 15 项判定不翻转（数值可抖动）", "FAIL",
                  "判定翻转按最不利值定并触发 P-05 连续 3 次规则：%s" % "; ".join(flips))
        gate_checks.append("FAIL")
    else:
        add_check("VP-R35", "性能 15 项判定不翻转（数值可抖动）", "PASS",
                  "两轮 %d 个性能项 within_budget 判定一致" % len(set(m1) & set(m2)))
        gate_checks.append("PASS")

    # VP-R36 报告 §16 可复现段（reproducibility 块须非空且含两轮标识）
    rep_block = report2.get("reproducibility") or {}
    if not rep_block:
        add_check("VP-R36", "报告 §16 可复现段（reproducibility）", "NOT_RUN",
                  "第 2 轮报告 reproducibility={}：复跑比对结果未写入报告 §16，属报告完整性缺口")
        gate_checks.append("NOT_RUN")
    else:
        text = json.dumps(rep_block, ensure_ascii=False)
        if report2.get("report_id") in text and report1.get("report_id") in text:
            add_check("VP-R36", "报告 §16 可复现段（reproducibility）", "PASS",
                      "块非空且引用两轮 report_id")
            gate_checks.append("PASS")
        else:
            add_check("VP-R36", "报告 §16 可复现段（reproducibility）", "FAIL",
                      "reproducibility 块未同时引用两轮 report_id（#1=%s, #2=%s）" % (
                          report1.get("report_id"), report2.get("report_id")))
            gate_checks.append("FAIL")

    if "FAIL" in gate_checks:
        return "FAIL"
    if "NOT_RUN" in gate_checks:
        return "NOT_RUN"
    return "PASS"


# ---------------------------------------------------------------------------
# 检查组 4：ui_capture.json 三档状态（A-19 复判 / A-20 / A-21）
# ---------------------------------------------------------------------------
def check_ui(ui_path, report2):
    data, err = load_json(ui_path)
    if data is None:
        add_check("VP-U40", "ui_capture.json 可读", "FAIL", err)
        return
    add_check("VP-U40", "ui_capture.json 可读", "PASS", str(ui_path))

    # 与本轮报告同源（C-3 纪律：证据必须归属当前产物）
    ok, why = within_report_window(data.get("generated_at"), report2)
    add_check("VP-U41", "ui_capture 与第 2 轮报告同源", "PASS" if ok else "FAIL",
              "generated_at=%s；%s" % (data.get("generated_at"), why or "在本轮报告窗口内"))

    scales = {str(s.get("dpi_percent")): s for s in (data.get("scales") or [])}
    for tier in ("100", "125", "150"):
        ref = UI_TIER_TABLE[tier]
        cid = "VP-U4%s" % {"100": "2", "125": "3", "150": "4"}[tier]
        name = "UI %s%% 档（system_dpi=%s，room=%s，card=%s）" % (
            tier, ref["system_dpi"], "x".join(map(str, ref["room"])),
            "x".join(map(str, ref["card"])))
        status_field = (data.get("status") or {}).get(tier)
        scale = scales.get(tier)
        if scale is None or status_field in (None, "not-run"):
            add_check(cid, name, "NOT_RUN", "该档未采集（status=%r）；不得以另两档通过抵消" % status_field)
            continue
        if status_field == "approximated" or scale.get("approximated") is True \
                or scale.get("mode") == "tk-scaling-approximation":
            add_check(cid, name, "FAIL",
                      "status=approximated（tk scaling 近似）不采信；须真实 120/144 DPI 重拍"
                      "（每档注销/重启）或产品书面修订规范后按新表重判")
            continue
        problems = []
        if status_field != "pass" or scale.get("pass") is not True:
            problems.append("status=%r/scale.pass=%r" % (status_field, scale.get("pass")))
        awareness = scale.get("dpi_awareness")
        if awareness not in (1, 2):
            problems.append("dpi_awareness=%r∉{1,2}（awareness=0 直接 FAIL，run4 §4.1.3/C-2）" % (awareness,))
        for key, expect in (("room", ref["room"]), ("card", ref["card"])):
            phys = str(scale.get("%s_physical" % key) or "")
            m = re.match(r"^(\d+)x(\d+)$", phys)
            if not m:
                problems.append("%s_physical=%r 非WxH" % (key, phys))
                continue
            got = (int(m.group(1)), int(m.group(2)))
            if any(abs(g - e) > UI_SIZE_TOLERANCE for g, e in zip(got, expect)):
                problems.append("%s_physical=%s 与判定表 %s 偏差 >%dpx" % (
                    key, phys, "x".join(map(str, expect)), UI_SIZE_TOLERANCE))
            if (scale.get("size_assertions") or {}).get("%s_ok" % key) is not True:
                problems.append("size_assertions.%s_ok=%r" % (key, (scale.get("size_assertions") or {}).get("%s_ok" % key)))
        if problems:
            add_check(cid, name, "FAIL", "；".join(problems))
        else:
            add_check(cid, name, "PASS", "real-screenshot；awareness=%s；物理尺寸命中判定表 ±%dpx；sha256_full=%s…" % (
                awareness, UI_SIZE_TOLERANCE, str(scale.get("sha256_full"))[:12]))

    # C-2：非虚拟化 awareness 采样；顶层与分档矛盾即证据冲突
    top_awareness = (data.get("dpi") or {}).get("dpi_awareness")
    if top_awareness == 0:
        add_check("VP-U45", "DPI awareness 非虚拟化采样（C-2）", "FAIL",
                  "顶层 dpi.dpi_awareness=0（unaware）按 C-2 直接 FAIL；且与 scales 分档记录的 awareness=1 矛盾，"
                  "复跑须用 GetProcessDpiAwareness/GetDpiForSystem 非虚拟化采样并消除矛盾")
    else:
        add_check("VP-U45", "DPI awareness 非虚拟化采样（C-2）", "PASS",
                  "顶层 dpi_awareness=%r" % (top_awareness,))


# ---------------------------------------------------------------------------
# 检查组 5：issues.jsonl PT-PERF-002 关闭（A-25，run4 §6）
# ---------------------------------------------------------------------------
def check_issues(issues_path):
    records = []
    try:
        with open(issues_path, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        add_check("VP-I50", "issues.jsonl PT-PERF-002 已关闭", "FAIL", "文件不存在：%s" % issues_path)
        return
    except Exception as exc:
        add_check("VP-I50", "issues.jsonl PT-PERF-002 已关闭", "FAIL",
                  "%s: %s" % (type(exc).__name__, exc))
        return
    latest = None
    for rec in records:
        if rec.get("defectId") == "PT-PERF-002":
            latest = rec
    if latest is None:
        add_check("VP-I50", "issues.jsonl PT-PERF-002 已关闭", "FAIL",
                  "台账中无 PT-PERF-002 记录（S3 性能补测议题必须登记并关闭，不得静默）")
        return
    status = str(latest.get("status") or "")
    if status == "resolved" and latest.get("evidence") and latest.get("resolved_at"):
        add_check("VP-I50", "issues.jsonl PT-PERF-002 已关闭", "PASS",
                  "status=resolved；resolved_at=%s；evidence=%s" % (
                      latest.get("resolved_at"), str(latest.get("evidence"))[:80]))
    else:
        add_check("VP-I50", "issues.jsonl PT-PERF-002 已关闭", "FAIL",
                  "最新记录 status=%r（evidence=%r, resolved_at=%r）；关闭须回写 resolved + evidence + "
                  "resolved_at（run4 §6.1.3）；open/accepted/needs-decision 均封顶 partial" % (
                      status, latest.get("evidence"), latest.get("resolved_at")))


# ---------------------------------------------------------------------------
# 附加核验（advisory：不改变 overall，只提示）
# ---------------------------------------------------------------------------
def check_advisories(report2, report2_path, rss_path):
    if FREEZE_MANIFEST.is_file():
        add_check("VP-X60", "freeze_manifest.json 存在（S0 冻结，advisory）", "PASS", str(FREEZE_MANIFEST), gate=False)
    else:
        add_check("VP-X60", "freeze_manifest.json 存在（S0 冻结，advisory）", "NOT_RUN",
                  "qa/freeze_manifest.json 尚未生成（run4 §7.1 R2）；A-26 比对以两轮报告内嵌 S0 哈希为准",
                  gate=False)
    rss_data, err = load_json(rss_path)
    s0 = ((report2.get("stages") or {}).get("S0") or {}).get("files") or {}
    pt_sha = (s0.get("assets/p_table.json") or {}).get("sha256")
    if rss_data is None:
        add_check("VP-X61", "rss_probe.json 与冻结产物同源（advisory）", "NOT_RUN", err, gate=False)
    else:
        probe_sha = (rss_data.get("input_sha256") or {}).get("assets/p_table.json")
        ok = rss_data.get("pass") is True and (not probe_sha or not pt_sha or probe_sha == pt_sha)
        add_check("VP-X61", "rss_probe.json 与冻结产物同源（advisory）", "PASS" if ok else "FAIL",
                  "probe pass=%r；p_table.json sha probe=%s… vs 报告 S0=%s…" % (
                      rss_data.get("pass"), str(probe_sha)[:12], str(pt_sha)[:12]), gate=False)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="第 4 轮收口独立验收（只读）：15 项性能 + 第二次复跑一致性 + UI 三档 + PT-PERF-002")
    parser.add_argument("--report2", default=str(DEFAULT_REPORT2),
                        help="第 2 轮（最新）执行报告 JSON（默认 reports/p_table_execution_final.json）")
    parser.add_argument("--report1", default=None,
                        help="第 1 轮执行报告 JSON（默认在 reports/ 内沿 supersedes 链自动发现）")
    parser.add_argument("--ui-capture", default=str(DEFAULT_UI), help="qa/ui_capture.json")
    parser.add_argument("--issues", default=str(DEFAULT_ISSUES), help="qa/issues.jsonl")
    parser.add_argument("--rss-probe", default=str(DEFAULT_RSS), help="qa/rss_probe.json（advisory）")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows GBK 控制台保护
    except Exception:
        pass

    print("=" * 72)
    print("qa/verify_perf_rerun.py —— 只读独立验收（不写文件/不跑测试/不被子进程）")
    print("判据：run4_completion_criteria.md §4/§5/§6/§7 + run2_p_table_plan.md §5.3")
    print("=" * 72)

    report2, err = load_json(args.report2)
    if report2 is None:
        add_check("VP-000", "第 2 轮报告可读", "FAIL", err)
    elif report2.get("tool") != EXECUTOR_TOOL:
        add_check("VP-000", "第 2 轮报告可读", "FAIL",
                  "tool=%r 非 %s 产物，验收对象错链" % (report2.get("tool"), EXECUTOR_TOOL))
    else:
        add_check("VP-000", "第 2 轮报告可读", "PASS",
                  "%s | report_id=%s v%s | claim=%s | verdict=%s | %s → %s" % (
                      args.report2, report2.get("report_id"), report2.get("report_version"),
                      report2.get("claim_state"), report2.get("verdict"),
                      report2.get("started_at"), report2.get("finished_at")))

    perf_results = {}
    rerun_status = "NOT_RUN"
    if report2 is not None and report2.get("tool") == EXECUTOR_TOOL:
        perf_results = check_perf_15(report2)

        # 复跑一致性
        if args.report1:
            report1, err1 = load_json(args.report1)
            rerun_status = check_rerun(report1, report2, err1 or args.report1)
        else:
            report1, src = discover_report1(Path(args.report2).resolve(), report2)
            rerun_status = check_rerun(report1, report2, src)

        check_a_table_consistency(report2, perf_results, rerun_status)
        check_ui(args.ui_capture, report2)
        check_issues(args.issues)
        check_advisories(report2, args.report2, args.rss_probe)

    # 汇总
    print()
    print("-" * 72)
    gate_checks = [c for c in CHECKS if c["gate"]]
    fails = [c for c in gate_checks if c["status"] == "FAIL"]
    not_runs = [c for c in gate_checks if c["status"] == "NOT_RUN"]
    passes = [c for c in gate_checks if c["status"] == "PASS"]
    for c in CHECKS:
        mark = {"PASS": "[PASS   ]", "FAIL": "[FAIL   ]", "NOT_RUN": "[NOT_RUN]"}[c["status"]]
        gate = "" if c["gate"] else "（advisory）"
        print("%s %s %s" % (mark, c["id"], c["name"]))
        if c["detail"]:
            print("           └ %s" % c["detail"])
    print("-" * 72)
    print("门禁检查：PASS=%d  FAIL=%d  NOT_RUN=%d（另有 advisory %d 项）" % (
        len(passes), len(fails), len(not_runs),
        len(CHECKS) - len(gate_checks)))
    if fails:
        overall = "FAIL"
    elif not_runs:
        overall = "NOT_RUN"
    else:
        overall = "PASS"
    print("独立验收总判定：%s" % overall)
    if overall == "FAIL":
        print("处置：按 run4 §9.2 停止规则——修复受影响项后重跑；复跑前把第 1 轮报告归档。")
        code = 1
    elif overall == "NOT_RUN":
        print("处置：补齐 NOT_RUN 证据（未测项不折算 PASS；approximated 不冒充真实 DPI）。")
        code = 2
    else:
        print("处置：本脚本覆盖的验收面全部通过；attested 仍须 A-20/A-21/A-19/A-25 治理项与 A-28 双签（不在本脚本范围）。")
        code = 0
    print("=" * 72)
    return code


if __name__ == "__main__":
    sys.exit(main())
