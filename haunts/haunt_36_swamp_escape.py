"""SwampEscapeMode（剧本 36）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class SwampEscapeMode(GenericModeHandler):
    """剧本 36 有朋友更好（Better with Friends）。

    权威原文：英雄手册 p47 / 叛徒手册 p118。

    · 阁楼强制入场；小艇在阁楼（p118）；背负 ×2 移动、可交易。
    · 洪水：叛徒回合结束推进计时；6 个阶段（地下室部分淹 → 全淹 →
      一楼部分淹 → 全淹 → 全屋部分淹 → 全屋全淹）。部分淹 -2 移动 /
      全淹 -4 移动 + 2 骰物理（不可防——source="洪水"绕过盔甲）。
      洪水影响所有英雄，叛徒免疫。
    · 逃跑：全部活英雄在阳台/塔楼 + 小艇在场 → 逃离。至少半数出逃
      → 英雄胜。
    · 勋章：在部分/全淹房间丢弃勋章暂停洪水一回合（弃卡）。
    · 破坏小艇：叛徒力量 3+ 攻击小艇，5 次毁坏 → 叛徒胜。
    · 简化：狗不能背小艇未建模；洪水移动减值用 movement_cost_floor
      近似（不叠加怪物费——原始规则是减掉步数，本实现等效为抬高费
      用下限）；小艇不实现为可交易卡（用令牌承载，转交行动近似）。
    """

    mode = "swamp_escape"

    BOAT = "rowboat"
    ESCAPE_ROOMS = {"balcony", "tower"}

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["boat_carrier"] = None
        flags["boat_destroyed"] = False
        flags["medallion_pause"] = False
        attic = engine._ensure_room_in_play("attic", room_key)
        flags["boat_room"] = attic
        if attic:
            engine.spawn_token(self.BOAT, label="小艇", role="marker", room_key=attic)
        # p47 逃生点是阳台或塔楼：探索阶段未必翻到，缺了就只能扛着艇空转
        # （seed101/5p 实测：小艇扛起后英雄钉在二楼平台 351 次）。
        if not any(room.template_id in self.ESCAPE_ROOMS for room in engine.state.board.values()):
            engine._ensure_room_in_play("balcony", attic or room_key) or engine._ensure_room_in_play(
                "tower", attic or room_key
            )
        engine._log("地下室传来水声——房子正在沉入地下沼泽！")

    # ------------------------------------------------------------- 洪水
    def _flood_level(self, engine: Any) -> int:
        return int(engine._haunt_track_value("flood_timer"))

    def _flood_desc(self, engine: Any, floor: int) -> str:
        """返回 floor 层的洪水状态："none"/"partial"/"full"。"""
        turn = self._flood_level(engine)
        if turn <= 0:
            return "none"
        if floor == -1:  # 地下室
            return "partial" if turn == 1 else "full"
        if floor == 0:   # 一楼
            if turn <= 2:
                return "none"
            return "partial" if turn == 3 else "full"
        # 上层
        if turn <= 4:
            return "none"
        return "partial" if turn == 5 else "full"

    def _floor_for_room(self, engine: Any, key: str) -> int:
        room = engine.state.board.get(key)
        return room.floor if room else 0

    def _move_penalty(self, engine: Any, player: Any) -> int:
        """p47：部分淹 -2 / 全淹 -4。"""
        level = self._flood_desc(engine, self._floor_for_room(engine, player.room_key))
        if level == "partial":
            return 2
        if level == "full":
            return 4
        return 0

    def _advance_flood(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        if flags.get("medallion_pause"):
            flags["medallion_pause"] = False
            engine._log("勋章的力量暂时压制了洪水——本轮不推进。")
            return
        current = int(engine._haunt_track_value("flood_timer"))
        if current >= 6:
            return
        engine._set_haunt_track_value("flood_timer", current + 1)
        level = self._flood_level(engine)
        desc = {
            1: "地下室部分淹",
            2: "地下室全淹",
            3: "地下室全淹+一楼部分淹",
            4: "地下室+一楼全淹",
            5: "全屋部分淹",
            6: "全屋全淹",
        }.get(level, "")
        engine._log(f"洪水上涨！（{level}/6：{desc}）")

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.role == "traitor":
            if player.dead:
                return
            # p118：回合结束推进 → 用下一回合开始近似
            self._advance_flood(engine)
            return
        # 英雄：全淹伤害
        if player.dead:
            return
        if self._flood_desc(engine, self._floor_for_room(engine, player.room_key)) == "full":
            amount = engine.roll_dice(2, "洪水")
            engine._log(f"{player.name} 在齐胸的洪水中挣扎（2 骰不可防物理伤害）。")
            engine._deal_damage(player, "physical", amount, source="洪水")
            engine.check_victory()

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """叛徒死后洪水仍按"一整轮一次"上涨（p47 沉屋不因叛徒倒下而停）。"""
        if any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return
        alive_ids = {p.id for p in engine.state.players if not p.dead}
        if player.id not in alive_ids:
            return
        order = list(engine.state.turn_order or [])
        if not order:
            self._advance_flood(engine)
            return
        try:
            idx = order.index(player.id)
        except ValueError:
            self._advance_flood(engine)
            return
        next_alive = None
        for offset in range(1, len(order) + 1):
            candidate = order[(idx + offset) % len(order)]
            if candidate in alive_ids:
                next_alive = candidate
                break
        if next_alive is None:
            return
        # 下一个活人的下标不大于当前 → 本轮即将绕回，当前是本轮末尾
        try:
            next_idx = order.index(next_alive)
        except ValueError:
            return
        if next_idx <= idx:
            self._advance_flood(engine)

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p47：部分淹 -2 / 全淹 -4 移动——等效为抬高费用下限。"""
        if isinstance(getattr(player, "role", None), str) and player.role == "traitor":
            return 0  # p118：洪水不影响叛徒
        penalty = self._move_penalty(engine, player)
        return max(0, 1 + penalty) if penalty else 0

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p47：背着小艇入房 2 格。"""
        if engine._haunt_flags().get("boat_carrier") == getattr(player, "id", None):
            return 2
        return 1

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        flood = self._flood_level(engine)
        for action in actions:
            if action.id == "take_rowboat":
                if player.role != "hero" or flags.get("boat_destroyed"):
                    continue
                if flags.get("boat_carrier") is not None:
                    continue
                if not engine.tokens_in_room(player.room_key, self.BOAT):
                    continue
            if action.id == "drop_medallion":
                if player.role != "hero" or "omen_medallion" not in player.items:
                    continue
                if flood <= 0 or self._flood_desc(engine, self._floor_for_room(engine, player.room_key)) == "none":
                    continue
            if action.id == "escape_boat":
                if player.role != "hero" or flags.get("boat_destroyed"):
                    continue
                room_id = engine._current_room_template_id(player)
                if room_id not in self.ESCAPE_ROOMS:
                    continue
                if not self._boat_here(engine, player):
                    continue
                # p47：不能留下活着的英雄
                if any(p.role == "hero" and not p.dead and p.room_key != player.room_key
                       for p in engine.state.players):
                    continue
            result.append(action)
        return result

    def _boat_here(self, engine: Any, player: Any) -> bool:
        """小艇在本房间：地上、自己扛着、或同房队友扛着。

        give_token 会把令牌的 room_key 清掉，只查 tokens_in_room 会在扛起后
        永远找不到艇，逃生行动从此不再出现。
        """
        if engine.tokens_in_room(player.room_key, self.BOAT):
            return True
        return any(
            not p.dead
            and p.room_key == player.room_key
            and engine.tokens_held_by(p.id, self.BOAT)
            for p in engine.state.players
        )

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        flags = engine._haunt_flags()
        if action_id == "take_rowboat":
            # 艇已经被人扛走：阁楼不再是寻路目标，否则扛艇的人会折回去。
            return flags.get("boat_carrier") is not None or bool(flags.get("boat_destroyed"))
        return False

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """没人扛艇 → 去艇所在房间；扛着的人去阳台/塔楼；其余人去会合。"""
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        if flags.get("boat_destroyed"):
            return []
        escape_keys = [
            f"__room__{key}"
            for key, room in engine.state.board.items()
            if room.template_id in self.ESCAPE_ROOMS
        ]
        carrier_id = flags.get("boat_carrier")
        if carrier_id is None:
            boat = next(iter(engine.tokens_of_kind(self.BOAT)), None)
            if boat is not None and boat.room_key:
                return [f"__room__{boat.room_key}"]
            return ["attic"]
        if player.id == carrier_id:
            return escape_keys or ["balcony", "tower"]
        carrier = next((p for p in engine.state.players if p.id == carrier_id), None)
        if carrier is not None and not carrier.dead:
            return [f"__room__{carrier.room_key}"]
        return escape_keys

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """艇已经到了阳台/塔楼：先在这儿等其余活人到齐，再一起乘艇。"""
        if player.dead or player.role != "hero":
            return False
        if engine._current_room_template_id(player) not in self.ESCAPE_ROOMS:
            return False
        if not self._boat_here(engine, player):
            return False
        return any(
            p.role == "hero" and not p.dead and p.room_key != player.room_key
            for p in engine.state.players
        )

    def on_player_died(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if flags.get("boat_carrier") != player.id:
            return
        token = next(iter(engine.tokens_held_by(player.id, self.BOAT)), None)
        if token is not None and player.room_key:
            engine.place_token(token.uid, player.room_key)
        flags["boat_carrier"] = None
        engine._log("小艇从倒下的人身上滑落到地上。")

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "take_rowboat":
            token = next(iter(engine.tokens_in_room(player.room_key, self.BOAT)), None)
            if token is None or flags.get("boat_destroyed") or flags.get("boat_carrier") is not None:
                engine._log("这里没有小艇（或已有人在背）。")
                return False
            engine.give_token(token.uid, player.id)
            flags["boat_carrier"] = player.id
            engine._log(f"{player.name} 扛起了沉重的小艇。")
            return True

        if action_id == "drop_medallion":
            if "omen_medallion" not in player.items:
                engine._log("你没有勋章。")
                return False
            engine._discard_card_from_player(player, "omen_medallion", return_to_room=False)
            flags["medallion_pause"] = True
            engine._log("勋章在水中闪烁了最后的光芒——洪水暂停了一回合。")
            return True

        if action_id == "escape_boat":
            if flags.get("boat_destroyed"):
                engine._log("小艇已经被毁，无法逃生了。")
                return False
            room_id = engine._current_room_template_id(player)
            if room_id not in self.ESCAPE_ROOMS:
                engine._log("需要在阳台或塔楼才能乘艇逃离。")
                return False
            if not self._boat_here(engine, player):
                engine._log("小艇不在你的房间。")
                return False
            escaped = flags.setdefault("escaped", [])
            escaped.append(player.id)
            engine._log(f"{player.name} 乘着小艇逃出了这栋正在下沉的房子！")
            engine.check_victory()
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 小艇破坏
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        return False  # 无怪物实体

    def perform_traitor_attack_boat(self, engine: Any, traitor: Any) -> bool:
        """p118：叛徒力量 3+ 攻击小艇，5 次毁坏。由引擎攻击流程外部调用。"""
        flags = engine._haunt_flags()
        if flags.get("boat_destroyed"):
            return False
        roll = engine._roll_attack(traitor, "might")
        if roll >= 3:
            engine._advance_haunt_track("boat_damage", 1)
            dmg = engine._haunt_track_value("boat_damage")
            engine._log(f"{traitor.name} 用桨击打小艇（{dmg}/5）。")
            if dmg >= 5:
                flags["boat_destroyed"] = True
                engine._log("小艇散架了——最后的逃生希望破灭了！")
                engine.check_victory()
        else:
            engine._log(f"{traitor.name} 攻击小艇失败（{roll}）。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        import math
        flags = engine._haunt_flags()
        if flags.get("boat_destroyed"):
            engine._set_winner("traitor", "小艇碎了——死亡因有朋友相伴而更甜蜜。")
            return True
        heroes_start = sum(1 for p in engine.state.players if p.role == "hero")
        escaped = len(flags.get("escaped", []))
        need = math.ceil(heroes_start / 2)
        dead = sum(1 for p in engine.state.players if p.role == "hero" and p.dead)
        if escaped >= need:
            engine._set_winner("heroes", "小艇划离了正在下沉的房子——你拒绝了那个邀请。")
            return True
        if dead > heroes_start / 2:
            engine._set_winner("traitor", "朋友们终于都来了——永远地留在了水下。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也沉入了冰冷的水中。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p47/p118 只认"半数英雄乘船逃生"，
        # 叛徒死后沉屋与水鬼照常行动。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
