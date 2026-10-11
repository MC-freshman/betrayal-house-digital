"""本轮基础规则边界验证：python verify_base_rules.py。"""
from unittest import TestCase, main
from unittest.mock import patch

from verify_haunt_systems import _new_engine
from content import monster_def
from models import Monster
from net.serialize import monster_from_dict, monster_to_dict
from bot_ai import BotController


class BaseRules(TestCase):
    def setUp(self):
        self.engine = _new_engine(5, 4)
        self.player = self.engine.state.players[0]
        self.player.role = "hero"

    def test_vault_attempt_and_empty_marker(self):
        e, p = self.engine, self.player
        room = e._place_room(e.catalog.room_templates["vault"], 90, 90, -1)
        p.room_key = room.key
        with patch.object(e, "_resolve_check", return_value=False) as check, patch.object(e, "_deal_damage") as damage:
            e._apply_vault(p, room)
            e._apply_vault(p, room)
            check.assert_called_once_with(p, "knowledge", 6, "保险库检定")
            damage.assert_not_called()
        e._reset_player_turn_state(p)
        with patch.object(e, "_resolve_check", return_value=True), patch.object(e, "_draw_item") as draw:
            e._apply_vault(p, room)
            e._apply_vault(p, room)
            self.assertEqual(draw.call_count, 2)
        self.assertEqual(len(e.tokens_in_room(room.key, "empty_vault")), 1)

    def test_damage_dice_use_shared_damage_path(self):
        e, p = self.engine, self.player
        with patch.object(e, "roll_dice", return_value=3) as roll, patch.object(e, "_deal_damage") as damage:
            self.assertEqual(e.deal_dice_damage(p, "mental", 2, "测试"), 3)
            roll.assert_called_once_with(2, "测试")
            damage.assert_called_once_with(p, "mental", 3, source="测试")
        with self.assertRaises(ValueError):
            e.deal_dice_damage(p, "mental", -1)

    def test_distinct_items_and_transfer_lock(self):
        e, p = self.engine, self.player
        other = e.state.players[1]
        other.room_key = p.room_key
        p.items = ["item_adrenaline_shot", "item_angel_feather", "omen_spear"]
        self.assertTrue(e.use_item(p, "item_adrenaline_shot"))
        self.assertTrue(e.use_item(p, "item_angel_feather"))
        self.assertTrue(e.trade_item(p, other, "omen_spear"))
        self.assertFalse(e.drop_item(other, "omen_spear"))
        e._reset_player_turn_state(other)
        self.assertTrue(e.drop_item(other, "omen_spear"))
        self.assertFalse(e.pickup_item(other, "omen_spear"))

    def test_missing_trait_is_distinct_from_explicit_zero(self):
        a = monster_def(monster_id="test", name="测试", source_name="Test", speed=1, might=1)
        b = monster_def(monster_id="test", name="测试", source_name="Test", speed=1, might=1, sanity=0)
        self.assertNotIn("sanity", a["present_traits"])
        self.assertIn("sanity", b["present_traits"])
        e, p = self.engine, self.player
        e.state.phase = "HAUNT_PHASE"
        p.items = ["omen_ring"]
        m = Monster("test", "test", "测试", 1, 1, room_key=p.room_key, present_traits=a["present_traits"])
        with patch.object(e._mode_handler(), "attack_attr_override", return_value="sanity"):
            self.assertFalse(e.attack_would_be_allowed(p, m, None))
            m.present_traits = b["present_traits"]
            self.assertTrue(e.attack_would_be_allowed(p, m, None))
        self.assertEqual(monster_from_dict(monster_to_dict(m)).present_traits, m.present_traits)
        legacy = monster_to_dict(m)
        legacy.pop("present_traits")
        self.assertIsNone(monster_from_dict(legacy).present_traits)

    def test_monster_drops_and_recovers_items_after_stun(self):
        e, p = self.engine, self.player
        m = Monster("carrier", "test", "测试", 1, 1, room_key=p.room_key, can_carry_items=True,
                    items=["omen_spear"])
        e._stun_monster(m, 1)
        self.assertEqual(m.items, [])
        e._monster_pickup_items(m)
        self.assertEqual(m.items, [])
        m.stunned_turns = 0
        e._monster_pickup_items(m)
        self.assertEqual(m.items, ["omen_spear"])
        self.assertNotIn(p.room_key, e.state.room_items)
        m.can_carry_items = False
        e.state.room_items[p.room_key] = ["item_adrenaline_shot"]
        e._monster_pickup_items(m)
        self.assertNotIn("item_adrenaline_shot", m.items)

    def test_elevator_table_and_all_passengers(self):
        for result, floor in ((0, -1), (1, -1), (2, 0), (3, 1), (4, -1)):
            with self.subTest(result=result):
                e = _new_engine(5, 4)
                room = e._place_room(e.catalog.room_templates["mystic_elevator"], 90, 90, 0)
                crew = e.state.players[:2]
                for p in crew:
                    p.role, p.room_key = "hero", room.key
                with patch.object(e, "roll_dice", return_value=result), patch.object(e.prompter, "choose_from_list", return_value=0), patch.object(e, "deal_dice_damage") as damage:
                    e._apply_mystic_elevator(crew[0], room)
                    self.assertEqual(room.floor, floor)
                    self.assertTrue(all(p.room_key == room.key for p in crew))
                    self.assertEqual(damage.call_count, 2 if result == 0 else 0)
                    e._apply_mystic_elevator(crew[0], room)
                    self.assertEqual(damage.call_count, 2 if result == 0 else 0)

    def test_elevator_remaps_references_and_group_lock(self):
        e, p = self.engine, self.player
        room = e._place_room(e.catalog.room_templates["mystic_elevator"], 90, 90, 0)
        p.role, p.room_key = "traitor", room.key
        old = room.key
        flags = e._haunt_flags()
        flags["nested"] = {"room": old, "goal": "__room__" + old}
        e.state.room_items[old] = ["omen_spear"]
        token = e.spawn_token("test", label="测试", role="marker", room_key=old)
        with patch.object(e, "roll_dice", side_effect=AssertionError("叛徒自选不投骰")), patch.object(e.prompter, "choose_from_list", return_value=0):
            e._apply_mystic_elevator(p, room)
            self.assertIs(flags, e._haunt_flags())
            self.assertEqual(flags["nested"]["room"], room.key)
            self.assertEqual(flags["nested"]["goal"], "__room__" + room.key)
            self.assertEqual(token.room_key, room.key)
            self.assertIn("omen_spear", e.state.room_items[room.key])
            m = Monster("carrier", "test", "测试", 1, 1, room_key=room.key)
            key = room.key
            e._apply_mystic_elevator(m, room)
            self.assertEqual(room.key, key)

    def test_collapsed_discovers_new_basement_and_optional_reentry(self):
        e, p = self.engine, self.player
        room = e._place_room(e.catalog.room_templates["collapsed_room"], 90, 90, 1)
        p.room_key = room.key
        before = set(e.state.board)
        with patch.object(e, "_resolve_check", return_value=False), patch.object(e, "deal_dice_damage") as damage:
            e._apply_collapsed_room(p, room)
            damage.assert_called_once_with(p, "physical", 1, source="塌方房间")
        self.assertNotIn(room.data["below_key"], before)
        self.assertEqual(e.current_room(p).floor, -1)
        self.assertEqual(e.state.board[room.data["below_key"]].floor, -1)
        self.assertEqual(len(e.tokens_in_room(room.data["below_key"], "below_collapsed_room")), 1)
        p.room_key = room.key
        with patch.object(e.prompter, "confirm", return_value=False), patch.object(e, "roll_dice", side_effect=AssertionError("后来者可忽略")):
            e._apply_collapsed_room(p, room)
        self.assertEqual(p.room_key, room.key)

    def test_bot_leaves_elevator_before_building_a_branch(self):
        e, p = self.engine, self.player
        elevator = e._place_room(e.catalog.room_templates["mystic_elevator"], 90, 90, 0)
        fixed = e._place_room(e.catalog.room_templates["foyer"], 91, 90, 0)
        p.room_key = elevator.key
        p.steps_remaining = 5
        p.movement_stopped = False
        self.assertEqual(e._shortest_path(elevator.key, fixed.key, avoid_transit=True),
                         [elevator.key, fixed.key])
        options = e.available_move_options(p)
        self.assertTrue(any(o.is_new_room for o in options))
        ranked = BotController()._rank_move_options(e, p, options)
        self.assertEqual(ranked[0].target_key, fixed.key)


if __name__ == "__main__":
    main(verbosity=2)
