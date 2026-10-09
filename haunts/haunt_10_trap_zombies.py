"""ZombieTrapMode（剧本 10）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class ZombieTrapMode(GenericModeHandler):
    """剧本 10 家族聚会（Family Gathering）。

    权威原文：英雄手册 p21 / 叛徒手册 p92。

    骨架数据基本正确（僵尸按预兆房间生成、疯子 5 点伤害容量、陷阱房间
    列表），本模式把机制接通：

    · 叛徒开局即被疯子杀死（p92）——与剧本 4/6 同款"叛徒出局但游戏继续"
      模型；疯子令牌顶替他的位置，怪物阶段由本轮最后一位存活玩家代跑。
    · 陷阱（英雄胜）：僵尸进入或回合开始时处于特殊房间（主卧/教堂/温室/
      游戏室/图书馆/阁楼）→ 知识检定 4+ 成功则挣脱；失败则永远停在该
      房间（不再移动/攻击/检定），进度 +1；每间房只能困一只（p21）。
      全部僵尸被困 → 英雄胜。
    · 疯子（p92）：可承受 5 点物理伤害才死；伤害不影响属性，常规攻击的
      击晕照旧。累计伤害达容量即整场离场。
    · 已知简化：p92 的"无视野时叛徒自由操控、有视线才追人"未实现——
      电子版 bot 始终追最近英雄（引擎默认，接近"看到英雄"后的行为）；
      "A Zombie attacks as soon as it's in a room with an explorer" 的
      即时攻击用引擎"移动结束同房即攻击"近似（中途经过不额外攻击）。
    """

    mode = "trap_zombies"

    ZOMBIE = "zombie"
    MADMAN = "madman"
    TRAP_ROOMS = ["master_bedroom", "chapel", "conservatory", "game_room", "library", "attic"]

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        madman = engine._monster_by_template(self.MADMAN)
        if traitor is not None:
            if madman is not None:
                madman.room_key = traitor.room_key  # 疯子令牌顶替叛徒的位置
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"疯子从地板下爬出，把叛徒{traitor.name}拖进了地底。")
        engine._haunt_flags().setdefault("trapped_zombies", [])
        engine._haunt_flags().setdefault("trapped_rooms", [])

    # ------------------------------------------------------------- 陷阱
    def _try_trap(self, engine: Any, zombie: Any) -> bool:
        """僵尸在特殊房间时尝试困住它。返回 True = 已被困住（或本就困着）。"""
        trapped = set(engine._haunt_flags().get("trapped_zombies", []))
        zombie_id = str(getattr(zombie, "id", ""))
        if zombie_id in trapped:
            return True
        room = engine.state.board.get(getattr(zombie, "room_key", ""))
        if room is None or room.template_id not in self.TRAP_ROOMS:
            return False
        if room.key in set(engine._haunt_flags().get("trapped_rooms", [])):
            return False  # 这间房已经困过一只
        roll = engine.roll_dice(getattr(zombie, "knowledge", 3), "僵尸滞留检定")
        if roll >= 4:
            engine._log(f"{zombie.name} 在{room.name}里嗅了嗅，挣脱了回忆的束缚。")
            return False
        flags = engine._haunt_flags()
        flags["trapped_zombies"] = sorted(trapped | {zombie_id})
        flags["trapped_rooms"] = sorted(set(flags.get("trapped_rooms", [])) | {room.key})
        engine._advance_haunt_track("zombies_trapped", 1)
        engine._log(f"{zombie.name} 在{room.name}前愣住了——他认出了自己的家，永远停在了那里。")
        engine.check_victory()
        return True

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.ZOMBIE:
            return False
        if self._try_trap(engine, monster):
            return True  # 困在特殊房间开始回合：直接结算，不再行动
        return False

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """僵尸移动的终点若是特殊房间，先落位再判陷阱（p21 进入即判）。"""
        if _monster_id(monster) != self.ZOMBIE:
            return False
        if str(getattr(monster, "id", "")) in set(
            engine._haunt_flags().get("trapped_zombies", [])
        ):
            return True
        target = engine._find_monster_target(monster)
        if target is None:
            return False
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) <= 1:
            return False
        dest = path[min(len(path) - 1, rolled)]
        monster.room_key = dest  # 先落位（引擎默认随后也会走到同一格）
        if self._try_trap(engine, monster):
            return True  # 已被困住：跳过引擎的后续移动
        return False

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """疯子：物理伤害容量 5，常规击晕照旧（返回 False 让引擎默认击晕）。"""
        if _monster_id(monster) != self.MADMAN:
            return False
        engine._advance_haunt_track("madman_damage", max(1, amount))
        taken = engine._haunt_track_value("madman_damage")
        if taken >= engine._haunt_track_target("madman_damage"):
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            engine._log("疯子轰然倒地——这一家子终于团聚了。")
            engine.check_victory()
        return False

    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("zombies_trapped") >= engine._haunt_track_target("zombies_trapped"):
            engine._set_winner("heroes", "所有僵尸都回到了生前最爱的房间，安静地停了下来。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "疯子和他的家人们收割了整栋房子。")
            return True
        return True  # 吸收"叛徒开局已死 → 引擎判英雄胜"的兜底
