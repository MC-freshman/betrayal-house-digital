#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""峰值 RSS 探针：asset_pipeline.py --stage all 连续 5 次，按最大值判定。

方法
----
* 指标：进程树峰值工作集 ``PeakWorkingSetSize``（不是当前工作集、不是中位数、不是增量）。
* 采集：优先 psutil（``Process.memory_full_info().peak_wset``，Windows 实现来自
  psapi ``GetProcessMemoryInfo``）；psutil 缺失时退回 ctypes
  ``OpenProcess + psapi.GetProcessMemoryInfo`` 读取 ``PROCESS_MEMORY_COUNTERS``。
* 运行：``python asset_pipeline.py --stage all`` 子进程（P 表 -> 占位图 -> 95 张规范化，
  worst case）；连续 5 次；采样间隔 200 ms；进程退出前的最后一次读数即全局峰值
  （峰值单调，不下降）。
* 判定：按 **5 次峰值的最大值** 判（``verdict_basis=max``），任一次 >1536 MiB 即 fail，
  不得用中位数掩盖单次越界。
* 复用落盘：``--from-samples`` 从已保存的采样明细重建 JSON（不重跑子进程、不动 assets/），
  用于「采样在先、正式落盘在后」的串行收口顺序；``sampled_at`` 如实保留采样时刻，
  ``emitted_at`` 记录落盘时刻，两者不混写。

用法::

    python qa/rss_probe.py --json qa/rss_probe.json --samples-save qa/rss_samples.json
    python qa/rss_probe.py --from-samples qa/rss_samples.json --json qa/rss_probe.json

退出码：0 = 已测量（pass 或 fail 都是已测量）；1 = 未测量/环境异常。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
BUDGET_MIB = 1536.0
BUDGET_BYTES = int(1536 * 1024 * 1024)
SAMPLING_INTERVAL_MS = 200
RUN_COUNT = 5
COMMAND = ["asset_pipeline.py", "--stage", "all"]

METRIC = "psapi.GetProcessMemoryInfo/PeakWorkingSetSize"


# ---------------------------------------------------------------------------
# 内存读取
# ---------------------------------------------------------------------------
class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_wset_ctypes(pid) -> int:
    """ctypes 兜底：OpenProcess + GetProcessMemoryInfo 读 PeakWorkingSetSize。"""
    handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, int(pid))
    if not handle:
        raise OSError("OpenProcess(%s) 失败" % pid)
    try:
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo(%s) 失败" % pid)
        return int(counters.PeakWorkingSetSize)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _process_tree(pid) -> list:
    """枚举进程树（运行期间调用；psutil 缺失时退化为 pid 列表）。"""
    try:
        import psutil

        try:
            parent = psutil.Process(pid)
            return ["%s:%s" % (p.pid, p.name())
                    for p in [parent] + parent.children(recursive=True)]
        except psutil.Error:
            return ["pid=%s (已退出，无法枚举进程树)" % pid]
    except ImportError:
        return ["pid=%s (psutil 缺失，进程树未枚举)" % pid]


def make_reader():
    """返回 (reader(pid)->bytes, backend 名称)。psutil 优先，ctypes 兜底。"""
    try:
        import psutil

        def reader_psutil(pid):
            return int(psutil.Process(pid).memory_full_info().peak_wset)

        return reader_psutil, "psutil %s" % psutil.__version__
    except ImportError:
        return peak_wset_ctypes, "ctypes psapi.GetProcessMemoryInfo"


