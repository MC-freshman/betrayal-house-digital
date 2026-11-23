#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""机器人胜率基线（第 2 项）—— 先把尺子立起来，再谈调优。

为什么需要它
------------
仓库里已有三个能跑对局的工具，但没有一个能回答「英雄胜率是多少」：

* ``replay_golden.py`` 只比终局哈希（186 条），不看胜率；
* ``haunt_playtest.py`` 会按单本剧本打印胜方计数，但不落汇总字段；
* ``.workbuddy/_sim_balance.py`` 在源码树外，是可变脚本，不能当尺子。

本脚本把「执行器」和「聚合」分开：执行器复用
``haunt_playtest.run_case(haunt_id, seed, players, max_turns)``——仓库里唯一
内建「强制剧本号 + 指定人数」的入口（``engine._select_haunt_id`` 被钉成常量
lambda，见 haunt_playtest.py:232），聚合在本文件里做。

口径（与 ``docs/执行计划_第2-6项.md`` §2.1.1 一致，写进 JSON 的 definitions）
--------------------------------------------------------------------------
* 局数 = seeds × players × haunts，默认 11 × {3,4,5} × 70 = **2310**；
* 只有 ``phase=GAME_OVER`` 计 completed；胜率分母只算「有胜方」的局；
* ``winner`` ∈ {heroes, traitor}；打完却无胜方（全员阵亡）单列 ``no_winner``；
* 未完赛（含异常局）单列 ``unfinished``，**不稀释胜负分母**；
* 回合上限 400（与黄金回放一致）；
* 玩家全员 bot、``bot_difficulty=hard`` / ``bot_style=balanced``（默认档）。

用法
----
    python qa/winrate_baseline.py --json qa/winrate_baseline.json
    python qa/winrate_baseline.py --haunts 1-2 --seeds 3,7 --players 4   # 冒烟
    python qa/winrate_baseline.py --difficulty balanced                  # 换难度档

退出码：0 = 跑完并落盘；1 = 出现异常局（仍落盘，异常明细写 errors）。
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
from typing import Any, Dict, Iterable, List, Sequence, Tuple

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import haunt_playtest as playtest  # noqa: E402
from content import build_catalog  # noqa: E402
from haunt_ai_profiles import HAUNT_AI_PROFILE_OVERRIDES  # noqa: E402

DEFAULT_SEEDS: Tuple[int, ...] = (3, 7, 11, 23, 31, 101, 109, 113, 137, 151, 251)
DEFAULT_PLAYERS: Tuple[int, ...] = (3, 4, 5)
DEFAULT_HAUNTS: Tuple[int, ...] = tuple(range(1, 71))
DEFAULT_MAX_TURNS = 400
DEFAULT_OUT = QA_DIR / "winrate_baseline.json"

# 难度档 → (bot_difficulty, bot_style)。hard 档与 replay_golden._configs 完全一致，
# 这样本基线与 186 条黄金回放坐在同一套机器人参数上。
DIFFICULTY_PROFILES: Dict[str, Tuple[str, str]] = {
    "hard": ("hard", "balanced"),
    "balanced": ("normal", "balanced"),
}


# ----------------------------------------------------------------------
# 参数解析
# ----------------------------------------------------------------------
def _parse_ints(text: str) -> List[int]:
    """``"3,7,11"`` → [3, 7, 11]。"""
    values = []
    for chunk in str(text).replace("，", ",").split(","):
        chunk = chunk.strip()
        if chunk:
            values.append(int(chunk))
    return values


def _parse_ranges(text: str) -> List[int]:
    """``"1-5,9,11-12"`` → [1,2,3,4,5,9,11,12]（保序去重）。"""
    values: List[int] = []
    for chunk in str(text).replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = chunk.split("-", 1)
            values.extend(range(int(start), int(end) + 1))
        else:
            values.append(int(chunk))
    seen, ordered = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


# ----------------------------------------------------------------------
# 机器人档案
# ----------------------------------------------------------------------
_CATALOG_CACHE: Dict[int, Any] = {}


def _catalog(seed: int) -> Any:
    if seed not in _CATALOG_CACHE:
        _CATALOG_CACHE[seed] = build_catalog(seed)
    return _CATALOG_CACHE[seed]


