from __future__ import annotations

from ._imports import Player, STAT_NAMES

class DamageRules:
    def roll_dice(self, count: int, label: str = "") -> int:
        count = max(1, min(8, count))
        dice = [self.rng.choice((0, 1, 2)) for _ in range(count)]
        total = sum(dice)
        try:
            self.prompter.show_dice_roll(dice, total, label)
        except Exception:
            pass
        return total

    def _check_bonus(self, player: Player, stat: str) -> int:
        bonus = 0
        for card_id in player.items:
            card = self.catalog.cards.get(card_id)
            if not card:
                continue
            if stat in card.bonus:
                bonus += card.bonus[stat]
            if stat == "knowledge" and card.kind == "item" and card.id == "item_candle":
                bonus += 0
        return bonus

    def _attack_bonus_from_inventory(self, player: Player, weapon_card_id: str | None = None) -> int:
        bonus = 0
        for card_id in player.items:
            card = self.catalog.cards[card_id]
            if card.kind == "omen" and "attack" in card.bonus:
                bonus += card.bonus["attack"]
        if weapon_card_id:
            card = self.catalog.cards[weapon_card_id]
            bonus += card.bonus.get("attack", 0)
        return bonus

    def _effective_stat(self, player: Player, stat: str) -> int:
        return max(0, player.stats[stat])

    def _stat_track(self, player: Player, stat: str) -> list[int] | None:
        """返回某玩家某属性的轨道序列；旧存档缺失时才返回 None。"""
        if not player.stats_tracks:
            return None
        track = player.stats_tracks.get(stat)
        return track if track else None

    def _stat_cap(self, player: Player, stat: str) -> int:
        track = self._stat_track(player, stat)
        if track:
            return track[-1] + player.overflow.get(stat, 0)
        return player.stats_max[stat] + player.overflow.get(stat, 0)

    def _heal_stat(self, player: Player, stat: str, amount: int) -> None:
        before = player.stats[stat]
        track = self._stat_track(player, stat)
        if track:
            # 在轨道上向上划格
            pos = player.stat_positions.get(stat, 0)
            player.stat_positions[stat] = min(len(track) - 1, pos + amount)
            player.stats[stat] = track[player.stat_positions[stat]]
        else:
            cap = self._stat_cap(player, stat)
            player.stats[stat] = min(cap, player.stats[stat] + amount)
        if player.stats[stat] != before:
            self._log(f"{player.name} 的 {stat} 恢复到 {player.stats[stat]}。")

    def _increase_stat(self, player: Player, stat: str, amount: int) -> None:
        before = player.stats[stat]
        track = self._stat_track(player, stat)
        if track:
            top = len(track) - 1
            pos = player.stat_positions.get(stat, 0) + amount
            if pos > top:
                # 超出轨道顶端 → 超出部分记入临时加成
                player.overflow[stat] = player.overflow.get(stat, 0) + (pos - top)
                pos = top
            player.stat_positions[stat] = pos
            player.stats[stat] = track[pos]
        else:
            cap = self._stat_cap(player, stat)
            if before + amount <= cap:
                player.stats[stat] += amount
            else:
                overflow = before + amount - player.stats_max[stat]
                if overflow > player.overflow.get(stat, 0):
                    player.overflow[stat] = overflow
                player.stats[stat] = cap
        self._log(f"{player.name} 的 {stat} 提升到 {player.stats[stat]}。")

    def _resolve_check(self, player: Player, stat: str, target: int, label: str) -> bool:
        if player.next_check_auto_success:
            player.next_check_auto_success = False
            self._log(f"{player.name} 使用了一次自动成功。")
            return True
        if player.saved_roll is not None:
            saved = player.saved_roll
            if self.prompter.confirm("命中注定", f"{player.name} 要使用保存的掷骰结果 {saved} 来进行“{label}”吗？"):
                player.saved_roll = None
                self._log(f"{player.name} 使用了保存的掷骰结果 {saved}；目标 {target}。")
                return saved >= target
        dice = self._effective_stat(player, stat) + self._check_bonus(player, stat)
        dice = max(1, min(8, dice))
        roll = self.roll_dice(dice, label)
        self._log(f"{label}：{player.name} 掷出 {roll}（{dice} 骰），目标 {target}。")
        if roll >= target:
            return True
        if player.extra_check_rerolls > 0:
            player.extra_check_rerolls -= 1
            self._log(f"{player.name} 因额外重掷机会再次检定。")
            roll = self.roll_dice(dice, label)
            self._log(f"重掷结果：{roll}。")
            return roll >= target
        if self.prompter.confirm("重掷", f"{label} 失败了，要使用重掷机会吗？"):
            roll = self.roll_dice(dice, label)
            self._log(f"重掷结果：{roll}。")
            return roll >= target
        return False

    def _apply_damage_amounts(self, player: Player, physical: int = 0, mental: int = 0, source: str = "") -> None:
        if physical:
            self._split_and_apply(player, "physical", physical, source=source)
        if mental:
            self._split_and_apply(player, "mental", mental, source=source)
        self._check_player_death(player)

    def _split_and_apply(self, player: Player, damage_type: str, amount: int, source: str = "") -> None:
        if amount <= 0 or player.dead:
            return
        if damage_type == "physical" and player.ignore_first_physical_damage:
            player.ignore_first_physical_damage = False
            self._log(f"{player.name} 用护甲挡下了这次物理伤害。")
            return
        if damage_type == "physical" and source != "孢子" and self._has_card(player, "item_armor"):
            # 剧本 18 p29：盔甲不防孢子伤害。
            if self.prompter.confirm("盔甲", f"{player.name} 要用盔甲挡下这次物理伤害吗？"):
                self._discard_card_from_player(player, "item_armor", return_to_room=False)
                self._log(f"{player.name} 的盔甲挡下了物理伤害。")
                return
        first_label, second_label = ("速度", "力量") if damage_type == "physical" else ("理智", "知识")
        choice = self.prompter.choose_split_damage(
            "分配伤害",
            f"{player.name} 受到 {amount} 点{ '物理' if damage_type == 'physical' else '精神' }伤害，请分配到 {first_label}/{second_label}。",
            amount,
            first_label,
            second_label,
        )
        if choice is None:
            choice = amount
        if damage_type == "physical":
            first_stat, second_stat = "speed", "might"
        else:
            first_stat, second_stat = "sanity", "knowledge"
        first_amount = max(0, min(amount, choice))
        second_amount = amount - first_amount
        self._apply_stat_loss(player, first_stat, first_amount)
        self._apply_stat_loss(player, second_stat, second_amount)

    def _apply_stat_loss(self, player: Player, stat: str, amount: int) -> None:
        if amount <= 0:
            return
        before = player.stats[stat]
        track = self._stat_track(player, stat)
        if track:
            # 先消耗临时加成（overflow 视为卡尺之外的临时提升）
            ov = player.overflow.get(stat, 0)
            if ov > 0:
                consumed = min(ov, amount)
                player.overflow[stat] = ov - consumed
                amount -= consumed
                if amount <= 0:
                    return
            pos = player.stat_positions.get(stat, 0) - amount
            if pos < 0:
                if self.state.phase == "EXPLORE":
                    # 规则手册 p5/p16：作祟开始之前没有人会死亡——属性降到轨道
                    # 最左格就停住，不会滑到骷髅符号上。
                    pos = 0
                    player.stat_positions[stat] = pos
                    player.stats[stat] = track[pos]
                    if player.stats[stat] != before:
                        self._log(f"{player.name} 的 {stat} 从 {before} 降到 {player.stats[stat]}。")
                    return
                # 跌出轨道最左格（到达骷髅）→ 该属性归零（作祟期判定死亡）
                player.stat_positions[stat] = -1
                player.stats[stat] = 0
                self._log(f"{player.name} 的 {stat} 从 {before} 降到 0。")
                return
            player.stat_positions[stat] = pos
            player.stats[stat] = track[pos]
        else:
            player.stats[stat] = max(0, player.stats[stat] - amount)
        if player.stats[stat] != before:
            self._log(f"{player.name} 的 {stat} 从 {before} 降到 {player.stats[stat]}。")

    def _check_player_death(self, player: Player) -> None:
        if player.dead:
            return
        if self.state.phase == "EXPLORE":
            # 规则手册 p5：作祟开始之前没有人会死（属性只会停在最低值）。
            return
        if any(player.stats[stat] <= 0 for stat in STAT_NAMES):
            player.dead = True
            self._log(f"{player.name} 倒下了。")
            self._drop_inventory_on_death(player)
            # 剧本可对死亡做后处理（剧本 14 p96：尸体留在房间里可被搬走）。
            self._mode_handler().on_player_died(self, player)
            # 最后一个探险者倒下：立刻收口，不能把回合轮转停在死者身上。
            self._check_all_players_dead()

    def _check_all_players_dead(self) -> bool:
        """全员倒下时的收口：作祟期交给剧本判胜负，探索期直接终局。

        探索期还没有叛徒与剧本，无人可判；不在这里结束的话回合轮转会
        永远停在死者身上——seed7/3p 实测：三名机器人先后在探索期倒下，
        turn_count 冻结在第 31 回合，之后每次行动都是空转（黄金里唯一
        跑不完的用例）。作祟期仍按原口径交给 `check_victory`（10/24/47
        那类"叛徒开局就出局"的剧本也走这里）。
        """
        if self.state.phase == "GAME_OVER":
            return True
        if any(not player.dead for player in self.state.players):
            return False
        if self.state.phase == "HAUNT_PHASE":
            self.check_victory()
            if self.state.winner:
                return True
        self.state.phase = "GAME_OVER"
        self.state.winner_reason = "所有探险者都倒下了。"
        self._log("所有探险者都倒下了。游戏结束。")
        return True

    def _deal_damage(self, player: Player, damage_type: str, amount: int, source: str = "") -> None:
        if amount <= 0 or player.dead:
            return
        amount = self._adjust_damage_for_haunt(player, amount, source, damage_type=damage_type)
        if amount <= 0:
            return
        if source:
            self._log(f"{source} 让 {player.name} 受到 {amount} 点{ '物理' if damage_type == 'physical' else '精神' }伤害。")
        self._apply_damage_amounts(player, physical=amount if damage_type == "physical" else 0, mental=amount if damage_type == "mental" else 0, source=source)

    def deal_dice_damage(self, player: Player, damage_type: str, dice: int, source: str = "", label: str = "") -> int:
        """基础 A5：N 枚伤害骰的点数交给统一伤害入口，返回掷出点数。"""
        if damage_type not in ("physical", "mental") or not isinstance(dice, int) or dice < 0:
            raise ValueError("伤害类型须为 physical/mental，骰数须为非负整数")
        if player.dead or dice == 0:
            return 0
        amount = self.roll_damage_dice(dice, label or source)
        self._deal_damage(player, damage_type, amount, source=source)
        return amount

    def roll_damage_dice(self, dice: int, label: str = "") -> int:
        """共享或特殊分配伤害也从此处投骰，调用者保持原有的伤害分配顺序。"""
        if not isinstance(dice, int) or dice < 0:
            raise ValueError("伤害骰数须为非负整数")
        return self.roll_dice(dice, label) if dice else 0

    def _adjust_damage_for_haunt(self, player: Player, amount: int, source: str, damage_type: str = "physical") -> int:
        if amount <= 0:
            return amount
        # 剧本可整体改写伤害数值（剧本 5 p85：狼人受到的非银弹伤害减半，至少 1 点）。
        override = self._mode_handler().damage_amount_override(
            self, player, amount, source, damage_type
        )
        if override is not None:
            return override
        # 剧本可减免伤害（剧本 15 p26：古董护甲对非火焰物理伤害 -5）。
        reduction = self._mode_handler().physical_damage_reduction(
            self, player, amount, source, damage_type
        )
        if reduction > 0:
            # 减免来源名由剧本给出（默认"护甲"，剧本 52 p134 是戒指的魔力）。
            label = self._mode_handler().damage_reduction_label(self, player)
            self._log(f"{player.name} 的{label}挡下了 {min(reduction, amount)} 点伤害。")
        return max(0, amount - reduction)
