"""NightMurderMode（剧本 50）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
    _monster_id,
)


class NightMurderMode(GenericModeHandler):
    """剧本 50「A Little Night Murder / 小小夜谋」（英雄手册 p61 / 叛徒手册 p132）。

    老普雷斯蒂科特死在了大楼梯底下，遗嘱已经宣读：只要在房子里待到天亮，
    遗产就归你们。只有一个问题——屋里那些贪婪的仆人已经和那个被排除在
    遗嘱之外的亲戚谈好了分成。活到黎明，钱就是你们的。

    · 开局（p132）：仆人令牌数 = 英雄数；前三个各放在**不同楼层**的空房间，
      多余的放任意空房；没有空房时平均分配到已占用的房间（同 21/28 号
      "房不够就叠放"口径）。仆人按普通怪物处理。
    · 夜晚推进（p132）：叛徒回合结束时把回合/伤害轨道推进一格；叛徒若已死，
      由"本轮最后一名存活玩家"代跑——p132 明说"叛徒死了照样能赢"，
      所以计时器绝不能因为叛徒出局而停摆（4 号 spider_timer 同款坑）。
    · 仆人强化表（p132）：Turn 0-3 → 3/3/3；4-7 → 4/4/4；8 → 5/5/5；
      9 → 6/6/6。每次轨道推进后重算全体仆人属性（45 号蜘蛛成长同款写法）。
    · 胜负（p61/p132）：轨道推进到 10（日出）→ 存活的英雄获胜分遗产；
      黎明前英雄全灭 → 叛徒胜。叛徒出局不判英雄胜（吸收兜底）。

    已知简化：
        · "空房间"按"没有玩家的房间"判定（原版 occupied 主要指探险者）。
        · 日出时的"存活英雄"取作祟后仍活着的英雄；仆人继续存在不影响结算。
    """

    mode = "night_survival"

    SERVANT = "servant"
    DAWN = 10
    # p132 仆人强化表（轨道值 → speed/might/sanity），实际取值见 _apply_strength
    STRENGTH_TABLE = "0-3→3/3/3；4-7→4/4/4；8→5/5/5；9→6/6/6"

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        engine._haunt_tracks().setdefault(
            "night_timer", {"label": "夜晚进度（日出）", "target": self.DAWN, "value": 0}
        )["target"] = self.DAWN

        hero_count = sum(1 for p in engine.state.players if p.role == "hero")
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.SERVANT, {"template_id": self.SERVANT, "name": "贪婪仆人"})
        )
        for target in self._servant_rooms(engine, hero_count, room_key):
            engine._spawn_single_haunt_monster(spec, target)
        engine._log(
            f"{hero_count} 名仆人从走廊尽头现身——他们要你们熬不过今夜。"
        )

    def _servant_rooms(self, engine: Any, count: int, room_key: str) -> list[str]:
        """p132：前三个尽量放在不同楼层的空房，其余放任意空房。"""
        occupied = {p.room_key for p in engine.state.players if not p.dead}
        by_floor: dict[int, list[str]] = {}
        for key, room in sorted(engine.state.board.items()):
            if key in occupied:
                continue
            by_floor.setdefault(room.floor, []).append(key)
        chosen: list[str] = []
        # 前三个：尽量各占一层（先按天亮前分布最广的方式取）
        for floor in sorted(by_floor, reverse=True):
            if len(chosen) >= min(3, count):
                break
            if by_floor[floor]:
                chosen.append(by_floor[floor].pop(0))
        # 余下：任意空房
        rest = [key for keys in by_floor.values() for key in keys]
        while len(chosen) < count and rest:
            chosen.append(rest.pop(0))
        # 空房不够：平均分配到已占用的房间（21/28 号同口径）
        while len(chosen) < count:
            pool = sorted(engine.state.board) or [room_key]
            chosen.append(pool[len(chosen) % len(pool)])
        return chosen[:count]

    # ------------------------------------------------------------- 夜晚
    def _servants(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.SERVANT]

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p132：叛徒回合结束推进夜晚；叛徒已死则由本轮最后存活玩家代跑。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            should_tick = player.id == traitor.id
        else:
            should_tick = _is_last_in_round(engine, player)
        if not should_tick:
            return
        current = engine._advance_haunt_track("night_timer")
        engine._log(f"夜色又深了一层（{current}/{self.DAWN}）。")
        self._apply_strength(engine, current)

    def _apply_strength(self, engine: Any, turn: int) -> None:
        """p132 强化表：0-3 → 3/3/3；4-7 → 4/4/4；8 → 5/5/5；9 → 6/6/6。"""
        if turn >= 9:
            stats = (6, 6, 6)
        elif turn >= 8:
            stats = (5, 5, 5)
        elif turn >= 4:
            stats = (4, 4, 4)
        else:
            stats = (3, 3, 3)
        for monster in self._servants(engine):
            monster.speed, monster.might, monster.sanity = stats

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p132：黎明前英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "最后一个继承人也倒下了——仆人们举起了香槟。")
            return True
        # p61：撑到 Turn 10 日出 → 英雄胜（存活者分遗产）
        if engine._haunt_track_value("night_timer") >= self.DAWN:
            engine._set_winner("heroes", "晨光透过窗户洒进来——你们熬过了这一夜。")
            return True
        # 吸收兜底：p132 明说叛徒死了照样能赢（仆人继续），绝不判英雄胜
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def _best_melee_dice(self, engine: Any, player: Any) -> int:
        """这名英雄用最趁手的近战武器能掷几枚骰（力量 + 武器加成）。"""
        might = int((getattr(player, "stats", {}) or {}).get("might", 0))
        best = might
        for card_id in getattr(player, "items", []):
            card = engine.catalog.cards.get(card_id)
            if card is None or "weapon" not in card.tags or "ranged" in card.tags:
                continue
            best = max(best, might + int((card.bonus or {}).get("attack", 0)))
        return best

    def _has_ranged_weapon(self, engine: Any, player: Any) -> bool:
        for card_id in getattr(player, "items", []):
            card = engine.catalog.cards.get(card_id)
            if card is not None and "weapon" in card.tags and "ranged" in card.tags:
                return True
        return False

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """p61：英雄的活法是**撑到日出**，不是清场——仆人被打只是击晕，下回合照回来。

        实测（6 局诊断 + seed109/4p 逐回合）：英雄全灭在"夜晚 1-3/10"，死因是自己的
        送死攻击——`2 对 3`、`0 对 1`、`3 对 6`、`2 对 4` 这类交换落败后按 p20 吃差值
        反击，一个个倒下（seed109 里两名英雄都是这么死的），而仆人只是昏迷一回合。

        阈值取"骰数**不超过**仆人力量就别打"（比 29/30 号的 `<` 更严）：本剧本英雄的
        目标是活到天亮，连五五开的交换都不划算。A/B（18 局口径）：松档 1 胜、严格档
        1 胜、完全不打 0 胜、再加险区 1 胜 —— 胜率不动（夜晚进度中位仅 3-4/10），说明
        真正的瓶颈是引擎怪物持续追击 + 仆人 3/3/3→6/6/6 递增 + 要撑满 10 轮，属结构性
        难度；这里保留严格档只是让机器人打得更像人（不白送反击伤害）。
        """
        if getattr(player, "role", None) != "hero":
            return False
        if _monster_id(target) != self.SERVANT:
            return False
        if getattr(target, "stunned_turns", 0) > 0:
            return False  # 已昏迷：白送的输出窗口
        if self._has_ranged_weapon(engine, player):
            return False  # p20：远程攻击落败不受伤
        return self._best_melee_dice(engine, player) <= int(getattr(target, "might", 0))

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        current = engine._haunt_track_value("night_timer")
        lines = [f"夜晚进度：{current}/{self.DAWN}（撑到日出即英雄胜）。"]
        servants = self._servants(engine)
        if servants:
            sample = servants[0]
            lines.append(f"仆人：{len(servants)} 名，当前 {sample.speed}/{sample.might}/{sample.sanity}。")
        return lines
