from __future__ import annotations

from ._imports import Any, Monster, OPPOSITE, PlacedRoom, Player, _distance_hint

class RoomEffects:
    def _resolve_room_entry_if_needed(self, player: Player) -> None:
        room = self.current_room(player)
        room.visit_count += 1
        first_entry = not room.revealed
        if first_entry:
            room.revealed = True
            # 先弹进入房间的详细说明（符号/效果/描述），再抽卡
            self._notify_room_entry(player, room)
            self._mode_handler().on_room_discovered(self, player, room)
            # 剧本可禁止本次的符号抽牌（剧本 16 p27：发现带符号的地下室
            # 房间时"代替抽牌"必须先攻击幻影）。
            suppress_draw = self._mode_handler().suppress_room_draw(self, player, room)
            if room.data.get("no_first_draw"):
                # p10：非探索方式放入的房间（作祟指令等）首个进入者不抽符号牌。
                suppress_draw = True
            if room.symbol and not suppress_draw:
                if room.symbol == "event" and self.state.phase == "HAUNT_PHASE" and player.role == "traitor":
                    if self.prompter.confirm("事件卡", f"{player.name} 进入了带事件符号的房间。要触发事件吗？"):
                        self._draw_symbol_card(player, room.symbol)
                    else:
                        self._log(f"{player.name} 选择不触发这张事件卡。")
                else:
                    self._draw_symbol_card(player, room.symbol)
        self._collect_room_companions(player, room)
        # 无主的"携带型"令牌（花/喷雾/火把/蜡烛…）进房自动拾起。这类剧本关键
        # 令牌只由剧本行动产生，掉在地上过去没有任何拾取途径——18 号
        # seed31-6p 实测：花随阵亡英雄落地，剩下的人围着毒藤站到 400 回合也
        # 削弱不了（0 次），整局收不了场；7 号喷雾、17 号杀虫剂同理。令牌的
        # role 为 "marker"（尸体/护甲/女孩）不在此列，那些由各剧本自己的
        # 行动与 on_enter_room 钩子接管。
        if not player.dead:
            # 倒下的棋子会被房间效果/传送带着走，别再让它捡东西（18 号
            # seed31-6p：阵亡英雄被传送时把刚掉落的花又捡了回去）。
            for token in self.tokens_in_room(room.key):
                if token.role == "carried" and token.holder is None:
                    self.give_token(token.uid, player.id)
                    self._log(f"{player.name} 拾起了{token.label}。")
        # 令牌拾取之类要在房间效果之后，避免顺序上出现歧义
        self._mode_handler().on_enter_room(self, player, room)
        self._apply_room_effect(player, room, first_entry=first_entry)
        self.check_victory()

    def _room_effect_desc(self, effect: str) -> str:
        """返回房间特殊效果的一句话说明，供进房提示/悬停使用。"""
        return {
            "room_chapel": "每次进入：恢复 1 点理智。",
            "room_graveyard": "（无特殊效果）",
            "room_gymnasium": "每次进入：速度步数 +1。",
            "room_library": "每次进入：下一次检定重掷机会 +1。",
            "room_larder": "每次进入：恢复 1 点力量。",
            "room_research_laboratory": "进入时：知识检定（目标 4）通过则抽 1 张物品卡。",
            "room_bloody_room": "每次进入：受到 1 点物理伤害。",
            "room_bedroom": "每次进入：恢复 1 点理智。",
            "room_master_bedroom": "每次进入：恢复 1 点理智。",
            "room_charred_room": "每次进入：受到 1 点精神伤害。",
            "room_furnace_room": "每次进入：受到 1 点物理伤害。",
            "room_coal_chute": "进入时：被送到地下室大厅并结束移动。",
            "room_mystic_elevator": "进入时：掷骰前往随机楼层（叛徒可自选）。",
            "room_vault": "每回合可尝试一次知识 6+；成功取 2 件物品并放置空保险库标记。",
            "room_chasm": "进入时：速度检定（目标 4）失败受 1 点物理伤害并停下。",
            "room_collapsed_room": "首次发现速度 5+；失败落入地下室并受一枚骰子的物理伤害。后来者可选择利用。",
            "room_tower": "进入时：速度检定（目标 4）失败受 1 点物理伤害。",
            "room_pentagram_chamber": "（无特殊效果）",
            "room_attic": "特殊房间：部分剧本中的失败检定可留在这里下回合重试。",
            "room_bathroom": "无基础常规特效；首次发现时照房间符号抽事件牌。",
            "room_game_room": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_inner_hall": "无基础常规特效。",
            "room_creaky_hallway": "无基础常规特效；部分剧本会把它作为关键房间。",
            "room_dusty_hallway": "无基础常规特效。",
            "room_statuary_corridor": "无基础常规特效；部分剧本会把它作为关键房间。",
            "room_crawlspace": "无基础常规特效。",
            "room_storeroom": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_underground_lake": "若在上层发现，房间塌落到地下室并结束移动。",
            "room_wine_cellar": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_balcony": "无基础常规特效；首次发现时照房间符号抽事件牌。",
            "room_kitchen": "无基础常规特效；首次发现时照房间符号抽物品牌。",
            "room_organ_room": "无基础常规特效；首次发现时照房间符号抽预兆牌。",
            "room_crypt": "无基础常规特效；首次发现时照房间符号抽预兆牌。怪物无视本房间特殊规则。",
            "room_catacombs": "障碍房间：进入时速度检定（目标 4）失败受 1 点物理伤害并停下；怪物无视障碍。",
        }.get(effect, "")

    def _notify_room_entry(self, player: Player, room: PlacedRoom) -> None:
        """首次进入新房间时弹出详细说明。"""
        parts = []
        if room.symbol:
            sym = {"omen": "预兆", "item": "物品", "event": "事件"}.get(room.symbol, room.symbol)
            parts.append(f"房间符号：进入触发{sym}卡")
        desc = self._room_effect_desc(room.effect_id)
        if desc:
            parts.append(f"效果：{desc}")
        if room.text:
            parts.append(f"描述：{room.text}")
        if parts:
            self.prompter.notify(f"进入房间：{room.name}", "\n".join(parts))

    def _draw_symbol_card(self, player: Player, symbol: str, stop_movement: bool = True) -> None:
        """抽一张符号牌。stop_movement=False 用于剧本 25 p36 的延迟抽牌：
        正常的符号抽牌发生在"进房必须停"之后；但延迟抽牌（结束移动时补抽、
        搜寻前补抽）不该打断玩家本回合的移动。"""
        kind_map = {"omen": "omen", "item": "item", "event": "event"}
        kind = kind_map.get(symbol)
        if kind is None:
            return
        if player.frog:
            self._log("青蛙不能抽牌。")
            return
        if kind == "omen":
            self._draw_omen(player, stop_movement=stop_movement)
        elif kind == "item":
            self._draw_item(player, stop_movement=stop_movement)
        elif kind == "event":
            self._draw_event(player, stop_movement=stop_movement)
        if stop_movement:
            player.movement_stopped = True
            player.steps_remaining = 0

    def _stop_movement_for_draw(self, player: Player, stop_movement: bool = True) -> None:
        """规则手册 p6/p10：任何"抽牌"效果都会让该玩家本回合停止移动（仍可做其他动作）。

        唯一例外是剧本明文的延迟抽牌（剧本 25 p36：结束移动时补抽），
        由调用方传 stop_movement=False。
        """
        if stop_movement:
            player.movement_stopped = True
            player.steps_remaining = 0

    def _search_deck_for_required_card(self, kind: str) -> str | None:
        """剧本关键牌还在牌堆里时，允许"直接搜牌堆取走它"代替正常抽牌。

        p15（剧本 4 医疗包）："若「医疗包」卡尚未被发现，任何有机会抽物品卡的
        英雄都可以在牌堆中搜寻并直接取走医疗包，以代替正常抽牌。"
        p12（剧本 1 古书）对预兆牌有同样的写法（1 号已在自己的 handler 里实现）。

        rule_data 用 `searchable_cards` 显式声明哪些牌可以这样取——只有声明过的
        才生效，其它剧本的 required_cards 行为完全不变。已被别人拿走、或已流落
        在房间里的牌不在牌堆中，自然搜不到，按正常规则继续抽。

        取走时必须**从牌堆移除**：只报告不删除的话，同一张关键牌还能被再抽到
        一次，等于凭空复制（回归测试 verify_searchable_required_cards 抓到过）。
        """
        haunt = self.state.haunt
        if haunt is None:
            return None
        declared = [str(card_id) for card_id in (haunt.rule_data or {}).get("searchable_cards", [])]
        deck = self.state.card_decks.get(kind, [])
        for card_id in declared:
            card = self.catalog.cards.get(card_id)
            if card is None or card.kind != kind:
                continue
            if card_id in deck:
                deck.remove(card_id)
                return card_id
        return None

    def _draw_omen(self, player: Player, stop_movement: bool = True) -> None:
        self._stop_movement_for_draw(player, stop_movement)
        searched = self._search_deck_for_required_card("omen")
        card_id = searched or self._draw_card_id("omen")
        if not card_id:
            # 13 张预兆全在场上：作祟检定的"最后一次"规则（_has_future_omen_source）
            # 保证游戏已经或即将进入作祟，这里只需如实记录。
            self._log("预兆牌已经全部出现过了，抽不到新的预兆。")
            return
        card = self.catalog.cards[card_id]
        player.items.append(card_id)
        if card_id not in player.companions and "companion" in card.tags:
            player.companions.append(card_id)
        self.state.omens_drawn += 1
        self.state.last_omen_id = card_id
        self.state.haunt_pending = True
        if searched:
            self._log(f"{player.name} 在预兆牌堆里搜出了{card.name}（剧本关键牌）。")
        else:
            self._log(f"{player.name} 抽到预兆：{card.name}。")
        self.prompter.notify(f"抽到预兆：{card.name}", card.text or "（无说明）")
        self._resolve_omen_effect(player, card)

    def _draw_item(self, player: Player, stop_movement: bool = True) -> None:
        self._stop_movement_for_draw(player, stop_movement)
        searched = self._search_deck_for_required_card("item")
        card_id = searched or self._draw_card_id("item")
        choice_count = getattr(self._mode_handler(), "item_draw_choices", lambda e, p: 1)(self, player)
        if card_id and choice_count > 1 and not searched:
            candidates = [card_id]
            for _ in range(choice_count - 1):
                extra = self._draw_card_id("item")
                if extra:
                    candidates.append(extra)
            if player.control == "bot":
                preference = getattr(self._mode_handler(), "bot_item_draw_score", lambda e, p, c: 0)
                card_id = max(candidates, key=lambda cid: preference(self, player, cid))
            else:
                index = self.prompter.choose_from_list("选择物品", "选择一件，其余放回牌堆底。",
                                                      [self.catalog.cards[c].name for c in candidates])
                card_id = candidates[index if index is not None and 0 <= index < len(candidates) else 0]
            self.state.card_decks["item"].extend(c for c in candidates if c != card_id)
        if not card_id:
            self._log("物品牌已经全部散落在房子里，没有新的物品可抽。")
            return
        card = self.catalog.cards[card_id]
        player.items.append(card_id)
        if searched:
            self._log(f"{player.name} 在物品牌堆里搜出了{card.name}（剧本关键牌）。")
        else:
            self._log(f"{player.name} 抽到物品：{card.name}。")
        self.prompter.notify(f"获得物品：{card.name}", card.text or "（无说明）")

    def _draw_event(self, player: Player, stop_movement: bool = True) -> None:
        self._stop_movement_for_draw(player, stop_movement)
        card_id = self._draw_card_id("event")
        if not card_id:
            self._log("事件牌堆已经空了，这次没有事件发生。")
            return
        card = self.catalog.cards[card_id]
        self._log(f"{player.name} 抽到事件：{card.name}。")
        self.prompter.notify(f"触发事件：{card.name}", card.text or "（无说明）")
        self._resolve_event(player, card)
        self.state.card_discards["event"].append(card_id)

    def _collect_room_companions(self, player: Player, room: PlacedRoom) -> None:
        room_cards = self.state.room_items.get(room.key)
        if not room_cards:
            return
        for card_id in list(room_cards):
            card = self.catalog.cards.get(card_id)
            if not card or "companion" not in card.tags:
                continue
            room_cards.remove(card_id)
            player.items.append(card_id)
            if card_id not in player.companions:
                player.companions.append(card_id)
            self._log(f"{player.name} 接手了 {card.name}。")
        if not room_cards:
            self.state.room_items.pop(room.key, None)

    def room_stop_risk(self, room: Any) -> bool:
        """进入该房间是否**可能**立刻终止本回合剩余移动（纯查询，无副作用）。

        保守判定：只要效果里存在"抽牌/传送/坠落/障碍失败停下"的分支就算，
        不看检定结果（机器人没法预知掷骰）。
        """
        effect = getattr(room, "effect_id", "") or ""
        return effect in self.STOP_RISK_EFFECTS

    def _apply_room_effect(self, player: Player, room: PlacedRoom, first_entry: bool) -> None:
        effect = room.effect_id
        if effect == "none":
            return
        # 起始 / 楼梯房间：它们的规则就是楼梯连接本身（links 已实现），
        # 没有可结算的房间文字。过去只认 hall/foyer/stairs 三个，另外三间
        # 落到兜底分支报"[规则缺口]…尚未实现"，玩家（实测反馈）会以为坏了。
        if effect in {
            "room_start_hall", "room_start_foyer", "room_start_stairs",
            "room_start_above", "room_start_below", "room_stairs_from_basement",
        }:
            return
        if self.state.phase == "HAUNT_PHASE" and player.role == "traitor" and effect in {"room_bloody_room", "room_charred_room", "room_furnace_room"}:
            self._log("叛徒无视了这个房间的负面效果。")
            return
        if effect == "room_chapel":
            self._log("小教堂让人稍微平静下来。")
            self._heal_stat(player, "sanity", 1)
            return
        if effect == "room_graveyard":
            self._log("墓地的气氛让人不安。")
            return
        if effect == "room_gymnasium":
            self._log("健身房的空间让你更容易活动。")
            player.steps_remaining += 1
            return
        if effect == "room_library":
            self._log("图书馆里也许能找到灵感。")
            player.extra_check_rerolls += 1
            return
        if effect == "room_larder":
            self._log("储藏室里有一点补给。")
            self._heal_stat(player, "might", 1)
            return
        if effect == "room_research_laboratory":
            self._log("研究实验室的器材看上去还能用。")
            if self._resolve_check(player, "knowledge", 4, "研究实验室检定"):
                self._draw_item(player)
            return
        if effect == "room_bloody_room":
            self._log("血房间里的痕迹让人心里发紧。")
            self._deal_damage(player, "physical", 1, source="血房间")
            return
        if effect == "room_bedroom":
            self._log("卧室让人稍微放松了一点。")
            self._heal_stat(player, "sanity", 1)
            return
        if effect == "room_master_bedroom":
            self._log("主卧的安静有一点诡异。")
            self._heal_stat(player, "sanity", 1)
            return
        if effect == "room_charred_room":
            self._log("烧焦的房间残留着热与灰。")
            self._deal_damage(player, "mental", 1, source="烧焦的房间")
            return
        if effect == "room_furnace_room":
            self._log("熔炉房的余热让人难受。")
            self._deal_damage(player, "physical", 1, source="熔炉房")
            return
        if effect == "room_coal_chute":
            self._log("煤导槽把你往地下室入口送。")
            self._move_to_room(player, "basement_landing", via_effect=True)
            player.movement_stopped = True
            player.steps_remaining = 0
            return
        if effect == "room_mystic_elevator":
            self._apply_mystic_elevator(player, room)
            return
        if effect == "room_vault":
            if not room.data.get("opened"):
                self._apply_vault(player, room)
            return
        if effect == "room_chasm":
            self._apply_chasm(player, room)
            return
        if effect == "room_collapsed_room":
            self._apply_collapsed_room(player, room)
            return
        if effect == "room_tower":
            self._apply_tower(player, room)
            return
        if effect == "room_pentagram_chamber":
            self._log("五芒星室里的符号仍然令人不适。")
            return
        if effect == "room_abandoned_room" or effect == "room_ballroom" or effect == "room_garden" or effect == "room_junk_room" or effect == "room_patio" or effect == "room_conservatory" or effect == "room_dining_room" or effect == "room_gallery" or effect == "room_operating_laboratory" or effect == "room_servants_quarters":
            return
        if effect == "room_underground_lake":
            if room.floor == 1 and not room.data.get("collapsed"):
                room.data["collapsed"] = True
                self._log("地下湖所在的上层地板塌陷，房间落入地下室。")
                room.floor = -1
                player.movement_stopped = True
                player.steps_remaining = 0
            return
        if effect in {
            "room_attic", "room_bathroom", "room_game_room", "room_inner_hall",
            "room_creaky_hallway", "room_dusty_hallway", "room_statuary_corridor",
            "room_crawlspace", "room_storeroom", "room_wine_cellar",
        }:
            self._log(f"{room.name} 没有基础常规特效。")
            return
        # 阳台 / 厨房 / 风琴房：权威规则书（BetrayalHouseHill_v4.2.pdf p2「Special Rooms」）
        # 没有列出这三间，说明它们没有文字效果，只有牌面符号（事件/物品/预兆）。
        # 首次发现的抽牌由上面 _resolve_room_entry_if_needed 的符号分支处理，
        # 这里必须显式 return，避免落到函数末尾变成静默穿透。
        if effect in {"room_balcony", "room_kitchen", "room_organ_room"}:
            return
        # 地窖：与熔炉房同列（p2「Crypt, Furnace Room」）——怪物无视本房间的特殊规则。
        # 本房间本身没有文字效果，只有预兆符号；且怪物不走 _apply_room_effect 通道，
        # 因此"怪物无视"在此自动成立，无需额外处理。
        if effect == "room_crypt":
            return
        # 地下墓穴：障碍房间（p2「Vault, Tower, Chasm, Catacombs」）
        if effect == "room_catacombs":
            self._apply_catacombs(player, room)
            return
        # 兜底：未识别的房间效果不再静默吞掉，记进日志便于排查。
        self._log(f"[规则缺口] {room.name} 的房间效果 {effect} 尚未实现，已跳过。")

    def _apply_mystic_elevator(self, player: Player, room: PlacedRoom) -> None:
        if self._mode_handler().mystic_elevator_blocked(self, player):
            self._log("神秘电梯被剧本机制堵住。")
            return
        attempts = self.state.meta.setdefault("room_attempts", {}).setdefault(str(player.id), [])
        if "elevator" in attempts:
            return
        controlled = isinstance(player, Monster) or getattr(player, "role", "") == "traitor"
        if controlled and self.state.meta.get("elevator_group_turn") == self.state.turn_count:
            return
        attempts.append("elevator")
        crew = [p for p in self.state.players if p.room_key == room.key and not p.dead]
        if controlled:
            self.state.meta["elevator_group_turn"] = self.state.turn_count
            roll = 4
        else:
            roll = self.roll_dice(2, "神秘电梯")
        if roll == 4:
            choice = self.prompter.choose_from_list("神秘电梯", "选择目标楼层。", ["地下室", "一层", "二层"])
            if choice is None:
                return
            floor = (-1, 0, 1)[choice]
        else:
            floor = {0: -1, 1: -1, 2: 0, 3: 1}.get(roll, room.floor)
        if roll == 0:
            for explorer in crew:
                self.deal_dice_damage(explorer, "physical", 1, source="神秘电梯")
        slots = []
        for key, anchor in sorted(self.state.board.items()):
            if key == room.key or anchor.floor != floor or self._is_collapsed(key):
                continue
            for direction, (x, y) in self._free_slots_around(key):
                rotation = self._rotation_facing(room.template_id, OPPOSITE[direction])
                if rotation is not None:
                    slots.append((anchor.name, x, y, rotation))
        if not slots:
            self._log("神秘电梯没有找到可连接的门，留在原处。")
            return
        choice = self.prompter.choose_from_list("神秘电梯", "选择电梯连接的位置。",
                                               [f"{name}旁 ({x},{y})" for name, x, y, _ in slots])
        if choice is None:
            return
        _name, x, y, rotation = slots[choice]
        new_key = self._relocate_room(room.key, x, y, floor=floor)
        if new_key:
            self._set_room_orientation(new_key, rotation)
            for explorer in crew:
                self._mode_handler().on_player_moved(self, explorer)
            self._log(f"神秘电梯连接到{_distance_hint(floor)}的新门，乘客随板块一起移动。")

    def _choose_elevator_target(self, floor: int, current_key: str) -> str | None:
        candidates = [
            key
            for key, room in self.state.board.items()
            if room.floor == floor and key != current_key
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        return self.rng.choice(candidates)

    def _apply_vault(self, player: Player, room: PlacedRoom) -> None:
        attempts = self.state.meta.setdefault("room_attempts", {}).setdefault(str(player.id), [])
        attempt = "vault:" + room.key
        if attempt in attempts or room.data.get("opened"):
            return
        attempts.append(attempt)
        self._log("保险库仍然锁着。")
        if self._resolve_check(player, "knowledge", 6, "保险库检定"):
            room.data["opened"] = True
            self.spawn_token("empty_vault", label="空保险库", role="marker", room_key=room.key)
            self._log("保险库打开了。")
            self._draw_item(player)
            self._draw_item(player)
        else:
            self._log("保险库检定失败，大门仍然锁着。")

    def _apply_chasm(self, player: Player, room: PlacedRoom) -> None:
        if self._barrier_config(room):
            return
        self._log("深渊需要小心跨过。")
        if not self._resolve_check(player, "speed", 4, "深渊检定"):
            self._deal_damage(player, "physical", 1, source="深渊")
            player.movement_stopped = True
            player.steps_remaining = 0

    def _apply_collapsed_room(self, player: Player, room: PlacedRoom) -> None:
        first = not room.data.get("collapsed_resolved")
        room.data["collapsed_resolved"] = True
        traitor = player.role == "traitor"
        if first and not traitor:
            if self._resolve_check(player, "speed", 5, "塌方房间速度检定"):
                self._log(f"{player.name} 避开了塌方。")
                return
        elif not self.prompter.confirm("塌方房间", "是否故意落入地下室？英雄仍须承受一枚骰子的物理伤害。"):
            return
        if not traitor:
            self.deal_dice_damage(player, "physical", 1, source="塌方房间")
        if player.dead:
            return
        below = room.data.get("below_key")
        if below not in self.state.board or self._is_collapsed(below):
            below = None
            template = self._draw_room_template(-1)
            if template:
                # 抽牌已摘出牌堆；放置助手负责消费待放牌，先归入待放队列。
                self.state.room_deck.insert(0, template.id)
                for anchor in sorted(self.state.board.values(), key=lambda r: r.key):
                    if anchor.floor == -1 and not self._is_collapsed(anchor.key):
                        below = self._attach_template_adjacent(template.id, anchor.key)
                        if below:
                            break
                if not below:
                    self.state.room_deck.remove(template.id)
                    self.state.room_discard.append(template.id)
            if not below:
                choices = [key for key, r in sorted(self.state.board.items())
                           if r.floor == -1 and not self._is_collapsed(key)]
                if not choices:
                    self._log("地下室没有可落脚的房间。")
                    return
                index = self.prompter.choose_from_list("塌方落点", "选择地下室落点。", [self.state.board[key].name for key in choices])
                below = choices[0 if index is None else index]
            room.data["below_key"] = below
            self.spawn_token("below_collapsed_room", label="塌方下方", role="marker", room_key=below)
        self._log("坍塌的地板把探险者送入下方的地下室房间。")
        self._move_to_room(player, below, via_effect=True)

    def _apply_tower(self, player: Player, room: PlacedRoom) -> None:
        if self._barrier_config(room):
            return
        self._log("塔楼风很大，需要稳住脚步。")
        if not self._resolve_check(player, "speed", 4, "塔楼检定"):
            self._deal_damage(player, "physical", 1, source="塔楼")

    def _apply_catacombs(self, player: Player, room: PlacedRoom) -> None:
        """地下墓穴：障碍房间。

        权威原文（BetrayalHouseHill_v4.2.pdf p2）：
            "Vault, Tower, Chasm, Catacombs — These are all barrier rooms.
             You may attempt once per turn to make the trait roll to be able
             to cross the room. ... Crossing the barrier doesn't count as
             moving a space. Monsters ignore barriers."

        已满足的部分：
            - "Monsters ignore barriers"：怪物不走 _apply_room_effect 通道，自动成立。
        尚未实现的部分（依赖「房间两侧」概念，需改移动系统，见优化方案第 2 步）：
            - 跨越障碍不消耗移动格
            - 未跨越时不能与房间另一侧的玩家交互
            - 每回合只能尝试一次

        待确认：规则书只写 "the trait roll"，未指定属性与目标值（印在实体房间牌上）。
        此处沿用同类跨越型障碍（深渊 / 塔楼）的 speed 4，确认实体牌后需校正。
        """
        if self._barrier_config(room):
            return
        self._log("地下墓穴的通道很窄，需要侧身挤过去。")
        if not self._resolve_check(player, "speed", 4, "地下墓穴检定"):
            self._deal_damage(player, "physical", 1, source="地下墓穴")
            player.movement_stopped = True
            player.steps_remaining = 0

    def _move_to_room(self, player: Player, target_key: str, via_effect: bool = False) -> None:
        # 允许传模板 id（如 "basement_landing"），统一解析为板块 key
        target_key = self._link_target_key(target_key) or target_key
        if target_key not in self.state.board:
            return
        player.room_key = target_key
        self._barrier_choose_arrival(player, self.state.board[target_key])
        if via_effect:
            self._log(f"{player.name} 被移动到 {self.state.board[target_key].name}。")
        else:
            self._log(f"{player.name} 移动到 {self.state.board[target_key].name}。")
        # 剧本可跟随移动（剧本 3 p14：背着青蛙走，蛙跟着主人）。
        self._mode_handler().on_player_moved(self, player)
        self._resolve_room_entry_if_needed(player)
