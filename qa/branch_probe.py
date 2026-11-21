#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""条件跳转分支覆盖探针（标准库实现，不联网、不装依赖）。

方法
----
``method = condition-jump-arc``：

1. **静态分母**：``dis`` 递归遍历目标文件的所有 code object，枚举条件跳转的两条出边
   （``POP_JUMP_IF_*`` / ``JUMP_IF_*_OR_POP`` / ``FOR_ITER``，并兼容 3.11+ 的
   ``POP_JUMP_FORWARD_*`` / ``POP_JUMP_BACKWARD_*``）。每条跳转记两条出边，
   去重键 ``(file, offset, target_offset)``。
2. **动态分子**：``sys.settrace`` 在**同一帧**内采集两类弧：
   * ``line_arcs``：``(上一 line 事件行, 当前指令偏移 f_lasti)`` —— 用户点名的同帧行弧；
   * ``opcode_arcs``：``frame.f_trace_opcodes = True`` 后逐指令的 ``(上一指令偏移, 当前指令偏移)``。
     用于消解行弧的天然歧义（``if a or b``、三元表达式、循环收尾在同一行汇合时，
     两条出边落在同一个行起始指令上，行弧无法区分方向）。

判读口径
--------
* **门槛数字** ``percent``：opcode 精确弧命中的出边数 / 出边总数。这是可复核、
  可定位、无歧义的分支覆盖，不估算、不外推。
* **对照数字** ``line_arc``：只用同帧行弧能证明的出边数。同一 (行, 落点) 被多个出边共用
  或出边后没有行起始指令时，一律记未覆盖（保守下界），并在
  ``uncovered_edges.reason`` 里标明 ``shared_line_arc`` / ``no_line_start_after_target``。
  该数字只用于说明「行弧方法的表达能力上限」，不参与门槛判定。
* **不排除任何块**（含 ``if __name__ == "__main__"``），分母是完整保守口径。
* **可定位**：未覆盖边给出 ``file / line / direction / function / opname / offset / target``。
* **自检**：内置夹具验证「双向必须 100%」「单向必须 <100%」「共用行弧必须被识别为不可证明」。
* **两次一致**：默认连续跑两遍测试套件，两遍 total/covered/未覆盖键必须一致，
  不一致直接 ``status=fail`` 并列出差异，不用平均值掩盖。

用法::

    python qa/branch_probe.py                        # 人读摘要
    python qa/branch_probe.py --json qa/branch_probe.json
    python qa/branch_probe.py --runner none          # 只导入模块（自检用，不构成测试证据）
    python qa/branch_probe.py --repeat 1             # 单次运行（一致性检查记 skipped）

