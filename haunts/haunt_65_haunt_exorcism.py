"""BreathOfWindMode（剧本 65）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class BreathOfWindMode(GenericModeHandler):
    """剧本 65 一阵风息（A Breath of Wind）。

    权威原文：英雄手册 p76 / 叛徒手册 p147。

    英雄（p76）：
      · 找蜡烛：在 **厨房/餐厅/小教堂/画廊** 每回合一次，速度 3+ → 得到蜡烛令牌
        （蜡烛可以像物品一样掉落、交易、被抢）。
      · 点蜡烛：弃掉一根蜡烛，在**作祟所在楼层**的任意房间做知识 5+ → 成功在该房
        放一枚知识令牌；同一间房不能重复做。持「蜡烛」物品牌也可代替令牌弃掉。
      · 知识令牌数达到"作祟揭示时的英雄数" → 驱魔成功，英雄胜。
    叛徒（p147）：
      · 骚灵（ghost 模板）落在作祟房间；**回合/伤害轨**起始 3。
      · 每个怪物回合前，骚灵在 **杂物间/储藏室/图书馆/研究实验室/手术室** 时轨道 +1。
      · 骚灵攻击：对同房每个英雄各攻击一次，掷「当前轨道值」（上限 8）枚骰，英雄用
        **力量**防御；赢 3+ 时英雄只受 2 点伤害，否则按差值受伤；英雄防守赢下则骚灵
        毫发无损（它不会被打晕）。
      · 骚灵免疫力量攻击；英雄只能用**速度**打它，持 戒指/骷髅/铃铛 时改用**理智**：
        赢了不造成伤害，而是把轨道按差值压低。
      · 英雄全灭 → 叛徒胜；叛徒倒下不停止作祟（吸收引擎「叛徒死亡→英雄胜」兜底）。

    已知简化：
      · 本仓库的房间目录里**没有"阁楼"**（见 content.py 的房间清单），轨道加速房间
        因此只剩 杂物间/储藏室/图书馆/研究实验室/手术室 五间。
      · 「骚灵可以捡物品、每捡一件轨道 +1 / 掉一件 -1」未建模——引擎里怪物不持物品。
      · 重组（re-form）未建模：原文是叛徒的可选操作（丢掉所有物品 + 轨道重置为 3 +
        在任意预兆房现身），只有轨道被打到极低时才划算，且引擎的怪物位置没有
        "回预兆房"的通用入口。
      · 英雄打骚灵落败时原文是"掷 1 枚骰的物理伤害"而非差值伤害，引擎没有"反击伤害
        改写"入口，沿用引擎默认的差值伤害。
      · 左轮/玩具猴对骚灵无效、炸药把它打出局等武器特例未建模。
      · 速度攻击赢下后"抢它携带的一件物品"未建模（同"怪物不持物品"）。
    """

    mode = "haunt_exorcism"

    POLTERGEIST = "ghost"
    CANDLE = "candle"
    CANDLE_ITEM = "item_candle"
    MARK = "knowledge_check"
    TRACK = "poltergeist_timer"
    TRACK_START = 3
    TRACK_MAX = 8
    # 机器人一次出门囤几根蜡烛（原文不限根数；这只是"人不会一根一根跑"的策略值）
    CANDLE_STOCK = 2
    # p76：找蜡烛只在四间房；p147：轨道加速只在五间房（本仓库没有"阁楼"）。
    FIND_ROOMS = ("kitchen", "dining_room", "chapel", "gallery")
    BOOST_ROOMS = (
        "junk_room",
        "larder",
        "library",
        "research_laboratory",
        "operating_laboratory",
    )
    # p76：持这三件法器之一才能改用理智打骚灵。
    SANITY_TOOLS = ("omen_ring", "omen_skull", "omen_bell")

    # ------------------------------------------------------------- 小工具
    def _poltergeist(self, engine):
        return engine._monster_by_template(self.POLTERGEIST)

    def _track(self, engine):
        return int(engine._haunt_track_value(self.TRACK))

    def _attack_dice(self, engine):
        """p147：骚灵的攻击骰 = 当前轨道值（上限 8）。"""
        return max(1, min(self.TRACK_MAX, self._track(engine)))

    def _hero_count_at_reveal(self, engine):
        return max(1, int(engine._haunt_flags().get("hero_count_at_reveal", 1)))

    def _haunt_floor(self, engine):
        return int(engine._haunt_flags().get("haunt_floor", -1))

    def _candle_of(self, engine, player):
        """p76：蜡烛令牌与「蜡烛」物品牌都可以用来点火，返回 (令牌, 物品牌)。"""
        token = next(iter(engine.tokens_held_by(player.id, self.CANDLE)), None)
        if token is not None:
            return token, None
        if self.CANDLE_ITEM in player.items:
            return None, self.CANDLE_ITEM
        return None, None

    def _candle_count(self, engine, player):
        count = len(list(engine.tokens_held_by(player.id, self.CANDLE)))
        if self.CANDLE_ITEM in player.items:
            count += 1
        return count

    def _burn_room_ok(self, engine, player):
        """p76：得在作祟楼层、且这间房还没净化过。"""
        room = engine.current_room(player)
        if room is None or room.floor != self._haunt_floor(engine):
            return False
        used = engine._haunt_flags().get("candle_rooms_used", [])
        return room.template_id not in used

    # ------------------------------------------------------------- setup
    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        flags["candle_rooms_used"] = []
        flags["candles_found"] = 0
        flags["hero_count_at_reveal"] = len(heroes)
        room = engine.state.board.get(room_key)
        flags["haunt_floor"] = room.floor if room is not None else -1
        engine._set_haunt_track_value(self.TRACK, self.TRACK_START)
        # p76：知识令牌数要达到"**作祟揭示时**的英雄数"——不是当前人数，
        # 也不是总人数（含叛徒）。规则表里的 "player_count" 只是兜底默认值。
        track = engine._haunt_tracks().setdefault(
            "exorcism_progress", {"label": "驱魔进度", "value": 0, "side": "heroes"}
        )
        track["label"] = "驱魔进度"
        track["target"] = max(1, len(heroes))
        track["value"] = 0
        engine._log("骚灵发出了疯狂的笑声——物件开始朝你飞来！")

    # --------------------------------------------------------- 回合/伤害轨
    def on_monster_turn_start(self, engine, monster):
        """p147：骚灵在杂物间/储藏室/图书馆/研究实验室/手术室时，轨道 +1。"""
        if getattr(monster, "template_id", "") != self.POLTERGEIST:
            return False
        room = engine.state.board.get(monster.room_key)
        if room is None or room.template_id not in self.BOOST_ROOMS:
            return False
        value = self._track(engine) + 1
        engine._set_haunt_track_value(self.TRACK, value)
        engine._log(f"骚灵搅动的碎屑越来越凶（回合/伤害轨 {value}）。")
        return False

    def on_monster_turn_attack(self, engine, monster):
        """p147：骚灵对同房每个英雄各攻击一次，掷轨道值（上限 8）枚骰，英雄用力量防御。"""
        if getattr(monster, "template_id", "") != self.POLTERGEIST:
            return False
        victims = [
            p
            for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not victims:
            return False
        dice = self._attack_dice(engine)
        for victim in victims:
            attack = engine.roll_dice(dice, "骚灵的攻击")
            defense = engine._roll_attack(victim, "might")
            engine._log(
                f"{monster.name} 掀起碎屑砸向 {engine._player_label(victim)}："
                f"{attack} 对 {defense}。"
            )
            if attack <= defense:
                engine._log("碎屑擦身而过——骚灵不会因为防守输掉而受伤。")
                continue
            if attack - defense >= 3:
                engine._deal_damage(victim, "physical", 2, source=monster.name)
            else:
                engine._deal_damage(victim, "physical", attack - defense, source=monster.name)
        return True

    def on_monster_defeated(self, engine, monster, amount):
        """p76：打中骚灵不造成伤害、也不击晕。

        · 理智攻击（持戒指/骷髅/铃铛）：按**掷骰差值**把轨道压低。
        · 速度攻击：只能抢它携带的物品（本仓库未建模），同样不造成伤害。
        引擎在进入这个钩子前会把本次攻击的属性写进 `_last_attack_attr`。
        """
        if getattr(monster, "template_id", "") != self.POLTERGEIST:
            return False
        if str(getattr(engine, "_last_attack_attr", "") or "") == "sanity":
            value = max(0, self._track(engine) - max(1, int(amount)))
            engine._set_haunt_track_value(self.TRACK, value)
            engine._log(f"理智的冲击撕开了骚灵的怨气（回合/伤害轨 {value}）。")
        else:
            engine._log("骚灵被打散了片刻，但没有受伤。")
        return True

    def attack_attr_override(self, engine, attacker, target, default_attr):
        """p76：骚灵免疫力量；英雄默认用速度打它，持戒指/骷髅/铃铛时改用理智。"""
        if getattr(target, "template_id", "") != self.POLTERGEIST:
            return None
        if getattr(attacker, "role", "") != "hero":
            return None
        if any(card in getattr(attacker, "items", []) for card in self.SANITY_TOOLS):
            return "sanity"
        return "speed"

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "burn_candle":
                token, item = self._candle_of(engine, player)
                if token is None and item is None:
                    continue
                if not self._burn_room_ok(engine, player):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "find_candle":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                engine.spawn_token(self.CANDLE, label="蜡烛", role="carried", holder=player.id)
                flags["candles_found"] = int(flags.get("candles_found", 0)) + 1
                engine._log(f"{player.name} 找到了一根蜡烛。")
            return ok

        if action_id == "burn_candle":
            token, item = self._candle_of(engine, player)
            if token is None and item is None:
                engine._log("你没有蜡烛。")
                return False
            if not self._burn_room_ok(engine, player):
                engine._log("这个房间已经净化过了。")
                return False
            room_key = player.room_key
            room_id = engine._current_room_template_id(player)
            if token is not None:
                engine.remove_token(token.uid)
            else:
                engine._discard_card_from_player(player, item, return_to_room=False)
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                used = flags.setdefault("candle_rooms_used", [])
                used.append(room_id)
                engine.spawn_token(
                    self.MARK, label="驱魔成功", role="marker", room_key=room_key
                )
                engine._log("蜡烛的火焰净化了这个房间！")
                engine.check_victory()
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 机器人
    def bot_action_blocked(self, engine, player, action_id):
        """手上有蜡烛、且眼前就能点火时，别再翻找。

        两条都要，缺一条就废：
          ① 不作"能点火就别翻找"，机器人会一直挑 `find_candle`——同分时它总是取
             规则表里靠前的那个——攒一堆蜡烛却永远不去点火（批次13 seed101/4p
             实测 find_candle ×233、`burn_candle` 出现 114 次一次没用，卡到 300
             回合上限）。
          ② 不作"最多囤 2 根"，机器人就会"找一根 → 跑一整趟去烧一根 → 再跑回来"，
             把整局耗在来回路上（seed197/5p 煤导槽被踩 80 次）。人是一次多带几根。
        """
        if action_id != "find_candle":
            return False
        if self._candle_count(engine, player) == 0:
            return False
        if self._burn_room_ok(engine, player):
            return True
        return self._candle_count(engine, player) >= self.CANDLE_STOCK

    @staticmethod
    def _sticky_goal(engine, player, slot, candidates):
        """锁定"这一趟要去哪间房"，直到它不再合格。

        每回合都重新挑"最近的一间"会来回摆：两间等距的净化房之间会 A→B→A，
        而且只要队友烧掉一间、全场的最近房就会改名，走到一半的英雄当场掉头
        （批次13 seed151/4p 实测往返 45 次、seed197/5p 煤导槽踩 80 次）。
        人不会这么走——他认准一间走到为止。
        """
        flags = engine._haunt_flags()
        key = f"{slot}_{player.id}"
        current = flags.get(key)
        if (
            current in candidates
            and engine._path_length(player.room_key, current) < 9999
        ):
            return current
        reachable = [
            candidate for candidate in candidates
            if engine._path_length(player.room_key, candidate) < 9999
        ]
        if not reachable:
            flags.pop(key, None)
            return None
        best = min(
            sorted(reachable), key=lambda candidate: engine._path_length(player.room_key, candidate)
        )
        flags[key] = best
        return best

    def bot_goal_rooms(self, engine, player):
        """英雄：空手去四间蜡烛房翻找；拿到蜡烛就去作祟层还没净化的房间点火。"""
        if player.role != "hero":
            return []
        token, item = self._candle_of(engine, player)
        if token is not None or item is not None:
            used = set(engine._haunt_flags().get("candle_rooms_used", []))
            floor = self._haunt_floor(engine)
            candidates = [
                key
                for key, room in sorted(engine.state.board.items())
                if room.floor == floor and room.template_id not in used
            ]
            target = self._sticky_goal(engine, player, "burn_target", candidates)
        else:
            candidates = [
                key
                for key, room in sorted(engine.state.board.items())
                if room.template_id in self.FIND_ROOMS
            ]
            target = self._sticky_goal(engine, player, "find_target", candidates)
        return [f"__room__{target}"] if target else []

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine):
        target = engine._haunt_track_target("exorcism_progress") or self._hero_count_at_reveal(engine)
        if engine._haunt_track_value("exorcism_progress") >= target:
            engine._set_winner("heroes", "驱魔完成——骚灵消散了！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "骚灵的狂笑回荡在空荡的房子里。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p76/p147 只认"驱魔完成"，
        # 骚灵不随叛徒死亡停止作祟。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    def progress_summary(self, engine, viewer):
        dice = self._attack_dice(engine)
        return [
            f"驱魔进度 {engine._haunt_track_value('exorcism_progress')}/"
            f"{engine._haunt_track_target('exorcism_progress') or self._hero_count_at_reveal(engine)}"
            "（知识令牌）。",
            f"回合/伤害轨 {self._track(engine)}——骚灵攻击掷 {dice} 枚骰。",
        ]
