"""DarkerThanNightMode（剧本 51）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class DarkerThanNightMode(GenericModeHandler):
    """剧本 51 比夜更黑（Darker than Night）。"""

    mode = "darker_than_night"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["dark_hexes"] = 0
        flags["seal_rooms_used"] = []
        engine._log("窗户变成了镜子——黑暗在房子里蔓延。")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        hexes = int(flags.get("dark_hexes", 0))
        if hexes >= 3:
            return
        outer_rooms = [
            k for k, r in engine.state.board.items()
            if r.template_id in ("balcony", "garden", "graveyard", "patio", "tower")
            and not engine.tokens_in_room(k, "dark_hex")
        ]
        if outer_rooms:
            room = engine.rng.choice(sorted(outer_rooms))
            roll = engine._roll_attack(player, "knowledge")
            if roll >= 5:
                engine.spawn_token("dark_hex", label="黑暗 Hex", role="marker", room_key=room)
                flags["dark_hexes"] = hexes + 1
                engine._log(f"黑暗仪式推进了！（{hexes + 1}/3）")
                engine.check_victory()

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        if engine._haunt_track_value("hero_progress") >= engine._haunt_track_target("hero_progress"):
            engine._set_winner("heroes", "圣印驱散了黑暗。")
            return True
        if int(flags.get("dark_hexes", 0)) >= 3:
            engine._set_winner("traitor", "黑暗仪式完成了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也被黑暗吞噬了。")
            return True
        # p62：英雄胜利条件之二 = 杀死叛徒（"…or you kill the traitor."），显式接管判定。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            engine._set_winner("heroes", "黑暗的祭主被斩除了——仪式失去了主人。")
            return True
        return False