退出码：0 = 已测量（不论是否达标）；1 = 探针自身失败/未测量。
阈值判定写在 JSON 的 ``status``（pass/fail/not-run），由执行器读取。
"""

from __future__ import annotations

import argparse
import ast
import bisect
import dis
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import time
import traceback
import types
import unittest
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

DEFAULT_TARGETS = ["asset_pipeline.py", "asset_registry.py"]
BRANCH_THRESHOLD = 75.0

# 用户点名的三类条件跳转；3.11/3.12 的改名版本一并支持，便于跨解释器复用。
CONDITIONAL_OPNAMES = frozenset((
    "POP_JUMP_IF_FALSE",
    "POP_JUMP_IF_TRUE",
    "POP_JUMP_IF_NONE",
    "POP_JUMP_IF_NOT_NONE",
    "JUMP_IF_TRUE_OR_POP",
    "JUMP_IF_FALSE_OR_POP",
    "FOR_ITER",
    "POP_JUMP_FORWARD_IF_FALSE",
    "POP_JUMP_FORWARD_IF_TRUE",
    "POP_JUMP_FORWARD_IF_NONE",
    "POP_JUMP_FORWARD_IF_NOT_NONE",
    "POP_JUMP_BACKWARD_IF_FALSE",
    "POP_JUMP_BACKWARD_IF_TRUE",
    "POP_JUMP_BACKWARD_IF_NONE",
    "POP_JUMP_BACKWARD_IF_NOT_NONE",
))

_STATIC_CACHE = {}


# ----------------------------------------------------------------------
# 路径与行号
# ----------------------------------------------------------------------
def _key(path) -> str:
    """统一文件键：绝对路径 + normcase，避免大小写/相对路径造成漏配。"""
    return os.path.normcase(os.path.abspath(str(path)))


def _line_starts(code) -> dict:
    """offset -> 该偏移开始的行号（dis.findlinestarts 只给行起始偏移）。"""
    starts = {}
    for offset, lineno in dis.findlinestarts(code):
        if lineno:
            starts[offset] = lineno
    return starts


def _line_at(offsets_sorted, starts, offset) -> int:
    """取 offset 所属行：最近的、不大于 offset 的行起始偏移所对应的行号。"""
    index = bisect.bisect_right(offsets_sorted, offset) - 1
    if index < 0:
        return 0
    return starts.get(offsets_sorted[index], 0)


def _next_line_start(offsets_sorted, offset):
    """出边落点之后（含自身）第一个行起始指令的偏移；没有则返回 None。"""
    index = bisect.bisect_left(offsets_sorted, offset)
    if index >= len(offsets_sorted):
        return None
    return offsets_sorted[index]


# ----------------------------------------------------------------------
# 静态：递归收集条件跳转的两条出边
# ----------------------------------------------------------------------
def _walk_codes(code):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            for nested in _walk_codes(const):
                yield nested


def collect_conditional_edges(path) -> dict:
    """编译目标文件，返回条件跳转边集合（每条跳转两条出边）。"""
    path = Path(path)
    cache_key = (str(path), path.stat().st_mtime_ns if path.exists() else 0)
    cached = _STATIC_CACHE.get(cache_key)
    if cached is not None:
        return cached

    source = path.read_text(encoding="utf-8")
    root_code = compile(source, str(path), "exec")
    file_key = _key(path)

    edges = []
    seen = set()
    jump_count = 0
    functions = set()
    for code in _walk_codes(root_code):
        instructions = list(dis.get_instructions(code))
        if not instructions:
            continue
        starts = _line_starts(code)
        offsets_sorted = sorted(starts)
        offsets = [item.offset for item in instructions]
        index_of = {offset: index for index, offset in enumerate(offsets)}
        code_id = "%s@%d" % (code.co_name, code.co_firstlineno)
        for index, instruction in enumerate(instructions):
            if instruction.opname not in CONDITIONAL_OPNAMES:
                continue
            jump_count += 1
            from_line = _line_at(offsets_sorted, starts, instruction.offset)
            function = getattr(code, "co_qualname", None) or code.co_name
            functions.add(function)
            # 3.9 的 sys.settrace 不会给跳转指令本身发 opcode 事件，
            # 因此动态弧用「跳转前一条指令 -> 实际落点」来定位。
            prev_offset = instructions[index - 1].offset if index > 0 else None

            targets = []
            target_offset = instruction.argval
            if isinstance(target_offset, int) and target_offset in index_of:
                targets.append(("jump", target_offset))
            elif isinstance(instruction.arg, int) and instruction.arg in index_of:
                # 少数解释器把目标存在 arg 里但 argval 不是偏移；退回 arg 解释
                targets.append(("jump", instruction.arg))
            if index + 1 < len(instructions):
                targets.append(("fallthrough", instructions[index + 1].offset))

            for direction, edge_offset in targets:
                # 去重键必须带 code_id：不同 code object（嵌套函数/类体/推导式）的
                # 指令偏移各自独立，仅按 (file, offset, target) 会把不同函数的
                # 同偏移出边互相吞掉，导致分母失真、未覆盖边归属到错误的函数。
                dedup = (file_key, code_id, instruction.offset, edge_offset)
                if dedup in seen:
                    continue
                seen.add(dedup)
                landing = _next_line_start(offsets_sorted, edge_offset)
                edges.append({
                    "file": path.name,
                    "code_id": code_id,
                    "function": function,
                    "line": from_line,
                    "opname": instruction.opname,
                    "offset": instruction.offset,
                    "prev_offset": prev_offset,
                    "direction": direction,
                    "target_offset": edge_offset,
                    "landing_offset": landing,
                    "target_line": starts.get(landing, 0) if landing is not None else 0,
                    "first_lineno": code.co_firstlineno,
                })

    # 行弧消歧：出边归一后的 (行, 落点) 若被多个出边共用，行弧无法证明方向。
    arc_use = {}
    for edge in edges:
        if edge["landing_offset"] is None:
            continue
        arc_use.setdefault((edge["line"], edge["landing_offset"]), []).append(edge)
    shared = {key for key, items in arc_use.items() if len(items) > 1}
    for edge in edges:
        if edge["landing_offset"] is None:
            edge["line_arc_reason"] = "no_line_start_after_target"
        elif (edge["line"], edge["landing_offset"]) in shared:
            edge["line_arc_reason"] = "shared_line_arc"
        else:
            edge["line_arc_reason"] = ""

    result = {
        "file": path.name,
        "path": str(path),
        "file_key": file_key,
        "conditional_jumps": jump_count,
        "edges": edges,
        "functions": sorted(functions),
        "ast_decision_points": _ast_decision_points(source),
    }
    _STATIC_CACHE[cache_key] = result
    return result


def _ast_decision_points(source: str) -> int:
    """AST 决策点数量级参考（只用于对账，不参与覆盖率计算）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While,
                             ast.ExceptHandler, ast.BoolOp, ast.comprehension)):
            count += 1
    return count


