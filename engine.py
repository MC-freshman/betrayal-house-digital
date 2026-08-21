from __future__ import annotations

import hashlib
import random
from collections import deque
from dataclasses import dataclass
from datetime import date
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
    )
except ImportError:  # pragma: no cover - direct script execution
    from content import build_catalog  # type: ignore
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
                    overflow={key: 0 for key in STAT_NAMES},
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
        attempts = len(self.state.room_deck) + len(self.state.room_discard) + 8
        while attempts > 0:
            if not self.state.room_deck:
                if self.state.room_discard:
                    self.state.room_deck = self.state.room_discard[:]
                    self.state.room_discard.clear()
                    self.rng.shuffle(self.state.room_deck)
                else:
                    self.state.room_deck = [room_id for room_id in self.catalog.room_draw_pool]
                    self.rng.shuffle(self.state.room_deck)
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

        if self.state.phase == "HAUNT_PHASE" and self.state.traitor_id == player.id:
            self._resolve_monster_turns()

        self._advance_turn()
        if self.state.winner:
            return
        self.start_turn()

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
            if room.symbol:
                if room.symbol == "event" and self.state.phase == "HAUNT_PHASE" and player.role == "traitor":
                    if self.prompter.confirm("事件卡", f"{player.name} 进入了带事件符号的房间。要触发事件吗？"):
                        self._draw_symbol_card(player, room.symbol)
                    else:
                        self._log(f"{player.name} 选择不触发这张事件卡。")
                else:
                    self._draw_symbol_card(player, room.symbol)
        self._collect_room_companions(player, room)
        self._apply_room_effect(player, room, first_entry=first_entry)
        self.check_victory()

    def _draw_symbol_card(self, player: Player, symbol: str) -> None:
        kind_map = {"omen": "omen", "item": "item", "event": "event"}
        kind = kind_map.get(symbol)
        if kind is None:
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

    def _draw_item(self, player: Player) -> None:
        card_id = self._draw_card_id("item")
        card = self.catalog.cards[card_id]
        player.items.append(card_id)
        self._log(f"{player.name} 抽到物品：{card.name}。")

    def _draw_event(self, player: Player) -> None:
        card_id = self._draw_card_id("event")
        card = self.catalog.cards[card_id]
        self._log(f"{player.name} 抽到事件：{card.name}。")
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
        if effect == "room_placeholder":
            self._log(f"{room.name} 暂无额外特效，按普通房间处理。")
            return

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
            roll = self.roll_dice(2)
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
        if effect == "event_generic":
            roll = self.rng.random()
            if roll < 0.35:
                self._deal_damage(player, "physical", 1, source=card.name)
            elif roll < 0.7:
                self._deal_damage(player, "mental", 1, source=card.name)
            else:
                self._draw_item(player)
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
    def roll_dice(self, count: int) -> int:
        count = max(1, min(8, count))
        return sum(self.rng.choice((0, 1, 2)) for _ in range(count))

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

    def _stat_cap(self, player: Player, stat: str) -> int:
        return player.stats_max[stat] + player.overflow.get(stat, 0)

    def _heal_stat(self, player: Player, stat: str, amount: int) -> None:
        cap = self._stat_cap(player, stat)
        before = player.stats[stat]
        player.stats[stat] = min(cap, player.stats[stat] + amount)
        if player.stats[stat] != before:
            self._log(f"{player.name} 的 {stat} 恢复到 {player.stats[stat]}。")

    def _increase_stat(self, player: Player, stat: str, amount: int) -> None:
        cap = self._stat_cap(player, stat)
        before = player.stats[stat]
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
        dice = self._effective_stat(player, stat) + self._check_bonus(player, stat)
        dice = max(1, min(8, dice))
        roll = self.roll_dice(dice)
        self._log(f"{label}：{player.name} 掷出 {roll}（{dice} 骰），目标 {target}。")
        if roll >= target:
            return True
        if player.extra_check_rerolls > 0:
            player.extra_check_rerolls -= 1
            self._log(f"{player.name} 因额外重掷机会再次检定。")
            roll = self.roll_dice(dice)
            self._log(f"重掷结果：{roll}。")
            return roll >= target
        if self.prompter.confirm("重掷", f"{label} 失败了，要使用重掷机会吗？"):
            roll = self.roll_dice(dice)
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
        floor = 0 if self.state.phase == "HAUNT_PHASE" else 2
        before = player.stats[stat]
        player.stats[stat] = max(floor, player.stats[stat] - amount)
        self._log(f"{player.name} 的 {stat} 从 {before} 降到 {player.stats[stat]}。")

    def _check_player_death(self, player: Player) -> None:
        if self.state.phase != "HAUNT_PHASE":
            return
        if any(player.stats[stat] <= 0 for stat in STAT_NAMES):
            player.dead = True
            self._log(f"{player.name} 倒下了。")
            self._drop_inventory_on_death(player)

    def _deal_damage(self, player: Player, damage_type: str, amount: int, source: str = "") -> None:
        if amount <= 0 or player.dead:
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
        else:
            self._log(f"{card.name} 已经在背包里，暂时没有额外可启动的动作。")
            success = True
        if success:
            player.item_used = True
        return success

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
        if ranged:
            return self.available_ranged_targets(player)
        room = self.current_room(player)
        targets: list[object] = []
        for other in self.state.players:
            if other.id == player.id or other.dead:
                continue
            if other.role == player.role:
                continue
            if other.room_key == player.room_key:
                targets.append(other)
        for monster in self.state.monsters:
            if monster.room_key == player.room_key:
                targets.append(monster)
        return targets

    def available_ranged_targets(self, player: Player | None = None) -> list[object]:
        player = player or self.current_player
        if player.dead or self.state.phase != "HAUNT_PHASE" or player.attack_used:
            return []
        room = self.current_room(player)
        targets: list[object] = []
        for other in self.state.players:
            if other.id == player.id or other.dead or other.role == player.role:
                continue
            if self._has_line_of_sight(room.key, other.room_key):
                targets.append(other)
        for monster in self.state.monsters:
            if self._has_line_of_sight(room.key, monster.room_key):
                targets.append(monster)
        return targets

    def attack(self, attacker: Player, target: object, weapon_card_id: str | None = None, ranged: bool = False) -> bool:
        if attacker.dead or attacker.attack_used or self.state.phase != "HAUNT_PHASE":
            return False
        attacker_room = self.current_room(attacker)
        target_room_key = target.room_key
        if not ranged and attacker_room.key != target_room_key:
            return False
        if ranged and not self._has_line_of_sight(attacker_room.key, target_room_key):
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
        if isinstance(target, Player):
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
            if isinstance(target, Player) and not ranged and diff >= 2 and self._can_steal(target):
                if self.prompter.confirm("偷窃", f"造成了 {diff} 点伤害。要改为偷取物品吗？"):
                    self._steal_from_target(attacker, target)
                    if weapon is not None:
                        self._resolve_attack_weapon_use(attacker, weapon)
                    attacker.attack_used = True
                    return True
            self._apply_attack_damage(target, diff, attack_attr)
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
        return self.roll_dice(dice)

    def _roll_monster_attack(self, monster: Monster, attr: str) -> int:
        stat = getattr(monster, attr, 0)
        dice = max(1, min(8, stat))
        return self.roll_dice(dice)

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
            self._stun_monster(target, 1 if amount > 0 else 0)
            return
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
    def _resolve_haunt_check(self, revealer: Player) -> bool:
        if not self.state.haunt_pending:
            return False
        roll = self.roll_dice(6)
        self._log(f"作祟检定：掷出 {roll}，预兆总数为 {self.state.omens_drawn}。")
        if roll < self.state.omens_drawn:
            self._trigger_haunt(revealer)
            return True
        else:
            self._log("这次没有触发作祟。")
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
        self._spawn_haunt_monsters(haunt, current_room.key)
        self._prepare_haunt_turn_order(traitor.id)
        self.state.phase = "HAUNT_PHASE"
        self._log("作祟私密信息已发送。")
        self._show_private_haunt_briefings()

    def _select_haunt_id(self, room_id: str, omen_id: str) -> int:
        payload = f"{room_id}|{omen_id}".encode("utf-8")
        value = int(hashlib.sha1(payload).hexdigest(), 16)
        return (value % 50) + 1

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
        traitor = self.state.players[self.state.traitor_id] if self.state.traitor_id is not None else None
        if traitor:
            self.prompter.notify(
                "作祟信息",
                f"请秘密持有者单独阅读以下内容。\n\n{self.state.haunt.traitor_goal}",
            )
        heroes = [player.name for player in self.state.players if player.role == "hero" and not player.dead]
        if heroes:
            self.prompter.notify(
                "英雄信息",
                f"请英雄玩家一起阅读目标。\n\n{self.state.haunt.hero_goal}",
            )

    def _spawn_haunt_monsters(self, haunt: Haunt, room_key: str) -> None:
        for monster_id in haunt.suggested_monsters:
            if monster_id not in self.catalog.monsters:
                continue
            template = self.catalog.monsters[monster_id]
            monster = Monster(
                id=f"mon_{self._next_monster_id}",
                template_id=template.id,
                name=template.name,
                speed=template.speed,
                might=template.might,
                sanity=template.sanity,
                knowledge=template.knowledge,
                room_key=room_key,
                controller="traitor",
                stunned_turns=0,
                can_carry_items=template.can_carry_items,
                tags=template.tags,
            )
            self._next_monster_id += 1
            self.state.monsters.append(monster)
            self._log(f"怪物出现：{monster.name}。")

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
                steps = max(1, self.roll_dice(monster.speed))
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
        monster_roll = self._roll_monster_attack(monster, "might")
        target_roll = self._roll_attack(target, "might")
        self._log(f"{monster.name} 攻击 {self._player_label(target)}：{monster_roll} 对 {target_roll}。")
        if monster_roll > target_roll:
            self._deal_damage(target, "physical", monster_roll - target_roll, source=monster.name)
        elif monster_roll < target_roll:
            self._stun_monster(monster, 1)
        else:
            self._log("平手。")

    # ------------------------------------------------------------------
    # Graph/path helpers
    # ------------------------------------------------------------------
    def _build_graph(self) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {key: set() for key in self.state.board}
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
                    graph[room.key].add(target_key)
                    graph[target_key].add(room.key)
            for link_value in room.links.values():
                target_key = self._link_target_key(link_value)
                if target_key:
                    graph[room.key].add(target_key)
                    graph[target_key].add(room.key)
        return graph

    def _reachable_nodes(self, start_key: str, graph: dict[str, set[str]]) -> set[str]:
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
        path = self._shortest_path(start_key, target_key)
        return len(path) if path else 9999

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
    def check_victory(self) -> None:
        if self.state.phase != "HAUNT_PHASE" or self.state.winner:
            return
        heroes = [player for player in self.state.players if player.role == "hero" and not player.dead]
        traitor = next((player for player in self.state.players if player.role == "traitor" and not player.dead), None)
        if not heroes and traitor is not None:
            self.state.winner = "traitor"
            self.state.winner_reason = "所有英雄都倒下了。"
            self.state.phase = "GAME_OVER"
            self._log("叛徒获胜。")
        elif traitor is None and heroes:
            self.state.winner = "heroes"
            self.state.winner_reason = "叛徒已经倒下。"
            self.state.phase = "GAME_OVER"
            self._log("英雄获胜。")

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

    def _log(self, message: str) -> None:
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
