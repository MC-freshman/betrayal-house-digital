from __future__ import annotations

from ._imports import HauntAction, Player, deepcopy

class HauntActions:
    def available_haunt_actions(self, player: Player | None = None) -> list[HauntAction]:
        """按剧本 mode 分派。

        过去硬编码 `haunt.id == 1 / == 5`，导致 70 个 mode 字段形同虚设，
        每加一个剧本都要改引擎。现在查 haunt_modes 注册表，未注册的 mode
        自动回落到通用规则。
        """
        player = player or self.current_player
        if player.dead or self.state.phase != "HAUNT_PHASE" or not self.state.haunt:
            return []
        if self._haunt_action_used(player):
            return []
        return [a for a in self._mode_handler().available_actions(self, player)
                if all(self.item_action_available(cid)
                       for cid in self._haunt_action_cards(player, a.id))]

    def _haunt_action_cards(self, player: Player, action_id: str) -> list[str]:
        action = next((a for a in self._generic_haunt_actions() if a.get("id") == action_id), {})
        # 明确持卡的主动动作（读书、献祭、投矛、道具驱魔）与特殊 handler 共用锁。
        cards = [c for c in action.get("requires", []) + action.get("remove_cards", [])
                 if c in self.catalog.cards and c in player.items
                 and "companion" not in self.catalog.cards[c].tags and c != "omen_bite"]
        custom = getattr(self._mode_handler(), "action_item_cards", None)
        if callable(custom):
            cards.extend(custom(self, player, action_id) or [])
        return sorted(set(cards))

    def perform_haunt_action(self, player: Player, action_id: str, data: dict | None = None) -> bool:
        if player.dead or self.state.phase != "HAUNT_PHASE" or not self.state.haunt:
            return False
        if self._haunt_action_used(player):
            self._log(f"{player.name} 本回合已经执行过剧本行动。")
            return False
        cards = self._haunt_action_cards(player, action_id)
        if any(not self.item_action_available(cid) for cid in cards):
            return False
        before = set(player.items)
        success = self._mode_handler().perform_action(self, player, action_id, data or {})
        if success:
            cards.extend(before.symmetric_difference(player.items))
            for card_id in cards:
                self._mark_item_action(card_id, "haunt_action")
            self._mark_haunt_action_used(player)
            self.check_victory()
        return success

    def _generic_haunt_rule(self) -> dict:
        if not self.state.haunt:
            return {}
        return self.state.haunt.rule_data or {}

    def _generic_haunt_actions(self) -> list[dict]:
        actions = self._generic_haunt_rule().get("actions", [])
        return [action for action in actions if isinstance(action, dict)]

    def _haunt_side_allowed(self, player: Player, side: str) -> bool:
        return side in {"both", "any"} or side == player.role or (side == "heroes" and player.role == "hero")

    def _haunt_requirement_met(self, player: Player, requirement: str) -> bool:
        if not requirement:
            return True
        if requirement.startswith("same_room:"):
            target = requirement.split(":", 1)[1]
            if target in {"player", "hero", "frog"}:
                return any(
                    other.id != player.id
                    and not other.dead
                    and other.room_key == player.room_key
                    and (
                        target == "player"
                        or (target == "hero" and other.role == "hero")
                        # 青蛙是玩家身上的一种状态，不是令牌（剧本 3 p14：
                        # 复原青蛙必须先有一只同房间的青蛙可复原）。
                        or (target == "frog" and other.frog)
                    )
                    for other in self.state.players
                )
            if target == "revealer":
                return any(
                    other.id == self.state.haunt_revealer_id and other.room_key == player.room_key
                    for other in self.state.players
                )
            # 令牌类目标：same_room:<token_kind> 要求该房间有这个令牌
            # （如剧本 4 的蛛网、剧本 1 的女孩）。普通怪物查不到时回落到令牌。
            if any(
                monster.room_key == player.room_key and monster.template_id == target
                for monster in self.state.monsters
            ):
                return True
            return bool(self.tokens_in_room(player.room_key, target))
        if ">=" in requirement:
            track_id, raw_value = requirement.split(">=", 1)
            try:
                return self._haunt_track_value(track_id) >= int(raw_value)
            except ValueError:
                return False
        if requirement.startswith("flag:"):
            flag_id, _, expected = requirement[5:].partition("=")
            value = self._haunt_flags().get(flag_id)
            return bool(value) if not expected else str(value) == expected
        if requirement.startswith("not_flag:"):
            return not bool(self._haunt_flags().get(requirement[9:]))
        # 规则表中的普通字符串默认为必须由当前玩家携带的卡牌 ID。
        return requirement in player.items

    def _haunt_action_available(self, player: Player, action: dict) -> bool:
        if not self._haunt_side_allowed(player, str(action.get("side", "both"))):
            return False
        rooms = action.get("rooms", [])
        if rooms and self._current_room_template_id(player) not in rooms:
            # 剧本可豁免地点要求（剧本 2 p84：叛徒持有通灵板时可以在任何地方
            # 举行降灵会，不必回到五芒星室）。默认不豁免。
            handler = self._mode_handler()
            override = getattr(handler, "action_room_override", None)
            if not (callable(override) and override(self, player, action)):
                return False
        if any(not self._haunt_requirement_met(player, str(item)) for item in action.get("requires", [])):
            return False
        for flag_id, expected in dict(action.get("requires_flags", {})).items():
            if self._haunt_flags().get(flag_id) != expected:
                return False
        for track_id, expected in dict(action.get("requires_tracks", {})).items():
            if self._haunt_track_value(track_id) < int(expected):
                return False
        unique_flag = action.get("unique_flag")
        if unique_flag and self._haunt_flags().get(str(unique_flag)):
            return False
        progress_id = action.get("progress")
        if progress_id and self._haunt_track_target(str(progress_id)) > 0:
            if self._haunt_track_value(str(progress_id)) >= self._haunt_track_target(str(progress_id)):
                return False
        return True

    def _available_generic_haunt_actions(self, player: Player) -> list[HauntAction]:
        if self.state.turn_order and player.id != self.current_player.id:
            return []
        return [
            HauntAction(
                str(action.get("id", "")),
                str(action.get("label", action.get("id", "剧本行动"))),
                str(action.get("detail", "")),
                dict(action.get("data", {})),
            )
            for action in self._generic_haunt_actions()
            if action.get("id") and self._haunt_action_available(player, action)
        ]

    def _apply_generic_haunt_success(self, player: Player, action: dict) -> None:
        progress_id = action.get("progress")
        if progress_id:
            amount = max(1, int(action.get("progress_amount", 1)))
            value = self._advance_haunt_track(str(progress_id), amount)
            self._log(f"{action.get('label', '剧本行动')}成功：进度 {value}/{self._haunt_track_target(str(progress_id))}。")
        flags = self._haunt_flags()
        for flag_id, value in dict(action.get("set_flags", {})).items():
            flags[str(flag_id)] = deepcopy(value)
        for flag_id, amount in dict(action.get("increment_flags", {})).items():
            flags[str(flag_id)] = int(flags.get(str(flag_id), 0)) + int(amount)
        unique_flag = action.get("unique_flag")
        if unique_flag:
            flags[str(unique_flag)] = True
        for card_id in action.get("grant_cards", []):
            self._grant_card_to_player(player, str(card_id))
        for card_id in action.get("remove_cards", []):
            if str(card_id) in player.items:
                self._discard_card_from_player(player, str(card_id), return_to_room=False)
        if action.get("log_success"):
            self._log(str(action["log_success"]))
        if action.get("winner") in {"heroes", "traitor"}:
            self._set_winner(str(action["winner"]), str(action.get("win_reason", action.get("label", "完成剧本目标。"))))

    def _perform_generic_haunt_action(self, player: Player, action_id: str, data: dict) -> bool:
        # 先清零：行动不可用或检定失败时，绝不能让上一次的成功残留下来，
        # 被 handler 的 last_haunt_action_succeeded() 误读成"这次成功了"。
        self._last_haunt_action_success = False
        action = next((item for item in self._generic_haunt_actions() if item.get("id") == action_id), None)
        if not action or not self._haunt_action_available(player, action):
            return False
        stat = action.get("stat")
        success = True
        if stat:
            stats = [str(stat)] if isinstance(stat, str) else [str(item) for item in stat]
            stats = [item for item in stats if item in player.stats]
            if not stats:
                return False
            chosen_stat = max(stats, key=lambda item: self._effective_stat(player, item))
            success = self._resolve_check(player, chosen_stat, int(action.get("target", 0)), str(action.get("label", "剧本检定")))
        elif action.get("attack"):
            # 攻击型剧本行动：用指定属性与一个固定防御值对决。
            # 过去 attack/defense 这两个字段被引擎直接忽略，于是"打碎蛛网"
            # 之类变成必成功——剧本 4 的蛛网本该以 Might 4 防御，打输了
            # 既不推进进度也不受伤（p15）。
            attack_attr = str(action.get("attack", "might"))
            defense = int(action.get("defense", 0))
            label = str(action.get("label", "目标"))
            attack_roll = self._roll_attack(player, attack_attr)
            success = attack_roll > defense
            self._log(f"{player.name} 攻击{label}：{attack_roll} 对 {defense}。")
        self._last_haunt_action_success = bool(success)
        if success:
            self._apply_generic_haunt_success(player, action)
            self._log(f"{player.name} 完成了剧本行动：{action.get('label', action_id)}。")
        else:
            self._log(f"{player.name} 未完成剧本行动：{action.get('label', action_id)}。")
        return True

    def last_haunt_action_succeeded(self) -> bool:
        """最近一次通用剧本行动的**检定**是否成功（handler 包装 super() 时用）。

        `_perform_generic_haunt_action` 的返回值是"行动是否执行"——检定失败时
        它同样返回 True（这一回合的行动已经用掉）。handler 想"只在成功时发奖励/
        消耗资源"必须查这里，不能拿返回值当成功标志：旧写法
        `ok = super().perform_action(...)` + `if ok:` 在 31 处把失败也当成了成功
        （剧本 4 的蛛卵与前门、剧本 3 的曼德拉草都因此白送）。
        """
        return bool(self._last_haunt_action_success)

    def _haunt_rule_state(self) -> dict:
        return self.state.meta.setdefault("haunt_rule", {})

    def _haunt_flags(self) -> dict:
        return self._haunt_rule_state().setdefault("flags", {})

    def _haunt_tracks(self) -> dict:
        return self._haunt_rule_state().setdefault("tracks", {})

    def _haunt_action_used(self, player: Player) -> bool:
        used = self._haunt_rule_state().setdefault("actions_used", {})
        return bool(used.get(str(player.id)))

    def _mark_haunt_action_used(self, player: Player) -> None:
        used = self._haunt_rule_state().setdefault("actions_used", {})
        used[str(player.id)] = True

    def _haunt_track_value(self, track_id: str) -> int:
        track = self._haunt_tracks().get(track_id, {})
        return int(track.get("value", 0))

    def _haunt_track_target(self, track_id: str) -> int:
        track = self._haunt_tracks().get(track_id, {})
        return int(track.get("target", 0))

    def _set_haunt_track_value(self, track_id: str, value: int) -> None:
        track = self._haunt_tracks().setdefault(track_id, {"label": track_id, "target": 0, "value": 0})
        track["value"] = max(0, value)

    def _advance_haunt_track(self, track_id: str, amount: int = 1) -> int:
        value = self._haunt_track_value(track_id) + amount
        target = self._haunt_track_target(track_id)
        if target:
            value = min(value, target)
        self._set_haunt_track_value(track_id, value)
        return value

    def _current_room_template_id(self, player: Player) -> str:
        return self.current_room(player).template_id
