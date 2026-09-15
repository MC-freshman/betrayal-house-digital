from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

try:
    from .engine import ActionCommand, AutoDecisionProvider, ExitOption, GameEngine
    from .haunt_ai_profiles import get_haunt_ai_profile
    from .models import Monster, Player, STAT_NAMES
except ImportError:  # pragma: no cover - direct script execution
    from engine import ActionCommand, AutoDecisionProvider, ExitOption, GameEngine  # type: ignore
    from haunt_ai_profiles import get_haunt_ai_profile  # type: ignore
    from models import Monster, Player, STAT_NAMES  # type: ignore


STAT_LABELS = {
    "速度": "speed",
    "力量": "might",
    "理智": "sanity",
    "知识": "knowledge",
}


class BotDecisionProvider(AutoDecisionProvider):
    def __init__(self, engine: GameEngine, player: Player, human_prompter: object | None = None) -> None:
        self.engine = engine
        self.player = player
        self.human_prompter = human_prompter

    def confirm(self, title: str, message: str) -> bool:
        if title == "盔甲" and self._message_mentions_human(message):
            return self.human_prompter.confirm(title, message) if self.human_prompter else True
        if title in {"偷窃", "重掷"}:
            return False
        if title == "盔甲":
            return True
        if title == "事件卡":
            return False
        return True

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        if not options:
            return None
        if title == "恢复属性":
            return self._choose_lowest_stat_option(options)
        if title == "远古护身符":
            return self._choose_lowest_stat_option(options)
        if title == "神秘电梯":
            return 0
        return 0

    def choose_rotation(
        self,
        title: str,
        message: str,
        placements: list[dict],
        entry_direction: str,
    ) -> int | None:
        if not placements:
            return None
        return max(range(len(placements)), key=lambda idx: len(placements[idx].get("doors", ())))

    def choose_split_damage(
        self,
        title: str,
        message: str,
        amount: int,
        first_label: str,
        second_label: str,
    ) -> int | None:
        if self._message_mentions_human(message):
            if self.human_prompter:
                return self.human_prompter.choose_split_damage(title, message, amount, first_label, second_label)
            return max(0, amount // 2)
        target = self._player_mentioned_in_message(message) or self.player
        first_stat = STAT_LABELS.get(first_label)
        second_stat = STAT_LABELS.get(second_label)
        if not first_stat or not second_stat:
            return max(0, amount // 2)
        first_value = target.stats.get(first_stat, 0)
        second_value = target.stats.get(second_stat, 0)
        if first_value > second_value:
            return amount
        if second_value > first_value:
            return 0
        return max(0, amount // 2)

    def _choose_lowest_stat_option(self, options: list[str]) -> int:
        best_index = 0
        best_value = 999
        for index, label in enumerate(options):
            stat = STAT_LABELS.get(label)
            if not stat:
                continue
            value = self.player.stats.get(stat, 0)
            if value < best_value:
                best_index = index
                best_value = value
        return best_index

    def _message_mentions_human(self, message: str) -> bool:
        return any(player.control == "human" and player.name in message for player in self.engine.state.players)

    def _player_mentioned_in_message(self, message: str) -> Player | None:
        return next((player for player in self.engine.state.players if player.name in message), None)


class BotController:
    def __init__(self) -> None:
        # 机器人决策不写入存档，只用于避免同一回合在两个房间之间来回折返，
        # 以及让不同机器人轮流承担不同楼层的探索任务。
        self._previous_room_by_player: dict[int, str] = {}
        self._last_exploration_floor_by_player: dict[int, int] = {}

        # 作祟目标承诺：玩家 id → (目标房间 key, 承诺到期回合)。
        # 剧本目标房间往往不止一间（22 号 6 个驱魔来源、44 号 7 个仪式房间），
        # 每步都重挑最近的那个会让机器人在两三个房间之间来回打转：
        # 走了两步、目标换了、又折回来。seed23/5p 的 22 号实测 400 回合里
        # 第 5 次驱魔始终差一步，英雄在门厅一带空转。像人一样"认准一间先走到"
        # 才能推进。
        self._goal_commitment_by_player: dict[int, tuple[str, int]] = {}

    # 目标承诺的有效回合数：够走完一段长路（速度 3-5），又不至于锁死在
    # 已经变得不划算的目标上。
    GOAL_COMMITMENT_TURNS = 8

    def take_turn(self, engine: GameEngine) -> bool:
        if not engine.state.players or engine.state.phase == "GAME_OVER":
            return False
        player = engine.current_player
        if player.dead:
            # 死者的回合直接跳过并推进轮转。
            # 剧本 6 的叛徒开局就"等待运输"出局（剧本 4 的 3-4 人局叛徒被吃），
            # 以前这里返回 False，主循环会在第一次轮到死者时死锁——对局停在
            # 那轮，end_turn 里的怪物回合永远执行不到（实测 17 回合怪物 0 行动）。
            engine.execute_command(ActionCommand("end_turn", player.id))
            return True
        if player.control != "bot":
            return False

        with self._bot_prompter(engine, player):
            engine._log(f"机器人 {player.name} 开始行动。", category="robot")
            self._run_turn(engine, player)
        return True

    @contextmanager
    def _bot_prompter(self, engine: GameEngine, player: Player) -> Iterator[None]:
        original = engine.prompter
        engine.prompter = BotDecisionProvider(engine, player, original)
        try:
            yield
        finally:
            engine.prompter = original

    def _run_turn(self, engine: GameEngine, player: Player) -> None:
        self._pickup_room_items(engine, player)
        self._try_use_helpful_item(engine, player)

        if engine.state.phase == "HAUNT_PHASE":
            self._try_haunt_action(engine, player)
            self._try_share_quest_items(engine, player)
            self._try_attack(engine, player)

        moves = 0
        max_moves = {"easy": 4, "normal": 10, "hard": 12}.get(player.bot_difficulty, 10)
        while (
            engine.state.phase != "GAME_OVER"
            and not player.dead
            and player.steps_remaining > 0
            and not player.movement_stopped
            and moves < max_moves
        ):
            options = engine.available_move_options(player)
            if not options:
                break
            if engine.state.phase == "HAUNT_PHASE":
                stay = getattr(engine._mode_handler(), "bot_stay_in_room", None)
                if callable(stay) and stay(engine, player):
                    # 剧本声明"人已经站对了、在等队友"（36 号小艇到了阳台/
                    # 塔楼、其余英雄还在路上）：离开是把集合点拆掉。
                    break
            if (
                engine.state.phase == "HAUNT_PHASE"
                and engine._haunt_action_used(player)
                and self._pending_haunt_action_here(engine, player)
                and not self._leave_after_action(engine, player)
            ):
                # 已经在这间房做完一步、下一步还在这间房：原地等下回合。
                # 24 号实测——英雄启动管风琴后立刻被战斗牵走，知识 6+ 的第二步
                # 永远没人做，驱魔三步链断在中间。剧本可声明"做完必须挪窝"
                # 否决原地等待（27 号：贴边检定完留在扩张圈里＝下回合被吞）。
                break
            ranked = self._rank_move_options(engine, player, options)
            if not ranked:
                break
            option = self._choose_move_option(engine, player, options)
            candidates = [option] + [item for item in ranked if item is not option]
            moved = False
            previous_room_key = player.room_key
            for candidate in candidates:
                if candidate is not None and engine.execute_command(
                    ActionCommand("move", player.id, {"option": candidate})
                ):
                    moved = True
                    break
            if not moved:
                break
            self._previous_room_by_player[player.id] = previous_room_key
            if engine.state.phase == "EXPLORE":
                room = engine.state.board.get(player.room_key)
                if room:
                    self._last_exploration_floor_by_player[player.id] = room.floor
            moves += 1
            self._pickup_room_items(engine, player)
            if engine.state.phase == "HAUNT_PHASE":
                self._try_haunt_action(engine, player)
                self._try_attack(engine, player)

        if engine.state.phase == "HAUNT_PHASE":
            self._try_haunt_action(engine, player)
            self._try_attack(engine, player)

        if engine.state.phase != "GAME_OVER":
            engine.execute_command(ActionCommand("end_turn", player.id))

    def _pickup_room_items(self, engine: GameEngine, player: Player) -> None:
        for card_id in list(engine.room_items(player.room_key)):
            engine.execute_command(ActionCommand("pickup", player.id, {"card_id": card_id}))

    def _try_use_helpful_item(self, engine: GameEngine, player: Player) -> bool:
        if player.item_used:
            return False
        if player.bot_difficulty == "easy" and engine.rng.random() < 0.45:
            return False
        for card_id in list(player.items):
            card = engine.catalog.cards.get(card_id)
            if not card:
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

    def _bot_haunt_actions(self, engine: GameEngine, player: Player) -> list:
        """机器人眼里的剧本行动：模式层声明"现在别做"的从列表里拿掉。

        `bot_action_blocked` 原先只挡寻路目标。18 号屏息没有 rooms 字段，
        挡不到，于是它成了"无孢子房间里唯一可点的行动"——机器人每回合
        先屏息，再被 `_pending_haunt_action_here` 判成"下回合还能在这儿做"，
        整个人就钉在原地（seed113/3p 实测屏息 359 次，削弱 0/3）。
        """
        actions = list(engine.available_haunt_actions(player))
        blocked = getattr(engine._mode_handler(), "bot_action_blocked", None)
        if not callable(blocked):
            return actions
        return [
            action
            for action in actions
            if not blocked(engine, player, str(getattr(action, "id", "")))
        ]

    def _pending_haunt_action_here(self, engine: GameEngine, player: Player) -> bool:
        """本房间是否还有一次"这回合已用完、下回合还能做"的剧本行动。

        引擎的可用行动列表会因为"本回合已用过剧本行动"直接返回空，
        所以这里临时清掉标记问一次，看完再还原。
        """
        used = engine._haunt_rule_state().setdefault("actions_used", {})
        key = str(player.id)
        saved = used.get(key)
        used[key] = False
        try:
            return bool(self._bot_haunt_actions(engine, player))
        finally:
            if saved is None:
                used.pop(key, None)
            else:
                used[key] = saved

    def _try_haunt_action(self, engine: GameEngine, player: Player) -> bool:
        actions = self._bot_haunt_actions(engine, player)
        if not actions:
            return False
        if player.bot_difficulty == "easy" and engine.rng.random() < 0.3:
            return False

        def score(action) -> int:
            text = f"{action.id} {action.label}"
            value = 50
            if any(token in text for token in ["银弹", "左轮", "放逐", "制作", "搜索"]):
                value += 35
            if any(token in text for token in ["交给", "交出"]):
                value += 20
            if player.bot_difficulty == "hard":
                value += 15
            return value

        action = max(actions, key=score)
        return engine.execute_command(
            ActionCommand("haunt_action", player.id, {"action_id": action.id, "data": action.data})
        )

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
                score = self._target_score(engine, player, target, profile) + bonus
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
                focus[player.role] = target.template_id
            elif isinstance(target, Player):
                focus[player.role] = target.id
        return ok

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
            marker = target.template_id if isinstance(target, Monster) else (target.id if isinstance(target, Player) else None)
            if marker is not None and focus.get(player.role) == marker:
                score += 25
        return score

    def _choose_move_option(self, engine: GameEngine, player: Player, options: list[ExitOption]) -> ExitOption | None:
        if not options:
            return None
        ranked = self._rank_move_options(engine, player, options)
        if not ranked:
            return None
        if player.bot_difficulty == "easy" and len(ranked) > 1 and engine.rng.random() < 0.35:
            return ranked[1]
        return ranked[0]

    def _bot_wants_explore(self, engine: GameEngine, player: Player) -> bool:
        """剧本声明"现在必须去翻新房间找牌"（duck-typed `bot_wants_explore`）。

        39 号实测（seed109/4p）：戒指还压在预兆牌堆里，而作祟阶段机器人几乎
        不去探索（探索只在 EXPLORE 阶段有大额加分），继承人在王座前干等到
        400 回合。钩子返回 True 时，探索选项的权重抬到与剧本目标同档之上。
        """
        handler = engine._mode_handler()
        wants = getattr(handler, "bot_wants_explore", None)
        if not callable(wants):
            return False
        return bool(wants(engine, player))

    def _leave_after_action(self, engine: GameEngine, player: Player) -> bool:
        """剧本声明"本回合剧本行动做完后必须挪窝"（duck-typed，默认 False）。

        27 号实测：英雄贴着 Blob 做完知识检定后，`_pending_haunt_action_here`
        判定"下回合还能在这儿做"，于是原地过夜——下一个怪物回合 Blob 正好
        扩张进这间房，人直接被同化（seed101/3p 两名英雄都没活过两个回合）。
        真人贴边看一眼就会退开，这里把"要不要原地等"交给剧本决定。
        """
        handler = engine._mode_handler()
        leave = getattr(handler, "bot_leave_after_action", None)
        return bool(leave(engine, player)) if callable(leave) else False

    def _bot_path_filters(
        self, engine: GameEngine, player: Player
    ) -> tuple[set[str], set[str]]:
        """剧本声明的寻路禁区与危险房（duck-typed，默认空 → 行为不变）。

        · 禁区 `bot_blocked_rooms`：不走进去、也不作为路径中转（27 号 Blob
          房间：踏进去立刻被同化，真人不会走，也不该被当成抄近路的通道）。
        · 危险房 `bot_hazard_rooms`：可以靠近/经过（贴边做检定要做），但不该
          在本回合结束时留在里面（27 号扩张圈：下个怪物回合被吞）。评分时
          "走进去就没步数退出来"重扣。
        """
        handler = engine._mode_handler()
        blocked_fn = getattr(handler, "bot_blocked_rooms", None)
        hazard_fn = getattr(handler, "bot_hazard_rooms", None)
        blocked = set(blocked_fn(engine, player) or ()) if callable(blocked_fn) else set()
        hazards = set(hazard_fn(engine, player) or ()) if callable(hazard_fn) else set()
        return blocked - {player.room_key}, hazards

    def _rank_move_options(self, engine: GameEngine, player: Player, options: list[ExitOption]) -> list[ExitOption]:
        profile = self._side_profile(engine, player)
        blocked_rooms, hazard_rooms = self._bot_path_filters(engine, player)
        wants_explore = self._bot_wants_explore(engine, player)
        next_targets = self._next_steps_toward_objectives(engine, player, profile)
        # 剧本层面的目标（该去哪个房间完成剧本任务）。权重刻意低于"追杀"：
        # 先顾眼前的战斗，再顾剧本推进，但也明显高于单纯探索，避免被探索
        # 加分盖过去。
        haunt_targets = (
            self._haunt_goal_targets(engine, player)
            if engine.state.phase == "HAUNT_PHASE"
            else set()
        )
        haunt_goals = self._next_steps_toward(engine, player, haunt_targets)
        # 认准的那一间：它压过通用目标房间表（+130）——那张表里混着阁楼、
        # 卧室之类的"通用宝地"，会把真正的剧本目标挤掉（2 号实测：英雄被
        # 楼上房间牵着走，五芒星室就在三层外也不去，降灵会开不起来）。
        # 缺关键牌（wants_explore）时不承诺：那时目标是"翻遍房子找牌"。
        committed_target = (
            self._commit_haunt_goal(engine, player, haunt_targets)
            if haunt_targets and not wants_explore
            else None
        )
        committed_steps = (
            self._next_steps_toward(engine, player, {committed_target})
            if committed_target
            else set()
        )
        target_rooms = set(profile.get("target_rooms", []) or [])
        avoid_rooms = set(profile.get("avoid_rooms", []) or [])
        if wants_explore:
            # 剧本明说"关键牌还压在牌堆里、必须去翻出来"时，目标房间的吸引力
            # 必须先让路：圣徽没到手时，五芒星室是间空屋子，站在那儿干等不是
            # 人的打法——去翻新房间抽预兆牌才是。9 号实测：英雄在五芒星室
            # 空站 351 次，圣徽始终留在预兆牌堆里。
            target_rooms = set()
        previous_room_key = self._previous_room_by_player.get(player.id)
        # 探索阶段：站在"该探索的楼层"上时，就地翻门要压过"走去别的待探索房间"。
        # 缺这一条时，前沿寻路的 +130 永远高于探索的 +110（hard），机器人会在
        # 全屋各个待探索房间之间来回跑、却一间也不翻——seed101/4p 实测 300 回合
        # 只探到 26 间房、预兆只出了 2 张，作祟永远不开始，四个剧本全卡在探索期。
        explore_floor = (
            self._exploration_target_floor(engine, player) if engine.state.phase == "EXPLORE" else None
        )
        current_floor = engine.current_room(player).floor if explore_floor is not None else None
        # 剧本目标房间所在的楼层。换层惩罚（-18）原本无差别地压过一切，
        # 导致"目标在别的楼层"的剧本里，机器人永远不下地下室/不上楼
        # （70 号实测：吸血鬼形态差一间地下室的墓穴，叛徒在楼上打转 300 回合）。
        haunt_goal_floors = {
            engine.state.board[key].floor
            for key in haunt_goals
            if key in engine.state.board
        }
        if wants_explore:
            # 缺关键牌：剧本行动房（如还没拿到圣徽时的五芒星室）这时是间空屋子，
            # 站在那儿干等不是人的打法；目标是"去还没翻开的门前翻牌"。所以先把
            # 剧本目标房间的吸引力撤下来（否则 2 号那种 next+haunt 叠到 255 的
            # 房间永远压着探索的 135，而通往其它前沿的最短路又恰好穿过它，
            # 机器人就在它和邻居之间来回——9 号实测空站 351 次）。
            haunt_goals = set()
            # 但"去别的楼层的前沿"不能被换层惩罚挡住，把有待翻门位的楼层
            # 一并算进"该去的楼层"。
            haunt_goal_floors |= {
                floor
                for floor in (-1, 0, 1)
                if engine.exploration_frontier_keys(floor)
            }

        def score(option: ExitOption) -> int:
            value = 0
            if option.target_key in committed_steps:
                # 认准的剧本目标：高于一切常驻目标，机器人才会"一条路走到底"。
                value += {"easy": 100, "normal": 130, "hard": 165}.get(
                    player.bot_difficulty, 130
                )
            if option.target_key in next_targets:
                value += 130 if player.bot_difficulty == "hard" else 100
            if option.target_key in haunt_goals:
                # 剧本目标房间。与追杀同档：剧本任务是主要取胜路径，
                # 权重太低会被"追杀最近的怪"永久压制——剧本 4 实测中
                # 蜘蛛一直在动，英雄就永远在追它、永远不去打网。
                value += 125 if player.bot_difficulty == "hard" else 95
            if engine.state.phase == "EXPLORE" and option.is_new_room:
                value += {"easy": 45, "normal": 80, "hard": 95}.get(player.bot_difficulty, 80)
                if explore_floor == current_floor:
                    # 就站在该探的楼层上：翻门（+45 → 155）优先于"走去别的前沿"
                    # （+130），否则整局都在前沿之间打转，见上方 explore_floor 注释。
                    value += 45
            if option.is_new_room:
                value += 15
                if wants_explore:
                    # 剧情目标牌还没露面 → 翻新房间比"去王座干等"更接近胜利。
                    # +140（合计 155）要压过"走向剧本目标房"的 +125 和常驻
                    # 追杀/护送目标的 +130——钩子的语义就是"探索优先"，
                    # 之前 +120（合计 135）从来没压住过，9 号就卡在这儿。
                    value += 140
            room = engine.state.board.get(option.target_key)
            if room:
                if option.target_key == previous_room_key:
                    value -= 55
                if (
                    room.template_id in engine.NON_TRANSIT_TEMPLATES
                    and option.target_key not in haunt_goals
                    and option.target_key not in committed_steps
                ):
                    # 进入即被随机传送的房间（神秘电梯）：不是剧本明确目标就别进。
                    # 人不会为了抄近路赌一次随机传送；机器人却会因为它是"前沿"
                    # 或在中转路径上而走进去（seed137/4p）。扣分只影响优先级，
                    # 真的没别的选择时仍然会走。
                    value -= 70
                if engine.state.phase == "EXPLORE" and room.visit_count == 0:
                    value += 20
                if engine.state.phase == "EXPLORE":
                    # 目标楼层由 _next_steps_toward_objectives 决定；这里的前沿数量
                    # 只做轻微的同楼层偏好，不能压过前往另一层的明确路线。
                    # 上限 6：不封顶时"前沿越多、已有房间越香"——房子一大
                    # （前沿 ≥13 间）就永远压过"就地翻门"的 155，机器人从此
                    # 不再探索、整局在几间屋子间绕圈（seed131/3p 实测：
                    # 48/49 房间铺满后停在探索期 400 回合，最后一张预兆房
                    # 明明放得下却没人去翻）。
                    value += 2 * min(6, len(engine.exploration_frontier_keys(room.floor)))
                if engine.room_items(room.key):
                    value += 50 if player.bot_difficulty == "hard" else 35
                if room.name in target_rooms or room.template_id in target_rooms:
                    value += 95 if player.bot_difficulty == "hard" else 70
                if room.name in avoid_rooms or room.template_id in avoid_rooms:
                    value -= 90 if player.bot_difficulty == "hard" else 55
                if option.target_key in blocked_rooms:
                    # 剧本禁区（27 号 Blob 房间：踏进去立刻被同化）。扣到成负分，
                    # 只有真的无路可走时才会走——真人同样宁可不走近路。
                    value -= 400
                elif option.target_key in hazard_rooms and (
                    player.steps_remaining - option.cost <= 0
                    or engine.room_stop_risk(room)
                ):
                    # 剧本危险房（27 号扩张圈：下个怪物回合必被吞）：进去以后
                    # 一步不剩＝要在里面过夜。贴边看一眼就走是可以的，留宿不行，
                    # 所以只在"没步数退出来"时重扣，不禁止靠近。
                    # 另一类同样致命：进房可能立刻终止移动的效果房（保险库/
                    # 研究实验室抽牌、煤导槽/坍塌房传送、深渊/地下墓穴/地下湖
                    # 检定失败停下）——进去就退不出来，等于把命交给掷骰。
                    value -= 400
                value -= self._danger_penalty(player, room.effect_id)
                # 英雄走位三项扣分（均为新增情形，系数均小于追击 +100 / 剧本
                # 目标 +95 的正分，不会压过取胜主线）：
                if player.role == "hero":
                    # 分散：目标房间已有 ≥2 名存活同阵营英雄 → −40
                    same_heroes = sum(
                        1
                        for p in engine.state.players
                        if p.role == "hero" and not p.dead and p.id != player.id and p.room_key == option.target_key
                    )
                    if same_heroes >= 2:
                        value -= 40
                    room_monsters = [
                        m
                        for m in engine.state.monsters
                        if m.room_key == option.target_key and m.stunned_turns <= 0
                    ]
                    if room_monsters:
                        weapon_ids = [None] + engine.available_attack_weapons(player)
                        # 打不动怪所在房：本英雄空手/任一武器都打不动的非眩晕怪 → −60
                        unbeatable = any(
                            not any(
                                engine.attack_would_be_allowed(player, m, wid, ignore_position=True)
                                for wid in weapon_ids
                            )
                            for m in room_monsters
                        )
                        if unbeatable:
                            value -= 60
                        # 力量悬殊：怪 might > 英雄 might+speed 之和 → −25
                        if any(
                            m.might > player.stats.get("might", 0) + player.stats.get("speed", 0)
                            for m in room_monsters
                        ):
                            value -= 25
            if option.target_key and option.target_key not in engine.state.board:
                # 剧本给出的"非棋盘目标"（目前只有 33 号划入湖面的 "lake:" 选项）：
                # 这是剧本明说可以走的路线，不能因为普通房间的小加分或
                # "回上一个房间"的惩罚而被永远压着不选——seed101/5p 实测过
                # 400 回合在岸上与湖面之间来回打转。
                value += 20
            if option.is_special:
                value += 4
                if option.direction in {"up", "down"}:
                    current_room = engine.current_room(player)
                    changing_floor = room.floor != current_room.floor
                    if changing_floor and not engine.has_remaining_room_cards(current_room.floor):
                        value += 95 if engine.has_remaining_room_cards(room.floor) else 15
                    elif changing_floor:
                        # 换层去剧本目标所在楼层时不再惩罚，反而加分——
                        # 否则"目标在别的楼层"的剧本永远走不出去。
                        value += 40 if room.floor in haunt_goal_floors else -18
            return value

        return sorted(options, key=score, reverse=True)

    def _haunt_goal_targets(self, engine: GameEngine, player: Player) -> set[str]:
        """作祟阶段：剧本要求机器人去哪里，而不只是"追人/追怪"。

        过去作祟阶段的寻路目标只有敌对玩家与怪物，导致机器人完全不知道
        剧本要它站到哪个房间——于是出现了这些僵局：
            · 剧本 2：英雄必须到五芒星室才能对幽灵做理智攻击，bot 不去，
              幽灵打不死，回合数空转到上限
            · 剧本 3：书掉在已故英雄脚边，bot 不知道要去捡，永远施不出
              凡人形态，女巫始终无敌
        这里把三类剧本目标一并算出来，交由 _rank_move_options 分层加分。
        返回的是**目标房间本身**，下一步由 `_next_steps_toward` 换算。
        """
        haunt = engine.state.haunt
        rule = (haunt.rule_data or {}) if haunt else {}
        if not rule:
            return set()
        flags = engine._haunt_flags()
        goals: set[str] = set()

        # 0) 剧本可提供定制目标（剧本 25：每个英雄找"自己娃娃"的候选房间，
        #    静态 rule_data 表达不了按玩家区分的目标）。duck-typed 探测，
        #    未实现该方法的 handler 保持原行为。
        handler = engine._mode_handler()
        custom_goals = getattr(handler, "bot_goal_rooms", None)
        if callable(custom_goals):
            provided = custom_goals(engine, player) or []
            if provided:
                goals.update(provided)

        # 0b) 剧本可声明"这个玩家此刻没有任何剧本目标房间"（区别于上面
        #     bot_goal_rooms 返回空 = 退回通用换算）。9 号实测：叛徒唯一的
        #     行动要持圣徽才能做，而 key_rooms 保底会把深渊/熔炉房/地下湖
        #     当成目的地，它在三间空房之间绕了 33 圈；此时它的正确目标是
        #     追杀英雄（通用追击逻辑），不该再被空目标牵着走。
        suppressed = getattr(handler, "bot_goal_suppressed", None)
        if callable(suppressed) and suppressed(engine, player):
            return set()

        # 1) 有房间要求的剧本行动：挖曼德拉草要去温室/储藏室/厨房，
        #    降灵会要去五芒星室……
        action_blocked = getattr(handler, "bot_action_blocked", None)
        for action in rule.get("actions", []):
            if not engine._haunt_side_allowed(player, str(action.get("side", "both"))):
                continue
            # 模式层已经作废的行动不再是目标。22 号"每个驱魔来源只能用一次"
            # 记在 used_exorcism_sources 里（不是 set_flags），bot 看不见就
            # 一直往用过的房间跑——实测 3/5 时三名英雄在五芒星室/花园之间
            # 空转到 400 回合。
            if callable(action_blocked) and action_blocked(
                engine, player, str(action.get("id", ""))
            ):
                continue
            # 该行动的产出已经拿到了就不必再去（例如已经挖到草）
            set_flags = action.get("set_flags", {})
            if set_flags and all(flags.get(key) == value for key, value in set_flags.items()):
                continue
            goals.update(action.get("rooms") or [])

            # 要求"与某个目标同房间"的行动，目标就是它当前所在房间：
            #   · same_room:<怪物模板>   → 该怪物所在房间（如女巫）
            #   · same_room:<令牌类型>   → 该令牌所在房间（如剧本 4 的蛛网）
            #     ——attack_web 没有 rooms 字段，过去这段解析被
            #        "if not rooms: continue" 挡在前面，蛛网房间从未成为
            #        寻路目标，英雄根本不去打网。
            #   · same_room:revealer     → 作祟揭示者所在房间（如销毁蛛卵）
            for requirement in action.get("requires", []):
                if not str(requirement).startswith("same_room:"):
                    continue
                target = str(requirement).split(":", 1)[1]
                if target == "revealer":
                    revealer = next(
                        (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id),
                        None,
                    )
                    if revealer is not None and not revealer.dead:
                        goals.add("__room__" + revealer.room_key)
                    continue
                for monster in engine.state.monsters:
                    if monster.template_id == target:
                        goals.add("__room__" + monster.room_key)
                for token in engine.tokens_of_kind(target):
                    if token.room_key:
                        goals.add("__room__" + token.room_key)

        # 2) 剧本关键牌掉在地上时，去把它捡回来
        required = {str(card_id) for card_id in rule.get("required_cards", [])}
        if required:
            for room_key, items in engine.state.room_items.items():
                if required & {str(item) for item in items}:
                    goals.add("__room__" + room_key)

        # 3) 自己拿着关键牌、队友持有令牌（正在执行任务）时，去和他会合。
        #    令牌不能交易，所以只能让持牌方走过去（见 _try_share_quest_items）。
        #    剧本也可以直接指定"该把牌交给谁"（39 号继承人，quest_carrier）。
        if required & {str(item) for item in player.items}:
            carrier_id = self._quest_carrier_id(engine)
            for other in engine.state.players:
                if other.id == player.id or other.dead or other.frog:
                    continue
                if carrier_id is not None:
                    if other.id == carrier_id:
                        goals.add("__room__" + other.room_key)
                    continue
                if other.role == player.role and engine.tokens_held_by(other.id):
                    goals.add("__room__" + other.room_key)

        # 3) 剧本关键房间作为**保底**目标：只有前面几类具体目标（剧本行动房间、
        #    关键牌、令牌会合）都算不出来时才启用。以前是无条件并入，70 号实测
        #    受害最重——它的 key_rooms 有 22 间"形态可能用到的房间"，叛徒的目标
        #    集合被稀释成 19 间，承诺机制只能在最近的保底房里打转（地窖 ⇄ 地下湖），
        #    真正的形态房（雕像走廊 3 格、温室 6 格）永远排不上，转变停在 0/5。
        if not goals:
            for key_room in rule.get("key_rooms", []):
                goals.add(str(key_room))

        # 把模板 id / 房间名解析成实际房间 key
        room_keys: set[str] = set()
        for goal in goals:
            if goal.startswith("__room__"):
                room_keys.add(goal[len("__room__") :])
                continue
            for key, room in engine.state.board.items():
                if room.template_id == goal or room.name == goal:
                    room_keys.add(key)

        # 关键一步：打分比较的是"下一步走哪个房间"，所以这里换算成路径的第二格。
        # 直接返回目标房间的话，只有一步能抵达时才会加分，等于没引导。
        return room_keys

    def _next_steps_toward(self, engine: GameEngine, player: Player, room_keys: set[str]) -> set[str]:
        """把目标房间集合换算成"下一步该走进哪间"的集合。

        寻路会绕开剧本禁区（`bot_blocked_rooms`）：27 号实测，英雄从入口大厅
        去地下室方向的检定位，最短路穿过 Blob 已经吞掉的房间，机器人照走不误、
        一进去就被同化（seed101/3p 首名英雄）。
        """
        next_steps: set[str] = set()
        blocked, _hazards = self._bot_path_filters(engine, player)
        for room_key in room_keys:
            if room_key not in engine.state.board or room_key == player.room_key:
                continue
            path = engine._shortest_path(
                player.room_key, room_key, avoid_transit=True, blocked=blocked
            )
            if len(path) > 1:
                next_steps.add(path[1])
        return next_steps

    def _commit_haunt_goal(
        self, engine: GameEngine, player: Player, targets: set[str]
    ) -> str | None:
        """在一堆剧本目标里**认准一间**，并在若干回合内不换（像人一样先走到）。

        没有承诺时挑"走得通且最近"的那间（距离并列时按 key 排序取第一个，
        保证同种子可复现）；玩家已站在目标房间、目标消失或承诺过期时清掉。

        返回承诺的目标房间 key（没有可用目标时返回 None）。
        """
        turn = engine.state.turn_count
        committed = self._goal_commitment_by_player.get(player.id)
        if committed is not None:
            target_key, expires = committed
            if (
                expires > turn
                and target_key in engine.state.board
                and target_key != player.room_key
                and target_key in targets
            ):
                return target_key
            # 目标已达成/已消失/承诺过期：换一个（`target_key in targets` 这条
            # 很关键——访到形态房后它就不再是目标，死守承诺只会白站几回合）。
            self._goal_commitment_by_player.pop(player.id, None)

        reachable: list[tuple[int, str]] = []
        blocked, _hazards = self._bot_path_filters(engine, player)
        for key in sorted(targets):
            if key not in engine.state.board or key == player.room_key:
                continue
            distance = engine._path_length(
                player.room_key, key, avoid_transit=True, blocked=blocked
            )
            if distance == 9999:
                continue
            reachable.append((distance, key))
        if not reachable:
            return None
        _distance, target_key = min(reachable)
        self._goal_commitment_by_player[player.id] = (
            target_key,
            turn + self.GOAL_COMMITMENT_TURNS,
        )
        return target_key

    def _haunt_goal_rooms(self, engine: GameEngine, player: Player) -> set[str]:
        """剧本目标房间的**下一步**集合（`_haunt_goal_targets` 的路径换算）。"""
        return self._next_steps_toward(engine, player, self._haunt_goal_targets(engine, player))

    def _next_steps_toward_objectives(self, engine: GameEngine, player: Player, profile: dict) -> set[str]:
        targets: list[str] = []
        if engine.state.phase == "EXPLORE":
            current_room = engine.current_room(player)
            target_floor = self._exploration_target_floor(engine, player)
            if target_floor == current_room.floor:
                targets.extend(engine.exploration_frontier_keys(current_room.floor))
            elif target_floor is not None:
                # 跨楼层只能先走到已有的楼梯/平台，再从目标楼层的前沿继续探索。
                targets.extend(self._floor_anchor_keys(engine, target_floor))

        if engine.state.phase == "HAUNT_PHASE":
            if self._bot_wants_explore(engine, player):
                # 缺关键牌：把**每一层**还能翻门的房间都当成目标，让机器人先
                # 走到前沿再翻牌（跨层由 BFS 自动经过楼梯/平台）。缺这条，
                # 身边没有可翻门的机器人只会在几间屋子之间来回晃——9 号实测：
                # 圣徽还压在 8 张预兆牌里，英雄在一层小教堂那一带空转 180 次，
                # 永远不去楼上的前沿。
                for floor in (-1, 0, 1):
                    targets.extend(engine.exploration_frontier_keys(floor))
            if player.role == "traitor":
                # 剧本可用 chase_heroes=False 关掉"追英雄"的常驻目标（+130），
                # 让位给剧本目标（+125）——70 号实测：叛徒要访遍形态房间才能
                # 完成转变，追人权重更高时它会一路追人、从不访点，全局僵死。
                if profile.get("chase_heroes", True):
                    targets.extend(
                        other.room_key
                        for other in engine.state.players
                        if other.role == "hero" and not other.dead
                    )
            elif profile.get("attack_monsters", True):
                # 英雄追怪的两道闸门：
                # (i) 持有关键牌或剧本令牌时，优先去交付/会合而非盲目追怪；
                # (ii) 打不动的怪（免疫当前所有可用攻击属性）不值得追，省得白跑送死。
                rule = (engine.state.haunt.rule_data or {}) if engine.state.haunt else {}
                required = {str(card_id) for card_id in rule.get("required_cards", [])}
                holds_required = bool(required & {str(item) for item in player.items})
                holds_token = bool(engine.tokens_held_by(player.id))
                if not (holds_required or holds_token):
                    weapon_ids = [None] + engine.available_attack_weapons(player)
                    for monster in engine.state.monsters:
                        if monster.stunned_turns > 0:
                            continue
                        # 同源查询（忽略位置）：空手或任一武器都打不动就不追。
                        can_hurt = any(
                            engine.attack_would_be_allowed(player, monster, wid, ignore_position=True)
                            for wid in weapon_ids
                        )
                        if can_hurt:
                            targets.append(monster.room_key)
            if player.role == "hero":
                # 保护作祟揭示者（存活英雄）：其房间作为寻路目标，与 protect_humans 同档。
                revealer = next(
                    (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id),
                    None,
                )
                if revealer is not None and not revealer.dead and revealer.role == "hero":
                    targets.append(revealer.room_key)
                if player.bot_difficulty == "hard" and profile.get("protect_humans", True):
                    for human in engine.state.players:
                        if human.control == "human" and human.role == "hero" and not human.dead:
                            targets.append(human.room_key)

        wanted_rooms = set(profile.get("target_rooms", []) or [])
        if wanted_rooms and not self._bot_wants_explore(engine, player):
            # 缺关键牌时目标房间不再是目的地（见 _rank_move_options 的同款判断）
            for key, room in engine.state.board.items():
                if room.name in wanted_rooms or room.template_id in wanted_rooms:
                    targets.append(key)

        next_steps: set[str] = set()
        blocked, _hazards = self._bot_path_filters(engine, player)
        for target_key in targets:
            # avoid_transit=True：不能把"进入即传送"的神秘电梯当中转。默认
            # 路径会把它当普通房间穿过去，机器人于是主动走进电梯、被丢到随机
            # 楼层（seed137/4p 实测 400 行日志里 15 次进电梯、17 次被传送）。
            # blocked：同 _next_steps_toward，绕开剧本禁区。
            path = engine._shortest_path(
                player.room_key, target_key, avoid_transit=True, blocked=blocked
            )
            if len(path) > 1:
                next_steps.add(path[1])
        return next_steps

    def _exploration_target_floor(self, engine: GameEngine, player: Player) -> int | None:
        current_floor = engine.current_room(player).floor
        floors = [floor for floor in (-1, 0, 1) if engine.has_remaining_room_cards(floor)]
        if not floors:
            return None

        # 用已放置房间数 / (已放置 + 剩余牌数) 衡量楼层进度。旧逻辑只看当前
        # 楼层是否还有牌，导致机器人永远在一层的新门位上打转，根本不会去二层。
        # 选择进度最低的楼层，并用玩家编号稳定打散平局，让机器人自然分工。
        progress: dict[int, float] = {}
        for floor in floors:
            placed = sum(1 for room in engine.state.board.values() if room.floor == floor)
            remaining = sum(
                1
                for room_id in (*engine.state.room_deck, *engine.state.room_discard)
                if room_id in engine.catalog.room_templates
                and engine.catalog.room_templates[room_id].floor == floor
            )
            progress[floor] = placed / max(1, placed + remaining)

        lowest = min(progress.values())
        candidates = [floor for floor in floors if progress[floor] <= lowest + 0.025]
        # 当前楼层有可探索前沿时给一个很小的稳定偏好，避免刚到某层就立即折返；
        # 但不会改变明显落后楼层的优先级。
        if current_floor in candidates and engine.exploration_frontier_keys(current_floor):
            last_floor = self._last_exploration_floor_by_player.get(player.id)
            if last_floor == current_floor or len(candidates) == 1:
                return current_floor
        return candidates[player.id % len(candidates)]

    def _floor_anchor_keys(self, engine: GameEngine, floor: int) -> list[str]:
        anchor_ids = {
            -1: ("basement_landing", "stairs_from_basement"),
            0: ("entrance_hall", "grand_staircase"),
            1: ("upper_landing",),
        }.get(floor, ())
        anchors = [
            room.key
            for room in engine.state.board.values()
            if room.floor == floor and room.template_id in anchor_ids
        ]
        if anchors:
            return anchors
        return [room.key for room in engine.state.board.values() if room.floor == floor]

    def _danger_penalty(self, player: Player, effect_id: str) -> int:
        risky_physical = {"room_bloody_room", "room_furnace_room", "room_chasm", "room_collapsed_room", "room_tower"}
        risky_mental = {"room_charred_room"}
        if effect_id in risky_physical and min(player.stats.get("speed", 0), player.stats.get("might", 0)) <= 2:
            base = 55 if player.bot_style == "cautious" else 20 if player.bot_style == "aggressive" else 35
            return base + (25 if player.bot_difficulty == "hard" else -15 if player.bot_difficulty == "easy" else 0)
        if effect_id in risky_mental and min(player.stats.get("sanity", 0), player.stats.get("knowledge", 0)) <= 2:
            base = 55 if player.bot_style == "cautious" else 20 if player.bot_style == "aggressive" else 35
            return base + (25 if player.bot_difficulty == "hard" else -15 if player.bot_difficulty == "easy" else 0)
        return 0

    def _side_profile(self, engine: GameEngine, player: Player) -> dict:
        haunt_id = engine.state.haunt.id if engine.state.haunt else None
        profile = get_haunt_ai_profile(haunt_id)
        key = "traitor" if player.role == "traitor" else "hero"
        return dict(profile.get(key, {}))
