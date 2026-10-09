"""StarsRightMode（剧本 14）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    OPPOSITE_DOOR,
    _monster_id,
)


class StarsRightMode(GenericModeHandler):
    """剧本 14 星辰归位（The Stars Are Right）。

    权威原文：英雄手册 p25 / 叛徒手册 p96。

    · 油漆罐（Paint，数量 = 玩家数，p25）：按序放厨房/储藏室/杂物间/
      研究实验室/阁楼（原版 Storeroom 与 Larder 共用）；罐比房多则同房
      叠放；全不在场则从
      牌堆补第一间。英雄一次只能背一罐；从与五芒星室有门相连的相邻
      房间把罐扔进去（原版耗 1 格移动，电子版占用剧本行动）；所有罐
      入室即亵渎胜利。五芒星室用 _ensure_room_in_play 保证在场。
    · 狂信徒（4/4/4，p96）：数量 = 其他玩家数，生成于五芒星室；普通
      力量攻击；掷出高出 2+ 可改为偷窃（bot 自动偷第一件可交易物品）。
    · 尸体（p96）：探险者死亡即落尸（引擎新钩子 on_player_died）；
      叛徒可背尸（take_corpse，背尸者入房按 2 格移动——引擎新钩子
      movement_cost_multiplier），把尸体带进五芒星室献祭 +4 分。
    · 献祭（p96）：叛徒在五芒星室每次献上一件——尸体 4 分 / 狗·女孩·
      疯子卡 2 分 / 其他预兆或物品 1 分；累计 13 分召唤邪神胜利；被
      献祭物品进弃牌堆近似"移出游戏"。
    · 英雄胜：所有油漆罐入室；叛徒胜：献祭满 13 分或英雄全灭；
      叛徒阵亡不结束游戏（狂信徒自主行动，同 7/8 惯例）。
    · 已知简化：扔罐"1 格移动"与背尸"2 格移动"对英雄占剧本行动、对
      叛徒为移动加倍近似；狂信徒搬尸的 bot 后勤未实现（只有叛徒行动
      可搬尸）；狂信徒偷窃为 bot 自动，人类叛徒弹窗留待接 prompter。
    """

    mode = "paint_the_pentagram"

    PAINT = "paint"
    CORPSE = "corpse"
    # 原版序列中的 Storeroom 与 Larder 在本项目共用 larder，故为五间
    PAINT_ROOMS = ["kitchen", "larder", "junk_room", "research_laboratory", "attic"]
    PENTAGRAM = "pentagram_chamber"
    SPECIAL_OMENS = ("omen_girl", "omen_madman", "omen_dog")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        engine._ensure_room_in_play(self.PENTAGRAM, room_key)
        pentagram_key = next(
            (k for k, r in engine.state.board.items() if r.template_id == self.PENTAGRAM),
            room_key,
        )
        flags["pentagram_room"] = pentagram_key
        # p25：油漆罐按序放六房间，罐比房多则同房叠放
        available = [
            rid for rid in self.PAINT_ROOMS
            if any(r.template_id == rid for r in engine.state.board.values())
        ]
        if not available:
            if engine._ensure_room_in_play(self.PAINT_ROOMS[0], room_key):
                available = [self.PAINT_ROOMS[0]]
        players = len(engine.state.players)
        total = 0
        for index in range(players):
            if not available:
                break
            rid = available[index % len(available)]
            key = next(k for k, r in engine.state.board.items() if r.template_id == rid)
            engine.spawn_token(self.PAINT, label="油漆罐", role="marker", room_key=key)
            total += 1
        flags["total_cans"] = total
        # p96：狂信徒数量 = 其他玩家数
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "cultist"),
            {},
        )
        for _ in range(max(0, players - 1)):
            engine._spawn_single_haunt_monster(spec, pentagram_key)
        engine._log(f"{total} 罐油漆散落在老房子的各个角落；五芒星室里，狂信徒的吟唱越来越响。")

    # ------------------------------------------------------------- 内部
    def _pentagram_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("pentagram_room") or next(
            (k for k, r in engine.state.board.items() if r.template_id == self.PENTAGRAM),
            None,
        )

    def _corpse_carriers(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("corpse_carrier", {})

    def _door_adjacent(self, engine: Any, key_a: str, key_b: str) -> bool:
        """两房间是否同层、几何相邻且有互相连接的门（p25 扔罐要求）。"""
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor:
            return False
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy) and direction in a.doors and OPPOSITE_DOOR[direction] in b.doors:
                return True
        return False

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p25/p96 的后勤：背罐去五芒星室隔壁扔，背尸去五芒星室献祭。

        两个行动都没有 rooms 字段，静态表表达不了"罐/尸现在在哪、扔罐要站在
        哪"，机器人只剩 key_rooms 保底（五芒星室 + 四间油漆房）——到达一间后
        重挑"最近"的下一间，于是永远在油漆房之间来回（seed137/5p 实测
        厨房×88 / 储藏室×87、往返 172 步、整局拖到 127 回合）。
        """
        if player.dead:
            return []
        pentagram = self._pentagram_room(engine)
        if player.role == "hero":
            if engine.tokens_held_by(player.id, self.PAINT):
                if not pentagram:
                    return []
                # 背着罐：去与五芒星室有门相连的房间，到了就能扔（p25）
                return [
                    f"__room__{key}"
                    for key in sorted(engine.state.board)
                    if self._door_adjacent(engine, key, pentagram)
                ]
            # 空手：去还有罐的房间捡一罐（一次只能背一罐）
            return [
                f"__room__{token.room_key}"
                for token in engine.tokens_of_kind(self.PAINT)
                if token.room_key
            ]
        # 叛徒：背着尸体先去五芒星室献祭（4 分）；否则去有尸体的房间搬尸；
        # 都没有时不给目标，走通用追击逻辑去打英雄（尸体由击杀产生）。
        if engine.tokens_held_by(player.id, self.CORPSE):
            return [f"__room__{pentagram}"] if pentagram else []
        return [
            f"__room__{token.room_key}"
            for token in engine.tokens_of_kind(self.CORPSE)
            if token.room_key
        ]

    # ------------------------------------------------------------- 尸体
    def on_player_died(self, engine: Any, player: Any) -> None:
        if player.role != "hero":
            return
        engine.spawn_token(
            self.CORPSE, label=f"{player.name}的尸体", role="marker", room_key=player.room_key
        )
        engine._log(f"{player.name}的尸体倒在了{engine.state.board[player.room_key].name}。")

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """p96：背着尸体入房按 2 格移动计。"""
        if str(getattr(player, "id", "")) in self._corpse_carriers(engine):
            return 2
        return 1

    # ------------------------------------------------------------- 攻击
    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """p96：狂信徒掷出高出 2+ 时可改为偷窃（bot 自动偷第一件）。"""
        if _monster_id(monster) != "cultist" or amount < 2:
            return False
        candidates = [
            card_id for card_id in target.items
            if engine.catalog.cards[card_id].tradeable
        ]
        if not candidates:
            return False
        picked = candidates[0]
        target.items.remove(picked)
        monster.items.append(picked)
        card = engine.catalog.cards[picked]
        engine._log(f"狂信徒从 {target.name} 身上抢走了{card.name}！")
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        pentagram_key = self._pentagram_room(engine)
        for action in actions:
            if action.id == "take_paint":
                if player.role != "hero" or engine.tokens_held_by(player.id, self.PAINT):
                    continue  # 一次只能背一罐
                if not engine.tokens_in_room(player.room_key, self.PAINT):
                    continue
            if action.id == "throw_paint":
                if player.role != "hero" or not engine.tokens_held_by(player.id, self.PAINT):
                    continue
                if not pentagram_key or not self._door_adjacent(engine, player.room_key, pentagram_key):
                    continue
            if action.id == "take_corpse":
                if player.role != "traitor" or str(player.id) in self._corpse_carriers(engine):
                    continue
                if not engine.tokens_in_room(player.room_key, self.CORPSE):
                    continue
            if action.id == "sacrifice":
                if player.role != "traitor" or player.room_key != pentagram_key:
                    continue
                if not self._sacrifice_available(engine, player):
                    continue
            result.append(action)
        return result

    def _sacrifice_available(self, engine: Any, player: Any) -> bool:
        if engine.tokens_held_by(player.id, self.CORPSE):
            return True
        return any(card_id in player.items for card_id in engine.catalog.cards)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        pentagram_key = self._pentagram_room(engine)
        if action_id == "take_paint":
            token = next(iter(engine.tokens_in_room(player.room_key, self.PAINT)), None)
            if token is None or engine.tokens_held_by(player.id, self.PAINT):
                engine._log("这里没有可拿的油漆罐（或你已背着一罐）。")
                return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 抱起了一罐油漆。")
            return True

        if action_id == "throw_paint":
            held = engine.tokens_held_by(player.id, self.PAINT)
            if not held or not pentagram_key or not self._door_adjacent(engine, player.room_key, pentagram_key):
                engine._log("要站在与五芒星室门相连的相邻房间才能扔罐。")
                return False
            engine.place_token(held[0].uid, pentagram_key)
            engine._advance_haunt_track("desecration", 1)
            engine._log(
                f"{player.name} 把油漆泼进了五芒星室！"
                f"（{engine._haunt_track_value('desecration')}/{engine._haunt_track_target('desecration')}）"
            )
            engine.check_victory()
            return True

        if action_id == "take_corpse":
            token = next(iter(engine.tokens_in_room(player.room_key, self.CORPSE)), None)
            if token is None or str(player.id) in self._corpse_carriers(engine):
                engine._log("这里没有尸体可背（或你已背着一具）。")
                return False
            engine.give_token(token.uid, player.id)
            self._corpse_carriers(engine)[str(player.id)] = token.uid
            engine._log(f"{player.name} 吃力地背起了一具尸体。")
            return True

        if action_id == "sacrifice":
            if player.room_key != pentagram_key:
                engine._log("献祭必须在五芒星室进行。")
                return False
            corpse = next(iter(engine.tokens_held_by(player.id, self.CORPSE)), None)
            if corpse is not None:
                engine.remove_token(corpse.uid)
                self._corpse_carriers(engine).pop(str(player.id), None)
                engine._advance_haunt_track("sacrifice_points", 4)
                engine._log("一具探险者的尸体被献上了祭坛（4 点）。")
                engine.check_victory()
                return True
            special = next((c for c in player.items if c in self.SPECIAL_OMENS), None)
            if special is not None:
                engine._discard_card_from_player(player, special, return_to_room=False)
                engine._advance_haunt_track("sacrifice_points", 2)
                engine._log("一件特殊的预兆被献上了祭坛（2 点）。")
                engine.check_victory()
                return True
            other = next((c for c in player.items), None)
            if other is not None:
                engine._discard_card_from_player(player, other, return_to_room=False)
                engine._advance_haunt_track("sacrifice_points", 1)
                engine._log("一件物品被献上了祭坛（1 点）。")
                engine.check_victory()
                return True
            engine._log("你身上没有可献祭的东西（尸体要先用背尸行动搬进来）。")
            return False

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if int(flags.get("total_cans", 0)) > 0 and engine._haunt_track_value("desecration") >= int(flags["total_cans"]):
            engine._set_winner("heroes", "法阵被油漆彻底毁了——邪神的召唤被打断，世界暂时安全。")
            return True
        if engine._haunt_track_value("sacrifice_points") >= engine._haunt_track_target("sacrifice_points"):
            engine._set_winner("traitor", "血祭已足——时空裂开，邪神在朋友们的血中重生。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "英雄们的尸体成了祭坛上的贡品。")
            return True
        return True  # 叛徒阵亡不结束游戏（狂信徒自主行动）
