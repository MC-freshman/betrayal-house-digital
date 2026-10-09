"""TwistingNetherMode（剧本 63）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    DIRECTION_DELTAS,
    GenericModeHandler,
    HauntAction,
)


class TwistingNetherMode(GenericModeHandler):
    """剧本 63 扭曲虚空（The Twisting Nether）。

    权威原文：英雄手册 p74 / 叛徒手册 p145。

    英雄（p74）：
        · 「锚定房间」：**带预兆符号的房间**内，每回合一次，知识 5+ 立下一个锚
          （持骷髅 +1 骰、持通灵板 +2 骰）；同一房间只能有一个锚。
        · 含锚的房间、以及与含锚房间**连通**的房间都算"已锚定"。
        · 锚定房间数按人数：3 人 12 / 4 人 15 / 5 人 19 / 6 人 21 → 英雄胜。
        · 开局与每回合结束：只保留 门厅/门廊/大楼梯/上层平台/地下室平台、
          有探险者或怪物或锚的房间、以及与上述房间直接或间接连通的房间，
          其余板块连同房内的物品/预兆/事件一起收回牌堆、洗匀。
    叛徒（p145）：
        · 首个回合：放星界灵；英雄 ≥3 加放 Specter、≥4 加放 Ghost、
          5 名英雄加放 Phantom ——都放在"至少还有一个未探索门口"的房间。
        · 胜利：英雄全灭。

    特殊规则（p145）：
        · Specter：攻击速度或知识低于 4 的目标时多掷 1 枚骰。
        · Ghost：以理智攻击、被理智防御、造成精神伤害；免疫力量与速度攻击，
          持戒指（omen_ring）的英雄才能改以理智打它。
        · Phantom：行动前可瞬移到有别的怪物或叛徒的房间。

    已知简化：
        · 「穿越虚空」（从没有板块的门离开时多花 1 点移动、三选一）落地为：
          ① 开场的 "Right Now" 清算按原文执行，房子当场被撕成几座孤岛；
          ② 每回合结束按原文收回"没人在、没有锚、也不与起始板块连通"的孤岛；
          ③ **选项 3「寻求特定目的地」建成了独立行动 `nether_seek`**：站在有
             未探索门口的房间，知识 4+ 跳到任意"还有未探索门口"的房间——
             这是英雄唯一能跨孤岛的通道，缺了它胜线整条断掉；
          ④ **选项 1「随机坠入虚空」**作为检定失败的后果：从牌堆顶抽一块板块
             放在四邻皆空的格子上（与现有房间不连通）再把探险者放进去；
          ⑤ 选项 2「连接新房间」就是引擎常规的探索（本来就门对门接上），
             不再单独建模；"多花 1 点移动"没落地——跨孤岛改以"消耗本回合的
             剧本行动"作代价，避免动到通用移动逻辑；
          ⑥ 敌方按 p145 "All monsters can explore new rooms" 允许跨孤岛，
             简化为"目标在别的孤岛时直接落到它邻接的房间"（见
             `on_monster_turn_start`），不做额外移动力与检定。
        · 神秘电梯（原文"失效，当普通房间"）在本引擎仍可乘坐；神秘滑梯/
          Gallery/塌陷室的虚空特例未处理。
        · Phantom 的"瞬移到任意有怪物或叛徒的房间"简化为"瞬移到离最近英雄
          最近的那个候选房间"（原版由叛徒任选，bot 固定取最优）。
    """

    mode = "twisting_nether"

    ANCHOR_ACTION = "anchor_room"
    SEEK_ACTION = "nether_seek"
    ANCHOR_TOKEN = "anchor"
    SPIRIT = "astral_spirit"
    SPECTER = "spectre"
    GHOST = "ghost"
    PHANTOM = "shadow"  # 引擎没有 phantom 模板；借未占用的 shadow 承载，名字改写
    PHANTOM_NAME = "魅影"

    # p74：锚定房间数按人数（3/4/5/6 人 → 12/15/19/21）
    ANCHOR_TARGETS = {3: 12, 4: 15, 5: 19, 6: 21}
    # p74/p145：锚定需要预兆符号，知识 5+；骷髅 +1 骰、通灵板 +2 骰。
    # 通灵板的 +2 由它自己的卡牌 bonus（knowledge +2）经 `_check_bonus` 结算，
    # 这里只补骷髅那 +1，避免重复计数。
    ANCHOR_MIN = 5
    ANCHOR_BONUS = {"omen_skull": 1}
    # p74/p145「穿越虚空」选项 3：知识 4+（持通灵板 +2 骰）跳到任意"还有
    # 未探索门口"的房间。通灵板的 +2 同样走卡牌 bonus（knowledge +2），
    # 这里不再重复补骰。
    SEEK_MIN = 4
    # 开局与每回合结束都不动的起始板块
    FIXED_ROOMS = (
        "entrance_hall",
        "foyer",
        "grand_staircase",
        "upper_landing",
        "basement_landing",
    )

    # ------------------------------------------------------------- 小工具
    @staticmethod
    def _monster_id(entity: Any) -> str:
        return str(getattr(entity, "template_id", "") or "")

    def _target(self, engine: Any) -> int:
        players = len(engine.state.players)
        return int(self.ANCHOR_TARGETS.get(players, 12))

    def _haunt_room(self, engine: Any) -> str:
        return str(engine._haunt_rule_state().get("haunt_room") or "")

    # ------------------------------------------------------------- 开场
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["anchored_rooms"] = []
        flags["dissolved_rooms"] = []
        flags["nether_spawned"] = False
        target = self._target(engine)
        track = engine._haunt_tracks().setdefault(
            "anchor_progress", {"label": "锚定房间", "value": 0, "side": "heroes"}
        )
        track["label"] = "锚定房间"
        track["target"] = target
        track["value"] = 0
        engine._log(
            f"一次剧烈的颠簸把所有人掀翻在地——房子之外的现实扭曲成一片阴影。"
            f"英雄必须锚定 {target} 间房，才能把它拉回物质位面！"
        )
        # p74 "Right Now"：**只**保留五间起始板块与有探险者的房间（原文
        # "Remove from play any rooms that do not contain explorers except for
        # the Entrance Hall/Foyer/Grand Staircase, Upper Landing, and Basement
        # Landing"）——这一刀把房子当场撕成几座孤岛，正是本剧本的核心压力：
        # 之后的每回合结束，没人在、没有锚、也不与起始板块连通的孤岛会被虚空
        # 整个吃掉。开场若照"连通闭包"清算，整栋房子连成一片、锚一次就满，
        # 机制会退化成 1-4 次锚定的走过场（seed101/3p 实测）。
        self._purge(engine, keep_closure=False)

    # ------------------------------------------------------------- 锚定
    def _can_anchor(self, engine: Any, player: Any) -> bool:
        room = engine.state.board.get(player.room_key)
        if room is None or getattr(room, "symbol", None) != "omen":
            return False
        return player.room_key not in engine._haunt_flags().get("anchored_rooms", [])

    # ------------------------------------------------- 穿越虚空（p74 选项 3）
    #
    # 这一条是**英雄胜线的命门**，不是锦上添花：p74 "Right Now" 开场那一刀按
    # 原文只保留五间起始板块与有探险者的房间，房子当场被撕成几座孤岛；而预兆房
    # 落在哪座孤岛上是随机的（seed151/4p 实测：唯一存活下来的预兆房"墓地"与叛徒
    # 同岛，三名英雄全在别的孤岛上）。不做选项 3，英雄永远够不到那座孤岛，
    # anchor_progress 一局钉死在 0，叛徒靠怪物收割 100% 获胜。
    def _seek_departure_ok(self, engine: Any, player: Any) -> bool:
        """出发条件（p74）：所在房间要有一扇门通向还没有板块的格子。"""
        return player.room_key in self._unexplored_door_rooms(engine)

    def _seek_destinations(self, engine: Any, player: Any) -> list[str]:
        """目的地（p74 选项 3）：任意**至少还有一扇未探索门口**的房间。"""
        return [
            key
            for key in self._unexplored_door_rooms(engine)
            if key != player.room_key
        ]

    def _best_seek_destination(self, engine: Any, player: Any) -> tuple[str, int] | None:
        """挑一个"离某个未锚定预兆房最近"的落点，返回 (房间, 距离)。

        距离 < 9999 就说明落点与那间预兆房在**同一座孤岛**上——落到那儿之后再
        走过去锚定即可。全体落点都够不到预兆房时返回 None（这时该去探索，
        而不是白掷一次知识）。
        """
        destinations = self._seek_destinations(engine, player)
        if not destinations:
            return None
        anchored = set(engine._haunt_flags().get("anchored_rooms", []))
        omens = [
            key
            for key in sorted(engine.state.board)
            if getattr(engine.state.board[key], "symbol", None) == "omen"
            and key not in anchored
        ]
        if not omens:
            return None
        best = min(
            sorted(destinations),
            key=lambda key: (min(engine._path_length(key, omen) for omen in omens), key),
        )
        return best, min(engine._path_length(best, omen) for omen in omens)

    def _seek_useful(self, engine: Any, player: Any) -> bool:
        """只在"真的够不到预兆房、但跳一下就能够到"时才把这个行动摆出来。

        与 18/62 号同样的教训：行动摆出来却一局都没用过，就是"空转"警报。
        门槛必须与 bot 的用法同源，所以这里把两个条件都写死。
        """
        if not self._seek_departure_ok(engine, player):
            return False
        anchored = set(engine._haunt_flags().get("anchored_rooms", []))
        for key, room in engine.state.board.items():
            if getattr(room, "symbol", None) != "omen" or key in anchored:
                continue
            if engine._path_length(player.room_key, key) < 9999:
                return False  # 能走过去，不需要跳
        picked = self._best_seek_destination(engine, player)
        return bool(picked and picked[1] < 9999)

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if player.role != "hero":
            return actions
        if not self._can_anchor(engine, player):
            actions = [
                action
                for action in actions
                if str(getattr(action, "id", "")) != self.ANCHOR_ACTION
            ]
        if self._seek_useful(engine, player):
            picked = self._best_seek_destination(engine, player)
            destination = engine.state.board.get(picked[0]) if picked else None
            actions = list(actions) + [
                HauntAction(
                    self.SEEK_ACTION,
                    "穿越虚空",
                    f"知识 {self.SEEK_MIN}+：跳到 {destination.name if destination else '未知房间'}"
                    "（附近有预兆房）",
                    {"room": picked[0]} if picked else {},
                )
            ]
        return actions

    def _fall_through_nether(self, engine: Any, player: Any) -> str | None:
        """p74 选项 1「随机坠入虚空」：从牌堆顶抽一块板块（不论楼层），

        放在**不与任何房间连通**的空格上，然后把探险者放进去。检定失败的
        代价就是"你没跳成想去的地方，虚空把你扔到了别处"。
        """
        deck = engine.state.room_deck
        if not deck:
            # 牌堆抽空 → 把弃牌堆洗回来（与 `_draw_room_template` 同口径）。
            engine.state.room_deck = list(engine.state.room_discard)
            engine.state.room_discard = []
            engine.rng.shuffle(engine.state.room_deck)
            deck = engine.state.room_deck
        template = None
        while deck:
            # 与常规探索同口径：从牌堆尾部拿（`room_deck.pop()`）。
            candidate = engine.catalog.room_templates.get(deck.pop())
            if candidate is not None:
                template = candidate
                break
        if template is None:
            return None
        slot = self._isolated_slot(engine, template.floor)
        if slot is None:
            return None
        rotated = engine._build_rotated_template(template, 0)
        room = engine._place_room(rotated, slot[0], slot[1], 0)
        engine._move_to_room(player, room.key, via_effect=True)
        engine._log(f"{player.name} 翻滚着跌进{room.name}——它与任何房间都不相连。")
        return room.key

    @staticmethod
    def _isolated_slot(engine: Any, floor: int, radius: int = 8) -> tuple[int, int] | None:
        """找一格"空着且四邻皆空"的坐标，保证新板块不与现有房间连通。

        按"离大宅最近"的顺序扫，避免把板块甩到棋盘边缘（前端画布有边界）。
        """
        taken = engine.state.pos_index
        offsets = sorted(
            (
                (x, y)
                for x in range(-radius, radius + 1)
                for y in range(-radius, radius + 1)
            ),
            key=lambda pos: (max(abs(pos[0]), abs(pos[1])), abs(pos[0]) + abs(pos[1]), pos),
        )
        deltas = tuple(DIRECTION_DELTAS.values())
        for x, y in offsets:
            if (floor, x, y) in taken:
                continue
            if any((floor, x + dx, y + dy) in taken for dx, dy in deltas):
                continue
            return x, y
        return None

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == self.SEEK_ACTION:
            return self._perform_seek(engine, player, data)
        if action_id != self.ANCHOR_ACTION:
            return super().perform_action(engine, player, action_id, data)
        if not self._can_anchor(engine, player):
            engine._log(f"{player.name} 这里没有预兆符号，钉不住现实。")
            return False
        # 检定自己做：器具的额外骰（p74 骷髅 +1 / 通灵板 +2）通用通道表达不了。
        bonus = sum(
            dice for card_id, dice in self.ANCHOR_BONUS.items() if card_id in player.items
        )
        dice = engine._effective_stat(player, "knowledge") + engine._check_bonus(
            player, "knowledge"
        )
        dice = max(1, min(8, dice + bonus))
        roll = engine.roll_dice(dice, "锚定房间")
        if bonus:
            engine._log(f"{player.name} 借法器多掷了 {bonus} 枚骰（共 {dice} 枚）。")
        engine._log(f"锚定房间：{player.name} 掷出 {roll}，目标 {self.ANCHOR_MIN}。")
        if roll < self.ANCHOR_MIN:
            engine._log(f"{player.name} 没能在这个房间钉住现实。")
            return True  # 失败也算行动已执行（否则机器人会反复尝试）
        room = engine.state.board[player.room_key]
        engine.spawn_token(
            self.ANCHOR_TOKEN, label="锚", role="marker", room_key=player.room_key
        )
        anchored = engine._haunt_flags().setdefault("anchored_rooms", [])
        if player.room_key not in anchored:
            anchored.append(player.room_key)
        region = self._recount(engine)
        engine._log(
            f"{room.name} 被锚定了！锚网现覆盖 {len(region)}/{self._target(engine)} 间房。"
        )
        return True

    def _perform_seek(self, engine: Any, player: Any, data: dict) -> bool:
        if not self._seek_departure_ok(engine, player):
            engine._log(f"{player.name} 这里没有通向虚空的门口。")
            return False
        destination = str(data.get("room") or "")
        if destination not in self._seek_destinations(engine, player):
            picked = self._best_seek_destination(engine, player)
            destination = picked[0] if picked else ""
        dice = engine._effective_stat(player, "knowledge") + engine._check_bonus(
            player, "knowledge"
        )
        dice = max(1, min(8, dice))
        roll = engine.roll_dice(dice, "穿越虚空")
        engine._log(f"穿越虚空：{player.name} 掷出 {roll}，目标 {self.SEEK_MIN}。")
        if roll < self.SEEK_MIN or not destination:
            engine._log(f"{player.name} 没找准方向，被虚空甩了出去。")
            self._fall_through_nether(engine, player)
            return True
        engine._log(f"{player.name} 在虚空中锁定了目标。")
        engine._move_to_room(player, destination, via_effect=True)
        return True

    # ------------------------------------------------------- 锚定区域 / 收回
    def _anchored_region(self, engine: Any) -> set[str]:
        """含锚房间 + 与含锚房间直接或间接连通的房间（p74）。"""
        anchors = {
            token.room_key
            for token in engine.tokens_of_kind(self.ANCHOR_TOKEN)
            if token.room_key and token.room_key in engine.state.board
        }
        if not anchors:
            return set()
        graph = engine._build_graph()
        seen = set(anchors)
        frontier = list(anchors)
        while frontier:
            key = frontier.pop()
            for neighbor in graph.get(key, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        return seen

    def _recount(self, engine: Any) -> set[str]:
        region = self._anchored_region(engine)
        engine._set_haunt_track_value("anchor_progress", len(region))
        return region

    def _keep_set(self, engine: Any, closure: bool = True) -> set[str]:
        """每回合结束时必须留下的房间（p74/p145 "Do This After Each Turn"）。

        closure=True：再加上"与上述房间直接或间接连通"的房间（每回合结束）。
        closure=False：只要 起始板块 + 有探险者/怪物的房间（开场 "Right Now"
        那一刀，原文没有连通这一条）。
        """
        keep: set[str] = set()
        for key, room in engine.state.board.items():
            if room.template_id in self.FIXED_ROOMS:
                keep.add(key)
            if engine.tokens_in_room(key, self.ANCHOR_TOKEN):
                keep.add(key)
        haunt_room = self._haunt_room(engine)
        if haunt_room in engine.state.board:
            keep.add(haunt_room)
        for player in engine.state.players:
            if not player.dead and player.room_key in engine.state.board:
                keep.add(player.room_key)
        for monster in engine.state.monsters:
            if monster.room_key in engine.state.board:
                keep.add(monster.room_key)
        if not closure:
            return keep
        # 连通闭包：与上述任一房间"直接或间接连通"的都在场
        graph = engine._build_graph()
        seen = set(keep)
        frontier = list(keep)
        while frontier:
            key = frontier.pop()
            for neighbor in graph.get(key, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        return seen

    def _recycle_room(self, engine: Any, key: str) -> None:
        """把一块板块收回牌堆：房内的物品/预兆/事件先洗回对应牌堆。"""
        room = engine.state.board.get(key)
        if room is None:
            return
        for card_id in list(engine.state.room_items.pop(key, [])):
            card = engine.catalog.cards.get(card_id)
            kind = card.kind if card is not None else "item"
            engine.state.card_decks.setdefault(kind, []).append(card_id)
        for token in [
            t for t in engine.state.tokens if t.room_key == key and t.holder is None
        ]:
            engine.remove_token(token.uid)
        engine._detach_room(key, return_to_deck=True, force=True)

    def _purge(self, engine: Any, keep_closure: bool = True) -> list[str]:
        keep = self._keep_set(engine, closure=keep_closure)
        removed: list[str] = []
        for key in sorted(engine.state.board):
            if key in keep:
                continue
            name = engine.state.board[key].name
            self._recycle_room(engine, key)
            removed.append(key)
            engine._log(f"{name} 被虚空吞掉了。")
        if removed:
            flags = engine._haunt_flags()
            flags["dissolved_rooms"] = sorted(
                set(flags.get("dissolved_rooms", [])) | set(removed)
            )
            # p74/p145："shuffle the room tiles back into the room stack"。
            # `_detach_room(return_to_deck=True)` 是 `insert(0, ...)`，而抽牌是
            # `room_deck.pop()`（从尾部拿）——不洗一次，被回收的板块会**排在整副
            # 牌的最后**，预兆房等于被雪藏。seed151/4p 实测：开场回收 39 块之后
            # 英雄连翻 12 间房，一间预兆房都没翻到，锚定数永远 0。
            engine._shuffle_room_piles()
        return removed

    def on_turn_end(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE":
            return
        self._purge(engine)
        self._recount(engine)

    # ------------------------------------------------------------- 虚空怪物
    def _unexplored_door_rooms(self, engine: Any) -> list[str]:
        """至少还有一扇门通向空白格（未探索门口）的房间。"""
        result: list[str] = []
        for key in sorted(engine.state.board):
            room = engine.state.board[key]
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                if (room.floor, room.x + dx, room.y + dy) not in engine.state.pos_index:
                    result.append(key)
                    break
        return result

    def _spawn_nether(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        flags["nether_spawned"] = True
        heroes = len(
            [p for p in engine.state.players if p.role == "hero" and not p.dead]
        )
        plan = [self.SPIRIT]
        if heroes >= 3:
            plan.append(self.SPECTER)
        if heroes >= 4:
            plan.append(self.GHOST)
        if heroes >= 5:
            plan.append(self.PHANTOM)
        specs = engine._haunt_rule_state().get("monster_specs", {})
        rooms = self._unexplored_door_rooms(engine)
        fallback = self._haunt_room(engine)
        for index, template_id in enumerate(plan):
            spec = dict(specs.get(template_id) or {"template_id": template_id})
            spec.setdefault("template_id", template_id)
            if template_id == self.PHANTOM:
                spec.setdefault("name", self.PHANTOM_NAME)
            if rooms:
                room_key = rooms[index % len(rooms)]
            elif fallback in engine.state.board:
                room_key = fallback
            else:
                room_key = next(iter(sorted(engine.state.board)), "")
            if not room_key:
                continue
            engine._spawn_single_haunt_monster(spec, room_key)
        engine._log("虚空里挤出了东西——它们要在房子里猎杀探险者。")

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if engine.state.phase != "HAUNT_PHASE":
            return
        # p145 "At the Start of Your First Turn"
        if (
            player.role == "traitor"
            and not player.dead
            and not engine._haunt_flags().get("nether_spawned")
        ):
            self._spawn_nether(engine)

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """虚空穿行（p145 "All monsters can explore new rooms in this Haunt"）。

        原作里怪物同样走"穿越虚空"三选一，所以它们能跨过没有板块的门。本引擎
        的移动完全基于门图，孤岛之间不连通——不补这一条，"开场清算把房子撕成
        孤岛"之后怪物会永远够不到隔壁岛上的英雄，叛徒的胜线整条断掉
        （seed113/5p 实测：3 只怪物与最后 1 名英雄僵到 300 回合）。
        简化：不做三选一与额外移动力，只把"目标在别的孤岛"这一种情况简化为
        直接落到目标邻接的房间。
        """
        if self._monster_id(monster) == self.PHANTOM:
            dest = self._phantom_destination(engine, monster)
            if dest and dest != monster.room_key:
                monster.room_key = dest
                engine._log(f"{monster.name} 瞬移到了 {engine.state.board[dest].name}。")
        target = engine._find_monster_target(monster)
        if target is None or target.room_key not in engine.state.board:
            return False
        if engine._path_length(monster.room_key, target.room_key) < 9999:
            return False
        dest = next(
            iter(sorted(engine._build_graph().get(target.room_key, ()))), target.room_key
        )
        monster.room_key = dest
        engine._log(
            f"{monster.name} 穿过扭曲的虚空，从 {engine.state.board[dest].name} 逼近。"
        )
        return False

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """英雄的本层预兆房锚完之后必须去翻新房间——牌堆里还有被虚空收回的
        板块（里面就有新的预兆房），不去探索就只能在已探明的几间房之间游荡
        （seed113/5p 实测：机器人5 在花园一带空转到 300 回合）。
        """
        if player.role != "hero" or player.dead:
            return False
        anchored = set(engine._haunt_flags().get("anchored_rooms", []))
        for key, room in engine.state.board.items():
            if getattr(room, "symbol", None) != "omen" or key in anchored:
                continue
            if engine._path_length(player.room_key, key) < 9999:
                return False
        return True

    def _phantom_destination(self, engine: Any, monster: Any) -> str | None:
        candidates: set[str] = set()
        for other in engine.state.monsters:
            if getattr(other, "id", None) == getattr(monster, "id", None):
                continue
            if other.room_key in engine.state.board:
                candidates.add(other.room_key)
        for player in engine.state.players:
            if player.role == "traitor" and not player.dead and player.room_key:
                candidates.add(player.room_key)
        candidates = {key for key in candidates if key in engine.state.board}
        if not candidates:
            return None
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return sorted(candidates)[0]

        def score(key: str) -> tuple[int, str]:
            return (min(engine._path_length(key, hero.room_key) for hero in heroes), key)

        return min(sorted(candidates), key=score)

    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        """p145：Specter 攻击速度或知识低于 4 的目标时多掷 1 枚骰。"""
        if self._monster_id(monster) != self.SPECTER:
            return 0
        stats = getattr(target, "stats", None)
        if not isinstance(stats, dict):
            return 0
        if stats.get("speed", 99) < 4 or stats.get("knowledge", 99) < 4:
            return 1
        return 0

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p145：Ghost 以理智攻击、造成精神伤害，防御方也用理智。"""
        if self._monster_id(monster) != self.GHOST:
            return False
        victim = next(
            (
                p
                for p in engine.state.players
                if p.role == "hero" and not p.dead and p.room_key == monster.room_key
            ),
            None,
        )
        if victim is None:
            return False
        attack = engine._roll_monster_attack(monster, "sanity")
        defense = engine._roll_attack(victim, "sanity")
        engine._log(
            f"{monster.name} 用理智撕扯 {engine._player_label(victim)}：{attack} 对 {defense}。"
        )
        if attack > defense:
            engine._deal_damage(victim, "mental", attack - defense, source=monster.name)
        elif attack < defense:
            engine._stun_monster(monster, 1)
        else:
            engine._log("平手。")
        return True

    def attack_attr_override(
        self, engine: Any, attacker: Any, target: Any, default_attr: str
    ) -> str | None:
        """p145：Ghost 免疫力量/速度，但持戒指的英雄可以改用理智打它。"""
        if self._monster_id(target) != self.GHOST:
            return None
        if getattr(attacker, "role", "") != "hero":
            return None
        if "omen_ring" in getattr(attacker, "items", []):
            return "sanity"
        return None

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄去还没锚的预兆房间；没有剩余目标就交回通用探索逻辑。

        够不到预兆房（开场清查把房子撕成了孤岛）时，改把"附近还有未探索门口的
        房间"当成目标——走到那样的房间门口，下回合才掷得出 p74 选项 3。没有这
        一步，机器人会抱着一个 `_path_length == 9999` 的目标原地打转到终局。
        """
        if player.role != "hero":
            return []
        anchored = set(engine._haunt_flags().get("anchored_rooms", []))
        targets = [
            f"__room__{key}"
            for key in sorted(engine.state.board)
            if getattr(engine.state.board[key], "symbol", None) == "omen"
            and key not in anchored
        ]
        if not targets:
            return []
        if any(
            engine._path_length(player.room_key, key) < 9999
            for key in (t[len("__room__") :] for t in targets)
        ):
            return targets
        picked = self._best_seek_destination(engine, player)
        if not picked or picked[1] >= 9999:
            return targets
        departures = [
            f"__room__{key}"
            for key in sorted(self._unexplored_door_rooms(engine))
            if engine._path_length(player.room_key, key) < 9999
        ]
        return departures or targets

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        self._recount(engine)
        target = engine._haunt_track_target("anchor_progress") or self._target(engine)
        if engine._haunt_track_value("anchor_progress") >= target:
            engine._set_winner("heroes", "足够的房间被锚回现实——房子重新变得坚实！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后的英雄也消失在虚空里。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p74/p145 的英雄胜只认"锚定足够
        # 房间"，叛徒倒下后虚空怪物照常行动（见 verify_traitor_death_semantics_sweep
        # 的 keeps_playing 名单，63 号在其中）。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        region = self._anchored_region(engine)
        target = engine._haunt_track_target("anchor_progress") or self._target(engine)
        anchors = len(engine.tokens_of_kind(self.ANCHOR_TOKEN))
        monsters = "、".join(m.name for m in engine.state.monsters) or "尚未出现"
        return [
            f"锚定房间 {len(region)}/{target}（锚点 {anchors} 个）。",
            f"虚空怪物：{monsters}。",
        ]
