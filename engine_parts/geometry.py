from __future__ import annotations

try:
    from ..models import DIRECTIONS
except ImportError:
    from models import DIRECTIONS

def _room_key(floor: int, x: int, y: int) -> str:
    return f"{floor}:{x}:{y}"

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
