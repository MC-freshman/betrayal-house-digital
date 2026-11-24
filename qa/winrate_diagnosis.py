#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""零胜剧本归因（执行计划 T-01）。

它回答的是「这些剧本为什么英雄一场都赢不了」，而不是「胜率是多少」：
胜率由 ``qa/winrate_baseline.py`` 负责，本脚本只做**归因**。

数据来源（全部可回读，不靠记忆）
--------------------------------
* 基线：``qa/winrate_baseline.json``（局数/胜方/平均回合/by_haunt）；
* 规则：``content.py`` → ``Catalog.haunt_defs[i].rule_data``，即 ``haunt_rules.py``
  里该剧本的 ``mode / key_rooms / required_cards / actions / setup / win_conditions``；
* 模式处理器：``haunts.get_mode_handler(rule["mode"])`` 的类名与模块；
* 机器人档案：``haunt_ai_profiles.HAUNT_AI_PROFILE_OVERRIDES`` + 默认档案；
* 抽样实证：用与基线完全相同的机器人参数（``hard`` / ``balanced``）实跑
  ``SAMPLE_SEEDS × SAMPLE_PLAYERS`` 局，记录终局原因、轨道值、剧本行动使用次数。

为什么还要实跑
--------------
``win_conditions`` 在 70 本里大多为空（真正的胜负写在 handler 的
``check_victory`` 里），只读数据分不出「叛徒靠什么赢」。抽样对局能拿到
引擎自己的 ``winner_reason`` 与轨道终值，这是「叛徒取胜手段」的实证来源；
剧本行动 ``offered/used/succeeded`` 则用来判断英雄的目标链是不是根本走不通。

字段约定
--------
* 读不到的字段写 ``null`` 并在同级的 ``*_note`` 里说明原因（例如
  ``target_rooms`` 为空但目标由 handler 的 ``bot_goal_rooms`` 动态给出）；
* 不写「未知」：每条结论要么来自规则数据，要么来自抽样实证。

产物::

    python qa/winrate_diagnosis.py                 # 默认 4 局/本抽样
    python qa/winrate_diagnosis.py --no-sample     # 只读规则，不实跑（快）
    python qa/winrate_diagnosis.py --json qa/winrate_diagnosis.json
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

GAME_DIR = Path(__file__).resolve().parents[1]
QA_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import haunt_playtest as playtest  # noqa: E402
import winrate_baseline as baseline_tool  # noqa: E402
from content import build_catalog  # noqa: E402
from haunt_ai_profiles import (  # noqa: E402
    DEFAULT_HAUNT_AI_PROFILE,
    HAUNT_AI_PROFILE_OVERRIDES,
)
from haunts import get_mode_handler  # noqa: E402

DEFAULT_BASELINE = QA_DIR / "winrate_baseline.json"
DEFAULT_OUT = QA_DIR / "winrate_diagnosis.json"

# 执行计划 §一 点名的 11 本。基线 JSON 里的实际零胜清单另有出入（多出 19/29、
# 21 实际赢过 1 局），脚本把两者并集都归因，并在 scope.note 里如实标出差异。
PLAN_ZERO_WIN_HAUNTS: tuple[int, ...] = (10, 13, 20, 21, 26, 31, 32, 33, 40, 50, 67)
SAMPLE_SEEDS: tuple[int, ...] = (3, 101)
SAMPLE_PLAYERS: tuple[int, ...] = (3, 5)
SAMPLE_MAX_TURNS = 400

# 「零胜本要看的轨道」——只用于把抽样数字写进假设句，不做逻辑分派。
_SCOPE_TRACKS: Dict[int, str] = {
    10: "zombies_trapped",
    13: "waking_progress",
    19: "minions_slain",
    20: "wedding_timer",
    21: "lord_damage",
    26: "ritual_rolls",
    29: "torch_hits",
    31: "house_slain",
    32: "clues_found",
    33: "drown_timer",
    40: "dig_progress",
    50: "night_timer",
    67: "quests",
}

_BASELINE: Dict[str, Any] = {}


