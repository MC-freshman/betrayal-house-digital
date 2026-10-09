"""BanishmentEscortMode（剧本 1）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
    _monster_id,
)


class BanishmentEscortMode(GenericModeHandler):
    """剧本 1 木乃伊苏醒（The Mummy Walks）。

    权威原文：英雄手册 p12 / 叛徒手册 p83。

    已核对且原本就正确的部分：
        木乃伊属性 Speed 3 / Might 8 / Sanity 5；两步调查均为 Knowledge 6+；
        放逐需 2 枚知识检定令牌 + 持书与木乃伊同房间打理智战。
    本次补齐的是此前完全缺失的令牌链路：
        石棺/木乃伊/女孩三个令牌的放置、女孩拾取、关键牌不在场时补抽。
    已实现（on_monster_attack / on_monster_move，见下方方法）：
        木乃伊造成速度伤害直到对手速度触底（但不降到骷髅）后转为力量伤害；
        单次造成 2+ 伤害时可改为夺取物品或抢走女孩（人类叛徒弹窗选择，
        机器人固定优先抢女孩）；
        移动掷出 0 或 1 时可经秘密通道移动到屋内任意位置（机器人固定选
        "朝最近英雄"；原版由叛徒任选房间——若将来支持人类叛徒自选，在
        on_monster_move 里加 prompter 询问即可）。
    """

    mode = "banishment_escort"

    SEARCH_ROOMS = {"catacombs", "research_laboratory", "library"}
    BRIDE_CARD = "omen_girl"
    RELIC_CARDS = ("omen_ring", "omen_holy_symbol")

    # ------------------------------------------------- 调查 / 放逐（p12/p83）

    def _girl_start_room(self, engine: Any, haunt_room_key: str) -> str | None:
        """女孩令牌的起始房间。

        叛徒手册 p83 原文：
            "Put the Girl token (crimson) in any room on the same floor as the
             room where the haunt was and at least five tiles away from the
             Mummy. If no rooms are at least five tiles away, place her as far
             away as possible on that floor."

        按 key 排序遍历，保证同一种子每次都选到同一个房间。
        （M10-72 自 engine._haunt1_girl_start_room 迁入。）
        """
        room = engine.state.board.get(haunt_room_key)
        if room is None:
            return None
        best_key: str | None = None
        best_distance = -1
        for key in sorted(engine.state.board):
            other = engine.state.board[key]
            if other.key == room.key or other.floor != room.floor:
                continue
            distance = engine._path_length(room.key, other.key)
            if 5 <= distance < 9999:  # 9999 是 _path_length 表示不可达的哨兵值
                return other.key
            if distance > best_distance:
                best_key, best_distance = other.key, distance
        return best_key

    def _mummy_ready_to_win(self, engine: Any, mummy: Any) -> bool:
        """p83：木乃伊带着女孩 + 戒指/圣徽之一回到作祟揭示的房间即叛徒胜。"""
        haunt_room = engine._haunt_rule_state().get("haunt_room", "")
        has_bride = self.BRIDE_CARD in mummy.items
        has_relic = any(card_id in mummy.items for card_id in self.RELIC_CARDS)
        return bool(haunt_room and mummy.room_key == haunt_room and has_bride and has_relic)

    def _check_traitor_victory(self, engine: Any) -> None:
        mummy = engine._monster_by_template("mummy")
        if mummy and self._mummy_ready_to_win(engine, mummy):
            engine._set_winner("traitor", "木乃伊带着女孩和仪式物回到了石棺房。")

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions: list[Any] = []
        room_id = engine._current_room_template_id(player)
        step = engine._haunt_track_value("banishment_steps")
        if player.role == "hero":
            if step < 1 and room_id in self.SEARCH_ROOMS:
                actions.append(HauntAction("h1_learn_true_name", "调查木乃伊真名", "知识 6+，成功后获得第一枚调查进度。"))
            if step == 1 and engine._has_item(player, "omen_book"):
                actions.append(HauntAction("h1_learn_spell", "在书中学习咒语", "知识 6+，成功后获得第二枚调查进度。"))
            mummy = engine._monster_by_template("mummy")
            if (
                step >= 2 and mummy and mummy.room_key == player.room_key
                and engine._has_item(player, "omen_book") and not player.attack_used
            ):
                actions.append(HauntAction("h1_banish_mummy", "放逐木乃伊", "与木乃伊进行理智战斗，胜利则英雄获胜。"))
        elif player.role == "traitor":
            mummy = engine._monster_by_template("mummy")
            if mummy and mummy.room_key == player.room_key:
                for card_id in (self.BRIDE_CARD,) + self.RELIC_CARDS:
                    if card_id in player.items:
                        card = engine.catalog.cards[card_id]
                        actions.append(
                            HauntAction(
                                "h1_give_mummy_card",
                                f"交给木乃伊：{card.name}",
                                "木乃伊可以保管女孩、戒指或圣徽。",
                                {"card_id": card_id},
                            )
                        )
                if self._mummy_ready_to_win(engine, mummy):
                    actions.append(HauntAction("h1_finish_wedding", "完成木乃伊婚礼", "木乃伊带着女孩和仪式物返回石棺房，叛徒获胜。"))
        return actions

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "h1_learn_true_name":
            if player.role != "hero" or engine._haunt_track_value("banishment_steps") >= 1:
                return False
            if engine._current_room_template_id(player) not in self.SEARCH_ROOMS:
                return False
            if engine._resolve_check(player, "knowledge", 6, "调查木乃伊真名"):
                engine._set_haunt_track_value("banishment_steps", 1)
                engine._log("英雄找到了木乃伊真名的线索。")
            return True
        if action_id == "h1_learn_spell":
            if (
                player.role != "hero"
                or engine._haunt_track_value("banishment_steps") != 1
                or not engine._has_item(player, "omen_book")
            ):
                return False
            if engine._resolve_check(player, "knowledge", 6, "学习放逐咒语"):
                engine._set_haunt_track_value("banishment_steps", 2)
                engine._log("英雄从书中学会了放逐咒语。")
            return True
        if action_id == "h1_banish_mummy":
            mummy = engine._monster_by_template("mummy")
            if (
                player.role != "hero" or not mummy or mummy.room_key != player.room_key
                or not engine._has_item(player, "omen_book")
            ):
                return False
            if engine._haunt_track_value("banishment_steps") < 2 or player.attack_used:
                return False
            hero_roll = engine._roll_attack(player, "sanity")
            mummy_roll = engine._roll_monster_attack(mummy, "sanity")
            engine._log(f"放逐木乃伊：{player.name} 掷出 {hero_roll}，木乃伊掷出 {mummy_roll}。")
            player.attack_used = True
            if hero_roll > mummy_roll:
                engine._set_winner("heroes", "英雄念出了木乃伊真名并完成放逐咒语。")
            elif mummy_roll > hero_roll:
                engine._deal_damage(player, "mental", mummy_roll - hero_roll, source="木乃伊的诅咒")
            else:
                engine._log("咒语暂时没有压过木乃伊。")
            return True
        if action_id == "h1_give_mummy_card":
            mummy = engine._monster_by_template("mummy")
            card_id = data.get("card_id")
            allowed = (self.BRIDE_CARD,) + self.RELIC_CARDS
            if (
                player.role != "traitor" or not mummy or mummy.room_key != player.room_key
                or card_id not in allowed
            ):
                return False
            if card_id not in player.items:
                return False
            player.items.remove(card_id)
            if card_id in player.companions:
                player.companions.remove(card_id)
            mummy.items.append(card_id)
            engine._log(f"{player.name} 把 {engine.catalog.cards[card_id].name} 交给了木乃伊。")
            self._check_traitor_victory(engine)
            return True
        if action_id == "h1_finish_wedding":
            mummy = engine._monster_by_template("mummy")
            if player.role != "traitor" or not mummy or not self._mummy_ready_to_win(engine, mummy):
                return False
            engine._set_winner("traitor", "木乃伊带着女孩和仪式物回到了石棺房。")
            return True
        return False

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # 叛徒手册 p83："Set aside the Girl card." —— 先把女孩卡从预兆牌堆
        # 里取出来，之后只能靠走进女孩令牌所在房间来拿到。不这样做的话，
        # 女孩会被当作普通预兆牌抽走，令牌机制就形同虚设。
        # 若女孩卡此时已在某人手上或遗落在房间里，则保持现状。
        if not engine._card_is_controlled("omen_girl"):
            for deck in engine.state.card_decks.values():
                if "omen_girl" in deck:
                    deck.remove("omen_girl")
                    break
        # 叛徒手册 p83：木乃伊令牌（大）与石棺令牌（五边形）放在作祟揭示的房间
        engine.spawn_token("sarcophagus", label="石棺", role="marker", room_key=room_key)
        mummy = engine._monster_by_template("mummy")
        if mummy:
            engine.spawn_token("mummy_marker", label="木乃伊", role="marker", room_key=mummy.room_key)
        # p83：女孩令牌放在同一楼层、距木乃伊至少 5 格的房间；
        #      没有这么远的就放在该楼层尽可能远处。
        girl_room = self._girl_start_room(engine, room_key)
        if girl_room:
            engine.spawn_token("girl", label="女孩", role="marker", room_key=girl_room)
        # 英雄手册 p12：预先拿出 2 枚知识检定令牌（三角形）
        engine.spawn_tokens("knowledge_check", 2, label="知识检定", role="check")

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        # p12 / p83：探险者进入女孩所在房间就把女孩带走。
        # 叛徒按 p83 "You lose the Girl" 不能拿。
        if player.role == "traitor" or player.dead:
            return
        if engine._card_is_controlled("omen_girl"):
            return
        girl = next(iter(engine.tokens_in_room(room.key, "girl")), None)
        if girl is None:
            return
        if engine._grant_card_to_player(player, "omen_girl"):
            engine.remove_token(girl.uid)
            engine._log(f"{player.name} 在{room.name}找到了女孩。")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        if room.symbol != "omen":
            return
        # p12：书若不在场上，下一个发现预兆房间的英雄从预兆牌堆里找出书。
        if player.role == "hero" and not engine._card_is_controlled("omen_book"):
            if engine._grant_card_to_player(player, "omen_book"):
                engine._log("有人在预兆牌堆里翻出了那本古书。")
            return
        # p83：戒指与圣徽都不在场时，下次发现预兆房间补抽其中之一。
        if player.role == "traitor":
            if engine._card_is_controlled("omen_ring") or engine._card_is_controlled("omen_holy_symbol"):
                return
            for card_id in ("omen_ring", "omen_holy_symbol"):
                if engine._grant_card_to_player(player, card_id):
                    card = engine.catalog.cards[card_id]
                    engine._log(f"仪式所需的{card.name}被找了出来。")
                    return

    # ---------------------------------------------------------------- 战斗
    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """木乃伊的专属攻击结算。

        叛徒手册 p83 原文：
            "The Mummy makes Might attacks but inflicts Speed damage until its
             opponent's Speed is at its lowest number. (This attack can't lower
             that trait to the skull symbol.) After that, its opponent takes
             Might damage instead until he or she is dead.
             When the Mummy inflicts 2 or more points of damage with an attack,
             it can steal an item from its opponent instead of inflicting that
             damage. The Mummy can also take the Girl from her custodian
             this way."
        """
        if _monster_id(monster) != "mummy" or amount <= 0:
            return False

        # 造成 2 点以上伤害时，可改为夺取物品或抢走女孩
        if amount >= 2 and self._haunt1_steal_instead(engine, monster, target, amount):
            return True

        # 速度尚未触底就扣速度（且不能扣到骷髅）；触底后改扣力量
        position = target.stat_positions.get("speed")
        track = engine._stat_track(target, "speed")
        if track and position is not None and position > 0:
            # position 就是还能往下降的格数，最多降到最低格（索引 0）
            engine._apply_stat_loss(target, "speed", min(amount, position))
        else:
            engine._apply_stat_loss(target, "might", amount)
        engine._check_player_death(target)
        return True

    def _haunt1_steal_instead(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """木乃伊改为夺取物品/女孩。返回 True 表示已夺取，本次不造成伤害。"""
        girl_first = [card_id for card_id in target.items if card_id == "omen_girl"]
        others = [card_id for card_id in target.items if card_id != "omen_girl"]
        if not girl_first and not others:
            return False

        traitor = next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)
        picked: str | None = None

        if traitor is not None and traitor.control == "human" and engine.prompter is not None:
            options = ["造成正常伤害"]
            mapping: list[str] = []
            for card_id in girl_first + others:
                card = engine.catalog.cards.get(card_id)
                if card:
                    options.append(f"夺取：{card.name}")
                    mapping.append(card_id)
            if len(options) == 1:
                return False
            choice = engine.prompter.choose_from_list(
                "木乃伊",
                f"木乃伊造成 {amount} 点伤害，可以改为夺取 {target.name} 的一件物品。",
                options,
            )
            if choice is None or choice == 0 or not (1 <= choice <= len(mapping)):
                return False
            picked = mapping[choice - 1]
        else:
            # 机器人叛徒：优先抢女孩，没有女孩就拿第一件物品
            picked = (girl_first + others)[0]

        target.items.remove(picked)
        card = engine.catalog.cards[picked]
        engine._log(f"木乃伊从 {target.name} 手中夺走了{card.name}。")
        if picked == "omen_girl":
            # p83：木乃伊可以这样把女孩从监护人手里抢走
            engine.state.meta.setdefault("haunt_rule", {}).setdefault("flags", {})["mummy_has_girl"] = True
        engine._check_player_death(target)
        return True

    # ---------------------------------------------------------------- 移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """木乃伊移动掷出 0 或 1 时可经秘密通道前往屋内任意房间。

        叛徒手册 p83："If the Mummy rolls a 0 or a 1 for its movement, it may
        use a secret passage to move to any space in the house."
        """
        if _monster_id(monster) != "mummy":
            return False
        if rolled > 1:
            return False  # 掷出 2 以上按常规移动处理

        target = engine._find_monster_target(monster)
        if target is None:
            return False
        # 直接落到目标所在房间：秘密通道本就可以去屋内任意位置，
        # 对机器人而言追人是最合理的选择，也保证同一种子结果一致。
        if monster.room_key == target.room_key:
            return True  # 已在目标房间，无需移动
        monster.room_key = target.room_key
        engine._log(f"木乃伊掷出 {rolled}，经秘密通道移动到 {engine.state.board[target.room_key].name}。")
        return True

    def check_victory(self, engine: Any) -> bool:
        mummy = engine._monster_by_template("mummy")
        if mummy and self._mummy_ready_to_win(engine, mummy):
            engine._set_winner("traitor", "木乃伊带着女孩和仪式物回到了石棺房。")
            return True
        if engine._check_generic_haunt_victory():
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p12/p83 的英雄条件是放逐木乃伊，
        # 叛徒死后木乃伊照常行动（基础规则 Even if the Traitor dies…they still
        # get their turn），不构成英雄胜利。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
