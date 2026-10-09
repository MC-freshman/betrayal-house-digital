"""CarnivorousIvyMode（剧本 7）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class CarnivorousIvyMode(GenericModeHandler):
    """剧本 7 食人常春藤（Carnivorous Ivy）。

    权威原文：英雄手册 p18 / 叛徒手册 p89。

    本剧本此前只有一份"看起来对"的数据（爬行物尖端模板 + 三个行动），
    但机制全部没接：藤蔓不会抓人、根/尖端不配对、喷雾造不出、尖端被
    击败不释放人质、没有人被拖回根部吞噬。本次补齐的机制：

    · 爬行藤（Creeper）= 一对令牌：Root（根，永远不离开所在房间，不可
      攻击不可被攻击）+ Tip（尖端，会移动、会攻击）。尖端用怪物模板
      creeper_tip 表示，根用 marker 令牌表示，令牌 data 记录配对的尖端。
    · 开场布藤：p89 "Set aside a number of pairs of Root and Tip tokens
      (orange) equal to twice the number of players (up to a maximum of
      10 pairs)"。只有已在场的爬行房间能放根（每房最多一对）；多余的对
      留到后续新房间被发现时再放（on_room_discovered）。
    · 抓人（p89）：尖端击败英雄不造成伤害——英雄被抓住、掉光物品（留在
      原房间），不能移动；其他尖端不会攻击被抓者；英雄可以攻击抓自己的
      尖端，赢了尖端被击晕并松手（可以继续移动行动），输了回合结束。
    · 拖回根部（p89）：抓着人的尖端在它的回合开始时已经抓着人，就向配
      对的根移动 2 格（代替正常移动），并且不能攻击。
    · 吞噬（p89）："At the beginning of a creeper's turn, any grabbed
      characters at that creeper's Root are killed and mulched. A creeper
      that kills an explorer is removed from the game." 用新钩子
      on_monster_turn_start 实现。
    · 植物喷雾（p18）：英雄持书在研究实验室/厨房做 Knowledge 5+ 检定，
      全书只能造一瓶；造出后带着它走进有根或有尖端的房间，喷洒即自动杀
      死一整株（根和尖端都消失），不需要检定、代替本回合攻击。杀死的爬
      行藤数量 = 玩家数时英雄获胜。叛徒偷走喷雾后在深坑/熔炉房/地下湖
      结束回合可以把它毁掉——喷雾被毁即叛徒获胜，且无法再造。
    · 叛徒开局必须丢掉古书且之后不能捡（p89）；神秘电梯被尖端堵住时
      停用（p89）。

    已知简化（代码注释均已标注，非 bug）：
    · "Roots don't slow hero movement … Only Tips do"（p89）：引擎的移动
      结算本来就没有"房间里有怪物就减速"的规则，该条在此自动空转。
    · 铃铛对被抓英雄无效、灵应板对尖端无效（p89）：属于物品交互的边界
      规则，物品效果系统未按"是否被抓/对象类型"细分，暂不接。
    · 被抓英雄攻击尖端落败时"不掉血、仅回合结束"（p18）：引擎的败方
      反击伤害是全局规则，本剧本未做例外，被抓英雄落败仍会吃反击伤害。
    · 喷洒在行动框架里是"剧本行动"，与原版"代替本回合攻击"相比，英雄
      喷完还能继续普通攻击（对英雄有利，未收紧）。
    """

    mode = "carnivorous_ivy"

    CREEPER_TEMPLATE = "creeper_tip"
    ROOM_IDS = [
        "entrance_hall", "balcony", "bedroom", "chapel", "conservatory",
        "dining_room", "garden", "grand_staircase", "graveyard",
        "master_bedroom", "patio", "tower",
    ]

    # ------------------------------------------------------------- 内部工具
    def _tips(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.CREEPER_TEMPLATE]

    def _root_for_tip(self, engine: Any, tip: Any) -> Any | None:
        tip_id = str(getattr(tip, "id", ""))
        for token in engine.tokens_of_kind("root"):
            if str(token.data.get("tip_id", "")) == tip_id:
                return token
        return None

    def _grabbed_by(self, engine: Any, monster: Any) -> Any | None:
        """谁正被这只尖端抓着（没有返回 None）。"""
        tip_id = str(getattr(monster, "id", ""))
        grabbed = engine._haunt_flags().get("grabbed", {})
        for player in engine.state.players:
            if not player.dead and str(grabbed.get(str(player.id))) == tip_id:
                return player
        return None

    def _ungrab(self, engine: Any, player: Any) -> None:
        grabbed = engine._haunt_flags().get("grabbed", {})
        grabbed.pop(str(player.id), None)
        engine._haunt_flags()["grabbed"] = grabbed

    def _drop_carried_items(self, engine: Any, player: Any, room_key: str) -> None:
        """把英雄所有物品留在指定房间（被抓时掉装备，p89）。"""
        room_cards = engine.state.room_items.setdefault(room_key, [])
        for card_id in list(player.items):
            if card_id not in room_cards:
                room_cards.append(card_id)
        for card_id in list(player.companions):
            if card_id not in room_cards:
                room_cards.append(card_id)
        player.items.clear()
        player.companions.clear()

    def _pair_in_room(self, engine: Any, room_key: str) -> tuple[Any | None, Any | None]:
        """返回房间里的 (根令牌, 尖端怪物)。没有则对应为 None。"""
        root = next(iter(engine.tokens_in_room(room_key, "root")), None)
        tip = next((m for m in self._tips(engine) if m.room_key == room_key), None)
        return root, tip

    def _remove_pair(self, engine: Any, root: Any | None, tip: Any | None) -> None:
        """整株爬行藤离场：删尖端怪物 + 删根令牌。"""
        if tip is not None:
            engine.state.monsters = [
                m for m in engine.state.monsters if m is not tip and getattr(m, "id", None) != getattr(tip, "id", None)
            ]
        if root is not None:
            engine.remove_token(root.uid)
        # 被杀的爬行藤若正抓着人，人质就地获释（藤死了自然松手）
        grabbed = engine._haunt_flags().get("grabbed", {})
        tip_id = str(getattr(tip, "id", "")) if tip is not None else ""
        for pid in [pid for pid, tid in grabbed.items() if tid == tip_id]:
            player = next((p for p in engine.state.players if str(p.id) == pid), None)
            if player is not None:
                grabbed.pop(pid, None)
                player.movement_stopped = False
        engine._haunt_flags()["grabbed"] = grabbed

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        rule = haunt.rule_data or {}
        specs = [s for s in rule.get("monsters", []) if s.get("template_id") == self.CREEPER_TEMPLATE]
        spec = specs[0] if specs else {}
        players = len(engine.state.players)
        budget = min(players * 2, 10)  # p89：两倍玩家数（上限 10 对）
        board_ids = {room.template_id for room in engine.state.board.values()}
        candidates = [rid for rid in self.ROOM_IDS if rid in board_ids]
        engine._haunt_flags().setdefault("grabbed", {})
        engine._haunt_flags()["ivy_budget"] = budget
        engine._log(f"食人常春藤：备下 {budget} 对根与尖端。")

        # p89：叛徒开局若持有古书必须丢弃，之后不能再捡（引擎
        # item_pickup_blocked 钩子负责拦截重拾）。
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and "omen_book" in traitor.items:
            engine._discard_card_from_player(traitor, "omen_book", return_to_room=True)
            engine._log(f"叛徒{traitor.name}被迫丢下了古书。")

        # 为每只已在场的爬行藤尖端（spawn: deferred 时场上还没有，由本
        # handler 全权布藤）在其房间放下配对的根。引擎的 _spawn_haunt_
        # monsters 对 deferred 规格不生成怪物，所以这里先补生成，再放根。
        placed = 0
        for candidate in candidates:
            if placed >= budget:
                break
            key = next(
                (k for k, room in engine.state.board.items()
                 if room.template_id == candidate and not engine.tokens_in_room(k, "root")),
                None,
            )
            if key is None:
                continue
            tip = engine._spawn_single_haunt_monster(spec, key)
            if tip is None:
                continue
            root = engine.spawn_token("root", label="藤蔓之根", role="marker", room_key=key)
            root.data["tip_id"] = tip.id
            placed += 1
            engine._log(f"一株爬行藤的根扎在了 {engine.state.board[key].name}。")
        engine._haunt_flags()["ivy_unplaced"] = budget - placed

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """p89：备用的根/尖端对在后续新爬行房间被发现时入场（每房最多一对）。"""
        if room.template_id not in self.ROOM_IDS:
            return
        if engine.tokens_in_room(room.key, "root"):
            return
        remaining = int(engine._haunt_flags().get("ivy_unplaced", 0))
        if remaining <= 0:
            return
        rule = (engine.state.haunt.rule_data or {}) if engine.state.haunt else {}
        specs = [s for s in rule.get("monsters", []) if s.get("template_id") == self.CREEPER_TEMPLATE]
        spec = specs[0] if specs else {}
        tip = engine._spawn_single_haunt_monster(spec, room.key)
        if tip is None:
            return
        root = engine.spawn_token("root", label="藤蔓之根", role="marker", room_key=room.key)
        root.data["tip_id"] = tip.id
        engine._haunt_flags()["ivy_unplaced"] = remaining - 1
        engine._log(f"藤蔓沿着{room.name}的墙壁蔓延开来——又一对根与尖端入场了。")

    # ------------------------------------------------------------- 回合开始
    def on_turn_start(self, engine: Any, player: Any) -> None:
        """被抓者：不能移动；若人已死或藤已亡则清理标记。"""
        grabbed = engine._haunt_flags().get("grabbed", {})
        if str(player.id) not in grabbed:
            return
        if player.dead:
            self._ungrab(engine, player)
            return
        player.movement_stopped = True  # 被藤蔓抓着，迈不出步子

    # ------------------------------------------------------------- 吞噬
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """p89：尖端回合开始时，若有人质在它根部，人被杀、藤也离场。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        victim = self._grabbed_by(engine, monster)
        root = self._root_for_tip(engine, monster)
        if victim is None or root is None:
            return False
        if victim.room_key != root.room_key:
            # 引擎只在"怪不在目标房"时才调 on_monster_move（`_resolve_monster_turns`
            # 里的 `len(path) > 1` 闸门），可抓着人的尖端恰恰总与猎物同房——拖拽
            # 永远不发生，人质被永久钉住、也不掉血（23 号 seed137/4p 实测 400 回合
            # 两边都收不了场：`往根部缩` 0 次、`没能挣脱` 363 次、位置全程冻结）。
            # 这里补一次向根部的拖拽。
            path = engine._shortest_path(monster.room_key, root.room_key)
            if len(path) > 1:
                dest = path[min(len(path) - 1, 2)]
                monster.room_key = dest
                victim.room_key = dest
                engine._log(f"拖着{victim.name}的藤蔓向根部爬去，来到{engine.state.board[dest].name}。")
                return True
            return False
        engine._log(f"{victim.name} 被拖回了藤蔓根部——他来不及呼救就被吞噬了！")
        self._ungrab(engine, victim)
        victim.dead = True
        engine._drop_inventory_on_death(victim)
        self._remove_pair(engine, root, monster)
        engine._log("吞噬了英雄的爬行藤心满意足地缩回泥土里，彻底消失。")
        engine.check_victory()
        return True  # 本怪物本回合不再行动

    # ------------------------------------------------------------- 移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """p89：抓着人的尖端不追人，而是向配对的根移动 2 格（携带人质）。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        carried = self._grabbed_by(engine, monster)
        if carried is None:
            return False  # 自由尖端：常规追人
        root = self._root_for_tip(engine, monster)
        if root is None:
            return False
        if monster.room_key == root.room_key:
            return True  # 已在根部，无需移动（下回合开始吞噬）
        path = engine._shortest_path(monster.room_key, root.room_key)
        if len(path) <= 1:
            return True
        dest = path[min(len(path) - 1, 2)]
        monster.room_key = dest
        carried.room_key = dest
        engine._log(f"拖着{carried.name}的藤蔓向根部爬去，来到{engine.state.board[dest].name}。")
        return True

    # ------------------------------------------------------------- 攻击
    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """p89：尖端只攻击没被抓住的英雄；赢了改为抓住而非伤害。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        if self._grabbed_by(engine, monster) is not None:
            engine._log(f"{monster.name} 拖着猎物，无法攻击。")
            return True
        grabbed = set(engine._haunt_flags().get("grabbed", {}).keys())
        victims = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead
            and p.room_key == monster.room_key
            and str(p.id) not in grabbed
        ]
        if not victims:
            # 本房间没有可抓的英雄；也不许引擎默认去打被抓者。
            return True
        victim = victims[0]
        vine_roll = engine._roll_monster_attack(monster, "might")
        hero_roll = engine._roll_attack(victim, "might")
        engine._log(f"{monster.name} 扑向 {victim.name}：{vine_roll} 对 {hero_roll}。")
        if vine_roll > hero_roll:
            # p89：不掉血，改为抓住 + 掉光物品
            self._drop_carried_items(engine, victim, monster.room_key)
            grabbed_state = engine._haunt_flags().get("grabbed", {})
            grabbed_state[str(victim.id)] = monster.id
            engine._haunt_flags()["grabbed"] = grabbed_state
            engine._log(f"藤蔓缠住了 {victim.name}！他掉落了所有物品，被拖向根部……")
        elif vine_roll < hero_roll:
            engine._stun_monster(monster, 1)
            engine._log(f"{victim.name} 挣开了藤蔓，把它打得缩了回去。")
        else:
            engine._log("藤蔓与英雄僵持不下，谁也没占到便宜。")
        return True

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p18/p89：英雄击败尖端 → 击晕并松手（人质获释，可继续行动）。"""
        if _monster_id(monster) != self.CREEPER_TEMPLATE:
            return False
        carried = self._grabbed_by(engine, monster)
        if carried is not None:
            self._ungrab(engine, carried)
            carried.movement_stopped = False
            engine._log(f"藤蔓被打晕松开了{carried.name}——他恢复了自由！")
        return False  # 走引擎默认：击晕一回合

    # ------------------------------------------------------------- 行动
    def item_pickup_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        """p89：叛徒开局被迫丢下的古书，之后不能再捡起来。"""
        return card_id == "omen_book" and player.role == "traitor"

    def mystic_elevator_blocked(self, engine: Any, player: Any) -> bool:
        """p89：尖端进入神秘电梯后，电梯停用直到它离开。"""
        return any(
            _monster_id(m) == self.CREEPER_TEMPLATE and m.room_key == player.room_key
            for m in engine.state.monsters
        )

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """古书还压在预兆牌堆里时，英雄必须去翻新房间把它抽出来。

        p18 的英雄胜利线是"持书 + 研究实验室/厨房 + 知识 5+ 造喷雾"，书
        整局不进场整条链就断掉：实测 seed101/4p、5p 两局里书始终留在预兆
        牌堆（既没人抽到、也没掉在地上），全局一次剧本行动都没出现过，
        173 回合被藤蔓吃光。规则允许继续探索抽预兆，所以让机器人像人一样
        先去把书翻出来。喷雾已造出/已被毁则不必再找（p18：毁掉后不能重造）。
        """
        if player.dead or player.role != "hero":
            return False
        flags = engine._haunt_flags()
        if flags.get("plant_spray_created") or flags.get("plant_spray_destroyed"):
            return False
        return "omen_book" in engine.state.card_decks.get("omen", [])

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """没拿着关键道具时，相关行动的"目的地"不作数。

        · 造喷雾要持书（requires: omen_book）。不挡的话全体英雄都往研究
          实验室/厨房挤，而只有持书的人做得成检定。
        · 毁喷雾要叛徒先把喷雾偷到手（p89）。不挡的话叛徒把深渊/熔炉房/
          地下湖当常驻目标来回巡视空房（与 9 号"毁圣徽"同款问题）。
        """
        if action_id == "make_plant_spray" and "omen_book" not in player.items:
            return True
        if action_id == "destroy_spray" and not engine.tokens_held_by(player.id, "plant_spray"):
            return True
        return False

    def bot_goal_suppressed(self, engine: Any, player: Any) -> bool:
        """叛徒没抢到喷雾时没有剧本目标房间（见 bot_action_blocked）。

        它的取胜路径只剩"杀光英雄"（p89），正确行为是转头追杀英雄；不抑制
        的话 key_rooms 保底会把实验室/厨房/三间销毁房当成目的地。
        """
        return player.role == "traitor" and not engine.tokens_held_by(player.id, "plant_spray")

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """拿着喷雾的人去找爬行藤（根或尖端）所在的房间喷杀（p18）。

        喷杀不需要检定，但要"走进有根或尖端的房间"才能按住喷雾（引擎在
        available_actions 里按这条过滤）。spray_creeper 行动没有 rooms
        字段，静态表表达不了"藤现在在哪"，所以按令牌/怪物实时取。
        """
        if player.dead or player.role != "hero":
            return []
        if not engine.tokens_held_by(player.id, "plant_spray"):
            return []
        rooms: set[str] = set()
        for token in engine.tokens_of_kind("root"):
            if token.room_key:
                rooms.add(f"__room__{token.room_key}")
        for monster in engine.state.monsters:
            if _monster_id(monster) == self.CREEPER_TEMPLATE:
                rooms.add(f"__room__{monster.room_key}")
        return sorted(rooms)

    def bot_captor_monster(self, engine: Any, player: Any) -> Any | None:
        """抓着该玩家的爬行藤尖端（bot_ai 会让它优先攻击这只，赢即脱身）。

        p18："You can also make an attack against the Tip ... If you defeat
        the Tip, it is stunned and releases you." 同房间往往有多只尖端，
        不指定目标时机器人按列表顺序打错对象，永远脱不了身——实测
        seed127/5p 在入口大厅被钉了 180 回合、整局 245 回合。
        """
        grabbed = engine._haunt_flags().get("grabbed", {})
        monster_id = grabbed.get(str(player.id))
        if monster_id is None:
            return None
        return next(
            (m for m in engine.state.monsters if str(getattr(m, "id", "")) == str(monster_id)),
            None,
        )

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "spray_creeper":
                held = engine.tokens_held_by(player.id, "plant_spray")
                root, tip = self._pair_in_room(engine, player.room_key)
                if not held or (root is None and tip is None):
                    continue  # 没喷雾 / 房间里没有根或尖端
            if action.id == "destroy_spray":
                if not engine.tokens_held_by(player.id, "plant_spray"):
                    continue  # 喷雾不在叛徒手上（p89：要先偷到手才能毁）
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "make_plant_spray":
            # 前置在 rule_data 里已由通用框架校验（持书、房间、只能造一次）；
            # 这里只管"检定成功就发令牌"。
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine._haunt_flags().get("plant_spray_created"):
                token = engine.spawn_token(
                    "plant_spray", label="植物喷雾", role="carried", holder=player.id
                )
                engine._log(f"{player.name} 调配出了植物喷雾——这是全村唯一的希望！")
            return ok

        if action_id == "spray_creeper":
            if not engine.tokens_held_by(player.id, "plant_spray"):
                engine._log("植物喷雾不在你手上。")
                return False
            root, tip = self._pair_in_room(engine, player.room_key)
            if root is None and tip is None:
                engine._log("这个房间里没有爬行藤可喷。")
                return False
            # 杀掉一整株（根、尖端同时离场）；自动成功，不掷骰
            self._remove_pair(engine, root, tip)
            engine._advance_haunt_track("creepers_killed", 1)
            killed = engine._haunt_track_value("creepers_killed")
            engine._log(
                f"{player.name} 喷出的药剂让一整株爬行藤当场枯萎！"
                f"（已消灭 {killed} 株）"
            )
            return True

        if action_id == "destroy_spray":
            if not engine.tokens_held_by(player.id, "plant_spray"):
                engine._log("要先从英雄手里偷到植物喷雾才能毁掉它。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine._haunt_flags().get("plant_spray_destroyed"):
                token = next(iter(engine.tokens_held_by(player.id, "plant_spray")), None)
                if token is not None:
                    engine.remove_token(token.uid)
                engine._log("植物喷雾被丢进深渊，瞬间被吞没了。")
            return ok

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if engine._haunt_flags().get("plant_spray_destroyed"):
            engine._set_winner("traitor", "英雄们唯一的武器——植物喷雾——被毁掉了。")
            return True
        if engine._haunt_track_value("creepers_killed") >= engine._haunt_track_target("creepers_killed"):
            engine._set_winner("heroes", "喷杀的爬行藤已达目标数，余下的藤蔓仓皇退去。")
            return True
        # p89 只规定两种终局（英雄全灭 / 喷雾被毁）：藤蔓自主行动，
        # 叛徒阵亡【不】构成英雄胜利。吸收引擎兜底，游戏继续。
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有英雄都被藤蔓吞噬了。")
            return True
        return True