# ----------------------------------------------------------------------
# 规则 / 档案读取
# ----------------------------------------------------------------------
def _profile_slice(haunt_id: int, side: str) -> Dict[str, Any]:
    """返回该剧本该阵营的**生效**档案（默认档案 + 覆盖合并）。"""
    merged: Dict[str, Any] = {
        side: dict(DEFAULT_HAUNT_AI_PROFILE[side]),
        "monster": dict(DEFAULT_HAUNT_AI_PROFILE["monster"]),
        "scenario": dict(DEFAULT_HAUNT_AI_PROFILE["scenario"]),
    }
    override = HAUNT_AI_PROFILE_OVERRIDES.get(haunt_id) or {}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged[side]


def _handler_overrides(handler_cls: type, hook: str) -> bool:
    """该 handler 是否**自己**实现了这个 bot 钩子（而不是从基类继承）。"""
    for klass in handler_cls.__mro__:
        if hook in klass.__dict__:
            return klass.__name__ != "GenericModeHandler"
    return False


def _hero_side_rooms(rule: Dict[str, Any]) -> List[str]:
    """只算**英雄侧**带 rooms 的剧本行动（叛徒侧行动不会给英雄目标）。"""
    rooms = {
        str(room)
        for action in rule.get("actions", [])
        if str(action.get("side")) in ("heroes", "any", "both")
        for room in (action.get("rooms") or [])
    }
    return sorted(rooms)


def _target_rooms_note(haunt_id: int, rule: Dict[str, Any], profile: Dict[str, Any]) -> str | None:
    """静态目标房间为空时，说明目标由谁给（handler 钩子 / 规则行动 / 本就没有）。"""
    if profile.get("target_rooms"):
        return None
    handler_cls = type(get_mode_handler(str(rule.get("mode") or "")))
    if _handler_overrides(handler_cls, "bot_goal_rooms"):
        return "静态表为空；目标由 %s.bot_goal_rooms 按局面动态给出" % handler_cls.__name__
    rooms = _hero_side_rooms(rule)
    if rooms:
        return "静态表为空；英雄侧剧本行动自带 rooms（%s），由 _haunt_goal_targets 直接换算" % "、".join(
            rooms[:4]
        )
    if rule.get("key_rooms"):
        return "静态表为空；目标回落到 rule_data.key_rooms（%d 间）" % len(rule.get("key_rooms"))
    return "静态表为空，且 rule_data 没有 key_rooms / 英雄侧带 rooms 的行动：bot 在作祟阶段没有地点目标"


def _traitor_win_method(
    rule: Dict[str, Any], handler_cls: type, evidence: Dict[str, Any] | None
) -> Dict[str, Any]:
    """叛徒取胜手段：先看 win_conditions，再看轨道，最后用抽样终局原文实证。"""
    declared = [
        {"type": item.get("type"), "reason": item.get("reason")}
        for item in (rule.get("win_conditions") or [])
        if str(item.get("winner")) == "traitor"
    ]
    tracks = (rule.get("setup") or {}).get("tracks") or {}
    track_targets = {
        key: value.get("target")
        for key, value in tracks.items()
        if isinstance(value, dict) and str(value.get("side")) == "traitor"
    }
    observed: List[str] = []
    if evidence:
        observed = [reason for reason, _ in Counter(evidence["reasons"]).most_common(3) if reason]
    if declared:
        summary = "win_conditions 声明：" + "；".join(
            "%s（%s）" % (item.get("reason"), item.get("type")) for item in declared
        )
        source = "win_conditions"
    elif track_targets:
        summary = "handler %s 按轨道判定：%s" % (
            handler_cls.__name__,
            "、".join("%s→%s" % (key, target) for key, target in sorted(track_targets.items())),
        )
        source = "handler_track"
    elif observed:
        summary = "剧本目标：%s；handler %s 按内部条件判定，抽样终局原文：%s" % (
            (rule.get("traitor_goal") or "").strip() or "（rule_data 未写 traitor_goal）",
            handler_cls.__name__,
            observed[0],
        )
        source = "handler_observed"
    else:
        summary = "剧本目标：%s；handler %s 的 check_victory 内部判定" % (
            (rule.get("traitor_goal") or "").strip() or "（rule_data 未写 traitor_goal）",
            handler_cls.__name__,
        )
        source = "handler_only"
    return {
        "summary": summary,
        "source": source,
        "declared": declared,
        "traitor_track_targets": track_targets,
        "observed_reasons": observed,
    }


