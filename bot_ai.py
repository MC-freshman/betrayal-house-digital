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

    def _try_haunt_action(self, engine: GameEngine, player: Player) -> bool:
        actions = engine.available_haunt_actions(player)
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
        for other in engine.state.players:
            if other.id == player.id or other.dead or other.frog:
                continue
            if other.role != player.role or other.room_key != player.room_key:
                continue
            # 队友手里有本剧本的令牌，说明他才是执行者
            if not engine.tokens_held_by(other.id):
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
        weapon_ids: list[str | None] = [None] + engine.available_attack_weapons(player)
        for weapon_id in weapon_ids:
            ranged = False
            bonus = 0
            if weapon_id:
                weapon = engine.catalog.cards[weapon_id]
                ranged = "ranged" in weapon.tags
                bonus = weapon.bonus.get("attack", 0)
            targets = engine.available_attack_targets(player, ranged=ranged)
            for target in self._filter_attack_targets(player, targets, profile):
                score = self._target_score(player, target, profile) + bonus
                if ranged:
                    score += 3
                choices.append((score, target, weapon_id, ranged))
        if not choices:
            return False
        score, target, weapon_id, ranged = max(choices, key=lambda item: item[0])
        if player.bot_difficulty == "easy" and score < 95:
            return False
        return engine.execute_command(
            ActionCommand(
                "attack",
                player.id,
                {"target": target, "weapon_card_id": weapon_id, "ranged": ranged},
            )
        )

    def _filter_attack_targets(self, player: Player, targets: list[object], profile: dict) -> list[object]:
        filtered: list[object] = []
        for target in targets:
            if isinstance(target, Player) and player.role == "hero" and not profile.get("attack_traitor_players", False):
                continue
            filtered.append(target)
        return filtered

    def _target_score(self, player: Player, target: object, profile: dict) -> int:
        style_bonus = 12 if player.bot_style == "aggressive" else 0
        caution_penalty = 20 if player.bot_style == "cautious" and min(player.stats.get("speed", 0), player.stats.get("might", 0)) <= 2 else 0
        difficulty_bonus = {"easy": -18, "normal": 0, "hard": 18}.get(player.bot_difficulty, 0)
        if isinstance(target, Monster):
            return 90 + max(target.might, target.sanity, target.knowledge) + style_bonus + difficulty_bonus - caution_penalty
        if isinstance(target, Player):
            weakness = 12 - (target.stats.get("speed", 0) + target.stats.get("might", 0))
            if player.role == "traitor" and profile.get("prefer_weak_targets", True):
                return 85 + weakness + style_bonus + difficulty_bonus - caution_penalty
            return 70 + style_bonus + difficulty_bonus - caution_penalty
        return 0

    def _choose_move_option(self, engine: GameEngine, player: Player, options: list[ExitOption]) -> ExitOption | None:
        if not options:
            return None
        ranked = self._rank_move_options(engine, player, options)
        if not ranked:
            return None
        if player.bot_difficulty == "easy" and len(ranked) > 1 and engine.rng.random() < 0.35:
            return ranked[1]
        return ranked[0]

    def _rank_move_options(self, engine: GameEngine, player: Player, options: list[ExitOption]) -> list[ExitOption]:
        profile = self._side_profile(engine, player)
        next_targets = self._next_steps_toward_objectives(engine, player, profile)
        # 剧本层面的目标（该去哪个房间完成剧本任务）。权重刻意低于"追杀"：
        # 先顾眼前的战斗，再顾剧本推进，但也明显高于单纯探索，避免被探索
        # 加分盖过去。
        haunt_goals = (
            self._haunt_goal_rooms(engine, player)
            if engine.state.phase == "HAUNT_PHASE"
            else set()
        )
        target_rooms = set(profile.get("target_rooms", []) or [])
        avoid_rooms = set(profile.get("avoid_rooms", []) or [])
        previous_room_key = self._previous_room_by_player.get(player.id)

        def score(option: ExitOption) -> int:
            value = 0
            if option.target_key in next_targets:
                value += 130 if player.bot_difficulty == "hard" else 100
            if option.target_key in haunt_goals:
                # 剧本目标房间。与追杀同档：剧本任务是主要取胜路径，
                # 权重太低会被"追杀最近的怪"永久压制——剧本 4 实测中
                # 蜘蛛一直在动，英雄就永远在追它、永远不去打网。
                value += 125 if player.bot_difficulty == "hard" else 95
            if engine.state.phase == "EXPLORE" and option.is_new_room:
                value += {"easy": 45, "normal": 80, "hard": 95}.get(player.bot_difficulty, 80)
            if option.is_new_room:
                value += 15
            room = engine.state.board.get(option.target_key)
            if room:
                if option.target_key == previous_room_key:
                    value -= 55
                if engine.state.phase == "EXPLORE" and room.visit_count == 0:
                    value += 20
                if engine.state.phase == "EXPLORE":
                    # 目标楼层由 _next_steps_toward_objectives 决定；这里的前沿数量
                    # 只做轻微的同楼层偏好，不能压过前往另一层的明确路线。
                    value += 2 * len(engine.exploration_frontier_keys(room.floor))
                if engine.room_items(room.key):
                    value += 50 if player.bot_difficulty == "hard" else 35
                if room.name in target_rooms or room.template_id in target_rooms:
                    value += 95 if player.bot_difficulty == "hard" else 70
                if room.name in avoid_rooms or room.template_id in avoid_rooms:
                    value -= 90 if player.bot_difficulty == "hard" else 55
                value -= self._danger_penalty(player, room.effect_id)
            if option.is_special:
                value += 4
                if option.direction in {"up", "down"}:
                    current_room = engine.current_room(player)
                    changing_floor = room.floor != current_room.floor
                    if changing_floor and not engine.has_remaining_room_cards(current_room.floor):
                        value += 95 if engine.has_remaining_room_cards(room.floor) else 15
                    elif changing_floor:
                        value -= 18
            return value

        return sorted(options, key=score, reverse=True)

    def _haunt_goal_rooms(self, engine: GameEngine, player: Player) -> set[str]:
        """作祟阶段：剧本要求机器人去哪里，而不只是"追人/追怪"。

        过去作祟阶段的寻路目标只有敌对玩家与怪物，导致机器人完全不知道
        剧本要它站到哪个房间——于是出现了这些僵局：
            · 剧本 2：英雄必须到五芒星室才能对幽灵做理智攻击，bot 不去，
              幽灵打不死，回合数空转到上限
            · 剧本 3：书掉在已故英雄脚边，bot 不知道要去捡，永远施不出
              凡人形态，女巫始终无敌
        这里把三类剧本目标一并算出来，交由 _rank_move_options 分层加分。
        """
        haunt = engine.state.haunt
        rule = (haunt.rule_data or {}) if haunt else {}
        if not rule:
            return set()
        flags = engine._haunt_flags()
        goals: set[str] = set()

        # 1) 有房间要求的剧本行动：挖曼德拉草要去温室/储藏室/厨房，
        #    降灵会要去五芒星室……
        for action in rule.get("actions", []):
            if not engine._haunt_side_allowed(player, str(action.get("side", "both"))):
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
        if required & {str(item) for item in player.items}:
            for other in engine.state.players:
                if other.id == player.id or other.dead or other.frog:
                    continue
                if other.role == player.role and engine.tokens_held_by(other.id):
                    goals.add("__room__" + other.room_key)

        # 3) 剧本关键房间作为保底目标
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

        # 关键一步：打分比较的是"下一步走哪个房间"，所以这里要像
        # _next_steps_toward_objectives 那样换算成路径的第二格。
        # 直接返回目标房间的话，只有一步能抵达时才会加分，等于没引导。
        next_steps: set[str] = set()
        for room_key in room_keys:
            if room_key not in engine.state.board:
                continue
            path = engine._shortest_path(player.room_key, room_key)
            if len(path) > 1:
                next_steps.add(path[1])
        return next_steps

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
            if player.role == "traitor":
                targets.extend(other.room_key for other in engine.state.players if other.role == "hero" and not other.dead)
            elif profile.get("attack_monsters", True):
                targets.extend(monster.room_key for monster in engine.state.monsters if monster.stunned_turns <= 0)
            if player.role == "hero" and player.bot_difficulty == "hard" and profile.get("protect_humans", True):
                for human in engine.state.players:
                    if human.control == "human" and human.role == "hero" and not human.dead:
                        targets.append(human.room_key)

        wanted_rooms = set(profile.get("target_rooms", []) or [])
        if wanted_rooms:
            for key, room in engine.state.board.items():
                if room.name in wanted_rooms or room.template_id in wanted_rooms:
                    targets.append(key)

        next_steps: set[str] = set()
        for target_key in targets:
            path = engine._shortest_path(player.room_key, target_key)
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
