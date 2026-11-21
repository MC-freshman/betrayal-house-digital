#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""行覆盖率探针：标准库 ``trace`` + ``dis``，不依赖 coverage.py，不联网。

判定口径
--------
* **行覆盖**：分母 = 目标文件里所有可执行行（``dis.findlinestarts`` 递归收集，
  含 ``if __name__ == "__main__"`` 块，未做任何排除，故数值是偏保守的下界）；
  分子 = ``trace(count=1, trace=0)`` 观测到执行次数 > 0 的行。
* **分支覆盖**：标准库 trace 没有分支计数能力，``coverage`` 未安装（本轮不联网装
  依赖），因此 branch 一律返回 ``status=not-run`` 并写明原因，不估算、不编造数字。

用法::

    python qa/coverage_probe.py                     # 人读摘要
    python qa/coverage_probe.py --json qa/coverage_probe.json
    python qa/coverage_probe.py --runner tests      # 默认：跑 qa/test_p_table_execution.py
    python qa/coverage_probe.py --runner none       # 只导入模块，测 module-level 行

输出结论只有两种：``measured``（有实测行覆盖）与 ``not-run``（未执行）；不存在
“未执行却记为 PASS”的中间态。
"""

from __future__ import annotations

import argparse
import dis
import importlib.util
import io
import json
import sys
import trace
import types
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

DEFAULT_TARGETS = ["asset_pipeline.py", "asset_registry.py"]
LINE_THRESHOLD = 85.0
BRANCH_THRESHOLD = 75.0
BRANCH_REASON = (
    "coverage.py 未安装（本轮不联网装依赖）；标准库 trace 只统计行执行次数，"
    "无法给出分支总数/覆盖数，故 branch 记为 not-run，不估算、不编造数字。"
)


# ----------------------------------------------------------------------
# 可执行行
# ----------------------------------------------------------------------
def _collect_lines(code, acc):
    for _offset, lineno in dis.findlinestarts(code):
        if lineno:
            acc.add(lineno)
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            _collect_lines(const, acc)


def executable_lines(path) -> set:
    """编译目标文件并用 dis 收集所有可执行行号（含嵌套函数/类）。"""
    source = Path(path).read_text(encoding="utf-8")
    code = compile(source, str(path), "exec")
    acc = set()
    _collect_lines(code, acc)
    return acc


# ----------------------------------------------------------------------
# 测试运行器
# ----------------------------------------------------------------------
def run_unittest_suite():
    """加载 qa/test_p_table_execution.py 并运行（在 trace 窗口内 import 目标模块）。"""
    import unittest

    module_name = "qa_test_p_table_execution"
    module_path = QA_DIR / "test_p_table_execution.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    # 必须登记到 sys.modules：否则 unittest 找不到模块，setUpModule 不会执行
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return {
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "failure_ids": [str(test) for test, _trace in result.failures + result.errors],
    }


def run_import_only():
    """只导入目标模块，用于确认探针本身可用（不构成测试通过证据）。"""
    import asset_pipeline  # noqa: F401
    import asset_registry  # noqa: F401

    return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}


RUNNERS = {"tests": run_unittest_suite, "none": run_import_only}


# ----------------------------------------------------------------------
# 测量
# ----------------------------------------------------------------------
def measure_coverage(target_files, runner):
    """在 trace 窗口内执行 runner，返回逐文件行覆盖与 branch=not-run 说明。"""
    tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix, sys.exec_prefix])
    runner_result = {}
    error = ""
    try:
        runner_result = tracer.runfunc(runner) or {}
    except SystemExit as exc:  # 被测代码可能提前退出
        error = "SystemExit(%s)" % exc.code
    except Exception as exc:  # 探针不能吞掉真实异常，只记录后继续统计
        error = "%s: %s" % (type(exc).__name__, exc)

    counts = tracer.results().counts
    covered_by_file = {}
    for (filename, lineno), count in counts.items():
        if count <= 0:
            continue
        try:
            key = Path(filename).resolve()
        except OSError:
            continue
        covered_by_file.setdefault(key, set()).add(lineno)

    files = []
    for name in target_files:
        path = (GAME_DIR / name).resolve()
        if not path.is_file():
            files.append({
                "file": name,
                "status": "not-run",
                "reason": "目标文件不存在：%s" % path,
                "branch": {"status": "not-run", "reason": BRANCH_REASON},
            })
            continue
        try:
            total = executable_lines(path)
        except (OSError, SyntaxError) as exc:
            files.append({
                "file": name,
                "status": "not-run",
                "reason": "无法编译统计：%s: %s" % (type(exc).__name__, exc),
                "branch": {"status": "not-run", "reason": BRANCH_REASON},
            })
            continue
        covered = total & covered_by_file.get(path, set())
        missing = sorted(total - covered)
        percent = round(100.0 * len(covered) / len(total), 2) if total else 0.0
        files.append({
            "file": name,
            "status": "measured",
            "total_lines": len(total),
            "covered_lines": len(covered),
            "line_percent": percent,
            "threshold": LINE_THRESHOLD,
            "meets_threshold": percent >= LINE_THRESHOLD,
            "missing_lines_count": len(missing),
            "missing_sample": missing[:25],
            "branch": {
                "status": "not-run",
                "threshold": BRANCH_THRESHOLD,
                "reason": BRANCH_REASON,
            },
        })

    measured = [item for item in files if item.get("status") == "measured"]
    summary = {
        "targets": len(target_files),
        "measured": len(measured),
        "not_run": len(target_files) - len(measured),
        "line_percent": {
            item["file"]: item["line_percent"] for item in measured
        },
        "all_line_thresholds_met": bool(measured)
        and all(item["meets_threshold"] for item in measured)
        and len(measured) == len(target_files),
        "branch_status": "not-run",
        "branch_reason": BRANCH_REASON,
        "exclusions": "未排除任何块（含 if __name__ == '__main__'），因此行覆盖是保守下界",
    }
    return {
        "tool": "qa/coverage_probe.py",
        "method": "stdlib trace(count=1, trace=0) + dis.findlinestarts 可执行行集合",
        "runner": runner_result,
        "runner_error": error,
        "files": files,
        "summary": summary,
    }


# ----------------------------------------------------------------------
# 人读输出
# ----------------------------------------------------------------------
def _print_report(report: dict) -> None:
    print("覆盖率探针（标准库 trace + dis）")
    for item in report["files"]:
        if item.get("status") != "measured":
            print("  %-20s NOT-RUN  %s" % (item["file"], item.get("reason", "")))
            continue
        print("  %-20s %6.2f%%（%d/%d 行，阈值 %.0f%%）%s"
              % (item["file"], item["line_percent"], item["covered_lines"],
                 item["total_lines"], item["threshold"],
                 "" if item["meets_threshold"] else "  < 阈值"))
        if item["missing_sample"]:
            print("    未覆盖样例行：%s" % item["missing_sample"][:12])
    print("  分支覆盖：not-run（%s）" % report["summary"]["branch_reason"])
    if report.get("runner_error"):
        print("  runner 异常：%s" % report["runner_error"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="标准库行覆盖率探针（branch 显式 not-run）")
    parser.add_argument("--json", default="", help="把结果写入该 JSON 路径")
    parser.add_argument("--runner", choices=sorted(RUNNERS), default="tests",
                        help="tests=跑 qa/test_p_table_execution.py；none=只导入模块")
    parser.add_argument("--target", action="append", default=None,
                        help="目标文件（可重复），默认 asset_pipeline.py + asset_registry.py")
    args = parser.parse_args(argv)

    targets = args.target or DEFAULT_TARGETS
    report = measure_coverage(targets, RUNNERS[args.runner])
    _print_report(report)
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print("  JSON：%s" % path)
    # 覆盖率未达阈值不改变退出码：它是度量项，不是门禁（门禁由执行器判定）
    return 0 if not report["runner_error"] else 1


if __name__ == "__main__":
    sys.exit(main())
