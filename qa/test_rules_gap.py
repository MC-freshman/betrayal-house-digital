#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第 4 项（T16/T17）叛徒人类自选的回归测试。

核心命题只有一条：**新增的 ``DecisionProvider.choose_traitor`` 不得改变任何
既有实现下的叛徒归属**。因此这里逐条比较

    ``GameEngine._select_traitor(haunt, revealer)``          # 新入口（含决策点）
    ``GameEngine._select_traitor_by_rule(haunt, revealer)``  # 改动前的属性规则

在 11 个 ``traitor_rule`` 分支上必须选中同一位玩家；只有显式给出有效下标的
人类实现才会覆盖，异常 / None / 越界 / 布尔值一律回落属性规则。

跑法::

    python qa/test_rules_gap.py
    python -m unittest qa.test_rules_gap -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

GAME_DIR = Path(__file__).resolve().parents[1]
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

from ai.decisions import BotDecisionProvider  # noqa: E402
from content import BARRIER_SPECS, build_catalog  # noqa: E402
from engine import AutoDecisionProvider, GameEngine  # noqa: E402
from models import Haunt, Monster  # noqa: E402

# 引擎里 _select_traitor_by_rule 认识的全部分支（含兜底 default）。
TRAITOR_RULES = (
    "highest_might_except_revealer",
    "revealer",
    "highest_might",
    "lowest_sanity",
    "lowest_sanity_except_revealer",
    "highest_knowledge",
    "lowest_knowledge",
    "highest_speed",
    "left_of_revealer",
    "specific_character",
    "unknown_rule_falls_back_to_revealer",
)


class _ScriptedProvider:
    """只实现 choose_traitor 的鸭子类型实现（模拟人类界面 / 异常实现）。"""

    def __init__(self, index):
        self.index = index
        self.calls = 0

    def choose_traitor(self, candidates, state):
        self.calls += 1
        if isinstance(self.index, Exception):
            raise self.index
        return self.index


class _LegacyProvider:
    """改动前的 prompter 形态：没有 choose_traitor 方法。"""

    def notify(self, title, message):
        return None

    def confirm(self, title, message):
        return True


def _engine(players: int = 4) -> GameEngine:
    catalog = build_catalog(7)
    faces = list(catalog.characters)
    engine = GameEngine(catalog=catalog, seed=7)
    engine.start_new_game(
        [
            {
                "name": "P%d" % (index + 1),
                "character_id": faces[index],
                "control": "human",
            }
            for index in range(players)
        ]
    )
    # 把四条属性掰成互不相同的梯度，让"最高/最低/揭示者/左侧"四类规则各自落在
    # 不同玩家身上——否则"等价"可能只是因为谁都一样。
    stats = [
        {"speed": 6, "might": 8, "sanity": 3, "knowledge": 7},
        {"speed": 5, "might": 4, "sanity": 6, "knowledge": 5},
        {"speed": 4, "might": 6, "sanity": 5, "knowledge": 3},
        {"speed": 3, "might": 5, "sanity": 7, "knowledge": 4},
    ]
    for player, values in zip(engine.state.players, stats):
        player.stats.update(values)
    engine.state.turn_order = [player.id for player in engine.state.players]
    return engine