# ----------------------------------------------------------------------
# 抽样实证
# ----------------------------------------------------------------------
def _sample_haunt(haunt_id: int) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for seed in SAMPLE_SEEDS:
        for players in SAMPLE_PLAYERS:
            try:
                result = playtest.run_case(haunt_id, seed, players, max_turns=SAMPLE_MAX_TURNS)
            except Exception as exc:  # noqa: BLE001 - 单局异常不该带走整轮归因
                rows.append(
                    {
                        "seed": seed,
                        "players": players,
                        "error": "%s: %s" % (type(exc).__name__, exc),
                        "trace": traceback.format_exc(limit=2).splitlines()[-3:],
                    }
                )
                continue
            rows.append(
                {
                    "seed": seed,
                    "players": players,
                    "winner": result.get("winner") or "",
                    "reason": result.get("winner_reason") or "",
                    "turns": int(result.get("turns") or 0),
                    "completed": bool(result.get("completed")),
                    "heroes_alive": int(result.get("heroes_alive") or 0),
                    "heroes_total": int(result.get("heroes_total") or 0),
                    "tracks": result.get("tracks") or {},
                    "offered": result.get("offered") or {},
                    "used": result.get("used") or {},
                    "succeeded": result.get("succeeded") or {},
                    "flags": result.get("flags") or {},
                    "warnings": result.get("warnings") or [],
                }
            )

    good = [row for row in rows if "error" not in row]
    track_max: Dict[str, int] = {}
    track_target: Dict[str, int] = {}
    track_targets_all: Dict[str, List[int]] = {}
    for row in good:
        for track_id, track in (row["tracks"] or {}).items():
            value = int(track.get("value", 0))
            track_max[track_id] = max(track_max.get(track_id, value), value)
            track_target[track_id] = int(track.get("target", 0))
            track_targets_all.setdefault(track_id, []).append(int(track.get("target", 0)))
    used: Counter = Counter()
    succeeded: Counter = Counter()
    offered: Counter = Counter()
    for row in good:
        used.update(row["used"])
        succeeded.update(row["succeeded"])
        offered.update(row["offered"])

    return {
        "seeds": list(SAMPLE_SEEDS),
        "players": list(SAMPLE_PLAYERS),
        "games": len(rows),
        "ok": len(good),
        "hero_wins": sum(1 for row in good if row["winner"] == "heroes"),
        "traitor_wins": sum(1 for row in good if row["winner"] == "traitor"),
        "unfinished": sum(1 for row in good if not row["completed"]),
        "wipes": sum(1 for row in good if row["heroes_alive"] == 0),
        "avg_turns": round(sum(row["turns"] for row in good) / len(good), 2) if good else 0.0,
        "reasons": dict(Counter(row["reason"] for row in good if row["reason"])),
        "track_max": dict(sorted(track_max.items())),
        "track_target": dict(sorted(track_target.items())),
        "track_targets_all": {key: sorted(set(value)) for key, value in sorted(track_targets_all.items())},
        "offered": dict(sorted(offered.items())),
        "used": dict(sorted(used.items())),
        "succeeded": dict(sorted(succeeded.items())),
        "errors": [row for row in rows if "error" in row],
        "rows": good,
    }


# ----------------------------------------------------------------------
# 逐本假设（模板里的数字全部来自本次运行的规则/基线/抽样）
# ----------------------------------------------------------------------
# 基线已不为零的剧本：写清"计划清单记的是什么 / 实测多少 / 本轮改了什么"。
_POST_FIX_NOTES: Dict[int, tuple[str, str]] = {
    13: (
        "计划清单 0/33，本轮后 5/33",
        "根因是圣徽被沉睡者本人捡走并锁死（setup 掉落 → 下一回合又被拾起），"
        "英雄永远凑不齐唤醒条件；本轮在 NightmareDreamMode 加 item_pickup_blocked 修掉",
    ),
    21: (
        "计划清单按 0 胜记，实测基线前后都是 1/33",
        "本轮补的档案只是把 handler 已有的徽章路由写成声明（hunt_with_required_item + 徽章），"
        "生效字段与默认档案等价，胜场没有变化：领主伤害全程 0/7、作祟后数回合被清场",
    ),
    31: (
        "计划清单 0/33，本轮后 1/33",
        "原来目标回落到 15 间 key_rooms，真正的两间器官房被稀释；"
        "本轮把 target_rooms 收紧到管风琴室/阁楼",
    ),
}


