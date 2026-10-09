"""TentacledHorrorMode（剧本 23）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    _is_last_in_round,
    _monster_id,
)
from .haunt_07_carnivorous_ivy import CarnivorousIvyMode  # noqa: F401  继承自其他具体 handler


class TentacledHorrorMode(CarnivorousIvyMode):
    """剧本 23 触手恐怖（Tentacled Horror）。

    权威原文：英雄手册 p34 / 叛徒手册 p105。

    复用剧本 7 的爬行藤机器（根令牌 + 尖端怪物配对、抓住不掉血改拖走、
    拖向根部、到根即吞噬、尖端进神秘电梯则电梯停用），本剧本按原文改动的部分：

    · 叛徒开局即死并移出对局（p105 "Your explorer is dead. Remove it from the
      game"）；成长时钟与怪物回合由"本轮最后一名存活玩家"代跑（同 6/10/21 惯例）。
    · 根/尖端对数 = 玩家数，只能落在 熔炉房/温室/风琴房/地下湖/花园/裂隙，
      在场不足就从房间牌堆里找出来补上（p105 "You cannot save any tentacles
      for later"），所以本剧本不再在后续发现房间时补藤。
    · 触手按 p105 成长表变强：回合 0 → 2/3/6，1-2 → 2/4/7，3-4 → 3/5/7，
      5-7 → 3/7/7，8+ → 4/8/8（每只尖端在自己回合开始时刷新）。
    · 抓着人的尖端每回合只挪 1 格（7 号是 2 格），且携带人质时不能攻击。
    · 尖端被任何攻击击败 → 缩回到配对的根所在房间并昏迷（7 号留在原地）。
    · 被抓者下个回合开始必须与缠着自己的尖端打一场力量对决（p34）：打赢即获释，
      但本回合之后每进一间房按 2 格计；打输或平手不掉血，本回合直接结束。
    · 头颅（p34）：持水晶球者知识 4+ 凝视成功 → 掷 4 骰查表定头位
      （0 储藏室 / 1 厨房 / 2 风琴房 / 3 裂隙 / 4-5 地下湖 / 6 温室 / 7 地窖 /
      8 熔炉房），球随即碎裂；该房未入场就从牌堆找出来放到合法楼层。
      走进头位房间、持炸药或长矛攻击 → 不掷骰自动杀死怪物（且不吃炸药反噬）。
    · 胜负：摧毁头颅 → 英雄胜；英雄全灭 → 叛徒胜。叛徒开局就死，
      必须吸收引擎"叛徒死亡即英雄胜"的兜底（老坑第 13 次）。

    已知简化：
        · p105「铃铛对被抓者无效、灵应板对尖端无效」属物品交互边界，未接（同 7 号）。
        · 被抓者的开局对决由引擎自动掷骰，原版是玩家在自己回合开始时主动攻击——
          结果等价，但人类玩家失去"先做别的再打"的选择权。
        · 头颅房间的接入口由引擎按 `_ensure_room_in_play` 选位，原版由叛徒任选
          一个未探索门口（楼层合法即可）。
        · p105「尖端用力量攻击击败英雄时不造成伤害，改为抓住」只在尖端的主动攻击
          里生效；英雄主动攻击尖端却落败时的反击伤害是引擎全局规则，本剧本未做
          例外（与 7 号同源的同一条简化）。
    """

    mode = "tentacled_horror"

    ROOM_IDS = ["furnace_room", "conservatory", "organ_room", "underground_lake", "garden", "chasm"]
    # p34：掷 4 骰（0-8）→ 头颅所在房间模板
    HEAD_TABLE = (
        "larder", "kitchen", "organ_room", "chasm",
        "underground_lake", "underground_lake", "conservatory", "crypt", "furnace_room",
    )
    # p105 成长表：(回合上限, 速度, 力量, 理智)
    GROWTH = ((0, 2, 3, 6), (2, 2, 4, 7), (4, 3, 5, 7), (7, 3, 7, 7), (99, 4, 8, 8))
    GAZE_ACTION = "gaze_crystal_ball"
    KILL_ACTION = "destroy_head"
    HEAD_WEAPONS = ("item_dynamite", "omen_spear")
    CRYSTAL_BALL = "omen_crystal_ball"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}被卷进了墙里——回应她的只剩下咀嚼声。")
        flags = engine._haunt_flags()
        flags.setdefault("grabbed", {})
        spec = self._tip_spec(engine)
        players = len(engine.state.players)
        placed = 0
        for template_id in self.ROOM_IDS:
            if placed >= players:
                break
            key = engine._ensure_room_in_play(template_id, room_key)
            if not key or engine.tokens_in_room(key, "root"):
                continue
            tip = engine._spawn_single_haunt_monster(spec, key)
            if tip is None:
                continue
            root = engine.spawn_token("root", label="触手之根", role="marker", room_key=key)
            root.data["tip_id"] = tip.id
            placed += 1
        flags["pairs_placed"] = placed
        engine._log(f"{placed} 条触手从墙里探出来，每一条都连着自己的根。")

    CRYSTAL_BALL_OMEN = "omen_crystal_ball"

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """水晶球还压在预兆牌堆里时，英雄必须继续探索去把它抽出来。

        p34：只有持水晶球做知识 4+ 才能定位头颅，而水晶球只能靠正常抽预兆牌
        入手（原文没有搜牌堆条款）。缺了这条，英雄会在触手房里站到天荒地老
        ——头颅永不露面，`creature_destroyed` 永远是 False。任何英雄拿到都能
        凝视，所以对全体英雄放行。
        """
        if player.dead or player.role != "hero":
            return False
        if engine._haunt_flags().get("head_found"):
            return False
        if any(
            self.CRYSTAL_BALL_OMEN in p.items
            for p in engine.state.players
            if not p.dead
        ):
            return False
        if any(
            self.CRYSTAL_BALL_OMEN in items
            for items in engine.state.room_items.values()
        ):
            return False
        return self.CRYSTAL_BALL_OMEN in engine.state.card_decks.get("omen", [])

    def _tip_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.CREEPER_TEMPLATE) or {"template_id": self.CREEPER_TEMPLATE, "name": "触手尖端"})

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        return None  # p105：所有触手开局就全部入场，不留备用

    # ------------------------------------------------------------- 成长
    def _growth_stats(self, turn: int) -> tuple[int, int, int]:
        for upper, speed, might, sanity in self.GROWTH:
            if turn <= upper:
                return speed, might, sanity
        return 4, 8, 8

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        speed, might, sanity = self._growth_stats(engine._haunt_track_value("tentacle_turn"))
        monster.speed, monster.might, monster.sanity = speed, might, sanity
        # p105：本剧本抓着人的尖端每回合只挪 1 格（7 号是 2 格）。父类的吞噬钩子
        # 会补拖拽——引擎在"怪已与猎物同房"时不调 on_monster_move，抓人的尖端却
        # 总与猎物同房；这里先按本剧本的幅度处理掉，父类再管吞噬。
        victim = self._grabbed_by(engine, monster)
        root = self._root_for_tip(engine, monster)
        if victim is not None and root is not None and victim.room_key != root.room_key:
            path = engine._shortest_path(monster.room_key, root.room_key)
            if len(path) > 1:
                dest = path[1]
                monster.room_key = dest
                victim.room_key = dest
                engine._log(f"触手拖着{victim.name}往根部缩，来到{engine.state.board[dest].name}。")
                return True
        return super().on_monster_turn_start(engine, monster)

    # ------------------------------------------------------------- 拖拽
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """p105：抓人的尖端每回合只朝配对的根挪 1 格（7 号是 2 格）。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        carried = self._grabbed_by(engine, monster)
        if carried is None:
            return False
        root = self._root_for_tip(engine, monster)
        if root is None or monster.room_key == root.room_key:
            return True
        path = engine._shortest_path(monster.room_key, root.room_key)
        if len(path) <= 1:
            return True
        dest = path[1]
        monster.room_key = dest
        carried.room_key = dest
        engine._log(f"触手拖着{carried.name}往根部缩，来到{engine.state.board[dest].name}。")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p105：尖端被击败 → 松手（人质摔在原地）、缩回配对的根、翻成昏迷面。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        carried = self._grabbed_by(engine, monster)
        if carried is not None:
            self._ungrab(engine, carried)
            carried.movement_stopped = False
            engine._log(f"触手断了，{carried.name}摔在原地——他自由了。")
        root = self._root_for_tip(engine, monster)
        if root is not None and monster.room_key != root.room_key:
            monster.room_key = root.room_key
            engine._log(f"{monster.name}缩回了它的根部。")
        return False  # 引擎默认击晕一回合 = 翻成昏迷面

    def item_pickup_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        return False  # 7 号的"叛徒不能重拾古书"是常春藤专属，本剧本没有

    # ------------------------------------------------------- 被抓者的开局对决
    def on_turn_start(self, engine: Any, player: Any) -> None:
        grabbed = engine._haunt_flags().get("grabbed", {})
        tip_id = str(grabbed.get(str(player.id), ""))
        if not tip_id:
            return
        if player.dead:
            self._ungrab(engine, player)
            return
        tip = next((m for m in engine.state.monsters if str(getattr(m, "id", "")) == tip_id), None)
        if tip is None:
            self._ungrab(engine, player)
            player.movement_stopped = False
            return
        player_roll = engine._roll_attack(player, "might")
        tip_roll = engine._roll_monster_attack(tip, "might")
        engine._log(f"{player.name} 开局劈向缠住自己的触手：{player_roll} 对 {tip_roll}。")
        if player_roll > tip_roll:
            self._ungrab(engine, player)
            player.movement_stopped = False
            flags = engine._haunt_flags()
            escaped = set(flags.get("escaped_ids", []) or [])
            escaped.add(player.id)
            flags["escaped_ids"] = sorted(escaped)
            engine._log(f"{player.name}挣脱了，但一身伤——本回合每进一间房都算两格。")
            return
        player.movement_stopped = True
        player.steps_remaining = 0
        player.attack_used = True
        player.item_used = True
        engine._log(f"{player.name}没能挣脱（不掉血），这个回合就这么到头了。")

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """p34：挣脱后的剩余回合里，每进一间房按 2 格计。"""
        if player.id in set(engine._haunt_flags().get("escaped_ids", []) or []):
            return 2
        return 1

    def on_turn_end(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        flags["escaped_ids"] = [pid for pid in (flags.get("escaped_ids", []) or []) if int(pid) != player.id]
        if _is_last_in_round(engine, player):
            engine._advance_haunt_track("tentacle_turn", 1)

    def _is_round_last(self, engine: Any, player: Any) -> bool:
        """叛徒已出局：成长时钟由本轮最后一名存活玩家代跑（同怪物回合惯例）。"""
        return _is_last_in_round(engine, player)

    # ------------------------------------------------------------- 头颅
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        return [
            action for action in actions
            if action.id != self.KILL_ACTION or self._can_destroy_head(engine, player)
        ]

    def _can_destroy_head(self, engine: Any, player: Any) -> bool:
        head = engine._haunt_flags().get("head_room")
        return bool(head) and player.room_key == head and any(w in player.items for w in self.HEAD_WEAPONS)

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p105 英雄胜线：拿着炸药/长矛的人要走到那颗头所在的房间才能斩首。

        斩首只在同房间可用（`_can_destroy_head`），而头颅定位成功后头颅房
        可能离得很远。不给目标房间时，机器人只会按"最近怪物"追触手——
        18 局实测 `destroy_head` 一次都没发生（英雄 0 胜）。
        """
        if player.dead or player.role != "hero":
            return []
        head = engine._haunt_flags().get("head_room")
        if head and any(weapon in player.items for weapon in self.HEAD_WEAPONS):
            return [f"__room__{head}"]
        return []

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == self.GAZE_ACTION:
            return self._gaze(engine, player, action_id, data)
        if action_id == self.KILL_ACTION:
            return self._destroy_head(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _gaze(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if not super().perform_action(engine, player, action_id, data):
            return False
        engine._discard_card_from_player(player, self.CRYSTAL_BALL, return_to_room=False)
        flags = engine._haunt_flags()
        flags["head_found"] = True
        roll = engine.roll_dice(4, "头颅定位")
        template_id = self.HEAD_TABLE[min(roll, len(self.HEAD_TABLE) - 1)]
        key = engine._ensure_room_in_play(template_id, player.room_key)
        flags["head_room"] = key
        room = engine.state.board.get(key or "")
        engine._log(f"水晶球炸成碎片，碎屑重新聚拢——那颗头在 {room.name if room else template_id}。")
        return True

    def _destroy_head(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        head = flags.get("head_room")
        if not head or head not in engine.state.board:
            engine._log("你还不知道那颗头在哪里。")
            return False
        if player.room_key != head:
            engine._log("你得先走进那颗头所在的房间。")
            return False
        weapon = next((w for w in self.HEAD_WEAPONS if w in player.items), "")
        if not weapon:
            engine._log("只有炸药或长矛能一击摧毁它。")
            return False
        if weapon == "item_dynamite":
            engine._discard_card_from_player(player, weapon, return_to_room=False)
        flags["creature_destroyed"] = True
        grabbed = flags.get("grabbed", {})
        for pid in list(grabbed):
            victim = next((p for p in engine.state.players if str(p.id) == str(pid)), None)
            if victim is not None:
                victim.movement_stopped = False
        flags["grabbed"] = {}
        engine.state.monsters = []
        for token in engine.tokens_of_kind("root"):
            engine.remove_token(token.uid)
        engine._log("你把武器送进那颗头里——它没有挣扎，整栋房子都跟着震了一下。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_flags().get("creature_destroyed"):
            engine._set_winner("heroes", "那颗头终于不再动了，垂着的触手一条接一条软了下去。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一名探险者也成了某条触手的食物。")
            return True
        return True  # 叛徒开局即死：吸收引擎兜底
