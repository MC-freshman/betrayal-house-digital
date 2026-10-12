"""EternalGloryMode（剧本 61）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class EternalGloryMode(GenericModeHandler):
    """剧本 61 永恒荣耀（Eternal Glory）。

    权威原文：英雄手册 p72 / 叛徒手册 p143。

    机制（逐条对照原文）：
      · 开局：雕像令牌→画廊、石棺令牌→墓地、古甲令牌→酒窖（房间不在场则
        拉进屋子）；盾牌令牌归叛徒；长矛放在作祟房间地上；幽灵战士
        （Speed 3 / Might 5）绑定长矛。说服轨道与鼓舞轨道归零。
      · 英雄胜线：把长矛带进任一遗物房，同房英雄每回合可做一次知识检定代替
        攻击，**按总点分档**推说服轨道（≤2 拒绝不推 / 3-5 +1 / 6-8 +2 / 9+ +3）。
        轨道达到「作祟时英雄数 × 2」时在该房放一枚安息印记，**两间不同房间**
        各有一枚即获胜。长矛离开所在房间时轨道立刻归零（原文 reset to zero）。
      · 叛徒胜线：与长矛同房时改为做知识或理智检定，6+ 记一次鼓舞；
        累计 6 次即让幽灵重燃战意（叛徒胜）。盾牌在自己身上时多掷 2 骰
        （封顶 8），但要让英雄看见「盾牌让幽灵兴奋起来」。
      · 长矛控制：英雄回合开始时若手持长矛须做理智 4+；拾取或被交给长矛时
        同样检定。失败则幽灵以「力量 4 攻击」打过来（幽灵输了不受损）；
        受伤者掉矛，且本回合不能再拾起。
      · 自动挥击：英雄进入或结束回合于长矛所在房间时须做速度 3+，失败吃
        1 骰物理伤害（无人持矛时照样触发）。
      · 幽灵只在**无人持矛**时行动（带矛游走并攻击）；持矛英雄不能攻击，
        幽灵与长矛本身也不可被攻击（引擎本就没有针对令牌的攻击入口）。

    已知简化：
      · 盾牌只作为叛徒身上的携带令牌，未接通用物品层的「丢下/交易/被偷」
        （bot 与人类都不会主动交出，与原文的差别仅在极端局面）。
      · 「战斗中偷长矛需 ≥3 点物理伤害」沿用引擎通用的 special_steal 阈值
        （净胜 >2），比原文严一格。
      · 叛徒「化作虚体免除物理伤害、代价是丢光携带物」未建模——它牵动全局
        伤害结算入口，按现状留作后续专项。
    """

    mode = "ghost_warrior"

    RELICS = [
        ("statue_relic", "gallery", "雕像"),
        ("sarcophagus_relic", "graveyard", "石棺"),
        ("ancient_armor", "wine_cellar", "古甲"),
    ]
    INSPIRE_NEEDED = 6

    # ------------------------------------------------------------- 工具
    def _hero_count(self, engine: Any) -> int:
        return sum(1 for p in engine.state.players if p.role == "hero")

    def _spear(self, engine: Any) -> Any:
        return next(iter(engine.tokens_of_kind("spear")), None)

    def _spear_room(self, engine: Any) -> str | None:
        """长矛当前所在房间（被携带时算携带者所在房间）。"""
        token = self._spear(engine)
        if token is None:
            return None
        if token.holder is not None:
            holder = next((p for p in engine.state.players if p.id == token.holder), None)
            return holder.room_key if holder is not None else None
        return token.room_key or None

    def _spear_holder(self, engine: Any) -> Any:
        token = self._spear(engine)
        if token is None or token.holder is None:
            return None
        return next((p for p in engine.state.players if p.id == token.holder), None)

    def _relic_room_for(self, engine: Any, room_key: str) -> str | None:
        relic_rooms = engine._haunt_flags().get("relic_rooms", {})
        for token_kind, rk in relic_rooms.items():
            if rk == room_key:
                return token_kind
        return None

    def _drop_spear(self, engine: Any, player: Any) -> None:
        token = self._spear(engine)
        if token is None:
            return
        engine.place_token(token.uid, player.room_key)
        engine._log(f"{player.name} 没能握住长矛——长矛脱手掉在地上。")

    def _ghost_strike(self, engine: Any, player: Any) -> bool:
        """p72：幽灵以「力量 4 攻击」打过来，幽灵输了不受任何损伤。"""
        ghost_roll = engine.roll_dice(4, "幽灵战士")
        hero_roll = engine._roll_attack(player, "might")
        engine._log(f"幽灵战士挥矛刺向{player.name}：{ghost_roll} 对 {hero_roll}。")
        if ghost_roll > hero_roll:
            engine._deal_damage(player, "physical", ghost_roll - hero_roll, source="幽灵战士")
            return True
        return False

    def _control_check(self, engine: Any, player: Any) -> bool:
        """p72：持矛英雄理智 4+ 才能握稳；失败被幽灵攻击，受伤即掉矛。"""
        roll = engine._roll_attack(player, "sanity")
        if roll >= 4:
            engine._log(f"{player.name} 握紧了命运之矛（理智 {roll}）。")
            return True
        engine._log(f"{player.name} 压不住长矛的挣扎（理智 {roll}）。")
        hurt = self._ghost_strike(engine, player)
        if hurt and not player.dead:
            self._drop_spear(engine, player)
            lock = engine._haunt_flags().setdefault("spear_locked", {})
            lock[str(player.id)] = int(engine._haunt_flags().get("turn_seq", 0))
        return False

    def _wild_spear(self, engine: Any, player: Any) -> None:
        """p72：进入/结束回合于长矛所在房间须做速度 3+，否则 1 骰物理伤害。"""
        if player.dead or player.role != "hero":
            return
        if engine.tokens_held_by(player.id, "spear"):
            return
        if player.room_key != self._spear_room(engine):
            return
        roll = engine._roll_attack(player, "speed")
        if roll >= 3:
            engine._log(f"{player.name} 避开了乱舞的长矛（速度 {roll}）。")
            return
        amount = engine.roll_damage_dice(1, "长矛乱舞")
        engine._log(f"长矛在{player.name}面前疯狂乱舞（速度 {roll}）——{amount} 点物理伤害。")
        engine._deal_damage(player, "physical", amount, source="疯狂的长矛")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["rest_token_rooms"] = []
        flags["inspire_count"] = 0
        flags["spear_locked"] = {}
        flags["turn_seq"] = 0
        flags["hero_count_at_start"] = self._hero_count(engine)
        engine._set_haunt_track_value("persuasion_track", 0)
        engine._set_haunt_track_value("inspire_track", 0)
        # p72：达标线 = 2 × 作祟时英雄数，按人数动态钉进轨道（UI 才能显示对）。
        engine._haunt_tracks().setdefault("persuasion_track", {})["target"] = (
            2 * int(flags["hero_count_at_start"])
        )

        # p72：三件遗物落进画廊/墓地/酒窖；房间不在场时先拉进屋子
        # （作祟后探险者不再主动探索，否则遗物可能整局不出现）。
        relic_rooms = flags.setdefault("relic_rooms", {})
        for token_kind, template_id, label in self.RELICS:
            key = next((k for k, r in engine.state.board.items() if r.template_id == template_id), None)
            if key is None:
                key = engine._ensure_room_in_play(template_id, room_key)
            if key:
                engine.spawn_token(token_kind, label=label, role="marker", room_key=key)
                relic_rooms[token_kind] = key

        # 长矛放在作祟房间的地上（无人持有时幽灵才带着它游走）。
        engine.spawn_token("spear", label="命运之矛", role="marker", room_key=room_key)
        flags["last_spear_room"] = room_key

        spec = next((s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == "ghost"), {})
        spec = dict(spec)
        spec["name"] = "幽灵战士"
        engine._spawn_single_haunt_monster(spec, room_key)

        # p143：盾牌令牌归叛徒，可丢可交易可被偷（本仓库只做携带令牌）。
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine.spawn_token("shield", label="盾牌", role="carried", holder=traitor.id)
        engine._log('幽灵战士手持长矛现身——"谁能与我匹敌！"')

    # ------------------------------------------------------------- 生命周期
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if not flags.get("relic_rooms"):
            return
        flags["turn_seq"] = int(flags.get("turn_seq", 0)) + 1
        # p72：长矛一旦离开所在房间，说服轨道清零（跨房间累计必须重新来过）。
        room_key = self._spear_room(engine)
        if room_key != flags.get("last_spear_room"):
            flags["last_spear_room"] = room_key
            if engine._haunt_track_value("persuasion_track") > 0:
                engine._set_haunt_track_value("persuasion_track", 0)
                engine._log("长矛离开了原来的房间，说服进度全部作废。")
        if player.dead or player.role != "hero":
            return
        # p72：回合开始时手持长矛须通过理智 4+
        if engine.tokens_held_by(player.id, "spear"):
            self._control_check(engine, player)

    def on_turn_end(self, engine: Any, player: Any) -> None:
        self._wild_spear(engine, player)

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        self._wild_spear(engine, player)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        locked = flags.get("spear_locked", {})
        held = bool(engine.tokens_held_by(player.id, "spear"))
        result = []
        for action in actions:
            if action.id == "persuade_ghost":
                if not held:
                    continue
                if self._relic_room_for(engine, player.room_key) is None:
                    continue
            elif action.id == "pick_up_spear":
                if held or not engine.tokens_in_room(player.room_key, "spear"):
                    continue
                if locked.get(str(player.id)) == int(flags.get("turn_seq", 0)):
                    continue
            elif action.id == "inspire_ghost":
                if held or not engine.tokens_in_room(player.room_key, "spear"):
                    continue
            result.append(action)
        return result

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """机器人眼里不可用的剧本行动（与 available_actions 同源，但不看位置）。"""
        flags = engine._haunt_flags()
        held = bool(engine.tokens_held_by(player.id, "spear"))
        if action_id == "persuade_ghost":
            if not held:
                return True
            # 本房已经留下安息印记：再劝也没有意义，机器人必须换到下一间遗物房
            # （批 13 实测：不挡这一条时，英雄在画廊把说服轨道刷到封顶 20 后
            # 站了 60 多个回合，第二枚印记永远拿不到）。
            if player.room_key in set(flags.get("rest_token_rooms", [])):
                return True
            return False
        if action_id == "pick_up_spear":
            if held:
                return True
            return bool(self._spear_holder(engine))
        if action_id == "inspire_ghost":
            return held
        return False

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """本房已留下安息印记 → 立刻动身去下一间遗物房（否则原地空转）。"""
        if player.role != "hero":
            return False
        if not engine.tokens_held_by(player.id, "spear"):
            return False
        return player.room_key in set(engine._haunt_flags().get("rest_token_rooms", []))

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄：没矛去长矛所在房，有矛去还没放印记的遗物房。

        叛徒：去长矛所在房刷鼓舞（凑满 6 次是它的主动胜线），
        长矛被英雄拿着时改追持矛者。
        """
        flags = engine._haunt_flags()
        relic_rooms = flags.get("relic_rooms", {})
        if not relic_rooms:
            return []
        if player.role == "hero":
            if engine.tokens_held_by(player.id, "spear"):
                done = set(flags.get("rest_token_rooms", []))
                # 注意：bot_goal_rooms 返回的**房间 key 必须带 `__room__` 前缀**，
                # 否则会被当成模板 id 去找同模板的房间（批 13 实测：英雄拿着
                # 长矛在地下室绕了 20 回合，遗物房一次都没去过）。
                pending = ["__room__" + rk for rk in relic_rooms.values() if rk not in done]
                return pending
            spear_room = self._spear_room(engine)
            return ["__room__" + spear_room] if spear_room else []
        # 叛徒
        carrier = self._spear_holder(engine)
        if carrier is not None:
            return ["__room__" + carrier.room_key]
        spear_room = self._spear_room(engine)
        return ["__room__" + spear_room] if spear_room else []

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """p72：幽灵战士不可被攻击——英雄打它只会白费一回合（原文"never stunned"）。

        批 13 实测：不加这一条时英雄每回合去捶幽灵（Might 5 打不动），
        长矛一直躺在地上没人捡。
        """
        if getattr(target, "template_id", "") == "ghost" and player.role == "hero":
            return True
        return False

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p72：手持长矛的英雄不能做任何攻击（剧本规则要求的除外）。"""
        if attacker.role == "hero" and engine.tokens_held_by(attacker.id, "spear"):
            return False
        return True

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if getattr(monster, "name", "") != "幽灵战士":
            return False
        # p143：只有长矛无人持有时，幽灵才会带着它游走并攻击。
        if self._spear_holder(engine) is not None:
            return True
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        path = engine._shortest_path(monster.room_key, target.room_key)
        if len(path) > 1:
            steps = engine.roll_dice(getattr(monster, "speed", 3), "幽灵移动")
            monster.room_key = path[min(len(path) - 1, steps)]
            token = self._spear(engine)
            if token is not None and token.holder is None:
                engine.place_token(token.uid, monster.room_key)
        if target.room_key == monster.room_key:
            ghost_roll = engine._roll_monster_attack(monster, "might")
            hero_roll = engine._roll_attack(target, "might")
            if ghost_roll > hero_roll:
                engine._deal_damage(target, "physical", ghost_roll - hero_roll, source="幽灵战士")
        return True

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        if action_id == "pick_up_spear":
            token = next(iter(engine.tokens_in_room(player.room_key, "spear")), None)
            if token is None:
                return False
            engine.give_token(token.uid, player.id)
            flags["last_spear_room"] = player.room_key
            engine._log(f"{player.name} 拾起了命运之矛。")
            # p72：接到长矛时必须立刻做同样的理智检定。
            self._control_check(engine, player)
            return True
        if action_id == "persuade_ghost":
            if not engine.tokens_held_by(player.id, "spear"):
                return False
            if self._relic_room_for(engine, player.room_key) is None:
                return False
            self._persuade(engine, player)
            return True
        if action_id == "inspire_ghost":
            self._inspire(engine, player)
            return True
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 结算
    def _persuade(self, engine: Any, player: Any) -> None:
        """p72：知识检定按总点分档推进；达标放印记，两间不同房间即胜。"""
        roll = engine._roll_attack(player, "knowledge")
        if roll <= 2:
            engine._log(f"{player.name} 试图唤起幽灵的回忆，但幽灵拒绝倾听（知识 {roll}）。")
            return
        delta = 1 if roll <= 5 else (2 if roll <= 8 else 3)
        value = engine._advance_haunt_track("persuasion_track", delta)
        flags = engine._haunt_flags()
        need = 2 * int(flags.get("hero_count_at_start", self._hero_count(engine)))
        engine._log(f"{player.name} 的劝说起了作用：说服进度 {value}/{need}（知识 {roll}，+{delta}）。")
        if value < need:
            return
        rooms = flags.setdefault("rest_token_rooms", [])
        if player.room_key in rooms:
            return
        rooms.append(player.room_key)
        engine.spawn_token("rest_token", label="安息印记", role="check", room_key=player.room_key)
        engine._log(f"遗物房里的幽灵战士动摇了（安息印记 {len(rooms)}/2）。")
        if len(rooms) >= 2:
            engine._set_winner("heroes", "幽灵战士终于放下长矛，永远安息了。")

    def _inspire(self, engine: Any, player: Any) -> None:
        """p143：知识或理智 6+；盾牌在身上可多掷 2 骰（封顶 8 枚）。"""
        flags = engine._haunt_flags()
        has_shield = bool(engine.tokens_held_by(player.id, "shield"))
        stat = max(("knowledge", "sanity"), key=lambda name: engine._effective_stat(player, name))
        dice = max(1, min(8, engine._effective_stat(player, stat) + (2 if has_shield else 0)))
        roll = engine.roll_dice(dice, "鼓舞幽灵")
        if has_shield:
            engine._log("盾牌闪着幽光——幽灵的战意被点燃了，英雄们也看在眼里。")
        if roll < 6:
            engine._log(f"{player.name} 讲述旧日荣耀，但幽灵战士毫无反应（{stat} {roll}）。")
            return
        flags["inspire_count"] = int(flags.get("inspire_count", 0)) + 1
        engine._advance_haunt_track("inspire_track", 1)
        engine._log(f"幽灵战士的战意被点燃（鼓舞 {flags['inspire_count']}/{self.INSPIRE_NEEDED}）。")
        if flags["inspire_count"] >= self.INSPIRE_NEEDED:
            engine._set_winner("traitor", "幽灵战士在战吼中重拾长矛——他将为永恒荣耀而战。")

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        if not flags.get("relic_rooms"):
            return []
        lines = []
        rooms = flags.get("rest_token_rooms", [])
        lines.append(f"安息印记：{len(rooms)}/2 间遗物房")
        holder = self._spear_holder(engine)
        if holder is not None:
            lines.append(f"长矛在{holder.name}手上")
        elif self._spear_room(engine):
            room = engine.state.board.get(self._spear_room(engine))
            lines.append(f"长矛掉在{room.name if room else '未知房间'}")
        if int(flags.get("inspire_count", 0)):
            lines.append(f"幽灵的战意：{flags['inspire_count']}/{self.INSPIRE_NEEDED}")
        return lines

    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "幽灵战士的最后一击命中了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p72/p143 只认"让幽灵战士安息"，
        # 幽灵战士是独立怪物，叛徒死后照常挥剑。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
