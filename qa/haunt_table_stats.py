#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""作祟查表回退覆盖率统计（第 3 项）。

目的只有一个：证明「表不存在时，200 局真对局全部走回退、且不抛异常」。
它**不验证表值正确性**——``qa/haunt_table.json`` 的 ``entries`` 目前是空的，
官方 13×7=91 格表值未获取，谁也没有资格在这里断言某格应该等于几号剧本。

关键点：必须走**自然选择**。``haunt_playtest.run_case`` 会把
``engine._select_haunt_id`` 钉成常量 lambda（强制剧本号），那条路径根本不经过
``haunt_table.select_haunt``；所以这里用 ``replay_golden.run_case``（不传
forced_haunt，不替换选择函数），让引擎自己触发作祟。

用法::

    python qa/haunt_table_stats.py
    python qa/haunt_table_stats.py --games 30 --json qa/_haunt_stats_smoke.json

退出码：0 = 回退通路正常且无异常；1 = 计数对不上或有异常局。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import haunt_table  # noqa: E402
import replay_golden  # noqa: E402

DEFAULT_GAMES = 200
DEFAULT_OUT = QA_DIR / "haunt_table_stats.json"
PLAYER_COUNTS: Tuple[int, ...] = (3, 4, 5)
MAX_SEED = 67  # 67 × 3 = 201 ≥ 200，够默认网格用


def _grid(games: int) -> List[Tuple[int, int]]:
    """确定性网格：种子 1..67 × {3,4,5} 人，按序取前 games 局。"""
    pairs = [(seed, players) for seed in range(1, MAX_SEED + 1) for players in PLAYER_COUNTS]
    if games > len(pairs):
        raise SystemExit("games 超出网格容量（%d）" % len(pairs))
    return pairs[:games]


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def run(games: int) -> Dict[str, Any]:
    haunt_table.reset_selection_counts()
    pairs = _grid(games)

    started_at = datetime.now()
    clock = time.time()
    errors: List[Dict[str, Any]] = []
    no_haunt: List[Dict[str, Any]] = []
    reached = 0

    for index, (seed, players) in enumerate(pairs, start=1):
        try:
            result = replay_golden.run_case(seed, players)
            if result.get("haunt"):
                reached += 1
            else:
                # 探索期就结束（例如全员阵亡）的局没有作祟可触发，如实登记，
                # 不把它算成"回退成功"，也不让它悄悄消失。
                no_haunt.append(
                    {
                        "seed": seed,
                        "players": players,
                        "completed": bool(result.get("completed")),
                        "phase": result.get("phase", ""),
                        "winner": result.get("winner") or "",
                        "turns": result.get("turns", 0),
                    }
                )
        except Exception as exc:  # noqa: BLE001 - 记下来，不让一局带走统计
            errors.append(
                {
                    "seed": seed,
                    "players": players,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "trace": traceback.format_exc(limit=3).splitlines()[-4:],
                }
            )
        if index % 50 == 0 or index == len(pairs):
            print(
                "[%3d/%3d] elapsed=%5.1fs" % (index, len(pairs), time.time() - clock),
                flush=True,
            )

    duration = time.time() - clock
    counts = haunt_table.selection_counts()
    status = haunt_table.table_status()
    selections = counts["table"] + counts["fallback"]
    fallback_rate = round(counts["fallback"] / selections, 4) if selections else 0.0

    return {
        "schema": "haunt-table-stats/v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "games": len(pairs),
        "selections": selections,
        "games_reached_haunt": reached,
        "games_without_haunt": len(pairs) - reached,
        "games_without_haunt_detail": no_haunt,
        "table_hits": counts["table"],
        "fallback_hits": counts["fallback"],
        "fallback_rate": fallback_rate,
        "table_rate": counts["table_rate"],
        "invalid_cells": counts["invalid"],
        "table_missing": counts["table_missing"],
        "load_errors": counts["load_error"],
        "errors": errors,
        "duration_s": round(duration, 2),
        "grid": {
            "seeds": sorted({seed for seed, _ in pairs}),
            "players": list(PLAYER_COUNTS),
            "take": len(pairs),
            "shape": "product(seed 1..67, players 3/4/5)[:games]",
            "forced_haunt": False,
            "executor": "replay_golden.run_case",
        },
        "table": status,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "engine_sha256": _sha256(GAME_DIR / "engine.py"),
            "haunt_table_sha256": _sha256(GAME_DIR / "haunt_table.py"),
            "started_at": started_at.isoformat(timespec="seconds"),
        },
    }


def judge(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if payload["errors"]:
        reasons.append("%d 局抛异常" % len(payload["errors"]))
    if payload["selections"] != payload["games_reached_haunt"]:
        reasons.append(
            "选择次数 %d ≠ 触发作祟局数 %d"
            % (payload["selections"], payload["games_reached_haunt"])
        )
    if payload["table_hits"] + payload["fallback_hits"] != payload["selections"]:
        reasons.append(
            "table_hits %d + fallback_hits %d ≠ selections %d"
            % (payload["table_hits"], payload["fallback_hits"], payload["selections"])
        )
    if payload["table"]["empty"] and payload["selections"]:
        if payload["table_hits"] != 0:
            reasons.append("空表却出现 %d 次命中" % payload["table_hits"])
        if payload["fallback_hits"] != payload["selections"]:
            reasons.append(
                "空表但回退只覆盖 %d/%d" % (payload["fallback_hits"], payload["selections"])
            )
    if payload["load_errors"] or payload["invalid_cells"]:
        reasons.append(
            "表读取/脏值计数非 0：load_errors=%d invalid=%d"
            % (payload["load_errors"], payload["invalid_cells"])
        )
    return (not reasons), reasons


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="作祟查表回退覆盖率统计（200 局自然对局）")
    parser.add_argument("--games", type=int, default=DEFAULT_GAMES)
    parser.add_argument("--json", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    payload = run(args.games)
    out_path = Path(args.json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ok, reasons = judge(payload)
    print(
        "games=%d 触发作祟=%d 选择=%d table_hits=%d fallback_hits=%d 回退率=%.4f 耗时=%.1fs"
        % (
            payload["games"],
            payload["games_reached_haunt"],
            payload["selections"],
            payload["table_hits"],
            payload["fallback_hits"],
            payload["fallback_rate"],
            payload["duration_s"],
        ),
        flush=True,
    )
    print("表状态：%s" % json.dumps(payload["table"], ensure_ascii=False), flush=True)
    print("产物：%s" % out_path, flush=True)

    if not ok:
        for reason in reasons:
            print("[FAIL] %s" % reason, file=sys.stderr, flush=True)
        return 1
    if payload["table"]["empty"]:
        print("[PASS] 回退通路正常：表为空，全部选择走 SHA1 兜底且未抛异常", flush=True)
    else:
        print(
            "[PASS] 查表通路正常：%d/%d 次命中表值（表源=%s），未抛异常"
            % (payload["table_hits"], payload["selections"], payload["table"]["source"]),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
