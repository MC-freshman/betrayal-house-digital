from __future__ import annotations

from ._imports import Monster, Player, STAT_NAMES, deque

class MonsterRules:
    def _stun_monster(self, monster: Monster, turns: int) -> None:
        monster.stunned_turns += max(1, turns)
        if monster.items:
            self.state.room_items.setdefault(monster.room_key, []).extend(monster.items)
            monster.items.clear()
        self._log(f"{monster.name} 被击晕了。")

    def _monster_pickup_items(self, monster: Monster) -> None:
        if not monster.can_carry_items or monster.stunned_turns > 0:
            return
        cards = self.state.room_items.get(monster.room_key, [])
        for card_id in list(cards):
            card = self.catalog.cards.get(card_id)
            if card and card.tradeable and "companion" not in card.tags:
                cards.remove(card_id)
                monster.items.append(card_id)
        if not cards:
            self.state.room_items.pop(monster.room_key, None)

    def _kill_monster(self, monster: Monster, killer: object | None = None) -> None:
        """把怪物彻底移出对局（区别于 `_stun_monster` 的一回合击晕）。"""
        monster_id = getattr(monster, "id", None)
        self.state.monsters = [m for m in self.state.monsters if getattr(m, "id", None) != monster_id]
        who = getattr(killer, "name", None)
        self._log(f"{who} 摧毁了 {monster.name}。" if who else f"{monster.name} 被摧毁了。")

    def _monster_by_template(self, template_id: str) -> Monster | None:
        return next((monster for monster in self.state.monsters if monster.template_id == template_id), None)

    def _monsters_in_room(self, room_key: str, template_id: str | None = None) -> list[Monster]:
        return [
            monster
            for monster in self.state.monsters
            if monster.room_key == room_key and (template_id is None or monster.template_id == template_id)
        ]

    def _resolve_monster_turns(self) -> None:
        if not self.state.monsters:
            return
        # p18：数个相同类似的怪物（蝙蝠/僵尸）整组只投一次骰，该类型每个怪物
        # 本回合都移动这个格数。键里带 speed —— 剧本会成长/削减个别怪的数值。
        group_steps: dict[tuple[str, int], int] = {}
        for monster in list(self.state.monsters):
            if monster.stunned_turns > 0:
                monster.stunned_turns -= 1
                self._log(f"{monster.name} 因昏迷跳过一回合。")
                continue
            # 剧本可在怪物行动前介入（剧本 7 p89：被拖回根部的英雄被吞噬，
            # 该爬行物随之离场）。返回 True = 本怪物本回合不再行动。
            if self._mode_handler().on_monster_turn_start(self, monster):
                continue
            self._monster_pickup_items(monster)
            target = self._find_monster_target(monster)
            if target is None:
                continue
            path = self._monster_path(monster.room_key, target.room_key)
            if len(path) > 1:
                group_key = (monster.template_id, monster.speed)
                if group_key not in group_steps:
                    group_steps[group_key] = max(1, self.roll_dice(monster.speed, "怪物移动"))
                steps = group_steps[group_key]
                # 剧本可接管移动（例如木乃伊掷出 0/1 时经秘密通道移动）；
                # 返回 False 才走常规的沿最短路径前进。
                if not self._mode_handler().on_monster_move(self, monster, steps):
                    new_index = self._monster_move_index(monster, path, steps)
                    self._move_monster_along_path(monster, path, new_index)
                    self._log(f"{monster.name} 移动到 {self.state.board[monster.room_key].name}。")
                    self._monster_pickup_items(monster)
                    moved_room = self.state.board.get(monster.room_key)
                    if moved_room and moved_room.effect_id == "room_mystic_elevator":
                        self._apply_mystic_elevator(monster, moved_room)
            if monster.room_key == target.room_key:
                room = self.state.board[monster.room_key]
                if self._barrier_config(room):
                    self._set_barrier_side(monster, room, self._barrier_side(target))
                self._monster_attack(monster, target)
        self.check_victory()

    def _monster_move_index(self, monster: Monster, path: list[str], steps: int) -> int:
        """把步数折算成实际前进格数（p17/p22 的"途经对手"对怪物同样生效）。

        作祟开始后，房间里每有一名对手，离开该房间就要额外消耗 1 点移动力；
        无论被拖慢多少，至少可以移动 1 格（p17：怪物投出 0 时也一样）。
        """
        index = 0
        budget = max(1, steps)
        while index + 1 < len(path):
            room = self.state.board.get(path[index])
            cost = 1 + (self._hostile_count_for_monster(monster, path[index]) if room else 0)
            if index == 0:
                index = 1
                budget -= cost
                if budget <= 0:
                    break
                continue
            if cost > budget:
                break
            budget -= cost
            index += 1
        return index

    def _hostile_count_for_monster(self, monster: Monster, room_key: str) -> int:
        """怪物在 room_key 里遇到的对手数（叛徒的怪 = 英雄，反之亦然）。"""
        if self.state.phase != "HAUNT_PHASE":
            return 0
        expected_role = "hero" if monster.controller == "traitor" else "traitor"
        return sum(
            1
            for player in self.state.players
            if not player.dead and player.room_key == room_key and player.role == expected_role
        )

    def _find_monster_target(self, monster: Monster) -> Player | None:
        candidates = [player for player in self.state.players if not player.dead and player.role != "traitor"]
        if monster.controller == "traitor":
            candidates = [player for player in self.state.players if not player.dead and player.role == "hero"]
        if not candidates:
            return None
        candidates.sort(key=lambda player: self._monster_path_length(monster.room_key, player.room_key))
        return candidates[0]

    def _monster_graph(self) -> dict[str, list[str]]:
        """怪物可免伤使用、逆行塌方通道；普通探险者图不增加这些边。"""
        graph = self._build_graph()
        basement = [k for k, r in sorted(self.state.board.items())
                    if r.floor == -1 and not self._is_collapsed(k)]
        for key, room in self.state.board.items():
            if self._is_collapsed(key):
                continue
            destinations = []
            if room.template_id == "collapsed_room":
                below = room.data.get("below_key")
                if below in graph:
                    destinations = [below]
                else:
                    # 第一只选择落下的怪物可以选任意已揭示地下室房，不抽新板块。
                    graph[key] = sorted(set(graph.get(key, [])) | set(basement))
            for below in destinations:
                if below in graph:
                    graph[key] = sorted(set(graph.get(key, [])) | {below})
                    graph[below] = sorted(set(graph[below]) | {key})
        return graph

    def _monster_path(self, start_key: str, target_key: str) -> list[str]:
        graph = self._monster_graph()
        queue = deque([(start_key, [start_key])])
        seen = {start_key}
        while queue:
            key, path = queue.popleft()
            if key == target_key:
                return path
            for neighbor in graph.get(key, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return [start_key]

    def _monster_path_length(self, start_key: str, target_key: str) -> int:
        path = self._monster_path(start_key, target_key)
        return len(path) - 1 if path[-1] == target_key else 9999

    def _move_monster_along_path(self, monster: Monster, path: list[str], index: int) -> None:
        for origin, destination in zip(path[:index], path[1:index + 1]):
            room = self.state.board[origin]
            below = self.state.board[destination]
            if (room.template_id == "collapsed_room" and below.floor == -1
                    and room.data.get("below_key") not in self.state.board):
                room.data["below_key"] = destination
                self.spawn_token("below_collapsed_room", label="塌方下方", role="marker", room_key=destination)
        monster.room_key = path[index]

    def _monster_attack(self, monster: Monster, target: Player) -> None:
        # 剧本可完全接管本回合的攻击（如外星人对同房间所有人的意念攻击——
        # 它是"代替普通攻击"的主动技能，输赢都要结算，不能等命中判定）。
        if self._mode_handler().on_monster_turn_attack(self, monster):
            return
        # 剧本 4 p86：蜘蛛每次攻击可把每个"空白骰"（掷出 0）重掷一次。
        reroll_blanks = bool(self._mode_handler().monster_rerolls_blanks(self, monster))
        monster_roll = self._roll_monster_attack(monster, "might", reroll_blanks=reroll_blanks)
        # 剧本可给主动攻击的怪物加值（剧本 19 p101：熊 +2 / 鳄鱼 +1，
        # 被攻击时不加）。数据声明在 monster_specs 的 initiate_bonus。
        specs = self._haunt_rule_state().get("monster_specs", {}).get(
            getattr(monster, "template_id", ""), {}
        )
        monster_roll += int(specs.get("initiate_bonus", 0) or 0)
        # 剧本可按被攻击者调整怪物的攻击骰（剧本 21 p32：圣徽持有者让
        # 僵尸的力量攻击少掷两枚骰，对僵尸领主无效）。
        monster_roll += self._mode_handler().monster_attack_roll_bonus(self, monster, target)
        target_roll = self._roll_attack(target, "might")
        self._log(f"{monster.name} 攻击 {self._player_label(target)}：{monster_roll} 对 {target_roll}。")
        if monster_roll > target_roll:
            amount = monster_roll - target_roll
            # 剧本可自行结算伤害（例如木乃伊扣速度而非造成物理伤害）；
            # 返回 False 才走默认的物理伤害。
            if not self._mode_handler().on_monster_attack(self, monster, target, amount):
                self._deal_damage(target, "physical", amount, source=monster.name)
            if isinstance(target, Player):
                # 剧本可在英雄被怪物击中后追加副作用（剧本 5 p14：狼犬咬中即感染）。
                self._mode_handler().on_hero_damaged(self, monster, target)
        elif monster_roll < target_roll:
            self._stun_monster(monster, 1)
        else:
            self._log("平手。")

    def _spawn_single_haunt_monster(self, spec: dict, room_key: str) -> Monster | None:
        template_id = spec.get("template_id")
        if not template_id or template_id not in self.catalog.monsters:
            return None
        template = self.catalog.monsters[template_id]
        monster = Monster(
            id=f"mon_{self._next_monster_id}",
            template_id=template.id,
            name=spec.get("name", template.name),
            speed=int(spec.get("speed", template.speed)),
            might=int(spec.get("might", template.might)),
            sanity=int(spec.get("sanity", template.sanity)),
            knowledge=int(spec.get("knowledge", template.knowledge)),
            room_key=room_key,
            controller=spec.get("controller", "traitor"),
            stunned_turns=0,
            can_carry_items=bool(spec.get("can_carry_items", template.can_carry_items)),
            tags=tuple(spec.get("tags", template.tags)),
            present_traits=tuple(sorted(set(template.present_traits or STAT_NAMES)
                                        | (set(spec) & set(STAT_NAMES)))),
        )
        self._next_monster_id += 1
        self.state.monsters.append(monster)
        self._log(f"怪物出现：{monster.name}。")
        return monster