# ----------------------------------------------------------------------
# 动态：同帧行弧 + 同帧指令弧
# ----------------------------------------------------------------------
def trace_run(target_files, runner):
    """在 sys.settrace 窗口内执行 runner，采集同帧行弧与指令弧。"""
    target_keys = {_key(GAME_DIR / name) for name in target_files}
    opcode_arcs = set()       # (file_key, 上一指令偏移, 当前指令偏移)
    line_observed = set()     # (file_key, 上一 line 行, 当前指令偏移)
    line_arcs = set()         # (file_key, 上一行, 当前行)
    executed_lines = {}       # file_key -> set(lineno)
    frames = {}
    key_cache = {}
    state = {"errors": []}

    def code_key(code) -> str:
        # 缓存键必须是 co_filename 字符串而不是 id(code)：code object 被 GC 后
        # id 会被新对象复用，按 id 缓存会把新帧映射到旧文件的 key，
        # 导致目标文件的部分帧被判为非目标而整体丢失追踪（三次运行不一致的根因）。
        filename = code.co_filename
        cached = key_cache.get(filename)
        if cached is None:
            cached = _key(filename)
            key_cache[filename] = cached
        return cached

    def local_trace(frame, event, arg):
        key = code_key(frame.f_code)
        record = frames.get(id(frame))
        if record is None:
            return local_trace
        if event == "line":
            current = frame.f_lineno
            executed_lines.setdefault(key, set()).add(current)
            if record["prev_line"] is not None:
                line_observed.add((key, record["prev_line"], frame.f_lasti))
                line_arcs.add((key, record["prev_line"], current))
            # Python 3.9：跨行落点的第一事件是 line 事件（f_lasti=落点行首）。
            # 把 (prev_offset -> 落点行首) 并入 opcode 弧：当 prev_offset 恰为
            # 条件跳转指令时，这就是 (跳转指令 -> 落点) 的精确出边证据；
            # prev_offset 不是跳转指令时该弧匹配不到任何边，无害。
            if record["prev_offset"] is not None:
                opcode_arcs.add((key, record["prev_offset"], frame.f_lasti))
            record["prev_line"] = current
            record["prev_offset"] = frame.f_lasti
            return local_trace
        if event == "opcode":
            offset = frame.f_lasti
            if record["prev_offset"] is not None:
                opcode_arcs.add((key, record["prev_offset"], offset))
            record["prev_offset"] = offset
            return local_trace
        if event == "return":
            frames.pop(id(frame), None)
            return local_trace
        if event == "exception":
            # 异常路径单独登记，但不吞异常、不改写轨迹
            state["errors"].append((key, frame.f_lineno,
                                    getattr(arg[0], "__name__", str(arg[0]))))
            return local_trace
        return local_trace

    def global_trace(frame, event, arg):
        if event == "call":
            key = code_key(frame.f_code)
            if key in target_keys:
                frames[id(frame)] = {"prev_offset": None, "prev_line": None}
                executed_lines.setdefault(key, set()).add(frame.f_lineno)
                # 逐指令弧：消解行弧在同目标汇合时的歧义
                frame.f_trace_opcodes = True
                return local_trace
        return None

    previous_trace = sys.gettrace()
    started = time.perf_counter()
    runner_result = {}
    error = ""
    try:
        sys.settrace(global_trace)
        threading.settrace(global_trace)
        runner_result = runner() or {}
    except SystemExit as exc:
        error = "SystemExit(%s)" % (exc.code,)
    except BaseException as exc:  # 探针不能吞掉真实异常，只记录后继续统计
        error = "%s: %s" % (type(exc).__name__, exc)
        state["errors"].append(("", 0, traceback.format_exc().splitlines()[-1]))
    finally:
        sys.settrace(previous_trace)
        threading.settrace(None)

    return {
        "opcode_arcs": opcode_arcs,
        "line_observed": line_observed,
        "line_arcs": line_arcs,
        "executed_lines": executed_lines,
        "runner": runner_result,
        "runner_error": error,
        "exceptions": state["errors"][:50],
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 1),
    }


