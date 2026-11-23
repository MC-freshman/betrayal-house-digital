#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""胜率基线产物校验器（第 2 项，只读）。

它只回答一个问题：``qa/winrate_baseline.json`` 里的数字**自洽**且**覆盖完整**吗？
（不重新跑对局，也不判断胜率高不高——那是调优的事。）

校验项
------
C01 文件存在且是合法 JSON
C02 schema = winrate-baseline/v1
C03 games = len(seeds) × len(players) × len(haunts)
C04 heroes + traitor + no_winner + unfinished = games
C05 heroes_win_rate + traitor_win_rate ≤ 1（且与计数换算一致）
C06 by_haunt 覆盖恰好 len(haunts) 项（默认 70），键与 haunts 一一对应
C07 by_haunt 逐本计数汇总 = 全局计数
C08 by_profile（default/dedicated）汇总 = 全局计数
C09 by_player_count 汇总 = 全局计数
C10 completed > 0 时 avg_turns > 0；duration_s > 0
C11 runtime 记录了执行器与 engine 的 sha256（证据可归属到代码版本）
C12 unfinished ≥ len(errors)（异常局必须被算进未完赛，不许凭空消失）
C13 seeds 无重复

用法::

    python qa/verify_winrate.py
    python qa/verify_winrate.py --json qa/winrate_baseline.json --out qa/verify_winrate.json

退出码：0 = 全部 PASS；1 = 有 FAIL。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

QA_DIR = Path(__file__).resolve().parent
DEFAULT_JSON = QA_DIR / "winrate_baseline.json"
RATE_TOL = 1e-3


def _check(results: List[Dict[str, Any]], ok: bool, item: str, detail: str) -> None:
    results.append({"item": item, "ok": bool(ok), "detail": detail})
    print("[%s] %s  %s" % ("PASS" if ok else "FAIL", item, detail), flush=True)


def _rate_ok(bucket: Dict[str, Any]) -> bool:
    decisive = int(bucket.get("heroes_win", 0)) + int(bucket.get("traitor_win", 0))
    expected = round(int(bucket.get("heroes_win", 0)) / decisive, 4) if decisive else 0.0
    return abs(float(bucket.get("heroes_win_rate", 0.0)) - expected) <= RATE_TOL


