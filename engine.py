from __future__ import annotations

import hashlib
import json
import random
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

try:
    from .content import build_catalog
    from .models import (
        Catalog,
        Card,
        CharacterFace,
        DIRECTIONS,
        DIRECTION_DELTAS,
        GameState,
        Haunt,
        Monster,
        OPPOSITE,
        PHYSICAL_STATS,
        Player,
        PlacedRoom,
        RoomTemplate,
        STAT_NAMES,
        Token,
    )
    from .haunt_modes import get_mode_handler
    from .rules.barriers import BarrierRules
    from .rules.omens import OmenRules
    from .engine_parts.damage import DamageRules
    from .engine_parts.inventory import InventoryRules
    from .engine_parts.room_effects import RoomEffects
    from .engine_parts.combat import CombatRules
    from .engine_parts.haunt_actions import HauntActions
    from .engine_parts.monsters import MonsterRules
    from .engine_parts.board import BoardRules
    from .engine_parts.paths import PathRules
    from .engine_parts.types import ExitOption, ActionCommand, HauntAction
    from .engine_parts.geometry import (
        _distance_hint,
        _room_key,
        _rotate_direction,
        _rotate_doors,
        _rotate_links,
    )
except ImportError:  # pragma: no cover - direct script execution
    from content import build_catalog  # type: ignore
    from models import (
        Catalog,
        Card,
        CharacterFace,
        DIRECTIONS,
        DIRECTION_DELTAS,
        GameState,
        Haunt,
        Monster,
        OPPOSITE,
        PHYSICAL_STATS,
        Player,
        PlacedRoom,
        RoomTemplate,
        STAT_NAMES,
        Token,
    )  # type: ignore
    from haunt_modes import get_mode_handler  # type: ignore
    from rules.barriers import BarrierRules  # type: ignore
    from rules.omens import OmenRules  # type: ignore
    from engine_parts.damage import DamageRules  # type: ignore
    from engine_parts.inventory import InventoryRules  # type: ignore
    from engine_parts.room_effects import RoomEffects  # type: ignore
    from engine_parts.combat import CombatRules  # type: ignore
    from engine_parts.haunt_actions import HauntActions  # type: ignore
    from engine_parts.monsters import MonsterRules  # type: ignore
    from engine_parts.board import BoardRules  # type: ignore
    from engine_parts.paths import PathRules  # type: ignore
    from engine_parts.types import ExitOption, ActionCommand, HauntAction  # type: ignore
    from engine_parts.geometry import (
        _distance_hint,
        _room_key,
        _rotate_direction,
        _rotate_doors,
        _rotate_links,
    )  # type: ignore


class DecisionProvider(Protocol):
    def notify(self, title: str, message: str) -> None: ...

    def confirm(self, title: str, message: str) -> bool: ...

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None: ...

    def choose_rotation(
        self,
        title: str,
        message: str,
        placements: list[dict],
        entry_direction: str,
    ) -> int | None: ...

    def choose_split_damage(
        self,
        title: str,
        message: str,
        amount: int,
        first_label: str,
        second_label: str,
    ) -> int | None: ...

    def show_dice_roll(self, dice: list[int], total: int, label: str) -> None: ...


class AutoDecisionProvider:
    def notify(self, title: str, message: str) -> None:
        return

    def confirm(self, title: str, message: str) -> bool:
        return True

    def choose_from_list(self, title: str, message: str, options: list[str]) -> int | None:
        return 0 if options else None

    def choose_rotation(
        self,
        title: str,
        message: str,
        placements: list[dict],
        entry_direction: str,
    ) -> int | None:
        return 0 if placements else None

    def choose_split_damage(
        self,
        title: str,
        message: str,
        amount: int,
        first_label: str,
        second_label: str,
    ) -> int | None:
        return amount

    def show_dice_roll(self, dice: list[int], total: int, label: str) -> None:
        return


def _parse_birthday(value: str) -> tuple[int, int]:
    month, day = value.split("/")
    return int(month), int(day)


def _days_until_birthday(value: str, today: date | None = None) -> int:
    today = today or date.today()
    month, day = _parse_birthday(value)
    year = today.year
    candidate = date(year, month, day)
    if candidate < today:
        candidate = date(year + 1, month, day)
    return (candidate - today).days


SAVE_VERSION = 2

_SAVE_MIGRATIONS: dict[int, Any] = {}  # {来自版本: Callable[[dict], dict]}，当前暂无历史版本


