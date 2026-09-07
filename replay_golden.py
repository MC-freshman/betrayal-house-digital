"""种子回放黄金测试 —— 严格复刻路线的回归安全网。

原理
----
引擎的随机数来自独立实例且状态会存进存档：
    engine.py:  self.rng = random.Random(seed)
    save/load:  rng.getstate() / rng.setstate()
因此「同一种子 + 同一串行动」必然得到完全相同的终局。把终局状态哈希存成
基准，以后每次改动规则都重跑对比：哈希变了，就说明行为变了，需要人工确认
是有意改动还是回归。

实测确认（2026-08-31）：seed=11 四人局跑两次，终局哈希一致；
seed=23 五人局同样一致。且对局能真正推进到 GAME_OVER。

本文件不依赖 tkinter，可用任意 Python 3.9+ 运行。

用法
----
    python replay_golden.py              # 对比基准
    python replay_golden.py --update     # 重新生成基准（确认改动是有意时）
    python replay_golden.py --verbose    # 显示每个用例的摘要

退出码：0 = 全部匹配；1 = 有差异；2 = 环境或用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bot_ai import BotController  # type: ignore
    from content import build_catalog  # type: ignore
    from engine import GameEngine  # type: ignore
    from net.serialize import state_to_dict  # type: ignore
else:  # pragma: no cover
    from .bot_ai import BotController
    from .content import build_catalog
    from .engine import GameEngine
    from .net.serialize import state_to_dict

BASELINE_PATH = Path(__file__).resolve().parent / "golden_replays.json"

# 覆盖 3/4/5/6 人局，每档 2 个种子。刻意选不同人数，因为剧本的怪物数量、
# 进度轨道目标值很多都按人数计算（half_players_floor / player_count 等），
# 只测单一人数会漏掉这类按人数分支的回归。
#
# 第三项是强制剧本号：1、2、5 是有定制 mode handler 的剧本
# （haunt_modes.BanishmentEscortMode / SeanceRaceMode / WerewolfHuntMode）。
# 随机对局很难撞上它们，而改动剧本分派逻辑时最可能弄坏的就是这几个，
# 所以单独钉住。
CASES: list[tuple[int, int, int | None]] = [
    (7, 3, None),
    (11, 3, None),
    (11, 4, None),
    (17, 4, None),
    (23, 5, None),
    (29, 5, None),
    (31, 6, None),
    (37, 6, None),
    (113, 3, 1),
    (127, 5, 1),
    (107, 5, 1),
    (105, 4, 5),
    (157, 4, 5),
    (113, 3, 2),
    (127, 5, 2),
    (109, 4, 2),
    (113, 3, 3),
    (113, 3, 7),
    (113, 3, 8),
    (113, 3, 9),
    (113, 3, 10),
    (113, 3, 11),
    (113, 3, 12),
    (113, 3, 13),
    (113, 3, 14),
    (113, 3, 15),
    (113, 3, 16),
    (113, 3, 17),
    (113, 3, 18),
    (113, 3, 19),
    (113, 3, 20),
    (113, 3, 21),
    (113, 3, 22),
    (113, 3, 23),
    (113, 3, 24),
    (113, 3, 25),
    (109, 4, 25),
    (113, 3, 26),
    (109, 4, 26),
    (113, 3, 27),
    (109, 4, 27),
    (113, 3, 28),
    (109, 4, 28),
    (113, 3, 29),
    (109, 4, 29),
    (113, 3, 30),
    (109, 4, 30),
    (131, 4, 3),
    (109, 4, 3),
    (137, 3, 4),
    (131, 4, 4),
    (127, 5, 6),
    (109, 4, 6),
    (113, 3, 38),
    (109, 4, 38),
    (113, 3, 31),
    (109, 4, 31),
    (113, 3, 32),
    (113, 3, 33),
    (113, 3, 34),
    (113, 3, 35),
    (113, 3, 36),
    (113, 3, 37),
    (113, 3, 39),
    (113, 3, 40),
    (113, 3, 41),
    (113, 3, 42),
    (113, 3, 43),
    (113, 3, 44),
    (109, 4, 44),
    (113, 3, 45),
    (113, 3, 46),
    (109, 4, 46),
    (113, 3, 47),
    (109, 4, 47),
    (113, 3, 48),
    (109, 4, 48),
    (113, 3, 49),
    (109, 4, 49),
    (113, 3, 50),
    (113, 3, 51),
    (113, 3, 52),
    (113, 3, 53),
    (109, 4, 50),
    (109, 4, 32),
]

MAX_TURNS = 400  # 兜底，防止偶发死循环把测试挂住


def _configs(seed: int, player_count: int) -> list[dict[str, str]]:
    faces = list(build_catalog(seed).characters)
    return [
        {
            "name": f"机器人{i + 1}",
            "character_id": faces[i % len(faces)],
            "control": "bot",
            "bot_difficulty": "hard",
            "bot_style": "balanced",
        }
        for i in range(player_count)
    ]


def _fingerprint(engine: GameEngine) -> tuple[str, dict]:
    """终局状态哈希 + 便于人工判断的摘要。"""
    payload = json.dumps(
        state_to_dict(engine.state),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    summary = {
        "turns": engine.state.turn_count,
        "phase": engine.state.phase,
        "winner": engine.state.winner,
        "winner_reason": engine.state.winner_reason,
        "haunt": engine.state.haunt.id if engine.state.haunt else None,
        "haunt_name": engine.state.haunt.name if engine.state.haunt else None,
        "rooms": len(engine.state.board),
        "monsters": len(engine.state.monsters),
    }
    return digest, summary


def run_case(seed: int, player_count: int, forced_haunt: int | None = None) -> dict:
    engine = GameEngine(seed=seed)
    engine.start_new_game(_configs(seed, player_count))
    if forced_haunt is not None:
        # 钉住指定剧本，确保手写的 1 号 / 5 号处理器也被回归覆盖。
        engine._select_haunt_id = lambda room_id, omen_id, _h=forced_haunt: _h  # type: ignore[method-assign]
    controller = BotController()
    completed = False
    for _ in range(MAX_TURNS):
        if engine.state.phase == "GAME_OVER":
            completed = True
            break
        if not controller.take_turn(engine):
            break
    digest, summary = _fingerprint(engine)

    # 已知问题（2026-08-31 实测）：房间牌耗尽后，探索阶段会僵死。
    # 表现：机器人放完全部房间牌后无处可去，不再抽到预兆牌，作祟永不触发，
    #       对局跑满上限仍停在 EXPLORE。
    # 权威规则（BetrayalHouseHill_v4.2.pdf p2）其实允许回收：
    #       "If the entire stack is used, shuffle the discard pile;
    #        it becomes the new stack."
    # 当前引擎的 has_remaining_room_cards() 选择了"楼层无剩余牌就不再生成"，
    # 与原版不同，属于严格复刻待修项。测试如实记录 completed=False，
    # 这样即便跑不完也能检出行为变化。
    stall = (
        not completed
        and engine.state.phase == "EXPLORE"
        and not engine.state.room_deck
    )
    return {
        "seed": seed,
        "players": player_count,
        "completed": completed,
        "stalled_no_room_cards": stall,
        "hash": digest,
        **summary,
    }


def load_baseline() -> dict[str, dict]:
    if not BASELINE_PATH.exists():
        return {}
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {item["key"]: item for item in data.get("cases", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description="种子回放黄金测试")
    parser.add_argument("--update", action="store_true", help="重新生成基准文件")
    parser.add_argument("--verbose", action="store_true", help="显示每个用例摘要")
    args = parser.parse_args()

    baseline = load_baseline()
    results: list[dict] = []

    for seed, player_count, forced_haunt in CASES:
        key = f"seed{seed}-{player_count}p" + (f"-haunt{forced_haunt}" if forced_haunt else "")
        try:
            current = run_case(seed, player_count, forced_haunt)
        except Exception as exc:  # 任用例崩溃都要报出来，不能静默跳过
            print(f"[异常] {key}: {type(exc).__name__}: {exc}")
            return 1
        current["key"] = key
        current["forced_haunt"] = forced_haunt
        results.append(current)

        expected = baseline.get(key)
        if expected is None:
            print(f"[新增] {key}: 基准中没有该用例（{current['turns']} 回合，"
                  f"{current['phase']}），请确认后用 --update 写入")
            continue
        if expected["hash"] == current["hash"]:
            if args.verbose:
                flag = "" if current["completed"] else "  ⚠ 未跑到终局"
                print(f"[通过] {key}: {current['turns']} 回合，"
                      f"胜方 {current['winner']}，剧本 #{current['haunt']} {current['haunt_name']}{flag}")
            continue

        print(f"[差异] {key}")
        print(f"       期望: {expected['turns']} 回合 / {expected['phase']} / "
              f"胜方 {expected['winner']} / 剧本 #{expected['haunt']}")
        print(f"       实际: {current['turns']} 回合 / {current['phase']} / "
              f"胜方 {current['winner']} / 剧本 #{current['haunt']}")
        print(f"       期望哈希 {expected['hash'][:16]}…  实际哈希 {current['hash'][:16]}…")

    if args.update:
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "note": "种子回放基准。改动规则后若哈希变化，先确认是有意改动再 --update。",
                    "cases": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n已写入基准：{BASELINE_PATH}（{len(results)} 个用例）")
        return 0

    if not baseline:
        print("\n基准文件不存在。首次运行请先生成：")
        print("  python replay_golden.py --update")
        return 1

    mismatched = [
        item
        for item in results
        if item["key"] in baseline and baseline[item["key"]]["hash"] != item["hash"]
    ]
    missing = [item for item in results if item["key"] not in baseline]

    print()
    if mismatched or missing:
        print(f"黄金测试：{len(mismatched)} 个差异，{len(missing)} 个新增。"
              f"若改动是有意的，运行 --update 更新基准。")
        return 1
    print(f"黄金测试通过：{len(results)} 个用例全部与基准一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
