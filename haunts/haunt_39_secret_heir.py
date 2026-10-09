"""HeirAssassinMode（剧本 39）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class HeirAssassinMode(GenericModeHandler):
    """剧本 39 继承人（The Heir）。

    权威原文：英雄手册 p50 / 叛徒手册 p121。

    · 雕像走廊强制入场；王座在其内。
    · 继承人：揭示者秘密选择（bot 随机选一名非自己英雄），身份存
      flags["heir_id"]；继承人死亡 → 叛徒胜。
    · 刺客：数量 = 玩家数，隐藏在已探明空房（每房至多一只，不在
      占用房/雕像走廊）；英雄进入即暴露 → sneak attack（Might 2 无
      防御）→ 攻击后服毒死亡。
    · 计时：叛徒回合结束推进；第 3/6 回合各补一批新刺客。
    · 矛：p50 原文是 "the Spear card"——直接用项目卡表里的 omen_spear
      （长矛）放进随机已探明房间（旧版写成 marker 令牌 → 无人能拾取、
      英雄胜利线不可达；M10-35 改为卡牌，走引擎常规拾取/交易通道）。
    · 胜利：继承人在雕像走廊持矛 + 戒指 → 英雄胜；继承人死 → 叛徒胜。
    · 简化：叛徒不知道继承人是谁（bot 不针对性攻击）；刺客 bot 追
      最近英雄（引擎默认——隐藏刺客被暴露后才能移动，隐藏状态
      on_monster_move 返回 True 不动）。
    """

    mode = "secret_heir"

    ASSASSIN = "cultist"
    THRONE_ROOM = "statuary_corridor"
    # p50：英雄胜利要求"继承人在王座上同时持有长矛与戒指"。
    # 与 rule_data.required_cards 声明的是同两张牌（改一处必须改两处）。
    REQUIRED_CARDS = ("omen_spear", "omen_ring")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        corridor = engine._ensure_room_in_play(self.THRONE_ROOM, room_key)
        flags["throne_room"] = corridor
        # 继承人：随机选一名非揭示者英雄
        revealer_id = engine.state.haunt_revealer_id
        candidates = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.id != revealer_id
        ]
        if not candidates:
            candidates = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        heir = engine.rng.choice(candidates) if candidates else None
        flags["heir_id"] = heir.id if heir else None
        # 刺客：隐藏在已探明空房（不在占用房/雕像走廊）
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.ASSASSIN),
            {},
        )
        spec = dict(spec)
        spec["name"] = "刺客"
        hidden_rooms = sorted(
            k for k, r in engine.state.board.items()
            if r.revealed and not any(
                p.room_key == k and not p.dead for p in engine.state.players
            ) and k != corridor
        )
        engine.rng.shuffle(hidden_rooms)
        assassin_rooms = []
        hidden_ids = flags.setdefault("hidden_assassins", [])
        for i in range(len(engine.state.players)):
            if i < len(hidden_rooms):
                key = hidden_rooms[i]
                monster = engine._spawn_single_haunt_monster(spec, key)
                if monster is not None:
                    assassin_rooms.append(key)
                    hidden_ids.append(str(monster.id))
        flags["assassin_rooms"] = assassin_rooms
        # p50 原文是 "the Spear card"——项目卡表里本来就有 omen_spear（长矛），
        # 这里直接用它、放进随机已探明房间（非雕像走廊），走引擎常规"拾取"
        # 通道。旧版写成 marker 令牌，而引擎没有任何令牌拾取机制，继承人
        # 永远拿不到矛 = 英雄胜利线根本不可达（54 号骷髅同款死锁，M10-35 修）。
        spear_rooms = [k for k in hidden_rooms if k != corridor]
        spear_room = engine.rng.choice(spear_rooms) if spear_rooms else room_key
        flags["spear_room"] = spear_room
        for deck in engine.state.card_decks.values():
            while "omen_spear" in deck:
                deck.remove("omen_spear")
        for discard in engine.state.card_discards.values():
            while "omen_spear" in discard:
                discard.remove("omen_spear")
        for key in list(engine.state.room_items.keys()):
            engine.state.room_items[key] = [
                card_id for card_id in engine.state.room_items[key] if card_id != "omen_spear"
            ]
        engine.state.room_items.setdefault(spear_room, []).append("omen_spear")
        engine._log("一把古老的长矛静静躺在某个房间里，等着它真正的主人。")
        engine._log(f"雕像走廊的王座在等待真正的继承人……（刺客在暗处潜伏）")

    # ------------------------------------------------------------- 内部
    def _heir(self, engine: Any) -> Any | None:
        hid = engine._haunt_flags().get("heir_id")
        return next((p for p in engine.state.players if p.id == hid), None)

    def _throne_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("throne_room")

    def quest_carrier(self, engine: Any) -> int | None:
        """剧本关键牌应该交给谁（供 bot_ai._try_share_quest_items 探测）。

        p50 的英雄胜利要求"继承人本人"持矛与戒登王座——队友捡到矛/戒指
        必须交给他，而通用的"交给持令牌队友"启发在这里不适用（继承人身上
        没有令牌，令牌化还会在 UI 上泄露继承人身份）。返回继承人的 player id。
        """
        heir = self._heir(engine)
        if heir is None or heir.dead:
            return None
        return heir.id

    def bot_wants_steal(self, engine: Any, attacker: Any, target: Any) -> str | None:
        """p50：矛与戒必须落到继承人手里——打赢了就从持有者身上抢回来。

        机器人默认"赢下战斗照常结算伤害、从不偷牌"，而 39 号的胜线是"继承人在
        王座上同时持有长矛与戒指"。实测 seed101/103/107/109/127（3 人局）：
        戒指 5/6 局整局攥在叛徒手里，英雄全程不还手也不夺牌 → 18/18 全败、
        胜线在 AI 层断开。队友抢到也行：`quest_carrier` 会把牌转交给继承人。
        """
        if getattr(attacker, "role", None) != "hero" or getattr(target, "role", None) != "traitor":
            return None
        heir = self._heir(engine)
        if heir is None or heir.dead:
            return None
        held = getattr(target, "items", None) or []
        for card_id in ("omen_spear", "omen_ring"):
            if card_id in held and card_id not in heir.items:
                return card_id
        return None

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p50：继承人先捡地上的矛/戒，之后钉在王座上；队友把牌送去王座。

        关键的"不做什么"：继承人**不去追持牌队友**。队友的目标本来就是
        "继承人在哪"，两个目标互相指对方会变成原地互换房间的互追——
        seed79/5p 实测：持矛的 P0 与继承人 P2 在门厅／入口大厅之间对调了
        250 多个回合，而 `_try_share_quest_items` 要求"回合开始时同房"，
        两人永远凑不到一间，交接从未发生。
        改成"继承人钉在王座等，队友带着牌过来"后交接必然发生（王座本就是
        继承人的终点）。地上的牌照捡——它不会移动，没有互追风险。
        """
        if player.dead or player.role != "hero":
            return []
        throne = self._throne_room(engine)
        heir = self._heir(engine)
        if heir is None or heir.dead:
            return []
        if player.id != heir.id:
            return [f"__room__{heir.room_key}"]
        for card_id in self.REQUIRED_CARDS:
            if card_id in player.items:
                continue
            for room_key, items in engine.state.room_items.items():
                if card_id in items:
                    return [f"__room__{room_key}"]
        return [f"__room__{throne}"] if throne else []

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """p50：交接点上的人各自站住——关键牌要交到继承人手里。

        玩家的通用交接判定（`_try_share_quest_items`）只在**回合开始时**看
        "两人是否同房"，所以两边都必须"到站就停"：

        · 送牌的一方：王座是死胡同，走进去后若还剩步数，通用走位会把仅有的
          出口（回楼梯）当唯一选项选掉——进了又出，回合开始时永远不在王座，
          交接因此从未发生（seed113/5p 实测：持矛者 62 个回合 0 次留在王座房；
          seed101/4p 同款）。
        · 继承人：站在王座上等（它本来就是终点）。

        两种例外都不能钉死：地上还有关键牌就得去捡（seed63/4p：兜底牌落到
        十步外的地板，继承人一动不动空转到 300 回合）；只剩自己一个活人、
        牌还压在牌堆里时得亲自去翻（seed197/5p）。
        """
        if getattr(player, "role", None) != "hero" or getattr(player, "dead", False):
            return False
        heir = self._heir(engine)
        if heir is None or heir.dead:
            return False
        # (1) 送牌方：带着继承人所缺的关键牌站在继承人房里 → 停下等交接。
        if player.id != heir.id:
            if player.room_key != heir.room_key:
                return False
            return any(
                card_id in player.items and card_id not in heir.items
                for card_id in self.REQUIRED_CARDS
            )
        # (2) 继承人：站在王座上等牌送来。
        throne = self._throne_room(engine)
        if not throne or player.room_key != throne:
            return False
        for card_id in self.REQUIRED_CARDS:
            if card_id in player.items:
                continue
            if any(card_id in items for items in engine.state.room_items.values()):
                return False
        if self._required_card_unaccounted(engine) and len(self._alive_heroes(engine)) < 2:
            return False
        return True

    def _alive_heroes(self, engine: Any) -> list[Any]:
        return [
            p for p in engine.state.players if p.role == "hero" and not p.dead
        ]

    def _required_card_unaccounted(self, engine: Any) -> bool:
        """还有关键牌既不在任何活人手上、也不在地上（＝只可能还压在牌堆里）。"""
        for card_id in self.REQUIRED_CARDS:
            if any(
                card_id in p.items
                for p in engine.state.players
                if not p.dead
            ):
                continue
            if any(card_id in items for items in engine.state.room_items.values()):
                continue
            return True
        return False

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """p50：矛与戒都是"要在牌堆里找出来"的卡——凑不齐时得去翻新房间。

        39 号实测（seed109/4p）：戒指还压在预兆牌堆里、没人在探索，继承人在
        王座前干等到 400 回合。这里声明"该去探索了"，bot 会给探索选项大幅加分。

        本轮把这份差事交给**队友**：继承人要钉在王座上等牌送来（见
        `bot_goal_rooms` / `bot_stay_in_room`），它一边守王座一边翻牌的话，
        队友追着它跑又会退回互追。继承人只在"只剩自己一个活人"时才自己去翻。
        """
        if player.dead or player.role != "hero":
            return False
        if not self._required_card_unaccounted(engine):
            return False
        if player.id == engine._haunt_flags().get("heir_id"):
            return len(self._alive_heroes(engine)) < 2
        return True

    # ------------------------------------------------------------- 牌堆兜底
    def _ensure_required_cards_reachable(self, engine: Any) -> None:
        """内容兜底：预兆来源真的枯竭时，把还压在牌堆里的关键牌放到王座脚下。

        p50 / p121 都没有"搜牌堆"条款，引擎的通用搜牌通道
        `_search_deck_for_required_card` 只在**抽预兆**的那一刻生效；而本仓库
        预兆牌 13 张、带预兆符号的房间只有 7 间，房屋探满之后不可能再抽到任何
        预兆（内容失衡见 handoff §11.x）。seed63/4p 实测：继承人已持矛，
        `omen_ring` 静静躺在 6 张残余预兆牌里，49 间房全已揭开、三层前沿全为 0、
        `_has_future_omen_source()` 为 False —— 英雄胜利线物理不可达。

        只在"确实再也抽不到预兆"时才动手，且只挪牌堆里那张关键牌：正常对局
        （前沿还在、预兆还能翻）行为完全不变。
        """
        deck = engine.state.card_decks.get("omen", [])
        missing = [card_id for card_id in self.REQUIRED_CARDS if card_id in deck]
        if not missing:
            return
        if engine._has_future_omen_source():
            return
        throne = self._throne_room(engine)
        if not throne:
            return
        for card_id in missing:
            deck.remove(card_id)
            engine.state.room_items.setdefault(throne, []).append(card_id)
            card = engine.catalog.cards.get(card_id)
            name = card.name if card is not None else card_id
            engine._log(f"再也翻不出新的预兆了——{name}被发现在王座脚下。")

    # ------------------------------------------------------------- 刺客暴露
    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """p121：英雄进入刺客房间 → 暴露并 sneak attack。

        已知简化：原文是"叛徒**可以选择**揭出刺客"，这里是进房即自动揭出。
        原因：揭出发生在**英雄的移动过程中**（常常是机器人回合），而引擎的
        prompt 通道是单实例——机器人回合里它由 BotDecisionProvider 接管
        （confirm 一律 True），人类叛徒的确认框根本递不到；热座局里还可能
        把提示弹给正在移动的英雄玩家本人（等于泄露叛徒的抉择）。
        代价：挂机的叛徒也会靠刺客偷袭伤人（实测叛徒完全不行动时，继承人
        仍可能在途中被打死）。属"叛徒侧人类自选界面"这一已知简化类。
        """
        flags = engine._haunt_flags()
        if player.role != "hero" or player.dead:
            return
        for monster in engine.state.monsters:
            if _monster_id(monster) != self.ASSASSIN:
                continue
            if monster.room_key != room.key:
                continue
            if str(getattr(monster, "id", "")) not in flags.get("hidden_assassins", []):
                continue
            # 暴露
            hid = str(getattr(monster, "id", ""))
            hidden_list = flags.get("hidden_assassins", [])
            if hid in hidden_list:
                hidden_list.remove(hid)
            engine._log(f"一名刺客从暗处跳出来攻击 {player.name}！")
            # sneak attack：Might 2，无防御
            assassin_roll = engine.roll_dice(2, "刺客偷袭")
            engine._log(f"刺客偷袭 {player.name}：{assassin_roll}（无防御）。")
            if assassin_roll > 0:
                engine._deal_damage(player, "physical", assassin_roll, source="刺客")
            # 服毒死亡
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            engine._log("刺客服毒自尽。")
            engine.check_victory()
            return

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.ASSASSIN:
            return False
        if str(getattr(monster, "id", "")) in engine._haunt_flags().get("hidden_assassins", []):
            return True  # 隐藏刺客不动
        return False  # 已暴露的刺客追击最近英雄

    # ------------------------------------------------------------- 计时
    def on_turn_start(self, engine: Any, player: Any) -> None:
        self._ensure_required_cards_reachable(engine)
        flags = engine._haunt_flags()
        if player.role != "traitor" or player.dead:
            return
        current = int(engine._haunt_track_value("assassin_timer")) + 1
        engine._set_haunt_track_value("assassin_timer", current)
        if current in (3, 6):
            # p121：第 3/6 回合各补一批新刺客
            spec = next(
                (s for s in (engine.state.haunt.rule_data or {}).get("monsters", [])
                 if s.get("template_id") == self.ASSASSIN),
                {},
            )
            spec = dict(spec)
            spec["name"] = "刺客"
            available = sorted(
                k for k, r in engine.state.board.items()
                if r.revealed and k not in flags.get("assassin_rooms", [])
                and k != flags.get("throne_room")
                and not any(m.room_key == k for m in engine.state.monsters)
            )
            engine.rng.shuffle(available)
            for i in range(len(engine.state.players)):
                if i < len(available):
                    monster = engine._spawn_single_haunt_monster(spec, available[i])
                    if monster is not None:
                        hidden_ids = flags.setdefault("hidden_assassins", [])
                        hidden_ids.append(str(monster.id))
                        flags["assassin_rooms"].append(available[i])
            engine._log("新的刺客潜入了房子！")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heir = self._heir(engine)
        if heir is not None and heir.dead:
            engine._set_winner("traitor", "继承人死了——纸皇冠染上了鲜血。")
            return True
        if heir is not None:
            throne = self._throne_room(engine)
            has_spear = "omen_spear" in heir.items
            has_ring = "omen_ring" in heir.items
            if heir.room_key == throne and has_spear and has_ring:
                engine._set_winner("heroes", "戒指化为王冠，长矛缩成钥匙——继承人知道了……一切。")
                return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "再没有人能继承罗马尼斯库的遗产了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p50/p121 只认"继承人持矛与戒登上王座"，
        # 刺客们不随叛徒死亡停下。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