class TraitorChoice(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _engine()
        self.revealer = self.engine.state.players[0]
        self.engine.prompter = AutoDecisionProvider()

    def test_default_provider_matches_attribute_rule_on_every_branch(self) -> None:
        for rule in TRAITOR_RULES:
            with self.subTest(rule=rule):
                haunt = Haunt(id=1, name="测试剧本", traitor_rule=rule)
                expected = self.engine._select_traitor_by_rule(haunt, self.revealer)
                actual = self.engine._select_traitor(haunt, self.revealer)
                self.assertIs(actual, expected, "默认实现必须与属性规则选中同一位玩家")

    def test_default_provider_is_flagged_and_payload_is_complete(self) -> None:
        engine = self.engine
        haunt = Haunt(id=2, name="测试剧本", traitor_rule="highest_might")
        expected = engine._select_traitor_by_rule(haunt, self.revealer)
        seen = {}

        class _Capture(AutoDecisionProvider):
            def choose_traitor(inner_self, candidates, state):
                seen["candidates"] = candidates
                seen["state"] = state
                return super().choose_traitor(candidates, state)

        engine.prompter = _Capture()
        chosen = engine._select_traitor(haunt, self.revealer)
        self.assertIs(chosen, expected)
        self.assertIs(seen["state"], engine.state)
        candidates = seen["candidates"]
        self.assertEqual(len(candidates), len(engine.state.players))
        for candidate in candidates:
            for key in ("id", "name", "character", "label", "default"):
                self.assertIn(key, candidate)
        defaults = [c for c in candidates if c["default"]]
        self.assertEqual(len(defaults), 1, "必须恰好标记一个属性规则默认候选")
        self.assertEqual(defaults[0]["id"], expected.id)

    def test_human_override_wins(self) -> None:
        engine = self.engine
        engine.prompter = _ScriptedProvider(2)
        haunt = Haunt(id=3, name="测试剧本", traitor_rule="revealer")
        rule_pick = engine._select_traitor_by_rule(haunt, self.revealer)
        chosen = engine._select_traitor(haunt, self.revealer)
        self.assertIs(chosen, engine.state.players[2])
        self.assertNotEqual(chosen.id, rule_pick.id, "本用例要覆盖的是「人类改了默认值」")

    def test_bad_or_failed_choice_falls_back_to_rule(self) -> None:
        engine = self.engine
        haunt = Haunt(id=4, name="测试剧本", traitor_rule="highest_might")
        expected = engine._select_traitor_by_rule(haunt, self.revealer)
        for bad in (None, -1, 99, True, False, RuntimeError("界面崩了")):
            with self.subTest(bad=repr(bad)):
                engine.prompter = _ScriptedProvider(bad)
                self.assertIs(engine._select_traitor(haunt, self.revealer), expected)

    def test_legacy_prompter_without_method_keeps_rule(self) -> None:
        engine = self.engine
        engine.prompter = _LegacyProvider()
        haunt = Haunt(id=5, name="测试剧本", traitor_rule="lowest_sanity")
        expected = engine._select_traitor_by_rule(haunt, self.revealer)
        self.assertIs(engine._select_traitor(haunt, self.revealer), expected)

    def test_bot_provider_keeps_rule(self) -> None:
        engine = self.engine
        haunt = Haunt(id=6, name="测试剧本", traitor_rule="highest_knowledge")
        expected = engine._select_traitor_by_rule(haunt, self.revealer)
        engine.prompter = BotDecisionProvider(engine, engine.state.players[1])
        self.assertIs(engine._select_traitor(haunt, self.revealer), expected)

    def test_dead_players_are_not_offered(self) -> None:
        engine = self.engine
        engine.state.players[3].dead = True
        haunt = Haunt(id=7, name="测试剧本", traitor_rule="revealer")
        candidates = []

        class _Capture(_ScriptedProvider):
            def choose_traitor(inner_self, payload, state):
                candidates.extend(payload)
                return 0

        engine.prompter = _Capture(0)
        engine._select_traitor(haunt, self.revealer)
        offered = {c["id"] for c in candidates}
        self.assertNotIn(engine.state.players[3].id, offered, "死者不应出现在候选里")
        self.assertEqual(len(candidates), 3)


class BarrierWiring(unittest.TestCase):
    """K2 接线：没登记的房间一律不配置；登记了就按 rotation 正确落位。"""

    def test_no_room_is_wired_without_disclosed_data(self) -> None:
        engine = _engine(players=3)
        configured = {}
        for index, (template_id, template) in enumerate(sorted(engine.catalog.room_templates.items())):
            room = engine._place_room(template, 100 + index * 10, 100, 0)
            if "barrier" in room.data:
                configured[template_id] = room.data["barrier"]
        # 没登记的房间不允许加障碍；登记了就必须生效（两侧都出现、属性阈值与登记一致）。
        self.assertEqual(sorted(configured), sorted(BARRIER_SPECS),
                         "接线集合必须严格等于 BARRIER_SPECS")
        self.assertNotIn("vault", configured, "Vault 官方 1 门、引擎无 1 门能力，见 D-06")
        for template_id, config in configured.items():
            self.assertEqual(set(config["doors"]),
                             set(engine.catalog.room_templates[template_id].doors))
            self.assertEqual(set(config["doors"].values()), {0, 1}, "两侧都必须有门")
            self.assertEqual((config["stat"], config["target"]),
                             (BARRIER_SPECS[template_id]["stat"],
                              BARRIER_SPECS[template_id]["target"]))
            self.assertTrue(config["source"])

    def test_disclosed_spec_is_applied_and_rotated(self) -> None:
        engine = _engine(players=3)
        template = engine.catalog.room_templates["catacombs"]
        # 官方板块：north/south 两门（二手交叉验证，见 content.BARRIER_SPECS）。
        spec = {
            "doors": {"north": 0, "south": 1},
            "stat": "speed",
            "target": 4,
            "source": "synthetic-test-fixture",
        }
        self.assertEqual(set(spec["doors"]), set(template.doors), "登记表必须覆盖该模板的全部门")
        with mock.patch.dict("rules.barriers.BARRIER_SPECS", {"catacombs": spec}):
            rotated = engine._build_rotated_template(template, 1)
            room = engine._place_room(rotated, 200, 200, 1)
        config = room.data.get("barrier")
        self.assertIsNotNone(config, "登记过的房间落位后应带两侧配置")
        self.assertEqual(set(config["doors"]), set(room.doors), "门->侧映射必须覆盖旋转后的门")
        # north->east(0)、south->west(1)：side 跟着门一起转。
        self.assertEqual(config["doors"], {"east": 0, "west": 1})
        self.assertEqual((config["stat"], config["target"]), ("speed", 4))
        self.assertEqual(config["source"], "synthetic-test-fixture")


class MonsterIgnoresBarrier(unittest.TestCase):
    """p2：Monsters ignore barriers —— 两侧归属只约束探险者。

    背景：``BARRIER_SPECS`` 为空时侧归属判定是死代码；K2 落地后第一次被
    走到，英雄与同房间怪物分居两侧时攻击被误拒（30 号剧本德古拉在 chasm）。
    规则书 p2 与 ``_apply_catacombs`` docstring 都写明怪物无视障碍。
    """

    def setUp(self) -> None:
        self.engine = _engine(players=3)
        self.engine.state.phase = "HAUNT_PHASE"
        self.hero = self.engine.state.players[0]
        self.hero.role = "hero"
        self.hero.attack_used = False
        self.hero.stats["might"] = 4
        self.engine.state.turn_order = [player.id for player in self.engine.state.players]
        self.engine.state.turn_index = 0
        # 真实怪物模板（cat）走 state.monsters，另外断言 is_monster 标记形态。
        self.monster = Monster("mon_test", "cat", "测试怪物", 4, 4, room_key="")
        self.engine.state.monsters = [self.monster]
        self.room = self.engine._place_room(
            self.engine.catalog.room_templates["catacombs"], 90, 90, 0
        )
        self.engine.configure_barrier(
            self.room,
            {d: (1 if d == self.room.doors[-1] else 0) for d in self.room.doors},
            "speed",
            3,
            "synthetic-test-fixture",
        )
        self.hero.room_key = self.room.key
        self.monster.room_key = self.room.key
        self.engine._set_barrier_side(self.hero, self.room, 1)
        self.engine._set_barrier_side(self.monster, self.room, 0)
        self.assertNotEqual(
            self.engine._barrier_side(self.hero),
            self.engine._barrier_side(self.monster),
            "本用例的前提就是分居两侧",
        )

    def test_monster_and_hero_share_room_across_barrier(self) -> None:
        self.assertTrue(self.engine.entities_share_room(self.hero, self.monster))
        self.assertTrue(self.engine.entities_share_room(self.monster, self.hero))
        # 对照：两位探险者分居两侧仍然不能交互（没有放宽探险者规则）。
        other = self.engine.state.players[1]
        other.room_key = self.room.key
        self.engine._set_barrier_side(other, self.room, 0)
        self.assertFalse(self.engine.entities_share_room(self.hero, other))

    def test_hero_can_attack_monster_across_barrier(self) -> None:
        with mock.patch.object(self.engine, "_roll_attack", return_value=5), \
                mock.patch.object(self.engine, "_roll_monster_attack", return_value=1):
            self.assertTrue(self.engine.attack(self.hero, self.monster))
        self.assertTrue(self.hero.attack_used)

    def test_monster_can_attack_hero_across_barrier(self) -> None:
        with mock.patch.object(self.engine, "_roll_monster_attack", return_value=7), \
                mock.patch.object(self.engine, "_roll_attack", return_value=1), \
                mock.patch.object(self.engine, "_deal_damage") as deal:
            self.engine._monster_attack(self.monster, self.hero)
        deal.assert_called_once()

    def test_monster_crosses_without_roll_and_hero_still_rolls(self) -> None:
        # 怪物：直接翻侧，不掷检定、不占每回合一次的机会。
        with mock.patch.object(self.engine, "_resolve_check") as check:
            self.assertTrue(self.engine._cross_barrier(self.monster))
            check.assert_not_called()
        self.assertEqual(self.engine._barrier_side(self.monster), 1)
        self.assertNotIn(
            self.engine._barrier_attempt_key(self.monster, self.room),
            self.engine.state.meta.get("barrier_attempts", []),
        )
        # 英雄：仍需检定，失败原地停步。
        with mock.patch.object(self.engine, "_resolve_check", return_value=False) as check:
            self.assertTrue(self.engine._cross_barrier(self.hero))
            check.assert_called_once()
        self.assertEqual(self.engine._barrier_side(self.hero), 1, "检定失败不能翻侧")
        self.assertTrue(self.hero.movement_stopped)
        self.assertEqual(self.hero.steps_remaining, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
