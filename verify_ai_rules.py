"""P1/P2 的行为边界回归：python verify_ai_rules.py。"""
from unittest import TestCase, main
from unittest.mock import patch

from bot_ai import BotDecisionProvider
from engine import ExitOption
from models import Monster
from haunt_modes import get_mode_handler
from haunt_playtest import run_case
from verify_haunt_systems import _new_engine
from net.serialize import state_from_dict, state_to_dict


class AIRules(TestCase):
    def setUp(self):
        self.e = _new_engine(5, 4)
        self.p = self.e.state.players[0]
        self.e.state.phase = "HAUNT_PHASE"
        self.p.role = "hero"
        self.e.state.turn_order = [p.id for p in self.e.state.players]
        self.e.state.turn_index = 0

    def test_original_three_timeouts_complete(self):
        for h, seed in ((35, 11), (35, 109), (70, 251)):
            with self.subTest(haunt=h, seed=seed):
                result = run_case(h, seed, 3, max_turns=400)
                self.assertTrue(result["completed"], result)
                self.assertIn(result["winner"], ("heroes", "traitor"))

    def test_cat_hook_does_not_skip_normal_turn(self):
        e = self.e
        e.state.haunt = e.catalog.haunt_defs[35]
        cat = Monster("cat", "cat", "猫", 6, 7, room_key=self.p.room_key)
        e.state.monsters = [cat]
        self.assertFalse(get_mode_handler("small_change_escape").on_monster_turn_start(e, cat))

    def test_damage_split_preserves_life_on_repeated_value_tracks(self):
        e, p = self.e, self.p
        p.stats_tracks = {"speed": [2, 2, 3, 3, 3], "might": [4, 4]}
        p.stat_positions.update(speed=4, might=0)
        p.stats.update(speed=3, might=4)
        chooser = BotDecisionProvider(e, p)
        first = chooser.choose_split_damage("分配伤害", f"{p.name} 受到伤害", 3, "速度", "力量")
        self.assertEqual(first, 3)
        e._apply_stat_loss(p, "speed", first)
        e._apply_stat_loss(p, "might", 3 - first)
        e._check_player_death(p)
        self.assertFalse(p.dead)

    def test_damage_split_accounts_for_overflow(self):
        e, p = self.e, self.p
        p.stats_tracks = {"speed": [2], "might": [3]}
        p.stat_positions.update(speed=0, might=0)
        p.stats.update(speed=2, might=3)
        p.overflow.update(speed=3, might=0)
        self.assertEqual(BotDecisionProvider(e, p).choose_split_damage("", p.name, 3, "速度", "力量"), 3)

    def test_damage_roll_zero_and_invalid_inputs(self):
        with patch.object(self.e, "roll_dice") as roll:
            self.assertEqual(self.e.roll_damage_dice(0), 0)
            roll.assert_not_called()
        with self.assertRaises(ValueError):
            self.e.roll_damage_dice(-1)

    def test_quest_card_cannot_be_used_after_transfer(self):
        e, p = self.e, self.p
        e.state.haunt = e.catalog.haunt_defs[20]
        p.items = ["omen_book"]
        e._haunt_flags()["groom_name_known"] = False
        e._mark_item_action("omen_book", "trade")
        with patch.object(e, "_resolve_check", side_effect=AssertionError("锁住的牌不能投骰")):
            self.assertFalse(e.perform_haunt_action(p, "learn_name_book"))
        self.assertNotIn("learn_name_book", [a.id for a in e.available_haunt_actions(p)])

    def test_failed_quest_roll_still_consumes_card_operation(self):
        e, p = self.e, self.p
        e.state.haunt = e.catalog.haunt_defs[20]
        p.items = ["omen_book"]
        e._haunt_flags()["groom_name_known"] = False
        with patch.object(e, "_resolve_check", return_value=False):
            self.assertTrue(e.perform_haunt_action(p, "learn_name_book"))
        self.assertFalse(e.item_action_available("omen_book"))

    def test_second_holy_weapon_can_be_dipped(self):
        e, p = self.e, self.p
        e.state.haunt = e.catalog.haunt_defs[70]
        handler = e._mode_handler()
        p.items = ["omen_spear", "item_axe"]
        e._haunt_flags().update(holy_rooms=[p.room_key], holy_weapons=["omen_spear"])
        self.assertTrue(handler._dip_weapon(e, p))
        self.assertEqual(set(e._haunt_flags()["holy_weapons"]), {"omen_spear", "item_axe"})

    def test_secret_form_does_not_remove_legal_human_actions(self):
        e, p = self.e, self.p
        e.state.haunt = e.catalog.haunt_defs[70]
        room = e._place_room(e.catalog.room_templates["chapel"], 90, 90, 0)
        p.room_key = room.key
        p.items = ["omen_holy_symbol"]
        e._haunt_flags().update(form="bane_spider", holy_rooms=[], bug_spray=False)
        self.assertIn("create_holy_water", [a.id for a in e._mode_handler().available_actions(e, p)])
        self.assertTrue(e._mode_handler().bot_action_blocked(e, p, "create_holy_water"))

    def test_monster_collapse_route_does_not_grant_explorer_climb(self):
        e, p = self.e, self.p
        top = e._place_room(e.catalog.room_templates["collapsed_room"], 90, 90, 0)
        below = e._place_room(e.catalog.room_templates["foyer"], 95, 95, 0)
        below.floor = -1
        top.data["below_key"] = below.key
        self.assertEqual(e._monster_path(below.key, top.key), [below.key, top.key])
        self.assertEqual(e._shortest_path(below.key, top.key), [below.key])

    def test_first_monster_fall_creates_marker_without_drawing_tile(self):
        e = self.e
        top = e._place_room(e.catalog.room_templates["collapsed_room"], 90, 90, 0)
        below = next(r for r in e.state.board.values() if r.floor == -1)
        m = Monster("fall", "cat", "猫", 6, 7, room_key=top.key)
        before = set(e.state.board)
        e._move_monster_along_path(m, [top.key, below.key], 1)
        self.assertEqual(top.data["below_key"], below.key)
        self.assertEqual(set(e.state.board), before)
        self.assertEqual(len(e.tokens_in_room(below.key, "below_collapsed_room")), 1)

    def test_token_ids_do_not_collide_after_deletion_or_reload(self):
        e = self.e
        a = e.spawn_token("paint")
        b = e.spawn_token("paint")
        e.remove_token(a.uid)
        c = e.spawn_token("paint")
        self.assertNotEqual(b.uid, c.uid)
        e.remove_token(b.uid)
        e.remove_token(c.uid)
        e.state = state_from_dict(state_to_dict(e.state))
        d = e.spawn_token("paint")
        self.assertEqual(len({a.uid, b.uid, c.uid, d.uid}), 4)

    def test_token_ids_infer_legacy_maximum(self):
        e = self.e
        token = e.spawn_token("paint")
        token.uid = "paint#9"
        e.state.meta.pop("token_serials", None)
        self.assertEqual(e.spawn_token("paint").uid, "paint#10")

    def _barrier(self):
        e, p = self.e, self.p
        room = e._place_room(e.catalog.room_templates["catacombs"], 90, 90, 0)
        e.configure_barrier(room, {d: (1 if d == room.doors[-1] else 0) for d in room.doors},
                            "speed", 3, "synthetic-test-fixture")
        p.room_key = room.key
        p.steps_remaining = 3
        e._set_barrier_side(p, room, 0)
        return room

    def test_barrier_success_costs_no_move_and_attempts_once(self):
        e, p = self.e, self.p
        room = self._barrier()
        crossing = next(o for o in e.available_move_options(p) if o.direction == "cross_barrier")
        with patch.object(e, "_resolve_check", return_value=True) as check:
            self.assertTrue(e.move_player(p, crossing))
            self.assertFalse(e.move_player(p, crossing))
            self.assertEqual(check.call_count, 1)
        self.assertEqual(p.steps_remaining, 3)
        self.assertEqual(e._barrier_side(p), 1)
        e._reset_player_turn_state(p)
        self.assertTrue(e._barrier_can_attempt(p, room))

    def test_barrier_failure_stops_turn_and_blocks_opposite_side_trade(self):
        e, p = self.e, self.p
        room = self._barrier()
        other = e.state.players[1]
        other.room_key = room.key
        e._set_barrier_side(other, room, 1)
        p.items = ["omen_spear"]
        self.assertFalse(e.entities_share_room(p, other))
        self.assertFalse(e.trade_item(p, other, "omen_spear"))
        with patch.object(e, "_resolve_check", return_value=False):
            self.assertTrue(e._cross_barrier(p))
        self.assertTrue(p.movement_stopped)
        self.assertEqual(p.steps_remaining, 0)
        restored = state_from_dict(state_to_dict(e.state))
        self.assertEqual(restored.meta["barrier_sides"], e.state.meta["barrier_sides"])

    def test_barrier_requires_explicit_source_data(self):
        room = self.e.current_room(self.p)
        with self.assertRaises(ValueError):
            self.e.configure_barrier(room, {}, "speed", 3, "")

    def test_traitor_bite_choice_precedes_any_roll(self):
        e, p = self.e, self.p
        p.role = "traitor"
        card = e.catalog.cards["omen_bite"]
        card.data["bite_attack"] = {"stat": "might", "dice": 4, "damage_type": "physical", "source": "synthetic-test-fixture"}
        with patch.object(e.prompter, "confirm", return_value=True), patch.object(e, "roll_dice", side_effect=AssertionError("选择豁免后不得投骰")):
            e._resolve_omen_effect(p, card)

    def test_bite_uses_explicit_data_and_missing_data_is_not_guessed(self):
        e, p = self.e, self.p
        card = e.catalog.cards["omen_bite"]
        with patch.object(e, "roll_dice") as roll:
            e._resolve_omen_effect(p, card)
            roll.assert_not_called()
        card.data["bite_attack"] = {"stat": "might", "dice": 4, "damage_type": "physical", "source": "synthetic-test-fixture"}
        with patch.object(e, "roll_dice", return_value=6), patch.object(e, "_roll_attack", return_value=2), patch.object(e, "_deal_damage") as damage:
            e._resolve_omen_effect(p, card)
            damage.assert_called_once_with(p, "physical", 4, source=card.name)


if __name__ == "__main__":
    main(verbosity=2)
