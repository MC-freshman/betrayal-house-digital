"""剧本试玩诊断器 —— 让 70 本剧本的 AI 表现可量化、可对比、可回归。

为什么需要它
------------
黄金回放网（replay_golden.py）只认终局哈希：AI 在中途怎么走、有没有
"像个人"地玩，它看不出来。本工具补上这一层：

  · **单本排查**：一本剧本跑若干种子，看它能不能自然打完、AI 有没有
    朝着自己的胜利线推进、剧本行动有没有被真正用起来。
  · **跨本隔离**：`--json` 存快照 + `--compare` 对比，改动一本剧本后
    全量重跑，只有被改的那几本允许出现差异，其它本一旦变化就报警。

用法
----
    python haunt_playtest.py --haunts 39            # 单本
    python haunt_playtest.py --batch 1              # 批次（1 = 剧本 1-5）
    python haunt_playtest.py --all --players 4 --seeds 101,113
    python haunt_playtest.py --haunts 39 --idle traitor   # 叛徒挂机探针
    python haunt_playtest.py --all --json playtest.json   # 存快照
    python haunt_playtest.py --all --compare playtest.json --allow 39,40

诊断项（每局）
    turns/winner/reason/phase   终局情况
    offered/used/succeeded      剧本行动"出现过几次/执行过几次/成功几次"
                                （区分「没机会用」和「有机会却不爱用」）
    max_room                    同一玩家访问同一房间的最高次数（震荡度量）
    pingpong                    A→B→A 往返步数（来回踱步度量）
    tracks/flags                轨道与旗标快照（进度是否推进）
    monsters/heroes             怪物与英雄存亡

自动判警
    [未跑完]      回合打满仍未 GAME_OVER
    [探索僵死]    停在 EXPLORE 且房间牌耗尽（引擎已知待修项）
    [回合过长]    >= --long-turns（默认 120）
    [行动空转]    剧本行动能出现但一次都没执行
    [震荡]        单房间访问 >= --osc-threshold（默认 15）

退出码：0 = 无警；1 = 有警或对比出现非允许差异；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bot_ai import BotController  # type: ignore
    from content import build_catalog  # type: ignore
    from engine import ActionCommand, GameEngine  # type: ignore
else:  # pragma: no cover
    from .bot_ai import BotController
    from .content import build_catalog
    from .engine import ActionCommand, GameEngine

MOVE_RE = re.compile(r"^(.+?) 移动到 (.+?)。$")

DEFAULT_SEEDS = (101, 113, 109)
DEFAULT_PLAYERS = 4
DEFAULT_MAX_TURNS = 300
DEFAULT_LONG_TURNS = 120
DEFAULT_OSC = 15


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


class _Stats:
    """一局的原始观测数据。"""

    def __init__(self) -> None:
        self.offered: dict[str, int] = {}
        self.used: dict[str, int] = {}
        self.succeeded: dict[str, int] = {}
        self.moves: dict[str, list[str]] = {}
        self.log: list[str] = []

    def note_offered(self, action_id: str) -> None:
        self.offered[action_id] = self.offered.get(action_id, 0) + 1

    def note_used(self, action_id: str, ok: bool) -> None:
        self.used[action_id] = self.used.get(action_id, 0) + 1
        if ok:
            self.succeeded[action_id] = self.succeeded.get(action_id, 0) + 1

    def note_move(self, player: str, room: str) -> None:
        self.moves.setdefault(player, []).append(room)


class _HandlerProxy:
    """包住剧本 handler 单例，统计行动的出现/执行；其余属性原样透传。

    handler 在 `_MODE_HANDLERS` 里是单例，直接给实例方法打补丁会污染
    后续所有对局（工具本身会成为 bug 源）。所以改为每局包一层一次性代理，
    对局结束即随 engine 一起丢弃。

    注意两点，都是实测踩出来的：
      1. 剧本是探索中才抽出来的，引擎开局时 `_mode_handler()` 还是通用回落。
         所以这里保存的是**解析函数**，每次调用都重新取当前 handler。
      2. 绝不能缓存解析结果：探索阶段 `available_move_options` 会查
         `can_discover_rooms`，那一次解析拿到的是通用 handler；一旦缓存，
         整个作祟阶段都会被锁死在通用 handler 上（第一版实测：1-5 号全
         按 generic 跑完，剧本机制根本没被触发）。
    """

    def __init__(self, resolver: object, stats: _Stats) -> None:
        object.__setattr__(self, "_resolve", resolver)
        object.__setattr__(self, "_stats", stats)

    def _inner(self) -> object:
        return object.__getattribute__(self, "_resolve")()

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner(), name)

    def available_actions(self, engine: object, player: object) -> list:
        actions = self._inner().available_actions(engine, player)  # type: ignore[attr-defined]
        for action in actions:
            self._stats.note_offered(str(getattr(action, "id", action)))
        return actions

    def perform_action(self, engine: object, player: object, action_id: str, data: dict) -> bool:
        ok = self._inner().perform_action(engine, player, action_id, data)  # type: ignore[attr-defined]
        self._stats.note_used(str(action_id), bool(ok))
        return bool(ok)


class _IdleController(BotController):
    """指定角色挂机（每回合直接结束），用来检验另一侧的 AI 能否独立取胜。"""

    def __init__(self, idle_role: str) -> None:
        super().__init__()
        self.idle_role = idle_role

    def take_turn(self, engine: GameEngine) -> bool:
        if not engine.state.players or engine.state.phase == "GAME_OVER":
            return False
        player = engine.current_player
        if player.role == self.idle_role and not player.dead:
            engine.execute_command(ActionCommand("end_turn", player.id))
            return True
        return super().take_turn(engine)


def _summarize_flags(flags: dict) -> dict:
    """旗标摘要：标量原样，列表/字典只记规模，避免快照过大。"""
    out: dict[str, object] = {}
    for key, value in sorted(flags.items()):
        if isinstance(value, (bool, int, float, str)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = f"[{len(value)}]"
        elif isinstance(value, dict):
            out[key] = f"{{{len(value)}}}"
        else:
            out[key] = type(value).__name__
    return out


def _move_metrics(moves: dict[str, list[str]]) -> dict:
    """从移动序列里算震荡指标。"""
    total = 0
    worst_room = ("", 0)
    worst_pingpong = ("", 0)
    for player, seq in moves.items():
        total += len(seq)
        visits: dict[str, int] = {}
        for room in seq:
            visits[room] = visits.get(room, 0) + 1
        for room, count in visits.items():
            if count > worst_room[1]:
                worst_room = (f"{player}@{room}", count)
        # A→B→A：第 i 步回到第 i-2 步的房间
        back = sum(1 for i in range(2, len(seq)) if seq[i] == seq[i - 2])
        if back > worst_pingpong[1]:
            worst_pingpong = (player, back)
    return {
        "moves_total": total,
        "max_room": worst_room[0],
        "max_room_count": worst_room[1],
        "pingpong": worst_pingpong[1],
        "pingpong_player": worst_pingpong[0],
    }


def run_case(
    haunt_id: int,
    seed: int,
    players: int,
    max_turns: int = DEFAULT_MAX_TURNS,
    idle_role: str | None = None,
    long_turns: int = DEFAULT_LONG_TURNS,
    osc_threshold: int = DEFAULT_OSC,
) -> dict:
    engine = GameEngine(seed=seed)
    engine.start_new_game(_configs(seed, players))
    engine._select_haunt_id = lambda room_id, omen_id, _h=haunt_id: _h  # type: ignore[method-assign]

    stats = _Stats()
    original_mode_handler = engine._mode_handler
    proxy = _HandlerProxy(original_mode_handler, stats)
    engine._mode_handler = lambda: proxy  # type: ignore[method-assign]

    original_log = engine._log

    def logged(message: str, category: str = "") -> None:
        stats.log.append(message)
        match = MOVE_RE.match(message)
        if match:
            stats.note_move(match.group(1), match.group(2))
        original_log(message, category)

    engine._log = logged  # type: ignore[method-assign]

    controller: BotController = _IdleController(idle_role) if idle_role else BotController()
    completed = False
    for _ in range(max_turns):
        if engine.state.phase == "GAME_OVER":
            completed = True
            break
        if not controller.take_turn(engine):
            break

    metrics = _move_metrics(stats.moves)
    if engine.state.haunt is not None:
        inner_handler = proxy._inner()
        mode_name = str(getattr(inner_handler, "mode", type(inner_handler).__name__))
    else:
        mode_name = "generic(未进作祟)"
    tracks = {
        str(track_id): {
            "value": int(track.get("value", 0)),
            "target": int(track.get("target", 0)),
        }
        for track_id, track in sorted(engine._haunt_tracks().items())
    }
    heroes_alive = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)
    heroes_total = sum(1 for p in engine.state.players if p.role == "hero")

    warnings: list[str] = []
    if not completed:
        warnings.append("未跑完")
        if engine.state.phase == "EXPLORE":
            warnings.append("探索僵死" if not engine.state.room_deck else "卡在探索")
    if engine.state.turn_count >= long_turns:
        warnings.append(f"回合过长({engine.state.turn_count})")
    idle_actions = sorted(
        action_id for action_id, offered in stats.offered.items() if offered > 0 and action_id not in stats.used
    )
    if idle_actions:
        warnings.append("行动空转:" + ",".join(idle_actions))
    if metrics["max_room_count"] >= osc_threshold:
        warnings.append(f"震荡({metrics['max_room']}×{metrics['max_room_count']})")

    return {
        "haunt": haunt_id,
        "mode": mode_name,
        "seed": seed,
        "players": players,
        "idle": idle_role or "",
        "completed": completed,
        "turns": engine.state.turn_count,
        "phase": engine.state.phase,
        "winner": engine.state.winner or "",
        "winner_reason": engine.state.winner_reason or "",
        "haunt_name": engine.state.haunt.name if engine.state.haunt else "",
        "monsters": len(engine.state.monsters),
        "heroes_alive": heroes_alive,
        "heroes_total": heroes_total,
        "rooms": len(engine.state.board),
        "offered": dict(sorted(stats.offered.items())),
        "used": dict(sorted(stats.used.items())),
        "succeeded": dict(sorted(stats.succeeded.items())),
        "tracks": tracks,
        "flags": _summarize_flags(engine._haunt_flags()),
        **metrics,
        "warnings": warnings,
    }


def _format_case(result: dict) -> str:
    side = {"heroes": "英雄", "traitor": "叛徒"}.get(str(result["winner"]), str(result["winner"]) or "—")
    reason = str(result["winner_reason"])[:28]
    actions = " ".join(f"{aid}×{n}" for aid, n in result["used"].items()) or "—"
    offered_idle = " ".join(
        f"{aid}(出现{result['offered'][aid]}/未用)" for aid in result["offered"] if aid not in result["used"]
    )
    parts = [
        f"seed{result['seed']}/{result['players']}p".ljust(12),
        f"{result['turns']:>3}回合".ljust(7),
        (f"{side}胜" + (f"({reason})" if reason else "")).ljust(30),
        f"行动[{actions}]",
        f"移动{result['moves_total']}/最热{result['max_room_count']}/往返{result['pingpong']}",
        f"怪物{result['monsters']}",
        f"英雄{result['heroes_alive']}/{result['heroes_total']}",
        f"房{result['rooms']}",
    ]
    line = "  ".join(parts)
    if offered_idle:
        line += f"  ⚠ {offered_idle}"
    if result["warnings"]:
        line += "  ⚠ " + ";".join(result["warnings"])
    return line


def _haunt_summary(results: list[dict]) -> str:
    if not results:
        return ""
    haunt = results[0]["haunt"]
    name = results[0]["haunt_name"] or f"#{haunt}"
    mode = results[0]["mode"]
    completed = sum(1 for r in results if r["completed"])
    sides: dict[str, int] = {}
    for r in results:
        if r["winner"]:
            key = str(r["winner"])
        elif r["completed"]:
            # 打完了却没有胜方：全员阵亡（探索期也会触发）没人能赢，如实
            # 单列，别跟"卡住没跑完"混成一个"未完"——那会把正常的终局
            # 读成僵局告警。
            key = "全员阵亡"
        else:
            key = "未完"
        sides[key] = sides.get(key, 0) + 1
    turns = sorted(r["turns"] for r in results)
    median = turns[len(turns) // 2]
    warn_count = sum(1 for r in results if r["warnings"])
    side_text = " ".join(f"{k}×{v}" for k, v in sides.items())
    return (
        f"#{haunt:<3}{name[:14]:<16}{mode[:22]:<24}"
        f"完成{completed}/{len(results)}  胜方[{side_text}]  中位{median}回合  "
        f"警{warn_count}"
    )


def _parse_seeds(text: str) -> list[int]:
    return [int(item) for item in text.replace("，", ",").split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="剧本试玩诊断器")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--haunts", help="剧本号，逗号分隔，如 39 或 1,2,3")
    group.add_argument("--batch", type=int, help="批次号（1 起，一批 5 本）")
    group.add_argument("--all", action="store_true", help="全部 70 本")
    parser.add_argument("--seeds", default=",".join(str(s) for s in DEFAULT_SEEDS))
    parser.add_argument("--players", default=str(DEFAULT_PLAYERS), help="人数，逗号分隔")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--long-turns", type=int, default=DEFAULT_LONG_TURNS)
    parser.add_argument("--osc-threshold", type=int, default=DEFAULT_OSC)
    parser.add_argument("--idle", choices=["traitor", "heroes"], help="指定角色挂机")
    parser.add_argument("--json", dest="json_path", help="把结果写成 JSON 快照")
    parser.add_argument("--compare", help="与既有 JSON 快照对比（隔离回归）")
    parser.add_argument("--allow", default="", help="--compare 时允许变化的剧本号")
    parser.add_argument("--verbose", action="store_true", help="逐局明细")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总与警")
    args = parser.parse_args(argv)

    if args.batch is not None:
        if args.batch < 1 or args.batch > 14:
            parser.error("--batch 取值 1-14")
        haunts = list(range(args.batch * 5 - 4, args.batch * 5 + 1))
    elif args.all:
        haunts = list(range(1, 71))
    else:
        haunts = [int(item) for item in str(args.haunts).replace("，", ",").split(",") if item.strip()]

    seeds = _parse_seeds(args.seeds)
    player_counts = _parse_seeds(args.players)

    results: list[dict] = []
    started = time.time()
    for haunt_id in haunts:
        cases: list[dict] = []
        for players in player_counts:
            for seed in seeds:
                case = run_case(
                    haunt_id,
                    seed,
                    players,
                    max_turns=args.max_turns,
                    idle_role=args.idle,
                    long_turns=args.long_turns,
                    osc_threshold=args.osc_threshold,
                )
                cases.append(case)
                results.append(case)
        print(_haunt_summary(cases))
        if args.verbose:
            for case in cases:
                print("    " + _format_case(case))
        elif not args.quiet:
            for case in cases:
                if case["warnings"]:
                    print("    " + _format_case(case))

    elapsed = time.time() - started
    warned = [r for r in results if r["warnings"]]
    print()
    print(
        f"共 {len(results)} 局，{elapsed:.1f}s；有警 {len(warned)} 局"
        + (f"（{len({r['haunt'] for r in warned})} 本剧本）" if warned else "")
    )

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps({"note": "haunt_playtest 快照，用于跨剧本隔离回归", "cases": results},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"快照已写入：{args.json_path}")

    if args.compare:
        baseline_path = Path(args.compare)
        if not baseline_path.exists():
            print(f"对比基准不存在：{baseline_path}")
            return 2
        baseline = {
            (c["haunt"], c["seed"], c["players"], c.get("idle", "")): c
            for c in json.loads(baseline_path.read_text(encoding="utf-8"))["cases"]
        }
        allow = {int(item) for item in args.allow.replace("，", ",").split(",") if item.strip()}
        fields = ("turns", "winner", "completed", "max_room_count", "pingpong", "monsters")
        diffs = 0
        for case in results:
            key = (case["haunt"], case["seed"], case["players"], case.get("idle", ""))
            old = baseline.get(key)
            if old is None:
                print(f"[新增] 剧本#{case['haunt']} seed{case['seed']}/{case['players']}p")
                continue
            changed = [f for f in fields if old.get(f) != case.get(f)]
            if changed and case["haunt"] not in allow:
                diffs += 1
                detail = ", ".join(f"{f}: {old.get(f)}→{case.get(f)}" for f in changed)
                print(f"[差异] 剧本#{case['haunt']} seed{case['seed']}/{case['players']}p  {detail}")
        if diffs:
            print(f"对比发现 {diffs} 处非允许差异（允许名单：{sorted(allow) or '空'}）。")
            return 1
        print("对比通过：允许名单之外无差异。")

    return 1 if warned else 0


if __name__ == "__main__":
    raise SystemExit(main())
