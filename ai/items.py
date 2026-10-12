from __future__ import annotations

from ._imports import ActionCommand, GameEngine, Player, STAT_NAMES

class InventoryDecisions:
    def _try_use_helpful_item(self, engine: GameEngine, player: Player) -> bool:
        if player.bot_difficulty == "easy" and engine.rng.random() < 0.45:
            return False
        for card_id in list(player.items):
            card = engine.catalog.cards.get(card_id)
            if not card:
                continue
            if not engine.item_action_available(card_id):
                continue
            preserve = getattr(engine._mode_handler(), "bot_preserve_item", None)
            if callable(preserve) and preserve(engine, player, card_id):
                continue
            if card.effect_id in {"item_heal_small", "item_heal_large"} and self._needs_heal(player, ("speed", "might")):
                return engine.execute_command(ActionCommand("use_item", player.id, {"card_id": card_id}))
            if card.effect_id == "item_heal_sanity" and self._needs_heal(player, ("sanity", "knowledge")):
                return engine.execute_command(ActionCommand("use_item", player.id, {"card_id": card_id}))
            if card.effect_id == "item_music_box" and self._monster_in_room(engine, player):
                return engine.execute_command(ActionCommand("use_item", player.id, {"card_id": card_id}))
            if card.effect_id == "item_amulet" and min(player.stats.get(stat, 0) for stat in STAT_NAMES) <= 2:
                return engine.execute_command(ActionCommand("use_item", player.id, {"card_id": card_id}))
            if card.effect_id == "item_adrenaline" and player.steps_remaining <= 1 and engine.available_move_options(player):
                return player.bot_difficulty == "hard" and engine.execute_command(ActionCommand("use_item", player.id, {"card_id": card_id}))
            if card.effect_id == "item_puzzle_box" and engine.state.phase == "EXPLORE" and player.bot_difficulty != "easy":
                return engine.execute_command(ActionCommand("use_item", player.id, {"card_id": card_id}))
        return False

    def _needs_heal(self, player: Player, stats: tuple[str, str]) -> bool:
        for stat in stats:
            track = player.stats_tracks.get(stat) if player.stats_tracks else None
            if track:
                pos = player.stat_positions.get(stat, 0)
                if pos >= 0 and pos <= 1:
                    return True
            elif player.stats.get(stat, 0) <= 2:
                return True
        return False

    def _monster_in_room(self, engine: GameEngine, player: Player) -> bool:
        return any(monster.room_key == player.room_key and monster.stunned_turns <= 0 for monster in engine.state.monsters)

    def _quest_carrier_id(self, engine: GameEngine) -> int | None:
        """剧本指定的"关键牌该交给谁"（duck-typed `quest_carrier` 钩子）。

        39 号：英雄胜利要求**继承人本人**持矛与戒登上王座，队友捡到必须交给
        他；而通用的"交给持令牌队友"启发在这里不适用（继承人身上没有令牌，
        用令牌标记继承人还会在 UI 上泄露身份）。未实现该钩子的剧本返回 None，
        行为保持原样。
        """
        handler = engine._mode_handler()
        carrier = getattr(handler, "quest_carrier", None)
        if not callable(carrier):
            return None
        value = carrier(engine)
        return int(value) if value is not None else None

    def _try_share_quest_items(self, engine: GameEngine, player: Player) -> bool:
        """同房间时，把剧本关键牌交给正在执行任务（持有剧本令牌）的队友。

        剧本 3 实测僵局：曼德拉草是**令牌**、无法交易，而魔法书是**卡牌**、
        可以交易。于是出现"A 挖到草却没有书、B 拿着书却没有草"，两人各自
        卡死，女巫永远无敌、整局空转到回合上限。
        令牌既不能交易，就让能交易的那一方去找它——把关键牌交给持令牌的
        队友。原版桌游里玩家会自然协商传递，这是电子版的等价行为。
        """
        if engine.state.phase != "HAUNT_PHASE":
            return False
        haunt = engine.state.haunt
        rule = (haunt.rule_data or {}) if haunt else {}
        required = {str(card_id) for card_id in rule.get("required_cards", [])}
        held = required & {str(item) for item in player.items}
        if not held:
            return False
        # 剧本指定的收牌人（39 号：继承人）优先于"持令牌队友"这一通用启发。
        carrier_id = self._quest_carrier_id(engine)
        for other in engine.state.players:
            if other.id == player.id or other.dead or other.frog:
                continue
            if other.role != player.role or other.room_key != player.room_key:
                continue
            if carrier_id is not None:
                if other.id != carrier_id:
                    continue
            # 队友手里有本剧本的令牌，说明他才是执行者
            elif not engine.tokens_held_by(other.id):
                continue
            for card_id in sorted(held):
                if card_id in other.items:
                    continue
                if engine.execute_command(
                    ActionCommand("trade", player.id, {"target_id": other.id, "card_id": card_id})
                ):
                    return True
        return False
