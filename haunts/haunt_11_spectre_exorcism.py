"""SpecterInvasionMode（剧本 11）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    _monster_id,
)
from .haunt_08_exorcism import ExorcismMode  # noqa: F401  继承自其他具体 handler


class SpecterInvasionMode(ExorcismMode):
    """剧本 11 放他们进来（Let Them In）。

    权威原文：英雄手册 p22 / 叛徒手册 p93。

    复用剧本 8 的驱魔底座（八来源一次性、成功放检定令牌、满玩家人数即
    全部放逐），但理智物品来源用**戒指**替换灵应板（p22）。本次新增：

    · 雾中人影（Specter）：背面朝下待命于门厅 + 五个朝外窗房间
      （大楼梯/主卧/卧室/教堂/餐厅，p93）；后发现的窗房间补放
      （on_room_discovered）。用 ghost 模板承载，数值由规则表覆盖
      （Speed 4 / Sanity 6），免疫力量/速度攻击（p22 "can't be attacked
      physically"）。
    · 疯子（Speed 7 / Might 7 / Sanity 7，p93）：开局顶替在叛徒房间；
      每回合自动走向最近的背面人影并开窗放入（放入当回合即可移动与
      攻击）；全部放入前不攻击（可自卫），之后按常规怪物行动。
    · 持戒指者对雾中人影的徒手攻击改为理智攻击（attack_attr_override
      钩子），击败即放逐；只有持戒指者能攻击人影（attack_allowed）；
      人影攻击英雄落败时照常被击晕（p22 "If you defeat a Specter when
      it attacks you, the Specter is stunned"）。
    · 叛徒也可亲自开窗（open_window 剧本行动；原版开窗耗 1 格移动，
      电子版近似为占用剧本行动）。
    · 英雄胜：驱魔满员，或"放入数 = 放逐数且无背面人影"（p22 "banish
      all the Specters"）；叛徒胜：英雄全灭。叛徒阵亡不结束游戏
      （疯子与人影自主行动，同 7/8 惯例）。
    · 已知简化：窗户"假窗"（被邻室挡住即失效、失效则移除背面人影）
      不建模；铃铛/灵应板对背面人影无效属物品交互边界，未接；叛徒
      "失去疯子加成"是纯卡牌文本，未建模。
    """

    mode = "spectre_exorcism"

    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_ring"]
    ALL_SOURCES = (
        ExorcismMode.SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + ExorcismMode.KNOWLEDGE_ROOM_SOURCES + ExorcismMode.KNOWLEDGE_ITEM_SOURCES
    )
    SPECTER = "ghost"   # 雾中人影用 ghost 模板承载，数值由规则表覆盖
    MADMAN = "madman"
    WINDOW_ROOMS = ["grand_staircase", "master_bedroom", "bedroom", "chapel", "dining_room"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("used_exorcism_sources", [])
        flags["specters_activated"] = 0
        flags["specters_banished"] = 0
        # p93：门厅 + 朝外窗房间放背面人影（房间已在场才放）
        for template_id in ["entrance_hall", *self.WINDOW_ROOMS]:
            key = next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key and not engine.tokens_in_room(key, "specter"):
                engine.spawn_token("specter", label="雾中人影", role="marker", room_key=key, face_up=False)
        # p93：疯子令牌放在叛徒房间，疯子怪物在此生成
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine.spawn_token("madman", label="疯子", role="marker", room_key=traitor.room_key)
            spec = next(
                (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.MADMAN),
                {},
            )
            if engine._spawn_single_haunt_monster(spec, traitor.room_key) is not None:
                engine._log(f"疯子在{engine.state.board[traitor.room_key].name}推开了一扇窗。")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        # p93：后发现的朝外窗房间补放背面人影
        if room.template_id in self.WINDOW_ROOMS and not engine.tokens_in_room(room.key, "specter"):
            engine.spawn_token("specter", label="雾中人影", role="marker", room_key=room.key, face_up=False)
            engine._log(f"{room.name}的窗外，雾里浮出了一个人影。")

    # ------------------------------------------------------------- 内部
    def _facedown_rooms(self, engine: Any) -> list[str]:
        return [t.room_key for t in engine.tokens_of_kind("specter") if not t.face_up and t.room_key]

    def _release_specter(self, engine: Any, room_key: str) -> bool:
        token = next(
            (t for t in engine.tokens_in_room(room_key, "specter") if not t.face_up),
            None,
        )
        if token is None:
            return False
        engine.flip_token(token.uid, True)
        spec = next(
            (
                s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
                if s.get("template_id") == self.SPECTER
            ),
            {},
        )
        monster = engine._spawn_single_haunt_monster(spec, room_key)
        if monster is None:
            return False
        flags = engine._haunt_flags()
        flags["specters_activated"] = int(flags.get("specters_activated", 0)) + 1
        engine._log(f"{engine.state.board[room_key].name}的窗被推开了——雾中人影涌了进来！")
        self._specter_turn(engine, monster)  # p93：放入当回合即可移动与攻击
        return True

    def _specter_turn(self, engine: Any, monster: Any) -> None:
        target = engine._find_monster_target(monster)
        if target is None:
            return
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 4), "雾中人影移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"雾中人影飘进了{engine.state.board[monster.room_key].name}。")
        if monster.room_key == target.room_key:
            self._specter_attack(engine, monster)

    def _specter_attack(self, engine: Any, monster: Any) -> bool:
        victims = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return True
        victim = victims[0]
        specter_roll = engine._roll_monster_attack(monster, "sanity")
        hero_roll = engine._roll_attack(victim, "sanity")
        engine._log(f"雾中人影的哀嚎穿透{victim.name}：{specter_roll} 对 {hero_roll}。")
        if specter_roll > hero_roll:
            engine._deal_damage(victim, "mental", specter_roll - hero_roll, source="雾中人影")
        elif specter_roll < hero_roll:
            engine._stun_monster(monster, 1)
            engine._log(f"{victim.name} 驱散了哀嚎，雾中人影畏缩了。")
        else:
            engine._log("僵持不下。")
        return True

    # ------------------------------------------------------------- 攻击
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p22：只有持戒指者能攻击雾中人影。"""
        if _monster_id(target) == self.SPECTER:
            return "omen_ring" in attacker.items
        return True

    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p22：持戒指者的徒手攻击对人影改为理智攻击。"""
        if _monster_id(target) == self.SPECTER and default_attr == "might":
            return "sanity"
        return None

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """疯子：优先开最近的窗；全部放入后交回引擎常规追击。"""
        if _monster_id(monster) != self.MADMAN:
            return False
        facedown = self._facedown_rooms(engine)
        if not facedown:
            return False
        target = min(facedown, key=lambda key: (engine._path_length(monster.room_key, key), key))
        path = engine._shortest_path(monster.room_key, target)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 7), "疯子移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"疯子走向{engine.state.board[monster.room_key].name}。")
        if monster.room_key in facedown:
            self._release_specter(engine, monster.room_key)
        return True

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        mid = _monster_id(monster)
        if mid == self.MADMAN:
            if self._facedown_rooms(engine):
                return True  # p93：全部放入前疯子不攻击（被打了也会自卫）
            return False
        if mid != self.SPECTER:
            return False
        return self._specter_attack(engine, monster)

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p22：持戒指者击败雾中人影即放逐（闸门已保证只有持戒者能打）。"""
        if _monster_id(monster) != self.SPECTER:
            return False
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        flags = engine._haunt_flags()
        flags["specters_banished"] = int(flags.get("specters_banished", 0)) + 1
        engine._log("雾中人影被放逐，在圣咏里消散了。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "open_window":
                tokens = engine.tokens_in_room(player.room_key, "specter")
                if player.role != "traitor" or not tokens or all(t.face_up for t in tokens):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "open_window":
            if not any(not t.face_up for t in engine.tokens_in_room(player.room_key, "specter")):
                engine._log("这个房间的窗已经开过了。")
                return False
            return self._release_specter(engine, player.room_key)
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "驱魔完成——雾中人影全部被送回了雾里。")
            return True
        flags = engine._haunt_flags()
        activated = int(flags.get("specters_activated", 0))
        banished = int(flags.get("specters_banished", 0))
        if activated > 0 and banished >= activated and not self._facedown_rooms(engine):
            engine._set_winner("heroes", "所有进屋的雾中人影都被放逐了。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "雾中人影与疯子收割了整栋房子。")
            return True
        return True  # 叛徒阵亡不构成英雄胜（疯子与人影自主行动）
