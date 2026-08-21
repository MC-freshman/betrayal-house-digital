from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


DIRECTIONS = ("north", "east", "south", "west")
OPPOSITE = {
    "north": "south",
    "east": "west",
    "south": "north",
    "west": "east",
}
DIRECTION_DELTAS = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}
STAT_NAMES = ("speed", "might", "sanity", "knowledge")
PHYSICAL_STATS = ("speed", "might")
MENTAL_STATS = ("sanity", "knowledge")


@dataclass
class CharacterFace:
    id: str
    card_id: str
    face_index: int
    name: str
    source_name: str = ""
    aliases: list[str] = field(default_factory=list)
    birthday: str = ""
    stats: dict[str, int] = field(default_factory=dict)
    stats_max: dict[str, int] = field(default_factory=dict)
    flavor: str = ""


@dataclass
class Card:
    id: str
    kind: str
    name: str
    source_name: str = ""
    text: str = ""
    tags: tuple[str, ...] = ()
    effect_id: str = "generic"
    keep: bool = True
    tradeable: bool = True
    omen_trigger: bool = False
    one_shot: bool = False
    bonus: dict[str, int] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoomTemplate:
    id: str
    name: str
    source_name: str = ""
    floor: int = 0
    doors: tuple[str, ...] = ()
    symbol: str | None = None
    effect_id: str = "none"
    text: str = ""
    special: bool = False
    links: dict[str, str] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    generated: bool = False


@dataclass
class PlacedRoom:
    key: str
    template_id: str
    name: str
    floor: int
    x: int
    y: int
    rotation: int = 0
    doors: tuple[str, ...] = ()
    symbol: str | None = None
    effect_id: str = "none"
    text: str = ""
    special: bool = False
    links: dict[str, str] = field(default_factory=dict)
    discovered_by: Optional[int] = None
    revealed: bool = False
    first_effect_done: bool = False
    visit_count: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonsterTemplate:
    id: str
    name: str
    source_name: str = ""
    speed: int = 2
    might: int = 2
    sanity: int = 0
    knowledge: int = 0
    tags: tuple[str, ...] = ()
    can_carry_items: bool = False
    text: str = ""


@dataclass
class Monster:
    id: str
    template_id: str
    name: str
    speed: int
    might: int
    sanity: int = 0
    knowledge: int = 0
    room_key: str = ""
    controller: str = "traitor"
    stunned_turns: int = 0
    can_carry_items: bool = False
    items: list[str] = field(default_factory=list)
    tags: tuple[str, ...] = ()


@dataclass
class Haunt:
    id: int
    name: str
    traitor_rule: str = "revealer"
    hero_goal: str = ""
    traitor_goal: str = ""
    mode: str = "generic"
    trigger_hint: str = ""
    suggested_monsters: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Player:
    id: int
    name: str
    character_id: str
    character_name: str
    source_name: str = ""
    aliases: list[str] = field(default_factory=list)
    birthday: str = ""
    stats: dict[str, int] = field(default_factory=dict)
    stats_max: dict[str, int] = field(default_factory=dict)
    overflow: dict[str, int] = field(default_factory=dict)
    room_key: str = ""
    items: list[str] = field(default_factory=list)
    companions: list[str] = field(default_factory=list)
    role: str = "explorer"
    dead: bool = False
    steps_remaining: int = 0
    attack_used: bool = False
    item_used: bool = False
    moved_this_turn: bool = False
    movement_stopped: bool = False
    extra_speed_this_turn: int = 0
    extra_check_rerolls: int = 0
    ignore_first_physical_damage: bool = False
    next_check_auto_success: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class GameState:
    phase: str = "SETUP"
    turn_index: int = 0
    turn_order: list[int] = field(default_factory=list)
    turn_count: int = 0
    players: list[Player] = field(default_factory=list)
    board: dict[str, PlacedRoom] = field(default_factory=dict)
    pos_index: dict[tuple[int, int, int], str] = field(default_factory=dict)
    room_deck: list[str] = field(default_factory=list)
    room_discard: list[str] = field(default_factory=list)
    card_decks: dict[str, list[str]] = field(default_factory=dict)
    card_discards: dict[str, list[str]] = field(default_factory=dict)
    omens_drawn: int = 0
    last_omen_id: Optional[str] = None
    haunt_pending: bool = False
    haunt_revealer_id: Optional[int] = None
    haunt: Optional[Haunt] = None
    traitor_id: Optional[int] = None
    monsters: list[Monster] = field(default_factory=list)
    room_items: dict[str, list[str]] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    winner: Optional[str] = None
    winner_reason: str = ""
    seed: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Catalog:
    characters: dict[str, CharacterFace]
    character_cards: dict[str, list[str]]
    cards: dict[str, Card]
    room_templates: dict[str, RoomTemplate]
    room_draw_pool: list[str]
    haunt_defs: dict[int, Haunt]
    monsters: dict[str, MonsterTemplate]
    start_room_ids: list[str]
    room_targets: dict[int, int]
