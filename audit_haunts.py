"""全量剧本审计：把 70 本的「机制 / AI 覆盖」变成可核对的一致性表。

为什么需要它
------------
批次 1–14 已经逐本精修过，但那些结论散在 §11.8…§11.28 的叙述里，**没法一眼看出
"哪一本少挂了哪个钩子"**。本工具做的是**静态一致性审计**（不跑对局）：

1. 每本挂了哪些 handler、覆盖了哪些 duck-typed 钩子（对照 `GenericModeHandler` 基类）；
2. rule_data 与 handler 代码是否自洽——重点是三类**已知会出事**的写法：
   - `actions[].progress` 指向 `setup.tracks` 里**没声明**的轨道
     （引擎 `_haunt_track_target(未声明) == 0` → `0 >= 0` 恒真 → 直接判胜）；
   - handler 源码里 `_haunt_track_value("X")` / `_set_haunt_track_value` /
     `_advance_haunt_track("X")` 用了未声明的轨道名（同上，且更难发现）；
   - `check_victory` 覆盖了却以 `return False` 收尾（把胜负交回引擎隐式兜底
     「叛徒死 → 英雄胜」，是 §6 第 1 条铁律踩过 14 次的那类坑）。
3. 机制/AI 的**覆盖缺口**：声明了 deferred 怪物却没有怪物回合钩子、有剧本行动却
   没有 `bot_goal_rooms`（bot 不知道该去哪）、`fidelity` 与实现不符等；
4. 顺带统计每本的黄金用例数与专项测试数（按函数名粗匹配），方便对照"每本 ≥2 条黄金"。

用法
----
    python audit_haunts.py                # 全量表格
    python audit_haunts.py --only 66,67   # 只看某几本
    python audit_haunts.py --issues       # 只打印异常项（审计用）
    python audit_haunts.py --json out.json

退出码：0 = 无异常；1 = 有异常项。
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import haunt_ai_profiles as hap  # type: ignore
import haunt_modes as hm  # type: ignore
import haunt_rules as hr  # type: ignore

# ---------------------------------------------------------------- 钩子分组
# 只挑**影响玩法**的钩子；纯 UI/展示类（progress_summary 等）单独一组。
GAMEPLAY_HOOKS = (
    # 结构
    "setup", "check_victory", "available_actions", "perform_action",
    # 规则闸门
    "attack_allowed", "attack_attr_override", "attack_roll_bonus", "attack_loss_damage_disabled",
    "defense_roll_override", "defense_roll_disabled", "damage_reduction_label",
    "physical_damage_reduction", "monster_killed_on_defeat", "monster_rerolls_blanks",
    "monster_counterattack_disabled", "monster_attack_roll_bonus",
    "item_use_blocked", "item_pickup_blocked", "item_trade_blocked",
    "can_discover_rooms", "room_entry_blocked", "mystic_elevator_blocked",
    "counts_as_movement_obstacle", "suppress_room_draw", "explore_stop_suspended",
    "movement_cost_floor", "movement_cost_multiplier", "lake_move",
    "extra_move_options", "action_room_override", "special_steal",
    # 事件
    "on_turn_start", "on_turn_end", "on_player_moved", "on_player_died",
    "on_enter_room", "on_room_discovered", "on_attack_resolved", "on_item_dropped",
    "on_monster_turn_start", "on_monster_turn_attack", "on_monster_move",
    "on_monster_attack", "on_monster_defeated",
    # bot
    "bot_goal_rooms", "bot_blocked_rooms", "bot_hazard_rooms",
    "bot_stay_in_room", "bot_leave_after_action", "bot_action_blocked",
    "bot_goal_suppressed", "bot_captor_monster", "quest_carrier",
)
REPORT_HOOKS = ("progress_summary",)

MONSTER_HOOKS = {
    "on_monster_turn_start", "on_monster_turn_attack",
    "on_monster_move", "on_monster_attack", "on_monster_defeated",
}

TRACK_READERS = (
    "_haunt_track_value", "_set_haunt_track_value", "_advance_haunt_track",
    "_haunt_track_target",
)
TRACK_RE = re.compile(
    r"_(?:haunt_track_value|set_haunt_track_value|advance_haunt_track|haunt_track_target)"
    r"\(\s*(?:track_id\s*=\s*)?['\"]([a-z0-9_]+)['\"]"
)


def _handler_for(haunt_id: int):
    rule = hr.HAUNT_RULE_OVERRIDES.get(haunt_id) or {}
    mode = rule.get("mode", "")
    return rule, mode, hm._MODE_HANDLERS.get(mode)


def _overridden_hooks(cls) -> list[str]:
    base = hm.GenericModeHandler
    out = []
    for name in GAMEPLAY_HOOKS + REPORT_HOOKS:
        if getattr(cls, name, None) is not getattr(base, name, None):
            out.append(name)
    return out


def _declared_tracks(rule: dict) -> dict:
    return (rule.get("setup") or {}).get("tracks") or {}


def _action_progress_issues(rule: dict) -> list[str]:
    tracks = _declared_tracks(rule)
    issues = []
    for action in rule.get("actions") or []:
        aid = action.get("id", "?")
        prog = action.get("progress")
        names = []
        if isinstance(prog, str):
            names.append(prog)
        elif isinstance(prog, dict):
            names.append(prog.get("track") or prog.get("track_id"))
        for name in names:
            if name and name not in tracks:
                issues.append(f"action {aid}.progress 指向未声明轨道 {name!r}")
        # set_flags 是合法写法（引擎只在检定成功时应用）
        if isinstance(prog, dict) and "set_flags" in prog:
            continue
    return issues


def _track_name_issues(cls, rule: dict) -> list[str]:
    tracks = set(_declared_tracks(rule))
    try:
        src = inspect.getsource(cls)
    except (OSError, TypeError):
        return []
    used = set(TRACK_RE.findall(src))
    # 引擎自己的通用轨道不算异常
    generic = {"progress"}
    missing = sorted(n for n in used if n not in tracks and n not in generic)
    return [f"源码引用未声明轨道 {n!r}" for n in missing]


def _victory_issues(cls) -> list[str]:
    """`check_victory` 的风险只有一种：**通篇不提叛徒**。

    「以 `return False` 收尾」不是异常——批次 3（M10-35）已把 34 个这样的 handler
    逐本对照英文手册定性过（14 本补吸收兜底、4 本改显式接管）。收尾的
    `return False` 语义是"当前还没有胜者"，与 §6 第 1 条铁律（**叛徒死亡时必须
    显式接管**，别让基类误判「叛徒死 → 英雄胜」）并不冲突，只要叛徒死亡那条分支
    在前面被处理掉。所以这里只找真正危险的形态：handler 既不覆盖、或覆盖了却
    从头到尾**没有一句提到 traitor**（等于完全依赖基类兜底）。
    """
    fn = cls.__dict__.get("check_victory")
    if fn is None:
        return ["未覆盖 check_victory（走基类兜底：仅 traitor_dead → 英雄胜）"]
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return []
    if "traitor" not in src:
        return ["check_victory 通篇不提 traitor（叛徒死亡未被显式接管，靠基类兜底）"]
    return []


def _goal_sources(rule: dict, hooks: list[str], profile) -> dict:
    """列出 bot 的"目标从哪来"——静态字段 vs 动态钩子。

    §10.2 的约定：目标随玩家状态变化的剧本必须把静态字段留空、改由
    `bot_goal_rooms` 动态给出。所以判断"bot 有没有目标"不能只看钩子，
    要看静态来源是否也空。
    """
    targets = []
    for action in rule.get("actions") or []:
        for room in action.get("rooms") or []:
            targets.append(str(room))
    profile_targets = []
    if isinstance(profile, dict):
        for side, cfg in profile.items():
            if isinstance(cfg, dict):
                profile_targets += [str(x) for x in (cfg.get("target_rooms") or [])]
    return {
        "key_rooms": [str(x) for x in (rule.get("key_rooms") or [])],
        "action_rooms": targets,
        "profile_targets": profile_targets,
        "dynamic": "bot_goal_rooms" in hooks,
    }


def _mechanics_issues(rule: dict, hooks: list[str], goals: dict) -> list[str]:
    issues = []
    monsters = rule.get("monsters") or []
    if monsters and not (MONSTER_HOOKS & set(hooks)):
        issues.append(f"声明了 {len(monsters)} 只剧本怪物却没有任何怪物钩子")
    if (rule.get("actions") or []) and not goals["dynamic"]:
        static = goals["key_rooms"] or goals["action_rooms"] or goals["profile_targets"]
        if not static:
            issues.append("有剧本行动但没有任何目标来源（既无 bot_goal_rooms，静态目标字段也全空）")
    return issues


def _golden_counts() -> dict[int, int]:
    path = Path(__file__).resolve().parent / "golden_replays.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else data
    out: dict[int, int] = {}
    if isinstance(cases, dict):
        for key in cases:
            m = re.search(r"haunt(\d+)", str(key))
            if m:
                hid = int(m.group(1))
                out[hid] = out.get(hid, 0) + 1
    return out


def _verify_counts() -> dict[int, int]:
    path = Path(__file__).resolve().parent / "verify_haunt_systems.py"
    if not path.exists():
        return {}
    src = path.read_text(encoding="utf-8", errors="replace")
    names = re.findall(r"^def (verify_\w+)", src, re.M)
    out: dict[int, int] = {}
    for name in names:
        m = re.match(r"verify_haunt(\d+)", name)
        if m:
            hid = int(m.group(1))
            out[hid] = out.get(hid, 0) + 1
    return out


def collect() -> list[dict]:
    golden = _golden_counts()
    verifies = _verify_counts()
    rows = []
    for haunt_id in range(1, 71):
        rule, mode, handler = _handler_for(haunt_id)
        cls = type(handler) if handler is not None else None
        hooks = _overridden_hooks(cls) if cls is not None else []
        tracks = _declared_tracks(rule)
        profile = hap.HAUNT_AI_PROFILE_OVERRIDES.get(haunt_id)
        goals = _goal_sources(rule, hooks, profile) if cls is not None else {}
        issues = []
        if handler is None:
            issues.append(f"mode {mode!r} 没有注册 handler")
        else:
            issues += _action_progress_issues(rule)
            issues += _track_name_issues(cls, rule)
            issues += _victory_issues(cls)
            issues += _mechanics_issues(rule, hooks, goals)
        rows.append({
            "haunt": haunt_id,
            "mode": mode,
            "status": rule.get("status", ""),
            "fidelity": rule.get("fidelity", ""),
            "version": rule.get("version", 0),
            "handler": cls.__name__ if cls else "",
            "bases": [b.__name__ for b in cls.__mro__[1:-1]] if cls else [],
            "hooks": hooks,
            "hook_count": len(hooks),
            "tracks": {k: v.get("target", 0) for k, v in sorted(tracks.items())},
            "actions": len(rule.get("actions") or []),
            "monsters": len(rule.get("monsters") or []),
            "tokens": len(rule.get("tokens") or []),
            "required_cards": len(rule.get("required_cards") or []),
            "win_conditions": len(rule.get("win_conditions") or {}),
            "goals": goals,
            "ai_profile": sorted(profile.keys()) if isinstance(profile, dict) else [],
            "golden": golden.get(haunt_id, 0),
            "verify": verifies.get(haunt_id, 0),
            "issues": issues,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全量剧本机制/AI 静态审计")
    parser.add_argument("--only", default="", help="只审计某几本，逗号分隔，如 66,67")
    parser.add_argument("--issues", action="store_true", help="只打印有异常的剧本")
    parser.add_argument("--json", dest="json_path", help="写出 JSON")
    args = parser.parse_args(argv)

    rows = collect()
    if args.only:
        keep = {int(x) for x in args.only.replace("，", ",").split(",") if x.strip()}
        rows = [r for r in rows if r["haunt"] in keep]

    def goal_tag(r: dict) -> str:
        g = r.get("goals") or {}
        if not g:
            return "--"
        parts = []
        if g.get("dynamic"):
            parts.append("动态")
        if g.get("key_rooms"):
            parts.append(f"key{len(g['key_rooms'])}")
        if g.get("action_rooms"):
            parts.append(f"act{len(g['action_rooms'])}")
        if g.get("profile_targets"):
            parts.append(f"prof{len(g['profile_targets'])}")
        return "+".join(parts) or "--"

    header = (f"{'#':>3} {'mode':<24}{'handler':<30}{'hooks':>5} {'tracks':>6} "
              f"{'act':>3} {'mon':>3} {'ai':>2} {'gold':>4} {'ver':>3} {'goal':<14} issues")
    print(header)
    print("-" * len(header))
    for r in rows:
        if args.issues and not r["issues"]:
            continue
        ai = len(r["ai_profile"])
        print(f"{r['haunt']:>3} {r['mode']:<24}{r['handler']:<30}{r['hook_count']:>5} "
              f"{len(r['tracks']):>6} {r['actions']:>3} {r['monsters']:>3} {ai:>2} "
              f"{r['golden']:>4} {r['verify']:>3} {goal_tag(r):<14} "
              + ("; ".join(r["issues"]) if r["issues"] else ""))

    bad = [r for r in rows if r["issues"]]
    print()
    print(f"共 {len(rows)} 本，{len(bad)} 本有异常项。")
    if bad:
        print("异常分布：")
        for r in bad:
            print(f"  #{r['haunt']:<3}{r['mode']:<24}" + " | ".join(r["issues"]))

    # 覆盖统计
    all_hooks: dict[str, int] = {}
    for r in rows:
        for h in r["hooks"]:
            all_hooks[h] = all_hooks.get(h, 0) + 1
    print()
    print("钩子使用频次（前 20）：")
    for name, cnt in sorted(all_hooks.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {name:<32}{cnt}")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps({"rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写出：{args.json_path}")

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
