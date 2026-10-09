"""HellOnEarthMode（剧本 66）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class HellOnEarthMode(GenericModeHandler):
    """剧本 66 人间地狱（Hell on Earth）。

    权威原文：英雄手册 p77 / 叛徒手册 p148。
    · 力量轨道从 0 起、上限 8。
    · 充能代替攻击：小教堂、图书馆或圣徽所在房间做理智检定；4–7 +1，8+ +2。
    · 持徽者本回合充能后可封闭当前房间（轨道 ≥1 时 -1，放封印令牌）。
    · 只能用圣徽打恶魔领主：骰数 = 当前轨道，对方用理智防守；未胜过则无事发生。
    · 封闭房打胜 → 驱逐、英雄胜；未封闭则击退（差值为步数）或击晕（扣开局英雄数格轨道）。
    · 叛徒仍在场，不能拾取/偷窃圣徽；神秘电梯对双方都拒绝移动。
    · 恶魔领主属性随人数：3p Speed 3 Might 5 Sanity 3；4p 4/5/4；5p 5/6/5；6p 6/6/6。
    · 领主能摸到持徽英雄时必须打他，否则必须打得到的英雄；主动攻击落败不击晕。
    已知简化：击退方向由 bot 固定策略（远离持徽英雄/最近英雄）；人类的击退/击晕选择未接 prompter；
    圣徽若开局不在场则补发给揭示者（揭示者是叛徒则发给第一名英雄）；
    引擎每回合只能做一次剧本行动，持徽者充能成功且轨道仍 ≥1 时会立刻封闭当前房间
    （原文是本回合内可另选封闭，这里把两步并进同一次行动）。
    bot 战术（`bot_stay_in_room` / `bot_action_blocked`）：持徽者与同房队友**站住充能**
    ——站住才能让力量只增不减（旧行为每回合换房，充能 +1 立刻被封闭新房的 -1 抵掉，
    力量恒在 2 上下、圣徽攻击必输）；封闭房里领主就在眼前时必须出手（`charge` 与
    `attack` 的 bot 打分相同，不挡就会永远充能）。非持徽英雄去与持徽者会合。
    """

    mode = "hell_on_earth"
    LORD = "hell_demon_lord"
    HOLY = "omen_holy_symbol"
    CHARGE_ROOMS = ("chapel", "library")
    STATS = {
        3: (3, 5, 3),
        4: (4, 5, 4),
        5: (5, 6, 5),
        6: (6, 6, 6),
    }

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["sealed_rooms"] = []
        flags["prayed_this_turn"] = None
        flags["initial_hero_count"] = sum(
            1 for p in engine.state.players if p.role == "hero" and not p.dead
        )
        engine._set_haunt_track_value("holy_power", 0)

        # 骨架可能已按旧 monsters 表刷出 giant/cultist，清掉后按原文放领主。
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "template_id", "") == self.LORD
        ]
        if engine._monster_by_template(self.LORD) is None:
            spawn_key = self._pick_lord_room(engine, room_key)
            n = max(3, min(6, len(engine.state.players)))
            speed, might, sanity = self.STATS[n]
            spec = {
                "template_id": self.LORD,
                "name": "恶魔领主",
                "speed": speed,
                "might": might,
                "sanity": sanity,
            }
            engine._spawn_single_haunt_monster(spec, spawn_key)

        if not engine._card_is_controlled(self.HOLY):
            holder = next(
                (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id and p.role == "hero" and not p.dead),
                None,
            )
            if holder is None:
                holder = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if holder is not None:
                engine._grant_card_to_player(holder, self.HOLY)

        engine._log("火焰一闪，虚空裂开——恶魔领主踏进了这栋房子。")

    def on_turn_start(self, engine, player):
        engine._haunt_flags()["prayed_this_turn"] = None

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            if aid == "charge_holy_symbol" and not self._can_charge(engine, player):
                continue
            if aid == "seal_room" and not self._can_seal(engine, player):
                continue
            if aid == "holy_symbol_attack" and not self._can_holy_attack(engine, player):
                continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        if action_id == "charge_holy_symbol":
            return self._charge(engine, player)
        if action_id == "seal_room":
            return self._seal(engine, player)
        if action_id == "holy_symbol_attack":
            return self._holy_attack(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def attack_allowed(self, engine, attacker, target):
        if getattr(target, "template_id", "") == self.LORD:
            return False
        return True

    def mystic_elevator_blocked(self, engine, player):
        return True

    def item_pickup_blocked(self, engine, player, card_id):
        return card_id == self.HOLY and getattr(player, "role", "") == "traitor"

    def item_trade_blocked(self, engine, giver, target, card_id):
        return card_id == self.HOLY and getattr(target, "role", "") == "traitor"

    def on_monster_defeated(self, engine, monster, amount):
        # 普通攻击打不中领主（attack_allowed 已拦）；这里兜底：领主被击败时不走默认击晕。
        return getattr(monster, "template_id", "") == self.LORD

    def on_monster_turn_start(self, engine, monster):
        """整回合接管：先追持徽英雄（够得着就必须打他），再结算力量攻击。"""
        if getattr(monster, "template_id", "") != self.LORD:
            return False
        target = self._lord_target(engine, monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = max(1, engine.roll_dice(getattr(monster, "speed", 3), "恶魔领主移动"))
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        if monster.room_key == target.room_key:
            self._lord_might_attack(engine, monster, target)
        return True

    def on_monster_move(self, engine, monster, rolled):
        if getattr(monster, "template_id", "") != self.LORD:
            return False
        return True

    def on_monster_turn_attack(self, engine, monster):
        return getattr(monster, "template_id", "") == self.LORD

    def _lord_might_attack(self, engine, monster, target):
        monster_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(target, "might")
        engine._log(f"{monster.name} 攻击 {engine._player_label(target)}：{monster_roll} 对 {hero_roll}。")
        if monster_roll > hero_roll:
            engine._deal_damage(target, "physical", monster_roll - hero_roll, source=monster.name)
        elif monster_roll < hero_roll:
            # p148：领主主动攻击时被击败不击晕。
            engine._log(f"{monster.name} 被挡住了，但没有被击晕。")
        else:
            engine._log("平手。")

    def bot_stay_in_room(self, engine, player):
        """#66：站住不动，圣徽力量才会累积。

        实测（seed3/4p）：持徽者每回合换一间房 → 每次充能成功得到的 +1 立刻
        被用来封闭这间新房（封闭要扣 1），力量永远停在 2 上下，圣徽攻击必输
        （英雄 0/33 胜）。站住以后所在房已封闭、无法重复封闭，力量只增不减；
        领主会自己送上门（p148：够得着就必须打持徽者），届时在封闭房里出手。
        """
        if player.role != "hero" or player.dead:
            return False
        return self._holy_in_room(engine, player.room_key)

    def bot_action_blocked(self, engine, player, action_id):
        """#66：英雄胜线只有一条——在**封闭房间**里用圣徽打赢领主。

        `charge_holy_symbol`（持徽者在任何房间都能充能）与
        `holy_symbol_attack` 的 bot 打分相同（标签都不含打分器的加分词），
        `max()` 取列表靠前者 → bot 永远充能、从不攻击（实测英雄 0/33 胜、
        每局 `holy_symbol_attack` 出现却一次没用）。这里在"封闭房里领主就在
        眼前、骰数也够看"时挡住充能，逼它出手；力量仍不足时允许继续充能攒力。
        """
        if action_id != "charge_holy_symbol":
            return False
        if not self._can_holy_attack(engine, player):
            return False
        sealed = set(engine._haunt_flags().get("sealed_rooms") or [])
        # 封闭房里的每一次攻击都是"赢了就结束"的成败手；领主每回合都在打
        # 持徽者，与其挨打攒力不如连续出手（圣徽力量不会因失败下降）。
        return player.room_key in sealed

    def bot_goal_rooms(self, engine, player):
        if player.role != "hero" or player.dead:
            return []
        holder = self._holy_holder(engine)
        if holder is None:
            goals = [
                f"__room__{room_key}"
                for room_key, cards in engine.state.room_items.items()
                if self.HOLY in cards
            ]
            return goals or [f"__room__{self.CHARGE_ROOMS[0]}"]
        if holder.id != player.id:
            # 队友去和持徽者会合（护送圣徽）。
            return [f"__room__{holder.room_key}"]
        # 我是持徽者：**站住充能**。持徽者在任何房间都能充能，而充能成功会
        # 立刻把所在房封闭（原文的"充能后可封闭"由 handler 并进同一行动）。
        # 旧逻辑让持徽者跑去追领主所在的**未封闭**房间，打赢也只能击退/击晕，
        # 永远够不到"封闭房驱逐"这条唯一胜线（实测英雄 0/33）。
        return [f"__room__{player.room_key}"]

    def progress_summary(self, engine, viewer):
        flags = engine._haunt_flags()
        power = engine._haunt_track_value("holy_power")
        sealed = flags.get("sealed_rooms") or []
        lines = [f"圣徽力量 {power}/8", f"已封闭房间 {len(sealed)}"]
        holder = self._holy_holder(engine)
        if holder is not None:
            lines.append(f"圣徽持有者：{holder.name}")
        return lines

    def check_victory(self, engine):
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也倒下了——人间成了地狱。")
            return True
        if engine.state.winner:
            return True
        # p77：英雄只能靠封闭房驱逐取胜。拦截引擎默认的「叛徒倒下 = 英雄胜」。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 内部

    def _can_charge(self, engine, player):
        if player.role != "hero" or player.dead or getattr(player, "attack_used", False):
            return False
        room = engine.state.board.get(player.room_key)
        if room is None:
            return False
        if room.template_id in self.CHARGE_ROOMS:
            return True
        return self._holy_in_room(engine, player.room_key)

    def _can_seal(self, engine, player):
        if player.role != "hero" or player.dead:
            return False
        if engine._haunt_flags().get("prayed_this_turn") != player.id:
            return False
        if self._holy_holder(engine) is not player:
            return False
        if engine._haunt_track_value("holy_power") < 1:
            return False
        sealed = set(engine._haunt_flags().get("sealed_rooms") or [])
        return player.room_key not in sealed

    def _can_holy_attack(self, engine, player):
        if player.role != "hero" or player.dead or getattr(player, "attack_used", False):
            return False
        if self._holy_holder(engine) is not player:
            return False
        if engine._haunt_track_value("holy_power") < 1:
            return False
        lord = engine._monster_by_template(self.LORD)
        return lord is not None and lord.room_key == player.room_key

    def _charge(self, engine, player):
        if not self._can_charge(engine, player):
            return False
        dice = max(1, min(8, engine._effective_stat(player, "sanity") + engine._check_bonus(player, "sanity")))
        roll = engine.roll_dice(dice, "为圣徽充能")
        engine._log(f"{player.name} 为圣徽祈祷，掷出 {roll}。")
        gain = 0
        if roll >= 8:
            gain = 2
        elif roll >= 4:
            gain = 1
        if gain:
            value = engine._advance_haunt_track("holy_power", gain)
            engine._log(f"圣徽力量升到 {value}。")
        else:
            engine._log("祈祷没有唤来力量。")
        player.attack_used = True
        if self._holy_holder(engine) is player:
            engine._haunt_flags()["prayed_this_turn"] = player.id
            # 引擎每回合只能做一次剧本行动，持徽者充能后立刻封闭当前房间。
            if self._can_seal(engine, player):
                self._seal(engine, player)
        return True

    def _seal(self, engine, player):
        if not self._can_seal(engine, player):
            return False
        power = engine._haunt_track_value("holy_power")
        engine._set_haunt_track_value("holy_power", power - 1)
        sealed = engine._haunt_flags().setdefault("sealed_rooms", [])
        sealed.append(player.room_key)
        room = engine.state.board[player.room_key]
        engine.spawn_token("seal", label="封印", role="marker", room_key=player.room_key)
        engine._log(f"{player.name} 封闭了 {room.name}（圣徽力量 {power - 1}）。")
        return True

    def _holy_attack(self, engine, player):
        if not self._can_holy_attack(engine, player):
            return False
        lord = engine._monster_by_template(self.LORD)
        power = engine._haunt_track_value("holy_power")
        hero_roll = engine.roll_dice(power, "圣徽攻击")
        lord_roll = engine._roll_monster_attack(lord, "sanity")
        engine._log(f"{player.name} 用圣徽攻击恶魔领主：{hero_roll} 对 {lord_roll}。")
        player.attack_used = True
        if hero_roll <= lord_roll:
            engine._log("圣徽没有压住恶魔领主。")
            return True
        diff = hero_roll - lord_roll
        sealed = set(engine._haunt_flags().get("sealed_rooms") or [])
        if player.room_key in sealed:
            engine._kill_monster(lord, killer=player)
            engine._set_winner("heroes", "恶魔领主被圣徽从凡间驱逐了。")
            engine.check_victory()
            return True
        self._repel_or_stun(engine, player, lord, diff)
        return True

    def _repel_or_stun(self, engine, player, lord, diff):
        """未封闭房间打胜：击晕要扣开局英雄数格轨道，不够就击退。"""
        flags = engine._haunt_flags()
        hero_count = max(1, int(flags.get("initial_hero_count") or 1))
        power = engine._haunt_track_value("holy_power")
        if power >= hero_count:
            engine._set_haunt_track_value("holy_power", max(0, power - hero_count))
            engine._stun_monster(lord, 1)
            engine._log(f"恶魔领主被击晕了（圣徽力量 {max(0, power - hero_count)}）。")
            return
        self._repel_lord(engine, player, lord, diff)
        engine._log(f"恶魔领主被击退了 {diff} 格。")

    def _repel_lord(self, engine, player, lord, diff):
        holder = self._holy_holder(engine) or player
        graph = engine._build_graph()
        start = lord.room_key
        best = start
        best_score = engine._path_length(start, holder.room_key)
        frontier = {start}
        visited = {start}
        for _ in range(max(1, int(diff))):
            nxt = set()
            for key in frontier:
                for neigh in graph.get(key, ()):
                    if neigh in visited:
                        continue
                    visited.add(neigh)
                    nxt.add(neigh)
                    score = engine._path_length(neigh, holder.room_key)
                    if score > best_score or (score == best_score and neigh > best):
                        best_score = score
                        best = neigh
            if not nxt:
                break
            frontier = nxt
        lord.room_key = best

    def _pick_lord_room(self, engine, fallback):
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return fallback
        best = fallback
        best_min = -1
        for key in sorted(engine.state.board.keys()):
            distances = [engine._path_length(key, p.room_key) for p in heroes]
            if any(d >= 9999 for d in distances):
                continue
            min_d = min(distances)
            if min_d > best_min or (min_d == best_min and key > best):
                best_min = min_d
                best = key
            if min_d >= 3 and best_min >= 3:
                # 继续找同样 ≥3 里字典序稳定的最远最小距离
                continue
        return best

    def _holy_holder(self, engine):
        return next((p for p in engine.state.players if self.HOLY in p.items and not p.dead), None)

    def _holy_in_room(self, engine, room_key):
        cards = engine.state.room_items.get(room_key, [])
        if self.HOLY in cards:
            return True
        return any(self.HOLY in p.items and p.room_key == room_key and not p.dead for p in engine.state.players)

    def _lord_target(self, engine, monster):
        holder = self._holy_holder(engine)
        speed = max(1, int(getattr(monster, "speed", 1)))
        if holder is not None:
            dist = engine._path_length(monster.room_key, holder.room_key)
            if dist <= speed:
                return holder
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return None
        heroes.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
        return heroes[0]