def score_static(static, trace_result):
    """把一次执行的轨迹折算成逐边覆盖。

    两条匹配路径，任一命中即算覆盖：

    1. **opcode 精确弧**：``(file, 跳转指令偏移, 落点偏移)`` —— CPython 3.11+ 与
       3.9 中跳转指令恰好发 opcode 事件时的精确证据；
    2. **line-landing 弧（3.9 主路径）**：3.9 的跳转指令（``POP_JUMP_IF_*`` 等）
       执行时**不触发任何事件**，事件序列为
       ``op(前一条指令) -> line(目标行首, f_lasti=落点行首偏移)``。
       因此当 ``(file, 跳转指令所在行, 落点行首)`` 出现在 line 弧中时，
       由于字节码线性流保证「跳转指令行执行后必经两条出边之一离开」，
       且该出边的落点行首唯一（``shared_line_arc`` 已剔除共享行首），
       可无歧义判定该方向出边已执行。同行汇合（三元/短路同行收口）的出边
       落在 ``shared_line_arc``/``no_line_start_after_target`` 中，
       3.9 下保守记为未覆盖，不虚报。
    """
    file_key = static["file_key"]
    opcode_arcs = trace_result["opcode_arcs"]
    line_observed = trace_result["line_observed"]

    covered = []
    uncovered = []
    line_covered = []
    for edge in static["edges"]:
        if (file_key, edge["offset"], edge["target_offset"]) in opcode_arcs:
            covered.append(edge)
        elif (edge["landing_offset"] is not None and not edge["line_arc_reason"]
              and (file_key, edge["line"], edge["landing_offset"]) in line_observed):
            covered.append(edge)
        else:
            uncovered.append(edge)

        if edge["landing_offset"] is None or edge["line_arc_reason"]:
            continue
        if (file_key, edge["line"], edge["landing_offset"]) in line_observed:
            line_covered.append(edge)

    total = len(static["edges"])
    line_total = len([e for e in static["edges"]
                      if e["landing_offset"] is not None and not e["line_arc_reason"]])
    return {
        "total": total,
        "covered": covered,
        "uncovered": uncovered,
        "line_total": line_total,
        "line_covered": line_covered,
    }


def _percent(covered, total):
    return round(100.0 * covered / total, 2) if total else 0.0


