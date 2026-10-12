from collections import deque
from copy import deepcopy
from typing import Any
try:
    from ..models import Catalog, Card, CharacterFace, DIRECTIONS, DIRECTION_DELTAS, GameState, Haunt, Monster, OPPOSITE, PHYSICAL_STATS, Player, PlacedRoom, RoomTemplate, STAT_NAMES, Token
    from ..haunt_modes import get_mode_handler
except ImportError:
    from models import Catalog, Card, CharacterFace, DIRECTIONS, DIRECTION_DELTAS, GameState, Haunt, Monster, OPPOSITE, PHYSICAL_STATS, Player, PlacedRoom, RoomTemplate, STAT_NAMES, Token
    from haunt_modes import get_mode_handler
from .types import ExitOption, ActionCommand, HauntAction
from .geometry import _distance_hint, _room_key, _rotate_direction, _rotate_doors, _rotate_links
