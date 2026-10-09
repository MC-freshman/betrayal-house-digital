"""VoodooMode（剧本 25）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
)


class VoodooMode(GenericModeHandler):
    """剧本 25 巫毒（Voodoo）。

    权威原文：英雄手册 p36 / 叛徒手册 p107。

    已按原文实现：
        · 开局（p107）：叛徒仍在场（揭示者变叛徒）。给每个英雄各分配一只
          娃娃（5 种），每种绑定两个候选房间（蜡=熔炉房/厨房、瓷=阳台/塔楼、
          石=地下湖/墓地、玻璃=五芒星室/教堂、布=花园/温室）；「恰有一间
          已发现」必须选已发现那间，两间都发现或都没发现时任选（bot 取
          列表第一间，原版叛徒任选）。每个英雄被宣读自己娃娃的描述引文
          ——即知道自己的娃娃类型与两个候选房间。娃娃绑定房间模板 id，
          候选房还没上桌也是合法放置。
        · 探索规则变更（p36）：解除"进带符号的新房间必须停"——本 handler
          覆盖 explore_stop_suspended + suppress_room_draw，探索不再强制
          停下、发现时不抽牌，把抽牌推迟到「结束移动的房间」：回合结束
          时停在新发现的符号房间才补抽；中途经过的房间不抽。
        · 搜寻（p36）：知识 2+，每回合一次（引擎行动经济天然保证）。成功
          后按盘面如实回答本房间有无娃娃；搜到自己房里的娃娃当场自动销毁，
          搜到别人的只公开位置（只有主人能"安全"销毁自己的娃娃）。搜寻
          落空的「这里没有」对全桌公开（实体桌游里答案是口头宣布的）。
        · 英雄死亡 → 其娃娃同时销毁（p36，on_player_died）。
        · 时钟（p107）：叛徒回合结束时把回合/伤害轨道 +1（从 1 起），届时
          每个未销毁的娃娃结算一次效果。叛徒死亡后按本仓库惯例由"本轮
          最后一名存活玩家"的回合结束代推（原文未覆盖叛徒死亡）。
        · 效果（p107）：蜡=自选掉 1 力量或速度；瓷=掷 4 骰 < 回合数即当场
          死亡；石=力量掷骰 < 回合数则每项属性各掉 1 点；玻璃=自选掉 1
          理智或知识；布=知识掷骰 < 回合数则受 2 点物理伤害。结算时逐条
          宣读效果引文。
        · 胜负（p36/p107）：英雄胜 = 所有娃娃销毁 且 存活英雄 ≥ 原英雄数
          一半（向上取整）；叛徒胜 = 开局英雄过半死亡（严格大于一半）。
          两者互斥；叛徒死亡不等于英雄胜（覆盖引擎兜底）。

    已知简化：
        · 「恰有一间已发现」之外的两难由 bot 固定取列表第一间；原版由叛徒
          任选（他会挑英雄难找的房间）。
        · p36「你可以找到任何娃娃的位置，但只能安全销毁自己的」——找到
          别人的娃娃只公开位置；原文未写主人是否可免检定直接销毁，本实现
          按较严格口径：主人仍须自己在该房间搜寻成功才能销毁。
        · 「不安全地销毁别人的娃娃」原文没有给出机制，未建模。
        · bot 英雄只搜自己娃娃的候选房间（或已被公开位置的娃娃房间）；
          不会主动替队友排查其它房间（人类可以）。
        · 蜡/玻璃娃娃的「自选掉哪项」：bot 在"掉 1 点不会死"的属性里掉数值
          较高的一项（两项都会死则掉前者），人类弹窗自选。
    """

    mode = "voodoo_dolls"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        dolls = self._dolls(engine)
        if not dolls:
            return []
        names = {"wax": "蜡", "china": "瓷", "stone": "石", "glass": "玻璃", "cloth": "布"}
        rows = [f"娃娃 {sum(1 for d in dolls if d['destroyed'])}/{len(dolls)} 已销毁"]
        for d in dolls:
            hero = next((p for p in engine.state.players if p.id == d["hero_id"]), None)
            who = hero.name if hero else "?"
            state = "已销毁" if d["destroyed"] else ("位置已公开" if d.get("found") else "下落不明")
            rows.append(f"  {names.get(d['kind'], d['kind'])}·{who}：{state}")
        return rows

    CANDIDATES = {
        "wax": ("furnace_room", "kitchen"),
        "china": ("balcony", "tower"),
        "stone": ("underground_lake", "graveyard"),
        "glass": ("pentagram_chamber", "chapel"),
        "rag": ("garden", "conservatory"),
    }
    DOLL_NAMES = {
        "wax": "蜡娃娃", "china": "瓷娃娃", "stone": "石娃娃",
        "glass": "玻璃娃娃", "rag": "布娃娃",
    }
    DESCRIPTION_QUOTES = {
        "wax": "你烧起来了！",
        "china": "下方的地面，正等着你。",
        "stone": "泥浆灌进嘴里，你喘不过气。",
        "glass": "到处都是邪恶，不神圣的邪恶。",
        "rag": "刺穿的伤口，泥土与鲜血。",
    }
    EFFECT_QUOTES = {
        "wax": "火对善与恶一视同仁。",
        "china": "一阵强风推了你一把。",
        "stone": "你在污秽里越陷越深，又黑又脏。",
        "glass": "不神圣的存在，盘踞在曾有善意的地方。",
        "rag": "血红，玫瑰之死。",
    }
    KIND_ORDER = ("wax", "china", "stone", "glass", "rag")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("dolls", [])
        flags.setdefault("cleared_rooms", [])
        flags.setdefault("pending_draws", {})
        heroes = [p for p in engine.state.players if p.role == "hero"]
        for index, hero in enumerate(heroes):
            kind = self.KIND_ORDER[index % len(self.KIND_ORDER)]
            candidates = self.CANDIDATES[kind]
            discovered = [tid for tid in candidates if self._is_discovered(engine, tid)]
            if len(discovered) == 1:
                chosen = discovered[0]  # p107：恰有一间已发现 → 必须选它
            else:
                chosen = candidates[0]  # 都发现/都没发现 → bot 取列表第一间（原版叛徒任选）
            flags["dolls"].append(
                {"kind": kind, "hero_id": hero.id, "room_template": chosen,
                 "destroyed": bool(hero.dead), "found": False}
            )
            if hero.dead:
                # p36：英雄死亡其娃娃同时销毁。探索阶段就倒下的英雄开局即
                # 触发这条，否则一只永远无人能销毁的娃娃会把英雄胜利锁死。
                engine._log(f"{hero.name} 已不在人世——对应的那只{self.DOLL_NAMES[kind]}随之碎裂。")
                continue
            engine._log(f"{hero.name} 听到了一段引文：「{self.DESCRIPTION_QUOTES[kind]}」")
        engine._log("叛徒已经把和每个人一一对应的巫毒娃娃藏进了这座房子。")

    def _is_discovered(self, engine: Any, template_id: str) -> bool:
        return any(
            room.template_id == template_id and room.revealed and not engine._is_collapsed(key)
            for key, room in engine.state.board.items()
        )

    # ----------------------------------------------------------- 状态查询
    def _dolls(self, engine: Any) -> list[dict]:
        return list(engine._haunt_flags().get("dolls", []) or [])

    def _own_doll(self, engine: Any, player: Any) -> dict | None:
        return next(
            (d for d in self._dolls(engine) if d["hero_id"] == player.id and not d["destroyed"]),
            None,
        )

    def _destroy_doll(self, engine: Any, doll: dict, reason: str) -> None:
        doll["destroyed"] = True
        engine._log(reason)
        engine.check_victory()

    # ------------------------------------------------- 探索规则变更（p36）
    def explore_stop_suspended(self, engine: Any, player: Any) -> bool:
        return True

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        """发现符号房间时不立刻抽牌：抽牌推迟到「结束移动的房间」（p36）。"""
        if not room.symbol:
            return False
        pending = engine._haunt_flags().setdefault("pending_draws", {})
        pending[str(room.key)] = player.id
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        dolls = self._dolls(engine)
        if not any(not d["destroyed"] for d in dolls):
            return []  # 全部销毁：没有可搜寻的东西了
        room = engine.current_room(player)
        cleared = engine._haunt_flags().get("cleared_rooms", [])
        if room.template_id in cleared:
            return []  # 这间房已被如实问过"没有"——再问不会得到新答案
        if player.control == "bot" and player.role == "hero":
            own = self._own_doll(engine, player)
            if own is None:
                return []
            in_play = set(self.CANDIDATES[own["kind"]])
            if own["found"]:
                in_play.add(own["room_template"])
            if room.template_id not in in_play:
                return []  # bot 只在自己娃娃的候选房间里搜寻
        return actions

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "search_doll":
            return super().perform_action(engine, player, action_id, data)
        room = engine.current_room(player)
        # p36：在当回合新发现的符号房间里搜寻 → 先抽一张符号牌（不打断移动）
        pending = engine._haunt_flags().setdefault("pending_draws", {})
        key = str(room.key)
        if pending.get(key) == player.id and room.symbol:
            pending.pop(key, None)
            engine._draw_symbol_card(player, room.symbol, stop_movement=False)
        if not engine._resolve_check(player, "knowledge", 2, "搜寻巫毒娃娃"):
            engine._log(f"{player.name} 在{room.name}翻找了半天，什么也没翻出来。")
            return True
        doll = next(
            (d for d in self._dolls(engine) if not d["destroyed"] and d["room_template"] == room.template_id),
            None,
        )
        if doll is None:
            cleared = engine._haunt_flags().setdefault("cleared_rooms", [])
            if room.template_id not in cleared:
                cleared.append(room.template_id)
            engine._log(f"叛徒如实回答：{room.name}里没有巫毒娃娃。")
            return True
        doll["found"] = True
        if doll["hero_id"] == player.id:
            self._destroy_doll(
                engine, doll,
                reason=f"{player.name} 在{room.name}找到了自己的{self.DOLL_NAMES[doll['kind']]}，当场把它砸了个粉碎！",
            )
        else:
            owner = next((p for p in engine.state.players if p.id == doll["hero_id"]), None)
            owner_name = owner.name if owner is not None else "某位英雄"
            engine._log(
                f"{player.name} 在{room.name}找到了{owner_name}的{self.DOLL_NAMES[doll['kind']]}——"
                "只有娃娃的主人能安全地销毁它。"
            )
        return True

    # ------------------------------------------------------- 时钟与效果
    def on_turn_end(self, engine: Any, player: Any) -> None:
        pending = engine._haunt_flags().setdefault("pending_draws", {})
        room = engine.current_room(player)
        key = str(room.key)
        # p36：只有「结束移动的房间」有符号才抽牌；没停在里面的一律作废
        if pending.get(key) == player.id and room.symbol:
            pending.pop(key, None)
            engine._draw_symbol_card(player, room.symbol, stop_movement=False)
        for stale in [k for k, owner in pending.items() if owner == player.id]:
            pending.pop(stale, None)
        # p107 时钟：叛徒回合结束推进；叛徒出局后由本轮最后一名存活玩家代推
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            if player.id == traitor.id:
                self._advance_clock(engine)
        elif _is_last_in_round(engine, player):
            self._advance_clock(engine)

    def _advance_clock(self, engine: Any) -> None:
        if engine.state.winner:
            return
        turn_no = engine._advance_haunt_track("turn_damage", 1)
        engine._log(f"回合/伤害轨道推进到 {turn_no}。")
        for doll in self._dolls(engine):
            if doll["destroyed"] or engine.state.winner:
                continue
            owner = next((p for p in engine.state.players if p.id == doll["hero_id"]), None)
            if owner is None or owner.dead:
                continue
            engine._log(f"「{self.EFFECT_QUOTES[doll['kind']]}」")
            self._apply_effect(engine, owner, doll, turn_no)
        engine.check_victory()

    def _apply_effect(self, engine: Any, hero: Any, doll: dict, turn_no: int) -> None:
        kind = doll["kind"]
        name = self.DOLL_NAMES[kind]
        if kind == "wax":
            stat = self._choose_loss(engine, hero, ("might", "speed"))
            engine._apply_stat_loss(hero, stat, 1)
            engine._check_player_death(hero)
        elif kind == "china":
            roll = engine.roll_dice(4, f"{name}坠落")
            if roll < turn_no:
                engine._log(f"{name}从高处坠下摔得粉碎——{hero.name} 当场死亡。")
                for stat in ("might", "speed", "sanity", "knowledge"):
                    hero.stats[stat] = 0
                engine._check_player_death(hero)
                self._destroy_doll_if_dead(engine, doll, hero)
            else:
                engine._log(f"{name}在风中摇晃，但没有落下（掷出 {roll}，回合数 {turn_no}）。")
        elif kind == "stone":
            roll = self._trait_roll(engine, hero, "might", f"{name}窒息")
            if roll < turn_no:
                engine._log(f"{hero.name} 快要窒息了，每项属性各失去 1 点。")
                for stat in ("might", "speed", "sanity", "knowledge"):
                    engine._apply_stat_loss(hero, stat, 1)
                engine._check_player_death(hero)
                self._destroy_doll_if_dead(engine, doll, hero)
            else:
                engine._log(f"{hero.name} 憋着气撑了过去（掷出 {roll}，回合数 {turn_no}）。")
        elif kind == "glass":
            stat = self._choose_loss(engine, hero, ("sanity", "knowledge"))
            engine._apply_stat_loss(hero, stat, 1)
            engine._check_player_death(hero)
        elif kind == "rag":
            roll = self._trait_roll(engine, hero, "knowledge", f"{name}绞紧")
            if roll < turn_no:
                engine._log(f"玫瑰的荆棘绞紧了——{hero.name} 受到 2 点物理伤害。")
                engine._deal_damage(hero, "physical", 2, source="血红的玫瑰")
                engine._check_player_death(hero)
                self._destroy_doll_if_dead(engine, doll, hero)
            else:
                engine._log(f"{hero.name} 挣脱了荆棘（掷出 {roll}，回合数 {turn_no}）。")

    def _destroy_doll_if_dead(self, engine: Any, doll: dict, hero: Any) -> None:
        # p36：英雄死亡时其娃娃同时销毁（China/Stone/Rag 直接致死的路径
        # 不走 on_player_died 的兜底时在这里补上；引擎死亡钩子会再兜一次）
        if hero.dead and not doll["destroyed"]:
            self._destroy_doll(engine, doll, reason=f"{hero.name} 倒下了，对应的那只巫毒娃娃随之碎裂。")

    def _trait_roll(self, engine: Any, hero: Any, stat: str, label: str) -> int:
        """属性掷骰的原始结果（石/布娃娃比较的是掷骰值与回合数，不是过线）。"""
        dice = max(1, min(8, engine._effective_stat(hero, stat) + engine._check_bonus(hero, stat)))
        return engine.roll_dice(dice, label)

    def _choose_loss(self, engine: Any, hero: Any, stats: tuple[str, str]) -> str:
        """「自选失去 1 点 X 或 Y」的确定性策略。

        bot：优先在「掉 1 点不会死」的属性里选当前数值较高的一项（平手取
        前者）；两项都会致死时掉前者。注意不能只比数值——轨道最底格的
        数值再高，掉 1 点也是直接见骷髅（实测 157 种子 P2 速度 2→0 当场死）。
        人类：弹窗自选。
        """
        if getattr(hero, "control", "bot") != "bot":
            labels = {"might": "力量", "speed": "速度", "sanity": "理智", "knowledge": "知识"}
            idx = engine.prompter.choose_from_list(
                "巫毒娃娃",
                f"{hero.name}：要失去 1 点{labels[stats[0]]}还是{labels[stats[1]]}？",
                [labels[stats[0]], labels[stats[1]]],
            )
            if idx is not None and 0 <= idx < len(stats):
                return stats[idx]

        def is_safe(stat: str) -> bool:
            track = engine._stat_track(hero, stat)
            if track:
                return int(hero.stat_positions.get(stat, 0)) >= 1
            return hero.stats.get(stat, 0) - 1 > 0

        pool = [s for s in stats if is_safe(s)] or list(stats)
        return max(pool, key=lambda s: hero.stats.get(s, 0))

    # --------------------------------------------------------- 死亡联动
    def on_player_died(self, engine: Any, player: Any) -> None:
        # p36：英雄死亡时，他的娃娃同时被销毁
        for doll in self._dolls(engine):
            if doll["hero_id"] == player.id and not doll["destroyed"]:
                self._destroy_doll(
                    engine, doll,
                    reason=f"{player.name} 倒下了，对应的那只巫毒娃娃随之碎裂。",
                )

    # ------------------------------------------------------------ bot
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero" or player.dead:
            return []
        own = self._own_doll(engine, player)
        if own is None:
            return []
        if own["found"]:
            return [own["room_template"]]  # 位置已被公开：直奔那间房
        cleared = set(engine._haunt_flags().get("cleared_rooms", []))
        return [tid for tid in self.CANDIDATES[own["kind"]] if tid not in cleared]

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        heroes = [p for p in engine.state.players if p.role == "hero"]
        alive = [p for p in heroes if not p.dead]
        total = len(heroes)
        # p107：过半英雄死亡 → 叛徒胜（严格大于一半）
        if total and (total - len(alive)) * 2 > total:
            engine._set_winner("traitor", "黑暗里，一排按钮眼睛齐刷刷地眨了一下——过半英雄死了。")
            return True
        dolls = self._dolls(engine)
        # p36：销毁所有娃娃 且 存活英雄 ≥ 一半（向上取整）→ 英雄胜
        if dolls and all(d["destroyed"] for d in dolls) and len(alive) * 2 >= total:
            engine._set_winner("heroes", "最后一只娃娃被砸得粉碎，诅咒的丝线断了——活下来的人比死去的多。")
            return True
        return True  # 覆盖引擎「叛徒死亡→英雄胜」兜底：娃娃时钟不随叛徒死亡停下