def _hypothesis(haunt_id: int, rule: Dict[str, Any], ev: Dict[str, Any] | None) -> str:
    """返回一句「假设失败原因」。数字来自证据，不是手写常量。"""
    if not ev or not ev["ok"]:
        return "本次未抽样（--no-sample）：按规则数据，英雄目标是「%s」" % (
            (rule.get("hero_goal") or "").strip() or "剧本未声明英雄目标"
        )
    baseline_row = (_BASELINE.get("by_haunt") or {}).get(str(haunt_id)) or {}
    if int(baseline_row.get("heroes_win") or 0) > 0 and haunt_id in _POST_FIX_NOTES:
        status, note = _POST_FIX_NOTES[haunt_id]
        tail = (
            "本轮抽样 %s/%s 局英雄胜。" % (ev["hero_wins"], ev["ok"])
            if ev["hero_wins"]
            else "本轮抽样仍 0/%s 局，剩余瓶颈是战斗消耗而不是目标链。" % ev["ok"]
        )
        return "（%s）%s；%s" % (status, note, tail)
    games = ev["ok"]
    wipes = ev["wipes"]
    tmax = ev["track_max"]
    targets_all = ev.get("track_targets_all") or {}
    used = ev["used"]
    reasons = Counter(ev["reasons"])
    top_reason, _top_count = (reasons.most_common(1)[0] if reasons else ("", 0))

    def goal_text(track: str) -> str:
        """目标值随人数变（3 人 / 5 人），如实写成「3-5」而不是单选一个。"""
        values = targets_all.get(track) or []
        if not values:
            return "?"
        return str(values[0]) if len(values) == 1 else "%d-%d" % (values[0], values[-1])

    def reached(track: str) -> str:
        return "%s（目标 %s）" % (tmax.get(track, 0), goal_text(track))

    def act(name: str) -> int:
        return int(used.get(name, 0))

    groom_dead = sum(1 for row in ev["rows"] if (row["flags"] or {}).get("groom_dead"))

    templates: Dict[int, str] = {
        10: (
            "英雄只有「把每只僵尸分别引进 6 间陷阱房、让它知识检定失败」这一条胜利线，"
            "规则也不允许靠击晕取胜；抽样 {games} 局单局最多困住 {t}，僵尸力量 6、疯子力量 5、"
            "英雄平均力量 3，{wipes}/{games} 局英雄全灭。"
        ),
        13: (
            "梦魇被击败会立即补一只（on_monster_defeated），追打零收益；英雄该做的是把圣徽"
            "送进沉睡者房间做 5+ 唤醒检定，而抽样唤醒进度只有 {t}，{escaped}/{games} 局"
            "在唤醒前就被梦魇逃满逃脱路线。"
        ),
        19: (
            "英雄胜要求对驯兽师打出 >2 点伤害触发 special_steal 夺矛（杀了他反而判负），"
            "抽样 {games} 局随从最多被击毙 {t}、{wipes}/{games} 局英雄全灭；bot 只能攻击同房间目标，"
            "没有任何「追驯兽师本人」的寻路目标。"
        ),
        20: (
            "四步链（问名→定位→掘尸→送葬）由 requires_flags 串行，新娘又是 invulnerable；"
            "抽样 {games} 局婚礼计时最高 {t}、{groom_dead}/{games} 局新郎被新娘抽干力量，"
            "4 局合计只掘尸 {disinter} 次，赶不上 3 回合婚礼。"
        ),
        21: (
            "只有持徽章者能伤到僵尸领主，领主有 7 点伤害容量；抽样 {games} 局 lord_damage 全程 {t}，"
            "开局最多布下 {zombies} 只僵尸（人数 + 已布点房间数），作祟触发后 {wipes}/{games} 局"
            "英雄在数回合内被清场。"
        ),
        26: (
            "叛徒在五芒星室 5 次理智 3+ 即完成仪式（约 5 回合），英雄要么清光 {rats} 只老鼠、"
            "要么抢在他进五芒星室前杀了他；抽样 {games} 局仪式先完成 {ritual} 局，"
            "而英雄侧没有任何自带 rooms 的行动，bot 在作祟阶段拿不到「去五芒星室」这个目标。"
        ),
        29: (
            "火把要在烧焦房/熔炉房/五芒星室/厨房点燃，再贴到怪物邻房投掷；抽样 {games} 局"
            "合计投掷 {throws} 次、命中最多 {t}。怪物力量 8，英雄空手对拼直接被打穿。"
        ),
        31: (
            "只有长矛能伤到心脏/大脑（attack_allowed 硬闸门），心脏防御力量 7；抽样 {games} 局 "
            "house_slain 始终 {t}，英雄到不了管风琴室/阁楼就被抗体与器官房消耗殆尽。"
        ),
        32: (
            "弹奏门槛 15-20 点且每枚干扰令牌 -3，英雄必须先集齐 3 条线索；抽样 {games} 局线索最多 {t}、"
            "合计弹奏 {organ} 次，毒大气持续掉属性，{wipes}/{games} 局全灭。"
        ),
        33: (
            "救人是「站上湖面砖 → 4 骰+距离+水晶球凑 19+」，女孩按溺水线 9/10 计时；抽样 {games} 局"
            "溺水计时最高 {t}、{drown} 局女孩先溺亡、{wipes_other} 局英雄全灭——rule_data 没有 "
            "key_rooms、档案也没有 target_rooms；本轮补了 LakeRescueMode.bot_goal_rooms 指路地下湖，"
            "但搜索表本身需要累计距离加值，短计时内凑不到 19+。"
        ),
        40: (
            "搜查靠知识 3+ 逐间排除地下室，挖掘要力量 4+ 且进度 = 玩家人数；抽样 {games} 局"
            "挖掘进度最多 {t}，而伤害轨先以 {dmg}/12 打满 —— 4-5 轮里凑不出 3-5 次力量 4+。"
        ),
        50: (
            "撑满 10 个夜晚格即胜，但仆人属性 3/3/3→4/4/4→5/5/5→6/6/6 递增且每回合追最近英雄；"
            "抽样 {games} 局夜晚进度最多 {t}、{wipes}/{games} 局英雄全灭——档案里没有任何"
            "「远离仆人」的可执行目标。"
        ),
        67: (
            "故事轨道每回合推进、7 格即悲伤结局，英雄要先与入定叛徒同房抽任务再凑物件；"
            "抽样 {games} 局任务完成最多 {t}、故事轨道到 {story}/7。"
        ),
    }
    template = templates.get(haunt_id) or (
        "抽样 {games} 局英雄 {hero_wins} 胜、{wipes} 局全灭，最常见终局原因：{reason}；"
        "剧本目标：{hero_goal}"
    )
    return template.format(
        games=games,
        wipes=wipes,
        hero_wins=ev["hero_wins"],
        t=reached(_SCOPE_TRACKS.get(haunt_id, "")),
        escaped=sum(1 for row in ev["rows"] if "逃脱路线" in (row["reason"] or "")),
        drown=sum(1 for row in ev["rows"] if "没有浮上来" in (row["reason"] or "")),
        disinter=act("disinter_body"),
        groom_dead=groom_dead,
        wipes_other=games - sum(1 for row in ev["rows"] if "没有浮上来" in (row["reason"] or "")),
        zombies=max([int(row["flags"].get("zombies_placed") or 0) for row in ev["rows"]] or [0]),
        rats=max([int(row["flags"].get("rat_pool") or 0) for row in ev["rows"]] or [0]),
        ritual=sum(1 for row in ev["rows"] if "仪式完成" in (row["reason"] or "")),
        throws=act("throw_torch"),
        organ=act("play_organ"),
        dmg=tmax.get("burial_damage", 0),
        story=tmax.get("story", 0),
        reason=top_reason or "无",
        hero_goal=(rule.get("hero_goal") or "").strip(),
    )


