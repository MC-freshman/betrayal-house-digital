"""ForAThousandYearsMode（剧本 59）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
)


class ForAThousandYearsMode(GenericModeHandler):
    """剧本 59「For a Thousand Years / 千年之约」（英雄手册 p70 / 叛徒手册 p141）。

    千年前的诅咒封存了王室血脉；如今王族徽章重见天日，把它挂回国王
    雕像的脖子上就能破咒。可惜叛徒早已布好陷阱——女巫和她的使魔们
    正等着抢走徽章，把它扔下塔楼，让诅咒永世长存。

    · 开局（p141）：女巫 + 雕像令牌放**带预兆图标的房间**（除作祟房，
      无则任意房）；英雄数 ≥3 时熊放带预兆图标的空房间（无则女巫房）、
      ≥4 时猫放女巫房、≥5 时信徒放叛徒房。徽章（omen_medallion）确保
      在叛徒手里（作祟由徽章触发时本来就在；不在则补给他，47 号骷髅
      兜底同口径）。
    · 徽章归属（p141）：flags["medallion_holder"] 统一追踪
      （"traitor:<id>" / "monster:<id>" / "hero:<id>" / None=在地上）；
      英雄持有时同时把卡放进 items（供 UI 与检定），转移时同步。
    · 持徽章移动（p70）：每回合最多移动 2 格（on_player_moved 计数 +
      movement_stopped）；拾取当回合可再走最多 2 格。
    · 放置徽章（p70）：持徽章者在雕像房做速度掷骰，结果 ≥ 房间内未
      昏迷对手数（叛徒+怪物）的两倍 → 挂上雕像 → 英雄胜。
    · 摧毁徽章（p141）：持有者（叛徒或怪物）在塔楼或地下湖结束回合
      → 扔下徽章 → 叛徒胜（on_turn_end 检查，路过不算）。
    · 怪物攻击（p141）：女巫以知识攻击（目标以理智防御、精神伤害）；
      熊力量攻击多掷 2 骰；猫以速度攻击（目标以速度防御、物理伤害）；
      猫/信徒造成 ≥2 伤害且目标持徽章 → 偷走徽章（bot 总是偷）。
    · 徽章易手：怪物可拾取地上的徽章；怪物被击败/击晕时徽章掉在地上
      （英雄拾取即转为英雄持有）；英雄持有时被偷则同步移出 items。
    · 胜负（p70/p141）：英雄胜 = 徽章挂上雕像；叛徒胜 = 持有者在塔楼/
      地下湖结束回合扔下徽章，或英雄全灭。叛徒出局时女巫与使魔继续
      行动（7/8 号口径），故吸收兜底。

    已知简化：
        · "拖拽昏迷怪物"未建模（引擎无怪物跟随移动机制）。
        · 怪物探索新房间未建模（复用引擎常规怪物移动，不探索）。
        · 熊/猫禁用特殊通道、猫坠落即晕未建模（引擎怪物走常规门移动）。
        · 徽章"只在回合开始可丢弃/交易"与"狗不能携带"未建模
          （引擎没有怪物/同伴主动持卡的通用层）。
        · 怪物持徽章时"不能丢弃/交易，但可被英雄偷回"简化为：
          怪物被击败或击晕时徽章掉在地上，英雄拾取即转持有。
        · 火把令牌/事件掷骰等无关卡牌不动。
    """

    mode = "badge_curse"

    WITCH = "curse_witch"
    BEAR = "curse_bear"
    CAT = "curse_cat"
    CULTIST = "curse_cultist"
    MEDALLION = "omen_medallion"
    STATUE = "royal_statue"
    DOOM_ROOMS = ("tower", "underground_lake")
    MEDALLION_MOVE_CAP = 2

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("medallion_holder", None)
        flags.setdefault("medallion_steps", {})
        flags.setdefault("statue_key", None)

        # p141：女巫 + 雕像放带预兆图标的房间（除作祟房）
        omen_rooms = [
            k
            for k, r in sorted(engine.state.board.items())
            if r.symbol == "omen" and k != room_key
        ]
        witch_room = omen_rooms[0] if omen_rooms else room_key
        flags["statue_key"] = witch_room
        engine.spawn_token(self.STATUE, label="国王雕像", room_key=witch_room)
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.WITCH, {"template_id": self.WITCH, "name": "诅咒女巫"})
        )
        engine._spawn_single_haunt_monster(spec, witch_room)
        engine._log("女巫在雕像旁现身——她要亲眼看着诅咒永世长存。")

        players = len(engine.state.players)
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        specs = engine._haunt_rule_state().get("monster_specs", {})

        # p141：英雄数 ≥3 → 熊（预兆图标的空房间，无则女巫房）
        if hero_count >= 3:
            bear_room = next(
                (
                    k
                    for k in omen_rooms
                    if not any(p.room_key == k for p in engine.state.players)
                    and not any(m.room_key == k for m in engine.state.monsters)
                ),
                witch_room,
            )
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.BEAR, {"template_id": self.BEAR, "name": "女巫之熊"})),
                bear_room,
            )
        # p141：英雄数 ≥4 → 猫（女巫房）
        if hero_count >= 4:
            engine._spawn_single_haunt_monster(
                dict(specs.get(self.CAT, {"template_id": self.CAT, "name": "女巫之猫"})),
                witch_room,
            )
        # p141：英雄数 ≥5 → 信徒（叛徒房）
        if hero_count >= 5:
            traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
            if traitor is not None:
                engine._spawn_single_haunt_monster(
                    dict(
                        specs.get(
                            self.CULTIST, {"template_id": self.CULTIST, "name": "女巫信徒"}
                        )
                    ),
                    traitor.room_key,
                )

        # p141：徽章确保在叛徒手里
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            if self.MEDALLION not in traitor.items:
                traitor.items.append(self.MEDALLION)
            flags["medallion_holder"] = f"traitor:{traitor.id}"
        # 塔楼/地下湖是叛徒胜线的投掷点，不在场就从牌堆拉进来
        for template_id in self.DOOM_ROOMS:
            engine._ensure_room_in_play(template_id, room_key)
        engine._log("王室徽章在叛徒手里闪闪发光——把它挂回雕像，就能破咒。")

    # ------------------------------------------------------- 徽章归属
    def _statue_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("statue_key")

    def _holder_id(self, flags: dict, prefix: str) -> str | None:
        holder = flags.get("medallion_holder")
        if holder and holder.startswith(prefix + ":"):
            return holder.split(":", 1)[1]
        return None

    def _hero_holds(self, engine: Any, player: Any) -> bool:
        self._sync_medallion(engine)
        flags = engine._haunt_flags()
        holder = flags.get("medallion_holder")
        return holder == f"hero:{player.id}" or self.MEDALLION in player.items

    def _sync_medallion(self, engine: Any) -> None:
        """引擎偷窃/拾取只改 items，必须把 flags 持有者同步过来。"""
        flags = engine._haunt_flags()
        for player in engine.state.players:
            if player.dead:
                continue
            if self.MEDALLION not in getattr(player, "items", []):
                continue
            prefix = "traitor" if player.role == "traitor" else "hero"
            flags["medallion_holder"] = f"{prefix}:{player.id}"
            return
        for key, cards in engine.state.room_items.items():
            if self.MEDALLION in cards:
                flags["medallion_holder"] = None
                return
        holder = flags.get("medallion_holder") or ""
        if holder.startswith("monster:"):
            return
        flags["medallion_holder"] = None

    def bot_wants_steal(self, engine: Any, attacker: Any, target: Any) -> str | None:
        """p70/p141：徽章是胜负钥匙——打赢了就从对方身上抢，默认不偷会整局拿不到。"""
        if self.MEDALLION in getattr(target, "items", []):
            return self.MEDALLION
        return None

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        self._sync_medallion(engine)

    def on_player_died(self, engine: Any, player: Any) -> None:
        self._sync_medallion(engine)

    def _give_to_hero(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        flags["medallion_holder"] = f"hero:{player.id}"
        flags["medallion_steps"] = {}
        if self.MEDALLION not in player.items:
            player.items.append(self.MEDALLION)

    def _drop_to_floor(self, engine: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["medallion_holder"] = None
        engine.state.room_items.setdefault(room_key, []).append(self.MEDALLION)
        engine._log("徽章哐当一声掉在了地上。")

    def _medallion_on_floor(self, engine: Any) -> str | None:
        flags = engine._haunt_flags()
        if flags.get("medallion_holder") is not None:
            return None
        for key, cards in engine.state.room_items.items():
            if self.MEDALLION in cards:
                return key
        return None

    # ------------------------------------------------------- 持徽章移动
    def on_player_moved(self, engine: Any, player: Any) -> None:
        """p70：持徽章的英雄每回合最多移动 2 格（叛徒持徽章不限速）。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        if player.role != "hero" or not self._hero_holds(engine, player):
            return
        flags = engine._haunt_flags()
        steps = dict(flags.get("medallion_steps", {}))
        used = int(steps.get(str(player.id), 0)) + 1
        steps[str(player.id)] = used
        flags["medallion_steps"] = steps
        if used >= self.MEDALLION_MOVE_CAP:
            player.movement_stopped = True
            player.steps_remaining = 0
            engine._log("徽章沉得惊人——带着它走不动了（本回合最多 2 格）。")

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """回合开始重置持徽章步数（p70：拾取当回合也可再走 2 格）。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        self._sync_medallion(engine)
        flags = engine._haunt_flags()
        steps = dict(flags.get("medallion_steps", {}))
        if str(player.id) in steps:
            steps.pop(str(player.id))
            flags["medallion_steps"] = steps

    # ------------------------------------------------------- 徽章易手
    def _steal_from_hero(self, engine: Any, monster: Any, hero: Any) -> bool:
        """p141：猫/信徒造成 ≥2 伤害时抢走徽章。"""
        flags = engine._haunt_flags()
        if not self._hero_holds(engine, hero):
            return False
        hero.items = [c for c in hero.items if c != self.MEDALLION]
        flags["medallion_holder"] = f"monster:{monster.id}"
        engine._log(f"{monster.name} 一把抢走了王室徽章！")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p141：持徽章的怪物被击败/击晕时，徽章掉在地上（英雄可拾取）。"""
        flags = engine._haunt_flags()
        if flags.get("medallion_holder") == f"monster:{monster.id}":
            self._drop_to_floor(engine, monster.room_key)
        return False  # 噩梦式全权接管不需要——普通击晕流程照走

    # ------------------------------------------------------- 噩梦式怪物攻击
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """p141：怪物可拾取地上的徽章。"""
        template = getattr(monster, "template_id", "")
        if template not in (self.WITCH, self.BEAR, self.CAT, self.CULTIST):
            return False
        self._sync_medallion(engine)
        flags = engine._haunt_flags()
        floor_key = self._medallion_on_floor(engine)
        if floor_key is not None and floor_key == monster.room_key:
            cards = engine.state.room_items.get(floor_key, [])
            if self.MEDALLION in cards:
                cards.remove(self.MEDALLION)
                flags["medallion_holder"] = f"monster:{monster.id}"
                engine._log(f"{monster.name} 捡起了地上的王室徽章！")
        if flags.get("medallion_holder") == f"monster:{monster.id}":
            doom = [
                key
                for key, room in engine.state.board.items()
                if room.template_id in self.DOOM_ROOMS
            ]
            if doom and monster.room_key not in doom:
                dest = min(doom, key=lambda k: engine._path_length(monster.room_key, k))
                path = engine._shortest_path(monster.room_key, dest)
                if len(path) > 1:
                    monster.room_key = path[1]
                    room = engine.state.board.get(monster.room_key)
                    engine._log(
                        f"{monster.name} 带着徽章赶往 {room.name if room else dest}。"
                    )
            return True
        return False

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p141：女巫知识攻击/熊力量+2 骰/猫速度攻击；打伤持徽章者 ≥2 可抢走。"""
        template = getattr(monster, "template_id", "")
        if template not in (self.WITCH, self.BEAR, self.CAT, self.CULTIST):
            return False
        flags = engine._haunt_flags()
        if flags.get("medallion_holder") == f"monster:{monster.id}":
            # 持徽章的怪物不攻击，专心往塔楼/地下湖跑（p141 无此明文，取合理化）
            return True
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        if template == self.WITCH:
            roll = engine._roll_monster_attack(monster, "knowledge")
            defense = engine._roll_attack(target, "sanity")
            engine._log(f"诅咒女巫的咒文缠上 {engine._player_label(target)}：{roll} 对 {defense}。")
            if roll > defense:
                engine._deal_damage(target, "mental", roll - defense, source="女巫")
            elif roll < defense:
                engine._stun_monster(monster, 1)
            return True
        if template == self.CAT:
            roll = engine._roll_monster_attack(monster, "speed")
            defense = engine._roll_attack(target, "speed")
            engine._log(f"女巫之猫猛扑 {engine._player_label(target)}：{roll} 对 {defense}。")
        else:  # 熊：力量攻击多掷 2 骰
            roll = engine._roll_monster_attack(monster, "might") + engine.roll_dice(
                2, "熊之蛮力"
            )
            defense = engine._roll_attack(target, "might")
            engine._log(f"女巫之熊横冲直撞：{roll} 对 {defense}。")
        if roll > defense:
            damage = roll - defense
            can_steal = template in (self.CAT, self.CULTIST) and damage >= 2 and self._hero_holds(
                engine, target
            )
            if can_steal:
                self._steal_from_hero(engine, monster, target)
            else:
                engine._deal_damage(target, "physical", damage, source=monster.name)
        elif roll < defense:
            engine._stun_monster(monster, 1)
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        statue_key = self._statue_room(engine)
        for action in actions:
            if getattr(action, "id", "") == "place_medallion":
                if not (
                    self._hero_holds(engine, player)
                    and statue_key is not None
                    and player.room_key == statue_key
                ):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "place_medallion":
            return self._place_medallion(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _place_medallion(self, engine: Any, player: Any) -> bool:
        """p70：速度掷骰 ≥ 房间内未昏迷对手数的两倍 → 挂上雕像 → 英雄胜。"""
        statue_key = self._statue_room(engine)
        if statue_key is None or player.room_key != statue_key:
            return False
        if not self._hero_holds(engine, player):
            return False
        opponents = sum(
            1
            for m in engine.state.monsters
            if m.room_key == statue_key and m.stunned_turns <= 0
        ) + sum(
            1
            for p in engine.state.players
            if p.role == "traitor" and not p.dead and p.room_key == statue_key
        )
        threshold = 2 * opponents
        roll = engine._resolve_check(player, "speed", threshold, "挂上王室徽章")
        if not roll:
            engine._log(
                f"雕像前守着 {opponents} 个敌人（需 ≥{threshold}）——徽章没能挂上去。"
            )
            return False
        engine._log("徽章稳稳挂上了雕像的脖颈——诅咒应声而碎，女巫与使魔化作尘烟！")
        engine._set_winner("heroes", "千年的诅咒破除了——房子恢复了旧日的荣光。")
        return True

    def _holder_in_doom_room(self, engine: Any) -> bool:
        """持徽章的叛徒/怪物此刻是否站在塔楼或地下湖。"""
        holder = engine._haunt_flags().get("medallion_holder", "") or ""
        prefix, _, hid = holder.partition(":")
        if prefix == "traitor":
            owner = next((p for p in engine.state.players if p.id == hid), None)
            room_key = owner.room_key if owner is not None else None
        elif prefix == "monster":
            owner = next((m for m in engine.state.monsters if m.id == hid), None)
            room_key = owner.room_key if owner is not None else None
        else:
            return False
        room = engine.state.board.get(room_key) if room_key else None
        return room is not None and room.template_id in self.DOOM_ROOMS

    def _throw_medallion(self, engine: Any) -> bool:
        """p141：在塔楼/地下湖结束回合 → 扔下徽章 → 叛徒胜。"""
        if engine.state.winner:
            return True
        if not self._holder_in_doom_room(engine):
            return False
        engine._set_winner("traitor", "王室徽章被扔进了深渊——诅咒将延续一千年。")
        return True

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p141：持徽章者结束回合时才扔；怪物回合由叛徒（或本轮末尾）代跑。"""
        if engine.state.phase != "HAUNT_PHASE" or engine.state.winner:
            return
        self._sync_medallion(engine)
        holder = engine._haunt_flags().get("medallion_holder", "") or ""
        prefix, _, hid = holder.partition(":")
        if prefix == "traitor" and player.id == hid:
            self._throw_medallion(engine)
            return
        if prefix == "monster":
            traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
            if traitor is not None and not traitor.dead:
                if player.id == traitor.id:
                    self._throw_medallion(engine)
            elif _is_last_in_round(engine, player):
                self._throw_medallion(engine)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p70：徽章挂上雕像 → 英雄胜（在 _place_medallion 里已判）
        # p141：英雄全灭 → 叛徒胜。路过塔楼/湖不算赢，必须结束回合才扔。
        if not heroes_alive:
            engine._set_winner("traitor", "最后的继承人倒下了——血脉永埋尘土。")
            return True
        # 吸收兜底：叛徒出局时女巫与使魔继续行动（7/8 号怪物自主口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def _doom_room_keys(self, engine: Any) -> list[str]:
        return [
            f"__room__{key}"
            for key, room in engine.state.board.items()
            if room.template_id in self.DOOM_ROOMS
        ]

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """没拿着徽章时，挂徽章不能当寻路目标——否则全员扎进雕像房，从不去抢叛徒。"""
        if action_id == "place_medallion":
            return not self._hero_holds(engine, player)
        return False

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """徽章不在这只怪手里时，别专门去追女巫/使魔。

        例外：自己拿着徽章、怪就堵在雕像房——不打就永远挂不上去。真人会先清场再挂。
        """
        if getattr(player, "role", None) != "hero":
            return False
        template = getattr(target, "template_id", "")
        if template not in (self.WITCH, self.BEAR, self.CAT, self.CULTIST):
            return False
        holder = engine._haunt_flags().get("medallion_holder", "") or ""
        if holder == f"monster:{getattr(target, 'id', '')}":
            return False
        if self._hero_holds(engine, player):
            statue = self._statue_room(engine)
            if statue and getattr(target, "room_key", None) == statue:
                return False
        return True

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """持徽章就别在原地过夜：英雄赶去雕像，叛徒赶去塔楼/湖。"""
        if player.dead:
            return False
        self._sync_medallion(engine)
        if self._hero_holds(engine, player):
            statue = self._statue_room(engine)
            return statue is None or player.room_key != statue
        holder = engine._haunt_flags().get("medallion_holder", "") or ""
        if player.role == "traitor" and holder == f"traitor:{player.id}":
            return not self._holder_in_doom_room(engine)
        return False

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set:
        """持徽章的英雄每回合只能走 2 格，别进有未晕怪物的房间过夜。雕像除外。"""
        if player.dead or player.role != "hero" or not self._hero_holds(engine, player):
            return set()
        statue = self._statue_room(engine)
        hazards = set()
        for monster in engine.state.monsters:
            if monster.stunned_turns > 0 or not monster.room_key:
                continue
            if statue is not None and monster.room_key == statue:
                continue
            hazards.add(monster.room_key)
        return hazards

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        self._sync_medallion(engine)
        holder = engine._haunt_flags().get("medallion_holder", "") or ""
        if player.role == "traitor":
            if holder == f"traitor:{player.id}":
                return self._doom_room_keys(engine)
            if holder.startswith("hero:"):
                hero = next(
                    (p for p in engine.state.players if p.id == holder.split(":", 1)[1]),
                    None,
                )
                if hero is not None and not hero.dead:
                    return [f"__room__{hero.room_key}"]
            floor_key = self._medallion_on_floor(engine)
            if floor_key is not None:
                return [f"__room__{floor_key}"]
            return []
        if player.role != "hero":
            return []
        statue_key = self._statue_room(engine)
        if self._hero_holds(engine, player) and statue_key is not None:
            return [f"__room__{statue_key}"]
        floor_key = self._medallion_on_floor(engine)
        if floor_key is not None:
            return [f"__room__{floor_key}"]
        if holder.startswith("monster:"):
            monster = next(
                (m for m in engine.state.monsters if m.id == holder.split(":", 1)[1]), None
            )
            if monster is not None:
                return [f"__room__{monster.room_key}"]
        if holder.startswith("traitor:"):
            traitor = next((p for p in engine.state.players if p.id == holder.split(":", 1)[1]), None)
            if traitor is not None and not traitor.dead:
                return [f"__room__{traitor.room_key}"]
        if holder.startswith("hero:") and statue_key is not None:
            # 队友拿着徽章：去雕像会合。返回空会掉进 key_rooms 保底（塔楼/湖），
            # 真人不会在自己人护送徽章时往深渊跑。
            return [f"__room__{statue_key}"]
        return []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        holder = flags.get("medallion_holder", "")
        if holder.startswith("hero:"):
            who = "英雄手里"
        elif holder.startswith("traitor:"):
            who = "叛徒手里"
        elif holder.startswith("monster:"):
            who = "怪物手里"
        else:
            who = "掉在地上"
        lines = [f"王室徽章：{who}。"]
        statue_key = self._statue_room(engine)
        if statue_key is not None:
            lines.append(f"雕像位于：{engine.state.board[statue_key].name}。")
        return lines
