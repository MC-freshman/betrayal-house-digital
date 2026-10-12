from __future__ import annotations

from ._imports import DIRECTIONS, DIRECTION_DELTAS, OPPOSITE, PlacedRoom, Player, STAT_NAMES, _room_key, _rotate_doors

class BoardRules:
    def _is_collapsed(self, room_key: str) -> bool:
        room = self.state.board.get(room_key)
        return bool(room is not None and room.data.get(self.COLLAPSE_KEY))

    def _collapsed_rooms(self) -> list[PlacedRoom]:
        return [room for room in self.state.board.values() if room.data.get(self.COLLAPSE_KEY)]

    def _grid_neighbors(self, room_key: str) -> list[str]:
        """同楼层正交相邻的房间（不要求有门、不含斜角）。

        p104：深渊沿邻格扩散，"The rooms do not need to have a connecting
        door. Diagonal is not considered adjacent"。
        """
        room = self.state.board.get(room_key)
        if room is None:
            return []
        keys = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            key = self.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
            if key:
                keys.append(key)
        return sorted(keys)

    def _door_neighbors(self, room_key: str) -> list[str]:
        """有门双向连通的相邻房间（逃生跳落点用，p104 "with a connecting door"）。"""
        room = self.state.board.get(room_key)
        if room is None:
            return []
        keys = []
        for direction in room.doors:
            if direction not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[direction]
            target_key = self.state.pos_index.get((room.floor, room.x + dx, room.y + dy))
            if not target_key:
                continue
            target = self.state.board[target_key]
            if OPPOSITE[direction] in target.doors:
                keys.append(target_key)
        return sorted(keys)

    def _room_occupants(self, room_key: str) -> tuple[list, list, list]:
        """房里的人 / 怪物 / 放在地上的令牌（被携带的令牌不算）。"""
        players = [p for p in self.state.players if not p.dead and p.room_key == room_key]
        monsters = [m for m in self.state.monsters if m.room_key == room_key]
        tokens = [t for t in self.state.tokens if t.room_key == room_key and t.holder is None]
        return players, monsters, tokens

    def _room_occupant_counts(self, room_key: str) -> dict[str, int]:
        players, monsters, tokens = self._room_occupants(room_key)
        return {
            "players": len(players),
            "monsters": len(monsters),
            "tokens": len(tokens),
            "items": len(self.state.room_items.get(room_key, [])),
        }

    def _is_room_occupied(self, room_key: str) -> bool:
        """该房是否"占用"。

        **刻意的取舍**：原版 p114 的 "occupied rooms" 通常指有 figure（探险者 /
        怪物）的房间；这里把**地面上的令牌与卡牌也算占用**，避免把放在地上的
        物品连同板块一起移出游戏（那会让剧本道具凭空消失）。已记入 handler 的
        「已知简化」段。
        """
        return any(self._room_occupant_counts(room_key).values())

    def _remap_room_key(self, old_key: str, new_key: str) -> None:
        """板块换 key 之后，把所有指向旧 key 的引用改到新 key。

        覆盖：玩家/怪物位置、地上市令牌、地面卡牌、以及其它板块里存 key 的
        动态链接（如密道）。静态链接存的是模板 id，不受影响。
        """
        for player in self.state.players:
            if player.room_key == old_key:
                player.room_key = new_key
        for monster in self.state.monsters:
            if monster.room_key == old_key:
                monster.room_key = new_key
        for token in self.state.tokens:
            if token.room_key == old_key:
                token.room_key = new_key
        if old_key in self.state.room_items:
            cards = self.state.room_items.pop(old_key)
            self.state.room_items.setdefault(new_key, []).extend(cards)
        for other in self.state.board.values():
            for direction, value in list(other.links.items()):
                if value == old_key:
                    other.links[direction] = new_key

        def replace(value):
            if isinstance(value, str):
                if value == old_key:
                    return new_key
                if value == "__room__" + old_key:
                    return "__room__" + new_key
                return value
            if isinstance(value, dict):
                for key, item in list(value.items()):
                    mapped_key = replace(key)
                    if mapped_key != key:
                        value.pop(key)
                    value[mapped_key] = replace(item)
                return value
            if isinstance(value, list):
                value[:] = [replace(item) for item in value]
                return value
            if isinstance(value, tuple):
                return tuple(replace(item) for item in value)
            return value
        replace(self.state.meta)
        for other in self.state.board.values():
            replace(other.data)

    def _evict_room(self, room_key: str, dest_key: str) -> int:
        """把房里的人、怪物、地上令牌与地面卡牌全挪到 dest_key，返回搬动件数。"""
        players, monsters, tokens = self._room_occupants(room_key)
        for player in players:
            player.room_key = dest_key
        for monster in monsters:
            monster.room_key = dest_key
        for token in tokens:
            token.room_key = dest_key
        cards = self.state.room_items.pop(room_key, [])
        if cards:
            self.state.room_items.setdefault(dest_key, []).extend(cards)
        return len(players) + len(monsters) + len(tokens) + len(cards)

    def _detach_room(self, room_key: str, return_to_deck: bool = False, force: bool = False) -> PlacedRoom | None:
        """把一块板块从场上摘下来（真删除，不是 22 号那种翻面标记）。

        默认**拒绝**摘除仍被占用的房间（force=True 可跳过，由调用方自行保证
        房里的人与物已经处理掉）。`return_to_deck=True` 时把模板 id 塞回房间
        牌堆。返回被摘下的 PlacedRoom，失败返回 None。
        """
        room = self.state.board.get(room_key)
        if room is None:
            return None
        if not force and self._is_room_occupied(room_key):
            return None
        self.state.board.pop(room_key, None)
        self.state.pos_index.pop((room.floor, room.x, room.y), None)
        # 残留物记在返回值上，绝不静默蒸发（正常调用前应已清空）
        room.data["detached_items"] = self.state.room_items.pop(room_key, [])
        room.data["detached_tokens"] = [
            t.uid for t in self.state.tokens if t.room_key == room_key and t.holder is None
        ]
        if return_to_deck:
            self.state.room_deck.insert(0, room.template_id)
        # 指向这块牌的动态链接（存 key 的）随之作废，否则会解析到不存在的 key
        for other in self.state.board.values():
            for direction, value in list(other.links.items()):
                if value == room_key:
                    other.links.pop(direction, None)
        return room

    def _set_room_orientation(self, room_key: str, rotation: int) -> bool:
        """按 rotation 重设板块的门与链接朝向（保留 handler 动态写入的链接）。"""
        room = self.state.board.get(room_key)
        if room is None:
            return False
        template = self.catalog.room_templates.get(room.template_id)
        if template is None:
            return False
        rotated = self._build_rotated_template(template, rotation)
        dynamic = {k: v for k, v in room.links.items() if k not in DIRECTIONS}
        room.rotation = rotation
        room.doors = rotated.doors
        room.links = {**rotated.links, **dynamic}
        return True

    def _relocate_room(self, room_key: str, x: int, y: int, floor: int | None = None) -> str | None:
        """把一块板块搬到同层的 (x, y)，返回新 key（失败/位置被占返回 None）。

        板块上的人、怪物、令牌与地面卡牌随板块一起移动（key 变了，必须同步）。
        """
        room = self.state.board.get(room_key)
        if room is None:
            return None
        target_floor = room.floor if floor is None else floor
        new_key = _room_key(target_floor, x, y)
        occupant = self.state.pos_index.get((target_floor, x, y))
        if occupant is not None and occupant != room_key:
            return None
        self.state.pos_index.pop((room.floor, room.x, room.y), None)
        if new_key != room_key:
            self.state.board.pop(room_key, None)
        room.key = new_key
        room.floor = target_floor
        room.x = x
        room.y = y
        self.state.board[new_key] = room
        self.state.pos_index[(room.floor, x, y)] = new_key
        if new_key != room_key:
            self._remap_room_key(room_key, new_key)
        return new_key

    def _rotation_facing(self, template_id: str, want_direction: str) -> int | None:
        """返回让该模板有一扇门朝 want_direction 的 rotation（做不到返回 None）。

        本仓库所有房间都有 2–3 扇门，任意房间都能转到任意朝向。
        """
        template = self.catalog.room_templates.get(template_id)
        if template is None or not template.doors:
            return None
        for rotation in range(4):
            if want_direction in _rotate_doors(template.doors, rotation):
                return rotation
        return None

    def _free_slots_around(self, anchor_key: str) -> list[tuple[str, tuple[int, int]]]:
        """锚点房间每个门方向上的相邻空位：(门朝向, (x, y))，按方向排序。"""
        anchor = self.state.board.get(anchor_key)
        if anchor is None:
            return []
        slots: list[tuple[str, tuple[int, int]]] = []
        for direction in sorted(anchor.doors):
            if direction not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[direction]
            pos = (anchor.x + dx, anchor.y + dy)
            if (anchor.floor, pos[0], pos[1]) in self.state.pos_index:
                continue
            slots.append((direction, pos))
        return slots

    def _place_room_adjacent(
        self, room_key: str, anchor_key: str, require_connection: bool = False
    ) -> str | None:
        """把已在场的一块板块挪到锚点旁边，优先摆成门对门连通（p114）。

        `require_connection=True` 时只在能门对门接上时才搬（找不到就返回 None，
        留给调用方换一个锚点再试）；默认在无门对门空位时退回第一个空位。
        """
        room = self.state.board.get(room_key)
        anchor = self.state.board.get(anchor_key)
        if room is None or anchor is None or room is anchor:
            return None
        if room.floor != anchor.floor:
            return None
        slots = self._free_slots_around(anchor_key)
        for direction, pos in slots:
            rotation = self._rotation_facing(room.template_id, OPPOSITE[direction])
            if rotation is None:
                continue
            new_key = self._relocate_room(room_key, pos[0], pos[1])
            if new_key is None:
                continue
            self._set_room_orientation(new_key, rotation)
            return new_key
        if require_connection:
            return None
        for _direction, pos in slots:
            new_key = self._relocate_room(room_key, pos[0], pos[1])
            if new_key is not None:
                return new_key
        return None

    def _attach_template_adjacent(self, template_id: str, anchor_key: str) -> str | None:
        """把牌堆里的某个模板取出，直接接到锚点旁边（优先摆成门对门）。

        与 `_ensure_room_in_play` 的区别：那个走完整的探索放置校验（含
        "不封死探索边界"），在场面被大改之后可能挑不到合法位；这里只要求
        "锚点有一个空的门口"并且能转出对应朝向，用于 32 号"把管风琴房接到
        起始牌上"这类原版明文指定的落位。放不下时不动牌堆、返回 None。
        """
        anchor = self.state.board.get(anchor_key)
        template = self.catalog.room_templates.get(template_id)
        if anchor is None or template is None or template.floor != anchor.floor:
            return None
        if template_id not in self.state.room_deck and template_id not in self.state.room_discard:
            return None
        slots = self._free_slots_around(anchor_key)
        if not slots:
            return None
        chosen: tuple[tuple[int, int], int] | None = None
        for direction, pos in slots:
            rotation = self._rotation_facing(template_id, OPPOSITE[direction])
            if rotation is not None:
                chosen = (pos, rotation)
                break
        if chosen is None:
            chosen = (slots[0][1], 0)  # 没有门对门的空位：退回第一个空位
        pos, rotation = chosen
        for deck in (self.state.room_deck, self.state.room_discard):
            if template_id in deck:
                deck.remove(template_id)
                break
        rotated = self._build_rotated_template(template, rotation)
        return self._place_room(rotated, pos[0], pos[1], rotation).key

    def _shuffle_room_piles(self, extra_templates: tuple[str, ...] = ()) -> None:
        """把指定模板收回牌堆，与弃牌堆、未抽房间一起洗匀（32 号 p114）。"""
        deck = self.state.room_deck
        for template_id in extra_templates:
            deck.insert(0, template_id)
        deck.extend(self.state.room_discard)
        self.state.room_discard = []
        self.rng.shuffle(deck)

    def _rearrange_floor(self, floor: int) -> int:
        """把该层的板块重摆成一个**连通**的新布局（68 号 p150）。

        贪心生成：取该层的一张起始牌作锚点（原位不动——楼梯锚点），随后反复从
        "已放板块的门位"里挑一个空位、把下一块转向去匹配。本仓库所有房间都有
        2–3 扇门，任意房间都能转到需要的朝向，所以只要还有未放的板块就一定能
        接上——**连通性由构造保证**，不需要回溯搜索。

        返回被搬动的板块数（位置未变的计 0）。
        """
        keys = [k for k in sorted(self.state.board) if self.state.board[k].floor == floor]
        # 塌进深渊的板块（22/38/68 号用的翻面标记）已被 `_build_graph` 排除在外：
        # 既有重排时必须把它们留在原位并占住格子，否则新布局会覆盖到它们身上。
        collapsed = [
            self.state.board[k] for k in keys if self.state.board[k].data.get(self.COLLAPSE_KEY)
        ]
        rooms = [
            self.state.board[k] for k in keys if not self.state.board[k].data.get(self.COLLAPSE_KEY)
        ]
        if len(rooms) <= 1:
            return 0
        # 1) 参与重排的板块先从网格上摘除，原坐标随之释放（board 暂不动）
        for room in rooms:
            self.state.pos_index.pop((room.floor, room.x, room.y), None)

        anchor = next((r for r in rooms if r.template_id in self.START_ROOM_IDS), rooms[0])
        plan: dict[str, tuple[int, int]] = {anchor.key: (anchor.x, anchor.y)}
        taken = {(r.x, r.y) for r in collapsed} | {(anchor.x, anchor.y)}
        frontier: dict[tuple[int, int], str] = {}

        def expand(room: PlacedRoom, x: int, y: int) -> None:
            for direction in sorted(room.doors):
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                slot = (x + dx, y + dy)
                if slot in taken or slot in frontier:
                    continue
                frontier[slot] = direction  # 新房间需要一扇朝 OPPOSITE[direction] 的门

        expand(anchor, anchor.x, anchor.y)
        pending = [r for r in rooms if r is not anchor]
        while pending:
            placed = False
            for slot in sorted(frontier):
                want = OPPOSITE[frontier[slot]]
                for index, room in enumerate(pending):
                    rotation = self._rotation_facing(room.template_id, want)
                    if rotation is None:
                        continue
                    plan[room.key] = slot
                    taken.add(slot)
                    frontier.pop(slot)
                    self._set_room_orientation(room.key, rotation)
                    expand(room, slot[0], slot[1])
                    pending.pop(index)
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                # 构造上到不了这里（房房有门）。保底：塞到第一个人工空位，
                # 保证循环一定收敛，不静默死循环。
                room = pending.pop(0)
                cursor = 0
                while (anchor.x + cursor, anchor.y) in taken:
                    cursor += 1
                slot = (anchor.x + cursor, anchor.y)
                plan[room.key] = slot
                taken.add(slot)
                expand(room, slot[0], slot[1])

        # 2) 记录旧 key → 新坐标，再统一重挂并重映射引用
        positions = {room.key: plan[room.key] for room in rooms}
        moved = sum(
            1 for room in rooms if (room.x, room.y) != positions[room.key]
        )
        mapping = {
            room.key: _room_key(floor, positions[room.key][0], positions[room.key][1])
            for room in rooms
        }
        for room in rooms:
            self.state.board.pop(room.key, None)
        for room in rooms:
            old_key = room.key
            new_key = mapping[old_key]
            x, y = positions[old_key]
            room.key = new_key
            room.x = x
            room.y = y
            self.state.board[new_key] = room
            self.state.pos_index[(floor, x, y)] = new_key
        for old_key, new_key in mapping.items():
            if old_key != new_key:
                self._remap_room_key(old_key, new_key)
        return moved

    def _collapse_room(self, room_key: str, cause: str = "深渊", consumes_monsters: bool = True) -> bool:
        """翻掉一块房间牌（牌面朝下 = 塌进深渊），并结算房里的人与怪物。

        `consumes_monsters=False` 供"幽灵能穿过坍塌房间"这类剧本自行保留怪物。
        """
        room = self.state.board.get(room_key)
        if room is None or room.data.get(self.COLLAPSE_KEY):
            return False
        room.data[self.COLLAPSE_KEY] = True
        room.revealed = False  # 牌翻回背面：与实体桌游"把板块翻过来"一致
        self._log(f"{room.name} 塌进了{cause}。")
        for player in [p for p in self.state.players if not p.dead and p.room_key == room_key]:
            self._escape_abyss(player, room)
        if consumes_monsters:
            for monster in [m for m in self.state.monsters if m.room_key == room_key]:
                self._kill_monster(monster)
                self._log(f"{monster.name} 随地板一起坠了下去。")
        self.check_victory()
        return True

    def _escape_abyss(self, player: Player, room: PlacedRoom) -> None:
        """p104：被吞房间里的探险者做速度 4+；成功则跳进相邻、有门连通、
        已发现且没塌的房间，失败或无处可跳即坠入深渊死亡。"""
        escaped_key = ""
        if self._resolve_check(player, "speed", 4, "逃离深渊"):
            escaped_key = next(
                (
                    key for key in self._door_neighbors(room.key)
                    if key != room.key and not self._is_collapsed(key) and self.state.board[key].revealed
                ),
                "",
            )
        if escaped_key:
            self._move_to_room(player, escaped_key, via_effect=True)
            self._log(f"{self._player_label(player)} 在地板塌掉的瞬间跳进了 {self.state.board[escaped_key].name}。")
            return
        self._log(f"{self._player_label(player)} 随着塌落的地板坠入了深渊。")
        for stat in STAT_NAMES:
            player.stats[stat] = 0
        self._check_player_death(player)

    def _abyss_candidates(self, origin_keys: set[str], floor: int) -> list[str]:
        """指定楼层里"与深渊邻接、还没塌、已放上桌"的房间（按坐标定序，保证种子可复现）。"""
        candidates = []
        for key in self._all_room_keys():
            if self._is_collapsed(key):
                continue
            room = self.state.board[key]
            if room.floor != floor:
                continue
            if not any(key in self._grid_neighbors(origin) for origin in origin_keys):
                continue
            candidates.append(key)
        return sorted(candidates, key=lambda key: (self.state.board[key].y, self.state.board[key].x))

    def _all_room_keys(self) -> list[str]:
        return sorted(self.state.board)

    def _room_has_open_door(self, room_key: str) -> bool:
        """该房间是否还留着未探索的门口（相邻格尚未放板块）。"""
        room = self.state.board.get(room_key)
        if room is None:
            return False
        for direction in room.doors:
            if direction not in DIRECTION_DELTAS:
                continue
            dx, dy = DIRECTION_DELTAS[direction]
            if self.state.pos_index.get((room.floor, room.x + dx, room.y + dy)) is None:
                return True
        return False

    def _collapse_adjacent_rooms(self, count: int, cause: str = "深渊") -> int:
        """按 p104 的扩散规则翻掉 count 间房，返回实际翻掉数。

        规则（p104 "Each Player Must Do This Every Turn"）：
        ① 深渊只在它**已占据的楼层**上扩散，且只能吃与已有深渊正交相邻的房间
          （不要求有门、不算斜角）——`_abyss_candidates` 是这条的权威判据；
        ② 「If the Abyss engulfs a whole floor, it moves to the next floor up,
          starting in an unoccupied room of your choosing with an unexplored
          door」——某层**整层塌完**才升到上一层，从"无人且留着未探索门口"的
          房间播种；播种之后回到 ① 按同层邻格继续扩散（"无人 + 有空门"只是
          升层那一刻的选点条件，不是之后每一步的扩散条件）。

        旧实现的坑（M10-71 修掉）：基准层取 `min(origin floors)`，地下室一旦
        塌完该值恒为最小层，`candidate_floor > floor` 恒成立 —— 于是 ① 跨层
        播种格永远选不出（升层分支成了死代码，深渊永久困在地下室），② 上层
        的**每一次**扩散都被错加上播种过滤。实测剧本 22 seed197/5p：深渊吃完
        地下室 9 间即停摆，够不到二楼英雄，而英雄又刚好无来源可拿 → 300 回合
        无胜者。
        """
        collapsed = 0
        while collapsed < count:
            origins = {room.key for room in self._collapsed_rooms()}
            if not origins:
                break
            occupied = sorted({self.state.board[key].floor for key in origins})
            picked = ""
            # ① 在深渊已占据的楼层上找邻格（自低向高，保证种子可复现）
            for floor in occupied:
                options = self._abyss_candidates(origins, floor)
                if options:
                    picked = options[0]
                    break
            # ② 本层扩散不动：若某层已整层塌完，升到上一层播种
            if not picked:
                engulfed = [
                    floor for floor in occupied
                    if not any(
                        room.floor == floor and not self._is_collapsed(key)
                        for key, room in self.state.board.items()
                    )
                ]
                for floor in sorted(engulfed, reverse=True):
                    upper = floor + 1
                    if upper > 1:
                        continue
                    options = [
                        key for key in self._all_room_keys()
                        if not self._is_collapsed(key)
                        and self.state.board[key].floor == upper
                        and not any(p.room_key == key and not p.dead for p in self.state.players)
                        and self._room_has_open_door(key)
                    ]
                    options.sort(key=lambda key: (
                        self.state.board[key].y, self.state.board[key].x))
                    if options:
                        picked = options[0]
                        break
            if not picked:
                break
            if self._collapse_room(picked, cause=cause):
                collapsed += 1
        return collapsed
