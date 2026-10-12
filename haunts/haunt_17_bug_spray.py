"""BugSprayMode（剧本 17）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
    name_map,
)


class BugSprayMode(GenericModeHandler):
    """剧本 17 虫群（Bugs）。

    权威原文：英雄手册 p28 / 叛徒手册 p99。

    · 配料（p28）：六种配料令牌（硝酸/鼠药/喷枪/地板蜡/醋/园艺用品）
      按序放实验室/储藏室/阁楼/仆人房/厨房/花园（原版 Storeroom 与
      Larder 在本项目共用 larder）；未发现的房间等发现时补放。英雄
      拾取任意三种带进实验室或厨房（不拘谁拿着），知识 4+ 合成杀虫剂
      （每回合一次；失败配料保留，下回合再试）。
    · 巨虫（p99）：螳螂 4/5/4（作祟房间）、蜈蚣 3/3/4（杂物间）、黄蜂
      5/2/4（阁楼）、蜘蛛 3/6/4（储藏室）、蟑螂 0/5/4（厨房）、甲虫
      3/6/4（地窖）。项目没有昆虫模板，全部用 spider 模板承载，种类
      映射存 flags["bug_kind"]（优化方案 engine_note 惯例）。
    · 杀虫剂攻击（p28）：持杀虫剂对虫攻击改为**速度攻击**
      （attack_attr_override）；用杀虫剂击败虫即杀死（非击晕），杀满
      三只其余虫逃散；用杀虫剂攻击落败不受伤（attack_loss_damage_disabled）。
    · 蛛网（p99）：被蜘蛛击败的探险者被缚——四属性各 -2（不低于 1）、
      不能移动；同房任意探险者每回合一次力量 5+ 挣脱并恢复失去的 2 点。
    · 蟑螂（p99）：永不离开厨房（on_monster_move）；它守在厨房时离开
      厨房按 3 格移动（movement_cost_floor 钩子）。
    · 叛徒（p99）：拾取/偷取配料——至多背 3 枚配料或 1 瓶杀虫剂（不可
      兼有）；在深坑/熔炉房/地下湖销毁背着的配料或杀虫剂；4 枚配料被
      毁且英雄没有杀虫剂 → 叛徒胜。
    · 英雄胜：毒杀三只虫（其余逃散）；叛徒胜：配料被毁条件或英雄全灭。
      虫群自主行动，叛徒阵亡不结束游戏。
    · 已知简化：英雄丢下配料未建模（拾取即持有）；人类叛徒的偷窃/选择
      弹窗留待接 prompter；杀虫剂被毁后英雄可再用剩余配料重新合成
      （原文规则，已支持）。
    """

    mode = "bug_spray"

    INGREDIENT = "ingredient"
    SPRAY = "bug_spray"
    BUG = "spider"  # 全部昆虫用 spider 模板承载
    INGREDIENT_ROOMS = [
        ("research_laboratory", "硝酸"), ("larder", "鼠药"), ("attic", "喷枪"),
        ("servants_quarters", "地板蜡"), ("kitchen", "醋"), ("garden", "园艺用品"),
    ]
    BUG_ROOMS = [
        ("mantis", None, "螳螂", (4, 5, 4)),      # None = 作祟房间
        ("centipede", "junk_room", "蜈蚣", (3, 3, 4)),
        ("wasp", "attic", "黄蜂", (5, 2, 4)),
        ("spider_bug", "larder", "蜘蛛", (3, 6, 4)),   # 原版 Storeroom 与 Larder 共用
        ("roach", "kitchen", "蟑螂", (0, 5, 4)),
        ("beetle", "crypt", "甲虫", (3, 6, 4)),
    ]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["bug_kind"] = {}
        flags.setdefault("webbed", [])
        flags["ingredient_destroyed"] = 0
        # 配料（p28）：房间在场即放，否则等发现时补放
        for template_id, label in self.INGREDIENT_ROOMS:
            key = next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key:
                token = engine.spawn_token(self.INGREDIENT, label=label, role="marker", room_key=key)
                token.data["name"] = label
        # 六只虫（p99）：房间在场即放，否则等发现时补放；螳螂在作祟房间
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.BUG),
            {},
        )
        for kind, template_id, name, stats in self.BUG_ROOMS:
            key = room_key if template_id is None else next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key is None:
                continue
            bug_spec = dict(spec)
            bug_spec["name"] = name
            bug_spec["speed"], bug_spec["might"], bug_spec["sanity"] = stats
            monster = engine._spawn_single_haunt_monster(bug_spec, key)
            if monster is not None:
                flags["bug_kind"][str(monster.id)] = kind
        engine._log("房间里响起密集的窸窣声——巨型昆虫 crawling 出来了！")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p28/p99：配料与虫所在的房间未探索时，发现即补放。"""
        flags = engine._haunt_flags()
        for template_id, label in self.INGREDIENT_ROOMS:
            if room.template_id == template_id and not any(
                t.data.get("name") == label for t in engine.tokens_of_kind(self.INGREDIENT)
            ):
                token = engine.spawn_token(self.INGREDIENT, label=label, role="marker", room_key=room.key)
                token.data["name"] = label
                return
        spec_source = (engine.state.haunt.rule_data or {}).get("monsters", [])
        for kind, template_id, name, stats in self.BUG_ROOMS:
            if template_id is None or room.template_id != template_id:
                continue
            if any(k == kind for k in flags.get("bug_kind", {}).values()):
                continue
            spec = next((s for s in spec_source if s.get("template_id") == self.BUG), {})
            spec = dict(spec)
            spec["name"] = name
            spec["speed"], spec["might"], spec["sanity"] = stats
            monster = engine._spawn_single_haunt_monster(spec, room.key)
            if monster is not None:
                flags["bug_kind"][str(monster.id)] = kind
                engine._log(f"一只{name}从{room.name}的阴影里爬了出来！")
            return

    # ------------------------------------------------------------- 机器人合成链
    bot_goal_exclusive = True

    def _mix_room(self, engine):
        flags = engine._haunt_flags()
        saved = flags.get("bot_mix_room")
        if saved in engine.state.board and not engine._is_collapsed(saved):
            return saved
        rooms = [key for key, room in engine.state.board.items()
                 if room.template_id in ("research_laboratory", "kitchen")
                 and not engine._is_collapsed(key)]
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not rooms or not heroes:
            return None
        room = min(rooms, key=lambda key: (sum(engine._path_length(p.room_key, key) for p in heroes), key))
        flags["bot_mix_room"] = room
        return room

    def bot_goal_rooms(self, engine, player):
        if player.dead or player.role != "hero":
            return []
        if self._holding_spray(engine, player):
            return ["__room__" + bug.room_key for bug in self._bugs(engine)]
        ingredients = list(engine.tokens_of_kind(self.INGREDIENT))
        hero_ids = {p.id for p in engine.state.players if p.role == "hero" and not p.dead}
        held = [token for token in ingredients if token.holder in hero_ids]
        if len(held) >= 3 or any(t.kind == self.SPRAY for t in engine.state.tokens):
            room = self._mix_room(engine)
            return ["__room__" + room] if room else []
        loose = [token for token in ingredients if token.holder is None and token.room_key]
        return ["__room__" + token.room_key for token in loose]

    def bot_wants_explore(self, engine, player):
        if player.role != "hero" or self._holding_spray(engine, player):
            return False
        hero_ids = {p.id for p in engine.state.players if p.role == "hero" and not p.dead}
        usable = [t for t in engine.tokens_of_kind(self.INGREDIENT)
                  if t.holder is None or t.holder in hero_ids]
        return len(usable) < 3 and not any(t.kind == self.SPRAY for t in engine.state.tokens)

    def bot_stay_in_room(self, engine, player):
        if player.role != "hero" or player.dead or self._holding_spray(engine, player):
            return False
        held = self._held_ingredients(engine, player)
        hero_ids = {p.id for p in engine.state.players if p.role == "hero" and not p.dead}
        gathered = [t for t in engine.tokens_of_kind(self.INGREDIENT) if t.holder in hero_ids]
        # 原地接收同伴的配料；到达集合点后离开会让材料永远凑不齐。
        return bool(held and len(gathered) >= 3 and player.room_key == self._mix_room(engine))

    def bot_attack_blocked(self, engine, player, target):
        # 毒杀才推进胜利轨；没有杀虫剂时先完成配料后勤。
        if player.role != "hero" or not self._is_bug(engine, target) or self._holding_spray(engine, player):
            return False
        if target.stunned_turns > 0:
            return True
        for weapon in [None] + engine.available_attack_weapons(player):
            params = engine._derive_attack_params(player, target, weapon, False)
            if params is not None:
                ranged, stat, _, bonus = params
                dice = min(8, engine._effective_stat(player, stat) + bonus + engine._check_bonus(player, stat))
                if ranged or dice >= getattr(target, stat, 0) + 2:
                    return False  # 有把握的击晕为材料会合争取一轮。
        return True

    def bot_action_priority(self, engine, player, action_id):
        return {"make_spray": 100, "take_ingredient": 80, "break_webs": 60}.get(action_id, 0)

    # ------------------------------------------------------------- 内部
    def _kind_of(self, engine: Any, monster: Any) -> str:
        return str(engine._haunt_flags().get("bug_kind", {}).get(str(getattr(monster, "id", "")), ""))

    def _bugs(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.BUG]

    def _is_bug(self, engine: Any, target: Any) -> bool:
        return _monster_id(target) == self.BUG

    def _holding_spray(self, engine: Any, player: Any) -> bool:
        return bool(engine.tokens_held_by(player.id, self.SPRAY))

    def _held_ingredients(self, engine: Any, player: Any) -> list[Any]:
        return engine.tokens_held_by(player.id, self.INGREDIENT)

    def _room_ingredient_pool(self, engine: Any, room_key: str) -> list[Any]:
        """该房间里可用的配料：地上未持的 + 同房英雄手里拿的（p28）。"""
        pool = list(engine.tokens_in_room(room_key, self.INGREDIENT))
        for p in engine.state.players:
            if not p.dead and p.room_key == room_key:
                pool.extend(engine.tokens_held_by(p.id, self.INGREDIENT))
        return pool

    # ------------------------------------------------------------- 装备规则
    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """p28：持杀虫剂对虫的攻击改为速度攻击。"""
        if self._is_bug(engine, target) and self._holding_spray(engine, attacker):
            return "speed"
        return None

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p28：用杀虫剂攻击落败不受伤。"""
        return self._is_bug(engine, target) and self._holding_spray(engine, attacker)

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p99：蟑螂守厨房时，离开厨房按 3 格移动计。"""
        if not from_key:
            return 0
        room = engine.state.board.get(from_key)
        if room is None or room.template_id != "kitchen":
            return 0
        roach = next(
            (m for m in self._bugs(engine) if self._kind_of(engine, m) == "roach"
             and m.room_key == from_key and int(getattr(m, "stunned_turns", 0)) <= 0),
            None,
        )
        return 3 if roach is not None else 0

    def on_player_died(self, engine: Any, player: Any) -> None:
        # 被缚者死亡时解除蛛网标记
        flags = engine._haunt_flags()
        webbed = [pid for pid in flags.get("webbed", []) if pid != str(player.id)]
        flags["webbed"] = webbed

    # ------------------------------------------------------------- 蛛网
    def _web_lower_traits(self, engine: Any, player: Any) -> None:
        """p99：被缚者四属性各 -2，但不低于 1（原文 minimum of 1）。"""
        for stat in ("speed", "might", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            position = player.stat_positions.get(stat)
            if not track or position is None:
                player.stats[stat] = max(1, player.stats.get(stat, 1) - 2)
                continue
            # 找到值 >= 1 的最低格
            floor_pos = 0
            for idx, value in enumerate(track):
                if value >= 1:
                    floor_pos = idx
                    break
            new_pos = max(position - 2, floor_pos)
            player.stat_positions[stat] = new_pos
            player.stats[stat] = track[new_pos]
        player.movement_stopped = True

    def _web_restore(self, engine: Any, player: Any) -> None:
        for stat in ("speed", "might", "sanity", "knowledge"):
            track = engine._stat_track(player, stat)
            position = player.stat_positions.get(stat)
            if track and position is not None:
                player.stat_positions[stat] = min(position + 2, len(track) - 1)
                player.stats[stat] = track[player.stat_positions[stat]]

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """p99：蜘蛛击败探险者改为缚网而非伤害。"""
        if self._kind_of(engine, monster) != "spider_bug":
            return False
        flags = engine._haunt_flags()
        webbed = list(flags.get("webbed", []))
        if str(target.id) in webbed:
            return False  # 已被缚：走正常伤害
        webbed.append(str(target.id))
        flags["webbed"] = webbed
        self._web_lower_traits(engine, target)
        engine._log(f"{target.name} 被蛛丝缠住了！四属性各 -2，动弹不得。")
        engine.check_victory()
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """被缚者不能移动。"""
        if str(player.id) in engine._haunt_flags().get("webbed", []):
            player.movement_stopped = True

    # ------------------------------------------------------------- 虫行为
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.BUG:
            return False
        if self._kind_of(engine, monster) == "roach":
            return True  # p99：蟑螂永不离开厨房（同房攻击由引擎默认处理）
        return False  # 其余虫常规追击

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p28：用杀虫剂击败虫 → 杀死（非击晕）并计数；杀满 3 只其余逃散。"""
        if _monster_id(monster) != self.BUG:
            return False
        attacker = None
        active_id = getattr(engine, "_active_player_id", None)
        if active_id is not None:
            attacker = engine.state.players[active_id]
        if attacker is None or not self._holding_spray(engine, attacker):
            return False  # 无杀虫剂：默认击晕
        monster_id = getattr(monster, "id", None)
        engine.state.monsters = [
            m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
        ]
        engine._advance_haunt_track("bugs_killed", 1)
        engine._log(f"杀虫剂的毒雾让{name_map(engine, monster)}当场蜷缩死去！")
        if engine._haunt_track_value("bugs_killed") >= 3:
            for bug in list(self._bugs(engine)):
                bug_id = getattr(bug, "id", None)
                engine.state.monsters = [
                    m for m in engine.state.monsters if getattr(m, "id", None) != bug_id
                ]
            engine._log("其余的虫子窸窸窣窣地逃出了房子！")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "take_ingredient":
                if not engine.tokens_in_room(player.room_key, self.INGREDIENT):
                    continue
                if player.role == "traitor":
                    if self._holding_spray(engine, player) or len(self._held_ingredients(engine, player)) >= 3:
                        continue  # p99：至多 3 枚配料，或 1 瓶杀虫剂（不可兼有）
            if action.id == "make_spray":
                if player.role != "hero" or len(self._room_ingredient_pool(engine, player.room_key)) < 3:
                    continue  # 三枚配料同房（不拘谁拿着）
            if action.id == "destroy_ingredient":
                if player.role != "traitor":
                    continue
                if not self._held_ingredients(engine, player) and not self._holding_spray(engine, player):
                    continue
            if action.id == "break_webs":
                if not any(
                    str(p.id) in engine._haunt_flags().get("webbed", [])
                    and p.room_key == player.room_key
                    for p in engine.state.players
                ):
                    continue  # 同房要有被缚的探险者
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "take_ingredient":
            token = next(iter(engine.tokens_in_room(player.room_key, self.INGREDIENT)), None)
            if token is None:
                engine._log("这个房间里没有配料。")
                return False
            if player.role == "traitor":
                if self._holding_spray(engine, player) or len(self._held_ingredients(engine, player)) >= 3:
                    engine._log("你拿不下了（至多 3 枚配料或 1 瓶杀虫剂）。")
                    return False
            engine.give_token(token.uid, player.id)
            engine._log(f"{player.name} 收起了{token.label}。")
            return True

        if action_id == "make_spray":
            pool = self._room_ingredient_pool(engine, player.room_key)
            if len(pool) < 3:
                engine._log("需要三枚配料在同一间房（不拘谁拿着）。")
                return False
            flags = engine._haunt_flags()
            # 边沿触发：引擎只在检定成功时应用 set_flags(spray_mixed)，所以"跑过"不等于"配成"
            flags["spray_mixed"] = False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and flags.get("spray_mixed"):
                flags["spray_mixed"] = False
                # 优先消耗放在地上的，再消耗英雄手里的；移出游戏
                for token in pool[:3]:
                    engine.remove_token(token.uid)
                spray = engine.spawn_token(self.SPRAY, label="杀虫剂", role="carried", holder=player.id)
                engine._log(f"{player.name} 调配出了杀虫剂（{spray.label}）！对虫用速度攻击！")
            elif ok:
                engine._log("配方错了味——三枚配料还在，本回合的剧本行动已经用掉。")
            return ok

        if action_id == "destroy_ingredient":
            held = self._held_ingredients(engine, player)
            if held:
                token = held[0]
                engine.remove_token(token.uid)
                engine._advance_haunt_track("ingredients_destroyed", 1)
                engine._log(
                    f"{player.name} 把{token.label}扔进了深渊"
                    f"（被毁配料 {engine._haunt_track_value('ingredients_destroyed')}/4）。"
                )
                engine.check_victory()
                return True
            if self._holding_spray(engine, player):
                spray = engine.tokens_held_by(player.id, self.SPRAY)[0]
                engine.remove_token(spray.uid)
                flags = engine._haunt_flags()
                flags["spray_destroyed"] = True
                engine._log("杀虫剂被毁掉了——英雄们得再配一瓶。")
                return True
            engine._log("你身上没有可销毁的东西。")
            return False

        if action_id == "break_webs":
            webbed_here = [
                p for p in engine.state.players
                if str(p.id) in engine._haunt_flags().get("webbed", [])
                and p.room_key == player.room_key
            ]
            if not webbed_here:
                engine._log("这个房间里没有被缚的探险者。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                flags = engine._haunt_flags()
                freed_ids = {str(p.id) for p in webbed_here}
                flags["webbed"] = [pid for pid in flags.get("webbed", []) if pid not in freed_ids]
                for p in webbed_here:
                    self._web_restore(engine, p)
                    p.movement_stopped = False
                    engine._log(f"{p.name} 挣脱了蛛丝，恢复了自由！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p28：毒杀三只虫，其余逃散 → 英雄胜
        if engine._haunt_track_value("bugs_killed") >= engine._haunt_track_target("bugs_killed"):
            for bug in list(self._bugs(engine)):
                bug_id = getattr(bug, "id", None)
                engine.state.monsters = [
                    m for m in engine.state.monsters if getattr(m, "id", None) != bug_id
                ]
            engine._set_winner("heroes", "最后的巨虫在毒雾中蜷缩死去——其余的逃出了房子。")
            return True
        # p99：四枚配料被毁且英雄没有杀虫剂 → 叛徒胜
        spray_in_play = any(t.kind == self.SPRAY for t in engine.state.tokens)
        if (
            engine._haunt_track_value("ingredients_destroyed") >= engine._haunt_track_target("ingredients_destroyed")
            and not spray_in_play
        ):
            engine._set_winner("traitor", "配料毁尽，杀虫剂无踪——虫群饱餐了一顿。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "喋喋不休的人类成了虫群的粮食。")
            return True
        return True  # 虫群自主行动，叛徒阵亡不结束游戏
