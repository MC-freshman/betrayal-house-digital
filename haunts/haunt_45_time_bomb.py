"""TimeBombMode（剧本 45）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class TimeBombMode(GenericModeHandler):
    """剧本 45 滴答滴答（Tick, Tick, Tick）。

    权威原文：英雄手册 p56 / 叛徒手册 p127。

    · 每个英雄身上绑了炸弹；拆弹：知识 7+（持疯子卡 5+），每人每回合一次；
      掷出 ≤2 就地引爆，同房所有探险者一起被炸死、物品与预兆全部弃掉（p56）。
    · 叛徒**不能移动**（p127 "You cannot move"），坐在原地拼装大炸弹；开局
      必须握着炸药卡（没有就从持有者手里夺走，或翻物品牌堆取一张）。
    · 大炸弹（p127）：叛徒回合结束推进计时，**第 12 回合完成** → 全屋同归于尽
      （叛徒胜）。其余回合按"轨位 + 存活英雄数"掷骰（上限 8），8+ 时"叛徒
      左手最近、还带着活炸弹"的英雄爆炸，同房其他人一起被炸死。
    · 接近引爆（p127）：叛徒首回合结束后，任何还带着活炸弹的英雄**走进叛徒
      所在房间或其邻室**（邻室不需要有门相连）立即爆炸；炸弹已拆的英雄免疫。
    · 胜负（p56）：叛徒死 + 至少一名英雄存活 → 英雄胜。

    · 已知简化：替队友拆弹（原文允许，需同房并获同意）未建模；炸药卡"只能
      用在叛徒自己房间"的表现层未特殊处理。
    · M10-55 校准：此前计时写在 `drown_timer`（33 号复制而来）而 rule_data
      声明的是另一条轨道，UI 进度条永远不动；大炸弹回合数写 10（原文 12）；
      8+ 爆炸掷骰与接近引爆触发器完全没实现；叛徒可自由移动；拆弹走通用检定，
      于是"掷出 ≤2 引爆"与疯子卡的 5+ 折扣都不生效。
    """

    mode = "time_bomb"
    BIG_BOMB_TURNS = 12  # p127：叛徒第 12 回合完成大炸弹
    DYNAMITE = "item_dynamite"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        has_bomb = flags.setdefault("has_bomb", [])
        flags.setdefault("bomb_defused", [])
        flags["big_bomb_armed"] = False
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                has_bomb.append(str(p.id))
        # p127 Right Now：叛徒开局必须握着炸药卡（没有就从持有者手里夺走，
        # 或翻物品牌堆取一张）——_grant_card_to_player 会把这张卡从牌堆/
        # 弃牌/房间/其他玩家处挪过来。
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            engine._grant_card_to_player(traitor, self.DYNAMITE)
        engine._log("滴答……滴答……每个人身上都绑着一枚炸弹！")

    def _has_bomb(self, engine, player):
        flags = engine._haunt_flags()
        pid = str(getattr(player, "id", ""))
        return pid in flags.get("has_bomb", []) and pid not in flags.get("bomb_defused", [])

    def _has_madman(self, engine, player):
        return "omen_madman" in player.items

    def _defuse_target(self, engine, player):
        return 5 if self._has_madman(engine, player) else 7

    # ------------------------------------------------------------- 移动限制
    def movement_cost_floor(self, engine, player, from_key=None, to_key=None):
        """p127：叛徒不能移动——他坐在原地拼装大炸弹。

        引擎按"入房费用 > 剩余步数就走不了"过滤移动选项，抬高费用下限即可
        把人钉在原地（同 17/36 号的用法，只是这里的值大到无法承担）。
        """
        if getattr(player, "role", None) == "traitor":
            return 99
        return 0

    # ------------------------------------------------------------- 内部
    @staticmethod
    def _adjacent_to(engine, a_key, b_key):
        """同层且曼哈顿距离 ≤1（p127："邻室不需要有门相连"，只看坐标）。"""
        a = engine.state.board.get(a_key)
        b = engine.state.board.get(b_key)
        if a is None or b is None or a.floor != b.floor:
            return False
        return abs(a.x - b.x) + abs(a.y - b.y) <= 1

    def _next_bomb_hero(self, engine, traitor):
        """p127：8+ 时爆炸落在"叛徒左手边最近、还带着活炸弹"的英雄身上。"""
        order = list(engine.state.turn_order or [])
        if not order or traitor.id not in order:
            return None
        idx = order.index(traitor.id)
        for step in range(1, len(order) + 1):
            pid = order[(idx + step) % len(order)]
            other = next((q for q in engine.state.players if q.id == pid), None)
            if other is None or other.dead or other.role != "hero":
                continue
            if self._has_bomb(engine, other):
                return other
        return None

    def _explode_room(self, engine, room_key):
        """p56/p127：炸弹爆炸——房内英雄当场死亡，物品与预兆全部弃掉。"""
        victims = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == room_key
        ]
        if not victims:
            return
        room = engine.state.board.get(room_key)
        engine._log(f"{room.name if room else room_key} 里烈焰翻卷——炸弹炸开了。")
        for victim in victims:
            for card_id in list(victim.items):
                engine._discard_card_from_player(victim, card_id, return_to_room=False)
            victim.dead = True
            engine._log(f"{victim.name} 倒下了。")
            engine._mode_handler().on_player_died(engine, victim)
        engine.check_victory()

    # ------------------------------------------------------------- 回合
    def on_turn_end(self, engine, player):
        """p127：叛徒回合结束——推进计时，再按"轨位 + 存活英雄数"掷骰。

        第 12 回合：大炸弹完成，全屋同归于尽（叛徒胜）。其余回合掷
        min(8, 轨位 + 存活英雄数) 枚骰；8+ 时按"叛徒左手最近"的顺序找还带着
        活炸弹的英雄，他连同同房所有人一起被炸死。
        """
        if player.dead or player.role != "traitor":
            return
        flags = engine._haunt_flags()
        current = int(engine._haunt_track_value("big_bomb_timer")) + 1
        engine._set_haunt_track_value("big_bomb_timer", current)
        # 首回合结束后才武装引爆触发器（p127 "After the end of your first turn"）
        flags["big_bomb_armed"] = True
        if current >= self.BIG_BOMB_TURNS:
            engine._set_winner("traitor", "大炸弹爆炸了——整栋房子被夷为平地。")
            engine.check_victory()
            return
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        dice = max(1, min(8, current + len(heroes)))
        total = engine.roll_dice(dice, "大炸弹计时")
        engine._log(
            f"大炸弹滴答作响（{current}/{self.BIG_BOMB_TURNS}）：掷出 {total}（{dice} 骰）。"
        )
        if total < 8:
            return
        victim = self._next_bomb_hero(engine, player)
        if victim is None:
            return
        engine._log("引信烧到了尽头——炸弹在英雄身上炸开！")
        self._explode_room(engine, victim.room_key)

    # ------------------------------------------------------------- 接近引爆
    def on_enter_room(self, engine, player, room):
        """p127：带活炸弹的英雄踏进叛徒房间或其邻室即引爆（邻室无门也算）。"""
        if not engine._haunt_flags().get("big_bomb_armed"):
            return
        if getattr(player, "role", None) != "hero" or player.dead:
            return
        if not self._has_bomb(engine, player):
            return
        traitor = next(
            (p for p in engine.state.players if p.role == "traitor" and not p.dead), None
        )
        if traitor is None or not self._adjacent_to(engine, room.key, traitor.room_key):
            return
        engine._log(f"{player.name} 踏进了引爆范围——身上的炸弹立刻炸开！")
        self._explode_room(engine, player.room_key)

    # ------------------------------------------------------------- 机器人
    def bot_blocked_rooms(self, engine, player):
        """p127：引爆区＝叛徒所在房间及其邻室——带活炸弹的英雄走进去就是送命。

        炸弹已拆的英雄免疫，不受此限。
        """
        if getattr(player, "role", None) != "hero" or player.dead:
            return []
        if not engine._haunt_flags().get("big_bomb_armed") or not self._has_bomb(engine, player):
            return []
        traitor = next(
            (p for p in engine.state.players if p.role == "traitor" and not p.dead), None
        )
        if traitor is None:
            return []
        blast = [traitor.room_key]
        blast.extend(
            key
            for key in engine.state.board
            if key != traitor.room_key and self._adjacent_to(engine, key, traitor.room_key)
        )
        return blast

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        return [a for a in actions if a.id != "defuse_bomb" or self._has_bomb(engine, player)]

    def perform_action(self, engine, player, action_id, data):
        """p56：拆弹由 handler 自己掷骰。

        通用检定只回一个成功/失败，看不到骰面，而"掷出 ≤2 就地引爆"和疯子卡
        的 5+ 折扣都要看骰面（M10-55 修前两条都不生效）。
        """
        if action_id == "defuse_bomb":
            if not self._has_bomb(engine, player):
                engine._log("你身上没有炸弹（或已拆除）。")
                return False
            target = self._defuse_target(engine, player)
            dice = max(1, min(8, engine._effective_stat(player, "knowledge")))
            total = engine.roll_dice(dice, "拆除炸弹")
            engine._log(f"拆除炸弹：{player.name} 掷出 {total}（{dice} 骰），目标 {target}+。")
            if total <= 2:
                engine._log("剪错了线——炸弹被激活，当场炸开！")
                self._explode_room(engine, player.room_key)
                return True
            if total >= target:
                bomb_defused = engine._haunt_flags().setdefault("bomb_defused", [])
                pid = str(player.id)
                if pid not in bomb_defused:
                    bomb_defused.append(pid)
                engine._log(f"{player.name} 成功拆除了身上的炸弹！")
            return True
        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        traitor_alive = traitor is not None and not traitor.dead
        heroes_alive = any(p.role == "hero" and not p.dead for p in engine.state.players)
        if not traitor_alive and heroes_alive:
            engine._set_winner("heroes", "拆除专家死了——炸弹失去了主人的控制。")
            return True
        if not heroes_alive:
            engine._set_winner("traitor", "Tick, tick, tick... BOOM.")
            return True
        return False