def _install_configs(difficulty: str) -> Tuple[str, str]:
    """把 ``haunt_playtest._configs`` 换成指定难度档的版本。

    ``run_case`` 里 ``_configs(seed, players)`` 是模块级查找，替换模块属性即可，
    不改执行器源码——这样第 2 项不会顺手改动别人正在用的试玩工具。
    """
    bot_difficulty, bot_style = DIFFICULTY_PROFILES[difficulty]

    def configs(seed: int, player_count: int) -> List[Dict[str, str]]:
        faces = list(_catalog(seed).characters)
        return [
            {
                "name": "机器人%d" % (index + 1),
                "character_id": faces[index % len(faces)],
                "control": "bot",
                "bot_difficulty": bot_difficulty,
                "bot_style": bot_style,
            }
            for index in range(player_count)
        ]

    playtest._configs = configs  # type: ignore[assignment]
    return bot_difficulty, bot_style


# ----------------------------------------------------------------------
# 聚合
# ----------------------------------------------------------------------
def _new_bucket() -> Dict[str, int]:
    return {
        "games": 0,
        "completed": 0,
        "heroes_win": 0,
        "traitor_win": 0,
        "no_winner": 0,
        "unfinished": 0,
        "turns_completed_sum": 0,
    }


def _add(bucket: Dict[str, int], completed: bool, winner: str, turns: int) -> None:
    bucket["games"] += 1
    if not completed:
        bucket["unfinished"] += 1
        return
    bucket["completed"] += 1
    bucket["turns_completed_sum"] += turns
    if winner == "heroes":
        bucket["heroes_win"] += 1
    elif winner == "traitor":
        bucket["traitor_win"] += 1
    else:
        bucket["no_winner"] += 1


def _finish(bucket: Dict[str, int]) -> Dict[str, Any]:
    decisive = bucket["heroes_win"] + bucket["traitor_win"]
    completed = bucket["completed"]
    return {
        "games": bucket["games"],
        "completed": completed,
        "heroes_win": bucket["heroes_win"],
        "traitor_win": bucket["traitor_win"],
        "no_winner": bucket["no_winner"],
        "unfinished": bucket["unfinished"],
        "heroes_win_rate": round(bucket["heroes_win"] / decisive, 4) if decisive else 0.0,
        "traitor_win_rate": round(bucket["traitor_win"] / decisive, 4) if decisive else 0.0,
        "avg_turns": round(bucket["turns_completed_sum"] / completed, 2) if completed else 0.0,
    }