class GameEngine(DamageRules, InventoryRules, RoomEffects, CombatRules, HauntActions, MonsterRules, BoardRules, PathRules, BarrierRules, OmenRules):
    def __init__(
        self,
        catalog: Catalog | None = None,
        prompter: DecisionProvider | None = None,
        seed: int | None = None,
    ) -> None:
        self.rng = random.Random(seed)
        self.catalog = catalog or build_catalog(seed)
        self.prompter = prompter or AutoDecisionProvider()
        self.state = GameState(seed=seed)
        self._next_monster_id = 1
        # 当前正在执行操作的玩家 id（供 DecisionRouter 路由决策用，None=无）
        self._active_player_id: int | None = None
        # 最近一次通用剧本行动的检定结果。"行动是否执行"与"检定是否成功"是
        # 两件事（检定失败同样消耗行动），handler 包装 super().perform_action
        # 时要靠它判断该不该发奖励，见 last_haunt_action_succeeded()。
        self._last_haunt_action_success = False

    def save_to_file(self, path: str | Path) -> Path:
        try:
            from .net.serialize import state_to_dict
        except ImportError:  # pragma: no cover - direct script execution
            from net.serialize import state_to_dict  # type: ignore

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "betrayal_house_save",
            "version": 2,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "rng_state": self.rng.getstate(),
            "next_monster_id": self._next_monster_id,
            "state": state_to_dict(self.state),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def load_from_file(self, path: str | Path) -> None:
        try:
            from .net.serialize import state_from_dict
        except ImportError:  # pragma: no cover - direct script execution
            from net.serialize import state_from_dict  # type: ignore

        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("format") != "betrayal_house_save":
            raise ValueError("不是有效的山中小屋存档。")
        data = self._migrate_save_payload(data)
        self.state = state_from_dict(data.get("state") or {})
        rng_state = data.get("rng_state")
        if rng_state is not None:
            self.rng.setstate(self._tupleize_random_state(rng_state))
        else:
            self.rng.seed(self.state.seed)
        self._next_monster_id = int(data.get("next_monster_id") or self._infer_next_monster_id())
        self._active_player_id = None

    def _migrate_save_payload(self, data: dict) -> dict:
        """存档版本守卫：拒绝过新版本，把旧版本沿迁移链升到当前版本。

        version 字段缺失视为最早期存档（v2 之前从未写过其他结构，保持原样
        直读，不因补守卫而拒绝历史存档）。未来改动存档结构时：SAVE_VERSION
        +1，并在 _SAVE_MIGRATIONS 里登记 旧版本 -> 迁移函数。
        """
        if "version" not in data:
            return data
        version = int(data.get("version") or 1)
        if version > SAVE_VERSION:
            raise ValueError(
                f"存档版本过新（v{version}，本程序支持到 v{SAVE_VERSION}），请先升级游戏。"
            )
        while version < SAVE_VERSION:
            migrate = _SAVE_MIGRATIONS.get(version)
            if migrate is None:
                raise ValueError(f"存档版本 v{version} 缺少迁移路径，无法读取。")
            data = migrate(data)
            version = int(data.get("version") or version + 1)
        return data

    def _tupleize_random_state(self, value):
        if isinstance(value, list):
            return tuple(self._tupleize_random_state(item) for item in value)
        return value

    def _infer_next_monster_id(self) -> int:
        highest = 0
        for monster in self.state.monsters:
            suffix = str(monster.id).rsplit("_", 1)[-1]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
        return highest + 1

    def start_new_game(self, player_configs: list[dict[str, str]]) -> None:
        if not 3 <= len(player_configs) <= 6:
            raise ValueError("需要 3~6 名玩家")

        selected_ids = [cfg["character_id"] for cfg in player_configs]
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("角色不能重复")

        players: list[Player] = []
        for index, cfg in enumerate(player_configs):
            face = self.catalog.characters[cfg["character_id"]]
            stats = dict(face.stats)
            stats_max = dict(face.stats_max)
            tracks = dict(getattr(face, "stats_tracks", None) or {})
            stat_positions: dict[str, int] = {}
            for stat in STAT_NAMES:
                track = tracks.get(stat)
                if track:
                    # 起始位置 = 轨道中与设定起始值最接近的格子，并把起始值校正到该格
                    idx = min(range(len(track)), key=lambda i: abs(track[i] - stats.get(stat, track[-1])))
                    stat_positions[stat] = idx
                    stats[stat] = track[idx]
            players.append(
                Player(
                    id=index,
                    name=cfg["name"].strip() or f"玩家{index + 1}",
                    character_id=face.id,
                    character_name=face.name,
                    source_name=face.source_name,
                    aliases=list(face.aliases),
                    birthday=face.birthday,
                    stats=stats,
                    stats_max=stats_max,
                    stats_tracks=tracks,
                    stat_positions=stat_positions,
                    overflow={key: 0 for key in STAT_NAMES},
                    control=cfg.get("control", "human"),
                    bot_difficulty=cfg.get("bot_difficulty", "normal"),
                    bot_style=cfg.get("bot_style", "balanced"),
                )
            )

        seat_order = sorted(
            range(len(players)),
            key=lambda idx: (_days_until_birthday(players[idx].birthday), idx),
        )

        self.state = GameState(
            phase="EXPLORE",
            turn_index=0,
            turn_order=seat_order,
            turn_count=0,
            players=players,
            board={},
            pos_index={},
            room_deck=list(self.catalog.room_draw_pool),
            room_discard=[],
            card_decks={
                "omen": self._build_deck("omen"),
                "item": self._build_deck("item"),
                "event": self._build_deck("event"),
            },
            card_discards={"omen": [], "item": [], "event": []},
            omens_drawn=0,
            last_omen_id=None,
            haunt_pending=False,
            haunt_revealer_id=None,
            haunt=None,
            traitor_id=None,
            monsters=[],
            room_items={},
            log=[],
            winner=None,
            winner_reason="",
            seed=self.state.seed,
            meta={},
        )
        self.rng.shuffle(self.state.room_deck)
        self._next_monster_id = 1
        self._place_start_rooms()
        self._place_players_on_start()
        self._reset_player_turn_state(self.current_player)
        self._log(
            "游戏开始："
            + "、".join(self._player_label(self.state.players[idx]) for idx in self.state.turn_order)
        )

    @property
    def current_player(self) -> Player:
        if not self.state.turn_order:
            raise RuntimeError("游戏尚未开始")
        idx = self.state.turn_order[self.state.turn_index % len(self.state.turn_order)]
        return self.state.players[idx]

    def current_room(self, player: Player | None = None) -> PlacedRoom:
        player = player or self.current_player
        return self.state.board[player.room_key]

    def _build_deck(self, kind: str) -> list[str]:
        deck = [card_id for card_id, card in self.catalog.cards.items() if card.kind == kind]
        self.rng.shuffle(deck)
        return deck

    def _draw_card_id(self, kind: str) -> str:
        """抽一张牌；牌堆与弃牌堆都空时返回 ""（这一类牌已经抽光了）。

        弃牌堆回收是规则（p2「If the entire stack is used, shuffle the
        discard pile; it becomes the new stack.」），但"从零重建一整副"不是：
        它会把已经拿在玩家手里的牌再复制一份（实测 seed101/4p：4 名机器人
        攒出 150 张物品，同一张道具重复出现十几次）。牌全在场上时，这一类
        牌就是抽不出来了，调用方按"没抽到"处理。
        """
        deck = self.state.card_decks.setdefault(kind, [])
        discards = self.state.card_discards.setdefault(kind, [])
        if not deck:
            if not discards:
                return ""
            deck.extend(discards)
            discards.clear()
            self.rng.shuffle(deck)
        return deck.pop()

    def _draw_room_template(self, floor: int) -> RoomTemplate | None:
        # 房间牌不能像事件牌一样无限回收；探索完某楼层的牌后，该楼层应当
        # 通过楼梯前往其他仍有牌的楼层，而不是重复生成已经探索过的房间。
        if not self.has_remaining_room_cards(floor):
            return None
        attempts = len(self.state.room_deck) + len(self.state.room_discard)
        while attempts > 0:
            if not self.state.room_deck:
                if self.state.room_discard:
                    self.state.room_deck = self.state.room_discard[:]
                    self.state.room_discard.clear()
                    self.rng.shuffle(self.state.room_deck)
                else:
                    return None
            if not self.state.room_deck:
                return None
            template_id = self.state.room_deck.pop()
            template = self.catalog.room_templates[template_id]
            if template.floor != floor:
                self.state.room_discard.append(template_id)
                attempts -= 1
                continue
            return template
        return None

    def has_remaining_room_cards(self, floor: int) -> bool:
        """返回指定楼层是否仍有尚未放置的房间牌。"""
        remaining = (*self.state.room_deck, *self.state.room_discard)
        return any(
            room_id in self.catalog.room_templates
            and self.catalog.room_templates[room_id].floor == floor
            for room_id in remaining
        )

    def exploration_frontier_keys(self, floor: int) -> list[str]:
        """返回指定楼层上仍有空门位、可以继续探索的已放置房间。"""
        if not self.has_remaining_room_cards(floor):
            return []
        frontier: list[str] = []
        for room in self.state.board.values():
            if room.floor != floor:
                continue
            if room.template_id in self.NON_TRANSIT_TEMPLATES:
                # 进入即被传送的房间（神秘电梯）不能算"可探索前沿"：人一进去
                # 就被丢到随机楼层，根本站不住，更谈不上从里面翻门。
                # seed137/4p 实测：机器人把电梯当探索目标，进去→被传送→走回来，
                # 200 回合只开出 30 间房，作祟迟迟不触发。
                continue
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                if (floor, room.x + dx, room.y + dy) not in self.state.pos_index:
                    frontier.append(room.key)
                    break
        return frontier

    def _place_start_rooms(self) -> None:
        starts = {
            "basement_landing": (-1, 0, 0),
            "entrance_hall": (0, 0, 0),
            "foyer": (0, 1, 0),
            "grand_staircase": (0, 2, 0),
            "upper_landing": (1, 2, 0),
        }
        for room_id, (floor, x, y) in starts.items():
            template = self.catalog.room_templates[room_id]
            key = _room_key(floor, x, y)
            room = PlacedRoom(
                key=key,
                template_id=template.id,
                name=template.name,
                floor=template.floor,
                x=x,
                y=y,
                rotation=0,
                doors=template.doors,
                symbol=template.symbol,
                effect_id=template.effect_id,
                text=template.text,
                special=template.special,
                links=dict(template.links),
                data={},
            )
            self.state.board[key] = room
            self.state.pos_index[(floor, x, y)] = key

    def _place_players_on_start(self) -> None:
        start_key = _room_key(0, 0, 0)
        for player in self.state.players:
            player.room_key = start_key
            player.steps_remaining = 0

    def _reset_player_turn_state(self, player: Player | None) -> None:
        if player is None:
            return
        player.steps_remaining = max(1, player.stats["speed"])
        player.attack_used = False
        player.item_used = False
        player.moved_this_turn = False
        player.movement_stopped = False
        player.extra_speed_this_turn = 0
        player.extra_check_rerolls = 0
        player.ignore_first_physical_damage = False
        self.state.meta.setdefault("room_attempts", {}).pop(str(player.id), None)
        self.state.meta["item_actions"] = {}
        self.state.meta["barrier_attempts"] = []
        haunt_rule = self.state.meta.get("haunt_rule")
        if haunt_rule:
            used = haunt_rule.setdefault("actions_used", {})
            used.pop(str(player.id), None)

    def start_turn(self) -> None:
        for _ in range(len(self.state.turn_order) or 1):
            player = self.current_player
            if not player.dead:
                break
            self._advance_turn()
        else:
            # 全员已死还要收一次口。叛徒开局就出局的剧本（10/24/47 等）
            # 若英雄随后也全灭，这里若不判，就会永远停在死者回合上
            # （47 号 seed109/4p 实测卡在 27 回合 HAUNT_PHASE）。
            self._check_all_players_dead()
            return
        self._reset_player_turn_state(player)
        self.state.turn_count += 1
        self._log(f"轮到 {self._player_label(player)}")
        if (
            self.state.phase == "EXPLORE"
            and self.state.last_omen_id
            and not self._has_future_omen_source()
        ):
            # 探索期已经不可能再出现预兆（预兆牌抽光，或剩下的预兆房放不下）。
            # 再熬下去只是空转，按"最后一次预兆检定"的既有兜底口径直接进入
            # 作祟——判据与 _resolve_haunt_check 完全一致。
            self._log("场上已不可能再出现预兆；本次作为最后一次预兆检定，触发作祟。")
            self._trigger_haunt(player)
        if self.state.phase == "HAUNT_PHASE":
            self._apply_start_of_turn_haunt_effects(player)
            self.check_victory()

    def end_turn(self) -> None:
        if self.state.winner or self.state.phase == "GAME_OVER":
            return
        player = self.current_player
        if (not player.dead and not player.moved_this_turn
                and self.current_room(player).template_id == "mystic_elevator"):
            self._apply_mystic_elevator(player, self.current_room(player))
        haunt_triggered = False
        if self.state.phase == "EXPLORE" and self.state.haunt_pending:
            haunt_triggered = self._resolve_haunt_check(player)
            self.state.haunt_pending = False

        if haunt_triggered:
            self.start_turn()
            return

        if self.state.phase == "HAUNT_PHASE":
            # 剧本可在"玩家回合结束"时介入（剧本 22 p104：每回合结束都要让
            # 房屋塌掉一部分）。必须在怪物回合之前跑，否则深渊扩散会慢一轮。
            self._mode_handler().on_turn_end(self, player)
            traitor_alive = any(
                p.role == "traitor" and not p.dead for p in self.state.players
            )
            should_run_monsters = False
            if traitor_alive:
                should_run_monsters = self.state.traitor_id == player.id
            else:
                # 叛徒已出局（剧本 6 等待运输 / 剧本 4 被蜘蛛吃掉）：怪物回合
                # 改由"本轮最后一位存活玩家"的回合结束代跑，否则怪物彻底瘫痪
                # ——剧本 6 实测 17 回合里外星人一动不动，全程被动挨打。
                # 判断"最后"：turn_order 是循环队列，若下一个活人的位置索引
                # 不大于当前位置，说明轮转即将绕回开头——当前玩家就是本轮末尾。
                alive_ids = {p.id for p in self.state.players if not p.dead}
                if player.id in alive_ids:
                    order = self.state.turn_order
                    total = len(order)
                    for step in range(1, total + 1):
                        nxt_idx = (self.state.turn_index + step) % total
                        if order[nxt_idx] in alive_ids:
                            should_run_monsters = nxt_idx <= self.state.turn_index
                            break
            if should_run_monsters:
                self._resolve_monster_turns()

        self._advance_turn()
        if self.state.winner:
            return
        self.start_turn()

    def execute_command(self, cmd: ActionCommand) -> bool:
        """执行玩家操作命令（本地 / 网络 / AI 共用入口）。"""
        if cmd.player_id < 0 or cmd.player_id >= len(self.state.players):
            return False
        player = self.state.players[cmd.player_id]
        if self.state.turn_order and player.id != self.current_player.id:
            self._log(f"{player.name} 的操作被拒绝：还没轮到该玩家。")
            return False
        if player.dead and cmd.action != "end_turn":
            # 死者只剩"结束回合"这一条命令。以前没有任何闸门，机器人倒下后
            # 还能被自己的收尾逻辑带着捡回刚掉落的牌（seed7/3p 实测：
            # 倒下 → 物品掉落 → 又"捡起了 疯子/铃铛/咬伤"）。
            return False
        data = cmd.data or {}
        self._active_player_id = player.id
        try:
            if cmd.action == "move":
                option = data.get("option")
                if isinstance(option, dict):
                    option = self._resolve_exit_option(player, option)
                if option is None:
                    return False
                return self.move_player(player, option)
            if cmd.action == "use_item":
                return self.use_item(player, data["card_id"])
            if cmd.action == "pickup":
                return self.pickup_item(player, data["card_id"])
            if cmd.action == "drop":
                return self.drop_item(player, data["card_id"])
            if cmd.action == "trade":
                target = self.state.players[data["target_id"]]
                return self.trade_item(player, target, data["card_id"], data.get("target_card_id"))
            if cmd.action == "attack":
                return self.attack(
                    player,
                    data["target"],
                    data.get("weapon_card_id"),
                    data.get("ranged", False),
                )
            if cmd.action == "haunt_action":
                return self.perform_haunt_action(player, data["action_id"], data.get("data"))
            if cmd.action == "end_turn":
                self.end_turn()
                return True
            return False
        finally:
            self._active_player_id = None

    def _resolve_exit_option(self, player: Player, option: dict) -> ExitOption | None:
        """把远程/字典形式的移动选项匹配为本地 ExitOption。"""
        direction = option.get("direction")
        target_key = option.get("target_key")
        for cand in self.available_move_options(player):
            if cand.direction == direction and cand.target_key == target_key:
                return cand
        return None

    def _is_attack_weapon(self, card: Card) -> bool:
        return "weapon" in card.tags

    def available_attack_weapons(self, player: Player | None = None) -> list[str]:
        player = player or self.current_player
        if player.dead or self.state.phase != "HAUNT_PHASE" or player.attack_used:
            return []
        return [card_id for card_id in player.items if self._is_attack_weapon(self.catalog.cards[card_id])]

    def _advance_turn(self) -> None:
        if not self.state.turn_order:
            return
        for _ in range(len(self.state.turn_order)):
            self.state.turn_index = (self.state.turn_index + 1) % len(self.state.turn_order)
            candidate = self.current_player
            if not candidate.dead:
                return
        self.state.turn_index = 0

    def available_move_options(self, player: Player | None = None) -> list[ExitOption]:
        player = player or self.current_player
        if player.dead or player.movement_stopped:
            return []
        room = self.current_room(player)
        options: list[ExitOption] = []
        # 剧本可以关掉探索（33 号 p44/p115："没有进地下室的已探明通路前不能
        # 探索新房间"）。这里必须同步过滤，否则引擎会给出一个"走的时候才被
        # 拒绝"的假选项——机器人会整局死循环在上面（seed101/5p 实测：400 回合
        # 全是"无法发现新房间"，一步没动）。
        can_discover = self._mode_handler().can_discover_rooms(self, player)

        for direction in room.doors:
            barrier = self._barrier_config(room)
            if barrier and barrier["doors"].get(direction) != self._barrier_side(player):
                continue
            if direction not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[direction]
            target_pos = (room.floor, room.x + dx, room.y + dy)
            target_key = self.state.pos_index.get(target_pos)
            if target_key:
                target_room = self.state.board[target_key]
                if (
                    not target_room.data.get(self.COLLAPSE_KEY)
                    and OPPOSITE[direction] in target_room.doors
                    and not self._mode_handler().room_entry_blocked(self, player, target_room)
                ):
                    cost = self._movement_cost(player, room, from_key=player.room_key)
                    options.append(
                        ExitOption(
                            label=f"向{self._direction_cn(direction)}移动到 {target_room.name}",
                            direction=direction,
                            target_key=target_key,
                            target_room_name=target_room.name,
                            is_new_room=False,
                            cost=cost,
                        )
                    )
                continue

            if can_discover and self._floor_has_room_capacity(room.floor):
                options.append(
                    ExitOption(
                        label=f"向{self._direction_cn(direction)}探索新房间",
                        direction=direction,
                        target_key=target_key or "",
                        target_room_name=None,
                        is_new_room=True,
                        cost=self._movement_cost(player, room, from_key=player.room_key),
                    )
                )

        if self._barrier_config(room) and self._barrier_can_attempt(player, room):
            options.append(ExitOption(label="跨越房间障碍", direction="cross_barrier", target_key=room.key,
                                      target_room_name=room.name, is_special=True, cost=0))
        # 已能通过门到达的目标（避免楼梯链接与门重复出现）
        door_reached = {option.target_key for option in options if not option.is_new_room}

        for label, target in room.links.items():
            if label in DIRECTIONS:  # 方位型链接已被门覆盖，忽略，避免"使用west"这类无意义选项
                continue
            target_key = self._link_target_key(target)
            if (
                target_key is None
                or target_key in door_reached
                or self._is_collapsed(target_key)
                or self._mode_handler().room_entry_blocked(self, player, self.state.board[target_key])
            ):
                continue
            cost = self._movement_cost(player, room, from_key=player.room_key)
            options.append(
                ExitOption(
                    label=f"使用{self._special_link_cn(label)}前往 {self.state.board[target_key].name}",
                    direction=label,
                    target_key=target_key,
                    target_room_name=self.state.board[target_key].name,
                    is_new_room=False,
                    is_special=True,
                    cost=cost,
                )
            )
        # 反向链接：楼梯这类连接只在一侧声明（"地下室楼梯"声明 up→"入口大厅"，
        # 入口大厅没有对应的 down 链接）。_build_graph 会对称补边，出口生成却只看
        # 本房间的 links——于是"图里相邻、实际走不过去"：机器人寻路会把这条件
        # 边当成下一步，承诺加成落在一个不存在的选项上，于是原地打转
        # （13 号 seed137/3p：英雄在入口大厅↔厨房来回 16 次，而去地下墓穴其实
        # 只要下两层楼）。楼梯在物理上双向可走，这里为指向本房间的单侧链接补出
        # 反向出口，让出口与图重新一致。
        reverse_labels = {"up": "down", "down": "up"}
        for other_key, other in self.state.board.items():
            if other_key == room.key or self._is_collapsed(other_key):
                continue
            for label, value in other.links.items():
                if label in DIRECTIONS:  # 方位型链接由门覆盖，同正向循环
                    continue
                if self._link_target_key(value) != room.key:
                    continue
                if any(
                    not option.is_new_room and option.target_key == other_key
                    for option in options
                ):
                    break  # 门或本房间自己的链接已经能到这里，不必重复
                if self._mode_handler().room_entry_blocked(self, player, other):
                    break
                reverse = reverse_labels.get(label, label)
                options.append(
                    ExitOption(
                        label=f"使用{self._special_link_cn(reverse)}前往 {other.name}",
                        direction=reverse,
                        target_key=other_key,
                        target_room_name=other.name,
                        is_new_room=False,
                        is_special=True,
                        cost=self._movement_cost(player, room, from_key=player.room_key),
                    )
                )
                break
        # 剧本可追加额外移动选项（剧本 33 p44：从地下湖的无门水缘划入湖面）。
        options.extend(self._mode_handler().extra_move_options(self, player, options))
        return options

    def _no_door_faces_wall(self, target_pos: tuple[int, int, int], doors: tuple[str, ...]) -> bool:
        """检查：房间的所有门都不能指向"已被占据且没有对应门"的位置（门对墙）。"""
        floor, x, y = target_pos
        for door in doors:
            if door not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[door]
            pos = (floor, x + dx, y + dy)
            key = self.state.pos_index.get(pos)
            if key:
                neighbor = self.state.board[key]
                if OPPOSITE[door] not in neighbor.doors:
                    return False
        return True

    def _compute_explore_placements(
        self,
        template: RoomTemplate,
        entry_direction: str,
        target_pos: tuple[int, int, int],
    ) -> list[dict]:
        """探索新房间时的所有合法放置方案（无门对墙、楼层不封闭）。
        每个方案记录 rotation，以及"连回上一个房间的门"（用原模板中的方向表示）。"""
        results: list[dict] = []
        for rotation in range(4):
            doors = _rotate_doors(template.doors, rotation)
            if OPPOSITE[entry_direction] not in doors:
                continue
            links = _rotate_links(template.links, rotation)
            if not self._no_door_faces_wall(target_pos, doors):
                continue
            if not self._placement_keeps_frontier(target_pos, doors, links):
                continue
            back_door = DIRECTIONS[(DIRECTIONS.index(OPPOSITE[entry_direction]) - rotation) % 4]
            results.append({
                "rotation": rotation,
                "doors": doors,
                "links": links,
                "entry_door": back_door,
            })
        return results

    def _rotation_label(self, placement: dict) -> str:
        door = placement["entry_door"]
        doors_cn = "、".join(self._direction_cn(d) for d in placement["doors"])
        return f"用房间的{self._direction_cn(door)}门连接 → 房门朝 {doors_cn}"

    def _build_rotated_template(self, template: RoomTemplate, rotation: int) -> RoomTemplate:
        return RoomTemplate(
            id=template.id,
            name=template.name,
            source_name=template.source_name,
            floor=template.floor,
            doors=_rotate_doors(template.doors, rotation),
            symbol=template.symbol,
            effect_id=template.effect_id,
            text=template.text,
            special=template.special,
            links=_rotate_links(template.links, rotation),
            tags=template.tags,
            generated=template.generated,
        )

    def move_player(self, player: Player, option: ExitOption) -> bool:
        if player.dead or player.movement_stopped:
            return False
        if option.direction == "cross_barrier":
            return option.target_key == player.room_key and self._cross_barrier(player)
        config = self._barrier_config(self.current_room(player))
        if config and option.direction in config["doors"] and config["doors"][option.direction] != self._barrier_side(player):
            return False
        if player.steps_remaining <= 0 and player.moved_this_turn:
            self._log(f"{player.name} 已没有剩余移动力。")
            return False

        current_room = self.current_room(player)
        cost = self._movement_cost(player, current_room, from_key=player.room_key)
        if cost > player.steps_remaining:
            if player.steps_remaining <= 0:
                self._log(f"{player.name} 已没有足够的移动力。")
                return False
            self._log(f"{player.name} 仍可移动 1 格，但遇敌代价会吃掉剩余移动力。")
            cost = player.steps_remaining

        if option.is_new_room:
            if player.frog:
                # p14：青蛙不能发现新房间。走到门口就停下，门还留着下次再探。
                self._log("青蛙不能发现新房间。")
                player.movement_stopped = True
                return False
            if not self._mode_handler().can_discover_rooms(self, player):
                # 剧本可禁止发现新房间（剧本 27 p109：Blobperson 不能发现房间）。
                self._log(f"{self._player_label(player)} 无法发现新房间。")
                player.movement_stopped = True
                return False
            dx, dy = DIRECTION_DELTAS[option.direction]
            target_pos = (current_room.floor, current_room.x + dx, current_room.y + dy)
            new_room = None
            # 尝试上限：牌不够放时弃牌堆会被循环补进牌堆，下面这个 while
            # 必须有界，否则"该位置放不进任何房间牌"会变成无限循环
            # （种子 109,4 的 28 号局实测触发）。
            draw_budget = len(self.state.room_deck) + len(self.state.room_discard) + 1
            while True:
                if draw_budget <= 0:
                    self._log("这一层的房间牌都放不进这个方向，只好作罢。")
                    return False
                draw_budget -= 1
                template = self._draw_room_template(current_room.floor)
                if template is None:
                    self._log("这一层已经没有可用的新房间了。")
                    return False
                if self._mode_handler().room_entry_blocked(self, player, template):
                    # 剧本可禁止探索特定房间（剧本 26 p37/p108：英雄进不了
                    # 五芒星室——抽到它就弃掉换一张，而不是把它放上桌再进去）。
                    self.state.room_discard.append(template.id)
                    self._log(f"{self._player_label(player)}抽到了{template.name}，但那里进不去，换一张再试。")
                    continue
                placements = self._compute_explore_placements(template, option.direction, target_pos)
                if not placements:
                    self.state.room_discard.append(template.id)
                    self._log(f"{template.name} 在这个方向放不下，换一张再试。")
                    continue
                if len(placements) > 1:
                    idx = self.prompter.choose_rotation(
                        "放置方向",
                        f"抽到「{template.name}」，请旋转到合适方向后点确定：",
                        placements,
                        option.direction,
                    )
                    if idx is None:
                        self.state.room_discard.append(template.id)
                        self._log(f"{self._player_label(player)} 取消了这次探索。")
                        return False
                    placement = placements[idx]
                else:
                    placement = placements[0]
                rotation = placement["rotation"]
                rotated = self._build_rotated_template(template, rotation)
                new_room = self._place_room(rotated, target_pos[1], target_pos[2], rotation)
                self._log(f"翻开新房间：{new_room.name}")
                target_key = new_room.key
                break
        else:
            target_key = option.target_key
            if isinstance(target_key, str) and target_key.startswith("lake:"):
                # 剧本 33：湖面砖按需铺设并移动，由剧本完全接管。
                return self._mode_handler().lake_move(self, player, option)
            if target_key not in self.state.board:
                self._log("目标房间不存在。")
                return False

        player.room_key = target_key
        arrival_direction = OPPOSITE.get(option.direction)
        self._barrier_choose_arrival(player, self.state.board[target_key], arrival_direction)
        player.steps_remaining = max(0, player.steps_remaining - cost)
        player.moved_this_turn = True
        self._log(f"{player.name} 移动到 {self.state.board[target_key].name}。")
        # 剧本可跟随移动（剧本 3 p14：背着青蛙走，蛙跟着主人）。
        self._mode_handler().on_player_moved(self, player)
        self._resolve_room_entry_if_needed(player)
        if option.is_new_room and not self._mode_handler().explore_stop_suspended(self, player):
            # 探索新房间会结束本回合移动（无论房间是否有特效）。
            # 例外：剧本 25 p36 明文解除"进带符号的新房间必须停"的限制，
            # 可以连续探索，只在结束移动的房间有符号时才抽牌。
            player.movement_stopped = True
            player.steps_remaining = 0
        self.check_victory()
        return True

    def _movement_cost(self, player: Player, room: PlacedRoom, from_key: str | None = None) -> int:
        if self.state.phase != "HAUNT_PHASE":
            return 1
        hostile_count = 0
        for occupant in self.room_occupants(room.key):
            if occupant["kind"] == "player" and occupant["player"].role != player.role and not occupant["player"].dead:
                if self._mode_handler().counts_as_movement_obstacle(self, player, occupant["player"]):
                    hostile_count += 1
            elif occupant["kind"] == "monster" and occupant["monster"].stunned_turns <= 0:
                hostile_count += 1
        cost = 1 + hostile_count
        # 剧本可加倍移动费用（剧本 14 p96：背着尸体入房按 2 格计）。
        cost *= max(1, int(self._mode_handler().movement_cost_multiplier(self, player, from_key)))
        # 剧本可抬高移动费用下限（剧本 17 p99：蟑螂守厨房离开按 3 格；
        # 剧本 33 p44：湖面砖按游泳检定结果计 2/3 格）。
        floor = int(self._mode_handler().movement_cost_floor(self, player, from_key, to_key=room.key))
        if floor > cost:
            cost = floor
        return cost

    def _floor_has_room_capacity(self, floor: int) -> bool:
        if not self.has_remaining_room_cards(floor):
            return False
        for room in self.state.board.values():
            if room.floor == floor:
                for direction in room.doors:
                    if direction not in DIRECTION_DELTAS:
                        continue
                    dx, dy = DIRECTION_DELTAS[direction]
                    pos = (floor, room.x + dx, room.y + dy)
                    if pos not in self.state.pos_index:
                        return True
                for target in room.links.values():
                    if self._link_target_key(target) is None:
                        return True
        return False

    def _choose_room_rotation(
        self,
        template: RoomTemplate,
        direction: str,
        target_pos: tuple[int, int, int],
    ) -> tuple[RoomTemplate, int] | None:
        best: tuple[int, int, tuple[str, ...], dict[str, str]] | None = None
        for rotation in range(4):
            doors = _rotate_doors(template.doors, rotation)
            if OPPOSITE[direction] not in doors:
                continue
            links = _rotate_links(template.links, rotation)
            score = 0
            for door in doors:
                if door not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[door]
                pos = (target_pos[0], target_pos[1] + dx, target_pos[2] + dy)
                neighbor_key = self.state.pos_index.get(pos)
                if neighbor_key:
                    neighbor = self.state.board[neighbor_key]
                    if OPPOSITE[door] in neighbor.doors:
                        score += 1
            if best is None or score > best[0]:
                best = (score, rotation, doors, links)
        if best is None:
            return None
        score, rotation, doors, links = best
        if not self._placement_keeps_frontier(target_pos, doors, links):
            return None
        rotated = RoomTemplate(
            id=template.id,
            name=template.name,
            source_name=template.source_name,
            floor=template.floor,
            doors=doors,
            symbol=template.symbol,
            effect_id=template.effect_id,
            text=template.text,
            special=template.special,
            links=links,
            tags=template.tags,
            generated=template.generated,
        )
        return rotated, rotation

    def _placement_keeps_frontier(self, target_pos: tuple[int, int, int], doors: tuple[str, ...], links: dict[str, str]) -> bool:
        floor, x, y = target_pos
        simulated_room = PlacedRoom(
            key=_room_key(floor, x, y),
            template_id="temp",
            name="temp",
            floor=floor,
            x=x,
            y=y,
            doors=doors,
            links=dict(links),
        )
        temp_board = dict(self.state.board)
        temp_board[simulated_room.key] = simulated_room
        temp_index = dict(self.state.pos_index)
        temp_index[(floor, x, y)] = simulated_room.key
        for room in temp_board.values():
            if room.floor != floor:
                continue
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                pos = (floor, room.x + dx, room.y + dy)
                if pos not in temp_index:
                    return True
            for target in room.links.values():
                if target not in temp_board:
                    return True
        return False

    def _ensure_room_in_play(
        self,
        template_id: str,
        origin_room_key: str | None = None,
        farthest_from_key: str | None = None,
    ) -> str | None:
        """确保指定模板的房间在场上；不在就从房间牌堆取出并放下。

        有些剧本依赖特定房间：剧本 3 的温室/储藏室/厨房长着曼德拉草，剧本 2
        的五芒星室是降灵会唯一场所。但探索阶段未必翻得到它们，而作祟之后
        探险者不再为探索而探索，这些房间可能整局都不出现，剧本会直接卡死
        （seed=109 实测：三间房一间都没出现，曼德拉草一株都没生成）。
        原版对此有先例（p84："If the Pentagram Chamber isn't in the house,
        search the room stack for it and put it ..."），这里做成通用能力。

        farthest_from_key：给出房间 key 时，在全部合法落位里选**离它最远**的
        那个（p84 后半句："距你至少五格远；若没有，就尽量远"）。不给则维持
        原行为（第一个合法位）。

        返回房间 key；已存在则直接返回；牌堆里没有或实在放不下则返回 None
        （此时会把牌还回牌堆，绝不让它凭空消失）。
        """
        for room in self.state.board.values():
            if room.template_id == template_id:
                return room.key
        template = self.catalog.room_templates.get(template_id)
        if template is None:
            return None
        for deck in (self.state.room_deck, self.state.room_discard):
            if template_id in deck:
                deck.remove(template_id)
                break
        else:
            return None

        # 只在该模板所属楼层找空位，避免把地面层房间塞进地下室。
        # 锚点还必须是**同层**房间：跨层锚点会把 (x, y) 直接搬到另一层去，
        # 而那个位置在那层往往四面皆空，房间会变成永远走不到的孤岛。
        # （70 号实测：地下室房间 -1:0:-3 的东门算出坐标 (1, -3)，温室按自己
        #  的楼层落到一层 (1, -3)，三个邻居位全空，形态房间永远访不到。）
        # 先把全部合法落位收集完再决定：试放会改变棋盘，边收边放会污染
        # 后续候选的 _placement_keeps_frontier 判断。
        origin_keys: list[str] = []
        if (
            origin_room_key
            and origin_room_key in self.state.board
            and self.state.board[origin_room_key].floor == template.floor
        ):
            origin_keys.append(origin_room_key)
        origin_keys.extend(
            key
            for key in sorted(self.state.board)
            if key != origin_room_key and self.state.board[key].floor == template.floor
        )
        candidates: list[tuple[tuple[int, int, int], dict]] = []
        for origin_key in origin_keys:
            origin = self.state.board[origin_key]
            for direction in sorted(origin.doors):
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                pos = (origin.floor, origin.x + dx, origin.y + dy)
                if pos in self.state.pos_index:
                    continue
                placements = self._compute_explore_placements(template, direction, pos)
                if not placements:
                    continue
                candidates.append((pos, placements[0]))
        if not candidates:
            self.state.room_deck.insert(0, template_id)
            return None

        # 连通性优先：剧本关键房间必须落在**玩家走得到**的位置。传送房
        # （神秘电梯）进入即被送走，不能当作中转，`avoid_transit=True` 的
        # 路径会把"只能经电梯进入"的落位判成不可达（剧本 2 实测：五芒星室
        # 被放到电梯西侧，进电梯就被传送走，降灵会永远开不起来）。
        walkable = self._walkable_candidates(template, candidates)
        if walkable:
            candidates = walkable

        chosen: tuple[tuple[int, int, int], dict] | None = None
        distance = -1
        if farthest_from_key and farthest_from_key in self.state.board:
            for pos, placement in candidates:
                rotated = self._build_rotated_template(template, placement["rotation"])
                probe = self._place_room(rotated, pos[1], pos[2], placement["rotation"])
                measured = self._path_length(farthest_from_key, probe.key, avoid_transit=True)
                del self.state.board[probe.key]
                del self.state.pos_index[pos]
                if measured == 9999:
                    # 走不到的落位不是"远"，是把房间藏起来；只在全不可达时才退而求其次。
                    continue
                if measured > distance:
                    distance = measured
                    chosen = (pos, placement)
        if chosen is None:
            chosen = candidates[0]
            distance = -1

        pos, placement = chosen
        rotated = self._build_rotated_template(template, placement["rotation"])
        room = self._place_room(rotated, pos[1], pos[2], placement["rotation"])
        # p10：房间以作祟指令等非探索方式放入时，首个进入者不抽符号牌。
        room.data["no_first_draw"] = True
        if distance >= 0:
            self._log(f"「{room.name}」被拉进了这栋房子（距叛徒 {distance} 格）。")
        else:
            self._log(f"「{room.name}」被强行拉进了这栋房子。")
        return room.key

    def _walkable_candidates(
        self,
        template: RoomTemplate,
        candidates: list[tuple[tuple[int, int, int], dict]],
    ) -> list[tuple[tuple[int, int, int], dict]]:
        """筛出"放上去之后玩家走得到"的落位（试放临时板块测路径）。

        判定用 `avoid_transit=True`：传送房（神秘电梯）进入即被送走，不能
        当作中转，所以"只能靠电梯到达"的落位会被算成不可达。入口大厅不在场
        时无从判定，返回空表表示"不筛"。
        """
        root = next(
            (
                key
                for key, room in self.state.board.items()
                if room.template_id == "entrance_hall"
            ),
            None,
        )
        if root is None:
            return []
        result: list[tuple[tuple[int, int, int], dict]] = []
        for pos, placement in candidates:
            rotated = self._build_rotated_template(template, placement["rotation"])
            probe = self._place_room(rotated, pos[1], pos[2], placement["rotation"])
            reachable = self._path_length(root, probe.key, avoid_transit=True) != 9999
            self.state.board.pop(probe.key, None)
            self.state.pos_index.pop((probe.floor, probe.x, probe.y), None)
            if reachable:
                result.append((pos, placement))
        return result

    def _place_room(self, template: RoomTemplate, x: int, y: int, rotation: int) -> PlacedRoom:
        # 注意：调用方（move_player / _choose_room_rotation）传入的 template 已经是旋转后的，
        # 这里不再二次旋转 doors/links，否则会造成"双重旋转"、门方向错乱。
        key = _room_key(template.floor, x, y)
        room = PlacedRoom(
            key=key,
            template_id=template.id,
            name=template.name,
            floor=template.floor,
            x=x,
            y=y,
            rotation=rotation,
            doors=tuple(template.doors),
            symbol=template.symbol,
            effect_id=template.effect_id,
            text=template.text,
            special=template.special,
            links=dict(template.links),
            data={},
        )
        self.state.board[key] = room
        self.state.pos_index[(template.floor, x, y)] = key
        return room

    STOP_RISK_EFFECTS = frozenset({
        "room_vault", "room_research_laboratory", "room_coal_chute",
        "room_collapsed_room", "room_chasm", "room_catacombs",
        "room_mystic_elevator", "room_underground_lake",
    })

    def _resolve_event(self, player: Player, card: Card) -> None:
        effect = card.effect_id
        if effect == "event_bloody_vision":
            if not self._resolve_check(player, "sanity", 4, card.name):
                self._deal_damage(player, "physical", 1, source=card.name)
            return
        if effect == "event_grave_dirt":
            self._deal_damage(player, "physical", 1, source=card.name)
            return
        if effect == "event_lights_out":
            player.steps_remaining = min(player.steps_remaining, 1)
            self._log("熄灯让这一回合的移动变得更困难。")
            return
        if effect == "event_mists_from_the_walls":
            for other in self.state.players:
                if not other.dead and self.current_room(other).floor == -1:
                    self._deal_damage(other, "mental", 1, source=card.name)
            return
        if effect == "event_mystic_slide":
            self._move_to_room(player, "basement_landing", via_effect=True)
            return
        if effect == "event_secret_passage":
            self._create_secret_link(player, same_floor=True)
            return
        if effect == "event_secret_stairs":
            self._create_secret_link(player, same_floor=False)
            return
        if effect == "event_silence":
            for other in self.state.players:
                if not other.dead and self.current_room(other).floor == -1:
                    self._deal_damage(other, "mental", 1, source=card.name)
            return
        if effect == "event_lost_one" or effect == "event_the_walls":
            self._move_to_room(player, "basement_landing", via_effect=True)
            return
        if effect == "event_awful_waffles":
            if not self._resolve_check(player, "might", 4, card.name):
                self._deal_damage(player, "physical", 1, source=card.name)
            return
        if effect == "event_smoke":
            if not self._resolve_check(player, "speed", 4, card.name):
                player.steps_remaining = 0
                player.movement_stopped = True
            return
        if effect == "event_whoops":
            if not self._resolve_check(player, "speed", 4, card.name):
                self._deal_damage(player, "physical", 1, source=card.name)
                player.steps_remaining = 0
                player.movement_stopped = True
            return
        if effect == "event_disquieting_sounds":
            if not self._resolve_check(player, "sanity", 4, card.name):
                self._deal_damage(player, "mental", 1, source=card.name)
            return
        if effect == "event_spider":
            if not self._resolve_check(player, "speed", 3, card.name):
                self._deal_damage(player, "physical", 1, source=card.name)
            return
        if effect == "event_closet_door":
            if self._resolve_check(player, "knowledge", 4, card.name):
                self._draw_item(player)
            else:
                self._deal_damage(player, "mental", 1, source=card.name)
            return
        if effect == "event_locked_safe":
            if self._resolve_check(player, "knowledge", 5, card.name):
                self._draw_item(player)
            else:
                player.steps_remaining = 0
                player.movement_stopped = True
            return
        if effect == "event_groundskeeper":
            if self._resolve_check(player, "knowledge", 4, card.name):
                self._draw_item(player)
            return
        if effect == "event_something_slimy":
            if not self._resolve_check(player, "might", 4, card.name):
                self._apply_stat_loss(player, "speed", 1)
            return
        if effect == "event_a_moment_of_hope":
            choice = self.prompter.choose_from_list(card.name, "选择恢复一项精神属性。", ["理智", "知识"])
            index = 0 if choice is None else max(0, min(1, choice))
            self._heal_stat(player, ("sanity", "knowledge")[index], 1)
            return
        if effect == "event_hanged_men":
            if not self._resolve_check(player, "sanity", 4, card.name):
                self._deal_damage(player, "mental", 1, source=card.name)
                player.steps_remaining = 0
                player.movement_stopped = True
            return
        if effect == "event_jonahs_turn":
            player.extra_check_rerolls += 1
            self._log(f"{player.name} 获得 1 次额外检定重掷。")
            return
        if effect == "event_it_is_meant_to_be":
            player.saved_roll = self.roll_dice(max(1, self._effective_stat(player, "knowledge")), card.name)
            self._log(f"{player.name} 保存了掷骰结果 {player.saved_roll}。")
            return
        if effect == "event_something_hidden":
            if self._resolve_check(player, "knowledge", 4, card.name):
                self._draw_item(player)
            return
        if effect == "event_the_voice":
            if not self._resolve_check(player, "sanity", 4, card.name):
                self._apply_stat_loss(player, "knowledge", 1)
                self._move_to_room(player, "basement_landing", via_effect=True)
            return
        if effect == "event_webs":
            if not self._resolve_check(player, "might", 4, card.name):
                player.steps_remaining = 0
                player.movement_stopped = True
            return
        if effect == "event_night_view":
            if self._resolve_check(player, "sanity", 4, card.name):
                self._increase_stat(player, "speed", 1)
            else:
                self._deal_damage(player, "mental", 1, source=card.name)
            return
        if effect == "event_creepy_crawlies":
            if not self._resolve_check(player, "might", 4, card.name):
                self._deal_damage(player, "physical", 1, source=card.name)
                player.steps_remaining = 0
                player.movement_stopped = True
            return
        if effect == "event_phone_call":
            choice = self.prompter.choose_from_list(card.name, "电话那头传来两个选择。", ["恢复 1 点知识", "再抽 1 张事件牌"])
            if choice == 1:
                self._draw_event(player)
            else:
                self._heal_stat(player, "knowledge", 1)
            return

    def _create_secret_link(self, player: Player, same_floor: bool) -> None:
        room = self.current_room(player)
        candidates = [
            other
            for other in self.state.board.values()
            if other.key != room.key and (other.floor == room.floor if same_floor else other.floor != room.floor)
        ]
        if not candidates:
            return
        target = self.rng.choice(candidates)
        room.links["secret"] = target.key
        target.links["secret"] = room.key
        self._log(f"{room.name} 与 {target.name} 之间多了一条秘密通道。")

    def _turn_into_frog(self, player: Player) -> None:
        """剧本 3：把探险者变成青蛙（英雄手册 p14）。

        "An explorer who is turned into a Frog drops all items and discards
         any companions. Lower that character's Might and Knowledge to their
         lowest numbers. (Don't lower either trait to the skull symbol.)
         A Frog can't attack, draw cards, or discover rooms."
        """
        if player.frog or player.dead:
            return
        player.frog = True
        room = self.current_room(player)
        # 丢弃所有物品（留在房间里，其他探险者可以捡）
        for card_id in list(player.items):
            self._discard_card_from_player(player, card_id, return_to_room=True)
        player.companions.clear()
        # 力量与知识降到最低格，但不降到骷髅（-1）
        for stat in ("might", "knowledge"):
            track = self._stat_track(player, stat)
            if track:
                player.stat_positions[stat] = 0
                player.stats[stat] = track[0]
        player.steps_remaining = 0
        player.movement_stopped = False
        self._log(f"{player.name} 变成了一只青蛙！物品散落在{room.name}。")
        self.check_victory()

    def _restore_from_frog(self, player: Player) -> None:
        """剧本 3：把青蛙变回人，属性恢复到角色卡的初始值（p14）。"""
        if not player.frog:
            return
        face = self.catalog.characters.get(player.character_id)
        if face is None:
            return
        player.frog = False
        for stat in STAT_NAMES:
            initial = face.stats.get(stat)
            track = self._stat_track(player, stat)
            if track and initial is not None:
                idx = min(range(len(track)), key=lambda i: abs(track[i] - initial))
                player.stat_positions[stat] = idx
                player.stats[stat] = track[idx]
        self._log(f"{player.name} 恢复了人形！")

    def spawn_token(
        self,
        kind: str,
        label: str = "",
        role: str = "marker",
        room_key: str = "",
        holder: int | None = None,
        face_up: bool = True,
    ) -> Token:
        """生成一个令牌。同类令牌可重复调用生成多份（如 24 只蝙蝠）。"""
        counters = self.state.meta.setdefault("token_serials", {})
        prefix = kind + "#"
        existing = [int(t.uid[len(prefix):]) for t in self.state.tokens
                    if t.uid.startswith(prefix) and t.uid[len(prefix):].isdigit()]
        serial = max([int(counters.get(kind, 0))] + existing) + 1
        counters[kind] = serial
        token = Token(
            uid=f"{kind}#{serial}",
            kind=kind,
            label=label or kind,
            role=role,
            room_key=room_key,
            holder=holder,
            face_up=face_up,
        )
        self.state.tokens.append(token)
        return token

    def spawn_tokens(self, kind: str, count: int, **kwargs) -> list[Token]:
        return [self.spawn_token(kind, **kwargs) for _ in range(max(0, count))]

    def token_by_uid(self, uid: str) -> Token | None:
        return next((token for token in self.state.tokens if token.uid == uid), None)

    def tokens_of_kind(self, kind: str) -> list[Token]:
        return [token for token in self.state.tokens if token.kind == kind]

    def tokens_in_room(self, room_key: str, kind: str | None = None) -> list[Token]:
        return [
            token
            for token in self.state.tokens
            if token.room_key == room_key and (kind is None or token.kind == kind)
        ]

    def tokens_held_by(self, player_id: int, kind: str | None = None) -> list[Token]:
        return [
            token
            for token in self.state.tokens
            if token.holder == player_id and (kind is None or token.kind == kind)
        ]

    def place_token(self, uid: str, room_key: str) -> bool:
        """把令牌放到房间。若原本被携带，会先从携带者手上取下。"""
        token = self.token_by_uid(uid)
        if token is None or room_key not in self.state.board:
            return False
        token.holder = None
        token.room_key = room_key
        return True

    def give_token(self, uid: str, player_id: int) -> bool:
        token = self.token_by_uid(uid)
        if token is None or not 0 <= player_id < len(self.state.players):
            return False
        token.room_key = ""
        token.holder = player_id
        return True

    def flip_token(self, uid: str, face_up: bool | None = None) -> bool:
        token = self.token_by_uid(uid)
        if token is None:
            return False
        token.face_up = not token.face_up if face_up is None else face_up
        return True

    def remove_token(self, uid: str) -> bool:
        token = self.token_by_uid(uid)
        if token is None:
            return False
        self.state.tokens = [item for item in self.state.tokens if item.uid != uid]
        return True

    def clear_tokens(self) -> None:
        self.state.tokens = []

    def _apply_start_of_turn_haunt_effects(self, player: Player) -> None:
        if not self.state.haunt or player.dead:
            return
        # 剧本专属的回合开始效果（诅咒发作、计时器等）由 mode handler 提供。
        self._mode_handler().on_turn_start(self, player)

    def _resolve_haunt_check(self, revealer: Player) -> bool:
        if not self.state.haunt_pending:
            return False
        roll = self.roll_dice(6, "作祟检定")
        self._log(f"作祟检定：掷出 {roll}，预兆总数为 {self.state.omens_drawn}。")
        normal_trigger = roll < self.state.omens_drawn
        no_future_omen = not self._has_future_omen_source()
        if normal_trigger:
            self._trigger_haunt(revealer)
            return True
        if no_future_omen:
            # 规则框架中预兆牌和预兆房间都是有限资源；如果最后一次预兆
            # 检定失败而场上已经不存在未来预兆来源，继续游戏会永远卡在探索期。
            self._log("所有预兆来源都已用尽；本次检定作为最后一次预兆检定，触发作祟。")
            self._trigger_haunt(revealer)
            return True
        self._log("这次没有触发作祟。")
        return False

    def _has_future_omen_source(self) -> bool:
        """判断失败后是否仍有机会通过未来预兆进入作祟。

        不调用 _draw_card_id 的重建逻辑：预兆在本游戏中是一次性资源，
        已耗尽的预兆牌不能因为牌堆为空而凭空重新生成。
        """
        if not self.state.card_decks.get("omen") and not self.state.card_discards.get("omen"):
            # 牌都没了：就算还有预兆房间也抽不出预兆，别再假装有未来来源。
            return False
        for room in self.state.board.values():
            if not room.revealed and room.symbol == "omen":
                return True
        for room_id in (*self.state.room_deck, *self.state.room_discard):
            template = self.catalog.room_templates.get(room_id)
            if template and template.symbol == "omen" and self._can_place_template(template):
                # 预兆房还得**放得下**才算未来来源：'还剩一张预兆牌'不等于
                # '还能翻出预兆房'。seed131/3p 实测：全屋铺满 48/49 间后，
                # 仅剩的小教堂（预兆房）落在没有任何合法落位的位置上，
                # 引擎却一直认为未来还有预兆，探索期永远不结束。
                return True
        return False

    def _can_place_template(self, template: RoomTemplate) -> bool:
        """这张房间牌是否还有合法落位（与探索时的放置规则同一套）。"""
        for room in self.state.board.values():
            if room.floor != template.floor:
                continue
            if room.template_id in self.NON_TRANSIT_TEMPLATES:
                # 传送房不能从里面翻门（见 exploration_frontier_keys）。
                continue
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                pos = (room.floor, room.x + dx, room.y + dy)
                if pos in self.state.pos_index:
                    continue
                if self._compute_explore_placements(template, direction, pos):
                    return True
        return False

    def _trigger_haunt(self, revealer: Player) -> None:
        if not self.state.last_omen_id:
            return
        current_room = self.current_room(revealer)
        haunt_id = self._select_haunt_id(current_room.template_id if current_room else "", self.state.last_omen_id)
        haunt = self.catalog.haunt_defs[haunt_id]
        traitor = self._select_traitor(haunt, revealer)
        self.state.haunt = haunt
        self.state.haunt_revealer_id = revealer.id
        self.state.traitor_id = traitor.id
        self.state.phase = "HAUNT_REVEAL"
        self._log(f"作祟揭示：#{haunt.id} {haunt.name}。")
        self._apply_roles(revealer, traitor, haunt)
        self._initialize_haunt_rules(haunt, current_room.key)
        self._spawn_haunt_monsters(haunt, current_room.key)
        # 放在怪物生成之后：很多剧本的 setup 要把令牌放到怪物所在房间。
        self._mode_handler().setup(self, haunt, current_room.key)
        self._prepare_haunt_turn_order(traitor.id)
        self.state.phase = "HAUNT_PHASE"
        self._log("作祟私密信息已发送。")
        self._show_private_haunt_briefings()

    def _select_haunt_id(self, room_id: str, omen_id: str) -> int:
        payload = f"{room_id}|{omen_id}".encode("utf-8")
        value = int(hashlib.sha1(payload).hexdigest(), 16)
        # 新版合并了原版 1-50 与扩展 51-70；70 个剧本都必须有机会被抽到。
        return (value % 70) + 1

    def _select_traitor(self, haunt: Haunt, revealer: Player) -> Player:
        players = self.state.players[:]
        if haunt.traitor_rule == "highest_might_except_revealer":
            eligible = [p for p in players if p.id != revealer.id and not p.dead]
            best = max(p.stats["might"] for p in eligible)
            return self._resolve_tie([p for p in eligible if p.stats["might"] == best], revealer)
        if haunt.traitor_rule == "revealer":
            return revealer
        if haunt.traitor_rule == "highest_might":
            best = max(player.stats["might"] for player in players)
            candidates = [player for player in players if player.stats["might"] == best]
            return self._resolve_tie(candidates, revealer)
        if haunt.traitor_rule == "lowest_sanity":
            best = min(player.stats["sanity"] for player in players)
            candidates = [player for player in players if player.stats["sanity"] == best]
            return self._resolve_tie(candidates, revealer, reverse=False)
        if haunt.traitor_rule == "specific_character":
            return revealer
        return revealer

    def _resolve_tie(self, candidates: list[Player], revealer: Player, reverse: bool = False) -> Player:
        if revealer in candidates:
            return revealer
        order = self.state.turn_order[:]
        if reverse:
            order = list(reversed(order))
        start = order.index(revealer.id)
        for offset in range(1, len(order) + 1):
            idx = order[(start + offset) % len(order)]
            candidate = self.state.players[idx]
            if candidate in candidates:
                return candidate
        return candidates[0]

    def _apply_roles(self, revealer: Player, traitor: Player, haunt: Haunt) -> None:
        for player in self.state.players:
            player.role = "hero"
        traitor.role = "traitor"
        if revealer.id != traitor.id:
            revealer.role = "hero"

    def _prepare_haunt_turn_order(self, traitor_id: int) -> None:
        ids = [player.id for player in self.state.players]
        idx = ids.index(traitor_id)
        self.state.turn_order = ids[idx + 1 :] + ids[: idx + 1]
        self.state.turn_index = 0

    def _show_private_haunt_briefings(self) -> None:
        if not self.state.haunt:
            return
        self.state.meta["haunt_briefings_ready"] = True
        self._log("作祟手册已准备好。请各玩家使用“剧本”按钮查看自己可见的内容。")

    def _initialize_haunt_rules(self, haunt: Haunt, room_key: str) -> None:
        rule = haunt.rule_data
        if not rule:
            self.state.meta.pop("haunt_rule", None)
            return
        setup = rule.get("setup", {})
        tracks = {}
        for track_id, spec in dict(setup.get("tracks", {})).items():
            target = self._resolve_haunt_target(spec.get("target", 0))
            tracks[track_id] = {
                "label": spec.get("label", track_id),
                "target": target,
                "value": int(spec.get("value", 0)),
                "side": spec.get("side", ""),
            }
        self.state.meta["haunt_rule"] = {
            "id": haunt.id,
            "name": haunt.name,
            "mode": haunt.mode,
            "status": rule.get("status", "playable_draft"),
            "haunt_room": room_key,
            "tracks": tracks,
            "flags": deepcopy(setup.get("flags", {})),
            "tokens": list(rule.get("tokens", [])),
            "key_rooms": list(rule.get("key_rooms", [])),
            "source_pages": list(rule.get("source_pages", [])),
            # 怪物规格存一份，供无敌判定（invulnerable / invulnerable_until）
            # 与 mode handler 的延迟生成使用。过去这两个字段只写在数据里，
            # 引擎从不读取——女巫/女妖的"不可攻击"从未生效过。
            "monster_specs": {
                str(spec.get("template_id")): dict(spec)
                for spec in rule.get("monsters", [])
                if isinstance(spec, dict) and spec.get("template_id")
            },
        }
        self._log("已初始化该剧本的专属规则状态。")

    def _monster_invulnerable(self, monster: Monster) -> bool:
        """按剧本规则判断怪物当前是否不可被攻击。

        invulnerable: True                      —— 始终无敌（如 8 号女妖）
        invulnerable_until: "<flag>"            —— 该 flag 为真后才可攻击
                                                   （如 3 号女巫需先被施放凡人形态）
        """
        specs = self._haunt_rule_state().get("monster_specs", {})
        spec = specs.get(monster.template_id)
        if not spec:
            return False
        if spec.get("invulnerable"):
            return True
        until = spec.get("invulnerable_until")
        if until:
            return not bool(self._haunt_flags().get(str(until)))
        return False

    def _resolve_haunt_target(self, value: object) -> int:
        players = len(self.state.players)
        heroes = len([player for player in self.state.players if player.role == "hero" and not player.dead])
        if isinstance(value, int):
            return value
        if value == "player_count":
            return players
        if value == "player_count_plus_one":
            return players + 1
        if value == "player_count_minus_one":
            return max(1, players - 1)
        if value == "hero_count":
            return heroes
        if value == "half_players_floor":
            return max(1, players // 2)
        if value == "half_players_ceil":
            return max(1, (players + 1) // 2)
        return 0

    def _spawn_haunt_monsters(self, haunt: Haunt, room_key: str) -> None:
        rule_monsters = list(haunt.rule_data.get("monsters", [])) if haunt.rule_data else []
        if rule_monsters:
            for spec in rule_monsters:
                if spec.get("spawn") == "deferred":
                    continue
                count = self._haunt_monster_count(spec)
                for target_room_key in self._haunt_monster_locations(spec, room_key, count):
                    self._spawn_single_haunt_monster(spec, target_room_key)
            return

        for monster_id in haunt.suggested_monsters:
            if monster_id not in self.catalog.monsters:
                continue
            template = self.catalog.monsters[monster_id]
            self._spawn_single_haunt_monster({"template_id": template.id}, room_key)

    def _haunt_monster_count(self, spec: dict) -> int:
        count = spec.get("count", 1)
        players = len(self.state.players)
        heroes = len([player for player in self.state.players if player.role == "hero" and not player.dead])
        if isinstance(count, int):
            return max(0, count)
        if isinstance(count, str):
            if count == "player_count":
                return players
            if count == "hero_count":
                return heroes
            return 1
        if isinstance(count, dict):
            if "lte4" in count and players <= 4:
                return max(0, int(count["lte4"]))
            if "per_player" in count:
                result = players * int(count["per_player"])
                if "max" in count:
                    result = min(result, int(count["max"]))
                if "min" in count:
                    result = max(result, int(count["min"]))
                return max(0, result)
            if "default" in count:
                return max(0, int(count["default"]))
        return 1

    def _haunt_monster_locations(self, spec: dict, haunt_room_key: str, count: int) -> list[str]:
        if count <= 0:
            return []
        spawn = spec.get("spawn", "haunt_room")
        if spawn == "haunt_room":
            return [haunt_room_key] * count
        if spawn == "room_id":
            target = self._link_target_key(spec.get("room_id", "")) or haunt_room_key
            return [target] * count
        if spawn == "room_ids":
            keys = [
                key
                for room_id in spec.get("room_ids", [])
                for key in [self._link_target_key(room_id)]
                if key
            ]
            if not keys:
                keys = [haunt_room_key]
            return keys[:count]
        if spawn == "omen_rooms":
            keys = [room.key for room in self.state.board.values() if room.symbol == "omen"]
            if len(keys) < count:
                keys.extend(
                    room.key
                    for room in self.state.board.values()
                    if room.key not in keys and room.symbol != "event"
                )
            while len(keys) < count:
                keys.append(haunt_room_key)
            return keys[:count]
        return [haunt_room_key] * count

    COLLAPSE_KEY = "abyss_collapsed"

    NON_TRANSIT_TEMPLATES = ("mystic_elevator", "coal_chute")

    START_ROOM_IDS = (
        "basement_landing",
        "entrance_hall",
        "foyer",
        "grand_staircase",
        "upper_landing",
    )

    def _set_winner(self, winner: str, reason: str) -> None:
        if self.state.winner:
            return
        self.state.winner = winner
        self.state.winner_reason = reason
        self.state.phase = "GAME_OVER"
        self._log("英雄获胜。" if winner == "heroes" else "叛徒获胜。")

    def _check_haunt_specific_victory(self) -> bool:
        """按剧本 mode 分派胜负判定。

        过去这里硬编码 `haunt.id == 1`，其余剧本只能靠 rule_data 里的
        win_conditions。现在改由 haunt_modes 按 mode 查表：注册了定制
        handler 的 mode 走定制逻辑，其余落到 _check_generic_haunt_victory。
        """
        if not self.state.haunt:
            return False
        return self._mode_handler().check_victory(self)

    def _check_generic_haunt_victory(self) -> bool:
        """执行 rule_data.win_conditions 里声明的胜负条件。"""
        rule = self._generic_haunt_rule()
        for condition in rule.get("win_conditions", []):
            if not isinstance(condition, dict):
                continue
            if self._generic_haunt_condition_met(condition):
                winner = str(condition.get("winner", ""))
                if winner in {"heroes", "traitor"}:
                    self._set_winner(winner, str(condition.get("reason", "完成了剧本胜利条件。")))
                    return True
        return False

    def _mode_handler(self):
        """取当前剧本的 mode handler；没有定制实现时回落到通用规则。"""
        mode = None
        if self.state.haunt:
            mode = (self.state.haunt.rule_data or {}).get("mode") or self.state.haunt.mode
        return get_mode_handler(mode)

    def _generic_haunt_condition_met(self, condition: dict) -> bool:
        condition_type = condition.get("type")
        if condition_type == "track":
            track_id = str(condition.get("track", ""))
            current = self._haunt_track_value(track_id)
            target_value = condition.get("target", 0)
            target = self._resolve_haunt_target(target_value)
            operator = condition.get("operator", ">=")
            if operator == "==":
                return current == target
            if operator == ">":
                return current > target
            return current >= target
        if condition_type == "turn_count":
            target = self._resolve_haunt_target(condition.get("target", 0))
            return self.state.turn_count >= target
        if condition_type == "flag":
            flag_id = str(condition.get("flag", ""))
            expected = condition.get("value", True)
            return self._haunt_flags().get(flag_id) == expected
        if condition_type in {"all_heroes_dead", "heroes_dead"}:
            return not any(player.role == "hero" and not player.dead for player in self.state.players)
        if condition_type == "traitor_dead":
            return self.state.traitor_id is not None and self.state.players[self.state.traitor_id].dead
        if condition_type == "heroes_alive_at_least":
            target = self._resolve_haunt_target(condition.get("target", 0))
            return sum(1 for player in self.state.players if player.role == "hero" and not player.dead) >= target
        if condition_type == "heroes_escaped_at_least":
            target = self._resolve_haunt_target(condition.get("target", 0))
            return int(self._haunt_flags().get("escaped_heroes", 0)) >= target
        if condition_type == "monster_count_at_most":
            target = self._resolve_haunt_target(condition.get("target", 0))
            template_ids = set(condition.get("template_ids", []))
            remaining = sum(
                1
                for monster in self.state.monsters
                if not template_ids or monster.template_id in template_ids
            )
            return remaining <= target
        return False

    def check_victory(self) -> None:
        if self.state.phase != "HAUNT_PHASE" or self.state.winner:
            return
        if self._check_haunt_specific_victory():
            return
        heroes = [player for player in self.state.players if player.role == "hero" and not player.dead]
        traitor = next((player for player in self.state.players if player.role == "traitor" and not player.dead), None)
        if not heroes and traitor is not None:
            self._set_winner("traitor", "所有英雄都倒下了。")
        elif traitor is None and heroes:
            self._set_winner("heroes", "叛徒已经倒下。")

    def room_occupants(self, room_key: str) -> list[dict]:
        occupants: list[dict] = []
        for player in self.state.players:
            if not player.dead and player.room_key == room_key:
                occupants.append({"kind": "player", "player": player})
        for monster in self.state.monsters:
            if monster.room_key == room_key:
                occupants.append({"kind": "monster", "monster": monster})
        return occupants

    def room_items(self, room_key: str) -> list[str]:
        return list(self.state.room_items.get(room_key, []))

    def _player_label(self, player: Player) -> str:
        return f"{player.name}（{player.character_name}）"

    def _direction_cn(self, direction: str) -> str:
        return {"north": "北", "east": "东", "south": "南", "west": "西"}.get(direction, direction)

    def _special_link_cn(self, label: str) -> str:
        return {
            "up": "楼梯",
            "down": "楼梯",
            "secret": "密道",
        }.get(label, label)

    def _log(self, message: str, category: str = "") -> None:
        self.state.log.append(message)
        if len(self.state.log) > 400:
            self.state.log = self.state.log[-400:]

    def log_message(self, message: str, category: str = "") -> None:
        self._log(message, category)

    @property
    def active_player_id(self) -> int | None:
        """当前正被引擎请求决策的玩家 id（None=无）。"""
        return self._active_player_id

    def smoke_turn(self) -> None:
        player = self.current_player
        if self.state.phase == "EXPLORE":
            options = self.available_move_options(player)
            if options:
                self.move_player(player, options[0])
        if self.state.phase == "HAUNT_PHASE":
            targets = self.available_attack_targets(player)
            if targets:
                self.attack(player, targets[0], None, False)
        self.end_turn()
