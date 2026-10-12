"""InhumanTransformationMode（剧本 70）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class InhumanTransformationMode(GenericModeHandler):
    """剧本 70「With an Inhuman Cry / 非人的嚎叫」（英雄手册 p81 / 叛徒手册 p152）。

    同伴被咬伤，正在变成吸血鬼、狼人或者祸害蜘蛛——而且他几乎打不死。
    唯一的机会是在转变完成之前，找出他变成的是什么，并备好克制它的武器。

    · 开局（p152）：叛徒**丢弃全部物品与预兆**（含血匕首、女孩这类通常
      不可丢的），但不因此改变属性；物理属性低于起始值时恢复到起始值；
      保留 Bite 卡。形态**随机秘密选定**（vampire / werewolf / bane_spider），
      引擎只把形态写进 flags，日志不泄密。
    · 转变条件（p152）：吸血鬼访问 Crypt/Graveyard/Bloody Room 后再对英雄
      用力量攻击造成 ≥1 点物理伤害（吸血）；狼人访问 Balcony/Tower/Patio/
      Garden/Graveyard；蜘蛛访问 Charred Room/Conservatory/Creaky Hallway/
      Statuary Corridor/Mystic Elevator。进入即计入（不必在房内结束回合）；
      集齐即完成转变 → 叛徒胜。
    · 免疫（p81/p152）：叛徒**只被克制其形态的武器**伤害——其余攻击一律
      被 attack_allowed 拦下（等价"忽略所有其他伤害"）。吸血鬼 → 蘸过圣水
      的矛/斧/血匕首；狼人 → 持银弹并用左轮；蜘蛛 → 杀虫剂（免掷骰直接
      判胜，走行动而非普通攻击）。
    · 英雄备武器（p81）：圣水（Chapel/Wine Cellar/Underground Lake + 持圣徽
      或天使羽毛，理智 ≥ 玩家人数）→ 房间留圣水；武器在同房圣水里蘸水
      （代替攻击）→ 该武器可杀吸血鬼。银弹（Furnace Room/各实验室，知识
      ≥ 玩家人数，仅一次）+ 左轮（未抽出时可在已开的 Vault 搜线索取出）。
      杀虫剂三材料（醋=厨房/储藏室、园艺工具=花园/天井、喷枪=阁楼/垃圾房，
      搜索代替攻击）集齐后知识 ≥ 玩家人数合成。
    · 干扰令牌（p152）：叛徒可用**匹配形态**的能力代替攻击，给同房英雄放
      一枚属性令牌（吸血鬼→理智、狼人→知识、蜘蛛→力量）；该英雄下回合做
      对应属性检定，4+ 挣脱弃令牌，否则回合立即结束、令牌保留。
    · 胜负（p81/p152）：英雄胜 = 用克制武器击败叛徒（通用"叛徒死"兜底，
      因为叛徒除了正确武器不会死）；叛徒胜 = 完成转变或英雄全灭。

    已知简化：
        · 德鲁伊符（Druidic Charm）不在本仓库 80 张卡牌目录里——圣水只需要
          圣徽或天使羽毛（记录差异）。
        · 左轮"由叛徒从牌堆找出并放进任意已发现房间"简化为直接放进 Vault。
        · 叛徒"不能拾取/携带物品"、"探索抽到物品立即丢弃"未在物品层拦截
          （bot 不会主动违例）。
        · "全场最低力量/速度提升到英雄最低值"简化为：物理属性一律恢复起始值。
        · 银弹/醋/园艺工具/喷枪/杀虫剂用 flags 记账（原版是实体令牌）。
        · 叛徒投放令牌"暴露本性"未做 UI 层隐藏（bot 对局不敏感）。
        · bot 行为修正（2026-09-16，11 种子 × 3/4/5 人 = 33 局对照）：
          ① `create_holy_water` 在"该房间已有圣水"时不再提供——它声明在
             `dip_weapon` 之前，bot 同分取靠前者，英雄站在礼拜堂里会无限重复
             制作圣水（实测 ×120），蘸水一次都排不上，吸血鬼那条英雄胜线整条
             死掉；② `dip_weapon` 在"手上克制品全蘸过"后同样不再提供；
          ③ 叛徒用 `bot_leave_after_action` 声明"投放令牌后继续挪窝"，并用
             `bot_stay_in_room` 声明"吸血鬼访完房间后贴住英雄就别走"（否则
             目标退化成当前房间、寻路失去牵引，`blood_drawn` 永远吸不到）。
          修前完成 26/33、警 14（token_infect×85、create_holy_water×120、
          300 回合僵局 ×7）；修后完成 33/33、警 1（仅 seed31/4p 的一处
          "同房 15 次"震荡，恰在阈值上）。
        · 试玩诊断口径（2026-10-12）：`available_actions` 同时服务真人界面，
          不会应用 bot 专属的 `bot_action_blocked` 过滤；因此“出现过但未执行”
          会把狼人形态下被 bot 明确屏蔽的 `search_ingredient` 记成空转。该告警
          不代表 bot 实际尝试了该行动；focused 6-seed audit 中复核的 7 次均被屏蔽。
    """

    mode = "inhuman_transformation"

    TRAITOR_WEAPONS = ("omen_spear", "item_axe", "item_blood_dagger")
    HOLY_TOOLS = ("omen_holy_symbol", "item_angel_feather")
    REVOLVER = "item_revolver"
    BITE = "omen_bite"
    HOLY_ROOMS = ("chapel", "wine_cellar", "underground_lake")
    LAB_ROOMS = ("furnace_room", "research_laboratory", "operating_laboratory")
    VAULT = "vault"
    INGREDIENT_ROOMS = {
        "kitchen": "vinegar",
        "larder": "vinegar",
        "garden": "gardening",
        "patio": "gardening",
        "attic": "spray_gun",
        "junk_room": "spray_gun",
    }
    INGREDIENTS = ("vinegar", "gardening", "spray_gun")
    FORMS = {
        "vampire": {
            "rooms": ("crypt", "graveyard", "bloody_room"),
            "need_blood": True,
            "token_stat": "sanity",
            "token_action": "token_hypnotize",
        },
        "werewolf": {
            "rooms": ("balcony", "tower", "patio", "garden", "graveyard"),
            "need_blood": False,
            "token_stat": "knowledge",
            "token_action": "token_infect",
        },
        "bane_spider": {
            "rooms": (
                "charred_room",
                "conservatory",
                "creaky_hallway",
                "statuary_corridor",
                "mystic_elevator",
            ),
            "need_blood": False,
            "token_stat": "might",
            "token_action": "token_trap",
        },
    }

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        form = engine.rng.choice(sorted(self.FORMS))
        flags["form"] = form
        flags["visited"] = []
        flags["blood_drawn"] = False
        flags["holy_rooms"] = []
        flags["holy_weapons"] = []
        flags["silver_bullets"] = False
        flags["bug_spray"] = False
        flags["ingredients"] = []
        flags["tokens"] = {}
        flags["transformed"] = False

        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            # p152：丢弃全部物品与预兆（保留 Bite），但不因此改变属性
            traitor.items = [c for c in traitor.items if c == self.BITE]
            if self.BITE not in traitor.items:
                traitor.items.append(self.BITE)
            # p152：物理属性低于起始值 → 恢复到起始值
            for stat in ("might", "speed"):
                floor_value = traitor.stats_max.get(stat)
                if floor_value is not None and traitor.stats.get(stat, 0) < floor_value:
                    track = engine._stat_track(traitor, stat) or []
                    if track:
                        pos = track.index(floor_value) if floor_value in track else 0
                        traitor.stat_positions[stat] = pos
                        traitor.stats[stat] = floor_value
            engine._log(f"{traitor.name} 的伤口在夜里发烫——某种东西正在他体内苏醒。")
        # 形态房间必须在场，否则转变永远无法完成（首版实测：蜘蛛形态需要 5 个
        # 内部房间，场上只有 1 个 → 必然僵局）。沿用 3/28/58/69 号的取牌先例。
        for room_id in self.FORMS[form]["rooms"]:
            engine._ensure_room_in_play(room_id, room_key)
        # 地下室与一层之间只有 basement_landing ⇄ entrance_hall 一条通路。
        # 入口大厅没被探索出来时地下室就是孤岛——墓穴（吸血鬼形态）永远到不了，
        # 200+ 回合后仍停在 2/3（实测）。这里把通路两端都保证在场。
        engine._ensure_room_in_play("entrance_hall", room_key)
        engine._ensure_room_in_play("basement_landing", room_key)
        engine._log("没有人知道那是什么在转变，只知道必须赶在它完成之前。")

    # ------------------------------------------------------- 转变进度
    def _form(self, engine: Any) -> str:
        return engine._haunt_flags().get("form", "vampire")

    def _traitor(self, engine: Any) -> Any:
        return next(
            (p for p in engine.state.players if p.role == "traitor" and not p.dead), None
        )

    def _reachable_template_rooms(self, engine: Any, template_ids, anchor: str) -> list[str]:
        """从 anchor 出发可达的模板房间（过滤掉孤立板块）。

        `_ensure_room_in_play` 会把房间放到"某个空位"，但可能是**孤立的**
        ——收官本实测：墓穴落在地下室 -1:5:0，四周无邻居，吸血鬼形态因此
        永远访不到第三间房，整局僵死。这里统一做可达性过滤。
        """
        by_tid = {}
        for key, room in engine.state.board.items():
            by_tid.setdefault(room.template_id, key)
        result = []
        for tid in template_ids:
            key = by_tid.get(tid)
            if key is None:
                continue
            if key == anchor or engine._path_length(anchor, key) < 9999:
                result.append(tid)
        return result

    def _required_rooms(self, engine: Any) -> list[str]:
        """该形态需要访遍的房间——只算场上存在**且可达**的那些。

        可达集合为空时退回"该形态声明的全部房间"：那时 `_ensure_room_in_play`
        放的板块一个都走不到，硬报一个走不到的目标不如让它照常游荡等探索
        把路打通（真出现这种情况本身就是地图孤岛问题，不该在这里掩盖）。
        """
        form = self.FORMS[self._form(engine)]
        anchor = engine.state.meta["haunt_rule"].get("haunt_room") or ""
        present = self._reachable_template_rooms(engine, form["rooms"], anchor)
        return present or list(form["rooms"])

    def _record_visit(self, engine: Any, player: Any) -> None:
        if player.role != "traitor":
            return
        flags = engine._haunt_flags()
        form = self.FORMS[self._form(engine)]
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id not in form["rooms"]:
            return
        visited = list(flags.get("visited", []))
        if room.template_id in visited:
            return
        visited.append(room.template_id)
        flags["visited"] = visited
        engine._log(f"（{player.name} 在某处停留了片刻……）")
        self._check_transformation(engine)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        self._record_visit(engine, player)

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """吸血鬼形态的兜底：回合结束时与英雄同房即视作吸到了血。

        原文要求"用力量攻击造成 ≥1 点物理伤害"，但 bot 是否发起这次攻击
        由寻路/意图层决定，实测在英雄防御值高时可能整局都打不出伤害，
        导致转变永远差最后一口气。这里放宽为"与英雄同房结束回合"，
        语义上仍是"贴身接触才能吸血"。
        """
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        if player.role != "traitor":
            return
        flags = engine._haunt_flags()
        form = self.FORMS[self._form(engine)]
        if not form["need_blood"]:
            return
        if not flags.get("blood_drawn"):
            nearby = any(
                p.role == "hero" and not p.dead and p.room_key == player.room_key
                for p in engine.state.players
            )
            if nearby:
                flags["blood_drawn"] = True
                engine._log(
                    f"{player.name} 贴着活人的脖子呼吸了一下——某种东西就此完整了。"
                )
        # 关键：即使血早就吸到了，也要在每次回合结束重试完成判定——
        # 首版在 blood_drawn 为真时直接 return，访点后来补齐也永远等不到
        # 那一次检查（实测 transformed 卡在 False 直到 400 回合上限）。
        self._check_transformation(engine)

    def on_attack_resolved(
        self, engine: Any, attacker: Any, target: Any, attacker_won: bool
    ) -> None:
        """吸血鬼形态：对英雄发动力量攻击并取胜即视作吸到血（p152）。

        原先挂在 special_steal 上——那个钩子只在净胜 >2 时才会被引擎调用，
        普通获胜根本触发不到，吸血鬼形态的转变就永远差最后一口气。
        """
        if not attacker_won or getattr(attacker, "role", "") != "traitor":
            return
        if getattr(target, "role", "") != "hero":
            return
        flags = engine._haunt_flags()
        if not self.FORMS[self._form(engine)]["need_blood"] or flags.get("blood_drawn"):
            return
        flags["blood_drawn"] = True
        engine._log(f"{attacker.name} 舔了舔嘴角的血——某种东西就此完整了。")
        self._check_transformation(engine)

    def _check_transformation(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        form = self.FORMS[self._form(engine)]
        visited = set(flags.get("visited", []))
        if not set(self._required_rooms(engine)).issubset(visited):
            return
        if form["need_blood"] and not flags.get("blood_drawn"):
            return
        flags["transformed"] = True
        engine._log("转变完成了——从今往后，没有什么能阻止它。")

    # ------------------------------------------------------- 免疫与武器
    def _has_holy_weapon(self, engine: Any, player: Any) -> bool:
        holy = set(engine._haunt_flags().get("holy_weapons", []))
        return any(weapon in holy and weapon in player.items for weapon in self.TRAITOR_WEAPONS)

    def _has_silver_shot(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        return bool(flags.get("silver_bullets")) and self.REVOLVER in player.items

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p81/p152：叛徒只被克制其形态的武器伤害，其余攻击一律无效。"""
        if getattr(target, "role", "") != "traitor" or target.dead:
            return super().attack_allowed(engine, attacker, target)
        form = self._form(engine)
        if form == "vampire":
            ok = self._has_holy_weapon(engine, attacker)
        elif form == "werewolf":
            ok = self._has_silver_shot(engine, attacker)
        else:  # bane_spider：必须用杀虫剂（走 spray_traitor 行动）
            ok = False
        if not ok:
            engine._log(f"{target.name} 对这记攻击毫不在意——普通的伤害伤不了他。")
        return ok

    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p81：持银弹的英雄用左轮攻击——左轮本身就是速度攻击，无需覆盖。"""
        return None

    # ------------------------------------------------------------- 行动
    def _has_bug_spray(self, engine: Any, player: Any) -> bool:
        return bool(engine._haunt_flags().get("bug_spray"))

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            if aid == "create_holy_water":
                room = engine.state.board.get(player.room_key)
                if room is None or room.template_id not in self.HOLY_ROOMS:
                    continue
                if player.room_key in set(flags.get("holy_rooms", [])):
                    # 这间房已经有圣水了：再做一次只会返回 True 却什么都不改，
                    # 而 bot 的行动打分是"同分取声明靠前者"，create_holy_water 排在
                    # dip_weapon 前面 → 英雄站在礼拜堂里（同时拿着圣徽与矛）会
                    # 无限重复"制作圣水"，蘸水永远排不上（实测 create_holy_water×120、
                    # dip_weapon 出现 54 次一次没执行，吸血鬼那条英雄胜线整条死掉）。
                    continue
                if not any(c in player.items for c in self.HOLY_TOOLS):
                    continue
            elif aid == "dip_weapon":
                if player.room_key not in set(flags.get("holy_rooms", [])):
                    continue
                weapons = [c for c in self.TRAITOR_WEAPONS if c in player.items]
                if not weapons:
                    continue
                if all(c in set(flags.get("holy_weapons", [])) for c in weapons):
                    continue  # 手上的家伙全蘸过了：再做一遍同样是空转
            elif aid == "create_silver_bullets":
                room = engine.state.board.get(player.room_key)
                if room is None or room.template_id not in self.LAB_ROOMS:
                    continue
                if flags.get("silver_bullets"):
                    continue
            elif aid == "search_revolver":
                room = engine.state.board.get(player.room_key)
                if room is None or room.template_id != self.VAULT:
                    continue
                if not room.data.get("opened"):
                    continue
                if any(self.REVOLVER in p.items for p in engine.state.players):
                    continue
                if self.REVOLVER in engine.state.room_items.get(player.room_key, []):
                    continue
            elif aid == "search_ingredient":
                room = engine.state.board.get(player.room_key)
                if room is None or room.template_id not in self.INGREDIENT_ROOMS:
                    continue
                material = self.INGREDIENT_ROOMS[room.template_id]
                if material in set(flags.get("ingredients", [])):
                    continue
            elif aid == "assemble_bug_spray":
                if not set(self.INGREDIENTS).issubset(set(flags.get("ingredients", []))):
                    continue
                if flags.get("bug_spray"):
                    continue
            elif aid == "spray_traitor":
                traitor = self._traitor(engine)
                if not self._has_bug_spray(engine, player):
                    continue
                if traitor is None or traitor.room_key != player.room_key:
                    continue
            elif aid in ("token_hypnotize", "token_infect", "token_trap"):
                form = self.FORMS[self._form(engine)]
                if aid != form["token_action"]:
                    continue
                target = next(
                    (
                        p
                        for p in engine.state.players
                        if p.role == "hero" and not p.dead and p.room_key == player.room_key
                    ),
                    None,
                )
                if target is None:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "create_holy_water":
            return self._create_holy_water(engine, player)
        if action_id == "dip_weapon":
            return self._dip_weapon(engine, player)
        if action_id == "create_silver_bullets":
            return self._create_silver_bullets(engine, player)
        if action_id == "search_revolver":
            return self._search_revolver(engine, player)
        if action_id == "search_ingredient":
            return self._search_ingredient(engine, player)
        if action_id == "assemble_bug_spray":
            return self._assemble_bug_spray(engine, player)
        if action_id == "spray_traitor":
            return self._spray_traitor(engine, player)
        if action_id in ("token_hypnotize", "token_infect", "token_trap"):
            return self._place_token(engine, player, action_id)
        return super().perform_action(engine, player, action_id, data)

    def _create_holy_water(self, engine: Any, player: Any) -> bool:
        """p81：理智 ≥ 玩家人数 → 该房出现圣水。"""
        threshold = len(engine.state.players)
        if not engine._resolve_check(player, "sanity", threshold, "制作圣水"):
            engine._log(f"{engine._player_label(player)} 的祈祷没能让水变得神圣。")
            return False
        flags = engine._haunt_flags()
        rooms = sorted(set(flags.get("holy_rooms", [])) | {player.room_key})
        flags["holy_rooms"] = rooms
        engine._log("清水在圣徽的映照下泛起微光——这里有了圣水。")
        return True

    def _dip_weapon(self, engine: Any, player: Any) -> bool:
        """p81：在有圣水的房间蘸武器（代替攻击）。"""
        flags = engine._haunt_flags()
        weapon = next((c for c in self.TRAITOR_WEAPONS if c in player.items
                       and c not in flags.get("holy_weapons", [])), None)
        if weapon is None or player.room_key not in set(flags.get("holy_rooms", [])):
            return False
        holy = sorted(set(flags.get("holy_weapons", [])) | {weapon})
        flags["holy_weapons"] = holy
        player.attack_used = True  # p81：代替攻击
        engine._log(f"{engine._player_label(player)} 把武器浸入圣水——它现在能伤到那个东西了。")
        return True

    def _create_silver_bullets(self, engine: Any, player: Any) -> bool:
        """p81：知识 ≥ 玩家人数 → 造出银弹（全局仅一次）。"""
        flags = engine._haunt_flags()
        if flags.get("silver_bullets"):
            return False
        threshold = len(engine.state.players)
        if not engine._resolve_check(player, "knowledge", threshold, "铸造银弹"):
            engine._log("熔炉的火候不对——银弹没能成型。")
            return False
        flags["silver_bullets"] = True
        engine._log("一颗银弹在火光中成形——它对某种东西格外致命。")
        return True

    def _search_revolver(self, engine: Any, player: Any) -> bool:
        """p81：在已开的 Vault 搜出左轮（原文由叛徒从牌堆取出放置）。"""
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id != self.VAULT or not room.data.get("opened"):
            return False
        if any(self.REVOLVER in p.items for p in engine.state.players):
            return False
        items = engine.state.room_items.setdefault(player.room_key, [])
        if self.REVOLVER in items:
            return False
        items.append(self.REVOLVER)
        engine._log("金库的暗格里躺着一把左轮——线索没有骗人。")
        return True

    def _search_ingredient(self, engine: Any, player: Any) -> bool:
        """p81：在对应房间搜索材料（代替攻击）。"""
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id not in self.INGREDIENT_ROOMS:
            return False
        material = self.INGREDIENT_ROOMS[room.template_id]
        flags = engine._haunt_flags()
        have = set(flags.get("ingredients", []))
        if material in have:
            return False
        have.add(material)
        flags["ingredients"] = sorted(have)
        player.attack_used = True  # p81：搜索代替攻击
        engine._log(
            f"{engine._player_label(player)} 翻出了材料（{len(have)}/3）——杀虫剂还差几样。"
        )
        return True

    def _assemble_bug_spray(self, engine: Any, player: Any) -> bool:
        """p81：三材料 + 知识 ≥ 玩家人数 → 合成杀虫剂。"""
        flags = engine._haunt_flags()
        if not set(self.INGREDIENTS).issubset(set(flags.get("ingredients", []))):
            return False
        if flags.get("bug_spray"):
            return False
        threshold = len(engine.state.players)
        if not engine._resolve_check(player, "knowledge", threshold, "调配杀虫剂"):
            engine._log("配比差了一点——这罐东西还不能用。")
            return False
        flags["ingredients"] = []
        flags["bug_spray"] = True
        engine._log("刺鼻的气味弥漫开来——杀虫剂配好了。")
        return True

    def _spray_traitor(self, engine: Any, player: Any) -> bool:
        """p81：持杀虫剂与叛徒同房 → 无需掷骰；若他是蜘蛛，直接获胜。"""
        traitor = self._traitor(engine)
        if traitor is None or traitor.room_key != player.room_key:
            return False
        if self._form(engine) == "bane_spider":
            engine._log("喷雾罩住了那个东西——它发出非人的尖叫，缩成了一团。")
            engine._set_winner("heroes", "杀虫剂找到了它真正的目标。")
        else:
            engine._log("喷雾毫无作用——他不是蜘蛛。")
        return True

    def _place_token(self, engine: Any, player: Any, action_id: str) -> bool:
        """p152：用匹配形态的能力给英雄放干扰令牌（代替攻击）。"""
        form = self.FORMS[self._form(engine)]
        if action_id != form["token_action"]:
            return False
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
        flags = engine._haunt_flags()
        tokens = dict(flags.get("tokens", {}))
        tokens[str(target.id)] = form["token_stat"]
        flags["tokens"] = tokens
        player.attack_used = True
        engine._log(f"{engine._player_label(target)} 恍惚了一下——某种东西缠上了他。")
        return True

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """p152：被投放令牌的英雄做对应属性检定，4+ 挣脱，否则回合立即结束。"""
        if engine.state.phase != "HAUNT_PHASE" or player.dead or player.role != "hero":
            return
        flags = engine._haunt_flags()
        tokens = dict(flags.get("tokens", {}))
        stat = tokens.get(str(player.id))
        if stat is None:
            return
        result = engine.roll_dice(max(1, player.stats.get(stat, 1)), "挣脱干扰")
        if result >= 4:
            tokens.pop(str(player.id), None)
            flags["tokens"] = tokens
            engine._log(f"{engine._player_label(player)} 甩开了那层影响。")
            return
        player.movement_stopped = True
        player.attack_used = True
        player.item_used = True
        engine._mark_haunt_action_used(player)
        engine._log(f"{engine._player_label(player)} 被困住了——本回合无法行动。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p152：完成转变 → 叛徒胜
        if flags.get("transformed"):
            engine._set_winner("traitor", "转变完成了——它再也不是人了。")
            return True
        # p152：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "没有人能阻止它了。")
            return True
        # 叛徒死亡 → 英雄胜（走引擎通用兜底：本剧本里他只会死于克制武器/环境）
        return False

    # ------------------------------------------------------------- bot/UI
    bot_goal_exclusive = True

    def action_item_cards(self, engine, player, action_id):
        if action_id == "dip_weapon":
            return [c for c in self.TRAITOR_WEAPONS if c in player.items
                    and c not in engine._haunt_flags().get("holy_weapons", [])][:1]
        if action_id == "create_holy_water":
            return [c for c in self.HOLY_TOOLS if c in player.items][:1]
        return []

    def bot_action_blocked(self, engine, player, action_id):
        if player.role != "hero":
            return False
        allowed = {
            "vampire": {"create_holy_water", "dip_weapon"},
            "werewolf": {"create_silver_bullets", "search_revolver"},
            "bane_spider": ({"spray_traitor"} if engine._haunt_flags().get("bug_spray") else
                            {"search_ingredient", "assemble_bug_spray"}),
        }
        return action_id not in allowed[self._form(engine)]

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """吸血鬼的转变只差"贴住一个活人"：人都到跟前了就别再走开（p152）。

        `bot_goal_rooms` 在访完房间后返回 `__room__<某个英雄的房间>`——可一旦
        英雄自己走进叛徒所在的房间，这个目标就退化成"当前房间"，
        `_next_steps_toward` 会跳过它、寻路失去牵引，叛徒于是又漂出去；而
        `on_turn_end` 的吸血判定要求"结束回合时与英雄同房"。两下相抵，血量
        永远吸不到。实测（seed251/3p）：三间形态房 t37 就访齐了，blood_drawn
        直到 400 回合仍是 False，整局僵死（seed31/5p 同款）。
        """
        if player.role != "traitor" or player.dead:
            return False
        flags = engine._haunt_flags()
        form = self.FORMS[self._form(engine)]
        if not form["need_blood"] or flags.get("blood_drawn"):
            return False
        # 还没访完形态房：主线是跑房间，不是贴人
        if not set(self._required_rooms(engine)).issubset(set(flags.get("visited", []))):
            return False
        return any(
            p.role == "hero" and not p.dead and p.room_key == player.room_key
            for p in engine.state.players
        )

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """叛徒投放干扰令牌之后必须继续挪窝（p152）。

        `token_*` 的能力在"同房有英雄"时就一直可用，于是 `_pending_haunt_action_here`
        每回合都判"下回合还能在这儿做"，`_run_turn` 的移动循环直接 break——叛徒
        原地驻扎、一回合放一枚令牌，永远走不到还没访过的形态房间。实测
        （seed3/4p）：token_trap×60、在仆人宿舍兜了 127 个来回、300 回合未分胜负；
        seed197/5p：token_trap×53、地下湖 91 次、往返 180 次。

        原文里这个能力对叛徒只是"代替攻击"的可选项，主线始终是访遍形态房间；
        真人不会为了贴着一个英雄而放弃转变（27 号同款用法）。
        """
        return player.role == "traitor"

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        flags = engine._haunt_flags()
        if player.role == "traitor":
            # p152：叛徒必须访遍形态房间才能完成转变——没目标就会僵在原地
            # （首版漏掉这条，三局全跑成 400 回合僵局）
            visited = set(flags.get("visited", []))
            remaining = [r for r in self._required_rooms(engine) if r not in visited]
            if remaining:
                # 注意：这里返回**裸模板 id**——bot 会把裸 id 解析成场上房间，
                # 而 "__room__" 前缀只接受真实房间 key（如 "0:5:1"）。首版误用
                # 前缀传模板 id，目标被静默丢弃，叛徒满场游荡从不访房间。
                return list(remaining)
            # 访完了：吸血鬼还差一次吸血，其余形态纯粹去清场
            heroes = [
                p for p in engine.state.players if p.role == "hero" and not p.dead
            ]
            return [f"__room__{heroes[0].room_key}"] if heroes else []
        form = self._form(engine)
        # 按形态去备武器：吸血鬼要圣水+武器蘸水；狼人要银弹+左轮；蜘蛛要三材料
        reachable = self._reachable_template_rooms(
            engine, tuple(self.HOLY_ROOMS) + tuple(self.LAB_ROOMS) + tuple(self.INGREDIENT_ROOMS) + (self.VAULT,), player.room_key
        )
        if form == "vampire":
            if not flags.get("holy_rooms"):
                room = next((r for r in self.HOLY_ROOMS if r in reachable), None)
                return [room] if room else []
            if not flags.get("holy_weapons"):
                return [flags["holy_rooms"][0]]  # 已是真实房间 key
        elif form == "werewolf":
            if not flags.get("silver_bullets"):
                room = next((r for r in self.LAB_ROOMS if r in reachable), None)
                return [room] if room else []
            if not any(self.REVOLVER in p.items for p in engine.state.players):
                return [self.VAULT] if self.VAULT in reachable else []
        else:
            if flags.get("bug_spray"):
                traitor = self._traitor(engine)
                return [f"__room__{traitor.room_key}"] if traitor is not None else []
            have = set(flags.get("ingredients", []))
            for material in self.INGREDIENTS:
                if material not in have:
                    room = next(
                        (
                            r
                            for r, m in self.INGREDIENT_ROOMS.items()
                            if m == material and r in reachable
                        ),
                        None,
                    )
                    if room:
                        return [room]
        # 武器/材料齐备后：直奔叛徒（首版没有这条，英雄备完武器就满场乱走，
        # 叛徒靠免疫拖着，双方都不动 → 250+ 回合僵局）
        traitor = self._traitor(engine)
        if traitor is not None:
            if form == "vampire" and flags.get("holy_weapons"):
                return [f"__room__{traitor.room_key}"]
            if form == "werewolf" and flags.get("silver_bullets") and any(
                self.REVOLVER in p.items for p in engine.state.players
            ):
                return [f"__room__{traitor.room_key}"]
            if form == "bane_spider" and flags.get("bug_spray"):
                return [f"__room__{traitor.room_key}"]
        return []
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        return [f"__room__{traitor.room_key}"] if traitor is not None else []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        form = self._form(engine)
        visited = set(flags.get("visited", []))
        need = self.FORMS[form]["rooms"]
        lines = []
        for p in engine.state.players:
            if p.role == "hero" and not p.dead:
                lines.append(f"{p.name}：材料 {len(flags.get('ingredients', []))}/3。")
                break
        if flags.get("holy_rooms"):
            lines.append(f"圣水：{len(flags['holy_rooms'])} 处。")
        if flags.get("holy_weapons"):
            lines.append(f"蘸水武器：{len(flags['holy_weapons'])} 件。")
        if flags.get("silver_bullets"):
            lines.append("银弹：已铸造。")
        if flags.get("bug_spray"):
            lines.append("杀虫剂：已调配。")
        lines.append(f"（叛徒的转变已完成访点 {len(visited)}/{len(need)}）")
        return lines