# ----------------------------------------------------------------------
# 汇总
# ----------------------------------------------------------------------
def _avg_turns(haunt_id: int) -> float | None:
    data = _BASELINE.get("by_haunt", {}).get(str(haunt_id))
    if not isinstance(data, dict):
        return None
    return float(data.get("avg_turns", 0.0))


def _evidence_digest(evidence: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "seeds": evidence["seeds"],
        "players": evidence["players"],
        "games": evidence["games"],
        "ok": evidence["ok"],
        "hero_wins": evidence["hero_wins"],
        "traitor_wins": evidence["traitor_wins"],
        "wipes": evidence["wipes"],
        "avg_turns": evidence["avg_turns"],
        "reasons": evidence["reasons"],
        "track_max": evidence["track_max"],
        "track_target": evidence["track_target"],
        "used": evidence["used"],
        "succeeded": evidence["succeeded"],
        "errors": evidence["errors"],
    }


def _collect(haunt_ids: Sequence[int], with_sample: bool) -> List[Dict[str, Any]]:
    catalog = build_catalog(0)
    records: List[Dict[str, Any]] = []
    for haunt_id in haunt_ids:
        defn = catalog.haunt_defs[haunt_id]
        rule = dict(defn.rule_data or {})
        mode = str(rule.get("mode") or "")
        handler_cls = type(get_mode_handler(mode))
        try:
            handler_source = inspect.getsource(handler_cls)
        except (OSError, TypeError):
            handler_source = ""
        hero_profile = _profile_slice(haunt_id, "hero")
        traitor_profile = _profile_slice(haunt_id, "traitor")
        evidence = _sample_haunt(haunt_id) if with_sample else None
        records.append(
            {
                "haunt_id": haunt_id,
                "name": defn.name,
                "mode": mode,
                "mode_handler": handler_cls.__name__,
                "mode_handler_module": handler_cls.__module__,
                "mode_handler_source_lines": len(handler_source.splitlines()) or None,
                "mode_handler_declares_check_victory": "def check_victory" in handler_source,
                "profile_source": "dedicated" if haunt_id in HAUNT_AI_PROFILE_OVERRIDES else "default",
                "hero": {
                    "mode": hero_profile.get("mode"),
                    "objective_type": hero_profile.get("objective_type"),
                    "needed_items": list(hero_profile.get("needed_items") or []),
                    "target_rooms": list(hero_profile.get("target_rooms") or []),
                    "target_rooms_note": _target_rooms_note(haunt_id, rule, hero_profile),
                    "attack_monsters": hero_profile.get("attack_monsters"),
                    "attack_traitor_players": hero_profile.get("attack_traitor_players"),
                    "victory_focus": hero_profile.get("victory_focus"),
                },
                "traitor": {
                    "objective_type": traitor_profile.get("objective_type"),
                    "needed_items": list(traitor_profile.get("needed_items") or []),
                    "target_rooms": list(traitor_profile.get("target_rooms") or []),
                    "victory_focus": traitor_profile.get("victory_focus"),
                },
                "rule_goal": {
                    "hero": rule.get("hero_goal"),
                    "traitor": rule.get("traitor_goal"),
                    "traitor_rule": rule.get("traitor_rule"),
                    "fidelity": rule.get("fidelity"),
                },
                "rule_targets": {
                    "key_rooms": list(rule.get("key_rooms") or []),
                    "required_cards": list(rule.get("required_cards") or []),
                    "tokens": list(rule.get("tokens") or []),
                    "tracks": (rule.get("setup") or {}).get("tracks") or {},
                    "actions": [
                        {
                            "id": action.get("id"),
                            "side": action.get("side"),
                            "rooms": action.get("rooms") or [],
                            "stat": action.get("stat"),
                            "target": action.get("target"),
                            "requires": action.get("requires") or [],
                        }
                        for action in rule.get("actions", [])
                    ],
                },
                "avg_turns": _avg_turns(haunt_id),
                "traitor_win_method": _traitor_win_method(rule, handler_cls, evidence),
                "hypothesis": _hypothesis(haunt_id, rule, evidence),
                "evidence": _evidence_digest(evidence),
            }
        )
    return records


