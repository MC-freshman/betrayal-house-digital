"""WispCaptureMode（剧本 69）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    DIRECTION_DELTAS,
    GenericModeHandler,
)


class WispCaptureMode(GenericModeHandler):
    """剧本 69「Way of the Wisp / 小精灵之道」（英雄手册 p80 / 叛徒手册 p151）。

    那团光把叛徒吞了下去——他的身体留在原地，人已经不在局中。现在那缕
    光只想逃出这栋房子，而它经过的地方会留下一团团迷雾，绊住每一个追它的人。

    · 开局（p151）：叛徒角色**移出游戏**（原文 remove your figure；电子版
      标记 dead 并由 handler 吸收"叛徒死 → 英雄胜"兜底——这是设计而非失败）；
      小精灵（Speed 5 / Might 6 / Sanity 6）放在作祟房；地下室楼梯未发现则
      取出放好；**小精灵先手**（轨道起点记为 1，等价它先推了一格）。
    · 小精灵回合（p151）：回合开始推进轨道 +1 并**清除全部孢子**；移动力按
      p17 投速度骰，然后**不能停止移动**——耗尽步数或无合法移动为止；离开的
      房间留下一枚孢子；不能进入已有孢子的房间；不主动攻击（防守反击照常）；
      **可像探索者一样翻开新房间**（不抽牌、不因符号停步）。整回合由 handler
      接管完毕，`on_monster_turn_start` 返回 True 挡掉引擎的默认追击。
    · 孢子迷雾（p80）：英雄每回合**第一次**尝试离开有孢子的房间时做理智
      检定：6+ 本回合免疫；2-5 本回合剩余每次离开孢子房多花 1 点移动；
      0-1 回合立即结束。实现在 movement_cost_floor 钩子（每步都会问一次）。
    · 捕捉（p80）：与小精灵同房的英雄做知识 4+，成功 +1 枚捕捉令牌；
      英雄们**累计**达到"作祟开始时英雄数"枚 → 抓住小精灵 → 英雄胜。
    · 胜负（p80/p151）：轨道到 6 小精灵仍自由 → 叛徒胜；捕捉令牌满 →
      英雄胜。叛徒角色出局是设计，吸收兜底（7/8 号怪物自主口径）。

    已知简化：
        · 小精灵探索新房间**已建模（2026-09-16）**：逃不开时按"离英雄最远的
          空门口"翻一块新板块（与 47 号蛇头同口径手写，引擎仍无怪物探索通用层）。
          同一次改动还修掉了两处更致命的规则错：`on_monster_turn_start` 原先返回
          False，逃跑结束后引擎默认怪物 AI 会把小精灵**往英雄方向拖**（既违反
          "不能进入已有孢子的房间"，也违反"移动不受对手阻挡"），以及移动力被
          写成固定 5 点而非投速度骰。
        · 小精灵"不能停止移动"按步数连续步进实现，遇到死路且开不出新房间即停；
          方向由 `_flee_step` 选"离最近英雄最远"的邻房（旧实现固定挑楼层最低处，
          等于直线钻地下室，英雄闭着眼都能堵住）。
        · 不能用神秘电梯/煤槽向上/坍塌房/舞厅→画廊未建模——逃跑只走**门邻居**
          与**新板块**，密道/秘门/电梯天然不在候选里，故此条近似自动满足。
        · 屏障房（如深渊）两侧各留一枚孢子未建模——只标记离开的那间。
        · 小精灵"免疫左轮"未建模：引擎 immune_to 按攻击属性判定，写
          "speed" 会连带免疫徒手速度攻击（超范围），故留空并记录。
        · 回合内"先手"用轨道起点 1 体现，未改动引擎回合顺序。
    """

    mode = "wisp_capture"

    WISP = "wisp"
    STAIRS = "stairs_from_basement"
    ESCAPE_TRACK = 6
    CATCH_TARGET = 4

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("spore_rooms", [])
        flags.setdefault("spore_state", {})
        flags.setdefault("wisp_track", 1)  # p151：小精灵先手，轨道先推到 1
        flags.setdefault("traitor_removed", True)

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        engine._haunt_tracks().setdefault(
            "capture_tokens",
            {"label": "捕捉进度", "target": hero_count, "value": 0},
        )["target"] = hero_count
        engine._haunt_tracks().setdefault(
            "escape_track", {"label": "逃脱轨道", "target": self.ESCAPE_TRACK, "value": 1}
        )

        # p151：叛徒角色移出游戏（是设计不是失败）
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            traitor.dead = True
            engine._log(f"{traitor.name} 的身体软倒在地——他已经是那团光了。")

        # p151：地下室楼梯未发现则取牌放好
        engine._ensure_room_in_play(self.STAIRS, room_key)

        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.WISP, {"template_id": self.WISP, "name": "小精灵"})
        )
        engine._spawn_single_haunt_monster(spec, room_key)
        engine._log("一团光在作祟房里亮起——它在找出口。")

    # ------------------------------------------------------- 孢子迷雾
    def _spore_rooms(self, engine: Any) -> set:
        return set(engine._haunt_flags().get("spore_rooms", []))

    def _set_spores(self, engine: Any, rooms) -> None:
        engine._haunt_flags()["spore_rooms"] = sorted(set(rooms))

    def _spore_state(self, engine: Any, player: Any) -> str:
        return engine._haunt_flags().get("spore_state", {}).get(str(player.id), "")

    def movement_cost_floor(
        self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None
    ) -> int:
        """p80：英雄每回合第一次离开孢子房做理智检定（6+/2-5/0-1）。"""
        if from_key is None or player.role != "hero":
            return 0
        if from_key not in self._spore_rooms(engine):
            return 0
        flags = engine._haunt_flags()
        state = dict(flags.get("spore_state", {}))
        mine = state.get(str(player.id), "")
        if mine == "immune":
            return 0
        if mine == "slow":
            return 2  # 离开有孢子房多花 1 点（基础 1 → 2）
        if mine == "ended":
            return 0
        # 本回合第一次：做理智掷骰（p80：骰数 = 当前理智）
        result = engine.roll_dice(max(1, player.stats.get("sanity", 1)), "孢子迷雾")
        if result >= 6:
            state[str(player.id)] = "immune"
            flags["spore_state"] = state
            engine._log(f"{engine._player_label(player)} 穿过迷雾——神志清明（{result}）。")
            return 0
        if result <= 1:
            state[str(player.id)] = "ended"
            flags["spore_state"] = state
            player.movement_stopped = True
            player.attack_used = True
            player.item_used = True
            engine._mark_haunt_action_used(player)
            engine._log(f"{engine._player_label(player)} 被迷雾呛住——本回合到此为止（{result}）。")
            return 0
        state[str(player.id)] = "slow"
        flags["spore_state"] = state
        engine._log(f"{engine._player_label(player)} 在迷雾里跌跌撞撞（{result}）——多花一点移动力。")
        return 2

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """回合开始重置本回合的孢子状态（每回合重新判定一次）。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        flags = engine._haunt_flags()
        state = dict(flags.get("spore_state", {}))
        if str(player.id) in state:
            state.pop(str(player.id))
            flags["spore_state"] = state

    # ------------------------------------------------------- 小精灵回合
    def _wisp(self, engine: Any) -> Any:
        return next((m for m in engine.state.monsters if m.template_id == self.WISP), None)

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.WISP:
            return False
        flags = engine._haunt_flags()
        # p151：回合开始推进轨道
        flags["wisp_track"] = int(flags.get("wisp_track", 0)) + 1
        engine._set_haunt_track_value("escape_track", min(flags["wisp_track"], self.ESCAPE_TRACK))
        # p151：清除全部孢子
        self._set_spores(engine, [])
        engine._log(f"小精灵的回合：轨道 {flags['wisp_track']}/{self.ESCAPE_TRACK}，迷雾散尽。")
        # p151 + p17：移动力 = 速度骰；拿到步数就不能停，直到步数耗尽或无合法移动
        steps = max(1, engine.roll_dice(monster.speed, "小精灵移动"))
        route = self._flee_run(engine, monster, steps)
        if route:
            names = "→".join(engine.state.board[k].name for k in route)
            engine._log(f"小精灵掠过 {names}，身后留下 {len(route)} 团迷雾。")
        else:
            engine._log("小精灵被迷雾围死了——一步也动不了。")
        engine.check_victory()
        # p151：整回合就是这条逃跑路线。**必须返回 True**：返回 False 会让引擎
        # 接着跑默认怪物 AI（追最近英雄 + 房内对手加成），实测 seed101/4p 它
        # 刚逃到塔楼就被拖回二楼平台，seed113 第二回合被拽进自己上回合的孢子房
        # ——既违反"不能进入已有孢子的房间"，也违反"移动不受对手阻挡"。
        return True

    def _flee_run(self, engine: Any, monster: Any, steps: int) -> list[str]:
        """按步数逃窜，返回途经房间（用于日志与孢子结算）。"""
        route: list[str] = []
        for _ in range(steps):
            room = engine.state.board.get(monster.room_key)
            if room is None:
                break
            spores = self._spore_rooms(engine)
            # p151：不能进入已有孢子的房间
            options = [k for k in engine._door_neighbors(monster.room_key) if k not in spores]
            dest = self._flee_step(engine, monster, options, room)
            if dest is None:
                break
            # p151：离开的房间留下一枚孢子
            self._set_spores(engine, set(spores) | {monster.room_key})
            monster.room_key = dest
            route.append(dest)
        return route

    def _flee_step(self, engine: Any, monster: Any, options: list[str], room: Any) -> str | None:
        """一步的落点：能往更远处逃就逃，否则开新房间，都没有才回头。

        p151 把这个角色整个交给叛徒玩家（"remove your figure... you want to fly,
        faster and faster, up and away"），赢法是"stay free until the Turn/Damage
        Track reaches 6"——所以它必须躲着追它的人跑。旧实现固定挑"楼层最低的
        邻房"（`sort(key=floor)`），等于一条直线钻进地下室：seed3/3p 实测作祟
        只撑 3 个回合就被两名英雄围住按死，逃脱轨道停在 2/6——叛徒那条胜线
        在 33 局里一次都没出现过。

        已探明落点的排序键（全部可复现）：离最近英雄的步数越远越好 → 门越多
        （别钻进死胡同）→ 楼层 → 房间 key。
        """
        current = self._threat(engine, monster.room_key)
        best: str | None = None
        if options:
            best = max(
                options,
                key=lambda k: (
                    self._threat(engine, k),
                    len(engine._door_neighbors(k)),
                    engine.state.board[k].floor,
                    k,
                ),
            )
            if self._threat(engine, best) >= current:
                return best
        # 已探明的房间都逃不开了：p151 明文"可像探索者一样探索新房间"
        opened = self._open_new_room(engine, room)
        if opened is not None:
            return opened
        return best

    def _threat(self, engine: Any, room_key: str) -> int:
        """房间到最近存活英雄的步数（不可达为 9999）。"""
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return 9999
        return min(engine._path_length(hero.room_key, room_key) for hero in heroes)

    # ------------------------------------------------- 小精灵探索新房间
    def _open_new_room(self, engine: Any, room: Any) -> str | None:
        """p151："The wisp may explore new rooms as if it were an explorer, but
        does not draw cards or end its movement when discovering a room
        containing a symbol."

        引擎没有怪物探索的通用层，与 47 号蛇头同口径在 handler 里手写。放房
        只走 `_place_room`、不经过 `move_player`，所以符号房的抽牌与"探索后
        停止移动"两条结算都不会触发——原文的"但不抽牌、不停步"自动满足。
        """
        unknown = self._unknown_doors(engine, room)
        if not unknown:
            return None
        direction = max(unknown, key=lambda d: self._away_score(engine, room, d))
        dx, dy = DIRECTION_DELTAS[direction]
        target_pos = (room.floor, room.x + dx, room.y + dy)
        budget = len(engine.state.room_deck) + len(engine.state.room_discard) + 1
        while budget > 0:
            budget -= 1
            template = engine._draw_room_template(room.floor)
            if template is None:
                return None
            placements = engine._compute_explore_placements(template, direction, target_pos)
            if not placements:
                engine.state.room_discard.append(template.id)
                continue
            placement = placements[0]
            rotated = engine._build_rotated_template(template, placement["rotation"])
            new_room = engine._place_room(
                rotated, target_pos[1], target_pos[2], placement["rotation"]
            )
            engine._log(f"小精灵撞开了未知区域：{new_room.name}")
            return new_room.key
        return None

    def _unknown_doors(self, engine: Any, room: Any) -> list[str]:
        """该房通向未知区域的门（未占格、方向合法）。"""
        unknown = []
        for direction in sorted(room.doors):
            if direction not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[direction]
            if engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy)) is None:
                unknown.append(direction)
        return unknown

    def _away_score(self, engine: Any, room: Any, direction: str) -> int:
        """开新房间挑门口：新板块必在同层，故按格子的曼哈顿距离离英雄越远越好。"""
        dx, dy = DIRECTION_DELTAS[direction]
        pos = (room.x + dx, room.y + dy)
        distances = []
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            here = engine.state.board.get(hero.room_key)
            if here is None:
                continue
            distances.append(abs(here.x - pos[0]) + abs(here.y - pos[1]))
        return min(distances) if distances else 0


    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p151：小精灵不主动攻击（防守反击走引擎默认）。"""
        if getattr(monster, "template_id", "") != self.WISP:
            return False
        return True

    # ------------------------------------------------------------- 捕获
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if getattr(action, "id", "") == "catch_wisp":
                wisp = self._wisp(engine)
                if wisp is None or wisp.room_key != player.room_key:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "catch_wisp":
            return self._catch_wisp(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _catch_wisp(self, engine: Any, player: Any) -> bool:
        """p80：与小精灵同房做知识 4+，成功 +1 枚捕捉令牌（累计英雄数枚即胜）。"""
        wisp = self._wisp(engine)
        if wisp is None or wisp.room_key != player.room_key:
            return False
        ok = engine._resolve_check(player, "knowledge", self.CATCH_TARGET, "捕捉小精灵")
        if not ok:
            engine._log(f"{engine._player_label(player)} 伸手去抓，只抓住一把光。")
            return False
        engine._advance_haunt_track("capture_tokens")
        current = engine._haunt_track_value("capture_tokens")
        needed = engine._haunt_track_target("capture_tokens")
        engine._log(f"捕捉进度 {current}/{needed}——光一点点被攥住。")
        if current >= needed > 0:
            engine._set_winner("heroes", "那团光凝在地上，化回了失踪的同伴。")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p80：捕捉令牌满 → 英雄胜（_catch_wisp 已设胜方）
        if engine.state.winner == "heroes":
            return True
        # p151：轨道到 6 小精灵仍自由 → 叛徒胜
        if int(flags.get("wisp_track", 0)) >= self.ESCAPE_TRACK:
            engine._set_winner("traitor", "那团光冲出了房子——它自由了。")
            return True
        # 英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "没有人在追它了。")
            return True
        # 吸收兜底：p151 叛徒角色本就移出游戏，绝不能判"叛徒死 → 英雄胜"
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        wisp = self._wisp(engine)
        return [f"__room__{wisp.room_key}"] if wisp is not None else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = [
            f"逃脱轨道：{int(flags.get('wisp_track', 0))}/{self.ESCAPE_TRACK}（到 6 小精灵逃脱）。",
            f"捕捉进度：{engine._haunt_track_value('capture_tokens')}/"
            f"{engine._haunt_track_target('capture_tokens')}。",
        ]
        spores = self._spore_rooms(engine)
        if spores:
            lines.append(f"迷雾房间：{len(spores)} 间。")
        return lines
