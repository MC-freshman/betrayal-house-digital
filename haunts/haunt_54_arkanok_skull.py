"""ArkanokSkullMode（剧本 54）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class ArkanokSkullMode(GenericModeHandler):
    """剧本 54 阿卡诺克之颅（The Skull of Ar'Kanok）。

    权威原文：英雄手册 p65 / 叛徒手册 p136。
    · 骷髅 token 放作祟房间；遗骸在六类房间之一。
    · 侦测：持骷髅/圣徽理智 4+；持水晶球/灵应板知识 5+。
    · 净化：持骷髅在遗骸房间理智 5+。
    · 僵尸 2× 英雄数（Speed 1 Might 4 Sanity 2）。
    · 英雄胜：净化；叛徒胜：英雄全灭。
    """

    mode = "arkanok_skull"

    REMAINS_ROOMS = ["chapel", "crypt", "graveyard", "furnace_room", "bloody_room", "charred_room"]

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["remains_found"] = False
        flags["skull_picked"] = False
        # 遗骸房间（叛徒知道；bot 随机选）
        candidates = [rid for rid in self.REMAINS_ROOMS
                      if any(r.template_id == rid for r in engine.state.board.values())]
        if not candidates:
            candidates = self.REMAINS_ROOMS
        remains_template = engine.rng.choice(candidates)
        remains_key = next((k for k, r in engine.state.board.items() if r.template_id == remains_template), None)
        if remains_key is None:
            remains_key = engine._ensure_room_in_play(remains_template, room_key)
        flags["remains_room"] = remains_key
        # 骷髅 token 放作祟房间
        engine.spawn_token("skull", label="Ar'Kanok 之颅", role="marker", room_key=room_key)
        # 僵尸 2× 英雄数
        spec = next((s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "zombie"), {})
        spec = dict(spec)
        spec["name"] = "僵尸"
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        for _ in range(hero_count * 2):
            key = engine.rng.choice(sorted(engine.state.board.keys()))
            engine._spawn_single_haunt_monster(spec, key)
        engine._log("墙壁长出了腐肉——僵尸在房子里游荡！")

    def on_enter_room(self, engine, player, room):
        # p65：探险者进入骷髅所在房间即可拾起（捡令牌不耗行动，与尸体令牌
        # 等既有先例一致）。bot 局实测必要：骷髅是 marker 令牌，
        # bot 的 _pickup_room_items 只捡卡牌，英雄到房也永远拿不到颅骨，
        # detect_remains/exorcise 的"持骷髅"前置永假，ritual_progress 恒 0/1
        # （探针 113/3p：remains_found=True 而 holder=None，整局死锁）。
        if player.dead or player.role == "traitor":
            return
        for token in engine.tokens_in_room(room.key, "skull"):
            if engine.give_token(token.uid, player.id):
                flags = engine._haunt_flags()
                flags["skull_picked"] = True
                engine._log(f"{player.name} 拾起了 Ar'Kanok 之颅。")

    def _object_room(self, engine):
        for t in engine.state.tokens:
            if t.kind == "skull":
                if t.holder is not None:
                    p = next((p for p in engine.state.players if p.id == t.holder), None)
                    return p.room_key if p else None
                return t.room_key
        return None

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        room_id = engine._current_room_template_id(player)
        has_skull = engine.tokens_held_by(player.id, "skull")
        has_hs = "omen_holy_symbol" in player.items
        has_cb = "omen_crystal_ball" in player.items
        has_sb = "omen_spirit_board" in player.items
        for action in actions:
            if action.id == "detect_remains":
                if not (has_skull or has_hs or has_cb or has_sb):
                    continue
                if flags.get("remains_found"):
                    continue
            if action.id == "exorcise":
                if not has_skull or not flags.get("remains_found"):
                    continue
                if room_id != engine.state.board.get(flags.get("remains_room"), type("R", (), {"template_id": ""})).template_id:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "detect_remains":
            room_id = engine._current_room_template_id(player)
            has_skull = engine.tokens_held_by(player.id, "skull")
            has_hs = "omen_holy_symbol" in player.items
            has_cb = "omen_crystal_ball" in player.items
            has_sb = "omen_spirit_board" in player.items
            if has_skull or has_hs:
                ok = engine._resolve_check(player, "sanity", 4, "侦测遗骸")
            elif has_cb or has_sb:
                ok = engine._resolve_check(player, "knowledge", 5, "搜索遗骸")
            else:
                engine._log("需要骷髅/圣徽/水晶球/灵应板才能侦测。")
                return False
            if ok:
                flags["remains_found"] = True
                room = engine.state.board.get(flags["remains_room"])
                engine._log(f"Ar'Kanok 的遗骸在{room.name}！")
            else:
                engine._log("侦测失败。")
            return True

        if action_id == "exorcise":
            room_id = engine._current_room_template_id(player)
            if not engine.tokens_held_by(player.id, "skull"):
                engine._log("你需要持有骷髅。")
                return False
            remains_key = flags.get("remains_room")
            if remains_key is None or engine.state.board.get(remains_key, type("R", (), {"template_id": ""})).template_id != room_id:
                engine._log("你必须在遗骸所在的房间。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                skull = next(iter(engine.tokens_held_by(player.id, "skull")), None)
                if skull:
                    engine.place_token(skull.uid, player.room_key)
                engine._log("Ar'Kanok 的灵魂终于安息了！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        if engine._haunt_track_value("ritual_progress") >= engine._haunt_track_target("ritual_progress"):
            engine._set_winner("heroes", "Ar'Kanok 安息了——僵尸随之倒下。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "僵尸撕碎了最后的英雄。")
            return True
        return True  # 吸收引擎"叛徒死亡即英雄胜"兜底（p136：叛徒死不触发英雄胜）

    # ------------------------------------------------------------- bot 寻路
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p65：英雄胜 = 持颅到遗骸房净化（ritual_progress 满）。引导：
        ① 本英雄持颅→遗骸已定位则去遗骸房净化，否则在本房侦测（返回空）；
        ② 骷髅还是松散令牌→去骷髅令牌房间拾取；
        ③ 别人持颅且遗骸已定位→陪去遗骸房就近保护。"""
        flags = engine._haunt_flags()
        skull = next((t for t in engine.state.tokens if t.kind == "skull"), None)
        if skull is None:
            return []
        if engine.tokens_held_by(player.id, "skull"):
            if flags.get("remains_found"):
                remains_key = flags.get("remains_room")
                if remains_key:
                    return ["__room__" + remains_key]
            return []  # 持颅但遗骸未定位，本房即可侦测
        # 没持颅：先去拾取（若松散令牌）；若别人持颅且遗骸已定位→陪去遗骸房
        if skull.holder is None and skull.room_key:
            return ["__room__" + skull.room_key]
        if skull.holder is not None and flags.get("remains_found"):
            remains_key = flags.get("remains_room")
            if remains_key:
                return ["__room__" + remains_key]
        return []
