"""OffspringMode（剧本 18）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class OffspringMode(GenericModeHandler):
    """剧本 18 毒藤子嗣（Offspring）。

    权威原文：英雄手册 p29 / 叛徒手册 p100。

    · 花朵（p29）：英雄在温室/花园/墓地做知识 5+ 发现（find_flower，
      每回合一次），花令牌挂到发现者身上（令牌不可被偷，天然满足）。
    · 削弱（p29）：花被带进毒藤房间后，房内英雄各做知识 5+（每回合
      一次），3-4 人局累计 2 次成功、5-6 人局 3 次成功即杀死毒藤。
    · 孢子（p29/p100）：开局玩家数枚孢子与毒藤同房；叛徒每回合按其他
      玩家数加 2 枚（3-4 人局）或 3 枚（5-6 人局），新增当回合即可移动
      （bot 每枚每回合向最近英雄爬 1 格）。孢子不可被攻击（是令牌）。
    · 孢子伤害（p29）：回合开始处于孢子房间、或移动经过孢子房间，各
      受 1 骰物理伤害（多枚不叠加；盔甲不防——引擎按 source="孢子"
      豁免）。
    · 屏息（p29）：在无孢子房间可用 hold_breath 行动屏息，屏息期间移动
      不受孢子伤害，格数上限=力量（每进一间房递减）；屏息回合结束后
      下一回合不能移动（可行动），若屏息回合结束身处孢子房则受 1 骰。
      原文"回合开始可选屏息"以剧本行动近似，已注明。
    · 毒藤本体放在离持书者最远的房间（p100 "far away from the explorer
      with the Book card" 的 bot 实现）。
    · 胜负：毒藤死 → 英雄胜；英雄全灭 → 叛徒胜。叛徒阵亡不结束游戏
      （毒藤与孢子自主）。
    """

    mode = "poisonous_plant"

    PLANT = "evil_plant"
    SPORE = "spore"
    FLOWER = "flower"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        players = len(engine.state.players)
        # p100：毒藤放在离持书者最远的房间
        book_holder = next((p for p in engine.state.players if "omen_book" in p.items), None)
        origin = book_holder.room_key if book_holder is not None else room_key
        plant_room = max(
            (k for k in engine.state.board if k != origin),
            key=lambda k: (engine._path_length(origin, k), k),
        )
        flags["plant_room"] = plant_room
        engine.spawn_token(self.PLANT, label="邪恶毒藤", role="marker", room_key=plant_room)
        for _ in range(players):
            engine.spawn_token(self.SPORE, label="孢子", role="marker", room_key=plant_room)
        flags["breath_active"] = {}
        flags["catching_breath"] = []
        # 寻花房间必须在场：探索阶段未必翻到温室/花园/墓地，缺了就整局
        # 找不到花（weaken_count 永远 0）。
        if not any(
            room.template_id in ("conservatory", "garden", "graveyard")
            for room in engine.state.board.values()
        ):
            engine._ensure_room_in_play("garden", room_key) or engine._ensure_room_in_play(
                "conservatory", room_key
            ) or engine._ensure_room_in_play("graveyard", room_key)
        engine._log(
            f"一株扭曲的藤蔓盘踞在{engine.state.board[plant_room].name}，"
            f"{players} 团孢子在它周围浮动。"
        )

    # ------------------------------------------------------------- 内部
    def _plant_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("plant_room")

    def _spore_rooms(self, engine: Any) -> set[str]:
        return {t.room_key for t in engine.tokens_of_kind(self.SPORE) if t.room_key}

    def _flower_token(self, engine: Any) -> Any:
        return next(iter(engine.tokens_of_kind(self.FLOWER)), None)

    def _loose_flower_room(self, engine: Any) -> str | None:
        """落在地上（无人携带）的花所在房间。

        持花英雄阵亡时引擎会把携带的令牌落在死亡房间（`_drop_inventory_on_death`），
        但这株花过去**没有任何人捡得回来**：`find_flower` 已被
        `requires_flags={"flower_found": False}` 关掉，`bot_goal_rooms` 又无条件
        指向毒藤房间，于是全场没人踏进那片地——花和胜线一起烂在原地。
        实测 seed3/4p 与 seed31/5p 两局都打满 300 回合收不了场。
        """
        token = self._flower_token(engine)
        if token is not None and token.holder is None and token.room_key:
            return token.room_key
        return None

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """英雄走进散落着花的房间时自动捡起（剧本 1 女孩 / 20 号尸体的同款做法）。"""
        if player.role != "hero" or player.dead:
            return
        if not engine._haunt_flags().get("flower_found"):
            return
        flower = next(iter(engine.tokens_in_room(room.key, self.FLOWER)), None)
        if flower is not None:
            engine.give_token(flower.uid, player.id)
            engine._log(f"{player.name} 捡起了那朵薰衣草色的花。")

    def _in_spores(self, engine: Any, player: Any) -> bool:
        return player.room_key in self._spore_rooms(engine)

    def _spore_damage(self, engine: Any, player: Any) -> None:
        amount = engine.roll_dice(1, "孢子")
        engine._log(f"{player.name} 吸入了孢子（1 骰物理伤害）。")
        engine._deal_damage(player, "physical", amount, source="孢子")
        engine.check_victory()

    def _add_spores(self, engine: Any, count: int) -> None:
        plant_room = self._plant_room(engine)
        if not plant_room:
            return
        for _ in range(count):
            engine.spawn_token(self.SPORE, label="孢子", role="marker", room_key=plant_room)

    def _move_spores(self, engine: Any) -> None:
        """bot：每枚孢子每回合向最近英雄爬 1 格（p100 Speed 4 由叛徒微操）。"""
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return
        for token in engine.tokens_of_kind(self.SPORE):
            if not token.room_key:
                continue
            nearest = min(
                heroes,
                key=lambda p: (engine._path_length(token.room_key, p.room_key), p.id),
            )
            path = engine._shortest_path(token.room_key, nearest.room_key)
            if len(path) > 2:
                engine.place_token(token.uid, path[1])

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.role == "traitor":
            if player.dead:
                return
            # p100：每回合按其他玩家数补充孢子并移动
            others = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)
            self._add_spores(engine, 2 if others <= 3 else 3)
            self._move_spores(engine)
            return
        if player.dead:
            return
        catching = str(player.id) in flags.get("catching_breath", [])
        if catching:
            # p29：屏息后的下一回合不能移动；身处孢子房则受 1 骰
            player.movement_stopped = True
            flags["catching_breath"] = [
                pid for pid in flags.get("catching_breath", []) if pid != str(player.id)
            ]
            if self._in_spores(engine, player):
                self._spore_damage(engine, player)
            return
        if self._in_spores(engine, player) and str(player.id) not in flags.get("breath_active", {}):
            self._spore_damage(engine, player)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.dead or player.role != "hero":
            return
        breath = flags.get("breath_active", {})
        pid = str(player.id)
        if pid in breath:
            # 屏息中：不受孢子伤害，每进一间房消耗 1 格屏息
            breath[pid] = int(breath[pid]) - 1
            if breath[pid] <= 0:
                breath.pop(pid, None)
                flags["catching_breath"] = sorted(set(flags.get("catching_breath", [])) | {pid})
            engine._haunt_flags()["breath_active"] = breath
            return
        if self._in_spores(engine, player):
            self._spore_damage(engine, player)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        plant_room = self._plant_room(engine)
        flower_carried_here = any(
            other.role == "hero" and not other.dead
            and other.room_key == player.room_key
            and engine.tokens_held_by(other.id, self.FLOWER)
            for other in engine.state.players
        )
        for action in actions:
            if action.id == "weaken_plant":
                if player.room_key != plant_room or not flower_carried_here:
                    continue  # 花必须被带进毒藤房间
            if action.id == "hold_breath":
                if player.role != "hero" or self._in_spores(engine, player):
                    continue  # p29：在无孢子房间才能屏息
                if str(player.id) in engine._haunt_flags().get("breath_active", {}):
                    continue  # 已经在屏息，不必再点一次
            result.append(action)
        return result

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """屏息：只在"接下来真要穿过孢子房"时才值得点（p29）。

        过去一律禁掉（理由见下：机器人每回合先点它，把唯一的剧本行动浪费在
        非推进上——seed113/3p 实测屏息 359 次、削弱 0/3）。但本剧本的孢子是
        核心威胁，一味硬吃伤害英雄会被磨死。折中：只有当"去目标的路"真的
        要穿过孢子房时才允许屏息，其余时候照旧禁掉。

        真人玩家不受影响（本钩子只过滤机器人）。
        """
        if action_id != "hold_breath":
            return False
        if self._in_spores(engine, player):
            return True  # 房间里就有孢子，屏不了（available_actions 也会挡）
        flags = engine._haunt_flags()
        targets: list[str] = []
        if flags.get("flower_found"):
            plant = flags.get("plant_room")
            if plant:
                targets.append(plant)
        else:
            targets.extend(
                key for key, room in engine.state.board.items()
                if room.template_id in ("conservatory", "garden", "graveyard")
            )
        spore_rooms = self._spore_rooms(engine)
        for target in targets:
            if target == player.room_key:
                continue
            path = engine._shortest_path(player.room_key, target)
            if any(step in spore_rooms for step in path[1:]):
                return False  # 这条路要穿过孢子房 → 值得屏息
        return True

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """没找到花就去温室/花园/墓地；找到了就把花带进毒藤房间削弱。

        花落在地上时（持花者阵亡）**先去捡花**——否则全员继续往毒藤房间挤，
        那朵花永远不会被带回战场（实测 seed3/4p / seed31/5p 两局 300 回合僵局）。
        """
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        if flags.get("flower_found"):
            loose = self._loose_flower_room(engine)
            if loose:
                return [f"__room__{loose}"]
            plant = flags.get("plant_room")
            return [f"__room__{plant}"] if plant else []
        return [
            f"__room__{key}"
            for key, room in engine.state.board.items()
            if room.template_id in ("conservatory", "garden", "graveyard")
        ]

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "find_flower":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("flower_found"):
                engine.spawn_token(self.FLOWER, label="花朵", role="carried", holder=player.id)
                engine._log(f"{player.name} 找到了那朵薰衣草色的花——把它带去毒藤那里！")
            return ok
        if action_id == "weaken_plant":
            plant_room = self._plant_room(engine)
            flower_here = any(
                other.role == "hero" and not other.dead
                and other.room_key == player.room_key
                and engine.tokens_held_by(other.id, self.FLOWER)
                for other in engine.state.players
            )
            if player.room_key != plant_room or not flower_here:
                engine._log("需要有人带着花朵进入毒藤的房间才能削弱它。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                engine.spawn_token("knowledge_check", label="削弱成功", role="check", room_key=player.room_key)
                flags["weaken_count"] = int(flags.get("weaken_count", 0)) + 1
                needed = 2 if len(engine.state.players) <= 4 else 3
                if int(flags["weaken_count"]) >= needed:
                    flags["plant_killed"] = True
            return ok
        if action_id == "hold_breath":
            if self._in_spores(engine, player):
                engine._log("身处孢子之中，来不及屏住呼吸了。")
                return False
            breath = flags.setdefault("breath_active", {})
            breath[str(player.id)] = max(1, int(player.stats.get("might", 1)))
            engine._log(f"{player.name} 深吸一口气屏住了呼吸（{breath[str(player.id)]} 格）。")
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        needed = 2 if len(engine.state.players) <= 4 else 3
        if int(flags.get("weaken_count", 0)) >= needed or flags.get("plant_killed"):
            engine._set_winner("heroes", "毒藤在血红色的树液中燃烧殆尽——胜利并不总是香甜的。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "孢子铺满了房子，藤蔓有了新的肥料。")
            return True
        return True  # 毒藤自主扩散，叛徒阵亡不结束游戏