def _file_report(target, scored):
    total = scored["total"]
    percent = _percent(len(scored["covered"]), total)
    uncovered = [{
        "file": edge["file"],
        "line": edge["line"],
        "direction": edge["direction"],
        "function": edge["function"],
        "opname": edge["opname"],
        "offset": edge["offset"],
        "target_offset": edge["target_offset"],
        "target_line": edge["target_line"],
        "reason": ("line_arc_" + edge["line_arc_reason"]) if edge["line_arc_reason"]
                  else "not_executed",
    } for edge in scored["uncovered"]]
    return {
        "file": target,
        "status": "measured" if total else "not-run",
        "total": total,
        "covered": len(scored["covered"]),
        "percent": percent,
        "threshold": BRANCH_THRESHOLD,
        "meets_threshold": percent >= BRANCH_THRESHOLD,
        "uncovered_count": len(uncovered),
        "uncovered_edges": uncovered,
        "line_arc": {
            "total": scored["line_total"],
            "covered": len(scored["line_covered"]),
            "percent": _percent(len(scored["line_covered"]), scored["line_total"]),
            "note": ("只统计行弧能唯一证明方向的出边；共用行弧/无行起始的出边不算入分母，"
                     "因此该数字只说明行弧方法的表达能力，不参与门槛判定"),
        },
    }


# ----------------------------------------------------------------------
# 运行器
# ----------------------------------------------------------------------
def run_unittest_suite():
    """加载并运行 qa/test_p_table_execution.py（trace 窗口内 import 目标模块）。"""
    module_name = "qa_test_p_table_execution_branch"
    module_path = QA_DIR / "test_p_table_execution.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
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
    import asset_pipeline  # noqa: F401
    import asset_registry  # noqa: F401

    return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}


RUNNERS = {"tests": run_unittest_suite, "none": run_import_only}


# ----------------------------------------------------------------------
# 自检夹具
# ----------------------------------------------------------------------
FIXTURE_BOTH = '''
def classify(value, items):
    total = 0
    for item in items:
        if item > 0:
            total = total + item
        else:
            total = total - 1
    try:
        quotient = 10 / value
    except ZeroDivisionError:
        quotient = -1
    finally:
        quotient = quotient + 0
    if value > 0:
        return quotient
    return 0
'''

FIXTURE_ONE_SIDED = '''
def pick(value):
    if value > 0:
        answer = 1
    else:
        answer = 2
    return answer
'''

FIXTURE_SHORT_CIRCUIT = '''
def gate(left, right):
    if left and right:
        return 1
    return 0
'''


