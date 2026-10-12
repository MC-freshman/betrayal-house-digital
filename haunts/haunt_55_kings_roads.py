"""KingsRoadsMode（剧本 55）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
)


class KingsRoadsMode(GenericModeHandler):
    """剧本 55 国王之路（The King's Roads）。

    权威原文：英雄手册 p66 / 叛徒手册 p137。
    · 驱魔检定（p66）：知识 5+（研究实验室/神秘电梯/持水晶球）或理智 5+
      （小教堂/温室/地窖/持面具）；**每个房间或预兆只能成功一次**（成功后
      把该房间记进 used_sources）。
    · 国王之路（p66/p137）：从任一入口（花园/墓地/庭院/塔楼/阳台/地下湖/
      作祟揭示房）花 1 格移动直达另一入口。英雄要掷理智：4+ 安全抵达，并可
      再用知识 4+ 做一次驱魔（每人限一次，记在角色卡上）；3 抵达但受 1 骰
      精神伤害；2 被扔回起点并受 1 骰精神伤害；0-1 被拉到离自己影子最近的
      出口并立刻结束回合。叛徒走国王之路不需要检定。任何探险者用过一次后
      在角色卡上放一枚孢子（已有则不重复），每人每回合至多一次。
    · 孢子（p66）：每个玩家回合开始，若其角色卡上有孢子，就在其所在房间
      放一枚孢子。
    · 影子（p66）：每名英雄一只（Speed 3 / Might 5 / Sanity 5）；只追自己
      对应的英雄，攻击时用目标**较低**的那项属性对决；打赢不造成伤害而是
      **附身**（该英雄变成叛徒、得 2 点知识、那只影子离场）；英雄攻击影子
      取胜时影子不吃伤害，攻击者受 1 骰精神伤害。
    · 英雄胜：驱魔数 = 玩家数；叛徒胜：英雄全部被附身或死亡。
    · 简化：传送按"每回合一次剧本行动"实现（原文是花 1 格移动，且与"路上
      驱魔"合并为同一个行动）；房间数据里没有"外墙窗户"标记，入口只取六类
      房间加作祟揭示房；影子借孢子房间走国王之路未建模。
    """

    mode = "kings_roads"

    ENTRANCE_ROOMS = ("garden", "graveyard", "patio", "tower", "balcony", "underground_lake")
    KNOWLEDGE_ROOMS = ("research_laboratory", "mystic_elevator")
    SANITY_ROOMS = ("chapel", "conservatory", "crypt")
    DISENCHANT_ROOMS = KNOWLEDGE_ROOMS + SANITY_ROOMS
    SHADOW_NAME = "影子"

    # ------------------------------------------------------------------ 建立
    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["used_sources"] = []
        flags["road_cards"] = []          # 已经用过"路上驱魔"的英雄
        flags["shadow_targets"] = {}
        flags["roads_hub"] = room_key     # 作祟揭示房也是入口
        # p66：作祟揭示者的角色卡上先放一枚孢子；p137 的叛徒同理（他就是被
        # 影子附身的那一个）。
        flags["spore_cards"] = sorted({
            pid
            for pid in (engine.state.haunt_revealer_id, engine.state.traitor_id)
            if pid is not None
        })
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "shadow"),
            {},
        )
        spec = dict(spec)
        spec["name"] = self.SHADOW_NAME
        entrances = self._entrances(engine) or [room_key]
        targets: dict[str, int] = {}
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            nearest = min(sorted(entrances), key=lambda key: engine._path_length(hero.room_key, key))
            monster = engine._spawn_single_haunt_monster(spec, nearest)
            if monster is not None:
                targets[monster.id] = hero.id
        flags["shadow_targets"] = targets
        engine._log(f"{len(targets)} 道影子从国王之路涌入了房子！")

    # ------------------------------------------------------------- 查询辅助
    def _entrances(self, engine) -> list[str]:
        hub = engine._haunt_flags().get("roads_hub")
        keys = [
            key
            for key, room in engine.state.board.items()
            if room.template_id in self.ENTRANCE_ROOMS
        ]
        if isinstance(hub, str) and hub in engine.state.board and hub not in keys:
            keys.append(hub)
        return sorted(keys)

    def _shadows(self, engine) -> list:
        return [m for m in engine.state.monsters if getattr(m, "name", "") == self.SHADOW_NAME]

    def _shadow_of(self, engine, player):
        targets = engine._haunt_flags().get("shadow_targets", {})
        return next(
            (m for m in self._shadows(engine) if targets.get(m.id) == player.id), None
        )

    def _target_of(self, engine, monster):
        pid = engine._haunt_flags().get("shadow_targets", {}).get(monster.id)
        return next((p for p in engine.state.players if p.id == pid and not p.dead), None)

    def _disenchant_stats(self, engine, player) -> list[str]:
        """p66：房间与预兆各自只支持一种属性（实验室/电梯/水晶球 → 知识；
        教堂/温室/地窖/面具 → 理智）。"""
        room_id = engine._current_room_template_id(player)
        stats = []
        if room_id in self.KNOWLEDGE_ROOMS or "omen_crystal_ball" in player.items:
            stats.append("knowledge")
        if room_id in self.SANITY_ROOMS or "omen_mask" in player.items:
            stats.append("sanity")
        return [stat for stat in stats if player.stats.get(stat, 0) > 0]

    def _can_disenchant(self, engine, player) -> bool:
        room_id = engine._current_room_template_id(player)
        if not room_id or room_id in engine._haunt_flags().get("used_sources", []):
            return False
        return bool(self._disenchant_stats(engine, player))

    def _unused_sources(self, engine) -> list[str]:
        used = set(engine._haunt_flags().get("used_sources", []))
        return sorted(
            key
            for key, room in engine.state.board.items()
            if room.template_id in self.DISENCHANT_ROOMS and room.template_id not in used
        )

    def _preferred_stat(self, engine, player) -> str:
        if engine._effective_stat(player, "knowledge") >= engine._effective_stat(player, "sanity"):
            return "knowledge"
        return "sanity"

    def _rooms_for_stat(self, engine, stat: str) -> tuple:
        return self.KNOWLEDGE_ROOMS if stat == "knowledge" else self.SANITY_ROOMS

    # ------------------------------------------------------------- 回合钩子
    def on_turn_start(self, engine, player):
        """p66：角色卡上有孢子的玩家，回合开始在自己所在房间放一枚孢子。"""
        if player.dead:
            return
        if player.id not in set(engine._haunt_flags().get("spore_cards", [])):
            return
        engine.spawn_token("spore", label="孢子", role="marker", room_key=player.room_key)

    def on_monster_move(self, engine, monster, steps) -> bool:
        """p66：影子只追自己对应的英雄，且"离开有对手的房间不额外消耗移动力"。"""
        if getattr(monster, "name", "") != self.SHADOW_NAME:
            return False
        target = self._target_of(engine, monster)
        if target is None:
            return True  # 对应英雄已出局：原地不动
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            index = min(len(path) - 1, max(1, int(steps)))
            monster.room_key = path[index]
            engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        return True

    def on_monster_turn_attack(self, engine, monster) -> bool:
        """p66：影子只打自己对应的英雄，且用目标较低的那项属性对决；打赢＝附身。"""
        if getattr(monster, "name", "") != self.SHADOW_NAME:
            return False
        target = self._target_of(engine, monster)
        if target is None or target.room_key != monster.room_key:
            return True  # 不攻击别的英雄
        attr = (
            "might"
            if target.stats.get("might", 0) <= target.stats.get("sanity", 0)
            else "sanity"
        )
        attack = engine.roll_dice(max(1, int(getattr(monster, attr, 5))), f"影子（{attr}）")
        defense = engine._roll_attack(target, attr)
        engine._log(f"{monster.name} 攻击 {target.name}：{attr} {attack} 对 {defense}。")
        if attack > defense:
            self._possess(engine, monster, target)
        elif defense > attack:
            engine._stun_monster(monster, 1)
            engine._log(f"{target.name} 逼退了影子。")
        else:
            engine._log("平手。")
        return True

    def _possess(self, engine, monster, hero) -> None:
        """p66/p137：被影子打赢＝附身——英雄变叛徒、+2 知识、那只影子离场。"""
        flags = engine._haunt_flags()
        hero.role = "traitor"
        flags.get("shadow_targets", {}).pop(monster.id, None)
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [m for m in engine.state.monsters if getattr(m, "id", None) != monster_id]
        engine._heal_stat(hero, "knowledge", 2)
        cards = set(flags.get("spore_cards", []))
        cards.add(hero.id)
        flags["spore_cards"] = sorted(cards)
        engine._log(f"{monster.name} 附身了 {hero.name}——他从内部打开了国王之路！")
        engine.check_victory()

    def on_attack_resolved(self, engine, attacker, target, attacker_won: bool) -> None:
        """p66：影子被攻击时不吃伤害，进攻的英雄反而受 1 骰精神伤害。"""
        if not attacker_won or getattr(target, "name", "") != self.SHADOW_NAME:
            return
        if getattr(attacker, "role", "") != "hero":
            return
        damage = engine.roll_damage_dice(1, "影子反噬")
        engine._log(f"{attacker.name} 触碰影子，心神被侵蚀（{damage}）。")
        engine._deal_damage(attacker, "mental", damage, source="影子")
        engine.check_victory()

    def on_monster_defeated(self, engine, monster, amount) -> bool:
        """p66：影子不会被打死，也谈不上打晕——直接吸收这次"击败"。"""
        return getattr(monster, "name", "") == self.SHADOW_NAME

    def bot_attack_blocked(self, engine, player, target) -> bool:
        """p66：打影子只会让自己吃 1 骰精神伤害——真人不会这么干。"""
        return getattr(target, "name", "") == self.SHADOW_NAME

    # ------------------------------------------------------------- 可用行动
    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "disenchant_room":
                if player.role != "hero" or not self._can_disenchant(engine, player):
                    continue
            result.append(action)
        if not player.dead:
            roads = self._roads_actions(engine, player)
            if player.role == "hero" and self._shadow_pressing(engine, player) and roads:
                # p66：影子贴上来时先跑——国王之路是英雄唯一能甩开影子的手段
                # （影子只能借孢子房间跳转）。列表首位即机器人会选的那条。
                return roads + result
            result.extend(roads)
        return result

    def _shadow_pressing(self, engine, player) -> bool:
        """追我的影子是否已到"下一轮就能扑上来"的距离。

        影子 Speed 3（每轮掷 3 骰、均值 3 间房），所以两格以内就得动身——
        等它同房再跑通常已经晚了（它一赢就是附身）。
        """
        shadow = self._shadow_of(engine, player)
        return bool(
            shadow is not None
            and engine._path_length(shadow.room_key, player.room_key) <= 3
        )

    def _roads_actions(self, engine, player) -> list:
        """国王之路：从入口房直达另一入口，目的地按"离目标更近"排在前面。

        机器人同分取列表首位，所以把最划算的目的地放最前；人类玩家看到全部。
        """
        if player.dead or player.steps_remaining < 1:
            return []
        entrances = self._entrances(engine)
        if player.room_key not in entrances:
            return []
        destinations = [key for key in entrances if key != player.room_key]
        goal = self._roads_goal(engine, player)
        if goal:
            destinations.sort(key=lambda key: (engine._path_length(key, goal), key))
        return [
            HauntAction(
                "roads_travel",
                f"国王之路 → {engine.state.board[key].name}",
                "花 1 格移动直达；英雄要掷理智（4+ 安全，并可再做一次知识 4+ 的驱魔）。",
                {"room": key},
            )
            for key in destinations
        ]

    def _roads_goal(self, engine, player) -> str:
        """走国王之路最想去哪儿。

        英雄：影子没贴上来时去最近的可用驱魔源；影子已经逼近时去**离影子最远**
        的可用源（国王之路是唯一能一次甩开影子的手段）。
        叛徒：找最近的英雄。
        """
        if player.role == "traitor":
            heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
            if not heroes:
                return ""
            return min(
                heroes, key=lambda item: engine._path_length(player.room_key, item.room_key)
            ).room_key
        sources = self._unused_sources(engine)
        if not sources:
            return ""
        wants = self._rooms_for_stat(engine, self._preferred_stat(engine, player))
        matched = [key for key in sources if engine.state.board[key].template_id in wants]
        candidates = matched or sources
        shadow = self._shadow_of(engine, player)
        if shadow is not None and self._shadow_pressing(engine, player):
            return max(
                candidates, key=lambda key: engine._path_length(shadow.room_key, key)
            )
        return min(candidates, key=lambda key: engine._path_length(player.room_key, key))

    def perform_action(self, engine, player, action_id, data):
        if action_id == "disenchant_room":
            return self._disenchant(engine, player)
        if action_id == "roads_travel":
            return self._travel(engine, player, data)
        return super().perform_action(engine, player, action_id, data)

    def _disenchant(self, engine, player) -> bool:
        """p66：知识/理智 5+，成功则推进轨道并把该房间标记为已用。"""
        if not self._can_disenchant(engine, player):
            return False
        stats = self._disenchant_stats(engine, player)
        stat = max(stats, key=lambda item: engine._effective_stat(player, item))
        if not engine._resolve_check(player, stat, 5, "驱魔检定"):
            engine._log(f"{player.name} 的驱魔没有生效。")
            return True
        flags = engine._haunt_flags()
        room_id = engine._current_room_template_id(player)
        if room_id:
            used = set(flags.get("used_sources", []))
            used.add(room_id)
            flags["used_sources"] = sorted(used)
        value = engine._advance_haunt_track("disenchant_progress")
        engine._log(
            f"国王之路松动了一分（{value}/{engine._haunt_track_target('disenchant_progress')}）。"
        )
        engine.check_victory()
        return True

    def _travel(self, engine, player, data) -> bool:
        """p66/p137：花 1 格移动走国王之路；英雄要过理智，叛徒不用。"""
        target = data.get("room")
        entrances = self._entrances(engine)
        if (
            not isinstance(target, str)
            or target == player.room_key
            or target not in engine.state.board
            or player.room_key not in entrances
            or target not in entrances
            or player.steps_remaining < 1
        ):
            return False
        flags = engine._haunt_flags()
        cards = set(flags.get("spore_cards", []))
        cards.add(player.id)
        flags["spore_cards"] = sorted(cards)
        player.steps_remaining -= 1
        if player.role == "traitor":
            self._arrive(engine, player, target)
            return True
        roll = engine.roll_dice(max(1, engine._effective_stat(player, "sanity")), "国王之路")
        engine._log(f"{player.name} 踏入国王之路（理智 {roll}）。")
        if roll >= 4:
            self._arrive(engine, player, target)
            # p66："You may attempt a disenchantment roll of 4+ using Knowledge"
            # ——每人只能在路上驱魔一次（标记在角色卡上）。
            if player.id not in set(flags.get("road_cards", [])):
                if engine._resolve_check(player, "knowledge", 4, "路上的驱魔"):
                    road = set(flags.get("road_cards", []))
                    road.add(player.id)
                    flags["road_cards"] = sorted(road)
                    value = engine._advance_haunt_track("disenchant_progress")
                    engine._log(f"他在国王之路上完成了驱魔（{value}）！")
        elif roll == 3:
            self._arrive(engine, player, target)
            engine._deal_damage(player, "mental", engine.roll_damage_dice(1, "精神伤害"), source="国王之路")
        elif roll == 2:
            engine._deal_damage(player, "mental", engine.roll_damage_dice(1, "精神伤害"), source="国王之路")
            engine._log(f"{player.name} 被扔回了出发的房间。")
        else:
            shadow = self._shadow_of(engine, player)
            exit_key = target
            if shadow is not None and entrances:
                exit_key = min(
                    entrances, key=lambda key: engine._path_length(shadow.room_key, key)
                )
            self._arrive(engine, player, exit_key)
            player.movement_stopped = True
            engine._log(f"{player.name} 抗拒不了影子的呼唤，从最近的出口跌了出来。")
        engine.check_victory()
        return True

    def _arrive(self, engine, player, room_key) -> None:
        player.room_key = room_key
        player.moved_this_turn = True
        engine._log(f"{player.name} 从国王之路抵达{engine.state.board[room_key].name}。")
        engine._resolve_room_entry_if_needed(player)

    # ------------------------------------------------------------- bot 寻路
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p66：英雄的目标只有一个——把没用过的驱魔源走一遍（走国王之路更快）。

        没有这条时英雄只会按通用画像去追影子（chase 权重 +130 高于剧本目标
        +125），实测 seed127/4p：两名英雄在花园/墓地之间对撞 300 回合，驱魔
        进度停在 2/4，场上还剩"神秘电梯"没用过，谁也赢不了。
        """
        if player.dead or player.role != "hero":
            return []
        if self._can_disenchant(engine, player):
            return []  # 已经站在可用的源上：交给 bot_stay_in_room 钉住
        sources = self._unused_sources(engine)
        shadow = self._shadow_of(engine, player)
        if shadow is not None:
            # 影子一轮能走 3 格（掷 3 骰），所以只挑"离它 4 格以上"的源；
            # 全都太近时退而求其次（总比站着不动强）。
            safe = [key for key in sources if engine._path_length(shadow.room_key, key) >= 4]
            if safe:
                sources = safe
        return [f"__room__{key}" for key in sources]

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """站在"还能用、自己也掷得动"的驱魔源上：别挪窝，继续掷 5+。

        但影子一旦贴上来（同房或隔壁）就必须先躲开——p66 里影子赢一次就是
        附身（英雄直接变叛徒），站着不动等于把自己送出去。
        """
        if player.dead or player.role != "hero":
            return False
        if not self._can_disenchant(engine, player):
            return False
        shadow = self._shadow_of(engine, player)
        if shadow is not None and engine._path_length(shadow.room_key, player.room_key) <= 3:
            return False
        stats = self._disenchant_stats(engine, player)
        return max(engine._effective_stat(player, stat) for stat in stats) >= 3

    def bot_hazard_rooms(self, engine: Any, player: Any) -> list[str]:
        """p66：别在本回合结束时和追自己的影子同房（它赢一次就附身）。"""
        if player.dead or player.role != "hero":
            return []
        shadow = self._shadow_of(engine, player)
        return [shadow.room_key] if shadow is not None else []

    def check_victory(self, engine):
        if engine._haunt_track_value("disenchant_progress") >= engine._haunt_track_target("disenchant_progress"):
            engine._set_winner("heroes", "国王之路被封住了——影子退回了暗影国度。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "影子附身了最后的英雄。")
            return True
        return True  # 吸收引擎"叛徒死亡即英雄胜"兜底（p66：叛徒死不触发英雄胜）
