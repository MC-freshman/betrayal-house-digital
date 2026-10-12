"""SmallChangeMode（剧本 35）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class SmallChangeMode(GenericModeHandler):
    """剧本 35 小小变化（Small Change）。

    权威原文：英雄手册 p46 / 叛徒手册 p117。

    · 缩小（p46）：全员移动费用 ×2（movement_cost_multiplier 对所有
      角色返回 2——p46 "doorway counts as 2 spaces"）。
    · 猫（p117）：3-4 人 1 只门厅 / 5-6 人 2 只（门厅+作祟房）；
      Speed 6 / Might 7 / Sanity 5；猫力量胜利改为捕获（不伤害）。
    · 捕获逃生（p46/p117）：被俘者回合开始选属性对决（bot 选最强属性），
      赢则自由；其他英雄击败猫 → 猫晕 + 释放。捕获者在下一次怪物回合
      开始时被吞食（bot 局近似为"猫未被打晕则下一怪物回合杀"）。
    · 叛徒不可直接攻击英雄（p117 "You can't attack explorers"）。
    · 玩具飞机（p46）：卧室类房间知识 3+ 搜索 → 知识 4+ 发动；
      发动后在外缘房间逃离（escape_plane 行动）。至少半数英雄出逃
      → 英雄胜。被猫杀死超过半数 → 叛徒胜。
    · 简化：楼梯 Might 3+ / 不可用电梯/塌房等缩小限制未建模；
      飞机搭乘/接送/坠机等细节简化为"发动后在外缘房间逃离"；
      猫拍落飞机 Speed 7+ 未实现（猫已能捕获，拍落是次要手段）。
    """

    mode = "small_change_escape"

    CAT = "cat"
    OUTER_ROOMS = {"grand_staircase", "master_bedroom", "bedroom", "chapel",
                   "dining_room", "balcony", "garden", "graveyard", "patio", "tower"}

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["captured"] = {}
        flags["escaped"] = []
        players = len(engine.state.players)
        cat_count = 1 if players <= 4 else 2
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.CAT),
            {},
        )
        spec = dict(spec, knowledge=5)  # p117：猫的知识为5，可用于逃脱对决。
        entrance = next(
            (k for k, r in engine.state.board.items() if r.template_id == "entrance_hall"),
            room_key,
        )
        engine._spawn_single_haunt_monster(spec, entrance)
        if cat_count >= 2:
            engine._spawn_single_haunt_monster(spec, room_key)
        engine._log(f"{cat_count} 只巨大的猫从门缝里挤了进来——它们把你当成了老鼠！")

    # ------------------------------------------------------------- 缩小
    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p46：所有人缩小，每个门算 2 格。"""
        return 2

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p117：叛徒不能直接攻击英雄（猫来做）。"""
        if isinstance(getattr(attacker, "role", None), str) and attacker.role == "traitor":
            return False
        return True

    # ------------------------------------------------------------- 猫
    def _cats(self, engine: Any) -> list:
        return [m for m in engine.state.monsters if _monster_id(m) == self.CAT]

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """p117：猫力量胜利改为捕获而非伤害。"""
        if _monster_id(monster) != self.CAT:
            return False
        flags = engine._haunt_flags()
        captured = flags.setdefault("captured", {})
        captured[str(target.id)] = str(getattr(monster, "id", ""))
        engine._log(f"猫扑住了 {target.name}——TA 被猫爪按在了地上！")
        return True  # 不造成伤害

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """猫的怪物回合：吞食被俘者（简化——直接伤害而非延迟到下回合）。"""
        if _monster_id(monster) != self.CAT:
            return False
        flags = engine._haunt_flags()
        captured = flags.get("captured", {})
        victims = [
            p for p in engine.state.players
            if not p.dead and captured.get(str(p.id)) == str(getattr(monster, "id", ""))
            and p.room_key == monster.room_key
        ]
        for victim in victims:
            engine._log(f"猫把 {victim.name} 吞食了！")
            victim.dead = True
            captured.pop(str(victim.id), None)
        engine.check_victory()
        # 这里只处理回合开始的吞食；返回 True 会让引擎跳过猫的移动和攻击。
        return engine.state.phase == "GAME_OVER"

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p46：被俘者回合开始选属性对决逃生。"""
        flags = engine._haunt_flags()
        captured = flags.get("captured", {})
        pid = str(getattr(player, "id", ""))
        if pid not in captured or player.dead:
            return
        monster_id = captured[pid]
        cat = next((m for m in engine.state.monsters if str(getattr(m, "id", "")) == monster_id), None)
        if cat is None:
            captured.pop(pid, None)
            return
        # bot 选最强属性对决
        best_stat = max(("might", "speed", "sanity", "knowledge"), key=lambda s: player.stats.get(s, 0))
        hero_roll = engine._roll_attack(player, best_stat)
        cat_roll = engine.roll_dice(getattr(cat, best_stat, 3), "猫对决")
        engine._log(f"{player.name} 试图挣脱（{best_stat} 对决）：{hero_roll} 对 {cat_roll}。")
        if hero_roll > cat_roll:
            captured.pop(pid, None)
            player.movement_stopped = False
            engine._log(f"{player.name} 挣脱了猫爪！")
        else:
            player.movement_stopped = True
            engine._log(f"{player.name} 挣扎失败，仍然被猫按在地上。")

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p46：英雄击败猫 → 猫晕 + 释放被俘者。"""
        if _monster_id(monster) != self.CAT:
            return False
        flags = engine._haunt_flags()
        captured = flags.get("captured", {})
        cat_id = str(getattr(monster, "id", ""))
        for pid in [pid for pid, mid in captured.items() if mid == cat_id]:
            captured.pop(pid, None)
            player = next((p for p in engine.state.players if str(p.id) == pid), None)
            if player:
                player.movement_stopped = False
                engine._log(f"{player.name} 被从猫爪下救了出来！")
        return False  # 默认击晕

    # ------------------------------------------------------------- 行动
    bot_goal_exclusive = True

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero" or player.dead:
            return []
        flags = engine._haunt_flags()
        if flags.get("plane_started"):
            return list(self.OUTER_ROOMS)
        if flags.get("plane_found"):
            # 发动在任意房间都可进行，不让通用目标把搜索者拉走。
            return ["__room__" + player.room_key]
        return ["bedroom", "master_bedroom", "larder", "attic", "game_room"]

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        for action in actions:
            if action.id == "escape_plane":
                room_id = engine._current_room_template_id(player)
                if room_id not in self.OUTER_ROOMS or not flags.get("plane_started"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "search_plane":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("plane_found"):
                engine._log("玩具飞机找到了！")
            return ok
        if action_id == "start_plane":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("plane_started"):
                engine._log("玩具飞机嗡嗡地发动了——快带大家到窗边逃离！")
            return ok
        if action_id == "escape_plane":
            ok = super().perform_action(engine, player, action_id, data)
            if ok:
                escaped = flags.setdefault("escaped", [])
                if player.id not in escaped:
                    escaped.append(player.id)
                    engine._log(f"{player.name} 驾着玩具飞机飞出了窗外！")
                engine.check_victory()
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        import math
        flags = engine._haunt_flags()
        heroes_at_start = sum(1 for p in engine.state.players if p.role == "hero")
        escaped_count = len(flags.get("escaped", []))
        need_escape = math.ceil(heroes_at_start / 2)
        dead_heroes = sum(1 for p in engine.state.players if p.role == "hero" and p.dead)
        if escaped_count >= need_escape:
            engine._set_winner("heroes", "玩具飞机摇摇晃晃地飞出了窗外——猫的咆哮远去了！")
            return True
        if dead_heroes > heroes_at_start / 2:
            engine._set_winner("traitor", "超过半数的英雄被猫吃掉了——实验大获成功。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也成了猫的玩具。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p46/p117 只认"半数英雄飞出窗"，
        # 叛徒死后猫照常吃人。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