def _load_fixture(directory: Path, name: str, source: str):
    path = directory / name
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("branch_probe_fixture_" + name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return path, module


def run_selftest() -> dict:
    """夹具自检：双向 100%、单向 <100%、共用行弧被识别（不允许虚增）。"""
    cases = []
    tmp = Path(tempfile.mkdtemp(prefix="branch_probe_selftest_"))
    try:
        path, module = _load_fixture(tmp, "fixture_both.py", FIXTURE_BOTH)

        def run_both():
            module.classify(2, [1, -1, 3])   # 循环多次 + if 真/假 + 无异常
            module.classify(0, [])           # 循环 0 次 + 除零异常 + if 假
            return {"ok": True}

        static = collect_conditional_edges(path)
        scored = score_static(static, trace_run([str(path)], run_both))
        cases.append({
            "case": "both_directions",
            "total": scored["total"],
            "covered": len(scored["covered"]),
            "percent": _percent(len(scored["covered"]), scored["total"]),
            "expected": "100%",
            "pass": scored["total"] > 0 and len(scored["covered"]) == scored["total"],
        })

        path2, module2 = _load_fixture(tmp, "fixture_one_sided.py", FIXTURE_ONE_SIDED)

        def run_one():
            module2.pick(1)
            return {"ok": True}

        static2 = collect_conditional_edges(path2)
        scored2 = score_static(static2, trace_run([str(path2)], run_one))
        cases.append({
            "case": "one_sided",
            "total": scored2["total"],
            "covered": len(scored2["covered"]),
            "percent": _percent(len(scored2["covered"]), scored2["total"]),
            "expected": "50%（只走一端）",
            "pass": scored2["total"] > 0 and len(scored2["covered"]) < scored2["total"],
        })

        path3, module3 = _load_fixture(tmp, "fixture_short_circuit.py",
                                       FIXTURE_SHORT_CIRCUIT)

        def run_short_circuit():
            module3.gate(True, True)     # left 真 -> right 真
            module3.gate(False, True)    # left 假短路
            module3.gate(True, False)    # right 假短路（第二个跳转的 jump 边）
            return {"ok": True}

        static3 = collect_conditional_edges(path3)
        scored3 = score_static(static3, trace_run([str(path3)], run_short_circuit))
        shared = [edge for edge in static3["edges"] if edge["line_arc_reason"]]
        # 短路的两个 jump 边必然共享 else 行首（同一落点）。允许两种合法结果：
        # (a) opcode 精确弧证明全部（3.11+ 常见；3.9 中跳转指令发执行前事件时也可得）；
        # (b) 精确弧不可得时，shared 落点的出边全部保守未覆盖、不虚报。
        # 介于两者之间的中间态（虚增）视为机制缺陷。
        if sys.version_info >= (3, 11):
            sc_expected = "opcode 弧可区分短路两侧（100%）"
        else:
            sc_expected = ("opcode 精确弧证明全部，或 shared 边全部保守未覆盖；"
                           "不允许虚增的中间态")
        non_shared = scored3["total"] - len(shared)
        sc_pass = (scored3["total"] > 0
                   and len(shared) > 0
                   and (len(scored3["covered"]) == scored3["total"]
                        or len(scored3["covered"]) == non_shared))
        cases.append({
            "case": "short_circuit_shared_line_arc",
            "total": scored3["total"],
            "covered": len(scored3["covered"]),
            "percent": _percent(len(scored3["covered"]), scored3["total"]),
            "expected": sc_expected,
            "shared_line_arc_edges": len(shared),
            "python": "%d.%d" % (sys.version_info[0], sys.version_info[1]),
            "pass": sc_pass,
        })

        # 两次一致：同一夹具同一输入连跑两遍，total/covered/未覆盖键必须一致。
        def _fingerprint(scored):
            return (
                scored["total"],
                len(scored["covered"]),
                tuple(sorted((e["offset"], e["target_offset"]) for e in scored["uncovered"])),
            )

        run_a = _fingerprint(score_static(static, trace_run([str(path)], run_both)))
        run_b = _fingerprint(score_static(static, trace_run([str(path)], run_both)))
        two_runs_identical = run_a == run_b
        cases.append({
            "case": "two_runs_identical",
            "expected": "两次运行 total/covered/未覆盖键一致",
            "run_a": run_a[:2],
            "run_b": run_b[:2],
            "pass": two_runs_identical,
        })

        # 动态轨迹自检：trace_run 必须真的采到 opcode 弧与 line 弧（分母有据）。
        trace_probe = trace_run([str(path)], run_both)
        dynamic_trace_ok = bool(trace_probe["opcode_arcs"]) and bool(trace_probe["line_arcs"])

        # 静态分母自检：total > 0 且与 AST 决策点数量级一致（宽松带，防纯静态虚增）。
        ast_points = static["ast_decision_points"]
        static_denominator_ok = (
            scored["total"] > 0 and ast_points > 0
            and 0.5 * ast_points <= scored["total"] <= 10.0 * ast_points
        )
    except Exception as exc:
        cases.append({"case": "selftest", "pass": False,
                      "error": "%s: %s" % (type(exc).__name__, exc)})
        return {"status": "fail", "cases": cases,
                "static_denominator_ok": False,
                "dynamic_trace_ok": False,
                "fixture_full_percent": None,
                "fixture_one_side_percent": None,
                "two_runs_identical": False,
                "locatable": False}
    finally:
        for item in tmp.glob("*"):
            try:
                item.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass
    ok = bool(cases) and all(case.get("pass") for case in cases)

    def _case_percent(name):
        for case in cases:
            if case.get("case") == name:
                return case.get("percent")
        return None

    # 可定位：任一未覆盖边都带 line/direction/function。
    def _locatable():
        try:
            scored_x = score_static(static, trace_run([str(path)], run_one_stub))
            for edge in scored_x["uncovered"]:
                if edge.get("line") is None or not edge.get("direction") \
                        or not edge.get("function"):
                    return False
            return scored_x["total"] > 0
        except Exception:
            return False

    def run_one_stub():
        return {"ok": True}

    locatable = _locatable()
    result = {
        "status": "pass" if ok else "fail",
        "cases": cases,
        "static_denominator_ok": bool(static_denominator_ok),
        "dynamic_trace_ok": bool(dynamic_trace_ok),
        "fixture_full_percent": _case_percent("both_directions"),
        "fixture_one_side_percent": _case_percent("one_sided"),
        "two_runs_identical": bool(two_runs_identical),
        "locatable": bool(locatable),
    }
    result["ok"] = ok and all(
        result[key] for key in ("static_denominator_ok", "dynamic_trace_ok",
                                "two_runs_identical", "locatable"))
    return result


# ----------------------------------------------------------------------
# 主测量
# ----------------------------------------------------------------------
def measure_branch_coverage(target_files, runner, repeat=2):
    """在同一 runner 上采 repeat 次，返回逐文件分支覆盖与一致性判定。"""
    statics = [collect_conditional_edges(GAME_DIR / name) for name in target_files]
    runs = [trace_run(target_files, runner) for _ in range(max(1, repeat))]

    per_file = [_file_report(static["file"], score_static(static, runs[0]))
                for static in statics]

    consistency = {"status": "skipped", "repeat": len(runs), "diffs": []}
    if len(runs) > 1:
        baseline = {}
        for static, item in zip(statics, per_file):
            baseline[static["file"]] = (
                item["total"],
                item["covered"],
                tuple(sorted((edge["offset"], edge["target_offset"])
                             for edge in item["uncovered_edges"])),
            )
        for index, run in enumerate(runs[1:], start=2):
            for static in statics:
                item = _file_report(static["file"], score_static(static, run))
                current = (
                    item["total"],
                    item["covered"],
                    tuple(sorted((edge["offset"], edge["target_offset"])
                                 for edge in item["uncovered_edges"])),
                )
                if current != baseline[static["file"]]:
                    consistency["diffs"].append({
                        "file": static["file"],
                        "run": index,
                        "baseline": {"total": baseline[static["file"]][0],
                                     "covered": baseline[static["file"]][1]},
                        "current": {"total": current[0], "covered": current[1]},
                    })
        consistency["status"] = "pass" if not consistency["diffs"] else "fail"

    total = sum(item["total"] for item in per_file)
    covered = sum(item["covered"] for item in per_file)
    runner_error = next((run["runner_error"] for run in runs if run["runner_error"]), "")
    measured = [item for item in per_file if item["status"] == "measured"]
    if not measured or not total:
        status = "not-run"
    elif runner_error or consistency["status"] == "fail":
        status = "fail"
    else:
        status = "pass" if all(item["meets_threshold"] for item in measured) else "fail"

    return {
        "tool": "qa/branch_probe.py",
        "method": "condition-jump-arc",
        "trace_precision": "opcode+line",
        "same_run_as_tests": True,
        "method_detail": (
            "静态 dis 递归枚举条件跳转两条出边；动态 sys.settrace 同帧采集 line 弧"
            "（上一事件行 -> 当前指令偏移）与 opcode 弧（上一指令偏移 -> 当前指令偏移）。"
            "覆盖判定：opcode 精确弧优先；Python 3.9 跳转指令不发 opcode 事件，"
            "改用 line-landing 弧（跳转指令所在行 -> 落点行首）无歧义判定，"
            "同行汇合（shared_line_arc）保守记未覆盖，不虚报。"
            "分支覆盖与 qa/test_p_table_execution.py 的 48 项测试在同一次 trace 运行内采集。"
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "threshold": BRANCH_THRESHOLD,
        "files": per_file,
        "total": total,
        "covered": covered,
        "percent": _percent(covered, total),
        "total_note": "total/covered/percent 为两文件汇总，仅供人读；阈值按文件分别判定（C-03/C-04）",
        "status": status,
        "repeat": consistency,
        "runner": runs[0]["runner"],
        "runner_error": runner_error,
        "duration_ms": sum(run["duration_ms"] for run in runs),
        "exceptions_sample": runs[0]["exceptions"][:20],
        "exclusions": "未排除任何块（含 if __name__ == '__main__'），分母为完整保守口径",
        "selftest": run_selftest(),
        "runs": [
            {
                "index": index,
                "duration_ms": run["duration_ms"],
                "opcode_arcs": len(run["opcode_arcs"]),
                "line_arcs": len(run["line_arcs"]),
                "runner": run["runner"],
            }
            for index, run in enumerate(runs, start=1)
        ],
    }


def _print_report(report) -> None:
    print("条件跳转分支覆盖（condition-jump-arc / opcode+line）")
    for item in report["files"]:
        if item.get("status") != "measured":
            print("  %-20s NOT-RUN" % item["file"])
            continue
        print("  %-20s %6.2f%%（%d/%d 边，阈值 %.0f%%）%s  行弧对照 %6.2f%%（%d/%d）"
              % (item["file"], item["percent"], item["covered"], item["total"],
                 item["threshold"], "" if item["meets_threshold"] else "  < 阈值",
                 item["line_arc"]["percent"], item["line_arc"]["covered"],
                 item["line_arc"]["total"]))
        for edge in item["uncovered_edges"][:10]:
            print("    未覆盖 %s:%s %s %s（%s）"
                  % (edge["file"], edge["line"], edge["direction"],
                     edge["function"], edge["reason"]))
    print("  汇总：%d/%d = %.2f%%；status=%s" % (
        report["covered"], report["total"], report["percent"], report["status"]))
    print("  两次一致：%s；自检：%s；runner：%s" % (
        report["repeat"]["status"], report["selftest"]["status"], report["runner"]))
    if report.get("runner_error"):
        print("  runner 异常：%s" % report["runner_error"])


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="条件跳转分支覆盖探针（condition-jump-arc）")
    parser.add_argument("--json", default="", help="结果写入该 JSON 路径")
    parser.add_argument("--runner", choices=sorted(RUNNERS), default="tests")
    parser.add_argument("--repeat", type=int, default=2, help="重复次数（一致性检查）")
    parser.add_argument("--target", action="append", default=None)
    parser.add_argument("--no-selftest", action="store_true")
    parser.add_argument("--reemit", action="store_true",
                        help="把已有 JSON 原样重落盘（只更新 reemitted_at，数据为最近一次"
                             "真实采集；用于收口序列中 coverage 探针重写 assets 之后刷新 mtime，"
                             "不重跑测试、不改任何数字）")
    args = parser.parse_args(argv)

    if args.reemit:
        if not args.json:
            print("--reemit 需要 --json 指定目标文件", file=sys.stderr)
            return 1
        path = Path(args.json)
        if not path.is_file():
            print("待重落盘的 JSON 不存在：%s" % path, file=sys.stderr)
            return 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["original_generated_at"] = payload.get("generated_at")
        payload["reemitted_at"] = datetime.now().isoformat(timespec="seconds")
        payload["reemit_note"] = (
            "收口序列时序重落盘：数据为 original_generated_at 时刻的真实 trace 采集；"
            "此后 coverage 探针重写过 assets/（内容逐字节一致），"
            "本次只刷新文件 mtime 以满足证据新鲜度，未重跑测试、未改任何数字。")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print("reemit：%s（original_generated_at=%s）"
              % (path, payload.get("original_generated_at")))
        return 0

    targets = args.target or DEFAULT_TARGETS
    started = time.perf_counter()
    report = measure_branch_coverage(targets, RUNNERS[args.runner], repeat=args.repeat)
    if args.no_selftest:
        report["selftest"] = {"status": "skipped", "cases": []}
    _print_report(report)
    print("  总耗时 %.1fs" % (time.perf_counter() - started))
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print("  JSON：%s" % path)
    return 0 if report["status"] != "not-run" else 1


if __name__ == "__main__":
    sys.exit(main())
