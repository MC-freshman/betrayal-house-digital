"""WerewolfHuntMode（剧本 5）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
    _monster_id,
)


class WerewolfHuntMode(GenericModeHandler):
    """剧本 5 我曾是少年狼人（I Was a Teenage Werewolf）。

    权威原文：英雄手册 p14 / 叛徒手册 p85。胜负仍走通用 win_conditions。

    本 handler 实现的专属机制（M10-72 自 engine._haunt5_* 迁入，
    引擎只保留 attack_kill_override / on_hero_damaged / damage_amount_override
    三个 hook 的分派）：
      · 感染链：被叛徒或狼犬打中的英雄带上狼人诅咒标记（p14）；
      · 回合开始：叛徒力量与速度各 +1；被感染英雄理智 4+ 抵抗，
        失败即变成狼人（装备全弃、阵营改叛徒）；
      · 银弹：左轮 + 银弹令牌打中狼人或狼犬即死（p15）；
      · 狼人抗性：狼人（叛徒）受到的非银弹伤害减半，至少剩 1 点（p85）；
      · 行动：阁楼/游戏室/杂物间/主卧/金库搜左轮（知识 5+），
        研究实验室/熔炉房制银弹（知识 5+），持弹者可把银弹交给同房英雄。
    """

    mode = "werewolf_hunt"

    SEARCH_ROOMS = {"attic", "game_room", "junk_room", "master_bedroom", "vault"}
    LAB_ROOMS = {"research_laboratory", "furnace_room"}
    DOG = "dog"

    # ------------------------------------------------------- 感染 / 转化（p14）
    def on_hero_damaged(self, engine: Any, attacker: Any, target: Any) -> None:
        """英雄被击中：来源是叛徒（狼人）或狼犬 → 感染狼人诅咒。"""
        if target.dead or target.role != "hero":
            return
        if getattr(attacker, "role", "") == "traitor" or _monster_id(attacker) == self.DOG:
            self._infect(engine, target)

    def _infect(self, engine: Any, player: Any) -> None:
        if not engine.state.haunt or player.dead or player.role != "hero":
            return
        flags = engine._haunt_flags()
        infected = list(flags.get("infected", []))
        if player.id not in infected:
            infected.append(player.id)
            flags["infected"] = infected
            engine._log(f"{player.name} 被狼人诅咒感染。")

    def _convert_to_werewolf(self, engine: Any, player: Any) -> None:
        player.role = "traitor"
        for card_id in list(player.items):
            engine._discard_card_from_player(player, card_id, return_to_room=True)
        player.companions.clear()
        engine._log(f"{player.name} 变成了狼人，加入叛徒阵营。")
        engine.check_victory()

    def on_turn_start(self, engine: Any, player: Any) -> None:
        # 叛徒每回合开始时力量与速度各 +1；被感染的英雄做理智检定抵抗转化。
        if player.role == "traitor":
            engine._increase_stat(player, "speed", 1)
            engine._increase_stat(player, "might", 1)
        flags = engine._haunt_flags()
        infected = set(flags.get("infected", []))
        if player.role == "hero" and player.id in infected:
            if engine._resolve_check(player, "sanity", 4, "抵抗狼人诅咒"):
                engine._log(f"{player.name} 暂时压住了狼人诅咒。")
            else:
                self._convert_to_werewolf(engine, player)

    # ------------------------------------------------------- 银弹 / 抗性（p15/p85）
    def _has_silver_bullets(self, engine: Any, player: Any) -> bool:
        return engine._haunt_flags().get("silver_bullets_holder") == player.id

    def _is_werewolf_target(self, target: Any) -> bool:
        # 玩家目标：狼人（叛徒阵营）且还活着；怪物目标：狼犬。
        if getattr(target, "role", "") == "traitor" and not target.dead:
            return True
        return _monster_id(target) == self.DOG

    def attack_kill_override(self, engine: Any, attacker: Any, target: Any, weapon: Any) -> bool:
        # p15：银弹打中狼人或狼犬即死。
        if weapon is None or weapon.id != "item_revolver" or not self._has_silver_bullets(engine, attacker):
            return False
        if not self._is_werewolf_target(target):
            return False
        if _monster_id(target):  # 怪物目标：狼犬
            engine.state.monsters = [m for m in engine.state.monsters if m.id != target.id]
        else:  # 玩家目标：狼人
            target.dead = True
            engine._drop_inventory_on_death(target)
        engine._log(f"{attacker.name} 用银弹击杀了 {target.name}。")
        return True

    def damage_amount_override(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int | None:
        # p85：狼人（叛徒）受到的非银弹伤害减半，至少剩 1 点。
        if player.role != "traitor" or source == "银弹":
            return None
        reduced = max(1, (amount + 1) // 2)
        if reduced != amount:
            engine._log("狼人抗性让伤害减半。")
        return reduced

    # ------------------------------------------------------- 行动（p14）
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions: list[Any] = []
        if player.role != "hero":
            return actions
        room_id = engine._current_room_template_id(player)
        flags = engine._haunt_flags()
        silver_holder = flags.get("silver_bullets_holder")
        if room_id in self.SEARCH_ROOMS and not engine._card_is_controlled("item_revolver"):
            actions.append(HauntAction("h5_find_revolver", "搜索左轮手枪", "知识 5+，成功后从物品牌堆取得左轮手枪。"))
        if room_id in self.LAB_ROOMS and silver_holder is None:
            actions.append(HauntAction("h5_make_silver_bullets", "制作银弹", "知识 5+，成功后获得银弹令牌。"))
        if silver_holder == player.id:
            for other in engine.state.players:
                if other.id != player.id and not other.dead and other.room_key == player.room_key and other.role == "hero":
                    actions.append(
                        HauntAction(
                            "h5_give_silver_bullets",
                            f"交出银弹给 {other.name}",
                            "把银弹令牌交给同房间英雄。",
                            {"target_id": other.id},
                        )
                    )
        return actions

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "h5_find_revolver":
            if player.role != "hero" or engine._current_room_template_id(player) not in self.SEARCH_ROOMS:
                return False
            if engine._card_is_controlled("item_revolver"):
                return False
            if engine._resolve_check(player, "knowledge", 5, "搜索左轮手枪"):
                if engine._grant_card_to_player(player, "item_revolver"):
                    flags["revolver_found"] = True
            return True
        if action_id == "h5_make_silver_bullets":
            if player.role != "hero" or engine._current_room_template_id(player) not in self.LAB_ROOMS:
                return False
            if flags.get("silver_bullets_holder") is not None:
                return False
            if engine._resolve_check(player, "knowledge", 5, "制作银弹"):
                flags["silver_bullets_created"] = True
                flags["silver_bullets_holder"] = player.id
                engine._set_haunt_track_value("silver_bullets", 1)
                engine._log(f"{player.name} 制作出了银弹。")
            return True
        if action_id == "h5_give_silver_bullets":
            if flags.get("silver_bullets_holder") != player.id:
                return False
            target_id = int(data.get("target_id", -1))
            if not (0 <= target_id < len(engine.state.players)):
                return False
            target = engine.state.players[target_id]
            if target.dead or target.room_key != player.room_key or target.role != "hero":
                return False
            flags["silver_bullets_holder"] = target.id
            engine._log(f"{player.name} 把银弹交给了 {target.name}。")
            return True
        return False