def _percentile(sorted_values: Sequence[int], q: float) -> int:
    if not sorted_values:
        return 0
    index = int(round(q * (len(sorted_values) - 1)))
    return int(sorted_values[index])


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _haunt_names() -> Dict[int, str]:
    catalog = _catalog(0)
    return {haunt_id: haunt.name for haunt_id, haunt in catalog.haunt_defs.items()}


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def run_baseline(
    seeds: Sequence[int],
    players: Sequence[int],
    haunts: Sequence[int],
    difficulty: str,
    max_turns: int,
) -> Dict[str, Any]:
    bot_difficulty, bot_style = _install_configs(difficulty)
    names = _haunt_names()
    total = len(seeds) * len(players) * len(haunts)

    overall = _new_bucket()
    by_haunt: Dict[int, Dict[str, int]] = {haunt_id: _new_bucket() for haunt_id in haunts}
    by_profile: Dict[str, Dict[str, int]] = {"default": _new_bucket(), "dedicated": _new_bucket()}
    by_players: Dict[int, Dict[str, int]] = {count: _new_bucket() for count in players}

    completed_turns: List[int] = []
    all_turns: List[int] = []
    errors: List[Dict[str, Any]] = []

    started_at = datetime.now()
    clock = time.time()
    done = 0

    for seed in seeds:
        for player_count in players:
            for haunt_id in haunts:
                done += 1
                try:
                    result = playtest.run_case(
                        haunt_id,
                        seed,
                        player_count,
                        max_turns=max_turns,
                    )
                    completed = bool(result.get("completed"))
                    winner = str(result.get("winner") or "")
                    turns = int(result.get("turns") or 0)
                except Exception as exc:  # noqa: BLE001 - 单局异常不该带走 2310 局
                    errors.append(
                        {
                            "seed": seed,
                            "players": player_count,
                            "haunt": haunt_id,
                            "error": "%s: %s" % (type(exc).__name__, exc),
                            "trace": traceback.format_exc(limit=3).splitlines()[-4:],
                        }
                    )
                    completed, winner, turns = False, "", 0

                profile = "dedicated" if haunt_id in HAUNT_AI_PROFILE_OVERRIDES else "default"
                _add(overall, completed, winner, turns)
                _add(by_haunt[haunt_id], completed, winner, turns)
                _add(by_profile[profile], completed, winner, turns)
                _add(by_players[player_count], completed, winner, turns)
                all_turns.append(turns)
                if completed:
                    completed_turns.append(turns)

                if done % 100 == 0 or done == total:
                    elapsed = time.time() - clock
                    rate = done / elapsed if elapsed > 0 else 0.0
                    eta = (total - done) / rate if rate > 0 else 0.0
                    print(
                        "[%4d/%4d] %5.1f%%  elapsed=%6.1fs  eta=%6.1fs  rate=%.2f games/s"
                        % (done, total, 100.0 * done / total, elapsed, eta, rate),
                        flush=True,
                    )

    duration = time.time() - clock
    finished_at = datetime.now()
    completed_sorted = sorted(completed_turns)
    summary = _finish(overall)

    payload: Dict[str, Any] = {
        "schema": "winrate-baseline/v1",
        "generated_at": finished_at.isoformat(timespec="seconds"),
        "games": summary["games"],
        "completed": summary["completed"],
        "heroes_win": summary["heroes_win"],
        "traitor_win": summary["traitor_win"],
        "no_winner": summary["no_winner"],
        "unfinished": summary["unfinished"],
        "heroes_win_rate": summary["heroes_win_rate"],
        "traitor_win_rate": summary["traitor_win_rate"],
        "heroes_win_rate_all": round(summary["heroes_win"] / summary["games"], 4)
        if summary["games"]
        else 0.0,
        "unfinished_rate": round(summary["unfinished"] / summary["games"], 4)
        if summary["games"]
        else 0.0,
        "avg_turns": summary["avg_turns"],
        "avg_turns_all": round(sum(all_turns) / len(all_turns), 2) if all_turns else 0.0,
        "turns_median": _percentile(completed_sorted, 0.5),
        "turns_p90": _percentile(completed_sorted, 0.9),
        "turns_max": completed_sorted[-1] if completed_sorted else 0,
        "duration_s": round(duration, 2),
        "by_haunt": {
            str(haunt_id): {
                **_finish(bucket),
                "haunt_name": names.get(haunt_id, ""),
                "profile": "dedicated"
                if haunt_id in HAUNT_AI_PROFILE_OVERRIDES
                else "default",
            }
            for haunt_id, bucket in by_haunt.items()
        },
        "by_profile": {key: _finish(value) for key, value in by_profile.items()},
        "by_player_count": {str(key): _finish(value) for key, value in by_players.items()},
        "seeds": list(seeds),
        "players": list(players),
        "haunts": list(haunts),
        "difficulty": difficulty,
        "max_turns": max_turns,
        "definitions": {
            "games": "seeds × players × haunts；每局强制指定剧本号（haunt_playtest.run_case）",
            "completed": "phase 曾到达 GAME_OVER 的局数",
            "heroes_win_rate": "heroes_win / (heroes_win + traitor_win)，分母不含 unfinished 与 no_winner",
            "unfinished": "回合打满仍未 GAME_OVER；含执行异常的局（明细见 errors）",
            "no_winner": "已 GAME_OVER 但 state.winner 为空（如全员阵亡）",
            "avg_turns": "仅 completed 局的回合数均值",
            "heroes_win_rate_all": "heroes_win / games，仅作对照，不作为主口径",
            "by_profile": "dedicated = 该剧本在 haunt_ai_profiles.HAUNT_AI_PROFILE_OVERRIDES 有专属档案",
        },
        "diagnosis": _diagnose(by_haunt),
        "errors": errors,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executor": "haunt_playtest.run_case",
            "executor_sha256": _sha256(GAME_DIR / "haunt_playtest.py"),
            "engine_sha256": _sha256(GAME_DIR / "engine.py"),
            "bot_ai_sha256": _sha256(GAME_DIR / "bot_ai.py"),
            "haunt_ai_profiles_sha256": _sha256(GAME_DIR / "haunt_ai_profiles.py"),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "bot_difficulty": bot_difficulty,
            "bot_style": bot_style,
            "difficulty_flag": difficulty,
            "max_turns": max_turns,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "seconds_per_game": round(duration / total, 4) if total else 0.0,
        },
    }
    return payload


