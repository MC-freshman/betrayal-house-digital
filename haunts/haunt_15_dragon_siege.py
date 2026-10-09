"""DragonSiegeMode（剧本 15）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    OPPOSITE_DOOR,
    _monster_id,
)


class DragonSiegeMode(GenericModeHandler):
    """剧本 15 有龙在此（Here There Be Dragons）。

    权威原文：英雄手册 p26 / 叛徒手册 p97。

    · 巨龙（beast 模板承载，Speed 3 / Might 8 / Sanity 6）：开局在门厅；
      伤害容量 = 玩家数（p97 Turn/Damage Track）；韧性：每次被击败实扣
      伤害 -2（p97 Toughness）；免疫速度攻击；持戒指者的理智攻击可伤它。
    · 每回合两次攻击（p97）：火息（同房与门相邻房间的**所有**探险者，
      含叛徒：速度检定 4+ 免疫，失败同房 4 骰/相邻 2 骰物理伤害；弃一件
      物品减 2 点——bot 自动弃第一件直到伤害归零）与咬（同房力量对决，
      持矛者防御 +4）。
    · 装备三件套（地下室，p97）：古董护甲（墓穴/地下湖——穿整回合、
      非火焰物理 -5、移动 -1、不可被偷）；盾（深坑/地窖——携带者免疫
      火焰、移动 -1、同房英雄也免疫龙焰）；矛（原版 p26 明确为
      "the Spear card"，即预兆牌 `omen_spear`——与剧本 19 统一）。
      三件都摆在剩余的地下室房间供拾取（矛的摆位是可玩性补充，原文只
      指定护甲/盾的位置）；房间未被发现时等发现即补放（on_room_discovered）。
      长矛若开局已被某位探险者拿在手上，则不重摆（保留手握状态）。
    · 英雄胜：龙受到的伤害攒满玩家人数即斩杀；叛徒胜：英雄全灭。
      巨龙由 bot 驱动（叛徒无法微操），叛徒阵亡不结束游戏。
    · 已知简化：穿甲/脱甲的"交给他人"未建模；护甲与盔甲卡不可同穿未拦；
      弃物减伤为 bot 自动（人类弹窗留待接 prompter）。
    """

    mode = "dragon_siege"

    DRAGON = "beast"
    BASEMENT_ROOMS = ["catacombs", "underground_lake", "chasm", "crypt"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["worn_by"] = None
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.DRAGON),
            {},
        )
        if engine._spawn_single_haunt_monster(spec, entrance):
            engine.spawn_token("dragon", label="巨龙", role="marker", room_key=entrance)
            engine._log("前门轰然洞开——一头巨龙咆哮着涌了进来！")

        def place(preferred: list[str]) -> str | None:
            for rid in preferred:
                key = next(
                    (k for k, r in engine.state.board.items() if r.template_id == rid),
                    None,
                )
                if key:
                    return key
            return None

        armor_room = place(["catacombs", "underground_lake"])
        shield_room = place(["chasm", "crypt"])
        used = {armor_room, shield_room}
        spear_room = next(
            (
                k for k, r in engine.state.board.items()
                if r.template_id in self.BASEMENT_ROOMS and k not in used
            ),
            None,
        )
        flags["armor_room"] = armor_room
        flags["shield_room"] = shield_room
        labels = {"antique_armor": "古董护甲", "shield": "盾"}
        for kind, key in (("antique_armor", armor_room), ("shield", shield_room)):
            if key:
                engine.spawn_token(kind, label=labels[kind], role="marker", room_key=key)
        # 长矛 = 预兆牌 omen_spear（p26 原文 "the Spear card"），与剧本 19 统一
        # 走真卡。若开局尚无人握矛，则摆到剩余的地下室房间，之后由通用
        # pickup_item（人类按钮 / bot 自动）拾取；已有人握矛则保持现状。
        held = any("omen_spear" in p.items for p in engine.state.players)
        flags["spear_room"] = spear_room if (spear_room and not held) else None
        if flags["spear_room"]:
            engine._place_card_in_room(spear_room, "omen_spear")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p97：装备所在的地下室房间未被探索时，发现即补放。"""
        flags = engine._haunt_flags()
        if room.template_id not in self.BASEMENT_ROOMS:
            return
        pending = [
            ("antique_armor", "armor_room", "古董护甲"),
            ("shield", "shield_room", "盾"),
        ]
        for kind, flag, label in pending:
            if flags.get(flag) is None:
                engine.spawn_token(kind, label=label, role="marker", room_key=room.key)
                flags[flag] = room.key
                engine._log(f"{room.name}里躺着一件装备：{label}。")
                return
        # 长矛（omen_spear 预兆卡）：尚未摆放且无人握持时，发现地下室即补放
        if flags.get("spear_room") is None and not any(
            "omen_spear" in p.items for p in engine.state.players
        ):
            engine._place_card_in_room(room.key, "omen_spear")
            flags["spear_room"] = room.key
            engine._log(f"{room.name}里躺着一件装备：长矛。")

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p26/p97：先取地下室的三件套，再去屠龙——空手冲龙只是送死。

        装备全以令牌/卡牌形式散在地下室，没有这条目标机器人只会朝龙硬冲
        （试玩实测英雄 0/18 胜）。像人的打法是先武装自己：护甲（物理 -5）、
        盾（免疫龙焰）、长矛（攻防 +4）。装备被拿走/穿上/捡起后目标自动
        消失（令牌、卡牌已不在原地），不会赖着不走。
        """
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        rooms: list[str] = []
        if flags.get("worn_by") is None:
            armor_room = flags.get("armor_room")
            if armor_room and engine.tokens_in_room(armor_room, "antique_armor"):
                rooms.append(f"__room__{armor_room}")
        rooms.extend(
            f"__room__{token.room_key}"
            for token in engine.tokens_of_kind("shield")
            if token.room_key
        )
        spear_room = flags.get("spear_room")
        if spear_room and "omen_spear" in engine.state.room_items.get(spear_room, []):
            rooms.append(f"__room__{spear_room}")
        return rooms

    # ------------------------------------------------------------- 内部
    def _door_adjacent(self, engine: Any, key_a: str, key_b: str) -> bool:
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor:
            return False
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy) and direction in a.doors and OPPOSITE_DOOR[direction] in b.doors:
                return True
        return False

    def _shield_holder(self, engine: Any) -> Any | None:
        token = next(
            (t for t in engine.state.tokens if t.kind == "shield" and t.holder is not None),
            None,
        )
        if token is None:
            return None
        return next((p for p in engine.state.players if p.id == token.holder), None)

    def _movement_penalty(self, engine: Any, player: Any) -> int:
        penalty = 0
        if engine.tokens_held_by(player.id, "shield"):
            penalty += 1  # p26：持盾移动 -1
        if engine._haunt_flags().get("worn_by") == player.id:
            penalty += 1  # p26：穿古董护甲移动 -1
        return penalty

    def on_turn_start(self, engine: Any, player: Any) -> None:
        penalty = self._movement_penalty(engine, player)
        if penalty and player.steps_remaining > 1:
            player.steps_remaining = max(1, player.steps_remaining - penalty)

    # ------------------------------------------------------------- 巨龙回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.DRAGON:
            return False
        target = engine._find_monster_target(monster)
        if target is not None:
            path = engine._shortest_path(monster.room_key, target.room_key)
            if len(path) > 1:
                steps = engine.roll_dice(getattr(monster, "speed", 3), "巨龙移动")
                monster.room_key = path[min(len(path) - 1, steps)]
                engine._log(f"巨龙杀到了{engine.state.board[monster.room_key].name}。")
        self._firebreath(engine, monster)
        self._bite(engine, monster)
        return True

    def _firebreath(self, engine: Any, monster: Any) -> None:
        """p97：同房与门相邻房间的所有探险者（含叛徒）做速度检定。"""
        shield_holder = self._shield_holder(engine)
        same, adjacent = [], []
        for p in engine.state.players:
            if p.dead:
                continue
            if p.room_key == monster.room_key:
                same.append(p)
            elif self._door_adjacent(engine, monster.room_key, p.room_key):
                adjacent.append(p)
        for zone, victims in (("same", same), ("adjacent", adjacent)):
            for victim in victims:
                if shield_holder is not None and (
                    victim.id == shield_holder.id
                    or (victim.role == "hero" and victim.room_key == shield_holder.room_key)
                ):
                    engine._log(f"{victim.name} 在盾的庇护下免疫龙焰。")
                    continue
                roll = engine._roll_attack(victim, "speed")
                if roll >= 4:
                    engine._log(f"{victim.name} 敏捷地避开了龙焰（速度检定 {roll}）。")
                    continue
                dice = 4 if zone == "same" else 2
                damage = engine.roll_dice(dice, "龙焰")
                # p26：可弃一件物品减 2 点（bot 自动弃直到伤害归零）
                while damage > 0 and victim.items:
                    card_id = victim.items[0]
                    engine._discard_card_from_player(victim, card_id, return_to_room=False)
                    damage -= 2
                    engine._log(
                        f"{victim.name} 舍弃了{engine.catalog.cards[card_id].name}，火焰伤害 -2。"
                    )
                damage = max(0, damage)
                if damage:
                    engine._deal_damage(victim, "physical", damage, source="龙焰")
                else:
                    engine._log(f"{victim.name} 在烈焰中毫发无伤。")

    def _bite(self, engine: Any, monster: Any) -> None:
        victims = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return
        victim = victims[0]
        dragon_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(victim, "might")
        if "omen_spear" in victim.items:
            hero_roll += 4  # p26：持矛对龙防御 +4
            engine._log(f"{victim.name} 挥矛格挡（+4）。")
        engine._log(f"巨龙撕咬 {victim.name}：{dragon_roll} 对 {hero_roll}。")
        if dragon_roll > hero_roll:
            engine._deal_damage(victim, "physical", dragon_roll - hero_roll, source="巨龙之咬")
        elif dragon_roll < hero_roll:
            engine._stun_monster(monster, 1)

    # ------------------------------------------------------------- 攻击规则
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p97：持戒指者对巨龙的徒手攻击改为理智攻击。"""
        if _monster_id(target) == self.DRAGON and default_attr == "might" and "omen_ring" in attacker.items:
            return "sanity"
        return None

    def attack_roll_bonus(self, engine: Any, attacker: Any, target: Any) -> int:
        """p26：持矛（omen_spear）对巨龙的攻击骰 +4。"""
        if _monster_id(target) == self.DRAGON and "omen_spear" in attacker.items:
            return 4
        return 0

    def physical_damage_reduction(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int:
        """p26：古董护甲对非火焰物理伤害 -5。"""
        if engine._haunt_flags().get("worn_by") != player.id:
            return 0
        if damage_type != "physical":
            return 0
        if "火" in (source or "") or "热" in (source or ""):
            return 0
        return 5

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p97：韧性——每次被击败实扣伤害 -2；伤害由轨迹记录，不击晕。"""
        if _monster_id(monster) != self.DRAGON:
            return False
        net = max(0, amount - 2)
        if net > 0:
            engine._advance_haunt_track("dragon_damage", net)
        engine._log(
            f"巨龙受创（韧性抵消 2 点，实扣 {net}；"
            f"总 {engine._haunt_track_value('dragon_damage')}/{engine._haunt_track_target('dragon_damage')}）。"
        )
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "don_armor":
                if player.role != "hero" or engine._haunt_flags().get("worn_by") is not None:
                    continue
                if not engine.tokens_in_room(player.room_key, "antique_armor"):
                    continue
            if action.id == "take_shield" and not engine.tokens_in_room(player.room_key, "shield"):
                continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "don_armor":
            token = next(iter(engine.tokens_in_room(player.room_key, "antique_armor")), None)
            if token is None or engine._haunt_flags().get("worn_by") is not None:
                engine._log("这里没有可穿的古董护甲（或已有人在穿）。")
                return False
            engine.give_token(token.uid, player.id)
            engine._haunt_flags()["worn_by"] = player.id
            player.movement_stopped = True  # p26：穿甲花整个回合
            player.steps_remaining = 0
            engine._log(f"{player.name} 花了整整一个回合穿上古董护甲。")
            return True
        if action_id == "take_shield":
            token = next(iter(engine.tokens_in_room(player.room_key, "shield")), None)
            if token is None:
                engine._log("这里没有盾。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 扛起了沉重的盾。")
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("dragon_damage") >= engine._haunt_track_target("dragon_damage"):
            monster = engine._monster_by_template(self.DRAGON)
            if monster is not None:
                dragon_id = getattr(monster, "id", None)
                engine.state.monsters = [
                    m for m in engine.state.monsters if getattr(m, "id", None) != dragon_id
                ]
            engine._set_winner("heroes", "巨龙轰然倒地——现在是跟叛徒算账的时候了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "巨龙把最后的探险者也吞进了腹中。")
            return True
        return True  # 巨龙自主行动，叛徒阵亡不结束游戏
