from __future__ import annotations

from ._imports import ActionCommand, GameEngine, Monster, Player

class CombatDecisions:
    def _try_attack(self, engine: GameEngine, player: Player) -> bool:
        if player.attack_used or engine.state.phase != "HAUNT_PHASE":
            return False
        if player.bot_difficulty == "easy" and engine.rng.random() < 0.35:
            return False
        profile = self._side_profile(engine, player)
        choices: list[tuple[int, object, str | None, bool]] = []
        # 被某只怪"抓着/贴附"时先打它：打别的怪再多次也脱不了身。
        # 7 号实测：英雄被 mon_3 抓住，却按列表顺序一直打 mon_1，在入口
        # 大厅被钉了 180 回合（p18 明确"攻击抓着你的尖端，赢了就松手"）。
        captor = None
        captor_hook = getattr(engine._mode_handler(), "bot_captor_monster", None)
        if callable(captor_hook):
            captor = captor_hook(engine, player)
        weapon_ids: list[str | None] = [None] + engine.available_attack_weapons(player)
        for weapon_id in weapon_ids:
            ranged = False
            bonus = 0
            if weapon_id:
                weapon = engine.catalog.cards[weapon_id]
                ranged = "ranged" in weapon.tags
                bonus = weapon.bonus.get("attack", 0)
            targets = engine.available_attack_targets(player, ranged=ranged)
            for target in self._filter_attack_targets(engine, player, targets, profile):
                # 同源查询：剔除该 (目标, 武器) 组合本身不合法的情形
                # （如怪物免疫此属性、剧本 handler 闸门），避免白送攻击/白跑。
                if not engine.attack_would_be_allowed(player, target, weapon_id):
                    continue
                margin, safe_loss = self._combat_margin(engine, player, target, weapon_id)
                can_retreat = self._retreat_available(engine, player) and any(
                    option.target_key in engine.state.board
                    and self._room_threat(engine, player, option.target_key)
                    < self._room_threat(engine, player, player.room_key)
                    for option in engine.available_move_options(player)
                ) if player.role == "hero" and margin < -2 else False
                if player.role == "hero" and margin < -2 and not safe_loss and target is not captor and can_retreat:
                    continue
                score = self._target_score(engine, player, target, profile) + bonus
                score += 5 * margin
                # 剧本可给"该用哪件武器打这个目标"加权（duck-typed
                # `bot_weapon_bonus`，默认不实现 → 行为不变）。48 号 p59：
                # 只有那把诅咒武器能永久杀死血腥杰克，别的打法只会让他更强地回来。
                preference = getattr(engine._mode_handler(), "bot_weapon_bonus", None)
                if callable(preference):
                    score += int(preference(engine, player, target, weapon_id) or 0)
                if captor is not None and target is captor:
                    score += 200
                if ranged:
                    score += 3
                choices.append((score, target, weapon_id, ranged))
        if not choices:
            return False
        score, target, weapon_id, ranged = max(choices, key=lambda item: item[0])
        if player.bot_difficulty == "easy" and score < 95:
            return False
        ok = engine.execute_command(
            ActionCommand(
                "attack",
                player.id,
                {"target": target, "weapon_card_id": weapon_id, "ranged": ranged},
            )
        )
        if ok:
            # 集火：记录本玩家实际攻击的目标，供 _target_score 后续集中火力。
            # 只存不可变的标识（怪物 template_id / 玩家 id），不存对象引用，
            # 因为 bot_focus 会进 haunt_rule 存档。
            focus = engine._haunt_rule_state().setdefault("bot_focus", {})
            if isinstance(target, Monster):
                focus[player.role] = "monster:" + str(target.id)
            elif isinstance(target, Player):
                focus[player.role] = target.id
        return ok

    def _combat_margin(self, engine, player, target, weapon_id=None):
        """与引擎共用攻击属性和加骰规则；只读预测，不提前掷骰。"""
        params = engine._derive_attack_params(player, target, weapon_id, False)
        if params is None:
            return -8, False
        ranged, attr, _weapon, bonus = params
        attack = max(1, min(8, engine._effective_stat(player, attr) + bonus + engine._check_bonus(player, attr)))
        handler = engine._mode_handler()
        if isinstance(target, Player):
            fixed = handler.defense_roll_override(engine, player, target, weapon_id)
            defense = (max(1, min(8, engine._effective_stat(target, attr) + engine._check_bonus(target, attr)))
                       if fixed is None else int(fixed))
            if handler.defense_roll_disabled(engine, player, target, weapon_id):
                defense = 0
        else:
            defense = max(1, min(8, getattr(target, attr, 0)))
        return attack - defense, bool(ranged or handler.attack_loss_damage_disabled(engine, player, target))

    def _room_threat(self, engine, player, room_key):
        if player.role != "hero" or engine.state.phase != "HAUNT_PHASE":
            return 0
        enemies = [m for m in engine.state.monsters if m.room_key == room_key
                   and m.stunned_turns <= 0 and getattr(m, "controller", "traitor") != player.role]
        enemies += [p for p in engine.state.players if p.room_key == room_key
                    and p.role == "traitor" and not p.dead]
        threat = 0
        for enemy in enemies:
            if isinstance(enemy, Monster):
                attr = "sanity" if enemy.might <= 0 and enemy.sanity > 0 else "might"
                attack = max(1, min(8, getattr(enemy, attr, 0)))
                attack += engine._mode_handler().monster_attack_roll_bonus(engine, enemy, player)
            else:
                attr = "might"
                attack = max(1, min(8, enemy.stats.get(attr, 0) + engine._attack_bonus_from_inventory(enemy, None)))
            defense = max(1, min(8, player.stats.get(attr, 0) + engine._check_bonus(player, attr)))
            threat = max(threat, max(0, attack - defense))
        return threat

    def _retreat_signature(self, engine, player):
        enemies = sorted("monster:" + str(m.id) for m in engine.state.monsters
                         if m.room_key == player.room_key and m.stunned_turns <= 0
                         and m.controller != player.role)
        enemies += sorted("player:" + str(p.id) for p in engine.state.players
                          if p.room_key == player.room_key and not p.dead and p.role != player.role)
        return repr((enemies, sorted(player.stats.items()), sorted(player.items)))

    def _retreat_available(self, engine, player):
        # 战力未变时对同批敌人只撤一次，防止双方不推进胜利的反复绕圈。
        return (self._room_threat(engine, player, player.room_key) >= 3
                and self._retreat_signature(engine, player)
                not in engine.state.meta.get("bot_retreats", {}).get(str(player.id), []))

    def _filter_attack_targets(self, engine: GameEngine, player: Player, targets: list[object], profile: dict) -> list[object]:
        filtered: list[object] = []
        # 英雄默认不主动攻击同阵营玩家（除非 profile 允许）。
        hero_attacks_traitor = profile.get("attack_traitor_players", False)
        weapon_ids = [None] + engine.available_attack_weapons(player)
        # 剧本可禁用特定目标（duck-typed `bot_attack_blocked`，默认不禁）。
        # 29 号实测：`attack_monsters: False` 只挡住了"追怪"的走位，挡不住
        # 攻击本身——英雄被怪物堵在同一间房里就空手开打（1 对 13），
        # 反手吃 12 点反击当场倒下。真人不会拿拳头去捶力 8 的弗兰肯斯坦。
        attack_blocked = getattr(engine._mode_handler(), "bot_attack_blocked", None)
        for target in targets:
            if isinstance(target, Player) and player.role == "hero" and not hero_attacks_traitor:
                continue
            if isinstance(target, Monster) and getattr(target, "controller", "traitor") == player.role:
                # 不打自己这方的怪（怪物 controller 默认 traitor）。30 号实测：
                # 新娘开局就站在叛徒身边，叛徒 bot 第一回合照着它就是一下
                # （12 对 5 把自家新娘击晕），既不是人会做的事、也白送一回合。
                # 反向同理：英雄不追 controller=hero 的怪（如 19 号驯兽师的兽）。
                continue
            if callable(attack_blocked) and attack_blocked(engine, player, target):
                continue
            # 同源查询：该玩家用空手或任一武器至少有一种合法攻击方式才保留，
            # 顺带挡掉剧本 handler 闸门（如剧本 26 五芒星室叛徒）。
            if any(engine.attack_would_be_allowed(player, target, wid) for wid in weapon_ids):
                filtered.append(target)
        return filtered

    def _target_score(self, engine: GameEngine, player: Player, target: object, profile: dict) -> int:
        style_bonus = 12 if player.bot_style == "aggressive" else 0
        caution_penalty = 20 if player.bot_style == "cautious" and min(player.stats.get("speed", 0), player.stats.get("might", 0)) <= 2 else 0
        difficulty_bonus = {"easy": -18, "normal": 0, "hard": 18}.get(player.bot_difficulty, 0)
        if isinstance(target, Monster):
            score = 90 + max(target.might, target.sanity, target.knowledge) + style_bonus + difficulty_bonus - caution_penalty
        elif isinstance(target, Player):
            weakness = 12 - (target.stats.get("speed", 0) + target.stats.get("might", 0))
            if player.role == "traitor" and profile.get("prefer_weak_targets", True):
                score = 85 + weakness + style_bonus + difficulty_bonus - caution_penalty
            else:
                score = 70 + style_bonus + difficulty_bonus - caution_penalty
        else:
            return 0
        # 集火：英雄对与 bot_focus 一致的目标集中火力（+25）。
        if player.role == "hero":
            focus = engine._haunt_rule_state().get("bot_focus", {})
            marker = "monster:" + str(target.id) if isinstance(target, Monster) else (target.id if isinstance(target, Player) else None)
            legacy = target.template_id if isinstance(target, Monster) else marker
            if marker is not None and focus.get(player.role) in (marker, legacy):
                score += 25
        return score
