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
from content import build_catalog  # noqa: E402
from engine import AutoDecisionProvider, GameEngine  # noqa: E402
from models import Haunt  # noqa: E402

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
        configured = []
        for index, (template_id, template) in enumerate(sorted(engine.catalog.room_templates.items())):
            room = engine._place_room(template, 100 + index * 10, 100, 0)
            if "barrier" in room.data:
                configured.append(template_id)
        self.assertEqual(configured, [], "没有卡面依据时不允许给任何房间加障碍")

    def test_disclosed_spec_is_applied_and_rotated(self) -> None:
        engine = _engine(players=3)
        template = engine.catalog.room_templates["catacombs"]
        spec = {
            "doors": {"north": 0, "east": 1, "west": 1},
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
        # north->east(0)、east->south(1)、west->north(1)：side 跟着门一起转。
        self.assertEqual(config["doors"], {"east": 0, "south": 1, "north": 1})
        self.assertEqual((config["stat"], config["target"]), ("speed", 4))
        self.assertEqual(config["source"], "synthetic-test-fixture")


if __name__ == "__main__":
    unittest.main(verbosity=2)