def verify(path: Path) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []

    if not path.is_file():
        _check(results, False, "C01 产物存在", "缺少文件：%s" % path)
        return {"verdict": "FAIL", "checks": results, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        _check(results, False, "C01 产物存在", "JSON 解析失败：%s" % exc)
        return {"verdict": "FAIL", "checks": results, "path": str(path)}
    _check(results, True, "C01 产物存在", "已读取 %s" % path.name)

    _check(
        results,
        data.get("schema") == "winrate-baseline/v1",
        "C02 schema",
        "schema=%r" % data.get("schema"),
    )

    seeds = list(data.get("seeds") or [])
    players = list(data.get("players") or [])
    haunts = list(data.get("haunts") or [])
    games = int(data.get("games", 0))
    expected_games = len(seeds) * len(players) * len(haunts)
    _check(
        results,
        games == expected_games and expected_games > 0,
        "C03 局数 = 种子×人数×剧本",
        "games=%d，期望 %d（%d×%d×%d）"
        % (games, expected_games, len(seeds), len(players), len(haunts)),
    )

    heroes = int(data.get("heroes_win", 0))
    traitor = int(data.get("traitor_win", 0))
    no_winner = int(data.get("no_winner", 0))
    unfinished = int(data.get("unfinished", 0))
    total = heroes + traitor + no_winner + unfinished
    _check(
        results,
        total == games,
        "C04 胜方计数闭合",
        "英雄%d + 叛徒%d + 无胜方%d + 未完%d = %d，games=%d"
        % (heroes, traitor, no_winner, unfinished, total, games),
    )

    rate_sum = float(data.get("heroes_win_rate", 0.0)) + float(
        data.get("traitor_win_rate", 0.0)
    )
    decisive = heroes + traitor
    expected_rate = round(heroes / decisive, 4) if decisive else 0.0
    _check(
        results,
        rate_sum <= 1.0 + RATE_TOL
        and abs(float(data.get("heroes_win_rate", 0.0)) - expected_rate) <= RATE_TOL,
        "C05 胜率相加 ≤ 1 且可换算",
        "英雄率%.4f + 叛徒率%.4f = %.4f（期望英雄率 %.4f，分母=%d）"
        % (
            float(data.get("heroes_win_rate", 0.0)),
            float(data.get("traitor_win_rate", 0.0)),
            rate_sum,
            expected_rate,
            decisive,
        ),
    )

    by_haunt = data.get("by_haunt") or {}
    haunt_keys = {str(value) for value in haunts}
    coverage_ok = set(by_haunt) == haunt_keys and len(by_haunt) == len(haunts)
    _check(
        results,
        coverage_ok,
        "C06 by_haunt 覆盖剧本",
        "by_haunt=%d 项，haunts=%d 项，键集合%s"
        % (len(by_haunt), len(haunts), "相同" if set(by_haunt) == haunt_keys else "不同"),
    )

    sums = {"games": 0, "heroes_win": 0, "traitor_win": 0, "no_winner": 0, "unfinished": 0}
    rate_bad: List[str] = []
    for key, bucket in by_haunt.items():
        for field in sums:
            sums[field] += int(bucket.get(field, 0))
        if not _rate_ok(bucket):
            rate_bad.append(key)
    haunt_ok = (
        sums["games"] == games
        and sums["heroes_win"] == heroes
        and sums["traitor_win"] == traitor
        and sums["no_winner"] == no_winner
        and sums["unfinished"] == unfinished
        and not rate_bad
    )
    _check(
        results,
        haunt_ok,
        "C07 by_haunt 汇总一致",
        "games=%d 英雄%d 叛徒%d 无胜方%d 未完%d%s"
        % (
            sums["games"],
            sums["heroes_win"],
            sums["traitor_win"],
            sums["no_winner"],
            sums["unfinished"],
            "" if not rate_bad else "；胜率换算不符：%s" % ",".join(sorted(rate_bad)[:5]),
        ),
    )

    by_profile = data.get("by_profile") or {}
    prof_sums = {
        key: sum(int(bucket.get(key, 0)) for bucket in by_profile.values())
        for key in ("games", "heroes_win", "traitor_win", "no_winner", "unfinished")
    }
    profile_ok = (
        set(by_profile) == {"default", "dedicated"}
        and prof_sums["games"] == games
        and prof_sums["heroes_win"] == heroes
        and prof_sums["traitor_win"] == traitor
        and prof_sums["no_winner"] == no_winner
        and prof_sums["unfinished"] == unfinished
    )
    _check(
        results,
        profile_ok,
        "C08 by_profile 汇总一致",
        "档案=%s，games=%d 英雄%d 叛徒%d"
        % (sorted(by_profile), prof_sums["games"], prof_sums["heroes_win"], prof_sums["traitor_win"]),
    )

    by_players = data.get("by_player_count") or {}
    player_sums = {
        key: sum(int(bucket.get(key, 0)) for bucket in by_players.values())
        for key in ("games", "heroes_win", "traitor_win", "no_winner", "unfinished")
    }
    players_ok = (
        set(by_players) == {str(value) for value in players}
        and player_sums["games"] == games
        and player_sums["heroes_win"] == heroes
        and player_sums["traitor_win"] == traitor
        and player_sums["no_winner"] == no_winner
        and player_sums["unfinished"] == unfinished
    )
    _check(
        results,
        players_ok,
        "C09 by_player_count 汇总一致",
        "人数档=%s，games=%d" % (sorted(by_players), player_sums["games"]),
    )

    completed = int(data.get("completed", 0))
    avg_turns = float(data.get("avg_turns", 0.0))
    duration = float(data.get("duration_s", 0.0))
    _check(
        results,
        (completed == 0 or avg_turns > 0) and duration > 0 and completed == heroes + traitor + no_winner,
        "C10 回合与耗时可信",
        "completed=%d avg_turns=%.2f duration_s=%.1f" % (completed, avg_turns, duration),
    )

    runtime = data.get("runtime") or {}
    sha = str(runtime.get("engine_sha256", ""))
    _check(
        results,
        bool(runtime.get("executor")) and len(sha) == 64 and sha.strip("0") != "",
        "C11 证据可归属到代码版本",
        "executor=%r engine_sha256=%s…（%d 位）"
        % (runtime.get("executor"), sha[:12], len(sha)),
    )

    errors = list(data.get("errors") or [])
    _check(
        results,
        unfinished >= len(errors),
        "C12 异常局计入未完赛",
        "errors=%d，unfinished=%d" % (len(errors), unfinished),
    )

    _check(
        results,
        len(seeds) == len(set(seeds)),
        "C13 种子无重复",
        "%d 个种子，去重后 %d 个" % (len(seeds), len(set(seeds))),
    )

    failed = [item["item"] for item in results if not item["ok"]]
    return {
        "schema": "winrate-verify/v1",
        "path": str(path),
        "verdict": "PASS" if not failed else "FAIL",
        "checks_pass": len(results) - len(failed),
        "checks_total": len(results),
        "failed": failed,
        "checks": results,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验胜率基线 JSON 的自洽性与覆盖度（只读）")
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="待校验的基线 JSON")
    parser.add_argument("--out", default="", help="把校验结果另存为 JSON（可选）")
    args = parser.parse_args(argv)

    result = verify(Path(args.json))
    print("-" * 72, flush=True)
    print(
        "胜率基线校验：%d/%d 项通过 → %s"
        % (result["checks_pass"], result["checks_total"], result["verdict"]),
        flush=True,
    )
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("校验结果：%s" % out, flush=True)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
