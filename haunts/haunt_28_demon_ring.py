"""DemonRingMode（剧本 28）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class DemonRingMode(GenericModeHandler):
    """剧本 28 所罗门之戒（Ring of King Solomon）。

    权威原文：英雄手册 p39 / 叛徒手册 p110。

    已按原文实现：
        · 数值（p110 页脚，新增 demon_1..demon_5 与 demon_lord 模板）：
          速/力/智 = 2/5/5、3/4/4、4/3/3、5/2/2、6/1/1；领主 1/7/7。
          地狱门房放 领主 + 数量=英雄数的恶魔（按恶魔一、二…顺序）。
        · 地狱门（p110）：无人的事件符号房间，距最近探险者 ≥4 格；
          没有就选最远的（bot 按 (距离, key) 定序，确定性）。
        · 戒指（p39）：作祟由所罗门戒指触发，揭示者（=叛徒）开局持有。
          英雄胜利 = 持戒指击败恶魔领主两次（力量或理智攻击皆可）；
          理智攻击对领主 +2；第一次击败击晕，第二次摧毁；领主攻击戒指
          持有人落败也算一次击败（领主回合由 handler 接管以记这次败北）。
        · 速度攻击免疫（p110）：领主 monster_specs immune_to=["speed"]，
          复用引擎既有免疫（左轮等速度武器打不中它）。
        · 策反（p39）：持戒指对普通恶魔的理智攻击成功 → 恶魔被策反；
          电子版由戒指持有人回合开始自动代跑（移动 + 攻击其他恶魔或叛徒），
          与剧本 21 僵尸代跑同款先例；戒指转给其他英雄控制权随之转移，
          戒指被丢/被叛徒或恶魔拿走 → 恶魔恢复不受控（动态判定）。
          怪物间战斗按引擎惯例"胜=击晕"近似（引擎不追踪怪物伤害）。
        · 抢戒指（p110）：恶魔（含领主）击败戒指持有人且赢 2+ → 改为抢走
          戒指不掉血（on_monster_attack）；恶魔不能使用/交易/丢掉它；
          击败带戒指恶魔的探险者立刻取回（monster_killed_on_defeat）。
        · 胜负（p39/p110）：英雄胜 = 领主被戒指摧毁；叛徒胜 = 英雄全灭。
          叛徒死亡后恶魔照常追杀（怪物回合由本轮最后存活玩家代跑，
          老坑 18 号吸收者）。

    已知简化：
        · 受控恶魔的"移动并攻击"在戒指持有人回合开始自动执行（bot 代跑），
          人类玩家不能逐只手动操控；怪物间胜负以击晕表示（引擎不追踪
          怪物伤害）。
        · 地狱门房没有合法候选的极端局面（事件房全被占/塌）下恶魔不入场，
          该局无法分出胜负（原文未覆盖）。
        · bot 英雄不挑理智攻击打领主（默认徒手力量攻击），拿回戒指前的
          攻略节奏偏慢，属 bot 深度。
    """

    mode = "demon_ring"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = []
        portal = flags.get("portal_room")
        room = engine.state.board.get(portal) if portal else None
        rows.append(f"地狱之门：{room.name if room else '未开启'}")
        if flags.get("lord_destroyed"):
            rows.append("恶魔领主：已被戒指摧毁")
        controlled = len(flags.get("controlled_demons", []))
        if controlled:
            rows.append(f"受控恶魔 {controlled} 只")
        return rows

    LORD = "demon_lord"
    DEMON_TEMPLATES = ("demon_1", "demon_2", "demon_3", "demon_4", "demon_5")

    def __init__(self) -> None:
        self._attack_attrs: dict[str, str] = {}
        self._defeat_ctx: tuple[str, str] | None = None

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("portal_room", None)
        flags.setdefault("lord_destroyed", False)
        flags.setdefault("controlled_demons", [])
        # p110：地狱门 = 无人的事件符号房，距最近探险者 ≥4 格；没有就最远
        alive = [p for p in engine.state.players if not p.dead]
        candidates: list[tuple[int, str]] = []
        for key, room in engine.state.board.items():
            if room.symbol != "event" or engine._is_collapsed(key) or engine.room_occupants(key):
                continue
            dist = min(
                (engine._path_length(key, p.room_key) for p in alive),
                default=99,
            )
            candidates.append((dist, key))
        if not candidates:
            # 兜底（原文未覆盖）：场上没有合格事件房——从牌堆/弃牌堆里找
            # 一间事件符号房强行入场，否则这局永远无法分出胜负
            # （种子 109,4 实测：作祟开始时场上恰好没有事件房）。
            placed_key = ""
            for template_id in sorted(engine.catalog.room_templates):
                template = engine.catalog.room_templates[template_id]
                if template.symbol != "event":
                    continue
                placed_key = engine._ensure_room_in_play(template_id, room_key) or ""
                if placed_key:
                    break
            if not placed_key:
                engine._log("屋里找不到能撑开地狱之门的房间——门没有出现。")
                return
            flags["portal_room"] = placed_key
            engine._log(
                f"屋里本没有能开门的地方——地狱之力硬生生在{engine.state.board[placed_key].name}撕开了门。"
            )
            portal = placed_key
        else:
            far = max(dist for dist, _ in candidates)
            eligible = sorted(key for dist, key in candidates if dist >= 4)
            if not eligible:
                eligible = sorted(key for dist, key in candidates if dist == far)
            portal = eligible[0]
            flags["portal_room"] = portal
            engine._log(f"地板下的五芒星亮起——地狱之门在{engine.state.board[portal].name}打开了。")
        heroes = [p for p in engine.state.players if p.role == "hero"]
        specs = engine._haunt_rule_state().get("monster_specs", {})
        for spec_id in (self.LORD,) + tuple(f"demon_{i}" for i in range(1, len(heroes) + 1)):
            spec = dict(specs.get(spec_id) or {"template_id": spec_id})
            engine._spawn_single_haunt_monster(spec, portal)

    # ----------------------------------------------------------- 状态查询
    def _ring_holder(self, engine: Any) -> Any | None:
        return next(
            (p for p in engine.state.players if "omen_ring" in p.items and not p.dead),
            None,
        )

    def _controlled_ids(self, engine: Any) -> set[str]:
        """受控恶魔集合：仅当戒指在存活英雄手里时生效（p39）。"""
        holder = self._ring_holder(engine)
        if holder is None or holder.role != "hero":
            return set()
        return {str(i) for i in engine._haunt_flags().get("controlled_demons", [])}

    def _steal_ring(self, engine: Any, holder: Any, monster: Any) -> None:
        if "omen_ring" in holder.items:
            holder.items.remove("omen_ring")
            monster.items.append("omen_ring")
            engine._log(f"{monster.name} 击败了{holder.name}并抢走了所罗门戒指（它不会使用，p110）。")

    def _count_lord_defeat(self, engine: Any, killer: Any) -> None:
        value = engine._advance_haunt_track("lord_defeats", 1)
        if value >= 2:
            flags["lord_destroyed"] = True
            lord = next((m for m in engine.state.monsters if _monster_id(m) == self.LORD), None)
            if lord is not None:
                engine._kill_monster(lord, killer=killer)
            engine._log("恶魔领主第二次败在所罗门戒指之下——地狱之门塌缩成了地狱排水口！")
            engine.check_victory()
        else:
            engine._log(f"恶魔领主被击败（{value}/2），暂时被击晕。")

    # ------------------------------------------------- 戒指攻击修正（p39）
    def _prefer_sanity(self, attacker: Any, target: Any) -> bool:
        """持戒指者徒手打恶魔时，是否改用理智攻击。

        p39：持戒指对领主的**理智**攻击 +2；对普通恶魔的**理智**攻击成功
        即策反。真人持戒打恶魔时都会挑这两条路，但引擎的徒手默认是力量，
        所以这里在"理智不比力量差"时才切换——领主另给 +2 折算，
        避免把高力量低理智的角色反而改弱。
        """
        if "omen_ring" not in getattr(attacker, "items", []):
            return False
        stats = getattr(attacker, "stats", None) or {}
        bonus = 2 if _monster_id(target) == self.LORD else 0
        return int(stats.get("sanity", 0)) + bonus >= int(stats.get("might", 0))

    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        # 记录本次攻击属性，供 attack_roll_bonus 判断"理智攻击 +2"。
        # 引擎保证同一攻击里先调本钩子再调加值钩子。
        attr = default_attr
        tid = _monster_id(target)
        if default_attr == "might" and (tid == self.LORD or tid in self.DEMON_TEMPLATES):
            if self._prefer_sanity(attacker, target):
                attr = "sanity"
        self._attack_attrs[str(getattr(attacker, "id", ""))] = attr
        return attr if attr != default_attr else None

    def attack_roll_bonus(self, engine: Any, attacker: Any, target: Any) -> int:
        if _monster_id(target) != self.LORD:
            return 0
        if "omen_ring" not in getattr(attacker, "items", []):
            return 0
        if self._attack_attrs.get(str(getattr(attacker, "id", ""))) != "sanity":
            return 0
        return 2  # p39：持戒指对领主的理智攻击 +2

    # --------------------------------------------------- 击败结算（p39/p110）
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        tid = _monster_id(monster)
        if tid not in self.DEMON_TEMPLATES and tid != self.LORD:
            return False
        # p110：击败带戒指的恶魔 → 立刻取回戒指
        if "omen_ring" in (monster.items or []) and "omen_ring" not in getattr(attacker, "items", []):
            monster.items.remove("omen_ring")
            attacker.items.append("omen_ring")
            engine._log(f"{getattr(attacker, 'name', '探险者')} 从{monster.name}手里夺回了所罗门戒指！")
        self._defeat_ctx = (str(getattr(attacker, "id", "")), attack_attr)
        if tid != self.LORD:
            return False  # 普通恶魔不持戒指击败 = 照常击晕（是否策反看 on_monster_defeated）
        if "omen_ring" in getattr(attacker, "items", []):
            value = engine._advance_haunt_track("lord_defeats", 1)
            if value >= 2:
                engine._haunt_flags()["lord_destroyed"] = True
                engine._log("恶魔领主第二次败在所罗门戒指之下——地狱之门塌缩成了地狱排水口！")
                return True  # 引擎执行 _kill_monster
            engine._log(f"恶魔领主被击败（{value}/2），暂时被击晕。")
        return False  # 不持戒指的击败照常击晕，不计数

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        tid = _monster_id(monster)
        ctx = self._defeat_ctx
        self._defeat_ctx = None
        if tid in self.DEMON_TEMPLATES and ctx is not None:
            attacker_id, attack_attr = ctx
            holder = self._ring_holder(engine)
            if (
                holder is not None
                and str(holder.id) == attacker_id
                and attack_attr == "sanity"
            ):
                controlled = engine._haunt_flags().setdefault("controlled_demons", [])
                if monster.id not in controlled:
                    controlled.append(monster.id)
                engine._log(f"{monster.name} 在所罗门戒指的力量面前俯首——它被{holder.name}策反了！")
                return True  # 已处理：策反而非击晕
        return False  # 默认击晕

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        # p110：恶魔（含领主）赢戒指持有人 2+ → 抢戒指代替伤害
        if amount >= 2 and "omen_ring" in getattr(target, "items", []):
            self._steal_ring(engine, target, monster)
            return True
        return False

    # --------------------------------------------------------- 怪物回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        tid = _monster_id(monster)
        if tid == self.LORD:
            self._lord_turn(engine, monster)
            return True
        if tid in self.DEMON_TEMPLATES and monster.id in self._controlled_ids(engine):
            return True  # 受控恶魔由戒指持有人在回合开始代跑
        return False  # 未受控恶魔：引擎默认全速追最近英雄并攻击

    def _lord_turn(self, engine: Any, lord: Any) -> None:
        target = engine._find_monster_target(lord)
        if target is None:
            return
        if lord.room_key != target.room_key:
            steps = engine.roll_dice(max(1, lord.speed), "恶魔领主移动")
            path = engine._shortest_path(lord.room_key, target.room_key)
            if len(path) > 1:
                lord.room_key = path[min(len(path) - 1, max(1, steps))]
                engine._log(f"{lord.name} 移动到 {engine.state.board[lord.room_key].name}。")
        if lord.room_key != target.room_key:
            return
        attack_roll = engine._roll_monster_attack(lord, "might")
        target_roll = engine._roll_attack(target, "might")
        engine._log(f"{lord.name} 攻击 {target.name}：{attack_roll} 对 {target_roll}。")
        if attack_roll > target_roll:
            diff = attack_roll - target_roll
            if diff >= 2 and "omen_ring" in target.items:
                self._steal_ring(engine, target, lord)
            else:
                engine._deal_damage(target, "physical", diff, source=lord.name)
        elif attack_roll < target_roll:
            engine._stun_monster(lord, 1)
            if "omen_ring" in target.items:
                # p39：领主攻击戒指持有人落败也算一次击败
                self._count_lord_defeat(engine, killer=target)
        else:
            engine._log("平手。")

    # ------------------------------------------------- 受控恶魔代跑（p39）
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead or player.role != "hero" or "omen_ring" not in player.items:
            return
        controlled_ids = self._controlled_ids(engine)
        if not controlled_ids:
            return
        for demon in list(engine.state.monsters):
            if _monster_id(demon) not in self.DEMON_TEMPLATES:
                continue
            if str(demon.id) not in controlled_ids or demon.stunned_turns > 0:
                continue
            self._controlled_demon_act(engine, demon)

    def _controlled_demon_act(self, engine: Any, demon: Any) -> None:
        enemies: list[Any] = [
            m
            for m in engine.state.monsters
            if _monster_id(m) in self.DEMON_TEMPLATES
            and m is not demon
            and str(m.id) not in self._controlled_ids(engine)
        ]
        enemies += [p for p in engine.state.players if p.role == "traitor" and not p.dead]
        if not enemies:
            return
        nearest = min(enemies, key=lambda e: engine._path_length(demon.room_key, e.room_key))
        if demon.room_key != nearest.room_key:
            steps = engine.roll_dice(max(1, demon.speed), "受控恶魔移动")
            path = engine._shortest_path(demon.room_key, nearest.room_key)
            if len(path) > 1:
                demon.room_key = path[min(len(path) - 1, max(1, steps))]
                engine._log(f"受控的{demon.name} 移动到 {engine.state.board[demon.room_key].name}。")
        if demon.room_key != nearest.room_key:
            return
        if isinstance(getattr(nearest, "role", None), str):
            attack_roll = engine._roll_monster_attack(demon, "might")
            target_roll = engine._roll_attack(nearest, "might")
            engine._log(f"受控的{demon.name} 攻击 {nearest.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._deal_damage(nearest, "physical", attack_roll - target_roll, source=demon.name)
            elif attack_roll < target_roll:
                engine._stun_monster(demon, 1)
            else:
                engine._log("平手。")
        else:
            # 怪物间战斗：引擎不追踪怪物伤害，按惯例"胜=击晕"近似
            attack_roll = engine._roll_monster_attack(demon, "might")
            target_roll = engine._roll_monster_attack(nearest, "might")
            engine._log(f"受控的{demon.name} 攻击 {nearest.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._stun_monster(nearest, 1)
            elif attack_roll < target_roll:
                engine._stun_monster(demon, 1)
            else:
                engine._log("平手。")

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄 bot 的推进目标：先把戒指拿到手，再持戒去敲恶魔领主。

        旧实现只有"叛徒持戒时全队围攻他"一条，戒指一旦易主就退回通用追怪
        （打谁全看谁近）。p39/p110 的戒指流转有好几种分支，逐条给目标：
          · 自己持戒 → 直奔恶魔领主（只有它能被戒指摧毁；持有承诺加成会压过
            "追最近的怪"，避免被半路的普通恶魔牵走）；
          · 叛徒持戒 → 全队围攻叛徒（抢戒指）；
          · 恶魔持戒（p110 抢走）→ 去打那只恶魔夺回来；
          · 戒指随死亡掉在房间里 → 去那间房捡起来。
        """
        if player.role != "hero" or player.dead:
            return []
        holder = self._ring_holder(engine)
        if holder is not None and holder.id == player.id:
            lord = next(
                (m for m in engine.state.monsters if _monster_id(m) == self.LORD),
                None,
            )
            return ["__room__" + lord.room_key] if lord is not None else []
        if holder is not None:
            return ["__room__" + holder.room_key] if holder.role == "traitor" else []
        carrier = next(
            (m for m in engine.state.monsters if "omen_ring" in (m.items or [])),
            None,
        )
        if carrier is not None:
            return ["__room__" + carrier.room_key]
        ring_room = next(
            (key for key, items in engine.state.room_items.items() if "omen_ring" in items),
            None,
        )
        return ["__room__" + ring_room] if ring_room else []

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p39 英雄胜：领主被戒指摧毁
        if flags.get("lord_destroyed"):
            engine._set_winner("heroes", "所罗门戒指燃起烈焰——恶魔领主被拖回了地狱。")
            return True
        # p110 叛徒胜：英雄全灭
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "英雄们的尸体堆成了恶魔领主的血肉王座。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后恶魔照常追杀
