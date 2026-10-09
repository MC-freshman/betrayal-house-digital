"""CannibalFeastMode（剧本 46）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    HauntAction,
)


class CannibalFeastMode(GenericModeHandler):
    """剧本 46「The Feast / 盛宴」（英雄手册 p57 / 叛徒手册 p128）。

    叛徒把同伴们诱进了食人狂徒盘踞的宅子：阁楼里关着一批受害者，
    食人狂徒在餐厅待命。叛徒与狂徒吃得越多越强；英雄要么护送所有
    受害者从正门逃出去（前提是零伤亡），要么把叛徒和狂徒杀光。

    · 开局（p57/p128）：阁楼不在场则从牌堆取出放上层、餐厅不在场则
      取出放地面层（模板自带楼层，_ensure_room_in_play 自动满足）。
      阁楼放受害者（人数只）、餐厅放食人狂徒（人数只），全部同朝向。
    · 受害者漫游（p57）：叛徒左侧玩家的回合开始时，每只受害者直行
      2 格；不能直行则向左转走下一个出口；不能穿过未探明的门；与
      英雄同房间就停下不动。朝向按门方位实现（north/east/south/west，
      "左转"取逆时针下一向），比 8/20 号的连通图近似更保真。
    · 护送（p57）：英雄与受害者同房间时可带它移动（原版为回合开始
      免费带 2 格、任意方向；电子版简化为剧本行动——花 1 行动、
      自动沿最短路朝正门带 2 格，已知简化）。
    · 正门（p57）：门厅知识检定（撬锁）或力量 5+ 开门；成功后结束
      回合（抽事件卡未建模，同 16 号口径）。之后英雄可把同房间的
      受害者送出正门，自己也能出逃/再进门接人。
    · 伤亡即封锁（p57/p128）：只要有任何受害者或英雄被杀，英雄的
      "全员逃生"路线就关闭——只能杀光叛徒和狂徒。反之只要有一名
      受害者逃出正门，叛徒的"吃光受害者"路线也关闭。
    · 进食（p128）：受害者被杀翻成尸体、英雄被杀 likewise（引擎没有
      "放倒模型"，统一用尸体令牌）。叛徒或狂徒与尸体同房间、且房间
      里没有活着的英雄时，花整回合进食：所有属性 +1，尸体移出游戏。
      狂徒的加成直接写进怪物属性（45 号蜘蛛成长同款），攻击掷骰与
      移动掷骰天然生效。
    · 怪物互吃（p128）：狂徒攻击受害者成功即杀死——引擎没有怪物
      互攻，由 handler 在狂徒回合手写力量对决近似（21/27 号口径）。
    · 胜负（p57/p128）：英雄胜 = 叛徒与狂徒全灭，或（零伤亡时）全员
      逃出；叛徒胜 = 吃光所有受害者或杀光英雄。叛徒死亡≠英雄胜
      （狂徒还在就得继续打），老坑 #1 在本剧本必然触发，已吸收。
    · 受害者在怪物回合完全不行动（on_monster_turn_start 拦下）——
      它的移动只来自漫游与护送，绝不会主动凑到英雄面前。

    已知简化：
        · 「受害者对房屋危险与必需掷骰按怪物处理」未建模——事件卡与
          房间危险不作用于怪物（引擎事件卡只结算到玩家）。
        · 「叛徒/狂徒不减慢受害者」自动满足（引擎移动互不阻挡）。
        · 护送方向自动朝正门（原版任意方向）；人类失去"先往别处带"
          的选择权（同 22 号深渊定序口径）。
        · bot 叛徒不主动攻击受害者，吃受害者主要靠狂徒自动对决；
          人类叛徒可以用标准攻击杀死受害者（命中即死）。
    """

    mode = "cannibal_feast"

    ATTIC = "attic"
    DINING = "dining_room"
    ENTRANCE = "entrance_hall"
    VICTIM = "victim"
    FREAK = "cannibal_freak"
    # 朝向左转（逆时针）顺序：北 → 西 → 南 → 东
    LEFT_OF = {"north": "west", "west": "south", "south": "east", "east": "north"}
    DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("front_door_open", False)
        flags.setdefault("blood_spilled", False)
        flags.setdefault("victims_escaped", 0)
        flags.setdefault("victim_escaped_any", False)
        flags.setdefault("victim_corpses", 0)
        flags.setdefault("escaped_hero_ids", [])
        flags.setdefault("victim_facing", {})

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        attic_key = engine._ensure_room_in_play(self.ATTIC, room_key)
        dining_key = engine._ensure_room_in_play(self.DINING, room_key)
        facing: dict[str, str] = {}
        victim_room = attic_key if attic_key is not None else (dining_key or room_key)
        if attic_key is None:
            engine._log("阁楼始终没能出现——受害者被关在了别处。")
        for _ in range(hero_count):
            monster = engine._spawn_single_haunt_monster(
                {"template_id": self.VICTIM, "name": "受害者"}, victim_room
            )
            if monster is not None:
                facing[monster.id] = "north"
        engine._log(f"{hero_count} 名受害者被关在楼上，瑟瑟发抖。")
        if dining_key is not None:
            for _ in range(hero_count):
                engine._spawn_single_haunt_monster(
                    {"template_id": self.FREAK, "name": "食人狂徒"}, dining_key
                )
            engine._log(f"{hero_count} 名食人狂徒在餐厅磨刀霍霍。")
        flags["victim_facing"] = facing
        flags["victims_total"] = sum(
            1 for m in engine.state.monsters if m.template_id == self.VICTIM
        )
        # 轨道 target 改写为实际英雄数（UI 进度面板显示真实 x/y）
        track = engine._haunt_tracks().setdefault(
            "victims_escaped", {"label": "逃出的受害者", "target": hero_count, "value": 0}
        )
        track["target"] = hero_count

    # ------------------------------------------------------- 受害者漫游
    def _victim_mover(self, engine: Any) -> Any:
        """「叛徒左侧的玩家」：回合顺序中叛徒之后的第一名活人。"""
        players = engine.state.players
        traitor_idx = next(
            (i for i, p in enumerate(players) if p.role == "traitor"), -1
        )
        if traitor_idx < 0:
            return None
        for offset in range(1, len(players) + 1):
            candidate = players[(traitor_idx + offset) % len(players)]
            if not candidate.dead:
                return candidate
        return None

    def _roam_victims(self, engine: Any) -> None:
        facing = engine._haunt_flags().setdefault("victim_facing", {})
        for monster in [m for m in engine.state.monsters if m.template_id == self.VICTIM]:
            for _ in range(2):  # 每次激活走 2 格（p57 "moves two rooms"）
                if self._hero_in_room(engine, monster.room_key):
                    break  # 与英雄同房间就不动
                if not self._victim_step(engine, monster, facing):
                    break

    def _victim_step(self, engine: Any, monster: Any, facing: dict[str, str]) -> bool:
        """走 1 格：直行优先，不能直行则左转一次（p57）。返回是否移动。"""
        room = engine.state.board.get(monster.room_key)
        if room is None:
            return False
        current = facing.get(monster.id, "north")
        for direction in (current, self.LEFT_OF.get(current, "north")):
            if direction not in room.doors:
                continue
            dx, dy = self.DELTAS[direction]
            target_key = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
            if not target_key:
                continue  # 未探明的门不能穿
            monster.room_key = target_key
            facing[monster.id] = direction  # 朝向只在移动中改变
            if self._hero_in_room(engine, target_key):
                return False  # 撞见英雄就停下
            return True
        return False

    def _hero_in_room(self, engine: Any, room_key: str) -> bool:
        return any(
            p.role == "hero" and not p.dead and p.room_key == room_key
            for p in engine.state.players
        )

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE":
            return
        flags = engine._haunt_flags()
        # 已逃出的英雄不再参与移动（只剩"重新进门"行动）
        if player.id in set(flags.get("escaped_hero_ids", [])):
            player.movement_stopped = True
            return
        # p57：叛徒左侧玩家的回合开始时移动所有受害者
        mover = self._victim_mover(engine)
        if mover is not None and player.id == mover.id and not player.dead:
            self._roam_victims(engine)

    # ------------------------------------------------------------- 行动
    def _victims_in_room(self, engine: Any, room_key: str) -> list[Any]:
        return [
            m
            for m in engine.state.monsters
            if m.template_id == self.VICTIM and m.room_key == room_key
        ]

    def _corpses_in_room(self, engine: Any, room_key: str) -> list[Any]:
        return engine.tokens_in_room(room_key, "corpse")

    def _entrance_key(self, engine: Any) -> str | None:
        entrance = next(
            (r for r in engine.state.board.values() if r.template_id == self.ENTRANCE),
            None,
        )
        return entrance.key if entrance is not None else None

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        escaped = set(flags.get("escaped_hero_ids", []))
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 已开门别再显示撬锁
            if aid == "unlock_front_door" and flags.get("front_door_open"):
                continue
            # 身边没有受害者就不显示护送/送出
            if aid in {"escort_victim", "send_victim_out"} and not self._victims_in_room(
                engine, player.room_key
            ):
                continue
            # 已到门厅：护送的目的地就是门厅，再"护送"是空转（M10-58 修）。
            # rule_data 里 escort_victim 排在 send_victim_out 前面，机器人在门厅
            # 会永远选中前者（两者打分相同、max 取先出现的），于是正门开了也
            # 永远送不出受害者——探针实测 send_victim_out 出现 4 次、执行 0 次。
            if aid == "escort_victim" and player.room_key == self._entrance_key(engine):
                continue
            # 已逃出的英雄别再显示出逃
            if aid == "escape_house" and player.id in escaped:
                continue
            # 进食需要房间里有尸体、且没有活着的英雄（p128）
            if aid == "feast_corpse":
                if not self._corpses_in_room(engine, player.room_key):
                    continue
                if self._hero_in_room(engine, player.room_key):
                    continue
            result.append(action)
        # 「重新进门」条件是"该玩家已逃出"，rule_data 的 flags 表达不了，手动追加
        if player.role == "hero" and player.id in escaped:
            result.append(
                HauntAction("reenter_house", "重新进门", "从正门回到门厅，去接下一名受害者。")
            )
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "unlock_front_door":
            return self._unlock_front_door(engine, player)
        if action_id == "escort_victim":
            return self._escort_victim(engine, player)
        if action_id == "send_victim_out":
            return self._send_victim_out(engine, player)
        if action_id == "escape_house":
            flags = engine._haunt_flags()
            flags["escaped_hero_ids"] = sorted(
                set(flags.get("escaped_hero_ids", [])) | {player.id}
            )
            player.movement_stopped = True
            engine._log(f"{engine._player_label(player)} 从正门逃了出去，但还没到收工的时候。")
            return True
        if action_id == "reenter_house":
            flags = engine._haunt_flags()
            flags["escaped_hero_ids"] = sorted(
                set(flags.get("escaped_hero_ids", [])) - {player.id}
            )
            player.movement_stopped = False
            engine._log(f"{engine._player_label(player)} 重新溜回宅子，去接下一名受害者。")
            return True
        if action_id == "feast_corpse":
            return self._feast(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _unlock_front_door(self, engine: Any, player: Any) -> bool:
        """p57：知识检定（撬锁）或力量 5+。成功 → 开门 + 结束回合。"""
        use_might = False
        if getattr(player, "control", "bot") != "bot":
            idx = engine.prompter.choose_from_list(
                "正门", "用哪种方式开正门？", ["知识检定（撬锁）", "力量 5+（撞开）"]
            )
            use_might = idx == 1
        else:
            # bot：挑期望成功率更高的属性（力量按 5+ 门槛，知识按掷骰和）
            use_might = player.stats.get("might", 0) * 2 >= player.stats.get("knowledge", 0)
        if use_might:
            roll = engine.roll_dice(player.stats.get("might", 0), "撞门")
            ok = roll >= 5
            engine._log(f"{engine._player_label(player)} 撞门：掷出 {roll}（需 5+）。")
        else:
            ok = engine._resolve_check(player, "knowledge", 0, "撬锁")
            engine._log(
                f"{engine._player_label(player)} 试图撬开正门：{'成功' if ok else '失败'}。"
            )
        if not ok:
            return False
        engine._haunt_flags()["front_door_open"] = True
        engine._log("正门吱呀一声开了——外面的夜风从未如此甜美。")
        # p57：成功后抽事件卡并结束回合（抽卡未建模，同 16 号口径）
        self._end_turn(player)
        return True

    def _escort_victim(self, engine: Any, player: Any) -> bool:
        """p57：带同房受害者移动。原版为回合开始免费带 2 格、任意方向；
        电子版为 1 行动、自动沿最短路朝正门（已知简化）。"""
        victims = self._victims_in_room(engine, player.room_key)
        if not victims:
            return False
        victim = victims[0]
        if getattr(player, "control", "bot") != "bot" and len(victims) > 1:
            idx = engine.prompter.choose_from_list(
                "护送受害者",
                "带哪一名受害者走？",
                [f"受害者 {i + 1}" for i in range(len(victims))],
            )
            if idx is not None and 0 <= idx < len(victims):
                victim = victims[idx]
        entrance_key = self._entrance_key(engine)
        if entrance_key is None:
            return False
        path = engine._shortest_path(player.room_key, entrance_key)
        if len(path) <= 1:
            # 已在门厅：护送无事可做，**不能**当作"执行成功"——否则整回合的
            # 剧本行动被白白吃掉（M10-58 探针的"行动空转:send_victim_out"
            # 就是这个假成功导致的）。真正的下一步是 send_victim_out。
            engine._log("已经在正门厅了——该做的是把受害者送出门。")
            return False
        steps = min(2, len(path) - 1)
        dest = path[steps]
        player.room_key = dest
        victim.room_key = dest
        engine._log(
            f"{engine._player_label(player)} 护着受害者移到{engine.state.board[dest].name}。"
        )
        return True

    def _send_victim_out(self, engine: Any, player: Any) -> bool:
        """p57：把受害者送出正门（1 格）。逃出的受害者移出游戏。"""
        victims = self._victims_in_room(engine, player.room_key)
        if not victims:
            return False
        self._escape_victim(engine, victims[0])
        return True

    def _escape_victim(self, engine: Any, victim: Any) -> None:
        engine.state.monsters = [m for m in engine.state.monsters if m.id != victim.id]
        flags = engine._haunt_flags()
        flags["victims_escaped"] = int(flags.get("victims_escaped", 0)) + 1
        flags["victim_escaped_any"] = True
        engine._advance_haunt_track("victims_escaped")
        engine._log(
            f"一名受害者逃出了正门（{flags['victims_escaped']}/{flags.get('victims_total', '?')}）！"
        )

    def _feast(self, engine: Any, player: Any) -> bool:
        """p128：与尸体同房间且房内无活英雄 → 花整回合进食，全属性 +1。"""
        corpses = self._corpses_in_room(engine, player.room_key)
        if not corpses or self._hero_in_room(engine, player.room_key):
            return False
        self._consume_corpse(engine, corpses[0])
        for stat in ("speed", "might", "sanity", "knowledge"):
            engine._increase_stat(player, stat, 1)
        self._end_turn(player)
        engine._log(f"{engine._player_label(player)} 花了一整回合进食，感觉浑身是劲。")
        return True

    def _consume_corpse(self, engine: Any, corpse: Any) -> None:
        if corpse.label == "受害者尸体":
            flags = engine._haunt_flags()
            flags["victim_corpses"] = max(0, int(flags.get("victim_corpses", 0)) - 1)
        engine.remove_token(corpse.uid)

    def _end_turn(self, player: Any) -> None:
        """结束该玩家的回合（"花整回合"的行动，p57/p128）。"""
        player.movement_stopped = True
        player.steps_remaining = 0
        player.attack_used = True
        player.item_used = True

    # ------------------------------------------------------------- 怪物
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        template = getattr(monster, "template_id", "")
        if template == self.VICTIM:
            # 受害者绝不主动行动：移动只来自漫游与护送（p57）
            return True
        if template != self.FREAK:
            return False
        # p128：狂徒攻击同房间的受害者，成功即杀死
        victims = self._victims_in_room(engine, monster.room_key)
        if victims:
            victim = victims[0]
            freak_roll = engine._roll_monster_attack(monster, "might")
            victim_roll = engine.roll_dice(victim.might, "受害者反抗")
            engine._log(f"食人狂徒扑向受害者：{freak_roll} 对 {victim_roll}。")
            if freak_roll > victim_roll:
                self._kill_victim_to_corpse(engine, victim, killer=monster)
            else:
                engine._log("受害者挣扎着躲开了。")
            return True  # 无论成败，这回合都花在扑击上
        # p128：与尸体同房间且无活英雄 → 进食
        corpses = self._corpses_in_room(engine, monster.room_key)
        if corpses and not self._hero_in_room(engine, monster.room_key):
            self._consume_corpse(engine, corpses[0])
            monster.speed += 1
            monster.might += 1
            monster.sanity += 1
            engine._log(f"{monster.name} 花了一整回合进食，变得更加强壮。")
            return True
        return False  # 正常追杀英雄

    def _kill_victim_to_corpse(self, engine: Any, victim: Any, killer: Any = None) -> None:
        """受害者被杀：翻成尸体令牌（p128），并封锁逃生路线。"""
        engine.spawn_token(
            "corpse", label="受害者尸体", role="marker", room_key=victim.room_key
        )
        flags = engine._haunt_flags()
        flags["victim_corpses"] = int(flags.get("victim_corpses", 0)) + 1
        flags["blood_spilled"] = True
        engine._kill_monster(victim, killer=killer)

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p57/p128：受害者与食人狂徒被击败即死（不是击晕）。
        受害者被杀时在此生成尸体——本钩子的调用点唯一且就在击杀结算处。"""
        template = getattr(monster, "template_id", "")
        if template == self.VICTIM:
            self._kill_victim_to_corpse(engine, monster, killer=attacker)
            return True
        return template == self.FREAK

    def on_player_died(self, engine: Any, player: Any) -> None:
        """p128：探险者被杀也算尸体（放倒的模型），并封锁逃生路线。"""
        engine.spawn_token(
            "corpse", label="探险者尸体", role="marker", room_key=player.room_key
        )
        engine._haunt_flags()["blood_spilled"] = True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        freaks_alive = [m for m in engine.state.monsters if m.template_id == self.FREAK]
        victims_alive = [m for m in engine.state.monsters if m.template_id == self.VICTIM]

        # p57：英雄胜 A——叛徒与所有食人狂徒都死了
        if not traitor_alive and not freaks_alive:
            engine._set_winner("heroes", "叛徒与食人狂徒全部倒下，盛宴结束了。")
            return True
        # p57：英雄胜 B——零伤亡且全员（英雄+受害者）逃出
        if (
            not flags.get("blood_spilled")
            and int(flags.get("victims_total", 0)) > 0
            and int(flags.get("victims_escaped", 0)) >= int(flags.get("victims_total", 0))
            and heroes_alive
            and all(p.id in set(flags.get("escaped_hero_ids", [])) for p in heroes_alive)
        ):
            engine._set_winner("heroes", "最后一名受害者逃出正门——没人变成今晚的主菜。")
            return True
        # p128：叛徒胜 A——所有受害者都被吃掉（且从未有人逃出）
        if (
            not flags.get("victim_escaped_any")
            and not victims_alive
            and int(flags.get("victim_corpses", 0)) == 0
            and int(flags.get("victims_total", 0)) > 0
        ):
            engine._set_winner("traitor", "最后一名受害者被吃得干干净净——盛宴开席。")
            return True
        # 通用：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "所有英雄都倒下了。")
            return True
        # 吸收兜底：叛徒死亡但狂徒还在——游戏继续，不判英雄胜
        if not traitor_alive:
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        flags = engine._haunt_flags()
        if player.role != "hero":
            return []
        if player.id in set(flags.get("escaped_hero_ids", [])):
            return []
        # p57：一旦见血，零伤亡逃生路线（英雄胜线 B）永久关闭，只能杀光叛徒与
        # 所有狂徒。画像的 victory_focus 早就写着"见血就转杀光狂徒"，但目标
        # 房间没跟上：英雄还在满屋追受害者护送（18 局采样 6 局全部见血、
        # 英雄胜 1/18；seed101/3p 里两名英雄被叛徒+狂徒围殴到死还在搬人）。
        if flags.get("blood_spilled"):
            targets = [
                f"__room__{m.room_key}"
                for m in engine.state.monsters
                if m.template_id == self.FREAK
            ]
            traitor = next(
                (p for p in engine.state.players if p.role == "traitor" and not p.dead),
                None,
            )
            if traitor is not None:
                targets.append(f"__room__{traitor.room_key}")
            if targets:
                return targets
        # 门没开时优先护送受害者（受害者在哪，英雄就去哪）；门开了直奔门厅
        if not flags.get("front_door_open"):
            return [
                f"__room__{m.room_key}"
                for m in engine.state.monsters
                if m.template_id == self.VICTIM
            ]
        entrance_key = self._entrance_key(engine)
        return [f"__room__{entrance_key}"] if entrance_key else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = ["正门：已打开" if flags.get("front_door_open") else "正门：还没打开"]
        total = int(flags.get("victims_total", 0))
        lines.append(f"受害者：逃出 {int(flags.get('victims_escaped', 0))}/{total}。")
        if flags.get("blood_spilled"):
            lines.append("已经见血——全员逃生路线关闭，只能杀光叛徒与狂徒。")
        return lines
