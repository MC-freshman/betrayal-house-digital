"""CrimsonJackMode（剧本 48）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class CrimsonJackMode(GenericModeHandler):
    """剧本 48「Stacked Like Cordwood」（英雄手册 p59 / 叛徒手册 p130）。

    叛徒的远房亲戚——连环杀手血腥杰克——正从前门走进来。他打不死：
    被击败只是暂时消散，下个回合会更强地回到门厅。唯一能永久杀死他的，
    是藏在宅子里、且被研究明白用法的那件诅咒武器。

    · 开局（p130）：杰克令牌放进门厅（前门旁）。叛徒仍在场（未出局）。
    · 打不死（p130）：被击败 → 不击晕、不受伤，而是暂时移出房子；
      叛徒下个回合开始时回到门厅，且**每次回归所有属性 +1**（记在
      flags["jack_bonus"]，回归时重算 speed/might/sanity）。
    · 恐惧光环（p59/p130）：每个英雄回合开始，与杰克同房间必须理智 3+，
      失败则各掉 1 点精神属性（理智/知识）与 1 点物理属性（力量/速度）。
    · 找武器（p59）：图书馆/教堂/金库（须已开）/阁楼做知识 3+ 检定，
      成功则从对应牌堆取一件自选诅咒武器（斧/矛/血匕首），并洗匀该堆。
    · 研究（p59）：持武器者做力量 5+ 或知识 5+；每次成功 +1 枚研究令牌，
      累计到玩家数即"理解用法"（flags["cursed_weapon_understood"]）。
    · 永杀（p59）：理解用法后用该诅咒武器击败杰克 → 永久死亡，英雄胜。
    · 胜负（p59/p130）：英雄胜 = 诅咒武器永杀杰克；叛徒胜 = 英雄全灭。
      叛徒在场，无"叛徒死→英雄胜"兜底问题；但若叛徒被杀而杰克还在，
      杰克继续行动（7/8 号怪物自主口径），故吸收该兜底。

    已知简化：
        · 诅咒武器三选一在 bot 侧按斧→矛→血匕首的固定顺序取第一件可用的
          （原版由英雄任选）；人类玩家弹窗自选。
        · 找武器"从对应牌堆里挑出指定武器并洗匀"：斧/血匕首取自物品牌堆、
          矛取自预兆牌堆（对应原文的 appropriate stack）；牌堆里找不到时
          回落到弃堆，再没有就直接发放（同 28 号强行入场口径），不记账目。
        · 研究令牌用 flags 计数（原版是放在角色卡上的实体令牌）。
        · 杰克"暂时移出"期间不参与任何结算，回归时属性整体重算。
    """

    mode = "cursed_weapon"

    JACK = "crimson_jack"
    ENTRANCE = "entrance_hall"
    SEARCH_ROOMS = ("library", "chapel", "vault", "attic")
    # 诅咒武器 → 所在牌堆（斧/血匕首是物品牌，矛是预兆牌）
    WEAPONS = (
        ("item_axe", "item"),
        ("omen_spear", "omen"),
        ("item_blood_dagger", "item"),
    )
    WEAPON_NAMES = {
        "item_axe": "斧头",
        "omen_spear": "长矛",
        "item_blood_dagger": "血匕首",
    }
    MENTAL = ("sanity", "knowledge")
    PHYSICAL = ("might", "speed")

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("jack_bonus", 0)
        flags.setdefault("jack_banished", False)
        flags.setdefault("jack_killed", False)
        flags.setdefault("cursed_weapon", None)
        flags.setdefault("cursed_weapon_understood", False)
        engine._haunt_tracks().setdefault(
            "study_tokens", {"label": "研究进度", "target": len(engine.state.players), "value": 0}
        )["target"] = len(engine.state.players)

        entrance_key = self._entrance_key(engine) or engine._ensure_room_in_play(
            self.ENTRANCE, room_key
        )
        target = entrance_key or room_key
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.JACK, {"template_id": self.JACK, "name": "血腥杰克"})
        )
        engine._spawn_single_haunt_monster(spec, target)
        engine._log("前门吱呀作响——血腥杰克走了进来，尸体在他身后堆成了柴垛。")

    def _entrance_key(self, engine: Any) -> str | None:
        room = next(
            (r for r in engine.state.board.values() if r.template_id == self.ENTRANCE), None
        )
        return room.key if room is not None else None

    def _jack(self, engine: Any) -> Any:
        return next(
            (m for m in engine.state.monsters if m.template_id == self.JACK), None
        )

    # ------------------------------------------------------------- 回合
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE" or player.dead:
            return
        flags = engine._haunt_flags()
        # p130：叛徒回合开始时，被击败的杰克回到门厅且全属性 +1。
        # 叛徒已死时改由任意玩家的回合开始带回：杰克只在叛徒回合回归的话，
        # 叛徒一死、杰克又恰好被放逐，他就永远回不来，"用诅咒武器永久杀死
        # 杰克"这条英雄胜利线随之断裂，整局烂在 400 回合（seed101/5p 实测：
        # 研究进度 5/5、武器已理解，英雄却无杰克可杀）。这也符合本模式既有的
        # "叛徒倒下后杰克继续行动"口径。
        traitor_alive = any(
            p.role == "traitor" and not p.dead for p in engine.state.players
        )
        if flags.get("jack_banished") and (player.role == "traitor" or not traitor_alive):
            flags["jack_bonus"] = int(flags.get("jack_bonus", 0)) + 1
            flags["jack_banished"] = False
            self._return_jack(engine, player)
        # p59/p130：恐惧光环——与杰克同房间的英雄回合开始须理智 3+
        if player.role == "hero":
            self._fear_aura(engine, player)

    def _return_jack(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        target = self._entrance_key(engine) or player.room_key
        spec = dict(
            engine._haunt_rule_state()
            .get("monster_specs", {})
            .get(self.JACK, {"template_id": self.JACK, "name": "血腥杰克"})
        )
        bonus = int(flags.get("jack_bonus", 0))
        spec["speed"] = 3 + bonus
        spec["might"] = 3 + bonus
        spec["sanity"] = 3 + bonus
        engine._spawn_single_haunt_monster(spec, target)
        engine._log(
            f"血腥杰克重新走进门厅——他更强了（全属性 +{bonus}）。"
        )

    def _fear_aura(self, engine: Any, player: Any) -> None:
        jack = self._jack(engine)
        if jack is None or jack.room_key != player.room_key:
            return
        if engine._resolve_check(player, "sanity", 3, "恐惧光环"):
            engine._log(f"{engine._player_label(player)} 顶住了恐惧。")
            return
        for pool in (self.MENTAL, self.PHYSICAL):
            stat = self._pick_loss_stat(engine, player, pool)
            if stat is None:
                continue
            engine._apply_stat_loss(player, stat, 1)
        engine._check_player_death(player)
        engine._log(f"{engine._player_label(player)} 被恐惧击垮，心神与体力同时流失。")

    def _pick_loss_stat(self, engine: Any, player: Any, pool: tuple[str, ...]) -> str | None:
        """掉点：人类逐项弹窗，bot 掉在离骷髅最远的那一项（25/32/46 号同款）。"""
        options = [s for s in pool if player.stat_positions.get(s, 0) >= 0]
        if not options:
            return None
        if getattr(player, "control", "bot") != "bot":
            labels = {"sanity": "理智", "knowledge": "知识", "might": "力量", "speed": "速度"}
            idx = engine.prompter.choose_from_list(
                "恐惧光环", "要掉哪一项？", [labels[s] for s in options]
            )
            if idx is not None and 0 <= idx < len(options):
                return options[idx]
        return max(options, key=lambda s: player.stat_positions.get(s, 0))

    # ------------------------------------------------------------- 击败
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p59：理解用法后用诅咒武器击败 → 永久死亡（返回 True 让引擎移除）。"""
        if getattr(monster, "template_id", "") != self.JACK:
            return False
        flags = engine._haunt_flags()
        weapon = flags.get("cursed_weapon")
        if flags.get("cursed_weapon_understood") and weapon_id and weapon_id == weapon:
            flags["jack_killed"] = True
            engine._log("诅咒武器贯穿了他的胸膛——这一次，血腥杰克没有再爬起来。")
            return True
        return False  # 交给 on_monster_defeated 做"暂时消散"

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p130：非诅咒武器击败 → 暂时移出房子（不击晕、不受伤）。"""
        if getattr(monster, "template_id", "") != self.JACK:
            return False
        flags = engine._haunt_flags()
        flags["jack_banished"] = True
        engine.state.monsters = [m for m in engine.state.monsters if m.id != monster.id]
        engine._log(f"{monster.name} 化作一摊血水消散了——但他还会回来，而且更强。")
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        flags = engine._haunt_flags()
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            # 金库没开就不能在里面找武器（p59 "the Vault must be open"）
            if aid == "search_cursed_weapon" and self._vault_locked(engine, player):
                continue
            # 已找到武器就不再显示搜索；没武器/已理解就不能研究
            if aid == "search_cursed_weapon" and flags.get("cursed_weapon"):
                continue
            if aid == "study_cursed_weapon":
                if not flags.get("cursed_weapon"):
                    continue
                if flags.get("cursed_weapon_understood"):
                    continue
            result.append(action)
        return result

    def _vault_locked(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        if room is None or room.template_id != "vault":
            return False
        return not bool(room.data.get("opened"))

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "search_cursed_weapon":
            return self._search_weapon(engine, player)
        if action_id == "study_cursed_weapon":
            return self._study(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _search_weapon(self, engine: Any, player: Any) -> bool:
        """p59：知识 3+ → 从对应牌堆取一件自选诅咒武器。"""
        if self._vault_locked(engine, player):
            return False
        ok = engine._resolve_check(player, "knowledge", 3, "搜寻诅咒武器")
        if not ok:
            engine._log(f"{engine._player_label(player)} 翻遍了书架与暗格，一无所获。")
            return False
        weapon_id = self._pick_weapon(engine, player)
        if weapon_id is None:
            engine._log("宅子里再也找不到可用的诅咒武器了。")
            return False
        self._take_weapon(engine, player, weapon_id)
        engine._haunt_flags()["cursed_weapon"] = weapon_id
        engine._log(
            f"{engine._player_label(player)} 找到了诅咒武器：{self.WEAPON_NAMES.get(weapon_id, weapon_id)}！"
        )
        return True

    def _pick_weapon(self, engine: Any, player: Any) -> str | None:
        """原版由英雄自选；bot 按斧→矛→血匕首取第一件还在牌堆里的。"""
        available = []
        for weapon_id, kind in self.WEAPONS:
            deck = engine.state.card_decks.get(kind, [])
            discard = engine.state.card_discards.get(kind, [])
            if weapon_id in deck or weapon_id in discard:
                available.append(weapon_id)
        if not available:
            return self.WEAPONS[0][0]  # 三处都没有 → 直接发放（强行入场口径）
        if getattr(player, "control", "bot") != "bot" and len(available) > 1:
            idx = engine.prompter.choose_from_list(
                "诅咒武器",
                "要拿哪一件？",
                [self.WEAPON_NAMES.get(w, w) for w in available],
            )
            if idx is not None and 0 <= idx < len(available):
                return available[idx]
        return available[0]

    def _take_weapon(self, engine: Any, player: Any, weapon_id: str) -> None:
        kind = next((k for w, k in self.WEAPONS if w == weapon_id), "item")
        deck = engine.state.card_decks.setdefault(kind, [])
        discard = engine.state.card_discards.setdefault(kind, [])
        if weapon_id in deck:
            deck.remove(weapon_id)
        elif weapon_id in discard:
            discard.remove(weapon_id)
        player.items.append(weapon_id)
        engine.rng.shuffle(deck)  # p59：取走后洗匀该堆

    @staticmethod
    def _weapon_here(engine: Any, player: Any, weapon: str) -> bool:
        """p59：只要**与武器同房间**就能研究（自己拿着、队友拿着、或掉在地上）。"""
        if weapon in player.items:
            return True
        if weapon in (engine.state.room_items.get(player.room_key) or []):
            return True
        return any(
            other.id != player.id
            and not other.dead
            and other.room_key == player.room_key
            and weapon in other.items
            for other in engine.state.players
        )

    def _study(self, engine: Any, player: Any) -> bool:
        """p59：与诅咒武器同房间的英雄做力量 5+ 或知识 5+，成功 +1 枚研究令牌。

        原文允许**所有同房间的英雄各试各的**（成功者的令牌记在自己角色卡上，
        合计到玩家数即"理解用法"）；旧实现要求武器在自己背包里，等于只有拾取者
        能研究——6 人局要一个人成功 6 次，实测 seed107/6p 研究 38 次、进度仍 0。
        """
        flags = engine._haunt_flags()
        weapon = flags.get("cursed_weapon")
        if not weapon or not self._weapon_here(engine, player, weapon):
            return False
        use_might = True
        if getattr(player, "control", "bot") != "bot":
            idx = engine.prompter.choose_from_list(
                "研究武器", "用哪种方式研究诅咒武器？", ["力量 5+", "知识 5+"]
            )
            use_might = idx != 1
        else:
            use_might = player.stats.get("might", 0) >= player.stats.get("knowledge", 0)
        stat = "might" if use_might else "knowledge"
        ok = engine._resolve_check(player, stat, 5, "研究诅咒武器")
        if not ok:
            engine._log(f"{engine._player_label(player)} 的研究毫无进展。")
            return False
        engine._advance_haunt_track("study_tokens")
        needed = engine._haunt_track_target("study_tokens")
        current = engine._haunt_track_value("study_tokens")
        engine._log(f"{engine._player_label(player)} 参透了武器的用法（{current}/{needed}）。")
        if current >= needed > 0:
            flags["cursed_weapon_understood"] = True
            engine._log("诅咒武器的用法彻底明白了——现在它能真正杀死血腥杰克！")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p59：用诅咒武器永久杀死杰克 → 英雄胜
        if flags.get("jack_killed"):
            engine._set_winner("heroes", "血腥杰克终于死了——这一次是真的。")
            return True
        # p130：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "柴垛上又添了几具尸体——血腥杰克从不失手。")
            return True
        # 吸收兜底：叛徒被杀而杰克还在时，杰克继续行动（7/8 号怪物自主口径）
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- bot/UI
    def bot_attack_blocked(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p59：用别的办法击败杰克只会让他**更强地回到门厅**——英雄不该白送。

        引擎的击杀结算里，只有"理解用法 + 手里正是那把诅咒武器"才会永久杀死他
        （`monster_killed_on_defeat`）；其余任何攻击（空手、左轮、别件武器）都走
        `on_monster_defeated` 的"暂时消散"，顺带把 `jack_bonus` 抬 1——实测
        seed127/6p 的杰克加成涨到 +6，多半是英雄自己喂出来的。叛徒不受此限
        （杰克变强对他有利）。
        """
        if getattr(target, "template_id", "") != self.JACK:
            return False
        if getattr(attacker, "role", None) != "hero":
            return False
        flags = engine._haunt_flags()
        weapon = flags.get("cursed_weapon")
        if not flags.get("cursed_weapon_understood") or not weapon:
            return True
        return weapon not in (getattr(attacker, "items", None) or [])

    def bot_weapon_bonus(self, engine: Any, player: Any, target: Any, weapon_id: str | None) -> int:
        """p59：打杰克只该用那把诅咒武器——别的武器（甚至空手）只会把他打散，
        而他下回合会**更强地**回到门厅（`jack_bonus` +1）。

        引擎的击杀结算只认"理解用法 + 手里正是那把武器"（`monster_killed_on_defeat`），
        所以机器人即使已经把武器揣在兜里，也可能按普通打分挑走左轮之类
        （修正前 seed101/3p 一局把杰克打散 9 次、加成涨到 +9）。
        """
        if getattr(target, "template_id", "") != self.JACK:
            return 0
        weapon = engine._haunt_flags().get("cursed_weapon")
        if weapon and weapon_id == weapon:
            return 300
        return -300

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        flags = engine._haunt_flags()
        # 已理解用法 → 去打杰克
        if flags.get("cursed_weapon_understood"):
            jack = self._jack(engine)
            return [f"__room__{jack.room_key}"] if jack is not None else []
        weapon = flags.get("cursed_weapon")
        if not weapon:
            return [r for r in self.SEARCH_ROOMS]
        # 有武器但还没吃透：全体到武器所在房间一起研究（p59 允许同房间的英雄
        # 各自尝试；旧实现只认拾取者，队友还在外面乱走）。M10-60 修。
        for other in engine.state.players:
            if weapon in other.items and not other.dead:
                return [f"__room__{other.room_key}"]
        for room_key, items in engine.state.room_items.items():
            if weapon in items:
                return [f"__room__{room_key}"]
        return []

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = []
        weapon = flags.get("cursed_weapon")
        if weapon:
            name = self.WEAPON_NAMES.get(weapon, weapon)
            state = "已理解用法" if flags.get("cursed_weapon_understood") else "尚未参透"
            lines.append(f"诅咒武器：{name}（{state}）。")
            lines.append(
                f"研究进度：{engine._haunt_track_value('study_tokens')}/"
                f"{engine._haunt_track_target('study_tokens')}。",
            )
        else:
            lines.append("诅咒武器：还没找到（图书馆/教堂/金库/阁楼）。")
        if flags.get("jack_banished"):
            lines.append("血腥杰克暂时消散了下个叛徒回合会回来。")
        bonus = int(flags.get("jack_bonus", 0))
        if bonus:
            lines.append(f"血腥杰克已强化 +{bonus}。")
        return lines
