from __future__ import annotations

from dataclasses import dataclass, field

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
