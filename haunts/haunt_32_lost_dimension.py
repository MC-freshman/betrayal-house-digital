"""LostDimensionMode（剧本 32）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class LostDimensionMode(GenericModeHandler):
    """剧本 32「Lost / 迷失异维度」（英雄手册 p43 / 叛徒手册 p114）。

    叛徒是外星人，把整栋房子搬到了自己的维度——大气本身在慢慢杀死英雄。
    英雄唯一的出路是风琴房的管风琴：它同时也是一台跨维度传送器，弹对
    那首曲子就能把房子送回家。

    · 开局（p114）：房屋重排 + 保证风琴房在场。
    · 毒大气（p43）：每个英雄回合开始掷 2 骰，从任意属性组合里扣减——
      人类逐点弹窗自选，bot 自动扣在「掉 1 点不会死」里数值最高的一项。
    · 三条线索（p43，各 +2，全局共享、各只能找到一次）：
      图书馆知识 5+ 找乐谱、游戏室理智 5+ 认标本、塔楼知识 5+ 观星象。
      这三条由 rule_data 声明，走 `_perform_generic_haunt_action`。
    · 弹奏（p43）：风琴房每回合一次知识检定，结果需达到按人数定的门槛
      （3/4/5/6 人 → 15/16/18/20+）。加值：场上每间预兆符号房 +1；
      三条线索各 +2；疯子（同伴）或书（魔典卡）在风琴房各 +2；
      叛徒每放一枚干扰令牌 -3。达标 → 房子回原维度，英雄胜。
    · 干扰（p114）：叛徒在教堂/游戏室/两间实验室/五芒星室做知识 4+，
      成功就在该房放一枚干扰令牌（每间限一枚）——这是叛徒除了杀人之外
      唯一的主动手段，bot 会优先跑完这五间。
    · 胜负（p43/p114）：英雄胜 = 弹奏达标；叛徒胜 = 英雄全灭。叛徒死亡
      后毒大气照常生效（老坑 21 号吸收者）。

    已知简化：
        · 「占用」取保护性更宽的读法：房内有玩家/怪物/**地面令牌或卡牌**都算
          占用（原版 p114 只提 figure）——避免把放在地上的道具连同板块一起被
          收回牌堆。这是刻意取舍，不是遗漏。
        · 「移除通往被撤房间的 Secret Passage / Secret Stairs / Wall Switch
          令牌」：本仓库的密道/密梯建模为房间的双向 `links["secret"]`，撤牌时
          由 `engine._detach_room` 自动清理；Wall Switch 没有对应组件、未建模。
        · 「爱好音乐 +2」未建模——角色数据没有 hobby 字段（同 24 号口径）。
        · 疯子与书的判定只看「持有人/房间物品在风琴房」，原版还要求
          疯子是有意识的同伴（引擎不区分同伴是否被控制）。
        · 弹奏门槛 15+/16+/18+/20+ 远超单个知识掷骰上限（8 骰 16 点），
          必须靠线索与房间加值堆出来——这是原版设计意图，未做平衡调整。
    """

    mode = "lost_dimension"

    ORGAN_ROOM = "organ_room"
    NEEDED = {3: 15, 4: 16, 5: 18, 6: 20}
    CLUE_LABELS = {"search_books": "乐谱", "search_trophy": "异维度标本", "search_stars": "星象"}
    SABOTAGE_ROOMS = (
        "chapel",
        "game_room",
        "research_laboratory",
        "operating_laboratory",
        "pentagram_chamber",
    )
    STAT_LABELS = {"might": "力量", "speed": "速度", "sanity": "理智", "knowledge": "知识"}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("clue_books", False)
        flags.setdefault("clue_trophy", False)
        flags.setdefault("clue_stars", False)
        flags.setdefault("sabotage_rooms", [])
        flags.setdefault("returned_home", False)

        # p114 第一步：Set aside all the room tiles that have been played in the
        # house so far, except for the starting tiles and any occupied rooms.
        # 「占用」取保护性更宽的读法（含地面上的令牌与卡牌，见
        # engine._is_room_occupied）——避免把地上的道具连同板块一起收走。
        # 撤牌时 `_detach_room` 会顺手清掉指向它的密道/密梯链接，正好对应
        # 原文那句"Remove any Secret Passage / Secret Stairs ... tokens that
        # lead to rooms that have been set aside"（本仓库的密道就是双向
        # `links["secret"]`；Wall Switch 没有对应建模，见「已知简化」）。
        set_aside: list[str] = []
        for key in sorted(engine.state.board):
            room = engine.state.board[key]
            if room.template_id in engine.START_ROOM_IDS:
                continue
            if engine._is_room_occupied(key):
                continue
            set_aside.append(key)
        for key in set_aside:
            engine._detach_room(key, return_to_deck=True, force=True)
        flags["set_aside_rooms"] = len(set_aside)

        # p114：If the Organ Room isn't in the house, take it from the room stack
        # and put it into the house attached to a starting tile of your choice.
        organ_anchor = next(
            (
                k
                for k in sorted(engine.state.board)
                if engine.state.board[k].template_id in engine.START_ROOM_IDS
                and engine.state.board[k].floor == 0
            ),
            room_key,
        )
        placed = engine._ensure_room_in_play(self.ORGAN_ROOM, organ_anchor)
        if not placed:
            placed = engine._attach_template_adjacent(self.ORGAN_ROOM, organ_anchor)
        if placed:
            engine._log(f"管风琴的低鸣从{engine.state.board[placed].name}传来——那是回家的钥匙。")
        else:
            engine._log("管风琴始终没能出现——这一局的回家之路被彻底堵死了。")

        # p114：Shuffle together all the tiles you set aside and all the undrawn
        # rooms from the room stack and discard stack.（撤下的牌已由
        # `_detach_room(return_to_deck=True)` 放回牌堆，这里再把弃牌堆并进来一起洗。）
        engine._shuffle_room_piles()
        engine._log(
            f"整栋房子在震颤中重排——{len(set_aside)} 块房间被卷回牌堆，像牌一样重新洗过。"
        )

        # p114：The occupied room tiles are still in the house. Move them next to
        # the starting tiles of the appropriate floors.（原文是复数的 starting
        # tiles——逐张起始牌试，直到门对门接上，保证人还能走出来。）
        for key in sorted(engine.state.board):
            room = engine.state.board.get(key)
            if room is None or room.template_id in engine.START_ROOM_IDS:
                continue
            if not engine._is_room_occupied(key):
                continue
            anchors = [
                k
                for k in sorted(engine.state.board)
                if engine.state.board[k].floor == room.floor
                and engine.state.board[k].template_id in engine.START_ROOM_IDS
            ]
            for anchor in anchors:
                if engine._place_room_adjacent(key, anchor, require_connection=True):
                    engine._log(f"「{room.name}」连同里面的一切被挪到了起始牌旁边。")
                    break
            else:
                engine._log(f"「{room.name}」四周没有能门对门接上的起始牌空位，留在原处。")

    # ------------------------------------------------------- 回合开始（毒大气）
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE":
            return
        if player.role != "hero" or player.dead:
            return
        if engine._haunt_flags().get("returned_home"):
            return
        total = engine.roll_dice(2, "毒大气")
        if total <= 0:
            engine._log(f"{player.name} 屏住了呼吸——这回合没有被大气灼伤。")
            return
        engine._log(f"{player.name} 吸进一口绿色的空气，掷出 {total}。")
        self._lose_points(engine, player, total)

    def _lose_points(self, engine: Any, player: Any, total: int) -> None:
        for _ in range(total):
            if player.dead:
                return
            # 引擎的「掉点」是卡尺格位移动：格位跌破 0 即死亡，与当前数值无关
            # （轨道有重复值，数值再高也可能只剩一格——25 号巫毒踩过同一个坑）。
            options = [s for s in self.STAT_LABELS if player.stat_positions.get(s, 0) >= 0]
            if not options:
                return
            stat = self._pick_loss_stat(engine, player, options)
            engine._apply_stat_loss(player, stat, 1)
            engine._log(f"  {player.name} 的{self.STAT_LABELS[stat]}被灼掉 1 点（{player.stats.get(stat, 0)}）。")
        engine._check_player_death(player)

    def _pick_loss_stat(self, engine: Any, player: Any, options: list[str]) -> str:
        """「从任意属性组合里扣」：人类逐点弹窗，bot 自动扣。"""
        if getattr(player, "control", "bot") != "bot":
            idx = engine.prompter.choose_from_list(
                "异维度的大气",
                f"{player.name}：要扣掉 1 点哪一项属性？",
                [self.STAT_LABELS[s] for s in options],
            )
            if idx is not None and 0 <= idx < len(options):
                return options[idx]
        # bot：先挑「掉 1 格不会死」的（格位 ≥1），再在其中取格位最高的——
        # 离骷髅最远最能扛；全都只剩最后一格时认命，取格位最高的。
        safe = [s for s in options if player.stat_positions.get(s, 0) >= 1]
        pool = safe or options
        return max(pool, key=lambda s: (player.stat_positions.get(s, 0), player.stats.get(s, 0)))

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        # p114：每间房只能放一枚干扰令牌——已放过的房间不再提供该行动。
        done = set(engine._haunt_flags().get("sabotage_rooms", []))
        if done:
            room = engine.current_room(player)
            if room is not None and room.template_id in done:
                actions = [a for a in actions if a.id != "sabotage_transporter"]
        return actions

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "play_organ":
            return self._play_organ(engine, player)
        if action_id == "sabotage_transporter":
            return self._sabotage(engine, player)
        # 三条线索（图书馆乐谱/游戏室标本/塔楼星象）由 rule_data 声明，
        # 走引擎的通用剧本行动：检定 → set_flags → 推进线索轨道。
        return super().perform_action(engine, player, action_id, data)

    def _needed(self, engine: Any) -> int:
        return self.NEEDED.get(len(engine.state.players), 20)

    def _bonus(self, engine: Any, player: Any) -> tuple[int, list[str]]:
        """p43 的全部加值，返回 (合计, 明细)。"""
        flags = engine._haunt_flags()
        parts: list[str] = []
        total = 0
        omen_rooms = sum(
            1 for room in engine.state.board.values() if room.symbol == "omen" and not engine._is_collapsed(room.key)
        )
        if omen_rooms:
            total += omen_rooms
            parts.append(f"预兆房 +{omen_rooms}")
        for flag_id, label in (("clue_books", "乐谱"), ("clue_trophy", "标本"), ("clue_stars", "星象")):
            if flags.get(flag_id):
                total += 2
                parts.append(f"{label} +2")
        if self._card_in_organ_room(engine, "madman", companions=True):
            total += 2
            parts.append("疯子在场 +2")
        if self._card_in_organ_room(engine, "omen_book", companions=False):
            total += 2
            parts.append("魔典在场 +2")
        sabotage = len(flags.get("sabotage_rooms", []))
        if sabotage:
            total -= 3 * sabotage
            parts.append(f"叛徒干扰 -{3 * sabotage}")
        return total, parts

    def _card_in_organ_room(self, engine: Any, card_id: str, companions: bool) -> bool:
        """某张卡（同伴或物品）是否在风琴房：持有人站着，或掉在地上。"""
        organ_keys = {k for k, room in engine.state.board.items() if room.template_id == self.ORGAN_ROOM}
        if not organ_keys:
            return False
        for other in engine.state.players:
            if other.dead or other.room_key not in organ_keys:
                continue
            pool = other.companions if companions else other.items
            if card_id in pool:
                return True
        for key in organ_keys:
            if card_id in engine.room_items(key):
                return True
        return False

    def _play_organ(self, engine: Any, player: Any) -> bool:
        needed = self._needed(engine)
        bonus, parts = self._bonus(engine, player)
        dice = max(1, min(8, engine._effective_stat(player, "knowledge")))
        roll = engine.roll_dice(dice, "弹奏管风琴")
        total = roll + bonus
        detail = "，".join(parts) if parts else "无加值"
        engine._log(
            f"{player.name} 按下第一个琴键：知识 {dice} 骰掷出 {roll}，"
            f"加值 {bonus:+d}（{detail}），合计 {total}，需要 {needed}+。"
        )
        if total >= needed:
            engine._haunt_flags()["returned_home"] = True
            engine._log("琴声轰然共鸣——房子震颤、移位，空气重新变得透明。你们回家了。")
        else:
            engine._log("管风琴只发出一声贫血的喘息——曲子不对，再想想还缺什么。")
        return True

    def _sabotage(self, engine: Any, player: Any) -> bool:
        room_key = player.room_key
        room = engine.state.board.get(room_key)
        template_id = room.template_id if room else ""
        if template_id not in self.SABOTAGE_ROOMS:
            return False
        flags = engine._haunt_flags()
        done = flags.setdefault("sabotage_rooms", [])
        if template_id in done:
            return False
        if not engine._resolve_check(player, "knowledge", 4, "改造传送器"):
            engine._log(f"{player.name} 没能解开传送器的控制逻辑。")
            return True
        done.append(template_id)
        engine._advance_haunt_track("sabotage", 1)
        engine._log(
            f"{player.name} 改写了{room.name}里的控制符文——英雄的弹奏检定 -3"
            f"（累计 {len(done)} 枚）。"
        )
        return True

    # ------------------------------------------------------- bot 目标（寻路）
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p43/p114：英雄先把三条线索跑齐再去风琴房；叛徒先跑完五间干扰房。

        实测（seed101/3p）：p114 的房屋重排把三间线索房卷回了牌堆（作祟揭示时
        全屋只剩 8 间），而旧实现仍返回这三条**不在场**的模板 id——等于没目标，
        英雄只能黏在风琴房反复弹奏（加值只有"预兆房 +2"，合计 3-8 对门槛 15+），
        三条线索整局 0 次找到。这里只列**在场**的线索房；不在场的交给
        `bot_wants_explore`（翻新房间把线索房重新抽出来）。
        """
        flags = engine._haunt_flags()
        if player.role == "traitor":
            left = [r for r in self.SABOTAGE_ROOMS if r not in flags.get("sabotage_rooms", [])]
            return list(left) if left else []
        in_play = {room.template_id for room in engine.state.board.values()}
        pending: list[str] = []
        for flag_id, room_id in (
            ("clue_books", "library"),
            ("clue_trophy", "game_room"),
            ("clue_stars", "tower"),
        ):
            if not flags.get(flag_id) and room_id in in_play:
                pending.append(room_id)
        # 线索找齐（或线索房还没翻出来）就去风琴房
        if not pending:
            return [self.ORGAN_ROOM]
        # 还差 1-2 条时先补线索：门槛 15+ 靠裸掷骰不可能达到
        return pending + [self.ORGAN_ROOM]

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """p114/p43：线索房被叛徒的重排卷回牌堆时，英雄必须靠探索把它们翻回来。

        少了这条，英雄没有任何信号去翻新房间：`bot_goal_rooms` 的目标全不在场、
        通用换算也不认"被撤走的房间"——实测三局线索 0/3 找到、弹奏加值恒为
        "预兆房 +2~+3"，合计 3-8 对门槛 15-18，必输。翻新房间还有双重收益：
        每条线索 +2，每翻出一间预兆符号房弹奏再 +1。
        """
        if player.role != "hero" or player.dead:
            return False
        flags = engine._haunt_flags()
        pending = [
            room_id
            for flag_id, room_id in (
                ("clue_books", "library"),
                ("clue_trophy", "game_room"),
                ("clue_stars", "tower"),
            )
            if not flags.get(flag_id)
        ]
        if not pending:
            return False
        in_play = {room.template_id for room in engine.state.board.values()}
        missing = [room_id for room_id in pending if room_id not in in_play]
        if not missing:
            return False  # 线索房都在场：走 bot_goal_rooms 去那几间，不必探索
        return any(engine.has_remaining_room_cards(floor) for floor in (-1, 0, 1))

    # ------------------------------------------------------------- 进度
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = [f"回家门槛：{self._needed(engine)}+"]
        found = [label for flag_id, label in (("clue_books", "乐谱"), ("clue_trophy", "标本"), ("clue_stars", "星象")) if flags.get(flag_id)]
        rows.append("线索：" + ("、".join(found) if found else "一条都没找到"))
        sabotage = len(flags.get("sabotage_rooms", []))
        if sabotage:
            rows.append(f"叛徒干扰：{sabotage} 枚（弹奏 -{3 * sabotage}）")
        return rows

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_flags().get("returned_home"):
            engine._set_winner("heroes", "最后一个音符落下，房子回到了它该在的地方。")
            return True
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "绿色的空气终于安静下来——标本们不再挣扎了。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后大气照常杀人
