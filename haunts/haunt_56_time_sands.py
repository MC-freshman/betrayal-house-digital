"""SandsOfTimeMode（剧本 56）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
)


class SandsOfTimeMode(GenericModeHandler):
    """剧本 56「Time Waits for One Man」（英雄手册 p67 / 叛徒手册 p138）。

    叛徒戴上了面具，时之沙脱缰而出：记忆与命运的幽影在他差遣下猎杀
    昔日的朋友。但他每次动用时间之力，时之沙就离他的掌控更远一分——
    一旦失控，连他自己的存在都会被磨损。

    · 开局（p138）：幽影数 = 英雄数，放作祟房；叛徒立即戴上面具：
      +2 知识、-2 理智（若理智会死则停在骷髅上方最低格，p138 明文保护）。
    · 幽影（p138/p67）：免疫力量攻击（monster_specs immune_to）；只能以
      理智攻击（on_monster_turn_attack 接管，目标以理智防御、精神伤害）；
      **穿墙移动**（同层正交邻格、无需门，排除神秘电梯——p138 明文；
      上下楼通道 Chute/Collapsed/Gallery 简化掉）；不阻碍移动（引擎互不
      阻挡自动满足）。被理智攻击（持戒指）击败则正常击晕。
    · 时间之力（p138，每次轨道 +1、无上限）：电子版落成三个叛徒行动——
      命运之风（+2 移动）、时停打击（力量攻击同房英雄，造成 ≥1 伤害则
      该英雄跳过下回合）、补充时沙（知识 3+：每只同房幽影使轨道 -1，
      无论成败同房幽影全晕）。轨道用 flags["time_track"] 记（原文无上限，
      UI 轨道封顶显示）。Recall/Visions/Blitz 未建模（见已知简化）。
    · 失控检定（p67）：叛徒回合结束后（叛徒已死则由本轮最后存活玩家
      代跑），一名英雄掷玩家数枚骰——结果 ≤ 轨道值 → 叛徒全属性 -1、
      轨道 -1、再掷（循环到结果 > 轨道值）。越用时间之力越容易失控。
    · 欺骗命运（p67）：英雄行动——与幽影同房 +（持水晶球 或 房内没有
      其他英雄）→ 知识 4+ → 该幽影立即移出游戏。每回合一次。
    · 戒指/奖章（p67）：持戒指者可用理智攻击幽影（attack_attr_override
      覆盖力量为理智）；持奖章者与幽影对决落败不受伤。
    · 胜负（p67/p138）：英雄胜 = 叛徒死亡（失控磨损同算）；叛徒胜 =
      英雄全灭。本剧本叛徒死即英雄胜（p67 原文），不需要吸收兜底。

    已知简化：
        · Recall（强制重掷）没有全局掷骰后钩子可挂，未建模；Visions
          （看牌堆顶重排）对 bot 无意义、人类收益低，未建模；Blitz
          （速度攻击变体）未建模——叛徒用标准力量攻击。
        · 幽影上下楼通道（Chute/Collapsed/Gallery 各花 1 点）未建模，
          幽影只在已探明层内穿墙游走。
        · 面具"不可摘/不可弃/不可偷"未在物品系统层拦截（bot 不偷）。
        · 失控检定的掷骰英雄由系统自动选择（原版由英雄们自行商定）。
        · "时停打击"重构为显式剧本行动（原版为攻击附效自动触发）。
        · 幽影穿墙在 on_monster_turn_start 里走完；on_monster_move 对幽影
          返回 True，避免引擎再沿最短路叠一次移动。
    """

    mode = "time_sands"

    SPECTRE = "spectre"
    MASK = "omen_mask"
    RING = "omen_ring"
    MEDALLION = "omen_medallion"
    CRYSTAL_BALL = "omen_crystal_ball"
    ELEVATOR = "mystic_elevator"
    DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("time_track", 0)
        flags.setdefault("skip_turn_ids", [])
        engine._haunt_tracks().setdefault(
            "time_track", {"label": "时之沙掌控（失控线）", "target": 10, "value": 0}
        )
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        # p138：立即戴上面具——+2 知识、-2 理智（若这次损失会致死，理智停在骷髅上一格）
        if traitor is not None and not traitor.dead:
            engine._increase_stat(traitor, "knowledge", 2)
            # 属性轨道一律递增（实测 sanity=[3,4,5,5,6,7,7,8]），格位 0 是最低值、
            # 骷髅在 -1，所以「骷髅上一格」= 格位 0。旧实现判断的是**上界**
            # （pos + 2 > len - 1）并把位置**上调**，方向整个反了——只有理智接近
            # 顶格时才触发、触发后反而把理智抬上去（M10-16 实测探针修正）。
            track = engine._stat_track(traitor, "sanity") or []
            pos = traitor.stat_positions.get("sanity", 0)
            if track and pos - 2 < 0:
                traitor.stat_positions["sanity"] = 0
                traitor.stats["sanity"] = track[0]
                engine._log(f"{traitor.name} 的理智坠到了崩溃边缘，但面具不容他死去。")
            else:
                engine._apply_stat_loss(traitor, "sanity", 2)
            engine._log("面具焊在了脸上——知识涌入，理智流失。")
        # p138：幽影 = 英雄数，放作祟房
        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SPECTRE, {"template_id": self.SPECTRE, "name": "记忆幽影"})
        )
        for _ in range(hero_count):
            engine._spawn_single_haunt_monster(spec, room_key)
        engine._log(f"{hero_count} 道幽影自墙壁渗出——那是记忆，也是命运。")

    # ------------------------------------------------------- 幽影规则
    def _spectres(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.SPECTRE]

    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p67：幽影免疫力量攻击，但持戒指者可用理智攻击（正常规则）。"""
        if (
            getattr(target, "template_id", "") == self.SPECTRE
            and default_attr == "might"
            and self.RING in getattr(attacker, "items", [])
        ):
            return "sanity"
        return None

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p67：持奖章者与幽影对决落败不受伤。"""
        return getattr(target, "template_id", "") == self.SPECTRE and (
            self.MEDALLION in getattr(attacker, "items", [])
        )

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.SPECTRE:
            return False
        # p138：幽影可在相邻房间间穿行（无需门）；同层正交邻格、排除电梯
        target = engine._find_monster_target(monster)
        for _ in range(max(1, monster.speed)):
            room = engine.state.board.get(monster.room_key)
            if room is None:
                break
            neighbors = []
            for direction in sorted(room.doors):
                dx, dy = self.DELTAS.get(direction, (0, 0))
                key = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if key and engine.state.board[key].template_id != self.ELEVATOR:
                    neighbors.append(key)
            # 穿墙：同层正交邻格里门邻居之外的房间也算可走
            for dx, dy in self.DELTAS.values():
                key = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if key and key not in neighbors and engine.state.board[key].template_id != self.ELEVATOR:
                    neighbors.append(key)
            if not neighbors:
                break
            if target is not None:
                dest = min(neighbors, key=lambda k: engine._path_length(k, target.room_key))
            else:
                dest = sorted(neighbors)[0]
            monster.room_key = dest
        return False  # 不跳过攻击阶段；移动由 on_monster_move 宣告已处理

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """穿墙步已在 on_monster_turn_start 走完，跳过引擎默认的沿路移动。"""
        return getattr(monster, "template_id", "") == self.SPECTRE

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p138：幽影只能以理智攻击（目标以理智防御，精神伤害）。"""
        if getattr(monster, "template_id", "") != self.SPECTRE:
            return False
        target = engine._find_monster_target(monster)
        if target is None or target.room_key != monster.room_key:
            return True
        roll = engine._roll_monster_attack(monster, "sanity")
        defense = engine._roll_attack(target, "sanity")
        engine._log(f"幽影的尖啸刺入 {engine._player_label(target)} 的脑海：{roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "mental", roll - defense, source="幽影")
        elif roll < defense:
            engine._stun_monster(monster, 1)
        return True

    # ------------------------------------------------------- 时间之力
    def _advance_time(self, engine: Any, amount: int = 1) -> int:
        """p138：轨道无上限（flags 记真实值），UI 轨道同步（封顶显示）。"""
        flags = engine._haunt_flags()
        value = max(0, int(flags.get("time_track", 0)) + amount)
        flags["time_track"] = value
        engine._set_haunt_track_value("time_track", min(value, 10))
        return value

    def _cheat_fate_allowed(self, engine: Any, player: Any) -> bool:
        has_spectre = any(s.room_key == player.room_key for s in self._spectres(engine))
        if not has_spectre:
            return False
        if self.CRYSTAL_BALL in player.items:
            return True
        others = any(
            p.role == "hero" and not p.dead and p.id != player.id
            and p.room_key == player.room_key
            for p in engine.state.players
        )
        return not others  # 房内没有其他英雄才可尝试

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 欺骗命运：须持水晶球，或房内没有其他英雄（p67）
            if aid == "cheat_fate" and not self._cheat_fate_allowed(engine, player):
                continue
            # 补充时沙：同房间得有没被晕的幽影；轨道已是 0 时再点只会空耗
            if aid == "replenish_sands" and (
                int(engine._haunt_flags().get("time_track", 0)) <= 0
                or not any(
                    s.room_key == player.room_key and s.stunned_turns <= 0
                    for s in self._spectres(engine)
                )
            ):
                continue
            # 时停打击：没有同房英雄时行动必失败，不该出现在列表里
            # （否则机器人空点一次、本回合剧本行动额度还没花掉，再被之风钉死）
            if aid == "time_stop_strike" and not any(
                p.role == "hero" and not p.dead and p.room_key == player.room_key
                for p in engine.state.players
            ):
                continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "cheat_fate":
            return self._cheat_fate(engine, player)
        if action_id == "winds_of_fate":
            player.steps_remaining += 2
            self._advance_time(engine)
            engine._log("命运之风鼓起叛徒的衣袍——本回合移动 +2（轨道 +1）。")
            return True
        if action_id == "time_stop_strike":
            return self._time_stop_strike(engine, player)
        if action_id == "replenish_sands":
            return self._replenish(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _cheat_fate(self, engine: Any, player: Any) -> bool:
        """p67：知识 4+ → 同房幽影立即移出游戏。"""
        if not self._cheat_fate_allowed(engine, player):
            return False
        targets = [s for s in self._spectres(engine) if s.room_key == player.room_key]
        if not targets:
            return False
        ok = engine._resolve_check(player, "knowledge", 4, "欺骗命运")
        if not ok:
            engine._log(f"{engine._player_label(player)} 试图篡改命运，但时之沙不为所动。")
            return False
        spectre = targets[0]
        engine.state.monsters = [m for m in engine.state.monsters if m.id != spectre.id]
        engine._log("命运被改写了——一道幽影从现实中被抹去！")
        return True

    def _time_stop_strike(self, engine: Any, player: Any) -> bool:
        """p138 时停：力量攻击同房英雄，造成 ≥1 伤害则该英雄跳过下回合（轨道 +1）。"""
        target = next(
            (
                p
                for p in engine.state.players
                if p.role == "hero" and not p.dead and p.room_key == player.room_key
            ),
            None,
        )
        if target is None:
            return False
        roll = engine._roll_attack(player, "might")
        defense = engine._roll_attack(target, "might")
        engine._log(f"时停打击：{engine._player_label(player)} {roll} 对 {defense}。")
        if roll > defense:
            engine._deal_damage(target, "physical", roll - defense, source="时停打击")
            flags = engine._haunt_flags()
            flags["skip_turn_ids"] = sorted(set(flags.get("skip_turn_ids", [])) | {target.id})
            engine._log(f"{engine._player_label(target)} 被冻结在了时间之外——下回合无法行动。")
        self._advance_time(engine)
        return True

    def _replenish(self, engine: Any, player: Any) -> bool:
        """p138：知识 3+ → 每只同房幽影使轨道 -1；无论成败同房幽影全晕。"""
        here = [s for s in self._spectres(engine) if s.room_key == player.room_key]
        if not here:
            return False
        ok = engine._resolve_check(player, "knowledge", 3, "补充时沙")
        if ok:
            self._advance_time(engine, -len(here))
            engine._log(f"幽影被榨干了——时之沙退回 {engine._haunt_flags().get('time_track', 0)}。")
        else:
            engine._log("补充时沙失败——幽影依旧被抽干了力量。")
        for spectre in here:
            spectre.stunned_turns += 1
        return True

    # ------------------------------------------------------- 失控检定
    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p67：叛徒回合结束（叛徒死则本轮最后存活玩家代跑）做失控检定。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            should_roll = player.id == traitor.id
        else:
            should_roll = _is_last_in_round(engine, player)
        if not should_roll:
            return
        self._control_check(engine)

    def _control_check(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        track = int(flags.get("time_track", 0))
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return
        roller = heroes[0]  # 原版由英雄们商定，电子版自动选第一名活英雄
        dice = len(engine.state.players)
        guard = 0
        while guard < 24:
            guard += 1
            result = engine.roll_dice(dice, "时之沙掌控检定")
            if result > track:
                engine._log(f"时之沙掌控检定：{result} > {track}——叛徒勉强维持住了控制。")
                return
            traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
            if traitor is None or traitor.dead:
                return
            engine._log(f"时之沙掌控检定：{result} ≤ {track}——叛徒失控了！")
            for stat in ("sanity", "knowledge", "might", "speed"):
                engine._apply_stat_loss(traitor, stat, 1)
            # _apply_stat_loss 可以把属性滑到骷髅，但不会判死；p67 英雄胜线
            # 就是叛徒死亡，必须在这里补一次，否则轨道被之风堆高后循环 24 次
            # 仍带着 0 属性活着（批次 12 实测 4 局 300 回合僵局）。
            engine._check_player_death(traitor)
            track = self._advance_time(engine, -1)
            engine.check_victory()
            if traitor.dead or engine.state.winner:
                return

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p138 时停：被冻结的英雄跳过本回合。"""
        flags = engine._haunt_flags()
        skipped = set(flags.get("skip_turn_ids", []))
        if player.id in skipped:
            flags["skip_turn_ids"] = sorted(skipped - {player.id})
            player.movement_stopped = True
            player.attack_used = True
            player.item_used = True
            engine._mark_haunt_action_used(player)
            engine._log(f"{engine._player_label(player)} 仍被冻结在时间之外——本回合无法行动。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p67：叛徒死亡 → 英雄胜（失控磨损同算）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            engine._set_winner("heroes", "时之沙反噬了它的主人——时间重新开始流动。")
            return True
        # p138：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后的记忆也被幽影吞噬了。")
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def _hero_here(self, engine: Any, player: Any) -> bool:
        return any(
            p.role == "hero" and not p.dead and p.room_key == player.room_key
            for p in engine.state.players
        )

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """叛徒按情境选时间之力：同房才时停，轨道高才补充，有活可打就别吹风。

        英雄的欺骗命运带 `same_room:spectre`：不挡住的话，所有英雄都会把幽影房
        当成剧本目标，没戒指的人围着打不了的怪转、不去杀叛徒。
        """
        if player.dead:
            return False
        if action_id == "cheat_fate":
            return not self._cheat_fate_allowed(engine, player)
        if player.role != "traitor":
            return False
        track = int(engine._haunt_flags().get("time_track", 0))
        hero_here = self._hero_here(engine, player)
        spectres_here = any(
            s.room_key == player.room_key and s.stunned_turns <= 0
            for s in self._spectres(engine)
        )
        if action_id == "time_stop_strike":
            return not hero_here
        if action_id == "replenish_sands":
            return track < 3 or not spectres_here
        if action_id == "winds_of_fate":
            if hero_here:
                return True
            if spectres_here and track >= 3:
                return True
            return False
        return False

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """没戒指就别拿拳头捶免疫力量的幽影——真人会去打叛徒。"""
        if getattr(target, "template_id", "") != self.SPECTRE:
            return False
        return self.RING not in getattr(player, "items", [])

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """吹完命运之风必须去找人；原地等下一回合之风会把人钉死在同一间房。"""
        if player.dead:
            return False
        if player.role == "traitor":
            if self._hero_here(engine, player):
                return False
            track = int(engine._haunt_flags().get("time_track", 0))
            if track >= 3 and any(
                s.room_key == player.room_key and s.stunned_turns <= 0
                for s in self._spectres(engine)
            ):
                return False
            return True
        return not self._cheat_fate_allowed(engine, player)

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        # 戒指把力量改成理智；水晶球能在同房骗命运。奖章只是落败免伤，围着转杀不死。
        if self.RING in player.items or self.CRYSTAL_BALL in player.items:
            spectres = self._spectres(engine)
            if spectres:
                return [f"__room__{spectres[0].room_key}"]
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        return [f"__room__{traitor.room_key}"] if traitor is not None else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        track = int(flags.get("time_track", 0))
        lines = [f"时之沙轨道：{track}（每回合结束掷玩家数骰，≤ 轨道即失控）。"]
        skipped = flags.get("skip_turn_ids", [])
        if skipped:
            lines.append(f"被时停的英雄：{len(skipped)} 名。")
        lines.append(f"幽影：{len(self._spectres(engine))} 只。")
        return lines
