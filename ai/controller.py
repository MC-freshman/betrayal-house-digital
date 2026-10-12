from __future__ import annotations

from ._imports import ActionCommand, GameEngine, Iterator, Player, contextmanager

from .items import InventoryDecisions
from .haunt_actions import HauntDecisions
from .combat import CombatDecisions
from .navigation import NavigationDecisions
from .decisions import BotDecisionProvider

class BotController(InventoryDecisions, HauntDecisions, CombatDecisions, NavigationDecisions):
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
            option = self._choose_move_option(engine, player, options, ranked=ranked)
            candidates = [option] + [item for item in ranked if item is not option]
            moved = False
            previous_room_key = player.room_key
            previous_threat = self._room_threat(engine, player, previous_room_key)
            retreat_signature = self._retreat_signature(engine, player)
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
                self._try_share_quest_items(engine, player)
                self._try_attack(engine, player)
                if previous_threat >= 3 and self._room_threat(engine, player, player.room_key) < previous_threat:
                    spent = engine.state.meta.setdefault("bot_retreats", {}).setdefault(str(player.id), [])
                    if retreat_signature not in spent:
                        spent.append(retreat_signature)
                    break

        if engine.state.phase == "HAUNT_PHASE":
            self._try_haunt_action(engine, player)
            self._try_attack(engine, player)

        if engine.state.phase != "GAME_OVER":
            engine.execute_command(ActionCommand("end_turn", player.id))

    def _pickup_room_items(self, engine: GameEngine, player: Player) -> None:
        for card_id in list(engine.room_items(player.room_key)):
            engine.execute_command(ActionCommand("pickup", player.id, {"card_id": card_id}))
