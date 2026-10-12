from __future__ import annotations

from ._imports import Card, Player, STAT_NAMES

class InventoryRules:
    def item_action_available(self, card_id: str) -> bool:
        """每件道具在本回合只可做一次主动操作。"""
        return card_id not in self.state.meta.get("item_actions", {})

    def _mark_item_action(self, card_id: str, operation: str) -> None:
        self.state.meta.setdefault("item_actions", {})[card_id] = operation

    def _has_card(self, player: Player, card_id: str) -> bool:
        return card_id in player.items

    def _discard_card_from_player(self, player: Player, card_id: str, return_to_room: bool = True) -> bool:
        if card_id not in player.items:
            return False
        player.items.remove(card_id)
        if card_id in player.companions:
            player.companions.remove(card_id)
        if return_to_room:
            self.state.room_items.setdefault(player.room_key, []).append(card_id)
            if self._barrier_config(self.current_room(player)):
                self.state.meta.setdefault("barrier_item_sides", {}).setdefault(player.room_key, {})[card_id] = self._barrier_side(player)
        return True

    def drop_item(self, player: Player, card_id: str) -> bool:
        card = self.catalog.cards.get(card_id)
        if not card or card_id not in player.items:
            return False
        if not self.item_action_available(card_id):
            return False
        # p11："咬""狗""女孩""女士"不是道具，不能被丢弃（也不能被盗取或交易）。
        if "companion" in card.tags or card.id == "omen_bite":
            self._log(f"{card.name} 不能被丢弃。")
            return False
        self._discard_card_from_player(player, card_id, return_to_room=True)
        self._mark_item_action(card_id, "drop")
        self._log(f"{player.name} 丢弃了 {card.name}。")
        # 剧本可对丢弃做后处理（剧本 33 p44：湖面上丢弃的物品直接沉没）。
        self._mode_handler().on_item_dropped(self, player, card_id)
        return True

    def pickup_item(self, player: Player, card_id: str) -> bool:
        sides = self.state.meta.get("barrier_item_sides", {}).get(player.room_key, {})
        if card_id in sides and sides[card_id] != self._barrier_side(player):
            return False
        # 剧本 7 p89：叛徒开局被迫丢下古书后，不能再捡起来。
        if self._mode_handler().item_pickup_blocked(self, player, card_id):
            card = self.catalog.cards.get(card_id)
            self._log(f"{card.name if card else card_id}无法被 {player.name} 捡起。")
            return False
        if player.dead:
            return False
        room_cards = self.state.room_items.get(player.room_key, [])
        if card_id not in room_cards:
            return False
        if not self.item_action_available(card_id):
            return False
        room_cards.remove(card_id)
        if not room_cards:
            self.state.room_items.pop(player.room_key, None)
        player.items.append(card_id)
        self._mark_item_action(card_id, "pickup")
        if "companion" in self.catalog.cards[card_id].tags and card_id not in player.companions:
            player.companions.append(card_id)
        self._log(f"{player.name} 捡起了 {self.catalog.cards[card_id].name}。")
        return True

    def trade_item(self, player: Player, target: Player, card_id: str, target_card_id: str | None = None) -> bool:
        if card_id not in player.items:
            return False
        if not self.item_action_available(card_id):
            return False
        if target_card_id and target_card_id in target.items and not self.item_action_available(target_card_id):
            return False
        card = self.catalog.cards[card_id]
        if not card.tradeable:
            self._log(f"{card.name} 不能交易。")
            return False
        # 剧本 9 p20：持圣徽的英雄不能自愿把圣徽交给别人（只能被偷走）。
        if self._mode_handler().item_trade_blocked(self, player, target, card_id):
            self._log(f"{player.name} 无法把 {card.name} 交给别人。")
            return False
        if not self.entities_share_room(player, target) or player.dead or target.dead:
            return False
        player.items.remove(card_id)
        target.items.append(card_id)
        self._mark_item_action(card_id, "trade")
        if "companion" in card.tags:
            if card_id in player.companions:
                player.companions.remove(card_id)
            if card_id not in target.companions:
                target.companions.append(card_id)
        if target_card_id and target_card_id in target.items:
            target_card = self.catalog.cards[target_card_id]
            if target_card.tradeable:
                target.items.remove(target_card_id)
                player.items.append(target_card_id)
                self._mark_item_action(target_card_id, "trade")
                self._log(f"{player.name} 与 {target.name} 交换了 {card.name} 和 {target_card.name}。")
                return True
        self._log(f"{player.name} 把 {card.name} 交给了 {target.name}。")
        return True

    def use_item(self, player: Player, card_id: str) -> bool:
        if card_id not in player.items:
            return False
        if self._mode_handler().item_use_blocked(self, player, card_id):
            self._log(f"{player.name} 此刻不能使用物品。")
            return False
        card = self.catalog.cards[card_id]
        if not self.item_action_available(card_id):
            self._log(f"{card.name} 本回合已经做过一件事。")
            return False
        effect = card.effect_id
        success = False
        if "weapon" in card.tags or effect in {"item_weapon", "item_weapon_blood", "item_dynamite", "item_revolver", "item_weapon_sacrifice"}:
            self._log(f"{card.name} 要在攻击时选择使用。")
            return False
        if effect == "item_heal_small" or effect == "item_heal_large" or effect == "item_heal_sanity":
            success = self._use_heal_item(player, card)
        elif effect == "item_adrenaline":
            player.steps_remaining += int(card.data.get("speed_bonus", 3))
            self._log(f"{player.name} 使用了肾上腺素针。")
            self._discard_card_from_player(player, card_id, return_to_room=False)
            success = True
        elif effect == "item_angel_feather":
            player.next_check_auto_success = True
            self._log(f"{player.name} 使用了天使羽毛。")
            self._discard_card_from_player(player, card_id, return_to_room=False)
            success = True
        elif effect == "item_music_box":
            success = self._use_music_box(player, card)
        elif effect == "item_bottle":
            success = self._use_random_stat_item(player, card, repeatable=False)
        elif effect == "item_dark_dice":
            success = self._use_random_stat_item(player, card, repeatable=True)
        elif effect == "item_amulet":
            success = self._use_amulet(player, card)
        elif effect == "item_pickpocket":
            success = self._use_pickpocket_gloves(player, card)
        elif effect == "item_puzzle_box":
            for _ in range(int(card.data.get("draw_items", 2))):
                self._draw_item(player)
            self._log(f"{player.name} 打开了谜题盒。")
            success = True
        elif effect == "item_reroll":
            player.extra_check_rerolls += 1
            self._log(f"{player.name} 使用了 {card.name}，下一次检定可重掷一次。")
            success = True
        elif effect == "item_bell":
            success = self._use_bell(player, card)
        elif effect == "item_armor":
            # 盔甲是被动减伤：由 _split_and_apply 在结算物理伤害时自动消耗，
            # 刻意不让它占用本回合的物品使用次数。
            self._log("盔甲会在你受到物理伤害时自动生效，不需要主动使用。")
            success = False
        elif card.bonus:
            # 确实只有被动加值的道具（护甲 / 蜡烛等）：加值由 _check_bonus 自动结算。
            self._log(f"{card.name} 是被动效果道具，无需主动使用（不占用本回合物品次数）。")
            success = False
        else:
            # 既没有主动分支、也没有被动加值——这是规则缺口，不能伪装成"被动道具"。
            self._log(f"[规则缺口] {card.name}（{effect}）的主动效果尚未实现。")
            success = False
        if success:
            self._mark_item_action(card_id, "use")
            player.item_used = True
        return success

    def _use_bell(self, player: Player, card: Card) -> bool:
        """铃铛：摇铃，把怪物吸引过来。

        权威依据（BetrayalHouseHill_v4.2.pdf）：
            p74 / p145（剧本 63 扭曲虚空）：
            "If you use an item (such as the Bell or Spirit Board) that would
             normally allow the Traitor to move monsters closer to you ..."
            → 铃铛的用途是让怪物朝使用者靠近，而不是被动加值道具。
              （被动的 +1 理智检定由 _check_bonus 另行结算。）

        各剧本对铃铛规定了免疫对象，精修对应剧本时需一并处理：
            p89（#7 食人常春藤）/ p105（#23 触手恐怖）：对被抓住的英雄无效
            p93（#11 放它们进来）：对背面朝上的幽灵无效
            p109（#27 狂乱血肉）：对 Blob 无效
            p117（#35 小小变化）：对被捕获的英雄无效
            p119（#37 将军）：不能影响与 Death 同房间的英雄

        待确认：规则书未写明每次摇铃怪物移动几格（印在实体卡上）。
        此处按"沿最短路径移动 1 格"实现，确认卡面后需校正。
        """
        if self.state.phase != "HAUNT_PHASE" or not self.state.monsters:
            self._log(f"{player.name} 摇响了铃铛，但此刻没有东西会被声音吸引。")
            return False
        self._log(f"{player.name} 摇响了{card.name}。")
        moved = 0
        for monster in self.state.monsters:
            if monster.stunned_turns > 0:
                self._log(f"{monster.name} 处于昏迷，没有反应。")
                continue
            if monster.room_key == player.room_key:
                continue
            path = self._shortest_path(monster.room_key, player.room_key)
            if len(path) > 1:
                monster.room_key = path[1]
                moved += 1
                self._log(f"{monster.name} 被铃声吸引，移动到 {self.state.board[monster.room_key].name}。")
        if not moved:
            self._log("没有怪物被铃声吸引过来。")
        self.check_victory()
        return True

    def _use_heal_item(self, player: Player, card: Card) -> bool:
        kind = card.data.get("kind", "physical")
        heal = int(card.data.get("heal", 1))
        options = ["速度", "力量"] if kind == "physical" else ["理智", "知识"]
        choice = self.prompter.choose_from_list(
            "恢复属性",
            f"要把 {card.name} 用在什么属性上？",
            options,
        )
        if choice is None:
            return False
        stat = ("speed", "might") if kind == "physical" else ("sanity", "knowledge")
        self._heal_stat(player, stat[choice], heal)
        self._discard_card_from_player(player, card.id, return_to_room=False)
        self._log(f"{player.name} 使用了 {card.name}。")
        return True

    def _use_music_box(self, player: Player, card: Card) -> bool:
        monsters = [m for m in self.state.monsters if m.room_key == player.room_key and m.stunned_turns <= 0]
        if not monsters:
            self._log("房间里没有可迷惑的怪物。")
            return False
        names = [monster.name for monster in monsters]
        idx = self.prompter.choose_from_list("音乐盒", "要让哪只怪物停顿一下？", names)
        if idx is None:
            return False
        monster = monsters[idx]
        self._stun_monster(monster, int(card.data.get("stun", 2)))
        self._discard_card_from_player(player, card.id, return_to_room=False)
        self._log(f"{monster.name} 被音乐盒迷住了。")
        return True

    def _use_random_stat_item(self, player: Player, card: Card, repeatable: bool) -> bool:
        stat = self.rng.choice(list(STAT_NAMES))
        delta = self.rng.choice([-1, 1]) * int(card.data.get("random_shift", 1))
        self._log(f"{card.name} 影响了 {player.name} 的 {stat}。")
        if delta > 0:
            self._increase_stat(player, stat, delta)
        else:
            self._apply_stat_loss(player, stat, -delta)
        if not repeatable:
            self._discard_card_from_player(player, card.id, return_to_room=False)
        return True

    def _use_amulet(self, player: Player, card: Card) -> bool:
        idx = self.prompter.choose_from_list("远古护身符", "要提升哪一项属性？", ["速度", "力量", "理智", "知识"])
        if idx is None:
            return False
        stat = STAT_NAMES[idx]
        boost = int(card.data.get("stat_boost", 1))
        player.overflow[stat] = player.overflow.get(stat, 0) + boost
        self._increase_stat(player, stat, boost)
        self._discard_card_from_player(player, card.id, return_to_room=False)
        return True

    def _use_pickpocket_gloves(self, player: Player, card: Card) -> bool:
        targets = [
            other
            for other in self.state.players
            if other.id != player.id and other.room_key == player.room_key and not other.dead and other.items
        ]
        if not targets:
            self._log("同房间没有可以偷取的对象。")
            return False
        idx = self.prompter.choose_from_list("扒手手套", "从谁那里偷一件物品？", [self._player_label(other) for other in targets])
        if idx is None:
            return False
        target = targets[idx]
        candidates = self._steal_candidates(player, target)
        if not candidates:
            self._log("对方没有可偷取的物品。")
            return False
        steal_idx = self.prompter.choose_from_list("偷窃", "要偷哪一件？", [self.catalog.cards[card_id].name for card_id in candidates])
        if steal_idx is None:
            return False
        steal_id = candidates[steal_idx]
        target.items.remove(steal_id)
        player.items.append(steal_id)
        self._mark_item_action(steal_id, "steal")
        self._log(f"{player.name} 偷走了 {target.name} 的 {self.catalog.cards[steal_id].name}。")
        self._discard_card_from_player(player, card.id, return_to_room=False)
        return True

    def _drop_inventory_on_death(self, player: Player) -> None:
        room_cards = self.state.room_items.setdefault(player.room_key, [])
        for card_id in player.items:
            room_cards.append(card_id)
        for card_id in player.companions:
            if card_id not in room_cards:
                room_cards.append(card_id)
        player.items.clear()
        player.companions.clear()
        # 携带的令牌也要落地。过去只掉卡片，令牌会一直挂在死人身上：剧本关键
        # 令牌（花/尸体/女孩/护甲…）因此被锁死，胜线整条断掉——18 号 seed31-6p
        # 实测：花被阵亡英雄拿着，全场 400 回合 0 次削弱、毒藤不死、叛徒也早死，
        # 两边都收不了场；20 号扛尸者倒下后尸体同样悬空。落回死亡房间后，后来者
        # 进房即可接手（各剧本的 on_enter_room 拾取逻辑照常生效）。
        for token in self.tokens_held_by(player.id):
            self.place_token(token.uid, player.room_key)
        self._log(f"{player.name} 的物品掉落在 {self.current_room(player).name}。")

    def _has_item(self, player: Player, card_id: str) -> bool:
        return card_id in player.items

    def _card_is_controlled(self, card_id: str) -> bool:
        if any(card_id in player.items for player in self.state.players):
            return True
        return any(card_id in room_cards for room_cards in self.state.room_items.values())

    def _grant_card_to_player(self, player: Player, card_id: str) -> bool:
        card = self.catalog.cards.get(card_id)
        if not card:
            return False
        if card_id in player.items:
            return True
        for deck in self.state.card_decks.values():
            if card_id in deck:
                deck.remove(card_id)
        for discards in self.state.card_discards.values():
            if card_id in discards:
                discards.remove(card_id)
        for room_cards in self.state.room_items.values():
            if card_id in room_cards:
                room_cards.remove(card_id)
        for other in self.state.players:
            if card_id in other.items:
                other.items.remove(card_id)
            if card_id in other.companions:
                other.companions.remove(card_id)
        player.items.append(card_id)
        if "companion" in card.tags and card_id not in player.companions:
            player.companions.append(card_id)
        self._log(f"{player.name} 获得了 {card.name}。")
        return True

    def _place_card_in_room(self, room_key: str, card_id: str) -> bool:
        """把一张牌摆到指定房间的地面（先摘离牌堆/弃牌堆/他人手上）。

        与 `_grant_card_to_player` 互为反向：剧本要把某件预定装备（例如
        p26 的长矛）预先放在某个房间供人拾取时用它，落点是 `state.room_items`，
        之后由通用的 `pickup_item`（人类按钮 / bot 自动）拾起。
        """
        card = self.catalog.cards.get(card_id)
        if card is None or room_key not in self.state.board:
            return False
        for deck in self.state.card_decks.values():
            if card_id in deck:
                deck.remove(card_id)
        for discards in self.state.card_discards.values():
            if card_id in discards:
                discards.remove(card_id)
        for other in self.state.players:
            if card_id in other.items:
                other.items.remove(card_id)
            if card_id in other.companions:
                other.companions.remove(card_id)
        for room_cards in self.state.room_items.values():
            if card_id in room_cards:
                room_cards.remove(card_id)
        self.state.room_items.setdefault(room_key, []).append(card_id)
        return True
