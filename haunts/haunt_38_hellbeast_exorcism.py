"""HellbeastMode（剧本 38）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    _monster_id,
)
from .haunt_08_exorcism import ExorcismMode  # noqa: F401  继承自其他具体 handler


class HellbeastMode(ExorcismMode):
    """剧本 38 火蝠（Hellbeasts）。

    权威原文：英雄手册 p49 / 叛徒手册 p120。

    继承路子与 22 号 AbyssExorcismMode 相同（都继承 ExorcismMode 复用驱魔底座），
    而【不是】交接文档曾建议的"继承 24 号 BatSwarmMode"——经英文 PDF 原文核对，
    38 号火蝠与 24 号吸血蝠几乎全相反：
        · 火蝠不贴附英雄、不可被攻击、叛徒存活、伤害在怪物回合按"房间区域"结算；
        · 24 号蝙蝠贴附吸血、可被力量攻击杀死、叛徒开局即死、伤害按"贴附数"结算。
    而 38 号的驱魔来源清单与 22 号逐字一致（理智道具把灵应板换成戒指 omen_ring），
    所以照抄 AbyssExorcismMode 覆盖 SANITY_ITEM_SOURCES + 重算 ALL_SOURCES 的写法。
    全程不改 engine.py / content.py / ui.py，火蝠怪物层复用 bat 模板与既有钩子。

    已按原文实现：
        · 火蝠（bat 模板）Speed 3、不可攻击也不可被攻击（monster spec invulnerable=True，
          攻击闸门由引擎 _monster_invulnerable 承担）；不影响英雄移动（引擎怪物本就不
          阻挡移动，天然满足）。
        · 开局（p120）：叛徒存活（揭示者变叛徒）。取出「玩家数一半向上取整」只火蝠，
          全部放在作祟揭露房。
        · 怪物回合（p120 "You Must Do This On Your Turn"）：叛徒存活 → 走引擎正常怪物
          回合（在叛徒回合结束触发）。一次掷骰（roll_dice(速度3)）的结果同时决定
          「现有火蝠移动格数」与「新进揭露房的火蝠数」；先移动现有火蝠、再繁殖新蝠，
          天然满足"新蝠当回合不移动"。一个怪物回合只跑一次（last_swarm_turn 守卫）。
        · 灼烧（p120）：移动后，对每个"含≥1 活英雄且含≥1 火蝠"的房间，掷「该房火蝠数」
          枚骰，房内所有英雄受该总和的物理伤害。
        · 驱魔（p49，英雄胜）：成功次数 = 玩家数即放逐火蝠。理智 5+（教堂/地窖/五芒星室/
          圣徽/戒指）或知识 5+（图书馆/研究实验室/古书/水晶球），每人每回合一次，每个
          来源只能成功用一次（成功后作废，房间放检定令牌）——全部继承自 ExorcismMode。
        · 胜负：驱魔满员 → 英雄胜；英雄全灭 → 叛徒胜。叛徒存活操控火蝠，叛徒死亡
          【不】构成英雄胜利，吸收引擎兜底（老坑）。

    已知简化 / 解释性决策：
        ① 原文未指定"移动/繁殖"掷几颗骰，采用 roll_dice(火蝠速度=3)，与引擎怪物
           移动惯例（roll_dice(monster.speed)）一致，保证种子回放可复现。
        ② 原文未设火蝠数量上限，忠实实现不设上限（bot 局可能滚雪球致英雄必败，
           属难度/AI 深度问题，不在剧本层截断）。
        ③ 盔甲：原文"只防 1 点"，引擎既有盔甲是"挡掉整次物理伤害"，采用引擎既有
           语义（同 24 号已知简化）；不为对齐"只防 1 点"把一次灼烧拆成逐蝠多次
           _deal_damage（那样盔甲会逐次触发、语义更偏）。
        ④ 新蝠计入当回合灼烧：先移动现有蝠 → 繁殖新蝠 → 对当前所有同房蝠结算，
           与 p120"After you have moved your monsters, roll..."的顺序一致。
        ⑤ 8 骰上限：engine.roll_dice(count) 内部 count=max(1,min(8,count))，故单房间
           火蝠 >8 只时灼烧只掷 8 枚骰、少于"火蝠数"枚，伤害被系统性低估；因火蝠
           不设数量上限（见②），长局可能触发。属接受的引擎限制。
        ⑥ 道具驱魔令牌落点：道具来源（圣徽/戒指/古书/水晶球）成功驱魔时，检定令牌
           被放在英雄所在房间板块而非对应道具卡（继承 ExorcismMode 行为，8/22 号同款）；
           "来源不可复用"由 used_exorcism_sources 去重保证，功能正确，仅表现层与 p49
           字面（"on the item card"）有偏差。
    """

    mode = "hellbeast_exorcism"

    FIREBAT = "bat"
    DAMAGE_SOURCE = "火蝠灼烧"
    # 22 号同款：理智道具把 8 号的灵应板换成戒指
    SANITY_ITEM_SOURCES = ["omen_holy_symbol", "omen_ring"]
    ALL_SOURCES = (
        ExorcismMode.SANITY_ROOM_SOURCES + SANITY_ITEM_SOURCES
        + ExorcismMode.KNOWLEDGE_ROOM_SOURCES + ExorcismMode.KNOWLEDGE_ITEM_SOURCES
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """p120：叛徒存活；取「玩家数一半向上取整」只火蝠全放揭露房。

        刻意不调 super().setup（ExorcismMode.setup 会生成 8 号女妖令牌）；
        驱魔底座靠继承的方法即可，无需女妖令牌。不杀叛徒、不强制房间入场。
        """
        flags = engine._haunt_flags()
        flags.setdefault("used_exorcism_sources", [])
        flags["haunt_room"] = room_key
        flags["last_swarm_turn"] = -1
        count = (len(engine.state.players) + 1) // 2
        spec = self._firebat_spec(engine)
        born = 0
        for _ in range(count):
            if engine._spawn_single_haunt_monster(spec, room_key) is not None:
                born += 1
        room = engine.state.board.get(room_key)
        engine._log(
            f"{born} 只燃烧的火蝠从{room.name if room else '暗处'}里涌出，"
            f"翅膀上噼啪作响——叛徒要让它们喝饱人血。"
        )

    # ------------------------------------------------------------- 火蝠群回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.FIREBAT:
            return False  # 非火蝠交回引擎默认
        # 一个怪物回合只跑一次群集阶段（引擎会逐只火蝠调用本钩子）
        if int(engine._haunt_flags().get("last_swarm_turn", -1)) != engine.state.turn_count:
            self._run_swarm_phase(engine)
        return True  # 火蝠永不做引擎默认的追击/攻击

    def _run_swarm_phase(self, engine: Any) -> None:
        """p120：一次掷骰同时决定移动格数与新进揭露房的火蝠数；先移动后繁殖，
        再对每个"火蝠与英雄同房"的房间结算灼烧伤害。"""
        flags = engine._haunt_flags()
        flags["last_swarm_turn"] = engine.state.turn_count
        spec = self._firebat_spec(engine)
        speed = max(1, int(spec.get("speed", 3)))
        steps = engine.roll_dice(speed, "火蝠群移动")

        # 1) 先移动现有火蝠：每只朝最近英雄走至多 steps 格（借 BatSwarmMode 写法）
        for bat in self._bats(engine):
            target = engine._find_monster_target(bat)
            if target is None or bat.room_key == target.room_key:
                continue
            path = engine._shortest_path(bat.room_key, target.room_key)
            if len(path) > 1 and steps > 0:
                bat.room_key = path[min(len(path) - 1, steps)]

        # 2) 再繁殖 steps 只新火蝠到揭露房（新蝠当回合不移动）
        haunt_room = str(flags.get("haunt_room") or "")
        born = 0
        if haunt_room:
            for _ in range(max(0, steps)):
                if engine._spawn_single_haunt_monster(spec, haunt_room) is None:
                    break
                born += 1
        engine._log(
            f"火蝠群掷出 {steps}：现有火蝠各移动至多 {steps} 格，"
            f"{born} 只新火蝠在揭露房里破蛹而出。"
        )

        # 3) 结算房间灼烧伤害
        self._burn_rooms(engine)

    def _burn_rooms(self, engine: Any) -> None:
        """p120：对每个"含≥1 活英雄且含≥1 火蝠"的房间，掷「该房火蝠数」枚骰，
        房内所有英雄受该总和的物理伤害（盔甲由引擎自动结算）。"""
        counts: dict[str, int] = {}
        for bat in self._bats(engine):
            counts[bat.room_key] = counts.get(bat.room_key, 0) + 1
        for room_key, bat_count in counts.items():
            victims = [
                p for p in engine.state.players
                if not p.dead and p.role == "hero" and p.room_key == room_key
            ]
            if not victims:
                continue
            amount = engine.roll_dice(bat_count, "火蝠灼烧")
            if amount <= 0:
                continue
            room = engine.state.board.get(room_key)
            engine._log(
                f"{room.name if room else room_key} 里 {bat_count} 只火蝠一齐喷焰，"
                f"灼烧房内的英雄（{amount} 点物理伤害）。"
            )
            for victim in victims:
                engine._deal_damage(victim, "physical", amount, source=self.DAMAGE_SOURCE)

    # ------------------------------------------------------------- 工具
    def _bats(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.FIREBAT]

    def _firebat_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.FIREBAT) or {"template_id": self.FIREBAT, "name": "火蝠", "speed": 3})

    # ------------------------------------------------------------- 驱魔（覆盖基类）
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """覆盖 ExorcismMode.perform_action：忠实 p49"只有【成功】使用某来源，该来源
        才不可复用"——仅在驱魔检定真正成功时才作废来源并放检定令牌。

        基类 ExorcismMode 只要行动【可执行】（底层 _perform_generic_haunt_action 恒
        返回 True）就无条件 used_exorcism_sources.append + spawn_token(role="check")，
        但 exorcism_successes 轨道只在检定成功时推进；于是理智/知识 5+ 检定【失败】
        时来源被永久作废、令牌落下、轨道却不 +1。38 号 target=玩家数、仅 9 个来源，
        6 人局若失败 ≥4 次会把来源耗尽，出现"9 来源全 used、轨道 < target"的不可胜
        软锁。

        修法：绕过基类的无条件消耗——用 super(ExorcismMode, self) 直达祖父级
        GenericModeHandler → _perform_generic_haunt_action，以 exorcism_successes
        轨道增量作为"本次检定确实成功"的信号，仅在成功时复刻基类的全部成功副作用
        （used 去重记账 + 令牌 kind 判定 + spawn_token）。

        M10-19 更新：基类 `ExorcismMode.perform_action` 已按同一信号修好，这份覆盖
        与基类行为等价，保留只为留档；后续清理时**只删这份 perform_action 即可**，
        本类 setup 不能一起删（它刻意不调 super，以避免生成 8 号的女妖令牌）。
        """
        # 非驱魔来源：交回基类处理（ExorcismMode → GenericModeHandler）
        if action_id not in self.ALL_SOURCES:
            return super().perform_action(engine, player, action_id, data)
        # 已作废的来源不可复用（与基类同款守卫）
        if action_id in set(engine._haunt_flags().get("used_exorcism_sources", [])):
            engine._log("这个驱魔来源已经成功用过，不能再用了。")
            return False
        # 用轨道增量判定检定是否真正成功（绕过基类的"可执行即消耗"）
        before = engine._haunt_track_value("exorcism_successes")
        ok = super(ExorcismMode, self).perform_action(engine, player, action_id, data)
        after = engine._haunt_track_value("exorcism_successes")
        if ok and after > before:
            # 仅在检定成功时作废来源 + 放检定令牌（复刻基类成功副作用）
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

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_track_value("exorcism_successes") >= engine._haunt_track_target("exorcism_successes"):
            engine._set_winner("heroes", "驱魔完成——火蝠被赶回了最先孕育它们的那片地狱。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一名英雄在火蝠的烈焰里倒下，屋里只剩噼啪的火光。")
            return True
        return True  # 叛徒存活操控火蝠；吸收引擎"叛徒死亡即英雄胜"兜底

    # ------------------------------------------------------------- bot 寻路
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p49：英雄胜 = 驱魔成功次数满员；火蝠不可被攻击（monster invulnerable，
        见 7542 注释），追它纯浪费。引导英雄去还【没用过】的房间类驱魔来源
        （教堂/地窖/五芒星室/图书馆/研究实验室）；道具类来源（圣徽/戒指/古书/
        水晶球）英雄随身带着，在任意房间即可使用，无需专门寻路。"""
        flags = engine._haunt_flags()
        used = set(flags.get("used_exorcism_sources", []))
        goals: list[str] = []
        room_sources = self.SANITY_ROOM_SOURCES + self.KNOWLEDGE_ROOM_SOURCES
        for template_id in room_sources:
            if template_id in used:
                continue
            key = next(
                (k for k, r in engine.state.board.items()
                 if r.template_id == template_id and not engine._is_collapsed(k)),
                "",
            )
            if key:
                goals.append(key)
        return goals

    # ------------------------------------------------------------- 进度摘要
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """公开信息：火蝠总数 + "某房有 N 只火蝠与英雄同房"的灼烧预警。

        驱魔进度本身由 UI 的 ●○ 轨道渲染，这里不重复。火蝠位置是桌面公开的
        （bat 令牌摆在板块上），无需按 viewer 过滤。
        """
        lines: list[str] = []
        bats = self._bats(engine)
        lines.append(f"火蝠总数：{len(bats)} 只（不可被攻击，会在怪物回合灼烧同房英雄）。")
        counts: dict[str, int] = {}
        for bat in bats:
            counts[bat.room_key] = counts.get(bat.room_key, 0) + 1
        for room_key, count in sorted(counts.items()):
            heroes_here = [
                p for p in engine.state.players
                if not p.dead and p.role == "hero" and p.room_key == room_key
            ]
            if heroes_here:
                room = engine.state.board.get(room_key)
                name = room.name if room else room_key
                lines.append(f"⚠ {name}：{count} 只火蝠正与英雄同房——下个怪物回合会被灼烧。")
        return lines
