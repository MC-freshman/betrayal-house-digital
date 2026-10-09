"""ExorcismMode（剧本 8）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class ExorcismMode(GenericModeHandler):
    """剧本 8 女妖哀嚎（Wail of the Banshee）。

    权威原文：英雄手册 p19 / 叛徒手册 p90。

    核心机制（此前数据只有"看起来对"的骨架，实际全未接上）：
    · 女妖不可被攻击（invulnerable），没有普通攻击；每次怪物阶段按 p90
      "移动计划"行动：掷两枚骰（0-2 面），和 0-4 直接对应五个选项：
        0 传送到 ≤7 格远的任意房间（途中不经任何房间）
        1 先选第一个房间，此后尽量左转（贴左墙）
        2 先选第一个房间，此后尽量直行；只剩左右可走时随机
        3 先选第一个房间，此后尽量右转（贴右墙）
        4 本回合由叛徒操控移动，且哀嚎对每位探险者至多生效一次
      贴墙规则（1/3 共用）：左/右转优先，不行直行，再不行反向转，
      死胡同从原路返回。
    · 哀嚎：女妖途经或停下的房间，每位探险者理智检定按总点分档受伤：
        6+ 受 1 骰精神伤害；3-5 受 2 骰；0-2 受 4 骰。持灵应板的叛徒
      免疫；板被偷走后不再免疫，偷板者自己也不获得免疫。
    · 驱魔（英雄胜）：成功次数 = 玩家人数即放逐女妖。每次成功需要一个
      房间/物品来源（理智：教堂/地窖/五芒星室/圣徽/灵应板；知识：图书
      馆/研究实验室/古书/水晶球），理智或知识 5+，每人每回合一次；每个
      来源只能成功使用一次（成功后来源作废，房间放一枚检定令牌）。
    · 已知简化：p90 女妖途经楼梯类房间的"定向传送"（二楼平台/塌房/画廊/
      门厅等）未实现——引擎连通图已含楼梯链接，抄近路近似；女妖不用
      神秘电梯（引擎怪物从不触发电梯效果，天然满足）。
    · 移动目标（选项 1-3 的"先选第一个房间"与选项 4 的操控）统一取
      "机器人叛徒选择朝最近英雄方向"，保证种子回放可复现。
    """

    mode = "exorcism"

    BANSHEE = "banshee"
    SANITY_ROOM_SOURCES = ["chapel", "crypt", "pentagram_chamber"]
    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_spirit_board"]
    KNOWLEDGE_ROOM_SOURCES = ["library", "research_laboratory"]
    KNOWLEDGE_ITEM_SOURCES = ["omen_book", "omen_crystal_ball"]
    ALL_SOURCES = (
        SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + KNOWLEDGE_ROOM_SOURCES + KNOWLEDGE_ITEM_SOURCES
    )
    # 贴墙转向（相对当前行进方向）：1=左墙，3=右墙
    WALL_TURN = {1: -1, 3: 1}

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        # p90：女妖令牌（大）放在叛徒所在房间；p19 检定令牌按需生成
        engine.spawn_token("banshee", label="女妖", role="marker", room_key=room_key)
        engine._haunt_flags().setdefault("used_exorcism_sources", [])

    # ------------------------------------------------------------- 女妖回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.BANSHEE:
            return False
        self._banshee_turn(engine, monster)
        return True  # 移动与哀嚎都已处理，跳过引擎默认追击/攻击

    def _banshee_turn(self, engine: Any, monster: Any) -> None:
        option = engine.roll_dice(2, "女妖移动计划")  # 两枚 0-2 骰 → 0..4
        steps = engine.roll_dice(getattr(monster, "speed", 8), "女妖速度")
        engine._log(f"女妖的移动计划掷出 {option}，可移动 {steps} 格。")
        target = engine._find_monster_target(monster)

        if option == 0:
            # 传送到任意 ≤7 格的房间（到达即停，仍会哀嚎）
            candidates = [
                key for key in engine.state.board
                if key != monster.room_key
                and engine._path_length(monster.room_key, key) <= 7
            ]
            if not candidates:
                engine._log("女妖周围七格内空无一物。")
                return
            dest = min(
                candidates,
                key=lambda key: (
                    engine._path_length(key, target.room_key) if target is not None else 0,
                    key,
                ),
            )
            monster.room_key = dest
            engine._log(f"女妖化作阴风，直接飘进了{engine.state.board[dest].name}。")
            self._wail(engine, dest, None)
            return

        if target is None:
            return
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) < 2:
            return  # 已与目标同房（引擎不会在此阶段调用，防御性返回）

        if option == 2:
            # 直行优先：沿最短路径走完剩余步数（途经房间照常哀嚎）
            remaining = path[1 : min(len(path) - 1, steps) + 1]
            for next_key in remaining:
                monster.room_key = next_key
                self._wail(engine, next_key, None)
                if engine.state.winner:
                    return
            return

        # 选项 1/3/4：第一格朝最近英雄方向；1/3 之后按贴墙规则，
        # 4 为叛徒操控（机器人叛徒选"向目标推进"，哀嚎去重一次）
        once_set: set | None = set() if option == 4 else None
        first = path[1]
        monster.room_key = first
        self._wail(engine, first, once_set)
        facing = self._facing(engine, monster.room_key, first)
        if option == 1 or option == 3:
            for _ in range(max(0, steps - 1)):
                nxt = self._wall_step(engine, monster.room_key, facing, option)
                if nxt is None or nxt == monster.room_key:
                    break
                facing = self._facing(engine, monster.room_key, nxt)
                monster.room_key = nxt
                self._wail(engine, nxt, None)
                if engine.state.winner:
                    return
        else:
            chase = engine._shortest_path(monster.room_key, target.room_key)
            for next_key in chase[1 : min(len(chase) - 1, steps - 1) + 1]:
                monster.room_key = next_key
                self._wail(engine, next_key, once_set)
                if engine.state.winner:
                    return

    def _facing(self, engine: Any, prev_key: str, curr_key: str) -> str:
        """上一房间 -> 当前房间 的几何方向；链接跳转等非正交移动返回空串。"""
        prev = engine.state.board.get(prev_key)
        curr = engine.state.board.get(curr_key)
        if not prev or not curr or prev.floor != curr.floor:
            return ""
        dx = curr.x - prev.x
        dy = curr.y - prev.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy):
                return direction
        return ""

    def _neighbors(self, engine: Any, room_key: str) -> list[str]:
        return engine._build_graph().get(room_key, [])

    def _wall_step(self, engine: Any, room_key: str, facing: str, option: int) -> str | None:
        """按贴墙优先级走一步：左/直/右/原路，返回下一房间；无路返回 None。"""
        neighbors = self._neighbors(engine, room_key)
        if not neighbors:
            return None
        if not facing:
            return neighbors[0]
        order = ["north", "east", "south", "west"]
        idx = order.index(facing)
        turn = self.WALL_TURN.get(option, 0)
        priority_dirs = [
            order[(idx + turn) % 4],   # 转向侧
            order[idx],                # 直行
            order[(idx - turn) % 4],   # 反向侧
            order[(idx + 2) % 4],      # 原路返回
        ]
        for direction in priority_dirs:
            matches = [k for k in neighbors if self._facing(engine, room_key, k) == direction]
            if matches:
                return matches[0]
        return neighbors[0]

    def _wail(self, engine: Any, room_key: str, once_set: set | None) -> None:
        """女妖哀嚎：房间里的探险者按理智检定分档吃精神伤害。

        once_set 非空（选项 4）时，本回合已中招的英雄跳过。
        """
        occupants = [
            p for p in engine.state.players
            if not p.dead and p.room_key == room_key
            and not (p.role == "traitor" and "omen_spirit_board" in p.items)
        ]
        for victim in occupants:
            if once_set is not None and victim.id in once_set:
                continue
            roll = engine._roll_attack(victim, "sanity")
            dice = 1 if roll >= 6 else (2 if roll >= 3 else 4)
            amount = engine.roll_dice(dice, "女妖哀嚎")
            if once_set is not None:
                once_set.add(victim.id)
            engine._log(
                f"女妖的哀嚎撕裂了{victim.name}的心智（理智检定 {roll}，"
                f"{dice} 骰 → {amount} 点精神伤害）。"
            )
            engine._deal_damage(victim, "mental", amount, source="女妖哀嚎")
            if victim.dead:
                break

    # ------------------------------------------------------------- 驱魔
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        used = set(engine._haunt_flags().get("used_exorcism_sources", []))
        return [action for action in actions if action.id not in used]

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """给 bot 判寻路目标用：成功用过的驱魔来源不再是目的地（p49/p90 一次性）。

        与 available_actions 的区别是**不看位置**——机器人必须能算出"该去哪间
        还没用过的来源房"，而不是等站进去了才发现行动不可用。8/11/22/38 共用。
        """
        return action_id in set(engine._haunt_flags().get("used_exorcism_sources", []))

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """驱魔来源：只有检定【成功】才作废来源并在房间放检定令牌（p49/p90）。

        底层 `_perform_generic_haunt_action` 只要行动执行过就返回 True，检定失败也是
        True——所以"可执行"不等于"成功"，不能拿它当消耗来源的依据。这里改用
        `exorcism_successes` 轨道的增量作为成功信号（来源行动全部声明
        `progress: exorcism_successes`，轨道到 target 后行动本身就不再用）。
        返回值仍是 `ok`：失败的尝试照样占掉"每人每回合一次剧本行动"的额度。
        8/11/22 号共用这份实现；38 号另有等价覆盖，行为一致。
        """
        if action_id not in self.ALL_SOURCES:
            return super().perform_action(engine, player, action_id, data)
        if action_id in set(engine._haunt_flags().get("used_exorcism_sources", [])):
            engine._log("这个驱魔来源已经成功用过，不能再用了。")
            return False
        before = engine._haunt_track_value("exorcism_successes")
        ok = super().perform_action(engine, player, action_id, data)
        if ok and engine._haunt_track_value("exorcism_successes") > before:
            used = list(engine._haunt_flags().get("used_exorcism_sources", []))
            if action_id not in used:
                used.append(action_id)
            engine._haunt_flags()["used_exorcism_sources"] = used
            kind = (
                "sanity_check"
                if action_id in self.SANITY_ROOM_SOURCES + self.SANITY_ITEM_SOURCES
                else "knowledge_check"
            )
            engine.spawn_token(kind, label="驱魔成功", role="check", room_key=player.room_key)
        return ok

    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "驱魔完成——女妖在圣咏中化为青烟消散了。")
            return True
        # p90 只规定两种终局（放逐 / 英雄全灭）：女妖按自己的计划行动，
        # 叛徒阵亡【不】构成英雄胜利。吸收引擎兜底，游戏继续。
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "女妖的哀嚎夺走了最后一个活着的灵魂。")
            return True
        return True
