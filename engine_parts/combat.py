from __future__ import annotations

from ._imports import Card, Monster, PHYSICAL_STATS, Player

class CombatRules:
    def available_attack_targets(self, player: Player | None = None, ranged: bool = False) -> list[object]:
        player = player or self.current_player
        if player.dead or self.state.phase != "HAUNT_PHASE" or player.attack_used:
            return []
        if player.frog:
            return []  # p14：青蛙不能攻击
        if ranged:
            return self.available_ranged_targets(player)
        room = self.current_room(player)
        targets: list[object] = []
        controlled = set(self._haunt_flags().get("controlled_ids", []) or [])
        for other in self.state.players:
            if other.id == player.id or other.dead:
                continue
            if other.role == player.role and other.id not in controlled:
                continue
            # 剧本 6：被精神控制的英雄可以被任何人攻击（同阵营也能打，
            # 打赢是解救，p17）。其余情况维持"只打敌对阵营"。
            if other.room_key == player.room_key:
                targets.append(other)
        for monster in self.state.monsters:
            if monster.room_key == player.room_key and not self._monster_invulnerable(monster):
                targets.append(monster)
        return targets

    def available_ranged_targets(self, player: Player | None = None) -> list[object]:
        player = player or self.current_player
        if player.dead or self.state.phase != "HAUNT_PHASE" or player.attack_used or player.frog:
            return []
        room = self.current_room(player)
        targets: list[object] = []
        for other in self.state.players:
            if other.id == player.id or other.dead or other.role == player.role:
                continue
            if self._has_line_of_sight(room.key, other.room_key):
                targets.append(other)
        for monster in self.state.monsters:
            if self._has_line_of_sight(room.key, monster.room_key) and not self._monster_invulnerable(monster):
                targets.append(monster)
        return targets

    def _derive_attack_params(self, attacker: Player, target: object, weapon_card_id: str | None, ranged: bool):
        """推导一次攻击的确定性参数（远程否 / 攻击属性 / 武器 / 加值）。

        执行（attack）与合法性查询（_attack_gates_pass / attack_would_be_allowed）
        共用本方法，保证"能不能打"的预测与真实执行走同一份推导，不会漂移。
        返回 None 表示武器非法（不存在或未持有），闸门据此判否。
        """
        attack_attr = "might"
        weapon: Card | None = None
        if weapon_card_id:
            weapon = self.catalog.cards.get(weapon_card_id)
            if weapon is None or weapon_card_id not in attacker.items:
                return None
            if "ranged" in weapon.tags:
                ranged = True
            # 标签优先级与执行路径一致：knowledge → sanity → speed，后写覆盖。
            if "knowledge" in weapon.tags:
                attack_attr = "knowledge"
            if "sanity" in weapon.tags:
                attack_attr = "sanity"
            if "speed" in weapon.tags:
                attack_attr = "speed"
            attack_bonus = self._attack_bonus_from_inventory(attacker, weapon_card_id)
        else:
            attack_bonus = self._attack_bonus_from_inventory(attacker, None)
        # 剧本可覆盖攻击属性（剧本 11 雾中人影 / 剧本 19 持戒理智攻击驯兽师）。
        override_attr = self._mode_handler().attack_attr_override(
            self, attacker, target, attack_attr
        )
        if override_attr:
            attack_attr = override_attr
        if not isinstance(target, Player):
            # 剧本可给攻击骰加值（剧本 15 p26：持矛对巨龙 +4）。
            attack_bonus += self._mode_handler().attack_roll_bonus(self, attacker, target)
        return (ranged, attack_attr, weapon, attack_bonus)

    def _attack_gates_pass(self, attacker: Player, target: object, weapon_card_id: str | None, ranged: bool = False, ignore_position: bool = False, log: bool = True) -> bool:
        """攻击的确定性前置检查（与 attack 执行同源）。

        所有"能不能打"的判定集中在此：phase/frog/attack_used、剧本 handler 的
        attack_allowed 闸门、房间邻接或视线（LOS）、怪物无敌、武器合法性与
        怪物免疫（immune_to）。bot 通过 attack_would_be_allowed 复用同一逻辑，
        不再自己复刻一份会漂移的副本。
        ignore_position=True 时跳过"邻接/LOS"闸门，用于"若该玩家与怪物同室能否
        伤到它"这类不依赖当前位置的预判（追击 / 走位评分）。
        log=False 时只做判定不写日志——bot 在决策阶段大量查询，必须避免污染
        对局日志（真实执行路径 attack() 始终用 log=True）。
        """
        if attacker.dead or attacker.attack_used or self.state.phase != "HAUNT_PHASE":
            return False
        if attacker.frog:
            if log:
                self._log("青蛙不能攻击。")
            return False
        # 剧本可禁止攻击（如剧本 2 p13：降灵会完成前谁都不许动手）。
        # 查询路径（bot 的 attack_would_be_allowed，log=False）要把"这是预判、
        # 不是真打"告诉剧本：31 号攻大脑前须掷理智 4+，掷骰与"回合就此结束"
        # 都是真打才许发生的副作用——放在预判里会反复掷骰、清空移动力、刷日志
        # （实测一局 80-120 行"只有长矛能伤到心脏"噪声，机器人还会在评分阶段
        # 被自己的查询冻结）。瞬态标记只在本调用期间有效；不读它的剧本行为不变。
        self._attack_query = not log
        try:
            allowed = self._mode_handler().attack_allowed(self, attacker, target)
        finally:
            self._attack_query = False
        if not allowed:
            if log:
                self._log(f"{attacker.name} 此刻不能攻击。")
            return False
        attacker_room = self.current_room(attacker)
        target_room_key = target.room_key
        if not ignore_position:
            if not ranged and not self.entities_share_room(attacker, target):
                return False
            if ranged and attacker_room.key == target_room_key and not self.entities_share_room(attacker, target):
                return False
            if ranged and not self._has_line_of_sight(attacker_room.key, target_room_key):
                return False
        if not isinstance(target, Player) and self._monster_invulnerable(target):
            if log:
                self._log(f"{target.name} 目前无法被攻击。")
            return False
        params = self._derive_attack_params(attacker, target, weapon_card_id, ranged)
        if params is None:
            return False
        if weapon_card_id and not self.item_action_available(weapon_card_id):
            return False
        _ranged, attack_attr, weapon, attack_bonus = params
        if (isinstance(target, Monster) and target.present_traits is not None
                and attack_attr not in target.present_traits and getattr(target, attack_attr, 0) == 0):
            if log:
                self._log(f"{target.name} 没有 {attack_attr} 属性，不能用该属性攻击。")
            return False
        # 怪物免疫：immune_to 列出的攻击属性对它无效（p17/p88：外星人免疫
        # 速度攻击如左轮；剧本 1 木乃伊同理；剧本 11 雾中人影免疫力量/速度）。
        if not isinstance(target, Player):
            specs = self._haunt_rule_state().get("monster_specs", {}).get(
                getattr(target, "template_id", ""), {}
            )
            immune = set(specs.get("immune_to", []) or [])
            if attack_attr in immune or f"{attack_attr}_attack" in immune:
                if log:
                    self._log(f"{target.name} 免疫{ {'might': '力量', 'speed': '速度', 'sanity': '理智', 'knowledge': '知识'}[attack_attr] }攻击。")
                return False
        return True

    def attack_would_be_allowed(self, attacker: Player, target: object, weapon_card_id: str | None = None, ignore_position: bool = False) -> bool:
        """bot 用：预测"该玩家能否合法攻击该目标"，与真实执行同源。

        不传 ranged —— 远程与否由武器标签决定，正好契合"用现有武器或空手
        至少有一种方式合法"的判定需求。
        """
        return self._attack_gates_pass(attacker, target, weapon_card_id, ranged=False, ignore_position=ignore_position, log=False)

    def attack(self, attacker: Player, target: object, weapon_card_id: str | None = None, ranged: bool = False) -> bool:
        # 确定性前置检查与 bot 查询方法同源（见 _attack_gates_pass）。
        if not self._attack_gates_pass(attacker, target, weapon_card_id, ranged):
            return False
        # 闸门已通过，重新推导执行所需参数；与闸门共用 _derive_attack_params，
        # 保证攻击属性推导只有一份实现，不会与查询漂移。
        _ranged, attack_attr, weapon, attack_bonus = self._derive_attack_params(
            attacker, target, weapon_card_id, ranged
        )
        ranged = _ranged
        if isinstance(target, Player):
            # 剧本 6：被控英雄不能被外星人"攻击受伤"之外的手段打死这里不拦；
            # 但被控者可以被打（解救），见 _apply_attack_damage 的半伤解控。
            defense_attr = attack_attr
            target_name = self._player_label(target)
            if self._mode_handler().defense_roll_disabled(
                self, attacker, target, weapon_card_id
            ):
                # 剧本 41 p123：隐形叛徒的偷袭"Your opponent can't defend
                # against this"——防守方不掷骰，攻击骰直接当伤害。
                target_roll = 0
                self._log(f"{target_name} 来不及反应——攻击从暗处袭来。")
            else:
                # 剧本可规定"防守方按固定骰数结算"（剧本 52 p134：叛徒总是以
                # 3 骰防守，与自身属性和攻击者所用武器无关）。钩子返回 None
                # （所有未实现它的剧本）时走原来的常规掷骰，行为不变。
                fixed_defense = self._mode_handler().defense_roll_override(
                    self, attacker, target, weapon_card_id
                )
                if fixed_defense is None:
                    target_roll = self._roll_attack(target, defense_attr)
                else:
                    target_roll = int(fixed_defense)
        else:
            defense_attr = attack_attr
            target_name = target.name
            target_roll = self._roll_monster_attack(target, defense_attr)

        attacker_roll = self._roll_attack(attacker, attack_attr, attack_bonus)
        self._log(f"{self._player_label(attacker)} 攻击 {target_name}：{attacker_roll} 对 {target_roll}。")
        if attacker_roll == target_roll:
            self._log("平手，没有伤害。")
            if weapon is not None:
                self._resolve_attack_weapon_use(attacker, weapon)
            attacker.attack_used = True
            return True
        diff = abs(attacker_roll - target_roll)
        attacker_wins = attacker_roll > target_roll
        if attacker_wins:
            # 剧本可接管击杀结算（剧本 5 p15：银弹打中狼人/狼犬即死）。
            if self._mode_handler().attack_kill_override(self, attacker, target, weapon):
                if weapon is not None:
                    self._resolve_attack_weapon_use(attacker, weapon)
                attacker.attack_used = True
                self.check_victory()
                return True
            # 剧本可定义特殊偷取（剧本 19 p30：>2 点伤害改为偷走长矛，
            # 让驯兽师恢复神智——英雄的胜利条件）。
            if (
                isinstance(target, Player) and not ranged and diff > 2
                and self._mode_handler().special_steal(self, attacker, target, diff, attack_attr)
            ):
                if weapon is not None:
                    self._resolve_attack_weapon_use(attacker, weapon)
                attacker.attack_used = True
                self.check_victory()
                return True
            if isinstance(target, Player) and not ranged and diff >= 2 and self._can_steal(target):
                # 机器人不会自己弹窗。剧本可以用 duck-typed `bot_wants_steal`
                # 指定"该抢哪一件"——39 号继承人的胜线是从叛徒手里夺回戒指/
                # 长矛，而机器人默认"赢下战斗照常结算伤害、从不偷牌"，
                # 关键牌攥在敌人手上就永远赢不了。返回 None → 沿用默认不偷；
                # 人类玩家的确认框不受影响。
                wanted = self._bot_steal_choice(attacker, target)
                if wanted or self.prompter.confirm("偷窃", f"造成了 {diff} 点伤害。要改为偷取物品吗？"):
                    self._steal_from_target(attacker, target, prefer=wanted)
                    if weapon is not None:
                        self._resolve_attack_weapon_use(attacker, weapon)
                    attacker.attack_used = True
                    return True
            self._apply_attack_damage(target, diff, attack_attr, attacker=attacker, weapon_id=weapon_card_id or "")
            if isinstance(target, Player):
                # 剧本可在英雄被击中后追加副作用（剧本 5 p14：被叛徒打中即感染）。
                self._mode_handler().on_hero_damaged(self, attacker, target)
        else:
            if ranged:
                # p20 词汇表："当你攻击骰结果低于对手时不受到伤害"——远程攻击
                # 落败免伤对玩家与怪物目标一视同仁。
                self._log(f"{target_name} 反击成功，但远程攻击不会让攻击者受伤。")
            elif self._mode_handler().attack_loss_damage_disabled(self, attacker, target):
                self._log(f"{target_name} 反击了，但没能伤到 {attacker.name}。")
            elif isinstance(target, Monster) and self._mode_handler().monster_counterattack_disabled(self, target):
                self._log(f"{target_name} 反击了，但昏迷中使不上力。")
            else:
                self._apply_attack_damage(attacker, diff, attack_attr, attacker=target, weapon_id="")
                self._log(f"{target_name} 反击成功。")
        if weapon is not None:
            self._resolve_attack_weapon_use(attacker, weapon)
        attacker.attack_used = True
        # 剧本可对"攻击结束"做后处理（剧本 12 p23：与自己的双胞胎交手，
        # 无论谁赢都要额外掉 1 点各属性）。
        self._mode_handler().on_attack_resolved(self, attacker, target, attacker_wins)
        self.check_victory()
        return True

    def _resolve_attack_weapon_use(self, attacker: Player, weapon: Card) -> None:
        self._mark_item_action(weapon.id, "use")
        self._deal_attack_weapon_cost(attacker, weapon)
        if weapon.one_shot:
            self._discard_card_from_player(attacker, weapon.id, return_to_room=False)

    def _deal_attack_weapon_cost(self, attacker: Player, weapon: Card) -> None:
        self_damage = int(weapon.data.get("self_damage", 0))
        if self_damage > 0:
            self._deal_damage(attacker, "physical", self_damage, source=weapon.name)

    def _roll_attack(self, player: Player, attr: str, bonus: int = 0) -> int:
        dice = self._effective_stat(player, attr) + bonus + self._check_bonus(player, attr)
        dice = max(1, min(8, dice))
        return self.roll_dice(dice, "攻击检定")

    def _roll_monster_attack(self, monster: Monster, attr: str, reroll_blanks: bool = False) -> int:
        """掷怪物攻击骰。

        reroll_blanks（剧本 4 p86：蜘蛛每次攻击可把每个空白骰重掷一次）：
        先掷 count 枚 0-2 骰，把掷出 0（空白）的骰子各补掷一次再求和。
        补掷的随机数同样来自引擎 rng，种子回放保持可复现。
        """
        stat = getattr(monster, attr, 0)
        dice = max(1, min(8, stat))
        try:
            values = [self.rng.choice((0, 1, 2)) for _ in range(dice)]
        except Exception:
            values = []
        if reroll_blanks:
            blanks = [i for i, value in enumerate(values) if value == 0]
            for index in blanks:
                try:
                    values[index] = self.rng.choice((0, 1, 2))
                except Exception:
                    break
        total = sum(values)
        try:
            self.prompter.show_dice_roll(values, total, "怪物攻击")
        except Exception:
            pass
        return total

    def _steal_candidates(self, attacker: Player, target: Player) -> list[str]:
        """可偷清单：可交易，且剧本没有挡住拾取（剧本 66：叛徒不能偷圣徽）。"""
        return [
            card_id
            for card_id in target.items
            if self.catalog.cards[card_id].tradeable
            and self.item_action_available(card_id)
            and not self._mode_handler().item_pickup_blocked(self, attacker, card_id)
        ]

    def _can_steal(self, target: Player) -> bool:
        attacker = self.current_player
        return bool(self._steal_candidates(attacker, target))

    def _bot_steal_choice(self, attacker: Player, target: Player) -> str | None:
        """机器人偷窃：剧本可用 duck-typed `bot_wants_steal` 指定该抢哪一件。

        机器人默认不偷（BotDecisionProvider 对"偷窃"一律回否）——"弃伤害改偷牌"
        多数时候是亏的。但"关键牌在敌人手上"的剧本（39 号继承人：戒指常整局攥在
        叛徒手里）不抢就永远赢不了。人类玩家的确认框不受影响。
        """
        if getattr(attacker, "control", "") != "bot":
            return None
        wants_steal = getattr(self._mode_handler(), "bot_wants_steal", None)
        if not callable(wants_steal):
            return None
        card_id = wants_steal(self, attacker, target)
        return str(card_id) if card_id else None

    def _steal_from_target(self, attacker: Player, target: Player, prefer: str | None = None) -> None:
        candidates = self._steal_candidates(attacker, target)
        if not candidates:
            return
        if prefer is not None and prefer in candidates:
            # 剧本点名要抢的那张（机器人不知道自己在偷什么，得有人告诉它）
            steal_id = prefer
        else:
            idx = self.prompter.choose_from_list("偷窃", "要偷哪一件？", [self.catalog.cards[card_id].name for card_id in candidates])
            if idx is None:
                return
            steal_id = candidates[idx]
        target.items.remove(steal_id)
        attacker.items.append(steal_id)
        self._mark_item_action(steal_id, "steal")
        if "companion" in self.catalog.cards[steal_id].tags:
            if steal_id not in attacker.companions:
                attacker.companions.append(steal_id)
            if steal_id in target.companions:
                target.companions.remove(steal_id)
        self._log(f"{attacker.name} 偷走了 {target.name} 的 {self.catalog.cards[steal_id].name}。")

    def _apply_attack_damage(
        self,
        target: object,
        amount: int,
        attack_attr: str,
        attacker: object | None = None,
        weapon_id: str = "",
    ) -> None:
        if amount <= 0:
            return
        self._last_attack_weapon_id = weapon_id
        self._last_attack_attr = attack_attr
        damage_type = "physical" if attack_attr in PHYSICAL_STATS else "mental"
        if isinstance(target, Monster):
            # 剧本可按"谁用什么打的"决定这次击败是直接杀死（剧本 21 p32：
            # 力量武器与炸药能杀死僵尸，其他攻击只能把它打晕）。
            if self._mode_handler().monster_killed_on_defeat(
                self, target, attacker, attack_attr, weapon_id
            ):
                self._kill_monster(target, killer=attacker)
                return
            # 默认是击晕一回合，但剧本可以要求"命中即杀死"——
            # 剧本 2 要求摧毁幽灵、剧本 3 施法后任何成功攻击都杀死女巫。
            # 没有这一步，这些剧本的胜利条件永远无法达成。
            if self._mode_handler().on_monster_defeated(self, target, amount):
                return
            self._stun_monster(target, 1 if amount > 0 else 0)
            return
        # 剧本 6（p17）：攻击被精神控制的同伴并取胜，是"解救"而非伤害——
        # 被救者只受一半伤害（向下取整），并从此免疫精神控制。
        controlled = set(self._haunt_flags().get("controlled_ids", []) or [])
        if isinstance(target, Player) and target.id in controlled:
            amount = amount // 2
            controlled.discard(target.id)
            immune = set(self._haunt_flags().get("immune_ids", []) or [])
            immune.add(target.id)
            self._haunt_flags()["controlled_ids"] = sorted(controlled)
            self._haunt_flags()["immune_ids"] = sorted(immune)
            self._log(f"{target.name} 从精神控制中挣脱了！他将免疫外星人的意念。")
        self._deal_damage(target, damage_type, amount, source="攻击")

    def _has_line_of_sight(self, start_key: str, target_key: str) -> bool:
        if start_key == target_key:
            return True
        start = self.state.board.get(start_key)
        target = self.state.board.get(target_key)
        if not start or not target or start.floor != target.floor:
            return False
        if start.x != target.x and start.y != target.y:
            return False
        graph = self._build_graph()
        return target_key in self._reachable_nodes(start_key, graph)
