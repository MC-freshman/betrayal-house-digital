from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

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
except ImportError:  # pragma: no cover - direct script execution
    from content import build_catalog  # type: ignore
    from haunt_modes import get_mode_handler  # type: ignore
    from models import (  # type: ignore
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


@dataclass
class ExitOption:
    label: str
    direction: str
    target_key: str
    target_room_name: str | None
    is_new_room: bool = False
    is_special: bool = False
    cost: int = 1


@dataclass
class ActionCommand:
    """一个玩家对引擎发出的操作命令（本地 / 网络 / AI 的统一入口）。

    action 取值：move / use_item / pickup / drop / trade / attack / end_turn
    data 为动作参数（本地对象或 dict，见 execute_command）。
    """

    action: str
    player_id: int
    data: dict = field(default_factory=dict)


@dataclass
class HauntAction:
    id: str
    label: str
    detail: str = ""
    data: dict = field(default_factory=dict)


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


def _room_key(floor: int, x: int, y: int) -> str:
    return f"{floor}:{x}:{y}"


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


def _rotate_direction(direction: str, rotation: int) -> str:
    order = ["north", "east", "south", "west"]
    idx = order.index(direction)
    return order[(idx + rotation) % 4]


def _rotate_doors(doors: tuple[str, ...], rotation: int) -> tuple[str, ...]:
    return tuple(_rotate_direction(direction, rotation) for direction in doors)


def _rotate_links(links: dict[str, str], rotation: int) -> dict[str, str]:
    rotated: dict[str, str] = {}
    for key, value in links.items():
        if key in DIRECTIONS:
            rotated[_rotate_direction(key, rotation)] = value
        else:
            rotated[key] = value
    return rotated


def _distance_hint(floor: int) -> str:
    return { -1: "地下室", 0: "一层", 1: "二层" }.get(floor, "未知楼层")


class GameEngine:
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

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------
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
        self.state = state_from_dict(data.get("state") or {})
        rng_state = data.get("rng_state")
        if rng_state is not None:
            self.rng.setstate(self._tupleize_random_state(rng_state))
        else:
            self.rng.seed(self.state.seed)
        self._next_monster_id = int(data.get("next_monster_id") or self._infer_next_monster_id())
        self._active_player_id = None

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

    # ------------------------------------------------------------------
    # Public setup
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def current_player(self) -> Player:
        if not self.state.turn_order:
            raise RuntimeError("游戏尚未开始")
        idx = self.state.turn_order[self.state.turn_index % len(self.state.turn_order)]
        return self.state.players[idx]

    def current_room(self, player: Player | None = None) -> PlacedRoom:
        player = player or self.current_player
        return self.state.board[player.room_key]

    # ------------------------------------------------------------------
    # Deck helpers
    # ------------------------------------------------------------------
    def _build_deck(self, kind: str) -> list[str]:
        deck = [card_id for card_id, card in self.catalog.cards.items() if card.kind == kind]
        self.rng.shuffle(deck)
        return deck

    def _draw_card_id(self, kind: str) -> str:
        deck = self.state.card_decks.setdefault(kind, [])
        discards = self.state.card_discards.setdefault(kind, [])
        if not deck:
            if discards:
                deck.extend(discards)
                discards.clear()
                self.rng.shuffle(deck)
            else:
                deck.extend(self._build_deck(kind))
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
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                if (floor, room.x + dx, room.y + dy) not in self.state.pos_index:
                    frontier.append(room.key)
                    break
        return frontier

    # ------------------------------------------------------------------
    # Board setup
    # ------------------------------------------------------------------
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
        haunt_rule = self.state.meta.get("haunt_rule")
        if haunt_rule:
            used = haunt_rule.setdefault("actions_used", {})
            used.pop(str(player.id), None)

    # ------------------------------------------------------------------
    # Turn flow
    # ------------------------------------------------------------------
    def start_turn(self) -> None:
        for _ in range(len(self.state.turn_order) or 1):
            player = self.current_player
            if not player.dead:
                break
            self._advance_turn()
        else:
            return
        self._reset_player_turn_state(player)
        self.state.turn_count += 1
        self._log(f"轮到 {self._player_label(player)}")
        if self.state.phase == "HAUNT_PHASE":
            self._apply_start_of_turn_haunt_effects(player)
            self.check_victory()

    def end_turn(self) -> None:
        if self.state.winner:
            return
        player = self.current_player
        haunt_triggered = False
        if self.state.phase == "EXPLORE" and self.state.haunt_pending:
            haunt_triggered = self._resolve_haunt_check(player)
            self.state.haunt_pending = False

        if haunt_triggered:
            self.start_turn()
            return

        if self.state.phase == "HAUNT_PHASE":
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

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def available_move_options(self, player: Player | None = None) -> list[ExitOption]:
        player = player or self.current_player
        if player.dead or player.movement_stopped:
            return []
        room = self.current_room(player)
        options: list[ExitOption] = []

        for direction in room.doors:
            if direction not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[direction]
            target_pos = (room.floor, room.x + dx, room.y + dy)
            target_key = self.state.pos_index.get(target_pos)
            if target_key:
                target_room = self.state.board[target_key]
                if OPPOSITE[direction] in target_room.doors:
                    cost = self._movement_cost(player, room)
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

            if self._floor_has_room_capacity(room.floor):
                options.append(
                    ExitOption(
                        label=f"向{self._direction_cn(direction)}探索新房间",
                        direction=direction,
                        target_key=target_key or "",
                        target_room_name=None,
                        is_new_room=True,
                        cost=self._movement_cost(player, room),
                    )
                )

        # 已能通过门到达的目标（避免楼梯链接与门重复出现）
        door_reached = {option.target_key for option in options if not option.is_new_room}

        for label, target in room.links.items():
            if label in DIRECTIONS:  # 方位型链接已被门覆盖，忽略，避免"使用west"这类无意义选项
                continue
            target_key = self._link_target_key(target)
            if target_key is None or target_key in door_reached:
                continue
            cost = self._movement_cost(player, room)
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
        if player.steps_remaining <= 0 and player.moved_this_turn:
            self._log(f"{player.name} 已没有剩余移动力。")
            return False

        current_room = self.current_room(player)
        cost = self._movement_cost(player, current_room)
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
            dx, dy = DIRECTION_DELTAS[option.direction]
            target_pos = (current_room.floor, current_room.x + dx, current_room.y + dy)
            new_room = None
            while True:
                template = self._draw_room_template(current_room.floor)
                if template is None:
                    self._log("这一层已经没有可用的新房间了。")
                    return False
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
            if target_key not in self.state.board:
                self._log("目标房间不存在。")
                return False

        player.room_key = target_key
        player.steps_remaining = max(0, player.steps_remaining - cost)
        player.moved_this_turn = True
        self._log(f"{player.name} 移动到 {self.state.board[target_key].name}。")
        self._resolve_room_entry_if_needed(player)
        if option.is_new_room:
            # 探索新房间会结束本回合移动（无论房间是否有特效）
            player.movement_stopped = True
            player.steps_remaining = 0
        self.check_victory()
        return True

    def _movement_cost(self, player: Player, room: PlacedRoom) -> int:
        if self.state.phase != "HAUNT_PHASE":
            return 1
        hostile_count = 0
        for occupant in self.room_occupants(room.key):
            if occupant["kind"] == "player" and occupant["player"].role != player.role and not occupant["player"].dead:
                hostile_count += 1
            elif occupant["kind"] == "monster" and occupant["monster"].stunned_turns <= 0:
                hostile_count += 1
        return 1 + hostile_count

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

    def _ensure_room_in_play(self, template_id: str, origin_room_key: str | None = None) -> str | None:
        """确保指定模板的房间在场上；不在就从房间牌堆取出并放下。

        有些剧本依赖特定房间：剧本 3 的温室/储藏室/厨房长着曼德拉草，剧本 2
        的五芒星室是降灵会唯一场所。但探索阶段未必翻得到它们，而作祟之后
        探险者不再为探索而探索，这些房间可能整局都不出现，剧本会直接卡死
        （seed=109 实测：三间房一间都没出现，曼德拉草一株都没生成）。
        原版对此有先例（p84："If the Pentagram Chamber isn't in the house,
        search the room stack for it and put it ..."），这里做成通用能力。

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

        # 只在该模板所属楼层找空位，避免把地面层房间塞进地下室
        origin_keys: list[str] = []
        if origin_room_key and origin_room_key in self.state.board:
            origin_keys.append(origin_room_key)
        origin_keys.extend(
            key
            for key in sorted(self.state.board)
            if key != origin_room_key and self.state.board[key].floor == template.floor
        )
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
                placement = placements[0]
                rotated = self._build_rotated_template(template, placement["rotation"])
                room = self._place_room(rotated, pos[1], pos[2], placement["rotation"])
                self._log(f"「{room.name}」被强行拉进了这栋房子。")
                return room.key

        self.state.room_deck.insert(0, template_id)
        return None

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

    # ------------------------------------------------------------------
    # Room entry and symbol draws
    # ------------------------------------------------------------------
    def _resolve_room_entry_if_needed(self, player: Player) -> None:
        room = self.current_room(player)
        room.visit_count += 1
        first_entry = not room.revealed
        if first_entry:
            room.revealed = True
            # 先弹进入房间的详细说明（符号/效果/描述），再抽卡
            self._notify_room_entry(player, room)
            self._mode_handler().on_room_discovered(self, player, room)
            if room.symbol:
                if room.symbol == "event" and self.state.phase == "HAUNT_PHASE" and player.role == "traitor":
                    if self.prompter.confirm("事件卡", f"{player.name} 进入了带事件符号的房间。要触发事件吗？"):
                        self._draw_symbol_card(player, room.symbol)
                    else:
                        self._log(f"{player.name} 选择不触发这张事件卡。")
                else:
                    self._draw_symbol_card(player, room.symbol)
        self._collect_room_companions(player, room)
        # 令牌拾取之类要在房间效果之后，避免顺序上出现歧义
        self._mode_handler().on_enter_room(self, player, room)
        self._apply_room_effect(player, room, first_entry=first_entry)
        self.check_victory()

    def _room_effect_desc(self, effect: str) -> str:
        """返回房间特殊效果的一句话说明，供进房提示/悬停使用。"""
        return {
            "room_chapel": "每次进入：恢复 1 点理智。",
            "room_graveyard": "（无特殊效果）",
            "room_gymnasium": "每次进入：速度步数 +1。",
            "room_library": "每次进入：下一次检定重掷机会 +1。",
            "room_larder": "每次进入：恢复 1 点力量。",
            "room_research_laboratory": "进入时：知识检定（目标 4）通过则抽 1 张物品卡。",
            "room_bloody_room": "每次进入：受到 1 点物理伤害。",
            "room_bedroom": "每次进入：恢复 1 点理智。",
            "room_master_bedroom": "每次进入：恢复 1 点理智。",
            "room_charred_room": "每次进入：受到 1 点精神伤害。",
            "room_furnace_room": "每次进入：受到 1 点物理伤害。",
            "room_coal_chute": "进入时：被送到地下室大厅并结束移动。",
            "room_mystic_elevator": "进入时：掷骰前往随机楼层（叛徒可自选）。",
            "room_vault": "首次进入：知识检定（目标 4）通过抽 2 张物品卡，失败受 1 点物理伤害。",
            "room_chasm": "进入时：速度检定（目标 4）失败受 1 点物理伤害并停下。",
            "room_collapsed_room": "首次进入：受 1 点物理伤害并掉到地下室。",
            "room_tower": "进入时：速度检定（目标 4）失败受 1 点物理伤害。",
            "room_pentagram_chamber": "（无特殊效果）",
            "room_attic": "特殊房间：部分剧本中的失败检定可留在这里下回合重试。",
            "room_bathroom": "无基础常规特效；首次发现时照房间符号抽事件牌。",
            "room_game_room": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_inner_hall": "无基础常规特效。",
            "room_creaky_hallway": "无基础常规特效；部分剧本会把它作为关键房间。",
            "room_dusty_hallway": "无基础常规特效。",
            "room_statuary_corridor": "无基础常规特效；部分剧本会把它作为关键房间。",
            "room_crawlspace": "无基础常规特效。",
            "room_storeroom": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_underground_lake": "若在上层发现，房间塌落到地下室并结束移动。",
            "room_wine_cellar": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_balcony": "无基础常规特效；首次发现时照房间符号抽事件牌。",
            "room_kitchen": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_organ_room": "无基础常规特效；首次发现时照房间符号抽预兆牌。",
            "room_crypt": "无基础常规特效；首次发现时照房间符号抽预兆牌。怪物无视本房间特殊规则。",
            "room_catacombs": "障碍房间：进入时速度检定（目标 4）失败受 1 点物理伤害并停下；怪物无视障碍。",
        }.get(effect, "")

    def _notify_room_entry(self, player: Player, room: PlacedRoom) -> None:
        """首次进入新房间时弹出详细说明。"""
        parts = []
        if room.symbol:
            sym = {"omen": "预兆", "item": "物品", "event": "事件"}.get(room.symbol, room.symbol)
            parts.append(f"房间符号：进入触发{sym}卡")
        desc = self._room_effect_desc(room.effect_id)
        if desc:
            parts.append(f"效果：{desc}")
        if room.text:
            parts.append(f"描述：{room.text}")
        if parts:
            self.prompter.notify(f"进入房间：{room.name}", "\n".join(parts))

    def _draw_symbol_card(self, player: Player, symbol: str) -> None:
        kind_map = {"omen": "omen", "item": "item", "event": "event"}
        kind = kind_map.get(symbol)
        if kind is None:
            return
        if player.frog:
            self._log("青蛙不能抽牌。")
            return
        if kind == "omen":
            self._draw_omen(player)
        elif kind == "item":
            self._draw_item(player)
        elif kind == "event":
            self._draw_event(player)
        player.movement_stopped = True
        player.steps_remaining = 0

    def _draw_omen(self, player: Player) -> None:
        card_id = self._draw_card_id("omen")
        card = self.catalog.cards[card_id]
        player.items.append(card_id)
        if card_id not in player.companions and "companion" in card.tags:
            player.companions.append(card_id)
        self.state.omens_drawn += 1
        self.state.last_omen_id = card_id
        self.state.haunt_pending = True
        self._log(f"{player.name} 抽到预兆：{card.name}。")
        self.prompter.notify(f"抽到预兆：{card.name}", card.text or "（无说明）")

    def _draw_item(self, player: Player) -> None:
        card_id = self._draw_card_id("item")
        card = self.catalog.cards[card_id]
        player.items.append(card_id)
        self._log(f"{player.name} 抽到物品：{card.name}。")
        self.prompter.notify(f"获得物品：{card.name}", card.text or "（无说明）")

    def _draw_event(self, player: Player) -> None:
        card_id = self._draw_card_id("event")
        card = self.catalog.cards[card_id]
        self._log(f"{player.name} 抽到事件：{card.name}。")
        self.prompter.notify(f"触发事件：{card.name}", card.text or "（无说明）")
        self._resolve_event(player, card)
        self.state.card_discards["event"].append(card_id)

    def _collect_room_companions(self, player: Player, room: PlacedRoom) -> None:
        room_cards = self.state.room_items.get(room.key)
        if not room_cards:
            return
        for card_id in list(room_cards):
            card = self.catalog.cards.get(card_id)
            if not card or "companion" not in card.tags:
                continue
            room_cards.remove(card_id)
            player.items.append(card_id)
            if card_id not in player.companions:
                player.companions.append(card_id)
            self._log(f"{player.name} 接手了 {card.name}。")
        if not room_cards:
            self.state.room_items.pop(room.key, None)

    # ------------------------------------------------------------------
    # Room effects
    # ------------------------------------------------------------------
    def _apply_room_effect(self, player: Player, room: PlacedRoom, first_entry: bool) -> None:
        effect = room.effect_id
        if effect == "none":
            return
        if effect == "room_start_hall" or effect == "room_start_foyer" or effect == "room_start_stairs":
            return
        if self.state.phase == "HAUNT_PHASE" and player.role == "traitor" and effect in {"room_bloody_room", "room_charred_room", "room_furnace_room"}:
            self._log("叛徒无视了这个房间的负面效果。")
            return
        if effect == "room_chapel":
            self._log("小教堂让人稍微平静下来。")
            self._heal_stat(player, "sanity", 1)
            return
        if effect == "room_graveyard":
            self._log("墓地的气氛让人不安。")
            return
        if effect == "room_gymnasium":
            self._log("健身房的空间让你更容易活动。")
            player.steps_remaining += 1
            return
        if effect == "room_library":
            self._log("图书馆里也许能找到灵感。")
            player.extra_check_rerolls += 1
            return
        if effect == "room_larder":
            self._log("储藏室里有一点补给。")
            self._heal_stat(player, "might", 1)
            return
        if effect == "room_research_laboratory":
            self._log("研究实验室的器材看上去还能用。")
            if self._resolve_check(player, "knowledge", 4, "研究实验室检定"):
                self._draw_item(player)
            return
        if effect == "room_bloody_room":
            self._log("血房间里的痕迹让人心里发紧。")
            self._deal_damage(player, "physical", 1, source="血房间")
            return
        if effect == "room_bedroom":
            self._log("卧室让人稍微放松了一点。")
            self._heal_stat(player, "sanity", 1)
            return
        if effect == "room_master_bedroom":
            self._log("主卧的安静有一点诡异。")
            self._heal_stat(player, "sanity", 1)
            return
        if effect == "room_charred_room":
            self._log("烧焦的房间残留着热与灰。")
            self._deal_damage(player, "mental", 1, source="烧焦的房间")
            return
        if effect == "room_furnace_room":
            self._log("熔炉房的余热让人难受。")
            self._deal_damage(player, "physical", 1, source="熔炉房")
            return
        if effect == "room_coal_chute":
            self._log("煤导槽把你往地下室入口送。")
            self._move_to_room(player, "basement_landing", via_effect=True)
            player.movement_stopped = True
            player.steps_remaining = 0
            return
        if effect == "room_mystic_elevator":
            self._apply_mystic_elevator(player, room)
            return
        if effect == "room_vault":
            if not room.data.get("opened"):
                self._apply_vault(player, room)
            return
        if effect == "room_chasm":
            self._apply_chasm(player, room)
            return
        if effect == "room_collapsed_room":
            self._apply_collapsed_room(player, room)
            return
        if effect == "room_tower":
            self._apply_tower(player, room)
            return
        if effect == "room_pentagram_chamber":
            self._log("五芒星室里的符号仍然令人不适。")
            return
        if effect == "room_abandoned_room" or effect == "room_ballroom" or effect == "room_garden" or effect == "room_junk_room" or effect == "room_patio" or effect == "room_conservatory" or effect == "room_dining_room" or effect == "room_gallery" or effect == "room_operating_laboratory" or effect == "room_servants_quarters":
            return
        if effect == "room_underground_lake":
            if room.floor == 1 and not room.data.get("collapsed"):
                room.data["collapsed"] = True
                self._log("地下湖所在的上层地板塌陷，房间落入地下室。")
                room.floor = -1
                player.movement_stopped = True
                player.steps_remaining = 0
            return
        if effect in {
            "room_attic", "room_bathroom", "room_game_room", "room_inner_hall",
            "room_creaky_hallway", "room_dusty_hallway", "room_statuary_corridor",
            "room_crawlspace", "room_storeroom", "room_wine_cellar",
        }:
            self._log(f"{room.name} 没有基础常规特效。")
            return
        # 阳台 / 厨房 / 风琴房：权威规则书（BetrayalHouseHill_v4.2.pdf p2「Special Rooms」）
        # 没有列出这三间，说明它们没有文字效果，只有牌面符号（事件/物品/预兆）。
        # 首次发现的抽牌由上面 _resolve_room_entry_if_needed 的符号分支处理，
        # 这里必须显式 return，避免落到函数末尾变成静默穿透。
        if effect in {"room_balcony", "room_kitchen", "room_organ_room"}:
            return
        # 地窖：与熔炉房同列（p2「Crypt, Furnace Room」）——怪物无视本房间的特殊规则。
        # 本房间本身没有文字效果，只有预兆符号；且怪物不走 _apply_room_effect 通道，
        # 因此"怪物无视"在此自动成立，无需额外处理。
        if effect == "room_crypt":
            return
        # 地下墓穴：障碍房间（p2「Vault, Tower, Chasm, Catacombs」）
        if effect == "room_catacombs":
            self._apply_catacombs(player, room)
            return
        # 兜底：未识别的房间效果不再静默吞掉，记进日志便于排查。
        self._log(f"[规则缺口] {room.name} 的房间效果 {effect} 尚未实现，已跳过。")

    def _apply_mystic_elevator(self, player: Player, room: PlacedRoom) -> None:
        if player.role == "traitor":
            choice = self.prompter.choose_from_list(
                "神秘电梯",
                "叛徒进入神秘电梯时可以直接选择目标楼层。",
                ["地下室", "一层", "二层"],
            )
            if choice is None:
                return
            floor = [-1, 0, 1][choice]
        else:
            roll = self.roll_dice(2, "神秘电梯")
            if roll <= 4:
                floor = -1
            elif roll <= 8:
                floor = 0
            else:
                floor = 1
            self._log(f"神秘电梯骰出 {roll}，目标楼层为 {_distance_hint(floor)}。")

        target_key = self._choose_elevator_target(floor, player.room_key)
        if target_key:
            self._move_to_room(player, target_key, via_effect=True)
        else:
            self._log("神秘电梯没有找到合适的目标。")

    def _choose_elevator_target(self, floor: int, current_key: str) -> str | None:
        candidates = [
            key
            for key, room in self.state.board.items()
            if room.floor == floor and key != current_key
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return self.rng.choice(candidates)

    def _apply_vault(self, player: Player, room: PlacedRoom) -> None:
        self._log("保险库仍然锁着。")
        if self._resolve_check(player, "knowledge", 4, "保险库检定"):
            room.data["opened"] = True
            self._log("保险库打开了。")
            self._draw_item(player)
            self._draw_item(player)
        else:
            self._deal_damage(player, "physical", 1, source="保险库")

    def _apply_chasm(self, player: Player, room: PlacedRoom) -> None:
        self._log("深渊需要小心跨过。")
        if not self._resolve_check(player, "speed", 4, "深渊检定"):
            self._deal_damage(player, "physical", 1, source="深渊")
            player.movement_stopped = True
            player.steps_remaining = 0

    def _apply_collapsed_room(self, player: Player, room: PlacedRoom) -> None:
        if room.data.get("collapsed_resolved"):
            return
        room.data["collapsed_resolved"] = True
        self._log("坍塌的地板把你往地下室带。")
        self._deal_damage(player, "physical", 1, source="坍塌的房间")
        self._move_to_room(player, "basement_landing", via_effect=True)
        player.movement_stopped = True
        player.steps_remaining = 0

    def _apply_tower(self, player: Player, room: PlacedRoom) -> None:
        self._log("塔楼风很大，需要稳住脚步。")
        if not self._resolve_check(player, "speed", 4, "塔楼检定"):
            self._deal_damage(player, "physical", 1, source="塔楼")

    def _apply_catacombs(self, player: Player, room: PlacedRoom) -> None:
        """地下墓穴：障碍房间。

        权威原文（BetrayalHouseHill_v4.2.pdf p2）：
            "Vault, Tower, Chasm, Catacombs — These are all barrier rooms.
             You may attempt once per turn to make the trait roll to be able
             to cross the room. ... Crossing the barrier doesn't count as
             moving a space. Monsters ignore barriers."

        已满足的部分：
            - "Monsters ignore barriers"：怪物不走 _apply_room_effect 通道，自动成立。
        尚未实现的部分（依赖「房间两侧」概念，需改移动系统，见优化方案第 2 步）：
            - 跨越障碍不消耗移动格
            - 未跨越时不能与房间另一侧的玩家交互
            - 每回合只能尝试一次

        待确认：规则书只写 "the trait roll"，未指定属性与目标值（印在实体房间牌上）。
        此处沿用同类跨越型障碍（深渊 / 塔楼）的 speed 4，确认实体牌后需校正。
        """
        self._log("地下墓穴的通道很窄，需要侧身挤过去。")
        if not self._resolve_check(player, "speed", 4, "地下墓穴检定"):
            self._deal_damage(player, "physical", 1, source="地下墓穴")
            player.movement_stopped = True
            player.steps_remaining = 0

    def _move_to_room(self, player: Player, target_key: str, via_effect: bool = False) -> None:
        # 允许传模板 id（如 "basement_landing"），统一解析为板块 key
        target_key = self._link_target_key(target_key) or target_key
        if target_key not in self.state.board:
            return
        player.room_key = target_key
        if via_effect:
            self._log(f"{player.name} 被移动到 {self.state.board[target_key].name}。")
        else:
            self._log(f"{player.name} 移动到 {self.state.board[target_key].name}。")
        self._resolve_room_entry_if_needed(player)

    # ------------------------------------------------------------------
    # Cards and events
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Checks and damage
    # ------------------------------------------------------------------
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

    def _apply_damage_amounts(self, player: Player, physical: int = 0, mental: int = 0) -> None:
        if physical:
            self._split_and_apply(player, "physical", physical)
        if mental:
            self._split_and_apply(player, "mental", mental)
        self._check_player_death(player)

    def _split_and_apply(self, player: Player, damage_type: str, amount: int) -> None:
        if amount <= 0 or player.dead:
            return
        if damage_type == "physical" and player.ignore_first_physical_damage:
            player.ignore_first_physical_damage = False
            self._log(f"{player.name} 用护甲挡下了这次物理伤害。")
            return
        if damage_type == "physical" and self._has_card(player, "item_armor"):
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
                # 跌出轨道最左格（到达骷髅）→ 该属性归零（任何阶段都判定濒死/死亡）
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

    def _check_player_death(self, player: Player) -> None:
        if player.dead:
            return
        if any(player.stats[stat] <= 0 for stat in STAT_NAMES):
            player.dead = True
            self._log(f"{player.name} 倒下了。")
            self._drop_inventory_on_death(player)

    def _deal_damage(self, player: Player, damage_type: str, amount: int, source: str = "") -> None:
        if amount <= 0 or player.dead:
            return
        amount = self._adjust_damage_for_haunt(player, amount, source)
        if amount <= 0:
            return
        if source:
            self._log(f"{source} 让 {player.name} 受到 {amount} 点{ '物理' if damage_type == 'physical' else '精神' }伤害。")
        self._apply_damage_amounts(player, physical=amount if damage_type == "physical" else 0, mental=amount if damage_type == "mental" else 0)

    # ------------------------------------------------------------------
    # Inventory management
    # ------------------------------------------------------------------
    def _has_card(self, player: Player, card_id: str) -> bool:
        return card_id in player.items

    def _discard_card_from_player(self, player: Player, card_id: str, return_to_room: bool = True) -> bool:
        if card_id not in player.items:
            return False
        player.items.remove(card_id)
        if card_id in player.companions:
            player.companions.remove(card_id)
        if return_to_room:
            self.state.room_items.setdefault(player.room_key, []).append(card_id)
        return True

    def drop_item(self, player: Player, card_id: str) -> bool:
        card = self.catalog.cards.get(card_id)
        if not card or card_id not in player.items:
            return False
        if not card.tradeable and "companion" in card.tags:
            self._log(f"{card.name} 不能被丢弃。")
            return False
        self._discard_card_from_player(player, card_id, return_to_room=True)
        self._log(f"{player.name} 丢弃了 {card.name}。")
        return True

    def pickup_item(self, player: Player, card_id: str) -> bool:
        room_cards = self.state.room_items.get(player.room_key, [])
        if card_id not in room_cards:
            return False
        room_cards.remove(card_id)
        if not room_cards:
            self.state.room_items.pop(player.room_key, None)
        player.items.append(card_id)
        if "companion" in self.catalog.cards[card_id].tags and card_id not in player.companions:
            player.companions.append(card_id)
        self._log(f"{player.name} 捡起了 {self.catalog.cards[card_id].name}。")
        return True

    def trade_item(self, player: Player, target: Player, card_id: str, target_card_id: str | None = None) -> bool:
        if card_id not in player.items:
            return False
        card = self.catalog.cards[card_id]
        if not card.tradeable:
            self._log(f"{card.name} 不能交易。")
            return False
        if player.room_key != target.room_key or player.dead or target.dead:
            return False
        player.items.remove(card_id)
        target.items.append(card_id)
        if "companion" in card.tags:
            if card_id in player.companions:
                player.companions.remove(card_id)
            if card_id not in target.companions:
                target.companions.append(card_id)
        if target_card_id and target_card_id in target.items:
            target_card = self.catalog.cards[target_card_id]
            if target_card.tradeable:
                target.items.remove(target_card_id)
                player.items.append(target_card_id)
                self._log(f"{player.name} 与 {target.name} 交换了 {card.name} 和 {target_card.name}。")
                return True
        self._log(f"{player.name} 把 {card.name} 交给了 {target.name}。")
        return True

    def use_item(self, player: Player, card_id: str) -> bool:
        if card_id not in player.items:
            return False
        card = self.catalog.cards[card_id]
        if player.item_used and card.effect_id not in {"item_angel_feather", "item_bottle", "item_dark_dice"}:
            self._log(f"{player.name} 这一回合已经用过一个物品了。")
            return False
        effect = card.effect_id
        success = False
        if "weapon" in card.tags or effect in {"item_weapon", "item_weapon_blood", "item_dynamite", "item_revolver", "item_weapon_sacrifice"}:
            self._log(f"{card.name} 要在攻击时选择使用。")
            return False
        if effect == "item_heal_small" or effect == "item_heal_large" or effect == "item_heal_sanity":
            success = self._use_heal_item(player, card)
        elif effect == "item_adrenaline":
            player.steps_remaining += int(card.data.get("speed_bonus", 3))
            self._log(f"{player.name} 使用了肾上腺素针。")
            self._discard_card_from_player(player, card_id, return_to_room=False)
            success = True
        elif effect == "item_angel_feather":
            player.next_check_auto_success = True
            self._log(f"{player.name} 使用了天使羽毛。")
            self._discard_card_from_player(player, card_id, return_to_room=False)
            success = True
        elif effect == "item_music_box":
            success = self._use_music_box(player, card)
        elif effect == "item_bottle":
            success = self._use_random_stat_item(player, card, repeatable=False)
        elif effect == "item_dark_dice":
            success = self._use_random_stat_item(player, card, repeatable=True)
        elif effect == "item_amulet":
            success = self._use_amulet(player, card)
        elif effect == "item_pickpocket":
            success = self._use_pickpocket_gloves(player, card)
        elif effect == "item_puzzle_box":
            for _ in range(int(card.data.get("draw_items", 2))):
                self._draw_item(player)
            self._log(f"{player.name} 打开了谜题盒。")
            success = True
        elif effect == "item_reroll":
            player.extra_check_rerolls += 1
            self._log(f"{player.name} 使用了 {card.name}，下一次检定可重掷一次。")
            success = True
        elif effect == "item_bell":
            success = self._use_bell(player, card)
        elif effect == "item_armor":
            # 盔甲是被动减伤：由 _split_and_apply 在结算物理伤害时自动消耗，
            # 刻意不让它占用本回合的物品使用次数。
            self._log("盔甲会在你受到物理伤害时自动生效，不需要主动使用。")
            success = False
        elif card.bonus:
            # 确实只有被动加值的道具（护甲 / 蜡烛等）：加值由 _check_bonus 自动结算。
            self._log(f"{card.name} 是被动效果道具，无需主动使用（不占用本回合物品次数）。")
            success = False
        else:
            # 既没有主动分支、也没有被动加值——这是规则缺口，不能伪装成"被动道具"。
            self._log(f"[规则缺口] {card.name}（{effect}）的主动效果尚未实现。")
            success = False
        if success:
            player.item_used = True
        return success

    def _use_bell(self, player: Player, card: Card) -> bool:
        """铃铛：摇铃，把怪物吸引过来。

        权威依据（BetrayalHouseHill_v4.2.pdf）：
            p74 / p145（剧本 63 扭曲虚空）：
            "If you use an item (such as the Bell or Spirit Board) that would
             normally allow the Traitor to move monsters closer to you ..."
            → 铃铛的用途是让怪物朝使用者靠近，而不是被动加值道具。
              （被动的 +1 神志检定由 _check_bonus 另行结算。）

        各剧本对铃铛规定了免疫对象，精修对应剧本时需一并处理：
            p89（#7 食人常春藤）/ p105（#23 触手恐怖）：对被抓住的英雄无效
            p93（#11 放它们进来）：对背面朝上的幽灵无效
            p109（#27 狂乱血肉）：对 Blob 无效
            p117（#35 小小变化）：对被捕获的英雄无效
            p119（#37 将军）：不能影响与 Death 同房间的英雄

        待确认：规则书未写明每次摇铃怪物移动几格（印在实体卡上）。
        此处按"沿最短路径移动 1 格"实现，确认卡面后需校正。
        """
        if self.state.phase != "HAUNT_PHASE" or not self.state.monsters:
            self._log(f"{player.name} 摇响了铃铛，但此刻没有东西会被声音吸引。")
            return False
        self._log(f"{player.name} 摇响了{card.name}。")
        moved = 0
        for monster in self.state.monsters:
            if monster.stunned_turns > 0:
                self._log(f"{monster.name} 处于昏迷，没有反应。")
                continue
            if monster.room_key == player.room_key:
                continue
            path = self._shortest_path(monster.room_key, player.room_key)
            if len(path) > 1:
                monster.room_key = path[1]
                moved += 1
                self._log(f"{monster.name} 被铃声吸引，移动到 {self.state.board[monster.room_key].name}。")
        if not moved:
            self._log("没有怪物被铃声吸引过来。")
        self.check_victory()
        return True

    def _use_heal_item(self, player: Player, card: Card) -> bool:
        kind = card.data.get("kind", "physical")
        heal = int(card.data.get("heal", 1))
        options = ["速度", "力量"] if kind == "physical" else ["理智", "知识"]
        choice = self.prompter.choose_from_list(
            "恢复属性",
            f"要把 {card.name} 用在什么属性上？",
            options,
        )
        if choice is None:
            return False
        stat = ("speed", "might") if kind == "physical" else ("sanity", "knowledge")
        self._heal_stat(player, stat[choice], heal)
        self._discard_card_from_player(player, card.id, return_to_room=False)
        self._log(f"{player.name} 使用了 {card.name}。")
        return True

    def _use_music_box(self, player: Player, card: Card) -> bool:
        monsters = [m for m in self.state.monsters if m.room_key == player.room_key and m.stunned_turns <= 0]
        if not monsters:
            self._log("房间里没有可迷惑的怪物。")
            return False
        names = [monster.name for monster in monsters]
        idx = self.prompter.choose_from_list("音乐盒", "要让哪只怪物停顿一下？", names)
        if idx is None:
            return False
        monster = monsters[idx]
        monster.stunned_turns = max(monster.stunned_turns, int(card.data.get("stun", 2)))
        self._discard_card_from_player(player, card.id, return_to_room=False)
        self._log(f"{monster.name} 被音乐盒迷住了。")
        return True

    def _use_random_stat_item(self, player: Player, card: Card, repeatable: bool) -> bool:
        stat = self.rng.choice(list(STAT_NAMES))
        delta = self.rng.choice([-1, 1]) * int(card.data.get("random_shift", 1))
        self._log(f"{card.name} 影响了 {player.name} 的 {stat}。")
        if delta > 0:
            self._increase_stat(player, stat, delta)
        else:
            self._apply_stat_loss(player, stat, -delta)
        if not repeatable:
            self._discard_card_from_player(player, card.id, return_to_room=False)
        return True

    def _use_amulet(self, player: Player, card: Card) -> bool:
        idx = self.prompter.choose_from_list("远古护身符", "要提升哪一项属性？", ["速度", "力量", "理智", "知识"])
        if idx is None:
            return False
        stat = STAT_NAMES[idx]
        boost = int(card.data.get("stat_boost", 1))
        player.overflow[stat] = player.overflow.get(stat, 0) + boost
        self._increase_stat(player, stat, boost)
        self._discard_card_from_player(player, card.id, return_to_room=False)
        return True

    def _use_pickpocket_gloves(self, player: Player, card: Card) -> bool:
        targets = [
            other
            for other in self.state.players
            if other.id != player.id and other.room_key == player.room_key and not other.dead and other.items
        ]
        if not targets:
            self._log("同房间没有可以偷取的对象。")
            return False
        idx = self.prompter.choose_from_list("扒手手套", "从谁那里偷一件物品？", [self._player_label(other) for other in targets])
        if idx is None:
            return False
        target = targets[idx]
        candidates = [card_id for card_id in target.items if self.catalog.cards[card_id].tradeable]
        if not candidates:
            self._log("对方没有可偷取的物品。")
            return False
        steal_idx = self.prompter.choose_from_list("偷窃", "要偷哪一件？", [self.catalog.cards[card_id].name for card_id in candidates])
        if steal_idx is None:
            return False
        steal_id = candidates[steal_idx]
        target.items.remove(steal_id)
        player.items.append(steal_id)
        self._log(f"{player.name} 偷走了 {target.name} 的 {self.catalog.cards[steal_id].name}。")
        self._discard_card_from_player(player, card.id, return_to_room=False)
        return True

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------
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

    def attack(self, attacker: Player, target: object, weapon_card_id: str | None = None, ranged: bool = False) -> bool:
        if attacker.dead or attacker.attack_used or self.state.phase != "HAUNT_PHASE":
            return False
        if attacker.frog:
            self._log("青蛙不能攻击。")
            return False
        attacker_room = self.current_room(attacker)
        target_room_key = target.room_key
        if not ranged and attacker_room.key != target_room_key:
            return False
        if ranged and not self._has_line_of_sight(attacker_room.key, target_room_key):
            return False
        if not isinstance(target, Player) and self._monster_invulnerable(target):
            self._log(f"{target.name} 目前无法被攻击。")
            return False

        attack_attr = "might"
        weapon: Card | None = None
        if weapon_card_id:
            weapon = self.catalog.cards.get(weapon_card_id)
            if weapon is None or weapon_card_id not in attacker.items:
                return False
            attack_bonus = self._attack_bonus_from_inventory(attacker, weapon_card_id)
            if "ranged" in weapon.tags:
                ranged = True
            if "knowledge" in weapon.tags:
                attack_attr = "knowledge"
            if "sanity" in weapon.tags:
                attack_attr = "sanity"
            if "speed" in weapon.tags:
                attack_attr = "speed"
        else:
            attack_bonus = self._attack_bonus_from_inventory(attacker, None)
        # 怪物免疫：immune_to 列出的攻击属性对它无效（p17/p88：外星人免疫
        # 速度攻击如左轮；剧本 1 木乃伊同理）。数据早就声明了，引擎此前
        # 从不读取——与剧本 4 的 attack/defense 字段是同一类"假数据"。
        if not isinstance(target, Player):
            specs = self._haunt_rule_state().get("monster_specs", {}).get(
                getattr(target, "template_id", ""), {}
            )
            immune = set(specs.get("immune_to", []) or [])
            if attack_attr == "speed" and ("speed_attack" in immune or "speed" in immune):
                self._log(f"{target.name} 免疫速度攻击。")
                return False
        if isinstance(target, Player):
            # 剧本 6：被控英雄不能被外星人"攻击受伤"之外的手段打死这里不拦；
            # 但被控者可以被打（解救），见 _apply_attack_damage 的半伤解控。
            defense_attr = attack_attr
            target_name = self._player_label(target)
            target_roll = self._roll_attack(target, defense_attr)
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
            if self._haunt5_try_silver_bullet_kill(attacker, target, weapon):
                if weapon is not None:
                    self._resolve_attack_weapon_use(attacker, weapon)
                attacker.attack_used = True
                self.check_victory()
                return True
            if isinstance(target, Player) and not ranged and diff >= 2 and self._can_steal(target):
                if self.prompter.confirm("偷窃", f"造成了 {diff} 点伤害。要改为偷取物品吗？"):
                    self._steal_from_target(attacker, target)
                    if weapon is not None:
                        self._resolve_attack_weapon_use(attacker, weapon)
                    attacker.attack_used = True
                    return True
            self._apply_attack_damage(target, diff, attack_attr)
            if isinstance(target, Player) and attacker.role == "traitor" and target.role == "hero":
                self._haunt5_infect(target)
        else:
            if ranged and isinstance(target, Player):
                self._log(f"{target_name} 反击成功，但远程攻击不会让攻击者受伤。")
            else:
                self._apply_attack_damage(attacker, diff, attack_attr)
                self._log(f"{target_name} 反击成功。")
        if weapon is not None:
            self._resolve_attack_weapon_use(attacker, weapon)
        attacker.attack_used = True
        self.check_victory()
        return True

    def _resolve_attack_weapon_use(self, attacker: Player, weapon: Card) -> None:
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

    def _roll_monster_attack(self, monster: Monster, attr: str) -> int:
        stat = getattr(monster, attr, 0)
        dice = max(1, min(8, stat))
        return self.roll_dice(dice, "怪物攻击")

    def _can_steal(self, target: Player) -> bool:
        for card_id in target.items:
            card = self.catalog.cards[card_id]
            if card.tradeable:
                return True
        return False

    def _steal_from_target(self, attacker: Player, target: Player) -> None:
        candidates = [card_id for card_id in target.items if self.catalog.cards[card_id].tradeable]
        if not candidates:
            return
        idx = self.prompter.choose_from_list("偷窃", "要偷哪一件？", [self.catalog.cards[card_id].name for card_id in candidates])
        if idx is None:
            return
        steal_id = candidates[idx]
        target.items.remove(steal_id)
        attacker.items.append(steal_id)
        if "companion" in self.catalog.cards[steal_id].tags:
            if steal_id not in attacker.companions:
                attacker.companions.append(steal_id)
            if steal_id in target.companions:
                target.companions.remove(steal_id)
        self._log(f"{attacker.name} 偷走了 {target.name} 的 {self.catalog.cards[steal_id].name}。")

    def _apply_attack_damage(self, target: object, amount: int, attack_attr: str) -> None:
        if amount <= 0:
            return
        damage_type = "physical" if attack_attr in PHYSICAL_STATS else "mental"
        if isinstance(target, Monster):
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

    def _stun_monster(self, monster: Monster, turns: int) -> None:
        monster.stunned_turns += max(1, turns)
        self._log(f"{monster.name} 被击晕了。")

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

    # ------------------------------------------------------------------
    # Haunt
    # ------------------------------------------------------------------
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
        return self._mode_handler().available_actions(self, player)

    def perform_haunt_action(self, player: Player, action_id: str, data: dict | None = None) -> bool:
        if player.dead or self.state.phase != "HAUNT_PHASE" or not self.state.haunt:
            return False
        if self._haunt_action_used(player):
            self._log(f"{player.name} 本回合已经执行过剧本行动。")
            return False
        success = self._mode_handler().perform_action(self, player, action_id, data or {})
        if success:
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
            if target in {"player", "hero"}:
                return any(
                    other.id != player.id
                    and not other.dead
                    and other.room_key == player.room_key
                    and (target == "player" or other.role == "hero")
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
        if success:
            self._apply_generic_haunt_success(player, action)
            self._log(f"{player.name} 完成了剧本行动：{action.get('label', action_id)}。")
        else:
            self._log(f"{player.name} 未完成剧本行动：{action.get('label', action_id)}。")
        return True

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

    def _has_item(self, player: Player, card_id: str) -> bool:
        return card_id in player.items

    def _card_is_controlled(self, card_id: str) -> bool:
        if any(card_id in player.items for player in self.state.players):
            return True
        return any(card_id in room_cards for room_cards in self.state.room_items.values())

    def _grant_card_to_player(self, player: Player, card_id: str) -> bool:
        card = self.catalog.cards.get(card_id)
        if not card:
            return False
        if card_id in player.items:
            return True
        for deck in self.state.card_decks.values():
            if card_id in deck:
                deck.remove(card_id)
        for discards in self.state.card_discards.values():
            if card_id in discards:
                discards.remove(card_id)
        for room_cards in self.state.room_items.values():
            if card_id in room_cards:
                room_cards.remove(card_id)
        for other in self.state.players:
            if card_id in other.items:
                other.items.remove(card_id)
            if card_id in other.companions:
                other.companions.remove(card_id)
        player.items.append(card_id)
        if "companion" in card.tags and card_id not in player.companions:
            player.companions.append(card_id)
        self._log(f"{player.name} 获得了 {card.name}。")
        return True

    def _monster_by_template(self, template_id: str) -> Monster | None:
        return next((monster for monster in self.state.monsters if monster.template_id == template_id), None)

    def _monsters_in_room(self, room_key: str, template_id: str | None = None) -> list[Monster]:
        return [
            monster
            for monster in self.state.monsters
            if monster.room_key == room_key and (template_id is None or monster.template_id == template_id)
        ]

    # ------------------------------------------------------------------
    # Tokens
    #
    # 原版令牌是实体配件，70 个剧本累计声明了 160 种，此前引擎完全没实现。
    # 这里只提供通用骨架（生成 / 放置 / 携带 / 翻转 / 移除 / 查询），
    # 各剧本"放几个、放哪里、怎么消耗"由精修 haunt_rules 时调用这些方法来表达。
    # ------------------------------------------------------------------
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
        same_kind = sum(1 for token in self.state.tokens if token.kind == kind)
        token = Token(
            uid=f"{kind}#{same_kind + 1}",
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

    def _haunt1_girl_start_room(self, haunt_room_key: str) -> str | None:
        """剧本 1：女孩令牌的起始房间。

        叛徒手册 p83 原文：
            "Put the Girl token (crimson) in any room on the same floor as the
             room where the haunt was and at least five tiles away from the
             Mummy. If no rooms are at least five tiles away, place her as far
             away as possible on that floor."

        按 key 排序遍历，保证同一种子每次都选到同一个房间。
        """
        room = self.state.board.get(haunt_room_key)
        if room is None:
            return None
        best_key: str | None = None
        best_distance = -1
        for key in sorted(self.state.board):
            other = self.state.board[key]
            if other.key == room.key or other.floor != room.floor:
                continue
            distance = self._path_length(room.key, other.key)
            if 5 <= distance < 9999:  # 9999 是 _path_length 表示不可达的哨兵值
                return other.key
            if distance > best_distance:
                best_key, best_distance = other.key, distance
        return best_key

    def _available_haunt1_actions(self, player: Player) -> list[HauntAction]:
        actions: list[HauntAction] = []
        room_id = self._current_room_template_id(player)
        step = self._haunt_track_value("banishment_steps")
        if player.role == "hero":
            if step < 1 and room_id in {"catacombs", "research_laboratory", "library"}:
                actions.append(HauntAction("h1_learn_true_name", "调查木乃伊真名", "知识 6+，成功后获得第一枚调查进度。"))
            if step == 1 and self._has_item(player, "omen_book"):
                actions.append(HauntAction("h1_learn_spell", "在书中学习咒语", "知识 6+，成功后获得第二枚调查进度。"))
            mummy = self._monster_by_template("mummy")
            if step >= 2 and mummy and mummy.room_key == player.room_key and self._has_item(player, "omen_book") and not player.attack_used:
                actions.append(HauntAction("h1_banish_mummy", "放逐木乃伊", "与木乃伊进行理智战斗，胜利则英雄获胜。"))
        elif player.role == "traitor":
            mummy = self._monster_by_template("mummy")
            if mummy and mummy.room_key == player.room_key:
                for card_id in ("omen_girl", "omen_ring", "omen_holy_symbol"):
                    if card_id in player.items:
                        card = self.catalog.cards[card_id]
                        actions.append(
                            HauntAction(
                                "h1_give_mummy_card",
                                f"交给木乃伊：{card.name}",
                                "木乃伊可以保管女孩、戒指或圣徽。",
                                {"card_id": card_id},
                            )
                        )
                if self._haunt1_mummy_ready_to_win(mummy):
                    actions.append(HauntAction("h1_finish_wedding", "完成木乃伊婚礼", "木乃伊带着女孩和仪式物返回石棺房，叛徒获胜。"))
        return actions

    def _perform_haunt1_action(self, player: Player, action_id: str, data: dict) -> bool:
        if action_id == "h1_learn_true_name":
            if player.role != "hero" or self._haunt_track_value("banishment_steps") >= 1:
                return False
            if self._current_room_template_id(player) not in {"catacombs", "research_laboratory", "library"}:
                return False
            if self._resolve_check(player, "knowledge", 6, "调查木乃伊真名"):
                self._set_haunt_track_value("banishment_steps", 1)
                self._log("英雄找到了木乃伊真名的线索。")
            return True
        if action_id == "h1_learn_spell":
            if player.role != "hero" or self._haunt_track_value("banishment_steps") != 1 or not self._has_item(player, "omen_book"):
                return False
            if self._resolve_check(player, "knowledge", 6, "学习放逐咒语"):
                self._set_haunt_track_value("banishment_steps", 2)
                self._log("英雄从书中学会了放逐咒语。")
            return True
        if action_id == "h1_banish_mummy":
            mummy = self._monster_by_template("mummy")
            if player.role != "hero" or not mummy or mummy.room_key != player.room_key or not self._has_item(player, "omen_book"):
                return False
            if self._haunt_track_value("banishment_steps") < 2 or player.attack_used:
                return False
            hero_roll = self._roll_attack(player, "sanity")
            mummy_roll = self._roll_monster_attack(mummy, "sanity")
            self._log(f"放逐木乃伊：{player.name} 掷出 {hero_roll}，木乃伊掷出 {mummy_roll}。")
            player.attack_used = True
            if hero_roll > mummy_roll:
                self.state.winner = "heroes"
                self.state.winner_reason = "英雄念出了木乃伊真名并完成放逐咒语。"
                self.state.phase = "GAME_OVER"
                self._log("英雄获胜。")
            elif mummy_roll > hero_roll:
                self._deal_damage(player, "mental", mummy_roll - hero_roll, source="木乃伊的诅咒")
            else:
                self._log("咒语暂时没有压过木乃伊。")
            return True
        if action_id == "h1_give_mummy_card":
            mummy = self._monster_by_template("mummy")
            card_id = data.get("card_id")
            if player.role != "traitor" or not mummy or mummy.room_key != player.room_key or card_id not in {"omen_girl", "omen_ring", "omen_holy_symbol"}:
                return False
            if card_id not in player.items:
                return False
            player.items.remove(card_id)
            if card_id in player.companions:
                player.companions.remove(card_id)
            mummy.items.append(card_id)
            self._log(f"{player.name} 把 {self.catalog.cards[card_id].name} 交给了木乃伊。")
            self._check_haunt1_traitor_victory()
            return True
        if action_id == "h1_finish_wedding":
            mummy = self._monster_by_template("mummy")
            if player.role != "traitor" or not mummy or not self._haunt1_mummy_ready_to_win(mummy):
                return False
            self._set_winner("traitor", "木乃伊带着女孩和仪式物回到了石棺房。")
            return True
        return False

    def _haunt1_mummy_ready_to_win(self, mummy: Monster) -> bool:
        haunt_room = self._haunt_rule_state().get("haunt_room", "")
        has_bride = "omen_girl" in mummy.items
        has_relic = "omen_ring" in mummy.items or "omen_holy_symbol" in mummy.items
        return bool(haunt_room and mummy.room_key == haunt_room and has_bride and has_relic)

    def _check_haunt1_traitor_victory(self) -> None:
        mummy = self._monster_by_template("mummy")
        if mummy and self._haunt1_mummy_ready_to_win(mummy):
            self._set_winner("traitor", "木乃伊带着女孩和仪式物回到了石棺房。")

    def _available_haunt5_actions(self, player: Player) -> list[HauntAction]:
        actions: list[HauntAction] = []
        if player.role != "hero":
            return actions
        room_id = self._current_room_template_id(player)
        flags = self._haunt_flags()
        silver_holder = flags.get("silver_bullets_holder")
        if room_id in {"attic", "game_room", "junk_room", "master_bedroom", "vault"} and not self._card_is_controlled("item_revolver"):
            actions.append(HauntAction("h5_find_revolver", "搜索左轮手枪", "知识 5+，成功后从物品牌堆取得左轮手枪。"))
        if room_id in {"research_laboratory", "furnace_room"} and silver_holder is None:
            actions.append(HauntAction("h5_make_silver_bullets", "制作银弹", "知识 5+，成功后获得银弹令牌。"))
        if silver_holder == player.id:
            for other in self.state.players:
                if other.id != player.id and not other.dead and other.room_key == player.room_key and other.role == "hero":
                    actions.append(
                        HauntAction(
                            "h5_give_silver_bullets",
                            f"交出银弹给 {other.name}",
                            "把银弹令牌交给同房间英雄。",
                            {"target_id": other.id},
                        )
                    )
        return actions

    def _perform_haunt5_action(self, player: Player, action_id: str, data: dict) -> bool:
        flags = self._haunt_flags()
        if action_id == "h5_find_revolver":
            if player.role != "hero" or self._current_room_template_id(player) not in {"attic", "game_room", "junk_room", "master_bedroom", "vault"}:
                return False
            if self._card_is_controlled("item_revolver"):
                return False
            if self._resolve_check(player, "knowledge", 5, "搜索左轮手枪"):
                if self._grant_card_to_player(player, "item_revolver"):
                    flags["revolver_found"] = True
            return True
        if action_id == "h5_make_silver_bullets":
            if player.role != "hero" or self._current_room_template_id(player) not in {"research_laboratory", "furnace_room"}:
                return False
            if flags.get("silver_bullets_holder") is not None:
                return False
            if self._resolve_check(player, "knowledge", 5, "制作银弹"):
                flags["silver_bullets_created"] = True
                flags["silver_bullets_holder"] = player.id
                self._set_haunt_track_value("silver_bullets", 1)
                self._log(f"{player.name} 制作出了银弹。")
            return True
        if action_id == "h5_give_silver_bullets":
            if flags.get("silver_bullets_holder") != player.id:
                return False
            target_id = int(data.get("target_id", -1))
            if not (0 <= target_id < len(self.state.players)):
                return False
            target = self.state.players[target_id]
            if target.dead or target.room_key != player.room_key or target.role != "hero":
                return False
            flags["silver_bullets_holder"] = target.id
            self._log(f"{player.name} 把银弹交给了 {target.name}。")
            return True
        return False

    def _apply_start_of_turn_haunt_effects(self, player: Player) -> None:
        if not self.state.haunt or player.dead:
            return
        # 剧本专属的回合开始效果（诅咒发作、计时器等）由 mode handler 提供。
        self._mode_handler().on_turn_start(self, player)

    def _haunt5_start_of_turn(self, player: Player) -> None:
        """剧本 5 的回合开始效果（供 WerewolfHuntMode 调用）。"""
        if player.role == "traitor":
            self._increase_stat(player, "speed", 1)
            self._increase_stat(player, "might", 1)
        flags = self._haunt_flags()
        infected = set(flags.get("infected", []))
        if player.role == "hero" and player.id in infected:
            if self._resolve_check(player, "sanity", 4, "抵抗狼人诅咒"):
                self._log(f"{player.name} 暂时压住了狼人诅咒。")
            else:
                self._haunt5_convert_to_werewolf(player)

    def _haunt5_infect(self, player: Player) -> None:
        if not self.state.haunt or self.state.haunt.id != 5 or player.dead or player.role != "hero":
            return
        flags = self._haunt_flags()
        infected = list(flags.get("infected", []))
        if player.id not in infected:
            infected.append(player.id)
            flags["infected"] = infected
            self._log(f"{player.name} 被狼人诅咒感染。")

    def _haunt5_convert_to_werewolf(self, player: Player) -> None:
        player.role = "traitor"
        for card_id in list(player.items):
            self._discard_card_from_player(player, card_id, return_to_room=True)
        player.companions.clear()
        self._log(f"{player.name} 变成了狼人，加入叛徒阵营。")
        self.check_victory()

    def _haunt5_has_silver_bullets(self, player: Player) -> bool:
        return self._haunt_flags().get("silver_bullets_holder") == player.id

    def _haunt5_is_werewolf_target(self, target: object) -> bool:
        if isinstance(target, Player):
            return target.role == "traitor" and not target.dead
        if isinstance(target, Monster):
            return target.template_id == "dog"
        return False

    def _haunt5_try_silver_bullet_kill(self, attacker: Player, target: object, weapon: Card | None) -> bool:
        if not self.state.haunt or self.state.haunt.id != 5:
            return False
        if weapon is None or weapon.id != "item_revolver" or not self._haunt5_has_silver_bullets(attacker):
            return False
        if not self._haunt5_is_werewolf_target(target):
            return False
        if isinstance(target, Player):
            target.dead = True
            self._log(f"{attacker.name} 用银弹击杀了 {target.name}。")
            self._drop_inventory_on_death(target)
        elif isinstance(target, Monster):
            self.state.monsters = [monster for monster in self.state.monsters if monster.id != target.id]
            self._log(f"{attacker.name} 用银弹击杀了 {target.name}。")
        return True

    def _adjust_damage_for_haunt(self, player: Player, amount: int, source: str) -> int:
        if amount <= 0:
            return amount
        if self.state.haunt and self.state.haunt.id == 5 and player.role == "traitor" and source != "银弹":
            reduced = max(1, (amount + 1) // 2)
            if reduced != amount:
                self._log("狼人抗性让伤害减半。")
            return reduced
        return amount

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
        for room in self.state.board.values():
            if not room.revealed and room.symbol == "omen":
                return True
        for room_id in (*self.state.room_deck, *self.state.room_discard):
            template = self.catalog.room_templates.get(room_id)
            if template and template.symbol == "omen":
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
        )
        self._next_monster_id += 1
        self.state.monsters.append(monster)
        self._log(f"怪物出现：{monster.name}。")
        return monster

    # ------------------------------------------------------------------
    # Monster turn
    # ------------------------------------------------------------------
    def _resolve_monster_turns(self) -> None:
        if not self.state.monsters:
            return
        for monster in self.state.monsters:
            if monster.stunned_turns > 0:
                monster.stunned_turns -= 1
                self._log(f"{monster.name} 因昏迷跳过一回合。")
                continue
            target = self._find_monster_target(monster)
            if target is None:
                continue
            path = self._shortest_path(monster.room_key, target.room_key)
            if len(path) > 1:
                steps = max(1, self.roll_dice(monster.speed, "怪物移动"))
                # 剧本可接管移动（例如木乃伊掷出 0/1 时经秘密通道移动）；
                # 返回 False 才走常规的沿最短路径前进。
                if not self._mode_handler().on_monster_move(self, monster, steps):
                    new_index = min(len(path) - 1, steps)
                    monster.room_key = path[new_index]
                    self._log(f"{monster.name} 移动到 {self.state.board[monster.room_key].name}。")
            if monster.room_key == target.room_key:
                self._monster_attack(monster, target)
        self.check_victory()

    def _find_monster_target(self, monster: Monster) -> Player | None:
        candidates = [player for player in self.state.players if not player.dead and player.role != "traitor"]
        if monster.controller == "traitor":
            candidates = [player for player in self.state.players if not player.dead and player.role == "hero"]
        if not candidates:
            return None
        candidates.sort(key=lambda player: self._path_length(monster.room_key, player.room_key))
        return candidates[0]

    def _monster_attack(self, monster: Monster, target: Player) -> None:
        # 剧本可完全接管本回合的攻击（如外星人对同房间所有人的意念攻击——
        # 它是"代替普通攻击"的主动技能，输赢都要结算，不能等命中判定）。
        if self._mode_handler().on_monster_turn_attack(self, monster):
            return
        monster_roll = self._roll_monster_attack(monster, "might")
        target_roll = self._roll_attack(target, "might")
        self._log(f"{monster.name} 攻击 {self._player_label(target)}：{monster_roll} 对 {target_roll}。")
        if monster_roll > target_roll:
            amount = monster_roll - target_roll
            # 剧本可自行结算伤害（例如木乃伊扣速度而非造成物理伤害）；
            # 返回 False 才走默认的物理伤害。
            if not self._mode_handler().on_monster_attack(self, monster, target, amount):
                self._deal_damage(target, "physical", amount, source=monster.name)
            if monster.template_id == "dog":
                self._haunt5_infect(target)
        elif monster_roll < target_roll:
            self._stun_monster(monster, 1)
        else:
            self._log("平手。")

    # ------------------------------------------------------------------
    # Graph/path helpers
    # ------------------------------------------------------------------
    def _build_graph(self) -> dict[str, set[str]]:
        # 邻接表必须是有序结构。若用 set，BFS 遍历顺序会随 PYTHONHASHSEED
        # 变化，导致同一种子在不同进程得到不同的最短路径——种子回放、
        # 存档复现、联机重放都会失效。这里用 dict 做有序去重，再输出排序列表。
        adjacency: dict[str, dict[str, None]] = {key: {} for key in self.state.board}
        for room in self.state.board.values():
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                pos = (room.floor, room.x + dx, room.y + dy)
                target_key = self.state.pos_index.get(pos)
                if not target_key:
                    continue
                target = self.state.board[target_key]
                if OPPOSITE[direction] in target.doors:
                    adjacency[room.key][target_key] = None
                    adjacency[target_key][room.key] = None
            for link_value in room.links.values():
                target_key = self._link_target_key(link_value)
                if target_key:
                    adjacency[room.key][target_key] = None
                    adjacency[target_key][room.key] = None
        return {key: sorted(neighbors) for key, neighbors in adjacency.items()}

    def _reachable_nodes(self, start_key: str, graph: dict[str, list[str]]) -> set[str]:
        visited = {start_key}
        queue = deque([start_key])
        while queue:
            key = queue.popleft()
            for neighbor in graph.get(key, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def _path_length(self, start_key: str, target_key: str) -> int:
        """两房间之间的步数（相邻为 1，同房间为 0，不可达返回 9999）。

        修正说明：_shortest_path 返回的是**包含起点**的节点序列，所以步数
        是 长度 - 1。过去直接返回 len(path)，导致距离整体多算 1
        （自己房间算出 1、相邻房间算出 2）。

        更严重的是：没找到路径时 _shortest_path 也返回 [start_key]，
        与"同房间"无法区分，于是不可达的房间被算成距离 1——比真正相邻的
        房间（2）还要近，9999 这个哨兵值从来没生效过。后果是怪物会优先
        追那些根本走不到的目标。
        """
        if start_key == target_key:
            return 0
        path = self._shortest_path(start_key, target_key)
        if len(path) < 2:
            return 9999
        return len(path) - 1

    def _shortest_path(self, start_key: str, target_key: str) -> list[str]:
        if start_key == target_key:
            return [start_key]
        graph = self._build_graph()
        queue = deque([(start_key, [start_key])])
        visited = {start_key}
        while queue:
            key, path = queue.popleft()
            for neighbor in graph.get(key, ()):
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                if neighbor == target_key:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))
        return [start_key]

    # ------------------------------------------------------------------
    # Victory
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
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

    def _drop_inventory_on_death(self, player: Player) -> None:
        room_cards = self.state.room_items.setdefault(player.room_key, [])
        for card_id in player.items:
            room_cards.append(card_id)
        for card_id in player.companions:
            if card_id not in room_cards:
                room_cards.append(card_id)
        player.items.clear()
        player.companions.clear()
        self._log(f"{player.name} 的物品掉落在 {self.current_room(player).name}。")

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

    def _link_target_key(self, link_value: str) -> str | None:
        """把链接目标解析为板块 key。
        静态链接（如楼梯）存的是模板 id，动态链接（如密道）存的是板块 key。"""
        if link_value in self.state.board:
            return link_value
        for key, room in self.state.board.items():
            if room.template_id == link_value:
                return key
        return None

    def _log(self, message: str, category: str = "") -> None:
        self.state.log.append(message)
        if len(self.state.log) > 400:
            self.state.log = self.state.log[-400:]

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