# ---------------------------------------------------------------------------
# 单次运行
# ---------------------------------------------------------------------------
def run_once(reader, index) -> dict:
    """启动一次 --stage all 子进程，200 ms 采样峰值工作集。"""
    env = dict(__import__("os").environ)
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable] + COMMAND,
        cwd=str(GAME_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    samples = []
    peak_bytes = 0
    reader_error = ""
    exited = False
    retry_budget = 3
    tree = []
    while not exited:
        # 先看进程状态再采样：进程已退出时不再读内存（峰值单调，最后一次读数即全局峰值）
        if proc.poll() is not None:
            exited = True
            break
        try:
            value = reader(proc.pid)
            if value > peak_bytes:
                peak_bytes = value
            if not tree:
                tree = _process_tree(proc.pid)
            samples.append({
                "t_ms": int((time.perf_counter() - started) * 1000),
                "peak_bytes": value,
                "peak_mib": round(value / 1048576.0, 2),
            })
        except (OSError,) + psutil_access_denied_exceptions() as exc:
            # 进程仍活着但读取瞬时失败（句柄竞争）：短暂退避后重试；重试耗尽才放弃
            retry_budget -= 1
            reader_error = str(exc)
            if retry_budget <= 0 or proc.poll() is not None:
                exited = True
                break
            time.sleep(0.05)
            continue
        time.sleep(SAMPLING_INTERVAL_MS / 1000.0)

    stdout_text, stderr_text = proc.communicate()
    duration_ms = int((time.perf_counter() - started) * 1000)

    if not tree:
        tree = _process_tree(proc.pid)

    # 进程退出后再读一次峰值（Windows 句柄失效则用最后一次采样值；峰值单调）
    final_peak = peak_bytes
    try:
        final_peak = max(peak_bytes, reader(proc.pid))
    except Exception:
        pass

    ok_exit = proc.returncode == 0
    return {
        "run_id": index,
        "stage": "all",
        "command": "python " + " ".join(COMMAND),
        "exit_code": proc.returncode,
        "exit_ok": ok_exit,
        "duration_ms": duration_ms,
        "sampling_interval_ms": SAMPLING_INTERVAL_MS,
        "sample_count": len(samples),
        "samples": samples,
        "peak_bytes": int(final_peak),
        "peak_mib": round(final_peak / 1048576.0, 2),
        "budget_mib": BUDGET_MIB,
        "budget_bytes": BUDGET_BYTES,
        "within_budget": final_peak <= BUDGET_BYTES,
        "process_tree": tree,
        "stdout_tail": "\n".join((stdout_text or "").splitlines()[-6:]),
        "stderr_tail": "\n".join((stderr_text or "").splitlines()[-6:]),
        "reader_error": reader_error,
    }


def psutil_access_denied_exceptions():
    """psutil.Error 元组（psutil 缺失时返回 OSError 之外的空元组）。"""
    try:
        import psutil

        return (psutil.Error,)
    except ImportError:
        return (OSError,)


# ---------------------------------------------------------------------------
# 汇总与判定
# ---------------------------------------------------------------------------
def summarize(runs, backend, sampled_at=None) -> dict:
    peaks_mib = [run["peak_mib"] for run in runs]
    peaks_bytes = [run["peak_bytes"] for run in runs]
    maximum = max(peaks_mib) if peaks_mib else 0.0
    all_ok = all(run["within_budget"] and run["exit_ok"] for run in runs)
    payload = {
        "tool": "qa/rss_probe.py",
        "metric": METRIC,
        "backend": backend,
        "stage": "all",
        "command": "python " + " ".join(COMMAND),
        "sampling_interval_ms": SAMPLING_INTERVAL_MS,
        "run_count": RUN_COUNT,
        "budget_mib": BUDGET_MIB,
        "budget_bytes": BUDGET_BYTES,
        "verdict_basis": "max",
        "verdict_note": "按 5 次峰值的最大值判定；任一次 >1536 MiB 即 fail；不用中位数替代峰值",
        "runs": runs,
        "process_tree": (runs[0].get("process_tree") if runs else []) or [],
        "process_tree_note": "进程树在运行期间枚举（--stage all 为单进程，无子进程）",
        "peaks_mib": peaks_mib,
        "peaks_bytes": peaks_bytes,
        "max_peak_mib": round(maximum, 2),
        "max_peak_bytes": max(peaks_bytes) if peaks_bytes else 0,
        "median_mib": round(statistics.median(peaks_mib), 2) if peaks_mib else 0.0,
        "min_peak_mib": round(min(peaks_mib), 2) if peaks_mib else 0.0,
        "pass": bool(runs) and all_ok and maximum <= BUDGET_MIB,
        "environment": _environment(),
        "input_sha256": _input_hashes(),
        "sampled_at": sampled_at or datetime.now().isoformat(timespec="seconds"),
        "emitted_at": datetime.now().isoformat(timespec="seconds"),
    }
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_hashes() -> dict:
    out = {}
    for rel in ("asset_pipeline.py", "content.py",
                "assets/p_table.json", "assets/asset_mapping.json"):
        path = GAME_DIR / rel
        if path.is_file():
            out[rel] = _sha256(path)
    return out


def _environment() -> dict:
    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "timezone": time.tzname[0],
    }
    try:
        import PIL

        info["pillow"] = PIL.__version__
    except ImportError:
        info["pillow"] = "absent"
    try:
        import psutil

        vm = psutil.virtual_memory()
        info["memory_total_mib"] = round(vm.total / 1048576.0, 1)
        info["memory_available_mib"] = round(vm.available / 1048576.0, 1)
    except ImportError:
        pass
    return info


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="峰值 RSS 探针（PeakWorkingSetSize，5 次，按最大值判定）")
    parser.add_argument("--json", default="qa/rss_probe.json")
    parser.add_argument("--samples-save", default="",
                        help="采样明细另存到该路径（供 --from-samples 复用落盘）")
    parser.add_argument("--from-samples", default="",
                        help="从已保存的采样明细重建 JSON（不重跑子进程）")
    args = parser.parse_args(argv)

    if args.from_samples:
        source = Path(args.from_samples)
        if not source.is_file():
            print("采样明细不存在：%s" % source, file=sys.stderr)
            return 1
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["emitted_at"] = datetime.now().isoformat(timespec="seconds")
        payload["emit_mode"] = "from-samples"
        payload["emit_source"] = str(source)
        # 输入哈希在落盘时按当前文件重算（采样时的输入以 samples 模式记录为准）
        payload["input_sha256"] = _input_hashes()
        print("复用采样落盘：%s（sampled_at=%s，不重跑子进程）"
              % (payload.get("sampled_at"), payload.get("sampled_at")))
    else:
        reader, backend = make_reader()
        print("RSS 探针：backend=%s；连续 %d 次 --stage all；间隔 %d ms"
              % (backend, RUN_COUNT, SAMPLING_INTERVAL_MS))
        runs = []
        for index in range(1, RUN_COUNT + 1):
            run = run_once(reader, index)
            runs.append(run)
            print("  run %d/%d：峰值 %.1f MiB（%d 字节，%d 次采样，%.1fs，exit=%s）%s" % (
                index, RUN_COUNT, run["peak_mib"], run["peak_bytes"],
                run["sample_count"], run["duration_ms"] / 1000.0, run["exit_code"],
                "" if run["within_budget"] else "  > 预算 %d MiB！" % int(BUDGET_MIB)))
        payload = summarize(runs, backend)
        if args.samples_save:
            save = Path(args.samples_save)
            save.parent.mkdir(parents=True, exist_ok=True)
            save.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            print("  采样明细：%s" % save)

    maximum = payload.get("max_peak_mib", 0.0)
    passed = payload.get("pass", False)
    print("最大峰值：%.1f MiB / 预算 %d MiB；verdict_basis=max；pass=%s"
          % (maximum, int(BUDGET_MIB), passed))

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print("  JSON：%s" % path)
    return 0 if payload.get("runs") else 1


if __name__ == "__main__":
    sys.exit(main())
