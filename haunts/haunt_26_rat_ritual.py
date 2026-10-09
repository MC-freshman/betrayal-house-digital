"""RatRitualMode（剧本 26）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class RatRitualMode(GenericModeHandler):
    """剧本 26 鼠祭（Pay the Piper）。

    权威原文：英雄手册 p37 / 叛徒手册 p108。

    已按原文实现：
        · 数值：老鼠 Speed 3 / Might 2 / Sanity 1（p108 页脚，新增 rat 模板
          ——骨架此前用 spider 冒充）。
        · 开局（p37/p108）：叛徒（鼠人）仍在场；属性低于初始值的先恢复到
          初始值，然后每项属性 +1。布置老鼠之前，先把身处五芒星室的探险者
          挪去邻格房间（不需要门相连）。
        · 老鼠（p108）：数量 = 玩家数 × 2，放进有符号（事件/物品/预兆）的
          未被占据房间；多于房间从头叠放，少于房间取前 N 间（bot 按 key 序
          确定，原版由叛徒任选）。
        · 老鼠战斗（p37/p108）：被击败即死亡（monster_killed_on_defeat）；
          同房间 ≥2 只 awake 老鼠合力攻击——力量相加、封顶 8 骰，对单一目标
          掷骰对决，失败不受伤（p108 明文）。
        · 五芒星室（p37/p108）：英雄与老鼠都不能进入——引擎新钩子
          room_entry_blocked 过滤英雄的移动选项、探索抽到该模板直接弃掉换
          一张；老鼠寻路绕开。叛徒进室后不受攻击（attack_allowed 闸门），
          并在 on_enter_room 里记 traitor_reached。
        · 仪式（p108）：五芒星室内理智 3+，成功 +1 理智检定轨道并把一只
          "可用"老鼠放到五芒星室邻格（可用 = 初始 2×N 池中不在场的老鼠，
          即被杀死的会回流）。所需次数 3-4 人 5 / 5-6 人 4（轨道 target
          固定 5，实际判定按人数在 check_victory 里算）。
        · 胜负（p37/p108）：英雄胜 = 杀光所有老鼠，或在叛徒抵达五芒星室
          之前杀死他；叛徒胜 = 仪式完成或英雄全灭。叛徒在五芒星室内被
          杀死不可能发生（免伤闸门）；他若在进室前被杀即英雄胜，
          吸收引擎「叛徒死亡→英雄胜」兜底（老坑 16 号吸收者）。

    已知简化：
        · 老鼠布置/叠放/仪式回流邻格由 bot 按 key 序决定，原版由叛徒任选。
        · p108 布点未明文排除五芒星室，但「英雄与老鼠都进不去」意味着放在
          里面的老鼠永远杀不掉、英雄「杀光老鼠」的胜利条件会被锁死——
          故布点排除五芒星室（校准决定）。
        · 单只老鼠攻击落败：原文应按差值受物理伤害（可能死），引擎不追踪
          怪物伤害，按既有惯例用「击晕一回合」表示攻击方受挫——只有被
          英雄击败时才按 p108「被击败即死」处理。
        · 「叛徒在五芒星室不受任何影响」以攻击闸门实现；物品/特殊能力对
          他的边界影响未逐一建模（bot 英雄只有普攻）。
    """

    mode = "rat_ritual"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        rats = self._rats(engine)
        rows = [f"场上老鼠 {len(rats)} 只（须清光）"]
        if engine._haunt_flags().get("traitor_reached"):
            rows.append("叛徒已进入五芒星室")
        return rows

    RAT = "rat"
    PENTAGRAM = "pentagram_chamber"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("traitor_reached", False)
        flags["rats_placed"] = False
        flags.setdefault("rat_pool", 0)
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p37：布置老鼠之前，先把五芒星室里的探险者挪去邻格（不需要门）
        penta_key = self._pentagram_key(engine)
        if penta_key:
            for person in engine.state.players:
                if person.dead or person.room_key != penta_key:
                    continue
                dest = next(
                    (
                        k
                        for k in sorted(engine._grid_neighbors(penta_key))
                        if k != penta_key and not engine._is_collapsed(k)
                    ),
                    "",
                )
                if dest:
                    person.room_key = dest
                    engine._log(f"五芒星室里的符号开始发烫——{person.name} 被挪到了隔壁。")
        # p108：鼠人强化——属性先恢复初始值，再每项 +1
        if traitor is not None:
            self._boost_traitor(engine, traitor)
        # p108：老鼠 = 玩家数 × 2，放进有符号的未被占据房间
        count = 2 * len(engine.state.players)
        flags["rat_pool"] = count
        spec = self._rat_spec(engine)
        eligible = sorted(
            key
            for key, room in engine.state.board.items()
            if room.symbol in ("event", "item", "omen")
            and room.template_id != self.PENTAGRAM
            and not engine._is_collapsed(key)
            and not engine.room_occupants(key)
        )
        placed = 0
        if eligible:
            for index in range(count):
                # 少于房间 → 取前 N 间；多于房间 → 从头叠放（bot 确定性策略）
                target = eligible[index % len(eligible)]
                if engine._spawn_single_haunt_monster(spec, target) is None:
                    break
                placed += 1
        # 零放置不能置真：check_victory 用「已布置 且 场上无老鼠」判英雄胜，
        # 若所有有符号房间都被占据/塌陷，0 只老鼠会被误判成「杀光老鼠」。
        flags["rats_placed"] = placed > 0
        engine._log(f"{placed} 只老鼠从墙缝与踢脚板下涌了出来。")
        if placed == 0:
            engine._log("没有可用的房间安置老鼠——它们仍在墙里蠢动。")

    def _boost_traitor(self, engine: Any, traitor: Any) -> None:
        face = engine.catalog.characters.get(traitor.character_id)
        if face is None:
            return
        for stat in ("might", "speed", "sanity", "knowledge"):
            start = face.stats.get(stat)
            if start is None:
                continue
            track = engine._stat_track(traitor, stat)
            if track is not None:
                if traitor.stats[stat] < start:
                    idx = next((i for i, v in enumerate(track) if v >= start), len(track) - 1)
                    traitor.stat_positions[stat] = idx
                    traitor.stats[stat] = track[idx]
                # 按数值 +1（跳过同值格），而不是按格 +1——轨道常有重复值
                target_value = traitor.stats[stat] + 1
                idx = next((i for i, v in enumerate(track) if v >= target_value), len(track) - 1)
                traitor.stat_positions[stat] = idx
                traitor.stats[stat] = track[idx]
            else:
                traitor.stats[stat] = max(traitor.stats[stat], start) + 1
        engine._log(f"{traitor.name} 的皮下长出了灰色的绒毛——每项属性提升 1 点（p108）。")

    # ----------------------------------------------------------- 状态查询
    def _rats(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.RAT]

    def _pentagram_key(self, engine: Any) -> str:
        return next(
            (k for k, room in engine.state.board.items() if room.template_id == self.PENTAGRAM),
            "",
        )

    def _rat_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.RAT) or {"template_id": self.RAT, "name": "老鼠"})

    def _ritual_needed(self, engine: Any) -> int:
        return 5 if len(engine.state.players) <= 4 else 4  # p108：3-4 人 5 次，5-6 人 4 次

    # ------------------------------------------------- 进入限制与叛徒免疫
    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        template_id = getattr(room, "template_id", None) or getattr(room, "id", "")
        if template_id != self.PENTAGRAM:
            return False
        # p37/p108：英雄与老鼠不能进入五芒星室（叛徒可以）
        return getattr(player, "role", "") != "traitor"

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        if getattr(target, "role", "") == "traitor":
            room = engine.state.board.get(getattr(target, "room_key", ""))
            if room is not None and room.template_id == self.PENTAGRAM:
                return False  # p37/p108：五芒星室里的叛徒不受任何影响
        return super().attack_allowed(engine, attacker, target)

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        if player.role == "traitor" and room.template_id == self.PENTAGRAM:
            if not engine._haunt_flags().get("traitor_reached"):
                engine._haunt_flags()["traitor_reached"] = True
                engine._log(f"{player.name} 踏进五芒星室开始念诵鼠语——他在这里任何人都碰不到。")

    # --------------------------------------------------------- 老鼠回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.RAT:
            return False
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        if monster.room_key != target.room_key:
            steps = engine.roll_dice(max(1, monster.speed), "老鼠移动")
            path = self._rat_path(engine, monster.room_key, target.room_key)
            if len(path) > 1:
                monster.room_key = path[min(len(path) - 1, max(1, steps))]
                engine._log(f"{monster.name} 移动到 {engine.state.board[monster.room_key].name}。")
        if monster.room_key != target.room_key:
            return True
        pack = [
            m
            for m in engine.state.monsters
            if _monster_id(m) == self.RAT and m.room_key == monster.room_key and m.stunned_turns <= 0
        ]
        if len(pack) >= 2:
            # p108：合力攻击——力量相加、封顶 8 骰，失败不受伤。
            # 但整组每回合只能扑一次：这个钩子对同房每一只老鼠都会跑一遍，
            # 不加记录的话 N 只老鼠会各自发动一次 6–8 骰群攻，伤害直接翻 N 倍
            # （seed101/3p 实测英雄 5/6 局全灭，根本进不到"清光老鼠"那一步）。
            done = getattr(engine, "_rat_pack_done", None)
            if done is None or done.get("turn") != engine.state.turn_count:
                done = {"turn": engine.state.turn_count, "rooms": set()}
                engine._rat_pack_done = done
            if monster.room_key in done["rooms"]:
                return True  # 本回合这间房的鼠群已经扑过了
            done["rooms"].add(monster.room_key)
            dice = min(8, sum(max(0, m.might) for m in pack))
            attack_roll = engine.roll_dice(dice, "鼠群合力扑击")
            target_roll = engine._roll_attack(target, "might")
            engine._log(f"{len(pack)} 只老鼠合力扑向 {target.name}：{attack_roll} 对 {target_roll}。")
            if attack_roll > target_roll:
                engine._deal_damage(target, "physical", attack_roll - target_roll, source="鼠群")
            else:
                engine._log("鼠群扑空了——合力攻击失败不受伤（p108）。")
        else:
            engine._monster_attack(monster, target)
        return True

    def _rat_path(self, engine: Any, start: str, goal: str) -> list[str]:
        """避开五芒星室的最短路径（p37/p108：老鼠进不去）。"""
        if start == goal:
            return [start]
        graph = engine._build_graph()
        blocked = {
            k for k, room in engine.state.board.items() if room.template_id == self.PENTAGRAM
        }
        queue = [start]
        prev: dict[str, str | None] = {start: None}
        cursor = 0
        while cursor < len(queue):
            current = queue[cursor]
            cursor += 1
            for nxt in graph.get(current, ()):
                if nxt in prev or nxt in blocked:
                    continue
                prev[nxt] = current
                if nxt == goal:
                    path = [nxt]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                queue.append(nxt)
        return [start]  # 无路可走：原地不动

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        return _monster_id(monster) == self.RAT  # p37/p108：老鼠被击败即死，不会昏迷

    # ------------------------------------------------------------- 仪式
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "perform_ritual":
            return super().perform_action(engine, player, action_id, data)
        before = engine._haunt_track_value("ritual_rolls")
        result = super().perform_action(engine, player, action_id, data)
        if engine._haunt_track_value("ritual_rolls") > before:
            self._spawn_ritual_rat(engine)
        return result

    def _spawn_ritual_rat(self, engine: Any) -> None:
        """p108：仪式成功后放一只"可用"老鼠到五芒星室邻格（不需要门）。"""
        pool = int(engine._haunt_flags().get("rat_pool", 0))
        if len(self._rats(engine)) >= pool:
            engine._log("老鼠令牌都在屋里跑着，没有多余的可用。")
            return
        penta_key = self._pentagram_key(engine)
        if not penta_key:
            return
        dest = next(
            (
                k
                for k in sorted(engine._grid_neighbors(penta_key))
                if k != penta_key and not engine._is_collapsed(k)
            ),
            "",
        )
        if not dest:
            return
        if engine._spawn_single_haunt_monster(self._rat_spec(engine), dest) is not None:
            engine._log("仪式的嘶鸣召来另一只老鼠，钻进了隔壁房间。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p37 英雄胜 1：杀光所有老鼠（布置之后任意时刻）
        if flags.get("rats_placed") and not self._rats(engine):
            engine._set_winner("heroes", "最后一只老鼠被踩扁了——墙里的吱吱声终于停了。")
            return True
        # p37 英雄胜 2：叛徒在抵达五芒星室之前被杀
        if traitor is not None and traitor.dead and not flags.get("traitor_reached"):
            engine._set_winner("heroes", "鼠人在完成仪式之前就被放倒了，鼠群四散而逃。")
            return True
        # p108 叛徒胜 1：仪式完成（3-4 人 5 次 / 5-6 人 4 次）
        if engine._haunt_track_value("ritual_rolls") >= self._ritual_needed(engine):
            engine._set_winner("traitor", "仪式完成了——墙里传来的不再是吱吱声，而是欢呼。")
            return True
        # p108 叛徒胜 2：英雄全灭
        if traitor is not None and not heroes_alive:
            engine._set_winner("traitor", "所有英雄都倒下了，老鼠们涌了出来。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：未进五芒星室的叛徒被杀才算英雄胜