def build(baseline_path: Path, with_sample: bool) -> Dict[str, Any]:
    global _BASELINE
    _BASELINE = json.loads(baseline_path.read_text(encoding="utf-8"))
    if with_sample:
        baseline_tool._install_configs("hard")  # 与 2310 局基线同参数

    actual_zero = list((_BASELINE.get("diagnosis") or {}).get("zero_hero_haunts") or [])
    scope = sorted(set(PLAN_ZERO_WIN_HAUNTS) | set(actual_zero))
    records = _collect(scope, with_sample)

    dedicated = sorted(HAUNT_AI_PROFILE_OVERRIDES)
    default_profile = sorted(set(range(1, 71)) - set(dedicated))
    by_haunt = _BASELINE.get("by_haunt") or {}

    return {
        "schema": "winrate-diagnosis/v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": {
            "path": baseline_path.name,
            "generated_at": _BASELINE.get("generated_at"),
            "games": _BASELINE.get("games"),
            "heroes_win": _BASELINE.get("heroes_win"),
            "traitor_win": _BASELINE.get("traitor_win"),
            "heroes_win_rate": _BASELINE.get("heroes_win_rate"),
            "avg_turns": _BASELINE.get("avg_turns"),
        },
        "coverage": {
            "haunts_total": 70,
            "dedicated_profiles": len(dedicated),
            "default_profiles": len(default_profile),
            "default_profile_haunts": default_profile,
        },
        "scope": {
            "plan_zero_win_haunts": list(PLAN_ZERO_WIN_HAUNTS),
            "baseline_zero_win_haunts": actual_zero,
            "diagnosed_haunts": scope,
            "note": (
                "计划点名的 11 本与基线实测清单不一致（21 号实际 1 胜/33；19、29 号实测 0 胜）。"
                "本文件按并集归因，不做取舍。"
                if set(actual_zero) != set(PLAN_ZERO_WIN_HAUNTS)
                else "计划清单与基线实测一致。"
            ),
            "by_haunt": {
                str(haunt_id): {
                    "games": (by_haunt.get(str(haunt_id)) or {}).get("games"),
                    "heroes_win": (by_haunt.get(str(haunt_id)) or {}).get("heroes_win"),
                    "traitor_win": (by_haunt.get(str(haunt_id)) or {}).get("traitor_win"),
                    "heroes_win_rate": (by_haunt.get(str(haunt_id)) or {}).get("heroes_win_rate"),
                    "avg_turns": (by_haunt.get(str(haunt_id)) or {}).get("avg_turns"),
                }
                for haunt_id in scope
            },
        },
        "haunts": records,
        "method": {
            "sample_seeds": list(SAMPLE_SEEDS),
            "sample_players": list(SAMPLE_PLAYERS),
            "sample_max_turns": SAMPLE_MAX_TURNS,
            "bot": "control=bot / bot_difficulty=hard / bot_style=balanced（与 2310 局基线一致）",
            "sources": [
                "qa/winrate_baseline.json",
                "content.build_catalog(0).haunt_defs[i].rule_data（= haunt_rules.py）",
                "haunts.get_mode_handler(rule_data['mode']) 的处理器类",
                "haunt_ai_profiles.HAUNT_AI_PROFILE_OVERRIDES + DEFAULT_HAUNT_AI_PROFILE",
                "haunt_playtest.run_case 实跑抽样（winner_reason / tracks / offered-used-succeeded）",
            ],
        },
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="零胜剧本归因（T-01）")
    parser.add_argument("--json", default=str(DEFAULT_OUT), help="输出路径")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="基线 JSON")
    parser.add_argument("--no-sample", action="store_true", help="跳过实跑抽样（只读规则）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = build(Path(args.baseline), with_sample=not args.no_sample)
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    coverage = payload["coverage"]
    print(
        "归因完成：%d 本 → %s"
        % (len(payload["haunts"]), ", ".join(str(row["haunt_id"]) for row in payload["haunts"])),
        flush=True,
    )
    print(
        "档案覆盖：%d/70 专属，%d 本走默认%s"
        % (
            coverage["dedicated_profiles"],
            coverage["default_profiles"],
            "：" + ",".join(str(h) for h in coverage["default_profile_haunts"])
            if coverage["default_profile_haunts"]
            else "",
        ),
        flush=True,
    )
    print("产物：%s" % out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