def _diagnose(by_haunt: Dict[int, Dict[str, int]]) -> Dict[str, Any]:
    """异常清单：0 英雄胜、有未完赛、英雄胜率最低的 5 本。"""
    rows = []
    zero_hero: List[int] = []
    incomplete: List[Dict[str, Any]] = []
    for haunt_id in sorted(by_haunt):
        bucket = _finish(by_haunt[haunt_id])
        if bucket["completed"] and bucket["heroes_win"] == 0:
            zero_hero.append(haunt_id)
        if bucket["unfinished"]:
            incomplete.append(
                {
                    "haunt": haunt_id,
                    "unfinished": bucket["unfinished"],
                    "games": bucket["games"],
                }
            )
        rows.append(
            {
                "haunt": haunt_id,
                "games": bucket["games"],
                "heroes_win": bucket["heroes_win"],
                "traitor_win": bucket["traitor_win"],
                "unfinished": bucket["unfinished"],
                "heroes_win_rate": bucket["heroes_win_rate"],
                "avg_turns": bucket["avg_turns"],
            }
        )
    lowest = sorted(
        [row for row in rows if row["games"] > 0],
        key=lambda row: (row["heroes_win_rate"], -row["games"], row["haunt"]),
    )[:5]
    return {
        "zero_hero_haunts": zero_hero,
        "zero_hero_count": len(zero_hero),
        "incomplete_haunts": incomplete,
        "lowest_hero_rate_top5": lowest,
        "highest_hero_rate_top5": sorted(
            [row for row in rows if row["games"] > 0],
            key=lambda row: (-row["heroes_win_rate"], -row["games"], row["haunt"]),
        )[:5],
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="机器人胜率基线（2310 局口径）")
    parser.add_argument(
        "--seeds",
        default=",".join(str(value) for value in DEFAULT_SEEDS),
        help="逗号分隔种子，默认 11 个（与执行计划 §2.1.1 一致）",
    )
    parser.add_argument(
        "--players",
        default=",".join(str(value) for value in DEFAULT_PLAYERS),
        help="逗号分隔人数，默认 3,4,5",
    )
    parser.add_argument(
        "--haunts",
        default="1-70",
        help="剧本号区间/列表，如 1-70 或 1-5,9",
    )
    parser.add_argument(
        "--difficulty",
        default="hard",
        choices=sorted(DIFFICULTY_PROFILES),
        help="hard=bot_difficulty hard（与黄金回放一致）；balanced=normal",
    )
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--json", default=str(DEFAULT_OUT), help="输出路径")
    args = parser.parse_args(list(argv) if argv is not None else None)

    seeds = _parse_ints(args.seeds)
    players = _parse_ints(args.players)
    haunts = _parse_ranges(args.haunts)
    if not seeds or not players or not haunts:
        print("[FAIL] seeds / players / haunts 不能为空", file=sys.stderr)
        return 2

    total = len(seeds) * len(players) * len(haunts)
    print(
        "胜率基线：%d 种子 × %d 人数 × %d 剧本 = %d 局（difficulty=%s, max_turns=%d）"
        % (len(seeds), len(players), len(haunts), total, args.difficulty, args.max_turns),
        flush=True,
    )

    payload = run_baseline(seeds, players, haunts, args.difficulty, args.max_turns)
    out_path = Path(args.json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        "完成：games=%d 英雄 %d(%.2f%%) 叛徒 %d(%.2f%%) 未完 %d 无胜方 %d "
        "平均回合 %.1f 耗时 %.1fs"
        % (
            payload["games"],
            payload["heroes_win"],
            payload["heroes_win_rate"] * 100,
            payload["traitor_win"],
            payload["traitor_win_rate"] * 100,
            payload["unfinished"],
            payload["no_winner"],
            payload["avg_turns"],
            payload["duration_s"],
        ),
        flush=True,
    )
    print("产物：%s" % out_path, flush=True)
    if payload["errors"]:
        print(
            "[WARN] %d 局执行异常，已计入 unfinished，明细见 errors"
            % len(payload["errors"]),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
