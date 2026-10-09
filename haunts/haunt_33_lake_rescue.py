"""LakeRescueMode（剧本 33）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    DIRECTION_DELTAS,
    ExitOption,
    GenericModeHandler,
)


class LakeRescueMode(GenericModeHandler):
    """剧本 33 湖中怪物（Creature from the Lake）。

    权威原文：英雄手册 p44 / 叛徒手册 p115。

    · 布点（p44）：地下湖强制入场（带门相邻地下室）；持有女孩卡的
      探险者失去她（女孩卡 set aside，属性微调未建模——同 16/18 口径）。
    · 房屋探索关闭（p44/p115）：can_discover_rooms 仅当"没有任何已探明
      通路进地下室"时放行；地下室门厅开局已探明 → 整局关闭探索。
    · 湖面砖（p44）：从地下湖两侧无门水缘按需铺设——extra_move_options
      追加 `lake:` 前缀选项，move_player 委托 lake_move 铺面并移动。
      砖名"湖面"、面朝下（无符号，不触发抽牌）、四向互连；新砖从房间
      牌堆取模板，耗尽取弃牌堆（p44 "start taking tiles from other
      floors" 的电子版近似——弃牌堆耗尽后不再延伸）。湖面砖与地下湖/
      相邻湖面砖双向开门。
    · 游泳（p44）：回合开始身处湖面砖时自动掷力量（4+ 每砖 2 格 /
      0-3 每砖 3 格），结果存 flags["swim_cost"]；湖面移动的费用下限
      用 movement_cost_floor（新增 to_key 参数）落到 2/3。未掷（本回合
      从干岸入湖）按 3 格计。
    · 搜索表（p115）：回合开始身处湖面砖时掷 4 骰 + 距离加值（与地下湖
      间隔的湖面砖数、含所在砖）+ 水晶球 2，按表结算；19+ 救出女孩
      （英雄胜）。表内"再掷"用累计附加 +3（11 号条目）实现，迭代上限
      8 段防死循环；湖怪 Might 5/6、触手 Speed 5、大浪 Might 5+、
      幻鱼/漩涡 Sanity 4+，全部本地对决实现。
    · 溺水（p115）：叛徒回合开始推进计时并掷等量骰，3-4 人局 10+ /
      5-6 人局 9+ → 女孩溺亡，叛徒胜。
    · 湖面丢弃即沉没（on_item_dropped，p44 "those items are lost"）；
      湖面死亡掉落同样沉没未建模（低频边界）。
    · 简化汇总：搜索从"回合末"近似为"回合开始"（同 16 号口径，
      节奏等价）；女孩卡属性微调未建模；叛徒入湖可战不搜索
      （bot 自然满足）；湖怪不作为常驻怪物实体。
    """

    mode = "lake_rescue"

    LAKE_PREFIX = "lake:"
    LAKE_NAME = "湖面"
    SEARCH_BONUS_CRYSTAL = 2
    SEARCH_BONUS_FRESH_TILE = 3

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        # p115：持女孩卡的探险者失去她（女孩卡 set aside）
        holder = next((p for p in engine.state.players if "omen_girl" in p.items), None)
        if holder is not None:
            holder.items.remove("omen_girl")
        for deck in engine.state.card_decks.values():
            if "omen_girl" in deck:
                deck.remove("omen_girl")
        for key in list(engine.state.room_items.keys()):
            if "omen_girl" in engine.state.room_items.get(key, []):
                engine.state.room_items[key].remove("omen_girl")
        engine.state.card_discards.setdefault("omen", []).append("omen_girl")
        # p115：溺水阈值
        flags["drown_threshold"] = 10 if len(engine.state.players) <= 4 else 9
        flags["swim_cost"] = {}
        lake = next(
            (k for k, r in engine.state.board.items() if r.template_id == "underground_lake"),
            None,
        )
        if lake is None:
            # p44：地下湖不在场则强制入场（带门相邻地下室）
            lake = engine._ensure_room_in_play("underground_lake", room_key)
        flags["lake_room"] = lake
        if lake:
            engine._log("地下湖的湖面炸开又归于平静——女孩被拖进了漆黑的水域。")

    # ------------------------------------------------------------- 内部
    def _lake_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("lake_room") or next(
            (k for k, r in engine.state.board.items() if r.template_id == "underground_lake"),
            None,
        )

    def _is_lake_tile(self, engine: Any, key: str | None) -> bool:
        room = engine.state.board.get(key or "")
        return room is not None and bool(room.data.get("lake_tile"))

    def _water_sides(self, engine: Any, lake_key: str) -> list[str]:
        """地下湖无门的两条边 = 水缘方向。"""
        room = engine.state.board.get(lake_key)
        if room is None:
            return []
        return [d for d in ("north", "east", "south", "west") if d not in room.doors]

    def _lake_adjacent_cells(self, engine: Any, key: str) -> list[tuple[str, int, int, int]]:
        """当前砖可向外铺设/移动的相邻格：水缘方向（地下湖）或全部方向（湖面砖）。"""
        room = engine.state.board.get(key)
        if room is None:
            return []
        if self._is_lake_tile(engine, key):
            directions = ["north", "east", "south", "west"]
        else:
            directions = self._water_sides(engine, key)
        cells = []
        for d in directions:
            dx, dy = DIRECTION_DELTAS[d]
            cells.append((d, room.floor, room.x + dx, room.y + dy))
        return cells

    def _take_template_from_stack(self, engine: Any) -> str | None:
        """p44：铺面用砖先取房间牌堆，再取弃牌堆。"""
        if engine.state.room_deck:
            return engine.state.room_deck.pop()
        if engine.state.room_discard:
            return engine.state.room_discard.pop()
        return None

    def _place_lake_tile(self, engine: Any, floor: int, x: int, y: int, connect_to: str) -> Any | None:
        """在 (floor,x,y) 铺一块面朝下湖面砖，并与 connect_to 双向开门。"""
        target_pos = (floor, x, y)
        if target_pos in engine.state.pos_index:
            return None
        template_id = self._take_template_from_stack(engine)
        template = engine.catalog.room_templates.get(template_id or "")
        if template is None:
            return None
        room = engine._place_room(template, x, y, 0)
        room.name = self.LAKE_NAME
        room.symbol = None
        room.effect_id = "none"
        room.text = ""
        room.data["lake_tile"] = True
        room.revealed = False
        room.doors = ("north", "east", "south", "west")  # 湖面砖四向互连
        # 与来源双向开门
        back = self._direction_between(engine, room.key, connect_to)
        if back:
            neighbor = engine.state.board.get(connect_to)
            if neighbor is not None:
                forward = self._direction_between(engine, connect_to, room.key)
                if forward:
                    neighbor.doors = tuple(sorted(set(neighbor.doors) | {forward}))
            engine.state.pos_index[target_pos] = room.key
        engine._log("一块面朝下的砖铺进水里——湖面又延伸了一格。")
        return room

    def _direction_between(self, engine: Any, key_a: str, key_b: str) -> str | None:
        a = engine.state.board.get(key_a)
        b = engine.state.board.get(key_b)
        if not a or not b or a.floor != b.floor:
            return None
        dx = b.x - a.x
        dy = b.y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy):
                return direction
        return None

    def _swim_cost(self, engine: Any, player: Any) -> int:
        return int(engine._haunt_flags().get("swim_cost", {}).get(str(player.id), 3))

    def _lake_distance(self, engine: Any, player: Any) -> int:
        """与地下湖间隔的湖面砖数（含所在砖）；不在湖面返回 0。"""
        start = player.room_key
        if not self._is_lake_tile(engine, start):
            return 0
        lake = self._lake_room(engine)
        if not lake:
            return 0
        from collections import deque

        visited = {start}
        queue = deque([(start, 1)])
        while queue:
            key, dist = queue.popleft()
            if key == lake:
                return dist - 1  # 地下湖本身不算湖面砖
            room = engine.state.board.get(key)
            for direction in room.doors:
                dx, dy = DIRECTION_DELTAS[direction]
                neighbor = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                if neighbor and neighbor not in visited and (
                    self._is_lake_tile(engine, neighbor) or neighbor == lake
                ):
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))
        return 1

    # ------------------------------------------------------------- 钩子
    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        """p44/p115：只有当没有任何已探明通路进地下室时才允许探索房屋。"""
        from collections import deque

        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        for hero in heroes:
            start = hero.room_key
            visited = {start}
            queue = deque([start])
            while queue:
                key = queue.popleft()
                room = engine.state.board.get(key)
                if room is None:
                    continue
                if room.floor == -1 and room.revealed:
                    return False  # 有已探明的地下室通路：禁止探索新房间
                # 门邻居
                for direction in room.doors:
                    dx, dy = DIRECTION_DELTAS[direction]
                    neighbor = engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
                    if neighbor and neighbor not in visited:
                        neighbor_room = engine.state.board.get(neighbor)
                        if neighbor_room is not None and neighbor_room.revealed:
                            visited.add(neighbor)
                            queue.append(neighbor)
                # 链接邻居（楼梯等跨楼层通路——地下室必须走楼梯）
                for label, target in room.links.items():
                    target_key = engine._link_target_key(target)
                    if target_key and target_key not in visited:
                        neighbor_room = engine.state.board.get(target_key)
                        if neighbor_room is not None and neighbor_room.revealed:
                            visited.add(target_key)
                            queue.append(target_key)
        return True

    def extra_move_options(self, engine: Any, player: Any, options: list) -> list:
        if player.dead or player.movement_stopped:
            return []
        result = []
        existing = {o.target_key for o in options}
        for direction, floor, x, y in self._lake_adjacent_cells(engine, player.room_key):
            target_pos = (floor, x, y)
            target_key = engine.state.pos_index.get(target_pos)
            if target_key:
                continue  # 已有砖：正常门选项已覆盖
            sentinel = f"{self.LAKE_PREFIX}{floor}:{x}:{y}"
            if sentinel in existing:
                continue
            cost = self._swim_cost(engine, player)
            result.append(
                ExitOption(
                    label="划水进入湖面（游泳检定后每砖 2 格，否则 3 格）",
                    direction=direction,
                    target_key=sentinel,
                    target_room_name=self.LAKE_NAME,
                    is_new_room=False,
                    cost=cost,
                )
            )
        return result

    def lake_move(self, engine: Any, player: Any, option: Any) -> bool:
        segs = option.target_key.split(":")
        if len(segs) != 4:
            return False
        floor, x, y = int(segs[1]), int(segs[2]), int(segs[3])
        swim = self._swim_cost(engine, player)
        if swim > player.steps_remaining:
            engine._log(f"{player.name} 的移动力不足以划水（需 {swim} 格）。")
            return False
        target_pos = (floor, x, y)
        target_key = engine.state.pos_index.get(target_pos)
        if not target_key:
            back = self._direction_between_from(engine, player.room_key, floor, x, y)
            if back is None:
                engine._log("只能从相邻的水域格进入湖面。")
                return False
            room = self._place_lake_tile(engine, floor, x, y, player.room_key)
            if room is None:
                engine._log("房间砖已经用完了，湖面无法继续延伸。")
                return False
            target_key = room.key
            engine._haunt_flags().setdefault("fresh_tiles", {})[str(player.id)] = target_key
        player.room_key = target_key
        player.steps_remaining = max(0, player.steps_remaining - swim)
        player.moved_this_turn = True
        engine._log(f"{player.name} 划水进入{engine.state.board[target_key].name}（{swim} 格）。")
        engine._resolve_room_entry_if_needed(player)
        self._search_roll(engine, player)
        engine.check_victory()
        return True

    def _direction_between_from(self, engine: Any, from_key: str, floor: int, x: int, y: int) -> str | None:
        a = engine.state.board.get(from_key)
        if not a or a.floor != floor:
            return None
        dx, dy = x - a.x, y - a.y
        for direction, (ddx, ddy) in {
            "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
        }.items():
            if (dx, dy) == (ddx, ddy):
                return direction
        return None

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p44：湖面砖按游泳检定结果计 2/3 格。"""
        if to_key and self._is_lake_tile(engine, to_key):
            return self._swim_cost(engine, player)
        return 0

    def on_item_dropped(self, engine: Any, player: Any, card_id: str) -> None:
        """p44：湖面上丢弃的物品直接沉没。"""
        if not self._is_lake_tile(engine, player.room_key):
            return
        room_cards = engine.state.room_items.get(player.room_key, [])
        if card_id in room_cards:
            room_cards.remove(card_id)
            engine._log("掉落的物品沉入了漆黑的湖水，再也找不回来了。")

    # ------------------------------------------------------------- 游泳与搜索
    def on_turn_start(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        if player.dead:
            return
        # "本回合铺设的砖 +3"只在本回合有效：跨回合先清掉自己的记录。
        fresh = flags.get("fresh_tiles")
        if isinstance(fresh, dict):
            fresh.pop(str(player.id), None)
        if player.role == "traitor":
            self._drown_clock(engine)
            return
        # 叛徒出局后：计时改由轮转顺序里第一位存活玩家代推（惯例，同 22/30 号）。
        # 缺这条时计时随叛徒一起冻结——英雄又常常划不动水（速度 2 < 每砖 3 格），
        # 女孩既不溺亡也救不上岸，对局永远收不了场（seed107/3p 实测 300 回合、
        # 溺水轨道停在 10；本 handler 的 check_victory 注释本就写明"叛徒死后
        # 湖怪照常拖人下水"，这里把时钟补齐）。
        traitor_alive = any(p.role == "traitor" and not p.dead for p in engine.state.players)
        if not traitor_alive:
            first_alive = next(
                (
                    pid
                    for pid in engine.state.turn_order
                    if any(p.id == pid and not p.dead for p in engine.state.players)
                ),
                None,
            )
            if player.id == first_alive:
                self._drown_clock(engine)
                return
        # 英雄在湖面砖上：回合开始自动游泳检定，然后搜索
        if self._is_lake_tile(engine, player.room_key):
            roll = engine._roll_attack(player, "might")
            cost = 2 if roll >= 4 else 3
            flags["swim_cost"][str(player.id)] = cost
            engine._log(f"{player.name} 的游泳检定：{roll}（每砖 {cost} 格）。")
            self._search_roll(engine, player)

    def _drown_clock(self, engine: Any) -> None:
        """p115：推进溺水计时并掷等量骰——到达阈值女孩溺亡（叛徒胜）。"""
        flags = engine._haunt_flags()
        if flags.get("girl_rescued") or flags.get("girl_drowned"):
            return
        current = int(engine._haunt_track_value("drown_timer")) + 1
        engine._set_haunt_track_value("drown_timer", current)
        threshold = int(flags.get("drown_threshold", 10))
        roll = engine.roll_dice(current, "溺水计时")
        engine._log(f"女孩在水下的时间又长了一拍（{current}）：掷出 {roll}（溺亡线 {threshold}+）。")
        if roll >= threshold:
            flags["girl_drowned"] = True
            engine._set_winner("traitor", "湖面重归平静——女孩再也没有浮上来。")
            engine.check_victory()

    def _search_bonus(self, engine: Any, player: Any) -> int:
        flags = engine._haunt_flags()
        bonus = self._lake_distance(engine, player)
        if "omen_crystal_ball" in player.items:
            bonus += self.SEARCH_BONUS_CRYSTAL
        # p44："Add 3 to the result if you are on a lake tile that was placed on
        # your current turn." 本回合刚铺下的砖再 +3（M10-35 补；缺这条会把
        # 救出所需的距离从 6 格外抬到 11 格外）。
        if flags.get("fresh_tiles", {}).get(str(player.id)) == player.room_key:
            bonus += self.SEARCH_BONUS_FRESH_TILE
        return bonus

    def _search_roll(self, engine: Any, player: Any) -> None:
        """p115 搜索表：4 骰 + 距离 + 水晶球；19+ 救出女孩。"""
        flags = engine._haunt_flags()
        if flags.get("girl_rescued") or flags.get("girl_drowned"):
            return
        if player.role == "traitor":
            return  # p115：叛徒入湖不搜索
        static = self._search_bonus(engine, player)
        extra = 0
        for _ in range(8):  # 迭代上限，防止"再掷"链死循环
            roll = engine.roll_dice(4, "搜寻女孩") + static + extra
            engine._log(f"{player.name} 在湖面搜寻（4 骰+加值 {static + extra}）：总点 {roll}。")
            if roll >= 19:
                flags["girl_rescued"] = True
                engine._log("女孩浮了上来——她还活着！英雄们把她救回了岸上！")
                engine.check_victory()
                return
            if roll <= 4:
                engine._log("湖面一片死寂，什么都没有发生。")
                return
            if roll == 5:
                engine._log("远处传来呼救声——方向更加清晰了。")
                self._move_on_lake(engine, player, away=True, steps=1)
                continue
            if roll in (6, 7):
                sub = engine._resolve_check(player, "sanity", 4, "稳住心神")
                if not sub:
                    engine._log(f"盲眼白鱼擦过——{player.name} 受到精神创伤。")
                    engine._deal_damage(player, "mental", 1, source="湖中幻象")
                else:
                    engine._log(f"{player.name} 稳住了心神。")
                return
            if roll == 8:
                engine._log("发现一座小小的湖心岛。")
                engine._draw_event(player)
                return
            if roll == 9:
                engine._log("只有水声。")
                return
            if roll == 10:
                self._creature_duel(engine, player, might=5, on_win_move=1)
                if flags.get("girl_rescued") or player.dead:
                    return
                continue
            if roll == 11:
                extra += 3
                engine._log("水面上似乎有什么在向前挪动……")
                continue
            if roll in (12, 13):
                sub = engine._resolve_check(player, "might", 5, "搏击大浪")
                if sub:
                    engine._log("大浪把探险者推向湖心。")
                    self._move_on_lake(engine, player, away=True, steps=3)
                else:
                    engine._log("大浪把探险者卷回地下湖方向。")
                    self._move_on_lake(engine, player, away=False, steps=2)
                continue
            if roll == 14:
                monster_roll = engine.roll_dice(5, "触手怪")
                hero_roll = engine._roll_attack(player, "speed")
                engine._log(f"带刺的触手卷向 {player.name}：{monster_roll} 对 {hero_roll}。")
                if monster_roll > hero_roll:
                    engine._deal_damage(player, "physical", monster_roll - hero_roll, source="触手怪")
                    self._move_on_lake(engine, player, away=False, steps=2)
                elif monster_roll == hero_roll:
                    engine._log("触手扑了个空。")
                return
            if roll in (15, 16):
                sub = engine._resolve_check(player, "sanity", 4, "忍受漩涡的触感")
                if not sub:
                    engine._deal_damage(player, "mental", 2, source="漩涡")
                    self._move_on_lake(engine, player, away=False, steps=2)
                return
            if roll in (17, 18):
                self._creature_duel(engine, player, might=6, on_win_move=1)
                if flags.get("girl_rescued") or player.dead:
                    return
                continue
            return
        engine._log("湖水吞没了太多尝试——这一轮搜寻暂告一段落。")

    def _move_on_lake(self, engine: Any, player: Any, away: bool, steps: int) -> None:
        """沿湖面砖向远离/靠近地下湖的方向移动 steps 格（远离方向可铺设新砖）。"""
        lake = self._lake_room(engine)
        if not lake:
            return
        for _ in range(steps):
            candidates = self._lake_adjacent_cells(engine, player.room_key)
            best = None
            for direction, floor, x, y in candidates:
                target_pos = (floor, x, y)
                key = engine.state.pos_index.get(target_pos)
                if key is None:
                    if not away:
                        continue  # 靠近方向不铺设新砖
                    score = (1, 0)
                    if best is None or score < best[0]:
                        best = (score, direction, floor, x, y, None)
                    continue
                if not (self._is_lake_tile(engine, key) or key == lake):
                    continue
                dist = engine._path_length(key, lake)
                score = (-dist if away else dist, 1)
                if best is None or score < best[0]:
                    best = (score, direction, floor, x, y, key)
            if best is None:
                return
            _, direction, floor, x, y, key = best
            if key is None:
                room = self._place_lake_tile(engine, floor, x, y, player.room_key)
                if room is None:
                    return
                key = room.key
                engine._haunt_flags().setdefault("fresh_tiles", {})[str(player.id)] = key
            player.room_key = key
            engine._log(f"{player.name} 在湖面{'向外' if away else '向回'}挪动，来到{engine.state.board[key].name}。")
            if key == lake:
                return

    def _creature_duel(self, engine: Any, player: Any, might: int, on_win_move: int) -> None:
        """p115：湖怪攻击（Might 5/6）。探险者胜：不造成伤害、可挪 1 格；
        湖怪胜：正常伤害。"""
        monster_roll = engine.roll_dice(might, "湖怪")
        hero_roll = engine._roll_attack(player, "might")
        engine._log(f"湖怪从水下掀起巨浪扑向 {player.name}：{monster_roll} 对 {hero_roll}。")
        if monster_roll > hero_roll:
            engine._deal_damage(player, "physical", monster_roll - hero_roll, source="湖怪")
        elif monster_roll < hero_roll:
            engine._log(f"{player.name} 击退了湖怪，趁势在湖面挪动。")
            if on_win_move:
                self._move_on_lake(engine, player, away=True, steps=on_win_move)
        else:
            engine._log("僵持不下。")

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        if flags.get("girl_rescued"):
            engine._set_winner("heroes", "女孩在岸边咳出湖水，睁开了眼睛——英雄们赢了。")
            return True
        if flags.get("girl_drowned"):
            return True  # winner 已在溺水处设定
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "湖面恢复了平静——再没有人来打扰湖怪的进食了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p44/p115 只认"救出女孩"，
        # 叛徒死后湖怪照常拖人下水。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
